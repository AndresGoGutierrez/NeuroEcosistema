"""F4 T4d (D-T4d-3): which author decisions the sequence needs, and their bindings.

The judged blocks are small placeholder directories: the checker only reads the SHA-256 of
``provenance.json`` and ``criteria.csv`` and the rows of the criteria. No episode is run.
"""

import csv
import json

import pytest

from neuroeco.analysis.sequence import ENTRY, ITERATION, ROUND, Outcome, RoundResult, Step
from neuroeco.application.decisions import (
    BCriteriaDecision,
    DecisionItem,
    EntryReviewDecision,
    JudgedBlock,
    StepRef,
)
from neuroeco.infrastructure.provenance import file_sha256
from neuroeco.presentation.pilot_p1 import P1RefusalError
from neuroeco.presentation.pilot_p1_sequence import check_author_decisions

RULES = {"prey_flee_threshold": 0.3, "prey_cruise_fraction": 0.5, "predator_cruise_fraction": 0.5}
FIELDS = ("criterion", "class", "part", "scenario", "status")
B_ROWS = [("B1", "B", "", "B", "pass"), ("B4", "B", "ii", "B-A", "fail")]
ENTRY_ROWS = [
    ("A1", "A", "", "", "pass"),
    ("B1", "B", "", "A", "pass"),
    ("B4", "B", "ii", "B-A", "fail"),
    ("C2", "C", "", "A", "no_alert"),
]


def block(root, relative, rows, gate=None):
    directory = root / relative
    directory.mkdir(parents=True)
    provenance = {"schema": "placeholder", "sequence_gate": gate}
    (directory / "provenance.json").write_text(json.dumps(provenance), encoding="utf-8")
    with (directory / "criteria.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(FIELDS)
        writer.writerows(rows)
    return directory


def judges(directory, root):
    return JudgedBlock(
        directory.relative_to(root).as_posix(),
        file_sha256(directory / "provenance.json"),
        file_sha256(directory / "criteria.csv"),
    )


def item(criterion, part, scenario, status):
    return DecisionItem(criterion, part, scenario, status, "documented", "reason")


def b_decision(number, step, judged, choice="next_stage", items=None):
    items = items or (item("B4", "ii", "B-A", "fail"),)
    return BCriteriaDecision(
        "neuroeco.p1-decision/1", number, "b_criteria", step, judged, choice, items, "why"
    )


# A -> round without changes -> B (met, B4/ii missed) -> C
STAGE_B = Step(ITERATION, 2, "B", outcome=Outcome(True, ("B4/ii@B-A",)), values=RULES)
SEQUENCE = [
    Step(ITERATION, 1, "A", outcome=Outcome(True), values=RULES),
    Step(ROUND, 1, after_iteration=1, values=RULES, round_result=RoundResult(False, RULES)),
    STAGE_B,
    Step(ITERATION, 3, "C", values=RULES),
]


@pytest.fixture
def root(tmp_path):
    block(tmp_path, "calibration/iteration_002", B_ROWS)
    return tmp_path


def path_of(root, number):
    path = root / "decisions" / f"{number:03d}.yaml"
    path.parent.mkdir(exist_ok=True)
    path.write_text(f"decision {number}", encoding="utf-8")
    return path


def test_moving_on_with_missed_b_criteria_needs_the_decision(root) -> None:
    with pytest.raises(P1RefusalError, match="needs a b_criteria decision"):
        check_author_decisions(SEQUENCE, ITERATION, 3, (), root)
    judged = judges(root / "calibration" / "iteration_002", root)
    decision = b_decision(1, StepRef("iteration", 3), judged)
    used = check_author_decisions(SEQUENCE, ITERATION, 3, [(path_of(root, 1), decision)], root)
    assert [entry["decision"] for entry in used] == [1]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d, j: b_decision(1, d.step, j, choice="repeat_stage"), "choice"),
        (
            lambda d, j: b_decision(1, d.step, j, items=(item("B1", "", "B", "pass"),)),
            "must decide exactly on",
        ),
        (
            lambda d, j: b_decision(1, d.step, j, items=(item("B4", "ii", "B-A", "pass"),)),
            "results of",
        ),
        (
            lambda d, j: b_decision(
                1, d.step, JudgedBlock(j.directory, "0" * 64, j.criteria_sha256)
            ),
            "SHA-256",
        ),
        (lambda d, j: b_decision(1, StepRef("iteration", 4), j), "has not reached"),
    ],
)
def test_a_decision_must_match_what_it_judges(root, change, message) -> None:
    judged = judges(root / "calibration" / "iteration_002", root)
    decision = change(b_decision(1, StepRef("iteration", 3), judged), judged)
    with pytest.raises(P1RefusalError, match=message):
        check_author_decisions(SEQUENCE, ITERATION, 3, [(path_of(root, 1), decision)], root)


def test_a_decision_cannot_be_reused_nor_left_without_use(root) -> None:
    judged = judges(root / "calibration" / "iteration_002", root)
    first = (path_of(root, 1), b_decision(1, StepRef("iteration", 3), judged))
    second = (path_of(root, 2), b_decision(2, StepRef("iteration", 3), judged))
    with pytest.raises(P1RefusalError, match="two b_criteria decisions"):
        check_author_decisions(SEQUENCE, ITERATION, 3, [first, second], root)
    useless = (path_of(root, 1), b_decision(1, StepRef("iteration", 2), judged))
    with pytest.raises(P1RefusalError, match="authorizes nothing"):
        check_author_decisions(SEQUENCE, ITERATION, 3, [useless], root)


def test_a_decision_published_or_modified_after_its_step_stops(root) -> None:
    judged = judges(root / "calibration" / "iteration_002", root)
    path = path_of(root, 1)
    decision = (path, b_decision(1, StepRef("iteration", 3), judged))
    complete = [*SEQUENCE[:3], Step(ITERATION, 3, "C", outcome=Outcome(False), values=RULES)]
    following = [*complete, Step(ITERATION, 4, "C", "n_predators_c", values=RULES)]
    recorded = {"decisions": [{"decision": 1, "sha256": file_sha256(path)}]}
    block(root, "calibration/iteration_003", [], gate=recorded)
    check_author_decisions(following, ITERATION, 4, [decision], root)  # recorded when it ran

    path.write_text("decision 1, edited afterwards", encoding="utf-8")
    with pytest.raises(P1RefusalError, match=r"STOP .*published or modified after"):
        check_author_decisions(following, ITERATION, 4, [decision], root)


def test_the_entry_review_covers_every_b_and_c_row(tmp_path) -> None:
    entry = block(tmp_path, "calibration/entry", ENTRY_ROWS)
    steps = [*SEQUENCE[:2], Step(ITERATION, 2, "B", outcome=Outcome(True), values=RULES)]
    steps += [Step(ITERATION, 3, "C", outcome=Outcome(True)), Step(ENTRY, 0, outcome=Outcome(True))]
    with pytest.raises(P1RefusalError, match="needs a entry_review decision"):
        check_author_decisions(steps, "confirmation", 0, (), tmp_path)

    def review(items):
        return EntryReviewDecision(
            "neuroeco.p1-decision/1",
            1,
            "entry_review",
            StepRef("confirmation", 0),
            judges(entry, tmp_path),
            items,
            "reviewed",
        )

    only_missed = review((item("B4", "ii", "B-A", "fail"),))
    path = path_of(tmp_path, 1)
    with pytest.raises(P1RefusalError, match="must decide exactly on"):
        check_author_decisions(steps, "confirmation", 0, [(path, only_missed)], tmp_path)
    every = review(
        (
            item("B1", "", "A", "pass"),
            item("B4", "ii", "B-A", "fail"),
            item("C2", "", "A", "no_alert"),
        )
    )
    used = check_author_decisions(steps, "confirmation", 0, [(path, every)], tmp_path)
    assert used == [{"decision": 1, "sha256": file_sha256(path)}]
