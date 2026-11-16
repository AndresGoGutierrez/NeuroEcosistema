"""F4 T3b: protections of ``neuroeco pilot p1`` against bypasses (ADR-033; audit of T3).

Approved seed groups (I-1), execution order and complete prerequisites (I-2), earlier attempts
and D18 (M-6), strict registry (M-10), the git refusals (M-1, I-1) and interruptions (M-7).
Synthetic specifications with seed_group >= 1000 run the episodes. The only appearances of the
real groups 10-32 are specifications refused in the pre-flight, before any random generator is
created. Git facts are simulated here; ``test_pilot_p1_git.py`` uses real repositories.
"""

import copy
import json

import pytest
import yaml

from neuroeco.application import calibration
from neuroeco.application.calibration import InvariantViolationError
from neuroeco.domain.state import InitializationError
from neuroeco.presentation import pilot_p1
from p1_support import (
    SYNTHETIC_SPEC,
    assert_no_results,
    failures,
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


@pytest.fixture
def setup(tmp_path, monkeypatch):
    output = tmp_path / "out"
    return make_configs(tmp_path), output, simulate_git(monkeypatch, output)


def spec_with(**blocks) -> dict:
    spec = copy.deepcopy(SYNTHETIC_SPEC)
    for name, (episodes, groups) in blocks.items():
        spec["blocks"][name] = {
            "episodes": episodes,
            "seed_groups": dict(zip("abc", groups, strict=True)),
        }
    return spec


def authorized(last) -> tuple[str, ...]:
    return ("--values-from", str(last), "--author-authorized")


# ---------------------------------------------------------------- I-1: approved seed groups


@pytest.mark.parametrize(
    "blocks",
    [
        {  # calibration on the confirmation seeds and vice versa
            "calibration": (30, (20, 21, 22)),
            "confirmation": (50, (10, 11, 12)),
            "second_confirmation": (50, (30, 31, 32)),
        },
        {"calibration": (2, (20, 21, 22))},  # confirmation seeds, synthetic elsewhere
        {"calibration": (2, (10, 11, 12))},  # real calibration groups with another size
        {  # the approved groups but 31 episodes
            "calibration": (31, (10, 11, 12)),
            "confirmation": (50, (20, 21, 22)),
            "second_confirmation": (50, (30, 31, 32)),
        },
    ],
    ids=["swapped", "confirmation-seeds", "real-groups-wrong-size", "approved-groups-31"],
)
def test_real_seed_groups_must_be_the_approved_table(setup, blocks) -> None:
    configs, output, state = setup
    write_spec(configs, spec_with(**blocks))
    result = invoke(configs, output, "--iteration", str(register(configs, 1, "A")))
    assert result.exit_code == 1
    assert state["files_at_capture"] == []  # refused before anything else: no episode ran
    assert_no_results(output)
    _, failure = only_failure(output)
    assert failure["phase"] == "preflight" and "must match ADR-033" in failure["message"]


# ---------------------------------------------------------------- I-2: execution order


def test_iterations_run_in_order(setup) -> None:
    configs, output, state = setup
    first = register(configs, 1, "A")
    second = register(configs, 2, "A", "plant_energy", plant_energy=35.0)
    refused = invoke(configs, output, "--iteration", str(second))
    assert refused.exit_code == 1 and state["files_at_capture"] == []
    _, failure = only_failure(output)
    assert "iteration_001 must be a published, completed result first" in failure["message"]

    run_ok(configs, output, "--iteration", str(first))
    run_ok(configs, output, "--iteration", str(second))
    provenance = read_json(output / "calibration" / "iteration_002" / "provenance.json")
    [prerequisite] = provenance["prerequisites"]
    assert prerequisite["directory"].endswith("calibration/iteration_001")


def test_entry_evaluation_needs_the_whole_chain(setup) -> None:
    configs, output, _ = setup
    register(configs, 1, "A")
    two = register(configs, 2, "B")
    last = register(configs, 3, "C")
    run_ok(configs, output, "--iteration", str(configs / "pilots/p1/iterations/001.yaml"))
    run_ok(configs, output, "--iteration", str(two))
    result = invoke(configs, output, "--entry-evaluation", "--values-from", str(last))
    assert result.exit_code == 1
    failure = last_failure(output / "calibration", "entry")
    assert "iteration_003 must be a published, completed result" in failure["message"]


def test_confirmation_needs_the_entry_evaluation(setup) -> None:
    configs, output, _ = setup
    last = run_chain(configs, output)
    result = invoke(configs, output, "--confirmation", *authorized(last))
    assert result.exit_code == 1
    failure = last_failure(output / "confirmation", "evaluation")
    assert "calibration/entry must be a published, completed result" in failure["message"]


def corrupt_status(directory, configs) -> None:
    path = directory / "provenance.json"
    path.write_text(json.dumps({**read_json(path), "status": "failed"}), encoding="utf-8")


def drop_last_row(directory, configs) -> None:
    path = directory / "episodes.csv"
    lines = path.read_bytes().splitlines(keepends=True)
    path.write_bytes(b"".join(lines[:-1]))


def drop_bootstrap_keys(directory, configs) -> None:
    (directory / "bootstrap_keys.csv").unlink()


def drop_provenance(directory, configs) -> None:
    (directory / "provenance.json").unlink()


def overstate_written(directory, configs) -> None:
    path = directory / "provenance.json"
    data = read_json(path)
    data.update(episodes_written=25, episodes_planned=25)
    path.write_text(json.dumps(data), encoding="utf-8")


def edit_registered_spec(directory, configs) -> None:
    """The registered specification changed after its result (identity by SHA-256)."""
    path = configs / "pilots" / "p1" / "iterations" / "001.yaml"
    path.write_text(path.read_text(encoding="utf-8") + "# edited\n", encoding="utf-8")


@pytest.mark.parametrize(
    ("damage", "message"),
    [
        (corrupt_status, "status 'failed'"),
        (drop_last_row, "has 23 rows (expected 24)"),
        (drop_bootstrap_keys, "bootstrap_keys.csv is missing"),
        (drop_provenance, "must be a published, completed result first"),
        (overstate_written, "has 24 rows (expected 25)"),
        (edit_registered_spec, "values_source.sha256 is"),
    ],
    ids=["status", "missing-row", "missing-keys", "missing-provenance", "count", "spec-sha256"],
)
def test_incomplete_or_altered_prerequisites_are_refused(setup, damage, message) -> None:
    configs, output, _ = setup
    run_ok(configs, output, "--iteration", str(register(configs, 1, "A")))
    second = register(configs, 2, "A", "plant_energy", plant_energy=35.0)
    damage(output / "calibration" / "iteration_001", configs)
    result = invoke(configs, output, "--iteration", str(second))
    assert result.exit_code == 1
    failure = last_failure(output / "calibration", "iteration_002")
    assert failure["phase"] == "preflight" and message in failure["message"]
    assert not (output / "calibration" / "iteration_002").exists()


def test_prerequisite_files_are_declared_as_inputs(setup) -> None:
    """Every file read, results included, goes to the git check (I-1)."""
    configs, output, state = setup
    run_ok(configs, output, "--iteration", str(register(configs, 1, "A")))
    run_ok(
        configs,
        output,
        "--iteration",
        str(register(configs, 2, "A", "plant_energy", plant_energy=35.0)),
    )
    names = {(p.parent.name, p.name) for p in state["inputs"]}
    assert {
        ("pilots", "p1.yaml"),
        ("pilots", "p0.yaml"),
        ("configs", "base.yaml"),
        ("configs", "scenarios.yaml"),
        ("configs", "baselines.yaml"),
        ("iterations", "001.yaml"),
        ("iterations", "002.yaml"),
        ("iteration_001", "provenance.json"),
        ("iteration_001", "episodes.csv"),
        ("iteration_001", "bootstrap_keys.csv"),
    } == names


# ---------------------------------------------------------------- second confirmation (P1-21)


def test_second_confirmation_follows_a_completed_confirmation_and_a_recalibration(setup) -> None:
    configs, output, _ = setup
    last = run_chain(configs, output)
    run_ok(configs, output, "--entry-evaluation", "--values-from", str(last))
    refused = invoke(configs, output, "--second-confirmation", *authorized(last))
    assert refused.exit_code == 1
    failure = last_failure(output / "second_confirmation", "evaluation")
    assert "confirmation/evaluation must be a published, completed result" in failure["message"]

    run_ok(configs, output, "--confirmation", *authorized(last))
    same_values = invoke(configs, output, "--second-confirmation", *authorized(last))
    assert same_values.exit_code == 1
    failure = last_failure(output / "second_confirmation", "evaluation")
    assert "must come from a later iteration" in failure["message"]

    recalibrated = register(configs, 4, "C", "n_predators_c", n_predators_c=9)
    run_ok(configs, output, "--iteration", str(recalibrated))
    run_ok(configs, output, "--second-confirmation", *authorized(recalibrated))
    provenance = read_json(output / "second_confirmation" / "evaluation" / "provenance.json")
    assert (provenance["block"], provenance["values_iteration"]) == ("second_confirmation", 4)
    assert len(provenance["previous_attempts"]) == 2  # the two refusals, kept on record


# ---------------------------------------------------------------- earlier attempts (D18, M-6)


def inject_a2(monkeypatch) -> None:
    original = calibration.InvariantChecker.__call__

    def failing(self, trace) -> None:
        original(self, trace)
        if trace.step == 1:
            raise InvariantViolationError("prey_identity", 1, "injected for the test")

    monkeypatch.setattr(calibration.InvariantChecker, "__call__", failing)


def test_a_confirmation_stopped_by_a2_is_never_repeated_nor_replaced(setup, monkeypatch) -> None:
    configs, output, _ = setup
    last = run_chain(configs, output)
    run_ok(configs, output, "--entry-evaluation", "--values-from", str(last))
    with monkeypatch.context() as patch:
        inject_a2(patch)
        assert invoke(configs, output, "--confirmation", *authorized(last)).exit_code == 2

    retry = invoke(configs, output, "--confirmation", *authorized(last))
    assert retry.exit_code == 1
    failure = last_failure(output / "confirmation", "evaluation")
    assert "never after an A2 violation (D18)" in failure["message"]
    assert [a["a2_violation"] for a in failure["previous_attempts"]] == [True]

    recalibrated = register(configs, 4, "C", "n_predators_c", n_predators_c=9)
    run_ok(configs, output, "--iteration", str(recalibrated))
    second = invoke(configs, output, "--second-confirmation", *authorized(recalibrated))
    assert second.exit_code == 1
    failure = last_failure(output / "second_confirmation", "evaluation")
    assert "cannot justify a second confirmation" in failure["message"]


def test_a_confirmation_is_repeated_after_an_infrastructure_failure(setup, monkeypatch) -> None:
    configs, output, _ = setup
    last = run_chain(configs, output)
    run_ok(configs, output, "--entry-evaluation", "--values-from", str(last))

    def broken(name, species, config):
        raise OSError("synthetic infrastructure failure")

    with monkeypatch.context() as patch:
        patch.setattr(pilot_p1, "build_policy", broken)
        assert invoke(configs, output, "--confirmation", *authorized(last)).exit_code == 1

    run_ok(configs, output, "--confirmation", *authorized(last))
    provenance = read_json(output / "confirmation" / "evaluation" / "provenance.json")
    [attempt] = provenance["previous_attempts"]
    assert (attempt["kind"], attempt["phase"], attempt["a2_violation"]) == (
        "failure",
        "execution",
        False,
    )


def recovered_partial(output, contents: dict | None) -> None:
    """A partial directory recovered by the documented procedure (M-8)."""
    directory = output / "confirmation" / "evaluation.failed-20261115T120000Z-0000abcd"
    directory.mkdir(parents=True)
    if contents is not None:
        (directory / "provenance.json").write_text(json.dumps(contents), encoding="utf-8")


def test_an_interrupted_confirmation_may_be_repeated(setup) -> None:
    configs, output, _ = setup
    last = run_chain(configs, output)
    run_ok(configs, output, "--entry-evaluation", "--values-from", str(last))
    recovered_partial(output, {"schema": pilot_p1.PROVENANCE_SCHEMA, "status": "running"})
    run_ok(configs, output, "--confirmation", *authorized(last))
    provenance = read_json(output / "confirmation" / "evaluation" / "provenance.json")
    assert [a["kind"] for a in provenance["previous_attempts"]] == ["interrupted"]


def test_an_unrecognized_attempt_blocks_a_confirmation(setup) -> None:
    configs, output, _ = setup
    last = run_chain(configs, output)
    run_ok(configs, output, "--entry-evaluation", "--values-from", str(last))
    recovered_partial(output, None)  # no record: A2 cannot be excluded
    result = invoke(configs, output, "--confirmation", *authorized(last))
    assert result.exit_code == 1
    failure = last_failure(output / "confirmation", "evaluation")
    assert "cannot be told apart from an A2 violation" in failure["message"]


def test_a_leftover_partial_directory_is_refused(setup) -> None:
    configs, output, _ = setup
    (output / "calibration" / "iteration_001.partial-0000abcd").mkdir(parents=True)
    result = invoke(configs, output, "--iteration", str(register(configs, 1, "A")))
    assert result.exit_code == 1
    failure = last_failure(output / "calibration", "iteration_001")
    assert "must be recovered first" in failure["message"]


# ---------------------------------------------------------------- strict registry (M-10)


@pytest.mark.parametrize(
    "stray",
    [
        "iterations/002.yml",
        "iterations/notes.txt",
        "iterations/drafts/002.yaml",
        "iterations/2.yaml",
        "rounds/1.yaml",
        "extra.yaml",
    ],
)
def test_unexpected_registry_entries_are_refused(setup, stray) -> None:
    configs, output, _ = setup
    path = register(configs, 1, "A")
    target = configs / "pilots" / "p1" / stray
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("iteration: 2\n", encoding="utf-8")
    result = invoke(configs, output, "--iteration", str(path))
    assert result.exit_code == 1
    _, failure = only_failure(output)
    assert "unexpected entries" in failure["message"]


# ---------------------------------------------------------------- git refusals (simulated)


@pytest.mark.parametrize(
    ("checks", "message"),
    [
        ({"root": None}, "inside the git repository"),
        ({"outside_repository": ["/elsewhere/p1.yaml"]}, "files outside the repository"),
        ({"untracked": None}, "could not list the tracked files"),
        ({"untracked": ["configs/pilots/p1.yaml"]}, "not tracked by git"),
        ({"output_root_inside": False}, "output root must be inside the repository"),
        ({"upstream": None}, "no upstream branch"),
        ({"synchronized": False}, "is not synchronized"),
    ],
    ids=["no-repo", "outside", "git-error", "untracked", "output-root", "no-upstream", "unpushed"],
)
def test_each_git_refusal_is_recorded_with_the_checks(setup, checks, message) -> None:
    configs, output, state = setup
    state["checks"] = checks
    result = invoke(configs, output, "--iteration", str(register(configs, 1, "A")))
    assert result.exit_code == 1
    assert_no_results(output)
    directory, failure = only_failure(output)
    assert failure["phase"] == "preflight" and message in failure["message"]
    provenance = read_json(directory / "provenance.json")
    assert provenance["status"] == "failed"
    for key, value in checks.items():
        assert provenance["git_checks"][key] == value


# ---------------------------------------------------------------- interruptions (M-7)


def test_ctrl_c_is_recorded_and_propagated(setup, monkeypatch) -> None:
    configs, output, _ = setup
    real_policy, calls = pilot_p1.build_policy, {"n": 0}

    def interrupting(name, species, config):
        calls["n"] += 1
        if calls["n"] == 7:  # fourth episode: three episodes completed
            raise KeyboardInterrupt
        return real_policy(name, species, config)

    monkeypatch.setattr(pilot_p1, "build_policy", interrupting)
    result = invoke(configs, output, "--iteration", str(register(configs, 1, "A")))
    assert result.exit_code != 0
    assert_no_results(output)
    directory, failure = only_failure(output)
    assert failure["error_type"] == "builtins.KeyboardInterrupt"
    assert (failure["phase"], failure["episodes_completed"]) == ("execution", 3)
    provenance = read_json(directory / "provenance.json")
    assert (provenance["status"], provenance["episodes_discarded"]) == ("failed", 3)


def test_initialization_errors_through_the_command(setup) -> None:
    """P1-18: the configuration is rejected, no episode is discarded or skipped."""
    configs, output, _ = setup
    base = configs / "base.yaml"
    data = yaml.safe_load(base.read_text(encoding="utf-8"))
    data["world"]["n_prey"] = 400  # no room for d_safe: the placement fails
    base.write_text(yaml.safe_dump(data), encoding="utf-8")
    result = invoke(configs, output, "--iteration", str(register(configs, 1, "A")))
    assert result.exit_code == 1
    assert_no_results(output)
    _, failure = only_failure(output)
    assert failure["error_type"] == f"{InitializationError.__module__}.InitializationError"
    assert failure["phase"] == "execution" and failure["episodes_completed"] == 0
    assert failure["notes"] == ["P1 episode: calibration/A/rules/seed_group 1000/item 0"]


def test_failures_list_the_earlier_attempts(setup) -> None:
    configs, output, state = setup
    state["git_dirty"] = True
    path = register(configs, 1, "A")
    invoke(configs, output, "--iteration", str(path))
    invoke(configs, output, "--iteration", str(path))
    records = [read_json(d / "failure.json") for d in failures(output)]
    assert sorted(len(r["previous_attempts"]) for r in records) == [0, 1]
