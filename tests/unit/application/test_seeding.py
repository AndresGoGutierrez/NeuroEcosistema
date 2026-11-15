"""T2: seed derivation policy (ADR-028)."""

import itertools

import numpy as np
import pytest

from neuroeco.application.seeding import (
    FIELD_LIMIT,
    Purpose,
    SeedRegistry,
    Stream,
    make_key,
)

SEED = 151810796106167051982782525292607188790  # same value as configs/base.yaml


def _first_draws(generator: np.random.Generator, n: int = 4) -> tuple[int, ...]:
    return tuple(int(x) for x in generator.integers(0, 2**63, size=n))


def test_key_has_six_integer_fields_in_range() -> None:
    key = make_key(Purpose.TRAIN, 12, 3, 40, 1, Stream.ENV_INIT)
    assert key == (2, 12, 3, 40, 1, 3)
    assert all(type(field) is int and 0 <= field < FIELD_LIMIT for field in key)


@pytest.mark.parametrize(
    "bad",
    [
        {"seed_group": -1},
        {"run": FIELD_LIMIT},
        {"generation": 1.0},
        {"item": "evo"},
        {"item": True},
    ],
)
def test_invalid_fields_are_rejected(bad) -> None:
    fields = {"seed_group": 0, "run": 0, "generation": 0, "item": 0} | bad
    with pytest.raises(ValueError):
        make_key(Purpose.TRAIN, stream=Stream.GA_VARIATION, **fields)


def test_purpose_and_stream_must_be_enum_members() -> None:
    with pytest.raises(ValueError):
        make_key(2, 0, 0, 0, 0, Stream.ENV_INIT)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        make_key(Purpose.TRAIN, 0, 0, 0, 0, 3)  # type: ignore[arg-type]


@pytest.mark.parametrize("seed", [0, -5, 2**128, 1.5, True])
def test_project_seed_is_validated(seed) -> None:
    with pytest.raises(ValueError):
        SeedRegistry(seed)


def test_generator_uses_the_documented_seed_sequence() -> None:
    registry = SeedRegistry(SEED)
    expected = np.random.default_rng(np.random.SeedSequence(SEED, spawn_key=(4, 0, 0, 0, 25, 4)))
    actual = registry.generator(Purpose.TEST, 0, 0, 0, 25, Stream.ENV_DYNAMICS)
    assert _first_draws(actual) == _first_draws(expected)


def test_rederivation_is_identical() -> None:
    a = SeedRegistry(SEED).generator(Purpose.TRAIN, 7, 2, 10, 3, Stream.POLICY_PREY)
    b = SeedRegistry(SEED).generator(Purpose.TRAIN, 7, 2, 10, 3, Stream.POLICY_PREY)
    assert _first_draws(a, 16) == _first_draws(b, 16)


def test_distinct_keys_give_distinct_streams() -> None:
    registry = SeedRegistry(SEED)
    keys = list(itertools.product(Purpose, (0, 1), (0, 1), (0, 1), (0, 1), Stream))
    draws = {_first_draws(registry.generator(*key)) for key in keys}
    assert len(draws) == len(keys)


def test_purposes_are_disjoint_for_the_same_indices() -> None:
    registry = SeedRegistry(SEED)
    by_purpose = {
        purpose: _first_draws(registry.generator(purpose, 0, 0, 0, 5, Stream.ENV_INIT))
        for purpose in Purpose
    }
    assert len(set(by_purpose.values())) == len(Purpose)


def test_wrong_key_length_is_rejected() -> None:
    with pytest.raises(ValueError):
        SeedRegistry(SEED).sequence((1, 2, 3))
