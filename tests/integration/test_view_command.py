"""T5 (F2): the `view` command, its session record and its equivalence with `run`."""

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pygame
import pytest
from typer.testing import CliRunner

import neuroeco.presentation.cli as cli
import viewer_support as vs  # headless SDL
from neuroeco.presentation.cli import app
from support import state_digest

ROOT = Path(__file__).resolve().parents[2]
CONFIGS = ROOT / "configs"
runner = CliRunner()
AUTOMATIC = ("--no-paused", "--exit-at-end", "--fps", "0")


def view(tmp_path: Path, *args: str):
    return runner.invoke(
        app,
        ["view", "--config-dir", str(CONFIGS), "--output-dir", str(tmp_path), *AUTOMATIC, *args],
    )


def session_record(tmp_path: Path) -> dict:
    (path,) = tmp_path.glob("*/session.json")
    return json.loads(path.read_text(encoding="utf-8"))


def test_view_runs_an_episode_and_records_it(tmp_path) -> None:
    overrides = ("world.n_predators=6", "world.t_max=90")
    result = view(tmp_path, "--scenario", "C", "--episode", "2", *(f"--set={o}" for o in overrides))
    assert result.exit_code == 0, result.output
    record = session_record(tmp_path)
    assert record["status"] == "completed"
    assert record["overrides"] == list(overrides)
    assert record["seed_identity"]["seed_group"] == 0 and record["seed_identity"]["item"] == 2
    assert record["world"]["n_predators"] == 6
    assert record["steps_completed"] == record["metrics"]["steps"] > 0
    assert record["ended_utc"] is not None and record["error"] is None
    for key in ("git_commit", "git_dirty", "python", "numpy", "platform"):
        assert key in record["provenance"]
    assert not list(tmp_path.glob("*/*.tmp"))


def test_view_and_run_produce_the_same_episode(tmp_path, monkeypatch) -> None:
    """Same arguments -> same per-step hashes and same metrics in `run` and in `view`."""
    args = ("--scenario", "B", "--prey", "random", "--predator", "rules", "--episode", "5")
    overrides = ("--set", "world.t_max=150")
    digests: dict[str, list[str]] = {"run": [], "view": []}

    original_run_episode, original_run_session = cli.run_episode, cli.run_session

    def run_episode_spy(*a, **k):
        k["on_step"] = lambda t: digests["run"].append(state_digest(t.world))
        return original_run_episode(*a, **k)

    def run_session_spy(*a, **k):
        k["after_step"] = lambda t: digests["view"].append(state_digest(t.world))
        return original_run_session(*a, **k)

    monkeypatch.setattr(cli, "run_episode", run_episode_spy)
    monkeypatch.setattr(cli, "run_session", run_session_spy)

    ran = runner.invoke(app, ["run", "--config-dir", str(CONFIGS), *args, *overrides])
    viewed = view(tmp_path, *args, *overrides)
    assert ran.exit_code == 0 and viewed.exit_code == 0, ran.output + viewed.output
    assert len(digests["run"]) > 10
    assert digests["view"] == digests["run"]

    def printed(label: str) -> str:
        (line,) = [line for line in ran.output.splitlines() if line.startswith(label)]
        return line[len(label) :].strip()

    metrics = session_record(tmp_path)["metrics"]
    survival = metrics["prey_survival"]
    assert printed("steps") == f"{metrics['steps']} / 150"
    assert printed("prey survival") == f"{survival['numerator'] / survival['denominator']:.4f}"
    assert printed("plants eaten") == str(metrics["plants_eaten"])
    assert printed("captures").split()[0] == str(metrics["captures"])


def test_provenance_is_captured_before_any_output(tmp_path, monkeypatch) -> None:
    seen = {}
    original = cli.collect_provenance

    def spy(*args, **kwargs):
        seen["outputs_existed"] = tmp_path.exists() and any(tmp_path.iterdir())
        return original(*args, **kwargs)

    monkeypatch.setattr(cli, "collect_provenance", spy)
    assert view(tmp_path, "--set", "world.t_max=5").exit_code == 0
    assert seen == {"outputs_existed": False}


def test_record_exists_with_status_running_before_the_episode(tmp_path, monkeypatch) -> None:
    from neuroeco.presentation import viewer as viewer_module

    statuses = []
    original_start = viewer_module.Viewer.start

    def start(self, frame):
        statuses.append(session_record(tmp_path)["status"])
        return original_start(self, frame)

    monkeypatch.setattr(viewer_module.Viewer, "start", start)
    assert view(tmp_path, "--set", "world.t_max=5").exit_code == 0
    assert statuses == ["running"]
    assert session_record(tmp_path)["status"] == "completed"


def test_closing_early_is_recorded(tmp_path, monkeypatch) -> None:
    calls = {"n": 0}

    def events():
        calls["n"] += 1
        return [vs.close_window()] if calls["n"] == 3 else []

    monkeypatch.setattr(pygame.event, "get", events)
    result = view(tmp_path, "--set", "world.t_max=400")
    assert result.exit_code == 0, result.output
    record = session_record(tmp_path)
    assert record["status"] == "closed"
    assert record["steps_completed"] == 2  # renders: S0, after step 0, after step 1 (closed)
    assert record["metrics"] is None and record["ended_utc"] is not None


def test_interruption_is_recorded(tmp_path, monkeypatch) -> None:
    from neuroeco.presentation import viewer as viewer_module

    def interrupt(self, frame):
        self.frame = frame
        raise KeyboardInterrupt

    monkeypatch.setattr(viewer_module.Viewer, "step", interrupt)
    result = view(tmp_path, "--set", "world.t_max=50")
    assert result.exit_code == 130
    record = session_record(tmp_path)
    assert record["status"] == "interrupted" and record["steps_completed"] == 1


def test_unexpected_errors_are_recorded_and_propagate(tmp_path, monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(cli, "run_session", fail)
    result = view(tmp_path, "--set", "world.t_max=5")
    assert result.exit_code != 0 and isinstance(result.exception, RuntimeError)
    record = session_record(tmp_path)
    assert record["status"] == "error" and record["error"] == "RuntimeError: boom"


@pytest.mark.parametrize(
    "args", [("--speed", "3"), ("--set", "world.unknown=1"), ("--prey", "telepathic")]
)
def test_invalid_arguments_fail_before_writing_anything(tmp_path, args) -> None:
    result = view(tmp_path, *args)
    assert result.exit_code == 1 and "error:" in result.output
    assert not tmp_path.exists() or not any(tmp_path.iterdir())


CHILD = textwrap.dedent(
    """
    import sys
    from typer.testing import CliRunner
    from neuroeco.presentation.cli import app

    configs, output = sys.argv[1], sys.argv[2]
    runner = CliRunner()
    commands = (
        ["run", "--config-dir", configs, "--set", "world.t_max=5"],
        ["pilot", "p0", "--config-dir", configs, "--spec", configs + "/pilots/p0.yaml",
         "--output-dir", output, "--repetitions", "1", "--set", "world.t_max=3"],
    )
    for command in commands:
        result = runner.invoke(app, command)
        assert result.exit_code == 0, result.output
    print("pygame" in sys.modules)
    """
)


def test_run_and_pilot_do_not_load_pygame(tmp_path) -> None:
    completed = subprocess.run(
        [sys.executable, "-c", CHILD, str(CONFIGS), str(tmp_path)],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    assert completed.stdout.strip() == "False"
