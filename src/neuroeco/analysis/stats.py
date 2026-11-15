"""Statistical methods of ADR-013, ADR-014 and ADR-017 (implementation decisions: ADR-032).

Exact methods are implemented here by enumeration and return exact ``Fraction`` p-values; the
tests compare them with scipy and with independent naive enumerations. Only the bootstrap uses
floating point (``scipy.stats.bootstrap``).

The experimental unit is the training run (ADR-017): per-run metrics enter as integer numerators
with a common denominator, so zeros and ties are detected exactly.
"""

from __future__ import annotations

import statistics
from collections.abc import Callable, Hashable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from functools import cache
from math import comb
from types import MappingProxyType

import numpy as np

CONFIDENCE = Fraction(95, 100)

# ---------------------------------------------------------------- per-run data (ADR-017)


class PseudoReplicationError(ValueError):
    """The same run appears more than once: episodes must be aggregated per run first."""


def _check_integer(value: object, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int | np.integer):
        raise TypeError(f"{what} must be an integer numerator, got {value!r}")
    return int(value)


@dataclass(frozen=True)
class RunValues:
    """One integer numerator per training run, in insertion order."""

    values: Mapping[Hashable, int]

    @classmethod
    def from_pairs(cls, pairs: Iterable[tuple[Hashable, object]]) -> RunValues:
        values: dict[Hashable, int] = {}
        for run_id, value in pairs:
            if run_id in values:
                raise PseudoReplicationError(
                    f"run {run_id!r} appears more than once; the experimental unit is the run "
                    "(ADR-017): aggregate its episodes before the analysis"
                )
            values[run_id] = _check_integer(value, f"value of run {run_id!r}")
        if not values:
            raise ValueError("at least one run is required")
        return cls(MappingProxyType(values))

    @property
    def run_ids(self) -> tuple[Hashable, ...]:
        return tuple(self.values)

    def __len__(self) -> int:
        return len(self.values)


def paired_differences(before: RunValues, after: RunValues) -> tuple[int, ...]:
    """d_r = after_r - before_r for every run, in the order of ``before`` (exact integers)."""
    missing = [r for r in before.run_ids if r not in after.values]
    extra = [r for r in after.run_ids if r not in before.values]
    if missing or extra:
        raise ValueError(
            f"before and after must contain the same runs; only before: {missing}, "
            f"only after: {extra}"
        )
    return tuple(after.values[r] - before.values[r] for r in before.run_ids)


@dataclass(frozen=True)
class SignCounts:
    positive: int
    zero: int
    negative: int

    @property
    def n(self) -> int:
        return self.positive + self.zero + self.negative


def sign_counts(differences: Sequence[float]) -> SignCounts:
    """k+, k0 and k- of the differences (exact for integers)."""
    data = np.asarray(differences)
    if data.ndim != 1 or data.size == 0:
        raise ValueError("differences must be a non-empty one-dimensional sequence")
    if not np.all(np.isfinite(data)):
        raise ValueError("differences must be finite")
    return SignCounts(
        positive=int(np.count_nonzero(data > 0)),
        zero=int(np.count_nonzero(data == 0)),
        negative=int(np.count_nonzero(data < 0)),
    )


def _values(data: Sequence[float]) -> list:
    """Finite one-dimensional data as plain Python numbers (ints stay exact)."""
    array = np.asarray(data)
    if array.ndim != 1 or array.size == 0:
        raise ValueError("data must be a non-empty one-dimensional sequence")
    if not np.all(np.isfinite(array)):
        raise ValueError("data must be finite")
    return array.tolist()


# ---------------------------------------------------------------- sign test (ADR-017)


@cache
def binomial_cdf_half(n: int, k: int) -> Fraction:
    """P(B <= k) for B ~ Bin(n, 1/2), exactly."""
    if k < 0:
        return Fraction(0)
    if k >= n:
        return Fraction(1)
    return Fraction(sum(comb(n, i) for i in range(k + 1)), 2**n)


def binomial_sf_half(n: int, k: int) -> Fraction:
    """P(B >= k) for B ~ Bin(n, 1/2), exactly."""
    return 1 - binomial_cdf_half(n, k - 1)


@dataclass(frozen=True)
class SignTest:
    counts: SignCounts
    p_value: Fraction  # two-sided, unconditional


def sign_test(differences: Sequence[float]) -> SignTest:
    """Exact unconditional sign test (ADR-017): zeros count against both sides.

    H0: 0 is a median of d. p = min{1, 2 * min[P(B >= k+), P(B >= k-)]}, B ~ Bin(n, 1/2),
    with n including the zeros. No mid-p.
    """
    counts = sign_counts(differences)
    n = counts.n
    tail = min(binomial_sf_half(n, counts.positive), binomial_sf_half(n, counts.negative))
    return SignTest(counts, min(Fraction(1), 2 * tail))


@dataclass(frozen=True)
class OrderInterval:
    """Exact interval [x_(k), x_(N-k+1)] from ordered values, with its attained level."""

    lower: float
    upper: float
    k: int
    level: Fraction

    def contains(self, value: float) -> bool:
        return self.lower <= value <= self.upper

    def excludes_zero(self) -> bool:
        return self.lower > 0 or self.upper < 0


def _largest_k(
    count: int, tail: Callable[[int], Fraction], confidence: Fraction
) -> tuple[int, Fraction]:
    """Largest k whose interval [x_(k), x_(count-k+1)] has level 1 - 2*tail(k-1) >= confidence."""
    best: tuple[int, Fraction] | None = None
    for k in range(1, count // 2 + 1):
        level = 1 - 2 * tail(k - 1)
        if level < confidence:
            break
        best = (k, level)
    if best is None:
        raise ValueError(f"no exact interval reaches the {float(confidence):.1%} level")
    return best


def sign_interval_rank(n: int, confidence: Fraction = CONFIDENCE) -> tuple[int, Fraction]:
    """k and attained level of the sign interval for the median of n values (ADR-017, ADR-032)."""
    return _largest_k(n, lambda j: binomial_cdf_half(n, j), confidence)


def median_sign_interval(
    differences: Sequence[float], confidence: Fraction = CONFIDENCE
) -> OrderInterval:
    """Exact distribution-free interval for a median, [d_(k), d_(n-k+1)], zeros included.

    Valid for continuous and discrete data because the interval is closed.
    """
    data = sorted(_values(differences))
    k, level = sign_interval_rank(len(data), confidence)
    return OrderInterval(data[k - 1], data[len(data) - k], k, level)


@dataclass(frozen=True)
class SignAnalysis:
    """Per-scenario estimation and confirmatory test of ADR-017."""

    counts: SignCounts
    median: float
    interval: OrderInterval
    p_value: Fraction


def sign_analysis(differences: Sequence[float], confidence: Fraction = CONFIDENCE) -> SignAnalysis:
    test = sign_test(differences)
    return SignAnalysis(
        counts=test.counts,
        median=statistics.median(_values(differences)),
        interval=median_sign_interval(differences, confidence),
        p_value=test.p_value,
    )


# ---------------------------------------------------------------- Holm (ADR-017)


def holm(p_values: Sequence[Fraction | int], m: int | None = None) -> tuple[Fraction, ...]:
    """Holm-adjusted p-values in the input order, with a fixed family size m >= len(p).

    p~_(i) = max_{j <= i} min(1, (m - j + 1) * p_(j)), computed exactly.
    """
    for p in p_values:
        if isinstance(p, bool) or not isinstance(p, Fraction | int):
            raise TypeError(f"p-values must be exact (Fraction or int), got {p!r}")
        if not 0 <= p <= 1:
            raise ValueError(f"p-values must lie in [0, 1], got {p}")
    size = len(p_values)
    family = size if m is None else m
    if family < size:
        raise ValueError(f"the family size m = {family} is smaller than the {size} p-values")
    order = sorted(range(size), key=lambda i: p_values[i])
    adjusted: list[Fraction] = [Fraction(0)] * size
    running = Fraction(0)
    for rank, index in enumerate(order):
        running = max(running, min(Fraction(1), (family - rank) * Fraction(p_values[index])))
        adjusted[index] = running
    return tuple(adjusted)
