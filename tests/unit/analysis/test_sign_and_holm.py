"""T2 (F3): exact sign test, sign interval for the median and Holm (ADR-017, ADR-032)."""

from fractions import Fraction

import numpy as np
import pytest
from scipy import stats

from neuroeco.analysis.stats import (
    binomial_cdf_half,
    binomial_sf_half,
    holm,
    median_sign_interval,
    sign_analysis,
    sign_interval_rank,
    sign_test,
)

# ---------------------------------------------------------------- sign test


@pytest.mark.parametrize(
    ("differences", "expected"),
    [
        ([1] * 8, Fraction(2, 256)),  # R = 8, 8 positive
        ([1] * 7 + [0], Fraction(18, 256)),  # R = 8, 7 positive and 1 zero
        ([1] * 9 + [0], Fraction(22, 1024)),  # R = 10, 9 positive and 1 zero
        ([1] * 8 + [0, 0], Fraction(112, 1024)),  # R = 10, 8 positive and 2 zeros
    ],
)
def test_sign_test_reference_cases(differences, expected) -> None:
    assert sign_test(differences).p_value == expected  # exact equality (ADR-017)


def test_sign_test_is_symmetric_and_capped_at_one() -> None:
    assert sign_test([-3] * 8).p_value == Fraction(2, 256)
    assert sign_test([2, -2, 5, -1, 4, -7, 1, -1]).p_value == 1
    assert sign_test([0] * 6).p_value == 1  # zeros count against both sides
    result = sign_test([4, 0, -1, 2, 2, 0, 3])
    assert (result.counts.positive, result.counts.zero, result.counts.negative) == (4, 2, 1)


@pytest.mark.parametrize("n", range(1, 21))
def test_binomial_tails_match_scipy(n) -> None:
    for k in range(-1, n + 2):
        assert float(binomial_cdf_half(n, k)) == pytest.approx(stats.binom.cdf(k, n, 0.5))
        assert float(binomial_sf_half(n, k)) == pytest.approx(stats.binom.sf(k - 1, n, 0.5))


def test_sign_test_matches_an_independent_scipy_computation() -> None:
    rng = np.random.default_rng(17)
    for _ in range(300):
        n = int(rng.integers(6, 13))
        d = rng.integers(-2, 3, size=n)
        result = sign_test(d)
        k_pos, k_neg = int((d > 0).sum()), int((d < 0).sum())
        expected = min(
            1.0, 2 * min(stats.binom.sf(k_pos - 1, n, 0.5), stats.binom.sf(k_neg - 1, n, 0.5))
        )
        assert float(result.p_value) == pytest.approx(expected)


# ---------------------------------------------------------------- sign interval


@pytest.mark.parametrize(
    ("n", "k", "level"),
    [
        (6, 1, Fraction(31, 32)),  # 96.9 %
        (7, 1, Fraction(63, 64)),  # 98.4 %
        (8, 1, Fraction(127, 128)),  # 99.2 %
        (9, 2, Fraction(123, 128)),  # 96.1 %
        (10, 2, Fraction(501, 512)),  # 97.9 %
    ],
)
def test_sign_interval_levels_n6_to_n10(n, k, level) -> None:
    assert sign_interval_rank(n) == (k, level)


def test_sign_interval_rank_is_the_largest_k_reaching_95_percent() -> None:
    for n in range(6, 31):
        k, level = sign_interval_rank(n)
        assert level >= Fraction(95, 100)
        assert level == 1 - 2 * binomial_cdf_half(n, k - 1)
        if k + 1 <= n // 2:
            assert 1 - 2 * binomial_cdf_half(n, k) < Fraction(95, 100)
    with pytest.raises(ValueError, match="no exact interval"):
        sign_interval_rank(5)  # [min, max] only reaches 93.75 %


def test_sign_interval_uses_the_right_order_statistics() -> None:
    interval = median_sign_interval([5, -1, 3, 0, 2, 2, 7, 1, 4])  # n = 9 -> k = 2
    assert (interval.lower, interval.upper, interval.k) == (0, 5, 2)
    interval = median_sign_interval([3, 0, 0, 2, 9, 1])  # n = 6 -> [min, max], zeros included
    assert (interval.lower, interval.upper) == (0, 9)
    assert not interval.excludes_zero() and interval.contains(0)
    assert type(interval.lower) is int  # integers stay exact


def test_sign_interval_and_test_are_dual_on_integer_data_with_zeros_and_ties() -> None:
    """The interval excludes 0 exactly when p <= 1 - attained level (n = 6...12)."""
    rng = np.random.default_rng(2026)
    excluded = included = 0
    for n in range(6, 13):
        for _ in range(2000):
            d = rng.integers(-2, 4, size=n)  # many zeros and ties
            analysis = sign_analysis(d)
            rejects = analysis.p_value <= 1 - analysis.interval.level
            assert analysis.interval.excludes_zero() == rejects, (n, d.tolist())
            excluded += rejects
            included += not rejects
    assert excluded > 100 and included > 100  # both outcomes exercised


def test_sign_analysis_reports_counts_median_interval_and_p() -> None:
    analysis = sign_analysis([4, 0, -1, 2, 2, 0, 3, 5])
    assert analysis.median == 2
    assert analysis.interval.level == Fraction(127, 128)
    assert analysis.p_value == sign_test([4, 0, -1, 2, 2, 0, 3, 5]).p_value


# ---------------------------------------------------------------- Holm


def test_holm_textbook_example() -> None:
    raw = [Fraction(1, 100), Fraction(4, 100), Fraction(3, 100), Fraction(5, 1000)]
    # sorted: 0.005, 0.01, 0.03, 0.04 -> 4*0.005, 3*0.01, 2*0.03, max(0.06, 1*0.04)
    assert holm(raw) == (Fraction(3, 100), Fraction(6, 100), Fraction(6, 100), Fraction(2, 100))


def test_holm_adjusted_p_are_monotone_and_bounded() -> None:
    rng = np.random.default_rng(5)
    for _ in range(500):
        size = int(rng.integers(1, 7))
        raw = [Fraction(int(rng.integers(0, 1025)), 1024) for _ in range(size)]
        m = size + int(rng.integers(0, 3))
        adjusted = holm(raw, m)
        order = sorted(range(size), key=lambda i: raw[i])
        sequence = [adjusted[i] for i in order]
        assert sequence == sorted(sequence)  # non-decreasing in the order of the raw p
        assert all(raw[i] <= adjusted[i] <= 1 for i in range(size))


def test_holm_uses_the_fixed_family_size() -> None:
    raw = [Fraction(1, 100), Fraction(2, 100), Fraction(3, 100)]
    assert holm(raw, m=6) == (Fraction(6, 100), Fraction(10, 100), Fraction(12, 100))
    with pytest.raises(ValueError, match="family size"):
        holm(raw, m=2)


@pytest.mark.parametrize("bad", [[0.01], [True], [Fraction(3, 2)], [Fraction(-1, 10)]])
def test_holm_requires_exact_probabilities(bad) -> None:
    with pytest.raises((TypeError, ValueError)):
        holm(bad)
