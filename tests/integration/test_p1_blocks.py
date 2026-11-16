"""F4 T2: planning and execution of the episodes of a P1 block (ADR-033).

Synthetic specifications only, with seed_group >= 1000 (D16), few episodes and a short t_max.
The configuration files are only read. No real P1 episode, data or result is produced.
"""

import dataclasses
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from neuroeco.application import calibration
from neuroeco.application.calibration import (
    CONDITIONS_BY_SCENARIO,
    SCENARIOS,
    A2ViolationError,
    BlockSet,
    BlockSpec,
    CandidateValues,
    Grids,
    InvariantViolationError,
    P1Spec,
    ScenarioGroups,
    condition_overrides,
    iter_block,
    keys_from_columns,
    plan_block,
)
from neuroeco.application.seeding import Purpose
from neuroeco.bootstrap import build_policy
from neuroeco.domain.simulator import simulate_episode
from neuroeco.domain.state import EpisodeStreams
from neuroeco.infrastructure.config_loader import ConfigError, load_config

CONFIGS = Path(__file__).resolve().parents[2] / "configs"
SHORT = ("world.t_max=40",)
PROVISIONAL = CandidateValues(30.0, 50, 40, 15, 8, 0.3, 0.5, 0.5)


def spec(episodes: int = 2) -> P1Spec:
    return P1Spec(
        "P1",
        BlockSet(
            calibration=BlockSpec(episodes, ScenarioGroups(1000, 1001, 1002)),
            confirmation=BlockSpec(episodes, ScenarioGroups(1010, 1011, 1012)),
            second_confirmation=BlockSpec(episodes, ScenarioGroups(1020, 1021, 1022)),
        ),
        Grids((0.2, 0.3, 0.4, 0.5), (0.3, 0.5, 0.7)),
    )


def resolve(scenario: str, overrides: tuple[str, ...]):
    return load_config(CONFIGS, scenario, (*overrides, *SHORT))


def run(tasks, **kwargs):
    return list(iter_block(tasks, resolve, build_policy, **kwargs))


def same_record(first, second) -> bool:
    left, right = dataclasses.asdict(first), dataclasses.asdict(second)
    return left.keys() == right.keys() and all(_equal(left[k], right[k]) for k in left)


def _equal(a, b) -> bool:
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(_equal(a[k], b[k]) for k in a)
    if isinstance(a, np.ndarray):
        return a.dtype == b.dtype and np.array_equal(a, b, equal_nan=a.dtype.kind == "f")
    return a == b


# ---------------------------------------------------------------- planning


def test_full_block_plans_match_the_catalogue_and_the_specification() -> None:
    calibration_plan = plan_block(spec(30), "calibration", PROVISIONAL)
    confirmation_plan = plan_block(spec(50), "confirmation", PROVISIONAL)
    assert (len(calibration_plan), len(confirmation_plan)) == (1050, 1750)

    per_scenario = Counter(t.scenario for t in calibration_plan)
    assert per_scenario == {"A": 12 * 30, "B": 12 * 30, "C": 11 * 30}
    groups = {t.scenario: t.seed_group for t in confirmation_plan}
    assert groups == {"A": 1010, "B": 1011, "C": 1012}
    for task in calibration_plan:
        assert task.overrides == condition_overrides(
            PROVISIONAL, task.scenario, task.condition.name
        )
        assert task.identity.purpose == Purpose.PILOT
        assert (task.identity.run, task.identity.generation) == (0, 0)


def test_plan_order_is_scenario_condition_item() -> None:
    plan = plan_block(spec(2), "calibration", PROVISIONAL)
    expected = [
        (s, c.name, item) for s in SCENARIOS for c in CONDITIONS_BY_SCENARIO[s] for item in range(2)
    ]
    assert [(t.scenario, t.condition.name, t.item) for t in plan] == expected


def test_plan_subsets_for_stages_and_rounds() -> None:
    stage_b = plan_block(spec(2), "calibration", PROVISIONAL, scenarios=("B", "A"))
    assert (stage_b[0].scenario, stage_b[-1].scenario) == ("A", "B")  # canonical order
    assert len(stage_b) == (12 + 12) * 2
    grid = plan_block(spec(2), "calibration", PROVISIONAL, scenarios=("A",), conditions=("rules",))
    assert [(t.scenario, t.condition.name, t.item) for t in grid] == [
        ("A", "rules", 0),
        ("A", "rules", 1),
    ]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"block": "pilot"}, "unknown block"),
        ({"scenarios": ()}, "non-empty selection"),
        ({"scenarios": ("A", "A")}, "non-empty selection"),
        ({"scenarios": ("D",)}, "scenario must be one of"),
        ({"conditions": ()}, "non-empty selection"),
        (
            {"scenarios": ("A", "C"), "conditions": ("no_predators",)},
            "does not exist in scenario C",
        ),
        ({"conditions": ("rules", "unknown")}, "does not exist in scenario A"),
    ],
)
def test_invalid_plans_are_rejected(kwargs, message) -> None:
    arguments = {"block": "calibration", **kwargs}
    block = arguments.pop("block")
    with pytest.raises(ValueError, match=message):
        plan_block(spec(2), block, PROVISIONAL, **arguments)


# ---------------------------------------------------------------- execution


@pytest.fixture(scope="module")
def block_outcomes():
    tasks = plan_block(spec(2), "calibration", PROVISIONAL)
    return tasks, run(tasks)


def test_every_condition_of_the_block_runs_under_the_checker(block_outcomes) -> None:
    tasks, outcomes = block_outcomes
    assert [o.task for o in outcomes] == list(tasks)
    for outcome in outcomes:
        record = outcome.result.record
        assert outcome.steps_checked == record.steps > 0
        expected_hash = resolve(outcome.task.scenario, outcome.task.overrides).config_hash
        assert outcome.config_hash == expected_hash
        assert outcome.key_columns == {
            "purpose": 1,
            "seed_group": outcome.task.seed_group,
            "run": 0,
            "generation": 0,
            "item": outcome.task.item,
            "stream_env_init": 3,
            "stream_env_dynamics": 4,
            "stream_policy_prey": 5,
            "stream_policy_predator": 6,
        }
        n_predators = record.predators.death_step.shape[0]
        if outcome.task.condition.no_predators:
            assert n_predators == 0
        else:
            assert n_predators == (8 if outcome.task.scenario == "C" else 3)


def test_the_nine_key_columns_identify_the_streams_used(block_outcomes) -> None:
    """A direct simulation with generators rebuilt from the columns gives the same record."""
    _, outcomes = block_outcomes
    for outcome in [outcomes[0], outcomes[25], outcomes[-1]]:
        config = resolve(outcome.task.scenario, outcome.task.overrides)
        keys = keys_from_columns(outcome.key_columns)

        def rebuilt(column, seed=config.project_seed, keys=keys):
            return np.random.default_rng(np.random.SeedSequence(seed, spawn_key=keys[column]))

        streams = EpisodeStreams(
            env_init=rebuilt("stream_env_init"),
            env_dynamics=rebuilt("stream_env_dynamics"),
            policy_prey=rebuilt("stream_policy_prey"),
            policy_predator=rebuilt("stream_policy_predator"),
        )
        condition = outcome.task.condition
        record = simulate_episode(
            config.world,
            build_policy(condition.prey_policy, "prey", config),
            build_policy(condition.predator_policy, "predator", config),
            streams,
        )
        assert same_record(record, outcome.result.record)


def test_a_block_is_reproducible(block_outcomes) -> None:
    tasks, outcomes = block_outcomes
    sample = [tasks[1], tasks[30], tasks[-2]]
    again = run(sample)
    by_task = {o.task: o for o in outcomes}
    for outcome in again:
        assert same_record(outcome.result.record, by_task[outcome.task].result.record)
        assert repr(outcome.result.metrics) == repr(by_task[outcome.task].result.metrics)


def test_no_state_leaks_between_episodes(block_outcomes) -> None:
    tasks, outcomes = block_outcomes
    by_task = {o.task: o for o in outcomes}
    x, y = tasks[4], tasks[50]  # random predator in A; random prey in C
    sequence = run([x, y, x])
    assert same_record(sequence[0].result.record, sequence[2].result.record)
    assert same_record(sequence[0].result.record, by_task[x].result.record)
    assert same_record(sequence[1].result.record, run([y])[0].result.record)


# ---------------------------------------------------------------- confirmation guard


def test_confirmation_blocks_need_explicit_authorization() -> None:
    for block in ("confirmation", "second_confirmation"):
        tasks = plan_block(spec(2), block, PROVISIONAL, scenarios=("A",), conditions=("rules",))
        with pytest.raises(PermissionError, match="explicit authorization"):
            iter_block(tasks, resolve, build_policy)
        iter_block(tasks, resolve, build_policy, confirmation_authorized=True)  # not iterated
    mixed = plan_block(spec(2), "calibration", PROVISIONAL, scenarios=("A",), conditions=("rules",))
    mixed += plan_block(
        spec(2), "confirmation", PROVISIONAL, scenarios=("A",), conditions=("rules",)
    )
    with pytest.raises(PermissionError):
        iter_block(mixed, resolve, build_policy)


# ---------------------------------------------------------------- errors are never hidden


def test_an_a2_violation_stops_the_block(monkeypatch) -> None:
    tasks = plan_block(spec(2), "calibration", PROVISIONAL, scenarios=("A",), conditions=("rules",))
    original = calibration.InvariantChecker.__call__
    armed = {"value": False}

    def failing(self, trace) -> None:
        original(self, trace)
        if armed["value"] and trace.step == 3:
            raise InvariantViolationError("prey_energy", trace.step, "injected for the test")

    monkeypatch.setattr(calibration.InvariantChecker, "__call__", failing)
    seen = []
    iterator = iter_block(tasks, resolve, build_policy)
    seen.append(next(iterator))  # item 0 runs normally
    armed["value"] = True
    with pytest.raises(A2ViolationError) as info:
        seen.append(next(iterator))
    assert info.value.task == tasks[1]
    assert info.value.violation.invariant == "prey_energy"
    assert info.value.violation.step == 3
    assert "calibration/A/rules/seed_group 1000/item 1" in str(info.value)
    assert len(seen) == 1
    with pytest.raises(StopIteration):
        next(iterator)


def test_other_errors_keep_their_type_and_name_the_episode() -> None:
    tasks = plan_block(spec(2), "calibration", PROVISIONAL, scenarios=("B",), conditions=("rules",))

    def broken_resolve(scenario, overrides):
        raise ConfigError("synthetic configuration failure")

    with pytest.raises(ConfigError) as info:
        list(iter_block(tasks, broken_resolve, build_policy))
    assert "P1 episode: calibration/B/rules/seed_group 1001/item 0" in info.value.__notes__

    def broken_policy(name, species, config):
        raise ValueError("synthetic policy failure")

    with pytest.raises(ValueError, match="synthetic policy failure") as info:
        list(iter_block(tasks, resolve, broken_policy))
    assert info.value.__notes__ == ["P1 episode: calibration/B/rules/seed_group 1001/item 0"]


def test_resolved_configuration_must_match_the_task() -> None:
    tasks = plan_block(spec(2), "calibration", PROVISIONAL, scenarios=("A",), conditions=("rules",))
    with pytest.raises(ValueError, match="resolved scenario 'B'"):
        list(iter_block(tasks, lambda s, o: resolve("B", ()), build_policy))

    seeds = iter([None, "other"])

    def two_seeds(scenario, overrides):
        config = resolve(scenario, overrides)
        if next(seeds) == "other":
            config = dataclasses.replace(config, project_seed=config.project_seed + 1)
        return config

    # rules and no_predators have different overrides, so each is resolved separately
    two_configs = plan_block(spec(2), "calibration", PROVISIONAL, ("A",), ("rules", "no_predators"))
    with pytest.raises(ValueError, match="share the project seed"):
        list(iter_block(two_configs, two_seeds, build_policy))
