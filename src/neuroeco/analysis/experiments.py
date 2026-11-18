"""Analysis of the formal experiments (F8): C1, C2, C3 and generalization, from the CSV files.

Reads only result files (ADR-023); never imports the simulation core. The experimental unit is
the training run (ADR-017): test episodes are summed per run into integer numerators with a
common denominator, so the run values are exact.

- C1 (before/after, base networks, 3 scenarios x 2 species): d_r = after - before against M0.
- C3 (network vs rule policy, same families): d_r = after - rules against M0.
  Both: median with the exact sign interval; exact unconditional sign test; Holm with m = 6
  only if R >= 8 (otherwise estimation only); Hodges-Lehmann and Wilcoxon as sensitivity.
- C2 (compact vs base, scenario A, per species): Hodges-Lehmann shift with exact interval and
  the non-inferiority rule with Delta; generations to theta compared by exact permutation;
  Holm m = 2 over the two species' efficiency tests.
- Generalization (ADR-019): Adv(O) = network - rules against O = M0..M4, estimation only.
"""

from __future__ import annotations

import csv
import json
import statistics
from collections import defaultdict
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from neuroeco.analysis.stats import (
    classify_noninferiority,
    cliffs_delta,
    generations_to_threshold,
    hodges_lehmann_one_sample,
    hodges_lehmann_two_sample,
    holm,
    median_sign_interval,
    rank_sum_permutation_test,
    shift_model_warning,
    sign_test,
    wilcoxon_signed_rank,
)

CONFIRMATORY_MIN_RUNS = 8
SPECIES = ("prey", "predator")
SCENARIOS = ("A", "B", "C")


def primary(species: str) -> tuple[str, str]:
    """(numerator, denominator) columns of the primary metric (ADR-014)."""
    return (
        ("survival_steps", "survival_denominator")
        if species == "prey"
        else (
            "captures",
            "capture_denominator",
        )
    )


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


@dataclass(frozen=True)
class RunTotals:
    """Primary metric of each run (summed over its test episodes) and the common denominator."""

    numerators: dict[str, int]
    denominator: int

    def value(self, run: str) -> float:
        return self.numerators[run] / self.denominator


def totals(
    rows, species, scenario, model, opponent, architecture=None, opponent_run=""
) -> RunTotals:
    num, den = primary(species)
    numerators: dict[str, int] = defaultdict(int)
    denominators: dict[str, int] = defaultdict(int)
    for r in rows:
        if (
            r["species"] == species
            and r["scenario"] == scenario
            and r["model"] == model
            and r["opponent"] == opponent
            and (architecture is None or r["architecture"] == architecture)
            and (opponent_run is None or r["opponent_run"] == opponent_run)
        ):
            numerators[r["run"]] += int(r[num])
            denominators[r["run"]] += int(r[den])
    if not numerators:
        return RunTotals({}, 1)
    if len(set(denominators.values())) != 1:
        raise ValueError(f"{species} {scenario} {model} {opponent}: denominators differ")
    return RunTotals(dict(numerators), next(iter(denominators.values())))


def _fraction(value: Fraction) -> float:
    return float(value)


@dataclass(frozen=True)
class Estimate:
    """Sign-test estimation that tolerates small n: the interval is None when no exact interval
    reaches the confidence level (ADR-032), which is reported instead of failing."""

    counts: Any
    median: float
    lower: float | None
    upper: float | None
    level: float | None
    p_value: Fraction


def estimate(values) -> Estimate:
    test = sign_test(values)
    try:
        interval = median_sign_interval(values)
        bounds = (interval.lower, interval.upper, float(interval.level))
    except ValueError:
        bounds = (None, None, None)
    return Estimate(test.counts, statistics.median(values), *bounds, test.p_value)


def _scaled(value: float | None, denominator: int) -> float | None:
    return None if value is None else value / denominator


def paired_family(
    differences: dict[tuple[str, str], tuple[list[int], int]], runs: int
) -> list[dict]:
    """Per (species, scenario): estimation, sign test, Holm (m = 6) when R >= 8, sensitivity.

    ``differences`` holds exact integer differences of numerators and their common denominator;
    medians and intervals are reported on the metric scale (divided by the denominator).
    """
    results = []
    p_values = []
    for (species, scenario), (d, denominator) in differences.items():
        analysis = estimate(d)
        p_values.append(analysis.p_value)
        row: dict[str, Any] = {
            "species": species,
            "scenario": scenario,
            "n": len(d),
            "k_plus": analysis.counts.positive,
            "k_zero": analysis.counts.zero,
            "k_minus": analysis.counts.negative,
            "denominator": denominator,
            "median": analysis.median / denominator,
            "ci_lower": _scaled(analysis.lower, denominator),
            "ci_upper": _scaled(analysis.upper, denominator),
            "ci_level": analysis.level,
            "p_sign": _fraction(analysis.p_value),
            "differences": [x / denominator for x in d],
        }
        try:
            hl = hodges_lehmann_one_sample(d)
        except ValueError:
            hl = None
        if hl is not None:
            row.update(
                hl_estimate=hl.estimate / denominator,
                hl_lower=hl.interval.lower / denominator,
                hl_upper=hl.interval.upper / denominator,
            )
            try:
                row["p_wilcoxon"] = _fraction(wilcoxon_signed_rank(d).p_value)
            except ValueError:
                row["p_wilcoxon"] = None
        results.append(row)
    confirmatory = runs >= CONFIRMATORY_MIN_RUNS
    if confirmatory and results:
        adjusted = holm(p_values, m=6)
        for r, p in zip(results, adjusted, strict=True):
            r["p_holm"] = _fraction(p)
    for r in results:
        r["confirmatory"] = confirmatory
    return results


def analyze(root: Path, decision_path: Path, runs: int) -> dict[str, Any]:
    rows = read_rows(root / "test_episodes.csv")
    report: dict[str, Any] = {"runs_planned": runs}

    c1: dict[tuple[str, str], tuple[list[int], int]] = {}
    c3: dict[tuple[str, str], tuple[list[int], int]] = {}
    for species in SPECIES:
        for scenario in SCENARIOS:
            architecture = f"{species}_base"
            before = totals(rows, species, scenario, "before", "M0", architecture)
            after = totals(rows, species, scenario, "after", "M0", architecture)
            rules = totals(rows, species, scenario, "reference", "M0", "rules")
            common = sorted(set(before.numerators) & set(after.numerators))
            if not common:
                continue
            if not before.denominator == after.denominator == rules.denominator:
                raise ValueError(f"{species} {scenario}: the test episodes differ between arms")
            den = after.denominator
            c1[(species, scenario)] = (
                [after.numerators[r] - before.numerators[r] for r in common],
                den,
            )
            reference = rules.numerators["rules"]
            c3[(species, scenario)] = ([after.numerators[r] - reference for r in common], den)
    report["C1"] = paired_family(c1, runs)
    report["C3"] = paired_family(c3, runs)

    decision = json.loads(decision_path.read_text("utf-8"))
    c2 = []
    efficiency_p = []
    for species in SPECIES:
        base = totals(rows, species, "A", "after", "M0", f"{species}_base")
        compact = totals(rows, species, "A", "after", "M0", f"{species}_compact")
        if not base.numerators or not compact.numerators:
            continue
        b = [base.value(r) for r in sorted(base.numerators)]
        c = [compact.value(r) for r in sorted(compact.numerators)]
        try:
            shift = hodges_lehmann_two_sample(b, c)
            interval = (shift.estimate, shift.interval.lower, shift.interval.upper)
            level = float(shift.interval.level)
        except ValueError:
            interval = (statistics.median(c) - statistics.median(b), None, None)
            level = None
        delta = decision["targets"][species]["delta"]
        theta = decision["targets"][species]["theta"]
        g_base = [
            _generations_to_theta(root, f"{species}_base", r, theta)
            for r in sorted(base.numerators)
        ]
        g_comp = [
            _generations_to_theta(root, f"{species}_compact", r, theta)
            for r in sorted(compact.numerators)
        ]
        efficiency = rank_sum_permutation_test(g_comp, g_base)
        efficiency_p.append(efficiency.p_value)
        c2.append(
            {
                "species": species,
                "base": b,
                "compact": c,
                "delta_estimate": interval[0],
                "ci_lower": interval[1],
                "ci_upper": interval[2],
                "ci_level": level,
                "margin": delta,
                "verdict": _verdict(interval, delta),
                "shift_model_warning": shift_model_warning(b, c),
                "cliffs_delta": _fraction(cliffs_delta(c, b)),
                "theta": theta,
                "generations_to_theta_base": g_base,
                "generations_to_theta_compact": g_comp,
                "p_efficiency": _fraction(efficiency.p_value),
            }
        )
    if efficiency_p:
        for row, p in zip(c2, holm(efficiency_p, m=2), strict=True):
            row["p_efficiency_holm"] = _fraction(p)
    report["C2"] = c2

    generalization = []
    for species in SPECIES:
        for scenario in SCENARIOS:
            architecture = f"{species}_base"
            for opponent in ("M0", "M1", "M2", "M3"):
                net = totals(rows, species, scenario, "after", opponent, architecture)
                rules = totals(rows, species, scenario, "reference", opponent, "rules")
                if not net.numerators:
                    continue
                adv = [net.value(r) - rules.value("rules") for r in sorted(net.numerators)]
                generalization.append(_estimate(species, scenario, opponent, adv))
            adv4 = _cross_play_advantage(rows, species, scenario)
            if adv4:
                generalization.append(_estimate(species, scenario, "M4", adv4))
    report["generalization"] = generalization
    return report


def _verdict(interval, delta: float) -> str:
    if not delta > 0:
        return "undefined (no training gain in P2)"
    if interval[1] is None:
        return "inconclusive (no exact interval at this n)"
    return str(classify_noninferiority(interval[1], interval[2], delta))


def _estimate(species, scenario, opponent, values) -> dict[str, Any]:
    analysis = estimate(values)
    return {
        "species": species,
        "scenario": scenario,
        "opponent": opponent,
        "median_advantage": analysis.median,
        "ci_lower": analysis.lower,
        "ci_upper": analysis.upper,
        "values": values,
    }


def _cross_play_advantage(rows, species, scenario) -> list[float]:
    """Per model: mean over the R opponent models of (network - rules) against each (ADR-019)."""
    num, den = primary(species)
    per_model: dict[str, list[float]] = defaultdict(list)
    rules: dict[str, float] = {}
    sums: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    for r in rows:
        if r["species"] == species and r["scenario"] == scenario and r["opponent"] == "M4":
            key = (r["run"], r["opponent_run"])
            sums[key][0] += int(r[num])
            sums[key][1] += int(r[den])
    for (run, opponent_run), (n, d) in sums.items():
        if run == "rules":
            rules[opponent_run] = n / d
    for (run, opponent_run), (n, d) in sums.items():
        if run != "rules":
            per_model[run].append(n / d - rules[opponent_run])
    return [sum(v) / len(v) for _, v in sorted(per_model.items())]


def _generations_to_theta(root: Path, architecture: str, run_id: str, theta: float) -> int:
    directory = root / "runs" / run_id
    rows = read_rows(directory / "generations.csv")
    validated = [(int(r["generation"]), float(r["f_val"])) for r in rows if r["f_val"]]
    interval = validated[1][0] - validated[0][0] if len(validated) > 1 else 1
    result = generations_to_threshold(
        [g for g, _ in validated], [v for _, v in validated], theta, len(rows), interval
    )
    return result.generation
