"""Formal experiments (F7 protocol, F8): the runs to train and their test evaluation.

Configurations (ADR-004, ADR-005): prey_base and predator_base in A, B and C, and prey_compact
and predator_compact in A; R independent runs each, every configuration with its own seed_group
(ADR-013, ADR-028). Runs are ordered run index first, so a partial campaign stays balanced.

Test evaluation (ADR-017, ADR-019): every model is evaluated on the same ``test_episodes`` TEST
seeds of its scenario, against the opponents M0 (nominal rules), M1 and M2 (rule variants of
ADR-012), M3 (random) and M4 (each trained model of the other species, cross-play). The rule and
random policies of the learner's species are evaluated on the same seeds as references.
Primary metrics are integer numerators with a common denominator (ADR-014, ADR-017).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

import numpy as np

from neuroeco.application.configs import ResolvedConfig, RuleParams
from neuroeco.application.evaluation import EpisodeIdentity, run_episode
from neuroeco.application.seeding import Purpose, SeedRegistry
from neuroeco.application.training import TrainingSpec
from neuroeco.domain.neural import ARCHITECTURES, NeuralNetwork, NeuralPolicy
from neuroeco.domain.params import WorldParams
from neuroeco.domain.policies import (
    Policy,
    RandomPolicy,
    RuleBasedPredatorPolicy,
    RuleBasedPreyPolicy,
)

CONFIGURATIONS = (
    ("prey_base", "A"),
    ("prey_base", "B"),
    ("prey_base", "C"),
    ("predator_base", "A"),
    ("predator_base", "B"),
    ("predator_base", "C"),
    ("prey_compact", "A"),
    ("predator_compact", "A"),
)
OPPONENTS = ("M0", "M1", "M2", "M3")  # M4 (cross-play) is added per trained model


@dataclass(frozen=True)
class Protocol:
    """Values fixed by P2/P3 and pre-registered in F7 (ADR-035)."""

    runs: int  # R
    test_episodes: int
    first_seed_group: int
    population: int
    elite: int
    tournament: int
    episodes: int
    validation_episodes: int
    generations: int
    validation_interval: int
    sigma_prey_base: float
    sigma_predator_base: float
    sigma_prey_compact: float
    sigma_predator_compact: float
    curriculum_kappa: float
    curriculum_generations: int
    stage: str = "f8"  # "p3": the timing pilot of F6, seed groups 64-71 (ADR-028, ADR-035)

    def __post_init__(self) -> None:
        if self.runs < 1 or self.test_episodes < 1:
            raise ValueError("runs and test_episodes must be >= 1")
        if self.stage == "f8" and self.first_seed_group < 100:
            raise ValueError("formal seed groups start at 100")
        if self.stage == "p3" and (self.first_seed_group != 64 or self.runs != 1):
            raise ValueError("P3 uses seed groups 64-71 and one run per configuration")
        if self.stage not in ("f8", "p3"):
            raise ValueError(f"unknown stage {self.stage!r}")

    def sigma(self, architecture: str) -> float:
        return getattr(self, f"sigma_{architecture}")


def run_name(architecture: str, scenario: str, run: int, stage: str = "f8") -> str:
    return f"{stage}_{architecture}_{scenario}_r{run}"


def formal_specs(protocol: Protocol) -> list[TrainingSpec]:
    """Every formal run, run index first (balanced if the campaign stops early)."""
    specs = []
    for run in range(protocol.runs):
        for index, (architecture, scenario) in enumerate(CONFIGURATIONS):
            species = architecture.split("_")[0]
            curriculum = species == "predator" and protocol.curriculum_kappa > 1.0
            specs.append(
                TrainingSpec(
                    name=run_name(architecture, scenario, run, protocol.stage),
                    species=species,
                    architecture=architecture,
                    scenario=scenario,
                    seed_group=protocol.first_seed_group + index,
                    run=run,
                    population=protocol.population,
                    elite=protocol.elite,
                    tournament=protocol.tournament,
                    sigma=protocol.sigma(architecture),
                    episodes=protocol.episodes,
                    validation_episodes=protocol.validation_episodes,
                    generations=protocol.generations,
                    validation_interval=protocol.validation_interval,
                    curriculum_kappa=protocol.curriculum_kappa if curriculum else 1.0,
                    curriculum_generations=protocol.curriculum_generations if curriculum else 0,
                )
            )
    return specs


# ------------------------------------------------------------------ policies of an evaluation


@dataclass(frozen=True)
class PolicySpec:
    """A picklable description of a policy: rules (with a variant), random or a model."""

    kind: str  # "rules", "random" or "model"
    variant: str = "nominal"  # rules: nominal, low or high (ADR-012 variants)
    architecture: str = ""
    genome: np.ndarray | None = None


def rule_variant(species: str, rules: RuleParams, variant: str) -> RuleParams:
    """ADR-012: prey p_flee -0.1 / +0.1; predator u_cruise x0.75 / x1.25."""
    if variant == "nominal":
        return rules
    sign = {"low": -1, "high": 1}[variant]
    if species == "prey":
        flee = min(1.0, max(0.0, rules.prey.flee_threshold + 0.1 * sign))
        prey = dataclasses.replace(rules.prey, flee_threshold=flee)
        return dataclasses.replace(rules, prey=prey)
    cruise = min(1.0, rules.predator.cruise_fraction * (1.0 + 0.25 * sign))
    predator = dataclasses.replace(rules.predator, cruise_fraction=cruise)
    return dataclasses.replace(rules, predator=predator)


def build(spec: PolicySpec, species: str, world: WorldParams, rules: RuleParams) -> Policy:
    if spec.kind == "random":
        return RandomPolicy()
    if spec.kind == "model":
        return NeuralPolicy(NeuralNetwork(ARCHITECTURES[spec.architecture], spec.genome))
    r = rule_variant(species, rules, spec.variant)
    if species == "prey":
        return RuleBasedPreyPolicy(
            world.prey.omega_max, r.prey.flee_threshold, r.prey.cruise_fraction
        )
    return RuleBasedPredatorPolicy(world.predator.omega_max, r.predator.cruise_fraction)


def opponent_spec(opponent: str) -> PolicySpec:
    return {
        "M0": PolicySpec("rules"),
        "M1": PolicySpec("rules", "low"),
        "M2": PolicySpec("rules", "high"),
        "M3": PolicySpec("random"),
    }[opponent]


@dataclass(frozen=True)
class TestTask:
    project_seed: int
    world: WorldParams
    rules: RuleParams
    species: str  # the evaluated (learner) species
    learner: PolicySpec
    opponent: PolicySpec
    item: int


def test_episode(task: TestTask) -> dict[str, int]:
    """Integer numerators of one TEST episode (full termination rule, ADR-015)."""
    other = "predator" if task.species == "prey" else "prey"
    learner = build(task.learner, task.species, task.world, task.rules)
    opponent = build(task.opponent, other, task.world, task.rules)
    prey, predator = (learner, opponent) if task.species == "prey" else (opponent, learner)
    result = run_episode(
        task.world,
        prey,
        predator,
        SeedRegistry(task.project_seed),
        EpisodeIdentity(Purpose.TEST, 0, 0, 0, task.item),
    )
    m = result.metrics
    return {
        "survival_steps": m.prey_survival.numerator,
        "survival_denominator": m.prey_survival.denominator,
        "captures": m.captured_fraction.numerator,
        "capture_denominator": m.captured_fraction.denominator,
        "steps": m.steps,
    }


def test_tasks(
    config: ResolvedConfig,
    species: str,
    learner: PolicySpec,
    opponent: PolicySpec,
    episodes: int,
) -> list[TestTask]:
    return [
        TestTask(config.project_seed, config.world, config.rules, species, learner, opponent, e)
        for e in range(episodes)
    ]
