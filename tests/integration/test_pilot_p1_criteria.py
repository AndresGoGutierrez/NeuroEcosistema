"""F4 T4-I3: ``neuroeco pilot p1-criteria`` (D1).

The evaluated blocks are produced by ``neuroeco pilot p1`` with the synthetic configuration
(seed groups >= 1000, t_max = 40, D16). The git facts of the criteria command are simulated,
except in the last test, which uses a temporary repository with a local bare remote.
"""

import csv
import json
import shutil

import pytest
from typer.testing import CliRunner

from neuroeco.analysis import calibration as crit
from neuroeco.presentation import pilot_p1_criteria
from neuroeco.presentation.cli import app
from p1_support import (
    commit_all,
    git,
    isolate_git,
    make_configs,
    register,
    run_ok,
    simulate_git,
)

PASSING = {
    "root": "simulated",
    "result_inside": True,
    "result_directory": "results/pilots/p1/calibration/iteration_001",
    "untracked_elsewhere": [],
    "hidden_changes": [],
    "content_overrides": [],
    "head_mismatches": [],
    "package_inside": True,
    "ignored_outputs": [],
    "head": "simulated",
    "upstream": "origin/main",
    "upstream_full_ref": "refs/remotes/origin/main",
    "remote_url": "https://example.invalid/simulated.git",
    "upstream_commit": "simulated",
    "synchronized": True,
}


def publish_iteration(base, monkeypatch):
    """A stage-A block published by ``pilot p1`` (synthetic, simulated git)."""
    output = base / "out"
    configs = make_configs(base)
    simulate_git(monkeypatch, output)
    run_ok(configs, output, "--iteration", str(register(configs, 1, "A")))
    return output / "calibration" / "iteration_001"


@pytest.fixture
def block(tmp_path, monkeypatch):
    directory = publish_iteration(tmp_path, monkeypatch)
    checks = dict(PASSING)
    monkeypatch.setattr(pilot_p1_criteria, "repository_checks", lambda cwd, result: checks)
    return directory, checks


def criteria(directory):
    return CliRunner().invoke(app, ["pilot", "p1-criteria", "--result", str(directory)])


def test_writes_the_criteria_and_their_provenance(block) -> None:
    directory, _ = block
    result = criteria(directory)
    assert result.exit_code == 0, result.output
    with (directory / "criteria.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    expected = crit.evaluate_block(crit.load_block(directory))
    assert [(r["criterion"], r["part"], r["scenario"]) for r in rows] == [r.key for r in expected]
    record = json.loads((directory / "criteria_provenance.json").read_text(encoding="utf-8"))
    assert record["schema"] == "neuroeco.p1-criteria-provenance/1"
    assert record["criteria_rows"] == len(rows)
    assert record["stage_requirements"]["stage"] == "A"
    assert set(record["input_files"]) == {"provenance.json", "episodes.csv", "bootstrap_keys.csv"}
    assert record["criteria_sha256"] == crit._sha256(directory / "criteria.csv")


def test_criteria_are_deterministic_and_never_overwritten(block, tmp_path) -> None:
    directory, _ = block
    copy = tmp_path / "copy"
    shutil.copytree(directory, copy)
    assert criteria(directory).exit_code == 0 and criteria(copy).exit_code == 0
    first = (directory / "criteria.csv").read_bytes()
    assert first == (copy / "criteria.csv").read_bytes()  # two independent evaluations

    record = (directory / "criteria_provenance.json").read_bytes()
    again = criteria(directory)  # identical output: accepted, nothing rewritten
    assert again.exit_code == 0 and "identical" in again.output
    assert (directory / "criteria_provenance.json").read_bytes() == record

    (directory / "criteria.csv").write_bytes(first.replace(b"pass", b"fail", 1))
    conflict = criteria(directory)
    assert conflict.exit_code == 1 and "nothing is overwritten" in conflict.output
    (copy / "criteria_provenance.json").unlink()  # an incomplete earlier evaluation
    assert criteria(copy).exit_code == 1
    assert not (copy / "criteria_provenance.json").exists()


@pytest.mark.parametrize(
    ("damage", "message"),
    [
        (lambda d, c: (d / "episodes.csv").write_bytes(b"x"), "SHA-256"),
        (
            lambda d, c: (d / "provenance.json").write_text(
                json.dumps(
                    {
                        **json.loads((d / "provenance.json").read_text(encoding="utf-8")),
                        "a2_violation": True,
                    }
                ),
                encoding="utf-8",
            ),
            "A2 violation",
        ),
        (lambda d, c: c.update(synchronized=False), "not synchronized"),
        (lambda d, c: c.update(untracked_elsewhere=["notes.txt"]), "untracked files outside"),
        (lambda d, c: c.update(head_mismatches=["src/x.py"]), "differs from HEAD"),
    ],
)
def test_refusals_write_nothing(block, damage, message) -> None:
    directory, checks = block
    damage(directory, checks)
    result = criteria(directory)
    assert result.exit_code == 1 and message in result.output
    assert not (directory / "criteria.csv").exists()
    assert not (directory / "criteria_provenance.json").exists()


def test_untracked_files_are_allowed_only_in_the_evaluated_block(tmp_path, monkeypatch) -> None:
    """Real git: results and criteria can enter one commit; any other untracked file refuses."""
    produced = publish_iteration(tmp_path / "produce", monkeypatch)
    base = tmp_path / "repo"
    base.mkdir()
    isolate_git(monkeypatch, base)
    remote, work = base / "remote.git", base / "work"
    git(base, "init", "-q", "--bare", "-b", "main", str(remote))
    work.mkdir()
    git(work, "init", "-q", "-b", "main")
    code = work / "src" / "neuroeco" / "module.py"  # stands for the package code
    code.parent.mkdir(parents=True)
    code.write_text("VALUE = 1\n", encoding="utf-8")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "code")
    git(work, "remote", "add", "origin", str(remote))
    git(work, "push", "-q", "-u", "origin", "main")
    monkeypatch.setattr(pilot_p1_criteria, "package_directory", lambda: code.parent)
    monkeypatch.chdir(work)
    result_dir = work / "results" / "pilots" / "p1" / "calibration" / "iteration_001"
    shutil.copytree(produced, result_dir)  # published, not yet committed

    (work / "notes.txt").write_text("draft\n", encoding="utf-8")
    refused = criteria(result_dir.relative_to(work))
    assert refused.exit_code == 1 and "notes.txt" in refused.output
    (work / "notes.txt").unlink()

    accepted = criteria(result_dir.relative_to(work))
    assert accepted.exit_code == 0, accepted.output
    record = json.loads((result_dir / "criteria_provenance.json").read_text(encoding="utf-8"))
    assert record["git"]["head"] == git(work, "rev-parse", "HEAD")
    assert record["result_directory"] == "results/pilots/p1/calibration/iteration_001"
    commit_all(work, "results and criteria of iteration 1")  # one commit, as P1-19 says
