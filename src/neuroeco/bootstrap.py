"""Composition root: the only place that wires infrastructure into the application."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from neuroeco.application.configs import ResolvedConfig
from neuroeco.application.seeding import SeedRegistry
from neuroeco.domain.neural import NeuralPolicy
from neuroeco.domain.policies import (
    PROBE_NAMES,
    Policy,
    RandomPolicy,
    RuleBasedPredatorPolicy,
    RuleBasedPreyPolicy,
    make_probe,
)
from neuroeco.infrastructure.config_loader import load_config
from neuroeco.infrastructure.model_store import load_model

DEFAULT_CONFIG_DIR = Path("configs")
EXPLORATORY_SEED_GROUP = 0  # reserved for ad-hoc `neuroeco run` executions
REFERENCE_POLICIES = ("rules", "random", *(name.lower() for name in PROBE_NAMES))
MODEL_PREFIX = "model:"  # a saved network: model:<path to .npz> (F5)


@dataclass(frozen=True)
class Runtime:
    config: ResolvedConfig
    registry: SeedRegistry


def build_runtime(
    scenario: str, overrides: Sequence[str] = (), config_dir: Path = DEFAULT_CONFIG_DIR
) -> Runtime:
    config = load_config(config_dir, scenario, overrides)
    return Runtime(config=config, registry=SeedRegistry(config.project_seed))


def build_policy(name: str, species: str, config: ResolvedConfig) -> Policy:
    """Reference policies by name (rules, random or a probe, ADR-012) or a saved network.

    ``model:<path>`` loads a network model (F5); its input schema must be the current schema of
    ``species`` (ADR-007), otherwise the model is rejected.
    """
    if species not in ("prey", "predator"):
        raise ValueError(f"species must be 'prey' or 'predator', got {species!r}")
    if name.startswith(MODEL_PREFIX):
        network, _ = load_model(Path(name[len(MODEL_PREFIX) :]))
        if network.spec.schema.species != species:
            raise ValueError(
                f"{name} is a {network.spec.schema.species} model, not a {species} one"
            )
        return NeuralPolicy(network)
    world, rules = config.world, config.rules
    if name == "random":
        return RandomPolicy()
    if name == "rules":
        if species == "prey":
            return RuleBasedPreyPolicy(
                world.prey.omega_max, rules.prey.flee_threshold, rules.prey.cruise_fraction
            )
        return RuleBasedPredatorPolicy(world.predator.omega_max, rules.predator.cruise_fraction)
    if name.upper() in PROBE_NAMES:
        cruise = rules.prey.cruise_fraction if species == "prey" else rules.predator.cruise_fraction
        return make_probe(name.upper(), cruise)
    raise ValueError(f"unknown policy {name!r}; expected one of {REFERENCE_POLICIES}")
