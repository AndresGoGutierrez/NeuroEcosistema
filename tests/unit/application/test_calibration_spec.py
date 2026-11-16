"""F4 T1: P1 specification, condition catalogue, overrides, state K and seed keys (ADR-033).

Every specification here is synthetic and uses seed_group >= 1000 (D16): the real P1 groups
are never used by tests. No episode is run.
"""

import dataclasses
import math

import numpy as np
import pytest

from neuroeco.analysis import stats
from neuroeco.application.calibration import (
    ALTERNATION_LIMIT,
    BOOTSTRAP_CONFIDENCE,
    BOOTSTRAP_RESAMPLES,
    CONDITIONS_BY_SCENARIO,
    ENTRY_EVALUATION_RUN,
    KEY_COLUMNS,
    RESERVED_SEED_GROUPS,
    ROUND_LIMIT,
    STAGE_ITERATION_LIMIT,
    BlockSet,
    BlockSpec,
    CandidateValues,
    Comparison,
    Grids,
    IterationSpec,
    P1Spec,
    RoundSpec,
    ScenarioGroups,
    admissibility,
    bootstrap_key,
    check_calibration_sequence,
    check_candidate,
    condition,
    condition_overrides,
    episode_key_columns,
    k5_margin,
    keys_from_columns,
    scenario_overrides,
)
from neuroeco.application.seeding import Purpose, SeedRegistry, Stream
from neuroeco.bootstrap import REFERENCE_POLICIES
from support import PROVISIONAL_WORLD

SEED = 151810796106167051982782525292607188790  # configs/base.yaml (no P1 seed group used)
GRIDS = Grids(prey_flee_threshold=(0.2, 0.3, 0.4, 0.5), cruise_fraction=(0.3, 0.5, 0.7))
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
N_PREDATORS_A = 3


def groups(first: int) -> ScenarioGroups:
    return ScenarioGroups(first, first + 1, first + 2)


def synthetic_spec(**blocks: BlockSpec) -> P1Spec:
    default = {
        "calibration": BlockSpec(4, groups(1000)),
        "confirmation": BlockSpec(5, groups(1010)),
        "second_confirmation": BlockSpec(5, groups(1020)),
    }
    return P1Spec("P1", BlockSet(**{**default, **blocks}), GRIDS)


def iteration(number: int, stage: str, changed: str = "none", **values) -> IterationSpec:
    return IterationSpec(
        iteration=number,
        stage=stage,
        changed_parameter=changed,
        values=dataclasses.replace(PROVISIONAL, **values),
        motive="synthetic test motive",
        exploratory_observations="",
    )


def round_spec(number: int, after: int, **values) -> RoundSpec:
    return RoundSpec(
        round_number=number,
        after_iteration=after,
        values=dataclasses.replace(PROVISIONAL, **values),
        motive="synthetic test motive",
        exploratory_observations="",
    )


def check(iterations, rounds=()) -> None:
    check_calibration_sequence(iterations, rounds, GRIDS, N_PREDATORS_A)


# ---------------------------------------------------------------- constants (T1-5)


def test_procedure_constants_match_adr_033() -> None:
    assert (STAGE_ITERATION_LIMIT, ROUND_LIMIT, ALTERNATION_LIMIT) == (5, 3, 3)
    assert RESERVED_SEED_GROUPS == {0: "exploratory", 1: "P0"}
    assert ENTRY_EVALUATION_RUN == 0


def test_bootstrap_constants_match_the_statistics_module() -> None:
    assert BOOTSTRAP_RESAMPLES == stats.BOOTSTRAP_RESAMPLES == 9999
    assert BOOTSTRAP_CONFIDENCE == stats.BOOTSTRAP_CONFIDENCE == 0.95


# ---------------------------------------------------------------- conditions (P1-14)


def test_condition_catalogue_has_35_conditions() -> None:
    sizes = {scenario: len(conditions) for scenario, conditions in CONDITIONS_BY_SCENARIO.items()}
    assert sizes == {"A": 12, "B": 12, "C": 11}
    names_c = [c.name for c in CONDITIONS_BY_SCENARIO["C"]]
    assert names_c == [
        "rules",
        "random_prey",
        "random_predator",
        "prey_probe_STILL",
        "prey_probe_SPIN",
        "prey_probe_STRAIGHT_MAX",
        "prey_probe_STRAIGHT_CRUISE",
        "predator_probe_STILL",
        "predator_probe_SPIN",
        "predator_probe_STRAIGHT_MAX",
        "predator_probe_STRAIGHT_CRUISE",
    ]
    for scenario in "AB":
        last = CONDITIONS_BY_SCENARIO[scenario][-1]
        assert (last.name, last.no_predators) == ("no_predators", True)
    every = [c for conditions in CONDITIONS_BY_SCENARIO.values() for c in conditions]
    assert sum(c.no_predators for c in every) == 2
    assert {c.prey_policy for c in every} | {c.predator_policy for c in every} <= set(
        REFERENCE_POLICIES
    )


def test_block_episode_totals() -> None:
    assert BlockSpec(30, groups(1000)).total_episodes == 1050
    assert BlockSpec(50, groups(1000)).total_episodes == 1750


def test_unknown_condition_is_rejected() -> None:
    assert condition("A", "no_predators").no_predators
    with pytest.raises(ValueError, match="does not exist in scenario C"):
        condition("C", "no_predators")
    with pytest.raises(ValueError, match="scenario must be one of"):
        condition("D", "rules")


# ---------------------------------------------------------------- block specification


def test_synthetic_spec_declares_nine_distinct_groups() -> None:
    declared = synthetic_spec().declared_seed_groups()
    assert len(declared) == 9 and min(declared.values()) >= 1000
    assert declared["P1.confirmation.B"] == 1011


@pytest.mark.parametrize("reserved", [0, 1])
def test_reserved_seed_groups_are_rejected(reserved: int) -> None:
    with pytest.raises(ValueError, match=f"seed_group {reserved} is reserved"):
        synthetic_spec(calibration=BlockSpec(4, ScenarioGroups(reserved, 1001, 1002)))


def test_a_seed_group_cannot_be_shared_by_two_blocks() -> None:
    with pytest.raises(ValueError, match="its own seed_group"):
        synthetic_spec(confirmation=BlockSpec(5, groups(1002)))


def test_block_validation() -> None:
    with pytest.raises(ValueError, match="distinct seed_groups"):
        ScenarioGroups(1000, 1000, 1001)
    with pytest.raises(ValueError, match="episodes must be an integer >= 2"):
        BlockSpec(1, groups(1000))
    with pytest.raises(ValueError, match="pilot must be 'P1'"):
        P1Spec("P0", synthetic_spec().blocks, GRIDS)


@pytest.mark.parametrize(
    ("flee", "cruise", "message"),
    [
        ((), (0.5,), "must not be empty"),
        ((0.3, 0.2), (0.5,), "strictly increasing"),
        ((0.2, 0.2), (0.5,), "strictly increasing"),
        ((0.2,), (0.5, 1.5), r"in \[0, 1\]"),
    ],
)
def test_grid_validation(flee, cruise, message) -> None:
    with pytest.raises(ValueError, match=message):
        Grids(flee, cruise)


# ---------------------------------------------------------------- candidate values


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"n_plants_b": 40}, "n_plants_b < n_plants_a"),
        ({"n_plants_b": 0}, "n_plants_b < n_plants_a"),
        ({"plant_energy": 0.0}, "plant_energy must be > 0"),
        ({"regrow_delay": 0}, "regrow_delay must be >= 1"),
        ({"regrow_delay": 50.0}, "regrow_delay must be an integer"),
        ({"n_predators_c": True}, "n_predators_c must be an integer"),
        ({"prey_cruise_fraction": 1.5}, r"in \[0, 1\]"),
        ({"plant_energy": math.inf}, "finite number"),
    ],
)
def test_candidate_validation(change, message) -> None:
    with pytest.raises(ValueError, match=message):
        dataclasses.replace(PROVISIONAL, **change)


def test_candidate_against_grids_and_base() -> None:
    check_candidate(PROVISIONAL, GRIDS, N_PREDATORS_A)
    with pytest.raises(ValueError, match="n_predators_c must be >"):
        check_candidate(dataclasses.replace(PROVISIONAL, n_predators_c=3), GRIDS, N_PREDATORS_A)
    with pytest.raises(ValueError, match="prey_flee_threshold must belong"):
        check_candidate(
            dataclasses.replace(PROVISIONAL, prey_flee_threshold=0.35), GRIDS, N_PREDATORS_A
        )
    with pytest.raises(ValueError, match="predator_cruise_fraction must belong"):
        check_candidate(
            dataclasses.replace(PROVISIONAL, predator_cruise_fraction=0.6), GRIDS, N_PREDATORS_A
        )


def test_specification_validation() -> None:
    with pytest.raises(ValueError, match="stage B can only change"):
        iteration(2, "B", "plant_energy")
    with pytest.raises(ValueError, match="stage must be one of"):
        iteration(2, "D")
    with pytest.raises(ValueError, match="motive must not be empty"):
        dataclasses.replace(iteration(1, "A"), motive="  ")
    with pytest.raises(ValueError, match=r"round_number must be an integer in \[1, 3\]"):
        round_spec(4, 1)


# ---------------------------------------------------------------- static sequence (P1-18)


def test_a_complete_valid_sequence_is_accepted() -> None:
    it2 = {"plant_energy": 35.0}
    tuned = {"prey_flee_threshold": 0.4, "predator_cruise_fraction": 0.7}
    it3 = {**it2, **tuned, "regrow_delay": 40}
    tuned_again = {**it3, "prey_cruise_fraction": 0.3}
    iterations = [
        iteration(1, "A"),
        iteration(2, "A", "plant_energy", **it2),
        iteration(3, "A", "regrow_delay", **it3),  # alternation: rules changed by round 1
        iteration(4, "B", **tuned_again),  # first of B, after round 2
        iteration(5, "B", "n_plants_b", **tuned_again, n_plants_b=12),
        iteration(6, "C", **tuned_again, n_plants_b=12),
        iteration(7, "C", "n_predators_c", **tuned_again, n_plants_b=12, n_predators_c=10),
    ]
    rounds = [round_spec(1, 2, **it2), round_spec(2, 3, **it3)]
    check(iterations, rounds)


def test_an_iteration_must_change_exactly_the_declared_parameter() -> None:
    with pytest.raises(ValueError, match=r"changes \['plant_energy', 'regrow_delay'\]"):
        check(
            [
                iteration(1, "A"),
                iteration(2, "A", "plant_energy", plant_energy=35.0, regrow_delay=40),
            ]
        )
    with pytest.raises(ValueError, match=r"declares 'regrow_delay' but changes \['plant_energy'\]"):
        check([iteration(1, "A"), iteration(2, "A", "regrow_delay", plant_energy=35.0)])
    with pytest.raises(ValueError, match=r"declares 'plant_energy' but changes \[\]"):
        check([iteration(1, "A"), iteration(2, "A", "plant_energy")])
    with pytest.raises(ValueError, match="must change exactly one parameter"):
        check([iteration(1, "A"), iteration(2, "A")])


def test_rule_values_change_only_through_a_round() -> None:
    with pytest.raises(ValueError, match=r"changes \['plant_energy', 'prey_flee_threshold'\]"):
        check(
            [
                iteration(1, "A"),
                iteration(2, "A", "plant_energy", plant_energy=35.0, prey_flee_threshold=0.4),
            ]
        )
    with pytest.raises(ValueError, match=r"iteration 2 must not change \['prey_flee_threshold'\]"):
        check([iteration(1, "A"), iteration(2, "B", prey_flee_threshold=0.4)])


def test_the_first_iteration_of_a_stage_changes_nothing() -> None:
    with pytest.raises(ValueError, match="first iteration of stage A"):
        check([iteration(1, "A", "plant_energy", plant_energy=35.0)])
    with pytest.raises(ValueError, match="first iteration of stage B"):
        check([iteration(1, "A"), iteration(2, "B", "n_plants_b", n_plants_b=12)])
    with pytest.raises(ValueError, match=r"iteration 2 must not change \['n_plants_b'\]"):
        check([iteration(1, "A"), iteration(2, "B", n_plants_b=12)])


def test_stage_order_has_no_return_and_no_gaps() -> None:
    with pytest.raises(ValueError, match="no return from stage B to stage A"):
        check(
            [
                iteration(1, "A"),
                iteration(2, "B"),
                iteration(3, "A", "regrow_delay", regrow_delay=40),
            ]
        )
    with pytest.raises(ValueError, match="A -> B -> C without gaps"):
        check([iteration(1, "A"), iteration(2, "C")])
    with pytest.raises(ValueError, match="A -> B -> C without gaps"):
        check([iteration(1, "B")])


def test_at_most_five_iterations_per_stage() -> None:
    sequence = [iteration(1, "A")]
    for number in range(2, 7):
        sequence.append(iteration(number, "A", "regrow_delay", regrow_delay=50 + number))
    check(sequence[:5])
    with pytest.raises(ValueError, match="stage A: at most 5 iterations"):
        check(sequence)


def test_round_placement_and_budget() -> None:
    with pytest.raises(ValueError, match="at most 3 rounds"):
        check([iteration(1, "A")], [round_spec(n, 1) for n in (1, 2, 3)] + [round_spec(3, 1)])
    with pytest.raises(ValueError, match="round 1 must follow a stage-A iteration"):
        check([iteration(1, "A"), iteration(2, "B")], [round_spec(1, 2)])
    with pytest.raises(ValueError, match="round 1 must follow a stage-A iteration"):
        check([iteration(1, "A")], [round_spec(1, 5)])
    with pytest.raises(ValueError, match=r"round 1 must not change \['plant_energy'\]"):
        check([iteration(1, "A")], [round_spec(1, 1, plant_energy=35.0)])
    with pytest.raises(ValueError, match="rounds must be numbered"):
        check([iteration(1, "A")], [round_spec(2, 1)])
    with pytest.raises(ValueError, match="iterations must be numbered"):
        check([iteration(1, "A"), iteration(3, "A", "regrow_delay", regrow_delay=40)])


def test_consecutive_rounds_may_change_rule_values_only() -> None:
    first = {"prey_flee_threshold": 0.4}
    check([iteration(1, "A")], [round_spec(1, 1), round_spec(2, 1, **first)])
    with pytest.raises(ValueError, match=r"round 2 must not change \['regrow_delay'\]"):
        check([iteration(1, "A")], [round_spec(1, 1), round_spec(2, 1, regrow_delay=40)])


def test_sequence_checks_candidates_against_the_grids() -> None:
    with pytest.raises(ValueError, match="prey_flee_threshold must belong"):
        check([iteration(1, "A", prey_flee_threshold=0.25)])


# ---------------------------------------------------------------- overrides


def test_scenario_overrides_give_each_scenario_its_own_values() -> None:
    common = (
        "world.plant_energy=30.0",
        "world.regrow_delay=50",
    )
    rules = (
        "rules.prey.flee_threshold=0.3",
        "rules.prey.cruise_fraction=0.5",
        "rules.predator.cruise_fraction=0.5",
    )
    assert scenario_overrides(PROVISIONAL, "A") == (*common, "world.n_plants=40", *rules)
    assert scenario_overrides(PROVISIONAL, "B") == (*common, "world.n_plants=15", *rules)
    assert scenario_overrides(PROVISIONAL, "C") == (
        *common,
        "world.n_plants=40",
        *rules,
        "world.n_predators=8",
    )
    assert condition_overrides(PROVISIONAL, "B", "no_predators")[-1] == "world.n_predators=0"
    assert condition_overrides(PROVISIONAL, "A", "rules") == scenario_overrides(PROVISIONAL, "A")
    with pytest.raises(ValueError, match="only in A and B"):
        scenario_overrides(PROVISIONAL, "C", no_predators=True)


# ---------------------------------------------------------------- state K (A1, B7)


def worlds(**per_scenario: dict) -> dict:
    base = {
        "A": PROVISIONAL_WORLD,
        "B": dataclasses.replace(PROVISIONAL_WORLD, n_plants=15),
        "C": dataclasses.replace(PROVISIONAL_WORLD, n_predators=8),
    }
    for scenario, change in per_scenario.items():
        base[scenario] = dataclasses.replace(base[scenario], **change)
    return base


def test_k5_margin_of_the_provisional_world() -> None:
    assert k5_margin(PROVISIONAL_WORLD) == pytest.approx(20.0 - (2.5 + 2.3 * 7))
    assert k5_margin(PROVISIONAL_WORLD) == pytest.approx(1.4)


def test_provisional_worlds_are_admissible() -> None:
    result = admissibility(worlds())
    assert result.a1 and result.b7 and not result.design_problems
    assert len(result.checks) == 3 * 5  # E1 and E2 per species and E5, in each scenario


def test_e5_violation_fails_a1() -> None:
    too_rich = {"plant_energy": 60.0}
    result = admissibility(worlds(A=too_rich, B=too_rich, C=too_rich))
    assert not result.a1
    failed = {(s, c.constraint_id) for s, c in result.checks if not c.satisfied}
    assert failed == {("A", "E5"), ("B", "E5"), ("C", "E5")}


def test_scenarios_must_change_only_their_factor() -> None:
    result = admissibility(worlds(B={"regrow_delay": 40}))
    assert not result.a1
    assert result.design_problems == ("B differs from A in ['regrow_delay'], not only in n_plants",)
    result = admissibility(worlds(C={"n_predators": 3}))
    assert result.design_problems == ("C must have more predators than A",)
    result = admissibility(worlds(B={"n_plants": 40}))
    assert result.design_problems == ("B must have fewer plants than A",)
    with pytest.raises(ValueError, match="needs the worlds of"):
        admissibility({"A": PROVISIONAL_WORLD})


# ---------------------------------------------------------------- seed keys (P1-13, P1-20)


def test_episode_key_columns() -> None:
    columns = episode_key_columns(1000, 7)
    assert tuple(columns) == KEY_COLUMNS
    assert columns == {
        "purpose": 1,
        "seed_group": 1000,
        "run": 0,
        "generation": 0,
        "item": 7,
        "stream_env_init": 3,
        "stream_env_dynamics": 4,
        "stream_policy_prey": 5,
        "stream_policy_predator": 6,
    }
    assert keys_from_columns(columns) == {
        "stream_env_init": (1, 1000, 0, 0, 7, 3),
        "stream_env_dynamics": (1, 1000, 0, 0, 7, 4),
        "stream_policy_prey": (1, 1000, 0, 0, 7, 5),
        "stream_policy_predator": (1, 1000, 0, 0, 7, 6),
    }
    with pytest.raises(ValueError, match="item must be an integer"):
        episode_key_columns(1000, -1)
    with pytest.raises(ValueError, match="missing key columns"):
        keys_from_columns({k: v for k, v in columns.items() if k != "stream_policy_prey"})


@pytest.mark.parametrize(("seed_group", "item"), [(1000, 0), (1001, 29), (1002, 49)])
def test_key_columns_rebuild_exactly_the_episode_streams(seed_group: int, item: int) -> None:
    """NumPy reconstruction from the nine columns == SeedRegistry.episode_streams (P1-13)."""
    expected = SeedRegistry(SEED).episode_streams(Purpose.PILOT, seed_group, 0, 0, item)
    keys = keys_from_columns(episode_key_columns(seed_group, item))
    for column, attribute in [
        ("stream_env_init", "env_init"),
        ("stream_env_dynamics", "env_dynamics"),
        ("stream_policy_prey", "policy_prey"),
        ("stream_policy_predator", "policy_predator"),
    ]:
        rebuilt = np.random.default_rng(np.random.SeedSequence(SEED, spawn_key=keys[column]))
        generator = getattr(expected, attribute)
        assert rebuilt.bit_generator.state == generator.bit_generator.state
        assert np.array_equal(rebuilt.random(8), generator.random(8))


def test_streams_of_an_episode_are_distinct() -> None:
    keys = keys_from_columns(episode_key_columns(1000, 3))
    states = {
        str(np.random.default_rng(np.random.SeedSequence(SEED, spawn_key=k)).bit_generator.state)
        for k in keys.values()
    }
    assert len(states) == 4


def test_bootstrap_keys() -> None:
    block = BlockSpec(4, groups(1000))
    assert [int(c) for c in Comparison] == list(range(1, 9))
    assert bootstrap_key(block, 3, Comparison.A6_B_VS_A) == (5, 1000, 3, 0, 1, 7)
    assert bootstrap_key(block, ENTRY_EVALUATION_RUN, Comparison.B2_PREDATOR_C) == (
        5,
        1000,
        0,
        0,
        8,
        7,
    )
    with pytest.raises(ValueError, match="Comparison member"):
        bootstrap_key(block, 1, 1)


def test_bootstrap_key_rebuilds_the_registry_generator() -> None:
    key = bootstrap_key(BlockSpec(4, groups(1000)), 2, Comparison.A6_C_VS_A)
    rebuilt = np.random.default_rng(np.random.SeedSequence(SEED, spawn_key=key))
    expected = SeedRegistry(SEED).generator(Purpose.ANALYSIS, 1000, 2, 0, 2, Stream.BOOTSTRAP)
    assert rebuilt.bit_generator.state == expected.bit_generator.state
