"""F6: ``neuroeco train`` stores a complete run and never overwrites one."""

import csv
import json

import numpy as np
import yaml
from typer.testing import CliRunner

from neuroeco.infrastructure.model_store import load_model
from neuroeco.presentation.cli import app

SPEC = {
    "name": "tiny",
    "species": "predator",
    "architecture": "predator_compact",
    "scenario": "C",
    "seed_group": 901,
    "run": 0,
    "population": 4,
    "elite": 1,
    "tournament": 2,
    "sigma": 0.1,
    "episodes": 1,
    "validation_episodes": 1,
    "generations": 3,
    "validation_interval": 2,
    "curriculum_kappa": 1.5,
    "curriculum_generations": 2,
}


def run(tmp_path, *extra):
    spec = tmp_path / "spec.yaml"
    spec.write_text(yaml.safe_dump(SPEC), encoding="utf-8")
    return CliRunner().invoke(
        app, ["train", "--spec", str(spec), "--output-root", str(tmp_path / "runs"), *extra]
    )


def test_train_writes_the_run(tmp_path) -> None:
    result = run(tmp_path)
    assert result.exit_code == 0, result.output
    directory = tmp_path / "runs" / "tiny"
    manifest = json.loads((directory / "manifest.json").read_text("utf-8"))
    assert manifest["spec"]["name"] == "tiny" and manifest["workers"] == 0
    assert all(p["num_threads"] == 1 for p in manifest["thread_pools"])
    with (directory / "generations.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert [r["generation"] for r in rows] == ["0", "1", "2"]
    radii = [float(r["capture_radius"]) for r in rows]
    assert radii[0] == 1.5 * radii[2] and radii[1] == 1.25 * radii[2]  # curriculum (ADR-026)
    summary = json.loads((directory / "summary.json").read_text("utf-8"))
    assert [c["generation"] for c in summary["checkpoints"]] == [0, 2]
    _, header = load_model(directory / "selected.npz")
    assert header["metadata"]["generation"] == summary["selected_generation"]
    final, _ = load_model(directory / "final.npz")
    checkpoint, _ = load_model(directory / "checkpoints" / "gen_0002.npz")
    assert np.array_equal(final.genome, checkpoint.genome)


def test_train_never_overwrites_a_run(tmp_path) -> None:
    assert run(tmp_path).exit_code == 0
    again = run(tmp_path)
    assert again.exit_code == 1 and "never overwritten" in again.output
