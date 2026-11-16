"""F4 T4b: the P1-18 transitions that depend on results (ADR-033; D-T4b-2, 3, 4).

Synthetic steps and outcomes only. Stage B and C cannot be reached through a verified walk
before T4c (S_A met always leads to a round), so their transitions are checked through
``options_after``, which the walk itself uses.
"""

import pytest

from neuroeco.analysis.sequence import (
    ENTRY,
    ITERATION,
    ROUND,
    Outcome,
    Step,
    Verdict,
    options_after,
    verify_sequence,
)


def it(number, stage="A", changed="none", met=None, failed_b=()):
    outcome = None if met is None else Outcome(met, tuple(failed_b))
    return Step(ITERATION, number, stage, changed, outcome=outcome)


def rnd(number, after):
    return Step(ROUND, number, after_iteration=after)


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
        # what follows a round needs its results and A_rev (T4c): never accepted silently
        (
            [it(1, met=True), rnd(1, 1), it(2, changed="plant_energy")],
            Verdict.NOT_VERIFIABLE,
            "T4c",
        ),
        (
            [it(1, met=True), rnd(1, 1), it(2, changed="plant_energy", met=False)],
            Verdict.NOT_VERIFIABLE,
            "T4c",
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
