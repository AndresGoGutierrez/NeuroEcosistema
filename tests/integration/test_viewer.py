"""T3 (F2): viewer controls, selection, early close and end of episode (ADR-031)."""

from pathlib import Path

import pygame
import pytest

import viewer_support as vs  # headless SDL
from neuroeco.application.evaluation import EpisodeIdentity
from neuroeco.application.seeding import Purpose
from neuroeco.application.session import SessionTracker, initial_world, run_session
from neuroeco.bootstrap import EXPLORATORY_SEED_GROUP, build_policy, build_runtime
from neuroeco.presentation.inspector import SessionInfo
from neuroeco.presentation.viewer import (
    SPEEDS,
    Command,
    Controls,
    Viewer,
    ViewerClosed,
    canvas_transform,
    command_for,
)

CONFIGS = Path(__file__).resolve().parents[2] / "configs"
IDENTITY = EpisodeIdentity(Purpose.PILOT, EXPLORATORY_SEED_GROUP, item=0)


def setup(t_max: int = 120):
    runtime = build_runtime("A", (f"world.t_max={t_max}",), CONFIGS)
    config = runtime.config
    info = SessionInfo("A", "rules", "rules", 0, config.config_hash)
    policies = (build_policy("rules", "prey", config), build_policy("rules", "predator", config))
    return config.world, policies, runtime.registry, info


# ---------------------------------------------------------------- controls (no display needed)


def test_controls_state_machine() -> None:
    controls = Controls(paused=True)
    controls.apply(Command.STEP)
    assert controls.step_requested
    controls.step_requested = False
    controls.apply(Command.TOGGLE_PAUSE)
    assert not controls.paused
    controls.apply(Command.STEP)  # ignored while running
    assert not controls.step_requested
    for _ in range(10):
        controls.apply(Command.FASTER)
    assert controls.steps_per_frame == SPEEDS[-1]
    for _ in range(10):
        controls.apply(Command.SLOWER)
    assert controls.steps_per_frame == SPEEDS[0]
    controls.apply(Command.QUIT)
    assert controls.quit_requested


@pytest.mark.parametrize(
    ("event", "command"),
    [
        (vs.key(vs.SPACE), Command.TOGGLE_PAUSE),
        (vs.key(vs.RIGHT), Command.STEP),
        (vs.key(vs.PLUS), Command.FASTER),
        (vs.key(pygame.K_KP_PLUS), Command.FASTER),
        (vs.key(pygame.K_1, unicode="+"), Command.FASTER),  # '+' on other keyboard layouts
        (vs.key(vs.MINUS), Command.SLOWER),
        (vs.key(vs.ESCAPE), Command.QUIT),
        (vs.close_window(), Command.QUIT),
        (vs.key(pygame.K_a, unicode="a"), None),
    ],
)
def test_events_map_to_commands(event, command) -> None:
    assert command_for(event) is command


def test_invalid_viewer_options_are_rejected() -> None:
    params, _, _, info = setup()
    with pytest.raises(ValueError, match="speed"):
        Viewer(params, info, speed=3)
    with pytest.raises(ValueError, match="fps"):
        Viewer(params, info, fps=-1)


# ---------------------------------------------------------------- with the real viewer


def test_click_selects_the_agent_under_the_cursor() -> None:
    params, _, registry, info = setup()
    world = initial_world(params, registry, IDENTITY)
    target = canvas_transform(params).to_screen(*world.predators.positions[1])
    viewer = Viewer(params, info, paused=False, fps=0, event_source=vs.script([vs.click(target)]))
    try:
        viewer.start(SessionTracker(params).start(world))
        assert (viewer.selected.species, viewer.selected.index) == ("predator", 1)
        assert "PREDATOR #1" in viewer.panel_lines()
    finally:
        viewer.close()


def test_closing_the_window_stops_the_episode_early() -> None:
    params, policies, registry, info = setup(t_max=500)
    events = vs.script([], [], [vs.close_window()])
    viewer = Viewer(params, info, paused=False, fps=0, event_source=events)
    steps: list[int] = []
    try:
        with pytest.raises(ViewerClosed) as closed:
            run_session(
                params,
                *policies,
                registry,
                IDENTITY,
                viewer,
                after_step=lambda t: steps.append(t.step),
            )
    finally:
        viewer.close()
    # Renders: S0, after step 0, after step 1 -> the close event arrives on the third render.
    assert closed.value.step == 2
    assert steps == [0]  # the step whose frame triggered the close never completed its hook


def test_escape_while_paused_closes_the_viewer() -> None:
    params, policies, registry, info = setup()
    viewer = Viewer(
        params, info, paused=True, fps=0, event_source=vs.script([], [vs.key(vs.ESCAPE)])
    )
    try:
        with pytest.raises(ViewerClosed) as closed:
            run_session(params, *policies, registry, IDENTITY, viewer)
    finally:
        viewer.close()
    assert closed.value.step == 0  # still at S0


def test_finish_shows_the_final_state() -> None:
    params, policies, registry, info = setup(t_max=30)
    viewer = Viewer(params, info, paused=False, fps=0, exit_at_end=True)
    try:
        result = run_session(params, *policies, registry, IDENTITY, viewer)
        viewer.finish()
        assert viewer.finished
        assert viewer.frame.step == result.metrics.steps
        assert "FINISHED" in viewer.panel_lines()[0]
    finally:
        viewer.close()
