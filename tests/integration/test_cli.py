"""T13: entry point, composition root and the `run` command."""

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from neuroeco import launcher
from neuroeco.bootstrap import REFERENCE_POLICIES, build_policy, build_runtime
from neuroeco.domain.policies import (
    ConstantPolicy,
    RandomPolicy,
    RuleBasedPredatorPolicy,
    RuleBasedPreyPolicy,
)
from neuroeco.presentation.cli import app

CONFIGS = Path(__file__).resolve().parents[2] / "configs"
runner = CliRunner()


def invoke(*args: str):
    return runner.invoke(app, ["run", "--config-dir", str(CONFIGS), *args])


@pytest.mark.parametrize("scenario", ["A", "B", "C"])
def test_run_works_in_every_scenario(scenario) -> None:
    result = invoke("--scenario", scenario, "--set", "world.t_max=100")
    assert result.exit_code == 0, result.output
    assert f"scenario            {scenario}" in result.output
    assert "prey survival" in result.output


@pytest.mark.parametrize("policy", REFERENCE_POLICIES)
def test_run_accepts_every_reference_policy(policy) -> None:
    result = invoke("--prey", policy, "--predator", policy, "--set", "world.t_max=50")
    assert result.exit_code == 0, result.output


def test_run_is_reproducible() -> None:
    first = invoke("--episode", "2", "--set", "world.t_max=120")
    second = invoke("--episode", "2", "--set", "world.t_max=120")
    assert first.output == second.output


@pytest.mark.parametrize(
    "args",
    [
        ("--scenario", "Z"),
        ("--prey", "telepathic"),
        ("--set", "world.unknown=1"),
        ("--set", "world.capture_radius=0.5"),  # violates K1
    ],
)
def test_run_reports_errors_cleanly(args) -> None:
    result = invoke(*args)
    assert result.exit_code == 1
    assert "error:" in result.output


def test_policy_factory_builds_the_expected_types() -> None:
    config = build_runtime("A", config_dir=CONFIGS).config
    assert isinstance(build_policy("rules", "prey", config), RuleBasedPreyPolicy)
    assert isinstance(build_policy("rules", "predator", config), RuleBasedPredatorPolicy)
    assert isinstance(build_policy("random", "prey", config), RandomPolicy)
    probe = build_policy("straight_cruise", "predator", config)
    assert isinstance(probe, ConstantPolicy) and probe.throttle == 0.0  # cruise 0.5
    with pytest.raises(ValueError):
        build_policy("rules", "plant", config)


def test_launcher_sets_thread_defaults_without_overriding(monkeypatch) -> None:
    for name in launcher.THREAD_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OMP_NUM_THREADS", "3")
    launcher.configure_environment()
    assert os.environ["OMP_NUM_THREADS"] == "3"
    assert all(os.environ[name] == "1" for name in launcher.THREAD_VARIABLES[1:])
