"""F4 T4b and T4c: the P1-18 transitions that depend on results (ADR-033; D-T4b-2, 3, 4).

Synthetic steps and outcomes only. Some transitions of stages B and C are also checked through
``options_after``, which the walk itself uses.
"""

import pytest

from neuroeco.analysis.sequence import (
    ENTRY,
    ITERATION,
    ROUND,
    Outcome,
    RoundResult,
    Step,
    Verdict,
    options_after,
    verify_sequence,
)

RULES_IN_FORCE = {
    "prey_flee_threshold": 0.3,
    "prey_cruise_fraction": 0.5,
    "predator_cruise_fraction": 0.5,
}
WINNERS = {"prey_flee_threshold": 0.5, "prey_cruise_fraction": 0.3, "predator_cruise_fraction": 0.7}


def it(number, stage="A", changed="none", met=None, failed_b=(), values=None):
    outcome = None if met is None else Outcome(met, tuple(failed_b))
    return Step(ITERATION, number, stage, changed, outcome=outcome, values=values)


def rnd(number, after, *, changed=None, a_rev=None, values=RULES_IN_FORCE):
    """A round; ``changed`` None: its grids have not run; ``a_rev`` None: A_rev has not run."""
    result = None
    if changed is not None:
        reevaluation = None if a_rev is None else Outcome(a_rev)
        result = RoundResult(changed, WINNERS if changed else values, reevaluation)
    return Step(ROUND, number, after_iteration=after, values=values, round_result=result)


A_MISSED = [it(1, met=False)] + [it(n, changed="plant_energy", met=False) for n in range(2, 6)]


@pytest.mark.parametrize(
    ("steps", "verdict", "fragment"),
    [
        ([], Verdict.ALLOWED, "nothing has run"),
        ([it(1)], Verdict.ALLOWED, "first iteration"),
        ([it(2)], Verdict.REJECTED, "starts with iteration 1"),
        # A_eval: S_A missed -> A_ajuste; S_A met -> a round (r < 3), never A or B
        ([it(1, met=False), it(2, changed="plant_energy")], Verdict.ALLOWED, "A_ajuste"),
        ([it(1, met=False), it(2, "B")], Verdict.REJECTED, "stage-A iteration"),
        ([it(1, met=True), rnd(1, 1)], Verdict.ALLOWED, "a round"),
        ([it(1, met=True), it(2, changed="plant_energy")], Verdict.REJECTED, "must be a round"),
        ([it(1, met=True), it(2, "B")], Verdict.REJECTED, "must be a round"),
        ([it(1, met=True), rnd(1, 2)], Verdict.REJECTED, "must follow iteration 1"),
        # a round without its results is the step to run; nothing after it may have results
        (
            [it(1, met=True), rnd(1, 1), it(2, changed="plant_energy")],
            Verdict.ALLOWED,
            "a round",
        ),
        (
            [it(1, met=True), rnd(1, 1), it(2, changed="plant_energy", met=False)],
            Verdict.REJECTED,
            "have results while round 1 is not complete",
        ),
        # budget: iA = 5 with S_A missed is a STOP, with or without a sixth iteration
        (A_MISSED, Verdict.STOP, "iA = 5"),
        ([*A_MISSED, it(6, changed="plant_energy")], Verdict.STOP, "iA = 5"),
        (A_MISSED[:4], Verdict.ALLOWED, "iA = 4 < 5"),
    ],
)
def test_stage_a_transitions(steps, verdict, fragment) -> None:
    report = verify_sequence(steps)
    assert report.verdict is verdict
    assert fragment in report.reason


@pytest.mark.parametrize(
    ("steps", "confirmed", "verdict"),
    [
        # two consecutive unsuccessful A iterations that changed plant_energy / regrow_delay
        (
            [
                it(1, met=False),
                it(2, changed="plant_energy", met=False),
                it(3, changed="regrow_delay", met=False),
                it(4, changed="n_plants_a"),
            ],
            (),
            Verdict.ALLOWED,
        ),
        # only one of them changed plant_energy (iteration 1 changes nothing)
        (
            [
                it(1, met=False),
                it(2, changed="plant_energy", met=False),
                it(3, changed="n_plants_a"),
            ],
            (),
            Verdict.AUTHOR_CONFIRMATION,
        ),
        # the E5 route, confirmed by the author for iteration 3
        (
            [
                it(1, met=False),
                it(2, changed="plant_energy", met=False),
                it(3, changed="n_plants_a"),
            ],
            (3,),
            Verdict.ALLOWED,
        ),
        # not consecutive: an n_plants iteration in between does not count
        (
            [
                it(1, met=False),
                it(2, changed="plant_energy", met=False),
                it(3, changed="n_plants_a", met=False),
                it(4, changed="regrow_delay", met=False),
                it(5, changed="n_plants_a"),
            ],
            (3,),
            Verdict.AUTHOR_CONFIRMATION,
        ),
    ],
)
def test_d9_routes_for_changing_n_plants(steps, confirmed, verdict) -> None:
    report = verify_sequence(steps, d9_confirmed=confirmed)
    assert report.verdict is verdict
    assert "D9" in report.reason or "E5" in report.reason


@pytest.mark.parametrize(
    ("step", "used", "rounds", "successors", "terminal"),
    [
        (it(4, met=True), 4, 3, ((ITERATION, "B"),), None),  # r = 3: T_fin, then B
        (it(2, "B", met=False), 2, 1, ((ITERATION, "B"),), None),
        (it(6, "B", met=False), 5, 1, (), Verdict.STOP),
        (it(2, "B", met=True), 1, 1, ((ITERATION, "C"),), None),  # never back to A
        (
            it(2, "B", met=True, failed_b=["B4/ii@B-A"]),
            1,
            1,
            ((ITERATION, "B"), (ITERATION, "C")),
            None,
        ),
        (it(6, "B", met=True, failed_b=["B4/ii@B-A"]), 5, 1, ((ITERATION, "C"),), None),
        (it(3, "C", met=False), 1, 1, ((ITERATION, "C"),), None),
        (it(3, "C", met=True), 1, 1, ((ENTRY, ""),), None),
        (it(3, "C", met=True, failed_b=["B5@C-A"]), 1, 1, ((ITERATION, "C"), (ENTRY, "")), None),
        (Step(ENTRY, 0, outcome=Outcome(True)), 0, 1, (), Verdict.AUTHOR_AUTHORIZATION),
        (Step(ENTRY, 0, outcome=Outcome(False)), 0, 1, (), Verdict.STOP),
    ],
)
def test_transitions_after_b_c_and_the_entry(step, used, rounds, successors, terminal) -> None:
    counters = {"A": 1, "B": 0, "C": 0}
    if step.kind == ITERATION:
        counters[step.stage] = used
    options = options_after(step, counters, rounds)
    assert (options.successors, options.terminal) == (successors, terminal)
    if step.outcome and step.outcome.failed_b and len(successors) == 2:
        # D-T4b-3: both are allowed, and the report says it is the author's judgement
        assert "documented decision" in options.notes[0]
        assert "not an automatic check" in options.notes[0]


# ---------------------------------------------------------------- after a round (T4c, C3)

A_MET = it(1, met=True, values=RULES_IN_FORCE)


def after_winners(number, stage="A", changed="none", met=None):
    return it(number, stage, changed, met, values=WINNERS)


@pytest.mark.parametrize(
    ("steps", "verdict", "fragment"),
    [
        # no value changed: T_fin, then stage B with the values in force
        (
            [A_MET, rnd(1, 1, changed=False), it(2, "B", values=RULES_IN_FORCE)],
            Verdict.ALLOWED,
            "T_fin",
        ),
        (
            [A_MET, rnd(1, 1, changed=False), it(2, changed="plant_energy")],
            Verdict.REJECTED,
            "stage-B",
        ),
        # values changed: A_rev must run before anything else
        ([A_MET, rnd(1, 1, changed=True), it(2, "B")], Verdict.ALLOWED, "a round"),
        # A_rev met S_A with r = 1: another round, never stage B yet
        (
            [A_MET, rnd(1, 1, changed=True, a_rev=True), rnd(2, 1, values=WINNERS)],
            Verdict.ALLOWED,
            "r = 1 < 3",
        ),
        (
            [A_MET, rnd(1, 1, changed=True, a_rev=True), after_winners(2, "B")],
            Verdict.REJECTED,
            "a round",
        ),
        # A_rev missed S_A: alternation and A_ajuste with the winning rules
        (
            [A_MET, rnd(1, 1, changed=True, a_rev=False), after_winners(2, changed="plant_energy")],
            Verdict.ALLOWED,
            "v = 1 <= 3",
        ),
        # the step after a round must carry exactly the winning rule values
        (
            [
                A_MET,
                rnd(1, 1, changed=True, a_rev=False),
                it(2, changed="plant_energy", values=RULES_IN_FORCE),
            ],
            Verdict.REJECTED,
            "must be its winners",
        ),
        (
            [A_MET, rnd(1, 1, changed=True, a_rev=True), rnd(2, 1)],
            Verdict.REJECTED,
            "must be its winners",
        ),
        ([A_MET, rnd(1, 1, changed=False), rnd(2, 1)], Verdict.REJECTED, "stage-B"),
    ],
)
def test_transitions_after_a_round(steps, verdict, fragment) -> None:
    report = verify_sequence(steps)
    assert report.verdict is verdict
    assert fragment in report.reason


def test_three_rounds_without_convergence_lead_to_stage_b_with_a_note() -> None:
    steps = [
        A_MET,
        rnd(1, 1, changed=True, a_rev=True),
        rnd(2, 1, changed=True, a_rev=True, values=WINNERS),
        rnd(3, 1, changed=True, a_rev=True, values=WINNERS),
        after_winners(2, "B"),
    ]
    report = verify_sequence(steps)
    assert report.verdict is Verdict.ALLOWED and "r = 3" in report.reason
    assert "did not converge" in report.notes[0]
    assert verify_sequence([*steps[:-1], rnd(4, 1, values=WINNERS)]).verdict is Verdict.REJECTED


def test_alternations_and_stage_a_budget_after_failed_re_evaluations() -> None:
    """Three failed A_rev give v = 3 (v <= r <= 3, ADR-033); iA = 5 ends in a STOP."""
    steps = [A_MET]
    for round_number in range(1, 4):  # each round: changed, A_rev missed, then A_ajuste
        steps.append(
            rnd(round_number, round_number, changed=True, a_rev=False, values=steps[-1].values)
        )
        steps.append(after_winners(round_number + 1, changed="plant_energy", met=True))
    third = verify_sequence(steps)
    assert third.verdict is Verdict.ALLOWED and "r = 3: T_fin" in third.reason  # v = 3 allowed
    assert [t.reason for t in third.transitions if "v = 3" in t.reason]
    assert verify_sequence([*steps, after_winners(5, "B")]).verdict is Verdict.ALLOWED

    budget = [
        it(1, met=False, values=RULES_IN_FORCE),
        *(it(n, changed="plant_energy", met=False, values=RULES_IN_FORCE) for n in (2, 3, 4)),
        it(5, changed="plant_energy", met=True, values=RULES_IN_FORCE),
        rnd(1, 5, changed=True, a_rev=False),
    ]
    report = verify_sequence(budget)
    assert report.verdict is Verdict.STOP and "iA = 5" in report.reason
