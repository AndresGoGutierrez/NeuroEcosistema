"""Interactive session for the viewer (ADR-031).

The viewer is a synchronous observer of ``simulate_episode``. It never receives the live
``WorldState``: every step is converted into an immutable ``Frame`` holding read-only copies of

- the state after the step (S_t+1): positions, headings, energy, life status and plants;
- the decision of step t: observations taken on S_t and the raw actions of the policies;
- the HUD statistics.

The initial state S_0 does not pass through ``on_step``; it is rebuilt with ``initialize_world``
on fresh generators derived from the same seed identity, so the generators of the episode are
never touched.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from neuroeco.application.evaluation import EpisodeIdentity, EpisodeResult, run_episode
from neuroeco.application.seeding import SeedRegistry
from neuroeco.domain.actions import decode_actions
from neuroeco.domain.neural import NeuralNetwork
from neuroeco.domain.params import SpeciesParams, WorldParams
from neuroeco.domain.perception import PREDATOR_SCHEMA, PREY_SCHEMA, InputSchema
from neuroeco.domain.policies import Policy
from neuroeco.domain.simulator import StepTrace
from neuroeco.domain.state import NOT_DEAD, DeathCause, SpeciesState, WorldState, initialize_world

SPECIES = ("prey", "predator")


def _read_only(array: np.ndarray) -> np.ndarray:
    copy = np.array(array, copy=True)
    copy.setflags(write=False)
    return copy


@dataclass(frozen=True)
class SpeciesView:
    """Read-only copy of one species' state."""

    positions: np.ndarray
    headings: np.ndarray
    energy: np.ndarray
    alive: np.ndarray
    death_step: np.ndarray
    death_cause: np.ndarray

    @classmethod
    def of(cls, species: SpeciesState) -> SpeciesView:
        return cls(
            positions=_read_only(species.positions),
            headings=_read_only(species.headings),
            energy=_read_only(species.energy),
            alive=_read_only(species.alive),
            death_step=_read_only(species.death_step),
            death_cause=_read_only(species.death_cause),
        )

    @property
    def size(self) -> int:
        return int(self.alive.shape[0])


@dataclass(frozen=True)
class Decision:
    """Decision of step ``step``: observations taken on S_step and raw policy outputs."""

    step: int
    observations: np.ndarray  # (n, d_in)
    raw_actions: np.ndarray  # (n, 2) in [-1, 1]


@dataclass(frozen=True)
class HudStats:
    """Statistics shown by the HUD for the state S_step."""

    step: int  # completed steps
    t_max: int
    n_prey: int
    n_predators: int
    prey_alive: int
    prey_captured: int
    prey_starved: int
    predators_alive: int
    plants_active: int
    n_plants: int
    prey_mean_energy: float  # over living prey; nan when none is alive
    predator_mean_energy: float
    captures_total: int  # cumulative
    feedings_total: int  # cumulative


@dataclass(frozen=True)
class Frame:
    """Everything the viewer may show for one state S_step."""

    step: int
    prey: SpeciesView
    predators: SpeciesView
    plant_positions: np.ndarray
    plant_active: np.ndarray
    prey_decision: Decision | None  # None for S_0
    predator_decision: Decision | None
    stats: HudStats

    def species(self, name: str) -> SpeciesView:
        return {"prey": self.prey, "predator": self.predators}[_check_species(name)]

    def decision(self, name: str) -> Decision | None:
        return {"prey": self.prey_decision, "predator": self.predator_decision}[
            _check_species(name)
        ]


def _check_species(name: str) -> str:
    if name not in SPECIES:
        raise ValueError(f"species must be one of {SPECIES}, got {name!r}")
    return name


def _mean_energy(view: SpeciesView) -> float:
    return float(view.energy[view.alive].mean()) if view.alive.any() else float("nan")


class SessionTracker:
    """Builds frames from S_0 and from each step trace, accumulating the HUD counters."""

    def __init__(self, params: WorldParams) -> None:
        self._params = params
        self._captures = 0
        self._feedings = 0

    def start(self, world: WorldState) -> Frame:
        return self._frame(world, None, None)

    def observe(self, trace: StepTrace) -> Frame:
        self._captures += int(trace.captures.consumers.size)
        self._feedings += int(trace.feeding.consumers.size)
        prey = Decision(
            trace.step, _read_only(trace.prey_observations), _read_only(trace.prey_actions)
        )
        predators = Decision(
            trace.step, _read_only(trace.predator_observations), _read_only(trace.predator_actions)
        )
        return self._frame(trace.world, prey, predators)

    def _frame(
        self, world: WorldState, prey_decision: Decision | None, predator_decision: Decision | None
    ) -> Frame:
        prey, predators = SpeciesView.of(world.prey), SpeciesView.of(world.predators)
        params = self._params
        stats = HudStats(
            step=world.step,
            t_max=params.t_max,
            n_prey=prey.size,
            n_predators=predators.size,
            prey_alive=int(prey.alive.sum()),
            prey_captured=int((prey.death_cause == DeathCause.CAPTURED).sum()),
            prey_starved=int((prey.death_cause == DeathCause.STARVATION).sum()),
            predators_alive=int(predators.alive.sum()),
            plants_active=int(world.plants.active.sum()),
            n_plants=int(world.plants.active.shape[0]),
            prey_mean_energy=_mean_energy(prey),
            predator_mean_energy=_mean_energy(predators),
            captures_total=self._captures,
            feedings_total=self._feedings,
        )
        return Frame(
            step=world.step,
            prey=prey,
            predators=predators,
            plant_positions=_read_only(world.plants.positions),
            plant_active=_read_only(world.plants.active),
            prey_decision=prey_decision,
            predator_decision=predator_decision,
            stats=stats,
        )


@dataclass(frozen=True)
class AgentInspection:
    """Inspector content for one agent (ADR-031, decision V4).

    ``state_step`` identifies the state shown (S_state_step). The decision fields describe step
    ``decision_step`` = state_step - 1, whose observations were taken on S_decision_step. They
    are None for S_0.
    """

    species: str
    index: int
    state_step: int
    alive: bool
    death_cause: str
    death_step: int | None
    energy: float
    energy_fraction: float
    position: tuple[float, float]
    heading: float
    decision_step: int | None
    inputs: tuple[tuple[str, float], ...]
    raw_action: tuple[float, float] | None
    turn: float | None
    speed: float | None
    action_applied: bool | None  # alive when step decision_step started
    # hidden-layer outputs of a neural policy for this decision (F5); empty otherwise
    activations: tuple[tuple[float, ...], ...] = ()


def _schema_and_params(species: str, params: WorldParams) -> tuple[InputSchema, SpeciesParams]:
    if species == "prey":
        return PREY_SCHEMA, params.prey
    return PREDATOR_SCHEMA, params.predator


def inspect_agent(
    frame: Frame,
    params: WorldParams,
    species: str,
    index: int,
    network: NeuralNetwork | None = None,
) -> AgentInspection:
    """Inspector values of one agent, taken from the frame.

    With the ``network`` of a neural policy, its hidden activations for the recorded
    observations are recomputed (the forward pass is deterministic, so they are the ones of the
    decision, up to rounding); its output must match the recorded raw action.
    """
    view = frame.species(species)
    if not 0 <= index < view.size:
        raise IndexError(f"{species} index {index} out of range [0, {view.size})")
    schema, species_params = _schema_and_params(species, params)
    death_step = int(view.death_step[index])
    energy = float(view.energy[index])

    decision = frame.decision(species)
    inputs: tuple[tuple[str, float], ...] = ()
    raw = turn = speed = applied = None
    activations: tuple[tuple[float, ...], ...] = ()
    if decision is not None:
        row = decision.observations[index]
        if network is not None:
            layers = network.activations(row[np.newaxis, :])
            # One row and the whole batch may differ in the last bit (BLAS blocking), so the
            # check is to 1e-12: enough to reject a network that did not take the decision.
            if not np.allclose(layers[-1][0], decision.raw_actions[index], rtol=0, atol=1e-12):
                raise ValueError("the network does not reproduce the recorded action")
            activations = tuple(tuple(float(v) for v in a[0]) for a in layers[:-1])
        inputs = tuple((name, float(value)) for name, value in zip(schema.names, row, strict=True))
        raw_row = decision.raw_actions[index : index + 1]
        turns, speeds = decode_actions(raw_row, species_params)
        raw = (float(raw_row[0, 0]), float(raw_row[0, 1]))
        turn, speed = float(turns[0]), float(speeds[0])
        # Movement is applied in phase 3 to agents alive when the step starts; an agent that
        # died during this step (phases 5-6) had already moved.
        applied = bool(view.alive[index]) or death_step == decision.step

    return AgentInspection(
        species=species,
        index=index,
        state_step=frame.step,
        alive=bool(view.alive[index]),
        death_cause=DeathCause(int(view.death_cause[index])).name,
        death_step=None if death_step == NOT_DEAD else death_step,
        energy=energy,
        energy_fraction=energy / species_params.e_max,
        position=(float(view.positions[index, 0]), float(view.positions[index, 1])),
        heading=float(view.headings[index]),
        decision_step=None if decision is None else decision.step,
        inputs=inputs,
        raw_action=raw,
        turn=turn,
        speed=speed,
        action_applied=applied,
        activations=activations,
    )


class FrameObserver(Protocol):
    """Receives S_0 and then one frame per executed step."""

    def start(self, frame: Frame) -> None: ...

    def step(self, frame: Frame) -> None: ...


def initial_world(
    params: WorldParams, registry: SeedRegistry, identity: EpisodeIdentity
) -> WorldState:
    """S_0 rebuilt from fresh generators of the same identity (decision V7)."""
    streams = registry.episode_streams(
        identity.purpose, identity.seed_group, identity.run, identity.generation, identity.item
    )
    return initialize_world(params, streams)


def run_session(
    params: WorldParams,
    prey_policy: Policy,
    predator_policy: Policy,
    registry: SeedRegistry,
    identity: EpisodeIdentity,
    observer: FrameObserver,
    after_step: Callable[[StepTrace], None] | None = None,
) -> EpisodeResult:
    """Run one episode showing it to ``observer``; the episode itself is ``run_episode``'s.

    ``after_step`` runs after the observer on every step; verification code uses it to hash the
    state the observer has just seen.
    """
    tracker = SessionTracker(params)
    observer.start(tracker.start(initial_world(params, registry, identity)))

    def on_step(trace: StepTrace) -> None:
        observer.step(tracker.observe(trace))
        if after_step is not None:
            after_step(trace)

    return run_episode(params, prey_policy, predator_policy, registry, identity, on_step=on_step)
