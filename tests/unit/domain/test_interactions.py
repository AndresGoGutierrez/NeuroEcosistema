"""T6: greedy matching, captures, feeding and regrowth (ADR-008, ADR-009, ADR-010)."""

import numpy as np
import pytest

from neuroeco.domain.interactions import (
    greedy_match,
    regrow_plants,
    resolve_captures,
    resolve_feeding,
)
from neuroeco.domain.state import (
    NOT_DEAD,
    NOT_SCHEDULED,
    DeathCause,
    PlantRespawnQueue,
    PlantState,
    SpeciesState,
    WorldState,
)


def all_true(n: int) -> np.ndarray:
    return np.ones(n, dtype=bool)


def make_world(params, prey_xy, predator_xy=(), plant_xy=(), queue_seed=0) -> WorldState:
    def species(points, spec):
        array = np.array(points, dtype=float).reshape(-1, 2)
        return SpeciesState.create(array, np.zeros(array.shape[0]), spec)

    plants = np.array(plant_xy, dtype=float).reshape(-1, 2)
    return WorldState(
        step=0,
        prey=species(prey_xy, params.prey),
        predators=species(predator_xy, params.predator),
        plants=PlantState(
            positions=plants,
            active=all_true(plants.shape[0]),
            regrow_at=np.full(plants.shape[0], NOT_SCHEDULED, dtype=np.int64),
        ),
        respawn_queue=PlantRespawnQueue(np.random.default_rng(queue_seed), params.size),
    )


# ------------------------------------------------------------------ greedy matching


def test_single_pair_within_radius_is_matched_and_boundary_is_inclusive() -> None:
    consumers, resources = greedy_match(np.array([[2.5]]), 2.5, all_true(1), all_true(1))
    assert consumers.tolist() == [0] and resources.tolist() == [0]
    consumers, _ = greedy_match(np.array([[2.51]]), 2.5, all_true(1), all_true(1))
    assert consumers.size == 0


def test_contested_resource_goes_to_the_nearest_consumer() -> None:
    distances = np.array([[2.0], [1.0]])
    consumers, resources = greedy_match(distances, 3.0, all_true(2), all_true(1))
    assert consumers.tolist() == [1] and resources.tolist() == [0]


def test_distance_ties_are_broken_by_consumer_then_resource_index() -> None:
    distances = np.array([[1.0, 1.0], [1.0, 1.0]])
    consumers, resources = greedy_match(distances, 3.0, all_true(2), all_true(2))
    assert list(zip(consumers.tolist(), resources.tolist(), strict=True)) == [(0, 0), (1, 1)]


def test_each_consumer_and_resource_is_used_at_most_once() -> None:
    # Consumer 0 is closest to resource 1; resource 0 then goes to consumer 1.
    distances = np.array([[1.0, 0.5], [2.0, 0.7]])
    consumers, resources = greedy_match(distances, 3.0, all_true(2), all_true(2))
    assert sorted(zip(consumers.tolist(), resources.tolist(), strict=True)) == [(0, 1), (1, 0)]


def test_masks_exclude_dead_consumers_and_inactive_resources() -> None:
    distances = np.array([[0.1, 0.2], [0.3, 0.4]])
    consumers, resources = greedy_match(
        distances, 3.0, np.array([False, True]), np.array([False, True])
    )
    assert consumers.tolist() == [1] and resources.tolist() == [1]


# ------------------------------------------------------------------ captures


def test_capture_kills_prey_and_feeds_predator(world_params) -> None:
    params = world_params()
    world = make_world(params, prey_xy=[[10, 10], [50, 50]], predator_xy=[[11, 10]])
    world.predators.energy[:] = 30.0
    result = resolve_captures(world, params, step=12)
    assert result.consumers.tolist() == [0] and result.resources.tolist() == [0]
    assert world.prey.alive.tolist() == [False, True]
    assert world.prey.death_step[0] == 12 and world.prey.death_cause[0] == DeathCause.CAPTURED
    assert world.prey.death_step[1] == NOT_DEAD
    assert world.predators.energy[0] == pytest.approx(70.0)  # 30 + 40
    assert result.energy_gained[0] == pytest.approx(40.0)


def test_capture_energy_is_capped_and_excess_lost(world_params) -> None:
    params = world_params()
    world = make_world(params, prey_xy=[[10, 10]], predator_xy=[[11, 10]])
    world.predators.energy[:] = 90.0
    result = resolve_captures(world, params, step=0)
    assert world.predators.energy[0] == pytest.approx(100.0)
    assert result.energy_gained[0] == pytest.approx(10.0)


def test_one_capture_per_predator_per_step(world_params) -> None:
    params = world_params()
    world = make_world(params, prey_xy=[[10, 10], [10.5, 10]], predator_xy=[[10.2, 10]])
    resolve_captures(world, params, step=0)
    assert world.prey.alive.sum() == 1


def test_capture_across_the_torus_boundary(world_params) -> None:
    params = world_params()
    world = make_world(params, prey_xy=[[0.5, 75]], predator_xy=[[149.5, 75]])
    resolve_captures(world, params, step=0)
    assert not world.prey.alive[0]


def test_dead_agents_do_not_interact(world_params) -> None:
    params = world_params()
    world = make_world(params, prey_xy=[[10, 10]], predator_xy=[[11, 10]])
    world.predators.alive[0] = False
    assert resolve_captures(world, params, step=0).consumers.size == 0
    assert world.prey.alive[0]


# ------------------------------------------------------------------ feeding and regrowth


def test_feeding_caps_energy_and_schedules_regrowth(world_params) -> None:
    params = world_params()
    world = make_world(params, prey_xy=[[20, 20], [40, 40]], plant_xy=[[20.5, 20], [41, 40]])
    world.prey.energy[:] = [50.0, 90.0]
    result = resolve_feeding(world, params, step=7)
    np.testing.assert_allclose(world.prey.energy, [80.0, 100.0])
    np.testing.assert_allclose(result.energy_gained, [30.0, 10.0])
    assert not world.plants.active.any()
    np.testing.assert_array_equal(world.plants.regrow_at, [57, 57])  # 7 + 50


def test_captured_prey_cannot_eat(world_params) -> None:
    params = world_params()
    world = make_world(params, prey_xy=[[20, 20]], predator_xy=[[21, 20]], plant_xy=[[20.5, 20]])
    resolve_captures(world, params, step=3)
    result = resolve_feeding(world, params, step=3)
    assert result.consumers.size == 0
    assert world.plants.active[0]


def test_plant_reappears_exactly_at_regrow_step_with_queue_positions(world_params) -> None:
    params = world_params()
    world = make_world(params, prey_xy=[[0, 0]], plant_xy=[[10, 10], [20, 20], [30, 30]])
    world.plants.active[:] = [False, True, False]
    world.plants.regrow_at[:] = [5, NOT_SCHEDULED, 5]
    expected_queue = PlantRespawnQueue(np.random.default_rng(0), params.size)
    expected = [expected_queue.next_position() for _ in range(2)]

    assert regrow_plants(world, step=4).size == 0
    assert regrow_plants(world, step=5).tolist() == [0, 2]
    assert world.plants.active.all()
    np.testing.assert_array_equal(world.plants.positions[0], expected[0])
    np.testing.assert_array_equal(world.plants.positions[2], expected[1])
    np.testing.assert_array_equal(world.plants.positions[1], [20, 20])
    assert np.all(world.plants.regrow_at == NOT_SCHEDULED)
