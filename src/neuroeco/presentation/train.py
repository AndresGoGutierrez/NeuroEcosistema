"""``neuroeco train``: one training run of one species against the rule-based opponent (F6)."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Annotated

import numpy as np
import typer

from neuroeco.application.training import train
from neuroeco.bootstrap import DEFAULT_CONFIG_DIR
from neuroeco.infrastructure.config_loader import ConfigError, load_config, load_training_spec
from neuroeco.infrastructure.executors import (
    ProcessExecutor,
    SequentialExecutor,
    limit_blas_threads,
    single_threaded,
    thread_pools,
)
from neuroeco.infrastructure.provenance import collect_provenance
from neuroeco.infrastructure.run_store import RunStore

REFERENCE = Path("results/pilots/f5_i2/reference_observations.npz")


def train_command(
    spec_path: Annotated[Path, typer.Option("--spec", help="Training specification (YAML).")],
    workers: Annotated[int, typer.Option(min=0, help="Worker processes; 0 = sequential.")] = 0,
    output_root: Annotated[Path, typer.Option(help="Directory of the runs.")] = Path(
        "results/runs"
    ),
    config_dir: Annotated[Path, typer.Option(help="Configuration directory.")] = (
        DEFAULT_CONFIG_DIR
    ),
) -> None:
    """Train one network with the genetic algorithm (ADR-027) and store its run."""
    limit_blas_threads()
    try:
        spec = load_training_spec(spec_path)
        config = load_config(config_dir, spec.scenario)
        store = RunStore(output_root, spec)
    except (ConfigError, OSError, ValueError) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=1) from error
    if not single_threaded():
        typer.echo("error: a BLAS thread pool has more than one thread (ADR-016)", err=True)
        raise typer.Exit(code=1)

    reference = None
    if REFERENCE.exists():
        with np.load(REFERENCE) as data:
            reference = np.array(data[spec.species])
    store.write_manifest(
        {
            "provenance": collect_provenance(sys.argv, Path.cwd(), config.config_hash),
            "scenario_config_hash": config.config_hash,
            "workers": workers,
            "thread_pools": thread_pools(),
            "reference_set": str(REFERENCE) if reference is not None else None,
        }
    )
    started = time.perf_counter()

    def progress(record) -> None:
        store.add_generation(record)
        s = record.summary
        val = "" if record.f_val is None else f"  F_val {record.f_val:.4f}"
        typer.echo(
            f"gen {s.generation:4d}  max {s.fitness_max:.4f}  mean {s.fitness_mean:.4f}{val}"
        )

    if workers == 0:
        result = train(spec, config, SequentialExecutor(), reference, progress)
    else:
        with ProcessExecutor(workers) as executor:
            pools = executor.worker_thread_pools()
            if not all(p["num_threads"] == 1 for worker in pools for p in worker):
                typer.echo("error: a worker has a multi-threaded BLAS pool (ADR-016)", err=True)
                raise typer.Exit(code=1)
            result = train(spec, config, executor, reference, progress)
    store.finish(result)
    seconds = time.perf_counter() - started
    typer.echo(
        f"{store.directory}: selected generation {result.selected.generation} "
        f"(F_val {result.selected.f_val:.4f}); {seconds:.1f} s"
    )
