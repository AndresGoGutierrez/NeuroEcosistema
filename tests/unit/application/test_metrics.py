"""T10: metrics on synthetic records (ADR-014, ADR-020)."""

import math

import numpy as np
import pytest

from neuroeco.application.evaluation import EpisodeIdentity, run_episode
from neuroeco.application.metrics import (
    cumulative_incidence,
    episode_metrics,
    prey_alive_at_start,
)
from neuroeco.application.seeding import Purpose, SeedRegistry
from neuroeco.domain.policies import RuleBasedPredatorPolicy, RuleBasedPreyPolicy
from neuroeco.domain.records import EpisodeRecord, SpeciesOutcome
from neuroeco.domain.state import DeathCause

A, S, C = DeathCause.ALIVE, DeathCause.STARVATION, DeathCause.CAPTURED


def ints(values) -> np.ndarray:
    return np.array(values, dtype=np.int64)


def synthetic_record(steps: int = 10, t_max: int = 10) -> EpisodeRecord:
    """4 prey (captured at 3 and 7, starved at 5, one survivor), 1 predator, t_max = 10."""
    alive = [4, 4, 4, 3, 3, 2, 2, 1, 1, 1][:steps]
    captured = [0, 0, 0, 1, 1, 1, 1, 2, 2, 2][:steps]
    starved = [0, 0, 0, 0, 0, 1, 1, 1, 1, 1][:steps]
    return EpisodeRecord(
        t_max=t_max,
        steps=steps,
        prey=SpeciesOutcome(
            death_step=ints([3, 5, -1, 7]),
            death_cause=np.array([C, S, A, C], dtype=np.int8),
            final_energy=np.array([10.0, 0.05, 60.0, 20.0]),
            energy_gained=np.array([0.0, 0.0, 60.0, 0.0]),
            energy_spent=np.array([0.5, 1.0, 2.0, 1.0]),
            events=ints([0, 0, 2, 0]),
        ),
        predators=SpeciesOutcome(
            death_step=ints([-1]),
            death_cause=np.array([A], dtype=np.int8),
            final_energy=np.array([50.0]),
            energy_gained=np.array([80.0]),
            energy_spent=np.array([3.0]),
            events=ints([2]),
        ),
        capture_step=ints([3, 7]),
        capture_predator=ints([0, 0]),
        capture_prey=ints([0, 3]),
        feeding_step=ints([1, 6]),
        feeding_prey=ints([2, 2]),
        feeding_plant=ints([0, 1]),
        prey_alive_after=ints(alive),
        prey_captured_after=ints(captured),
        prey_starved_after=ints(starved),
        predators_alive_after=ints([1] * steps),
        plants_active_after=ints([5] * steps),
    )


def test_section_6_metrics() -> None:
    m = episode_metrics(synthetic_record())
    assert (m.prey_survival.numerator, m.prey_survival.denominator) == (25, 40)  # 3+5+10+7
    assert m.prey_survival.value == pytest.approx(0.625)
    assert m.prey_alive_fraction_end.value == pytest.approx(0.25)
    assert m.plants_eaten == 2 and m.plants_eaten_per_prey == pytest.approx(0.5)
    assert m.captures == 2 and m.captured_fraction.value == pytest.approx(0.5)
    assert m.captures_per_predator == pytest.approx(2.0)
    assert m.capture_rate_per_exposure.numerator == 2
    assert m.capture_rate_per_exposure.denominator == 28  # 4+4+4+4+3+3+2+2+1+1
    assert m.prey_final_energy_survivors == pytest.approx(60.0)
    assert m.prey_final_energy_population == pytest.approx(15.0)
    assert m.predator_final_energy_survivors == pytest.approx(50.0)
    assert m.capture_incidence_end == pytest.approx(0.5)
    assert m.starvation_incidence_end == pytest.approx(0.25)
    assert m.median_capture_step_among_captured == pytest.approx(5.0)


def test_p1_indicators() -> None:
    m = episode_metrics(synthetic_record())
    assert m.steps == 10
    assert m.prey_deaths_captured_share == pytest.approx(2 / 3)
    assert m.prey_deaths_starved_share == pytest.approx(1 / 3)
    assert m.early_capture_share == pytest.approx(0.0)  # threshold 0.5 steps
    assert m.prey_net_energy_rate == pytest.approx((60.0 - 4.5) / 28)
    assert m.predator_survival.value == pytest.approx(1.0)
    assert m.predators_alive_end == 1


def test_cumulative_incidence_and_identity() -> None:
    record = synthetic_record()
    capture, starvation = cumulative_incidence(record)
    alive = record.prey_alive_after / 4
    np.testing.assert_allclose(capture + starvation + alive, 1.0)
    assert np.all(np.diff(capture) >= 0) and np.all(np.diff(starvation) >= 0)


def test_cumulative_incidence_is_extended_after_early_termination() -> None:
    record = synthetic_record(steps=8, t_max=10)
    capture, starvation = cumulative_incidence(record)
    assert capture.shape == starvation.shape == (10,)
    assert capture[-1] == capture[7] and starvation[-1] == starvation[7]


def test_alive_at_start_shifts_alive_after() -> None:
    np.testing.assert_array_equal(prey_alive_at_start(synthetic_record())[:5], [4, 4, 4, 4, 3])


def test_undefined_quantities_are_nan_not_zero() -> None:
    record = synthetic_record()
    no_events = EpisodeRecord(
        **{
            **record.__dict__,
            "capture_step": ints([]),
            "capture_predator": ints([]),
            "capture_prey": ints([]),
        }
    )
    m = episode_metrics(no_events)
    assert m.captures == 0 and m.captured_fraction.value == 0.0
    assert math.isnan(m.median_capture_step_among_captured)
    assert math.isnan(m.early_capture_share)


def test_run_episode_use_case_is_reproducible(world_params) -> None:
    params = world_params(t_max=200)
    prey = RuleBasedPreyPolicy(params.prey.omega_max, 0.3, 0.5)
    predator = RuleBasedPredatorPolicy(params.predator.omega_max, 0.5)
    registry = SeedRegistry(987654321)
    identity = EpisodeIdentity(Purpose.PILOT, seed_group=1, item=4)
    first = run_episode(params, prey, predator, registry, identity)
    second = run_episode(params, prey, predator, registry, identity)
    # repr equality treats NaN fields (e.g. no captures) as equal; == would not.
    assert repr(first.metrics) == repr(second.metrics)
    assert first.identity == identity
