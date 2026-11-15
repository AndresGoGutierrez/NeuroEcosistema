"""Application-level configuration objects (ADR-022)."""

from __future__ import annotations

from dataclasses import dataclass

from neuroeco.domain.params import WorldParams


def _check_fraction(name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, int | float) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be a number in [0, 1], got {value!r}")


@dataclass(frozen=True)
class PreyRuleParams:
    flee_threshold: float
    cruise_fraction: float

    def __post_init__(self) -> None:
        _check_fraction("flee_threshold", self.flee_threshold)
        _check_fraction("cruise_fraction", self.cruise_fraction)


@dataclass(frozen=True)
class PredatorRuleParams:
    cruise_fraction: float

    def __post_init__(self) -> None:
        _check_fraction("cruise_fraction", self.cruise_fraction)


@dataclass(frozen=True)
class RuleParams:
    """Parameters of the rule-based reference policies (ADR-012); calibrated in P1."""

    prey: PreyRuleParams
    predator: PredatorRuleParams


@dataclass(frozen=True)
class ResolvedConfig:
    """Fully resolved configuration of one run: base, then scenario, then overrides."""

    project_seed: int
    scenario: str
    world: WorldParams
    rules: RuleParams
    config_hash: str
