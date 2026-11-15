"""Egocentric sensors (ADR-007).

Each perceived object is encoded with three continuous values:

- ``proximity`` p = 1 - d / R_v  (0 when not perceived)
- ``left``      p * sin(phi)     (positive: to the left)
- ``forward``   p * cos(phi)     (positive: in front)

The K = 2 nearest objects are listed nearest first; distance ties are broken by the lower
object index. Only living agents and active plants are perceived. Rows of dead observers are
zero. The network input size is derived from the schema, never configured by hand.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from neuroeco.domain.geometry import minimal_displacement, pairwise_distances, relative_bearing
from neuroeco.domain.params import WorldParams
from neuroeco.domain.state import SpeciesState, WorldState

NEAREST_K = 2
VALUES_PER_OBJECT = 3


@dataclass(frozen=True)
class InputSchema:
    """Ordered, versioned names of a species' observation vector."""

    species: str
    version: int
    names: tuple[str, ...]

    @property
    def size(self) -> int:
        return len(self.names)


def _object_names(prefix: str) -> tuple[str, str, str]:
    return (f"{prefix}_proximity", f"{prefix}_left", f"{prefix}_forward")


PREY_SCHEMA = InputSchema(
    species="prey",
    version=1,
    names=(
        *_object_names("plant"),
        *_object_names("predator1"),
        *_object_names("predator2"),
        "energy",
    ),
)

PREDATOR_SCHEMA = InputSchema(
    species="predator",
    version=1,
    names=(*_object_names("prey1"), *_object_names("prey2"), "energy"),
)


def encode_nearest(
    observers: SpeciesState,
    target_positions: np.ndarray,
    target_mask: np.ndarray,
    k: int,
    vision_radius: float,
    size: float,
) -> np.ndarray:
    """Encode the k nearest perceived targets of every observer: (n_observers, 3 * k)."""
    n = observers.size
    encoded = np.zeros((n, VALUES_PER_OBJECT * k), dtype=np.float64)
    if n == 0 or target_positions.shape[0] == 0:
        return encoded

    distances = pairwise_distances(observers.positions, target_positions, size)
    perceivable = target_mask[np.newaxis, :] & (distances <= vision_radius)
    masked = np.where(perceivable, distances, np.inf)
    # Stable sort: equal distances keep index order, so ties go to the lower index.
    order = np.argsort(masked, axis=1, kind="stable")[:, :k]
    nearest = np.take_along_axis(masked, order, axis=1)  # (n, k')
    found = np.isfinite(nearest) & observers.alive[:, np.newaxis]

    displacement = minimal_displacement(observers.positions, target_positions, size)
    selected = np.take_along_axis(displacement, order[:, :, np.newaxis], axis=1)  # (n, k', 2)
    forward_unit, left_unit = relative_bearing(selected, observers.headings)

    proximity = np.where(found, 1.0 - np.where(found, nearest, 0.0) / vision_radius, 0.0)
    columns = order.shape[1]
    encoded[:, 0 : VALUES_PER_OBJECT * columns : VALUES_PER_OBJECT] = proximity
    encoded[:, 1 : VALUES_PER_OBJECT * columns : VALUES_PER_OBJECT] = proximity * left_unit
    encoded[:, 2 : VALUES_PER_OBJECT * columns : VALUES_PER_OBJECT] = proximity * forward_unit
    return encoded


def _energy_column(species: SpeciesState, e_max: float) -> np.ndarray:
    return np.where(species.alive, species.energy / e_max, 0.0)[:, np.newaxis]


def observe_prey(world: WorldState, params: WorldParams) -> np.ndarray:
    """Prey observations, ordered as PREY_SCHEMA: (n_prey, 10)."""
    prey = world.prey
    plant = encode_nearest(
        prey, world.plants.positions, world.plants.active, 1, params.prey.vision_radius, params.size
    )
    predators = encode_nearest(
        prey,
        world.predators.positions,
        world.predators.alive,
        NEAREST_K,
        params.prey.vision_radius,
        params.size,
    )
    return np.hstack((plant, predators, _energy_column(prey, params.prey.e_max)))


def observe_predators(world: WorldState, params: WorldParams) -> np.ndarray:
    """Predator observations, ordered as PREDATOR_SCHEMA: (n_predators, 7)."""
    predators = world.predators
    prey = encode_nearest(
        predators,
        world.prey.positions,
        world.prey.alive,
        NEAREST_K,
        params.predator.vision_radius,
        params.size,
    )
    return np.hstack((prey, _energy_column(predators, params.predator.e_max)))
