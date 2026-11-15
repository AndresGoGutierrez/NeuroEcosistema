"""T8: reference policies and probes (ADR-012)."""

import numpy as np
import pytest

from neuroeco.domain.perception import PREDATOR_SCHEMA, PREY_SCHEMA
from neuroeco.domain.policies import (
    PROBE_NAMES,
    Policy,
    RandomPolicy,
    RuleBasedPredatorPolicy,
    RuleBasedPreyPolicy,
    make_probe,
)

OMEGA = 0.5


def prey_obs(plant=None, predator1=None, energy=0.8) -> np.ndarray:
    """One prey observation. Objects are (proximity, phi)."""
    row = np.zeros(PREY_SCHEMA.size)
    for prefix, obj in (("plant", plant), ("predator1", predator1)):
        if obj is not None:
            p, phi = obj
            start = PREY_SCHEMA.names.index(f"{prefix}_proximity")
            row[start : start + 3] = [p, p * np.sin(phi), p * np.cos(phi)]
    row[-1] = energy
    return row[np.newaxis, :]


def predator_obs(prey1=None) -> np.ndarray:
    row = np.zeros(PREDATOR_SCHEMA.size)
    if prey1 is not None:
        p, phi = prey1
        row[0:3] = [p, p * np.sin(phi), p * np.cos(phi)]
    row[-1] = 0.8
    return row[np.newaxis, :]


PREY_RULES = RuleBasedPreyPolicy(OMEGA, flee_threshold=0.3, cruise_fraction=0.5)
PREDATOR_RULES = RuleBasedPredatorPolicy(OMEGA, cruise_fraction=0.25)


def all_policies():
    return [RandomPolicy(), PREY_RULES, PREDATOR_RULES] + [
        make_probe(name, 0.5) for name in PROBE_NAMES
    ]


@pytest.mark.parametrize("policy", all_policies(), ids=lambda p: p.name)
def test_outputs_have_shape_and_range(policy) -> None:
    assert isinstance(policy, Policy)
    d_in = PREDATOR_SCHEMA.size if policy is PREDATOR_RULES else PREY_SCHEMA.size
    obs = np.random.default_rng(0).uniform(-1, 1, size=(9, d_in))
    obs[:, 0::3] = np.abs(obs[:, 0::3])  # proximities are non-negative
    actions = policy.act(obs, np.random.default_rng(1))
    assert actions.shape == (9, 2)
    assert np.all(np.isfinite(actions)) and np.all(np.abs(actions) <= 1.0)


def test_random_policy_depends_only_on_its_generator() -> None:
    obs = np.zeros((4, PREY_SCHEMA.size))
    a = RandomPolicy().act(obs, np.random.default_rng(5))
    b = RandomPolicy().act(obs * 7, np.random.default_rng(5))
    np.testing.assert_array_equal(a, b)


def test_prey_flees_away_from_a_close_predator() -> None:
    # Predator to the left (phi = +pi/2): fleeing means turning right at full speed.
    turn, throttle = PREY_RULES.act(prey_obs(predator1=(0.6, np.pi / 2)), None)[0]
    assert turn == -1.0 and throttle == 1.0
    turn, _ = PREY_RULES.act(prey_obs(predator1=(0.6, -np.pi / 2)), None)[0]
    assert turn == 1.0


def test_prey_ignores_a_distant_predator_and_seeks_the_plant() -> None:
    action = PREY_RULES.act(prey_obs(plant=(0.5, 0.1), predator1=(0.2, 0.0)), None)[0]
    np.testing.assert_allclose(action, [0.1 / OMEGA, 1.0])


def test_prey_cruises_when_nothing_is_perceived() -> None:
    np.testing.assert_allclose(PREY_RULES.act(prey_obs(), None)[0], [0.0, 0.0])  # cruise 0.5


def test_predator_chases_the_nearest_prey() -> None:
    action = PREDATOR_RULES.act(predator_obs(prey1=(0.4, -0.2)), None)[0]
    np.testing.assert_allclose(action, [-0.2 / OMEGA, 1.0])
    np.testing.assert_allclose(PREDATOR_RULES.act(predator_obs(), None)[0], [0.0, -0.5])


def test_probes_are_constant() -> None:
    expected = {
        "STILL": [0.0, -1.0],
        "SPIN": [1.0, 0.0],
        "STRAIGHT_MAX": [0.0, 1.0],
        "STRAIGHT_CRUISE": [0.0, -0.5],  # cruise fraction 0.25
    }
    obs = np.zeros((3, PREY_SCHEMA.size))
    for name, action in expected.items():
        np.testing.assert_allclose(make_probe(name, 0.25).act(obs, None), [action] * 3)


@pytest.mark.parametrize(
    "build",
    [
        lambda: make_probe("JUMP", 0.5),
        lambda: make_probe("STILL", 1.5),
        lambda: RuleBasedPreyPolicy(OMEGA, flee_threshold=-0.1, cruise_fraction=0.5),
        lambda: RuleBasedPredatorPolicy(OMEGA, cruise_fraction=2.0),
    ],
)
def test_invalid_policy_parameters_are_rejected(build) -> None:
    with pytest.raises(ValueError):
        build()
