"""World state as structure-of-arrays and its deterministic initialization (ADR-010, ADR-028).

Agents are never removed: a dead agent keeps its index and is masked by ``alive``. Stable
indices make tie-breaking and inspection deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum

import numpy as np

from neuroeco.domain.geometry import TWO_PI, pairwise_distances, wrap_positions
from neuroeco.domain.params import SpeciesParams, WorldParams

MAX_PLACEMENT_ATTEMPTS = 10_000
RESPAWN_BLOCK_SIZE = 64
NOT_DEAD = -1
NOT_SCHEDULED = -1


class InitializationError(RuntimeError):
    """Raised when the initial conditions cannot be satisfied (e.g. d_safe placement)."""


class DeathCause(IntEnum):
    ALIVE = 0
    STARVATION = 1
    CAPTURED = 2


@dataclass(frozen=True)
class EpisodeStreams:
    """Independent random streams of one episode (ADR-028).

    The environment streams are separate from the policy streams, so changing a policy never
    changes the environment (DET-5).
    """

    env_init: np.random.Generator
    env_dynamics: np.random.Generator
    policy_prey: np.random.Generator
    policy_predator: np.random.Generator


@dataclass
class SpeciesState:
    """Per-agent arrays of one species."""

    positions: np.ndarray  # (n, 2) float64
    headings: np.ndarray  # (n,) float64 in [0, 2*pi)
    energy: np.ndarray  # (n,) float64
    alive: np.ndarray  # (n,) bool
    death_step: np.ndarray  # (n,) int64, NOT_DEAD while alive
    death_cause: np.ndarray  # (n,) int8, DeathCause

    @classmethod
    def create(
        cls, positions: np.ndarray, headings: np.ndarray, species: SpeciesParams
    ) -> SpeciesState:
        n = positions.shape[0]
        return cls(
            positions=positions.astype(np.float64),
            headings=headings.astype(np.float64),
            energy=np.full(n, species.initial_energy, dtype=np.float64),
            alive=np.ones(n, dtype=bool),
            death_step=np.full(n, NOT_DEAD, dtype=np.int64),
            death_cause=np.full(n, DeathCause.ALIVE, dtype=np.int8),
        )

    @property
    def size(self) -> int:
        return int(self.alive.shape[0])


@dataclass
class PlantState:
    """Plant slots: position, availability and scheduled reactivation step."""

    positions: np.ndarray  # (m, 2) float64
    active: np.ndarray  # (m,) bool
    regrow_at: np.ndarray  # (m,) int64, NOT_SCHEDULED while active


class PlantRespawnQueue:
    """Deterministic sequence of respawn positions drawn from ENV_DYNAMICS (ADR-010).

    The k-th respawn always receives the k-th position of the sequence, regardless of when it
    happens and of the internal block size.
    """

    def __init__(
        self, generator: np.random.Generator, size: float, block_size: int = RESPAWN_BLOCK_SIZE
    ) -> None:
        if block_size < 1:
            raise ValueError("block_size must be >= 1")
        self._generator = generator
        self._size = size
        self._block_size = block_size
        self._buffer = np.empty((0, 2), dtype=np.float64)
        self._cursor = 0
        self.consumed = 0

    def next_position(self) -> np.ndarray:
        if self._cursor >= self._buffer.shape[0]:
            block = self._generator.uniform(0.0, self._size, size=(self._block_size, 2))
            self._buffer = wrap_positions(block, self._size)
            self._cursor = 0
        position = self._buffer[self._cursor].copy()
        self._cursor += 1
        self.consumed += 1
        return position


@dataclass
class WorldState:
    """Complete mutable state of an episode at step ``step``."""

    step: int
    prey: SpeciesState
    predators: SpeciesState
    plants: PlantState
    respawn_queue: PlantRespawnQueue = field(repr=False)


def _uniform_positions(generator: np.random.Generator, n: int, size: float) -> np.ndarray:
    return wrap_positions(generator.uniform(0.0, size, size=(n, 2)), size)


def _place_predators(
    generator: np.random.Generator, prey_positions: np.ndarray, params: WorldParams
) -> np.ndarray:
    """Rejection sampling: every predator starts at distance >= d_safe from every prey."""
    placed = np.empty((params.n_predators, 2), dtype=np.float64)
    for index in range(params.n_predators):
        for _ in range(MAX_PLACEMENT_ATTEMPTS):
            candidate = _uniform_positions(generator, 1, params.size)
            distances = pairwise_distances(candidate, prey_positions, params.size)
            if distances.size == 0 or distances.min() >= params.safe_distance:
                placed[index] = candidate[0]
                break
        else:
            raise InitializationError(
                f"could not place predator {index} at distance >= {params.safe_distance} "
                f"from all prey after {MAX_PLACEMENT_ATTEMPTS} attempts; "
                "reduce n_prey or the prey vision radius, or enlarge the world"
            )
    return placed


def initialize_world(params: WorldParams, streams: EpisodeStreams) -> WorldState:
    """Initial state, drawn in a fixed order from ENV_INIT (prey, plants, predators)."""
    rng = streams.env_init
    prey_positions = _uniform_positions(rng, params.n_prey, params.size)
    prey_headings = rng.uniform(0.0, TWO_PI, size=params.n_prey)
    plant_positions = _uniform_positions(rng, params.n_plants, params.size)
    predator_positions = _place_predators(rng, prey_positions, params)
    predator_headings = rng.uniform(0.0, TWO_PI, size=params.n_predators)

    return WorldState(
        step=0,
        prey=SpeciesState.create(prey_positions, prey_headings % TWO_PI, params.prey),
        predators=SpeciesState.create(
            predator_positions, predator_headings % TWO_PI, params.predator
        ),
        plants=PlantState(
            positions=plant_positions,
            active=np.ones(params.n_plants, dtype=bool),
            regrow_at=np.full(params.n_plants, NOT_SCHEDULED, dtype=np.int64),
        ),
        respawn_queue=PlantRespawnQueue(streams.env_dynamics, params.size),
    )
