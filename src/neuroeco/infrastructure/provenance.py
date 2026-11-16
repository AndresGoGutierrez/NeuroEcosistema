"""Minimal provenance of a run (decision A7): code version, environment and machine.

Benchmark results depend on the machine, so every measurement records where it was taken.
The full manifest (BLAS thread pools, seeds, run directory) arrives in later phases.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import os
import platform
import subprocess
import sys
from collections.abc import Sequence
from importlib import metadata
from pathlib import Path
from typing import Any

import numpy as np


def _git(arguments: Sequence[str], cwd: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *arguments], cwd=cwd, capture_output=True, text=True, check=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip()


def collect_provenance(command: Sequence[str], cwd: Path, config_hash: str) -> dict[str, Any]:
    status = _git(["status", "--porcelain"], cwd)
    return {
        "timestamp_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "command": list(command),
        "config_hash": config_hash,
        "git_commit": _git(["rev-parse", "HEAD"], cwd),
        "git_dirty": None if status is None else bool(status),
        "python": sys.version.split()[0],
        "numpy": np.__version__,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or None,
        "cpu_count": os.cpu_count(),
        "thread_env": {
            name: os.environ.get(name)
            for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
        },
    }


def file_sha256(path: Path) -> str:
    """SHA-256 of a file's bytes (specifications and ``uv.lock`` in the P1 provenance)."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dependency_versions(names: Sequence[str]) -> dict[str, str | None]:
    """Installed versions read from package metadata, without importing the packages."""
    versions: dict[str, str | None] = {}
    for name in names:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return versions
