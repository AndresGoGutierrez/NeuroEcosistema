"""F4 T3: the ``neuroeco pilot p1`` command (ADR-033; decisions T3-1 to T3-9, adapted in T3b).

Every run uses a temporary copy of the configuration with a synthetic P1 specification
(seed_group >= 1000, D16), t_max = 40 and energetics scaled so that E1 and E2 still hold, so state
K is evaluated, never bypassed. Results go to a temporary directory. The git facts (clean tree,
tracked inputs, synchronized upstream) are simulated by replacing two functions of the command
module (T3-5); the real checks are exercised in ``test_pilot_p1_git.py``. No real P1 episode,
specification or result is created.
"""

import dataclasses

import numpy as np
import pytest

from neuroeco.application import calibration
from neuroeco.application.calibration import (
    BOOTSTRAP_COLUMNS,
    EPISODE_COLUMNS,
    InvariantViolationError,
    keys_from_columns,
)
from neuroeco.application.seeding import Purpose, SeedRegistry
from neuroeco.infrastructure.config_loader import load_config
from neuroeco.presentation import pilot_p1
from p1_support import (
    VALUES,
    assert_no_results,
    failures,
    invoke,
    make_configs,
    only_failure,
    read_csv,
    read_json,
    register,
    run_chain,
    run_ok,
    simulate_git,
)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    """Synthetic configuration, empty output root and simulated git facts."""
    output = tmp_path / "out"
    return make_configs(tmp_path), output, simulate_git(monkeypatch, output)


# ---------------------------------------------------------------- a successful iteration


def test_iteration_writes_episodes_keys_and_provenance(setup) -> None:
    configs, output, state = setup
    path = register(configs, 1, "A")
    result = invoke(configs, output, "--iteration", str(path))
    assert result.exit_code == 0, result.output
    destination = output / "calibration" / "iteration_001"
    assert sorted(p.name for p in destination.iterdir()) == [
        "bootstrap_keys.csv",
        "episodes.csv",
        "provenance.json",
    ]
    assert sorted(p.name for p in output.rglob("*") if p.is_dir()) == [
        "calibration",
        "iteration_001",
    ]
    assert state["files_at_capture"] == [[]]  # provenance captured before anything was written

    header, rows = read_csv(destination / "episodes.csv")
    assert tuple(header) == EPISODE_COLUMNS
    assert len(rows) == 12 * 2
    assert {r["scenario"] for r in rows} == {"A"}
    assert {(r["block"], r["stage"], r["iteration"]) for r in rows} == {("calibration", "A", "1")}
    assert [r["condition"] for r in rows[::2]] == [
        c.name for c in calibration.CONDITIONS_BY_SCENARIO["A"]
    ]
    for row in rows:
        task = calibration.condition_overrides(
            calibration.CandidateValues(**VALUES), "A", row["condition"]
        )
        assert row["config_hash"] == load_config(configs, "A", task).config_hash
        assert row["seed_group"] == "1000" and row["t_max"] == "40"
    assert {r["n_predators"] for r in rows if r["condition"] == "no_predators"} == {"0"}

    header, keys = read_csv(destination / "bootstrap_keys.csv")
    assert tuple(header) == BOOTSTRAP_COLUMNS
    assert [(k["comparison"], k["seed_group"], k["run"], k["stream"]) for k in keys] == [
        ("3", "1000", "1", "7"),
        ("6", "1000", "1", "7"),
    ]

    provenance = read_json(destination / "provenance.json")
    assert provenance["status"] == "completed" and provenance["git_dirty"] is False
    assert (provenance["mode"], provenance["block"], provenance["bootstrap_run"]) == (
        "iteration",
        "calibration",
        1,
    )
    assert provenance["episodes_planned"] == provenance["episodes_written"] == 24
    assert provenance["episodes_discarded"] == 0 and provenance["values_iteration"] == 1
    assert provenance["prerequisites"] == [] and provenance["previous_attempts"] == []
    assert provenance["git_checks"]["synchronized"] is True
    assert provenance["values"] == VALUES and provenance["state_k"]["a1"] is True
    assert provenance["project_seed"] == keys[0]["project_seed"]
    assert provenance["dependencies"]["numpy"] and provenance["uv_lock_sha256"]
    assert [p["path"].endswith("001.yaml") for p in provenance["registered_iterations"]] == [True]


def test_key_columns_in_the_csv_rebuild_the_episode_streams(setup) -> None:
    configs, output, _ = setup
    run_ok(configs, output, "--iteration", str(register(configs, 1, "A")))
    destination = output / "calibration" / "iteration_001"
    _, rows = read_csv(destination / "episodes.csv")
    seed = int(read_json(destination / "provenance.json")["project_seed"])
    for row in (rows[0], rows[-1]):
        keys = keys_from_columns({k: int(row[k]) for k in calibration.KEY_COLUMNS})
        expected = SeedRegistry(seed).episode_streams(
            Purpose.PILOT, int(row["seed_group"]), 0, 0, int(row["item"])
        )
        for column, attribute in (
            ("stream_env_init", "env_init"),
            ("stream_env_dynamics", "env_dynamics"),
            ("stream_policy_prey", "policy_prey"),
            ("stream_policy_predator", "policy_predator"),
        ):
            rebuilt = np.random.default_rng(np.random.SeedSequence(seed, spawn_key=keys[column]))
            assert rebuilt.bit_generator.state == getattr(expected, attribute).bit_generator.state


@pytest.mark.determinism
def test_equivalent_runs_write_byte_identical_csv_files(setup, tmp_path) -> None:
    configs, output, _ = setup
    path = register(configs, 1, "A")
    second = tmp_path / "second"
    run_ok(configs, output, "--iteration", str(path))
    run_ok(configs, second, "--iteration", str(path))
    for name in ("episodes.csv", "bootstrap_keys.csv"):
        first_bytes = (output / "calibration" / "iteration_001" / name).read_bytes()
        assert first_bytes == (second / "calibration" / "iteration_001" / name).read_bytes()


# ---------------------------------------------------------------- entry and confirmation


def test_entry_evaluation_runs_the_35_conditions(setup) -> None:
    configs, output, _ = setup
    last = run_chain(configs, output)
    run_ok(configs, output, "--entry-evaluation", "--values-from", str(last))
    destination = output / "calibration" / "entry"
    _, rows = read_csv(destination / "episodes.csv")
    assert len(rows) == 35 * 2 and {r["stage"] for r in rows} == {"entry"}
    _, keys = read_csv(destination / "bootstrap_keys.csv")
    assert [k["comparison"] for k in keys] == [str(i) for i in range(1, 9)]
    assert {(k["seed_group"], k["run"]) for k in keys} == {("1000", "0")}
    provenance = read_json(destination / "provenance.json")
    assert [p["directory"].rsplit("/", 1)[-1] for p in provenance["prerequisites"]] == [
        "iteration_001",
        "iteration_002",
        "iteration_003",
    ]


def test_confirmation_needs_the_author_authorization(setup) -> None:
    configs, output, _ = setup
    last = run_chain(configs, output)
    run_ok(configs, output, "--entry-evaluation", "--values-from", str(last))
    refused = invoke(configs, output, "--confirmation", "--values-from", str(last))
    assert refused.exit_code == 1
    [directory] = failures(output)
    failure = read_json(directory / "failure.json")
    assert failure["phase"] == "preflight" and "--author-authorized" in failure["message"]
    assert not (output / "confirmation" / "evaluation").exists()

    run_ok(configs, output, "--confirmation", "--values-from", str(last), "--author-authorized")
    destination = output / "confirmation" / "evaluation"
    _, rows = read_csv(destination / "episodes.csv")
    assert len(rows) == 70 and {r["seed_group"] for r in rows} == {"1010", "1011", "1012"}
    _, keys = read_csv(destination / "bootstrap_keys.csv")
    assert {(k["seed_group"], k["run"]) for k in keys} == {("1010", "0")}
    provenance = read_json(destination / "provenance.json")
    assert provenance["author_authorized"] is True
    # the refused attempt is a failure record without A2 violation, kept in the provenance
    [attempt] = provenance["previous_attempts"]
    assert (attempt["kind"], attempt["a2_violation"]) == ("failure", False)


def test_values_must_come_from_the_last_stage_c_iteration(setup) -> None:
    configs, output, _ = setup
    first = register(configs, 1, "A")
    result = invoke(configs, output, "--entry-evaluation", "--values-from", str(first))
    assert result.exit_code == 1
    _, failure = only_failure(output)
    assert "last registered iteration, of stage C" in failure["message"]


@pytest.mark.parametrize(
    "arguments",
    [
        (),
        ("--entry-evaluation", "--confirmation"),
        ("--entry-evaluation",),
        ("--entry-evaluation", "--values-from", "SPEC", "--author-authorized"),
        ("--iteration", "SPEC", "--author-authorized"),
        ("--iteration", "SPEC", "--values-from", "SPEC"),
    ],
    ids=[
        "no-mode",
        "two-modes",
        "missing-values-from",
        "superfluous-authorization",
        "authorization-on-iteration",
        "values-from-on-iteration",
    ],
)
def test_usage_errors_create_nothing(setup, arguments) -> None:
    """Before the destination is known there is nowhere to record a failure: nothing is written."""
    configs, output, _ = setup
    path = str(register(configs, 1, "A"))
    result = invoke(configs, output, *(path if a == "SPEC" else a for a in arguments))
    assert result.exit_code == 1
    assert not output.exists()


# ---------------------------------------------------------------- pre-flight refusals


def test_existing_destination_is_refused_and_kept(setup) -> None:
    configs, output, _ = setup
    path = register(configs, 1, "A")
    run_ok(configs, output, "--iteration", str(path))
    destination = output / "calibration" / "iteration_001"
    before = (destination / "episodes.csv").read_bytes()
    result = invoke(configs, output, "--iteration", str(path))
    assert result.exit_code == 1
    assert (destination / "episodes.csv").read_bytes() == before
    _, failure = only_failure(output)
    assert failure["phase"] == "preflight" and "already exists" in failure["message"]


def test_dirty_tree_is_refused_and_recorded(setup) -> None:
    configs, output, state = setup
    state["git_dirty"] = True
    result = invoke(configs, output, "--iteration", str(register(configs, 1, "A")))
    assert result.exit_code == 1
    assert_no_results(output)
    directory, failure = only_failure(output)
    assert "working tree must be clean" in failure["message"]
    provenance = read_json(directory / "provenance.json")
    assert provenance["git_dirty"] is True and provenance["status"] == "failed"
    assert provenance["episodes_written"] is None and provenance["episodes_discarded"] == 0


def test_state_k_rejects_a_candidate_without_running(setup) -> None:
    configs, output, state = setup
    result = invoke(
        configs, output, "--iteration", str(register(configs, 1, "A", plant_energy=60.0))
    )
    assert result.exit_code == 1
    assert state["files_at_capture"] == []  # refused before the provenance capture
    _, failure = only_failure(output)
    assert "A1 does not hold" in failure["message"] and "E5" in failure["message"]
    # the rejected candidate is documented in its own failure record (T3b, M-5)
    assert failure["mode"]["values"]["plant_energy"] == 60.0
    assert failure["mode"]["values_source"]["sha256"]
    assert set(failure["git"]) == {"commit", "dirty", "upstream", "upstream_commit", "remote_url"}


def test_invalid_static_sequence_is_refused(setup) -> None:
    configs, output, _ = setup
    register(configs, 1, "A")
    two = register(configs, 2, "A", "plant_energy", plant_energy=35.0, regrow_delay=40)
    result = invoke(configs, output, "--iteration", str(two))
    assert result.exit_code == 1
    _, failure = only_failure(output)
    assert "exactly one parameter per iteration" in failure["message"]


def test_unregistered_specification_is_refused(setup, tmp_path) -> None:
    configs, output, _ = setup
    register(configs, 1, "A")
    stray = tmp_path / "001.yaml"
    stray.write_bytes((configs / "pilots" / "p1" / "iterations" / "001.yaml").read_bytes())
    result = invoke(configs, output, "--iteration", str(stray))
    assert result.exit_code == 1
    _, failure = only_failure(output)
    assert "not a registered iteration" in failure["message"]


def test_planned_groups_are_verified_independently(setup, monkeypatch) -> None:
    configs, output, _ = setup
    real_plan = pilot_p1.plan_block

    def wrong_groups(spec, block, values, scenarios):
        tasks = real_plan(spec, "confirmation", values, scenarios=scenarios)
        return tuple(dataclasses.replace(t, block=block) for t in tasks)  # relabeled

    monkeypatch.setattr(pilot_p1, "plan_block", wrong_groups)
    result = invoke(configs, output, "--iteration", str(register(configs, 1, "A")))
    assert result.exit_code == 1
    assert_no_results(output)
    _, failure = only_failure(output)
    assert "is not the group 1000" in failure["message"]


def test_an_empty_plan_is_refused(setup, monkeypatch) -> None:
    configs, output, _ = setup
    monkeypatch.setattr(pilot_p1, "plan_block", lambda *args, **kwargs: ())
    result = invoke(configs, output, "--iteration", str(register(configs, 1, "A")))
    assert result.exit_code == 1
    _, failure = only_failure(output)
    assert "no episodes" in failure["message"]


def test_failure_directories_never_collide(setup) -> None:
    configs, output, state = setup
    state["git_dirty"] = True
    path = register(configs, 1, "A")
    invoke(configs, output, "--iteration", str(path))
    invoke(configs, output, "--iteration", str(path))
    names = [p.name for p in failures(output)]
    assert len(names) == len(set(names)) == 2


# ---------------------------------------------------------------- failures during the block


def test_an_a2_violation_stops_the_block_and_is_recorded(setup, monkeypatch) -> None:
    configs, output, _ = setup
    original = calibration.InvariantChecker.__call__
    calls = {"episodes": 0}

    def failing(self, trace) -> None:
        original(self, trace)
        if trace.step == 0:
            calls["episodes"] += 1
        if calls["episodes"] == 3 and trace.step == 2:
            raise InvariantViolationError("prey_energy", 2, "injected for the test")

    monkeypatch.setattr(calibration.InvariantChecker, "__call__", failing)
    result = invoke(configs, output, "--iteration", str(register(configs, 1, "A")))
    assert result.exit_code == 2
    assert_no_results(output)
    assert not (output / "calibration" / "iteration_001").exists()
    directory, failure = only_failure(output)
    assert failure["phase"] == "execution" and failure["episodes_completed"] == 2
    violation = failure["a2_violation"]
    assert (violation["invariant"], violation["step"], violation["detail"]) == (
        "prey_energy",
        2,
        "injected for the test",
    )
    assert violation["task"] == {
        "block": "calibration",
        "scenario": "A",
        "condition": "random_prey",
        "seed_group": 1000,
        "item": 0,
        "label": "calibration/A/random_prey/seed_group 1000/item 0",
    }
    provenance = read_json(directory / "provenance.json")
    assert provenance["status"] == "failed"
    assert provenance["episodes_written"] is None and provenance["episodes_discarded"] == 2


def test_other_errors_keep_type_message_and_notes(setup, monkeypatch) -> None:
    configs, output, _ = setup

    def broken(name, species, config):
        raise ValueError("synthetic policy failure")

    monkeypatch.setattr(pilot_p1, "build_policy", broken)
    result = invoke(configs, output, "--iteration", str(register(configs, 1, "A")))
    assert result.exit_code == 1
    assert_no_results(output)
    _, failure = only_failure(output)
    assert failure["error_type"] == "builtins.ValueError"
    assert failure["message"] == "synthetic policy failure"
    assert failure["notes"] == ["P1 episode: calibration/A/rules/seed_group 1000/item 0"]
    assert failure["a2_violation"] is None


def test_a_failure_while_writing_leaves_no_csv(setup, monkeypatch) -> None:
    configs, output, _ = setup
    real_write = pilot_p1.write_csv

    def failing_write(path, columns, rows):
        real_write(path, columns, rows)
        if path.name == "bootstrap_keys.csv":
            raise OSError("synthetic disk failure")

    monkeypatch.setattr(pilot_p1, "write_csv", failing_write)
    result = invoke(configs, output, "--iteration", str(register(configs, 1, "A")))
    assert result.exit_code == 1
    assert_no_results(output)
    directory, failure = only_failure(output)
    assert failure["phase"] == "writing" and failure["episodes_completed"] == 24
    assert sorted(p.name for p in directory.iterdir()) == ["failure.json", "provenance.json"]


def test_a_failed_publication_declares_the_episodes_discarded(setup, monkeypatch) -> None:
    """M-4: after the completed provenance was written, a failed publication discards it all."""
    configs, output, _ = setup

    def locked(partial, target):
        raise PermissionError("synthetic lock")

    monkeypatch.setattr(pilot_p1, "publish_directory", locked)
    result = invoke(configs, output, "--iteration", str(register(configs, 1, "A")))
    assert result.exit_code == 1
    assert_no_results(output)
    directory, failure = only_failure(output)
    provenance = read_json(directory / "provenance.json")
    assert (provenance["status"], provenance["episodes_written"]) == ("failed", None)
    assert (provenance["finished_utc"], provenance["duration_seconds"]) == (None, None)
    assert provenance["episodes_discarded"] == failure["episodes_completed"] == 24
