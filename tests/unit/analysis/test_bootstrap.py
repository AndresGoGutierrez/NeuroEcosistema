"""T6 (F3): BCa intervals (ADR-014; ADR-020 A6) and variability (ADR-032, S6 and S7)."""

import statistics
import warnings

import numpy as np
import pytest
from scipy import stats

from neuroeco.analysis.stats import (
    BOOTSTRAP_RESAMPLES,
    _cliffs_delta_ranks,
    cliffs_delta,
    cliffs_delta_bca,
    paired_mean_bca,
    standard_deviation,
)


def test_paired_mean_bca_defaults_and_agreement_with_scipy() -> None:
    d = np.random.default_rng(41).normal(0.3, 1.0, 50)
    result = paired_mean_bca(d, np.random.default_rng(7))
    assert result.estimable and result.confidence == 0.95
    assert result.resamples == BOOTSTRAP_RESAMPLES == 9999
    assert result.estimate == d.mean()
    assert result.lower < result.estimate < result.upper
    direct = stats.bootstrap(
        (d,), np.mean, method="BCa", n_resamples=9999, rng=np.random.default_rng(7)
    ).confidence_interval
    assert (result.lower, result.upper) == (direct.low, direct.high)


def test_bootstrap_is_reproducible_with_the_same_generator_seed() -> None:
    d = np.random.default_rng(42).exponential(1.0, 50) - 0.7
    first = paired_mean_bca(d, np.random.default_rng(123), resamples=999)
    second = paired_mean_bca(d, np.random.default_rng(123), resamples=999)
    other = paired_mean_bca(d, np.random.default_rng(124), resamples=999)
    assert (first.lower, first.upper) == (second.lower, second.upper)
    assert (first.lower, first.upper) != (other.lower, other.upper)
    assert first.resamples == 999


def test_constant_data_are_not_estimable_without_warnings_or_errors() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # any leaked warning fails the test
        result = paired_mean_bca([2.0] * 20, np.random.default_rng(1), resamples=500)
        delta = cliffs_delta_bca([3] * 10, [3] * 10, np.random.default_rng(1), resamples=500)
    assert not result.estimable and result.lower is None and result.upper is None
    assert result.estimate == 2.0
    assert not delta.estimable and delta.estimate == 0


def test_vectorized_cliffs_delta_equals_the_pairwise_definition() -> None:
    rng = np.random.default_rng(43)
    for _ in range(200):
        a = rng.integers(0, 6, size=int(rng.integers(2, 30))).astype(float)
        b = rng.integers(0, 6, size=int(rng.integers(2, 30))).astype(float)
        assert _cliffs_delta_ranks(a, b) == pytest.approx(float(cliffs_delta(a, b)), abs=1e-12)
    batch_a, batch_b = rng.normal(size=(4, 12)), rng.normal(size=(4, 9))
    expected = [float(cliffs_delta(x, y)) for x, y in zip(batch_a, batch_b, strict=True)]
    np.testing.assert_allclose(_cliffs_delta_ranks(batch_a, batch_b), expected, atol=1e-12)


def test_cliffs_delta_bca_unpaired() -> None:
    rng = np.random.default_rng(44)
    a, b = rng.normal(0.5, 1, 50), rng.normal(0.0, 1, 50)
    result = cliffs_delta_bca(a, b, np.random.default_rng(9), resamples=1999)
    assert result.estimable and result.estimate == float(cliffs_delta(a, b))
    assert -1 <= result.lower <= result.estimate <= result.upper <= 1
    again = cliffs_delta_bca(a, b, np.random.default_rng(9), resamples=1999)
    assert (again.lower, again.upper) == (result.lower, result.upper)


@pytest.mark.parametrize("rng", [7, None, np.random.RandomState(7)])
def test_bootstrap_requires_a_generator_from_the_caller(rng) -> None:
    with pytest.raises(TypeError, match="Generator"):
        paired_mean_bca([1.0, 2.0, 3.0], rng)


def test_bootstrap_input_validation() -> None:
    with pytest.raises(ValueError):
        paired_mean_bca([1.0], np.random.default_rng(1))
    with pytest.raises(ValueError):
        cliffs_delta_bca([1.0], [2.0, 3.0], np.random.default_rng(1))
    with pytest.raises(ValueError):
        paired_mean_bca([1.0, 2.0], np.random.default_rng(1), resamples=0)


def test_standard_deviation_uses_ddof_1() -> None:
    data = [2, 4, 4, 4, 5, 5, 7, 9]
    assert standard_deviation(data) == pytest.approx(statistics.stdev(data))
    assert standard_deviation(data) == pytest.approx(np.std(data, ddof=1))
    with pytest.raises(ValueError):
        standard_deviation([3.0])
