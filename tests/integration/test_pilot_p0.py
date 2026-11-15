"""T14: pilot P0 specification, timing use case and command."""

import csv
import itertools
import json
from dataclasses import replace
from pathlib import Path

import pytest
from typer.testing import CliRunner

from neuroeco.application.configs import P0Spec
from neuroeco.application.evaluation import EpisodeIdentity, time_episode
from neuroeco.application.seeding import Purpose, SeedRegistry
from neuroeco.domain.policies import RuleBasedPredatorPolicy, RuleBasedPreyPolicy
from neuroeco.infrastructure.config_loader import ConfigError, load_p0_spec
from neuroeco.presentation.cli import app

CONFIGS = Path(__file__).resolve().parents[2] / "configs"
SPEC = CONFIGS / "pilots" / "p0.yaml"


def test_p0_specification_matches_the_approved_plan() -> None:
    spec = load_p0_spec(SPEC)
    assert spec.prey_counts == (10, 25, 50) and spec.predator_counts == (3, 8)
    assert (spec.reference_prey, spec.reference_predators) == (50, 8)  # decision A4
    assert spec.repetitions == 5 and spec.threshold_us == 500.0
    assert spec.seed_group == 1  # 0 is reserved for exploratory runs


def test_p0_reference_must_belong_to_the_grid() -> None:
    spec = load_p0_spec(SPEC)
    with pytest.raises(ValueError, match="reference_prey"):
        replace(spec, reference_prey=40)
    with pytest.raises(ValueError, match="repetitions"):
        replace(spec, repetitions=0)


def test_tuple_fields_require_lists_of_integers(tmp_path) -> None:
    bad = tmp_path / "p0.yaml"
    bad.write_text(SPEC.read_text(encoding="utf-8").replace("[10, 25, 50]", "[10, 2.5]"))
    with pytest.raises(ConfigError, match=r"prey_counts\[1\]"):
        load_p0_spec(bad)
    assert isinstance(load_p0_spec(SPEC), P0Spec)


def test_time_episode_uses_the_injected_clock(world_params) -> None:
    params = world_params(t_max=15)
    ticks = itertools.count()
    timed = time_episode(
        params,
        RuleBasedPreyPolicy(params.prey.omega_max, 0.3, 0.5),
        RuleBasedPredatorPolicy(params.predator.omega_max, 0.5),
        SeedRegistry(42),
        EpisodeIdentity(Purpose.PILOT, seed_group=1),
        clock=lambda: float(next(ticks)),
    )
    assert timed.steps == 15
    assert timed.phase_seconds == {"perception": 15.0, "decision": 15.0, "rules": 15.0}
    assert timed.total_seconds > 45.0
    assert timed.seconds_per_step == timed.total_seconds / 15


def test_p0_command_writes_evidence(tmp_path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "pilot",
            "p0",
            "--spec",
            str(SPEC),
            "--config-dir",
            str(CONFIGS),
            "--output-dir",
            str(tmp_path),
            "--repetitions",
            "2",
            "--set",
            "world.t_max=20",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "reference (50 prey, 8 predators)" in result.output

    with (tmp_path / "p0_episodes.csv").open(encoding="utf-8") as handle:
        episodes = list(csv.DictReader(handle))
    with (tmp_path / "p0_summary.csv").open(encoding="utf-8") as handle:
        summary = list(csv.DictReader(handle))
    assert len(episodes) == 3 * 2 * 2 and len(summary) == 3 * 2
    assert {row["seed_item"] for row in episodes} == {"0", "1"}
    assert all(float(row["us_per_step"]) > 0 for row in episodes)

    provenance = json.loads((tmp_path / "p0_provenance.json").read_text(encoding="utf-8"))
    assert provenance["verdict"] in {"PASS", "FAIL"}
    assert provenance["spec"]["repetitions"] == 2
    assert provenance["world_overrides"] == ["world.t_max=20"]
    for key in ("git_commit", "python", "numpy", "platform", "cpu_count", "config_hash"):
        assert key in provenance


def test_p0_provenance_is_captured_before_any_output(tmp_path, monkeypatch) -> None:
    import neuroeco.presentation.cli as cli

    seen: dict[str, bool] = {}
    original = cli.collect_provenance

    def spy(*args, **kwargs):
        seen["outputs_existed"] = any(tmp_path.iterdir())
        return original(*args, **kwargs)

    monkeypatch.setattr(cli, "collect_provenance", spy)
    result = CliRunner().invoke(
        app,
        [
            "pilot",
            "p0",
            "--spec",
            str(SPEC),
            "--config-dir",
            str(CONFIGS),
            "--output-dir",
            str(tmp_path),
            "--repetitions",
            "1",
            "--set",
            "world.t_max=5",
        ],
    )
    assert result.exit_code == 0, result.output
    assert seen == {"outputs_existed": False}
