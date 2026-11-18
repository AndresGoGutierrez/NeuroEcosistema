"""Task executors (ADR-016): sequential and a process pool with one BLAS thread per process.

The pool uses the ``spawn`` start method on every operating system and limits every BLAS/OpenMP
thread pool to one thread in the initializer of each worker (threadpoolctl is the mechanism that
rules; the launcher variables are the early complement). Results keep the order of the tasks,
so a run is bit-for-bit identical with any number of workers (DET-3).
"""

from __future__ import annotations

import multiprocessing
import os
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor
from typing import Any

from threadpoolctl import threadpool_info, threadpool_limits

_LIMITS: list[Any] = []  # keeps the limiter of a worker alive for the life of the process


THREAD_VARIABLES = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "BLIS_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)


def limit_blas_threads() -> None:
    """One thread in every native pool of this process (ADR-016, step 1).

    threadpoolctl only limits the libraries already loaded, so numpy (and its BLAS) is imported
    first; the variables cover libraries loaded later.
    """
    for name in THREAD_VARIABLES:
        os.environ.setdefault(name, "1")
    import numpy  # noqa: F401  (loads BLAS before limiting it)

    _LIMITS.append(threadpool_limits(limits=1))


def thread_pools() -> list[dict[str, Any]]:
    """``threadpool_info()`` of this process, for manifests (ADR-016, step 4)."""
    return [
        {k: pool.get(k) for k in ("user_api", "internal_api", "num_threads", "version")}
        for pool in threadpool_info()
    ]


def single_threaded() -> bool:
    return all(pool["num_threads"] == 1 for pool in thread_pools())


class SequentialExecutor:
    workers = 0

    def map(self, fn: Callable[[Any], Any], tasks: Sequence[Any]) -> list[Any]:
        return [fn(task) for task in tasks]


def _worker_threads(_: object) -> list[dict[str, Any]]:
    return thread_pools()


class ProcessExecutor:
    """A ``spawn`` process pool; use it as a context manager."""

    def __init__(self, workers: int) -> None:
        if workers < 1:
            raise ValueError("workers must be >= 1")
        self.workers = workers
        self._pool: ProcessPoolExecutor | None = None

    def __enter__(self) -> ProcessExecutor:
        self._pool = ProcessPoolExecutor(
            max_workers=self.workers,
            mp_context=multiprocessing.get_context("spawn"),
            initializer=limit_blas_threads,
        )
        return self

    def __exit__(self, *exc: object) -> None:
        if self._pool is not None:
            self._pool.shutdown(wait=True, cancel_futures=True)
            self._pool = None

    def map(self, fn: Callable[[Any], Any], tasks: Sequence[Any]) -> list[Any]:
        if self._pool is None:
            raise RuntimeError("the executor must be used inside a with block")
        chunk = max(1, len(tasks) // (4 * self.workers))
        return list(self._pool.map(fn, tasks, chunksize=chunk))

    def worker_thread_pools(self) -> list[list[dict[str, Any]]]:
        """``thread_pools()`` reported by the workers (verification of ADR-016)."""
        return self.map(_worker_threads, list(range(self.workers)))
