"""``neuroeco experiment train | evaluate`` (F8, protocol of F7).

``train`` runs the formal runs of the protocol, resumable: complete runs are kept, an incomplete
one is renamed to ``<name>.incomplete-<UTC>`` and trained again. With ``--stop-at`` it starts a
run only if the longest duration seen so far for its configuration (or for any, before the
first) fits before that time, so the machine can be switched off without losing work.

``evaluate`` evaluates every complete run on the TEST seeds (ADR-017, ADR-019) and writes
``test_episodes.csv``; it never overwrites an existing evaluation.
"""

from __future__ import annotations

import csv
import datetime as dt
import sys
import time
from pathlib import Path
from typing import Annotated

import numpy as np
import typer

from neuroeco.application.experiment import (
    CONFIGURATIONS,
    OPPONENTS,
    PolicySpec,
    formal_specs,
    opponent_spec,
    run_name,
    test_episode,
    test_tasks,
)
from neuroeco.application.training import train
from neuroeco.bootstrap import DEFAULT_CONFIG_DIR
from neuroeco.infrastructure.config_loader import load_config, load_protocol
from neuroeco.infrastructure.executors import (
    ProcessExecutor,
    SequentialExecutor,
    limit_blas_threads,
    thread_pools,
)
from neuroeco.infrastructure.model_store import load_model
from neuroeco.infrastructure.provenance import collect_provenance
from neuroeco.infrastructure.run_store import RunStore

PROTOCOL = DEFAULT_CONFIG_DIR / "protocol.yaml"
ROOT = Path("results/experiments/f8")
REFERENCE = Path("results/pilots/f5_i2/reference_observations.npz")
DURATIONS = "durations.csv"
TEST_COLUMNS = (
    "run",
    "architecture",
    "scenario",
    "species",
    "model",
    "opponent",
    "opponent_run",
    "item",
    "survival_steps",
    "survival_denominator",
    "captures",
    "capture_denominator",
    "steps",
)


def _durations(root: Path) -> dict[str, list[float]]:
    path = root / DURATIONS
    seen: dict[str, list[float]] = {}
    if path.exists():
        with path.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                seen.setdefault(row["configuration"], []).append(float(row["seconds"]))
    return seen


def _record_duration(root: Path, configuration: str, name: str, seconds: float) -> None:
    path = root / DURATIONS
    new = not path.exists()
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        if new:
            writer.writerow(["configuration", "run", "seconds"])
        writer.writerow([configuration, name, f"{seconds:.1f}"])


def experiment_train(
    workers: Annotated[int, typer.Option(min=0, help="Worker processes; 0 = sequential.")] = 16,
    stop_at: Annotated[
        str | None,
        typer.Option(help="Local time YYYY-MM-DDTHH:MM; no run starts that would end later."),
    ] = None,
    protocol_path: Annotated[Path, typer.Option("--protocol")] = PROTOCOL,
    root: Annotated[Path, typer.Option(help="Campaign directory.")] = ROOT,
    config_dir: Annotated[Path, typer.Option(help="Configuration directory.")] = DEFAULT_CONFIG_DIR,
) -> None:
    """Train the formal runs (resumable)."""
    limit_blas_threads()
    protocol = load_protocol(protocol_path)
    deadline = dt.datetime.fromisoformat(stop_at) if stop_at else None
    runs_root = root / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    reference = None
    if REFERENCE.exists():
        with np.load(REFERENCE) as data:
            reference = {s: np.array(data[s]) for s in ("prey", "predator")}
    configs = {s: load_config(config_dir, s) for s in "ABC"}

    def campaign(executor) -> None:
        for spec in formal_specs(protocol):
            directory = runs_root / spec.name
            if (directory / "summary.json").exists():
                continue
            configuration = f"{spec.architecture}_{spec.scenario}"
            seen = _durations(root)
            estimate = max(
                seen.get(configuration) or [s for v in seen.values() for s in v] or [0.0]
            )
            if deadline and dt.datetime.now() + dt.timedelta(seconds=1.1 * estimate) > deadline:
                typer.echo(
                    f"stop: {spec.name} (~{estimate / 60:.0f} min) would end after {stop_at}"
                )
                return
            if directory.exists():
                stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
                directory.rename(directory.with_name(f"{spec.name}.incomplete-{stamp}"))
            config = configs[spec.scenario]
            store = RunStore(runs_root, spec)
            store.write_manifest(
                {
                    "provenance": collect_provenance(sys.argv, Path.cwd(), config.config_hash),
                    "workers": workers,
                    "thread_pools": thread_pools(),
                    "protocol": str(protocol_path),
                }
            )
            started = time.perf_counter()
            result = train(
                spec,
                config,
                executor,
                None if reference is None else reference[spec.species],
                store.add_generation,
            )
            store.finish(result)
            seconds = time.perf_counter() - started
            _record_duration(root, configuration, spec.name, seconds)
            typer.echo(
                f"{spec.name}: F_val {result.selected.f_val:.4f} "
                f"(gen {result.selected.generation}), {seconds / 60:.1f} min"
            )
        typer.echo("all formal runs are complete")

    if workers == 0:
        campaign(SequentialExecutor())
    else:
        with ProcessExecutor(workers) as executor:
            campaign(executor)


def experiment_evaluate(
    workers: Annotated[int, typer.Option(min=0, help="Worker processes; 0 = sequential.")] = 16,
    protocol_path: Annotated[Path, typer.Option("--protocol")] = PROTOCOL,
    root: Annotated[Path, typer.Option(help="Campaign directory.")] = ROOT,
    config_dir: Annotated[Path, typer.Option(help="Configuration directory.")] = DEFAULT_CONFIG_DIR,
    output: Annotated[str, typer.Option(help="File name of the evaluation.")] = "test_episodes.csv",
) -> None:
    """Evaluate every complete formal run on the TEST seeds (M0-M4 and the references)."""
    limit_blas_threads()
    protocol = load_protocol(protocol_path)
    target = root / output
    if target.exists():
        typer.echo(f"error: {target} exists; evaluations are never overwritten", err=True)
        raise typer.Exit(code=1)
    configs = {s: load_config(config_dir, s) for s in "ABC"}
    t = protocol.test_episodes

    models: dict[tuple[str, str, int], dict[str, PolicySpec]] = {}
    for architecture, scenario in CONFIGURATIONS:
        for run in range(protocol.runs):
            directory = root / "runs" / run_name(architecture, scenario, run)
            if not (directory / "summary.json").exists():
                continue
            before, _ = load_model(directory / "checkpoints" / "gen_0000.npz")
            after, _ = load_model(directory / "selected.npz")
            models[(architecture, scenario, run)] = {
                "before": PolicySpec("model", architecture=architecture, genome=before.genome),
                "after": PolicySpec("model", architecture=architecture, genome=after.genome),
            }

    jobs: list[tuple[dict, list]] = []

    def add(meta: dict, species: str, scenario: str, learner, opponent) -> None:
        jobs.append((meta, test_tasks(configs[scenario], species, learner, opponent, t)))

    for (architecture, scenario, run), specs in models.items():
        species = architecture.split("_")[0]
        base = {"run": run_name(architecture, scenario, run), "architecture": architecture}
        common = {**base, "scenario": scenario, "species": species, "opponent_run": ""}
        add(
            {**common, "model": "before", "opponent": "M0"},
            species,
            scenario,
            specs["before"],
            opponent_spec("M0"),
        )
        for opponent in OPPONENTS:
            add(
                {**common, "model": "after", "opponent": opponent},
                species,
                scenario,
                specs["after"],
                opponent_spec(opponent),
            )
    # references: rules and random learners against M0-M3, per species and scenario
    for scenario in "ABC":
        for species in ("prey", "predator"):
            for kind in ("rules", "random"):
                for opponent in OPPONENTS:
                    meta = {
                        "run": kind,
                        "architecture": kind,
                        "scenario": scenario,
                        "species": species,
                        "model": "reference",
                        "opponent": opponent,
                        "opponent_run": "",
                    }
                    add(meta, species, scenario, PolicySpec(kind), opponent_spec(opponent))
    # M4: cross-play of the base networks in each scenario; the rules learner as reference
    for scenario in "ABC":
        for species, other in (("prey", "predator"), ("predator", "prey")):
            mine = [
                (k, v) for k, v in models.items() if k[0] == f"{species}_base" and k[1] == scenario
            ]
            theirs = [
                (k, v) for k, v in models.items() if k[0] == f"{other}_base" and k[1] == scenario
            ]
            for (_, _, other_run), other_specs in theirs:
                opponent = other_specs["after"]
                label = run_name(f"{other}_base", scenario, other_run)
                for (architecture, _, run), specs in mine:
                    meta = {
                        "run": run_name(architecture, scenario, run),
                        "architecture": architecture,
                        "scenario": scenario,
                        "species": species,
                        "model": "after",
                        "opponent": "M4",
                        "opponent_run": label,
                    }
                    add(meta, species, scenario, specs["after"], opponent)
                meta = {
                    "run": "rules",
                    "architecture": "rules",
                    "scenario": scenario,
                    "species": species,
                    "model": "reference",
                    "opponent": "M4",
                    "opponent_run": label,
                }
                add(meta, species, scenario, PolicySpec("rules"), opponent)

    tasks = [task for _, batch in jobs for task in batch]
    typer.echo(f"{len(models)} runs, {len(tasks)} test episodes")
    if workers == 0:
        values = SequentialExecutor().map(test_episode, tasks)
    else:
        with ProcessExecutor(workers) as executor:
            values = executor.map(test_episode, tasks)
    rows = []
    position = 0
    for meta, batch in jobs:
        for task in batch:
            rows.append({**meta, "item": task.item, **values[position]})
            position += 1
    root.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TEST_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    typer.echo(f"written {target}")


def experiment_analyze(
    protocol_path: Annotated[Path, typer.Option("--protocol")] = PROTOCOL,
    root: Annotated[Path, typer.Option(help="Campaign directory.")] = ROOT,
    decision: Annotated[Path, typer.Option(help="P2 decision (Delta, theta).")] = Path(
        "results/pilots/p2/p2_decision.json"
    ),
) -> None:
    """C1, C2, C3 and generalization tables and figures from test_episodes.csv (ADR-017)."""
    import matplotlib.pyplot as plt

    from neuroeco.analysis.experiments import analyze
    from neuroeco.analysis.report import report_documents

    protocol = load_protocol(protocol_path)
    report = analyze(root, decision, protocol.runs)
    output = root / "analysis"
    output.mkdir(parents=True, exist_ok=True)
    texts, figures = report_documents(report, root / "runs")
    for name, text in texts.items():
        (output / name).write_text(text, encoding="utf-8")
    for name, figure in figures.items():
        figure.savefig(output / name, dpi=150)
        plt.close(figure)
    typer.echo(f"written {root / 'analysis'}")
