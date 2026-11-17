"""F4 T4d (D-T4d-4): the reserved root of the real P1 results.

Temporary directories only, with simulated git facts; with the real seed groups the block runner
is replaced by a guard, so no real episode can start. The project repository is never touched.
"""

import copy
import json
import sys

import pytest
from typer.testing import CliRunner

from neuroeco.application import calibration
from neuroeco.infrastructure.provenance import file_sha256
from neuroeco.presentation import pilot_p1, pilot_p1_sequence
from neuroeco.presentation.cli import app
from p1_support import (
    SYNTHETIC_SPEC,
    invoke,
    make_configs,
    only_failure,
    register,
    run_ok,
    simulate_git,
    write_spec,
)


class EpisodeGuardError(Exception):
    """Raised instead of running the first episode."""


@pytest.fixture
def setup(tmp_path, monkeypatch):
    output = tmp_path / "results" / "pilots" / "p1"
    configs = make_configs(tmp_path)
    state = simulate_git(monkeypatch, output)

    def guard(*args, **kwargs):
        raise EpisodeGuardError("an episode with real seed groups was about to start")

    monkeypatch.setattr(pilot_p1, "iter_block", guard)
    return configs, output, state


def approved(configs) -> None:
    spec = copy.deepcopy(SYNTHETIC_SPEC)
    for block, (episodes, groups) in calibration.APPROVED_BLOCKS.items():
        spec["blocks"][block] = {
            "episodes": episodes,
            "seed_groups": dict(zip("abc", groups, strict=True)),
        }
    write_spec(configs, spec)


def reserve(configs, output):
    arguments = ["pilot", "p1-reserve", "--spec", str(configs / "pilots" / "p1.yaml")]
    return CliRunner().invoke(app, [*arguments, "--output-root", str(output)])


def contents(output) -> list[str]:
    return sorted(p.relative_to(output).as_posix() for p in output.rglob("*"))


def test_reserving_needs_the_approved_table_and_an_empty_root(setup) -> None:
    configs, output, _ = setup
    assert reserve(configs, output).exit_code == 1  # synthetic specification
    approved(configs)
    (output / "stray").mkdir(parents=True)
    assert reserve(configs, output).exit_code == 1  # not empty
    (output / "stray").rmdir()
    assert reserve(configs, output).exit_code == 0
    marker = json.loads((output / "RESERVED.json").read_text(encoding="utf-8"))
    assert marker["p1_spec_sha256"] == file_sha256(configs / "pilots" / "p1.yaml")
    assert set(marker["fingerprint"]) == {"code", "environment"}
    assert reserve(configs, output).exit_code == 1  # already reserved


def spellings(output):
    yield output
    yield output.parent / "x" / ".." / output.name
    if sys.platform == "win32":
        yield output.parent / output.name.upper()


@pytest.mark.parametrize("index", [0, 1, 2])
def test_a_synthetic_specification_never_writes_under_the_reserved_root(setup, index) -> None:
    configs, output, _ = setup
    approved(configs)
    assert reserve(configs, output).exit_code == 0
    candidates = list(spellings(output))
    if index >= len(candidates):
        pytest.skip("case-insensitive spelling only on Windows")
    write_spec(configs, SYNTHETIC_SPEC)
    for root in (candidates[index], output / "calibration"):
        arguments = ["pilot", "p1", "--iteration", str(register(configs, 1, "A")), "--spec"]
        arguments += [str(configs / "pilots" / "p1.yaml"), "--config-dir", str(configs)]
        result = CliRunner().invoke(app, [*arguments, "--output-root", str(root)])
        assert result.exit_code == 1 and "refused" in result.output
    assert contents(output) == ["RESERVED.json"]  # nothing written, not even a failure record


def test_another_specification_with_the_approved_table_is_refused(setup) -> None:
    configs, output, _ = setup
    approved(configs)
    assert reserve(configs, output).exit_code == 0
    spec = configs / "pilots" / "p1.yaml"
    spec.write_text(spec.read_text(encoding="utf-8") + "# edited\n", encoding="utf-8")
    result = invoke(configs, output, "--iteration", str(register(configs, 1, "A")))
    assert result.exit_code == 1 and "not the reserved spec" in result.output
    assert contents(output) == ["RESERVED.json"]


def test_the_real_table_runs_only_at_a_reserved_root(setup) -> None:
    configs, output, _ = setup
    approved(configs)
    result = invoke(configs, output, "--iteration", str(register(configs, 1, "A")))
    assert result.exit_code == 1
    _, failure = only_failure(output)
    assert "reserved by RESERVED.json" in failure["message"]


def test_a_different_fingerprint_from_the_reference_stops(setup, monkeypatch) -> None:
    configs, output, _ = setup
    approved(configs)
    assert reserve(configs, output).exit_code == 0
    real = pilot_p1.p1_fingerprint

    def changed(uv_lock):
        current = real(uv_lock)
        current["environment"] = {**current["environment"], "os": ["Other", "0", "0"]}
        return current

    monkeypatch.setattr(pilot_p1, "p1_fingerprint", changed)
    result = invoke(configs, output, "--iteration", str(register(configs, 1, "A")))
    assert result.exit_code == 1
    _, failure = only_failure(output)
    assert "STOP" in failure["message"] and "environment.os" in failure["message"]


def test_unexpected_content_of_the_reserved_root_is_detected(setup) -> None:
    """What another command (view, pilot p0) or a deleted specification leaves is refused."""
    configs, output, _ = setup
    approved(configs)
    assert reserve(configs, output).exit_code == 0
    register(configs, 1, "A")
    allowed = [
        "calibration/iteration_001/provenance.json",
        "calibration/iteration_001/criteria.csv",
        "calibration/iteration_001.failed-20261117T000000Z-0001/failure.json",
        "calibration/iteration_001.partial-0002/episodes.csv.tmp",
    ]
    foreign = [
        "p0_episodes.csv",
        "20261117T000000Z-abcd1234/session.json",
        "calibration/iteration_002/provenance.json",
        "calibration/notes.txt",
        "calibration/iteration_001/extra.csv",
    ]
    for name in allowed + foreign:
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")
    registry = pilot_p1.load_registry(configs / "pilots" / "p1.yaml")
    problems = pilot_p1_sequence.reserved_content_problems(output, registry)
    assert problems == sorted([*foreign, "20261117T000000Z-abcd1234", "calibration/iteration_002"])


def test_the_criteria_command_refuses_a_foreign_block_under_the_reserved_root(
    tmp_path, monkeypatch
) -> None:
    configs = make_configs(tmp_path)
    synthetic = tmp_path / "synthetic"
    simulate_git(monkeypatch, synthetic)
    run_ok(configs, synthetic, "--iteration", str(register(configs, 1, "A")))
    output = tmp_path / "results" / "pilots" / "p1"
    approved(configs)
    assert reserve(configs, output).exit_code == 0
    block = output / "calibration" / "iteration_001"
    block.mkdir(parents=True)
    for path in (synthetic / "calibration" / "iteration_001").iterdir():
        (block / path.name).write_bytes(path.read_bytes())
    result = CliRunner().invoke(app, ["pilot", "p1-criteria", "--result", str(block)])
    assert result.exit_code == 1 and "not produced by the reserved specification" in result.output
    assert not (block / "criteria.csv").exists()
