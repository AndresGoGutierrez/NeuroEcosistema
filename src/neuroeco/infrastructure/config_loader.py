"""YAML configuration loading (ADR-022).

Resolution order: ``base.yaml`` -> scenario overrides (``scenarios.yaml``) -> ``--set``
overrides. The resolved mapping is converted into frozen dataclasses by a strict generic
converter (unknown keys, missing keys and wrong types are rejected) and summarized by a
SHA-256 hash of its canonical JSON form.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import typing
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from neuroeco.application.calibration import IterationSpec, P1Spec, RoundSpec
from neuroeco.application.configs import P0Spec, ReferenceSpec, ResolvedConfig, RuleParams
from neuroeco.application.training import TrainingSpec
from neuroeco.domain.params import WorldParams

BASE_FILE = "base.yaml"
SCENARIOS_FILE = "scenarios.yaml"
BASELINES_FILE = "baselines.yaml"


class ConfigError(ValueError):
    """Invalid configuration file, key, type or override."""


def read_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        content = yaml.safe_load(handle)
    if not isinstance(content, dict):
        raise ConfigError(f"{path} must contain a mapping at the top level")
    return content


def _convert(value: Any, hint: Any, where: str) -> Any:
    if typing.get_origin(hint) is tuple:
        item_hint, ellipsis = (*typing.get_args(hint), None)[:2]
        if ellipsis is not Ellipsis:
            raise ConfigError(f"{where}: only homogeneous tuples (tuple[T, ...]) are supported")
        if not isinstance(value, list | tuple):
            raise ConfigError(f"{where}: expected a list")
        return tuple(_convert(item, item_hint, f"{where}[{i}]") for i, item in enumerate(value))
    if dataclasses.is_dataclass(hint):
        if not isinstance(value, Mapping):
            raise ConfigError(f"{where}: expected a mapping")
        return build_dataclass(hint, value, where)
    if hint is bool:
        if not isinstance(value, bool):
            raise ConfigError(f"{where}: expected a boolean, got {value!r}")
        return value
    if hint is int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigError(f"{where}: expected an integer, got {value!r}")
        return value
    if hint is float:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ConfigError(f"{where}: expected a number, got {value!r}")
        return float(value)
    if hint is str:
        if not isinstance(value, str):
            raise ConfigError(f"{where}: expected a string, got {value!r}")
        return value
    raise ConfigError(f"{where}: unsupported field type {hint!r}")


def build_dataclass[T](cls: type[T], data: Mapping[str, Any], where: str = "") -> T:
    """Strictly build ``cls`` from a mapping (recursively for nested dataclasses)."""
    hints = typing.get_type_hints(cls)
    names = [f.name for f in dataclasses.fields(cls)]  # type: ignore[arg-type]
    unknown = sorted(set(data) - set(names))
    missing = sorted(set(names) - set(data))
    prefix = f"{where}." if where else ""
    if unknown:
        raise ConfigError(f"unknown keys: {', '.join(prefix + k for k in unknown)}")
    if missing:
        raise ConfigError(f"missing keys: {', '.join(prefix + k for k in missing)}")
    kwargs = {name: _convert(data[name], hints[name], prefix + name) for name in names}
    return cls(**kwargs)


def apply_override(tree: dict[str, Any], assignment: str) -> None:
    """Apply one ``dotted.path=value`` override; the value is parsed as YAML."""
    if "=" not in assignment:
        raise ConfigError(f"override must look like key.path=value, got {assignment!r}")
    path, raw_value = assignment.split("=", 1)
    keys = path.strip().split(".")
    if not all(keys):
        raise ConfigError(f"invalid override path {path!r}")
    node: Any = tree
    for key in keys[:-1]:
        if not isinstance(node, dict) or key not in node:
            raise ConfigError(f"override path not found: {path}")
        node = node[key]
    if not isinstance(node, dict) or keys[-1] not in node:
        raise ConfigError(f"override path not found: {path}")
    if isinstance(node[keys[-1]], dict):
        raise ConfigError(f"override must target a single value, not a section: {path}")
    node[keys[-1]] = yaml.safe_load(raw_value)


def config_hash(tree: Mapping[str, Any]) -> str:
    canonical = json.dumps(tree, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def resolve_tree(config_dir: Path, scenario: str, overrides: Sequence[str] = ()) -> dict[str, Any]:
    """Merge base, scenario and overrides into one plain mapping."""
    base = read_yaml(config_dir / BASE_FILE)
    scenarios = read_yaml(config_dir / SCENARIOS_FILE).get("scenarios", {})
    baselines = read_yaml(config_dir / BASELINES_FILE)
    if scenario not in scenarios:
        raise ConfigError(f"unknown scenario {scenario!r}; available: {sorted(scenarios)}")

    world = copy.deepcopy(base.get("world", {}))
    scenario_overrides = scenarios[scenario] or {}
    unknown = sorted(set(scenario_overrides) - set(world))
    if unknown:
        raise ConfigError(f"scenario {scenario} overrides unknown world keys: {unknown}")
    world.update(copy.deepcopy(scenario_overrides))

    tree: dict[str, Any] = {
        "project_seed": base.get("project_seed"),
        "scenario": scenario,
        "world": world,
        "rules": copy.deepcopy(baselines.get("rules", {})),
    }
    for assignment in overrides:
        apply_override(tree, assignment)
    return tree


def load_config(config_dir: Path, scenario: str, overrides: Sequence[str] = ()) -> ResolvedConfig:
    tree = resolve_tree(config_dir, scenario, overrides)
    seed = tree["project_seed"]
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ConfigError("project_seed must be an integer")
    return ResolvedConfig(
        project_seed=seed,
        scenario=scenario,
        world=build_dataclass(WorldParams, tree["world"], "world"),
        rules=build_dataclass(RuleParams, tree["rules"], "rules"),
        config_hash=config_hash(tree),
    )


def load_p0_spec(path: Path) -> P0Spec:
    return build_dataclass(P0Spec, read_yaml(path), path.stem)


def load_training_spec(path: Path) -> TrainingSpec:
    """One training run (F6, ADR-027)."""
    return _build_spec(TrainingSpec, path)


def load_reference_spec(path: Path) -> ReferenceSpec:
    """I2 reference set of F5 (ADR-018)."""
    return _build_spec(ReferenceSpec, path)


def check_unique_seed_groups(declared: Mapping[str, int]) -> None:
    """ADR-028: every configuration must declare a distinct seed_group."""
    owners: dict[int, str] = {}
    for name, group in declared.items():
        if isinstance(group, bool) or not isinstance(group, int) or group < 0:
            raise ConfigError(f"{name}: seed_group must be a non-negative integer")
        if group in owners:
            raise ConfigError(f"seed_group {group} is declared by both {owners[group]} and {name}")
        owners[group] = name


def _build_spec[T](cls: type[T], path: Path) -> T:
    try:
        return build_dataclass(cls, read_yaml(path), path.stem)
    except ValueError as error:  # ConfigError and the dataclass validations
        raise ConfigError(f"{path}: {error}") from error


def load_p1_spec(path: Path, existing_seed_groups: Mapping[str, int]) -> P1Spec:
    """Pilot P1 specification (ADR-033, P1-13).

    ``existing_seed_groups`` are the groups already declared elsewhere (for example the
    exploratory group 0 and the group of P0); P1 must not reuse any of them (ADR-028).
    """
    spec = _build_spec(P1Spec, path)
    check_unique_seed_groups({**existing_seed_groups, **spec.declared_seed_groups()})
    return spec


def load_iteration_spec(path: Path) -> IterationSpec:
    """Pre-registered calibration iteration, ``configs/pilots/p1/iterations/NNN.yaml``."""
    return _build_spec(IterationSpec, path)


def load_round_spec(path: Path) -> RoundSpec:
    """Pre-registered rule-tuning round, ``configs/pilots/p1/rounds/RR.yaml``."""
    return _build_spec(RoundSpec, path)
