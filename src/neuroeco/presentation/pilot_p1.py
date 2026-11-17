"""Command ``neuroeco pilot p1``: one block of the P1 calibration (ADR-020, ADR-033; F4 T3-T3c).

Modes (exactly one per invocation, T3-1):

- ``--iteration iterations/NNN.yaml``: calibration iteration; stage A runs A, stage B runs A and
  B, stage C runs A and C (P1-18); bootstrap ``run`` = NNN.
- ``--entry-evaluation --values-from iterations/NNN.yaml``: the 35 conditions of the calibration
  block with the final values (P1-18, state E); ``run`` = 0.
- ``--confirmation`` / ``--second-confirmation`` with ``--values-from`` and
  ``--author-authorized``: the 35 conditions of the confirmation block (P1-21); ``run`` = 0.
- ``--round rounds/RR.yaml --phase prey|predator|reevaluation`` (T4c, D-T4c-3): one phase of a
  registered rule-tuning round (P1-17), with the same protections. ``prey`` and ``predator``
  run their grid (only ``rules`` in A, calibration seeds) and publish ``selection.json``; the
  predator grid takes the prey winner from the published prey grid, recomputed. In the prey
  grid the combination in force must reproduce the rows of the previous evaluation of A
  (D-T4c-4). ``reevaluation`` is A_rev with the winners (D-T4c-2).

Before any episode the command validates, in this order:

1. the P1 specification, and the approved seed groups and sizes if it declares real groups;
2. every registered iteration and round specification (strict file names) and their static
   sequence; then, unless every seed group of the specification is synthetic (>= 1000, D16),
   the sequence of P1-18 after the published results and their criteria (T4c, D-T4c-5): the
   block runs only if it is exactly the step that the sequence allows (the verification of
   ``pilot p1-sequence``; with the real seed groups it can never be skipped);
3. no new iteration once the entry evaluation exists or a confirmation started (Mn-6);
   earlier attempts at the same destination (D18); and the completed results this mode needs
   (iteration N needs 1..N-1; the entry evaluation the whole chain; the confirmation the entry
   evaluation; the second confirmation the first one, followed by a recalibration), each with
   the same configuration files, intact CSV files and the planned rows;
4. the resolved configurations and state K (A1);
5. the exact plan of the block (seed groups, conditions, items and overrides);
6. the author's authorization for confirmation blocks, and that the destination does not exist;
7. after capturing the provenance and before writing anything (P1-19): a clean git working
   tree; no file hidden with assume-unchanged or skip-worktree; every tracked file, code
   included, equal to HEAD (``git hash-object``) and the running package inside the repository;
   every file read inside the repository and tracked; the canonical paths with real seed
   groups; an output root inside the repository and not ignored; and HEAD synchronized with a
   remote-tracking upstream branch (pushed).

There is no option to bypass these checks.

Results are assembled in ``<destination>.partial-<id>`` and published in one rename when the
block is complete (T3-3). Any error after the destination is known leaves a separate
``<destination>.failed-<UTC>-<id>`` directory with ``failure.json`` (and ``provenance.json`` when
it was captured) and no CSV file (T3-4).
"""

from __future__ import annotations

import csv
import dataclasses
import datetime as dt
import glob
import json
import re
import sys
import time
from collections.abc import Mapping, Sequence
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

import typer

import neuroeco
from neuroeco.analysis.calibration import (
    CriteriaError,
    grid_selection,
    read_episodes,
    render_selection,
)
from neuroeco.application.calibration import (
    BOOTSTRAP_COLUMNS,
    CONFIRMATION_BLOCKS,
    CONFIRMATION_RUN,
    CONFIRMATION_STAGE,
    ENTRY_EVALUATION_RUN,
    ENTRY_STAGE,
    EPISODE_COLUMNS,
    GRID_PHASES,
    REAL_SEED_GROUPS,
    REEVALUATION_STAGE,
    ROUND_PREDATOR_STAGE,
    ROUND_PREY_STAGE,
    SCENARIOS,
    A2ViolationError,
    CandidateValues,
    IterationSpec,
    P1Spec,
    RoundSpec,
    admissibility,
    bootstrap_rows,
    check_approved_seed_groups,
    check_block_plan,
    check_calibration_sequence,
    check_grid_plan,
    episode_row,
    iter_block,
    plan_block,
    plan_grid,
    scenario_overrides,
    sequence_gate_required,
    stage_scenarios,
    uses_approved_table,
)
from neuroeco.application.configs import ResolvedConfig
from neuroeco.bootstrap import DEFAULT_CONFIG_DIR, EXPLORATORY_SEED_GROUP, build_policy
from neuroeco.infrastructure.config_loader import (
    BASE_FILE,
    BASELINES_FILE,
    SCENARIOS_FILE,
    ConfigError,
    load_config,
    load_iteration_spec,
    load_p0_spec,
    load_p1_spec,
    load_round_spec,
)
from neuroeco.infrastructure.decision_loader import load_decisions
from neuroeco.infrastructure.fingerprint import P1_DEPENDENCIES, p1_fingerprint
from neuroeco.infrastructure.p1_reserved import (
    RESERVED_FILE,
    ReservedRootError,
    read_reserved,
    reserved_root,
    same_directory,
)
from neuroeco.infrastructure.provenance import (
    collect_provenance,
    dependency_versions,
    file_sha256,
    git_content_overrides,
    git_head_mismatches,
    git_hidden_changes,
    git_ignored,
    git_state,
    git_toplevel,
    git_untracked,
    git_upstream,
    is_inside,
)
from neuroeco.infrastructure.storage import (
    create_partial_directory,
    publish_directory,
    replace_json,
    reserve_failure_directory,
    write_csv,
)

PROVENANCE_SCHEMA = "neuroeco.p1-provenance/1"
FAILURE_SCHEMA = "neuroeco.p1-failure/1"
DEFAULT_SPEC = DEFAULT_CONFIG_DIR / "pilots" / "p1.yaml"
DEFAULT_OUTPUT_ROOT = Path("results/pilots/p1")
REGISTRY_DIRECTORY = "p1"  # configs/pilots/p1/{iterations,rounds} next to p1.yaml (T1-4)
ITERATIONS_DIRECTORY = "iterations"
ROUNDS_DIRECTORY = "rounds"
ITERATION_FILE = re.compile(r"\d{3}\.yaml")
ROUND_FILE = re.compile(r"\d{2}\.yaml")
CALIBRATION_BLOCK = "calibration"
ENTRY_LEAF = "entry"
CONFIRMATION_LEAF = "evaluation"
DEPENDENCIES = P1_DEPENDENCIES  # the same list enters the environment fingerprint (T4d)
EXIT_FAILURE = 1
EXIT_A2_VIOLATION = 2
EPISODES_FILE = "episodes.csv"
BOOTSTRAP_FILE = "bootstrap_keys.csv"
PROVENANCE_FILE = "provenance.json"
FAILURE_FILE = "failure.json"
SELECTION_FILE = "selection.json"  # T4c: winner of a grid of a round

# T4c (D-T4c-3, D-T4c-6): the phases of a rule-tuning round.
ROUND_PHASES = ("prey", "predator", "reevaluation")
PHASE_MODES = {"prey": "round_prey", "predator": "round_predator", "reevaluation": "reevaluation"}
PHASE_STAGES = {
    "prey": ROUND_PREY_STAGE,
    "predator": ROUND_PREDATOR_STAGE,
    "reevaluation": REEVALUATION_STAGE,
}
PHASE_LEAVES = {"prey": "prey_grid", "predator": "predator_grid", "reevaluation": "reevaluation"}
ROUND_MODES = tuple(PHASE_MODES.values())
VALUES_FROM_MODES = ("entry", "confirmation", "second_confirmation")


def result_names(stage: str) -> tuple[str, ...]:
    """Files published by a block of ``stage`` besides its provenance (T4c, D-T4c-1)."""
    if stage in (ROUND_PREY_STAGE, ROUND_PREDATOR_STAGE):
        return (EPISODES_FILE, SELECTION_FILE)
    if stage == REEVALUATION_STAGE:
        return (EPISODES_FILE,)  # no bootstrap key is defined for A_rev (D-T4c-1)
    return (EPISODES_FILE, BOOTSTRAP_FILE)


def phase_directory(output_root: Path, round_number: int, phase: str) -> Path:
    return output_root / CALIBRATION_BLOCK / f"round_{round_number:02d}" / PHASE_LEAVES[phase]


class P1RefusalError(ValueError):
    """A pre-flight check refused to run the block; no episode was executed."""


@dataclass(frozen=True)
class Mode:
    """What one invocation runs and where its results go."""

    name: str  # iteration | entry | confirmation | second_confirmation | round_* | reevaluation
    block: str
    stage: str
    iteration: int  # 0 when the mode is not an iteration; the anchor iteration of a round
    run: int  # bootstrap ``run`` field (P1-20)
    scenarios: tuple[str, ...]
    values: CandidateValues  # for a round: the values in force when the round starts
    source: Path  # the iteration (or round) specification that provides the values
    values_iteration: int  # number of that iteration (for a round, its anchor iteration)
    leaf: str
    round_number: int = 0  # T4c: the round of a round mode
    phase: str = ""  # T4c: prey | predator | reevaluation

    def destination(self, output_root: Path) -> Path:
        return output_root / self.block / self.leaf


@dataclass(frozen=True)
class Registry:
    """Pre-registered iteration and round specifications (P1-19)."""

    iterations: tuple[tuple[Path, IterationSpec], ...]
    rounds: tuple[tuple[Path, RoundSpec], ...]

    def sha256(self, number: int) -> str:
        """SHA-256 of the registered specification of iteration ``number``."""
        for path, spec in self.iterations:
            if spec.iteration == number:
                return file_sha256(path)
        raise P1RefusalError(f"iteration {number} is not registered (P1-19)")

    def round_sha256(self, number: int) -> str:
        """SHA-256 of the registered specification of round ``number`` (T4c)."""
        for path, spec in self.rounds:
            if spec.round_number == number:
                return file_sha256(path)
        raise P1RefusalError(f"round {number} is not registered (P1-19)")


def select_mode(
    *,
    iteration: Path | None,
    entry_evaluation: bool,
    confirmation: bool,
    second_confirmation: bool,
    values_from: Path | None,
    author_authorized: bool,
    round_spec: Path | None = None,
    phase: str | None = None,
) -> Mode:
    """Exactly one mode; the values always come from a pre-registered iteration file."""
    chosen = [
        name
        for name, selected in (
            ("iteration", iteration is not None),
            ("entry", entry_evaluation),
            ("confirmation", confirmation),
            ("second_confirmation", second_confirmation),
            ("round", round_spec is not None),
        )
        if selected
    ]
    if len(chosen) != 1:
        raise P1RefusalError(
            "choose exactly one of --iteration, --entry-evaluation, --confirmation, "
            "--second-confirmation and --round"
        )
    name = chosen[0]
    # A missing authorization is checked in the pre-flight, once the destination is known, so
    # that the refused attempt is recorded; a superfluous one is a usage error.
    if author_authorized and name not in CONFIRMATION_BLOCKS:
        raise P1RefusalError("--author-authorized only applies to confirmation blocks")
    if (phase is not None) != (name == "round"):
        raise P1RefusalError("--phase goes with --round, and --round needs --phase")
    if name == "round":
        if phase not in ROUND_PHASES or values_from is not None:
            raise P1RefusalError(
                f"--round needs --phase one of {ROUND_PHASES} and no --values-from"
            )
        assert round_spec is not None
        spec = load_round_spec(round_spec)
        return Mode(
            name=PHASE_MODES[phase],
            block=CALIBRATION_BLOCK,
            stage=PHASE_STAGES[phase],
            iteration=spec.after_iteration,
            run=0,  # no bootstrap key in a round (P1-17, D-T4c-1)
            scenarios=("A",),
            values=spec.values,
            source=round_spec,
            values_iteration=spec.after_iteration,
            leaf=f"round_{spec.round_number:02d}/{PHASE_LEAVES[phase]}",
            round_number=spec.round_number,
            phase=phase,
        )
    if name == "iteration":
        if values_from is not None:
            raise P1RefusalError("--values-from is not used with --iteration")
        assert iteration is not None
        spec = load_iteration_spec(iteration)
        return Mode(
            name=name,
            block=CALIBRATION_BLOCK,
            stage=spec.stage,
            iteration=spec.iteration,
            run=spec.iteration,
            scenarios=stage_scenarios(spec.stage),
            values=spec.values,
            source=iteration,
            values_iteration=spec.iteration,
            leaf=f"iteration_{spec.iteration:03d}",
        )
    if values_from is None:
        raise P1RefusalError(f"--values-from is required with the {name} mode")
    spec = load_iteration_spec(values_from)
    if name == "entry":
        block, stage, run, leaf = CALIBRATION_BLOCK, ENTRY_STAGE, ENTRY_EVALUATION_RUN, ENTRY_LEAF
    else:
        block, stage, run, leaf = name, CONFIRMATION_STAGE, CONFIRMATION_RUN, CONFIRMATION_LEAF
    return Mode(
        name, block, stage, 0, run, SCENARIOS, spec.values, values_from, spec.iteration, leaf
    )


def _registry_files(directory: Path, pattern: re.Pattern[str], kind: str) -> list[Path]:
    """The specification files of one registry directory; anything else is refused (M-10)."""
    if not directory.exists():
        return []
    entries = sorted(directory.iterdir())
    unexpected = [e.name for e in entries if not (e.is_file() and pattern.fullmatch(e.name))]
    if unexpected:
        raise P1RefusalError(
            f"{directory}: unexpected entries {unexpected}; only {kind} files are allowed"
        )
    return entries


def load_registry(spec_path: Path) -> Registry:
    """Every iteration and round file registered next to ``p1.yaml``, in numeric order."""
    base = spec_path.parent / REGISTRY_DIRECTORY
    if base.exists():
        allowed = {ITERATIONS_DIRECTORY, ROUNDS_DIRECTORY}
        unexpected = sorted(
            e.name for e in base.iterdir() if not (e.is_dir() and e.name in allowed)
        )
        if unexpected:
            raise P1RefusalError(f"{base}: unexpected entries {unexpected}")
    iterations = []
    for path in _registry_files(base / ITERATIONS_DIRECTORY, ITERATION_FILE, "NNN.yaml"):
        spec = load_iteration_spec(path)
        if path.stem != f"{spec.iteration:03d}":
            raise P1RefusalError(f"{path}: iteration {spec.iteration} must be in a file NNN.yaml")
        iterations.append((path, spec))
    rounds = []
    for path in _registry_files(base / ROUNDS_DIRECTORY, ROUND_FILE, "RR.yaml"):
        spec = load_round_spec(path)
        if path.stem != f"{spec.round_number:02d}":
            raise P1RefusalError(f"{path}: round {spec.round_number} must be in a file RR.yaml")
        rounds.append((path, spec))
    return Registry(tuple(iterations), tuple(rounds))


def _registered(path: Path, registry: Registry) -> IterationSpec:
    for registered, spec in registry.iterations:
        if registered.resolve() == path.resolve():
            return spec
    raise P1RefusalError(f"{path} is not a registered iteration specification (P1-19)")


def _registered_round(path: Path, registry: Registry) -> RoundSpec:
    for registered, spec in registry.rounds:
        if registered.resolve() == path.resolve():
            return spec
    raise P1RefusalError(f"{path} is not a registered round specification (P1-19)")


# ---------------------------------------------------------------- earlier attempts (M-6, D18)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _attempt(directory: Path) -> dict[str, Any]:
    """Classify the directory of an earlier attempt: failure record, interrupted run or unknown.

    The command writes ``failure.json`` (and the failed provenance) inside the partial directory
    before it tries to rename it (T3c, IA-2), so an A2 violation keeps its evidence even when
    the rename fails. A directory without ``failure.json`` whose provenance is still
    ``running`` is an interruption that left no record (power cut, killed process). Either
    record can declare an A2 violation; any doubt makes the attempt ``unrecognized``.
    """
    record = {"directory": directory.name}
    failure = _read_json(directory / FAILURE_FILE)
    provenance = _read_json(directory / PROVENANCE_FILE)
    provenance_a2 = isinstance(provenance, dict) and provenance.get("a2_violation") is True
    if isinstance(failure, dict) and failure.get("schema") == FAILURE_SCHEMA:
        return {
            **record,
            "kind": "failure",
            "phase": failure.get("phase"),
            "error_type": failure.get("error_type"),
            "timestamp_utc": failure.get("timestamp_utc"),
            "a2_violation": failure.get("a2_violation") is not None or provenance_a2,
        }
    if (
        not (directory / FAILURE_FILE).exists()
        and isinstance(provenance, dict)
        and provenance.get("status") == "running"
        and provenance.get("a2_violation") is None
    ):
        return {**record, "kind": "interrupted", "a2_violation": False}
    return {**record, "kind": "unrecognized", "a2_violation": True if provenance_a2 else None}


def list_attempts(destination: Path, exclude: Path | None = None) -> list[dict[str, Any]]:
    """Partial and failed directories left next to ``destination`` by earlier attempts."""
    parent, prefix = destination.parent, glob.escape(destination.name)
    if not parent.is_dir():
        return []
    attempts: list[dict[str, Any]] = []
    for path in sorted(parent.glob(prefix + ".partial-*")):
        if exclude is None or path.name != exclude.name:
            # A partial directory never counts as clean: it must be recovered first (M-8).
            found = _attempt(path)
            attempts.append({**found, "kind": "partial", "recorded_kind": found["kind"]})
    attempts.extend(_attempt(p) for p in sorted(parent.glob(prefix + ".failed-*")))
    return attempts


CONFIRMATION_DESTINATIONS = (
    ("confirmation", CONFIRMATION_LEAF),
    ("second_confirmation", CONFIRMATION_LEAF),
)


def check_no_recalibration(mode: Mode, output_root: Path) -> None:
    """No new iteration once the entry evaluation exists or a confirmation started (Mn-6).

    T3c (decision Mn-7 of the author): recalibrating, or repeating the entry evaluation, after
    the confirmation started is not allowed while no methodological flow is approved. There is
    no option to bypass this check. The phases of a round are calibration too (T4c).
    """
    if mode.name not in ("iteration", *ROUND_MODES):
        return
    started = []
    entry = output_root / CALIBRATION_BLOCK / ENTRY_LEAF
    if entry.exists():
        started.append(entry.as_posix())
    for block, leaf in CONFIRMATION_DESTINATIONS:
        destination = output_root / block / leaf
        if destination.exists() or list_attempts(destination):
            started.append(destination.as_posix())
    if started:
        raise P1RefusalError(
            f"{started} exist: no calibration iteration runs after the entry evaluation or once "
            "a confirmation started; no recalibration flow is approved (T3c, Mn-6, Mn-7)"
        )


def check_attempts(mode: Mode, destination: Path, output_root: Path) -> list[dict[str, Any]]:
    """Earlier attempts at this destination; D18 rules for the confirmation blocks."""
    attempts = list_attempts(destination)
    partial = [a["directory"] for a in attempts if a["kind"] == "partial"]
    if partial:
        raise P1RefusalError(
            f"interrupted attempt(s) {partial} must be recovered first "
            "(docs/p1_data_dictionary.md, partial directories)"
        )
    if mode.block not in CONFIRMATION_BLOCKS:
        return attempts
    unknown = [a["directory"] for a in attempts if a["kind"] == "unrecognized"]
    if unknown:
        raise P1RefusalError(
            f"earlier attempt(s) {unknown} have no valid failure record: an infrastructure "
            "failure cannot be told apart from an A2 violation (D18)"
        )
    violations = [a["directory"] for a in attempts if a["a2_violation"]]
    if violations:
        raise P1RefusalError(
            f"earlier attempt(s) {violations} stopped on an A2 violation: a confirmation is only "
            "repeated after an infrastructure failure, never after an A2 violation (D18)"
        )
    if mode.name == "second_confirmation":
        first = list_attempts(output_root / "confirmation" / CONFIRMATION_LEAF)
        blocked = [
            a["directory"]
            for a in first
            if a["a2_violation"] is not False or a["kind"] == "partial"
        ]
        if blocked:
            raise P1RefusalError(
                f"first-confirmation attempt(s) {blocked} stopped on an A2 violation, or have no "
                "valid record: they cannot justify a second confirmation (D18, P1-21)"
            )
    return attempts


# ---------------------------------------------------------------- completed results (I-2)


def _field(data: Mapping[str, Any], dotted: str) -> Any:
    value: Any = data
    for key in dotted.split("."):
        value = value.get(key) if isinstance(value, Mapping) else None
    return value


ROW_IDENTITY = ("block", "stage", "iteration", "scenario", "condition", "seed_group", "item")


def _csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        return list(reader.fieldnames or []), rows


def _expected_identities(spec: P1Spec, data: Mapping[str, Any]) -> list[tuple[str, ...]]:
    """Row identities of a published block, rebuilt from its provenance and the P1 spec."""
    try:
        values = CandidateValues(**data["values"])
        grid = {PHASE_STAGES[p]: p for p in GRID_PHASES}.get(data.get("stage"))
        if grid is not None:  # T4c: a grid of a round
            tasks = tuple(task for task, _ in plan_grid(spec, values, grid))
        else:
            tasks = plan_block(spec, data["block"], values, scenarios=tuple(data["scenarios"]))
    except (KeyError, TypeError, ValueError) as error:
        raise P1RefusalError(f"the provenance cannot rebuild its plan: {error}") from error
    stage, iteration = str(data.get("stage")), str(data.get("iteration"))
    return [
        (t.block, stage, iteration, t.scenario, t.condition.name, str(t.seed_group), str(t.item))
        for t in tasks
    ]


def verify_result(
    directory: Path, expected: Mapping[str, Any], spec: P1Spec
) -> tuple[dict, list[Path]]:
    """A published, completed result with the expected identity; returns it and its files.

    Checks only the existence and integrity of the result, never the value of a criterion
    (that is task T4b): status ``completed``; mode, block, iteration, values and the hashes of
    the configuration files; every planned episode written; the SHA-256 of ``episodes.csv`` and
    ``bootstrap_keys.csv`` recorded at publication (T3c, Mn-4); and the identity of every row
    (block, stage, iteration, scenario, condition, seed group and item) in the planned order.
    """
    label = directory.as_posix()
    provenance_path = directory / PROVENANCE_FILE
    if not provenance_path.is_file():
        raise P1RefusalError(f"{label} must be a published, completed result first (P1-18)")
    data = _read_json(provenance_path)
    if not isinstance(data, dict) or data.get("schema") != PROVENANCE_SCHEMA:
        raise P1RefusalError(f"{label}: {PROVENANCE_FILE} is not a P1 provenance record")
    if data.get("status") != "completed":
        raise P1RefusalError(f"{label}: status {data.get('status')!r}, expected 'completed'")
    for key, value in expected.items():
        if _field(data, key) != value:
            raise P1RefusalError(f"{label}: {key} is {_field(data, key)!r}, expected {value!r}")
    planned, written = data.get("episodes_planned"), data.get("episodes_written")
    if type(planned) is not int or planned < 1 or written != planned:
        raise P1RefusalError(f"{label}: {written!r} of {planned!r} planned episodes written")
    episodes = directory / EPISODES_FILE
    published = [directory / name for name in result_names(str(data.get("stage")))]
    recorded = data.get("result_files")
    for path in published:
        if not path.is_file():
            raise P1RefusalError(f"{label}: {path.name} is missing")
        if not isinstance(recorded, dict) or recorded.get(path.name) != file_sha256(path):
            raise P1RefusalError(
                f"{label}: {path.name} does not match the SHA-256 recorded at publication"
            )
    header, rows = _csv_rows(episodes)
    if tuple(header) != EPISODE_COLUMNS or len(rows) != written:
        raise P1RefusalError(
            f"{label}: {EPISODES_FILE} has {len(rows)} rows (expected {written}) or wrong columns"
        )
    identities = [tuple(row[name] for name in ROW_IDENTITY) for row in rows]
    if identities != _expected_identities(spec, data):
        raise P1RefusalError(f"{label}: the rows of {EPISODES_FILE} are not the planned episodes")
    return data, [provenance_path, *published]


def published_winner(
    directory: Path, data: Mapping[str, Any], spec: P1Spec, phase: str
) -> dict[str, float]:
    """Winner of a published grid, recomputed from its rows (T4c, D-T4c-2).

    The selection is computed again with the P1-17 functions from ``episodes.csv`` and the
    values in force recorded in the provenance; ``selection.json`` must be exactly that.
    """
    label = directory.as_posix()
    try:
        rows = read_episodes(directory / EPISODES_FILE)
        selection = grid_selection(
            rows,
            phase,
            spec.grids.prey_flee_threshold,
            spec.grids.cruise_fraction,
            data["values"],
        )
    except (CriteriaError, KeyError, TypeError) as error:
        raise P1RefusalError(f"{label}: the winner cannot be recomputed ({error})") from error
    if render_selection(selection, phase) != (directory / SELECTION_FILE).read_bytes():
        raise P1RefusalError(
            f"{label}: {SELECTION_FILE} is not the selection recomputed from its episodes (P1-17)"
        )
    return dict(zip(selection.parameters, selection.winner, strict=True))


PHASES_BEFORE = {"prey": (), "predator": ("prey",), "reevaluation": ("prey", "predator")}


def check_prerequisites(
    mode: Mode,
    registry: Registry,
    output_root: Path,
    spec: P1Spec,
    config_files: Mapping[str, str],
) -> tuple[list[dict[str, Any]], list[Path], dict[str, float]]:
    """The completed results that must precede this mode, with their specification hashes.

    Every prerequisite must have been produced with exactly the same configuration files
    (``config_files``: SHA-256 of p1.yaml, p0.yaml, base.yaml, scenarios.yaml and
    baselines.yaml), so no parameter outside the candidate can change along the chain (IA-3).

    A phase of round R (T4c) needs the iterations up to its anchor, every phase of the earlier
    rounds (A_rev only when the round changed a value) and the earlier phases of R. The
    winners of R so far are returned, recomputed from the published grids.
    """
    records: list[dict[str, Any]] = []
    files: list[Path] = []

    def need(directory: Path, expected: Mapping[str, Any]) -> dict:
        data, paths = verify_result(directory, {**expected, "config_files": config_files}, spec)
        records.append(
            {
                "directory": directory.as_posix(),
                "mode": data.get("mode"),
                "values_iteration": data.get("values_iteration"),
                "provenance_sha256": file_sha256(paths[0]),
            }
        )
        files.extend(paths)
        return data

    calibration = output_root / CALIBRATION_BLOCK
    last = mode.iteration - 1 if mode.name == "iteration" else mode.values_iteration
    for number in range(1, last + 1):
        need(
            calibration / f"iteration_{number:03d}",
            {
                "mode": "iteration",
                "block": CALIBRATION_BLOCK,
                "iteration": number,
                "values_iteration": number,
                "values_source.sha256": registry.sha256(number),
            },
        )
    if mode.name == "confirmation":
        need(
            calibration / ENTRY_LEAF,
            {
                "mode": "entry",
                "block": CALIBRATION_BLOCK,
                "values_iteration": last,
                "values_source.sha256": registry.sha256(last),
            },
        )
    elif mode.name == "second_confirmation":
        first = need(
            output_root / "confirmation" / CONFIRMATION_LEAF,
            {"mode": "confirmation", "block": "confirmation"},
        )
        used = first.get("values_iteration")
        if type(used) is not int or used >= last:
            raise P1RefusalError(
                f"the first confirmation used iteration {used!r}: a second confirmation follows "
                f"a recalibration, so its values must come from a later iteration, not "
                f"{last} (P1-21); it never repeats or replaces the first confirmation"
            )
        if _field(first, "values_source.sha256") != registry.sha256(used):
            raise P1RefusalError(
                f"the specification of iteration {used} changed after the first confirmation"
            )
    winners: dict[str, float] = {}
    if mode.round_number:
        for _, round_spec in sorted(registry.rounds, key=lambda item: item[1].round_number):
            number = round_spec.round_number
            if number > mode.round_number:
                break
            phases = PHASES_BEFORE[mode.phase] if number == mode.round_number else ROUND_PHASES
            winners = {}
            for phase in phases:
                values = dataclasses.replace(round_spec.values, **winners)
                if phase == "reevaluation" and not values.differing(round_spec.values):
                    continue  # a round that changed nothing has no A_rev (P1-18)
                directory = phase_directory(output_root, number, phase)
                data = need(
                    directory,
                    {
                        "mode": PHASE_MODES[phase],
                        "block": CALIBRATION_BLOCK,
                        "round": number,
                        "values": dataclasses.asdict(values),
                        "values_source.sha256": registry.round_sha256(number),
                    },
                )
                if phase in GRID_PHASES:
                    winners.update(published_winner(directory, data, spec, phase))
    return records, files, winners


def previous_a_evaluation(mode: Mode, registry: Registry, output_root: Path) -> Path:
    """The evaluation of A that a round starts from (D-T4c-4): its anchor iteration, or the
    A_rev of the previous round on the same anchor."""
    earlier = [
        spec.round_number
        for _, spec in registry.rounds
        if spec.round_number < mode.round_number and spec.after_iteration == mode.iteration
    ]
    if earlier:
        return phase_directory(output_root, max(earlier), "reevaluation")
    return output_root / CALIBRATION_BLOCK / f"iteration_{mode.iteration:03d}"


COMPARED_OUT = ("block", "stage", "iteration")  # identify the block, not the episode


def check_reproduces_previous(
    rows: Sequence[Mapping[str, Any]], values: CandidateValues, previous: Path
) -> None:
    """D-T4c-4: the combination in force reproduces the rules episodes of A of ``previous``.

    Same seeds and same configuration give the same episodes (ADR-016, DET-5); any difference
    stops the round, because the grid would not compare like with like.
    """
    current = {
        str(row["item"]): row
        for row in rows
        if float(row["prey_flee_threshold"]) == values.prey_flee_threshold
        and float(row["prey_cruise_fraction"]) == values.prey_cruise_fraction
    }
    _, previous_rows = _csv_rows(previous / EPISODES_FILE)
    reference = {
        row["item"]: row
        for row in previous_rows
        if row["scenario"] == "A" and row["condition"] == "rules"
    }
    if not current or current.keys() != reference.keys():
        raise ValueError(
            f"D-T4c-4: the combination in force does not have the episodes of "
            f"{previous.as_posix()}; the round stops"
        )
    for item, row in sorted(current.items()):
        different = [
            name
            for name in EPISODE_COLUMNS
            if name not in COMPARED_OUT and str(row[name]) != reference[item][name]
        ]
        if different:
            raise ValueError(
                f"D-T4c-4: item {item} of the combination in force differs from "
                f"{previous.as_posix()} in {different}; the round stops"
            )


# ---------------------------------------------------------------- pre-flight


@dataclass
class Preflight:
    spec: P1Spec
    registry: Registry
    configs: dict[tuple[str, tuple[str, ...]], ResolvedConfig]
    tasks: tuple
    admissibility: Any
    project_seed: int
    prerequisites: list[dict[str, Any]]
    attempts: list[dict[str, Any]]
    inputs: list[Path]
    config_files: dict[str, str]  # SHA-256 of the five configuration files (IA-3)
    real_groups: bool  # the specification declares real P1 seed groups (10-32)
    # T4c: the values the block runs with (a round's winners applied), per task, and the
    # evaluation of A the prey grid must reproduce (D-T4c-4); None outside the prey grid.
    values: CandidateValues | None = None
    task_values: dict[Any, CandidateValues] | None = None
    previous_evaluation: Path | None = None
    # T4c (D-T4c-5): the verification of the P1-18 sequence, or why it did not apply.
    sequence_gate: dict[str, Any] | None = None
    # T4d (D-T4d-2): code and environment fingerprints of this block.
    fingerprint: dict[str, Any] | None = None


SYNTHETIC_GATE_RECORD = {
    "applied": False,
    "reason": "every seed group is synthetic (>= 1000, D16): test specification",
}


def sequence_gate(
    mode: Mode,
    spec_path: Path,
    spec: P1Spec,
    registry: Registry,
    output_root: Path,
    prey_e_max: float,
    fingerprint: Mapping[str, Any],
    config_files: Mapping[str, str],
) -> tuple[dict[str, Any], list[Path]]:
    """D-T4c-5: the P1-18 sequence allows this block, unless the specification is synthetic.

    There is no option to skip it: only the seed groups of the specification decide, and any
    group below 1000 (the real ones included) requires it. T4d adds the STOP of D-T4d-1 and
    D-T4d-2 (failed attempts, and the fingerprints of every published block) and the author
    decisions of D-T4d-3 (``p1_decisions/`` next to the specification).
    """
    if not sequence_gate_required(spec):
        return dict(SYNTHETIC_GATE_RECORD), []
    # Imported here: pilot_p1_sequence builds on this module (verify_result, Registry, ...).
    from neuroeco.presentation.pilot_p1_sequence import check_sequence_gate

    try:
        decisions = load_decisions(spec_path)
    except ConfigError as error:
        raise P1RefusalError(f"author decisions (D-T4d-3): {error}") from error
    return check_sequence_gate(
        mode, registry, output_root, spec, decisions, prey_e_max, fingerprint, config_files
    )


def preflight(
    mode: Mode,
    spec_path: Path,
    config_dir: Path,
    author_authorized: bool,
    destination: Path,
    output_root: Path,
) -> Preflight:
    """Validations that need no result value, in the order approved by the author (T3-T3c).

    T4c adds the verification of the P1-18 sequence (D-T4c-5) after the static sequence.
    """
    p0_path = config_dir / "pilots" / "p0.yaml"
    p0 = load_p0_spec(p0_path)
    spec = load_p1_spec(spec_path, {"exploratory": EXPLORATORY_SEED_GROUP, "P0": p0.seed_group})
    try:
        check_approved_seed_groups(spec)
    except ValueError as error:
        raise P1RefusalError(str(error)) from error
    real_groups = any(g in REAL_SEED_GROUPS for g in spec.declared_seed_groups().values())
    config_paths = {
        "p1_spec": spec_path,
        "p0_spec": p0_path,
        "base": config_dir / BASE_FILE,
        "scenarios": config_dir / SCENARIOS_FILE,
        "baselines": config_dir / BASELINES_FILE,
    }
    config_files = {name: file_sha256(path) for name, path in config_paths.items()}

    registry = load_registry(spec_path)
    if mode.round_number:
        current: IterationSpec | RoundSpec = _registered_round(mode.source, registry)
    else:
        current = _registered(mode.source, registry)
    if mode.name in VALUES_FROM_MODES:
        last_path, last = registry.iterations[-1]
        if last_path.resolve() != mode.source.resolve() or last.stage != "C":
            raise P1RefusalError(
                f"--values-from must be the last registered iteration, of stage C (P1-18); "
                f"the last one is {last_path.name} (stage {last.stage})"
            )
    reference = load_config(config_dir, "A", scenario_overrides(current.values, "A"))
    check_calibration_sequence(
        [s for _, s in registry.iterations],
        [s for _, s in registry.rounds],
        spec.grids,
        reference.world.n_predators,
    )
    fingerprint = p1_fingerprint(Path.cwd() / "uv.lock")
    gate_record, gate_files = sequence_gate(
        mode,
        spec_path,
        spec,
        registry,
        output_root,
        reference.world.prey.e_max,
        fingerprint,
        config_files,
    )

    check_no_recalibration(mode, output_root)
    attempts = check_attempts(mode, destination, output_root)
    prerequisites, result_files, winners = check_prerequisites(
        mode, registry, output_root, spec, config_files
    )
    # A round's phases run with the winners published so far (D-T4c-2); otherwise no change.
    values = dataclasses.replace(mode.values, **winners)
    if mode.phase == "reevaluation" and not values.differing(mode.values):
        raise P1RefusalError(
            f"round {mode.round_number} changed no value: there is no A_rev, the next step is "
            "T_fin (P1-18)"
        )

    candidate = {s: load_config(config_dir, s, scenario_overrides(values, s)) for s in SCENARIOS}
    state_k = admissibility({s: config.world for s, config in candidate.items()})
    if not state_k.a1:
        failed = [f"{s}:{c.constraint_id}" for s, c in state_k.checks if not c.satisfied]
        raise P1RefusalError(
            f"state K: A1 does not hold ({failed + list(state_k.design_problems)}); "
            "the candidate is rejected without running episodes (P1-18)"
        )

    if mode.phase in GRID_PHASES:
        planned = plan_grid(spec, values, mode.phase)
        check_grid_plan(planned, spec, values, mode.phase)
        tasks = tuple(task for task, _ in planned)
        task_values = dict(planned)
    else:
        tasks = plan_block(spec, mode.block, values, scenarios=mode.scenarios)
        check_block_plan(tasks, spec, mode.block, values, mode.scenarios)
        task_values = dict.fromkeys(tasks, values)
    previous = previous_a_evaluation(mode, registry, output_root) if mode.phase == "prey" else None
    configs = {}
    for task in tasks:
        key = (task.scenario, task.overrides)
        if key not in configs:
            configs[key] = load_config(config_dir, task.scenario, task.overrides)
    seeds = {config.project_seed for config in configs.values()}
    if len(seeds) != 1:
        raise P1RefusalError("all configurations of a block must share the project seed")

    if mode.block in CONFIRMATION_BLOCKS and not author_authorized:
        raise P1RefusalError(
            f"the {mode.block} block runs only with --author-authorized (P1-21, D16)"
        )
    if destination.exists():
        raise P1RefusalError(f"{destination} already exists; results are never overwritten")

    inputs = [
        *config_paths.values(),
        *(path for path, _ in registry.iterations),
        *(path for path, _ in registry.rounds),
        *result_files,
        *gate_files,
    ]
    return Preflight(
        spec,
        registry,
        configs,
        tasks,
        state_k,
        seeds.pop(),
        prerequisites,
        attempts,
        inputs,
        config_files,
        real_groups,
        values,
        task_values,
        previous,
        gate_record,
        fingerprint,
    )


# ---------------------------------------------------------------- git checks (P1-19, T3b, T3c)


def package_directory() -> Path:
    """Directory of the ``neuroeco`` package that is running (its code must be the commit's)."""
    return Path(neuroeco.__file__).resolve().parent


def destination_files(destination: Path) -> list[Path]:
    """Files the command may write for ``destination``; none of them may be ignored by git."""
    failed = destination.with_name(f"{destination.name}.failed-00000000T000000Z-00000000")
    partial = destination.with_name(f"{destination.name}.partial-00000000")
    return [
        *(
            destination / name
            for name in (EPISODES_FILE, BOOTSTRAP_FILE, SELECTION_FILE, PROVENANCE_FILE)
        ),
        *(directory / name for directory in (failed, partial) for name in (FAILURE_FILE,)),
        failed / PROVENANCE_FILE,
    ]


def repository_checks(
    cwd: Path,
    inputs: Sequence[Path],
    output_root: Path,
    destination: Path,
    spec_path: Path,
    config_dir: Path,
) -> dict[str, Any]:
    """What git says about the code, the files read and the output root (P1-19; T3b, T3c).

    It never trusts the paths or ``git status`` alone:

    - every file read is inside the repository and tracked;
    - no tracked file is marked assume-unchanged or skip-worktree (IA-1);
    - every tracked file, code included, has exactly the content of HEAD, compared with
      ``git hash-object`` (IA-1), and the running ``neuroeco`` package is inside the repository;
    - the destination files are not ignored by git (Mn-3);
    - the upstream is a remote-tracking branch with the commit of HEAD (M-1, Mn-1).
    """
    root = git_toplevel(cwd)
    if root is None:
        return {
            "root": None,
            "outside_repository": [p.as_posix() for p in inputs],
            "untracked": None,
            "hidden_changes": None,
            "content_overrides": None,
            "head_mismatches": None,
            "package_inside": False,
            "canonical_paths": False,
            "output_root_inside": False,
            "ignored_outputs": None,
            "head": None,
            "upstream": None,
            "upstream_full_ref": None,
            "remote": None,
            "remote_url": None,
            "upstream_commit": None,
            "synchronized": False,
        }
    inside = [p for p in inputs if is_inside(p, root)]
    untracked = git_untracked(inside, root)
    output_inside = is_inside(output_root, root)
    ignored = git_ignored(destination_files(destination), root) if output_inside else None
    state = git_state(root)
    upstream = git_upstream(root)
    canonical = (
        spec_path.resolve() == (root / "configs" / "pilots" / "p1.yaml").resolve()
        and config_dir.resolve() == (root / "configs").resolve()
        and output_root.resolve() == (root / DEFAULT_OUTPUT_ROOT).resolve()
    )
    return {
        "root": root.as_posix(),
        "outside_repository": [p.as_posix() for p in inputs if p not in inside],
        "untracked": None if untracked is None else [p.as_posix() for p in untracked],
        "hidden_changes": git_hidden_changes(root),
        "content_overrides": git_content_overrides(root),
        "head_mismatches": git_head_mismatches(root),
        "package_inside": is_inside(package_directory(), root),
        "canonical_paths": canonical,
        "output_root_inside": output_inside,
        "ignored_outputs": ignored,
        "head": state["commit"],
        "upstream": upstream["ref"],
        "upstream_full_ref": upstream["full_ref"],
        "remote": upstream["remote"],
        "remote_url": upstream["remote_url"],
        "upstream_commit": upstream["commit"],
        "synchronized": state["commit"] is not None and state["commit"] == upstream["commit"],
    }


def check_reserved_use(spec_path: Path, output_root: Path) -> None:
    """D-T4d-4: under the reserved root only the approved specification writes, at its root.

    Runs before anything is written. The marker is searched from ``output_root`` up through the
    file system, so any spelling of the same directory finds it. Without a marker nothing is
    checked here (the synthetic tests and their temporary repositories).
    """
    root = reserved_root(output_root)
    if root is None:
        return
    marker = read_reserved(root)
    label = (root / RESERVED_FILE).as_posix()
    if not same_directory(output_root, root):
        raise ReservedRootError(
            f"{label} reserves {root.as_posix()}: the output root must be that directory itself"
        )
    if not uses_approved_table(load_p1_spec(spec_path, {})):
        raise ReservedRootError(
            f"{label}: only the approved P1 table (ADR-033, P1-5, P1-13) writes under the real "
            "results; a synthetic or modified specification is refused"
        )
    if file_sha256(spec_path) != marker["p1_spec_sha256"]:
        raise ReservedRootError(f"{label}: {spec_path.as_posix()} is not the reserved spec")


def check_real_root(plan: Preflight, spec_path: Path, output_root: Path) -> str | None:
    """D-T4d-4: a real block runs only at its reserved root, on the reference fingerprints.

    Checked after the git checks (the canonical paths of IA-3 come first). Returns the SHA-256
    of the marker, recorded in the provenance; None when there is no marker (synthetic).
    """
    root = reserved_root(output_root)
    marker_path = None if root is None else root / RESERVED_FILE
    if not plan.real_groups:
        return None if marker_path is None else file_sha256(marker_path)
    if root is None or marker_path is None or not same_directory(output_root, root):
        raise P1RefusalError(
            f"the real P1 seed groups run only at a root reserved by {RESERVED_FILE} (D-T4d-4)"
        )
    marker = read_reserved(root)
    if file_sha256(spec_path) != marker["p1_spec_sha256"]:
        raise P1RefusalError(f"{spec_path.as_posix()} is not the reserved spec (D-T4d-4)")
    reference = marker["fingerprint"]
    different = [
        f"{part}.{name}"
        for part, values in (plan.fingerprint or {}).items()
        for name, value in values.items()
        if not isinstance(reference.get(part), dict) or reference[part].get(name) != value
    ]
    if different:
        raise P1RefusalError(
            f"STOP (P1-18): {different} differ from the reference fingerprint of "
            f"{RESERVED_FILE} (D-T4d-2, D-T4d-4)"
        )
    return file_sha256(marker_path)


def refuse_on_git(base: Mapping[str, Any], checks: Mapping[str, Any], *, real_groups: bool) -> None:
    if base.get("git_dirty") is not False:
        raise P1RefusalError(
            f"the git working tree must be clean (P1-19); git_dirty = {base.get('git_dirty')!r}"
        )
    if checks["root"] is None:
        raise P1RefusalError("the command must run inside the git repository (P1-19)")
    if any(checks[k] is None for k in ("hidden_changes", "content_overrides", "head_mismatches")):
        raise P1RefusalError("git could not compare the working tree with HEAD (P1-19)")
    if checks["content_overrides"]:
        raise P1RefusalError(
            f"local git settings can disguise modified content as HEAD: "
            f"{checks['content_overrides']} (P1-19, T3c IA-1)"
        )
    if checks["hidden_changes"]:
        raise P1RefusalError(
            f"files marked assume-unchanged or skip-worktree: {checks['hidden_changes']}; git "
            "status does not look at them (P1-19, T3c IA-1)"
        )
    if checks["head_mismatches"]:
        raise P1RefusalError(
            f"files whose content differs from HEAD: {checks['head_mismatches']} (P1-19, T3c IA-1)"
        )
    if not checks["package_inside"]:
        raise P1RefusalError(
            "the running neuroeco package is not the one of this repository: the provenance "
            "would not identify the code that runs (P1-19, T3c IA-1)"
        )
    if checks["outside_repository"]:
        raise P1RefusalError(
            f"files outside the repository: {checks['outside_repository']}; every specification "
            "and configuration must be versioned (P1-19)"
        )
    if checks["untracked"] is None:
        raise P1RefusalError("git could not list the tracked files (P1-19)")
    if checks["untracked"]:
        raise P1RefusalError(f"files not tracked by git: {checks['untracked']} (P1-19)")
    if real_groups and not checks["canonical_paths"]:
        raise P1RefusalError(
            "with the real P1 seed groups the specification must be configs/pilots/p1.yaml, "
            "the configuration directory configs/ and the output root results/pilots/p1 of the "
            "repository (T3c, IA-3)"
        )
    if not checks["output_root_inside"]:
        raise P1RefusalError("the output root must be inside the repository (P1-19)")
    if checks["ignored_outputs"] is None:
        raise P1RefusalError("git could not check the ignore rules of the output root (P1-19)")
    if checks["ignored_outputs"]:
        raise P1RefusalError(
            f"git ignores result files: {checks['ignored_outputs']}; results and failure "
            "records must be versioned (P1-19, T3c Mn-3)"
        )
    if checks["upstream"] is None:
        raise P1RefusalError("HEAD has no upstream branch: push the specification first (P1-19)")
    if (
        not (checks["upstream_full_ref"] or "").startswith("refs/remotes/")
        or not checks["remote_url"]
    ):
        raise P1RefusalError(
            f"the upstream {checks['upstream']!r} is not a remote-tracking branch of a remote "
            f"with a URL ({checks['upstream_full_ref']!r}): nothing would be published "
            "(P1-19, T3c Mn-1)"
        )
    if not checks["synchronized"]:
        raise P1RefusalError(
            f"HEAD {checks['head']} is not synchronized with {checks['upstream']} "
            f"({checks['upstream_commit']}): push the specification commit first (P1-19)"
        )


# ---------------------------------------------------------------- records


def _sha_or_none(path: Path) -> str | None:
    try:
        return file_sha256(path)
    except OSError:
        return None


def mode_summary(mode: Mode) -> dict[str, Any]:
    return {
        "name": mode.name,
        "block": mode.block,
        "stage": mode.stage,
        "iteration": mode.iteration,
        "values_iteration": mode.values_iteration,
        "values_source": {"path": mode.source.as_posix(), "sha256": _sha_or_none(mode.source)},
        "values": dataclasses.asdict(mode.values),
        **_round_fields(mode),
    }


def _round_fields(mode: Mode) -> dict[str, Any]:
    """T4c: the round and phase of a round mode (additive fields, absent otherwise)."""
    return {"round": mode.round_number, "phase": mode.phase} if mode.round_number else {}


def provenance_document(
    mode: Mode,
    plan: Preflight,
    base: dict[str, Any],
    spec_path: Path,
    author_authorized: bool,
) -> dict[str, Any]:
    uv_lock = Path.cwd() / "uv.lock"
    return {
        "schema": PROVENANCE_SCHEMA,
        "status": "running",
        **base,
        "mode": mode.name,
        "block": mode.block,
        "stage": mode.stage,
        "iteration": mode.iteration,
        "values_iteration": mode.values_iteration,
        "bootstrap_run": mode.run,
        "scenarios": list(mode.scenarios),
        "episodes_per_condition": plan.spec.blocks.named()[mode.block].episodes,
        "episodes_planned": len(plan.tasks),
        "author_authorized": author_authorized,
        "project_seed": str(plan.project_seed),
        **_round_fields(mode),
        # the values the block ran with (for a round phase, the winners so far applied)
        "values": dataclasses.asdict(plan.values or mode.values),
        "values_source": {"path": mode.source.as_posix(), "sha256": file_sha256(mode.source)},
        "p1_spec": {"path": spec_path.as_posix(), "sha256": file_sha256(spec_path)},
        "registered_iterations": [
            {"path": p.as_posix(), "sha256": file_sha256(p)} for p, _ in plan.registry.iterations
        ],
        "registered_rounds": [
            {"path": p.as_posix(), "sha256": file_sha256(p)} for p, _ in plan.registry.rounds
        ],
        "config_files": plan.config_files,
        "input_files": [
            {"path": p.as_posix(), "sha256": file_sha256(p)} for p in dict.fromkeys(plan.inputs)
        ],
        "prerequisites": plan.prerequisites,
        "previous_attempts": plan.attempts,
        "sequence_gate": plan.sequence_gate,  # T4c, D-T4c-5 (additive, Mn-8)
        "fingerprint": plan.fingerprint,  # T4d, D-T4d-2 (additive, Mn-8)
        "reserved_sha256": None,  # T4d, D-T4d-4: set after the git checks
        "git_checks": None,
        "uv_lock_sha256": file_sha256(uv_lock) if uv_lock.exists() else None,
        "dependencies": dependency_versions(DEPENDENCIES),
        "state_k": {
            "a1": plan.admissibility.a1,
            "b7_margin": plan.admissibility.b7_margin,
            "checks": [
                {
                    "scenario": s,
                    "constraint": c.constraint_id,
                    "satisfied": c.satisfied,
                    "value": c.value,
                    "target": c.target,
                }
                for s, c in plan.admissibility.checks
            ],
        },
        "configurations": [
            {
                "scenario": scenario,
                "overrides": list(overrides),
                "config_hash": config.config_hash,
                "world": dataclasses.asdict(config.world),
                "rules": dataclasses.asdict(config.rules),
            }
            for (scenario, overrides), config in plan.configs.items()
        ],
        "finished_utc": None,
        "duration_seconds": None,
        "episodes_written": None,
        "episodes_discarded": None,
        "result_files": None,
        "a2_violation": None,
    }


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def failure_document(
    error: BaseException,
    phase: str,
    destination: Path,
    completed: int,
    mode: Mode,
    partial: Path | None,
) -> dict[str, Any]:
    a2 = None
    if isinstance(error, A2ViolationError):
        task = error.task
        a2 = {
            "invariant": error.violation.invariant,
            "step": error.violation.step,
            "detail": error.violation.detail,
            "task": {
                "block": task.block,
                "scenario": task.scenario,
                "condition": task.condition.name,
                "seed_group": task.seed_group,
                "item": task.item,
                "label": task.label,
            },
        }
    return {
        "schema": FAILURE_SCHEMA,
        "timestamp_utc": _now().isoformat(timespec="seconds"),
        "phase": phase,
        "destination": destination.as_posix(),
        "command": list(sys.argv),
        "git": git_state(Path.cwd()),
        "mode": mode_summary(mode),
        "previous_attempts": list_attempts(destination, exclude=partial),
        "error_type": f"{type(error).__module__}.{type(error).__qualname__}",
        "message": str(error),
        "notes": list(getattr(error, "__notes__", [])),
        "episodes_completed": completed,
        "a2_violation": a2,
    }


def failed_provenance(
    provenance: Mapping[str, Any], discarded: int, *, a2_violation: bool
) -> dict[str, Any]:
    """The provenance of a failed block: nothing was published, every episode was discarded."""
    return {
        **provenance,
        "status": "failed",
        "finished_utc": None,
        "duration_seconds": None,
        "episodes_written": None,
        "episodes_discarded": discarded,
        "result_files": None,
        "a2_violation": a2_violation,
    }


def _write_records(
    directory: Path, provenance: dict[str, Any] | None, failure: dict[str, Any]
) -> None:
    replace_json(directory / FAILURE_FILE, failure)  # first: the evidence that matters most
    if provenance is not None:
        replace_json(
            directory / PROVENANCE_FILE,
            failed_provenance(
                provenance,
                failure["episodes_completed"],
                a2_violation=failure["a2_violation"] is not None,
            ),
        )


def record_failure(
    destination: Path,
    partial: Path | None,
    provenance: dict[str, Any] | None,
    failure: dict[str, Any],
) -> Path:
    """Keep the failure as its own artifact; CSV files of an unfinished block are discarded.

    With a partial directory, ``failure.json`` and the failed provenance are written INSIDE it
    before anything else and before the rename (T3c, IA-2): if the rename then fails (a
    Windows lock that outlasts the retries), the partial directory still carries the evidence,
    including an A2 violation, and can never be taken for an interruption without record.
    """
    if partial is not None and partial.exists():
        _write_records(partial, provenance, failure)
        for leftover in partial.glob("*.csv"):
            leftover.unlink()
        return reserve_failure_directory(destination, _now(), source=partial)
    directory = reserve_failure_directory(destination, _now())
    _write_records(directory, provenance, failure)
    return directory


def _report(error: BaseException, phase: str) -> None:
    """Say what happened on the console BEFORE recording it, in case recording fails (IA-2)."""
    if isinstance(error, A2ViolationError):
        typer.echo(f"A2 violation, block stopped: {error}", err=True)
    else:
        typer.echo(f"error ({phase}): {error}", err=True)


# ---------------------------------------------------------------- command


def pilot_p1(
    iteration: Annotated[
        Path | None, typer.Option("--iteration", help="Registered iteration file NNN.yaml.")
    ] = None,
    entry_evaluation: Annotated[
        bool, typer.Option("--entry-evaluation", help="Entry evaluation (state E).")
    ] = False,
    confirmation: Annotated[
        bool, typer.Option("--confirmation", help="Confirmation block (P1-21).")
    ] = False,
    second_confirmation: Annotated[
        bool, typer.Option("--second-confirmation", help="Second confirmation block.")
    ] = False,
    values_from: Annotated[
        Path | None,
        typer.Option("--values-from", help="Last registered iteration (entry/confirmation)."),
    ] = None,
    author_authorized: Annotated[
        bool,
        typer.Option("--author-authorized", help="The author authorized this confirmation."),
    ] = False,
    spec_path: Annotated[Path, typer.Option("--spec", help="P1 specification.")] = DEFAULT_SPEC,
    config_dir: Annotated[Path, typer.Option(help="Configuration directory.")] = (
        DEFAULT_CONFIG_DIR
    ),
    output_root: Annotated[Path, typer.Option(help="Root of the P1 results.")] = (
        DEFAULT_OUTPUT_ROOT
    ),
    round_spec: Annotated[
        Path | None, typer.Option("--round", help="Registered round file RR.yaml (T4c).")
    ] = None,
    round_phase: Annotated[
        str | None,
        typer.Option("--phase", help="Phase of the round: prey, predator or reevaluation."),
    ] = None,
) -> None:
    """Pilot P1: run one calibration iteration, a round phase, the entry or a confirmation."""
    try:
        mode = select_mode(
            iteration=iteration,
            entry_evaluation=entry_evaluation,
            confirmation=confirmation,
            second_confirmation=second_confirmation,
            values_from=values_from,
            author_authorized=author_authorized,
            round_spec=round_spec,
            phase=round_phase,
        )
    except (ValueError, OSError) as error:  # the destination is unknown: nothing to record
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=EXIT_FAILURE) from error

    try:  # D-T4d-4: checked before anything is written, so a refusal leaves no record there
        check_reserved_use(spec_path, output_root)
    except (ValueError, OSError) as error:
        typer.echo(f"refused: {error}", err=True)
        raise typer.Exit(code=EXIT_FAILURE) from error

    destination = mode.destination(output_root)
    phase, partial, provenance, completed = "preflight", None, None, 0
    try:
        plan = preflight(mode, spec_path, config_dir, author_authorized, destination, output_root)
        # Provenance is captured BEFORE anything is written (P1-19): git_dirty describes the
        # code that runs, not the files this command is about to create.
        first_hash = next(iter(plan.configs.values())).config_hash  # every hash is listed too
        base = collect_provenance(sys.argv, Path.cwd(), first_hash)
        provenance = provenance_document(mode, plan, base, spec_path, author_authorized)
        checks = repository_checks(
            Path.cwd(), plan.inputs, output_root, destination, spec_path, config_dir
        )
        provenance["git_checks"] = checks
        refuse_on_git(base, checks, real_groups=plan.real_groups)
        provenance["reserved_sha256"] = check_real_root(plan, spec_path, output_root)

        phase = "execution"
        started = time.perf_counter()
        partial = create_partial_directory(destination)
        replace_json(partial / PROVENANCE_FILE, provenance)
        rows = []
        outcomes = iter_block(
            plan.tasks,
            lambda scenario, overrides: plan.configs[(scenario, overrides)],
            build_policy,
            confirmation_authorized=author_authorized,
        )
        with closing(outcomes):
            for outcome in outcomes:
                world = plan.configs[(outcome.task.scenario, outcome.task.overrides)].world
                rows.append(
                    episode_row(
                        outcome,
                        world,
                        stage=mode.stage,
                        iteration=mode.iteration,
                        values=(plan.task_values or {}).get(outcome.task, mode.values),
                    )
                )
                completed += 1

        phase = "writing"
        block_spec = plan.spec.blocks.named()[mode.block]
        names = result_names(mode.stage)
        write_csv(partial / EPISODES_FILE, EPISODE_COLUMNS, rows)
        if BOOTSTRAP_FILE in names:
            write_csv(
                partial / BOOTSTRAP_FILE,
                BOOTSTRAP_COLUMNS,
                bootstrap_rows(block_spec, mode.run, mode.scenarios, plan.project_seed),
            )
        if SELECTION_FILE in names:  # T4c: a grid of a round
            if plan.previous_evaluation is not None:
                check_reproduces_previous(rows, mode.values, plan.previous_evaluation)
            selection = grid_selection(
                read_episodes(partial / EPISODES_FILE),
                mode.phase,
                plan.spec.grids.prey_flee_threshold,
                plan.spec.grids.cruise_fraction,
                dataclasses.asdict(plan.values or mode.values),
            )
            (partial / SELECTION_FILE).write_bytes(render_selection(selection, mode.phase))
        provenance = {
            **provenance,
            "status": "completed",
            "finished_utc": _now().isoformat(timespec="seconds"),
            "duration_seconds": round(time.perf_counter() - started, 3),
            "episodes_written": len(rows),
            "episodes_discarded": 0,
            "result_files": {name: file_sha256(partial / name) for name in names},
            "a2_violation": False,
        }
        replace_json(partial / PROVENANCE_FILE, provenance)
        publish_directory(partial, destination)
    except A2ViolationError as error:
        _report(error, phase)
        directory = record_failure(
            destination,
            partial,
            provenance,
            failure_document(error, phase, destination, completed, mode, partial),
        )
        typer.echo(f"failure recorded in {directory}", err=True)
        raise typer.Exit(code=EXIT_A2_VIOLATION) from error
    except Exception as error:
        _report(error, phase)
        directory = record_failure(
            destination,
            partial,
            provenance,
            failure_document(error, phase, destination, completed, mode, partial),
        )
        typer.echo(f"failure recorded in {directory}", err=True)
        raise typer.Exit(code=EXIT_FAILURE) from error
    except KeyboardInterrupt as error:
        record_failure(
            destination,
            partial,
            provenance,
            failure_document(error, phase, destination, completed, mode, partial),
        )
        raise

    typer.echo(f"P1 {mode.name}: {len(rows)} episodes written to {destination}")
