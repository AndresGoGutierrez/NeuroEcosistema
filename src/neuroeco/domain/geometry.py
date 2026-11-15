"""Toroidal geometry (ADR-002) and egocentric bearings (ADR-007).

Conventions:

- Positions live in [0, size) on both axes; angles are in radians, counterclockwise, with the
  y axis pointing up. Headings are stored in [0, 2*pi).
- The minimal-image displacement of each component lies in [-size/2, size/2). A component of
  exactly size/2 maps to -size/2, so the convention is deterministic.
- The relative bearing phi of a target is measured from the agent's heading: sin(phi) > 0 means
  the target is to the agent's left and cos(phi) > 0 means it is in front.
"""

from __future__ import annotations

import numpy as np

TWO_PI = 2.0 * np.pi
EPSILON = 1e-12


def wrap_positions(positions: np.ndarray, size: float) -> np.ndarray:
    """Map positions onto the torus, guaranteeing the half-open range [0, size)."""
    wrapped = np.mod(positions, size)
    # np.mod can return exactly `size` for tiny negative inputs because of rounding.
    return np.where(wrapped >= size, wrapped - size, wrapped)


def wrap_headings(headings: np.ndarray) -> np.ndarray:
    """Map angles onto [0, 2*pi)."""
    wrapped = np.mod(headings, TWO_PI)
    return np.where(wrapped >= TWO_PI, wrapped - TWO_PI, wrapped)


def minimal_displacement(origins: np.ndarray, targets: np.ndarray, size: float) -> np.ndarray:
    """Minimal-image displacement from every origin (n, 2) to every target (m, 2): (n, m, 2)."""
    half = size / 2.0
    delta = targets[np.newaxis, :, :] - origins[:, np.newaxis, :]
    return np.mod(delta + half, size) - half


def pairwise_distances(origins: np.ndarray, targets: np.ndarray, size: float) -> np.ndarray:
    """Toroidal Euclidean distance from every origin to every target: (n, m)."""
    delta = minimal_displacement(origins, targets, size)
    return np.hypot(delta[..., 0], delta[..., 1])


def relative_bearing(
    displacements: np.ndarray, headings: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Return (cos(phi), sin(phi)) of each displacement relative to its agent's heading.

    ``displacements`` has shape (n, ..., 2) and ``headings`` shape (n,). When a displacement
    is shorter than EPSILON the bearing is undefined and (1, 0) ("straight ahead") is
    returned (ADR-007).
    """
    dx = displacements[..., 0]
    dy = displacements[..., 1]
    extra_axes = (1,) * (dx.ndim - 1)
    cos_h = np.cos(headings).reshape(-1, *extra_axes)
    sin_h = np.sin(headings).reshape(-1, *extra_axes)
    distance = np.hypot(dx, dy)
    degenerate = distance < EPSILON
    safe = np.where(degenerate, 1.0, distance)
    forward = (dx * cos_h + dy * sin_h) / safe
    left = (-dx * sin_h + dy * cos_h) / safe
    return np.where(degenerate, 1.0, forward), np.where(degenerate, 0.0, left)
