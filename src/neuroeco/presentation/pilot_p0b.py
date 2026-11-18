"""``neuroeco pilot p0b``: network forward cost and parallel speed-up (F6, decision A3, O4).

O4 methodology (approved with the P0 optimization plan): the (population x policy) cells are
measured in a randomized, interleaved order (one repetition of every cell per round), each
measurement is preceded by an unrecorded warm-up episode of its cell, and the power state of the
machine is recorded. The speed-up runs a generation-like batch of training episodes with a warm
process pool of each size. Results are written to a new directory; nothing is overwritten.
"""

from __future__ import annotations

import dataclasses
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Annotated

import numpy as np
import typer

from neuroeco.application.evaluation import EpisodeIdentity, time_episode
from neuroeco.application.seeding import Purpose, SeedRegistry, Stream
from neuroeco.application.training import EpisodeTask, episode_fitness
from neuroeco.bootstrap import DEFAULT_CONFIG_DIR, build_policy
from neuroeco.domain.neural import (
    PREDATOR_BASE,
    PREY_BASE,
    NeuralNetwork,
    NeuralPolicy,
    lecun_genome,
)
from neuroeco.domain.simulator import PHASES
from neuroeco.infrastructure.config_loader import ConfigError, load_config, load_p0b_spec
from neuroeco.infrastructure.executors import (
    ProcessExecutor,
    limit_blas_threads,
    single_threaded,
    thread_pools,
)
from neuroeco.infrastructure.provenance import collect_provenance
from neuroeco.infrastructure.storage import write_csv, write_json

CELL_COLUMNS = (
    "round",
    "position",
    "n_prey",
    "n_predators",
    "policy",
    "steps",
    "us_per_step",
    *(f"{phase}_us_per_step" for phase in PHASES),
)
SPEEDUP_COLUMNS = ("round", "workers", "episodes", "seconds", "episodes_per_second")


def per_step(timed, phase: str) -> float:
    return 1e6 * timed.phase_seconds[phase] / timed.steps


def power_state() -> dict[str, str]:
    """Best-effort description of the power plan (O4); never fails the pilot."""
    state = {"platform": platform.platform(), "processor": platform.processor()}
    if sys.platform == "win32":
        try:
            completed = subprocess.run(
                ["powercfg", "/getactivescheme"], capture_output=True, text=True, timeout=10
            )
            state["power_scheme"] = completed.stdout.strip()
        except (OSError, subprocess.SubprocessError) as error:
            state["power_scheme"] = f"unavailable: {error}"
    return state


def pilot_p0b(
    spec_path: Annotated[Path, typer.Option("--spec", help="P0b specification.")] = (
        DEFAULT_CONFIG_DIR / "pilots" / "p0b.yaml"
    ),
    config_dir: Annotated[Path, typer.Option(help="Configuration directory.")] = (
        DEFAULT_CONFIG_DIR
    ),
    output_dir: Annotated[Path, typer.Option(help="Output directory (must not exist).")] = Path(
        "results/pilots/p0b"
    ),
) -> None:
    """P0b: forward cost of the networks per step and speed-up of the process pool."""
    limit_blas_threads()
    try:
        spec = load_p0b_spec(spec_path)
        if output_dir.exists():
            raise ConfigError(f"{output_dir} already exists; results are never overwritten")
        config = load_config(config_dir, spec.scenario)
        if not single_threaded():
            raise ConfigError("a BLAS thread pool has more than one thread (ADR-016)")
    except (ConfigError, OSError, ValueError) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=1) from error

    provenance = collect_provenance(sys.argv, Path.cwd(), config.config_hash)
    registry = SeedRegistry(config.project_seed)
    clock = time.perf_counter

    def genome(spec_net, item: int) -> np.ndarray:
        rng = registry.generator(Purpose.PILOT, spec.seed_group, 0, 0, item, Stream.GA_INIT)
        return lecun_genome(spec_net, rng)

    neural = {
        "prey": NeuralPolicy(NeuralNetwork(PREY_BASE, genome(PREY_BASE, 0))),
        "predator": NeuralPolicy(NeuralNetwork(PREDATOR_BASE, genome(PREDATOR_BASE, 1))),
    }
    rules = {s: build_policy("rules", s, config) for s in ("prey", "predator")}
    cells = [(p, q, policy) for p, q in spec.populations for policy in spec.policies]
    order_rng = registry.generator(Purpose.PILOT, spec.seed_group, 0, 0, 0, Stream.ENV_DYNAMICS)

    cell_rows: list[dict[str, object]] = []
    for round_ in range(spec.repetitions):
        for position, index in enumerate(order_rng.permutation(len(cells))):
            n_prey, n_predators, policy = cells[int(index)]
            policies = neural if policy == "neural" else rules
            world = dataclasses.replace(config.world, n_prey=n_prey, n_predators=n_predators)
            warm = dataclasses.replace(world, t_max=min(100, world.t_max))
            item = 1000 + round_
            identity = EpisodeIdentity(Purpose.PILOT, spec.seed_group, item=item)
            time_episode(warm, policies["prey"], policies["predator"], registry, identity, clock)
            timed = time_episode(
                world, policies["prey"], policies["predator"], registry, identity, clock
            )
            cell_rows.append(
                {
                    "round": round_,
                    "position": position,
                    "n_prey": n_prey,
                    "n_predators": n_predators,
                    "policy": policy,
                    "steps": timed.steps,
                    "us_per_step": f"{1e6 * timed.seconds_per_step:.3f}",
                    **{f"{phase}_us_per_step": f"{per_step(timed, phase):.3f}" for phase in PHASES},
                }
            )
            label = f"{n_prey}/{n_predators} {policy}"
            typer.echo(f"round {round_} {label}: {cell_rows[-1]['us_per_step']} us/step")

    tasks = [
        EpisodeTask(
            config.project_seed,
            config.world,
            config.rules,
            "prey",
            "prey_base",
            genome(PREY_BASE, 10 + g),
            EpisodeIdentity(Purpose.PILOT, spec.seed_group, 0, 1, e),
        )
        for g in range(spec.speedup_genomes)
        for e in range(spec.speedup_episodes)
    ]
    speedup_rows: list[dict[str, object]] = []
    for workers in spec.speedup_workers:
        with ProcessExecutor(workers) as executor:
            executor.map(episode_fitness, tasks[:workers])  # warm the pool
            for round_ in range(spec.speedup_repetitions):
                start = clock()
                executor.map(episode_fitness, tasks)
                seconds = clock() - start
                speedup_rows.append(
                    {
                        "round": round_,
                        "workers": workers,
                        "episodes": len(tasks),
                        "seconds": f"{seconds:.3f}",
                        "episodes_per_second": f"{len(tasks) / seconds:.3f}",
                    }
                )
                typer.echo(f"workers {workers}: {seconds:.2f} s")

    def median_us(n_prey, n_predators, policy) -> float:
        values = [
            float(r["us_per_step"])
            for r in cell_rows
            if (r["n_prey"], r["n_predators"], r["policy"]) == (n_prey, n_predators, policy)
        ]
        return statistics.median(values)

    medians = {f"{p}/{q}/{policy}": median_us(p, q, policy) for p, q, policy in cells}
    seconds = {
        w: statistics.median(float(r["seconds"]) for r in speedup_rows if r["workers"] == w)
        for w in spec.speedup_workers
    }
    speedup = {w: seconds[1] / seconds[w] for w in spec.speedup_workers}
    output_dir.mkdir(parents=True)
    write_csv(output_dir / "p0b_cells.csv", CELL_COLUMNS, cell_rows)
    write_csv(output_dir / "p0b_speedup.csv", SPEEDUP_COLUMNS, speedup_rows)
    write_json(
        output_dir / "p0b_summary.json",
        {
            **provenance,
            "spec": dataclasses.asdict(spec),
            "power_state": power_state(),
            "thread_pools": thread_pools(),
            "median_us_per_step": medians,
            "forward_overhead_us_per_step": {
                f"{p}/{q}": medians[f"{p}/{q}/neural"] - medians[f"{p}/{q}/rules"]
                for p, q in spec.populations
                if {"rules", "neural"} <= set(spec.policies)
            },
            "speedup_median_seconds": {str(w): s for w, s in seconds.items()},
            "speedup": {str(w): s for w, s in speedup.items()},
            "efficiency": {str(w): speedup[w] / w for w in spec.speedup_workers},
        },
    )
    typer.echo(f"P0b written to {output_dir}")
