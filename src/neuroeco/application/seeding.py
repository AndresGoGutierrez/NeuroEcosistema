"""Seed derivation policy (ADR-028).

Every random stream of the project is derived from ``project_seed`` with
``numpy.random.SeedSequence(project_seed, spawn_key=key)`` where ``key`` always has six
non-negative integer fields:

    (purpose, seed_group, run, generation, item, stream)

Fields that do not apply are 0. The fixed length and the explicit ``stream`` field keep every
key unambiguous.
"""

from __future__ import annotations

from enum import IntEnum

import numpy as np

KEY_LENGTH = 6
FIELD_LIMIT = 2**32  # each field must fit in an unsigned 32-bit word
PROJECT_SEED_LIMIT = 2**128


class Purpose(IntEnum):
    PILOT = 1
    TRAIN = 2
    VALIDATION = 3
    TEST = 4
    ANALYSIS = 5


class Stream(IntEnum):
    GA_INIT = 1
    GA_VARIATION = 2
    ENV_INIT = 3
    ENV_DYNAMICS = 4
    POLICY_PREY = 5
    POLICY_PREDATOR = 6
    BOOTSTRAP = 7


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def make_key(
    purpose: Purpose,
    seed_group: int,
    run: int,
    generation: int,
    item: int,
    stream: Stream,
) -> tuple[int, int, int, int, int, int]:
    """Build and validate a six-field spawn key."""
    if not isinstance(purpose, Purpose):
        raise ValueError(f"purpose must be a Purpose member, got {purpose!r}")
    if not isinstance(stream, Stream):
        raise ValueError(f"stream must be a Stream member, got {stream!r}")
    fields = {"seed_group": seed_group, "run": run, "generation": generation, "item": item}
    for name, value in fields.items():
        if not _is_int(value) or not 0 <= value < FIELD_LIMIT:
            raise ValueError(f"{name} must be an integer in [0, 2**32), got {value!r}")
    return (int(purpose), seed_group, run, generation, item, int(stream))


class SeedRegistry:
    """Derives reproducible, independent generators from the project seed."""

    def __init__(self, project_seed: int) -> None:
        if not _is_int(project_seed) or not 0 < project_seed < PROJECT_SEED_LIMIT:
            raise ValueError("project_seed must be an integer in (0, 2**128)")
        self._project_seed = project_seed

    @property
    def project_seed(self) -> int:
        return self._project_seed

    def sequence(self, key: tuple[int, ...]) -> np.random.SeedSequence:
        if len(key) != KEY_LENGTH:
            raise ValueError(f"spawn key must have {KEY_LENGTH} fields, got {len(key)}")
        return np.random.SeedSequence(self._project_seed, spawn_key=key)

    def generator(
        self,
        purpose: Purpose,
        seed_group: int,
        run: int,
        generation: int,
        item: int,
        stream: Stream,
    ) -> np.random.Generator:
        """A fresh ``Generator`` (PCG64) for the given key."""
        key = make_key(purpose, seed_group, run, generation, item, stream)
        return np.random.default_rng(self.sequence(key))
