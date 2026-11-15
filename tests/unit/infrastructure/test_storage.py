"""Storage helpers: atomic JSON replacement and unique run directories (ADR-031)."""

import datetime as dt
import json
import re

import pytest

from neuroeco.infrastructure.storage import new_run_directory, replace_json

NOW = dt.datetime(2026, 11, 15, 18, 30, 5, tzinfo=dt.UTC)


def test_replace_json_writes_and_replaces_without_leftovers(tmp_path) -> None:
    path = tmp_path / "nested" / "session.json"
    replace_json(path, {"status": "running", "steps": None})
    assert json.loads(path.read_text(encoding="utf-8")) == {"status": "running", "steps": None}
    replace_json(path, {"status": "completed", "steps": 12})
    assert json.loads(path.read_text(encoding="utf-8"))["status"] == "completed"
    assert [p.name for p in path.parent.iterdir()] == ["session.json"]


def test_replace_json_rejects_nan_and_keeps_the_previous_version(tmp_path) -> None:
    path = tmp_path / "session.json"
    replace_json(path, {"value": 1.0})
    with pytest.raises(ValueError):
        replace_json(path, {"value": float("nan")})
    assert json.loads(path.read_text(encoding="utf-8")) == {"value": 1.0}


def test_run_directories_are_unique_and_named_in_utc(tmp_path) -> None:
    created = {new_run_directory(tmp_path / "view", NOW) for _ in range(20)}
    assert len(created) == 20
    for directory in created:
        assert directory.is_dir()
        assert re.fullmatch(r"20261115T183005Z-[0-9a-f]{8}", directory.name)


def test_run_directory_requires_a_utc_datetime(tmp_path) -> None:
    with pytest.raises(ValueError, match="UTC"):
        new_run_directory(tmp_path, dt.datetime(2026, 11, 15, 18, 30))  # naive
    bogota = dt.timezone(dt.timedelta(hours=-5))
    with pytest.raises(ValueError, match="UTC"):
        new_run_directory(tmp_path, NOW.astimezone(bogota))
