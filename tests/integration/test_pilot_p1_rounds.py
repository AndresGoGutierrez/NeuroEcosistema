"""F4 T4c (C1): the grids of a rule-tuning round through ``neuroeco pilot p1 --round``.

Synthetic configuration only (seed groups >= 1000, t_max = 40, D16) with simulated git facts.
To make a winner predictable, ``favour`` raises the objective of one combination in the rows
the command writes; everything downstream (selection, recomputation, integrity) runs on the
published files as in a real round.
"""

import dataclasses
import json

import pytest
import yaml

from neuroeco.analysis.calibration import grid_selection, read_episodes, render_selection
from neuroeco.application import calibration as app
from neuroeco.presentation import pilot_p1
from p1_support import VALUES, invoke, make_configs, read_json, register, run_ok, simulate_git

PREY_WINNER = {"prey_flee_threshold": 0.5, "prey_cruise_fraction": 0.3}


def register_round(configs, number: int, after: int, **values):
    path = configs / "pilots" / "p1" / "rounds" / f"{number:02d}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    content = {
        "round_number": number,
        "after_iteration": after,
        "values": {**VALUES, **values},
        "motive": "synthetic test round",
        "exploratory_observations": "",
    }
    path.write_text(yaml.safe_dump(content), encoding="utf-8")
    return path


def round_phase(configs, output, path, phase):
    return invoke(configs, output, "--round", str(path), "--phase", phase)


def favour(monkeypatch, stage: str, **combination) -> None:
    """Rows of ``combination`` in grid ``stage`` get the best objective of P1-17."""
    real = pilot_p1.episode_row

    def row(outcome, world, *, stage: str, iteration: int, values):
        result = real(outcome, world, stage=stage, iteration=iteration, values=values)
        if result["stage"] == wanted and all(
            getattr(values, k) == v for k, v in combination.items()
        ):
            result["prey_survival_numerator"] = result["prey_survival_denominator"]
            result["prey_captured"] = result["n_prey"]
        return result

    wanted = stage
    monkeypatch.setattr(pilot_p1, "episode_row", row)


@pytest.fixture
def anchored(tmp_path, monkeypatch):
    """Iteration 1 (stage A) published and round 1 registered after it."""
    output = tmp_path / "out"
    configs = make_configs(tmp_path)
    simulate_git(monkeypatch, output)
    run_ok(configs, output, "--iteration", str(register(configs, 1, "A")))
    return configs, output, register_round(configs, 1, 1)


def grid_directory(output, phase):
    return output / "calibration" / "round_01" / pilot_p1.PHASE_LEAVES[phase]


def test_the_grids_publish_their_rows_and_winners(anchored, monkeypatch) -> None:
    configs, output, path = anchored
    favour(monkeypatch, "round_prey", **PREY_WINNER)
    assert round_phase(configs, output, path, "prey").exit_code == 0
    prey = grid_directory(output, "prey")
    assert sorted(p.name for p in prey.iterdir()) == [
        "episodes.csv",
        "provenance.json",
        "selection.json",
    ]
    rows = read_episodes(prey / "episodes.csv")
    assert len(rows) == 12 * 2  # 12 combinations x 2 synthetic episodes
    assert {(r["scenario"], r["condition"], r["stage"], r["iteration"]) for r in rows} == {
        ("A", "rules", "round_prey", 1)
    }
    assert len({(r["prey_flee_threshold"], r["prey_cruise_fraction"]) for r in rows}) == 12
    selection = json.loads((prey / "selection.json").read_text(encoding="utf-8"))
    assert selection["winner"] == PREY_WINNER and len(selection["totals"]) == 12
    record = read_json(prey / "provenance.json")
    assert (record["round"], record["phase"], record["values"]) == (1, "prey", VALUES)
    assert set(record["result_files"]) == {"episodes.csv", "selection.json"}

    assert round_phase(configs, output, path, "predator").exit_code == 0
    predator = grid_directory(output, "predator")
    record = read_json(predator / "provenance.json")
    assert record["values"] == {**VALUES, **PREY_WINNER}  # the prey winner, recomputed
    rows = read_episodes(predator / "episodes.csv")
    assert len(rows) == 3 * 2
    assert {(r["prey_flee_threshold"], r["prey_cruise_fraction"]) for r in rows} == {(0.5, 0.3)}
    recomputed = grid_selection(rows, "predator", (), (0.3, 0.5, 0.7), record["values"])
    assert render_selection(recomputed, "predator") == (predator / "selection.json").read_bytes()


def test_the_combination_in_force_must_reproduce_the_previous_evaluation(
    anchored, monkeypatch
) -> None:
    """D-T4c-4: a different episode of the combination in force stops the round."""
    configs, output, path = anchored
    real = pilot_p1.episode_row

    def drift(outcome, world, *, stage: str, iteration: int, values):
        row = real(outcome, world, stage=stage, iteration=iteration, values=values)
        if stage == "round_prey" and values == app.CandidateValues(**VALUES) and row["item"] == 1:
            row["plants_eaten"] += 1
        return row

    monkeypatch.setattr(pilot_p1, "episode_row", drift)
    result = round_phase(configs, output, path, "prey")
    assert result.exit_code == 1 and "D-T4c-4" in result.output
    assert not grid_directory(output, "prey").exists()
    assert list((output / "calibration" / "round_01").glob("prey_grid.failed-*"))


def test_the_predator_grid_needs_an_intact_prey_grid(anchored, monkeypatch) -> None:
    configs, output, path = anchored
    result = round_phase(configs, output, path, "predator")
    assert result.exit_code == 1 and "published, completed result first" in result.output

    assert round_phase(configs, output, path, "prey").exit_code == 0
    prey = grid_directory(output, "prey")
    forged = json.loads((prey / "selection.json").read_text(encoding="utf-8"))
    forged["winner"] = PREY_WINNER  # a forged winner with a consistent SHA-256 record
    (prey / "selection.json").write_text(json.dumps(forged), encoding="utf-8")
    record = read_json(prey / "provenance.json")
    record["result_files"]["selection.json"] = pilot_p1.file_sha256(prey / "selection.json")
    (prey / "provenance.json").write_text(json.dumps(record), encoding="utf-8")
    result = round_phase(configs, output, path, "predator")
    assert result.exit_code == 1 and "is not the selection recomputed" in result.output


def test_a_round_needs_its_anchor_iteration(tmp_path, monkeypatch) -> None:
    output = tmp_path / "out"
    configs = make_configs(tmp_path)
    simulate_git(monkeypatch, output)
    register(configs, 1, "A")
    path = register_round(configs, 1, 1)
    result = round_phase(configs, output, path, "prey")
    assert result.exit_code == 1 and "iteration_001" in result.output


@pytest.mark.parametrize(
    "arguments",
    [
        ("--phase", "prey"),  # a phase without a round
        ("--round", "01.yaml"),  # a round without a phase
        ("--round", "01.yaml", "--phase", "grid"),
    ],
)
def test_round_options_are_checked(anchored, arguments) -> None:
    configs, output, path = anchored
    resolved = [str(path) if a == "01.yaml" else a for a in arguments]
    result = invoke(configs, output, *resolved)
    assert result.exit_code == 1 and "--round" in result.output


def test_the_grid_plan_is_checked_independently(anchored) -> None:
    configs, _, _ = anchored
    spec = pilot_p1.load_p1_spec(configs / "pilots" / "p1.yaml", {})
    values = app.CandidateValues(**VALUES)
    planned = app.plan_grid(spec, values, "prey")
    app.check_grid_plan(planned, spec, values, "prey")
    with pytest.raises(ValueError, match="grid plan has 23 tasks"):
        app.check_grid_plan(planned[:-1], spec, values, "prey")
    task, combination = planned[0]
    other = app.condition_overrides(
        dataclasses.replace(combination, prey_flee_threshold=0.4), "A", "rules"
    )
    swapped = ((dataclasses.replace(task, overrides=other), combination), *planned[1:])
    with pytest.raises(ValueError, match="task 0 of the grid plan"):
        app.check_grid_plan(swapped, spec, values, "prey")
    duplicated = ((task, dataclasses.replace(combination, prey_flee_threshold=0.4)), *planned[1:])
    with pytest.raises(ValueError, match="planned twice"):
        app.check_grid_plan(duplicated, spec, values, "prey")
