"""T3: toroidal geometry and egocentric bearings (ADR-002, ADR-007)."""

import numpy as np
import pytest

from neuroeco.domain.geometry import (
    EPSILON,
    TWO_PI,
    minimal_displacement,
    pairwise_distances,
    relative_bearing,
    wrap_headings,
    wrap_positions,
)

SIZE = 150.0


def test_wrap_positions_is_half_open() -> None:
    raw = np.array([[-1e-17, 150.0], [151.0, -1.0], [75.0, 0.0]])
    wrapped = wrap_positions(raw, SIZE)
    assert np.all(wrapped >= 0.0) and np.all(wrapped < SIZE)
    np.testing.assert_allclose(wrapped[1], [1.0, 149.0])
    assert wrapped[0, 1] == 0.0


def test_wrap_headings_range() -> None:
    wrapped = wrap_headings(np.array([-1e-17, TWO_PI, 3 * TWO_PI + 0.5, -0.5]))
    assert np.all(wrapped >= 0.0) and np.all(wrapped < TWO_PI)
    np.testing.assert_allclose(wrapped[2], 0.5)
    np.testing.assert_allclose(wrapped[3], TWO_PI - 0.5)


def test_minimal_displacement_crosses_the_boundary() -> None:
    origin = np.array([[149.0, 1.0]])
    target = np.array([[1.0, 149.0]])
    np.testing.assert_allclose(minimal_displacement(origin, target, SIZE)[0, 0], [2.0, -2.0])


def test_minimal_displacement_is_antisymmetric_away_from_half_size() -> None:
    rng = np.random.default_rng(0)
    a = rng.uniform(0, SIZE, size=(20, 2))
    b = rng.uniform(0, SIZE, size=(20, 2))
    forward = minimal_displacement(a, b, SIZE)
    backward = minimal_displacement(b, a, SIZE)
    np.testing.assert_allclose(forward, -np.transpose(backward, (1, 0, 2)), atol=1e-9)
    assert np.all(np.abs(forward) <= SIZE / 2)


def test_half_size_component_follows_the_documented_convention() -> None:
    a = np.array([[0.0, 0.0]])
    b = np.array([[75.0, 0.0]])
    assert minimal_displacement(a, b, SIZE)[0, 0, 0] == -75.0
    assert minimal_displacement(b, a, SIZE)[0, 0, 0] == -75.0
    assert pairwise_distances(a, b, SIZE)[0, 0] == pairwise_distances(b, a, SIZE)[0, 0] == 75.0


def test_distances_are_bounded_and_shaped() -> None:
    rng = np.random.default_rng(1)
    d = pairwise_distances(rng.uniform(0, SIZE, (7, 2)), rng.uniform(0, SIZE, (5, 2)), SIZE)
    assert d.shape == (7, 5)
    assert np.all(d >= 0.0) and np.all(d <= SIZE / np.sqrt(2) + 1e-9)


@pytest.mark.parametrize(
    ("heading", "displacement", "expected_forward", "expected_left"),
    [
        (0.0, [1.0, 0.0], 1.0, 0.0),  # ahead
        (0.0, [0.0, 1.0], 0.0, 1.0),  # left (counterclockwise)
        (0.0, [0.0, -1.0], 0.0, -1.0),  # right
        (0.0, [-1.0, 0.0], -1.0, 0.0),  # behind
        (np.pi / 2, [0.0, 3.0], 1.0, 0.0),  # facing +y, target ahead
        (np.pi / 2, [-2.0, 0.0], 0.0, 1.0),  # facing +y, target to the left
    ],
)
def test_bearing_sign_convention(heading, displacement, expected_forward, expected_left) -> None:
    forward, left = relative_bearing(np.array([displacement]), np.array([heading]))
    np.testing.assert_allclose([forward[0], left[0]], [expected_forward, expected_left], atol=1e-12)


def test_bearing_is_a_unit_vector() -> None:
    rng = np.random.default_rng(2)
    displacements = rng.normal(size=(6, 4, 2))
    forward, left = relative_bearing(displacements, rng.uniform(0, TWO_PI, 6))
    np.testing.assert_allclose(forward**2 + left**2, 1.0)


def test_degenerate_displacement_points_straight_ahead() -> None:
    forward, left = relative_bearing(np.array([[EPSILON / 2, 0.0]]), np.array([1.0]))
    assert (forward[0], left[0]) == (1.0, 0.0)


def test_bearing_across_the_boundary() -> None:
    # Agent at x=149 facing +x; target at x=1 is 2 units ahead through the boundary.
    displacement = minimal_displacement(np.array([[149.0, 10.0]]), np.array([[1.0, 10.0]]), SIZE)
    forward, left = relative_bearing(displacement, np.array([0.0]))
    np.testing.assert_allclose([forward[0, 0], left[0, 0]], [1.0, 0.0], atol=1e-12)
