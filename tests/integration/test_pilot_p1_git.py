"""F4 T3b: the git checks of ``neuroeco pilot p1`` with real repositories (P1-19; I-1, M-1).

Each test builds a temporary repository with a synthetic configuration (seed_group >= 1000) and a
local bare remote, and runs the command inside it with no simulation at all: clean tree, tracked
inputs, output root inside the repository and HEAD synchronized with its upstream. The user's
git settings are isolated and the project repository is never touched.
"""

import shutil

import pytest
from typer.testing import CliRunner

from neuroeco.infrastructure.provenance import (
    git_state,
    git_toplevel,
    git_untracked,
    git_upstream,
    is_inside,
)
from neuroeco.presentation.cli import app
from p1_support import (
    commit_all,
    git,
    isolate_git,
    last_failure,
    make_configs,
    read_json,
    register,
)

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not available")

OUTPUT = "results/pilots/p1"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A pushed repository with the synthetic configuration and iteration 1; cwd inside it."""
    isolate_git(monkeypatch, tmp_path)
    remote, work = tmp_path / "remote.git", tmp_path / "work"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    work.mkdir()
    git(work, "init", "-q", "-b", "main")
    configs = make_configs(work)
    register(configs, 1, "A")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "synthetic specification")
    git(work, "remote", "add", "origin", str(remote))
    git(work, "push", "-q", "-u", "origin", "main")
    monkeypatch.chdir(work)
    return work


def run(*arguments: str, spec="configs/pilots/p1.yaml", config_dir="configs", output=OUTPUT):
    """The command with paths relative to the repository (the working directory)."""
    options = ["--spec", spec, "--config-dir", config_dir, "--output-root", output]
    return CliRunner().invoke(app, ["pilot", "p1", *arguments, *options])


def iteration(number: int) -> str:
    return f"configs/pilots/p1/iterations/{number:03d}.yaml"


def failure_of(work, leaf: str) -> dict:
    return last_failure(work / OUTPUT / "calibration", leaf)


def test_a_clean_pushed_repository_runs_and_records_the_checks(repo) -> None:
    result = run("--iteration", iteration(1))
    assert result.exit_code == 0, result.output
    provenance = read_json(repo / OUTPUT / "calibration" / "iteration_001" / "provenance.json")
    checks = provenance["git_checks"]
    assert checks["synchronized"] is True and checks["upstream"] == "origin/main"
    assert checks["untracked"] == [] and checks["outside_repository"] == []
    assert checks["output_root_inside"] is True and provenance["git_dirty"] is False
    assert checks["head"] == provenance["git_commit"] == git(repo, "rev-parse", "HEAD")


def test_results_must_be_committed_and_pushed_before_the_next_iteration(repo) -> None:
    assert run("--iteration", iteration(1)).exit_code == 0
    register(repo / "configs", 2, "A", "plant_energy", plant_energy=35.0)
    git(repo, "add", iteration(2))
    git(repo, "commit", "-q", "-m", "iteration 2 specification")
    git(repo, "push", "-q")
    assert run("--iteration", iteration(2)).exit_code == 1  # iteration 1 results not versioned
    assert "working tree must be clean" in failure_of(repo, "iteration_002")["message"]

    commit_all(repo, "iteration 1 results and the refused attempt")
    result = run("--iteration", iteration(2))
    assert result.exit_code == 0, result.output
    provenance = read_json(repo / OUTPUT / "calibration" / "iteration_002" / "provenance.json")
    assert [a["kind"] for a in provenance["previous_attempts"]] == ["failure"]


def test_an_unpushed_specification_is_refused(repo) -> None:
    assert run("--iteration", iteration(1)).exit_code == 0
    commit_all(repo, "iteration 1 results")
    register(repo / "configs", 2, "A", "plant_energy", plant_energy=35.0)
    commit_all(repo, "iteration 2 specification", push=False)
    assert run("--iteration", iteration(2)).exit_code == 1
    failure = failure_of(repo, "iteration_002")
    assert "is not synchronized with origin/main" in failure["message"]
    assert failure["git"]["upstream"] == "origin/main"
    assert failure["git"]["commit"] != failure["git"]["upstream_commit"]


def test_a_branch_without_upstream_is_refused(repo) -> None:
    git(repo, "branch", "--unset-upstream")
    assert run("--iteration", iteration(1)).exit_code == 1
    assert "no upstream branch" in failure_of(repo, "iteration_001")["message"]


def test_an_ignored_and_untracked_specification_is_refused(repo) -> None:
    """A clean tree is not enough: an ignored file is invisible to ``git status``."""
    git(repo, "rm", "-q", "--cached", iteration(1))
    (repo / ".gitignore").write_text(iteration(1) + "\n", encoding="utf-8")
    commit_all(repo, "stop tracking the specification")
    assert git(repo, "status", "--porcelain") == ""
    assert run("--iteration", iteration(1)).exit_code == 1
    failure = failure_of(repo, "iteration_001")
    assert "not tracked by git" in failure["message"] and "001.yaml" in failure["message"]


@pytest.mark.parametrize("external", ["spec", "config_dir"])
def test_external_specifications_and_configurations_are_refused(repo, tmp_path, external):
    outside = tmp_path / "outside"
    shutil.copytree(repo / "configs", outside / "configs")
    if external == "spec":
        result = run(
            "--iteration",
            str(outside / iteration(1)),
            spec=str(outside / "configs" / "pilots" / "p1.yaml"),
        )
    else:
        result = run("--iteration", iteration(1), config_dir=str(outside / "configs"))
    assert result.exit_code == 1
    failure = failure_of(repo, "iteration_001")
    assert "files outside the repository" in failure["message"]
    assert not (repo / OUTPUT / "calibration" / "iteration_001").exists()


def test_an_external_output_root_is_refused(repo, tmp_path) -> None:
    output = tmp_path / "elsewhere"
    assert run("--iteration", iteration(1), output=str(output)).exit_code == 1
    failure = last_failure(output / "calibration", "iteration_001")
    assert "output root must be inside the repository" in failure["message"]


def test_a_modified_tracked_file_is_refused(repo) -> None:
    base = repo / "configs" / "base.yaml"
    base.write_text(base.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert run("--iteration", iteration(1)).exit_code == 1
    assert "working tree must be clean" in failure_of(repo, "iteration_001")["message"]


# ---------------------------------------------------------------- infrastructure functions


def test_git_functions_on_a_real_repository(repo, tmp_path) -> None:
    assert git_toplevel(repo) == repo.resolve()
    tracked = repo / iteration(1)
    odd = repo / "configs" / "pilots" / "[odd].yaml"  # literal path, not a pattern
    odd.write_text("x: 1\n", encoding="utf-8")
    assert git_untracked([tracked, odd], repo) == [odd]
    git(repo, "add", str(odd.relative_to(repo)))
    assert git_untracked([tracked, odd], repo) == []
    assert is_inside(tracked, repo) and not is_inside(tmp_path / "remote.git", repo)
    upstream = git_upstream(repo)
    assert upstream["ref"] == "origin/main"
    state = git_state(repo)
    assert state["dirty"] is True and state["upstream_commit"] == upstream["commit"]


def test_git_functions_outside_a_repository(tmp_path, monkeypatch) -> None:
    isolate_git(monkeypatch, tmp_path)
    alone = tmp_path / "alone"
    alone.mkdir()
    assert git_toplevel(alone) is None
    assert git_upstream(alone) == {"ref": None, "commit": None}
    assert git_state(alone) == {
        "commit": None,
        "dirty": None,
        "upstream": None,
        "upstream_commit": None,
    }
