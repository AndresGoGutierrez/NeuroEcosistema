"""F6: training use case, early termination (ADR-015), model selection and DET-3 (ADR-016)."""

import dataclasses
from pathlib import Path

import numpy as np
import pytest

from neuroeco.application.evaluation import EpisodeIdentity, run_episode
from neuroeco.application.seeding import Purpose, SeedRegistry
from neuroeco.application.training import (
    Checkpoint,
    EpisodeTask,
    TrainingSpec,
    capture_radius,
    episode_fitness,
    opponent_policy,
    select_model,
    train,
    validation_generations,
)
from neuroeco.bootstrap import build_policy, build_runtime
from neuroeco.domain.neural import PREDATOR_COMPACT, PREY_COMPACT, lecun_genome
from neuroeco.infrastructure.executors import ProcessExecutor, SequentialExecutor

CONFIGS = Path(__file__).resolve().parents[2] / "configs"


def config(scenario="A", t_max=150):
    return build_runtime(scenario, (f"world.t_max={t_max}",), CONFIGS).config


def spec(**changes) -> TrainingSpec:
    values = {
        "name": "test",
        "species": "prey",
        "architecture": "prey_compact",
        "scenario": "A",
        "seed_group": 900,
        "run": 0,
        "population": 6,
        "elite": 1,
        "tournament": 2,
        "sigma": 0.1,
        "episodes": 2,
        "validation_episodes": 2,
        "generations": 3,
        "validation_interval": 2,
    }
    return TrainingSpec(**{**values, **changes})


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"species": "plant"}, "species"),
        ({"architecture": "prey_huge"}, "unknown architecture"),
        ({"architecture": "predator_base"}, "not a prey network"),
        ({"episodes": 0}, "episodes"),
        ({"elite": 6}, "elite"),
        ({"curriculum_kappa": 2.0}, "only to predators"),
        (
            {"curriculum_kappa": 0.5, "species": "predator", "architecture": "predator_base"},
            "kappa",
        ),
    ],
)
def test_spec_is_validated(changes, message) -> None:
    with pytest.raises(ValueError, match=message):
        spec(**changes)


def test_validation_happens_every_k_val_generations_and_at_the_end() -> None:
    assert validation_generations(spec(generations=7, validation_interval=3)) == {0, 3, 6}
    assert validation_generations(spec(generations=8, validation_interval=3)) == {0, 3, 6, 7}


def test_curriculum_shrinks_the_capture_radius_linearly() -> None:
    world = config().world
    s = spec(
        species="predator",
        architecture="predator_compact",
        curriculum_kappa=2.0,
        curriculum_generations=4,
    )
    radii = [capture_radius(s, world, g) for g in range(6)]
    r = world.capture_radius
    assert radii == pytest.approx([2 * r, 1.75 * r, 1.5 * r, 1.25 * r, r, r])
    assert capture_radius(spec(), world, 0) == r


def test_model_selection_takes_the_highest_validation_and_the_earliest_on_ties() -> None:
    def checkpoint(g, f_val):
        return Checkpoint(g, np.zeros(1), 0.0, f_val)

    chosen = select_model((checkpoint(0, 0.2), checkpoint(5, 0.4), checkpoint(10, 0.4)))
    assert chosen.generation == 5


@pytest.mark.parametrize("item", range(4))
def test_early_termination_does_not_change_the_predator_fitness(item) -> None:
    """ADR-015: same F_pred with and without ending when every predator is dead."""
    cfg = config("C", t_max=400)
    genome = lecun_genome(PREDATOR_COMPACT, np.random.default_rng(item))
    task = EpisodeTask(
        cfg.project_seed,
        cfg.world,
        cfg.rules,
        "predator",
        "predator_compact",
        genome,
        EpisodeIdentity(Purpose.TRAIN, 900, 0, 0, item),
    )
    from neuroeco.domain.neural import NeuralNetwork, NeuralPolicy

    learner = NeuralPolicy(NeuralNetwork(PREDATOR_COMPACT, genome))
    prey = opponent_policy("predator", cfg.world, cfg.rules)
    registry = SeedRegistry(cfg.project_seed)
    full = run_episode(cfg.world, prey, learner, registry, task.identity)
    early = run_episode(
        cfg.world, prey, learner, registry, task.identity, stop_without_predators=True
    )
    assert early.metrics.captured_fraction == full.metrics.captured_fraction
    assert early.record.steps <= full.record.steps
    assert episode_fitness(task) == full.metrics.captured_fraction.value


def test_episode_fitness_of_prey_is_the_mean_survival() -> None:
    cfg = config()
    genome = lecun_genome(PREY_COMPACT, np.random.default_rng(1))
    identity = EpisodeIdentity(Purpose.TRAIN, 900, 0, 0, 0)
    task = EpisodeTask(
        cfg.project_seed, cfg.world, cfg.rules, "prey", "prey_compact", genome, identity
    )
    from neuroeco.domain.neural import NeuralNetwork, NeuralPolicy

    expected = run_episode(
        cfg.world,
        NeuralPolicy(NeuralNetwork(PREY_COMPACT, genome)),
        build_policy("rules", "predator", cfg),
        SeedRegistry(cfg.project_seed),
        identity,
    )
    assert episode_fitness(task) == expected.metrics.prey_survival.value


def test_training_runs_validates_and_selects() -> None:
    result = train(spec(), config(), SequentialExecutor())
    assert [r.summary.generation for r in result.generations] == [0, 1, 2]
    assert [c.generation for c in result.checkpoints] == [0, 2]
    assert result.final_elite.generation == 2
    assert result.selected.f_val == max(c.f_val for c in result.checkpoints)
    assert [r.f_val is not None for r in result.generations] == [True, False, True]


def results_of(executor) -> tuple:
    result = train(spec(), config(), executor)
    return (
        [dataclasses.astuple(r.summary) for r in result.generations],
        [(c.generation, c.genome.tobytes(), c.f_train, c.f_val) for c in result.checkpoints],
    )


def test_det3_sequential_one_and_four_workers_are_identical() -> None:
    """DET-3 (ADR-016): the same run with 0, 1 and 4 workers, bit for bit."""
    sequential = results_of(SequentialExecutor())
    with ProcessExecutor(1) as one:
        assert results_of(one) == sequential
    with ProcessExecutor(4) as four:
        assert results_of(four) == sequential
        pools = four.worker_thread_pools()
    assert all(p["num_threads"] == 1 for worker in pools for p in worker)
