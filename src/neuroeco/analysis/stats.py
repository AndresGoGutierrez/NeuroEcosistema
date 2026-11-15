"""Statistical methods of ADR-013, ADR-014 and ADR-017 (implementation decisions: ADR-032).

Exact methods are implemented here by enumeration and return exact ``Fraction`` p-values; the
tests compare them with scipy and with independent naive enumerations. Only the bootstrap uses
floating point (``scipy.stats.bootstrap``).

The experimental unit is the training run (ADR-017): per-run metrics enter as integer numerators
with a common denominator, so zeros and ties are detected exactly.
"""

from __future__ import annotations

import itertools
import statistics
import warnings
from collections.abc import Callable, Hashable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction
from functools import cache
from math import comb
from types import MappingProxyType

import numpy as np
from scipy import stats as scipy_stats

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


# ---------------------------------------------------------------- one-sample sensitivity (ADR-017)

MAX_ONE_SAMPLE = 12  # exact one-sample enumerations (ADR-032)


def _check_one_sample_size(n: int) -> None:
    if n > MAX_ONE_SAMPLE:
        raise ValueError(f"exact one-sample methods are limited to n <= {MAX_ONE_SAMPLE}, got {n}")


def midranks_doubled(values: Sequence[float]) -> list[int]:
    """Twice the mid-ranks (ascending) of ``values``: integers even with ties."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    doubled = [0] * len(values)
    start = 0
    while start < len(order):
        end = start
        while end + 1 < len(order) and values[order[end + 1]] == values[order[start]]:
            end += 1
        for position in range(start, end + 1):
            doubled[order[position]] = start + end + 2  # 2 * mean of ranks start+1 .. end+1
        start = end + 1
    return doubled


def _subset_sum_counts(weights: Sequence[int]) -> dict[int, int]:
    """Number of subsets of ``weights`` with each possible sum (all 2^n sign assignments)."""
    counts = {0: 1}
    for weight in weights:
        updated = dict(counts)
        for total, ways in counts.items():
            updated[total + weight] = updated.get(total + weight, 0) + ways
        counts = updated
    return counts


@dataclass(frozen=True)
class WilcoxonSignedRank:
    n_used: int  # non-zero differences
    zeros: int  # excluded (Wilcox)
    statistic: Fraction  # T+ = sum of mid-ranks of the positive differences
    p_value: Fraction  # two-sided exact permutation p


def wilcoxon_signed_rank(differences: Sequence[float]) -> WilcoxonSignedRank:
    """Exact Wilcoxon signed-rank test by enumeration of the 2^n sign assignments.

    Zeros are excluded (Wilcox); tied |d| get mid-ranks, handled as doubled integers. Two-sided
    p = P(|T - E[T]| >= |t_obs - E[T]|) under equiprobable signs (ADR-032).
    """
    data = _values(differences)
    nonzero = [d for d in data if d != 0]
    n = len(nonzero)
    _check_one_sample_size(n)
    if n == 0:
        return WilcoxonSignedRank(0, len(data), Fraction(0), Fraction(1))
    ranks = midranks_doubled([abs(d) for d in nonzero])
    total = sum(ranks)
    observed = sum(r for r, d in zip(ranks, nonzero, strict=True) if d > 0)
    distance = abs(2 * observed - total)
    extreme = sum(
        ways for s, ways in _subset_sum_counts(ranks).items() if abs(2 * s - total) >= distance
    )
    return WilcoxonSignedRank(
        n_used=n,
        zeros=len(data) - n,
        statistic=Fraction(observed, 2),
        p_value=Fraction(extreme, 2**n),
    )


@cache
def signed_rank_null_cdf(n: int, t: int) -> Fraction:
    """P(T+ <= t) for the signed-rank statistic of n untied, non-zero values."""
    if t < 0:
        return Fraction(0)
    counts = _subset_sum_counts(range(1, n + 1))
    return Fraction(sum(ways for s, ways in counts.items() if s <= t), 2**n)


def walsh_averages(data: Sequence[float]) -> list[float]:
    """Sorted (x_i + x_j) / 2 for i <= j: n(n+1)/2 values."""
    values = _values(data)
    return sorted(
        (values[i] + values[j]) / 2 for i in range(len(values)) for j in range(i, len(values))
    )


@dataclass(frozen=True)
class HodgesLehmannOneSample:
    estimate: float  # median of the Walsh averages (pseudo-median)
    interval: OrderInterval  # [W_(k), W_(M-k+1)] by inversion of the Wilcoxon test


def hodges_lehmann_one_sample(
    data: Sequence[float], confidence: Fraction = CONFIDENCE
) -> HodgesLehmannOneSample:
    """One-sample Hodges-Lehmann estimate with the exact Wilcoxon-inversion interval.

    Assumes a continuous symmetric distribution (ADR-017 sensitivity); k comes from the exact
    null distribution of T+ without ties (ADR-032).
    """
    n = len(_values(data))
    _check_one_sample_size(n)
    walsh = walsh_averages(data)
    k, level = _largest_k(len(walsh), lambda j: signed_rank_null_cdf(n, j), confidence)
    return HodgesLehmannOneSample(
        estimate=statistics.median(walsh),
        interval=OrderInterval(walsh[k - 1], walsh[len(walsh) - k], k, level),
    )


# ---------------------------------------------------------------- two samples (ADR-013)

MAX_TWO_SAMPLE_TOTAL = 20  # n1 + n2 for exact two-sample enumerations (ADR-032)


def _check_two_sample_size(n1: int, n2: int) -> None:
    if n1 + n2 > MAX_TWO_SAMPLE_TOTAL:
        raise ValueError(
            f"exact two-sample methods are limited to n1 + n2 <= {MAX_TWO_SAMPLE_TOTAL}, "
            f"got {n1} + {n2}"
        )


def _sized_subset_sum_counts(weights: Sequence[int], size: int) -> dict[int, int]:
    """Number of subsets of exactly ``size`` weights with each possible sum."""
    table: list[dict[int, int]] = [{0: 1}] + [{} for _ in range(size)]
    for weight in weights:
        for used in range(size, 0, -1):
            for total, ways in table[used - 1].items():
                table[used][total + weight] = table[used].get(total + weight, 0) + ways
    return table[size]


@dataclass(frozen=True)
class RankSumTest:
    u_statistic: Fraction  # #{a > b} + 1/2 #{a = b}
    p_value: Fraction  # two-sided exact permutation p


def rank_sum_permutation_test(a: Sequence[float], b: Sequence[float]) -> RankSumTest:
    """Exact two-sample rank-sum (Mann-Whitney) test enumerating all C(n1 + n2, n1) partitions.

    Mid-ranks as doubled integers handle ties and censored values. Two-sided
    p = P(|W - E[W]| >= |w_obs - E[W]|) over equiprobable partitions (ADR-013, ADR-032).
    """
    first, second = _values(a), _values(b)
    n1, n2 = len(first), len(second)
    _check_two_sample_size(n1, n2)
    total_n = n1 + n2
    ranks = midranks_doubled(first + second)
    total = sum(ranks)
    observed = sum(ranks[:n1])
    # |W - E[W]| with W = doubled rank sum, E[W] = n1 * total / N: compare N*W - n1*total.
    distance = abs(total_n * observed - n1 * total)
    counts = _sized_subset_sum_counts(ranks, n1)
    extreme = sum(ways for s, ways in counts.items() if abs(total_n * s - n1 * total) >= distance)
    u = Fraction(observed, 2) - Fraction(n1 * (n1 + 1), 2)
    return RankSumTest(u_statistic=u, p_value=Fraction(extreme, comb(total_n, n1)))


@cache
def mann_whitney_null_cdf(n1: int, n2: int, u: int) -> Fraction:
    """P(U <= u) for the Mann-Whitney statistic of untied samples of sizes n1 and n2."""
    if u < 0:
        return Fraction(0)
    offset = n1 * (n1 + 1) // 2
    counts = _sized_subset_sum_counts(range(1, n1 + n2 + 1), n1)
    return Fraction(sum(w for s, w in counts.items() if s - offset <= u), comb(n1 + n2, n1))


@dataclass(frozen=True)
class HodgesLehmannShift:
    estimate: float  # median of treatment - reference over all pairs
    interval: OrderInterval  # [D_(k), D_(mn-k+1)] by inversion of the Mann-Whitney test


def hodges_lehmann_two_sample(
    reference: Sequence[float], treatment: Sequence[float], confidence: Fraction = CONFIDENCE
) -> HodgesLehmannShift:
    """Shift estimate delta = treatment - reference with its exact interval (ADR-013).

    Assumes a location-shift model; k comes from the exact null distribution of U without ties.
    """
    ref, treat = _values(reference), _values(treatment)
    _check_two_sample_size(len(ref), len(treat))
    differences = sorted(t - r for r in ref for t in treat)
    k, level = _largest_k(
        len(differences), lambda j: mann_whitney_null_cdf(len(ref), len(treat), j), confidence
    )
    return HodgesLehmannShift(
        estimate=statistics.median(differences),
        interval=OrderInterval(differences[k - 1], differences[len(differences) - k], k, level),
    )


def cliffs_delta(a: Sequence[float], b: Sequence[float]) -> Fraction:
    """delta(a, b) = (#{a > b} - #{a < b}) / (n_a n_b) = 2U / (n_a n_b) - 1, exactly."""
    first, second = np.asarray(_values(a)), np.asarray(_values(b))
    signs = np.sign(first[:, np.newaxis] - second[np.newaxis, :])
    return Fraction(int(signs.sum()), first.size * second.size)


# ---------------------------------------------------------------- C2 decision rules (ADR-013)


class NonInferiority(StrEnum):
    SUPERIOR = "superior"
    NON_INFERIOR = "non_inferior"
    INFERIOR = "inferior"
    INCONCLUSIVE = "inconclusive"


def classify_noninferiority(lower: float, upper: float, margin: float) -> NonInferiority:
    """ADR-013 rule on the interval [L, U] of delta = compact - base with margin Delta > 0.

    In this order, with strict inequalities (ADR-032): L > 0 superior; L > -Delta non-inferior;
    U < -Delta inferior; otherwise inconclusive.
    """
    if not margin > 0:
        raise ValueError(f"the non-inferiority margin must be > 0, got {margin}")
    if lower > upper:
        raise ValueError(f"invalid interval [{lower}, {upper}]")
    if lower > 0:
        return NonInferiority.SUPERIOR
    if lower > -margin:
        return NonInferiority.NON_INFERIOR
    if upper < -margin:
        return NonInferiority.INFERIOR
    return NonInferiority.INCONCLUSIVE


def iqr(values: Sequence[float]) -> float:
    """Interquartile range with NumPy linear quantiles (Hyndman-Fan type 7, ADR-032)."""
    q1, q3 = np.quantile(np.asarray(_values(values), dtype=np.float64), [0.25, 0.75])
    return float(q3 - q1)


SHIFT_MODEL_IQR_RATIO = 2


def shift_model_warning(a: Sequence[float], b: Sequence[float]) -> bool:
    """True when the IQRs of the two arms differ by more than a factor of 2 (ADR-013).

    Non-inferiority is then reported "conditional on the shift model". One IQR zero and the
    other not: warning; both zero: no warning (ADR-032).
    """
    small, large = sorted((iqr(a), iqr(b)))
    if large == 0:
        return False
    if small == 0:
        return True
    return large / small > SHIFT_MODEL_IQR_RATIO


EFFICIENCY_FRACTION = Fraction(9, 10)


def efficiency_threshold(f0: float, f_base: float) -> float:
    """theta = F0 + 0.9 (F_base - F0) (ADR-013)."""
    return f0 + float(EFFICIENCY_FRACTION) * (f_base - f0)


@dataclass(frozen=True)
class GenerationsToThreshold:
    generation: int  # first evaluated generation with F_val >= theta, or G + k_val
    censored: bool


def generations_to_threshold(
    generations: Sequence[int],
    validation: Sequence[float],
    theta: float,
    total_generations: int,
    k_val: int,
) -> GenerationsToThreshold:
    """G_theta of one run: first evaluated generation reaching theta; censored at G + k_val."""
    if len(generations) != len(validation) or not generations:
        raise ValueError("generations and validation values must be non-empty and aligned")
    if any(b <= a for a, b in itertools.pairwise(generations)) or generations[0] < 0:
        raise ValueError("evaluated generations must be non-negative and strictly increasing")
    if generations[-1] > total_generations or k_val < 1:
        raise ValueError("generations must not exceed G, and k_val must be >= 1")
    values = _values(validation)
    for generation, value in zip(generations, values, strict=True):
        if value >= theta:
            return GenerationsToThreshold(int(generation), censored=False)
    return GenerationsToThreshold(total_generations + k_val, censored=True)


# ---------------------------------------------------------- bootstrap and variability (ADR-014)

BOOTSTRAP_RESAMPLES = 9999  # ADR-032, S6
BOOTSTRAP_CONFIDENCE = 0.95


def standard_deviation(values: Sequence[float]) -> float:
    """Sample standard deviation with ddof = 1 (ADR-032, S7)."""
    data = np.asarray(_values(values), dtype=np.float64)
    if data.size < 2:
        raise ValueError("the standard deviation needs at least two values")
    return float(np.std(data, ddof=1))


@dataclass(frozen=True)
class BootstrapInterval:
    estimate: float
    lower: float | None  # None when not estimable
    upper: float | None
    estimable: bool
    confidence: float
    resamples: int


def _check_generator(rng: object) -> np.random.Generator:
    if not isinstance(rng, np.random.Generator):
        raise TypeError("the bootstrap needs a numpy Generator supplied by the caller (ADR-032)")
    return rng


def _bca(
    samples: tuple[np.ndarray, ...],
    statistic: Callable[..., np.ndarray],
    estimate: float,
    rng: np.random.Generator,
    resamples: int,
    confidence: float,
) -> BootstrapInterval:
    if resamples < 1:
        raise ValueError("resamples must be >= 1")
    with warnings.catch_warnings():
        # Degenerate data (e.g. constant values) give NaN: reported as "not estimable".
        warnings.simplefilter("ignore", scipy_stats.DegenerateDataWarning)
        warnings.simplefilter("ignore", RuntimeWarning)
        result = scipy_stats.bootstrap(
            samples,
            statistic,
            n_resamples=resamples,
            confidence_level=confidence,
            method="BCa",
            paired=False,
            vectorized=True,
            rng=rng,
        )
    lower, upper = float(result.confidence_interval.low), float(result.confidence_interval.high)
    if not (np.isfinite(lower) and np.isfinite(upper)):
        return BootstrapInterval(estimate, None, None, False, confidence, resamples)
    return BootstrapInterval(estimate, lower, upper, True, confidence, resamples)


def _mean(sample: np.ndarray, axis: int = -1) -> np.ndarray:
    return np.mean(sample, axis=axis)


def paired_mean_bca(
    differences: Sequence[float],
    rng: np.random.Generator,
    resamples: int = BOOTSTRAP_RESAMPLES,
    confidence: float = BOOTSTRAP_CONFIDENCE,
) -> BootstrapInterval:
    """Mean of the paired differences with its BCa interval (ADR-014, episode level)."""
    data = np.asarray(_values(differences), dtype=np.float64)
    if data.size < 2:
        raise ValueError("the bootstrap needs at least two values")
    return _bca((data,), _mean, float(data.mean()), _check_generator(rng), resamples, confidence)


def _cliffs_delta_ranks(a: np.ndarray, b: np.ndarray, axis: int = -1) -> np.ndarray:
    """Vectorized Cliff's delta through mid-ranks: 2U / (n_a n_b) - 1 (same value as pairs)."""
    n_a, n_b = a.shape[-1], b.shape[-1]
    ranks = scipy_stats.rankdata(np.concatenate((a, b), axis=-1), axis=-1)
    u = ranks[..., :n_a].sum(axis=-1) - n_a * (n_a + 1) / 2
    return 2 * u / (n_a * n_b) - 1


def cliffs_delta_bca(
    a: Sequence[float],
    b: Sequence[float],
    rng: np.random.Generator,
    resamples: int = BOOTSTRAP_RESAMPLES,
    confidence: float = BOOTSTRAP_CONFIDENCE,
) -> BootstrapInterval:
    """Cliff's delta(a, b) with an unpaired BCa interval (ADR-020 A6; ADR-032, S3)."""
    first = np.asarray(_values(a), dtype=np.float64)
    second = np.asarray(_values(b), dtype=np.float64)
    if first.size < 2 or second.size < 2:
        raise ValueError("the bootstrap needs at least two values per sample")
    return _bca(
        (first, second),
        _cliffs_delta_ranks,
        float(cliffs_delta(first, second)),
        _check_generator(rng),
        resamples,
        confidence,
    )
