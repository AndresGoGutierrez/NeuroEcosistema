"""Shared fixtures."""

from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pytest

from neuroeco.domain.params import WorldParams
from support import PROVISIONAL_WORLD


@pytest.fixture
def world_params() -> Callable[..., WorldParams]:
    """Factory: provisional world parameters with optional field overrides."""

    def build(**overrides: Any) -> WorldParams:
        return replace(PROVISIONAL_WORLD, **overrides)

    return build
