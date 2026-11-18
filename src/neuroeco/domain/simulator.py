"""Synchronous simulation step and episode loop (ADR-008).

Phases of step t:
    1 observe on S_t   2 decide (batched policies)   3 move (turn, then advance)
    4 metabolism       5 starvation                   6 captures (greedy matching)
    7 feeding of prey still alive                     8 plant regrowth
    9 termination: t + 1 == t_max or no prey alive

The domain never reads a clock: phase timing for the P0 benchmark uses an injected
``PhaseTimer`` and is kept out of the (deterministic) episode record.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from neuroeco.domain.actions import decode_actions
from neuroeco.domain.interactions import (
    InteractionResult,
    regrow_plants,
    resolve_captures,
    resolve_feeding,
)
from neuroeco.domain.params import WorldParams
from neuroeco.domain.perception import observe_predators, observe_prey
from neuroeco.domain.policies import Policy
from neuroeco.domain.records import EpisodeRecord, SpeciesOutcome
from neuroeco.domain.rules import apply_metabolism, apply_movement, apply_starvation, is_terminal
from neuroeco.domain.state import DeathCause, EpisodeStreams, WorldState, initialize_world

PHASES = ("perception", "decision", "rules")


@dataclass
class PhaseTimer:
    """Accumulates elapsed time per phase using an injected clock (seconds)."""

    clock: Callable[[], float]
    totals: dict[str, float] = field(default_factory=lambda: dict.fromkeys(PHASES, 0.0))
    steps: int = 0


@dataclass(frozen=True)
class StepTrace:
    """What happened in one step; passed to observers (viewer, determinism checks)."""

    step: int
    world: WorldState  # state after the step; observers must not modify it
    prey_observations: np.ndarray
    predator_observations: np.ndarray
    prey_actions: np.ndarray
    predator_actions: np.ndarray
    captures: InteractionResult
    feeding: InteractionResult
    prey_energy_spent: np.ndarray
    predator_energy_spent: np.ndarray


def step_world(
    world: WorldState,
    params: WorldParams,
    prey_policy: Policy,
    predator_policy: Policy,
    streams: EpisodeStreams,
    timer: PhaseTimer | None = None,
) -> StepTrace:
    """Advance the world by one synchronous step (phases 1-8) and increment ``world.step``."""
    t = world.step
    mark = timer.clock() if timer else 0.0

    prey_obs = observe_prey(world, params)  # 1
    predator_obs = observe_predators(world, params)
    if timer:
        now = timer.clock()
        timer.totals["perception"] += now - mark
        mark = now

    prey_raw = prey_policy.act(prey_obs, streams.policy_prey)  # 2
    predator_raw = predator_policy.act(predator_obs, streams.policy_predator)
    if timer:
        now = timer.clock()
        timer.totals["decision"] += now - mark
        mark = now

    prey_turns, prey_speeds = decode_actions(prey_raw, params.prey)  # 3
    predator_turns, predator_speeds = decode_actions(predator_raw, params.predator)
    apply_movement(world.prey, prey_turns, prey_speeds, params.size)
    apply_movement(world.predators, predator_turns, predator_speeds, params.size)
    prey_spent = apply_metabolism(world.prey, prey_speeds, params.prey)  # 4
    predator_spent = apply_metabolism(world.predators, predator_speeds, params.predator)
    apply_starvation(world.prey, t)  # 5
    apply_starvation(world.predators, t)
    captures = resolve_captures(world, params, t)  # 6
    feeding = resolve_feeding(world, params, t)  # 7
    regrow_plants(world, t)  # 8
    world.step = t + 1
    if timer:
        timer.totals["rules"] += timer.clock() - mark
        timer.steps += 1

    return StepTrace(
        step=t,
        world=world,
        prey_observations=prey_obs,
        predator_observations=predator_obs,
        prey_actions=prey_raw,
        predator_actions=predator_raw,
        captures=captures,
        feeding=feeding,
        prey_energy_spent=prey_spent,
        predator_energy_spent=predator_spent,
    )


class _Recorder:
    """Accumulates per-step information into an EpisodeRecord."""

    def __init__(self, world: WorldState) -> None:
        self.prey_gained = np.zeros(world.prey.size)
        self.prey_spent = np.zeros(world.prey.size)
        self.predator_gained = np.zeros(world.predators.size)
        self.predator_spent = np.zeros(world.predators.size)
        self.prey_events = np.zeros(world.prey.size, dtype=np.int64)
        self.predator_events = np.zeros(world.predators.size, dtype=np.int64)
        self.captures: list[tuple[int, int, int]] = []
        self.feedings: list[tuple[int, int, int]] = []
        self.counts: list[tuple[int, int, int, int, int]] = []
        self.last_energy_prey = world.prey.energy.copy()
        self.last_energy_predators = world.predators.energy.copy()

    def add(self, trace: StepTrace) -> None:
        world = trace.world
        self.prey_gained += trace.feeding.energy_gained
        self.prey_spent += trace.prey_energy_spent
        self.predator_gained += trace.captures.energy_gained
        self.predator_spent += trace.predator_energy_spent
        np.add.at(self.prey_events, trace.feeding.consumers, 1)
        np.add.at(self.predator_events, trace.captures.consumers, 1)
        self.captures.extend(
            (trace.step, int(p), int(q))
            for p, q in zip(trace.captures.consumers, trace.captures.resources, strict=True)
        )
        self.feedings.extend(
            (trace.step, int(p), int(q))
            for p, q in zip(trace.feeding.consumers, trace.feeding.resources, strict=True)
        )
        cause = world.prey.death_cause
        self.counts.append(
            (
                int(world.prey.alive.sum()),
                int((cause == DeathCause.CAPTURED).sum()),
                int((cause == DeathCause.STARVATION).sum()),
                int(world.predators.alive.sum()),
                int(world.plants.active.sum()),
            )
        )
        # Energy of agents alive after the step; dead agents keep their last living value.
        self.last_energy_prey[world.prey.alive] = world.prey.energy[world.prey.alive]
        self.last_energy_predators[world.predators.alive] = world.predators.energy[
            world.predators.alive
        ]

    def build(self, world: WorldState, t_max: int) -> EpisodeRecord:
        def events(rows: list[tuple[int, int, int]], column: int) -> np.ndarray:
            return np.array([row[column] for row in rows], dtype=np.int64)

        counts = np.array(self.counts, dtype=np.int64).reshape(-1, 5)
        return EpisodeRecord(
            t_max=t_max,
            steps=world.step,
            prey=SpeciesOutcome(
                death_step=world.prey.death_step.copy(),
                death_cause=world.prey.death_cause.copy(),
                final_energy=self.last_energy_prey,
                energy_gained=self.prey_gained,
                energy_spent=self.prey_spent,
                events=self.prey_events,
            ),
            predators=SpeciesOutcome(
                death_step=world.predators.death_step.copy(),
                death_cause=world.predators.death_cause.copy(),
                final_energy=self.last_energy_predators,
                energy_gained=self.predator_gained,
                energy_spent=self.predator_spent,
                events=self.predator_events,
            ),
            capture_step=events(self.captures, 0),
            capture_predator=events(self.captures, 1),
            capture_prey=events(self.captures, 2),
            feeding_step=events(self.feedings, 0),
            feeding_prey=events(self.feedings, 1),
            feeding_plant=events(self.feedings, 2),
            prey_alive_after=counts[:, 0],
            prey_captured_after=counts[:, 1],
            prey_starved_after=counts[:, 2],
            predators_alive_after=counts[:, 3],
            plants_active_after=counts[:, 4],
        )


def simulate_episode(
    params: WorldParams,
    prey_policy: Policy,
    predator_policy: Policy,
    streams: EpisodeStreams,
    on_step: Callable[[StepTrace], None] | None = None,
    timer: PhaseTimer | None = None,
    stop_without_predators: bool = False,
) -> EpisodeRecord:
    """Run one episode from deterministic initial conditions until termination (phase 9).

    ``stop_without_predators`` (ADR-015) also ends the episode when every predator is dead; it is
    only for training and validation of predators, whose fitness can no longer change then.
    """
    world = initialize_world(params, streams)
    recorder = _Recorder(world)
    while True:
        trace = step_world(world, params, prey_policy, predator_policy, streams, timer)
        recorder.add(trace)
        if on_step is not None:
            on_step(trace)
        if is_terminal(world.step, params.t_max, int(world.prey.alive.sum())):
            break
        if stop_without_predators and not world.predators.alive.any():
            break
    return recorder.build(world, params.t_max)
