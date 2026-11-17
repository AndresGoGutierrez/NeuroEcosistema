"""``neuroeco pilot p1-criteria``: the criteria of a published P1 block (F4 T4-I3, D1).

It reads a block that ``neuroeco pilot p1`` published, verifies it and writes, inside the same
directory, ``criteria.csv`` (every criterion of ADR-033 P1-16 evaluated by
``neuroeco.analysis.calibration``) and ``criteria_provenance.json``. The result files, the
criteria and their provenance are then committed together (P1-19).

Protections:

- the evaluation code must be the committed and published one: the same git checks as
  ``pilot p1`` (no hidden changes or content overrides, every tracked file equal to HEAD, the
  running package inside the repository, HEAD synchronized with a remote-tracking upstream),
  with one difference: the only untracked files allowed are those of the evaluated block, so
  that results and criteria can enter one commit;
- the block must be complete, unaltered (SHA-256 recorded at publication) and without an A2
  violation; anything else is refused and nothing is written;
- nothing is overwritten: if both files already exist, the run succeeds only when the new
  ``criteria.csv`` is byte for byte the existing one and the existing provenance matches it.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import platform
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any

import typer

import neuroeco
from neuroeco.analysis.calibration import (
    BOOTSTRAP_FILE,
    CRITERIA_COLUMNS,
    EPISODES_FILE,
    PROVENANCE_FILE,
    CriteriaError,
    block_files,
    criteria_rows,
    evaluate_block,
    load_block,
    requirements_met,
)
from neuroeco.infrastructure.fingerprint import p1_fingerprint
from neuroeco.infrastructure.provenance import (
    dependency_versions,
    file_sha256,
    git_content_overrides,
    git_head_mismatches,
    git_hidden_changes,
    git_ignored,
    git_state,
    git_toplevel,
    git_upstream,
    is_inside,
)

CRITERIA_FILE = "criteria.csv"
CRITERIA_PROVENANCE_FILE = "criteria_provenance.json"
CRITERIA_SCHEMA = "neuroeco.p1-criteria-provenance/1"
INPUT_FILES = (PROVENANCE_FILE, EPISODES_FILE, BOOTSTRAP_FILE)
BLOCK_FILES = (*INPUT_FILES, CRITERIA_FILE, CRITERIA_PROVENANCE_FILE)
DEPENDENCIES = ("numpy", "scipy", "pandas")
EXIT_REFUSED = 1


class CriteriaRefusalError(RuntimeError):
    """The criteria cannot be written; nothing was written."""


def package_directory() -> Path:
    """Directory of the ``neuroeco`` package that is running (its code must be the commit's)."""
    return Path(neuroeco.__file__).resolve().parent


def untracked_files(root: Path) -> list[str] | None:
    """Every untracked, non-ignored file under ``root`` (relative paths); None if git fails."""
    try:
        completed = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "-z"],
            cwd=root,
            capture_output=True,
            encoding="utf-8",
            errors="surrogateescape",
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return [name for name in completed.stdout.split("\0") if name]


def repository_checks(cwd: Path, result: Path) -> dict[str, Any]:
    """What git says about the evaluation code and the evaluated block (P1-19)."""
    root = git_toplevel(cwd)
    if root is None:
        return {"root": None}
    inside = is_inside(result, root)
    block = result.resolve().relative_to(root).as_posix() if inside else None
    untracked = untracked_files(root)
    allowed = {f"{block}/{name}" for name in BLOCK_FILES}
    state = git_state(root)
    upstream = git_upstream(root)
    return {
        "root": root.as_posix(),
        "result_inside": inside,
        "result_directory": block,
        "untracked_elsewhere": None
        if untracked is None
        else sorted(name for name in untracked if name not in allowed),
        "hidden_changes": git_hidden_changes(root),
        "content_overrides": git_content_overrides(root),
        "head_mismatches": git_head_mismatches(root),
        "package_inside": is_inside(package_directory(), root),
        "ignored_outputs": git_ignored(
            [result / CRITERIA_FILE, result / CRITERIA_PROVENANCE_FILE], root
        )
        if inside
        else None,
        "head": state["commit"],
        "upstream": upstream["ref"],
        "upstream_full_ref": upstream["full_ref"],
        "remote_url": upstream["remote_url"],
        "upstream_commit": upstream["commit"],
        "synchronized": state["commit"] is not None and state["commit"] == upstream["commit"],
    }


def refuse_on_git(checks: Mapping[str, Any]) -> None:
    def refuse(message: str) -> None:
        raise CriteriaRefusalError(f"{message} (P1-19)")

    if checks["root"] is None:
        refuse("the command must run inside the git repository")
    if not checks["result_inside"]:
        refuse("the result directory must be inside the repository")
    if any(checks[k] is None for k in ("hidden_changes", "content_overrides", "head_mismatches")):
        refuse("git could not compare the working tree with HEAD")
    if checks["content_overrides"]:
        refuse(f"local git settings can disguise modified content: {checks['content_overrides']}")
    if checks["hidden_changes"]:
        refuse(f"files marked assume-unchanged or skip-worktree: {checks['hidden_changes']}")
    if checks["head_mismatches"]:
        refuse(f"files whose content differs from HEAD: {checks['head_mismatches']}")
    if not checks["package_inside"]:
        refuse("the running neuroeco package is not the one of this repository")
    if checks["untracked_elsewhere"] is None:
        refuse("git could not list the untracked files")
    if checks["untracked_elsewhere"]:
        refuse(
            f"untracked files outside the evaluated block: {checks['untracked_elsewhere']}; "
            "the evaluation code must be the committed one"
        )
    if checks["ignored_outputs"] is None or checks["ignored_outputs"]:
        refuse(f"git ignores or cannot check the criteria files: {checks['ignored_outputs']}")
    if (
        not (checks["upstream_full_ref"] or "").startswith("refs/remotes/")
        or not checks["remote_url"]
    ):
        refuse(f"HEAD has no remote-tracking upstream with a URL ({checks['upstream']!r})")
    if not checks["synchronized"]:
        refuse(
            f"HEAD {checks['head']} is not synchronized with {checks['upstream']} "
            f"({checks['upstream_commit']}): publish the evaluation code first"
        )


def render_criteria(rows: list[dict[str, str]]) -> bytes:
    """``criteria.csv`` as bytes: UTF-8, header, ``\\r\\n`` (same format as the result CSVs)."""
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(CRITERIA_COLUMNS), extrasaction="raise")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _existing_is_identical(result: Path, content: bytes, inputs: Mapping[str, str]) -> bool:
    """Both files exist: True when they hold exactly these criteria for these inputs."""
    criteria = result / CRITERIA_FILE
    if criteria.read_bytes() != content:
        return False
    try:
        record = json.loads((result / CRITERIA_PROVENANCE_FILE).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        isinstance(record, dict)
        and record.get("schema") == CRITERIA_SCHEMA
        and record.get("criteria_sha256") == file_sha256(criteria)
        and record.get("input_files") == dict(inputs)
    )


def pilot_p1_criteria(
    result: Annotated[
        Path,
        typer.Option(
            help="Published P1 block (directory with provenance.json, episodes.csv and "
            "bootstrap_keys.csv).",
        ),
    ],
) -> None:
    """Evaluate the criteria of a published P1 block (ADR-033 P1-16) into criteria.csv."""
    try:
        if not result.is_dir():
            raise CriteriaRefusalError(f"{result.as_posix()} is not a directory")
        checks = repository_checks(Path.cwd(), result)
        refuse_on_git(checks)
        block = load_block(result)
        inputs = {name: file_sha256(result / name) for name in block_files(block.stage)}
        results = evaluate_block(block)
        met = requirements_met(block.stage, results)
        content = render_criteria(criteria_rows(results))
        existing = [
            name for name in (CRITERIA_FILE, CRITERIA_PROVENANCE_FILE) if (result / name).exists()
        ]
        if existing:
            if len(existing) == 2 and _existing_is_identical(result, content, inputs):
                typer.echo(f"{result.as_posix()}: criteria already written and identical")
                return
            raise CriteriaRefusalError(
                f"{result.as_posix()} already holds {existing} that differ from this evaluation "
                "(or are incomplete); nothing is overwritten"
            )
        provenance = {
            "schema": CRITERIA_SCHEMA,
            "timestamp_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            "command": [Path(sys.argv[0]).name, *sys.argv[1:]],
            "result_directory": checks["result_directory"],
            "block": {k: block.provenance.get(k) for k in ("block", "stage", "iteration")},
            "input_files": inputs,
            "git": {k: checks[k] for k in ("head", "upstream", "upstream_commit", "remote_url")},
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "dependencies": dependency_versions(DEPENDENCIES),
            # T4d (D-T4d-2): the analysis code and the environment of this evaluation
            "fingerprint": p1_fingerprint(Path.cwd() / "uv.lock"),
            "criteria_rows": len(results),
            "stage_requirements": {"stage": block.stage, "met": met},
        }
        with (result / CRITERIA_FILE).open("xb") as handle:
            handle.write(content)
        provenance["criteria_sha256"] = file_sha256(result / CRITERIA_FILE)
        with (result / CRITERIA_PROVENANCE_FILE).open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(provenance, indent=2, sort_keys=True) + "\n")
    except (CriteriaRefusalError, CriteriaError) as error:
        typer.echo(f"refused: {error}", err=True)
        raise typer.Exit(code=EXIT_REFUSED) from error
    typer.echo(
        f"{result.as_posix()}: {len(results)} criteria written; requirements of stage "
        f"{block.stage} met: {met}"
    )
