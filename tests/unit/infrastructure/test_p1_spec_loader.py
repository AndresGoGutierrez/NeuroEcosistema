"""F4 T1: loading of the P1 specification and of iteration and round specifications.

The only use of the real ``configs/pilots/p1.yaml`` is the passive read that pins it to
ADR-033 (authorized in the T1 plan). Every other specification is synthetic, with seed_group
>= 1000 (D16). No episode is run.
"""

import dataclasses
from pathlib import Path

import pytest
import yaml

from neuroeco.application.calibration import (
    SCENARIOS,
    BlockSet,
    BlockSpec,
    CandidateValues,
    Grids,
    IterationSpec,
    P1Spec,
    RoundSpec,
    ScenarioGroups,
    admissibility,
    condition_overrides,
    scenario_overrides,
)
from neuroeco.infrastructure.config_loader import (
    ConfigError,
    load_config,
    load_iteration_spec,
    load_p0_spec,
    load_p1_spec,
    load_round_spec,
)

CONFIGS = Path(__file__).resolve().parents[3] / "configs"
P1_SPEC = CONFIGS / "pilots" / "p1.yaml"
PROVISIONAL = CandidateValues(
    plant_energy=30.0,
    regrow_delay=50,
    n_plants_a=40,
    n_plants_b=15,
    n_predators_c=8,
    prey_flee_threshold=0.3,
    prey_cruise_fraction=0.5,
    predator_cruise_fraction=0.5,
)
# The values frozen by P1 (iteration 007, ADR-034), reproduced by the real configs.
FROZEN = dataclasses.replace(
    PROVISIONAL,
    n_plants_b=4,
    n_predators_c=5,
    prey_flee_threshold=0.2,
    prey_cruise_fraction=0.3,
    predator_cruise_fraction=0.7,
)
SYNTHETIC = {
    "pilot": "P1",
    "blocks": {
        "calibration": {"episodes": 4, "seed_groups": {"a": 1000, "b": 1001, "c": 1002}},
        "confirmation": {"episodes": 5, "seed_groups": {"a": 1010, "b": 1011, "c": 1012}},
        "second_confirmation": {"episodes": 5, "seed_groups": {"a": 1020, "b": 1021, "c": 1022}},
    },
    "grids": {"prey_flee_threshold": [0.2, 0.3, 0.4, 0.5], "cruise_fraction": [0.3, 0.5, 0.7]},
}


def existing_groups() -> dict[str, int]:
    return {"exploratory": 0, "P0": load_p0_spec(CONFIGS / "pilots" / "p0.yaml").seed_group}


def write(tmp_path: Path, content: dict, name: str = "spec.yaml") -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(content), encoding="utf-8")
    return path


# ---------------------------------------------------------------- the real specification


def test_real_p1_specification_matches_adr_033() -> None:
    """Passive read of configs/pilots/p1.yaml (P1-4, P1-5, P1-13). Nothing is executed."""
    spec = load_p1_spec(P1_SPEC, existing_groups())
    assert spec == P1Spec(
        pilot="P1",
        blocks=BlockSet(
            calibration=BlockSpec(30, ScenarioGroups(10, 11, 12)),
            confirmation=BlockSpec(50, ScenarioGroups(20, 21, 22)),
            second_confirmation=BlockSpec(50, ScenarioGroups(30, 31, 32)),
        ),
        grids=Grids(prey_flee_threshold=(0.2, 0.3, 0.4, 0.5), cruise_fraction=(0.3, 0.5, 0.7)),
    )
    assert spec.blocks.calibration.total_episodes == 1050
    assert spec.blocks.confirmation.total_episodes == 1750
    # P1-20: the bootstrap keys of P1 use the A group of each block, reserved for P1
    assert [block.seed_groups.a for block in spec.blocks.named().values()] == [10, 20, 30]


def test_provisional_rule_values_belong_to_the_real_grids() -> None:
    """Tie rule 1 of P1-17 needs the values in force to be part of the grids."""
    grids = load_p1_spec(P1_SPEC, existing_groups()).grids
    rules = load_config(CONFIGS, "A").rules
    assert rules.prey.flee_threshold in grids.prey_flee_threshold
    assert rules.prey.cruise_fraction in grids.cruise_fraction
    assert rules.predator.cruise_fraction in grids.cruise_fraction


# ---------------------------------------------------------------- loader strictness


def test_synthetic_specification_loads(tmp_path) -> None:
    spec = load_p1_spec(write(tmp_path, SYNTHETIC), existing_groups())
    assert spec.blocks.calibration == BlockSpec(4, ScenarioGroups(1000, 1001, 1002))


def test_unknown_and_missing_keys_are_rejected(tmp_path) -> None:
    unknown = {**SYNTHETIC, "budgets": {"rounds": 3}}
    with pytest.raises(ConfigError, match=r"spec\.yaml: unknown keys: spec\.budgets"):
        load_p1_spec(write(tmp_path, unknown), {})
    missing = {key: value for key, value in SYNTHETIC.items() if key != "grids"}
    with pytest.raises(ConfigError, match=r"spec\.yaml: missing keys: spec\.grids"):
        load_p1_spec(write(tmp_path, missing), {})


def test_wrong_types_are_rejected(tmp_path) -> None:
    content = yaml.safe_load(yaml.safe_dump(SYNTHETIC))
    content["blocks"]["calibration"]["episodes"] = "30"
    with pytest.raises(ConfigError, match="expected an integer"):
        load_p1_spec(write(tmp_path, content), {})


def test_seed_groups_of_other_configurations_are_rejected(tmp_path) -> None:
    with pytest.raises(ConfigError, match="seed_group 1011 is declared by both"):
        load_p1_spec(write(tmp_path, SYNTHETIC), {"other pilot": 1011})


def test_reserved_groups_are_rejected_by_the_loader(tmp_path) -> None:
    content = yaml.safe_load(yaml.safe_dump(SYNTHETIC))
    content["blocks"]["confirmation"]["seed_groups"]["b"] = 1
    with pytest.raises(ConfigError, match="seed_group 1 is reserved for P0"):
        load_p1_spec(write(tmp_path, content), {})


# ---------------------------------------------------------------- iteration and round specs


def test_iteration_and_round_specifications_load(tmp_path) -> None:
    values = dataclasses.asdict(PROVISIONAL)
    iteration = {
        "iteration": 1,
        "stage": "A",
        "changed_parameter": "none",
        "values": values,
        "motive": "synthetic motive",
        "exploratory_observations": "",
    }
    assert load_iteration_spec(write(tmp_path, iteration, "001.yaml")) == IterationSpec(
        1, "A", "none", PROVISIONAL, "synthetic motive", ""
    )
    round_content = {
        "round_number": 1,
        "after_iteration": 1,
        "values": values,
        "motive": "synthetic motive",
        "exploratory_observations": "",
    }
    assert load_round_spec(write(tmp_path, round_content, "01.yaml")) == RoundSpec(
        1, 1, PROVISIONAL, "synthetic motive", ""
    )


def test_invalid_iteration_specification_names_the_file(tmp_path) -> None:
    content = {
        "iteration": 2,
        "stage": "B",
        "changed_parameter": "plant_energy",
        "values": dataclasses.asdict(PROVISIONAL),
        "motive": "synthetic motive",
        "exploratory_observations": "",
    }
    path = write(tmp_path, content, "002.yaml")
    with pytest.raises(ConfigError, match=r"002\.yaml: stage B can only change"):
        load_iteration_spec(path)


# ---------------------------------------------------------------- overrides on the real configs


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_frozen_candidate_preserves_the_resolved_configuration(scenario: str) -> None:
    """The candidate of the frozen values reproduces A, B and C exactly, hash included."""
    plain = load_config(CONFIGS, scenario)
    overridden = load_config(CONFIGS, scenario, scenario_overrides(FROZEN, scenario))
    assert overridden == plain
    assert overridden.config_hash == plain.config_hash


@pytest.mark.parametrize("scenario", ["A", "B"])
def test_no_predators_changes_only_the_number_of_predators(scenario: str) -> None:
    plain = load_config(CONFIGS, scenario)
    batch = load_config(CONFIGS, scenario, condition_overrides(FROZEN, scenario, "no_predators"))
    assert batch.world == dataclasses.replace(plain.world, n_predators=0)
    assert batch.rules == plain.rules
    assert batch.config_hash != plain.config_hash


def test_a_new_candidate_reaches_each_scenario() -> None:
    candidate = dataclasses.replace(
        PROVISIONAL,
        plant_energy=35.0,
        regrow_delay=40,
        n_plants_a=45,
        n_plants_b=12,
        n_predators_c=9,
        prey_flee_threshold=0.4,
        prey_cruise_fraction=0.3,
        predator_cruise_fraction=0.7,
    )
    resolved = {s: load_config(CONFIGS, s, scenario_overrides(candidate, s)) for s in SCENARIOS}
    for config in resolved.values():
        assert (config.world.plant_energy, config.world.regrow_delay) == (35.0, 40)
        assert config.rules.prey.flee_threshold == 0.4
        assert config.rules.prey.cruise_fraction == 0.3
        assert config.rules.predator.cruise_fraction == 0.7
    a, b, c = (resolved[s].world for s in SCENARIOS)
    assert (a.n_plants, a.n_predators) == (45, 3)
    assert (b.n_plants, b.n_predators) == (12, 3)
    assert (c.n_plants, c.n_predators) == (45, 9)
    assert admissibility({s: resolved[s].world for s in SCENARIOS}).a1


def test_state_k_on_the_provisional_configuration() -> None:
    result = admissibility({s: load_config(CONFIGS, s).world for s in SCENARIOS})
    assert result.a1 and result.b7
    assert result.b7_margin == pytest.approx(1.4)
