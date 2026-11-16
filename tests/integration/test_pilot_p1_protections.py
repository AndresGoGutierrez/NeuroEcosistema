"""F4 T3b and T3c: protections of ``neuroeco pilot p1`` against bypasses (ADR-033; audits).

Approved seed groups (I-1), execution order and complete prerequisites (I-2), earlier attempts
and D18 (M-6), strict registry (M-10), the git refusals (M-1, I-1) and interruptions (M-7);
T3c: configuration identity along the chain (IA-3), integrity of the prerequisite CSV files
(Mn-4), no recalibration (Mn-6, Mn-7) and the A2 evidence when the rename fails (IA-2).
Synthetic specifications with seed_group >= 1000 run the episodes. The only appearances of the
real groups 10-32 are specifications refused before any episode, and the test that reaches the
git checks with them replaces the block runner with a guard that fails if an episode were ever
started. Git facts are simulated here; ``test_pilot_p1_git.py`` uses real repositories.
"""

import copy
import json
import shutil

import pytest
import yaml

from neuroeco.application import calibration
from neuroeco.application.calibration import InvariantViolationError
from neuroeco.domain.state import InitializationError
from neuroeco.infrastructure import storage
from neuroeco.infrastructure.provenance import file_sha256
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


def drop_config_files(directory, configs) -> None:
    """A result without the configuration hashes (as produced before T3c)."""
    path = directory / "provenance.json"
    data = read_json(path)
    del data["config_files"]
    path.write_text(json.dumps(data), encoding="utf-8")


def edit_bootstrap_keys(directory, configs) -> None:
    path = directory / "bootstrap_keys.csv"
    path.write_bytes(path.read_bytes().replace(b",1000,", b",1001,", 1))


def forge_rows_and_hash(directory, configs) -> None:
    """Mn-4: a foreign seed group in one row, and the recorded hash updated to match."""
    path = directory / "episodes.csv"
    path.write_bytes(path.read_bytes().replace(b",1000,", b",1010,", 1))
    provenance = directory / "provenance.json"
    data = read_json(provenance)
    data["result_files"]["episodes.csv"] = file_sha256(path)
    provenance.write_text(json.dumps(data), encoding="utf-8")


def edit_registered_spec(directory, configs) -> None:
    """The registered specification changed after its result (identity by SHA-256)."""
    path = configs / "pilots" / "p1" / "iterations" / "001.yaml"
    path.write_text(path.read_text(encoding="utf-8") + "# edited\n", encoding="utf-8")


@pytest.mark.parametrize(
    ("damage", "message"),
    [
        (corrupt_status, "status 'failed'"),
        (drop_last_row, "episodes.csv does not match the SHA-256 recorded at publication"),
        (drop_bootstrap_keys, "bootstrap_keys.csv is missing"),
        (drop_provenance, "must be a published, completed result first"),
        (overstate_written, "has 24 rows (expected 25)"),
        (edit_registered_spec, "values_source.sha256 is"),
        (drop_config_files, "config_files is None"),
        (edit_bootstrap_keys, "bootstrap_keys.csv does not match the SHA-256"),
        (forge_rows_and_hash, "are not the planned episodes"),
    ],
    ids=[
        "status",
        "missing-row",
        "missing-keys",
        "missing-provenance",
        "count",
        "spec-sha256",
        "no-config-hashes",
        "keys-edited",
        "forged-rows",
    ],
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


def test_second_confirmation_is_never_a_repetition_and_no_recalibration_runs(setup) -> None:
    """Mn-7 (author's decision in T3c): a completed first confirmation and values from a later
    iteration; no recalibration while no flow is approved, so a second confirmation cannot be
    reached today: every route to it is refused."""
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
    assert invoke(configs, output, "--iteration", str(recalibrated)).exit_code == 1
    failure = last_failure(output / "calibration", "iteration_004")
    assert "no recalibration flow is approved" in failure["message"]
    without_iteration = invoke(configs, output, "--second-confirmation", *authorized(recalibrated))
    assert without_iteration.exit_code == 1
    failure = last_failure(output / "second_confirmation", "evaluation")
    assert "iteration_004 must be a published, completed result" in failure["message"]
    assert not (output / "second_confirmation" / "evaluation").exists()


@pytest.mark.parametrize("started", ["entry", "confirmation-attempt"])
def test_no_iteration_after_the_entry_evaluation_or_a_started_confirmation(setup, started):
    configs, output, _ = setup
    last = run_chain(configs, output)
    if started == "entry":
        run_ok(configs, output, "--entry-evaluation", "--values-from", str(last))
    else:  # an attempt left in the confirmation directory, without any entry evaluation
        attempt = output / "confirmation" / "evaluation.failed-20261115T120000Z-0000abcd"
        attempt.mkdir(parents=True)
    four = register(configs, 4, "C", "n_predators_c", n_predators_c=9)
    assert invoke(configs, output, "--iteration", str(four)).exit_code == 1
    failure = last_failure(output / "calibration", "iteration_004")
    assert "no recalibration flow is approved" in failure["message"]
    assert not (output / "calibration" / "iteration_004").exists()


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
    assert invoke(configs, output, "--iteration", str(recalibrated)).exit_code == 1  # Mn-6
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


# ---------------------------------------------------------------- T3c: IA-3 configuration chain


def change_capture_radius(configs) -> None:
    """A parameter outside the candidate values (K1 still holds with 2.4)."""
    base = configs / "base.yaml"
    data = yaml.safe_load(base.read_text(encoding="utf-8"))
    data["world"]["capture_radius"] = 2.4
    base.write_text(yaml.safe_dump(data), encoding="utf-8")


def test_a_configuration_change_breaks_the_chain(setup) -> None:
    """Q5: only the 8 candidate values may change, one per iteration; anything else is refused."""
    configs, output, _ = setup
    run_ok(configs, output, "--iteration", str(register(configs, 1, "A")))
    change_capture_radius(configs)
    second = register(configs, 2, "A", "plant_energy", plant_energy=35.0)
    assert invoke(configs, output, "--iteration", str(second)).exit_code == 1
    failure = last_failure(output / "calibration", "iteration_002")
    assert "config_files is" in failure["message"]
    assert not (output / "calibration" / "iteration_002").exists()


@pytest.mark.parametrize("changed", [False, True])
def test_an_alternative_configuration_directory(setup, tmp_path, changed) -> None:
    """Same bytes are the same configuration; any difference breaks the chain."""
    configs, output, _ = setup
    run_ok(configs, output, "--iteration", str(register(configs, 1, "A")))
    register(configs, 2, "A", "plant_energy", plant_energy=35.0)
    alternative = tmp_path / "alternative" / "configs"
    shutil.copytree(configs, alternative)
    if changed:
        change_capture_radius(alternative)
    second = alternative / "pilots" / "p1" / "iterations" / "002.yaml"
    result = invoke(alternative, output, "--iteration", str(second))
    assert result.exit_code == (1 if changed else 0)
    if changed:
        failure = last_failure(output / "calibration", "iteration_002")
        assert "config_files is" in failure["message"]


def test_real_seed_groups_require_the_canonical_paths(setup, monkeypatch) -> None:
    """IA-3: with the real table the paths must be configs/ and configs/pilots/p1.yaml.

    The block runner is replaced by a guard: no episode may ever start with real seed groups.
    """
    configs, output, state = setup
    approved = copy.deepcopy(SYNTHETIC_SPEC)
    for block, (episodes, groups) in calibration.APPROVED_BLOCKS.items():
        approved["blocks"][block] = {
            "episodes": episodes,
            "seed_groups": dict(zip("abc", groups, strict=True)),
        }
    write_spec(configs, approved)

    def guard(*args, **kwargs):
        raise AssertionError("an episode with real seed groups was about to start")

    monkeypatch.setattr(pilot_p1, "iter_block", guard)
    state["checks"] = {"canonical_paths": False}
    result = invoke(configs, output, "--iteration", str(register(configs, 1, "A")))
    assert result.exit_code == 1
    assert_no_results(output)
    _, failure = only_failure(output)
    assert "must be configs/pilots/p1.yaml" in failure["message"]
    assert failure["error_type"].endswith("P1RefusalError")


# ---------------------------------------------------------------- T3c: IA-2 evidence of A2


def test_an_a2_violation_keeps_its_evidence_when_the_rename_fails(setup, monkeypatch) -> None:
    """Q7: A2 violation, then a persistent PermissionError on every rename (Windows lock).

    The partial directory keeps failure.json and the failed provenance; after the documented
    recovery the attempt is still an A2 violation and the confirmation is never repeated.
    """
    configs, output, _ = setup
    last = run_chain(configs, output)
    run_ok(configs, output, "--entry-evaluation", "--values-from", str(last))

    def locked(source, target):
        raise PermissionError("synthetic lock that outlasts the retries")

    with monkeypatch.context() as patch:
        inject_a2(patch)
        patch.setattr(storage, "RENAME_FIRST_DELAY_SECONDS", 0.0)
        patch.setattr(storage.os, "rename", locked)
        result = invoke(configs, output, "--confirmation", *authorized(last))
    assert result.exit_code != 0 and isinstance(result.exception, PermissionError)
    assert "A2 violation, block stopped" in result.stderr  # said before recording
    [partial] = sorted((output / "confirmation").glob("evaluation.partial-*"))
    assert sorted(p.name for p in partial.iterdir()) == ["failure.json", "provenance.json"]
    failure = read_json(partial / "failure.json")
    assert failure["a2_violation"]["invariant"] == "prey_identity"
    provenance = read_json(partial / "provenance.json")
    assert (provenance["status"], provenance["a2_violation"]) == ("failed", True)

    before_recovery = invoke(configs, output, "--confirmation", *authorized(last))
    assert before_recovery.exit_code == 1
    assert "must be recovered first" in before_recovery.output

    # documented recovery (M-8): rename the partial directory to a failed one
    partial.rename(partial.with_name(partial.name.replace("partial-", "failed-20261116T000000Z-")))
    retry = invoke(configs, output, "--confirmation", *authorized(last))
    assert retry.exit_code == 1
    assert "never after an A2 violation (D18)" in retry.output
    assert not (output / "confirmation" / "evaluation").exists()


def test_an_a2_flag_in_the_provenance_alone_blocks_a_confirmation(setup) -> None:
    """A failure record lost or damaged, but the failed provenance says A2: never repeated."""
    configs, output, _ = setup
    last = run_chain(configs, output)
    run_ok(configs, output, "--entry-evaluation", "--values-from", str(last))
    attempt = output / "confirmation" / "evaluation.failed-20261115T120000Z-0000abcd"
    attempt.mkdir(parents=True)
    (attempt / "provenance.json").write_text(
        json.dumps(
            {"schema": pilot_p1.PROVENANCE_SCHEMA, "status": "failed", "a2_violation": True}
        ),
        encoding="utf-8",
    )
    assert invoke(configs, output, "--confirmation", *authorized(last)).exit_code == 1
    failure = last_failure(output / "confirmation", "evaluation")
    assert "cannot be told apart from an A2 violation" in failure["message"]
    assert failure["previous_attempts"][0]["a2_violation"] is True
