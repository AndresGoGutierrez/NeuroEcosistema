"""F4 T4b: ``neuroeco pilot p1-sequence`` on blocks published by ``pilot p1`` (synthetic).

Seed groups >= 1000, t_max = 40 and simulated git facts (D16); no real P1 episode is run.
"""

import pytest
from typer.testing import CliRunner

from neuroeco.presentation import pilot_p1_criteria
from neuroeco.presentation.cli import app
from p1_support import PASSING_GIT_CHECKS, make_configs, register, run_ok, simulate_git

CRITERIA_CHECKS = {
    **PASSING_GIT_CHECKS,
    "result_inside": True,
    "result_directory": "simulated",
    "untracked_elsewhere": [],
}


@pytest.fixture
def chain(tmp_path, monkeypatch):
    """Iterations 1 (A) and 2 (B, statically valid) published, criteria of iteration 1."""
    output = tmp_path / "out"
    configs = make_configs(tmp_path)
    simulate_git(monkeypatch, output)
    monkeypatch.setattr(
        pilot_p1_criteria, "repository_checks", lambda cwd, result: dict(CRITERIA_CHECKS)
    )
    for number, stage in ((1, "A"), (2, "B")):
        run_ok(configs, output, "--iteration", str(register(configs, number, stage)))
    criteria(output / "calibration" / "iteration_001")
    return configs, output


def criteria(directory) -> None:
    result = CliRunner().invoke(app, ["pilot", "p1-criteria", "--result", str(directory)])
    assert result.exit_code == 0, result.output


def sequence(configs, output):
    return CliRunner().invoke(
        app,
        [
            "pilot",
            "p1-sequence",
            "--spec",
            str(configs / "pilots" / "p1.yaml"),
            "--output-root",
            str(output),
        ],
    )


def test_stage_b_right_after_stage_a_is_rejected(chain) -> None:
    """Whatever S_A gave, P1-18 never goes from A_eval to B_eval directly (r = 0)."""
    configs, output = chain
    criteria(output / "calibration" / "iteration_002")
    result = sequence(configs, output)
    assert result.exit_code == 1
    assert "iteration 1 (stage A) -> iteration 2 (stage B): rejected" in result.output


def test_the_next_step_after_a_published_iteration(chain) -> None:
    configs, output = chain
    (configs / "pilots" / "p1" / "iterations" / "002.yaml").unlink()  # only iteration 1 left
    result = sequence(configs, output)
    assert result.exit_code == 0, result.output
    assert "next: a round: allowed" in result.output or "next: a stage-A iteration" in (
        result.output
    )


@pytest.mark.parametrize(
    ("damage", "message"),
    [
        (lambda c, o: None, "run pilot p1-criteria first"),  # iteration 2 has no criteria
        (
            lambda c, o: (o / "calibration" / "iteration_001" / "criteria.csv").write_bytes(
                b"criterion\r\n"
            ),
            "does not match the criteria recomputed",
        ),
        (
            lambda c, o: (c / "pilots" / "p1" / "iterations" / "001.yaml").write_text(
                (c / "pilots" / "p1" / "iterations" / "001.yaml")
                .read_text(encoding="utf-8")
                .replace("synthetic test iteration", "edited after the run"),
                encoding="utf-8",
            ),
            "does not belong to the registered specification",
        ),
    ],
)
def test_results_that_cannot_be_trusted_are_refused(chain, damage, message) -> None:
    configs, output = chain
    damage(configs, output)
    result = sequence(configs, output)
    assert result.exit_code == 1 and message in result.output
