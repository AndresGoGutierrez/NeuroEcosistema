"""F6: ``neuroeco pilot p0b`` on a reduced specification (decision A3, O4)."""

import csv
import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from neuroeco.presentation.cli import app

ROOT = Path(__file__).resolve().parents[2]


def test_p0b_measures_every_cell_in_interleaved_rounds_and_the_speedup(tmp_path) -> None:
    spec = yaml.safe_load((ROOT / "configs" / "pilots" / "p0b.yaml").read_text("utf-8"))
    spec.update(
        repetitions=2,
        speedup_workers=[1, 2],
        speedup_genomes=2,
        speedup_episodes=1,
        speedup_repetitions=1,
    )
    path = tmp_path / "p0b.yaml"
    path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    output = tmp_path / "p0b"
    result = CliRunner().invoke(
        app,
        [
            "pilot",
            "p0b",
            "--spec",
            str(path),
            "--output-dir",
            str(output),
            "--config-dir",
            str(ROOT / "configs"),
        ],
    )
    assert result.exit_code == 0, result.output
    with (output / "p0b_cells.csv").open(encoding="utf-8") as handle:
        cells = list(csv.DictReader(handle))
    assert len(cells) == 2 * 4  # every cell once per round (O4)
    for round_ in ("0", "1"):
        measured = {(r["n_prey"], r["policy"]) for r in cells if r["round"] == round_}
        assert measured == {("25", "rules"), ("25", "neural"), ("50", "rules"), ("50", "neural")}
    summary = json.loads((output / "p0b_summary.json").read_text("utf-8"))
    assert set(summary["forward_overhead_us_per_step"]) == {"25/3", "50/8"}
    assert summary["speedup"]["1"] == 1.0 and "power_state" in summary


def test_p0b_never_overwrites(tmp_path) -> None:
    (tmp_path / "p0b").mkdir()
    result = CliRunner().invoke(app, ["pilot", "p0b", "--output-dir", str(tmp_path / "p0b")])
    assert result.exit_code == 1 and "never overwritten" in result.output
