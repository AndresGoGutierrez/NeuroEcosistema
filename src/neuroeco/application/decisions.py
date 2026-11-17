"""Author decisions of the P1 calibration (F4 T4d, D-T4d-3).

ADR-033 (P1-18) leaves three judgements to the author; each one is pre-registered as a
versioned file ``configs/pilots/p1_decisions/NNN.yaml`` (schema ``neuroeco.p1-decision/1``)
that ``pilot p1`` verifies before running the step it authorizes:

- ``b_criteria`` (D-T4b-3): after an iteration of stage B or C that met S_X with computable B
  criteria missed, the next step (``repeat_stage``: another iteration of the stage with an
  identifiable parametric cause; ``next_stage``: move on) needs a documented decision on
  exactly those criteria;
- ``entry_review`` (state E): the confirmation needs a decision on **every** B and C row of
  the entry evaluation, with its result;
- ``d9_e5`` (D9): a stage-A iteration may change ``n_plants`` through the E5 route only when
  the ``plant_energy`` that would be needed violates E5; the decision states that value and is
  bound to the iteration specification by its SHA-256.

Every decision is bound by SHA-256 to what it judges (the published block and its criteria, or
the iteration specification), so it cannot be reused for another step.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

DECISION_SCHEMA = "neuroeco.p1-decision/1"
B_CRITERIA, ENTRY_REVIEW, D9_E5 = "b_criteria", "entry_review", "d9_e5"
NEXT_STAGE, REPEAT_STAGE = "next_stage", "repeat_stage"
STEP_KINDS = {
    B_CRITERIA: ("iteration", "entry"),
    ENTRY_REVIEW: ("confirmation",),
    D9_E5: ("iteration",),
}
_SHA256 = re.compile(r"[0-9a-f]{64}")


def _text(name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} must not be empty (P1-19)")


def _sha256(name: str, value: str) -> None:
    if not _SHA256.fullmatch(value):
        raise ValueError(f"{name} must be a SHA-256 in lowercase hexadecimal")


@dataclass(frozen=True)
class StepRef:
    """The step a decision authorizes."""

    kind: str  # iteration | entry | confirmation
    number: int  # 0 for the entry and the confirmation

    @property
    def key(self) -> tuple[str, int]:
        return (self.kind, self.number)


@dataclass(frozen=True)
class JudgedBlock:
    """The published block a decision judges, bound by SHA-256."""

    directory: str  # relative to the root of the P1 results, e.g. calibration/iteration_004
    provenance_sha256: str
    criteria_sha256: str

    def __post_init__(self) -> None:
        _text("judges.directory", self.directory)
        _sha256("judges.provenance_sha256", self.provenance_sha256)
        _sha256("judges.criteria_sha256", self.criteria_sha256)


@dataclass(frozen=True)
class DecisionItem:
    """The decision on one criterion row (``criteria.csv``) and its result."""

    criterion: str
    part: str
    scenario: str
    status: str
    decision: str
    justification: str

    def __post_init__(self) -> None:
        _text("items.criterion", self.criterion)
        _text("items.status", self.status)
        _text("items.decision", self.decision)
        _text("items.justification", self.justification)

    @property
    def key(self) -> str:
        """Same form as the missed B criteria of the sequence: ``B4/ii@B-A``."""
        return f"{self.criterion}{'/' + self.part if self.part else ''}@{self.scenario}"


def _check_common(decision: int, kind: str, expected: str, step: StepRef, schema: str) -> None:
    if schema != DECISION_SCHEMA:
        raise ValueError(f"schema must be {DECISION_SCHEMA!r}")
    if decision < 1:
        raise ValueError("decision must be an integer >= 1")
    if kind != expected:
        raise ValueError(f"kind must be {expected!r}")
    if step.kind not in STEP_KINDS[kind]:
        raise ValueError(f"a {kind} decision authorizes a step of kind {STEP_KINDS[kind]}")
    if step.number < (0 if step.kind != "iteration" else 1):
        raise ValueError("step.number is out of range")


@dataclass(frozen=True)
class BCriteriaDecision:
    schema: str
    decision: int
    kind: str
    step: StepRef
    judges: JudgedBlock
    choice: str
    items: tuple[DecisionItem, ...]
    justification: str

    def __post_init__(self) -> None:
        _check_common(self.decision, self.kind, B_CRITERIA, self.step, self.schema)
        if self.choice not in (NEXT_STAGE, REPEAT_STAGE):
            raise ValueError(f"choice must be {NEXT_STAGE!r} or {REPEAT_STAGE!r}")
        if not self.items:
            raise ValueError("items must list the missed B criteria")
        _text("justification", self.justification)


@dataclass(frozen=True)
class EntryReviewDecision:
    schema: str
    decision: int
    kind: str
    step: StepRef
    judges: JudgedBlock
    items: tuple[DecisionItem, ...]
    justification: str

    def __post_init__(self) -> None:
        _check_common(self.decision, self.kind, ENTRY_REVIEW, self.step, self.schema)
        if self.step.number != 0:
            raise ValueError("the confirmation is step 0")
        if not self.items:
            raise ValueError("items must list every B and C row of the entry evaluation")
        _text("justification", self.justification)


@dataclass(frozen=True)
class D9E5Decision:
    schema: str
    decision: int
    kind: str
    step: StepRef
    plant_energy_needed: float
    iteration_spec_sha256: str
    justification: str

    def __post_init__(self) -> None:
        _check_common(self.decision, self.kind, D9_E5, self.step, self.schema)
        if not math.isfinite(self.plant_energy_needed) or self.plant_energy_needed <= 0:
            raise ValueError("plant_energy_needed must be a finite number > 0")
        _sha256("iteration_spec_sha256", self.iteration_spec_sha256)
        _text("justification", self.justification)


AuthorDecision = BCriteriaDecision | EntryReviewDecision | D9E5Decision
DECISION_TYPES: dict[str, type] = {
    B_CRITERIA: BCriteriaDecision,
    ENTRY_REVIEW: EntryReviewDecision,
    D9_E5: D9E5Decision,
}


def cites_decision(motive: str, number: int) -> bool:
    """Whether an iteration motive cites ``decision N`` (also ``decisión N``)."""
    pattern = rf"\bdecisi[oó]n\s+0*{number}\b"
    return re.search(pattern, motive, flags=re.IGNORECASE) is not None
