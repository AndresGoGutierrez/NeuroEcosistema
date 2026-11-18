"""F8: formal campaign (resumable training with a stop time) and test evaluation, reduced."""

import csv
import shutil
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from neuroeco.application.experiment import (
    CONFIGURATIONS,
    Protocol,
    formal_specs,
    rule_variant,
)
from neuroeco.infrastructure.config_loader import load_config
from neuroeco.presentation.cli import app

CONFIGS = Path(__file__).resolve().parents[2] / "configs"
PROTOCOL = {
    "runs": 2,
    "test_episodes": 1,
    "first_seed_group": 100,
    "population": 3,
    "elite": 1,
    "tournament": 2,
    "episodes": 1,
    "validation_episodes": 1,
    "generations": 2,
    "validation_interval": 1,
    "sigma_prey_base": 0.05,
    "sigma_predator_base": 0.05,
    "sigma_prey_compact": 0.1,
    "sigma_predator_compact": 0.1,
    "curriculum_kappa": 2.0,
    "curriculum_generations": 1,
}


def test_formal_specs_are_balanced_and_independent() -> None:
    specs = formal_specs(Protocol(**PROTOCOL))
    assert len(specs) == 2 * len(CONFIGURATIONS)
    assert [s.run for s in specs[:8]] == [0] * 8  # run index first
    assert len({(s.seed_group, s.run) for s in specs}) == len(specs)
    assert {s.seed_group for s in specs} == set(range(100, 108))
    assert all(s.curriculum_kappa == (2.0 if s.species == "predator" else 1.0) for s in specs)
    assert {s.sigma for s in specs if "compact" in s.architecture} == {0.1}


def test_formal_seed_groups_start_at_100() -> None:
    with pytest.raises(ValueError, match="start at 100"):
        Protocol(**{**PROTOCOL, "first_seed_group": 40})


def test_rule_variants_follow_adr_012() -> None:
    rules = load_config(CONFIGS, "A").rules
    assert rule_variant("prey", rules, "low").prey.flee_threshold == pytest.approx(0.1)
    assert rule_variant("prey", rules, "high").prey.flee_threshold == pytest.approx(0.3)
    assert rule_variant("predator", rules, "low").predator.cruise_fraction == pytest.approx(0.525)
    assert rule_variant("predator", rules, "high").predator.cruise_fraction == pytest.approx(0.875)
    assert rule_variant("prey", rules, "nominal") is rules


@pytest.fixture
def campaign(tmp_path):
    configs = tmp_path / "configs"
    shutil.copytree(CONFIGS, configs)
    base = yaml.safe_load((configs / "base.yaml").read_text("utf-8"))
    base["world"]["t_max"] = 60
    (configs / "base.yaml").write_text(yaml.safe_dump(base), encoding="utf-8")
    protocol = tmp_path / "protocol.yaml"
    protocol.write_text(yaml.safe_dump(PROTOCOL), encoding="utf-8")
    common = ["--protocol", str(protocol), "--root", str(tmp_path / "f8")]
    return tmp_path, [*common, "--config-dir", str(configs), "--workers", "0"]


def test_campaign_stops_before_the_deadline_and_resumes(campaign) -> None:
    tmp_path, options = campaign
    runner = CliRunner()
    past = "2000-01-01T00:00"
    first = runner.invoke(app, ["experiment", "train", *options, "--stop-at", past])
    assert first.exit_code == 0 and "stop:" in first.output  # nothing fits before the deadline
    assert not any((tmp_path / "f8" / "runs").iterdir())
    done = runner.invoke(app, ["experiment", "train", *options])
    assert done.exit_code == 0 and "all formal runs are complete" in done.output
    again = runner.invoke(app, ["experiment", "train", *options])
    assert again.exit_code == 0 and "F_val" not in again.output  # complete runs are kept

    evaluated = runner.invoke(app, ["experiment", "evaluate", *options])
    assert evaluated.exit_code == 0, evaluated.output
    with (tmp_path / "f8" / "test_episodes.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    after = {(r["run"], r["opponent"]) for r in rows if r["model"] == "after"}
    assert ("f8_prey_base_A_r0", "M0") in after and ("f8_prey_base_A_r1", "M3") in after
    cross = [r for r in rows if r["opponent"] == "M4" and r["scenario"] == "B"]
    assert len(cross) == 2 * 2 * 2 + 2 * 2  # prey and predator x 2 x 2 runs, plus rules refs
    assert {r["model"] for r in rows} == {"before", "after", "reference"}
    repeated = runner.invoke(app, ["experiment", "evaluate", *options])
    assert repeated.exit_code == 1 and "never overwritten" in repeated.output
