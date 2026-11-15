"""T1 (F2): session frames, HUD statistics and inspector values (ADR-031)."""

from pathlib import Path

import numpy as np
import pytest

from neuroeco.application.evaluation import EpisodeIdentity, run_episode
from neuroeco.application.seeding import Purpose
from neuroeco.application.session import (
    Frame,
    SessionTracker,
    initial_world,
    inspect_agent,
    run_session,
)
from neuroeco.bootstrap import build_policy, build_runtime
from neuroeco.domain.actions import decode_actions
from neuroeco.domain.perception import PREDATOR_SCHEMA, PREY_SCHEMA
from neuroeco.domain.simulator import StepTrace
from neuroeco.domain.state import NOT_DEAD
from support import state_digest

CONFIGS = Path(__file__).resolve().parents[3] / "configs"
IDENTITY = EpisodeIdentity(Purpose.PILOT, seed_group=0, item=4)


def setup(scenario: str, policy: str, t_max: int = 250):
    runtime = build_runtime(scenario, (f"world.t_max={t_max}",), CONFIGS)
    config = runtime.config
    return (
        config.world,
        build_policy(policy, "prey", config),
        build_policy(policy, "predator", config),
        runtime.registry,
    )


class Recorder:
    """Observer that keeps every frame it receives."""

    def __init__(self) -> None:
        self.frames: list[Frame] = []

    def start(self, frame: Frame) -> None:
        self.frames.append(frame)

    def step(self, frame: Frame) -> None:
        self.frames.append(frame)


@pytest.mark.parametrize("scenario", ["A", "B", "C"])
@pytest.mark.parametrize("policy", ["rules", "random"])
def test_session_does_not_change_the_episode(scenario, policy) -> None:
    params, prey, predator, registry = setup(scenario, policy)
    headless: list[str] = []
    expected = run_episode(
        params,
        prey,
        predator,
        registry,
        IDENTITY,
        on_step=lambda t: headless.append(state_digest(t.world)),
    )

    observed: list[str] = []
    recorder = Recorder()
    result = run_session(
        params,
        prey,
        predator,
        registry,
        IDENTITY,
        recorder,
        after_step=lambda t: observed.append(state_digest(t.world)),
    )
    assert observed == headless
    assert repr(result.metrics) == repr(expected.metrics)
    assert len(recorder.frames) == len(headless) + 1  # S_0 plus one frame per step


def test_initial_frame_is_s0_rebuilt_from_fresh_generators() -> None:
    params, *_, registry = setup("A", "rules")
    first = initial_world(params, registry, IDENTITY)
    second = initial_world(params, registry, IDENTITY)
    assert state_digest(first) == state_digest(second)

    frame = SessionTracker(params).start(first)
    assert frame.step == 0 and frame.prey_decision is None and frame.predator_decision is None
    np.testing.assert_array_equal(frame.prey.positions, first.prey.positions)
    np.testing.assert_array_equal(frame.predators.headings, first.predators.headings)
    np.testing.assert_array_equal(frame.plant_positions, first.plants.positions)
    assert frame.stats.prey_alive == params.n_prey and frame.stats.captures_total == 0


def test_frames_are_read_only_copies() -> None:
    params, *_, registry = setup("A", "rules")
    world = initial_world(params, registry, IDENTITY)
    frame = SessionTracker(params).start(world)
    arrays = [
        frame.prey.positions,
        frame.prey.energy,
        frame.predators.alive,
        frame.plant_positions,
        frame.plant_active,
    ]
    for array in arrays:
        with pytest.raises(ValueError):
            array[...] = 0
    assert not np.shares_memory(frame.prey.positions, world.prey.positions)
    assert not np.shares_memory(frame.plant_active, world.plants.active)


def test_hud_statistics_match_the_episode_record() -> None:
    params, prey, predator, registry = setup("C", "rules")
    recorder = Recorder()
    means: list[tuple[float, float]] = []

    def collect(trace: StepTrace) -> None:
        world = trace.world
        means.append(
            (
                world.prey.energy[world.prey.alive].mean() if world.prey.alive.any() else np.nan,
                world.predators.energy[world.predators.alive].mean(),
            )
        )

    result = run_session(params, prey, predator, registry, IDENTITY, recorder, after_step=collect)
    record = result.record
    stats = [frame.stats for frame in recorder.frames[1:]]
    assert [s.step for s in stats] == list(range(1, record.steps + 1))
    assert [s.prey_alive for s in stats] == record.prey_alive_after.tolist()
    assert [s.prey_captured for s in stats] == record.prey_captured_after.tolist()
    assert [s.prey_starved for s in stats] == record.prey_starved_after.tolist()
    assert [s.predators_alive for s in stats] == record.predators_alive_after.tolist()
    assert [s.plants_active for s in stats] == record.plants_active_after.tolist()
    assert all(s.captures_total == s.prey_captured for s in stats)
    assert stats[-1].captures_total == record.capture_step.size > 0
    assert stats[-1].feedings_total == record.feeding_step.size > 0
    for s, (prey_mean, predator_mean) in zip(stats, means, strict=True):
        np.testing.assert_equal(s.prey_mean_energy, prey_mean)
        assert s.predator_mean_energy == predator_mean


@pytest.mark.parametrize("scenario", ["A", "C"])
@pytest.mark.parametrize("policy", ["rules", "random"])
def test_inspector_matches_the_trace_of_the_same_step(scenario, policy) -> None:
    params, prey, predator, registry = setup(scenario, policy)
    recorder = Recorder()
    seen = {"dead_before": 0, "died_now": 0}

    def compare(trace: StepTrace) -> None:
        frame = recorder.frames[-1]  # the frame the observer has just received for this trace
        world = trace.world
        cases = (
            ("prey", PREY_SCHEMA, trace.prey_observations, trace.prey_actions, world.prey),
            (
                "predator",
                PREDATOR_SCHEMA,
                trace.predator_observations,
                trace.predator_actions,
                world.predators,
            ),
        )
        for species, schema, observations, actions, state in cases:
            species_params = params.prey if species == "prey" else params.predator
            turns, speeds = decode_actions(actions, species_params)
            for i in range(state.size):
                view = inspect_agent(frame, params, species, i)
                # Decision of step t, observed on S_t.
                assert view.decision_step == trace.step
                assert tuple(name for name, _ in view.inputs) == schema.names
                assert np.array_equal(np.array([v for _, v in view.inputs]), observations[i])
                assert view.raw_action == (actions[i, 0], actions[i, 1])
                assert (view.turn, view.speed) == (turns[i], speeds[i])
                # State after the step, S_t+1.
                assert view.state_step == trace.step + 1 == world.step
                assert view.position == tuple(state.positions[i])
                assert view.heading == state.headings[i]
                assert view.energy == state.energy[i]
                assert view.energy_fraction == state.energy[i] / species_params.e_max
                assert view.alive == bool(state.alive[i])
                death = int(state.death_step[i])
                assert view.death_step == (None if death == NOT_DEAD else death)
                if not state.alive[i]:
                    assert view.action_applied == (death == trace.step)
                    seen["died_now" if death == trace.step else "dead_before"] += 1
                else:
                    assert view.action_applied is True

    run_session(params, prey, predator, registry, IDENTITY, recorder, after_step=compare)
    if scenario == "C" and policy == "rules":
        assert seen["died_now"] > 0 and seen["dead_before"] > 0  # both cases exercised


def test_initial_inspection_has_no_decision() -> None:
    params, *_, registry = setup("A", "rules")
    frame = SessionTracker(params).start(initial_world(params, registry, IDENTITY))
    view = inspect_agent(frame, params, "predator", 0)
    assert view.state_step == 0 and view.decision_step is None
    assert view.inputs == () and view.raw_action is None and view.action_applied is None
    assert view.alive and view.death_cause == "ALIVE" and view.death_step is None


def test_inspector_rejects_unknown_species_and_indices() -> None:
    params, *_, registry = setup("A", "rules")
    frame = SessionTracker(params).start(initial_world(params, registry, IDENTITY))
    with pytest.raises(ValueError, match="species"):
        inspect_agent(frame, params, "plant", 0)
    with pytest.raises(IndexError):
        inspect_agent(frame, params, "prey", params.n_prey)
