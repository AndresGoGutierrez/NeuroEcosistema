"""F5: ``neuroeco pilot i2`` (ADR-018, I2) on a reduced specification; the real result is checked
against its recorded hash and thresholds when it exists."""

import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import yaml
from typer.testing import CliRunner

from neuroeco.presentation.cli import app

ROOT = Path(__file__).resolve().parents[2]
REAL = ROOT / "results" / "pilots" / "f5_i2"


def small_spec(tmp_path) -> Path:
    spec = yaml.safe_load((ROOT / "configs" / "pilots" / "f5_reference.yaml").read_text("utf-8"))
    # A reduced run checks the mechanics; with 5 genomes the median of S3 is too noisy to judge,
    # so its threshold is relaxed here. The real result uses the approved 100 genomes.
    spec.update(episodes=1, genomes=5, s3_min=0.0)
    path = tmp_path / "spec.yaml"
    path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    return path


def run(spec: Path, output: Path):
    return CliRunner().invoke(
        app, ["pilot", "i2", "--spec", str(spec), "--output-dir", str(output)]
    )


def test_pilot_i2_writes_the_reference_set_and_the_saturation_checks(tmp_path) -> None:
    output = tmp_path / "i2"
    result = run(small_spec(tmp_path), output)
    assert result.exit_code == 0, result.output
    provenance = json.loads((output / "provenance.json").read_text("utf-8"))
    reference = output / "reference_observations.npz"
    assert provenance["reference"]["sha256"] == hashlib.sha256(reference.read_bytes()).hexdigest()
    with np.load(reference) as data:
        assert data["prey"].shape[1] == 10 and data["predator"].shape[1] == 7
        assert np.all(data["prey"][:, -1] > 0) and np.all(data["predator"][:, -1] > 0)
    with (output / "saturation_genomes.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert {r["network"] for r in rows} == {
        "prey_base",
        "prey_compact",
        "predator_base",
        "predator_compact",
    }
    assert len(rows) == 4 * 5 * (3 + 3 + 2)


def test_pilot_i2_is_reproducible(tmp_path) -> None:
    spec = small_spec(tmp_path)
    assert run(spec, tmp_path / "one").exit_code == 0
    assert run(spec, tmp_path / "two").exit_code == 0
    for name in ("reference_observations.npz", "saturation_genomes.csv", "saturation_summary.csv"):
        assert (tmp_path / "one" / name).read_bytes() == (tmp_path / "two" / name).read_bytes()


def test_pilot_i2_fails_when_a_threshold_is_missed(tmp_path) -> None:
    spec = small_spec(tmp_path)
    data = yaml.safe_load(spec.read_text("utf-8"))
    data["s3_min"] = 1.0
    spec.write_text(yaml.safe_dump(data), encoding="utf-8")
    result = run(spec, tmp_path / "i2")
    assert result.exit_code == 2 and "FAIL" in result.output
    provenance = json.loads((tmp_path / "i2" / "provenance.json").read_text("utf-8"))
    assert provenance["verdict"] == "FAIL"


def test_pilot_i2_never_overwrites(tmp_path) -> None:
    output = tmp_path / "i2"
    output.mkdir()
    result = run(small_spec(tmp_path), output)
    assert result.exit_code == 1 and "never overwritten" in result.output


def test_the_published_i2_result_meets_s1_s3() -> None:
    """Closure evidence of F5 (ADR-024): the committed result passes and matches its hash."""
    if not REAL.exists():
        return  # produced once by `neuroeco pilot i2` and then committed
    provenance = json.loads((REAL / "provenance.json").read_text("utf-8"))
    reference = REAL / "reference_observations.npz"
    assert provenance["reference"]["sha256"] == hashlib.sha256(reference.read_bytes()).hexdigest()
    assert provenance["verdict"] == "PASS"
    with (REAL / "saturation_summary.csv").open(encoding="utf-8") as handle:
        assert all(row["passed"] == "True" for row in csv.DictReader(handle))
