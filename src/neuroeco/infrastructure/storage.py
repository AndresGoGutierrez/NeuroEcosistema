"""Minimal result storage (ADR-023; decision A7).

CSV with an explicit column order for tabular evidence and JSON for metadata. The full
``RunStore`` port arrives with the phases that need it.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import os
import uuid
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

RUN_DIRECTORY_ATTEMPTS = 10


def write_csv(path: Path, columns: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def replace_json(path: Path, data: Mapping[str, Any]) -> None:
    """Write JSON atomically: readers see the previous version or the new one, never a mix.

    Used for records that are rewritten while a session runs (ADR-031). ``allow_nan`` is off:
    missing values must be written as null.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    text = json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n"
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def new_run_directory(root: Path, now: dt.datetime) -> Path:
    """Create ``root/<YYYYMMDDTHHMMSSZ>-<8 hex>`` exclusively; never reuses an existing one.

    The suffix comes from ``uuid4`` (operating-system entropy). It only names a directory and
    has nothing to do with the simulation's seeded randomness (ADR-028).
    """
    if now.utcoffset() != dt.timedelta(0):
        raise ValueError("run directories are named in UTC; pass an aware UTC datetime")
    root.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    for _ in range(RUN_DIRECTORY_ATTEMPTS):
        candidate = root / f"{stamp}-{uuid.uuid4().hex[:8]}"
        try:
            candidate.mkdir()
        except FileExistsError:
            continue
        return candidate
    raise RuntimeError(f"could not create a unique run directory under {root}")


def _unique_sibling(target: Path, label: str, create: Callable[[Path], None]) -> Path:
    for _ in range(RUN_DIRECTORY_ATTEMPTS):
        candidate = target.with_name(f"{target.name}.{label}-{uuid.uuid4().hex[:8]}")
        if candidate.exists():
            continue
        try:
            create(candidate)
        except FileExistsError:
            continue
        return candidate
    raise RuntimeError(f"could not create a unique {label} directory next to {target}")


def create_partial_directory(target: Path) -> Path:
    """Create ``<target>.partial-<8 hex>`` next to ``target``, which must not exist yet.

    Results are assembled there and only appear under ``target`` when complete
    (``publish_directory``); an existing ``target`` is never overwritten.
    """
    if target.exists():
        raise FileExistsError(f"{target} already exists; results are never overwritten")
    target.parent.mkdir(parents=True, exist_ok=True)
    return _unique_sibling(target, "partial", lambda path: path.mkdir())


def publish_directory(partial: Path, target: Path) -> None:
    """Make a completed ``partial`` directory visible as ``target`` in one rename."""
    if target.exists():
        raise FileExistsError(f"{target} already exists; results are never overwritten")
    os.rename(partial, target)


def reserve_failure_directory(target: Path, now: dt.datetime, source: Path | None = None) -> Path:
    """``<target>.failed-<YYYYMMDDTHHMMSSZ>-<8 hex>``, unique; never the result directory.

    With ``source`` (a partial directory) the failure directory is that directory renamed;
    otherwise a new empty one is created.
    """
    if now.utcoffset() != dt.timedelta(0):
        raise ValueError("failure directories are named in UTC; pass an aware UTC datetime")
    target.parent.mkdir(parents=True, exist_ok=True)
    label = f"failed-{now.strftime('%Y%m%dT%H%M%SZ')}"
    if source is None:
        return _unique_sibling(target, label, lambda path: path.mkdir())
    return _unique_sibling(target, label, lambda path: os.rename(source, path))
