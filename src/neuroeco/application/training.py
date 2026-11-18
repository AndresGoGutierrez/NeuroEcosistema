"""Use case: train one species against the rule-based opponent (ADR-006, ADR-026, ADR-027).

Seeds (ADR-028):

- population: GA_INIT of (TRAIN, seed_group, run, 0, 0);
- variation of generation g: GA_VARIATION of (TRAIN, seed_group, run, g, 0);
- training episodes of generation g: (TRAIN, seed_group, run, g, e), e < E, common to every
  genome of the generation (F_train, the only selection signal);
- validation episodes: (VALIDATION, 0, 0, 0, v), v < V, fixed and shared by every run.

Each genome controls a cloned team of its species; its fitness is the mean over its episodes of
F_prey (mean survival time / T_max) or F_pred (captures / initial prey). Training and validation
episodes of predators also end when every predator is dead (ADR-015). Every k_val generations,
and in the last one, the best genome of the generation is validated and checkpointed; the
selected model is the checkpoint with the highest F_val, the earliest on ties (ADR-026).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from neuroeco.application.configs import ResolvedConfig, RuleParams
from neuroeco.application.evaluation import EpisodeIdentity, run_episode
from neuroeco.application.ports import TaskExecutor
from neuroeco.application.seeding import Purpose, SeedRegistry, Stream
from neuroeco.domain.evolution import GAParams, GenerationSummary, GeneticAlgorithm
from neuroeco.domain.neural import (
    ARCHITECTURES,
    NeuralNetwork,
    NeuralPolicy,
    saturation_stats,
)
from neuroeco.domain.params import WorldParams
from neuroeco.domain.policies import Policy, RuleBasedPredatorPolicy, RuleBasedPreyPolicy

SPECIES = ("prey", "predator")


@dataclass(frozen=True)
class TrainingSpec:
    """One training run (values of N, E, V, G, sigma and k_val come from P2)."""

    name: str
    species: str
    architecture: str
    scenario: str
    seed_group: int
    run: int
    population: int
    elite: int
    tournament: int
    sigma: float
    episodes: int  # E
    validation_episodes: int  # V
    generations: int  # G
    validation_interval: int  # k_val
    curriculum_kappa: float = 1.0  # initial capture radius factor (ADR-026); 1 = no curriculum
    curriculum_generations: int = 0  # G_c

    def __post_init__(self) -> None:
        if self.species not in SPECIES:
            raise ValueError(f"species must be one of {SPECIES}")
        if self.architecture not in ARCHITECTURES:
            raise ValueError(f"unknown architecture {self.architecture!r}")
        if ARCHITECTURES[self.architecture].schema.species != self.species:
            raise ValueError(f"{self.architecture} is not a {self.species} network")
        for name in ("episodes", "validation_episodes", "generations", "validation_interval"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be >= 1")
        if self.seed_group < 0 or self.run < 0:
            raise ValueError("seed_group and run must be >= 0")
        if self.curriculum_kappa < 1.0 or self.curriculum_generations < 0:
            raise ValueError("the curriculum needs kappa >= 1 and G_c >= 0")
        if self.curriculum_kappa > 1.0 and self.species != "predator":
            raise ValueError("the curriculum applies only to predators (ADR-026)")
        GAParams(self.population, self.elite, self.tournament, self.sigma)

    @property
    def ga_params(self) -> GAParams:
        return GAParams(self.population, self.elite, self.tournament, self.sigma)


@dataclass(frozen=True)
class EpisodeTask:
    """One episode of one genome; everything a worker process needs (picklable)."""

    project_seed: int
    world: WorldParams
    rules: RuleParams
    species: str
    architecture: str
    genome: np.ndarray
    identity: EpisodeIdentity


def opponent_policy(species: str, world: WorldParams, rules: RuleParams) -> Policy:
    """The rule-based policy of the other species (ADR-006, stage 1)."""
    if species == "prey":
        return RuleBasedPredatorPolicy(world.predator.omega_max, rules.predator.cruise_fraction)
    return RuleBasedPreyPolicy(
        world.prey.omega_max, rules.prey.flee_threshold, rules.prey.cruise_fraction
    )


def episode_fitness(task: EpisodeTask) -> float:
    """F_prey or F_pred of one episode (ADR-026); runs in worker processes."""
    network = NeuralNetwork(ARCHITECTURES[task.architecture], task.genome)
    learner = NeuralPolicy(network)
    opponent = opponent_policy(task.species, task.world, task.rules)
    prey, predator = (learner, opponent) if task.species == "prey" else (opponent, learner)
    result = run_episode(
        task.world,
        prey,
        predator,
        SeedRegistry(task.project_seed),
        task.identity,
        stop_without_predators=task.species == "predator",
    )
    metrics = result.metrics
    ratio = metrics.prey_survival if task.species == "prey" else metrics.captured_fraction
    return ratio.value


def capture_radius(spec: TrainingSpec, world: WorldParams, generation: int) -> float:
    """Training capture radius under the conditional curriculum (ADR-026)."""
    if spec.curriculum_kappa == 1.0 or generation >= spec.curriculum_generations:
        return world.capture_radius
    share = generation / spec.curriculum_generations
    factor = spec.curriculum_kappa + (1.0 - spec.curriculum_kappa) * share
    return world.capture_radius * factor


@dataclass(frozen=True)
class Checkpoint:
    generation: int
    genome: np.ndarray
    f_train: float
    f_val: float
    s1: tuple[float, ...] | None = None
    s2: tuple[float, ...] | None = None


@dataclass(frozen=True)
class GenerationRecord:
    summary: GenerationSummary
    capture_radius: float
    f_val: float | None


@dataclass(frozen=True)
class TrainingResult:
    spec: TrainingSpec
    generations: tuple[GenerationRecord, ...]
    checkpoints: tuple[Checkpoint, ...]
    selected: Checkpoint
    final_elite: Checkpoint


def select_model(checkpoints: tuple[Checkpoint, ...]) -> Checkpoint:
    """Highest F_val; the earliest checkpoint on ties (ADR-026)."""
    best = checkpoints[0]
    for checkpoint in checkpoints[1:]:
        if checkpoint.f_val > best.f_val:
            best = checkpoint
    return best


def validation_generations(spec: TrainingSpec) -> set[int]:
    last = spec.generations - 1
    return {g for g in range(spec.generations) if g % spec.validation_interval == 0} | {last}


def train(
    spec: TrainingSpec,
    config: ResolvedConfig,
    executor: TaskExecutor,
    reference: np.ndarray | None = None,
    on_generation: Callable[[GenerationRecord], None] | None = None,
) -> TrainingResult:
    """Run ``spec.generations`` generations; ``reference`` observations monitor S1/S2."""
    registry = SeedRegistry(config.project_seed)
    network_spec = ARCHITECTURES[spec.architecture]
    init = registry.generator(Purpose.TRAIN, spec.seed_group, spec.run, 0, 0, Stream.GA_INIT)
    algorithm = GeneticAlgorithm(network_spec, spec.ga_params, init)
    validate_at = validation_generations(spec)

    def tasks(genomes, world, purpose, generation, count, group, run):
        return [
            EpisodeTask(
                config.project_seed,
                world,
                config.rules,
                spec.species,
                spec.architecture,
                np.array(genome),
                EpisodeIdentity(purpose, group, run, generation, item),
            )
            for genome in genomes
            for item in range(count)
        ]

    records: list[GenerationRecord] = []
    checkpoints: list[Checkpoint] = []
    for generation in range(spec.generations):
        radius = capture_radius(spec, config.world, generation)
        world = dataclasses.replace(config.world, capture_radius=radius)
        genomes = algorithm.ask()
        values = executor.map(
            episode_fitness,
            tasks(
                genomes,
                world,
                Purpose.TRAIN,
                generation,
                spec.episodes,
                spec.seed_group,
                spec.run,
            ),
        )
        fitness = np.asarray(values).reshape(spec.population, spec.episodes).mean(axis=1)
        best = int(algorithm.ranking(fitness)[0])
        best_genome = np.array(genomes[best])

        f_val = None
        if generation in validate_at:
            # validation always uses the nominal capture radius (ADR-026)
            validation = executor.map(
                episode_fitness,
                tasks(
                    [best_genome],
                    config.world,
                    Purpose.VALIDATION,
                    0,
                    spec.validation_episodes,
                    0,
                    0,
                ),
            )
            f_val = float(np.mean(validation))
            stats = (
                saturation_stats(NeuralNetwork(network_spec, best_genome), reference)
                if reference is not None
                else None
            )
            checkpoints.append(
                Checkpoint(
                    generation,
                    best_genome,
                    float(fitness[best]),
                    f_val,
                    None if stats is None else stats.s1,
                    None if stats is None else stats.s2,
                )
            )

        variation = registry.generator(
            Purpose.TRAIN, spec.seed_group, spec.run, generation, 0, Stream.GA_VARIATION
        )
        summary = algorithm.tell(fitness, variation)
        record = GenerationRecord(summary, radius, f_val)
        records.append(record)
        if on_generation is not None:
            on_generation(record)

    done = tuple(checkpoints)
    return TrainingResult(spec, tuple(records), done, select_model(done), done[-1])
