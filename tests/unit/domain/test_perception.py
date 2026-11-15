"""T7: sensors and action decoding (ADR-007, ADR-012)."""

import numpy as np
import pytest

from neuroeco.application.seeding import Purpose, SeedRegistry
from neuroeco.domain.actions import decode_actions
from neuroeco.domain.perception import (
    PREDATOR_SCHEMA,
    PREY_SCHEMA,
    encode_nearest,
    observe_predators,
    observe_prey,
)
from neuroeco.domain.state import SpeciesState, initialize_world
from support import PROVISIONAL_PREY

R = 20.0
SIZE = 150.0


def observer(x=50.0, y=50.0, heading=0.0) -> SpeciesState:
    return SpeciesState.create(np.array([[x, y]]), np.array([heading]), PROVISIONAL_PREY)


def encode(observers, targets, mask=None, k=2):
    targets = np.array(targets, dtype=float).reshape(-1, 2)
    mask = np.ones(targets.shape[0], dtype=bool) if mask is None else np.array(mask)
    return encode_nearest(observers, targets, mask, k, R, SIZE)


def test_schemas_have_the_documented_sizes_and_unique_names() -> None:
    assert PREY_SCHEMA.size == 10 and PREDATOR_SCHEMA.size == 7
    assert PREY_SCHEMA.names[:3] == ("plant_proximity", "plant_left", "plant_forward")
    assert PREY_SCHEMA.names[-1] == PREDATOR_SCHEMA.names[-1] == "energy"
    for schema in (PREY_SCHEMA, PREDATOR_SCHEMA):
        assert len(set(schema.names)) == schema.size
        assert schema.version == 1


def test_object_ahead_and_to_the_left() -> None:
    ahead = encode(observer(), [[60.0, 50.0]], k=1)[0]  # d = 10 -> p = 0.5
    np.testing.assert_allclose(ahead, [0.5, 0.0, 0.5], atol=1e-12)
    left = encode(observer(), [[50.0, 55.0]], k=1)[0]  # d = 5 -> p = 0.75
    np.testing.assert_allclose(left, [0.75, 0.75, 0.0], atol=1e-12)


def test_nothing_perceived_beyond_the_vision_radius() -> None:
    np.testing.assert_array_equal(encode(observer(), [[50.0 + R + 0.01, 50.0]], k=1)[0], 0.0)


def test_encoding_is_continuous_at_the_vision_boundary() -> None:
    inside = encode(observer(), [[50.0 + R - 1e-6, 50.0]], k=1)[0]
    outside = encode(observer(), [[50.0 + R + 1e-6, 50.0]], k=1)[0]
    assert np.max(np.abs(inside - outside)) < 1e-6


def test_nearest_first_with_ties_broken_by_index() -> None:
    values = encode(observer(), [[58.0, 50.0], [55.0, 50.0], [50.0, 45.0]])[0]
    # Targets 1 (d=5, ahead) and 2 (d=5, right) tie: index 1 comes first.
    np.testing.assert_allclose(values[:3], [0.75, 0.0, 0.75], atol=1e-12)
    np.testing.assert_allclose(values[3:], [0.75, -0.75, 0.0], atol=1e-12)


def test_fewer_targets_than_k_are_zero_padded_and_masks_apply() -> None:
    values = encode(observer(), [[55.0, 50.0], [52.0, 50.0]], mask=[True, False])[0]
    np.testing.assert_allclose(values[:3], [0.75, 0.0, 0.75], atol=1e-12)
    np.testing.assert_array_equal(values[3:], 0.0)


def test_dead_observers_get_zero_rows() -> None:
    dead = observer()
    dead.alive[0] = False
    np.testing.assert_array_equal(encode(dead, [[55.0, 50.0]]), 0.0)


def test_perception_across_the_boundary() -> None:
    values = encode(observer(x=149.0), [[4.0, 50.0]], k=1)[0]  # 5 units ahead through the edge
    np.testing.assert_allclose(values, [0.75, 0.0, 0.75], atol=1e-12)


@pytest.mark.parametrize("item", range(3))
def test_full_observations_have_valid_shapes_and_ranges(world_params, item) -> None:
    params = world_params()
    world = initialize_world(
        params, SeedRegistry(1234567).episode_streams(Purpose.TEST, 0, 0, 0, item)
    )
    prey_obs = observe_prey(world, params)
    predator_obs = observe_predators(world, params)
    assert prey_obs.shape == (params.n_prey, PREY_SCHEMA.size)
    assert predator_obs.shape == (params.n_predators, PREDATOR_SCHEMA.size)
    for obs in (prey_obs, predator_obs):
        proximity = obs[:, 0:-1:3]
        directional = np.delete(obs[:, :-1], np.s_[0::3], axis=1)
        assert np.all((proximity >= 0) & (proximity <= 1))
        assert np.all((directional >= -1) & (directional <= 1))
        assert np.all((obs[:, -1] > 0) & (obs[:, -1] <= 1))


# ------------------------------------------------------------------ action decoding


def test_decoder_maps_raw_outputs_to_turn_and_speed() -> None:
    raw = np.array([[1.0, 1.0], [-1.0, -1.0], [0.5, 0.0]])
    turns, speeds = decode_actions(raw, PROVISIONAL_PREY)  # omega 0.5, v_max 1.0
    np.testing.assert_allclose(turns, [0.5, -0.5, 0.25])
    np.testing.assert_allclose(speeds, [1.0, 0.0, 0.5])


@pytest.mark.parametrize(
    "raw",
    [np.array([[1.1, 0.0]]), np.array([[0.0, np.nan]]), np.array([0.0, 0.0]), np.zeros((1, 3))],
)
def test_decoder_rejects_invalid_outputs(raw) -> None:
    with pytest.raises(ValueError):
        decode_actions(raw, PROVISIONAL_PREY)
