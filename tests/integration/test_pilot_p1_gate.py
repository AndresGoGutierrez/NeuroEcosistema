"""F4 T4c (C3, D-T4c-5): ``pilot p1`` verifies the P1-18 sequence before running a block.

With the real seed groups no episode may ever start in a test: the block runner is replaced by
a guard, so these tests stop in the pre-flight or at the first episode. The tests that need
published results use the synthetic specification (seed groups >= 1000, t_max = 40, D16) and
replace the predicate that exempts it, as T3-5 replaces the git facts; the production checks
are unchanged.
"""

import copy
import inspect

import pytest
import yaml
from typer.testing import CliRunner

from neuroeco.application import calibration
from neuroeco.infrastructure.provenance import file_sha256
from neuroeco.presentation import pilot_p1, pilot_p1_criteria, pilot_p1_sequence
from neuroeco.presentation.cli import app
from p1_support import (
    PASSING_GIT_CHECKS,
    SYNTHETIC_SPEC,
    VALUES,
    assert_no_results,
    invoke,
    last_failure,
    make_configs,
    only_failure,
    read_json,
    register,
    run_chain,
    run_ok,
    simulate_git,
    write_spec,
)

CRITERIA_CHECKS = {
    **PASSING_GIT_CHECKS,
    "result_inside": True,
    "result_directory": "simulated",
    "untracked_elsewhere": [],
}


class EpisodeGuardError(Exception):
    """Raised instead of running the first episode."""


@pytest.fixture
def setup(tmp_path, monkeypatch):
    output = tmp_path / "out"
    configs = make_configs(tmp_path)
    state = simulate_git(monkeypatch, output)
    return configs, output, state


def guard_episodes(monkeypatch) -> None:
    def guard(*args, **kwargs):
        raise EpisodeGuardError("an episode with real seed groups was about to start")

    monkeypatch.setattr(pilot_p1, "iter_block", guard)


def real_spec(configs, groups=None) -> None:
    """The approved table of P1-13 and P1-5 (or other non-synthetic ``groups``)."""
    spec = copy.deepcopy(SYNTHETIC_SPEC)
    for block, (episodes, approved) in calibration.APPROVED_BLOCKS.items():
        chosen = approved if groups is None else groups[block]
        spec["blocks"][block] = {
            "episodes": episodes if groups is None else 2,
            "seed_groups": dict(zip("abc", chosen, strict=True)),
        }
    write_spec(configs, spec)


def criteria(monkeypatch, directory) -> None:
    monkeypatch.setattr(
        pilot_p1_criteria, "repository_checks", lambda cwd, result: dict(CRITERIA_CHECKS)
    )
    result = CliRunner().invoke(app, ["pilot", "p1-criteria", "--result", str(directory)])
    assert result.exit_code == 0, result.output


def refused_in_preflight(output, state, fragment: str, reference: str = "D-T4c-5") -> dict:
    """The block was refused before any episode, the git checks and anything else were run."""
    assert_no_results(output)
    assert state["inputs"] is None  # the repository checks come later: never reached
    _, failure = only_failure(output)
    assert failure["phase"] == "preflight"
    assert failure["error_type"].endswith("P1RefusalError")
    assert reference in failure["message"] and fragment in failure["message"]
    assert failure["episodes_completed"] == 0
    return failure


# ---------------------------------------------------------------- real seed groups


def test_a_real_sequence_that_is_not_allowed_is_refused_before_any_episode(
    setup, monkeypatch
) -> None:
    configs, output, state = setup
    real_spec(configs)
    guard_episodes(monkeypatch)
    register(configs, 1, "A")
    second = register(configs, 2, "A", "plant_energy", plant_energy=35.0)
    result = invoke(configs, output, "--iteration", str(second))
    assert result.exit_code == 1
    refused_in_preflight(output, state, "allows iteration 1 (stage A) next, not iteration 2")


def test_a_real_sequence_that_is_allowed_reaches_the_execution_protections(
    setup, monkeypatch
) -> None:
    """Iteration 1 is the step P1-18 allows: the gate lets it through to the git checks and
    the execution, where the guard stops it before the first episode."""
    configs, output, state = setup
    real_spec(configs)
    guard_episodes(monkeypatch)
    result = invoke(configs, output, "--iteration", str(register(configs, 1, "A")))
    assert result.exit_code == 1
    assert state["inputs"] is not None  # the repository checks ran after the gate
    assert_no_results(output)
    directory, failure = only_failure(output)
    assert failure["phase"] == "execution"
    assert "about to start" in failure["message"] and failure["episodes_completed"] == 0
    gate = read_json(directory / "provenance.json")["sequence_gate"]
    assert (gate["applied"], gate["step"], gate["verdict"]) == (True, "iteration 1", "allowed")


# ---------------------------------------------------------------- synthetic specifications


def test_synthetic_specifications_keep_the_previous_behaviour(setup, monkeypatch) -> None:
    """The T3 chain (A -> B -> C without criteria or rounds) still runs: no verification."""
    configs, output, _ = setup

    def never(*args, **kwargs):
        raise AssertionError("the sequence gate ran for a synthetic specification")

    monkeypatch.setattr(pilot_p1_sequence, "check_sequence_gate", never)
    last = run_chain(configs, output)
    run_ok(configs, output, "--entry-evaluation", "--values-from", str(last))
    for leaf in ("iteration_001", "iteration_002", "iteration_003", "entry"):
        gate = read_json(output / "calibration" / leaf / "provenance.json")["sequence_gate"]
        assert gate == pilot_p1.SYNTHETIC_GATE_RECORD


# ---------------------------------------------------------------- no way around it


def test_the_command_has_no_option_to_skip_the_verification() -> None:
    options = set(inspect.signature(pilot_p1.pilot_p1).parameters)
    assert options == {
        "iteration",
        "entry_evaluation",
        "confirmation",
        "second_confirmation",
        "values_from",
        "author_authorized",
        "spec_path",
        "config_dir",
        "output_root",
        "round_spec",
        "round_phase",
    }
    # The predicate depends on the seed groups of the specification only.
    assert list(inspect.signature(calibration.sequence_gate_required).parameters) == ["spec"]


def test_a_command_line_option_never_replaces_a_decision_of_the_author(setup) -> None:
    """D-T4d-3: --d9-confirmed is gone; the option is a usage error and nothing is written."""
    configs, output, _ = setup
    result = invoke(
        configs, output, "--iteration", str(register(configs, 1, "A")), "--d9-confirmed", "1"
    )
    assert result.exit_code == 2 and "No such option" in result.output
    assert not output.exists()


def d9_decision(configs, number: int, iteration: int, spec_path) -> None:
    path = configs / "pilots" / "p1_decisions" / f"{number:03d}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    content = {
        "schema": "neuroeco.p1-decision/1",
        "decision": number,
        "kind": "d9_e5",
        "step": {"kind": "iteration", "number": iteration},
        "plant_energy_needed": 1000.0,
        "iteration_spec_sha256": file_sha256(spec_path),
        "justification": "synthetic test decision",
    }
    path.write_text(yaml.safe_dump(content), encoding="utf-8")


@pytest.mark.parametrize("decision", [False, True])
@pytest.mark.parametrize(
    "groups",
    [
        None,  # the approved table
        {  # neither real nor synthetic: the gate still applies
            "calibration": (40, 41, 42),
            "confirmation": (43, 44, 45),
            "second_confirmation": (46, 47, 48),
        },
    ],
)
def test_changing_the_specification_or_adding_a_decision_does_not_skip_it(
    setup, monkeypatch, groups, decision
) -> None:
    """A decision of the author only confirms what it is bound to: here it opens nothing."""
    configs, output, state = setup
    real_spec(configs, groups)
    guard_episodes(monkeypatch)
    register(configs, 1, "A")
    second = register(configs, 2, "A", "plant_energy", plant_energy=35.0)
    if decision:
        d9_decision(configs, 1, 2, second)
    result = invoke(configs, output, "--iteration", str(second))
    assert result.exit_code == 1
    if decision:
        refused_in_preflight(output, state, "does not change n_plants_a", "D-T4d-3")
    else:
        refused_in_preflight(output, state, "not iteration 2")


# ---------------------------------------------------------------- the verification itself


def test_the_gate_reads_the_published_results_and_their_criteria(setup, monkeypatch) -> None:
    """Synthetic results, with the exemption removed: the gate of a real experiment."""
    configs, output, state = setup
    monkeypatch.setattr(pilot_p1, "sequence_gate_required", lambda spec: True)
    first = output / "calibration" / "iteration_001"
    run_ok(configs, output, "--iteration", str(register(configs, 1, "A")))
    gate = read_json(first / "provenance.json")["sequence_gate"]
    assert (gate["applied"], gate["verdict"]) == (True, "allowed")

    # The chain of the T3 tests: refused without criteria, and refused by P1-18 with them.
    stage_b = register(configs, 2, "B")
    assert invoke(configs, output, "--iteration", str(stage_b)).exit_code == 1
    failure = last_failure(output / "calibration", "iteration_002")
    assert "run pilot p1-criteria first" in failure["message"]
    criteria(monkeypatch, first)
    assert invoke(configs, output, "--iteration", str(stage_b)).exit_code == 1
    failure = last_failure(output / "calibration", "iteration_002")
    assert failure["phase"] == "preflight" and "D-T4c-5" in failure["message"]
    assert "does not allow iteration 2 (stage B): rejected" in failure["message"]
    assert not (output / "calibration" / "iteration_002").exists()

    # Premise of this synthetic configuration: iteration 1 misses S_A, so P1-18 asks for
    # A_ajuste; a round is refused, and the stage-A iteration runs.
    stage_b.unlink()
    assert not pilot_p1_sequence.block_outcome(first, "A").requirements_met
    round_path = register_round(configs, 1, 1)
    result = invoke(configs, output, "--round", str(round_path), "--phase", "prey")
    assert result.exit_code == 1
    failure = last_failure(output / "calibration" / "round_01", "prey_grid")
    assert "D-T4c-5" in failure["message"]
    assert "the next step must be a stage-A iteration" in failure["message"]
    assert not (output / "calibration" / "round_01" / "prey_grid").exists()
    round_path.unlink()

    path = register(configs, 2, "A", "plant_energy", plant_energy=35.0)
    run_ok(configs, output, "--iteration", str(path))
    gate = read_json(output / "calibration" / "iteration_002" / "provenance.json")
    gate = gate["sequence_gate"]
    assert gate["applied"] and gate["verdict"] == "allowed"
    assert gate["transitions"] == ["iteration 1 (stage A) -> iteration 2 (stage A): allowed"]
    # every file the gate read is declared, so it is checked against HEAD (P1-19)
    read = {p.name for p in state["inputs"] if p.parent == first}
    assert {"criteria.csv", "criteria_provenance.json", "episodes.csv"} <= read


def register_round(configs, number: int, after: int):
    path = configs / "pilots" / "p1" / "rounds" / f"{number:02d}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    content = {
        "round_number": number,
        "after_iteration": after,
        "values": dict(VALUES),
        "motive": "synthetic test round",
        "exploratory_observations": "",
    }
    path.write_text(yaml.safe_dump(content), encoding="utf-8")
    return path
