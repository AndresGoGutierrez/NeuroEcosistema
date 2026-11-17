"""F4 T4d (D-T4d-4): finding the reserved root of the real P1 results from any spelling."""

import json
import os
import subprocess
import sys

import pytest

from neuroeco.infrastructure.p1_reserved import (
    RESERVED_FILE,
    ReservedRootError,
    read_reserved,
    reserved_document,
    reserved_root,
    same_directory,
)


@pytest.fixture
def root(tmp_path):
    directory = tmp_path / "results" / "pilots" / "p1"
    directory.mkdir(parents=True)
    document = reserved_document("a" * 64, {"code": {}, "environment": {}})
    (directory / RESERVED_FILE).write_text(json.dumps(document), encoding="utf-8")
    return directory


def test_the_marker_is_found_from_the_root_and_below(root, tmp_path) -> None:
    assert same_directory(reserved_root(root), root)
    assert same_directory(reserved_root(root / "calibration" / "iteration_001"), root)
    assert reserved_root(tmp_path / "results" / "pilots") is None
    assert reserved_root(tmp_path / "elsewhere") is None


def test_relative_paths_and_dot_dot_reach_the_marker(root, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    detour = os.path.join("results", "pilots", "x", "..", "p1")
    assert same_directory(reserved_root(type(root)(detour)), root)


@pytest.mark.skipif(sys.platform != "win32", reason="case-insensitive file system (Windows)")
def test_another_case_and_a_trailing_dot_reach_the_marker_on_windows(root, tmp_path) -> None:
    for spelling in ("RESULTS/Pilots/P1", "results/pilots/p1."):
        assert same_directory(reserved_root(tmp_path / spelling), root)


def test_a_link_to_the_root_reaches_the_marker(root, tmp_path) -> None:
    link = tmp_path / "link"
    if sys.platform == "win32":  # a junction needs no special privilege
        created = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(root)], capture_output=True, check=False
        )
        if created.returncode != 0:
            pytest.skip("junctions are not available")
    else:
        link.symlink_to(root, target_is_directory=True)
    assert same_directory(reserved_root(link / "calibration"), root)


def test_an_invalid_marker_is_refused(tmp_path) -> None:
    (tmp_path / RESERVED_FILE).write_text(json.dumps({"schema": "other"}), encoding="utf-8")
    with pytest.raises(ReservedRootError, match="not a valid"):
        read_reserved(tmp_path)
    (tmp_path / RESERVED_FILE).write_text("{", encoding="utf-8")
    with pytest.raises(ReservedRootError, match="cannot be read"):
        read_reserved(tmp_path)
