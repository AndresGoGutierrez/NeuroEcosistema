"""F4 T3: coverage gaps found in the audit of T2, exercised through ``iter_block``.

Synthetic specification (seed_group >= 1000, D16), short t_max; the configuration files are only
read. No real P1 episode or result is produced.
"""

from pathlib import Path

import pytest

from neuroeco.application import calibration
from neuroeco.application.calibration import (
    SAFE_DISTANCE,
    A2ViolationError,
    BlockSet,
    BlockSpec,
    CandidateValues,
    Grids,
    InvariantViolationError,
    P1Spec,
    ScenarioGroups,
    iter_block,
    plan_block,
)
from neuroeco.bootstrap import build_policy
from neuroeco.domain.state import InitializationError
from neuroeco.infrastructure.config_loader import load_config

CONFIGS = Path(__file__).resolve().parents[2] / "configs"
SPEC = P1Spec(
    "P1",
    BlockSet(
        calibration=BlockSpec(2, ScenarioGroups(1000, 1001, 1002)),
        confirmation=BlockSpec(2, ScenarioGroups(1010, 1011, 1012)),
        second_confirmation=BlockSpec(2, ScenarioGroups(1020, 1021, 1022)),
    ),
    Grids((0.2, 0.3, 0.4, 0.5), (0.3, 0.5, 0.7)),
)
TASKS = plan_block(
    SPEC, "calibration", CandidateValues(30.0, 50, 40, 15, 8, 0.3, 0.5, 0.5), ("A",), ("rules",)
)


def resolve(scenario, overrides, extra=("world.t_max=30",)):
    return load_config(CONFIGS, scenario, (*overrides, *extra))


def test_a_violation_at_s0_stops_the_block_with_step_none(monkeypatch) -> None:
    def violated(self, world) -> None:
        raise InvariantViolationError(SAFE_DISTANCE, None, "injected for the test")

    monkeypatch.setattr(calibration.InvariantChecker, "check_initial", violated)
    with pytest.raises(A2ViolationError) as info:
        list(iter_block(TASKS, resolve, build_policy))
    assert info.value.violation.step is None
    assert info.value.violation.invariant == SAFE_DISTANCE
    assert info.value.task == TASKS[0]
    assert "at S0" in str(info.value)


def test_initialization_errors_propagate_with_the_episode() -> None:
    crowded = ("world.t_max=30", "world.n_prey=400")  # no room for d_safe: placement fails

    with pytest.raises(InitializationError, match="could not place predator") as info:
        list(iter_block(TASKS, lambda s, o: resolve(s, o, crowded), build_policy))
    assert info.value.__notes__ == ["P1 episode: calibration/A/rules/seed_group 1000/item 0"]


def test_steps_missed_by_the_checker_stop_the_block(monkeypatch) -> None:
    monkeypatch.setattr(calibration.InvariantChecker, "__call__", lambda self, trace: None)
    with pytest.raises(RuntimeError, match="observed 0 of") as info:
        list(iter_block(TASKS, resolve, build_policy))
    assert info.value.__notes__ == ["P1 episode: calibration/A/rules/seed_group 1000/item 0"]
