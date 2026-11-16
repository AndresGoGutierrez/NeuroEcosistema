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


# ---------------------------------------------------------------- P1 git checks (F4 T3b, T3c)


def _run_git(
    arguments: Sequence[str], cwd: Path, stdin: str | None = None
) -> subprocess.CompletedProcess[str] | None:
    """Run git with UTF-8 input and output (T3c, Mn-5); None when git cannot be started.

    Git prints paths in UTF-8 on every platform; decoding with the locale code page (cp1252 on
    Windows) would garble non-ASCII paths. ``_git`` above is kept as it was for the F1 manifest.
    """
    try:
        return subprocess.run(
            ["git", *arguments],
            cwd=cwd,
            input=stdin,
            capture_output=True,
            encoding="utf-8",
            errors="surrogateescape",
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _git_out(arguments: Sequence[str], cwd: Path, stdin: str | None = None) -> str | None:
    completed = _run_git(arguments, cwd, stdin)
    if completed is None or completed.returncode != 0:
        return None
    return completed.stdout.rstrip("\r\n")


def git_toplevel(cwd: Path) -> Path | None:
    """Root of the git working tree that contains ``cwd``; None outside git or without git."""
    root = _git_out(["rev-parse", "--show-toplevel"], cwd)
    return Path(root).resolve() if root else None


def is_inside(path: Path, root: Path) -> bool:
    """True when ``path`` (resolved, symbolic links followed) lies under ``root``."""
    return path.resolve().is_relative_to(root.resolve())


def _relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def git_untracked(paths: Sequence[Path], root: Path) -> list[Path] | None:
    """The ``paths`` under ``root`` that git does not track (P1-19); None if git fails.

    Paths are matched literally (no pathspec patterns). Paths outside ``root`` must be filtered
    out by the caller with ``is_inside``.
    """
    relative = {path: _relative(path, root) for path in paths}
    if not relative:
        return []
    listed = _git_out(["--literal-pathspecs", "ls-files", "-z", "--", *relative.values()], root)
    if listed is None:
        return None
    fold = str.casefold if os.name == "nt" else str  # NTFS paths are case-insensitive
    tracked = {fold(name) for name in listed.split("\0") if name}
    return [path for path, name in relative.items() if fold(name) not in tracked]


def git_hidden_changes(root: Path) -> list[str] | None:
    """Tracked files marked ``assume-unchanged`` or ``skip-worktree`` (T3c, IA-1).

    ``git status`` does not look at those files, so a modified file can hide behind a clean
    status. ``git ls-files -v`` prints a lowercase tag for assume-unchanged and ``S`` for
    skip-worktree.
    """
    listed = _git_out(["ls-files", "-v", "-z"], root)
    if listed is None:
        return None
    hidden = []
    for entry in listed.split("\0"):
        tag, _, name = entry.partition(" ")
        if name and (tag == "S" or tag.islower()):
            hidden.append(name)
    return hidden


def git_head_mismatches(root: Path) -> list[str] | None:
    """Tracked paths whose working-tree content differs from the commit HEAD (T3c, IA-1).

    Every blob of HEAD (code, configuration, specifications and results) is compared with
    ``git hash-object`` of the working-tree file, which applies the same filters as git (end of
    line conversion), so the check does not rely on ``git status`` or on the index. A missing
    file, a symbolic link or a submodule counts as a mismatch. None when git fails.
    """
    # The real tree of HEAD: replacement objects (``git replace``) could otherwise substitute
    # the commit with another one while ``git rev-parse HEAD`` keeps printing the original.
    tree = _git_out(["--no-replace-objects", "ls-tree", "-r", "-z", "--full-tree", "HEAD"], root)
    if tree is None:
        return None
    blobs: dict[str, str] = {}
    mismatches: list[str] = []
    for entry in tree.split("\0"):
        if not entry:
            continue
        meta, _, name = entry.partition("\t")
        mode, kind, objectid = meta.split(" ")
        if kind != "blob" or mode == "120000" or not (root / name).is_file():
            mismatches.append(name)
        else:
            blobs[name] = objectid
    if blobs:
        names = list(blobs)
        hashed = _git_out(["hash-object", "--stdin-paths"], root, "\n".join(names) + "\n")
        if hashed is None:
            return None
        computed = [line.strip() for line in hashed.split("\n")]
        if len(computed) != len(names):
            return None
        mismatches.extend(n for n, h in zip(names, computed, strict=True) if blobs[n] != h)
    return sorted(mismatches)


def git_content_overrides(root: Path) -> list[str] | None:
    """Local git settings that can make modified content look like HEAD (T3c, IA-1).

    - a ``clean`` or ``process`` filter driver: ``git hash-object`` and ``git status`` apply it,
      so a filter configured locally (``.git/config`` with ``.git/info/attributes``, neither of
      them versioned) could turn a modified file back into the committed text;
    - replacement references (``refs/replace/``): they can substitute the commit HEAD.

    End-of-line conversion is not a filter driver and stays allowed. None when git fails.
    """
    found: list[str] = []
    drivers = _run_git(["config", "--get-regexp", r"^filter\..*\.(clean|process)$"], root)
    if drivers is None or drivers.returncode not in (0, 1):
        return None
    found.extend(f"filter: {line.split(' ', 1)[0]}" for line in drivers.stdout.splitlines() if line)
    replaced = _git_out(["for-each-ref", "--format=%(refname)", "refs/replace/"], root)
    if replaced is None:
        return None
    found.extend(f"replace: {ref}" for ref in replaced.splitlines() if ref)
    return found


def git_ignored(paths: Sequence[Path], root: Path) -> list[str] | None:
    """The ``paths`` (which need not exist) that git ignores; None when git fails (T3c, Mn-3)."""
    relative = [_relative(path, root) for path in paths]
    if not relative:
        return []
    completed = _run_git(
        ["check-ignore", "--no-index", "--stdin", "-z"], root, "\0".join(relative) + "\0"
    )
    if completed is None or completed.returncode not in (0, 1):
        return None
    return [name for name in completed.stdout.split("\0") if name]


def _without_credentials(url: str | None) -> str | None:
    """A remote URL without ``user:password@`` (tokens must never reach a provenance file)."""
    if url is None:
        return None
    scheme, separator, rest = url.partition("://")
    if not separator:
        return url
    host = rest.split("/", 1)
    if "@" in host[0]:
        host[0] = host[0].rsplit("@", 1)[1]
    return f"{scheme}://{'/'.join(host)}"


def git_upstream(cwd: Path) -> dict[str, str | None]:
    """The upstream branch of HEAD, its commit, full reference and remote URL (T3b M-1, T3c Mn-1).

    No fetch is made: the commit is the one the last push or fetch left in the local
    remote-tracking reference. ``remote`` is ``"."`` when the upstream is a local branch.
    """
    branch = _git_out(["symbolic-ref", "--quiet", "--short", "HEAD"], cwd)
    remote = _git_out(["config", "--get", f"branch.{branch}.remote"], cwd) if branch else None
    url = _git_out(["remote", "get-url", remote], cwd) if remote and remote != "." else None
    return {
        "ref": _git_out(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], cwd),
        "full_ref": _git_out(["rev-parse", "--symbolic-full-name", "@{u}"], cwd),
        "commit": _git_out(["rev-parse", "@{u}"], cwd),
        "remote": remote,
        "remote_url": _without_credentials(url),
    }


def git_state(cwd: Path) -> dict[str, Any]:
    """Commit, cleanliness and upstream of the working tree; never raises (failure records)."""
    status = _git_out(["status", "--porcelain"], cwd)
    upstream = git_upstream(cwd)
    return {
        "commit": _git_out(["rev-parse", "HEAD"], cwd),
        "dirty": None if status is None else bool(status),
        "upstream": upstream["ref"],
        "upstream_commit": upstream["commit"],
        "remote_url": upstream["remote_url"],
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
