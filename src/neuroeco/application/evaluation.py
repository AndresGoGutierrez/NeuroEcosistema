"""Use case: run one seeded episode and compute its metrics."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from neuroeco.application.metrics import EpisodeMetrics, episode_metrics
from neuroeco.application.seeding import Purpose, SeedRegistry
from neuroeco.domain.params import WorldParams
from neuroeco.domain.policies import Policy
from neuroeco.domain.records import EpisodeRecord
from neuroeco.domain.simulator import PhaseTimer, StepTrace, simulate_episode


@dataclass(frozen=True)
class EpisodeIdentity:
    """Seed coordinates of an episode (ADR-028)."""

    purpose: Purpose
    seed_group: int
    run: int = 0
    generation: int = 0
    item: int = 0


@dataclass(frozen=True)
class EpisodeResult:
    identity: EpisodeIdentity
    record: EpisodeRecord
    metrics: EpisodeMetrics


def run_episode(
    params: WorldParams,
    prey_policy: Policy,
    predator_policy: Policy,
    registry: SeedRegistry,
    identity: EpisodeIdentity,
    on_step: Callable[[StepTrace], None] | None = None,
    timer: PhaseTimer | None = None,
) -> EpisodeResult:
    streams = registry.episode_streams(
        identity.purpose, identity.seed_group, identity.run, identity.generation, identity.item
    )
    record = simulate_episode(params, prey_policy, predator_policy, streams, on_step, timer)
    return EpisodeResult(identity=identity, record=record, metrics=episode_metrics(record))
