"""Fingerprints of the code and the environment that produce P1 results (F4 T4d, D-T4d-2).

Every block of P1 must come from the same simulation code, the same analysis code and the same
environment; a difference stops the calibration. The fingerprints identify what can change a
result, never who or where: no host name, user, path or hardware identifier is recorded.

- ``code_fingerprint``: SHA-256 of the source of the running ``neuroeco`` package, split into
  the simulation (everything but ``analysis``) and the analysis code. Line endings are
  normalized so that the digest does not depend on how git checked the files out.
- ``environment_fingerprint``: Python, operating system (its version included, D-T4d-2),
  architecture, byte order, the installed versions of the dependencies, the SHA-256 of
  ``uv.lock``, the thread variables of ADR-016 and the CPU features numpy dispatches to.
"""

from __future__ import annotations

import hashlib
import os
import platform
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import neuroeco
from neuroeco.infrastructure.provenance import dependency_versions, file_sha256

ANALYSIS_PACKAGE = "analysis"
THREAD_VARIABLES = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
P1_DEPENDENCIES = ("numpy", "scipy", "pandas", "pyyaml", "typer", "threadpoolctl", "pygame-ce")


def p1_fingerprint(uv_lock: Path | None) -> dict[str, Any]:
    """The code and environment fingerprints recorded with every P1 block and its criteria."""
    return {
        "code": code_fingerprint(),
        "environment": environment_fingerprint(P1_DEPENDENCIES, uv_lock),
    }


def package_root() -> Path:
    """Directory of the ``neuroeco`` package that is running."""
    return Path(neuroeco.__file__).resolve().parent


def source_digest(root: Path, files: Sequence[Path]) -> str:
    """SHA-256 over the relative paths and the LF-normalized content of ``files``."""
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda p: p.relative_to(root).as_posix()):
        name = path.relative_to(root).as_posix().encode("utf-8")
        content = path.read_bytes().replace(b"\r\n", b"\n")
        digest.update(len(name).to_bytes(8, "big") + name)
        digest.update(len(content).to_bytes(8, "big") + content)
    return digest.hexdigest()


def code_fingerprint(root: Path | None = None) -> dict[str, str]:
    """Digests of the simulation code and of the analysis code of the package at ``root``."""
    base = package_root() if root is None else root
    sources = [p for p in base.rglob("*.py") if "__pycache__" not in p.parts]
    analysis = [p for p in sources if p.relative_to(base).parts[0] == ANALYSIS_PACKAGE]
    simulation = [p for p in sources if p not in analysis]
    return {
        "simulation": source_digest(base, simulation),
        "analysis": source_digest(base, analysis),
    }


def numpy_cpu_features() -> list[str] | None:
    """CPU features numpy dispatches to (they can change floating-point results)."""
    try:
        from numpy._core._multiarray_umath import __cpu_features__
    except ImportError:  # a private numpy module: unknown features count as a difference
        return None
    return sorted(name for name, enabled in __cpu_features__.items() if enabled)


def environment_fingerprint(dependencies: Sequence[str], uv_lock: Path | None) -> dict[str, Any]:
    """What must stay identical along P1 for results to be reproducible (D-T4d-2)."""
    return {
        "python": sys.version.split()[0],
        "implementation": sys.implementation.name,
        "platform": sys.platform,
        "os": [platform.system(), platform.release(), platform.version()],
        "machine": platform.machine(),
        "byteorder": sys.byteorder,
        "dependencies": dependency_versions(dependencies),
        "uv_lock_sha256": file_sha256(uv_lock) if uv_lock and uv_lock.is_file() else None,
        "thread_env": {name: os.environ.get(name) for name in THREAD_VARIABLES},
        "numpy_cpu_features": numpy_cpu_features(),
    }
