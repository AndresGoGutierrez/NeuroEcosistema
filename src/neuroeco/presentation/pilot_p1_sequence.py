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

import dataclasses
import json
from collections.abc import Sequence
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
    ROUND,
    Outcome,
    RoundResult,
    SequenceReport,
    Step,
    Verdict,
    verify_sequence,
)
from neuroeco.application.calibration import GRID_PHASES, P1Spec, RoundSpec
from neuroeco.infrastructure.config_loader import load_p1_spec
from neuroeco.infrastructure.provenance import file_sha256
from neuroeco.presentation.pilot_p1 import (
    CALIBRATION_BLOCK,
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
) -> RoundResult | None:
    """Result of a round from its published phases (T4c); None until both grids exist.

    Each grid is verified as ``pilot p1`` verifies a prerequisite (completed, intact, the
    planned rows, the registered round) and its winner is recomputed from its rows (D-T4c-2).
    When a value changed, the A_rev outcome comes from its block and matching criteria.
    ``files``, when given, receives every file read.
    """
    read = files if files is not None else []
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
            },
        )
        reevaluation = block_outcome(directory, "A_rev")
        read.extend(evaluated_files(directory, "A_rev"))
    return RoundResult(changed, dataclasses.asdict(final), reevaluation)


def build_steps(
    registry: Registry, output_root: Path, p1_spec: P1Spec, files: list[Path] | None = None
) -> list[Step]:
    """Registered iterations, each followed by its rounds, then the entry if it was published.

    ``files``, when given, receives every published file read.
    """
    read = files if files is not None else []
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
                round_result=round_result(registry, r, output_root, p1_spec, read),
            )
            for _, r in rounds
            if r.after_iteration == spec.iteration
        )
    entry = calibration / ENTRY_LEAF
    if entry.exists():
        last = steps[-1].number if steps and steps[-1].kind == ITERATION else None
        _check_provenance(entry, {"mode": "entry", "values_iteration": last})
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
            hint = "; the E5 route of D9 needs --d9-confirmed, documented in the motive"
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
    d9_confirmed: Sequence[int] = (),
) -> tuple[dict[str, Any], list[Path]]:
    """Pre-flight of ``pilot p1`` (D-T4c-5): the record of the verification and the files read.

    The sequence is built from the published results exactly as ``pilot p1-sequence`` builds it
    (results of their registered specifications, criteria recomputed byte for byte); any result
    that cannot be used, or a step that the sequence does not allow, refuses the block.
    """
    files: list[Path] = []
    try:
        steps = build_steps(registry, output_root, p1_spec, files)
    except (SequenceError, CriteriaError, ValueError) as error:
        raise P1RefusalError(f"sequence (D-T4c-5): {error}") from error
    kind, number = gate_target(mode)
    report = gate_report(steps, kind, number, d9_confirmed)
    record = {
        "applied": True,
        "step": _target_label(kind, number),
        "verdict": str(report.verdict),
        "reason": report.reason,
        "notes": list(report.notes),
        "transitions": [f"{t.source} -> {t.target}: {t.verdict}" for t in report.transitions],
        "d9_confirmed": sorted(set(d9_confirmed)),
    }
    return record, files


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
    d9_confirmed: Annotated[
        list[int] | None,
        typer.Option(
            help="Stage-A iteration whose n_plants change the author confirmed through the E5 "
            "route of D9 (documented in its motive); repeatable.",
        ),
    ] = None,
) -> None:
    """Verify the P1 calibration sequence against the published results (P1-18)."""
    try:
        steps = build_steps(load_registry(spec), output_root, load_p1_spec(spec, {}))
    except (SequenceError, CriteriaError, P1RefusalError, ValueError) as error:
        typer.echo(f"refused: {error}", err=True)
        raise typer.Exit(code=EXIT_NOT_ALLOWED) from error
    report = verify_sequence(steps, d9_confirmed=d9_confirmed or ())
    _print(report)
    if report.verdict is not Verdict.ALLOWED:
        raise typer.Exit(code=EXIT_NOT_ALLOWED)
