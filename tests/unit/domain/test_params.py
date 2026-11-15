"""T1: parameter invariants (K1-K4) and calibration checks (E1, E2, E5)."""

import math
from dataclasses import FrozenInstanceError, replace

import pytest

from neuroeco.domain.params import ConfigurationError, calibration_checks
from support import PROVISIONAL_PREDATOR, PROVISIONAL_PREY, PROVISIONAL_WORLD


def test_provisional_parameters_are_valid(world_params) -> None:
    params = world_params()
    assert params.safe_distance == params.prey.vision_radius
    assert params.prey.initial_energy == pytest.approx(80.0)


def test_parameters_are_immutable() -> None:
    with pytest.raises(FrozenInstanceError):
        PROVISIONAL_WORLD.size = 10.0  # type: ignore[misc]


def test_k1_capture_radius_below_relative_speed_is_rejected(world_params) -> None:
    # The boundary is computed with the same float expression as the invariant, so the test
    # does not depend on how the literal 2.3 rounds in binary.
    boundary = PROVISIONAL_PREDATOR.v_max + PROVISIONAL_PREY.v_max
    world_params(capture_radius=boundary)
    with pytest.raises(ConfigurationError, match="K1"):
        world_params(capture_radius=boundary - 0.01)


def test_k2_eat_radius_below_prey_speed_is_rejected(world_params) -> None:
    world_params(eat_radius=1.0)
    with pytest.raises(ConfigurationError, match="K2"):
        world_params(eat_radius=0.99)


@pytest.mark.parametrize("species", ["prey", "predator"])
def test_k3_vision_radius_must_be_below_half_the_world(world_params, species) -> None:
    base = PROVISIONAL_PREY if species == "prey" else PROVISIONAL_PREDATOR
    with pytest.raises(ConfigurationError, match="K3"):
        world_params(**{species: replace(base, vision_radius=75.0)})  # size / 2 = 75


def test_k4_predator_must_be_faster(world_params) -> None:
    slow_predator = replace(PROVISIONAL_PREDATOR, v_max=1.0)
    with pytest.raises(ConfigurationError, match="K4"):
        world_params(predator=slow_predator, capture_radius=3.0)


def test_k4_prey_must_be_more_agile(world_params) -> None:
    agile_predator = replace(PROVISIONAL_PREDATOR, omega_max=0.5)
    with pytest.raises(ConfigurationError, match="K4"):
        world_params(predator=agile_predator)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("v_max", 0.0),
        ("omega_max", 0.0),
        ("omega_max", math.pi + 0.01),
        ("vision_radius", -1.0),
        ("e_max", 0.0),
        ("initial_energy_fraction", 0.0),
        ("initial_energy_fraction", 1.01),
        ("c_basal", 0.0),
        ("c_move", -0.1),
        ("v_max", math.nan),
        ("v_max", True),
    ],
)
def test_species_rejects_invalid_values(field, value) -> None:
    with pytest.raises(ConfigurationError):
        replace(PROVISIONAL_PREY, **{field: value})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("size", 0.0),
        ("t_max", 0),
        ("t_max", 10.0),
        ("n_prey", 0),
        ("n_predators", -1),
        ("n_plants", -1),
        ("regrow_delay", 0),
        ("plant_energy", 0.0),
        ("prey_energy", 0.0),
        ("n_prey", True),
    ],
)
def test_world_rejects_invalid_values(world_params, field, value) -> None:
    with pytest.raises(ConfigurationError):
        world_params(**{field: value})


def test_world_without_predators_is_allowed(world_params) -> None:
    # Needed by the P1 no-predator control (ADR-020, B4).
    assert world_params(n_predators=0).n_predators == 0


def test_calibration_checks_pass_for_provisional_values(world_params) -> None:
    checks = {c.constraint_id: c for c in calibration_checks(world_params())}
    assert set(checks) == {"E1-prey", "E1-predator", "E2-prey", "E2-predator", "E5"}
    assert all(c.satisfied for c in checks.values())
    assert checks["E1-prey"].value == pytest.approx(0.5)  # 80 / 0.16 / 1000
    assert checks["E5"].value == pytest.approx(0.3)  # 30 / 100


def test_calibration_checks_report_without_rejecting(world_params) -> None:
    # A tiny-energy world violates E1 but must still be constructible (decision A2).
    weak_prey = replace(PROVISIONAL_PREY, e_max=1.0)
    params = world_params(prey=weak_prey, plant_energy=30.0)
    checks = {c.constraint_id: c for c in calibration_checks(params)}
    assert not checks["E1-prey"].satisfied
    assert not checks["E5"].satisfied
    cheap_moves = replace(PROVISIONAL_PREDATOR, c_move=0.1)
    predator_checks = {
        c.constraint_id: c for c in calibration_checks(world_params(predator=cheap_moves))
    }
    assert not predator_checks["E2-predator"].satisfied
