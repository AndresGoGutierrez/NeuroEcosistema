"""Use case: I2 of ADR-018, the initial saturation of random networks (F5).

The reference set holds observations of living agents in episodes of the rule-based policies
in every scenario (PILOT seeds of the declared group); one row of every ``stride`` is kept, in
step order. Random genomes come from the GA_INIT stream of the same group, so the whole check is
reproducible from the project seed.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

import numpy as np

from neuroeco.application.configs import ReferenceSpec, ResolvedConfig
from neuroeco.application.evaluation import EpisodeIdentity, run_episode
from neuroeco.application.seeding import Purpose, SeedRegistry, Stream
from neuroeco.domain.neural import (
    NetworkSpec,
    NeuralNetwork,
    SaturationStats,
    lecun_genome,
    saturation_stats,
)
from neuroeco.domain.policies import Policy
from neuroeco.domain.simulator import StepTrace

SPECIES = ("prey", "predator")
ENERGY_COLUMN = -1  # living observers have energy > 0; rows of dead observers are zero


def collect_reference(
    spec: ReferenceSpec,
    configs: Mapping[str, ResolvedConfig],
    make_policy: Callable[[str, str, ResolvedConfig], Policy],
    registry: SeedRegistry,
) -> dict[str, np.ndarray]:
    """Observations of living agents per species, one of every ``spec.stride`` rows."""
    rows: dict[str, list[np.ndarray]] = {s: [] for s in SPECIES}
    for index, scenario in enumerate(spec.scenarios):
        config = configs[scenario]
        prey = make_policy("rules", "prey", config)
        predator = make_policy("rules", "predator", config)

        def keep(trace: StepTrace) -> None:
            for species, obs in (
                ("prey", trace.prey_observations),
                ("predator", trace.predator_observations),
            ):
                rows[species].append(obs[obs[:, ENERGY_COLUMN] > 0.0])

        for episode in range(spec.episodes):
            item = index * spec.episodes + episode
            identity = EpisodeIdentity(Purpose.PILOT, spec.seed_group, item=item)
            run_episode(config.world, prey, predator, registry, identity, on_step=keep)
    return {s: np.concatenate(rows[s])[:: spec.stride].copy() for s in SPECIES}


def random_genome(spec: NetworkSpec, registry: SeedRegistry, seed_group: int, item: int):
    rng = registry.generator(Purpose.PILOT, seed_group, 0, 0, item, Stream.GA_INIT)
    return lecun_genome(spec, rng)


@dataclass(frozen=True)
class SaturationCheck:
    network: str
    per_genome: tuple[SaturationStats, ...]
    s1_median: tuple[float, ...]
    s2_median: tuple[float, ...]
    s3_median: tuple[float, ...]
    passed: bool


def check_saturation(
    spec: ReferenceSpec,
    network: NetworkSpec,
    observations: np.ndarray,
    registry: SeedRegistry,
) -> SaturationCheck:
    """S1-S3 of ADR-018 over ``spec.genomes`` random genomes of ``network``."""
    stats = tuple(
        saturation_stats(
            NeuralNetwork(network, random_genome(network, registry, spec.seed_group, g)),
            observations,
        )
        for g in range(spec.genomes)
    )

    def median(field: str) -> tuple[float, ...]:
        return tuple(float(v) for v in np.median([getattr(s, field) for s in stats], axis=0))

    s1, s2, s3 = median("s1"), median("s2"), median("s3")
    passed = (
        all(v <= spec.s1_max for v in s1)
        and all(v <= spec.s2_max for v in s2)
        and all(v >= spec.s3_min for v in s3)
    )
    return SaturationCheck(network.name, stats, s1, s2, s3, passed)
