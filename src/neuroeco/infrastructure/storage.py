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
from collections.abc import Mapping, Sequence
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
