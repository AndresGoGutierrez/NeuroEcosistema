"""T4 (F2): content of the `view` session record (ADR-031, decisions V2 and V3)."""

import json
import math
from pathlib import Path

from neuroeco.application.evaluation import EpisodeIdentity, run_episode
from neuroeco.application.seeding import Purpose
from neuroeco.bootstrap import EXPLORATORY_SEED_GROUP, build_policy, build_runtime
from neuroeco.infrastructure.storage import replace_json
from neuroeco.presentation.cli import VIEW_RECORD_SCHEMA, build_view_record, metrics_to_json

CONFIGS = Path(__file__).resolve().parents[3] / "configs"
OVERRIDES = ("world.n_predators=10", "world.t_max=80", "rules.prey.flee_threshold=0.4")


def make_record():
    config = build_runtime("C", OVERRIDES, CONFIGS).config
    identity = EpisodeIdentity(Purpose.PILOT, EXPLORATORY_SEED_GROUP, item=7)
    record = build_view_record(
        session_id="20261115T183005Z-0123abcd",
        config=config,
        overrides=OVERRIDES,
        prey_policy="rules",
        predator_policy="random",
        identity=identity,
        viewer_options={"paused": True, "speed": 1, "fps": 30, "exit_at_end": False},
        provenance={"git_commit": "abc", "git_dirty": False, "timestamp_utc": "t"},
    )
    return config, record


def test_record_keeps_overrides_hash_seeds_and_provenance() -> None:
    config, record = make_record()
    assert record["schema"] == VIEW_RECORD_SCHEMA and record["status"] == "running"
    assert record["overrides"] == list(OVERRIDES)  # literal and in order
    assert record["config_hash"] == config.config_hash
    assert record["project_seed"] == config.project_seed
    assert record["seed_identity"] == {
        "purpose": "PILOT",
        "purpose_code": 1,
        "seed_group": 0,
        "run": 0,
        "generation": 0,
        "item": 7,
    }
    assert record["world"]["n_predators"] == 10 and record["world"]["t_max"] == 80
    assert record["rules"]["prey"]["flee_threshold"] == 0.4
    assert record["policies"] == {"prey": "rules", "predator": "random"}
    assert record["provenance"]["git_commit"] == "abc"
    assert record["steps_completed"] is None and record["metrics"] is None


def test_record_is_valid_strict_json(tmp_path) -> None:
    _, record = make_record()
    path = tmp_path / "session.json"
    replace_json(path, record)  # allow_nan=False: fails if anything is not strict JSON
    assert json.loads(path.read_text(encoding="utf-8")) == record


def test_metrics_are_serialized_exactly() -> None:
    runtime = build_runtime("A", ("world.t_max=60",), CONFIGS)
    config = runtime.config
    result = run_episode(
        config.world,
        build_policy("still", "prey", config),
        build_policy("still", "predator", config),
        runtime.registry,
        EpisodeIdentity(Purpose.PILOT, EXPLORATORY_SEED_GROUP),
    )
    data = metrics_to_json(result.metrics)
    metrics = result.metrics
    assert data["prey_survival"] == {
        "numerator": metrics.prey_survival.numerator,
        "denominator": metrics.prey_survival.denominator,
    }
    assert data["steps"] == metrics.steps == 60
    assert math.isnan(metrics.median_capture_step_among_captured)  # no capture with STILL
    assert data["median_capture_step_among_captured"] is None
    assert json.loads(json.dumps(data, allow_nan=False)) == data
