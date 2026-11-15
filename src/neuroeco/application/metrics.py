"""Episode metrics (ADR-014) and the quantities required by the P1 indicators (ADR-020).

Primary metrics are kept as exact integer ratios with a common denominator (ADR-017), so that
aggregation over episodes and the detection of zeros and ties are exact:

- prey survival     = sum_i t_i / (n_prey * t_max), with t_i = death step or t_max
- captured fraction = captures / n_prey

Time-to-capture is described with the empirical cumulative incidence of capture and of
starvation (competing risks). Test episodes have no censoring before t_max, so the empirical
proportions are the Aalen-Johansen estimates.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from neuroeco.domain.records import EpisodeRecord, SpeciesOutcome
from neuroeco.domain.state import NOT_DEAD, DeathCause

EARLY_CAPTURE_FRACTION_OF_T_MAX = 0.05  # ADR-020, alert C2


@dataclass(frozen=True)
class Ratio:
    """Exact ratio of non-negative integers."""

    numerator: int
    denominator: int

    @property
    def value(self) -> float:
        return self.numerator / self.denominator if self.denominator else math.nan


@dataclass(frozen=True)
class EpisodeMetrics:
    # ---- §6 metrics (ADR-014)
    prey_survival: Ratio
    prey_alive_fraction_end: Ratio
    plants_eaten: int
    plants_eaten_per_prey: float
    captures: int
    captured_fraction: Ratio
    captures_per_predator: float
    capture_rate_per_exposure: Ratio  # captures / prey-steps alive
    prey_final_energy_survivors: float  # nan when no survivor
    prey_final_energy_population: float  # dead count as 0
    predator_final_energy_survivors: float
    predator_final_energy_population: float
    capture_incidence_end: float  # CIF_capture(t_max)
    starvation_incidence_end: float  # CIF_starvation(t_max)
    median_capture_step_among_captured: float  # conditional; nan when no capture
    # ---- P1 indicators (ADR-020)
    steps: int
    prey_deaths_captured_share: float  # among dead prey; nan when none died
    prey_deaths_starved_share: float
    early_capture_share: float  # captures before 5 % of t_max; nan when no capture
    prey_net_energy_rate: float  # (gained - spent) / prey-steps alive
    predator_survival: Ratio  # sum of predator survival steps / (n_predators * t_max)
    predators_alive_end: int


def survival_steps(outcome: SpeciesOutcome, t_max: int) -> np.ndarray:
    """t_i: death step for dead agents, t_max for survivors."""
    return np.where(outcome.death_step == NOT_DEAD, t_max, outcome.death_step)


def prey_alive_at_start(record: EpisodeRecord) -> np.ndarray:
    """Living prey at the start (observation) of each executed step."""
    n_prey = record.prey.death_step.shape[0]
    return np.concatenate(([n_prey], record.prey_alive_after[:-1])).astype(np.int64)


def cumulative_incidence(record: EpisodeRecord) -> tuple[np.ndarray, np.ndarray]:
    """CIF of capture and of starvation at the end of each step 0..t_max-1.

    After an early termination no further events occur, so the curves stay constant.
    """
    n_prey = record.prey.death_step.shape[0]
    pad = record.t_max - record.steps

    def extend(counts: np.ndarray) -> np.ndarray:
        last = counts[-1] if counts.size else 0
        return np.concatenate((counts, np.full(pad, last))) / n_prey

    return extend(record.prey_captured_after), extend(record.prey_starved_after)


def _mean_or_nan(values: np.ndarray) -> float:
    return float(values.mean()) if values.size else math.nan


def _share(part: int, whole: int) -> float:
    return part / whole if whole else math.nan


def episode_metrics(record: EpisodeRecord) -> EpisodeMetrics:
    t_max = record.t_max
    prey, predators = record.prey, record.predators
    n_prey, n_predators = prey.death_step.shape[0], predators.death_step.shape[0]

    prey_survivors = prey.death_step == NOT_DEAD
    predator_survivors = predators.death_step == NOT_DEAD
    captured = int((prey.death_cause == DeathCause.CAPTURED).sum())
    starved = int((prey.death_cause == DeathCause.STARVATION).sum())
    captures = int(record.capture_step.size)
    exposure = int(prey_alive_at_start(record).sum())
    capture_cif, starvation_cif = cumulative_incidence(record)
    early_limit = EARLY_CAPTURE_FRACTION_OF_T_MAX * t_max

    return EpisodeMetrics(
        prey_survival=Ratio(int(survival_steps(prey, t_max).sum()), n_prey * t_max),
        prey_alive_fraction_end=Ratio(int(prey_survivors.sum()), n_prey),
        plants_eaten=int(prey.events.sum()),
        plants_eaten_per_prey=float(prey.events.sum()) / n_prey,
        captures=captures,
        captured_fraction=Ratio(captures, n_prey),
        captures_per_predator=captures / n_predators if n_predators else math.nan,
        capture_rate_per_exposure=Ratio(captures, exposure),
        prey_final_energy_survivors=_mean_or_nan(prey.final_energy[prey_survivors]),
        prey_final_energy_population=float(np.where(prey_survivors, prey.final_energy, 0.0).mean()),
        predator_final_energy_survivors=_mean_or_nan(predators.final_energy[predator_survivors]),
        predator_final_energy_population=(
            float(np.where(predator_survivors, predators.final_energy, 0.0).mean())
            if n_predators
            else math.nan
        ),
        capture_incidence_end=float(capture_cif[-1]),
        starvation_incidence_end=float(starvation_cif[-1]),
        median_capture_step_among_captured=(
            float(np.median(record.capture_step)) if captures else math.nan
        ),
        steps=record.steps,
        prey_deaths_captured_share=_share(captured, captured + starved),
        prey_deaths_starved_share=_share(starved, captured + starved),
        early_capture_share=(
            float((record.capture_step < early_limit).sum()) / captures if captures else math.nan
        ),
        prey_net_energy_rate=(
            float((prey.energy_gained - prey.energy_spent).sum()) / exposure
            if exposure
            else math.nan
        ),
        predator_survival=Ratio(int(survival_steps(predators, t_max).sum()), n_predators * t_max),
        predators_alive_end=int(predator_survivors.sum()),
    )
