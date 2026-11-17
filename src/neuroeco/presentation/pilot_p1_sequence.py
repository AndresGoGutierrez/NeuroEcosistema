"""``neuroeco pilot p1-sequence``: verify the P1 calibration sequence (F4 T4b, D-T4b-1; T4c).

Read-only. The author runs it before authorizing each iteration (D-T4b-1), and since T4c
(D-T4c-5) ``pilot p1`` applies the same verification in its pre-flight through
``check_sequence_gate``: unless every seed group of the specification is synthetic (>= 1000,
D16), no block runs if the sequence does not allow exactly that step.

For every registered iteration with a published result it checks that the result belongs to
that registered specification (mode, stage, values and SHA-256 of the specification file) and
that its ``criteria.csv`` is exactly the evaluation of the current code (recomputed with
``analysis.calibration``, byte for byte, with ``criteria_provenance.json`` matching the input
files). The outcomes then go through ``analysis.sequence`` (P1-18).
"""

from __future__ import annotations

import csv
import dataclasses
import itertools
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Annotated, Any

import typer

from neuroeco.analysis.calibration import (
    PROVENANCE_FILE,
    CriteriaError,
    Status,
    block_files,
    criteria_rows,
    evaluate_block,
    load_block,
    requirements_met,
)
from neuroeco.analysis.sequence import (
    ENTRY,
    ITERATION,
    N_PLANTS_A,
    ROUND,
    Outcome,
    RoundResult,
    SequenceReport,
    Step,
    Verdict,
    verify_sequence,
)
from neuroeco.application.calibration import GRID_PHASES, P1Spec, RoundSpec
from neuroeco.application.decisions import (
    B_CRITERIA,
    D9_E5,
    ENTRY_REVIEW,
    NEXT_STAGE,
    REPEAT_STAGE,
    AuthorDecision,
    BCriteriaDecision,
    D9E5Decision,
    EntryReviewDecision,
    cites_decision,
)
from neuroeco.domain.params import E5_MAX_FRACTION
from neuroeco.domain.state import InitializationError
from neuroeco.infrastructure.config_loader import load_config, load_p1_spec
from neuroeco.infrastructure.decision_loader import load_decisions
from neuroeco.infrastructure.fingerprint import p1_fingerprint
from neuroeco.infrastructure.p1_reserved import RESERVED_FILE, reserved_root, same_directory
from neuroeco.infrastructure.provenance import file_sha256
from neuroeco.presentation.pilot_p1 import (
    CALIBRATION_BLOCK,
    CONFIRMATION_LEAF,
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_SPEC,
    ENTRY_LEAF,
    PHASE_MODES,
    ROUND_MODES,
    Mode,
    P1RefusalError,
    Registry,
    load_registry,
    phase_directory,
    published_winner,
    verify_result,
)
from neuroeco.presentation.pilot_p1 import _attempt as attempt_record
from neuroeco.presentation.pilot_p1_criteria import (
    CRITERIA_FILE,
    CRITERIA_PROVENANCE_FILE,
    render_criteria,
)

EXIT_NOT_ALLOWED = 1


class SequenceError(RuntimeError):
    """A published result cannot be used to verify the sequence."""


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SequenceError(f"{path.as_posix()} cannot be read ({error})") from None


def evaluated_files(directory: Path, stage: str) -> list[Path]:
    """The files of a published block that ``block_outcome`` reads (inputs of the gate)."""
    return [
        directory / PROVENANCE_FILE,
        *(directory / name for name in block_files(stage)),
        directory / CRITERIA_FILE,
        directory / CRITERIA_PROVENANCE_FILE,
    ]


def block_outcome(directory: Path, stage: str) -> Outcome:
    """Outcome of a published block whose criteria match the current evaluation exactly."""
    label = directory.as_posix()
    criteria = directory / CRITERIA_FILE
    if not criteria.is_file():
        raise SequenceError(f"{label}: no {CRITERIA_FILE}; run pilot p1-criteria first")
    block = load_block(directory)
    results = evaluate_block(block)
    if render_criteria(criteria_rows(results)) != criteria.read_bytes():
        raise SequenceError(
            f"{label}: {CRITERIA_FILE} does not match the criteria recomputed from the block"
        )
    record = _json(directory / CRITERIA_PROVENANCE_FILE)
    inputs = {name: file_sha256(directory / name) for name in block_files(block.stage)}
    if (
        not isinstance(record, dict)
        or record.get("criteria_sha256") != file_sha256(criteria)
        or record.get("input_files") != inputs
    ):
        raise SequenceError(f"{label}: {CRITERIA_PROVENANCE_FILE} does not match the files")
    failed_b = tuple(
        f"{r.criterion}{'/' + r.part if r.part else ''}@{r.scenario}"
        for r in results
        if r.criterion_class == "B" and r.status is Status.FAIL
    )
    return Outcome(requirements_met(stage, results), failed_b)


def _check_provenance(directory: Path, expected: dict[str, Any]) -> None:
    record = _json(directory / PROVENANCE_FILE)
    for key, value in expected.items():
        found: Any = record
        for part in key.split("."):
            found = found.get(part) if isinstance(found, dict) else None
        if found != value:
            raise SequenceError(
                f"{directory.as_posix()}: {key} is {found!r}, expected {value!r}: the result "
                "does not belong to the registered specification (P1-19)"
            )


def round_result(
    registry: Registry,
    round_spec: RoundSpec,
    output_root: Path,
    p1_spec: P1Spec,
    files: list[Path] | None = None,
    config_files: Mapping[str, str] | None = None,
) -> RoundResult | None:
    """Result of a round from its published phases (T4c); None until both grids exist.

    Each grid is verified as ``pilot p1`` verifies a prerequisite (completed, intact, the
    planned rows, the registered round) and its winner is recomputed from its rows (D-T4c-2).
    When a value changed, the A_rev outcome comes from its block and matching criteria.
    ``files``, when given, receives every file read; ``config_files``, when given, must be the
    configuration of every phase (IA-3, T4d).
    """
    read = files if files is not None else []
    same = {"config_files": dict(config_files)} if config_files else {}
    number = round_spec.round_number
    grids = [phase_directory(output_root, number, phase) for phase in GRID_PHASES]
    if not all(directory.exists() for directory in grids):
        return None
    winners: dict[str, float] = {}
    for phase, directory in zip(GRID_PHASES, grids, strict=True):
        values = dataclasses.replace(round_spec.values, **winners)
        data, paths = verify_result(
            directory,
            {
                "mode": PHASE_MODES[phase],
                "round": number,
                "values": dataclasses.asdict(values),
                "values_source.sha256": registry.round_sha256(number),
                **same,
            },
            p1_spec,
        )
        read.extend(paths)
        winners.update(published_winner(directory, data, p1_spec, phase))
    final = dataclasses.replace(round_spec.values, **winners)
    changed = bool(final.differing(round_spec.values))
    reevaluation = None
    directory = phase_directory(output_root, number, "reevaluation")
    if changed and directory.exists():
        _check_provenance(
            directory,
            {
                "mode": PHASE_MODES["reevaluation"],
                "round": number,
                "values": dataclasses.asdict(final),
                "values_source.sha256": registry.round_sha256(number),
                **same,
            },
        )
        reevaluation = block_outcome(directory, "A_rev")
        read.extend(evaluated_files(directory, "A_rev"))
    return RoundResult(changed, dataclasses.asdict(final), reevaluation)


def build_steps(
    registry: Registry,
    output_root: Path,
    p1_spec: P1Spec,
    files: list[Path] | None = None,
    config_files: Mapping[str, str] | None = None,
) -> list[Step]:
    """Registered iterations, each followed by its rounds, then the entry if it was published.

    ``files``, when given, receives every published file read; ``config_files``, when given,
    must be the configuration of every published block (IA-3; the gate of ``pilot p1``, T4d).
    """
    read = files if files is not None else []
    same = {"config_files": dict(config_files)} if config_files else {}
    calibration = output_root / CALIBRATION_BLOCK
    rounds = sorted(registry.rounds, key=lambda item: item[1].round_number)
    steps: list[Step] = []
    for path, spec in sorted(registry.iterations, key=lambda item: item[1].iteration):
        directory = calibration / f"iteration_{spec.iteration:03d}"
        outcome = None
        if directory.exists():
            _check_provenance(
                directory,
                {
                    "mode": "iteration",
                    "stage": spec.stage,
                    "iteration": spec.iteration,
                    "values": dataclasses.asdict(spec.values),
                    # the path is recorded as typed when the block ran; the content identifies it
                    "values_source.sha256": file_sha256(path),
                    **same,
                },
            )
            outcome = block_outcome(directory, spec.stage)
            read.extend(evaluated_files(directory, spec.stage))
        steps.append(
            Step(
                ITERATION,
                spec.iteration,
                spec.stage,
                spec.changed_parameter,
                outcome=outcome,
                values=dataclasses.asdict(spec.values),
            )
        )
        steps.extend(
            Step(
                ROUND,
                r.round_number,
                after_iteration=r.after_iteration,
                values=dataclasses.asdict(r.values),
                round_result=round_result(registry, r, output_root, p1_spec, read, config_files),
            )
            for _, r in rounds
            if r.after_iteration == spec.iteration
        )
    entry = calibration / ENTRY_LEAF
    if entry.exists():
        last = steps[-1].number if steps and steps[-1].kind == ITERATION else None
        expected: dict[str, Any] = {"mode": "entry", "values_iteration": last, **same}
        if last is not None:  # the entry carries the values of the last registered iteration
            expected["values_source.sha256"] = registry.sha256(last)
        _check_provenance(entry, expected)
        steps.append(Step(ENTRY, 0, outcome=block_outcome(entry, "entry")))
        read.extend(evaluated_files(entry, "entry"))
    return steps


# ---------------------------------------------------------------- gate of pilot p1 (D-T4c-5)

CONFIRMATION, SECOND_CONFIRMATION = "confirmation", "second_confirmation"


def gate_target(mode: Mode) -> tuple[str, int]:
    """The step of the sequence that a ``pilot p1`` mode runs: (kind, number)."""
    if mode.name == "iteration":
        return ITERATION, mode.iteration
    if mode.name in ROUND_MODES:
        return ROUND, mode.round_number
    if mode.name == "entry":
        return ENTRY, 0
    return mode.name, 0  # confirmation | second_confirmation


def _target_label(kind: str, number: int) -> str:
    if kind in (ITERATION, ROUND):
        return f"{kind} {number}"
    return "the entry evaluation" if kind == ENTRY else f"the {kind.replace('_', ' ')}"


def gate_report(
    steps: Sequence[Step], kind: str, number: int, d9_confirmed: Sequence[int] = ()
) -> SequenceReport:
    """The verification of ``steps`` if it allows exactly the step (kind, number) to run.

    Raises ``P1RefusalError`` otherwise: the step must be the pending one and its transition
    ``allowed``; a confirmation needs a complete sequence whose entry evaluation met the whole
    class A (P1-21, D11; the authorization itself is ``--author-authorized``). P1-18 has no
    state for a second confirmation: it needs a recalibration flow not yet approved (Mn-7).
    """
    reference = "(P1-18, D-T4c-5)"
    if kind == SECOND_CONFIRMATION:
        raise P1RefusalError(
            "the sequence of P1-18 never reaches a second confirmation: it needs a "
            f"recalibration flow that the author has not approved (Mn-7) {reference}"
        )
    steps = list(steps)
    if kind == ENTRY and not (steps and steps[-1].kind == ENTRY):
        steps.append(Step(ENTRY, 0))
    report = verify_sequence(steps, d9_confirmed=d9_confirmed)
    found = f"{report.next_step}: {report.verdict} ({report.reason})"
    if kind == CONFIRMATION:
        if report.verdict is Verdict.AUTHOR_AUTHORIZATION and steps and steps[-1].kind == ENTRY:
            return report
        raise P1RefusalError(
            "the confirmation needs a complete sequence whose entry evaluation met the whole "
            f"class A; the sequence gives {found} {reference}"
        )
    label = _target_label(kind, number)
    if report.verdict is not Verdict.ALLOWED:
        hint = ""
        if report.verdict is Verdict.AUTHOR_CONFIRMATION:
            hint = "; the E5 route of D9 needs a d9_e5 decision of the author (D-T4d-3)"
        raise P1RefusalError(f"the sequence does not allow {found}{hint} {reference}")
    pending = report.pending
    if pending is None or (pending.kind, pending.number) != (kind, number):
        raise P1RefusalError(
            f"the sequence allows {report.next_step} next, not {label} ({report.reason}) "
            f"{reference}"
        )
    return report


def check_sequence_gate(
    mode: Mode,
    registry: Registry,
    output_root: Path,
    p1_spec: P1Spec,
    decisions: Sequence[tuple[Path, AuthorDecision]],
    prey_e_max: float,
    fingerprint: Mapping[str, Any],
    config_files: Mapping[str, str] | None = None,
) -> tuple[dict[str, Any], list[Path]]:
    """Pre-flight of ``pilot p1`` (D-T4c-5): the record of the verification and the files read.

    First the STOP conditions of T4d: an earlier attempt that stops P1 (D-T4d-1), and any
    published block or criteria whose code or environment fingerprint is not ``fingerprint``
    (D-T4d-2).

    The sequence is built from the published results exactly as ``pilot p1-sequence`` builds it
    (results of their registered specifications, criteria recomputed byte for byte); any result
    that cannot be used, or a step that the sequence does not allow, refuses the block. The
    author decisions the steps need must exist and match what they judge (D-T4d-3).
    """
    raise_on_stops(attempt_stops(output_root), "D-T4d-1")
    unexpected = reserved_content_problems(output_root, registry)
    if unexpected:
        raise P1RefusalError(
            f"unexpected content in the reserved root of the real results: {unexpected}; only "
            "the blocks, attempts and criteria of registered steps belong there (D-T4d-4)"
        )
    files: list[Path] = [path for path, _ in decisions]
    try:
        steps = build_steps(registry, output_root, p1_spec, files, config_files)
    except (SequenceError, CriteriaError, ValueError) as error:
        raise P1RefusalError(f"sequence (D-T4c-5): {error}") from error
    raise_on_stops(fingerprint_stops(files, fingerprint), "D-T4d-2")
    raise_on_stops(reserved_stops(output_root, files), "D-T4d-4")
    kind, number = gate_target(mode)
    confirmed = d9_confirmations(decisions, registry, prey_e_max)
    report = gate_report(steps, kind, number, sorted(confirmed))
    used = check_author_decisions(steps, kind, number, decisions, output_root)
    record = {
        "applied": True,
        "step": _target_label(kind, number),
        "verdict": str(report.verdict),
        "reason": report.reason,
        "notes": list(report.notes),
        "transitions": [f"{t.source} -> {t.target}: {t.verdict}" for t in report.transitions],
        "d9_confirmed": sorted(confirmed),
        "decisions": used,
        "blocks_fingerprinted": len(published_directories(files)),
    }
    return record, files


# ---------------------------------------------------------------- author decisions (T4d, D-T4d-3)

DECISION_REFERENCE = "(P1-18, D-T4d-3)"


def _refuse(message: str) -> P1RefusalError:
    return P1RefusalError(f"{message} {DECISION_REFERENCE}")


def d9_confirmations(
    decisions: Sequence[tuple[Path, AuthorDecision]], registry: Registry, prey_e_max: float
) -> set[int]:
    """Stage-A iterations whose change of n_plants a valid d9_e5 decision confirms (D9).

    The decision is bound to the registered specification by its SHA-256, that specification
    changes ``n_plants_a`` and its motive cites the decision, and the ``plant_energy`` the
    author states as needed really violates E5 with the prey of the configuration.
    """
    specs = {spec.iteration: (path, spec) for path, spec in registry.iterations}
    confirmed: set[int] = set()
    for _, decision in decisions:
        if not isinstance(decision, D9E5Decision):
            continue
        name, number = f"decision {decision.decision}", decision.step.number
        if number not in specs:
            raise _refuse(f"{name}: iteration {number} is not registered")
        path, spec = specs[number]
        if file_sha256(path) != decision.iteration_spec_sha256:
            raise _refuse(f"{name} is not bound to the registered specification {path.name}")
        if spec.changed_parameter != N_PLANTS_A:
            raise _refuse(f"{name}: iteration {number} does not change {N_PLANTS_A}")
        if decision.plant_energy_needed / prey_e_max <= E5_MAX_FRACTION:
            raise _refuse(
                f"{name}: plant_energy {decision.plant_energy_needed} would not violate E5 "
                f"(plant_energy / prey.e_max <= {E5_MAX_FRACTION}), so the E5 route of D9 does "
                "not apply"
            )
        if not cites_decision(spec.motive, decision.decision):
            raise _refuse(f"{name}: the motive of iteration {number} must cite it")
        confirmed.add(number)
    return confirmed


def step_directory(output_root: Path, key: tuple[str, int]) -> Path:
    kind, number = key
    if kind == ITERATION:
        return output_root / CALIBRATION_BLOCK / f"iteration_{number:03d}"
    if kind == ENTRY:
        return output_root / CALIBRATION_BLOCK / ENTRY_LEAF
    return output_root / CONFIRMATION / CONFIRMATION_LEAF


def _row_key(row: Mapping[str, str]) -> str:
    part = row["part"]
    return f"{row['criterion']}{'/' + part if part else ''}@{row['scenario']}"


def _criteria_rows(directory: Path) -> list[dict[str, str]]:
    with (directory / CRITERIA_FILE).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _steps_up_to(steps: Sequence[Step], kind: str, number: int) -> list[Step]:
    upto = list(steps)
    if kind == ENTRY and not (upto and upto[-1].kind == ENTRY):
        upto.append(Step(ENTRY, 0))
    if kind == CONFIRMATION:
        return upto
    for index, step in enumerate(upto):
        if (step.kind, step.number) == (kind, number):
            return upto[: index + 1]
    return upto


def required_decisions(
    steps: Sequence[Step], kind: str, number: int
) -> dict[tuple[str, tuple[str, int]], tuple[Step, str]]:
    """The decisions the transitions up to the step (kind, number) need: what each judges."""
    upto = _steps_up_to(steps, kind, number)
    needed: dict[tuple[str, tuple[str, int]], tuple[Step, str]] = {}
    for previous, step in itertools.pairwise(upto):
        outcome = previous.outcome
        if (
            previous.kind == ITERATION
            and previous.stage in ("B", "C")
            and outcome is not None
            and outcome.requirements_met
            and outcome.failed_b
        ):
            same = step.kind == ITERATION and step.stage == previous.stage
            needed[(B_CRITERIA, (step.kind, step.number))] = (
                previous,
                REPEAT_STAGE if same else NEXT_STAGE,
            )
    if kind == CONFIRMATION and upto and upto[-1].kind == ENTRY:
        needed[(ENTRY_REVIEW, (CONFIRMATION, 0))] = (upto[-1], "")
    return needed


def _check_judged(
    name: str, decision: BCriteriaDecision | EntryReviewDecision, directory: Path, root: Path
) -> list[dict[str, str]]:
    expected = (
        directory.relative_to(root).as_posix(),
        file_sha256(directory / PROVENANCE_FILE),
        file_sha256(directory / CRITERIA_FILE),
    )
    judged = decision.judges
    if (judged.directory, judged.provenance_sha256, judged.criteria_sha256) != expected:
        raise _refuse(f"{name} does not judge {expected[0]} with its current files (SHA-256)")
    return _criteria_rows(directory)


def check_author_decisions(
    steps: Sequence[Step],
    kind: str,
    number: int,
    decisions: Sequence[tuple[Path, AuthorDecision]],
    output_root: Path,
) -> list[dict[str, Any]]:
    """Every decision the steps up to (kind, number) need exists, matches and is unchanged.

    One decision per kind and step; each authorizes a step that is reached and that needs it
    (a d9_e5 decision is checked by ``d9_confirmations``); a step already run must have
    recorded the SHA-256 of its decisions in its provenance, so a decision published or
    modified afterwards is a STOP. Returns the decisions of the step about to run.
    """
    by_key: dict[tuple[str, tuple[str, int]], tuple[Path, AuthorDecision]] = {}
    for path, decision in decisions:
        key = (decision.kind, decision.step.key)
        if key in by_key:
            raise _refuse(f"two {decision.kind} decisions for {decision.step.key}")
        by_key[key] = (path, decision)
    upto = _steps_up_to(steps, kind, number)
    reached = {(s.kind, s.number) for s in upto}
    if kind == CONFIRMATION:
        reached.add((CONFIRMATION, 0))
    needed = required_decisions(steps, kind, number)
    for (decision_kind, step_key), (_, decision) in by_key.items():
        name = f"decision {decision.decision}"
        if step_key not in reached:
            raise _refuse(f"{name} authorizes {step_key}, a step the sequence has not reached")
        if decision_kind != D9_E5 and (decision_kind, step_key) not in needed:
            raise _refuse(f"{name} authorizes nothing: {step_key} needs no {decision_kind}")

    for (decision_kind, step_key), (judged_step, choice) in needed.items():
        if (decision_kind, step_key) not in by_key:
            raise _refuse(
                f"{step_key} needs a {decision_kind} decision of the author on {judged_step.label}"
            )
        _, decision = by_key[(decision_kind, step_key)]
        assert isinstance(decision, BCriteriaDecision | EntryReviewDecision)
        name = f"decision {decision.decision}"
        directory = step_directory(output_root, (judged_step.kind, judged_step.number))
        rows = _check_judged(name, decision, directory, output_root)
        statuses = {_row_key(row): row["status"] for row in rows}
        if isinstance(decision, BCriteriaDecision):
            if decision.choice != choice:
                raise _refuse(f"{name}: choice {decision.choice!r}, the step is {choice!r}")
            assert judged_step.outcome is not None
            expected = set(judged_step.outcome.failed_b)
        else:
            expected = {_row_key(row) for row in rows if row["class"] in ("B", "C")}
        keys = [item.key for item in decision.items]
        if len(keys) != len(set(keys)) or set(keys) != expected:
            raise _refuse(f"{name} must decide exactly on {sorted(expected)}, not {keys}")
        wrong = [item.key for item in decision.items if item.status != statuses[item.key]]
        if wrong:
            raise _refuse(f"{name}: the results of {wrong} are not those of criteria.csv")

    target = (kind, number)
    used = []
    for (_, step_key), (path, decision) in sorted(by_key.items(), key=lambda i: i[1][1].decision):
        entry = {"decision": decision.decision, "sha256": file_sha256(path)}
        if step_key == target:
            used.append(entry)
            continue
        provenance = step_directory(output_root, step_key) / PROVENANCE_FILE
        if provenance.is_file():
            record = _json(provenance)
            gate = record.get("sequence_gate") if isinstance(record, dict) else None
            if not isinstance(gate, dict) or entry not in (gate.get("decisions") or []):
                raise P1RefusalError(
                    f"{STOP_REFERENCE} (D-T4d-3): decision {decision.decision} was published or "
                    f"modified after {step_key} ran"
                )
    return used


# ---------------------------------------------------------------- STOP (T4d, D-T4d-1, D-T4d-2)

P1_BLOCKS = (CALIBRATION_BLOCK, "confirmation", "second_confirmation")
INITIALIZATION_ERROR = f"{InitializationError.__module__}.{InitializationError.__qualname__}"
STOP_REFERENCE = "STOP (P1-18): consult the author; no step runs until an approved procedure"


def attempt_stops(output_root: Path) -> list[str]:
    """D-T4d-1: earlier attempts, anywhere in P1, that stop the calibration.

    An A2 violation (in ``failure.json`` or in the failed provenance alone), an attempt whose
    record cannot rule A2 out, an ``InitializationError`` and a partial directory that was not
    recovered. An infrastructure failure (an interruption, a refused pre-flight) does not stop.
    """
    reasons: list[str] = []
    for block in P1_BLOCKS:
        base = output_root / block
        if not base.is_dir():
            continue
        for path in sorted(p for p in base.rglob("*") if p.is_dir()):
            partial = ".partial-" in path.name
            if not (partial or ".failed-" in path.name):
                continue
            label = path.relative_to(output_root).as_posix()
            record = attempt_record(path)
            if record["a2_violation"] is True:
                reasons.append(f"{label}: an A2 violation (P1-22)")
            elif partial:
                reasons.append(f"{label}: a partial directory; recover it as documented first")
            elif record["a2_violation"] is None:
                reasons.append(f"{label}: no recognizable failure record, A2 cannot be ruled out")
            elif record.get("error_type") == INITIALIZATION_ERROR:
                reasons.append(f"{label}: an InitializationError (the configuration is rejected)")
    return reasons


def published_directories(files: Sequence[Path]) -> list[Path]:
    """The published blocks among the files the sequence read (their ``provenance.json``)."""
    return sorted({path.parent for path in files if path.name == PROVENANCE_FILE})


def _differences(recorded: Any, current: Mapping[str, Any]) -> list[str]:
    if not isinstance(recorded, Mapping):
        return ["no fingerprint"]
    found = []
    for part, values in current.items():
        other = recorded.get(part)
        names = values.keys() if isinstance(values, Mapping) else ()
        found.extend(
            f"{part}.{name}"
            for name in names
            if not isinstance(other, Mapping) or other.get(name) != values[name]
        )
    return found


def fingerprint_stops(files: Sequence[Path], current: Mapping[str, Any]) -> list[str]:
    """D-T4d-2: every published block, and its criteria, come from this code and environment."""
    reasons = []
    for directory in published_directories(files):
        for name in (PROVENANCE_FILE, CRITERIA_PROVENANCE_FILE):
            path = directory / name
            if not path.is_file():
                continue  # a grid has no criteria
            record = _json(path)
            recorded = record.get("fingerprint") if isinstance(record, dict) else None
            different = _differences(recorded, current)
            if different:
                reasons.append(f"{path.as_posix()}: {different} differ from the running ones")
    return reasons


BLOCK_CONTENT = {
    PROVENANCE_FILE,
    "episodes.csv",
    "bootstrap_keys.csv",
    "selection.json",
    CRITERIA_FILE,
    CRITERIA_PROVENANCE_FILE,
}
FAILURE_CONTENT = {"failure.json", PROVENANCE_FILE}


def _reserved_here(output_root: Path) -> Path | None:
    root = reserved_root(output_root)
    return root if root is not None and same_directory(root, output_root) else None


def reserved_content_problems(output_root: Path, registry: Registry) -> list[str]:
    """M-2 (D-T4d-4): what does not belong in the reserved root of the real results.

    Only the marker, the destinations of registered steps (iterations, the phases of registered
    rounds, the entry and the confirmations), their failed or partial attempts and the files of
    a block or of a failure record. Results without a registered specification, and anything
    another command wrote there, are refused. Nothing is checked without a marker.
    """
    root = _reserved_here(output_root)
    if root is None:
        return []
    leaves = {f"{CALIBRATION_BLOCK}/iteration_{s.iteration:03d}" for _, s in registry.iterations}
    leaves |= {
        phase_directory(Path(), s.round_number, phase).as_posix()
        for _, s in registry.rounds
        for phase in PHASE_MODES
    }
    leaves |= {f"{CALIBRATION_BLOCK}/{ENTRY_LEAF}"}
    leaves |= {f"{block}/{CONFIRMATION_LEAF}" for block in P1_BLOCKS[1:]}
    parents = {Path(leaf).parent.as_posix() for leaf in leaves} | set(P1_BLOCKS)

    def attempt_of_leaf(relative: str) -> bool:
        """``<leaf>.failed-…`` or ``<leaf>.partial-…`` of a registered destination."""
        for marker in (".failed-", ".partial-"):
            if marker in relative:
                return relative.split(marker)[0] in leaves
        return False

    problems = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        parent = path.parent.relative_to(root).as_posix()
        if path.is_dir():
            ok = relative in leaves or relative in parents or attempt_of_leaf(relative)
        elif parent == ".":
            ok = path.name == RESERVED_FILE
        elif parent in leaves:
            ok = path.name in BLOCK_CONTENT
        elif attempt_of_leaf(parent):
            ok = ".partial-" in parent or path.name in FAILURE_CONTENT
        else:
            ok = False
        if not ok:
            problems.append(relative)
    return problems


def reserved_stops(output_root: Path, files: Sequence[Path]) -> list[str]:
    """D-T4d-4: every published block ran under the current marker of the reserved root."""
    root = _reserved_here(output_root)
    if root is None:
        return []
    current = file_sha256(root / RESERVED_FILE)
    reasons = []
    for directory in published_directories(files):
        record = _json(directory / PROVENANCE_FILE)
        if not isinstance(record, dict) or record.get("reserved_sha256") != current:
            reasons.append(f"{directory.as_posix()} did not run under the current {RESERVED_FILE}")
    return reasons


def raise_on_stops(reasons: Sequence[str], cause: str) -> None:
    if reasons:
        raise P1RefusalError(f"{STOP_REFERENCE} ({cause}): {list(reasons)}")


def _print(report: SequenceReport) -> None:
    for t in report.transitions:
        typer.echo(f"{t.source} -> {t.target}: {t.verdict} ({t.reason})")
        for note in t.notes:
            typer.echo(f"  note: {note}")
    typer.echo(f"next: {report.next_step}: {report.verdict} ({report.reason})")
    for note in report.notes:
        typer.echo(f"  note: {note}")


def pilot_p1_sequence(
    spec: Annotated[Path, typer.Option(help="P1 specification (p1.yaml).")] = DEFAULT_SPEC,
    output_root: Annotated[
        Path, typer.Option(help="Root of the P1 results.")
    ] = DEFAULT_OUTPUT_ROOT,
) -> None:
    """Verify the P1 calibration sequence against the published results (P1-18).

    The E5 route of D9 is confirmed only by d9_e5 decisions of the author (D-T4d-3), read from
    ``p1_decisions/`` next to the specification; the configuration is ``configs/`` above it.
    """
    files: list[Path] = []
    try:
        stops = attempt_stops(output_root)
        registry = load_registry(spec)
        steps = build_steps(registry, output_root, load_p1_spec(spec, {}), files)
        prey_e_max = load_config(spec.parent.parent, "A").world.prey.e_max
        d9_confirmed = d9_confirmations(load_decisions(spec), registry, prey_e_max)
    except (SequenceError, CriteriaError, P1RefusalError, ValueError) as error:
        typer.echo(f"refused: {error}", err=True)
        raise typer.Exit(code=EXIT_NOT_ALLOWED) from error
    stops += fingerprint_stops(files, p1_fingerprint(Path.cwd() / "uv.lock"))
    if stops:  # D-T4d-1 and D-T4d-2: the same STOP as the gate of pilot p1
        typer.echo(f"next: -: {Verdict.STOP} ({STOP_REFERENCE})")
        for reason in stops:
            typer.echo(f"  stop: {reason}")
        raise typer.Exit(code=EXIT_NOT_ALLOWED)
    report = verify_sequence(steps, d9_confirmed=sorted(d9_confirmed))
    _print(report)
    if report.verdict is not Verdict.ALLOWED:
        raise typer.Exit(code=EXIT_NOT_ALLOWED)
