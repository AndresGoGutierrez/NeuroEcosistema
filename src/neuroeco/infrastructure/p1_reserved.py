"""The reserved root of the real P1 results, ``results/pilots/p1/RESERVED.json`` (T4d, D-T4d-4).

The marker declares a directory as the root of the real results. It fixes the SHA-256 of the
approved specification and the reference fingerprints of the code and the environment, so that
nothing else can write there and the first real block already runs on the reference code. It is
found by walking the existing ancestors of a path on the file system, so relative paths, ``..``,
symbolic links, Windows junctions and spellings that differ only in case reach the same marker.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

RESERVED_FILE = "RESERVED.json"
RESERVED_SCHEMA = "neuroeco.p1-reserved/1"
_SHA256 = re.compile(r"[0-9a-f]{64}")


class ReservedRootError(ValueError):
    """The reserved root refuses the operation; nothing was written."""


def reserved_root(path: Path) -> Path | None:
    """The nearest directory at or above ``path`` that holds the marker, or None."""
    resolved = Path(os.path.realpath(path))
    for directory in (resolved, *resolved.parents):
        if (directory / RESERVED_FILE).is_file():
            return directory
    return None


def read_reserved(root: Path) -> dict[str, Any]:
    path = root / RESERVED_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ReservedRootError(f"{path.as_posix()} cannot be read ({error})") from None
    if (
        not isinstance(data, dict)
        or data.get("schema") != RESERVED_SCHEMA
        or not _SHA256.fullmatch(str(data.get("p1_spec_sha256")))
        or not isinstance(data.get("fingerprint"), dict)
    ):
        raise ReservedRootError(f"{path.as_posix()} is not a valid {RESERVED_SCHEMA} marker")
    return data


def reserved_document(spec_sha256: str, fingerprint: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": RESERVED_SCHEMA,
        "purpose": "root of the real P1 results: only the approved specification writes here "
        "(D-T4d-4)",
        "p1_spec_sha256": spec_sha256,
        "fingerprint": dict(fingerprint),
    }


def same_directory(first: Path, second: Path) -> bool:
    return os.path.normcase(os.path.realpath(first)) == os.path.normcase(os.path.realpath(second))
