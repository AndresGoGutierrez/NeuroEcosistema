"""T11: configuration loading (ADR-022, ADR-028, ADR-029)."""

import dataclasses
import re
import shutil
from pathlib import Path

import pytest
import yaml

from neuroeco.domain.params import ConfigurationError, calibration_checks
from neuroeco.infrastructure.config_loader import (
    ConfigError,
    check_unique_seed_groups,
    load_config,
)
from support import PROVISIONAL_WORLD

CONFIGS = Path(__file__).resolve().parents[3] / "configs"


@pytest.fixture
def config_dir(tmp_path) -> Path:
    """A writable copy of the real configuration directory."""
    target = tmp_path / "configs"
    shutil.copytree(CONFIGS, target)
    return target


def edit(path: Path, change) -> None:
    content = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(content)
    path.write_text(yaml.safe_dump(content), encoding="utf-8")


def test_base_configuration_matches_the_approved_provisional_values() -> None:
    config = load_config(CONFIGS, "A")
    assert config.world == PROVISIONAL_WORLD
    assert config.project_seed == 151810796106167051982782525292607188790
    assert config.rules.prey.flee_threshold == 0.3
    assert all(check.satisfied for check in calibration_checks(config.world))


def test_scenarios_change_exactly_one_factor() -> None:
    a, b, c = (load_config(CONFIGS, s).world for s in "ABC")

    def differences(x, y) -> set[str]:
        return {f.name for f in dataclasses.fields(x) if getattr(x, f.name) != getattr(y, f.name)}

    assert differences(a, b) == {"n_plants"} and b.n_plants < a.n_plants
    assert differences(a, c) == {"n_predators"} and c.n_predators > a.n_predators


def test_unknown_scenario_is_rejected() -> None:
    with pytest.raises(ConfigError, match="unknown scenario"):
        load_config(CONFIGS, "Z")


def test_unknown_key_is_rejected(config_dir) -> None:
    edit(config_dir / "base.yaml", lambda c: c["world"]["prey"].update(speed_bonus=1.0))
    with pytest.raises(ConfigError, match=re.escape("unknown keys: world.prey.speed_bonus")):
        load_config(config_dir, "A")


def test_missing_key_is_rejected(config_dir) -> None:
    edit(config_dir / "base.yaml", lambda c: c["world"].pop("eat_radius"))
    with pytest.raises(ConfigError, match=re.escape("missing keys: world.eat_radius")):
        load_config(config_dir, "A")


@pytest.mark.parametrize(("key", "value"), [("t_max", 10.5), ("n_prey", True), ("size", "big")])
def test_wrong_types_are_rejected(config_dir, key, value) -> None:
    edit(config_dir / "base.yaml", lambda c: c["world"].update({key: value}))
    with pytest.raises(ConfigError):
        load_config(config_dir, "A")


def test_scenario_cannot_introduce_unknown_keys(config_dir) -> None:
    edit(config_dir / "scenarios.yaml", lambda c: c["scenarios"]["B"].update(rain=1))
    with pytest.raises(ConfigError, match="unknown world keys"):
        load_config(config_dir, "B")


def test_domain_invariants_still_apply(config_dir) -> None:
    edit(config_dir / "base.yaml", lambda c: c["world"].update(capture_radius=1.0))
    with pytest.raises(ConfigurationError, match="K1"):
        load_config(config_dir, "A")


def test_overrides_are_applied_after_the_scenario() -> None:
    config = load_config(
        CONFIGS, "B", ["world.n_plants=7", "world.prey.v_max=0.9", "rules.prey.flee_threshold=0.5"]
    )
    assert config.world.n_plants == 7
    assert config.world.prey.v_max == 0.9
    assert config.rules.prey.flee_threshold == 0.5


@pytest.mark.parametrize(
    "assignment",
    ["world.n_plants", "world.unknown=3", "world.prey=1", "world..size=3", "nothing.here=1"],
)
def test_invalid_overrides_are_rejected(assignment) -> None:
    with pytest.raises(ConfigError):
        load_config(CONFIGS, "A", [assignment])


def test_config_hash_is_stable_and_sensitive() -> None:
    first = load_config(CONFIGS, "A").config_hash
    assert first == load_config(CONFIGS, "A").config_hash
    assert first != load_config(CONFIGS, "B").config_hash
    assert first != load_config(CONFIGS, "A", ["world.t_max=999"]).config_hash
    assert len(first) == 64


def test_seed_groups_must_be_unique() -> None:
    check_unique_seed_groups({"p0": 1, "p1": 2})
    with pytest.raises(ConfigError, match="seed_group 1"):
        check_unique_seed_groups({"p0": 1, "p1": 1})
    with pytest.raises(ConfigError):
        check_unique_seed_groups({"p0": -1})
