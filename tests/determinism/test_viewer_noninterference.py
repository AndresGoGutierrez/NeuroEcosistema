"""F2 / ADR-024: the viewer does not change the simulation (hash with viewer = without).

The real pygame viewer runs with the SDL ``dummy`` driver and scripted input: pauses,
single steps, speed changes and agent selections happen while the episode runs.
"""

from pathlib import Path

import pytest

import viewer_support as vs  # sets the headless SDL driver before pygame initializes
from neuroeco.application.evaluation import EpisodeIdentity, run_episode
from neuroeco.application.seeding import Purpose
from neuroeco.application.session import SessionTracker, initial_world, run_session
from neuroeco.bootstrap import EXPLORATORY_SEED_GROUP, build_policy, build_runtime
from neuroeco.presentation.inspector import SessionInfo
from neuroeco.presentation.viewer import Viewer, canvas_transform
from support import state_digest

pytestmark = pytest.mark.determinism

CONFIGS = Path(__file__).resolve().parents[2] / "configs"
IDENTITY = EpisodeIdentity(Purpose.PILOT, EXPLORATORY_SEED_GROUP, item=1)


def setup(scenario: str, policy: str, t_max: int = 200):
    runtime = build_runtime(scenario, (f"world.t_max={t_max}",), CONFIGS)
    config = runtime.config
    info = SessionInfo(scenario, policy, policy, IDENTITY.item, config.config_hash)
    policies = (build_policy(policy, "prey", config), build_policy(policy, "predator", config))
    return config.world, policies, runtime.registry, info


def headless_run(params, policies, registry) -> tuple[list[str], str]:
    digests: list[str] = []
    result = run_episode(
        params,
        *policies,
        registry,
        IDENTITY,
        on_step=lambda t: digests.append(state_digest(t.world)),
    )
    return digests, repr(result.metrics)


def interactive_script(params, registry):
    """Pause at S0, select agents, single-step, change speed, resume, pause again, resume."""
    transform = canvas_transform(params)
    world = initial_world(params, registry, IDENTITY)
    prey_xy = transform.to_screen(*world.prey.positions[0])
    predator_xy = transform.to_screen(*world.predators.positions[0])
    return vs.script(
        [vs.click(prey_xy)],  # S0 shown paused: select prey 0
        [vs.key(vs.RIGHT)],  # one step
        [vs.key(vs.RIGHT), vs.key(vs.PLUS)],  # another step, faster
        [vs.click(predator_xy), vs.key(vs.PLUS)],
        [vs.key(vs.SPACE)],  # resume at x4
        [],
        [vs.key(vs.SPACE)],  # pause again
        [vs.key(vs.MINUS), vs.key(vs.RIGHT)],
        [vs.click((5, 5))],  # click on empty space
        [vs.key(vs.SPACE), vs.key(vs.PLUS)],  # resume until the end
    )


@pytest.mark.parametrize("scenario", ["A", "B", "C"])
@pytest.mark.parametrize("policy", ["rules", "random"])
def test_hash_with_viewer_equals_hash_without_viewer(scenario, policy) -> None:
    params, policies, registry, info = setup(scenario, policy)
    expected_digests, expected_metrics = headless_run(params, policies, registry)

    events = interactive_script(params, registry)
    viewer = Viewer(params, info, paused=True, fps=0, exit_at_end=True, event_source=events)
    digests: list[str] = []
    selections = []
    try:
        result = run_session(
            params,
            *policies,
            registry,
            IDENTITY,
            viewer,
            after_step=lambda t: (
                digests.append(state_digest(t.world)),
                selections.append(viewer.selected),
            ),
        )
        viewer.finish()
    finally:
        viewer.close()

    assert events.remaining() == 0, "the scripted interaction must be fully exercised"
    assert any(s is not None for s in selections), "an agent must have been inspected"
    assert digests == expected_digests  # per step, bit for bit
    assert repr(result.metrics) == expected_metrics
    assert len(digests) > 10


def test_drawing_does_not_modify_the_state() -> None:
    params, _, registry, info = setup("C", "rules")
    world = initial_world(params, registry, IDENTITY)
    before = state_digest(world)
    frame = SessionTracker(params).start(world)
    target = canvas_transform(params).to_screen(*world.prey.positions[2])
    viewer = Viewer(params, info, paused=False, fps=0, event_source=vs.script([vs.click(target)]))
    try:
        viewer.start(frame)
        viewer.start(frame)  # second render with the agent selected and the inspector drawn
        assert viewer.selected is not None
        assert any(line.startswith("PREY #") for line in viewer.panel_lines())
    finally:
        viewer.close()
    assert state_digest(world) == before
