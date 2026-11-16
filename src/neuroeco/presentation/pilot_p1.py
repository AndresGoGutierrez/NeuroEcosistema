"""Command ``neuroeco pilot p1``: one block of the P1 calibration (ADR-020, ADR-033; F4 T3).

Modes (exactly one per invocation, T3-1):

- ``--iteration iterations/NNN.yaml``: calibration iteration; stage A runs A, stage B runs A and
  B, stage C runs A and C (P1-18); bootstrap ``run`` = NNN.
- ``--entry-evaluation --values-from iterations/NNN.yaml``: the 35 conditions of the calibration
  block with the final values (P1-18, state E); ``run`` = 0.
- ``--confirmation`` / ``--second-confirmation`` with ``--values-from`` and
  ``--author-authorized``: the 35 conditions of the confirmation block (P1-21); ``run`` = 0.

Before any episode the command validates, in this order: the P1 specification; every registered
iteration and round specification and their static sequence; the resolved configurations and
state K (A1); the seed groups of the planned episodes; the author's authorization for
confirmation blocks; that the destination does not exist; and that the git working tree is
clean, as recorded by the provenance captured before anything is written (P1-19). There is no
option to bypass these checks.

Results are assembled in ``<destination>.partial-<id>`` and published in one rename when the
block is complete (T3-3). Any error after the destination is known leaves a separate
``<destination>.failed-<UTC>-<id>`` directory with ``failure.json`` (and ``provenance.json`` when
it was captured) and no CSV file (T3-4). Rule-tuning rounds are not run here (task T4c).
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import sys
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

import typer

from neuroeco.application.calibration import (
    BOOTSTRAP_COLUMNS,
    CONFIRMATION_BLOCKS,
    CONFIRMATION_RUN,
    CONFIRMATION_STAGE,
    ENTRY_EVALUATION_RUN,
    ENTRY_STAGE,
    EPISODE_COLUMNS,
    SCENARIOS,
    A2ViolationError,
    CandidateValues,
    IterationSpec,
    P1Spec,
    RoundSpec,
    admissibility,
    bootstrap_rows,
    check_block_groups,
    check_calibration_sequence,
    episode_row,
    iter_block,
    plan_block,
    scenario_overrides,
    stage_scenarios,
)
from neuroeco.application.configs import ResolvedConfig
from neuroeco.bootstrap import DEFAULT_CONFIG_DIR, EXPLORATORY_SEED_GROUP, build_policy
from neuroeco.infrastructure.config_loader import (
    load_config,
    load_iteration_spec,
    load_p0_spec,
    load_p1_spec,
    load_round_spec,
)
from neuroeco.infrastructure.provenance import (
    collect_provenance,
    dependency_versions,
    file_sha256,
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
CONFIRMATION_LEAF = "evaluation"
DEPENDENCIES = ("numpy", "scipy", "pandas", "pyyaml", "typer", "threadpoolctl", "pygame-ce")
EXIT_FAILURE = 1
EXIT_A2_VIOLATION = 2
EPISODES_FILE = "episodes.csv"
BOOTSTRAP_FILE = "bootstrap_keys.csv"
PROVENANCE_FILE = "provenance.json"
FAILURE_FILE = "failure.json"


class P1RefusalError(ValueError):
    """A pre-flight check refused to run the block; no episode was executed."""


@dataclass(frozen=True)
class Mode:
    """What one invocation runs and where its results go."""

    name: str  # iteration | entry | confirmation | second_confirmation
    block: str
    stage: str
    iteration: int  # 0 when the mode is not an iteration
    run: int  # bootstrap ``run`` field (P1-20)
    scenarios: tuple[str, ...]
    values: CandidateValues
    source: Path  # the iteration specification that provides the values
    leaf: str

    def destination(self, output_root: Path) -> Path:
        return output_root / self.block / self.leaf


@dataclass(frozen=True)
class Registry:
    """Pre-registered iteration and round specifications (P1-19)."""

    iterations: tuple[tuple[Path, IterationSpec], ...]
    rounds: tuple[tuple[Path, RoundSpec], ...]


def select_mode(
    *,
    iteration: Path | None,
    entry_evaluation: bool,
    confirmation: bool,
    second_confirmation: bool,
    values_from: Path | None,
    author_authorized: bool,
) -> Mode:
    """Exactly one mode; the values always come from a pre-registered iteration file."""
    chosen = [
        name
        for name, selected in (
            ("iteration", iteration is not None),
            ("entry", entry_evaluation),
            ("confirmation", confirmation),
            ("second_confirmation", second_confirmation),
        )
        if selected
    ]
    if len(chosen) != 1:
        raise P1RefusalError(
            "choose exactly one of --iteration, --entry-evaluation, --confirmation and "
            "--second-confirmation"
        )
    name = chosen[0]
    # A missing authorization is checked in the pre-flight, once the destination is known, so
    # that the refused attempt is recorded; a superfluous one is a usage error.
    if author_authorized and name not in CONFIRMATION_BLOCKS:
        raise P1RefusalError("--author-authorized only applies to confirmation blocks")
    if name == "iteration":
        if values_from is not None:
            raise P1RefusalError("--values-from is not used with --iteration")
        assert iteration is not None
        spec = load_iteration_spec(iteration)
        return Mode(
            name=name,
            block="calibration",
            stage=spec.stage,
            iteration=spec.iteration,
            run=spec.iteration,
            scenarios=stage_scenarios(spec.stage),
            values=spec.values,
            source=iteration,
            leaf=f"iteration_{spec.iteration:03d}",
        )
    if values_from is None:
        raise P1RefusalError(f"--values-from is required with the {name} mode")
    spec = load_iteration_spec(values_from)
    if name == "entry":
        block, stage, run, leaf = "calibration", ENTRY_STAGE, ENTRY_EVALUATION_RUN, "entry"
    else:
        block, stage, run, leaf = name, CONFIRMATION_STAGE, CONFIRMATION_RUN, CONFIRMATION_LEAF
    return Mode(name, block, stage, 0, run, SCENARIOS, spec.values, values_from, leaf)


def load_registry(spec_path: Path) -> Registry:
    """Every iteration and round file registered next to ``p1.yaml``, in numeric order."""
    base = spec_path.parent / REGISTRY_DIRECTORY
    iterations = []
    for path in sorted((base / "iterations").glob("*.yaml")):
        spec = load_iteration_spec(path)
        if path.stem != f"{spec.iteration:03d}":
            raise P1RefusalError(f"{path}: iteration {spec.iteration} must be in a file NNN.yaml")
        iterations.append((path, spec))
    rounds = []
    for path in sorted((base / "rounds").glob("*.yaml")):
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


@dataclass
class Preflight:
    spec: P1Spec
    registry: Registry
    configs: dict[tuple[str, tuple[str, ...]], ResolvedConfig]
    tasks: tuple
    admissibility: Any
    project_seed: int


def preflight(
    mode: Mode, spec_path: Path, config_dir: Path, author_authorized: bool, destination: Path
) -> Preflight:
    """Validations that need no result, in the order approved by the author (T3)."""
    p0 = load_p0_spec(config_dir / "pilots" / "p0.yaml")
    spec = load_p1_spec(spec_path, {"exploratory": EXPLORATORY_SEED_GROUP, "P0": p0.seed_group})

    registry = load_registry(spec_path)
    current = _registered(mode.source, registry)
    if mode.name != "iteration":
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

    candidate = {
        s: load_config(config_dir, s, scenario_overrides(mode.values, s)) for s in SCENARIOS
    }
    state_k = admissibility({s: config.world for s, config in candidate.items()})
    if not state_k.a1:
        failed = [f"{s}:{c.constraint_id}" for s, c in state_k.checks if not c.satisfied]
        raise P1RefusalError(
            f"state K: A1 does not hold ({failed + list(state_k.design_problems)}); "
            "the candidate is rejected without running episodes (P1-18)"
        )

    tasks = plan_block(spec, mode.block, mode.values, scenarios=mode.scenarios)
    check_block_groups(tasks, spec, mode.block)
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
    return Preflight(spec, registry, configs, tasks, state_k, seeds.pop())


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
        "bootstrap_run": mode.run,
        "scenarios": list(mode.scenarios),
        "episodes_per_condition": plan.spec.blocks.named()[mode.block].episodes,
        "episodes_planned": len(plan.tasks),
        "author_authorized": author_authorized,
        "project_seed": str(plan.project_seed),
        "values": dataclasses.asdict(mode.values),
        "values_source": {"path": mode.source.as_posix(), "sha256": file_sha256(mode.source)},
        "p1_spec": {"path": spec_path.as_posix(), "sha256": file_sha256(spec_path)},
        "registered_iterations": [
            {"path": p.as_posix(), "sha256": file_sha256(p)} for p, _ in plan.registry.iterations
        ],
        "registered_rounds": [
            {"path": p.as_posix(), "sha256": file_sha256(p)} for p, _ in plan.registry.rounds
        ],
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
    }


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def failure_document(
    error: BaseException, phase: str, destination: Path, completed: int
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
        "error_type": f"{type(error).__module__}.{type(error).__qualname__}",
        "message": str(error),
        "notes": list(getattr(error, "__notes__", [])),
        "episodes_completed": completed,
        "a2_violation": a2,
    }


def record_failure(
    destination: Path,
    partial: Path | None,
    provenance: dict[str, Any] | None,
    failure: dict[str, Any],
) -> Path:
    """Keep the failure as its own artifact; CSV files of an unfinished block are discarded."""
    if partial is not None and partial.exists():
        for leftover in partial.glob("*.csv"):
            leftover.unlink()
        directory = reserve_failure_directory(destination, _now(), source=partial)
    else:
        directory = reserve_failure_directory(destination, _now())
    if provenance is not None:
        replace_json(directory / PROVENANCE_FILE, {**provenance, "status": "failed"})
    replace_json(directory / FAILURE_FILE, failure)
    return directory


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
) -> None:
    """Pilot P1: run one calibration iteration, the entry evaluation or a confirmation."""
    try:
        mode = select_mode(
            iteration=iteration,
            entry_evaluation=entry_evaluation,
            confirmation=confirmation,
            second_confirmation=second_confirmation,
            values_from=values_from,
            author_authorized=author_authorized,
        )
    except (ValueError, OSError) as error:  # the destination is unknown: nothing to record
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=EXIT_FAILURE) from error

    destination = mode.destination(output_root)
    phase, partial, provenance, completed = "preflight", None, None, 0
    try:
        plan = preflight(mode, spec_path, config_dir, author_authorized, destination)
        # Provenance is captured BEFORE anything is written (P1-19): git_dirty describes the
        # code that runs, not the files this command is about to create.
        first_hash = next(iter(plan.configs.values())).config_hash  # every hash is listed too
        base = collect_provenance(sys.argv, Path.cwd(), first_hash)
        provenance = provenance_document(mode, plan, base, spec_path, author_authorized)
        if base.get("git_dirty") is not False:
            raise P1RefusalError(
                f"the git working tree must be clean (P1-19); git_dirty = {base.get('git_dirty')!r}"
            )

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
                        values=mode.values,
                    )
                )
                completed += 1

        phase = "writing"
        block_spec = plan.spec.blocks.named()[mode.block]
        write_csv(partial / EPISODES_FILE, EPISODE_COLUMNS, rows)
        write_csv(
            partial / BOOTSTRAP_FILE,
            BOOTSTRAP_COLUMNS,
            bootstrap_rows(block_spec, mode.run, mode.scenarios, plan.project_seed),
        )
        provenance = {
            **provenance,
            "status": "completed",
            "finished_utc": _now().isoformat(timespec="seconds"),
            "duration_seconds": round(time.perf_counter() - started, 3),
            "episodes_written": len(rows),
        }
        replace_json(partial / PROVENANCE_FILE, provenance)
        publish_directory(partial, destination)
    except A2ViolationError as error:
        directory = record_failure(
            destination, partial, provenance, failure_document(error, phase, destination, completed)
        )
        typer.echo(f"A2 violation, block stopped: {error}", err=True)
        typer.echo(f"failure recorded in {directory}", err=True)
        raise typer.Exit(code=EXIT_A2_VIOLATION) from error
    except Exception as error:
        directory = record_failure(
            destination, partial, provenance, failure_document(error, phase, destination, completed)
        )
        typer.echo(f"error ({phase}): {error}", err=True)
        typer.echo(f"failure recorded in {directory}", err=True)
        raise typer.Exit(code=EXIT_FAILURE) from error
    except KeyboardInterrupt as error:
        record_failure(
            destination, partial, provenance, failure_document(error, phase, destination, completed)
        )
        raise

    typer.echo(f"P1 {mode.name}: {len(rows)} episodes written to {destination}")
