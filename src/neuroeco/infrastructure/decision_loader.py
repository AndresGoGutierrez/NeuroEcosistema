"""Loader of the author decisions of P1, ``configs/pilots/p1_decisions/NNN.yaml`` (T4d).

Strict like every specification of P1: unknown or missing keys, wrong types, a file name that
is not the decision number, a gap in the numbering or any other entry in the directory are
refused.
"""

from __future__ import annotations

import re
from pathlib import Path

from neuroeco.application.decisions import DECISION_TYPES, AuthorDecision
from neuroeco.infrastructure.config_loader import ConfigError, build_dataclass, read_yaml

DECISIONS_DIRECTORY = "p1_decisions"  # next to p1.yaml (D-T4d-3)
DECISION_FILE = re.compile(r"\d{3}\.yaml")


def load_decision(path: Path) -> AuthorDecision:
    data = read_yaml(path)
    kind = data.get("kind")
    if kind not in DECISION_TYPES:
        raise ConfigError(f"{path}: kind must be one of {sorted(DECISION_TYPES)}, got {kind!r}")
    try:
        decision = build_dataclass(DECISION_TYPES[kind], data, path.stem)
    except ValueError as error:  # ConfigError and the dataclass validations
        raise ConfigError(f"{path}: {error}") from error
    if path.stem != f"{decision.decision:03d}":
        raise ConfigError(f"{path}: decision {decision.decision} must be in a file NNN.yaml")
    return decision


def load_decisions(spec_path: Path) -> tuple[tuple[Path, AuthorDecision], ...]:
    """Every decision registered next to ``p1.yaml``, numbered 1, 2, ... without gaps."""
    directory = spec_path.parent / DECISIONS_DIRECTORY
    if not directory.exists():
        return ()
    entries = sorted(directory.iterdir())
    unexpected = [e.name for e in entries if not (e.is_file() and DECISION_FILE.fullmatch(e.name))]
    if unexpected:
        raise ConfigError(f"{directory}: unexpected entries {unexpected}; only NNN.yaml files")
    decisions = tuple((path, load_decision(path)) for path in entries)
    numbers = [decision.decision for _, decision in decisions]
    if numbers != list(range(1, len(numbers) + 1)):
        raise ConfigError(f"{directory}: decisions must be numbered 1, 2, ... without gaps")
    return decisions
