"""``neuroeco pilot p2`` and ``pilot p2-decide`` (F6, ADR-035).

``p2`` runs the P2/P2b grid (four networks x three sigmas x two runs, scenario A) and can be
resumed: complete runs (with ``summary.json``) are kept, an incomplete one is renamed to
``<name>.incomplete-<UTC>`` and run again. ``p2-decide`` applies the rules of ADR-035 to the
stored runs and writes ``p2_decision.json``.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Annotated, Any

import numpy as np
import typer

from neuroeco.application.training import TrainingSpec, train
from neuroeco.bootstrap import DEFAULT_CONFIG_DIR
from neuroeco.infrastructure.config_loader import load_config
from neuroeco.infrastructure.executors import (
    ProcessExecutor,
    SequentialExecutor,
    limit_blas_threads,
    thread_pools,
)
from neuroeco.infrastructure.provenance import collect_provenance
from neuroeco.infrastructure.run_store import RunStore
from neuroeco.infrastructure.storage import write_json

NETWORKS = ("prey_base", "predator_base", "prey_compact", "predator_compact")
SIGMAS = (0.02, 0.05, 0.10)
RUNS = 2
PILOT_GENERATIONS = 60
FIXED = {"population": 40, "elite": 2, "tournament": 3, "episodes": 4, "validation_episodes": 16}
VALIDATION_INTERVAL = 5
FIRST_SEED_GROUP = 40
REFERENCE = Path("results/pilots/f5_i2/reference_observations.npz")


def p2_specs() -> list[TrainingSpec]:
    specs = []
    for n, network in enumerate(NETWORKS):
        for s, sigma in enumerate(SIGMAS):
            for run in range(RUNS):
                specs.append(
                    TrainingSpec(
                        name=f"p2_{network}_s{sigma:.2f}_r{run}",
                        species=network.split("_")[0],
                        architecture=network,
                        scenario="A",
                        seed_group=FIRST_SEED_GROUP + n * len(SIGMAS) + s,
                        run=run,
                        sigma=sigma,
                        generations=PILOT_GENERATIONS,
                        validation_interval=VALIDATION_INTERVAL,
                        **FIXED,
                    )
                )
    return specs


def pilot_p2(
    workers: Annotated[int, typer.Option(min=0, help="Worker processes; 0 = sequential.")] = 16,
    output_root: Annotated[Path, typer.Option(help="P2 directory.")] = Path("results/pilots/p2"),
    config_dir: Annotated[Path, typer.Option(help="Configuration directory.")] = (
        DEFAULT_CONFIG_DIR
    ),
    only: Annotated[list[str] | None, typer.Option(help="Run only these names (testing).")] = None,
) -> None:
    """Run the P2/P2b grid of ADR-035 (resumable)."""
    limit_blas_threads()
    config = load_config(config_dir, "A")
    runs_root = output_root / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    reference = None
    if REFERENCE.exists():
        with np.load(REFERENCE) as data:
            reference = {s: np.array(data[s]) for s in ("prey", "predator")}
    specs = [s for s in p2_specs() if not only or s.name in only]

    def run_all(executor) -> None:
        for spec in specs:
            directory = runs_root / spec.name
            if (directory / "summary.json").exists():
                typer.echo(f"{spec.name}: complete, kept")
                continue
            if directory.exists():
                stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
                directory.rename(directory.with_name(f"{spec.name}.incomplete-{stamp}"))
            store = RunStore(runs_root, spec)
            store.write_manifest(
                {
                    "provenance": collect_provenance(sys.argv, Path.cwd(), config.config_hash),
                    "workers": workers,
                    "thread_pools": thread_pools(),
                    "pilot": "P2 (ADR-035)",
                }
            )
            result = train(
                spec,
                config,
                executor,
                None if reference is None else reference[spec.species],
                store.add_generation,
            )
            store.finish(result)
            typer.echo(f"{spec.name}: selected F_val {result.selected.f_val:.4f}")

    if workers == 0:
        run_all(SequentialExecutor())
    else:
        with ProcessExecutor(workers) as executor:
            run_all(executor)


def _curve(directory: Path) -> list[tuple[int, float, float]]:
    """(generation, F_val or nan, share of genomes with F_train = 0) per generation."""
    with (directory / "generations.csv").open(encoding="utf-8") as handle:
        return [
            (
                int(r["generation"]),
                float(r["f_val"]) if r["f_val"] else math.nan,
                float(r["zero_share"]),
            )
            for r in csv.DictReader(handle)
        ]


def decide(output_root: Path) -> dict[str, Any]:
    runs_root = output_root / "runs"
    curves: dict[tuple[str, float], list[list[tuple[int, float, float]]]] = {}
    for spec in p2_specs():
        directory = runs_root / spec.name
        if not (directory / "summary.json").exists():
            raise FileNotFoundError(f"{directory}: the P2 run is missing or incomplete")
        curves.setdefault((spec.architecture, spec.sigma), []).append(_curve(directory))

    def validated(runs):
        """Median F_val over runs at every validated generation."""
        generations = [g for g, v, _ in runs[0] if not math.isnan(v)]
        return [
            (g, statistics.median(next(v for gg, v, _ in run if gg == g) for run in runs))
            for g in generations
        ]

    decision: dict[str, Any] = {"adr": "ADR-035", "fixed": {**FIXED, "k_val": VALIDATION_INTERVAL}}
    sigma: dict[str, float] = {}
    stagnation: dict[str, int] = {}
    curves_out: dict[str, Any] = {}
    for network in NETWORKS:
        finals = {s: validated(curves[(network, s)])[-1][1] for s in SIGMAS}
        best = max(SIGMAS, key=lambda s: (finals[s], -s))  # ties: the smaller sigma
        sigma[network] = best
        curve = validated(curves[(network, best)])
        start, top = curve[0][1], max(v for _, v in curve)
        gain = top - start
        target = start + 0.95 * gain
        stagnation[network] = next(g for g, v in curve if v >= target) if gain > 0 else curve[-1][0]
        curves_out[network] = {"final_f_val_by_sigma": finals, "median_curve": curve}
    g_star = max(stagnation.values())
    if g_star >= PILOT_GENERATIONS - 1:
        generations = 75
    else:
        generations = max(60, math.ceil(1.25 * g_star / VALIDATION_INTERVAL) * VALIDATION_INTERVAL)

    # curriculum (ADR-026): share of predator_base genomes with F_train = 0 in generations 0-9
    zero_share = float(
        np.mean(
            [
                share
                for run in curves[("predator_base", sigma["predator_base"])]
                for g, _, share in run
                if g < 10
            ]
        )
    )
    curriculum = zero_share > 0.80
    targets = {}
    for species in ("prey", "predator"):
        curve = validated(curves[(f"{species}_base", sigma[f"{species}_base"])])
        f0, f_base = curve[0][1], curve[-1][1]
        gain = f_base - f0
        targets[species] = {
            "F0": f0,
            "F_base": f_base,
            "gain": gain,
            "delta": 0.10 * gain,
            "theta": f0 + 0.9 * gain,
        }
    decision.update(
        {
            "sigma": sigma,
            "stagnation_generation": stagnation,
            "G": generations,
            "curriculum": {
                "predator_zero_share_g0_9": zero_share,
                "active": curriculum,
                "kappa": 2.0 if curriculum else 1.0,
                "G_c": math.ceil(generations / 2) if curriculum else 0,
            },
            "targets": targets,
            "curves": curves_out,
        }
    )
    return decision


def pilot_p2_decide(
    output_root: Annotated[Path, typer.Option(help="P2 directory.")] = Path("results/pilots/p2"),
) -> None:
    """Apply ADR-035 to the stored P2 runs and write p2_decision.json."""
    decision = decide(output_root)
    write_json(output_root / "p2_decision.json", decision)
    shown = {k: decision[k] for k in ("sigma", "G", "curriculum", "targets")}
    typer.echo(json.dumps(shown, indent=2))
