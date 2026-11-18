"""O1 of the P0 optimization plan (F6): bit-for-bit equivalence with the code before the change.

Condition of the author (docs/pilot_report.md): reference fingerprints of the state at every
step, recorded before the change, plus DET-1, DET-2 and DET-5 (unchanged, in tests/).
"""

import sys

import numpy as np
import pytest

from neuroeco.domain import perception
from neuroeco.domain.state import SpeciesState
from o1_reference import CASES, RECORDED, encode_nearest_before_o1, episode_fingerprint


@pytest.mark.skipif(sys.platform != "win32", reason="recorded on Windows (ADR-016)")
@pytest.mark.parametrize("case", CASES, ids=lambda c: f"{c[0]}-{c[1]}-{c[2]}-{len(c[3])}")
def test_recorded_fingerprints_are_unchanged(case) -> None:
    assert episode_fingerprint(*case) == RECORDED[case]


@pytest.mark.parametrize("case", CASES, ids=lambda c: f"{c[0]}-{c[1]}-{c[2]}-{len(c[3])}")
def test_episodes_match_the_implementation_before_o1(monkeypatch, case) -> None:
    current = episode_fingerprint(*case)
    monkeypatch.setattr(perception, "encode_nearest", encode_nearest_before_o1)
    assert episode_fingerprint(*case) == current


def test_random_states_match_bit_for_bit() -> None:
    rng = np.random.default_rng(20261117)
    size, radius = 150.0, 20.0
    for _ in range(300):
        n, m = rng.integers(0, 60), rng.integers(0, 60)
        positions = rng.uniform(0, size, (n, 2))
        # some exact coincidences and half-size separations, the delicate cases of ADR-002
        if n and m:
            positions[0] = 0.0
        observers = SpeciesState(
            positions=positions,
            headings=rng.uniform(-np.pi, np.pi, n),
            energy=rng.uniform(0, 100, n),
            alive=rng.random(n) > 0.2,
            death_step=np.zeros(n, dtype=np.int64),
            death_cause=np.zeros(n, dtype=np.int8),
        )
        targets = rng.uniform(0, size, (m, 2))
        if n and m:
            targets[0] = positions[0]
            targets[-1] = (positions[0] + size / 2) % size
        mask = rng.random(m) > 0.3
        for k in (1, 2):
            expected = encode_nearest_before_o1(observers, targets, mask, k, radius, size)
            actual = perception.encode_nearest(observers, targets, mask, k, radius, size)
            assert np.array_equal(actual, expected)
