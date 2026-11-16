"""Verifier of the P1 calibration sequence against the results (F4 T4b; ADR-033 P1-18).

The static rules of P1-18 (numbering, A -> B -> C without return, budgets on the registered
specifications, one parameter per iteration) are checked by ``application.calibration`` when
``pilot p1`` runs. This module checks the rules that depend on results: given the ordered steps
of the calibration (registered iterations and rounds, and the entry evaluation) with the outcome
of each completed one, it decides whether every transition, and the next step, is one that the
state machine of P1-18 allows after that outcome:

- A_eval: S_A met -> a round while r < 3, stage B once r = 3; S_A not met -> another stage-A
  iteration while iA < 5, STOP at iA = 5;
- D9 (author decision D-T4b-4): a stage-A iteration may change ``n_plants`` only right after two
  consecutive stage-A iterations that changed ``plant_energy`` or ``regrow_delay`` and missed
  S_A; the other route of D9 (the needed ``plant_energy`` change would violate E5) is never
  deduced and needs the explicit confirmation of the author;
- B_eval and C_eval: S_X not met -> another iteration of the stage while iX < 5, STOP at 5;
  S_X met with every computable B criterion met -> the next stage (C, then the entry
  evaluation); S_X met with a B criterion missed -> either, and the report states that the
  choice needs a justification and a documented decision of the author (D-T4b-3);
- E: the whole class A met -> author authorization (D11); otherwise STOP;
- no return from B or C to A.

What follows a round depends on the round's results and on A_rev, which do not exist before
task T4c: those transitions are reported as not verifiable and never accepted silently
(D-T4b-2). The verifier reads results only; it runs no episode and writes nothing.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

STAGES = ("A", "B", "C")
STAGE_ITERATION_LIMIT = 5  # iA, iB, iC (P1-18)
ROUND_LIMIT = 3  # r (P1-18)
ITERATION, ROUND, ENTRY = "iteration", "round", "entry"
D9_PARAMETERS = ("plant_energy", "regrow_delay")
N_PLANTS_A = "n_plants_a"


class Verdict(StrEnum):
    ALLOWED = "allowed"
    REJECTED = "rejected"
    STOP = "stop"  # P1-18: stop F4 and consult the author
    NOT_VERIFIABLE = "not_verifiable_until_T4c"
    AUTHOR_CONFIRMATION = "author_confirmation_required"  # D9 through E5
    AUTHOR_AUTHORIZATION = "author_authorization_required"  # the entry met class A (D11)


@dataclass(frozen=True)
class Outcome:
    """Result of a completed evaluation: its requirements and the computable B it missed."""

    requirements_met: bool  # S_A, S_B, S_C, or the whole class A for the entry
    failed_b: tuple[str, ...] = ()


@dataclass(frozen=True)
class Step:
    """One step of the calibration: a registered iteration, a registered round or the entry."""

    kind: str
    number: int  # iteration or round number; 0 for the entry
    stage: str = ""  # A, B or C for an iteration
    changed_parameter: str = ""
    after_iteration: int = 0  # rounds only
    outcome: Outcome | None = None  # None: no published result yet

    @property
    def label(self) -> str:
        if self.kind == ITERATION:
            return f"iteration {self.number} (stage {self.stage})"
        if self.kind == ROUND:
            return f"round {self.number}"
        return "entry evaluation"


@dataclass(frozen=True)
class Transition:
    source: str
    target: str
    verdict: Verdict
    reason: str
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class SequenceReport:
    """Every verified transition and the verdict on what comes next."""

    transitions: tuple[Transition, ...]
    next_step: str
    verdict: Verdict
    reason: str
    notes: tuple[str, ...] = field(default=())


@dataclass
class _Counters:
    iterations: dict[str, int] = field(default_factory=lambda: dict.fromkeys(STAGES, 0))
    rounds: int = 0


@dataclass(frozen=True)
class _Options:
    """What P1-18 allows after one completed step: successors, or a terminal verdict."""

    successors: tuple[tuple[str, str], ...]  # (kind, stage); stage "" for a round or the entry
    reason: str
    notes: tuple[str, ...] = ()
    terminal: Verdict | None = None


def options_after(step: Step, iterations: dict[str, int], rounds: int) -> _Options:
    """The successors that P1-18 allows after the completed ``step`` (counters include it)."""
    if step.kind == ROUND:
        return _Options(
            (),
            f"what follows {step.label} depends on its results and on A_rev (task T4c)",
            terminal=Verdict.NOT_VERIFIABLE,
        )
    assert step.outcome is not None
    met, failed_b = step.outcome.requirements_met, step.outcome.failed_b
    if step.kind == ENTRY:
        if met:
            return _Options(
                (),
                "the entry evaluation met the whole class A: the confirmation needs the "
                "express authorization of the author (P1-21, D11)",
                terminal=Verdict.AUTHOR_AUTHORIZATION,
            )
        return _Options(
            (), "the entry evaluation missed a class-A criterion", terminal=Verdict.STOP
        )

    stage, used = step.stage, iterations[step.stage]
    if stage == "A":
        if met and rounds < ROUND_LIMIT:
            return _Options(((ROUND, ""),), f"S_A met with r = {rounds} < 3: a round (T)")
        if met:
            return _Options(((ITERATION, "B"),), "S_A met with r = 3: T_fin, then stage B")
        if used < STAGE_ITERATION_LIMIT:
            return _Options(((ITERATION, "A"),), f"S_A not met with iA = {used} < 5: A_ajuste")
        return _Options((), "S_A not met with iA = 5", terminal=Verdict.STOP)

    following = (ITERATION, "C") if stage == "B" else (ENTRY, "")
    same = (ITERATION, stage)
    room = used < STAGE_ITERATION_LIMIT
    if not met:
        if room:
            return _Options((same,), f"S_{stage} not met with i{stage} = {used} < 5")
        return _Options((), f"S_{stage} not met with i{stage} = 5", terminal=Verdict.STOP)
    if not failed_b:
        return _Options((following,), f"S_{stage} met and every computable B criterion met")
    note = (
        f"computable B criteria missed: {list(failed_b)}; another stage-{stage} iteration "
        "needs an identifiable parametric cause, moving on needs a documented decision of the "
        "author (P1-18). This is the author's judgement, not an automatic check."
    )
    successors = (same, following) if room else (following,)
    return _Options(successors, f"S_{stage} met with B criteria missed", (note,))


def _matches(step: Step, successor: tuple[str, str]) -> bool:
    kind, stage = successor
    return step.kind == kind and (kind != ITERATION or step.stage == stage)


def _describe(successors: Sequence[tuple[str, str]]) -> str:
    names = {ROUND: "a round", ENTRY: "the entry evaluation"}
    return " or ".join(names.get(k, f"a stage-{s} iteration") for k, s in successors)


def _d9(history: Sequence[Step], target: Step, confirmed: frozenset[int]) -> Transition | None:
    """D9 for a stage-A iteration that changes n_plants (None when D9 does not apply)."""
    if not (target.kind == ITERATION and target.stage == "A"):
        return None
    if target.changed_parameter != N_PLANTS_A:
        return None
    last_two = history[-2:]
    unsuccessful = len(last_two) == 2 and all(
        s.kind == ITERATION
        and s.stage == "A"
        and s.changed_parameter in D9_PARAMETERS
        and s.outcome is not None
        and not s.outcome.requirements_met
        for s in last_two
    )
    source = history[-1].label
    if unsuccessful:
        return Transition(
            source,
            target.label,
            Verdict.ALLOWED,
            "n_plants after two consecutive unsuccessful stage-A iterations that changed "
            "plant_energy or regrow_delay (D9)",
        )
    if target.number in confirmed:
        return Transition(
            source,
            target.label,
            Verdict.ALLOWED,
            "n_plants through the E5 route of D9, confirmed by the author",
            ("the author's confirmation must be documented in the iteration's motive (P1-19)",),
        )
    return Transition(
        source,
        target.label,
        Verdict.AUTHOR_CONFIRMATION,
        "n_plants without two consecutive unsuccessful stage-A iterations that changed "
        "plant_energy or regrow_delay: only the E5 route of D9 is left, and the needed "
        "plant_energy change is never deduced; it needs the explicit, documented "
        "confirmation of the author",
    )


def verify_sequence(steps: Sequence[Step], *, d9_confirmed: Sequence[int] = ()) -> SequenceReport:
    """Check every transition of ``steps`` (in calibration order) and the next step.

    Verification stops at the first transition that is not allowed, and at the first step
    without a result: that step is the one about to run. ``d9_confirmed`` lists the stage-A
    iterations whose change of ``n_plants`` the author confirmed through the E5 route of D9.
    """
    confirmed = frozenset(d9_confirmed)
    if not steps:
        return SequenceReport((), "iteration 1 (stage A)", Verdict.ALLOWED, "nothing has run yet")
    first = steps[0]
    if not (first.kind == ITERATION and first.number == 1 and first.stage == "A"):
        return SequenceReport(
            (), first.label, Verdict.REJECTED, "the calibration starts with iteration 1 of A"
        )
    counters = _Counters()
    transitions: list[Transition] = []
    history: list[Step] = []
    for index, step in enumerate(steps):
        # A round has no published result before T4c: it is the step about to run only when
        # nothing is registered after it; otherwise what follows it is not verifiable.
        pending = step.outcome is None and (step.kind != ROUND or index == len(steps) - 1)
        if index > 0:
            previous = history[-1]
            options = options_after(previous, counters.iterations, counters.rounds)
            transition = _transition(previous, step, options, history, confirmed)
            transitions.append(transition)
            if transition.verdict is not Verdict.ALLOWED or pending:
                return SequenceReport(
                    tuple(transitions),
                    step.label,
                    transition.verdict,
                    transition.reason,
                    transition.notes,
                )
        elif pending:
            return SequenceReport((), step.label, Verdict.ALLOWED, "the first iteration of A")
        if step.kind == ITERATION:
            counters.iterations[step.stage] += 1
        elif step.kind == ROUND:
            counters.rounds += 1
        history.append(step)
    last = history[-1]
    options = options_after(last, counters.iterations, counters.rounds)
    if options.terminal is not None:
        return SequenceReport(
            tuple(transitions), "-", options.terminal, options.reason, options.notes
        )
    return SequenceReport(
        tuple(transitions),
        _describe(options.successors),
        Verdict.ALLOWED,
        options.reason,
        options.notes,
    )


def _transition(
    previous: Step,
    step: Step,
    options: _Options,
    history: Sequence[Step],
    confirmed: frozenset[int],
) -> Transition:
    if options.terminal is not None:
        return Transition(previous.label, step.label, options.terminal, options.reason)
    if not any(_matches(step, successor) for successor in options.successors):
        return Transition(
            previous.label,
            step.label,
            Verdict.REJECTED,
            f"{options.reason}: the next step must be {_describe(options.successors)} (P1-18)",
        )
    if step.kind == ROUND and step.after_iteration != previous.number:
        return Transition(
            previous.label,
            step.label,
            Verdict.REJECTED,
            f"{step.label} must follow iteration {previous.number}",
        )
    d9 = _d9(history, step, confirmed)
    if d9 is not None:
        return d9
    return Transition(previous.label, step.label, Verdict.ALLOWED, options.reason, options.notes)
