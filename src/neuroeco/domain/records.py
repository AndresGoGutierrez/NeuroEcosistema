"""Episode records (ADR-014, ADR-020; scope decision A6).

The record holds what the §6 metrics and the P1 indicators need: deaths and their causes,
capture and feeding events, per-step population counts and energy flows. Diagnostics added in
later phases (X2) will extend it with new fields without changing existing ones.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SpeciesOutcome:
    """Per-agent outcome of one species.

    ``events`` counts plants eaten (prey) or captures made (predators).
    ``death_step`` is -1 for survivors; ``death_cause`` follows ``state.DeathCause``.
    """

    death_step: np.ndarray  # (n,) int64
    death_cause: np.ndarray  # (n,) int8
    final_energy: np.ndarray  # (n,) float64; last value before death for dead agents
    energy_gained: np.ndarray  # (n,) float64, after the E_max cap
    energy_spent: np.ndarray  # (n,) float64
    events: np.ndarray  # (n,) int64


@dataclass(frozen=True)
class EpisodeRecord:
    """Everything an episode produces that later analyses need."""

    t_max: int
    steps: int  # number of steps executed (<= t_max)
    prey: SpeciesOutcome
    predators: SpeciesOutcome
    capture_step: np.ndarray  # (k,) int64, in occurrence order
    capture_predator: np.ndarray  # (k,) int64
    capture_prey: np.ndarray  # (k,) int64
    feeding_step: np.ndarray  # (f,) int64
    feeding_prey: np.ndarray  # (f,) int64
    feeding_plant: np.ndarray  # (f,) int64
    prey_alive_after: np.ndarray  # (steps,) int64, after each step
    prey_captured_after: np.ndarray  # (steps,) int64, cumulative
    prey_starved_after: np.ndarray  # (steps,) int64, cumulative
    predators_alive_after: np.ndarray  # (steps,) int64
    plants_active_after: np.ndarray  # (steps,) int64
