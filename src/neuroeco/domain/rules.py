"""Per-species rules of a simulation step (ADR-008, ADR-010).

Phases implemented here: movement (3), metabolism (4), starvation (5) and termination (9).
Every function acts only on living agents; dead agents keep their last values.

Step semantics: steps are indexed t = 0 .. t_max - 1. An agent that dies while processing
step t gets ``death_step = t``. After step t is processed the state's ``step`` becomes t + 1.
"""

from __future__ import annotations

import numpy as np

from neuroeco.domain.geometry import wrap_headings, wrap_positions
from neuroeco.domain.params import SpeciesParams
from neuroeco.domain.state import DeathCause, SpeciesState


def apply_movement(
    species: SpeciesState, turns: np.ndarray, speeds: np.ndarray, size: float
) -> None:
    """Phase 3: turn first, then advance along the new heading, on the torus."""
    alive = species.alive
    species.headings[alive] = wrap_headings(species.headings[alive] + turns[alive])
    heading = species.headings[alive]
    step = np.stack((np.cos(heading), np.sin(heading)), axis=1) * speeds[alive, np.newaxis]
    species.positions[alive] = wrap_positions(species.positions[alive] + step, size)


def metabolic_cost(speeds: np.ndarray, params: SpeciesParams) -> np.ndarray:
    """c_basal + c_move * (v / v_max)^2 (ADR-010)."""
    return params.c_basal + params.c_move * (speeds / params.v_max) ** 2


def apply_metabolism(
    species: SpeciesState, speeds: np.ndarray, params: SpeciesParams
) -> np.ndarray:
    """Phase 4: subtract the step cost from living agents; return energy spent per agent."""
    spent = np.zeros(species.size, dtype=np.float64)
    alive = species.alive
    spent[alive] = metabolic_cost(speeds[alive], params)
    species.energy[alive] -= spent[alive]
    return spent


def apply_starvation(species: SpeciesState, step: int) -> np.ndarray:
    """Phase 5: agents with energy <= 0 die of starvation; return their indices."""
    starving = np.flatnonzero(species.alive & (species.energy <= 0.0))
    species.alive[starving] = False
    species.death_step[starving] = step
    species.death_cause[starving] = DeathCause.STARVATION
    return starving


def is_terminal(next_step: int, t_max: int, prey_alive: int) -> bool:
    """Phase 9: the episode ends at t_max or when no prey is alive (ADR-008)."""
    return next_step >= t_max or prey_alive == 0
