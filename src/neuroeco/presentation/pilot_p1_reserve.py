"""``neuroeco pilot p1-reserve``: reserve the root of the real P1 results (F4 T4d, D-T4d-4).

Writes ``RESERVED.json`` once, before the first real block (task T5-0): the SHA-256 of the
approved specification and the reference fingerprints of the code and the environment that every
real block must reproduce. It refuses an unapproved specification, a root that is already
reserved (here or above) and a root that already holds anything.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from neuroeco.application.calibration import uses_approved_table
from neuroeco.infrastructure.config_loader import load_p1_spec
from neuroeco.infrastructure.fingerprint import p1_fingerprint
from neuroeco.infrastructure.p1_reserved import RESERVED_FILE, reserved_document, reserved_root
from neuroeco.infrastructure.provenance import file_sha256
from neuroeco.presentation.pilot_p1 import DEFAULT_OUTPUT_ROOT, DEFAULT_SPEC

EXIT_REFUSED = 1


def pilot_p1_reserve(
    spec: Annotated[Path, typer.Option(help="Approved P1 specification.")] = DEFAULT_SPEC,
    output_root: Annotated[
        Path, typer.Option(help="Root of the real P1 results.")
    ] = DEFAULT_OUTPUT_ROOT,
) -> None:
    """Reserve the root of the real P1 results for the approved specification (D-T4d-4)."""
    try:
        if not uses_approved_table(load_p1_spec(spec, {})):
            raise ValueError(f"{spec.as_posix()} is not the approved P1 table (ADR-033)")
        existing = reserved_root(output_root)
        if existing is not None:
            raise ValueError(f"{(existing / RESERVED_FILE).as_posix()} already reserves a root")
        if output_root.exists() and any(output_root.iterdir()):
            raise ValueError(f"{output_root.as_posix()} is not empty: reserve it before any block")
        output_root.mkdir(parents=True, exist_ok=True)
        document = reserved_document(file_sha256(spec), p1_fingerprint(Path.cwd() / "uv.lock"))
        with (output_root / RESERVED_FILE).open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(document, indent=2, sort_keys=True) + "\n")
    except (ValueError, OSError) as error:
        typer.echo(f"refused: {error}", err=True)
        raise typer.Exit(code=EXIT_REFUSED) from error
    typer.echo(f"{(output_root / RESERVED_FILE).as_posix()} written; commit and push it")
