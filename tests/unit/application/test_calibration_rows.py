"""F4 T3: episode rows, bootstrap key rows and the independent block-group check (ADR-033).

Records are built by hand to reach the censoring edge cases of B3 and B6 exactly; every seed
group is synthetic (>= 1000, D16). No episode is run.
"""

import dataclasses
import math

import numpy as np
import pytest

from neuroeco.application.calibration import (
    BOOTSTRAP_COLUMNS,
    EPISODE_COLUMN_TYPES,
    EPISODE_COLUMNS,
    KEY_COLUMNS,
    BlockSet,
    BlockSpec,
    CandidateValues,
    EpisodeOutcome,
    Grids,
    P1Spec,
    ScenarioGroups,
    bootstrap_rows,
    check_block_groups,
    episode_key_columns,
    episode_row,
    float_text,
    plan_block,
    stage_scenarios,
)
from neuroeco.application.evaluation import EpisodeResult
from neuroeco.application.metrics import episode_metrics
from neuroeco.domain.records import EpisodeRecord, SpeciesOutcome
from neuroeco.domain.state import NOT_DEAD, DeathCause
from support import PROVISIONAL_WORLD

ALIVE, STARVED, CAPTURED = DeathCause.ALIVE, DeathCause.STARVATION, DeathCause.CAPTURED
VALUES = CandidateValues(30.0, 50, 40, 15, 8, 0.3, 0.5, 0.5)
SPEC = P1Spec(
    "P1",
    BlockSet(
        calibration=BlockSpec(2, ScenarioGroups(1000, 1001, 1002)),
        confirmation=BlockSpec(2, ScenarioGroups(1010, 1011, 1012)),
        second_confirmation=BlockSpec(2, ScenarioGroups(1020, 1021, 1022)),
    ),
    Grids((0.2, 0.3, 0.4, 0.5), (0.3, 0.5, 0.7)),
)
TASK = plan_block(SPEC, "calibration", VALUES, scenarios=("A",), conditions=("rules",))[0]


def species(death_steps, causes, events=None) -> SpeciesOutcome:
    n = len(causes)
    return SpeciesOutcome(
        death_step=np.array(death_steps, dtype=np.int64),
        death_cause=np.array(causes, dtype=np.int8),
        final_energy=np.full(n, 50.0),
        energy_gained=np.full(n, 10.0),
        energy_spent=np.full(n, 30.0),
        events=np.array(events if events is not None else [0] * n, dtype=np.int64),
    )


def outcome(*, steps, t_max=1000, prey, predators, capture_steps=()) -> tuple:
    """An EpisodeOutcome around a hand-built record and the matching world."""
    k = len(capture_steps)
    n_prey = prey.death_step.size
    record = EpisodeRecord(
        t_max=t_max,
        steps=steps,
        prey=prey,
        predators=predators,
        capture_step=np.array(capture_steps, dtype=np.int64),
        capture_predator=np.zeros(k, dtype=np.int64),
        capture_prey=np.arange(k, dtype=np.int64),
        feeding_step=np.empty(0, dtype=np.int64),
        feeding_prey=np.empty(0, dtype=np.int64),
        feeding_plant=np.empty(0, dtype=np.int64),
        prey_alive_after=np.full(steps, n_prey, dtype=np.int64),
        prey_captured_after=np.full(steps, k, dtype=np.int64),
        prey_starved_after=np.zeros(steps, dtype=np.int64),
        predators_alive_after=np.zeros(steps, dtype=np.int64),
        plants_active_after=np.zeros(steps, dtype=np.int64),
    )
    result = EpisodeResult(TASK.identity, record, episode_metrics(record))
    world = dataclasses.replace(
        PROVISIONAL_WORLD,
        t_max=t_max,
        n_prey=n_prey,
        n_predators=predators.death_step.size,
    )
    columns = episode_key_columns(TASK.seed_group, TASK.item)
    return EpisodeOutcome(TASK, "synthetic-hash", columns, result, steps), world


def row_of(**kwargs) -> dict:
    data, world = outcome(**kwargs)
    return episode_row(data, world, stage="A", iteration=1, values=VALUES)


PREY_THREE = species([NOT_DEAD, 120, 300], [ALIVE, CAPTURED, STARVED])


# ---------------------------------------------------------------- stages and columns


def test_stage_scenarios() -> None:
    assert [stage_scenarios(s) for s in "ABC"] == [("A",), ("A", "B"), ("A", "C")]
    with pytest.raises(ValueError, match="stage must be one of"):
        stage_scenarios("entry")


def test_episode_columns_are_documented_with_types() -> None:
    assert EPISODE_COLUMNS[:5] == ("block", "stage", "iteration", "scenario", "condition")
    assert EPISODE_COLUMNS[5:14] == KEY_COLUMNS
    assert len(set(EPISODE_COLUMNS)) == len(EPISODE_COLUMNS) == 44
    assert {kind for _, kind in EPISODE_COLUMN_TYPES} == {"str", "int", "float"}
    assert BOOTSTRAP_COLUMNS == (
        "comparison",
        "comparison_name",
        "project_seed",
        "purpose",
        "seed_group",
        "run",
        "generation",
        "item",
        "stream",
    )


def test_float_text_is_the_round_trip_representation() -> None:
    assert float_text(0.1) == "0.1" and float(float_text(0.1)) == 0.1
    assert float_text(30) == "30.0"
    assert float_text(-0.0) == "-0.0"
    for bad in (math.nan, math.inf):
        with pytest.raises(ValueError, match="must be finite"):
            float_text(bad)


# ---------------------------------------------------------------- episode rows


def test_full_length_episode_row() -> None:
    predators = species(
        [499, 500, NOT_DEAD, NOT_DEAD], [STARVED, STARVED, ALIVE, ALIVE], events=[0, 1, 1, 2]
    )
    row = row_of(steps=1000, prey=PREY_THREE, predators=predators, capture_steps=(120,))
    assert tuple(row) == EPISODE_COLUMNS
    assert row["block"] == "calibration" and row["stage"] == "A" and row["iteration"] == 1
    assert (row["scenario"], row["condition"], row["config_hash"]) == (
        "A",
        "rules",
        "synthetic-hash",
    )
    assert {k: row[k] for k in KEY_COLUMNS} == episode_key_columns(1000, 0)
    assert (row["plant_energy"], row["prey_flee_threshold"], row["regrow_delay"]) == (
        "30.0",
        "0.3",
        50,
    )
    assert (row["t_max"], row["n_prey"], row["n_predators"], row["n_plants"]) == (1000, 3, 4, 40)
    assert (row["prey_survival_numerator"], row["prey_survival_denominator"]) == (
        1000 + 120 + 300,
        3 * 1000,
    )
    assert (row["prey_alive_end"], row["prey_captured"], row["prey_starved"]) == (1, 1, 1)
    assert row["exposure"] == 3 * 1000
    assert row["prey_net_energy_rate"] == float_text(3 * (10.0 - 30.0) / 3000)
    # B3 (D2): t_i = 499 < 500 does not reach; 500 reaches; survivors reach with t_i = 1000
    assert row["predators_reaching_half"] == 3
    assert row["predators_censored_before_half"] == row["predators_censored_after_half"] == 0
    # B6 (D3): two predators alive at T_max, one of them with fewer than two captures
    assert row["predators_alive_at_t_max"] == 2
    assert row["predators_alive_at_t_max_below_two_captures"] == 1
    assert (row["predators_alive_end"], row["predators_starved"]) == (2, 2)


@pytest.mark.parametrize(
    ("steps", "reaching", "before", "after"),
    [(400, 0, 2, 0), (499, 0, 2, 0), (500, 2, 0, 2), (600, 2, 0, 2)],
)
def test_early_end_censors_the_surviving_predators(steps, reaching, before, after) -> None:
    prey = species([steps - 1, steps - 1], [STARVED, STARVED])
    predators = species([NOT_DEAD, NOT_DEAD], [ALIVE, ALIVE], events=[3, 3])
    row = row_of(steps=steps, prey=prey, predators=predators)
    assert row["predators_reaching_half"] == reaching
    assert (row["predators_censored_before_half"], row["predators_censored_after_half"]) == (
        before,
        after,
    )
    # an early end never puts a predator alive at T_max (D3)
    assert row["predators_alive_at_t_max"] == 0
    assert row["predators_alive_at_t_max_below_two_captures"] == 0


def test_early_captures_use_the_metric_limit() -> None:
    prey = species([49, 50, NOT_DEAD], [CAPTURED, CAPTURED, ALIVE])
    predators = species([NOT_DEAD], [ALIVE], events=[2])
    row = row_of(steps=1000, prey=prey, predators=predators, capture_steps=(49, 50))
    assert row["early_captures"] == 1  # 49 < 0.05 * 1000 <= 50
    assert row["prey_captured"] == 2


def test_rows_without_predators() -> None:
    row = row_of(steps=1000, prey=PREY_THREE, predators=species([], []), capture_steps=(120,))
    assert row["n_predators"] == row["predators_alive_end"] == 0
    assert row["predators_reaching_half"] == row["predators_alive_at_t_max"] == 0


def test_row_consistency_checks() -> None:
    data, world = outcome(
        steps=1000, prey=PREY_THREE, predators=species([], []), capture_steps=(120,)
    )
    with pytest.raises(ValueError, match="does not match the resolved configuration"):
        episode_row(
            data, dataclasses.replace(world, n_prey=4), stage="A", iteration=1, values=VALUES
        )
    with pytest.raises(ValueError, match="stage must be one of"):
        episode_row(data, world, stage="D", iteration=1, values=VALUES)
    inconsistent, world = outcome(steps=1000, prey=PREY_THREE, predators=species([], []))
    with pytest.raises(RuntimeError, match="captured prey and capture events disagree"):
        episode_row(inconsistent, world, stage="A", iteration=1, values=VALUES)


# ---------------------------------------------------------------- bootstrap key rows


@pytest.mark.parametrize(
    ("scenarios", "expected"),
    [
        (("A",), [3, 6]),
        (("A", "B"), [1, 3, 4, 6, 7]),
        (("A", "C"), [2, 3, 5, 6, 8]),
        (("A", "B", "C"), [1, 2, 3, 4, 5, 6, 7, 8]),
    ],
)
def test_bootstrap_rows_cover_the_executed_comparisons(scenarios, expected) -> None:
    block = SPEC.blocks.calibration
    rows = bootstrap_rows(block, 7, scenarios, 123456789012345678901234567890)
    assert [row["comparison"] for row in rows] == expected
    for row in rows:
        assert tuple(row) == BOOTSTRAP_COLUMNS
        assert row["project_seed"] == "123456789012345678901234567890"
        assert (
            row["purpose"],
            row["seed_group"],
            row["run"],
            row["generation"],
            row["stream"],
        ) == (
            5,
            1000,
            7,
            0,
            7,
        )
        assert row["item"] == row["comparison"]


# ---------------------------------------------------------------- block groups (D16, T3-9)


def test_planned_tasks_pass_the_group_check() -> None:
    for block in ("calibration", "confirmation", "second_confirmation"):
        check_block_groups(plan_block(SPEC, block, VALUES), SPEC, block)


def test_tasks_are_checked_by_group_not_by_label() -> None:
    confirmation = plan_block(SPEC, "confirmation", VALUES, ("A",), ("rules",))
    relabeled = [dataclasses.replace(t, block="calibration") for t in confirmation]
    with pytest.raises(ValueError, match="seed_group 1010 is not the group 1000"):
        check_block_groups(relabeled, SPEC, "calibration")
    with pytest.raises(ValueError, match="task of block 'confirmation'"):
        check_block_groups(confirmation, SPEC, "calibration")


def test_other_group_check_failures() -> None:
    tasks = list(plan_block(SPEC, "calibration", VALUES, ("A",), ("rules",)))
    with pytest.raises(ValueError, match="no episodes"):
        check_block_groups([], SPEC, "calibration")
    with pytest.raises(ValueError, match=r"item outside 0\.\.1"):
        check_block_groups([dataclasses.replace(tasks[0], item=2)], SPEC, "calibration")
    with pytest.raises(ValueError, match="planned twice"):
        check_block_groups([tasks[0], tasks[0]], SPEC, "calibration")
