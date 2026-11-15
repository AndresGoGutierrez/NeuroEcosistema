"""Decision policies (ADR-012, ADR-021).

``Policy`` is the only protocol of the domain: every policy maps a batch of observations
(n, d_in) to raw actions (n, 2) in [-1, 1], decoded by ``domain.actions.decode_actions``.
Reference policies use exactly the same observations as the neural networks, so comparisons
isolate the decision model, not the information available.

Steering towards a relative angle alpha uses o0 = clip(alpha / omega_max, -1, 1), with
phi = atan2(left, forward) recovered from the sensors.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np

from neuroeco.domain.actions import RAW_ACTION_SIZE
from neuroeco.domain.perception import PREDATOR_SCHEMA, PREY_SCHEMA, InputSchema


@runtime_checkable
class Policy(Protocol):
    name: str

    def act(self, observations: np.ndarray, rng: np.random.Generator) -> np.ndarray:
        """Raw actions (n, 2) in [-1, 1] for a batch of observations (n, d_in)."""
        ...


def _check_fraction(name: str, value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be in [0, 1], got {value!r}")


def throttle_for_speed_fraction(fraction: float) -> float:
    """Raw throttle o1 that yields speed = fraction * v_max."""
    return 2.0 * fraction - 1.0


def _wrap_angle(angle: np.ndarray) -> np.ndarray:
    return np.mod(angle + np.pi, 2.0 * np.pi) - np.pi


def _steer(angle: np.ndarray, omega_max: float) -> np.ndarray:
    return np.clip(angle / omega_max, -1.0, 1.0)


def _bearing(observations: np.ndarray, schema: InputSchema, prefix: str) -> np.ndarray:
    left = observations[:, schema.names.index(f"{prefix}_left")]
    forward = observations[:, schema.names.index(f"{prefix}_forward")]
    return np.arctan2(left, forward)


class RandomPolicy:
    """Independent uniform raw actions at every step (ADR-012).

    Always draws n * 2 values per call, so its stream consumption does not depend on how many
    agents are alive.
    """

    name = "random"

    def act(self, observations: np.ndarray, rng: np.random.Generator) -> np.ndarray:
        return rng.uniform(-1.0, 1.0, size=(observations.shape[0], RAW_ACTION_SIZE))


@dataclass(frozen=True)
class ConstantPolicy:
    """Degenerate probe (ADR-012, ADR-019): the same raw action for every agent and step."""

    name: str
    turn: float
    throttle: float

    def __post_init__(self) -> None:
        if not (-1.0 <= self.turn <= 1.0 and -1.0 <= self.throttle <= 1.0):
            raise ValueError("probe actions must lie in [-1, 1]")

    def act(self, observations: np.ndarray, rng: np.random.Generator) -> np.ndarray:
        return np.tile([self.turn, self.throttle], (observations.shape[0], 1)).astype(np.float64)


PROBE_NAMES = ("STILL", "SPIN", "STRAIGHT_MAX", "STRAIGHT_CRUISE")


def make_probe(name: str, cruise_fraction: float) -> ConstantPolicy:
    """Probes of ADR-012.

    SPIN turns at the maximum rate at half speed, so the agent moves in circles: the degenerate
    behaviour the probe must expose (ADR-011). At zero speed it would duplicate STILL.
    """
    _check_fraction("cruise_fraction", cruise_fraction)
    probes = {
        "STILL": (0.0, -1.0),
        "SPIN": (1.0, 0.0),
        "STRAIGHT_MAX": (0.0, 1.0),
        "STRAIGHT_CRUISE": (0.0, throttle_for_speed_fraction(cruise_fraction)),
    }
    if name not in probes:
        raise ValueError(f"unknown probe {name!r}; expected one of {PROBE_NAMES}")
    turn, throttle = probes[name]
    return ConstantPolicy(name=f"probe_{name.lower()}", turn=turn, throttle=throttle)


class RuleBasedPreyPolicy:
    """Flee from the nearest predator when it is close; otherwise seek the nearest plant;
    otherwise cruise straight ahead (ADR-012)."""

    name = "rules"

    def __init__(self, omega_max: float, flee_threshold: float, cruise_fraction: float) -> None:
        _check_fraction("flee_threshold", flee_threshold)
        _check_fraction("cruise_fraction", cruise_fraction)
        self._omega_max = omega_max
        self._flee_threshold = flee_threshold
        self._cruise = throttle_for_speed_fraction(cruise_fraction)
        self._predator_proximity = PREY_SCHEMA.names.index("predator1_proximity")
        self._plant_proximity = PREY_SCHEMA.names.index("plant_proximity")

    def act(self, observations: np.ndarray, rng: np.random.Generator) -> np.ndarray:
        n = observations.shape[0]
        turn = np.zeros(n)
        throttle = np.full(n, self._cruise)

        flee = observations[:, self._predator_proximity] > self._flee_threshold
        seek = ~flee & (observations[:, self._plant_proximity] > 0.0)

        away = _wrap_angle(_bearing(observations, PREY_SCHEMA, "predator1") + np.pi)
        turn[flee] = _steer(away[flee], self._omega_max)
        throttle[flee] = 1.0

        towards_plant = _bearing(observations, PREY_SCHEMA, "plant")
        turn[seek] = _steer(towards_plant[seek], self._omega_max)
        throttle[seek] = 1.0
        return np.stack((turn, throttle), axis=1)


class RuleBasedPredatorPolicy:
    """Chase the nearest visible prey at full speed; otherwise cruise straight ahead."""

    name = "rules"

    def __init__(self, omega_max: float, cruise_fraction: float) -> None:
        _check_fraction("cruise_fraction", cruise_fraction)
        self._omega_max = omega_max
        self._cruise = throttle_for_speed_fraction(cruise_fraction)
        self._prey_proximity = PREDATOR_SCHEMA.names.index("prey1_proximity")

    def act(self, observations: np.ndarray, rng: np.random.Generator) -> np.ndarray:
        n = observations.shape[0]
        turn = np.zeros(n)
        throttle = np.full(n, self._cruise)
        chase = observations[:, self._prey_proximity] > 0.0
        towards_prey = _bearing(observations, PREDATOR_SCHEMA, "prey1")
        turn[chase] = _steer(towards_prey[chase], self._omega_max)
        throttle[chase] = 1.0
        return np.stack((turn, throttle), axis=1)
