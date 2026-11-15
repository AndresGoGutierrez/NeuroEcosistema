"""DET-1, DET-2 and DET-5 (catalog in docs/architecture.md; ADR-016, ADR-028)."""

import hashlib
import subprocess
import sys
import textwrap
from pathlib import Path

import numpy as np
import pytest

from neuroeco.application.seeding import Purpose, SeedRegistry
from neuroeco.domain.policies import RandomPolicy, RuleBasedPredatorPolicy, RuleBasedPreyPolicy
from neuroeco.domain.simulator import simulate_episode
from neuroeco.domain.state import initialize_world
from neuroeco.infrastructure.config_loader import load_config
from support import state_digest

pytestmark = pytest.mark.determinism

ROOT = Path(__file__).resolve().parents[2]
CONFIGS = ROOT / "configs"
OVERRIDES = ("world.t_max=300",)
ITEM = 3


def episode_fingerprint(policy_kind: str, item: int = ITEM) -> tuple[str, list[str]]:
    """Digest of the state after every step of a fixed episode, and their combined hash."""
    config = load_config(CONFIGS, "C", OVERRIDES)
    params = config.world
    if policy_kind == "rules":
        prey = RuleBasedPreyPolicy(params.prey.omega_max, 0.3, 0.5)
        predator = RuleBasedPredatorPolicy(params.predator.omega_max, 0.5)
    else:
        prey, predator = RandomPolicy(), RandomPolicy()
    streams = SeedRegistry(config.project_seed).episode_streams(Purpose.TEST, 0, 0, 0, item)
    steps: list[str] = []
    simulate_episode(
        params, prey, predator, streams, on_step=lambda t: steps.append(state_digest(t.world))
    )
    return hashlib.sha256("".join(steps).encode()).hexdigest(), steps


@pytest.mark.parametrize("policy_kind", ["rules", "random"])
def test_det1_same_episode_twice_in_one_process(policy_kind) -> None:
    first, first_steps = episode_fingerprint(policy_kind)
    second, second_steps = episode_fingerprint(policy_kind)
    assert len(first_steps) > 1
    assert first_steps == second_steps
    assert first == second


def test_fingerprint_is_sensitive_to_the_episode() -> None:
    # Guards DET-1/DET-2 against a digest that ignores the state.
    reference, steps = episode_fingerprint("rules")
    assert reference != episode_fingerprint("rules", item=ITEM + 1)[0]
    assert reference != episode_fingerprint("random")[0]
    assert len(set(steps)) == len(steps)  # every step changes the state


CHILD = textwrap.dedent(
    """
    import sys
    sys.path.insert(0, sys.argv[1])
    sys.path.insert(0, sys.argv[2])
    from test_determinism import episode_fingerprint
    print(episode_fingerprint(sys.argv[3])[0])
    """
)


@pytest.mark.parametrize("policy_kind", ["rules", "random"])
def test_det2_same_episode_in_an_independent_process(policy_kind) -> None:
    expected, _ = episode_fingerprint(policy_kind)
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            CHILD,
            str(Path(__file__).parent),
            str(ROOT / "tests"),
            policy_kind,
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=300,
    )
    assert completed.stdout.strip() == expected


def respawn_positions(policy_kind: str) -> list[tuple[float, float]]:
    """Positions taken by plants at each reappearance, in respawn order."""
    config = load_config(CONFIGS, "A", ("world.t_max=600", "world.n_prey=50"))
    params = config.world
    if policy_kind == "rules":
        prey = RuleBasedPreyPolicy(params.prey.omega_max, 0.3, 0.5)
        predator = RuleBasedPredatorPolicy(params.predator.omega_max, 0.5)
    else:
        prey, predator = RandomPolicy(), RandomPolicy()
    streams = SeedRegistry(config.project_seed).episode_streams(Purpose.TEST, 0, 0, 0, ITEM)
    positions: list[tuple[float, float]] = []
    previous = {"active": np.ones(params.n_plants, dtype=bool)}

    def collect(trace) -> None:
        plants = trace.world.plants
        reappeared = np.flatnonzero(plants.active & ~previous["active"])
        positions.extend((float(x), float(y)) for x, y in plants.positions[reappeared])
        previous["active"] = plants.active.copy()

    simulate_episode(params, prey, predator, streams, on_step=collect)
    return positions


def test_det5_changing_the_policy_keeps_the_environment() -> None:
    config = load_config(CONFIGS, "A")
    registry = SeedRegistry(config.project_seed)
    worlds = [
        initialize_world(config.world, registry.episode_streams(Purpose.TEST, 0, 0, 0, ITEM))
        for _ in range(2)
    ]
    assert state_digest(worlds[0]) == state_digest(worlds[1])

    by_rules = respawn_positions("rules")
    by_random = respawn_positions("random")
    common = min(len(by_rules), len(by_random))
    assert common >= 3, "the episode must exercise plant respawns"
    assert by_rules[:common] == by_random[:common]
