"""F4 T3 and T3b: atomic publication of result directories, failure directories, bounded retries
of the renames and file hashes."""

import datetime as dt
import hashlib
import re

import pytest

from neuroeco.infrastructure import storage
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


def flaky_rename(monkeypatch, failures: int, error: type[OSError] = PermissionError) -> list:
    """os.rename of the storage module fails ``failures`` times, then works (T3b, M-10)."""
    real, calls = storage.os.rename, []

    def rename(source, target) -> None:
        calls.append(target)
        if len(calls) <= failures:
            raise error("synthetic lock")
        real(source, target)

    monkeypatch.setattr(storage.os, "rename", rename)
    return calls


def test_publication_retries_a_transient_lock(tmp_path, monkeypatch) -> None:
    target = tmp_path / "iteration_001"
    partial = create_partial_directory(target)
    calls, waits = flaky_rename(monkeypatch, failures=2), []
    publish_directory(partial, target, sleep=waits.append)
    assert target.is_dir() and not partial.exists()
    assert len(calls) == 3 and waits == [0.2, 0.4]


def test_publication_gives_up_after_the_bounded_attempts(tmp_path, monkeypatch) -> None:
    target = tmp_path / "iteration_001"
    partial = create_partial_directory(target)
    calls, waits = flaky_rename(monkeypatch, failures=99), []
    with pytest.raises(PermissionError):
        publish_directory(partial, target, sleep=waits.append)
    assert len(calls) == storage.RENAME_ATTEMPTS == 5
    assert waits == [0.2, 0.4, 0.8, 1.6]  # at most 3 s in total
    assert partial.is_dir() and not target.exists()


def test_other_rename_errors_are_not_retried(tmp_path, monkeypatch) -> None:
    target = tmp_path / "iteration_001"
    partial = create_partial_directory(target)
    calls, waits = flaky_rename(monkeypatch, failures=1, error=OSError), []
    with pytest.raises(OSError, match="synthetic lock"):
        publish_directory(partial, target, sleep=waits.append)
    assert len(calls) == 1 and waits == []


def test_a_target_created_between_attempts_is_never_overwritten(tmp_path, monkeypatch) -> None:
    target = tmp_path / "iteration_001"
    partial = create_partial_directory(target)
    flaky_rename(monkeypatch, failures=1)
    with pytest.raises(FileExistsError, match="never overwritten"):
        publish_directory(partial, target, sleep=lambda _: target.mkdir())
    assert partial.is_dir() and not any(target.iterdir())


def test_failure_directory_rename_is_retried(tmp_path, monkeypatch) -> None:
    target = tmp_path / "iteration_001"
    partial = create_partial_directory(target)
    waits: list = []
    flaky_rename(monkeypatch, failures=1)
    moved = reserve_failure_directory(target, NOW, source=partial, sleep=waits.append)
    assert moved.is_dir() and not partial.exists() and waits == [0.2]


def test_file_sha256_and_dependency_versions(tmp_path) -> None:
    path = tmp_path / "spec.yaml"
    path.write_bytes(b"pilot: P1\n")
    assert file_sha256(path) == hashlib.sha256(b"pilot: P1\n").hexdigest()
    versions = dependency_versions(("numpy", "no-such-distribution-neuroeco"))
    assert versions["numpy"] and versions["no-such-distribution-neuroeco"] is None
