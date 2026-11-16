"""F4 T4c (C3, D-T4c-5): the gate of ``pilot p1`` on the P1-18 sequence.

Which specifications require it (only fully synthetic ones, seed groups >= 1000, are exempt)
and which step it lets run, on synthetic steps and outcomes. No episode is run.
"""

import pytest

from neuroeco.analysis.sequence import ENTRY, ITERATION, ROUND, Outcome, RoundResult, Step
from neuroeco.application.calibration import (
    APPROVED_BLOCKS,
    SYNTHETIC_SEED_GROUPS_FROM,
    BlockSet,
    BlockSpec,
    Grids,
    P1Spec,
    ScenarioGroups,
    sequence_gate_required,
)
from neuroeco.presentation.pilot_p1 import P1RefusalError
from neuroeco.presentation.pilot_p1_sequence import gate_report

GRIDS = Grids((0.2, 0.3, 0.4, 0.5), (0.3, 0.5, 0.7))


def spec(calibration, confirmation, second, episodes=2) -> P1Spec:
    return P1Spec(
        "P1",
        BlockSet(
            calibration=BlockSpec(episodes, ScenarioGroups(*calibration)),
            confirmation=BlockSpec(episodes, ScenarioGroups(*confirmation)),
            second_confirmation=BlockSpec(episodes, ScenarioGroups(*second)),
        ),
        GRIDS,
    )


SYNTHETIC = spec((1000, 1001, 1002), (1010, 1011, 1012), (1020, 1021, 1022))


def test_only_fully_synthetic_specifications_are_exempt() -> None:
    assert SYNTHETIC_SEED_GROUPS_FROM == 1000  # D16
    real = P1Spec(
        "P1",
        BlockSet(
            **{
                name: BlockSpec(episodes, ScenarioGroups(*groups))
                for name, (episodes, groups) in APPROVED_BLOCKS.items()
            }
        ),
        GRIDS,
    )
    assert sequence_gate_required(real)
    assert not sequence_gate_required(SYNTHETIC)


@pytest.mark.parametrize(
    "groups",
    [
        # one real group anywhere (any block, any scenario)
        ((10, 1001, 1002), (1010, 1011, 1012), (1020, 1021, 1022)),
        ((1000, 1001, 1002), (1010, 1011, 1012), (1020, 1021, 32)),
        # groups that are neither real nor synthetic still require the gate
        ((33, 34, 35), (1010, 1011, 1012), (1020, 1021, 1022)),
        ((2, 3, 4), (5, 6, 7), (8, 9, 999)),
        ((1000, 1001, 999), (1010, 1011, 1012), (1020, 1021, 1022)),
    ],
)
def test_any_group_below_the_synthetic_range_requires_the_gate(groups) -> None:
    assert sequence_gate_required(spec(*groups))


def it(number, stage="A", changed="none", met=None):
    outcome = None if met is None else Outcome(met)
    return Step(ITERATION, number, stage, changed, outcome=outcome)


RULES = {"prey_flee_threshold": 0.3, "prey_cruise_fraction": 0.5, "predator_cruise_fraction": 0.5}


@pytest.mark.parametrize(
    ("steps", "kind", "number"),
    [
        ([it(1)], ITERATION, 1),
        ([it(1, met=False), it(2, changed="plant_energy")], ITERATION, 2),
        ([it(1, met=True), Step(ROUND, 1, after_iteration=1, values=RULES)], ROUND, 1),
        # a round whose grids ran and changed a value: its A_rev is still part of the round
        (
            [
                it(1, met=True),
                Step(
                    ROUND, 1, after_iteration=1, values=RULES, round_result=RoundResult(True, RULES)
                ),
            ],
            ROUND,
            1,
        ),
    ],
)
def test_the_step_the_sequence_allows_passes(steps, kind, number) -> None:
    assert gate_report(steps, kind, number).pending.number == number


# A -> round without changes (T_fin) -> B -> C: the calibration is complete.
CALIBRATED = [
    it(1, met=True),
    Step(ROUND, 1, after_iteration=1, values=RULES, round_result=RoundResult(False, RULES)),
    it(2, "B", met=True),
    it(3, "C", met=True),
]


def test_the_entry_and_the_confirmation_follow_the_sequence() -> None:
    gate_report(CALIBRATED, ENTRY, 0)
    with pytest.raises(P1RefusalError, match="must be a stage-C iteration"):
        gate_report(CALIBRATED[:3], ENTRY, 0)  # stage C never registered
    with pytest.raises(
        P1RefusalError, match="allows iteration 3 \\(stage C\\) next, not the entry"
    ):
        gate_report([*CALIBRATED[:3], it(3, "C")], ENTRY, 0)  # stage C has not run
    # The confirmation needs the entry published with the whole class A met (D11).
    entry_met = Step(ENTRY, 0, outcome=Outcome(True))
    entry_missed = Step(ENTRY, 0, outcome=Outcome(False))
    assert gate_report([*CALIBRATED, entry_met], "confirmation", 0).verdict == (
        "author_authorization_required"
    )
    with pytest.raises(P1RefusalError, match="the confirmation needs"):
        gate_report(CALIBRATED, "confirmation", 0)  # no entry evaluation yet
    with pytest.raises(P1RefusalError, match="stop"):
        gate_report([*CALIBRATED, entry_missed], "confirmation", 0)
    # P1-18 has no state for a second confirmation while no recalibration flow is approved.
    with pytest.raises(P1RefusalError, match="Mn-7"):
        gate_report([*CALIBRATED, entry_met], "second_confirmation", 0)


@pytest.mark.parametrize(
    ("steps", "kind", "number", "message"),
    [
        # A_eval -> B_eval without a round (the chain of the T3 tests)
        ([it(1, met=True), it(2, "B")], ITERATION, 2, "does not allow iteration 2 (stage B)"),
        ([it(1, met=False), it(2, "B")], ITERATION, 2, "rejected"),
        # the target is not the pending step: iteration 1 has no result yet
        ([it(1), it(2, changed="plant_energy")], ITERATION, 2, "allows iteration 1 (stage A)"),
        # the step already has its result
        ([it(1, met=False)], ITERATION, 1, "not iteration 1"),
        # a round is pending: an iteration after it cannot run
        (
            [
                it(1, met=True),
                Step(ROUND, 1, after_iteration=1, values=RULES),
                it(2, changed="plant_energy"),
            ],
            ITERATION,
            2,
            "allows round 1 next",
        ),
        # budget exhausted: STOP
        (
            [it(1, met=False)]
            + [it(n, changed="plant_energy", met=False) for n in range(2, 6)]
            + [it(6, changed="plant_energy")],
            ITERATION,
            6,
            "stop",
        ),
        # D9 through E5 without the author's confirmation
        (
            [
                it(1, met=False),
                it(2, changed="plant_energy", met=False),
                it(3, changed="n_plants_a"),
            ],
            ITERATION,
            3,
            "--d9-confirmed",
        ),
    ],
)
def test_a_step_the_sequence_does_not_allow_is_refused(steps, kind, number, message) -> None:
    with pytest.raises(P1RefusalError, match="D-T4c-5") as refused:
        gate_report(steps, kind, number)
    assert message in str(refused.value)


def test_the_author_confirmation_of_d9_is_the_only_way_through_e5() -> None:
    steps = [
        it(1, met=False),
        it(2, changed="plant_energy", met=False),
        it(3, changed="n_plants_a"),
    ]
    with pytest.raises(P1RefusalError):
        gate_report(steps, ITERATION, 3, d9_confirmed=(2,))  # another iteration: no effect
    assert gate_report(steps, ITERATION, 3, d9_confirmed=(3,)).verdict == "allowed"
