"""F4 T2: the A2 invariant checker of ADR-033 (P1-22).

Synthetic worlds and seed_group >= 1000 only (D16). Each invariant is broken on purpose in a copy
of a real state to show that it is detected individually; the checker is also shown to read
without writing and without touching any random generator.
"""

import copy
import dataclasses

import numpy as np
import pytest

from neuroeco.application.calibration import (
    A2_INVARIANTS,
    FIRST_STEP_CAPTURE,
    PREDATOR_ENERGY,
    PREDATOR_IDENTITY,
    PREY_ENERGY,
    PREY_IDENTITY,
    SAFE_DISTANCE,
    InvariantChecker,
    InvariantViolationError,
)
from neuroeco.application.seeding import Purpose, SeedRegistry
from neuroeco.domain.interactions import InteractionResult
from neuroeco.domain.policies import RuleBasedPredatorPolicy, RuleBasedPreyPolicy
from neuroeco.domain.simulator import simulate_episode, step_world
from neuroeco.domain.state import DeathCause, initialize_world
from support import PROVISIONAL_WORLD, state_digest

SEED = 151810796106167051982782525292607188790
GROUP = 1000  # synthetic seed group (D16)
PARAMS = dataclasses.replace(PROVISIONAL_WORLD, t_max=120)


def streams(item: int = 0, params=PARAMS):
    return SeedRegistry(SEED).episode_streams(Purpose.PILOT, GROUP, 0, 0, item)


def policies(params=PARAMS):
    return (
        RuleBasedPreyPolicy(params.prey.omega_max, 0.3, 0.5),
        RuleBasedPredatorPolicy(params.predator.omega_max, 0.5),
    )


def first_trace(params=PARAMS):
    """S_0 and the trace of step 0 of a real episode."""
    episode_streams = streams(params=params)
    world = initialize_world(params, episode_streams)
    initial = copy.deepcopy(world)
    trace = step_world(world, params, *policies(params), episode_streams)
    return initial, trace


def broken(trace, change):
    """A copy of ``trace`` whose world has been altered by ``change(world)``."""
    world = copy.deepcopy(trace.world)
    change(world)
    return dataclasses.replace(trace, world=world)


def expect(invariant: str, call, step) -> InvariantViolationError:
    with pytest.raises(InvariantViolationError) as info:
        call()
    assert info.value.invariant == invariant
    assert info.value.step == step
    assert invariant in str(info.value)
    return info.value


def test_the_invariants_are_exactly_those_of_p1_22() -> None:
    assert A2_INVARIANTS == (
        "safe_distance_at_s0",
        "prey_identity",
        "predator_identity",
        "prey_energy",
        "predator_energy",
        "no_capture_in_first_step",
    )


def test_a_real_episode_satisfies_every_invariant() -> None:
    checker = InvariantChecker(PARAMS)
    episode_streams = streams()
    checker.check_initial(initialize_world(PARAMS, streams()))
    record = simulate_episode(PARAMS, *policies(), episode_streams, on_step=checker)
    assert checker.initial_checked
    assert checker.steps_checked == record.steps > 0


def test_a_world_without_predators_satisfies_every_invariant() -> None:
    params = dataclasses.replace(PARAMS, n_predators=0)
    checker = InvariantChecker(params)
    checker.check_initial(initialize_world(params, streams(params=params)))
    record = simulate_episode(params, *policies(params), streams(params=params), on_step=checker)
    assert checker.steps_checked == record.steps


# ---------------------------------------------------------------- each violation, individually


def test_safe_distance_violation_at_s0() -> None:
    initial, _ = first_trace()
    world = copy.deepcopy(initial)
    world.predators.positions[1] = world.prey.positions[4] + np.array([1.0, 0.0])
    violation = expect(SAFE_DISTANCE, lambda: InvariantChecker(PARAMS).check_initial(world), None)
    assert "predator 1" in violation.detail and "prey 4" in violation.detail
    assert "S0" in str(violation)


@pytest.mark.parametrize(
    "change",
    [
        lambda w: w.prey.death_cause.__setitem__(0, DeathCause.STARVATION),  # alive and dead
        lambda w: w.prey.alive.__setitem__(0, False),  # dead without a cause
    ],
    ids=["alive-with-cause", "dead-without-cause"],
)
def test_prey_identity_violation(change) -> None:
    _, trace = first_trace()
    expect(PREY_IDENTITY, lambda: InvariantChecker(PARAMS)(broken(trace, change)), 0)


def test_predator_identity_violation() -> None:
    _, trace = first_trace()

    def captured_predator(world) -> None:
        world.predators.alive[2] = False
        world.predators.death_cause[2] = DeathCause.CAPTURED

    expect(PREDATOR_IDENTITY, lambda: InvariantChecker(PARAMS)(broken(trace, captured_predator)), 0)


@pytest.mark.parametrize(
    "value", [0.0, -1.0, 100.5, np.nan], ids=["zero", "negative", "above", "nan"]
)
def test_prey_energy_violation(value: float) -> None:
    _, trace = first_trace()
    violation = expect(
        PREY_ENERGY,
        lambda: InvariantChecker(PARAMS)(
            broken(trace, lambda w: w.prey.energy.__setitem__(3, value))
        ),
        0,
    )
    assert "living agent 3" in violation.detail


def test_predator_energy_violation() -> None:
    _, trace = first_trace()
    expect(
        PREDATOR_ENERGY,
        lambda: InvariantChecker(PARAMS)(
            broken(trace, lambda w: w.predators.energy.__setitem__(0, 0.0))
        ),
        0,
    )


def test_dead_agents_are_exempt_from_the_energy_invariant() -> None:
    _, trace = first_trace()

    def starved(world) -> None:
        world.prey.alive[5] = False
        world.prey.death_cause[5] = DeathCause.STARVATION
        world.prey.energy[5] = -0.1

    InvariantChecker(PARAMS)(broken(trace, starved))


def test_capture_in_the_first_step_is_a_violation_but_not_later() -> None:
    _, trace = first_trace()
    capture = InteractionResult(
        consumers=np.array([0]), resources=np.array([0]), energy_gained=np.zeros(3)
    )
    expect(
        FIRST_STEP_CAPTURE,
        lambda: InvariantChecker(PARAMS)(dataclasses.replace(trace, captures=capture)),
        0,
    )

    checker = InvariantChecker(PARAMS)
    checker(trace)
    checker(dataclasses.replace(trace, step=1, captures=capture))
    assert checker.steps_checked == 2


def test_the_checker_must_see_every_step_in_order() -> None:
    _, trace = first_trace()
    with pytest.raises(RuntimeError, match="expected step 0 and received 1"):
        InvariantChecker(PARAMS)(dataclasses.replace(trace, step=1))
    initial, _ = first_trace()
    with pytest.raises(ValueError, match="S_0 must be at step 0"):
        InvariantChecker(PARAMS).check_initial(dataclasses.replace(initial, step=1))


# ---------------------------------------------------------------- no mutation, no randomness


def _freeze(world) -> None:
    for species in (world.prey, world.predators):
        for array in (
            species.positions,
            species.headings,
            species.energy,
            species.alive,
            species.death_step,
            species.death_cause,
        ):
            array.setflags(write=False)
    for array in (world.plants.positions, world.plants.active, world.plants.regrow_at):
        array.setflags(write=False)


def test_the_checker_only_reads_the_state() -> None:
    initial, trace = first_trace()
    before = (state_digest(initial), state_digest(trace.world))
    _freeze(initial)
    _freeze(trace.world)  # any write would raise "assignment destination is read-only"
    checker = InvariantChecker(PARAMS)
    checker.check_initial(initial)
    checker(trace)
    assert (state_digest(initial), state_digest(trace.world)) == before


def _generator_states(episode_streams) -> list:
    return [
        g.bit_generator.state
        for g in (
            episode_streams.env_init,
            episode_streams.env_dynamics,
            episode_streams.policy_prey,
            episode_streams.policy_predator,
        )
    ]


def test_checking_consumes_no_random_numbers() -> None:
    """Same per-step hashes and the same final state of the four generators, with or without."""
    plain_streams, checked_streams = streams(), streams()
    plain: list[str] = []
    simulate_episode(
        PARAMS, *policies(), plain_streams, on_step=lambda t: plain.append(state_digest(t.world))
    )

    checker = InvariantChecker(PARAMS)
    checker.check_initial(initialize_world(PARAMS, streams()))  # fresh generators (V7)
    checked: list[str] = []

    def observe(trace) -> None:
        checker(trace)
        checked.append(state_digest(trace.world))

    simulate_episode(PARAMS, *policies(), checked_streams, on_step=observe)
    assert checked == plain
    assert _generator_states(checked_streams) == _generator_states(plain_streams)
