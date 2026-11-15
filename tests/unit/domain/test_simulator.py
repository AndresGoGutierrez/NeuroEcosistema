"""T9: phase order, episode loop and records (ADR-003, ADR-008, ADR-014)."""

import itertools
from dataclasses import replace

import numpy as np
import pytest

from neuroeco.application.seeding import Purpose, SeedRegistry
from neuroeco.domain.policies import (
    PROBE_NAMES,
    RandomPolicy,
    RuleBasedPredatorPolicy,
    RuleBasedPreyPolicy,
    make_probe,
)
from neuroeco.domain.simulator import PhaseTimer, simulate_episode, step_world
from neuroeco.domain.state import (
    NOT_DEAD,
    NOT_SCHEDULED,
    DeathCause,
    PlantRespawnQueue,
    PlantState,
    SpeciesState,
    WorldState,
)
from support import PROVISIONAL_PREY

STILL = make_probe("STILL", 0.5)
SEED = 151810796106167051982782525292607188790


def streams(item: int = 0):
    return SeedRegistry(SEED).episode_streams(Purpose.TEST, 0, 0, 0, item)


def hand_world(params, prey_xy, predator_xy, plant_xy) -> WorldState:
    def species(points, spec):
        array = np.array(points, dtype=float).reshape(-1, 2)
        return SpeciesState.create(array, np.zeros(array.shape[0]), spec)

    plants = np.array(plant_xy, dtype=float).reshape(-1, 2)
    return WorldState(
        step=0,
        prey=species(prey_xy, params.prey),
        predators=species(predator_xy, params.predator),
        plants=PlantState(
            plants, np.ones(len(plants), bool), np.full(len(plants), NOT_SCHEDULED, np.int64)
        ),
        respawn_queue=PlantRespawnQueue(np.random.default_rng(0), params.size),
    )


def prey_rules(params):
    return RuleBasedPreyPolicy(params.prey.omega_max, flee_threshold=0.3, cruise_fraction=0.5)


def predator_rules(params):
    return RuleBasedPredatorPolicy(params.predator.omega_max, cruise_fraction=0.5)


# ------------------------------------------------------------------ phase order


def test_starving_prey_next_to_a_plant_dies_and_does_not_eat(world_params) -> None:
    params = world_params()
    world = hand_world(params, prey_xy=[[10, 10]], predator_xy=[], plant_xy=[[10.5, 10]])
    world.prey.energy[:] = 0.1  # basal cost 0.16 > 0.1
    trace = step_world(world, params, STILL, STILL, streams())
    assert world.prey.death_cause[0] == DeathCause.STARVATION
    assert trace.feeding.consumers.size == 0 and world.plants.active[0]


def test_captured_prey_does_not_eat(world_params) -> None:
    params = world_params()
    world = hand_world(params, prey_xy=[[10, 10]], predator_xy=[[11, 10]], plant_xy=[[10.5, 10]])
    step_world(world, params, STILL, STILL, streams())
    assert world.prey.death_cause[0] == DeathCause.CAPTURED
    assert world.plants.active[0]


def test_starving_predator_cannot_capture(world_params) -> None:
    params = world_params()
    world = hand_world(params, prey_xy=[[10, 10]], predator_xy=[[11, 10]], plant_xy=[])
    world.predators.energy[:] = 0.1
    step_world(world, params, STILL, STILL, streams())
    assert world.predators.death_cause[0] == DeathCause.STARVATION
    assert world.prey.alive[0]


def test_step_counter_and_trace(world_params) -> None:
    params = world_params()
    world = hand_world(params, prey_xy=[[10, 10]], predator_xy=[[90, 90]], plant_xy=[[50, 50]])
    trace = step_world(world, params, STILL, STILL, streams())
    assert trace.step == 0 and world.step == 1
    assert trace.prey_observations.shape == (1, 10)
    assert trace.predator_actions.shape == (1, 2)


# ------------------------------------------------------------------ episodes

SCENARIOS = {"A": {}, "B": {"n_plants": 15}, "C": {"n_predators": 8}}


def policy_pairs(params):
    yield "rules", prey_rules(params), predator_rules(params)
    yield "random", RandomPolicy(), RandomPolicy()
    for name in PROBE_NAMES:
        yield name.lower(), make_probe(name, 0.5), make_probe(name, 0.5)


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_every_policy_runs_in_every_scenario_and_counts_are_consistent(
    world_params, scenario
) -> None:
    params = world_params(t_max=150, **SCENARIOS[scenario])
    for label, prey_policy, predator_policy in policy_pairs(params):
        record = simulate_episode(params, prey_policy, predator_policy, streams())
        total = record.prey_alive_after + record.prey_captured_after + record.prey_starved_after
        assert np.all(total == params.n_prey), label
        assert record.steps == len(record.prey_alive_after)
        assert record.steps == params.t_max or record.prey_alive_after[-1] == 0, label
        assert record.capture_prey.size == record.prey_captured_after[-1], label
        assert record.prey.events.sum() == record.feeding_step.size, label
        assert record.predators.events.sum() == record.capture_step.size, label
        survivors = record.prey.death_step == NOT_DEAD
        assert np.all(record.prey.death_cause[survivors] == DeathCause.ALIVE), label


def test_episode_ends_early_when_all_prey_die(world_params) -> None:
    # c_basal = 0.125 is exact in binary, so repeated subtraction from 80 has no rounding
    # residue: energy reaches exactly 0 after 640 steps, i.e. during step t = 639.
    exact_prey = replace(PROVISIONAL_PREY, c_basal=0.125)
    params = world_params(t_max=1000, n_plants=0, n_predators=0, prey=exact_prey)
    record = simulate_episode(params, STILL, STILL, streams())
    assert record.steps == 640
    assert record.prey_alive_after[-1] == 0
    assert np.all(record.prey.death_step == 639)
    assert np.all(record.prey.death_cause == DeathCause.STARVATION)


def test_observer_sees_every_step_in_order(world_params) -> None:
    params = world_params(t_max=20)
    seen: list[int] = []
    simulate_episode(
        params,
        prey_rules(params),
        predator_rules(params),
        streams(),
        on_step=lambda t: seen.append(t.step),
    )
    assert seen == list(range(20))


def test_phase_timer_uses_the_injected_clock(world_params) -> None:
    ticks = itertools.count()
    timer = PhaseTimer(clock=lambda: float(next(ticks)))
    params = world_params(t_max=10)
    simulate_episode(params, prey_rules(params), predator_rules(params), streams(), timer=timer)
    assert timer.steps == 10
    assert timer.totals == {"perception": 10.0, "decision": 10.0, "rules": 10.0}


def test_energy_bookkeeping_is_consistent(world_params) -> None:
    params = world_params(t_max=300)
    record = simulate_episode(params, prey_rules(params), predator_rules(params), streams(1))
    for outcome, spec in ((record.prey, params.prey), (record.predators, params.predator)):
        expected = spec.initial_energy + outcome.energy_gained - outcome.energy_spent
        alive = outcome.death_step == NOT_DEAD
        np.testing.assert_allclose(outcome.final_energy[alive], expected[alive])
        assert np.all(outcome.final_energy[alive] <= spec.e_max)
