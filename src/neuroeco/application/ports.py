"""Ports of the application layer (ADR-021): implemented in ``infrastructure``."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol, TypeVar

T = TypeVar("T")
R = TypeVar("R")


class TaskExecutor(Protocol):
    """Runs independent tasks and returns their results in the order of the tasks."""

    workers: int

    def map(self, fn: Callable[[T], R], tasks: Sequence[T]) -> list[R]: ...
