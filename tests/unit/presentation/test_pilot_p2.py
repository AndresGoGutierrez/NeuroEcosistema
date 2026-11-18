"""F6: P2 grid and the decision rules of ADR-035, on synthetic run logs."""

import csv

import pytest

from neuroeco.infrastructure.run_store import GENERATION_COLUMNS
from neuroeco.presentation.pilot_p2 import (
    NETWORKS,
    PILOT_GENERATIONS,
    SIGMAS,
    decide,
    p2_specs,
)


def test_the_grid_has_distinct_seed_groups_per_network_and_sigma() -> None:
    specs = p2_specs()
    assert len(specs) == len(NETWORKS) * len(SIGMAS) * 2
    assert len({s.name for s in specs}) == len(specs)
    groups = {(s.architecture, s.sigma): s.seed_group for s in specs}
    assert len(set(groups.values())) == len(groups) == 12
    assert all(s.scenario == "A" and s.population == 40 and s.episodes == 4 for s in specs)


def write_run(root, name, curve, zero=0.0) -> None:
    """``curve(g)`` gives F_val at validated generations (every 5 and the last)."""
    directory = root / "runs" / name
    directory.mkdir(parents=True)
    (directory / "summary.json").write_text("{}", encoding="utf-8")
    with (directory / "generations.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=GENERATION_COLUMNS)
        writer.writeheader()
        for g in range(PILOT_GENERATIONS):
            validated = g % 5 == 0 or g == PILOT_GENERATIONS - 1
            row = dict.fromkeys(GENERATION_COLUMNS, 0)
            row.update(generation=g, zero_share=zero if g < 10 else 0.0)
            row["f_val"] = repr(curve(g)) if validated else ""
            writer.writerow(row)


def saturating(start, top, at):
    return lambda g: start + (top - start) * min(1.0, g / at)


@pytest.fixture
def p2(tmp_path):
    for spec in p2_specs():
        # sigma 0.05 is best for every network; it saturates at generation 20
        top = 0.6 if spec.sigma == 0.05 else 0.4
        zero = 0.9 if spec.architecture == "predator_base" else 0.0
        write_run(tmp_path, spec.name, saturating(0.2, top, 20), zero)
    return tmp_path


def test_decision_applies_adr_035(p2) -> None:
    decision = decide(p2)
    assert set(decision["sigma"].values()) == {0.05}
    # 95 % of the gain is reached at the validated generation 20 -> G = ceil(1.25 * 20) = 25,
    # rounded up to a multiple of k_val and at least 60
    assert decision["stagnation_generation"]["prey_base"] == 20
    assert decision["G"] == 60
    assert decision["curriculum"]["active"] is True
    assert decision["curriculum"]["kappa"] == 2.0 and decision["curriculum"]["G_c"] == 30
    prey = decision["targets"]["prey"]
    assert prey["F0"] == pytest.approx(0.2) and prey["F_base"] == pytest.approx(0.6)
    assert prey["delta"] == pytest.approx(0.04) and prey["theta"] == pytest.approx(0.56)


def test_sigma_ties_go_to_the_smaller_sigma_and_late_learning_gives_75(tmp_path) -> None:
    for spec in p2_specs():
        write_run(tmp_path, spec.name, saturating(0.1, 0.5, 59))
    decision = decide(tmp_path)
    assert set(decision["sigma"].values()) == {0.02}
    assert decision["G"] == 75
    assert decision["curriculum"]["active"] is False


def test_a_missing_run_is_an_error(tmp_path) -> None:
    for spec in p2_specs()[1:]:
        write_run(tmp_path, spec.name, saturating(0.1, 0.5, 20))
    with pytest.raises(FileNotFoundError, match="missing or incomplete"):
        decide(tmp_path)
