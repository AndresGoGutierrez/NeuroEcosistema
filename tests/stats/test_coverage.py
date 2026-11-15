"""T7 (F3): Monte Carlo coverage protocol of ADR-032 (slow).

Every configuration below reproduces a row of the ADR-032 tables literally: identifier, method,
generating distribution, true value, sample size, number of replicates N and seed
``SeedSequence(entropy=(32, id))``. Only the confirmatory configurations (id 1-32) can fail:
coverage >= L - 3 * sqrt(L (1 - L) / N), with L the attained level. The informative ones
(id 33-41) only report their coverage and its Monte Carlo standard error.

None of these values may be changed after the tests have been run (ADR-032).
"""

import math
from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction

import numpy as np
import pytest

from neuroeco.analysis.stats import (
    cliffs_delta_bca,
    hodges_lehmann_one_sample,
    hodges_lehmann_two_sample,
    median_sign_interval,
    paired_mean_bca,
)

pytestmark = pytest.mark.slow

N_CONFIRMATORY = 10_000
SIGN_LEVELS = {
    6: Fraction(31, 32),
    7: Fraction(63, 64),
    8: Fraction(127, 128),
    9: Fraction(123, 128),
    10: Fraction(501, 512),
}
HL_ONE_SAMPLE_LEVELS = {
    6: 1 - 2 * Fraction(1, 64),
    7: 1 - 2 * Fraction(3, 128),
    8: 1 - 2 * Fraction(5, 256),
    9: 1 - 2 * Fraction(10, 512),
    10: 1 - 2 * Fraction(25, 1024),
}
HL_TWO_SAMPLE_LEVEL = Fraction(443, 462)

Generator = np.random.Generator


def generator(config_id: int) -> Generator:
    return np.random.default_rng(np.random.SeedSequence(entropy=(32, config_id)))


def monte_carlo_se(level: float, replicates: int) -> float:
    return math.sqrt(level * (1 - level) / replicates)


@dataclass(frozen=True)
class Coverage:
    config_id: int
    replicates: int
    level: float
    covered: int

    @property
    def coverage(self) -> float:
        return self.covered / self.replicates

    @property
    def se(self) -> float:
        return monte_carlo_se(self.level, self.replicates)

    @property
    def threshold(self) -> float:
        return self.level - 3 * self.se

    def report(self, kind: str) -> str:
        return (
            f"COVERAGE id={self.config_id} {kind} N={self.replicates} level={self.level:.5f} "
            f"coverage={self.coverage:.5f} se={self.se:.5f} threshold={self.threshold:.5f}"
        )


# ---------------------------------------------------------------- confirmatory (id 1-32)

ONE_SAMPLE_SIGN: dict[str, tuple[Callable[[Generator, tuple], np.ndarray], float]] = {
    "normal": (lambda g, s: g.normal(0.4, 1.0, s), 0.4),  # id 1-5
    "exponential": (lambda g, s: g.exponential(1.0, s), math.log(2)),  # id 6-10
    "rounded_normal": (lambda g, s: np.rint(g.normal(0.3, 2.0, s)), 0.0),  # id 11-15
    "poisson": (lambda g, s: g.poisson(3.0, s) - 3.0, 0.0),  # id 16-20
}
ONE_SAMPLE_HL = {
    "normal": (lambda g, s: g.normal(0.5, 1.0, s), 0.5),  # id 21-25
    "laplace": (lambda g, s: g.laplace(0.5, 1.0, s), 0.5),  # id 26-30
}
SIZES = (6, 7, 8, 9, 10)


def sign_configurations():
    for block, distribution in enumerate(ONE_SAMPLE_SIGN):
        for offset, n in enumerate(SIZES):
            yield pytest.param(
                1 + 5 * block + offset, distribution, n, id=f"id{1 + 5 * block + offset}"
            )


def hl_configurations():
    for block, distribution in enumerate(ONE_SAMPLE_HL):
        for offset, n in enumerate(SIZES):
            config_id = 21 + 5 * block + offset
            yield pytest.param(config_id, distribution, n, id=f"id{config_id}")


def assert_confirmatory(result: Coverage, kind: str) -> None:
    print(result.report(kind) + (" PASS" if result.coverage >= result.threshold else " FAIL"))
    assert result.coverage >= result.threshold, result.report(kind)


@pytest.mark.parametrize(("config_id", "distribution", "n"), list(sign_configurations()))
def test_sign_interval_coverage(config_id, distribution, n) -> None:
    draw, true_median = ONE_SAMPLE_SIGN[distribution]
    samples = draw(generator(config_id), (N_CONFIRMATORY, n))
    covered = 0
    for sample in samples:
        interval = median_sign_interval(sample)
        assert interval.level == SIGN_LEVELS[n]
        covered += interval.contains(true_median)
    assert_confirmatory(
        Coverage(config_id, N_CONFIRMATORY, float(SIGN_LEVELS[n]), covered),
        f"sign/{distribution}/n={n}",
    )


@pytest.mark.parametrize(("config_id", "distribution", "n"), list(hl_configurations()))
def test_one_sample_hodges_lehmann_coverage(config_id, distribution, n) -> None:
    draw, center = ONE_SAMPLE_HL[distribution]
    samples = draw(generator(config_id), (N_CONFIRMATORY, n))
    covered = 0
    for sample in samples:
        interval = hodges_lehmann_one_sample(sample).interval
        assert interval.level == HL_ONE_SAMPLE_LEVELS[n]
        covered += interval.contains(center)
    assert_confirmatory(
        Coverage(config_id, N_CONFIRMATORY, float(HL_ONE_SAMPLE_LEVELS[n]), covered),
        f"hl1/{distribution}/n={n}",
    )


TWO_SAMPLE_SHIFT = {
    31: ("normal", lambda g, s: g.normal(0.0, 1.0, s)),
    32: ("exponential", lambda g, s: g.exponential(1.0, s)),
}
SHIFT = 0.7


@pytest.mark.parametrize("config_id", [31, 32], ids=["id31", "id32"])
def test_two_sample_hodges_lehmann_coverage(config_id) -> None:
    name, draw = TWO_SAMPLE_SHIFT[config_id]
    g = generator(config_id)
    reference = draw(g, (N_CONFIRMATORY, 6))
    treatment = draw(g, (N_CONFIRMATORY, 6)) + SHIFT
    covered = 0
    for x, y in zip(reference, treatment, strict=True):
        interval = hodges_lehmann_two_sample(x, y).interval
        assert interval.level == HL_TWO_SAMPLE_LEVEL
        covered += interval.contains(SHIFT)
    assert_confirmatory(
        Coverage(config_id, N_CONFIRMATORY, float(HL_TWO_SAMPLE_LEVEL), covered),
        f"hl2/{name}/6x6",
    )


# ---------------------------------------------------------------- informative (id 33-41)


def report_informative(result: Coverage, kind: str, not_estimable: int = 0) -> None:
    print(result.report(kind) + f" not_estimable={not_estimable} INFORMATIVE")
    assert 0 <= result.covered <= result.replicates  # reported only; never decides


@pytest.mark.parametrize(
    ("config_id", "n"),
    [(33 + i, n) for i, n in enumerate(SIZES)],
    ids=[f"id{33 + i}" for i in range(5)],
)
def test_informative_one_sample_hodges_lehmann_discrete(config_id, n) -> None:
    samples = generator(config_id).integers(-2, 5, size=(N_CONFIRMATORY, n))  # {-2, ..., 4}
    covered = sum(hodges_lehmann_one_sample(s).interval.contains(1) for s in samples)
    report_informative(
        Coverage(config_id, N_CONFIRMATORY, float(HL_ONE_SAMPLE_LEVELS[n]), covered),
        f"hl1/uniform_discrete/n={n}",
    )


def test_informative_two_sample_hodges_lehmann_discrete() -> None:
    g = generator(38)
    reference = g.poisson(3.0, (N_CONFIRMATORY, 6))
    treatment = g.poisson(3.0, (N_CONFIRMATORY, 6)) + 1
    covered = sum(
        hodges_lehmann_two_sample(x, y).interval.contains(1)
        for x, y in zip(reference, treatment, strict=True)
    )
    report_informative(
        Coverage(38, N_CONFIRMATORY, float(HL_TWO_SAMPLE_LEVEL), covered), "hl2/poisson/6x6"
    )


PAIRED_MEAN = {
    39: ("normal", lambda g, s: g.normal(0.3, 1.0, s)),
    40: ("exponential", lambda g, s: g.exponential(1.0, s) - 0.7),
}


@pytest.mark.parametrize("config_id", [39, 40], ids=["id39", "id40"])
def test_informative_paired_mean_bca(config_id) -> None:
    name, draw = PAIRED_MEAN[config_id]
    g = generator(config_id)
    samples = draw(g, (N_CONFIRMATORY, 50))
    covered = not_estimable = 0
    for sample in samples:
        result = paired_mean_bca(sample, g)
        if not result.estimable:
            not_estimable += 1
            continue
        covered += result.lower <= 0.3 <= result.upper
    report_informative(
        Coverage(config_id, N_CONFIRMATORY, 0.95, covered), f"bca_mean/{name}/n=50", not_estimable
    )


N_CLIFF = 2_000  # id 41: computational feasibility (ADR-032)


def test_informative_cliffs_delta_bca() -> None:
    g = generator(41)
    x = g.normal(0.0, 1.0, (N_CLIFF, 50))
    y = g.normal(0.5, 1.0, (N_CLIFF, 50))
    true_delta = 2 * _normal_cdf(0.5 / math.sqrt(2)) - 1  # P(Y > X) - P(Y < X)
    covered = not_estimable = 0
    for xs, ys in zip(x, y, strict=True):
        result = cliffs_delta_bca(ys, xs, g)
        if not result.estimable:
            not_estimable += 1
            continue
        covered += result.lower <= true_delta <= result.upper
    report_informative(
        Coverage(41, N_CLIFF, 0.95, covered), "bca_cliff/normal/50x50", not_estimable
    )


def _normal_cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def test_true_cliffs_delta_matches_the_protocol_value() -> None:
    assert 2 * _normal_cdf(0.5 / math.sqrt(2)) - 1 == pytest.approx(0.2763, abs=5e-5)
