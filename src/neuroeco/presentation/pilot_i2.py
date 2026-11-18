"""``neuroeco pilot i2``: initial saturation of the random networks (F5, ADR-018 I2).

Builds the reference observation set from rule-based episodes in the frozen scenarios, saves it
as ``reference_observations.npz`` with its SHA-256, and evaluates S1-S3 over random genomes of
the four architectures of ADR-025. An existing output directory is never overwritten.
"""

from __future__ import annotations

import dataclasses
import hashlib
import sys
from pathlib import Path
from typing import Annotated

import numpy as np
import typer

from neuroeco.application.reference import SPECIES, check_saturation, collect_reference
from neuroeco.application.seeding import SeedRegistry
from neuroeco.bootstrap import DEFAULT_CONFIG_DIR, build_policy
from neuroeco.domain.neural import ARCHITECTURES
from neuroeco.infrastructure.config_loader import (
    ConfigError,
    load_config,
    load_reference_spec,
)
from neuroeco.infrastructure.provenance import collect_provenance
from neuroeco.infrastructure.storage import write_csv, write_json

REFERENCE_FILE = "reference_observations.npz"
GENOME_COLUMNS = ("network", "genome", "metric", "layer", "value")
SUMMARY_COLUMNS = ("network", "metric", "layer", "median", "threshold", "passed")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pilot_i2(
    spec_path: Annotated[Path, typer.Option("--spec", help="I2 specification.")] = (
        DEFAULT_CONFIG_DIR / "pilots" / "f5_reference.yaml"
    ),
    config_dir: Annotated[Path, typer.Option(help="Configuration directory.")] = (
        DEFAULT_CONFIG_DIR
    ),
    output_dir: Annotated[Path, typer.Option(help="Output directory (must not exist).")] = Path(
        "results/pilots/f5_i2"
    ),
) -> None:
    """I2 (ADR-018): reference observations and S1-S3 over random genomes."""
    try:
        spec = load_reference_spec(spec_path)
        if output_dir.exists():
            raise ConfigError(f"{output_dir} already exists; results are never overwritten")
        configs = {s: load_config(config_dir, s) for s in spec.scenarios}
        seeds = {c.project_seed for c in configs.values()}
        if len(seeds) != 1:
            raise ConfigError("the scenarios do not share the project seed")
        registry = SeedRegistry(seeds.pop())
        provenance = collect_provenance(
            sys.argv, Path.cwd(), configs[spec.scenarios[0]].config_hash
        )
    except (ConfigError, OSError, ValueError) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=1) from error

    reference = collect_reference(spec, configs, build_policy, registry)
    output_dir.mkdir(parents=True)
    reference_path = output_dir / REFERENCE_FILE
    with reference_path.open("wb") as handle:
        np.savez(handle, **reference)

    genome_rows: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []
    verdicts = {}
    for name, network in ARCHITECTURES.items():
        check = check_saturation(spec, network, reference[network.schema.species], registry)
        verdicts[name] = check.passed
        for g, stats in enumerate(check.per_genome):
            for metric in ("s1", "s2", "s3"):
                for layer, value in enumerate(getattr(stats, metric)):
                    genome_rows.append(
                        {
                            "network": name,
                            "genome": g,
                            "metric": metric,
                            "layer": layer,
                            "value": repr(value),
                        }
                    )
        limits = {"s1": spec.s1_max, "s2": spec.s2_max, "s3": spec.s3_min}
        for metric in ("s1", "s2", "s3"):
            for layer, value in enumerate(getattr(check, f"{metric}_median")):
                ok = value >= limits[metric] if metric == "s3" else value <= limits[metric]
                summary_rows.append(
                    {
                        "network": name,
                        "metric": metric,
                        "layer": layer,
                        "median": repr(value),
                        "threshold": limits[metric],
                        "passed": ok,
                    }
                )

    write_csv(output_dir / "saturation_genomes.csv", GENOME_COLUMNS, genome_rows)
    write_csv(output_dir / "saturation_summary.csv", SUMMARY_COLUMNS, summary_rows)
    write_json(
        output_dir / "provenance.json",
        {
            **provenance,
            "spec": dataclasses.asdict(spec),
            "config_hashes": {s: c.config_hash for s, c in configs.items()},
            "reference": {
                "file": REFERENCE_FILE,
                "sha256": file_sha256(reference_path),
                "rows": {s: int(reference[s].shape[0]) for s in SPECIES},
            },
            "verdicts": verdicts,
            "verdict": "PASS" if all(verdicts.values()) else "FAIL",
        },
    )
    rows = ", ".join(f"{s} {reference[s].shape[0]}" for s in SPECIES)
    typer.echo(f"I2 reference rows: {rows}")
    for name, passed in verdicts.items():
        typer.echo(f"{name}: {'PASS' if passed else 'FAIL'}")
    if not all(verdicts.values()):
        raise typer.Exit(code=2)
