"""T1 (F3): per-run data and protection against pseudo-replication (ADR-017, ADR-032)."""

import numpy as np
import pytest

from neuroeco.analysis.stats import (
    PseudoReplicationError,
    RunValues,
    paired_differences,
    sign_counts,
)


def test_repeated_run_ids_are_rejected() -> None:
    # Episodes passed without aggregating them per run repeat the run identifier.
    episodes = [("r0", 410), ("r0", 395), ("r1", 402)]
    with pytest.raises(PseudoReplicationError, match="'r0' appears more than once"):
        RunValues.from_pairs(episodes)


@pytest.mark.parametrize("value", [0.5, 1.0, True, "3", None])
def test_values_must_be_integer_numerators(value) -> None:
    with pytest.raises(TypeError, match="integer numerator"):
        RunValues.from_pairs([("r0", value)])


def test_numpy_integers_are_accepted_and_stored_as_int() -> None:
    runs = RunValues.from_pairs([("r0", np.int64(7)), ("r1", np.int32(-2))])
    assert runs.values == {"r0": 7, "r1": -2}
    assert all(type(v) is int for v in runs.values.values())
    assert runs.run_ids == ("r0", "r1") and len(runs) == 2


def test_run_values_are_immutable_and_not_empty() -> None:
    runs = RunValues.from_pairs([(0, 1)])
    with pytest.raises(TypeError):
        runs.values[1] = 2  # type: ignore[index]
    with pytest.raises(ValueError):
        RunValues.from_pairs([])


def test_paired_differences_are_exact_and_follow_the_before_order() -> None:
    before = RunValues.from_pairs([(2, 100), (0, 250), (1, 300)])
    after = RunValues.from_pairs([(0, 250), (1, 301), (2, 97)])
    assert paired_differences(before, after) == (-3, 0, 1)


def test_pairing_requires_the_same_runs() -> None:
    before = RunValues.from_pairs([(0, 1), (1, 2)])
    after = RunValues.from_pairs([(0, 1), (2, 2)])
    with pytest.raises(ValueError, match=r"only before: \[1\], only after: \[2\]"):
        paired_differences(before, after)


def test_sign_counts_detect_zeros_and_ties_exactly() -> None:
    counts = sign_counts([3, 0, -1, 0, 3, 5, 0])
    assert (counts.positive, counts.zero, counts.negative, counts.n) == (3, 3, 1, 7)
    # Large integers keep exact zero detection.
    big = 10**15
    assert sign_counts([big + 1 - big, big - big]).zero == 1


@pytest.mark.parametrize("bad", [[], [[1, 2]], [1.0, float("nan")], [float("inf")]])
def test_sign_counts_reject_invalid_input(bad) -> None:
    with pytest.raises(ValueError):
        sign_counts(bad)
