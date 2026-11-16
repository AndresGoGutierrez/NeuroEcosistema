"""Evaluation of the P1 criteria from the published result files (F4 T4; ADR-020, ADR-033).

A block is read from ``episodes.csv``, ``bootstrap_keys.csv`` and ``provenance.json`` exactly as
``neuroeco pilot p1`` publishes them (``docs/p1_data_dictionary.md``) and every criterion of the
P1-16 table is computed from those files only (D14):

- integers and the never-NaN float ``prey_net_energy_rate`` only; a NaN or an infinite value in
  any float column stops the evaluation;
- "mean" is the mean per episode; comparisons of means are exact (``fractions.Fraction``), with
  no tolerance;
- paired comparisons join the conditions on (``seed_group``, ``item``) and require every pair;
- a null denominator makes the C2 or C4 part "not applicable"; any other invalid denominator
  stops the evaluation.

A criterion is computed when its scenarios were executed (P1-18). The bootstrap criteria (A6 and
the descriptive interval of B2) are a later increment of T4.

``analysis`` imports no other ``neuroeco`` layer (import-linter): the file contract below mirrors
``neuroeco.application.calibration`` and ``neuroeco.presentation.pilot_p1``, and a test checks
that both stay equal.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction
from pathlib import Path
from typing import Any

import pandas as pd

# ---------------------------------------------------------------- mirrored file contract

PROVENANCE_SCHEMA = "neuroeco.p1-provenance/1"
EPISODES_FILE = "episodes.csv"
BOOTSTRAP_FILE = "bootstrap_keys.csv"
PROVENANCE_FILE = "provenance.json"

SCENARIOS = ("A", "B", "C")
PROBES = ("STILL", "SPIN", "STRAIGHT_MAX", "STRAIGHT_CRUISE")
RULES = "rules"
RANDOM_PREY = "random_prey"
RANDOM_PREDATOR = "random_predator"
NO_PREDATORS = "no_predators"
PREY_PROBES = tuple(f"prey_probe_{probe}" for probe in PROBES)
PREDATOR_PROBES = tuple(f"predator_probe_{probe}" for probe in PROBES)
_COMMON_CONDITIONS = (RULES, RANDOM_PREY, RANDOM_PREDATOR, *PREY_PROBES, *PREDATOR_PROBES)
CONDITIONS_BY_SCENARIO: Mapping[str, tuple[str, ...]] = {
    "A": (*_COMMON_CONDITIONS, NO_PREDATORS),
    "B": (*_COMMON_CONDITIONS, NO_PREDATORS),
    "C": _COMMON_CONDITIONS,
}

ENTRY_STAGE = "entry"
CONFIRMATION_STAGE = "confirmation"
STAGE_SCENARIOS: Mapping[str, tuple[str, ...]] = {
    "A": ("A",),
    "B": ("A", "B"),
    "C": ("A", "C"),
    ENTRY_STAGE: SCENARIOS,
    CONFIRMATION_STAGE: SCENARIOS,
}

PILOT_PURPOSE = 1  # Purpose.PILOT (ADR-028)
ANALYSIS_PURPOSE = 5  # Purpose.ANALYSIS
BOOTSTRAP_STREAM = 7  # Stream.BOOTSTRAP
EPISODE_STREAMS: Mapping[str, int] = {
    "stream_env_init": 3,
    "stream_env_dynamics": 4,
    "stream_policy_prey": 5,
    "stream_policy_predator": 6,
}
KEY_COMMON_COLUMNS = ("purpose", "seed_group", "run", "generation", "item")

EPISODE_COLUMN_TYPES: tuple[tuple[str, str], ...] = (
    ("block", "str"),
    ("stage", "str"),
    ("iteration", "int"),
    ("scenario", "str"),
    ("condition", "str"),
    *((name, "int") for name in (*KEY_COMMON_COLUMNS, *EPISODE_STREAMS)),
    ("config_hash", "str"),
    ("plant_energy", "float"),
    ("regrow_delay", "int"),
    ("n_plants_a", "int"),
    ("n_plants_b", "int"),
    ("n_predators_c", "int"),
    ("prey_flee_threshold", "float"),
    ("prey_cruise_fraction", "float"),
    ("predator_cruise_fraction", "float"),
    ("t_max", "int"),
    ("n_prey", "int"),
    ("n_predators", "int"),
    ("n_plants", "int"),
    ("steps", "int"),
    ("prey_survival_numerator", "int"),
    ("prey_survival_denominator", "int"),
    ("prey_alive_end", "int"),
    ("prey_captured", "int"),
    ("prey_starved", "int"),
    ("plants_eaten", "int"),
    ("exposure", "int"),
    ("early_captures", "int"),
    ("prey_net_energy_rate", "float"),
    ("predators_alive_end", "int"),
    ("predators_starved", "int"),
    ("predators_reaching_half", "int"),
    ("predators_censored_before_half", "int"),
    ("predators_censored_after_half", "int"),
    ("predators_alive_at_t_max", "int"),
    ("predators_alive_at_t_max_below_two_captures", "int"),
)
EPISODE_COLUMNS = tuple(name for name, _ in EPISODE_COLUMN_TYPES)
OUTCOME_COUNTS = tuple(
    name for name, kind in EPISODE_COLUMN_TYPES[EPISODE_COLUMNS.index("t_max") :] if kind == "int"
)
KEY_FIELDS = ("purpose", "seed_group", "run", "generation", "item", "stream")
BOOTSTRAP_COLUMN_TYPES: tuple[tuple[str, str], ...] = (
    ("comparison", "int"),
    ("comparison_name", "str"),
    ("project_seed", "str"),
    *((name, "int") for name in KEY_FIELDS),
)
BOOTSTRAP_COLUMNS = tuple(name for name, _ in BOOTSTRAP_COLUMN_TYPES)

# P1-20: number -> (name, scenarios that must have been executed)
COMPARISONS: Mapping[int, tuple[str, tuple[str, ...]]] = {
    1: ("A6_B_VS_A", ("A", "B")),
    2: ("A6_C_VS_A", ("A", "C")),
    3: ("B2_PREY_A", ("A",)),
    4: ("B2_PREY_B", ("B",)),
    5: ("B2_PREY_C", ("C",)),
    6: ("B2_PREDATOR_A", ("A",)),
    7: ("B2_PREDATOR_B", ("B",)),
    8: ("B2_PREDATOR_C", ("C",)),
}

CANDIDATE_PARAMETERS = (
    "plant_energy",
    "regrow_delay",
    "n_plants_a",
    "n_plants_b",
    "n_predators_c",
    "prey_flee_threshold",
    "prey_cruise_fraction",
    "predator_cruise_fraction",
)

# ---------------------------------------------------------------- limits of P1-16 (exact)

A5_BOUNDS = (Fraction(1, 20), Fraction(19, 20))
B1_BOUNDS = (Fraction(1, 5), Fraction(9, 10))
B3_MIN_FRACTION = Fraction(1, 2)
B6_MIN_CAPTURES = 2  # recorded per episode as predators_alive_at_t_max_below_two_captures
C2_MAX_EARLY_FRACTION = Fraction(1, 10)
C3_MIN_MEDIAN_FRACTION_OF_T_MAX = Fraction(1, 4)
C4_MAX_STARVATION_FRACTION = Fraction(9, 10)


class CriteriaError(ValueError):
    """The block cannot be evaluated: the evaluation stops (D14)."""


class Status(StrEnum):
    PASS = "pass"  # classes A and B
    FAIL = "fail"
    ALERT = "alert"  # class C
    NO_ALERT = "no_alert"
    NOT_APPLICABLE = "not_applicable"  # a C2 or C4 part with a null denominator


@dataclass(frozen=True)
class CriterionResult:
    """One evaluated criterion (or one part of it) of P1-16.

    ``scenario`` is ``A``, ``B`` or ``C``; ``B-A`` or ``C-A`` for a comparison between scenarios;
    empty for a property of the whole candidate (A1, A2, B7). ``value`` holds the exact computed
    quantities and ``rule`` the condition that was applied.
    """

    criterion: str
    part: str
    scenario: str
    status: Status
    value: str
    rule: str

    @property
    def criterion_class(self) -> str:
        return self.criterion[0]

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.criterion, self.part, self.scenario)


Row = Mapping[str, Any]


@dataclass(frozen=True)
class Block:
    """A published, completed and verified P1 block."""

    directory: Path
    provenance: Mapping[str, Any]
    rows: tuple[Row, ...]
    keys: tuple[Row, ...]

    @property
    def stage(self) -> str:
        return self.provenance["stage"]

    @property
    def scenarios(self) -> tuple[str, ...]:
        return STAGE_SCENARIOS[self.stage]

    @property
    def t_max(self) -> int:
        return self.rows[0]["t_max"]

    def condition(self, scenario: str, name: str) -> list[Row]:
        """Rows of one condition in the canonical order (by ``item``)."""
        return sorted(
            (r for r in self.rows if r["scenario"] == scenario and r["condition"] == name),
            key=lambda r: r["item"],
        )


# ---------------------------------------------------------------- reading and validation


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


_CONVERTERS: Mapping[str, Callable[[Any], Any]] = {"str": str, "int": int, "float": float}
# Floats are read as text and converted by Python: the command writes repr(), so float() gives
# back exactly the recorded number, independently of the float parser of pandas.
_PANDAS_TYPES = {"str": str, "int": "int64", "float": str}


def _read_csv(path: Path, column_types: Sequence[tuple[str, str]]) -> tuple[Row, ...]:
    """Rows with explicit types (ADR-023); exact header; every float finite (D14)."""
    expected = tuple(name for name, _ in column_types)
    with path.open(encoding="utf-8", newline="") as handle:
        header = tuple(next(csv.reader(handle), ()))
    if header != expected:
        raise CriteriaError(f"{path.name}: the columns are not the expected ones")
    try:
        frame = pd.read_csv(
            path,
            dtype={name: _PANDAS_TYPES[kind] for name, kind in column_types},
            na_filter=False,
            encoding="utf-8",
        )
    except (ValueError, TypeError) as error:
        raise CriteriaError(
            f"{path.name}: a value does not have its column type ({error})"
        ) from None
    rows = []
    for number, record in enumerate(frame.itertuples(index=False), start=2):
        try:
            row = {
                name: _CONVERTERS[kind](value)
                for (name, kind), value in zip(column_types, record, strict=True)
            }
        except ValueError as error:
            raise CriteriaError(
                f"{path.name} line {number}: a value does not have its column type ({error})"
            ) from None
        for name, kind in column_types:
            if kind == "float" and not math.isfinite(row[name]):
                raise CriteriaError(f"{path.name} line {number}: {name} is not finite (D14)")
        rows.append(row)
    return tuple(rows)


def _read_provenance(directory: Path) -> dict[str, Any]:
    path = directory / PROVENANCE_FILE
    if not path.is_file():
        raise CriteriaError(f"{directory.as_posix()}: {PROVENANCE_FILE} is missing")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise CriteriaError(f"{PROVENANCE_FILE} is not valid JSON ({error})") from None
    if not isinstance(data, dict) or data.get("schema") != PROVENANCE_SCHEMA:
        raise CriteriaError(f"{PROVENANCE_FILE} is not a P1 provenance record")
    if data.get("a2_violation") is True:
        raise CriteriaError("the block recorded an A2 violation: STOP and consult (P1-22)")
    if data.get("status") != "completed" or data.get("a2_violation") is not False:
        raise CriteriaError(
            f"only a completed block can be evaluated (status {data.get('status')!r}, "
            f"a2_violation {data.get('a2_violation')!r}); no criteria for an incomplete block"
        )
    stage = data.get("stage")
    if stage not in STAGE_SCENARIOS or data.get("scenarios") != list(STAGE_SCENARIOS[stage]):
        raise CriteriaError(f"stage {stage!r} with scenarios {data.get('scenarios')!r}")
    return data


def load_block(directory: Path) -> Block:
    """Read and verify a published block; any inconsistency stops the evaluation."""
    provenance = _read_provenance(directory)
    recorded = provenance.get("result_files")
    for name in (EPISODES_FILE, BOOTSTRAP_FILE):
        path = directory / name
        if not path.is_file():
            raise CriteriaError(f"{name} is missing")
        if not isinstance(recorded, dict) or recorded.get(name) != _sha256(path):
            raise CriteriaError(f"{name} does not match the SHA-256 recorded at publication")
    rows = _read_csv(directory / EPISODES_FILE, EPISODE_COLUMN_TYPES)
    keys = _read_csv(directory / BOOTSTRAP_FILE, BOOTSTRAP_COLUMN_TYPES)
    block = Block(directory, provenance, rows, keys)
    _check_rows(block)
    _check_bootstrap_keys(block)
    return block


def _fail(row: Row, message: str) -> CriteriaError:
    label = f"{row.get('scenario')}/{row.get('condition')}/item {row.get('item')}"
    return CriteriaError(f"{EPISODES_FILE} {label}: {message}")


def _check_rows(block: Block) -> None:
    provenance, rows = block.provenance, block.rows
    written = provenance.get("episodes_written")
    if not rows or written != len(rows) or provenance.get("episodes_planned") != len(rows):
        raise CriteriaError(f"{len(rows)} rows, provenance declares {written!r} episodes")
    episodes = provenance.get("episodes_per_condition")
    if type(episodes) is not int or episodes < 2:
        raise CriteriaError(f"episodes_per_condition {episodes!r}: at least 2 are needed")
    hashes = {c.get("config_hash") for c in provenance.get("configurations") or ()}
    values = provenance.get("values") or {}
    if set(values) != set(CANDIDATE_PARAMETERS):
        raise CriteriaError("the provenance does not record the eight candidate values")
    t_max = rows[0]["t_max"]
    if t_max < 1:
        raise _fail(rows[0], "t_max must be >= 1")

    identities: set[tuple[str, str, int]] = set()
    groups: dict[str, set[int]] = {}
    condition_hashes: dict[tuple[str, str], set[str]] = {}
    for row in rows:
        fixed = {
            "block": provenance.get("block"),
            "stage": provenance.get("stage"),
            "iteration": provenance.get("iteration"),
            "purpose": PILOT_PURPOSE,
            "run": 0,
            "generation": 0,
            "t_max": t_max,
            **EPISODE_STREAMS,
        }
        for name, expected in fixed.items():
            if row[name] != expected:
                raise _fail(row, f"{name} is {row[name]!r}, expected {expected!r}")
        for name in CANDIDATE_PARAMETERS:
            if row[name] != values[name]:
                raise _fail(row, f"{name} {row[name]!r} is not the recorded value {values[name]!r}")
        scenario, name = row["scenario"], row["condition"]
        if scenario not in block.scenarios or name not in CONDITIONS_BY_SCENARIO[scenario]:
            raise _fail(row, "condition or scenario not executed in this stage")
        if not 0 <= row["item"] < episodes:
            raise _fail(row, f"item outside 0..{episodes - 1}")
        identity = (scenario, name, row["item"])
        if identity in identities:
            raise _fail(row, "duplicated episode")
        identities.add(identity)
        if row["config_hash"] not in hashes:
            raise _fail(row, "config_hash is not one of the recorded configurations")
        groups.setdefault(scenario, set()).add(row["seed_group"])
        condition_hashes.setdefault((scenario, name), set()).add(row["config_hash"])
        _check_outcomes(row, no_predators=name == NO_PREDATORS)

    expected = {
        (scenario, name, item)
        for scenario in block.scenarios
        for name in CONDITIONS_BY_SCENARIO[scenario]
        for item in range(episodes)
    }
    if identities != expected:
        missing = sorted(expected - identities)[:3]
        raise CriteriaError(f"incomplete block: missing episodes such as {missing}")
    if any(len(g) != 1 for g in groups.values()):
        raise CriteriaError("every condition of a scenario must use the same seed_group (P1-13)")
    if len({next(iter(g)) for g in groups.values()}) != len(groups):
        raise CriteriaError("each scenario must have its own seed_group (P1-13)")
    if any(len(h) != 1 for h in condition_hashes.values()):
        raise CriteriaError("a condition of a scenario mixes configurations (config_hash)")


def _check_outcomes(row: Row, *, no_predators: bool) -> None:
    """Denominators and counts that every criterion relies on (D14)."""
    negative = [name for name in OUTCOME_COUNTS if row[name] < 0]
    if negative:
        raise _fail(row, f"negative counts {negative}")
    n_prey, n_predators, t_max = row["n_prey"], row["n_predators"], row["t_max"]
    checks = {
        "n_prey >= 1": n_prey >= 1,
        "1 <= steps <= t_max": 1 <= row["steps"] <= t_max,
        "prey_survival_denominator = n_prey * t_max": (
            row["prey_survival_denominator"] == n_prey * t_max
        ),
        "prey_survival_numerator <= denominator": (
            row["prey_survival_numerator"] <= row["prey_survival_denominator"]
        ),
        "prey alive + captured + starved = n_prey": (
            row["prey_alive_end"] + row["prey_captured"] + row["prey_starved"] == n_prey
        ),
        "predators alive + starved = n_predators": (
            row["predators_alive_end"] + row["predators_starved"] == n_predators
        ),
        "exposure > 0": row["exposure"] > 0,
        "early_captures <= prey_captured": row["early_captures"] <= row["prey_captured"],
        "predators_reaching_half <= n_predators": row["predators_reaching_half"] <= n_predators,
        "alive at t_max <= alive at the end": (
            row["predators_alive_at_t_max_below_two_captures"]
            <= row["predators_alive_at_t_max"]
            <= row["predators_alive_end"]
        ),
        "no_predators has n_predators = 0": not no_predators or n_predators == 0,
    }
    broken = [name for name, holds in checks.items() if not holds]
    if broken:
        raise _fail(row, f"inconsistent outcomes: {broken}")


def _check_bootstrap_keys(block: Block) -> None:
    """``bootstrap_keys.csv`` holds exactly the keys of P1-20 for this block."""
    provenance = block.provenance
    stage = provenance["stage"]
    run = provenance.get("bootstrap_run")
    expected_run = provenance.get("iteration") if stage in ("A", "B", "C") else 0
    if type(run) is not int or run != expected_run or (stage in ("A", "B", "C") and run < 1):
        raise CriteriaError(f"bootstrap_run {run!r} does not match the stage (P1-20)")
    group_a = block.condition("A", RULES)[0]["seed_group"]
    executed = set(block.scenarios)
    expected = sorted(n for n, (_, needed) in COMPARISONS.items() if set(needed) <= executed)
    if [row["comparison"] for row in block.keys] != expected:
        raise CriteriaError(f"{BOOTSTRAP_FILE} must list the comparisons {expected}")
    for row in block.keys:
        number = row["comparison"]
        wanted = {
            "comparison_name": COMPARISONS[number][0],
            "project_seed": provenance.get("project_seed"),
            "purpose": ANALYSIS_PURPOSE,
            "seed_group": group_a,
            "run": run,
            "generation": 0,
            "item": number,
            "stream": BOOTSTRAP_STREAM,
        }
        for name, value in wanted.items():
            if row[name] != value:
                raise CriteriaError(
                    f"{BOOTSTRAP_FILE} comparison {number}: {name} is {row[name]!r}, "
                    f"expected {value!r} (P1-20)"
                )


# ---------------------------------------------------------------- exact helpers


def survival(row: Row) -> Fraction:
    """Prey survival of one episode (ADR-014): sum of t_i over n_prey * T_max."""
    return Fraction(row["prey_survival_numerator"], row["prey_survival_denominator"])


def captured_fraction(row: Row) -> Fraction:
    """Captured fraction of one episode (ADR-014): captured prey over n_prey."""
    return Fraction(row["prey_captured"], row["n_prey"])


def quantile_type7(values: Sequence[Fraction | int], p: Fraction) -> Fraction:
    """Hyndman-Fan type 7 quantile (ADR-032), computed exactly."""
    data = sorted(Fraction(v) for v in values)
    if not data:
        raise CriteriaError("a quantile needs at least one value")
    h = (len(data) - 1) * p
    low = math.floor(h)
    if low + 1 >= len(data):
        return data[low]
    return data[low] + (h - low) * (data[low + 1] - data[low])


def exact_iqr(values: Sequence[Fraction | int]) -> Fraction:
    return quantile_type7(values, Fraction(3, 4)) - quantile_type7(values, Fraction(1, 4))


def paired(block: Block, scenario: str, first: str, second: str) -> list[tuple[Row, Row]]:
    """Pairs of two conditions of one scenario joined on (seed_group, item); all must exist."""
    a = {(r["seed_group"], r["item"]): r for r in block.condition(scenario, first)}
    b = {(r["seed_group"], r["item"]): r for r in block.condition(scenario, second)}
    if not a or a.keys() != b.keys():
        raise CriteriaError(f"{scenario}: {first} and {second} do not form complete pairs")
    return [(a[key], b[key]) for key in sorted(a)]


def _total(rows: Iterable[Row], column: str) -> int:
    return sum(row[column] for row in rows)


def _text(value: Fraction | int) -> str:
    return str(Fraction(value))


def _verdict(holds: bool) -> Status:
    return Status.PASS if holds else Status.FAIL


def _alert(raised: bool) -> Status:
    return Status.ALERT if raised else Status.NO_ALERT


# ---------------------------------------------------------------- criteria (P1-16)


def _a1_a2_b7(block: Block) -> list[CriterionResult]:
    state = block.provenance.get("state_k")
    if not isinstance(state, dict) or not isinstance(state.get("a1"), bool):
        raise CriteriaError("the provenance does not record state K (A1)")
    margin = state.get("b7_margin")
    if not isinstance(margin, int | float) or isinstance(margin, bool) or not math.isfinite(margin):
        raise CriteriaError("the provenance does not record a finite B7 margin")
    unmet = [
        f"{c.get('scenario')}:{c.get('constraint')}"
        for c in state.get("checks") or ()
        if c.get("satisfied") is not True
    ]
    episodes = len(block.rows)
    return [
        CriterionResult(
            "A1",
            "",
            "",
            _verdict(state["a1"]),
            f"unmet checks: {unmet or 'none'}",
            "state K accepted K1-K4, E1, E2, E5 and the scenario design (provenance state_k)",
        ),
        CriterionResult(
            "A2",
            "",
            "",
            Status.PASS,
            f"no violation in {episodes} episodes",
            "completed block with a2_violation = false (P1-22)",
        ),
        CriterionResult(
            "B7",
            "",
            "",
            _verdict(margin >= 0),
            repr(float(margin)),
            "K5 margin >= 0 (provenance state_k)",
        ),
    ]


def _per_scenario(block: Block, scenario: str) -> list[CriterionResult]:
    rules = block.condition(scenario, RULES)
    results: list[CriterionResult] = []
    survival_values = [survival(r) for r in rules]
    captured_values = [captured_fraction(r) for r in rules]
    iqr_survival, iqr_captured = exact_iqr(survival_values), exact_iqr(captured_values)
    results.append(
        CriterionResult(
            "A3",
            "",
            scenario,
            _verdict(iqr_survival > 0 and iqr_captured > 0),
            f"IQR survival = {_text(iqr_survival)}; IQR captured fraction = {_text(iqr_captured)}",
            "IQR (type 7) of the survival per episode > 0 and of the captured fraction > 0",
        )
    )
    aggregate = Fraction(
        _total(rules, "prey_survival_numerator"), _total(rules, "prey_survival_denominator")
    )
    low, high = A5_BOUNDS
    results.append(
        CriterionResult(
            "A5",
            "",
            scenario,
            _verdict(low <= aggregate <= high),
            _text(aggregate),
            f"{low} <= sum of numerators / sum of denominators <= {high}",
        )
    )
    low, high = B1_BOUNDS
    results.append(
        CriterionResult(
            "B1",
            "",
            scenario,
            _verdict(low <= aggregate <= high),
            _text(aggregate),
            f"{low} <= aggregate survival <= {high}",
        )
    )
    for part, other, metric in (
        ("prey", RANDOM_PREY, survival),
        ("predator", RANDOM_PREDATOR, captured_fraction),
    ):
        difference = sum(
            (metric(r) - metric(o) for r, o in paired(block, scenario, RULES, other)), Fraction(0)
        )
        results.append(
            CriterionResult(
                "B2",
                part,
                scenario,
                _verdict(difference > 0),
                _text(difference),
                f"sum of paired differences rules - {other} > 0 (P1-7, D3)",
            )
        )
    predators = _total(rules, "n_predators")
    if predators == 0:
        raise CriteriaError(f"{scenario}: B3 needs predators in the rules condition")
    reaching = Fraction(_total(rules, "predators_reaching_half"), predators)
    censored = (
        _total(rules, "predators_censored_before_half"),
        _total(rules, "predators_censored_after_half"),
    )
    results.append(
        CriterionResult(
            "B3",
            "",
            scenario,
            _verdict(reaching >= B3_MIN_FRACTION),
            f"{_text(reaching)} (censored before / after the threshold: {censored[0]} / "
            f"{censored[1]})",
            f"fraction of predators with t_i >= T_max / 2 >= {B3_MIN_FRACTION} (D2)",
        )
    )
    below = _total(rules, "predators_alive_at_t_max_below_two_captures")
    results.append(
        CriterionResult(
            "B6",
            "",
            scenario,
            _verdict(below == 0),
            f"{below} of {_total(rules, 'predators_alive_at_t_max')} predators alive at T_max "
            f"have fewer than {B6_MIN_CAPTURES} captures; {_sufficient_condition(block, rules)}",
            f"every predator alive at T_max has at least {B6_MIN_CAPTURES} captures (D3)",
        )
    )
    results.extend(_probe_alerts(block, scenario))
    captures = _total(rules, "prey_captured")
    early = _total(rules, "early_captures")
    results.append(
        CriterionResult(
            "C2",
            "",
            scenario,
            Status.NOT_APPLICABLE
            if captures == 0
            else _alert(Fraction(early, captures) > C2_MAX_EARLY_FRACTION),
            f"{early} of {captures} captures before 0.05 T_max",
            f"alert if early captures / captures > {C2_MAX_EARLY_FRACTION}; "
            "not applicable without captures",
        )
    )
    median = quantile_type7([r["steps"] for r in rules], Fraction(1, 2))
    limit = C3_MIN_MEDIAN_FRACTION_OF_T_MAX * block.t_max
    results.append(
        CriterionResult(
            "C3",
            "",
            scenario,
            _alert(median < limit),
            f"median steps = {_text(median)}",
            f"alert if the median of steps < T_max / 4 = {_text(limit)}",
        )
    )
    return results


def _sufficient_condition(block: Block, rules: Sequence[Row]) -> str:
    """B6 report: E0,pred + e_prey < c_basal,pred * T_max from the recorded configuration."""
    config_hash = rules[0]["config_hash"]
    matches = [
        c for c in block.provenance.get("configurations") or () if c["config_hash"] == config_hash
    ]
    try:
        world = matches[0]["world"]
        predator = world["predator"]
        initial = Fraction(predator["initial_energy_fraction"]) * Fraction(predator["e_max"])
        left = initial + Fraction(world["prey_energy"])
        right = Fraction(predator["c_basal"]) * world["t_max"]
    except (IndexError, KeyError, TypeError, ValueError):
        raise CriteriaError("the configuration of the rules condition is not recorded") from None
    return (
        f"sufficient condition E0_pred + e_prey < c_basal_pred * T_max: {left < right} "
        f"({float(left)!r} vs {float(right)!r})"
    )


def _probe_alerts(block: Block, scenario: str) -> list[CriterionResult]:
    """C1: each probe against ``rules`` with the primary metric of the probe's species."""
    results = []
    for probes, metric, label in (
        (PREY_PROBES, survival, "prey survival"),
        (PREDATOR_PROBES, captured_fraction, "captured fraction"),
    ):
        reference = sum((metric(r) for r in block.condition(scenario, RULES)), Fraction(0))
        for probe in probes:
            total = sum((metric(r) for r in block.condition(scenario, probe)), Fraction(0))
            results.append(
                CriterionResult(
                    "C1",
                    probe,
                    scenario,
                    _alert(total >= reference),
                    f"{_text(total)} vs rules {_text(reference)}",
                    f"alert if the sum of the {label} of the probe >= that of rules",
                )
            )
    return results


def _scenario_a(block: Block) -> list[CriterionResult]:
    rules = block.condition("A", RULES)
    eaten, captures = _total(rules, "plants_eaten"), _total(rules, "prey_captured")
    still_prey = block.condition("A", "prey_probe_STILL")
    survivors = _total(still_prey, "prey_alive_end")
    starved = _total(still_prey, "prey_starved")
    still_predator = block.condition("A", "predator_probe_STILL")
    predators = _total(still_predator, "n_predators")
    if predators == 0:
        raise CriteriaError("A4 (b2) needs predators in predator_probe_STILL")
    not_starved = sum(r["n_predators"] - r["predators_starved"] for r in still_predator)
    deaths = captures + _total(rules, "prey_starved")
    prey_starved = _total(rules, "prey_starved")
    episodes = len(rules)
    return [
        CriterionResult(
            "A4",
            "a",
            "A",
            _verdict(eaten > 0 and captures > 0),
            f"plants eaten = {eaten}; captures = {captures}",
            "sum of plants eaten > 0 and sum of captures > 0 (rules)",
        ),
        CriterionResult(
            "A4",
            "b1",
            "A",
            _verdict(survivors == 0 and starved >= 1),
            f"prey alive at the end = {survivors}; starved = {starved}",
            "prey_probe_STILL: no prey alive at the end of any episode and at least one starved",
        ),
        CriterionResult(
            "A4",
            "b2",
            "A",
            _verdict(not_starved == 0),
            f"{not_starved} of {predators} predators did not starve",
            "predator_probe_STILL: every predator starves in every episode",
        ),
        CriterionResult(
            "C4",
            "starvation_share",
            "A",
            Status.NOT_APPLICABLE
            if deaths == 0
            else _alert(Fraction(prey_starved, deaths) > C4_MAX_STARVATION_FRACTION),
            f"{prey_starved} of {deaths} prey deaths by starvation",
            f"alert if prey starved / (prey captured + prey starved) > "
            f"{C4_MAX_STARVATION_FRACTION} (D2); not applicable without prey deaths",
        ),
        CriterionResult(
            "C4",
            "few_captures",
            "A",
            _alert(captures < episodes),
            f"{captures} captures in {episodes} episodes",
            "alert if the mean captures per episode < 1 (P1-9)",
        ),
    ]


def _scenario_b(block: Block) -> list[CriterionResult]:
    starved_a = _total(block.condition("A", RULES), "prey_starved")
    starved_b = _total(block.condition("B", RULES), "prey_starved")
    value = f"prey starved: B = {starved_b}, A = {starved_a}"
    rule = "sum of prey starvation deaths in B > in A (rules)"
    rates = {
        s: sum(
            (Fraction(r["prey_net_energy_rate"]) for r in block.condition(s, NO_PREDATORS)),
            Fraction(0),
        )
        / len(block.condition(s, NO_PREDATORS))
        for s in ("A", "B")
    }
    return [
        CriterionResult("A4", "c", "B-A", _verdict(starved_b > starved_a), value, rule),
        CriterionResult("B4", "i", "B-A", _verdict(starved_b > starved_a), value, rule),
        CriterionResult(
            "B4",
            "ii",
            "B-A",
            _verdict(rates["A"] > 0 and rates["B"] <= 0),
            f"mean prey_net_energy_rate without predators: A = {float(rates['A'])!r}, "
            f"B = {float(rates['B'])!r}",
            "mean per episode of prey_net_energy_rate in no_predators > 0 in A and <= 0 in B (D12)",
        ),
    ]


def _scenario_c(block: Block) -> list[CriterionResult]:
    rules_a, rules_c = block.condition("A", RULES), block.condition("C", RULES)
    captures_a, captures_c = _total(rules_a, "prey_captured"), _total(rules_c, "prey_captured")
    value = f"captures: C = {captures_c}, A = {captures_a}"
    rates = {
        s: _text(Fraction(_total(rows, "prey_captured"), _total(rows, "exposure")))
        for s, rows in (("A", rules_a), ("C", rules_c))
    }
    return [
        CriterionResult(
            "A4",
            "d",
            "C-A",
            _verdict(captures_c > captures_a),
            value,
            "sum of captures in C > in A (rules)",
        ),
        CriterionResult(
            "B5",
            "",
            "C-A",
            _verdict(captures_c > captures_a),
            f"{value}; captures per exposure (descriptive): C = {rates['C']}, A = {rates['A']}",
            "mean cumulative capture incidence in C > in A, that is captures C > A (D4)",
        ),
    ]


def evaluate_block(block: Block) -> tuple[CriterionResult, ...]:
    """Every deterministic criterion computable with the scenarios of the block (P1-18).

    A6 and the descriptive BCa interval of B2 need the bootstrap (a later increment of T4).
    """
    results = _a1_a2_b7(block)
    for scenario in block.scenarios:
        results.extend(_per_scenario(block, scenario))
    results.extend(_scenario_a(block))
    if "B" in block.scenarios:
        results.extend(_scenario_b(block))
    if "C" in block.scenarios:
        results.extend(_scenario_c(block))
    return tuple(results)


# ---------------------------------------------------------------- stage requirements (P1-18)

_COMMON_REQUIREMENTS = (("A1", "", ""), ("A2", "", ""))
STAGE_REQUIREMENTS: Mapping[str, tuple[tuple[str, str, str], ...]] = {
    "A": (
        *_COMMON_REQUIREMENTS,
        ("A3", "", "A"),
        ("A4", "a", "A"),
        ("A4", "b1", "A"),
        ("A4", "b2", "A"),
        ("A5", "", "A"),
    ),
    "B": (
        *_COMMON_REQUIREMENTS,
        ("A3", "", "B"),
        ("A5", "", "B"),
        ("A4", "c", "B-A"),
        ("A6", "", "B-A"),
    ),
    "C": (
        *_COMMON_REQUIREMENTS,
        ("A3", "", "C"),
        ("A5", "", "C"),
        ("A4", "d", "C-A"),
        ("A6", "", "C-A"),
    ),
}
CLASS_A_REQUIREMENTS: tuple[tuple[str, str, str], ...] = (
    *_COMMON_REQUIREMENTS,
    *(("A3", "", s) for s in SCENARIOS),
    ("A4", "a", "A"),
    ("A4", "b1", "A"),
    ("A4", "b2", "A"),
    ("A4", "c", "B-A"),
    ("A4", "d", "C-A"),
    *(("A5", "", s) for s in SCENARIOS),
    ("A6", "", "B-A"),
    ("A6", "", "C-A"),
)


def requirements(stage: str) -> tuple[tuple[str, str, str], ...]:
    """S_A, S_B or S_C of an iteration; the whole class A for the entry and confirmations."""
    if stage in STAGE_REQUIREMENTS:
        return STAGE_REQUIREMENTS[stage]
    if stage in (ENTRY_STAGE, CONFIRMATION_STAGE):
        return CLASS_A_REQUIREMENTS
    raise CriteriaError(f"unknown stage {stage!r}")


def requirements_met(stage: str, results: Iterable[CriterionResult]) -> bool:
    """Whether the criteria the stage requires all pass; every one must have been evaluated."""
    by_key = {result.key: result for result in results}
    missing = [key for key in requirements(stage) if key not in by_key]
    if missing:
        raise CriteriaError(f"stage {stage}: criteria not evaluated: {missing}")
    return all(by_key[key].status is Status.PASS for key in requirements(stage))
