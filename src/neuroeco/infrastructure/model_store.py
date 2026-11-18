"""Saving and loading network models (ADR-025, ADR-007; DET-4).

A model is one ``.npz`` file with the genome (float64, bit-exact) and a JSON header that
describes the topology and the sensor schema it was trained with. Loading rebuilds the network
only if the header matches the current schema of the species exactly (name, version and the
ordered input names) and the genome hash matches; any difference is rejected, never adapted.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import numpy as np

from neuroeco.domain.neural import ARCHITECTURES, NetworkSpec, NeuralNetwork
from neuroeco.domain.perception import PREDATOR_SCHEMA, PREY_SCHEMA

MODEL_SCHEMA = "neuroeco.model/1"
SCHEMAS = {s.species: s for s in (PREY_SCHEMA, PREDATOR_SCHEMA)}


class ModelError(ValueError):
    """A model file that cannot be used with the current code."""


def genome_sha256(genome: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(genome, dtype="<f8").tobytes()).hexdigest()


def model_header(network: NeuralNetwork, metadata: dict[str, Any] | None = None) -> dict:
    spec = network.spec
    return {
        "schema": MODEL_SCHEMA,
        "architecture": spec.name,
        "species": spec.schema.species,
        "input_schema_version": spec.schema.version,
        "input_names": list(spec.schema.names),
        "layer_sizes": list(spec.layer_sizes),
        "activation": "tanh",
        "parameter_count": spec.parameter_count,
        "genome_sha256": genome_sha256(network.genome),
        "metadata": metadata or {},
    }


def save_model(path: Path, network: NeuralNetwork, metadata: dict[str, Any] | None = None) -> None:
    """Write the model atomically; an existing file is never overwritten."""
    if path.suffix != ".npz":
        raise ModelError(f"a model file must end in .npz, got {path.name}")
    if path.exists():
        raise ModelError(f"refusing to overwrite the model {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    header = json.dumps(model_header(network, metadata), sort_keys=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as handle:
        np.savez(handle, genome=network.genome.astype("<f8"), header=np.array(header))
    os.replace(temporary, path)


def _expected_spec(header: dict) -> NetworkSpec:
    name = header.get("architecture")
    if name not in ARCHITECTURES:
        raise ModelError(f"unknown architecture {name!r}")
    spec = ARCHITECTURES[name]
    current = SCHEMAS.get(header.get("species"))
    if current is None or current != spec.schema:
        raise ModelError(f"the species {header.get('species')!r} does not match {name}")
    if (
        header.get("input_schema_version") != current.version
        or tuple(header.get("input_names", ())) != current.names
    ):
        raise ModelError(
            f"the model was saved with another input schema of {current.species} "
            f"(version {header.get('input_schema_version')!r}); current is version "
            f"{current.version} with {current.size} inputs (ADR-007)"
        )
    if (
        tuple(header.get("layer_sizes", ())) != spec.layer_sizes
        or header.get("activation") != "tanh"
        or header.get("parameter_count") != spec.parameter_count
    ):
        raise ModelError(f"the topology of the model does not match {name} (ADR-025)")
    return spec


def load_model(path: Path, expected: NetworkSpec | None = None) -> tuple[NeuralNetwork, dict]:
    """The network and its header; rejects any schema, topology or content mismatch."""
    try:
        with np.load(path, allow_pickle=False) as data:
            genome = np.array(data["genome"], dtype=np.float64)
            header = json.loads(str(data["header"]))
    except (OSError, KeyError, ValueError) as error:
        raise ModelError(f"{path}: not a readable model ({error})") from None
    if not isinstance(header, dict) or header.get("schema") != MODEL_SCHEMA:
        raise ModelError(f"{path}: not a {MODEL_SCHEMA} model")
    spec = _expected_spec(header)
    if expected is not None and spec != expected:
        raise ModelError(f"{path}: expected a {expected.name} model, got {spec.name}")
    if genome_sha256(genome) != header.get("genome_sha256"):
        raise ModelError(f"{path}: the genome does not match its recorded SHA-256")
    return NeuralNetwork(spec, genome), header
