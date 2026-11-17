"""F4 T4d (D-T4d-1, D-T4d-2): failures and fingerprints that STOP P1.

Synthetic configuration (seed groups >= 1000, t_max = 40, D16) with simulated git facts. The
exemption of synthetic specifications is removed in each test, as T3-5 replaces the git facts:
the gate then behaves as with the real seed groups. No real P1 episode is run.
"""

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from neuroeco.application import calibration
from neuroeco.application.calibration import InvariantViolationError
from neuroeco.infrastructure.provenance import file_sha256
from neuroeco.presentation import pilot_p1, pilot_p1_criteria
from neuroeco.presentation.cli import app
from p1_support import (
    PASSING_GIT_CHECKS,
    invoke,
    last_failure,
    make_configs,
    read_json,
    register,
    run_ok,
    simulate_git,
)

CRITERIA_CHECKS = {
    **PASSING_GIT_CHECKS,
    "result_inside": True,
    "result_directory": "simulated",
    "untracked_elsewhere": [],
}


@pytest.fixture
def gated(tmp_path, monkeypatch):
    output = tmp_path / "out"
    configs = make_configs(tmp_path)
    state = simulate_git(monkeypatch, output)
    monkeypatch.setattr(pilot_p1, "sequence_gate_required", lambda spec: True)
    return configs, output, state


def inject_a2(monkeypatch) -> None:
    original = calibration.InvariantChecker.__call__

    def failing(self, trace) -> None:
        original(self, trace)
        if trace.step == 1:
            raise InvariantViolationError("prey_identity", 1, "injected for the test")

    monkeypatch.setattr(calibration.InvariantChecker, "__call__", failing)


def stopped(output, leaf: str, cause: str) -> dict:
    failure = last_failure(output / "calibration", leaf)
    assert failure["phase"] == "preflight" and failure["error_type"].endswith("P1RefusalError")
    assert "STOP (P1-18)" in failure["message"] and cause in failure["message"]
    assert not (output / "calibration" / leaf).exists()
    return failure


def sequence(configs, output):
    arguments = ["pilot", "p1-sequence", "--spec", str(configs / "pilots" / "p1.yaml")]
    return CliRunner().invoke(app, [*arguments, "--output-root", str(output)])


def test_an_a2_violation_stops_every_later_step(gated, monkeypatch) -> None:
    configs, output, _ = gated
    first = register(configs, 1, "A")
    with monkeypatch.context() as patch:
        inject_a2(patch)
        assert invoke(configs, output, "--iteration", str(first)).exit_code == 2

    # Neither the same iteration nor any other step runs again.
    assert invoke(configs, output, "--iteration", str(first)).exit_code == 1
    stopped(output, "iteration_001", "an A2 violation")
    result = sequence(configs, output)
    assert result.exit_code == 1 and "next: -: stop" in result.output


def test_an_initialization_error_stops(gated) -> None:
    configs, output, _ = gated
    base = configs / "base.yaml"
    data = yaml.safe_load(base.read_text(encoding="utf-8"))
    data["world"]["n_prey"] = 400  # no room for d_safe: the placement fails
    base.write_text(yaml.safe_dump(data), encoding="utf-8")
    first = register(configs, 1, "A")
    assert invoke(configs, output, "--iteration", str(first)).exit_code == 1
    assert invoke(configs, output, "--iteration", str(first)).exit_code == 1
    stopped(output, "iteration_001", "an InitializationError")


@pytest.mark.parametrize("kind", ["unrecognized", "partial"])
def test_attempts_without_a_usable_record_stop(gated, kind) -> None:
    configs, output, _ = gated
    leaf = "failed-20261117T000000Z-0000" if kind == "unrecognized" else "partial-0000"
    directory = output / "calibration" / "round_01" / f"prey_grid.{leaf}"  # any destination
    directory.mkdir(parents=True)
    (directory / "failure.json").write_text("not json", encoding="utf-8")
    assert invoke(configs, output, "--iteration", str(register(configs, 1, "A"))).exit_code == 1
    message = "A2 cannot be ruled out" if kind == "unrecognized" else "a partial directory"
    stopped(output, "iteration_001", message)


def test_an_infrastructure_failure_can_be_repeated(gated) -> None:
    configs, output, state = gated
    first = register(configs, 1, "A")
    state["git_dirty"] = True
    assert invoke(configs, output, "--iteration", str(first)).exit_code == 1
    state["git_dirty"] = False
    run_ok(configs, output, "--iteration", str(first))


def test_synthetic_specifications_keep_the_t3_behaviour(tmp_path, monkeypatch) -> None:
    """Without the gate (D16 tests), an A2 failure of an iteration does not stop it (T3)."""
    output = tmp_path / "out"
    configs = make_configs(tmp_path)
    simulate_git(monkeypatch, output)
    first = register(configs, 1, "A")
    with monkeypatch.context() as patch:
        inject_a2(patch)
        assert invoke(configs, output, "--iteration", str(first)).exit_code == 2
    run_ok(configs, output, "--iteration", str(first))


@pytest.mark.parametrize(
    ("part", "name"), [("environment", "python"), ("code", "simulation"), ("code", "analysis")]
)
def test_a_different_code_or_environment_stops(gated, monkeypatch, part, name) -> None:
    configs, output, _ = gated
    run_ok(configs, output, "--iteration", str(register(configs, 1, "A")))
    monkeypatch.setattr(
        pilot_p1_criteria, "repository_checks", lambda cwd, result: dict(CRITERIA_CHECKS)
    )
    criteria = ["pilot", "p1-criteria", "--result", str(output / "calibration" / "iteration_001")]
    assert CliRunner().invoke(app, criteria).exit_code == 0
    second = register(configs, 2, "A", "plant_energy", plant_energy=35.0)

    real = pilot_p1.p1_fingerprint

    def changed(uv_lock):
        current = real(uv_lock)
        current[part] = {**current[part], name: "changed"}
        return current

    monkeypatch.setattr(pilot_p1, "p1_fingerprint", changed)
    assert invoke(configs, output, "--iteration", str(second)).exit_code == 1
    failure = stopped(output, "iteration_002", "D-T4d-2")
    assert f"{part}.{name}" in failure["message"]


# ---------------------------------------------------------------- author decisions (D-T4d-3)


def write_decision(configs, content: dict) -> Path:
    path = configs / "pilots" / "p1_decisions" / f"{content['decision']:03d}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(content), encoding="utf-8")
    return path


def test_the_e5_route_of_d9_needs_a_bound_decision_of_the_author(gated, monkeypatch) -> None:
    """n_plants without the premise of D9: refused until a valid d9_e5 decision exists, and a
    decision modified after its step ran stops the calibration."""
    configs, output, _ = gated
    run_ok(configs, output, "--iteration", str(register(configs, 1, "A")))
    monkeypatch.setattr(
        pilot_p1_criteria, "repository_checks", lambda cwd, result: dict(CRITERIA_CHECKS)
    )
    criteria = ["pilot", "p1-criteria", "--result", str(output / "calibration" / "iteration_001")]
    assert CliRunner().invoke(app, criteria).exit_code == 0
    second = register(configs, 2, "A", "n_plants_a", n_plants_a=45)
    assert invoke(configs, output, "--iteration", str(second)).exit_code == 1
    assert (
        "needs a d9_e5 decision" in last_failure(output / "calibration", "iteration_002")["message"]
    )

    second.write_text(
        second.read_text(encoding="utf-8").replace(
            "synthetic test iteration", "E5 route of D9, decision 1"
        ),
        encoding="utf-8",
    )
    decision = {
        "schema": "neuroeco.p1-decision/1",
        "decision": 1,
        "kind": "d9_e5",
        "step": {"kind": "iteration", "number": 2},
        "plant_energy_needed": 1000.0,
        "iteration_spec_sha256": file_sha256(second),
        "justification": "the plant_energy needed would violate E5",
    }
    path = write_decision(configs, decision)
    run_ok(configs, output, "--iteration", str(second))
    gate = read_json(output / "calibration" / "iteration_002" / "provenance.json")["sequence_gate"]
    assert gate["d9_confirmed"] == [2]
    assert gate["decisions"] == [{"decision": 1, "sha256": file_sha256(path)}]

    criteria[-1] = str(output / "calibration" / "iteration_002")
    assert CliRunner().invoke(app, criteria).exit_code == 0
    write_decision(configs, {**decision, "justification": "edited after the step ran"})
    third = register(configs, 3, "A", "plant_energy", plant_energy=35.0, n_plants_a=45)
    assert invoke(configs, output, "--iteration", str(third)).exit_code == 1
    stopped(output, "iteration_003", "published or modified after")
