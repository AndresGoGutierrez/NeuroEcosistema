"""T4: deterministic initialization and plant respawn queue (ADR-010, ADR-028)."""

from dataclasses import replace

import numpy as np
import pytest

from neuroeco.application.seeding import Purpose, SeedRegistry
from neuroeco.domain.geometry import TWO_PI, pairwise_distances
from neuroeco.domain.state import (
    NOT_DEAD,
    NOT_SCHEDULED,
    DeathCause,
    InitializationError,
    PlantRespawnQueue,
    initialize_world,
)
from support import PROVISIONAL_PREY

SEED = 151810796106167051982782525292607188790


def streams(item: int = 0):
    return SeedRegistry(SEED).episode_streams(Purpose.TEST, 0, 0, 0, item)


def test_initial_state_shapes_and_values(world_params) -> None:
    params = world_params()
    state = initialize_world(params, streams())
    assert state.step == 0
    assert state.prey.positions.shape == (25, 2)
    assert state.predators.positions.shape == (3, 2)
    assert state.plants.positions.shape == (40, 2)
    for species, spec in ((state.prey, params.prey), (state.predators, params.predator)):
        assert species.positions.dtype == np.float64
        assert np.all((species.positions >= 0) & (species.positions < params.size))
        assert np.all((species.headings >= 0) & (species.headings < TWO_PI))
        np.testing.assert_array_equal(species.energy, spec.initial_energy)
        assert species.alive.all()
        assert np.all(species.death_step == NOT_DEAD)
        assert np.all(species.death_cause == DeathCause.ALIVE)
    assert state.plants.active.all()
    assert np.all(state.plants.regrow_at == NOT_SCHEDULED)


@pytest.mark.parametrize("item", range(5))
def test_predators_start_at_safe_distance(world_params, item) -> None:
    params = world_params(n_prey=50, n_predators=8)  # P0 reference configuration
    state = initialize_world(params, streams(item))
    distances = pairwise_distances(state.predators.positions, state.prey.positions, params.size)
    assert distances.min() >= params.safe_distance


def test_impossible_placement_raises(world_params) -> None:
    crowded = world_params(n_prey=400, prey=replace(PROVISIONAL_PREY, vision_radius=70.0))
    with pytest.raises(InitializationError, match="could not place predator"):
        initialize_world(crowded, streams())


def test_world_without_predators(world_params) -> None:
    state = initialize_world(world_params(n_predators=0), streams())
    assert state.predators.positions.shape == (0, 2)
    assert state.predators.alive.shape == (0,)


def test_initialization_is_deterministic(world_params) -> None:
    params = world_params()
    a = initialize_world(params, streams(3))
    b = initialize_world(params, streams(3))
    c = initialize_world(params, streams(4))
    for field in ("positions", "headings"):
        np.testing.assert_array_equal(getattr(a.prey, field), getattr(b.prey, field))
        np.testing.assert_array_equal(getattr(a.predators, field), getattr(b.predators, field))
    np.testing.assert_array_equal(a.plants.positions, b.plants.positions)
    assert not np.array_equal(a.prey.positions, c.prey.positions)


def test_episode_streams_are_independent() -> None:
    s = streams()
    first = [
        g.integers(0, 2**63) for g in (s.env_init, s.env_dynamics, s.policy_prey, s.policy_predator)
    ]
    assert len(set(first)) == 4


@pytest.mark.parametrize("block_size", [1, 7, 64])
def test_respawn_position_does_not_depend_on_block_size(block_size) -> None:
    reference = PlantRespawnQueue(np.random.default_rng(11), 150.0, block_size=100)
    other = PlantRespawnQueue(np.random.default_rng(11), 150.0, block_size=block_size)
    expected = np.array([reference.next_position() for _ in range(100)])
    actual = np.array([other.next_position() for _ in range(100)])
    np.testing.assert_array_equal(actual, expected)
    assert other.consumed == 100
    assert np.all((actual >= 0) & (actual < 150.0))


def test_respawn_queue_rejects_invalid_block_size() -> None:
    with pytest.raises(ValueError):
        PlantRespawnQueue(np.random.default_rng(0), 150.0, block_size=0)
