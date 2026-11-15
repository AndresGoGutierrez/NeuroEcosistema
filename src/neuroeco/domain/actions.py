"""Decoding of raw policy outputs into movement (ADR-012, ADR-025).

Every policy (random, rule-based, constant probes and, later, neural) outputs raw actions in
[-1, 1]^2 and shares this decoder:

- turn  = o0 * omega_max            (positive: counterclockwise / left)
- speed = v_max * (o1 + 1) / 2      in [0, v_max]
"""

from __future__ import annotations

import numpy as np

from neuroeco.domain.params import SpeciesParams

RAW_ACTION_SIZE = 2
TOLERANCE = 1e-12


def decode_actions(raw: np.ndarray, species: SpeciesParams) -> tuple[np.ndarray, np.ndarray]:
    """Return (turns, speeds). Out-of-range or non-finite outputs are a policy bug: rejected."""
    if raw.ndim != 2 or raw.shape[1] != RAW_ACTION_SIZE:
        raise ValueError(f"raw actions must have shape (n, {RAW_ACTION_SIZE}), got {raw.shape}")
    if not np.all(np.isfinite(raw)) or np.any(np.abs(raw) > 1.0 + TOLERANCE):
        raise ValueError("raw actions must be finite and lie in [-1, 1]")
    bounded = np.clip(raw, -1.0, 1.0)  # removes only rounding noise within TOLERANCE
    turns = bounded[:, 0] * species.omega_max
    speeds = species.v_max * (bounded[:, 1] + 1.0) / 2.0
    return turns, speeds
