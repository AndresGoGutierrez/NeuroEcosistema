"""T5 (F3): C2 decision rules of ADR-013 (non-inferiority, shift-model warning, theta, G_theta)."""

import numpy as np
import pytest

from neuroeco.analysis.stats import (
    GenerationsToThreshold,
    NonInferiority,
    classify_noninferiority,
    efficiency_threshold,
    generations_to_threshold,
    iqr,
    shift_model_warning,
)

S, NI, INF, INC = (
    NonInferiority.SUPERIOR,
    NonInferiority.NON_INFERIOR,
    NonInferiority.INFERIOR,
    NonInferiority.INCONCLUSIVE,
)


@pytest.mark.parametrize(
    ("lower", "upper", "margin", "expected"),
    [
        (0.1, 0.5, 0.2, S),  # L > 0
        (1e-12, 0.5, 0.2, S),
        (0.0, 0.5, 0.2, NI),  # L = 0 is not > 0, but L > -Delta
        (-0.1, 0.1, 0.2, NI),
        (-0.19, 0.4, 0.2, NI),
        (-0.2, 0.3, 0.2, INC),  # L = -Delta is not > -Delta and U is not < -Delta
        (-0.3, 0.1, 0.2, INC),  # wide interval
        (-0.5, -0.2, 0.2, INC),  # U = -Delta is not < -Delta
        (-0.5, -0.21, 0.2, INF),  # U < -Delta
        (-0.3, -0.3, 0.2, INF),
        (0.0, 0.0, 0.2, NI),  # degenerate interval at 0
    ],
)
def test_noninferiority_case_table(lower, upper, margin, expected) -> None:
    assert classify_noninferiority(lower, upper, margin) is expected


@pytest.mark.parametrize(("lower", "upper", "margin"), [(0, 1, 0), (0, 1, -0.1), (1, 0, 0.2)])
def test_noninferiority_rejects_invalid_input(lower, upper, margin) -> None:
    with pytest.raises(ValueError):
        classify_noninferiority(lower, upper, margin)


def test_iqr_uses_linear_quantiles() -> None:
    assert iqr([1, 2, 3, 4, 5, 6, 7, 8]) == 3.5  # 6.25 - 2.75 (Hyndman-Fan type 7)
    data = np.random.default_rng(31).normal(size=37)
    q1, q3 = np.quantile(data, [0.25, 0.75], method="linear")
    assert iqr(data) == q3 - q1
    assert iqr([4, 4, 4]) == 0


def test_shift_model_warning() -> None:
    narrow = [0, 1, 2, 3, 4]  # IQR 2
    assert not shift_model_warning(narrow, [0, 2, 4, 6, 8])  # IQR 4: ratio exactly 2
    assert shift_model_warning(narrow, [0, 2, 4.02, 6.04, 8])  # ratio > 2
    assert not shift_model_warning([5] * 6, [3] * 6)  # both IQR 0
    assert shift_model_warning([5] * 6, narrow)  # one IQR 0


def test_efficiency_threshold() -> None:
    assert efficiency_threshold(0.2, 0.7) == pytest.approx(0.65)
    assert efficiency_threshold(1.0, 1.0) == 1.0
    assert efficiency_threshold(0.0, 10.0) == pytest.approx(9.0)


def test_generations_to_threshold_takes_the_first_crossing() -> None:
    generations = [0, 5, 10, 15, 20]
    curve = [0.1, 0.3, 0.66, 0.5, 0.8]
    assert generations_to_threshold(generations, curve, 0.65, 20, 5) == GenerationsToThreshold(
        10, censored=False
    )
    assert generations_to_threshold(generations, curve, 0.66, 20, 5).generation == 10  # >= theta
    assert generations_to_threshold(generations, [0.9, 0, 0, 0, 0], 0.65, 20, 5).generation == 0


def test_generations_to_threshold_censors_at_g_plus_kval() -> None:
    result = generations_to_threshold([0, 5, 10, 15, 20], [0.1, 0.2, 0.3, 0.4, 0.5], 0.65, 20, 5)
    assert result == GenerationsToThreshold(25, censored=True)


@pytest.mark.parametrize(
    ("generations", "values", "total", "k_val"),
    [
        ([], [], 20, 5),
        ([0, 5], [0.1], 20, 5),
        ([0, 5, 5], [0.1, 0.2, 0.3], 20, 5),
        ([-1, 5], [0.1, 0.2], 20, 5),
        ([0, 25], [0.1, 0.2], 20, 5),
        ([0, 5], [0.1, 0.2], 20, 0),
        ([0, 5], [0.1, float("nan")], 20, 5),
    ],
)
def test_generations_to_threshold_rejects_invalid_curves(generations, values, total, k_val) -> None:
    with pytest.raises(ValueError):
        generations_to_threshold(generations, values, 0.5, total, k_val)
