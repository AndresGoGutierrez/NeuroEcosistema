"""F5: model files, DET-4 and the rejection of another input schema (ADR-007, ADR-025)."""

import json

import numpy as np
import pytest

from neuroeco.domain.neural import (
    PREDATOR_BASE,
    PREDATOR_COMPACT,
    PREY_BASE,
    NeuralNetwork,
    lecun_genome,
)
from neuroeco.infrastructure.model_store import ModelError, load_model, save_model


def network(spec=PREY_BASE, seed=0) -> NeuralNetwork:
    return NeuralNetwork(spec, lecun_genome(spec, np.random.default_rng(seed)))


def rewrite(path, change_header=None, change_genome=None) -> None:
    with np.load(path, allow_pickle=False) as data:
        genome = np.array(data["genome"])
        header = json.loads(str(data["header"]))
    if change_header:
        change_header(header)
    if change_genome:
        change_genome(genome)
    path.unlink()
    with path.open("wb") as handle:
        np.savez(handle, genome=genome, header=np.array(json.dumps(header)))


@pytest.mark.parametrize("spec", [PREY_BASE, PREDATOR_COMPACT])
def test_det4_save_and_load_preserve_the_outputs(tmp_path, spec) -> None:
    net = network(spec, seed=11)
    path = tmp_path / "model.npz"
    save_model(path, net, {"run": 3})
    loaded, header = load_model(path, spec)
    obs = np.random.default_rng(1).uniform(-1, 1, (200, spec.schema.size))
    assert np.array_equal(loaded.genome, net.genome)
    assert np.array_equal(loaded.forward(obs), net.forward(obs))
    assert header["metadata"] == {"run": 3} and header["parameter_count"] == spec.parameter_count


def test_a_model_is_never_overwritten(tmp_path) -> None:
    path = tmp_path / "model.npz"
    save_model(path, network())
    with pytest.raises(ModelError, match="refusing to overwrite"):
        save_model(path, network(seed=1))


def test_a_model_with_another_input_schema_is_rejected(tmp_path) -> None:
    path = tmp_path / "model.npz"
    save_model(path, network())
    rewrite(path, lambda h: h.update(input_schema_version=2))
    with pytest.raises(ModelError, match="another input schema"):
        load_model(path)


def test_a_model_with_reordered_inputs_is_rejected(tmp_path) -> None:
    path = tmp_path / "model.npz"
    save_model(path, network())

    def swap(header):
        names = header["input_names"]
        names[0], names[1] = names[1], names[0]

    rewrite(path, swap)
    with pytest.raises(ModelError, match="another input schema"):
        load_model(path)


def test_a_model_of_another_species_or_architecture_is_rejected(tmp_path) -> None:
    path = tmp_path / "model.npz"
    save_model(path, network(PREDATOR_BASE))
    with pytest.raises(ModelError, match="expected a prey_base model"):
        load_model(path, PREY_BASE)
    rewrite(path, lambda h: h.update(species="prey"))
    with pytest.raises(ModelError, match="does not match predator_base"):
        load_model(path)


def test_a_model_with_another_topology_is_rejected(tmp_path) -> None:
    path = tmp_path / "model.npz"
    save_model(path, network())
    rewrite(path, lambda h: h.update(activation="relu"))
    with pytest.raises(ModelError, match="topology"):
        load_model(path)


def test_a_modified_genome_is_rejected(tmp_path) -> None:
    path = tmp_path / "model.npz"
    save_model(path, network())
    rewrite(path, change_genome=lambda g: g.__setitem__(0, g[0] + 1e-9))
    with pytest.raises(ModelError, match="SHA-256"):
        load_model(path)


def test_an_unreadable_file_is_rejected(tmp_path) -> None:
    path = tmp_path / "model.npz"
    path.write_bytes(b"not a model")
    with pytest.raises(ModelError, match="not a readable model"):
        load_model(path)
