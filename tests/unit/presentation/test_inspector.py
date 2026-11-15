"""T2 (F2): screen/world transform, agent picking and panel text (ADR-031)."""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from neuroeco.application.evaluation import EpisodeIdentity
from neuroeco.application.seeding import Purpose
from neuroeco.application.session import (
    Frame,
    SessionTracker,
    SpeciesView,
    initial_world,
    inspect_agent,
    run_session,
)
from neuroeco.bootstrap import build_policy, build_runtime
from neuroeco.domain.perception import PREDATOR_SCHEMA, PREY_SCHEMA
from neuroeco.presentation.inspector import (
    SessionInfo,
    WorldTransform,
    hud_lines,
    inspector_lines,
    pick_agent,
)

CONFIGS = Path(__file__).resolve().parents[3] / "configs"
INFO = SessionInfo("C", "rules", "random", 3, "a44a23f9c7441f956fb5")


def view_of(positions, alive=None) -> SpeciesView:
    positions = np.asarray(positions, dtype=np.float64)
    n = positions.shape[0]
    return SpeciesView(
        positions=positions,
        headings=np.zeros(n),
        energy=np.full(n, 50.0),
        alive=np.ones(n, dtype=bool) if alive is None else np.asarray(alive),
        death_step=np.full(n, -1, dtype=np.int64),
        death_cause=np.zeros(n, dtype=np.int8),
    )


def base_frame():
    runtime = build_runtime("A", (), CONFIGS)
    params = runtime.config.world
    world = initial_world(params, runtime.registry, EpisodeIdentity(Purpose.PILOT, 0))
    return params, SessionTracker(params).start(world)


def frame_with(prey, predators, prey_alive=None) -> Frame:
    _, frame = base_frame()
    return replace(frame, prey=view_of(prey, prey_alive), predators=view_of(predators))


# ---------------------------------------------------------------- transform


def test_transform_round_trip_and_orientation() -> None:
    transform = WorldTransform(size=150.0, scale=4.0, origin=(10, 20))
    assert transform.pixels == 600
    assert transform.to_screen(0.0, 150.0) == (10.0, 20.0)  # world top-left
    assert transform.to_screen(150.0, 0.0) == (610.0, 620.0)  # world bottom-right
    for point in [(0.0, 0.0), (12.5, 140.25), (149.0, 3.5)]:
        assert transform.to_world(*transform.to_screen(*point)) == pytest.approx(point)
    assert transform.contains(10, 20) and not transform.contains(610, 300)


# ---------------------------------------------------------------- picking


def test_pick_selects_the_nearest_living_agent_within_radius() -> None:
    frame = frame_with(prey=[[10.0, 10.0], [50.0, 50.0]], predators=[[12.0, 10.0]])
    selection = pick_agent(frame, (10.5, 10.0), 3.0)  # 0.5 from prey 0, 1.5 from the predator
    assert (selection.species, selection.index) == ("prey", 0)
    selection = pick_agent(frame, (11.5, 10.0), 3.0)
    assert (selection.species, selection.index) == ("predator", 0)
    selection = pick_agent(frame, (49.0, 50.0), 3.0)
    assert (selection.species, selection.index) == ("prey", 1)
    assert pick_agent(frame, (100.0, 100.0), 3.0) is None


def test_pick_ties_prefer_prey_then_lower_index() -> None:
    frame = frame_with(prey=[[20.0, 20.0], [20.0, 20.0]], predators=[[20.0, 20.0]])
    selection = pick_agent(frame, (20.0, 21.0), 3.0)
    assert (selection.species, selection.index) == ("prey", 0)


def test_pick_ignores_dead_agents_and_does_not_wrap() -> None:
    frame = frame_with(
        prey=[[30.0, 30.0], [149.5, 75.0]], predators=[[90.0, 90.0]], prey_alive=[False, True]
    )
    assert pick_agent(frame, (30.0, 30.0), 3.0) is None
    assert pick_agent(frame, (0.5, 75.0), 3.0) is None  # 1 unit away only through the torus


# ---------------------------------------------------------------- text


def test_hud_lines_show_counts_status_and_missing_means() -> None:
    _, frame = base_frame()
    stats = replace(frame.stats, prey_mean_energy=float("nan"))
    lines = "\n".join(hud_lines(stats, INFO, paused=True, steps_per_frame=4, finished=False))
    assert "step 0 / " in lines and "PAUSED" in lines
    assert f"alive {stats.prey_alive}/{stats.n_prey}" in lines
    assert f"active {stats.plants_active}/{stats.n_plants}" in lines
    assert "prey —" in lines and "config a44a23f9c744" in lines
    running = hud_lines(stats, INFO, paused=False, steps_per_frame=4, finished=False)
    assert "running x4" in running[0]
    assert "FINISHED" in hud_lines(stats, INFO, paused=False, steps_per_frame=1, finished=True)[0]


def test_initial_inspection_text_has_no_decision() -> None:
    params, frame = base_frame()
    lines = inspector_lines(inspect_agent(frame, params, "prey", 2))
    assert lines[0] == "PREY #2" and lines[1] == "state S_0"
    assert lines[-1] == "initial state: no decision yet"


@pytest.mark.parametrize(
    ("species", "schema"), [("prey", PREY_SCHEMA), ("predator", PREDATOR_SCHEMA)]
)
def test_inspection_text_lists_every_input_in_schema_order(species, schema) -> None:
    runtime = build_runtime("C", ("world.t_max=40",), CONFIGS)
    config = runtime.config
    frames: list[Frame] = []

    class Keep:
        def start(self, frame: Frame) -> None:
            frames.append(frame)

        def step(self, frame: Frame) -> None:
            frames.append(frame)

    run_session(
        config.world,
        build_policy("rules", "prey", config),
        build_policy("rules", "predator", config),
        runtime.registry,
        EpisodeIdentity(Purpose.PILOT, 0),
        Keep(),
    )
    view = inspect_agent(frames[-1], config.world, species, 0)
    text = inspector_lines(view)
    assert f"state S_{view.state_step} (after step {view.decision_step})" in text
    input_lines = [line for line in text if line.startswith("  ")]
    assert tuple(line.split()[0] for line in input_lines) == schema.names
    for (name, value), line in zip(view.inputs, input_lines, strict=True):
        assert line.split() == [name, f"{value:+.4f}"]
    assert any(line.startswith("action    turn") for line in text)
    assert text[-1] == "applied   yes"


def test_dead_agent_action_is_reported_as_not_applied() -> None:
    params, frame = base_frame()
    view = replace(
        inspect_agent(frame, params, "prey", 0),
        alive=False,
        death_cause="CAPTURED",
        death_step=5,
        decision_step=9,
        state_step=10,
        inputs=(("plant_proximity", 0.0),),
        raw_action=(0.0, 0.0),
        turn=0.0,
        speed=0.5,
        action_applied=False,
    )
    text = "\n".join(inspector_lines(view))
    assert "captured at step 5" in text and "applied   no (dead before the step)" in text
    with pytest.raises(ValueError, match="action"):
        inspector_lines(replace(view, raw_action=None))
