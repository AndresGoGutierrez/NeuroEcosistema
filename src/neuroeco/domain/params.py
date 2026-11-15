"""Immutable ecosystem parameters and their invariants.

Hard invariants (ADR-022, ADR-030) are enforced at construction:

- K1: capture_radius >= predator.v_max + prey.v_max (no tunnelling between steps)
- K2: eat_radius >= prey.v_max
- K3: vision_radius < size / 2 for both species (unique minimal image on the torus)
- K4: predator.v_max > prey.v_max and prey.omega_max > predator.omega_max

E1, E2 and E5 are calibration targets, not invariants: ``calibration_checks`` reports them
without rejecting the configuration (ADR-022, ADR-020 criterion A1).
"""

from __future__ import annotations

import math
from dataclasses import dataclass


class ConfigurationError(ValueError):
    """Raised when parameters violate a domain invariant."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ConfigurationError(message)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_real(value: object) -> bool:
    return (isinstance(value, int | float)) and not isinstance(value, bool) and math.isfinite(value)


@dataclass(frozen=True)
class SpeciesParams:
    """Kinematic, perceptual and energetic parameters of one species."""

    v_max: float
    omega_max: float
    vision_radius: float
    e_max: float
    initial_energy_fraction: float
    c_basal: float
    c_move: float

    def __post_init__(self) -> None:
        for name in (
            "v_max",
            "omega_max",
            "vision_radius",
            "e_max",
            "initial_energy_fraction",
            "c_basal",
            "c_move",
        ):
            _require(_is_real(getattr(self, name)), f"{name} must be a finite real number")
        _require(self.v_max > 0, "v_max must be > 0")
        _require(0 < self.omega_max <= math.pi, "omega_max must be in (0, pi]")
        _require(self.vision_radius > 0, "vision_radius must be > 0")
        _require(self.e_max > 0, "e_max must be > 0")
        _require(0 < self.initial_energy_fraction <= 1, "initial_energy_fraction must be in (0, 1]")
        _require(self.c_basal > 0, "c_basal must be > 0")
        _require(self.c_move >= 0, "c_move must be >= 0")

    @property
    def initial_energy(self) -> float:
        """E0 = rho0 * E_max (ADR-010)."""
        return self.initial_energy_fraction * self.e_max


@dataclass(frozen=True)
class WorldParams:
    """World, population and interaction parameters of one scenario."""

    size: float
    t_max: int
    n_prey: int
    n_predators: int
    n_plants: int
    regrow_delay: int
    capture_radius: float
    eat_radius: float
    plant_energy: float
    prey_energy: float
    prey: SpeciesParams
    predator: SpeciesParams

    def __post_init__(self) -> None:
        for name in ("t_max", "n_prey", "n_predators", "n_plants", "regrow_delay"):
            _require(_is_int(getattr(self, name)), f"{name} must be an integer")
        for name in ("size", "capture_radius", "eat_radius", "plant_energy", "prey_energy"):
            _require(_is_real(getattr(self, name)), f"{name} must be a finite real number")
        _require(
            isinstance(self.prey, SpeciesParams) and isinstance(self.predator, SpeciesParams),
            "prey and predator must be SpeciesParams",
        )
        _require(self.size > 0, "size must be > 0")
        _require(self.t_max >= 1, "t_max must be >= 1")
        _require(self.n_prey >= 1, "n_prey must be >= 1")
        _require(self.n_predators >= 0, "n_predators must be >= 0")
        _require(self.n_plants >= 0, "n_plants must be >= 0")
        _require(self.regrow_delay >= 1, "regrow_delay must be >= 1")
        _require(self.plant_energy > 0, "plant_energy must be > 0")
        _require(self.prey_energy > 0, "prey_energy must be > 0")

        _require(
            self.capture_radius >= self.predator.v_max + self.prey.v_max,
            "K1 violated: capture_radius must be >= predator.v_max + prey.v_max",
        )
        _require(
            self.eat_radius >= self.prey.v_max, "K2 violated: eat_radius must be >= prey.v_max"
        )
        for label, species in (("prey", self.prey), ("predator", self.predator)):
            _require(
                species.vision_radius < self.size / 2,
                f"K3 violated: {label}.vision_radius must be < size / 2",
            )
        _require(
            self.predator.v_max > self.prey.v_max,
            "K4 violated: predator.v_max must be > prey.v_max",
        )
        _require(
            self.prey.omega_max > self.predator.omega_max,
            "K4 violated: prey.omega_max must be > predator.omega_max",
        )

    @property
    def safe_distance(self) -> float:
        """Minimum initial predator-prey distance, d_safe = prey vision radius (ADR-010)."""
        return self.prey.vision_radius


@dataclass(frozen=True)
class ConstraintCheck:
    """Outcome of one calibration constraint (ADR-030)."""

    constraint_id: str
    satisfied: bool
    value: float
    target: str


E1_BOUNDS = (0.4, 0.6)
E5_MAX_FRACTION = 0.5


def calibration_checks(params: WorldParams) -> tuple[ConstraintCheck, ...]:
    """Evaluate E1, E2 and E5 without rejecting the configuration (ADR-022, ADR-030)."""
    low, high = E1_BOUNDS
    checks: list[ConstraintCheck] = []
    for label, species in (("prey", params.prey), ("predator", params.predator)):
        starvation_fraction = species.initial_energy / species.c_basal / params.t_max
        checks.append(
            ConstraintCheck(
                constraint_id=f"E1-{label}",
                satisfied=low <= starvation_fraction <= high,
                value=starvation_fraction,
                target=f"E0 / c_basal / t_max in [{low}, {high}]",
            )
        )
        checks.append(
            ConstraintCheck(
                constraint_id=f"E2-{label}",
                satisfied=species.c_move >= species.c_basal,
                value=species.c_move / species.c_basal,
                target="c_move / c_basal >= 1",
            )
        )
    plant_fraction = params.plant_energy / params.prey.e_max
    checks.append(
        ConstraintCheck(
            constraint_id="E5",
            satisfied=plant_fraction <= E5_MAX_FRACTION,
            value=plant_fraction,
            target=f"plant_energy / prey.e_max <= {E5_MAX_FRACTION}",
        )
    )
    return tuple(checks)
