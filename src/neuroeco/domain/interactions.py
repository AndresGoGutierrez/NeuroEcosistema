"""Interactions of a simulation step: captures (6), feeding (7) and plant regrowth (8).

Conflicts are resolved by a deterministic greedy matching (ADR-009): candidate pairs within
the interaction radius are sorted by (distance, consumer index, resource index) and accepted
when neither member is already matched.

Plant regrowth (ADR-008, ADR-010): a plant eaten at step t gets ``regrow_at = t + regrow_delay``,
is reactivated in phase 8 of step ``regrow_at`` and becomes observable at step
``regrow_at + 1``, so it is missing from exactly ``regrow_delay`` observations. Plants that
reappear in the same step are processed in index order; the k-th respawn receives the k-th
position of the respawn queue.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from neuroeco.domain.geometry import pairwise_distances
from neuroeco.domain.params import WorldParams
from neuroeco.domain.state import NOT_SCHEDULED, DeathCause, WorldState


@dataclass(frozen=True)
class InteractionResult:
    """Matched pairs (in matching order) and the energy actually gained per consumer."""

    consumers: np.ndarray  # (k,) int64
    resources: np.ndarray  # (k,) int64
    energy_gained: np.ndarray  # (n_consumers,) float64, after the E_max cap


def greedy_match(
    distances: np.ndarray,
    radius: float,
    consumer_mask: np.ndarray,
    resource_mask: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Deterministic greedy matching by (distance, consumer index, resource index)."""
    eligible = (distances <= radius) & consumer_mask[:, np.newaxis] & resource_mask[np.newaxis, :]
    consumer_idx, resource_idx = np.nonzero(eligible)
    if consumer_idx.size == 0:
        empty = np.empty(0, dtype=np.int64)
        return empty, empty
    candidate_distances = distances[consumer_idx, resource_idx]
    # np.lexsort sorts by the last key first: distance, then consumer, then resource.
    order = np.lexsort((resource_idx, consumer_idx, candidate_distances))
    consumer_used = np.zeros(distances.shape[0], dtype=bool)
    resource_used = np.zeros(distances.shape[1], dtype=bool)
    matched_consumers: list[int] = []
    matched_resources: list[int] = []
    for position in order:
        consumer = int(consumer_idx[position])
        resource = int(resource_idx[position])
        if consumer_used[consumer] or resource_used[resource]:
            continue
        consumer_used[consumer] = True
        resource_used[resource] = True
        matched_consumers.append(consumer)
        matched_resources.append(resource)
    return (
        np.array(matched_consumers, dtype=np.int64),
        np.array(matched_resources, dtype=np.int64),
    )


def resolve_captures(world: WorldState, params: WorldParams, step: int) -> InteractionResult:
    """Phase 6: each living predator captures at most one living prey within capture_radius."""
    predators, prey = world.predators, world.prey
    distances = pairwise_distances(predators.positions, prey.positions, params.size)
    hunters, victims = greedy_match(distances, params.capture_radius, predators.alive, prey.alive)

    prey.alive[victims] = False
    prey.death_step[victims] = step
    prey.death_cause[victims] = DeathCause.CAPTURED

    gained = np.zeros(predators.size, dtype=np.float64)
    before = predators.energy[hunters].copy()
    predators.energy[hunters] = np.minimum(
        params.predator.e_max, predators.energy[hunters] + params.prey_energy
    )
    gained[hunters] = predators.energy[hunters] - before
    return InteractionResult(hunters, victims, gained)


def resolve_feeding(world: WorldState, params: WorldParams, step: int) -> InteractionResult:
    """Phase 7: each living prey eats at most one active plant within eat_radius."""
    prey, plants = world.prey, world.plants
    distances = pairwise_distances(prey.positions, plants.positions, params.size)
    eaters, eaten = greedy_match(distances, params.eat_radius, prey.alive, plants.active)

    plants.active[eaten] = False
    plants.regrow_at[eaten] = step + params.regrow_delay

    gained = np.zeros(prey.size, dtype=np.float64)
    before = prey.energy[eaters].copy()
    prey.energy[eaters] = np.minimum(params.prey.e_max, prey.energy[eaters] + params.plant_energy)
    gained[eaters] = prey.energy[eaters] - before
    return InteractionResult(eaters, eaten, gained)


def regrow_plants(world: WorldState, step: int) -> np.ndarray:
    """Phase 8: reactivate plants whose timer expires, in index order; return their indices."""
    plants = world.plants
    due = np.flatnonzero(
        ~plants.active & (plants.regrow_at != NOT_SCHEDULED) & (plants.regrow_at <= step)
    )
    for index in due:
        plants.positions[index] = world.respawn_queue.next_position()
    plants.active[due] = True
    plants.regrow_at[due] = NOT_SCHEDULED
    return due
