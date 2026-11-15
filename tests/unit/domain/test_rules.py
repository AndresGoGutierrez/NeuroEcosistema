"""T5: movement, metabolism, starvation and termination (ADR-008, ADR-010)."""

import numpy as np
import pytest

from neuroeco.domain.rules import (
    apply_metabolism,
    apply_movement,
    apply_starvation,
    is_terminal,
    metabolic_cost,
)
from neuroeco.domain.state import NOT_DEAD, DeathCause, SpeciesState
from support import PROVISIONAL_PREY

SIZE = 150.0


def make_species(positions, headings, energy=80.0) -> SpeciesState:
    species = SpeciesState.create(
        np.array(positions, dtype=float), np.array(headings, dtype=float), PROVISIONAL_PREY
    )
    species.energy[:] = energy
    return species


def test_movement_turns_first_then_advances() -> None:
    species = make_species([[10.0, 10.0]], [0.0])
    apply_movement(species, np.array([np.pi / 2]), np.array([1.0]), SIZE)
    np.testing.assert_allclose(species.headings, [np.pi / 2])
    np.testing.assert_allclose(species.positions, [[10.0, 11.0]], atol=1e-12)


def test_movement_wraps_position_and_heading() -> None:
    species = make_species([[149.5, 0.2]], [6.2])
    apply_movement(species, np.array([0.2]), np.array([1.0]), SIZE)  # 6.4 > 2*pi
    assert 0.0 <= species.headings[0] < 2 * np.pi
    np.testing.assert_allclose(species.headings[0], 6.4 - 2 * np.pi)
    assert np.all((species.positions >= 0) & (species.positions < SIZE))
    np.testing.assert_allclose(species.positions[0, 0], (149.5 + np.cos(6.4)) % SIZE)


def test_dead_agents_do_not_move() -> None:
    species = make_species([[5.0, 5.0], [7.0, 7.0]], [0.0, 0.0])
    species.alive[1] = False
    apply_movement(species, np.array([1.0, 1.0]), np.array([1.0, 1.0]), SIZE)
    np.testing.assert_array_equal(species.positions[1], [7.0, 7.0])
    assert species.headings[1] == 0.0


def test_metabolic_cost_formula() -> None:
    # c_basal 0.16 + c_move 0.32 * (v / v_max)^2 with v_max = 1
    np.testing.assert_allclose(
        metabolic_cost(np.array([0.0, 0.5, 1.0]), PROVISIONAL_PREY), [0.16, 0.24, 0.48]
    )


def test_metabolism_only_charges_living_agents() -> None:
    species = make_species([[0, 0], [1, 1]], [0, 0], energy=10.0)
    species.alive[1] = False
    spent = apply_metabolism(species, np.array([1.0, 1.0]), PROVISIONAL_PREY)
    np.testing.assert_allclose(spent, [0.48, 0.0])
    np.testing.assert_allclose(species.energy, [9.52, 10.0])


def test_starvation_kills_non_positive_energy() -> None:
    species = make_species([[0, 0], [1, 1], [2, 2]], [0, 0, 0])
    species.energy[:] = [0.0, -0.1, 0.01]
    dead = apply_starvation(species, step=17)
    np.testing.assert_array_equal(dead, [0, 1])
    np.testing.assert_array_equal(species.alive, [False, False, True])
    np.testing.assert_array_equal(species.death_step, [17, 17, NOT_DEAD])
    assert list(species.death_cause) == [DeathCause.STARVATION, DeathCause.STARVATION, 0]
    assert np.all(species.energy[species.alive] > 0)


def test_starvation_ignores_already_dead_agents() -> None:
    species = make_species([[0, 0]], [0])
    species.alive[0] = False
    species.death_step[0] = 3
    species.death_cause[0] = DeathCause.CAPTURED
    species.energy[0] = -5.0
    assert apply_starvation(species, step=9).size == 0
    assert species.death_step[0] == 3 and species.death_cause[0] == DeathCause.CAPTURED


@pytest.mark.parametrize(
    ("next_step", "prey_alive", "expected"),
    [(999, 5, False), (1000, 5, True), (10, 0, True), (1001, 1, True)],
)
def test_termination(next_step, prey_alive, expected) -> None:
    assert is_terminal(next_step, 1000, prey_alive) is expected
