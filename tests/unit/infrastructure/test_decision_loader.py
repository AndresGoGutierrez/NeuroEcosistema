"""F4 T4d (D-T4d-3): the strict schema of the author decisions of P1."""

import pytest
import yaml

from neuroeco.application.decisions import B_CRITERIA, D9_E5, ENTRY_REVIEW, cites_decision
from neuroeco.infrastructure.config_loader import ConfigError
from neuroeco.infrastructure.decision_loader import load_decision, load_decisions

SHA = "a" * 64
ITEM = {
    "criterion": "B4",
    "part": "ii",
    "scenario": "B-A",
    "status": "fail",
    "decision": "move on",
    "justification": "no parametric cause",
}
VALID = {
    B_CRITERIA: {
        "schema": "neuroeco.p1-decision/1",
        "decision": 1,
        "kind": B_CRITERIA,
        "step": {"kind": "iteration", "number": 5},
        "judges": {
            "directory": "calibration/iteration_004",
            "provenance_sha256": SHA,
            "criteria_sha256": SHA,
        },
        "choice": "next_stage",
        "items": [ITEM],
        "justification": "documented decision",
    },
    ENTRY_REVIEW: {
        "schema": "neuroeco.p1-decision/1",
        "decision": 1,
        "kind": ENTRY_REVIEW,
        "step": {"kind": "confirmation", "number": 0},
        "judges": {
            "directory": "calibration/entry",
            "provenance_sha256": SHA,
            "criteria_sha256": SHA,
        },
        "items": [ITEM],
        "justification": "every B and C reviewed",
    },
    D9_E5: {
        "schema": "neuroeco.p1-decision/1",
        "decision": 1,
        "kind": D9_E5,
        "step": {"kind": "iteration", "number": 4},
        "plant_energy_needed": 90.0,
        "iteration_spec_sha256": SHA,
        "justification": "the plant_energy needed violates E5",
    },
}


def write(directory, content, name="001.yaml"):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(yaml.safe_dump(content), encoding="utf-8")
    return path


@pytest.mark.parametrize("kind", sorted(VALID))
def test_each_kind_loads(tmp_path, kind) -> None:
    decision = load_decision(write(tmp_path, VALID[kind]))
    assert decision.kind == kind and decision.decision == 1


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d.update(extra=1), "unknown keys"),
        (lambda d: d.pop("justification"), "missing keys"),
        (lambda d: d.update(schema="neuroeco.p1-decision/2"), "schema"),
        (lambda d: d.update(kind="other"), "kind must be one of"),
        (lambda d: d.update(justification="  "), "must not be empty"),
        (lambda d: d.update(choice="maybe"), "choice must be"),
        (lambda d: d.update(items=[]), "missed B criteria"),
        (lambda d: d["judges"].update(criteria_sha256="ABC"), "SHA-256"),
        (lambda d: d.update(step={"kind": "round", "number": 1}), "authorizes a step of kind"),
        (lambda d: d.update(decision=2), "must be in a file NNN.yaml"),
        (lambda d: d["items"][0].update(decision=""), "items.decision"),
    ],
)
def test_invalid_decisions_are_refused(tmp_path, change, message) -> None:
    content = yaml.safe_load(yaml.safe_dump(VALID[B_CRITERIA]))  # a deep copy
    change(content)
    with pytest.raises(ConfigError, match=message):
        load_decision(write(tmp_path, content))


def test_a_d9_decision_needs_a_finite_positive_plant_energy(tmp_path) -> None:
    with pytest.raises(ConfigError, match="plant_energy_needed"):
        load_decision(write(tmp_path, {**VALID[D9_E5], "plant_energy_needed": -1.0}))


def test_the_directory_is_strict(tmp_path) -> None:
    spec = tmp_path / "p1.yaml"
    decisions = tmp_path / "p1_decisions"
    assert load_decisions(spec) == ()
    write(decisions, VALID[D9_E5])
    assert [d.decision for _, d in load_decisions(spec)] == [1]
    write(decisions, {**VALID[D9_E5], "decision": 3}, "003.yaml")
    with pytest.raises(ConfigError, match="without gaps"):
        load_decisions(spec)
    (decisions / "003.yaml").unlink()
    (decisions / "notes.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ConfigError, match="unexpected entries"):
        load_decisions(spec)


@pytest.mark.parametrize(
    ("motive", "cited"),
    [
        ("change n_plants_a through the E5 route (decision 3)", True),
        ("decisión 003 del autor", True),
        ("Decision 3.", True),
        ("decision 30", False),
        ("decision 13", False),
        ("no decision cited", False),
    ],
)
def test_the_motive_must_cite_the_decision(motive, cited) -> None:
    assert cites_decision(motive, 3) is cited
