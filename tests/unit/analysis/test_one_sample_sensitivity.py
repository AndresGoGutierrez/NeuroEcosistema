"""T3 (F3): Wilcoxon signed-rank and one-sample Hodges-Lehmann (ADR-017 sensitivity, ADR-032)."""

import itertools
import statistics
from fractions import Fraction

import numpy as np
import pytest
from scipy import stats

from neuroeco.analysis.stats import (
    hodges_lehmann_one_sample,
    midranks_doubled,
    signed_rank_null_cdf,
    walsh_averages,
    wilcoxon_signed_rank,
)


def naive_wilcoxon_p(differences) -> Fraction:
    """Independent enumeration with scipy mid-ranks: P(|T - E| >= |t - E|) over all signs."""
    nonzero = [d for d in differences if d != 0]
    if not nonzero:
        return Fraction(1)
    ranks = stats.rankdata(np.abs(nonzero))  # average ranks
    expected = ranks.sum() / 2
    observed = abs(ranks[np.asarray(nonzero) > 0].sum() - expected)
    hits = 0
    for signs in itertools.product((False, True), repeat=len(nonzero)):
        t = ranks[list(signs)].sum()
        hits += abs(t - expected) >= observed - 1e-9
    return Fraction(hits, 2 ** len(nonzero))


def test_midranks_are_doubled_integers() -> None:
    assert midranks_doubled([1, 1, 2]) == [3, 3, 6]  # ranks 1.5, 1.5, 3
    assert midranks_doubled([5, 2, 9, 2, 2]) == [8, 4, 10, 4, 4]  # ranks 4, 2, 5, 2, 2
    assert midranks_doubled([3.5]) == [2]


def test_wilcoxon_without_ties_matches_scipy_exact() -> None:
    rng = np.random.default_rng(11)
    for _ in range(200):
        n = int(rng.integers(6, 13))
        d = rng.normal(0.4, 1.0, size=n)
        ours = wilcoxon_signed_rank(d)
        theirs = stats.wilcoxon(d, method="exact").pvalue
        assert float(ours.p_value) == pytest.approx(theirs)
        assert ours.n_used == n and ours.zeros == 0


def test_wilcoxon_with_ties_and_zeros_matches_a_naive_enumeration() -> None:
    rng = np.random.default_rng(12)
    for _ in range(300):
        n = int(rng.integers(6, 13))
        d = rng.integers(-3, 4, size=n)  # ties and zeros
        if np.count_nonzero(d) > 12:
            continue
        assert wilcoxon_signed_rank(d).p_value == naive_wilcoxon_p(d.tolist())


def test_wilcoxon_excludes_zeros() -> None:
    base = wilcoxon_signed_rank([3, 1, 4, 1, 5, 9, -2, 6])
    with_zeros = wilcoxon_signed_rank([3, 0, 1, 4, 1, 0, 5, 9, -2, 6])
    assert with_zeros.p_value == base.p_value and with_zeros.zeros == 2
    assert with_zeros.statistic == base.statistic == Fraction(33, 1)  # all but rank of |-2|=2
    nothing = wilcoxon_signed_rank([0, 0, 0])
    assert (nothing.n_used, nothing.p_value) == (0, 1)


def test_wilcoxon_size_limit() -> None:
    with pytest.raises(ValueError, match="n <= 12"):
        wilcoxon_signed_rank(list(range(1, 14)))
    assert wilcoxon_signed_rank(list(range(1, 13)) + [0] * 5).n_used == 12  # zeros do not count


@pytest.mark.parametrize(
    ("n", "k", "tail"),
    [
        (6, 1, Fraction(1, 64)),
        (7, 3, Fraction(3, 128)),
        (8, 4, Fraction(5, 256)),
        (9, 6, Fraction(10, 512)),
        (10, 9, Fraction(25, 1024)),
    ],
)
def test_hodges_lehmann_interval_ranks_and_levels(n, k, tail) -> None:
    assert signed_rank_null_cdf(n, k - 1) == tail
    result = hodges_lehmann_one_sample(np.arange(1.0, n + 1))
    assert result.interval.k == k and result.interval.level == 1 - 2 * tail


def test_hodges_lehmann_n6_is_min_max() -> None:
    data = [2.0, -1.0, 5.0, 3.0, 0.5, 4.0]
    result = hodges_lehmann_one_sample(data)
    assert (result.interval.lower, result.interval.upper) == (-1.0, 5.0)
    assert result.interval.level == Fraction(31, 32)


def test_hodges_lehmann_estimate_is_the_median_of_walsh_averages() -> None:
    data = [1, 4, 2, 8, 3, 3, 7]
    walsh = [(data[i] + data[j]) / 2 for i in range(7) for j in range(i, 7)]
    assert walsh_averages(data) == sorted(walsh) and len(walsh) == 28
    assert hodges_lehmann_one_sample(data).estimate == statistics.median(walsh)


def test_hodges_lehmann_is_shift_equivariant() -> None:
    rng = np.random.default_rng(13)
    for n in range(6, 11):
        data = rng.integers(-20, 20, size=n)
        base = hodges_lehmann_one_sample(data)
        shifted = hodges_lehmann_one_sample(data + 7)
        assert shifted.estimate == base.estimate + 7
        assert shifted.interval.lower == base.interval.lower + 7
        assert shifted.interval.upper == base.interval.upper + 7


def test_inverted_interval_is_dual_to_the_wilcoxon_test_without_ties() -> None:
    rng = np.random.default_rng(14)
    excluded = 0
    for _ in range(400):
        n = int(rng.integers(6, 11))
        d = rng.normal(0.8, 1.0, size=n)
        result = hodges_lehmann_one_sample(d)
        p = wilcoxon_signed_rank(d).p_value
        assert result.interval.excludes_zero() == (p <= 1 - result.interval.level)
        excluded += result.interval.excludes_zero()
    assert 20 < excluded < 380  # both outcomes exercised
