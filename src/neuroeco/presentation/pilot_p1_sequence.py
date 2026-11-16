"""``neuroeco pilot p1-sequence``: verify the P1 calibration sequence (F4 T4b, D-T4b-1).

Read-only and independent of ``pilot p1`` (author decision D-T4b-1): it is run before the author
authorizes each iteration; before T5 it must be integrated into the pre-flight of ``pilot p1``.

For every registered iteration with a published result it checks that the result belongs to
that registered specification (mode, stage, values and SHA-256 of the specification file) and
that its ``criteria.csv`` is exactly the evaluation of the current code (recomputed with
``analysis.calibration``, byte for byte, with ``criteria_provenance.json`` matching the input
files). The outcomes then go through ``analysis.sequence`` (P1-18).
"""

from __future__ import annotations

import dataclasses
import json
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
    registry: Registry, round_spec: RoundSpec, output_root: Path, p1_spec: P1Spec
) -> RoundResult | None:
    """Result of a round from its published phases (T4c); None until both grids exist.

    Each grid is verified as ``pilot p1`` verifies a prerequisite (completed, intact, the
    planned rows, the registered round) and its winner is recomputed from its rows (D-T4c-2).
    When a value changed, the A_rev outcome comes from its block and matching criteria.
    """
    number = round_spec.round_number
    grids = [phase_directory(output_root, number, phase) for phase in GRID_PHASES]
    if not all(directory.exists() for directory in grids):
        return None
    winners: dict[str, float] = {}
    for phase, directory in zip(GRID_PHASES, grids, strict=True):
        values = dataclasses.replace(round_spec.values, **winners)
        data, _ = verify_result(
            directory,
            {
                "mode": PHASE_MODES[phase],
                "round": number,
                "values": dataclasses.asdict(values),
                "values_source.sha256": registry.round_sha256(number),
            },
            p1_spec,
        )
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
    return RoundResult(changed, dataclasses.asdict(final), reevaluation)


def build_steps(registry: Registry, output_root: Path, p1_spec: P1Spec) -> list[Step]:
    """Registered iterations, each followed by its rounds, then the entry if it was published."""
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
                round_result=round_result(registry, r, output_root, p1_spec),
            )
            for _, r in rounds
            if r.after_iteration == spec.iteration
        )
    entry = calibration / ENTRY_LEAF
    if entry.exists():
        last = steps[-1].number if steps and steps[-1].kind == ITERATION else None
        _check_provenance(entry, {"mode": "entry", "values_iteration": last})
        steps.append(Step(ENTRY, 0, outcome=block_outcome(entry, "entry")))
    return steps


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
