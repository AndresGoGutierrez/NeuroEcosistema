"""Shared helpers for the tests of ``neuroeco pilot p1`` (F4 T3, T3b).

Every helper builds a temporary copy of the configuration with a synthetic P1 specification
(seed_group >= 1000, D16), t_max = 40 and energetics scaled so that E1 and E2 still hold: state
K is evaluated, never bypassed. No real P1 episode, specification or result is created.
"""

import csv
import json
import os
import shutil
import subprocess
from pathlib import Path

import yaml
from typer.testing import CliRunner

from neuroeco.presentation import pilot_p1
from neuroeco.presentation.cli import app

CONFIGS = Path(__file__).resolve().parents[1] / "configs"
VALUES = {
    "plant_energy": 30.0,
    "regrow_delay": 50,
    "n_plants_a": 40,
    "n_plants_b": 15,
    "n_predators_c": 8,
    "prey_flee_threshold": 0.3,
    "prey_cruise_fraction": 0.5,
    "predator_cruise_fraction": 0.5,
}
SYNTHETIC_SPEC = {
    "pilot": "P1",
    "blocks": {
        "calibration": {"episodes": 2, "seed_groups": {"a": 1000, "b": 1001, "c": 1002}},
        "confirmation": {"episodes": 2, "seed_groups": {"a": 1010, "b": 1011, "c": 1012}},
        "second_confirmation": {"episodes": 2, "seed_groups": {"a": 1020, "b": 1021, "c": 1022}},
    },
    "grids": {"prey_flee_threshold": [0.2, 0.3, 0.4, 0.5], "cruise_fraction": [0.3, 0.5, 0.7]},
}
PASSING_GIT_CHECKS = {
    "root": "simulated",
    "outside_repository": [],
    "untracked": [],
    "hidden_changes": [],
    "content_overrides": [],
    "head_mismatches": [],
    "package_inside": True,
    "canonical_paths": True,
    "output_root_inside": True,
    "ignored_outputs": [],
    "head": "simulated",
    "upstream": "origin/main",
    "upstream_full_ref": "refs/remotes/origin/main",
    "remote": "origin",
    "remote_url": "https://example.invalid/simulated.git",
    "upstream_commit": "simulated",
    "synchronized": True,
}


def make_configs(root: Path, spec: dict | None = None) -> Path:
    """``root/configs``: the real configuration files with the synthetic changes above."""
    configs = root / "configs"
    shutil.copytree(CONFIGS, configs)
    shutil.rmtree(configs / "pilots" / "p1", ignore_errors=True)  # never a real registry
    base = yaml.safe_load((configs / "base.yaml").read_text(encoding="utf-8"))
    base["world"]["t_max"] = 40
    for species in ("prey", "predator"):
        base["world"][species]["c_basal"] = 4.0  # E1: 80 / 4 = 20 = 0.5 * t_max
        base["world"][species]["c_move"] = 8.0  # E2
    (configs / "base.yaml").write_text(yaml.safe_dump(base), encoding="utf-8")
    write_spec(configs, spec or SYNTHETIC_SPEC)
    return configs


def write_spec(configs: Path, spec: dict) -> None:
    (configs / "pilots" / "p1.yaml").write_text(yaml.safe_dump(spec), encoding="utf-8")


def simulate_git(monkeypatch, output: Path) -> dict:
    """Replace the git facts of the command module (T3-5): the production checks are unchanged.

    ``state["git_dirty"]`` and ``state["checks"]`` (overrides of the repository checks) let a
    test simulate each git refusal; ``state["inputs"]`` records the files the command declared.
    """
    state: dict = {"git_dirty": False, "files_at_capture": [], "checks": {}, "inputs": None}
    real = pilot_p1.collect_provenance

    def collect(command, cwd, config_hash):
        state["files_at_capture"].append(sorted(p.name for p in output.rglob("*")))
        return {**real(command, cwd, config_hash), "git_dirty": state["git_dirty"]}

    def checks(cwd, inputs, output_root, destination, spec_path, config_dir):
        state["inputs"] = list(inputs)
        return {**PASSING_GIT_CHECKS, **state["checks"]}

    monkeypatch.setattr(pilot_p1, "collect_provenance", collect)
    monkeypatch.setattr(pilot_p1, "repository_checks", checks)
    return state


def register(configs: Path, number: int, stage: str, changed: str = "none", **values) -> Path:
    path = configs / "pilots" / "p1" / "iterations" / f"{number:03d}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    content = {
        "iteration": number,
        "stage": stage,
        "changed_parameter": changed,
        "values": {**VALUES, **values},
        "motive": "synthetic test iteration",
        "exploratory_observations": "",
    }
    path.write_text(yaml.safe_dump(content), encoding="utf-8")
    return path


def invoke(configs: Path, output: Path, *arguments: str):
    return CliRunner().invoke(
        app,
        [
            "pilot",
            "p1",
            *arguments,
            "--spec",
            str(configs / "pilots" / "p1.yaml"),
            "--config-dir",
            str(configs),
            "--output-root",
            str(output),
        ],
    )


def run_ok(configs: Path, output: Path, *arguments: str) -> None:
    result = invoke(configs, output, *arguments)
    assert result.exit_code == 0, result.output


def run_chain(configs: Path, output: Path) -> Path:
    """Register and run iterations 1 (A), 2 (B) and 3 (C); returns the stage-C specification."""
    paths = [register(configs, 1, "A"), register(configs, 2, "B"), register(configs, 3, "C")]
    for path in paths:
        run_ok(configs, output, "--iteration", str(path))
    return paths[-1]


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def failures(output: Path) -> list[Path]:
    return sorted(output.rglob("*.failed-*"))


def only_failure(output: Path) -> tuple[Path, dict]:
    [directory] = failures(output)
    assert not list(directory.glob("*.csv")), "a failure never keeps CSV files"
    return directory, read_json(directory / "failure.json")


def last_failure(directory_parent: Path, name: str) -> dict:
    """failure.json of the newest failed attempt at ``directory_parent / name``.

    Names share the second of the timestamp and end in a random suffix, so the newest attempt
    is the one that lists the most earlier attempts.
    """
    records = [
        read_json(path / "failure.json")
        for path in directory_parent.glob(f"{name}.failed-*")
        if (path / "failure.json").exists()
    ]
    return max(records, key=lambda record: len(record["previous_attempts"]))


def assert_no_results(output: Path) -> None:
    assert not list(output.rglob("*.csv"))
    assert not list(output.rglob("*.partial-*"))


# ---------------------------------------------------------------- temporary git repositories


def isolate_git(monkeypatch, tmp_path: Path) -> None:
    """Git commands of the test (and of the command under test) ignore the user's settings.

    A synthetic local identity commits in temporary repositories only; the project repository
    is never touched. Git never looks for a repository above ``tmp_path`` (a parent directory,
    such as the user's home, may itself be a repository).
    """
    empty = tmp_path / "gitconfig"
    empty.write_text("", encoding="utf-8")
    for name, value in {
        "GIT_CEILING_DIRECTORIES": tmp_path.as_posix(),
        "GIT_CONFIG_GLOBAL": str(empty),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "neuroeco-test",
        "GIT_AUTHOR_EMAIL": "neuroeco-test@example.invalid",
        "GIT_COMMITTER_NAME": "neuroeco-test",
        "GIT_COMMITTER_EMAIL": "neuroeco-test@example.invalid",
    }.items():
        monkeypatch.setenv(name, value)


def git(cwd: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        capture_output=True,
        encoding="utf-8",
        check=True,
        env=os.environ.copy(),
    )
    return completed.stdout.strip()


def commit_all(work: Path, message: str, *, push: bool = True) -> None:
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", message)
    if push:
        git(work, "push", "-q")
