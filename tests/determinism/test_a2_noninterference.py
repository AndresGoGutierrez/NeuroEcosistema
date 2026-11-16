"""F4 T2 / P1-22: the A2 checker does not alter the trajectory (hash per step, with = without).

Synthetic seed groups (>= 1000, D16) and a short t_max; the configuration files are only read.
"""

from pathlib import Path

import pytest

from neuroeco.application.calibration import InvariantChecker
from neuroeco.application.evaluation import EpisodeIdentity, run_episode
from neuroeco.application.seeding import Purpose, SeedRegistry
from neuroeco.application.session import initial_world
from neuroeco.bootstrap import build_policy
from neuroeco.infrastructure.config_loader import load_config
from support import state_digest

pytestmark = pytest.mark.determinism

CONFIGS = Path(__file__).resolve().parents[2] / "configs"
IDENTITY = EpisodeIdentity(Purpose.PILOT, 1000, item=3)


def run(scenario: str, prey: str, predator: str, overrides: tuple[str, ...], checked: bool):
    config = load_config(CONFIGS, scenario, ("world.t_max=150", *overrides))
    registry = SeedRegistry(config.project_seed)
    policies = (build_policy(prey, "prey", config), build_policy(predator, "predator", config))
    digests: list[str] = []
    checker = InvariantChecker(config.world)
    if checked:
        checker.check_initial(initial_world(config.world, registry, IDENTITY))

    def on_step(trace) -> None:
        if checked:
            checker(trace)
        digests.append(state_digest(trace.world))

    result = run_episode(config.world, *policies, registry, IDENTITY, on_step=on_step)
    return digests, repr(result.metrics), checker.steps_checked


@pytest.mark.parametrize("scenario", ["A", "B", "C"])
@pytest.mark.parametrize(
    ("prey", "predator"),
    [
        ("rules", "rules"),
        ("random", "rules"),
        ("rules", "random"),
        ("still", "rules"),
        ("rules", "spin"),
    ],
)
def test_hash_with_checker_equals_hash_without_checker(scenario, prey, predator) -> None:
    expected_digests, expected_metrics, _ = run(scenario, prey, predator, (), checked=False)
    digests, metrics, steps_checked = run(scenario, prey, predator, (), checked=True)
    assert digests == expected_digests  # per step, bit for bit
    assert metrics == expected_metrics
    assert steps_checked == len(digests) > 10


@pytest.mark.parametrize("scenario", ["A", "B"])
def test_hash_with_checker_without_predators(scenario) -> None:
    overrides = ("world.n_predators=0",)
    expected = run(scenario, "rules", "rules", overrides, checked=False)
    observed = run(scenario, "rules", "rules", overrides, checked=True)
    assert observed[:2] == expected[:2]
