"""Smoke tests: the package is installed and its layers are importable."""

import importlib
import importlib.metadata

import pytest

LAYERS = [
    "neuroeco.domain",
    "neuroeco.application",
    "neuroeco.infrastructure",
    "neuroeco.analysis",
    "neuroeco.presentation",
]


def test_package_is_installed() -> None:
    assert importlib.metadata.version("neuroeco") == "0.1.0"


@pytest.mark.parametrize("module_name", LAYERS)
def test_layer_is_importable(module_name: str) -> None:
    assert importlib.import_module(module_name) is not None
