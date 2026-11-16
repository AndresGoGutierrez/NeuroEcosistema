"""F4 T3: atomic publication of result directories, failure directories and file hashes."""

import datetime as dt
import hashlib
import re

import pytest

from neuroeco.infrastructure.provenance import dependency_versions, file_sha256
from neuroeco.infrastructure.storage import (
    create_partial_directory,
    publish_directory,
    reserve_failure_directory,
)

NOW = dt.datetime(2026, 11, 15, 12, 30, 5, tzinfo=dt.UTC)


def test_partial_directory_is_published_in_one_rename(tmp_path) -> None:
    target = tmp_path / "calibration" / "iteration_001"
    partial = create_partial_directory(target)
    assert re.fullmatch(r"iteration_001\.partial-[0-9a-f]{8}", partial.name)
    assert partial.parent == target.parent and not target.exists()
    (partial / "episodes.csv").write_text("a\n", encoding="utf-8")
    publish_directory(partial, target)
    assert (target / "episodes.csv").read_text(encoding="utf-8") == "a\n"
    assert not partial.exists()


def test_existing_results_are_never_overwritten(tmp_path) -> None:
    target = tmp_path / "entry"
    target.mkdir()
    with pytest.raises(FileExistsError, match="never overwritten"):
        create_partial_directory(target)
    partial = tmp_path / "entry.partial-00000000"
    partial.mkdir()
    with pytest.raises(FileExistsError, match="never overwritten"):
        publish_directory(partial, target)
    assert partial.exists()


def test_partial_directories_are_unique(tmp_path) -> None:
    target = tmp_path / "entry"
    assert create_partial_directory(target) != create_partial_directory(target)


def test_failure_directories_are_unique_and_separate(tmp_path) -> None:
    target = tmp_path / "iteration_002"
    first = reserve_failure_directory(target, NOW)
    second = reserve_failure_directory(target, NOW)
    assert first != second and not target.exists()
    for directory in (first, second):
        assert re.fullmatch(r"iteration_002\.failed-20261115T123005Z-[0-9a-f]{8}", directory.name)

    partial = create_partial_directory(target)
    (partial / "provenance.json").write_text("{}", encoding="utf-8")
    moved = reserve_failure_directory(target, NOW, source=partial)
    assert not partial.exists() and (moved / "provenance.json").exists()
    with pytest.raises(ValueError, match="UTC"):
        reserve_failure_directory(target, dt.datetime(2026, 11, 15, 12, 30))


def test_file_sha256_and_dependency_versions(tmp_path) -> None:
    path = tmp_path / "spec.yaml"
    path.write_bytes(b"pilot: P1\n")
    assert file_sha256(path) == hashlib.sha256(b"pilot: P1\n").hexdigest()
    versions = dependency_versions(("numpy", "no-such-distribution-neuroeco"))
    assert versions["numpy"] and versions["no-such-distribution-neuroeco"] is None
