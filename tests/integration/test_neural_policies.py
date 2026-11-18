"""F5: saved networks as policies in episodes, the inspector activations and the CLI."""

from pathlib import Path

import numpy as np
import pytest
from typer.testing import CliRunner

from neuroeco.application.evaluation import EpisodeIdentity, run_episode
from neuroeco.application.seeding import Purpose
from neuroeco.application.session import inspect_agent, run_session
from neuroeco.bootstrap import build_policy, build_runtime
from neuroeco.domain.neural import (
    PREDATOR_BASE,
    PREY_BASE,
    NeuralNetwork,
    NeuralPolicy,
    lecun_genome,
)
from neuroeco.domain.simulator import StepTrace
from neuroeco.infrastructure.model_store import ModelError, save_model
from neuroeco.presentation.cli import app

CONFIGS = Path(__file__).resolve().parents[2] / "configs"
IDENTITY = EpisodeIdentity(Purpose.PILOT, seed_group=0, item=7)


@pytest.fixture
def models(tmp_path) -> dict[str, Path]:
    paths = {}
    for species, spec in (("prey", PREY_BASE), ("predator", PREDATOR_BASE)):
        network = NeuralNetwork(spec, lecun_genome(spec, np.random.default_rng(len(species))))
        paths[species] = tmp_path / f"{species}.npz"
        save_model(paths[species], network)
    return paths


def runtime(t_max: int = 120):
    return build_runtime("A", (f"world.t_max={t_max}",), CONFIGS)


def test_saved_networks_run_an_episode_and_reproduce_it(models) -> None:
    rt = runtime()
    config = rt.config
    prey = build_policy(f"model:{models['prey']}", "prey", config)
    predator = build_policy(f"model:{models['predator']}", "predator", config)
    assert isinstance(prey, NeuralPolicy) and isinstance(predator, NeuralPolicy)
    first = run_episode(config.world, prey, predator, rt.registry, IDENTITY)
    again = run_episode(
        config.world,
        build_policy(f"model:{models['prey']}", "prey", config),
        build_policy(f"model:{models['predator']}", "predator", config),
        rt.registry,
        IDENTITY,
    )
    assert first.metrics == again.metrics


def test_a_model_of_the_other_species_is_rejected(models) -> None:
    with pytest.raises(ValueError, match="is a predator model, not a prey one"):
        build_policy(f"model:{models['predator']}", "prey", runtime().config)


def test_a_missing_model_is_rejected(tmp_path) -> None:
    with pytest.raises(ModelError, match="not a readable model"):
        build_policy(f"model:{tmp_path / 'none.npz'}", "prey", runtime().config)


def test_the_inspector_shows_the_activations_of_the_decision(models) -> None:
    rt = runtime(40)
    config = rt.config
    prey = build_policy(f"model:{models['prey']}", "prey", config)
    predator = build_policy("rules", "predator", config)
    frames = []

    class Recorder:
        def start(self, frame) -> None:
            frames.append(frame)

        def step(self, frame) -> None:
            frames.append(frame)

    checked = 0

    def compare(trace: StepTrace) -> None:
        nonlocal checked
        frame = frames[-1]
        for i in range(trace.world.prey.size):
            view = inspect_agent(frame, config.world, "prey", i, prey.network)
            layers = prey.network.activations(trace.prey_observations[i : i + 1])
            expected = [a[0] for a in layers[:-1]]
            assert all(
                np.array_equal(v, e) for v, e in zip(view.activations, expected, strict=True)
            )
            assert np.allclose(layers[-1][0], trace.prey_actions[i], rtol=0, atol=1e-12)
            assert [len(a) for a in view.activations] == [16, 16]
            checked += 1

    run_session(config.world, prey, predator, rt.registry, IDENTITY, Recorder(), compare)
    assert checked > 0


def test_the_inspector_rejects_a_network_that_did_not_decide(models) -> None:
    rt = runtime(5)
    config = rt.config
    frames = []

    class Recorder:
        def start(self, frame) -> None:
            frames.append(frame)

        def step(self, frame) -> None:
            frames.append(frame)

    rules = build_policy("rules", "prey", config)
    predator = build_policy("rules", "predator", config)
    run_session(config.world, rules, predator, rt.registry, IDENTITY, Recorder())
    other = build_policy(f"model:{models['prey']}", "prey", config).network
    with pytest.raises(ValueError, match="does not reproduce the recorded action"):
        inspect_agent(frames[-1], config.world, "prey", 0, other)


def test_run_command_accepts_models(models) -> None:
    result = CliRunner().invoke(
        app,
        [
            "run",
            "--scenario",
            "A",
            "--prey",
            f"model:{models['prey']}",
            "--predator",
            f"model:{models['predator']}",
            "--episode",
            "1",
            "--set",
            "world.t_max=30",
        ],
    )
    assert result.exit_code == 0, result.output
