"""Storage of training runs (ADR-023, ADR-027): one directory per run, never overwritten.

<root>/<name>/
    manifest.json        spec, provenance, BLAS thread pools, reference set hash
    generations.csv      one row per generation (ADR-027 log, F_val when validated)
    checkpoints/gen_NNNN.npz   best genome of each validated generation (models)
    selected.npz         checkpoint with the highest F_val (ADR-026)
    final.npz            elite of the last generation
    summary.json         selection and checkpoint table
"""

from __future__ import annotations

import csv
import dataclasses
from pathlib import Path
from typing import Any

from neuroeco.application.training import (
    Checkpoint,
    GenerationRecord,
    TrainingResult,
    TrainingSpec,
)
from neuroeco.domain.neural import ARCHITECTURES, NeuralNetwork
from neuroeco.infrastructure.model_store import save_model
from neuroeco.infrastructure.storage import write_json

GENERATION_COLUMNS = (
    "generation",
    "fitness_max",
    "fitness_mean",
    "fitness_median",
    "fitness_std",
    "diversity",
    "best_norm",
    "best_drift",
    "best_index",
    "capture_radius",
    "f_val",
)


class RunStore:
    def __init__(self, root: Path, spec: TrainingSpec) -> None:
        self.spec = spec
        self.directory = root / spec.name
        if self.directory.exists():
            raise FileExistsError(f"{self.directory} exists; runs are never overwritten")
        (self.directory / "checkpoints").mkdir(parents=True)
        self._csv = (self.directory / "generations.csv").open("w", encoding="utf-8", newline="")
        self._writer = csv.DictWriter(self._csv, fieldnames=GENERATION_COLUMNS)
        self._writer.writeheader()

    def write_manifest(self, manifest: dict[str, Any]) -> None:
        write_json(
            self.directory / "manifest.json", {"spec": dataclasses.asdict(self.spec), **manifest}
        )

    def add_generation(self, record: GenerationRecord) -> None:
        summary = dataclasses.asdict(record.summary)
        row = {k: (repr(v) if isinstance(v, float) else v) for k, v in summary.items()}
        row["capture_radius"] = repr(record.capture_radius)
        row["f_val"] = "" if record.f_val is None else repr(record.f_val)
        self._writer.writerow(row)
        self._csv.flush()

    def _model(self, path: Path, checkpoint: Checkpoint, role: str) -> None:
        network = NeuralNetwork(ARCHITECTURES[self.spec.architecture], checkpoint.genome)
        save_model(
            path,
            network,
            {
                "run": self.spec.name,
                "role": role,
                "generation": checkpoint.generation,
                "f_train": checkpoint.f_train,
                "f_val": checkpoint.f_val,
            },
        )

    def finish(self, result: TrainingResult) -> None:
        self._csv.close()
        for checkpoint in result.checkpoints:
            name = f"gen_{checkpoint.generation:04d}.npz"
            self._model(self.directory / "checkpoints" / name, checkpoint, "checkpoint")
        self._model(self.directory / "selected.npz", result.selected, "selected")
        self._model(self.directory / "final.npz", result.final_elite, "final")
        write_json(
            self.directory / "summary.json",
            {
                "selected_generation": result.selected.generation,
                "selected_f_val": result.selected.f_val,
                "final_generation": result.final_elite.generation,
                "final_f_val": result.final_elite.f_val,
                "checkpoints": [
                    {
                        "generation": c.generation,
                        "f_train": c.f_train,
                        "f_val": c.f_val,
                        "s1": c.s1,
                        "s2": c.s2,
                    }
                    for c in result.checkpoints
                ],
            },
        )
