"""T4 (F3): exact two-sample methods of ADR-013 (rank-sum permutation, HL shift, Cliff's delta)."""

import itertools
from fractions import Fraction

import numpy as np
import pytest
from scipy import stats

from neuroeco.analysis.stats import (
    cliffs_delta,
    hodges_lehmann_two_sample,
    mann_whitney_null_cdf,
    rank_sum_permutation_test,
)


def naive_rank_sum_p(a, b) -> Fraction:
    """Independent enumeration of all partitions with scipy average ranks."""
    pooled = np.concatenate((a, b)).astype(float)
    ranks = stats.rankdata(pooled)
    n1, n = len(a), len(pooled)
    expected = n1 * ranks.sum() / n
    observed = abs(ranks[:n1].sum() - expected)
    hits = total = 0
    for subset in itertools.combinations(range(n), n1):
        total += 1
        hits += abs(ranks[list(subset)].sum() - expected) >= observed - 1e-9
    return Fraction(hits, total)


def test_full_separation_2_over_924() -> None:
    low, high = [1, 2, 3, 4, 5, 6], [7, 8, 9, 10, 11, 12]
    result = rank_sum_permutation_test(low, high)
    assert result.p_value == Fraction(2, 924)
    assert result.u_statistic == 0
    assert rank_sum_permutation_test(high, low).u_statistic == 36


@pytest.mark.parametrize(("n1", "n2"), [(6, 6), (5, 7), (8, 8), (4, 9), (10, 10)])
def test_without_ties_matches_scipy_exact(n1, n2) -> None:
    rng = np.random.default_rng(n1 * 100 + n2)
    for _ in range(40):
        a, b = rng.normal(0, 1, n1), rng.normal(0.6, 1, n2)
        ours = rank_sum_permutation_test(a, b)
        theirs = stats.mannwhitneyu(a, b, method="exact")
        assert float(ours.p_value) == pytest.approx(theirs.pvalue)
        assert float(ours.u_statistic) == pytest.approx(theirs.statistic)


def test_with_ties_and_censoring_matches_a_naive_enumeration() -> None:
    rng = np.random.default_rng(21)
    for _ in range(60):
        a = rng.integers(0, 5, size=6)
        b = rng.integers(1, 6, size=6)
        assert rank_sum_permutation_test(a, b).p_value == naive_rank_sum_p(a, b)
    # Censored G_theta values (G + k_val = 30) produce large tie blocks.
    censored_a, censored_b = [12, 18, 30, 30, 30, 22], [9, 11, 14, 30, 10, 13]
    assert rank_sum_permutation_test(censored_a, censored_b).p_value == naive_rank_sum_p(
        censored_a, censored_b
    )


def test_all_tied_gives_p_one() -> None:
    assert rank_sum_permutation_test([3] * 6, [3] * 6).p_value == 1


def test_two_sample_interval_6x6_is_d6_d31_at_95_9_percent() -> None:
    assert mann_whitney_null_cdf(6, 6, 5) == Fraction(19, 924)
    reference = [0.3, 1.2, -0.4, 0.8, 2.1, 0.0]
    treatment = [1.0, 1.9, 0.6, 2.4, 3.3, 1.1]
    differences = sorted(t - r for r in reference for t in treatment)
    result = hodges_lehmann_two_sample(reference, treatment)
    assert result.interval.k == 6 and result.interval.level == Fraction(443, 462)
    assert (result.interval.lower, result.interval.upper) == (differences[5], differences[30])
    assert result.estimate == (differences[17] + differences[18]) / 2


@pytest.mark.parametrize(("n1", "n2"), [(6, 6), (5, 7), (8, 8)])
def test_null_cdf_matches_a_naive_enumeration(n1, n2) -> None:
    offset = n1 * (n1 + 1) // 2
    u_values = [
        sum(subset) - offset for subset in itertools.combinations(range(1, n1 + n2 + 1), n1)
    ]
    for u in range(-1, n1 * n2 + 1):
        expected = Fraction(sum(value <= u for value in u_values), len(u_values))
        assert mann_whitney_null_cdf(n1, n2, u) == expected


def test_two_sample_shift_equivariance_and_antisymmetry() -> None:
    rng = np.random.default_rng(22)
    for _ in range(50):
        reference = rng.integers(-10, 10, 6)
        treatment = rng.integers(-10, 10, 6)
        base = hodges_lehmann_two_sample(reference, treatment)
        shifted = hodges_lehmann_two_sample(reference, treatment + 4)
        assert shifted.estimate == base.estimate + 4
        assert (shifted.interval.lower, shifted.interval.upper) == (
            base.interval.lower + 4,
            base.interval.upper + 4,
        )
        swapped = hodges_lehmann_two_sample(treatment, reference)
        assert swapped.estimate == -base.estimate
        assert (swapped.interval.lower, swapped.interval.upper) == (
            -base.interval.upper,
            -base.interval.lower,
        )


def test_interval_and_rank_sum_test_are_dual_without_ties() -> None:
    rng = np.random.default_rng(23)
    excluded = 0
    for _ in range(300):
        reference, treatment = rng.normal(0, 1, 6), rng.normal(1.2, 1, 6)
        result = hodges_lehmann_two_sample(reference, treatment)
        p = rank_sum_permutation_test(reference, treatment).p_value
        assert result.interval.excludes_zero() == (p <= 1 - result.interval.level)
        excluded += result.interval.excludes_zero()
    assert 20 < excluded < 280


def test_cliffs_delta_conventions() -> None:
    assert cliffs_delta([7, 8, 9], [1, 2]) == 1
    assert cliffs_delta([1, 2], [7, 8, 9]) == -1
    rng = np.random.default_rng(24)
    for _ in range(100):
        a, b = rng.integers(0, 6, 7), rng.integers(0, 6, 5)
        delta = cliffs_delta(a, b)
        assert cliffs_delta(b, a) == -delta
        u = rank_sum_permutation_test(a, b).u_statistic  # #{a > b} + 1/2 #{a = b}
        assert delta == 2 * u / (7 * 5) - 1


def test_two_sample_size_limit() -> None:
    with pytest.raises(ValueError, match="n1 \\+ n2 <= 20"):
        rank_sum_permutation_test(range(11), range(10))
    with pytest.raises(ValueError, match="n1 \\+ n2 <= 20"):
        hodges_lehmann_two_sample(range(11), range(10))
