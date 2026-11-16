"""F4 T3b and T3c: the git checks of ``neuroeco pilot p1`` with real repositories (P1-19).

Each test builds a temporary repository with a synthetic configuration (seed_group >= 1000) and a
local bare remote, and runs the command inside it: clean tree, no hidden changes, every tracked
file equal to HEAD, tracked inputs, output root inside the repository and not ignored, and HEAD
synchronized with a remote-tracking upstream. The only simulated fact is where the ``neuroeco``
package lives (it is installed from the project, not from the temporary repository), and one
test checks that refusal with the real location. The user's git settings are isolated and the
project repository is never touched.
"""

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from neuroeco.infrastructure.provenance import (
    git_head_mismatches,
    git_hidden_changes,
    git_ignored,
    git_state,
    git_toplevel,
    git_untracked,
    git_upstream,
    is_inside,
)
from neuroeco.presentation import pilot_p1
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


def build_repo(base: Path, monkeypatch) -> Path:
    """A pushed repository under ``base`` with the synthetic configuration and iteration 1."""
    base.mkdir(parents=True, exist_ok=True)
    isolate_git(monkeypatch, base)
    remote, work = base / "remote.git", base / "work"
    git(base, "init", "-q", "--bare", "-b", "main", str(remote))
    work.mkdir()
    git(work, "init", "-q", "-b", "main")
    configs = make_configs(work)
    register(configs, 1, "A")
    code = work / "src" / "neuroeco" / "module.py"  # stands for the package code
    code.parent.mkdir(parents=True)
    code.write_text("VALUE = 1\n", encoding="utf-8")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "synthetic specification")
    git(work, "remote", "add", "origin", str(remote))
    git(work, "push", "-q", "-u", "origin", "main")
    monkeypatch.chdir(work)
    monkeypatch.setattr(pilot_p1, "package_directory", lambda: work / "src" / "neuroeco")
    return work


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A pushed repository with the synthetic configuration and iteration 1; cwd inside it."""
    return build_repo(tmp_path, monkeypatch)


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
    assert checks["hidden_changes"] == [] and checks["head_mismatches"] == []
    assert checks["ignored_outputs"] == [] and checks["package_inside"] is True
    assert checks["upstream_full_ref"] == "refs/remotes/origin/main"
    assert checks["remote_url"] == git(repo, "remote", "get-url", "origin")
    names = {Path(entry["path"]).name for entry in provenance["input_files"]}
    assert {"p1.yaml", "p0.yaml", "base.yaml", "scenarios.yaml", "baselines.yaml"} <= names
    assert set(provenance["config_files"]) == {
        "p1_spec",
        "p0_spec",
        "base",
        "scenarios",
        "baselines",
    }


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
    assert git_upstream(alone) == {
        "ref": None,
        "full_ref": None,
        "commit": None,
        "remote": None,
        "remote_url": None,
    }
    assert git_state(alone) == {
        "commit": None,
        "dirty": None,
        "upstream": None,
        "upstream_commit": None,
        "remote_url": None,
    }
    assert git_hidden_changes(alone) is None and git_head_mismatches(alone) is None


# ---------------------------------------------------------------- T3c: IA-1 hidden changes


def modify(path: Path) -> None:
    path.write_text(path.read_text(encoding="utf-8") + "# changed locally\n", encoding="utf-8")


@pytest.mark.parametrize("flag", ["--skip-worktree", "--assume-unchanged"])
@pytest.mark.parametrize("target", ["configs/base.yaml", "src/neuroeco/module.py"])
def test_hidden_local_changes_are_refused(repo, flag, target) -> None:
    """Q1: the change is invisible to ``git status`` but not to the command."""
    modify(repo / target)
    git(repo, "update-index", flag, target)
    assert git(repo, "status", "--porcelain") == ""
    assert run("--iteration", iteration(1)).exit_code == 1
    failure = failure_of(repo, "iteration_001")
    assert (
        "assume-unchanged or skip-worktree" in failure["message"] and target in failure["message"]
    )
    assert not (repo / OUTPUT / "calibration" / "iteration_001").exists()


def test_head_comparison_finds_hidden_and_deleted_files(repo) -> None:
    """The second layer, independent of the flags: content compared with HEAD blob by blob."""
    assert git_head_mismatches(repo) == []
    modify(repo / "configs" / "base.yaml")
    git(repo, "update-index", "--assume-unchanged", "configs/base.yaml")
    (repo / "src" / "neuroeco" / "module.py").unlink()
    git(repo, "update-index", "--skip-worktree", "src/neuroeco/module.py")
    assert git_hidden_changes(repo) == ["configs/base.yaml", "src/neuroeco/module.py"]
    assert git_head_mismatches(repo) == ["configs/base.yaml", "src/neuroeco/module.py"]


def test_a_local_clean_filter_is_refused(repo) -> None:
    """A filter driver set only in .git (not versioned) could turn modified text into HEAD's."""
    (repo / ".git" / "info" / "attributes").write_text("*.yaml filter=hide\n", encoding="utf-8")
    git(repo, "config", "filter.hide.clean", "cat")
    assert git(repo, "status", "--porcelain") == ""
    assert run("--iteration", iteration(1)).exit_code == 1
    failure = failure_of(repo, "iteration_001")
    assert (
        "can disguise modified content" in failure["message"]
        and "filter.hide" in (failure["message"])
    )


def test_a_replaced_head_commit_is_refused(repo) -> None:
    """``git replace`` swaps the commit HEAD while ``git rev-parse HEAD`` prints the original."""
    head = git(repo, "rev-parse", "HEAD")
    modify(repo / "configs" / "base.yaml")
    git(repo, "add", "configs/base.yaml")
    fake = git(repo, "commit-tree", git(repo, "write-tree"), "-m", "fake")
    git(repo, "replace", head, fake)
    assert git(repo, "rev-parse", "HEAD") == head and git(repo, "status", "--porcelain") == ""
    assert git_head_mismatches(repo) == ["configs/base.yaml"]  # the real tree of HEAD
    assert run("--iteration", iteration(1)).exit_code == 1
    failure = failure_of(repo, "iteration_001")
    assert (
        "can disguise modified content" in failure["message"]
        and "refs/replace/" in (failure["message"])
    )


def crlf(path: Path) -> None:
    """Rewrite ``path`` with CRLF line endings, whatever its current endings are."""
    path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))


def eol_info(repo: Path, name: str) -> str:
    """The index and working-tree line endings that ``git ls-files --eol`` reports."""
    return git(repo, "ls-files", "--eol", "--", name).split("\t")[0]


def test_end_of_line_conversion_is_not_a_mismatch(repo) -> None:
    """``git hash-object`` applies the filters: a CRLF checkout of an LF blob is equal.

    The blobs are renormalized after adding the attribute, so the premise (LF in HEAD) holds
    whatever line endings the files had on disk: on Windows the project checkout, and with it
    the copied configuration, may use CRLF (``core.autocrlf=true``).
    """
    (repo / ".gitattributes").write_text("*.yaml text eol=crlf\n", encoding="utf-8")
    git(repo, "add", ".gitattributes")
    git(repo, "add", "--renormalize", ".")
    commit_all(repo, "attributes")
    base = repo / "configs" / "base.yaml"
    crlf(base)
    assert eol_info(repo, "configs/base.yaml").split()[0] == "i/lf"
    assert b"\r\n" in base.read_bytes()
    assert git_head_mismatches(repo) == []


def test_a_crlf_blob_under_a_text_attribute_is_a_mismatch(repo) -> None:
    """The stricter case: HEAD keeps CRLF but the attribute normalizes the file to LF.

    Adding the file again would store a different blob, so it is not the content of HEAD even
    when ``git status`` (which trusts the cached file times and sizes) reports nothing.
    """
    base = repo / "configs" / "base.yaml"
    crlf(base)
    git(repo, "add", "configs/base.yaml")
    git(repo, "commit", "-q", "--allow-empty", "-m", "crlf blob")  # empty if already CRLF
    (repo / ".gitattributes").write_text("*.yaml text eol=crlf\n", encoding="utf-8")
    git(repo, "add", ".gitattributes")  # only the attribute: base.yaml is not added again
    git(repo, "commit", "-q", "-m", "attributes")
    assert eol_info(repo, "configs/base.yaml").split()[0] == "i/crlf"
    assert "configs/base.yaml" in git_head_mismatches(repo)


def test_the_package_must_be_the_repository_code(repo, monkeypatch) -> None:
    monkeypatch.setattr(pilot_p1, "package_directory", lambda: repo.parent / "elsewhere")
    assert run("--iteration", iteration(1)).exit_code == 1
    assert "running neuroeco package" in failure_of(repo, "iteration_001")["message"]


# ---------------------------------------------------------------- T3c: IA-3 canonical paths


def test_canonical_paths_are_detected(repo) -> None:
    shutil.copytree(repo / "configs", repo / "configs_alt")
    commit_all(repo, "alternative configuration")
    inputs = [repo / "configs" / "base.yaml"]
    canonical = pilot_p1.repository_checks(
        repo,
        inputs,
        repo / OUTPUT,
        repo / OUTPUT / "x",
        Path("configs/pilots/p1.yaml"),
        Path("configs"),
    )
    alternative = pilot_p1.repository_checks(
        repo,
        inputs,
        repo / OUTPUT,
        repo / OUTPUT / "x",
        Path("configs_alt/pilots/p1.yaml"),
        Path("configs_alt"),
    )
    assert canonical["canonical_paths"] is True and alternative["canonical_paths"] is False


# ---------------------------------------------------------------- T3c: Mn-1, Mn-3, Mn-5


def test_a_local_upstream_branch_is_refused(repo) -> None:
    """Q2: an upstream that is a local branch publishes nothing."""
    git(repo, "branch", "shadow")
    git(repo, "branch", "--set-upstream-to=shadow")
    assert git_upstream(repo)["full_ref"] == "refs/heads/shadow"
    assert run("--iteration", iteration(1)).exit_code == 1
    assert "not a remote-tracking branch" in failure_of(repo, "iteration_001")["message"]


def test_the_remote_url_is_recorded_without_credentials(repo) -> None:
    url = git(repo, "remote", "get-url", "origin")
    assert git_upstream(repo)["remote_url"] == url
    git(repo, "remote", "set-url", "origin", "https://user:secret-token@example.invalid/r.git")
    assert git_upstream(repo)["remote_url"] == "https://example.invalid/r.git"
    git(repo, "remote", "set-url", "origin", url)


@pytest.mark.parametrize("pattern", ["runs/", "*.json", "*.failed-*/"])
def test_ignored_result_files_are_refused(repo, pattern) -> None:
    """Q4: results or failure records that git ignores would never be versioned."""
    (repo / ".gitignore").write_text(pattern + "\n", encoding="utf-8")
    commit_all(repo, "ignore rule")
    output = "runs/p1" if pattern == "runs/" else OUTPUT
    assert run("--iteration", iteration(1), output=output).exit_code == 1
    failure = last_failure(repo / output / "calibration", "iteration_001")
    assert "git ignores result files" in failure["message"]
    assert git_ignored([repo / output / "calibration" / "x.csv"], repo) == (
        ["runs/p1/calibration/x.csv"] if pattern == "runs/" else []
    )


def test_a_repository_with_a_non_ascii_path_runs(tmp_path, monkeypatch) -> None:
    """Mn-5: git prints UTF-8 paths; decoding them with the Windows code page broke the checks."""
    work = build_repo(tmp_path / "repó ñ", monkeypatch)
    named = work / "configs" / "año.yaml"
    named.write_text("x: 1\n", encoding="utf-8")
    commit_all(work, "non-ASCII file name")
    assert git_toplevel(work) == work.resolve()
    assert git_untracked([named], work) == []
    result = run("--iteration", iteration(1))
    assert result.exit_code == 0, result.output
