"""F4 T4d (M-3, D-T4d-5): the whole P1 sequence through the gate of ``pilot p1``.

Seed groups 40-48 are neither real (10-32) nor synthetic (>= 1000): the gate applies exactly as
with the real table, while no real seed is used. Episodes (t_max = 40, 2 per condition),
``episodes.csv``, ``criteria.csv`` and every check run unchanged; the only test double is the
verdict S_X of each block (``requirements_met`` of the gate), so that the walk reaches every
stage without altering any row. The grids hold only the values in force, so the round changes
nothing (T_fin), and the author decisions the gate asks for are written from the real criteria.
"""

import copy
import csv

import pytest
import yaml
from typer.testing import CliRunner

from neuroeco.infrastructure.provenance import file_sha256
from neuroeco.presentation import pilot_p1_criteria, pilot_p1_sequence
from neuroeco.presentation.cli import app
from p1_support import (
    PASSING_GIT_CHECKS,
    SYNTHETIC_SPEC,
    VALUES,
    invoke,
    last_failure,
    make_configs,
    read_json,
    register,
    run_ok,
    simulate_git,
)

GROUPS = {
    "calibration": {"episodes": 2, "seed_groups": {"a": 40, "b": 41, "c": 42}},
    "confirmation": {"episodes": 2, "seed_groups": {"a": 43, "b": 44, "c": 45}},
    "second_confirmation": {"episodes": 2, "seed_groups": {"a": 46, "b": 47, "c": 48}},
}
CRITERIA_CHECKS = {
    **PASSING_GIT_CHECKS,
    "result_inside": True,
    "result_directory": "simulated",
    "untracked_elsewhere": [],
}


@pytest.fixture
def walk(tmp_path, monkeypatch):
    spec = copy.deepcopy(SYNTHETIC_SPEC)
    spec["blocks"] = GROUPS
    spec["grids"] = {"prey_flee_threshold": [0.3], "cruise_fraction": [0.5]}
    output = tmp_path / "out"
    configs = make_configs(tmp_path, spec)
    simulate_git(monkeypatch, output)
    monkeypatch.setattr(
        pilot_p1_criteria, "repository_checks", lambda cwd, result: dict(CRITERIA_CHECKS)
    )
    monkeypatch.setattr(pilot_p1_sequence, "requirements_met", lambda stage, results: True)
    return configs, output


def criteria(directory) -> list[dict[str, str]]:
    result = CliRunner().invoke(app, ["pilot", "p1-criteria", "--result", str(directory)])
    assert result.exit_code == 0, result.output
    with (directory / "criteria.csv").open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def item(row) -> dict:
    keys = ("criterion", "part", "scenario", "status")
    return {**{k: row[k] for k in keys}, "decision": "reviewed", "justification": "test"}


def decide(configs, output, number, kind, step, judged, rows, choice=None) -> None:
    content = {
        "schema": "neuroeco.p1-decision/1",
        "decision": number,
        "kind": kind,
        "step": step,
        "judges": {
            "directory": judged.relative_to(output).as_posix(),
            "provenance_sha256": file_sha256(judged / "provenance.json"),
            "criteria_sha256": file_sha256(judged / "criteria.csv"),
        },
        "items": [item(row) for row in rows],
        "justification": "decision of the author for the test",
    }
    if choice:
        content["choice"] = choice
    path = configs / "pilots" / "p1_decisions" / f"{number:03d}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(content), encoding="utf-8")


def missed_b(rows) -> list[dict[str, str]]:
    return [r for r in rows if r["class"] == "B" and r["status"] == "fail"]


def test_the_gate_leads_the_whole_calibration_to_the_confirmation(walk) -> None:
    configs, output = walk
    calibration = output / "calibration"
    decisions = 0

    def next_stage(previous, step, run):
        """Run a step after ``previous``; a decision first if B criteria were missed."""
        nonlocal decisions
        missed = missed_b(previous_rows[previous])
        if missed:
            assert run().exit_code == 1  # the gate asks for the decision of the author
            assert "needs a b_criteria decision" in last_failure(*failed_at(step))["message"]
            decisions += 1
            decide(
                configs,
                output,
                decisions,
                "b_criteria",
                step,
                calibration / previous,
                missed,
                "next_stage",
            )
        result = run()
        assert result.exit_code == 0, result.output

    def failed_at(step):
        leaf = "entry" if step["kind"] == "entry" else f"iteration_{step['number']:03d}"
        return calibration, leaf

    previous_rows = {}
    run_ok(configs, output, "--iteration", str(register(configs, 1, "A")))
    previous_rows["iteration_001"] = criteria(calibration / "iteration_001")

    # S_A met with r = 0: stage B is refused, the round runs and changes nothing (T_fin).
    stage_b = register(configs, 2, "B")
    assert invoke(configs, output, "--iteration", str(stage_b)).exit_code == 1
    assert "must be a round" in last_failure(calibration, "iteration_002")["message"]
    path = configs / "pilots" / "p1" / "rounds" / "01.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {
                "round_number": 1,
                "after_iteration": 1,
                "values": VALUES,
                "motive": "synthetic round",
                "exploratory_observations": "",
            }
        ),
        encoding="utf-8",
    )
    for phase in ("prey", "predator"):
        run_ok(configs, output, "--round", str(path), "--phase", phase)
    assert invoke(configs, output, "--round", str(path), "--phase", "reevaluation").exit_code == 1

    run_ok(configs, output, "--iteration", str(stage_b))
    previous_rows["iteration_002"] = criteria(calibration / "iteration_002")
    stage_c = register(configs, 3, "C")
    next_stage(
        "iteration_002",
        {"kind": "iteration", "number": 3},
        lambda: invoke(configs, output, "--iteration", str(stage_c)),
    )
    previous_rows["iteration_003"] = criteria(calibration / "iteration_003")
    next_stage(
        "iteration_003",
        {"kind": "entry", "number": 0},
        lambda: invoke(configs, output, "--entry-evaluation", "--values-from", str(stage_c)),
    )
    entry_rows = criteria(calibration / "entry")

    # The confirmation: the entry review of the author on every B and C row, and the express
    # authorization; the second confirmation is never reached (Mn-7).
    confirm = ("--confirmation", "--values-from", str(stage_c), "--author-authorized")
    assert invoke(configs, output, *confirm).exit_code == 1
    failure = last_failure(output / "confirmation", "evaluation")
    assert "needs a entry_review decision" in failure["message"]
    decisions += 1
    reviewed = [r for r in entry_rows if r["class"] in ("B", "C")]
    decide(
        configs,
        output,
        decisions,
        "entry_review",
        {"kind": "confirmation", "number": 0},
        calibration / "entry",
        reviewed,
    )
    result = invoke(configs, output, *confirm)
    assert result.exit_code == 0, result.output
    gate = read_json(output / "confirmation" / "evaluation" / "provenance.json")["sequence_gate"]
    assert gate["verdict"] == "author_authorization_required"
    assert [d["decision"] for d in gate["decisions"]] == [decisions]
    # Premise of this deterministic configuration: B criteria are missed after stages B and C,
    # so both b_criteria decisions and the entry review were exercised.
    assert decisions == 3
    second = ("--second-confirmation", "--values-from", str(stage_c), "--author-authorized")
    assert invoke(configs, output, *second).exit_code == 1
