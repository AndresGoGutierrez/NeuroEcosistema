"""ADR-028: the project seed exists and is a valid 128-bit SeedSequence entropy."""

from pathlib import Path

import numpy as np
import yaml

BASE_CONFIG = Path(__file__).resolve().parents[1] / "configs" / "base.yaml"


def test_project_seed_is_a_128_bit_non_negative_integer() -> None:
    config = yaml.safe_load(BASE_CONFIG.read_text(encoding="utf-8"))
    seed = config["project_seed"]
    assert isinstance(seed, int) and not isinstance(seed, bool)
    assert 0 < seed < 2**128


def test_project_seed_is_accepted_by_seed_sequence() -> None:
    config = yaml.safe_load(BASE_CONFIG.read_text(encoding="utf-8"))
    sequence = np.random.SeedSequence(config["project_seed"], spawn_key=(1, 0, 0, 0, 0, 1))
    first = np.random.default_rng(sequence).integers(0, 2**63)
    again = np.random.default_rng(
        np.random.SeedSequence(config["project_seed"], spawn_key=(1, 0, 0, 0, 0, 1))
    ).integers(0, 2**63)
    assert first == again
