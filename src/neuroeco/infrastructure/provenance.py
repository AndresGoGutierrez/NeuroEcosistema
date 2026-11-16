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


def git_toplevel(cwd: Path) -> Path | None:
    """Root of the git working tree that contains ``cwd``; None outside git or without git."""
    root = _git(["rev-parse", "--show-toplevel"], cwd)
    return Path(root).resolve() if root else None


def is_inside(path: Path, root: Path) -> bool:
    """True when ``path`` (resolved, symbolic links followed) lies under ``root``."""
    return path.resolve().is_relative_to(root.resolve())


def git_untracked(paths: Sequence[Path], root: Path) -> list[Path] | None:
    """The ``paths`` under ``root`` that git does not track (P1-19); None if git fails.

    Paths are matched literally (no pathspec patterns). Paths outside ``root`` must be filtered
    out by the caller with ``is_inside``.
    """
    root = root.resolve()
    relative = {path: path.resolve().relative_to(root).as_posix() for path in paths}
    if not relative:
        return []
    listed = _git(["--literal-pathspecs", "ls-files", "-z", "--", *relative.values()], root)
    if listed is None:
        return None
    fold = str.casefold if os.name == "nt" else str  # NTFS paths are case-insensitive
    tracked = {fold(name) for name in listed.split("\0") if name}
    return [path for path, name in relative.items() if fold(name) not in tracked]


def git_upstream(cwd: Path) -> dict[str, str | None]:
    """The upstream branch of HEAD and its commit, from the local remote-tracking reference.

    No fetch is made: the reference is the one the last push or fetch left (T3b, M-1).
    """
    return {
        "ref": _git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], cwd),
        "commit": _git(["rev-parse", "@{u}"], cwd),
    }


def git_state(cwd: Path) -> dict[str, Any]:
    """Commit, cleanliness and upstream of the working tree; never raises (failure records)."""
    status = _git(["status", "--porcelain"], cwd)
    upstream = git_upstream(cwd)
    return {
        "commit": _git(["rev-parse", "HEAD"], cwd),
        "dirty": None if status is None else bool(status),
        "upstream": upstream["ref"],
        "upstream_commit": upstream["commit"],
    }


def dependency_versions(names: Sequence[str]) -> dict[str, str | None]:
    """Installed versions read from package metadata, without importing the packages."""
    versions: dict[str, str | None] = {}
    for name in names:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return versions
