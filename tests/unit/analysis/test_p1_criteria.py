"""F4 T4 (I1, I2): P1 criteria from the published files (ADR-033 P1-16, P1-18, P1-20).

Every block is synthetic and written in memory with the exact format of ``neuroeco pilot p1``
(seed groups >= 1000, D16); no episode is run here. The default block meets every criterion and
raises no alert; each test changes only what it checks. Bootstrap tests check properties and
contracts, never BCa limits that could differ between platforms.
"""

import csv
import dataclasses
import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Callable
from fractions import Fraction
from pathlib import Path

import pytest

from neuroeco.analysis import calibration as crit
from neuroeco.analysis.stats import BootstrapInterval, iqr
from neuroeco.application import calibration as app
from neuroeco.application.seeding import Purpose, SeedRegistry, Stream
from neuroeco.presentation import pilot_p1

T_MAX, EPISODES, N_PREY, N_PREDATORS = 40, 4, 10, 2
GROUPS = {"A": 1000, "B": 1001, "C": 1002}
SEED = "123456789012345678901234567890"
VALUES = {
    "plant_energy": 30.0,
    "regrow_delay": 50,
    "n_plants_a": 40,
    "n_plants_b": 15,
    "n_predators_c": 8,
    "prey_flee_threshold": 0.3,
    "prey_cruise_fraction": 0.5,
    "predator_cruise_fraction": 0.5,
}
WORLD = {
    "t_max": T_MAX,
    "prey_energy": 40.0,
    "predator": {"initial_energy_fraction": 0.8, "e_max": 100.0, "c_basal": 4.0},
}
STAGE_INFO = {  # stage -> (block, iteration = bootstrap run)
    "A": ("calibration", 1),
    "B": ("calibration", 2),
    "C": ("calibration", 3),
    "entry": ("calibration", 0),
    "confirmation": ("confirmation", 0),
}

Edit = Callable[[dict], None]


def base_row(stage: str, scenario: str, condition: str, item: int) -> dict:
    """A plausible episode that meets every criterion and raises no alert."""
    block, iteration = STAGE_INFO[stage]
    captured, starved, numerator = 2 + item % 2, 1, 200 + 10 * (item % 4)
    if scenario in ("B", "C"):
        numerator -= 100  # A6: lower survival in B and C (complete separation from A)
    predators = {"n": N_PREDATORS, "starved": 0}
    if condition == "rules" and scenario == "B":
        starved = 2  # A4 (c): more starvation in B
    if condition == "rules" and scenario == "C":
        captured += 2  # A4 (d): more captures in C
    if condition == "random_prey" or condition.startswith("prey_probe"):
        numerator -= 100  # B2 and C1: rules survive longer
    if condition == "random_predator" or condition.startswith("predator_probe"):
        captured = 0  # B2 and C1: rules capture more
    if condition == "prey_probe_STILL":
        starved = N_PREY - captured  # A4 (b1): every prey dies
    if condition == "predator_probe_STILL":
        predators["starved"] = N_PREDATORS  # A4 (b2): every predator starves
    if condition == "no_predators":
        predators = {"n": 0, "starved": 0}
        captured = 0
    alive_predators = predators["n"] - predators["starved"]
    return {
        "block": block,
        "stage": stage,
        "iteration": iteration,
        "scenario": scenario,
        "condition": condition,
        **app.episode_key_columns(GROUPS[scenario], item),
        "config_hash": f"hash-{scenario}-{condition}",
        **VALUES,
        "t_max": T_MAX,
        "n_prey": N_PREY,
        "n_predators": predators["n"],
        "n_plants": 40,
        "steps": T_MAX,
        "prey_survival_numerator": numerator,
        "prey_survival_denominator": N_PREY * T_MAX,
        "prey_alive_end": N_PREY - captured - starved,
        "prey_captured": captured,
        "prey_starved": starved,
        "plants_eaten": 5,
        "exposure": 300,
        "early_captures": 0,
        "prey_net_energy_rate": -0.5 if scenario == "B" else 0.5,
        "predators_alive_end": alive_predators,
        "predators_starved": predators["starved"],
        "predators_reaching_half": alive_predators,
        "predators_censored_before_half": 0,
        "predators_censored_after_half": 0,
        "predators_alive_at_t_max": alive_predators,
        "predators_alive_at_t_max_below_two_captures": 0,
    }


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path: Path, columns, rows) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(rows)


def write_block(
    directory: Path,
    stage: str = "entry",
    edit: Edit | None = None,
    provenance_edit: Edit | None = None,
    episodes: int = EPISODES,
) -> Path:
    """A published block of ``stage``; ``edit`` changes rows, ``provenance_edit`` the record."""
    directory.mkdir(parents=True)
    block, iteration = STAGE_INFO[stage]
    scenarios = crit.STAGE_SCENARIOS[stage]
    rows = [
        base_row(stage, s, c.name, item)
        for s in scenarios
        for c in app.CONDITIONS_BY_SCENARIO[s]
        for item in range(episodes)
    ]
    for row in rows:
        if edit:
            edit(row)
    write_csv(directory / "episodes.csv", app.EPISODE_COLUMNS, rows)
    keys = [
        {
            "comparison": int(c),
            "comparison_name": c.name,
            "project_seed": SEED,
            **dict(zip(app.KEY_FIELDS, (5, GROUPS["A"], iteration, 0, int(c), 7), strict=True)),
        }
        for c in app.Comparison
        if set(app.COMPARISON_SCENARIOS[c]) <= set(scenarios)
    ]
    write_csv(directory / "bootstrap_keys.csv", app.BOOTSTRAP_COLUMNS, keys)
    provenance = {
        "schema": "neuroeco.p1-provenance/1",
        "status": "completed",
        "block": block,
        "stage": stage,
        "iteration": iteration,
        "bootstrap_run": iteration,
        "scenarios": list(scenarios),
        "episodes_per_condition": episodes,
        "episodes_planned": len(rows),
        "episodes_written": len(rows),
        "project_seed": SEED,
        "values": VALUES,
        "state_k": {
            "a1": True,
            "b7_margin": 1.4,
            "checks": [{"scenario": "A", "constraint": "E1", "satisfied": True}],
        },
        "configurations": [
            {"scenario": s, "config_hash": f"hash-{s}-{c.name}", "world": WORLD}
            for s in scenarios
            for c in app.CONDITIONS_BY_SCENARIO[s]
        ],
        "result_files": {name: sha(directory / name) for name in crit_files()},
        "a2_violation": False,
    }
    if provenance_edit:
        provenance_edit(provenance)
    (directory / "provenance.json").write_text(json.dumps(provenance), encoding="utf-8")
    return directory


def crit_files() -> tuple[str, str]:
    return (crit.EPISODES_FILE, crit.BOOTSTRAP_FILE)


def rewrite(directory: Path, name: str, change: Callable[[str], str]) -> None:
    """Change a published file and record its new SHA-256, so the parser is reached."""
    path = directory / name
    path.write_text(change(path.read_text(encoding="utf-8")), encoding="utf-8", newline="")
    record = json.loads((directory / "provenance.json").read_text(encoding="utf-8"))
    record["result_files"][name] = sha(path)
    (directory / "provenance.json").write_text(json.dumps(record), encoding="utf-8")


def evaluate(directory: Path) -> dict[tuple[str, str, str], crit.CriterionResult]:
    """The deterministic criteria (I1 tests: no bootstrap needed)."""
    return {r.key: r for r in crit.deterministic_criteria(crit.load_block(directory))}


def evaluate_all(directory: Path) -> dict[tuple[str, str, str], crit.CriterionResult]:
    """Every criterion, bootstrap included."""
    return {r.key: r for r in crit.evaluate_block(crit.load_block(directory))}


def where(scenario: str, condition: str, **changes) -> Edit:
    """An edit of one condition: each value is a constant or a list indexed by item."""

    def edit(row: dict) -> None:
        if row["scenario"] == scenario and row["condition"] == condition:
            for name, value in changes.items():
                row[name] = value[row["item"]] if isinstance(value, list) else value

    return edit


# ---------------------------------------------------------------- contract and applicability


def test_the_mirrored_contract_matches_application_and_command() -> None:
    assert crit.EPISODE_COLUMN_TYPES == app.EPISODE_COLUMN_TYPES
    assert crit.BOOTSTRAP_COLUMNS == app.BOOTSTRAP_COLUMNS
    assert crit.CANDIDATE_PARAMETERS == app.PARAMETERS
    assert {s: tuple(c.name for c in cs) for s, cs in app.CONDITIONS_BY_SCENARIO.items()} == dict(
        crit.CONDITIONS_BY_SCENARIO
    )
    assert {s: crit.STAGE_SCENARIOS[s] for s in app.STAGES} == dict(app.STAGE_SCENARIOS)
    for stage in (app.ENTRY_STAGE, app.CONFIRMATION_STAGE):
        assert crit.STAGE_SCENARIOS[stage] == app.SCENARIOS
    assert dict(crit.COMPARISONS) == {
        int(c): (c.name, app.COMPARISON_SCENARIOS[c]) for c in app.Comparison
    }
    assert {name: int(s) for name, s in app.EPISODE_STREAMS.items()} == crit.EPISODE_STREAMS
    assert (crit.PILOT_PURPOSE, crit.ANALYSIS_PURPOSE, crit.BOOTSTRAP_STREAM) == (
        Purpose.PILOT,
        Purpose.ANALYSIS,
        Stream.BOOTSTRAP,
    )
    assert (
        crit.PROVENANCE_SCHEMA,
        crit.EPISODES_FILE,
        crit.BOOTSTRAP_FILE,
        crit.PROVENANCE_FILE,
    ) == (
        pilot_p1.PROVENANCE_SCHEMA,
        pilot_p1.EPISODES_FILE,
        pilot_p1.BOOTSTRAP_FILE,
        pilot_p1.PROVENANCE_FILE,
    )


def per_scenario_keys(scenario: str) -> set[tuple[str, str, str]]:
    keys = {(c, "", scenario) for c in ("A3", "A5", "B1", "B3", "B6", "C2", "C3")}
    keys |= {("B2", "prey", scenario), ("B2", "predator", scenario)}
    return keys | {("C1", p, scenario) for p in (*crit.PREY_PROBES, *crit.PREDATOR_PROBES)}


SCENARIO_A_KEYS = {
    ("A4", "a", "A"),
    ("A4", "b1", "A"),
    ("A4", "b2", "A"),
    ("C4", "starvation_share", "A"),
    ("C4", "few_captures", "A"),
}
SCENARIO_B_KEYS = {
    ("A4", "c", "B-A"),
    ("B4", "i", "B-A"),
    ("B4", "ii", "B-A"),
    ("A6", "", "B-A"),
}
SCENARIO_C_KEYS = {("A4", "d", "C-A"), ("B5", "", "C-A"), ("A6", "", "C-A")}
CANDIDATE_KEYS = {("A1", "", ""), ("A2", "", ""), ("B7", "", "")}


@pytest.mark.parametrize(
    ("stage", "expected"),
    [
        ("A", CANDIDATE_KEYS | per_scenario_keys("A") | SCENARIO_A_KEYS),
        (
            "B",
            CANDIDATE_KEYS
            | per_scenario_keys("A")
            | per_scenario_keys("B")
            | SCENARIO_A_KEYS
            | SCENARIO_B_KEYS,
        ),
        (
            "C",
            CANDIDATE_KEYS
            | per_scenario_keys("A")
            | per_scenario_keys("C")
            | SCENARIO_A_KEYS
            | SCENARIO_C_KEYS,
        ),
        (
            "confirmation",
            CANDIDATE_KEYS
            | per_scenario_keys("A")
            | per_scenario_keys("B")
            | per_scenario_keys("C")
            | SCENARIO_A_KEYS
            | SCENARIO_B_KEYS
            | SCENARIO_C_KEYS,
        ),
    ],
)
def test_criteria_are_computed_when_their_scenarios_ran(tmp_path, stage, expected) -> None:
    """P1-18: the criteria of each stage; the default block meets all of them, no alert."""
    results = evaluate_all(write_block(tmp_path / "block", stage))
    assert set(results) == expected
    assert {r.status for r in results.values()} <= {crit.Status.PASS, crit.Status.NO_ALERT}


def test_stage_requirements(tmp_path) -> None:
    """S_A, S_B, S_C and the whole class A; A6 is required wherever B or C ran."""
    assert crit.requirements_met("A", evaluate_all(write_block(tmp_path / "a", "A")).values())
    block_b = write_block(tmp_path / "b", "B")
    with pytest.raises(crit.CriteriaError, match="A6"):
        crit.requirements_met("B", evaluate(block_b).values())  # without the bootstrap
    assert crit.requirements_met("B", evaluate_all(block_b).values())
    failing = write_block(tmp_path / "b2", "B", where("B", "rules", prey_survival_numerator=1))
    assert not crit.requirements_met("B", evaluate_all(failing).values())  # A3 in B fails
    assert crit.requirements_met("C", evaluate_all(write_block(tmp_path / "c", "C")).values())
    entry = evaluate_all(write_block(tmp_path / "e", "entry"))
    assert crit.requirements_met("entry", entry.values())


# ---------------------------------------------------------------- exact boundaries


def survival_total(total: int) -> list[int]:
    """Four numerators summing to ``total`` (denominator 4 * 400 = 1600)."""
    base = total // EPISODES
    return [base] * (EPISODES - 1) + [total - base * (EPISODES - 1)]


BOUNDARIES = [
    # (criterion key, edit, expected status)
    (("A5", "", "A"), where("A", "rules", prey_survival_numerator=survival_total(80)), "pass"),
    (("A5", "", "A"), where("A", "rules", prey_survival_numerator=survival_total(79)), "fail"),
    (("A5", "", "A"), where("A", "rules", prey_survival_numerator=survival_total(1520)), "pass"),
    (("A5", "", "A"), where("A", "rules", prey_survival_numerator=survival_total(1521)), "fail"),
    (("B1", "", "B"), where("B", "rules", prey_survival_numerator=survival_total(320)), "pass"),
    (("B1", "", "B"), where("B", "rules", prey_survival_numerator=survival_total(319)), "fail"),
    (("B1", "", "B"), where("B", "rules", prey_survival_numerator=survival_total(1440)), "pass"),
    (("B1", "", "B"), where("B", "rules", prey_survival_numerator=survival_total(1441)), "fail"),
    # B3: 4 of 8 predators reach T_max / 2 (exactly 1/2), then 3 of 8
    (("B3", "", "C"), where("C", "rules", predators_reaching_half=[1, 1, 1, 1]), "pass"),
    (("B3", "", "C"), where("C", "rules", predators_reaching_half=[1, 1, 1, 0]), "fail"),
    # B2: a null sum of paired differences is not > 0
    (
        ("B2", "prey", "A"),
        where("A", "random_prey", prey_survival_numerator=[200, 210, 220, 230]),
        "fail",
    ),
    (
        ("B2", "predator", "B"),
        where("B", "random_predator", prey_captured=[2, 3, 2, 3], prey_alive_end=[7, 6, 7, 6]),
        "fail",
    ),
    # C1: a probe equal to rules raises the alert
    (
        ("C1", "prey_probe_SPIN", "C"),
        where("C", "prey_probe_SPIN", prey_survival_numerator=[100, 110, 120, 130]),
        "alert",
    ),
    # C2: 10 captures in A; 1 early is exactly 1/10, 2 are more
    (("C2", "", "A"), where("A", "rules", early_captures=[1, 0, 0, 0]), "no_alert"),
    (("C2", "", "A"), where("A", "rules", early_captures=[1, 1, 0, 0]), "alert"),
    # C3: the median of steps equal to T_max / 4 = 10 raises no alert; 9.5 does
    (("C3", "", "B"), where("B", "rules", steps=[10, 10, 10, 10]), "no_alert"),
    (("C3", "", "B"), where("B", "rules", steps=[9, 10, 10, 9]), "alert"),
    # C4 (D2): prey starved / (captured + starved) = 36/40 = 9/10, then 37/40
    (
        ("C4", "starvation_share", "A"),
        where("A", "rules", prey_captured=1, prey_starved=9, prey_alive_end=0, early_captures=0),
        "no_alert",
    ),
    (
        ("C4", "starvation_share", "A"),
        where(
            "A",
            "rules",
            prey_captured=[1, 1, 1, 0],
            prey_starved=[9, 9, 9, 10],
            prey_alive_end=0,
        ),
        "alert",
    ),
    # C4: 4 captures in 4 episodes is a mean of 1, 3 is less
    (
        ("C4", "few_captures", "A"),
        where("A", "rules", prey_captured=1, prey_alive_end=8),
        "no_alert",
    ),
    (
        ("C4", "few_captures", "A"),
        where("A", "rules", prey_captured=[1, 1, 1, 0], prey_alive_end=[8, 8, 8, 9]),
        "alert",
    ),
]


@pytest.mark.parametrize(("key", "edit", "expected"), BOUNDARIES)
def test_exact_boundaries(tmp_path, key, edit, expected) -> None:
    assert evaluate(write_block(tmp_path / "block", "entry", edit))[key].status == expected


def test_a3_uses_the_exact_type_7_iqr_of_both_primary_metrics(tmp_path) -> None:
    sample = [Fraction(n, 8) for n in (3, 1, 4, 1, 5, 9, 2, 6)]
    assert crit.exact_iqr(sample) == Fraction(iqr([float(v) for v in sample]))
    constant_survival = where("A", "rules", prey_survival_numerator=210)
    constant_captures = where("B", "rules", prey_captured=2, prey_alive_end=6)
    results = evaluate(
        write_block(
            tmp_path / "block",
            "entry",
            lambda row: (constant_survival(row), constant_captures(row)),
        )
    )
    assert results[("A3", "", "A")].status == "fail"
    assert results[("A3", "", "B")].status == "fail"
    assert results[("A3", "", "C")].status == "pass"


@pytest.mark.parametrize(
    ("key", "edit"),
    [
        # one prey survives the STILL probe; then no prey starves at all
        (
            ("A4", "b1", "A"),
            where("A", "prey_probe_STILL", prey_alive_end=[1, 0, 0, 0], prey_starved=[7, 7, 8, 7]),
        ),
        (
            ("A4", "b1", "A"),
            where("A", "prey_probe_STILL", prey_captured=10, prey_starved=0, prey_alive_end=0),
        ),
        # an episode ends early (all prey gone) with a predator of the STILL probe alive
        (
            ("A4", "b2", "A"),
            where(
                "A",
                "predator_probe_STILL",
                steps=[12, 40, 40, 40],
                predators_starved=[1, 2, 2, 2],
                predators_alive_end=[1, 0, 0, 0],
            ),
        ),
        (("A4", "c", "B-A"), where("B", "rules", prey_starved=1, prey_alive_end=[7, 6, 7, 6])),
        (
            ("A4", "d", "C-A"),
            where("C", "rules", prey_captured=[2, 3, 2, 3], prey_alive_end=[7, 6, 7, 6]),
        ),
        (
            ("B5", "", "C-A"),
            where("C", "rules", prey_captured=[2, 3, 2, 3], prey_alive_end=[7, 6, 7, 6]),
        ),
        (("A4", "a", "A"), where("A", "rules", plants_eaten=0)),
    ],
)
def test_a4_and_b5_failures(tmp_path, key, edit) -> None:
    assert evaluate(write_block(tmp_path / "block", "entry", edit))[key].status == "fail"


def test_b3_and_b6_with_censored_episodes(tmp_path) -> None:
    """D2, D3: an episode that ends before T_max censors its surviving predators."""
    early_end = where(
        "A",
        "rules",
        steps=[15, 40, 40, 40],
        predators_reaching_half=[0, 2, 2, 2],
        predators_censored_before_half=[2, 0, 0, 0],
        predators_alive_at_t_max=[0, 2, 2, 2],
    )
    results = evaluate(write_block(tmp_path / "early", "entry", early_end))
    assert results[("B3", "", "A")].status == "pass"  # 6 of 8
    assert "censored before / after the threshold: 2 / 0" in results[("B3", "", "A")].value
    assert results[("B6", "", "A")].status == "pass"  # nobody alive at T_max with < 2 captures
    assert "sufficient condition E0_pred + e_prey < c_basal_pred * T_max: True" in (
        results[("B6", "", "A")].value
    )
    weak = where("B", "rules", predators_alive_at_t_max_below_two_captures=[0, 1, 0, 0])
    assert evaluate(write_block(tmp_path / "weak", "entry", weak))[("B6", "", "B")].status == (
        "fail"
    )


def test_b4_compares_the_exact_mean_energy_rate(tmp_path) -> None:
    """D12: > 0 in A and <= 0 in B, with exact sums of the recorded floats."""
    zero = [0.5, -0.25, -0.25, 0.0]
    results = evaluate(
        write_block(
            tmp_path / "zero_b", "entry", where("B", "no_predators", prey_net_energy_rate=zero)
        )
    )
    assert results[("B4", "ii", "B-A")].status == "pass"
    results = evaluate(
        write_block(
            tmp_path / "zero_a", "entry", where("A", "no_predators", prey_net_energy_rate=zero)
        )
    )
    assert results[("B4", "ii", "B-A")].status == "fail"


@pytest.mark.parametrize(
    ("key", "edit"),
    [
        (("C2", "", "B"), where("B", "rules", prey_captured=0, prey_alive_end=8)),
        (
            ("C4", "starvation_share", "A"),
            where("A", "rules", prey_captured=0, prey_starved=0, prey_alive_end=10),
        ),
    ],
)
def test_null_denominators_make_the_alert_not_applicable(tmp_path, key, edit) -> None:
    result = evaluate(write_block(tmp_path / "block", "entry", edit))[key]
    assert result.status == "not_applicable"


def test_a1_and_b7_come_from_state_k(tmp_path) -> None:
    def rejected(record: dict) -> None:
        record["state_k"] = {
            "a1": False,
            "b7_margin": -0.5,
            "checks": [{"scenario": "B", "constraint": "E5", "satisfied": False}],
        }

    results = evaluate(write_block(tmp_path / "block", "A", provenance_edit=rejected))
    assert results[("A1", "", "")].status == "fail" and "B:E5" in results[("A1", "", "")].value
    assert results[("B7", "", "")].status == "fail"


# ---------------------------------------------------------------- the evaluation stops


def change_item(scenario: str, condition: str, index: int, **changes) -> Edit:
    def edit(row: dict) -> None:
        if (row["scenario"], row["condition"], row["item"]) == (scenario, condition, index):
            row.update(changes)

    return edit


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (change_item("A", "rules", 0, prey_net_energy_rate="nan"), "not finite"),
        (change_item("B", "no_predators", 1, prey_net_energy_rate="inf"), "not finite"),
        (change_item("A", "rules", 0, prey_captured=""), "column type"),
        (change_item("A", "rules", 1, item=0), "duplicated episode"),
        (change_item("A", "random_prey", 2, seed_group=1003), "same seed_group"),
        (lambda row: row["scenario"] != "C" or row.update(seed_group=1000), "own seed_group"),
        (change_item("A", "rules", 0, prey_survival_denominator=399), "inconsistent"),
        (change_item("A", "rules", 0, exposure=0), "exposure > 0"),
        (change_item("B", "rules", 0, prey_alive_end=9), r"prey alive \+ captured"),
        (change_item("A", "rules", 0, plant_energy=31.0), "not the recorded value"),
        (change_item("A", "rules", 0, config_hash="unknown"), "config_hash"),
        (change_item("A", "rules", 0, stream_env_init=4), "stream_env_init"),
        (change_item("C", "rules", 3, iteration=7), "iteration"),
    ],
)
def test_invalid_rows_stop_the_evaluation(tmp_path, edit, message) -> None:
    directory = write_block(tmp_path / "block", "entry", edit)
    with pytest.raises(crit.CriteriaError, match=message):
        crit.load_block(directory)


def test_an_incomplete_block_stops_the_evaluation(tmp_path) -> None:
    """A missing episode (here, an unpaired rules row) is never ignored."""
    directory = write_block(tmp_path / "block", "entry")
    rewrite(directory, "episodes.csv", lambda text: text.replace(text.splitlines()[1] + "\n", ""))
    record = json.loads((directory / "provenance.json").read_text(encoding="utf-8"))
    record["episodes_written"] = record["episodes_planned"] = record["episodes_written"] - 1
    (directory / "provenance.json").write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(crit.CriteriaError, match="missing episodes"):
        crit.load_block(directory)


def test_reordered_columns_stop_the_evaluation(tmp_path) -> None:
    directory = write_block(tmp_path / "block", "A")
    rewrite(directory, "episodes.csv", lambda text: text.replace("block,stage", "stage,block", 1))
    with pytest.raises(crit.CriteriaError, match="columns"):
        crit.load_block(directory)


@pytest.mark.parametrize(
    ("provenance_edit", "message"),
    [
        (lambda r: r.update(status="failed", a2_violation=False), "only a completed block"),
        (lambda r: r.update(a2_violation=True), "A2 violation"),
        (lambda r: r.update(a2_violation=None), "only a completed block"),
        (lambda r: r.update(schema="other/1"), "not a P1 provenance"),
        (lambda r: r.update(project_seed="1"), "project_seed"),
        (lambda r: r.update(bootstrap_run=2), "bootstrap_run"),
        (lambda r: r.update(scenarios=["A", "B"]), "scenarios"),
    ],
)
def test_the_provenance_must_be_a_completed_consistent_record(
    tmp_path, provenance_edit, message
) -> None:
    directory = write_block(tmp_path / "block", "C", provenance_edit=provenance_edit)
    with pytest.raises(crit.CriteriaError, match=message):
        crit.load_block(directory)


def test_files_changed_after_publication_are_refused(tmp_path) -> None:
    directory = write_block(tmp_path / "block", "B")
    path = directory / "bootstrap_keys.csv"
    path.write_text(path.read_text(encoding="utf-8").replace("B2_PREY_B", "B2_PREY_X"))
    with pytest.raises(crit.CriteriaError, match="SHA-256"):
        crit.load_block(directory)
    rewrite(directory, "bootstrap_keys.csv", lambda text: text)  # hash fixed, content still wrong
    with pytest.raises(crit.CriteriaError, match="comparison_name"):
        crit.load_block(directory)


def test_a_rules_condition_without_predators_stops_b3(tmp_path) -> None:
    edit = where(
        "A",
        "rules",
        n_predators=0,
        predators_alive_end=0,
        predators_reaching_half=0,
        predators_alive_at_t_max=0,
    )
    with pytest.raises(crit.CriteriaError, match="B3 needs predators"):
        crit.evaluate_block(crit.load_block(write_block(tmp_path / "block", "A", edit)))


# ---------------------------------------------------------------- bootstrap (I2)


def test_the_rebuilt_generator_is_the_registry_generator(tmp_path) -> None:
    """P1-20: each key row rebuilds exactly ``SeedRegistry.generator`` of its comparison."""
    block = crit.load_block(write_block(tmp_path / "block", "B"))
    registry = SeedRegistry(int(SEED))
    states = []
    for row in block.keys:
        expected = registry.generator(
            Purpose.ANALYSIS, GROUPS["A"], 2, 0, row["comparison"], Stream.BOOTSTRAP
        )
        state = crit.bootstrap_generator(row).bit_generator.state
        assert state == expected.bit_generator.state
        states.append(str(state))
    assert len(set(states)) == len(states) == 5  # comparisons 1, 3, 4, 6, 7 of stage B


SCRIPT = """
import json, sys
from pathlib import Path
from neuroeco.analysis import calibration as crit
results = crit.evaluate_block(crit.load_block(Path(sys.argv[1])))
print(json.dumps([repr(r) for r in results]))
"""


def test_bootstrap_results_are_reproducible_across_processes(tmp_path) -> None:
    """Same intervals in this process, again, and under two other PYTHONHASHSEED values."""
    directory = write_block(tmp_path / "block", "entry")
    here = [repr(r) for r in crit.evaluate_block(crit.load_block(directory))]
    assert here == [repr(r) for r in crit.evaluate_block(crit.load_block(directory))]
    for hash_seed in ("0", "4242"):
        completed = subprocess.run(
            [sys.executable, "-c", SCRIPT, str(directory)],
            capture_output=True,
            encoding="utf-8",
            check=True,
            env={**os.environ, "PYTHONHASHSEED": hash_seed},
        )
        assert json.loads(completed.stdout) == here


def interval(lower: float | None, upper: float | None) -> BootstrapInterval:
    return BootstrapInterval(-0.5, lower, upper, lower is not None, 0.95, 9999)


@pytest.mark.parametrize(
    ("delta", "bca", "expected"),
    [
        (Fraction(-1, 2), interval(-0.8, -0.01), "pass"),
        (Fraction(-1, 2), interval(-0.8, 0.0), "fail"),  # 0 is not excluded: no tolerance
        (Fraction(-1, 2), interval(-0.8, 0.2), "fail"),
        (Fraction(-1), interval(None, None), "pass"),  # D1: degenerate interval {-1}
        (Fraction(0), interval(None, None), "fail"),
        (Fraction(1), interval(None, None), "fail"),
    ],
)
def test_the_a6_decision_rule(delta, bca, expected) -> None:
    status, text = crit.a6_decision(delta, bca)
    assert status == expected
    assert ("{-1}" in text) == (delta == -1 and not bca.estimable)


def a6_case(tmp_path, b_numerators, a_numerators=None, episodes=EPISODES):
    def edit(row: dict) -> None:
        values = {"B": b_numerators, "A": a_numerators}.get(row["scenario"])
        if row["condition"] == "rules" and values is not None:
            row["prey_survival_numerator"] = values[row["item"]]

    directory = write_block(tmp_path / "block", "B", edit, episodes=episodes)
    return evaluate_all(directory)[("A6", "", "B-A")]


def test_a6_with_complete_separation_uses_the_degenerate_interval(tmp_path) -> None:
    """Default block: every B episode survives less than every A episode (delta = -1)."""
    result = a6_case(tmp_path, [100, 110, 120, 130])
    assert result.status == "pass" and not result.interval.estimable
    assert "delta(B, A) = -1" in result.value and "{-1}" in result.value


@pytest.mark.parametrize(
    ("b_numerators", "a_numerators", "message"),
    [
        ([300, 310, 320, 330], None, "delta(B, A) = 1;"),  # separation in the wrong direction
        ([200, 210, 220, 230], None, "delta(B, A) = 0;"),  # same distribution
        ([210] * 4, [210] * 4, "BCa not estimable"),  # degenerate samples
    ],
)
def test_a6_fails_without_a_lower_survival_in_b(tmp_path, b_numerators, a_numerators, message):
    result = a6_case(tmp_path, b_numerators, a_numerators)
    assert result.status == "fail" and message in result.value


def test_a6_with_an_estimable_interval(tmp_path) -> None:
    """30 episodes per sample with overlap: the BCa is estimable and its upper limit < 0."""
    result = a6_case(
        tmp_path, [100 + 5 * i for i in range(30)], [150 + 5 * i for i in range(30)], episodes=30
    )
    assert result.interval.estimable and result.interval.upper < 0
    assert result.status == "pass"


def test_the_b2_interval_is_descriptive(tmp_path) -> None:
    """D3 scales; the verdict stays the sign of the sum of the paired differences (P1-7)."""
    directory = write_block(tmp_path / "block", "entry")
    block = crit.load_block(directory)
    deterministic = crit.deterministic_criteria(block)
    full = crit.evaluate_block(block)
    assert [dataclasses.replace(r, interval=None) for r in full if r.criterion != "A6"] == list(
        deterministic
    )
    assert {r.criterion for r in full if r.interval is not None} == {"A6", "B2"}
    results = {r.key: r for r in full}
    prey, predator = results[("B2", "prey", "A")], results[("B2", "predator", "A")]
    assert (prey.interval.resamples, prey.interval.confidence) == (9999, 0.95)
    assert prey.interval.estimate == pytest.approx(0.25)  # survival: 100 / 400 per pair
    assert predator.interval.estimate == pytest.approx(0.25)  # captured: (2, 3, 2, 3) / 10
    # A positive sum with mostly negative differences: B2 is met whatever the interval says.
    skewed = where("A", "random_prey", prey_survival_numerator=[240, 250, 260, 100])
    result = evaluate_all(write_block(tmp_path / "skewed", "entry", skewed))[("B2", "prey", "A")]
    assert result.status == "pass" and result.value == "1/40"
    assert result.interval.lower is None or result.interval.lower < 0


@pytest.mark.parametrize(
    ("change", "seed", "message"),
    [
        (lambda text: text.replace(text.splitlines()[1] + "\n", ""), SEED, "comparisons"),
        (lambda text: text + text.splitlines()[1] + "\n", SEED, "comparisons"),
        (lambda text: text.replace(SEED, "0" + SEED), "0" + SEED, "not a decimal integer"),
        (lambda text: text.replace(SEED, str(2**128)), str(2**128), r"outside \(0, 2\*\*128\)"),
    ],
)
def test_missing_duplicated_or_invalid_keys_stop_the_evaluation(
    tmp_path, change, seed, message
) -> None:
    directory = write_block(
        tmp_path / "block", "B", provenance_edit=lambda r: r.update(project_seed=seed)
    )
    rewrite(directory, "bootstrap_keys.csv", change)
    with pytest.raises(crit.CriteriaError, match=message):
        crit.load_block(directory)
