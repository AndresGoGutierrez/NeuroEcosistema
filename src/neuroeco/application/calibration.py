"""Pilot P1 (ecological calibration) specification: ADR-020 and ADR-033.

This module holds the P1 data model and the checks that need no episode results:

- the block specification (episodes and declared ``seed_group`` per scenario, P1-5, P1-13);
- the catalogue of the 35 conditions of a block (P1-14);
- candidate values and the iteration and round specifications (P1-17 to P1-19, T1-3);
- the translation of a candidate into per-scenario configuration overrides;
- state K of the calibration state machine: A1 and the B7 margin (P1-18);
- the episode key columns (P1-13) and the bootstrap keys (P1-20);
- the static validation of a sequence of iteration and round specifications.

Checks that depend on results (S_A met, "unsuccessful" iterations in D9, alternations caused by a
failed re-evaluation) belong to the calibration sequence verifier (task T4b). No function here
runs episodes.
"""

from __future__ import annotations

import dataclasses
import itertools
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import IntEnum

from neuroeco.application.seeding import Purpose, Stream, make_key
from neuroeco.domain.params import ConstraintCheck, WorldParams, calibration_checks
from neuroeco.domain.policies import PROBE_NAMES

PILOT_NAME = "P1"
SCENARIOS = ("A", "B", "C")
STAGES = ("A", "B", "C")

# ---------------------------------------------------------------- budgets (ADR-020, P1-18)
STAGE_ITERATION_LIMIT = 5
ROUND_LIMIT = 3
ALTERNATION_LIMIT = 3

# ---------------------------------------------------------------- bootstrap (ADR-032 S6, A6)
BOOTSTRAP_RESAMPLES = 9999
BOOTSTRAP_CONFIDENCE = 0.95

# ---------------------------------------------------------------- seed groups (ADR-028, P1-13)
RESERVED_SEED_GROUPS = {0: "exploratory", 1: "P0"}
MIN_BLOCK_EPISODES = 2  # the bootstrap needs at least two values per sample
ENTRY_EVALUATION_RUN = 0  # P1-20: run = 0 with the calibration group of A
CONFIRMATION_RUN = 0


# ---------------------------------------------------------------- conditions (P1-14)


@dataclass(frozen=True)
class Condition:
    """One condition of a block: the policy of each species, by reference-policy name."""

    name: str
    prey_policy: str
    predator_policy: str
    no_predators: bool = False


def _probe_conditions() -> tuple[Condition, ...]:
    prey = tuple(Condition(f"prey_probe_{p}", p.lower(), "rules") for p in PROBE_NAMES)
    predator = tuple(Condition(f"predator_probe_{p}", "rules", p.lower()) for p in PROBE_NAMES)
    return prey + predator


_COMMON_CONDITIONS = (
    Condition("rules", "rules", "rules"),
    Condition("random_prey", "random", "rules"),
    Condition("random_predator", "rules", "random"),
    *_probe_conditions(),
)
NO_PREDATORS = Condition("no_predators", "rules", "rules", no_predators=True)

CONDITIONS_BY_SCENARIO: Mapping[str, tuple[Condition, ...]] = {
    "A": (*_COMMON_CONDITIONS, NO_PREDATORS),
    "B": (*_COMMON_CONDITIONS, NO_PREDATORS),
    "C": _COMMON_CONDITIONS,
}


def condition(scenario: str, name: str) -> Condition:
    """The condition ``name`` of ``scenario``; unknown combinations are rejected."""
    for candidate in CONDITIONS_BY_SCENARIO[_scenario(scenario)]:
        if candidate.name == name:
            return candidate
    raise ValueError(f"condition {name!r} does not exist in scenario {scenario}")


def _scenario(scenario: str) -> str:
    if scenario not in SCENARIOS:
        raise ValueError(f"scenario must be one of {SCENARIOS}, got {scenario!r}")
    return scenario


# ---------------------------------------------------------------- block specification


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


@dataclass(frozen=True)
class ScenarioGroups:
    """Declared ``seed_group`` of each scenario in one block (one group per scenario)."""

    a: int
    b: int
    c: int

    def __post_init__(self) -> None:
        for name in ("a", "b", "c"):
            value = getattr(self, name)
            if not _is_int(value) or value < 0:
                raise ValueError(f"seed_groups.{name} must be a non-negative integer")
        if len({self.a, self.b, self.c}) != 3:
            raise ValueError("the three scenarios of a block need distinct seed_groups")

    def for_scenario(self, scenario: str) -> int:
        return getattr(self, _scenario(scenario).lower())


@dataclass(frozen=True)
class BlockSpec:
    episodes: int
    seed_groups: ScenarioGroups

    def __post_init__(self) -> None:
        if not _is_int(self.episodes) or self.episodes < MIN_BLOCK_EPISODES:
            raise ValueError(f"episodes must be an integer >= {MIN_BLOCK_EPISODES}")

    @property
    def total_episodes(self) -> int:
        """Episodes of the whole block: every condition of every scenario."""
        return self.episodes * sum(len(c) for c in CONDITIONS_BY_SCENARIO.values())


@dataclass(frozen=True)
class BlockSet:
    calibration: BlockSpec
    confirmation: BlockSpec
    second_confirmation: BlockSpec

    def named(self) -> dict[str, BlockSpec]:
        return {f.name: getattr(self, f.name) for f in dataclasses.fields(self)}


def _check_grid(name: str, values: tuple[float, ...]) -> None:
    if not values:
        raise ValueError(f"grid {name} must not be empty")
    if not all(_is_number(v) and 0.0 <= v <= 1.0 for v in values):
        raise ValueError(f"grid {name} values must be numbers in [0, 1]")
    if any(later <= earlier for earlier, later in itertools.pairwise(values)):
        raise ValueError(f"grid {name} must be strictly increasing")


@dataclass(frozen=True)
class Grids:
    """Rule-policy grids (P1-4): p_flee for the prey and u_cruise for both species."""

    prey_flee_threshold: tuple[float, ...]
    cruise_fraction: tuple[float, ...]

    def __post_init__(self) -> None:
        _check_grid("prey_flee_threshold", self.prey_flee_threshold)
        _check_grid("cruise_fraction", self.cruise_fraction)


@dataclass(frozen=True)
class P1Spec:
    """Pilot P1: blocks and grids. Fixed procedure values are code constants (T1-5)."""

    pilot: str
    blocks: BlockSet
    grids: Grids

    def __post_init__(self) -> None:
        if self.pilot != PILOT_NAME:
            raise ValueError(f"pilot must be {PILOT_NAME!r}, got {self.pilot!r}")
        declared = self.declared_seed_groups()
        if len(set(declared.values())) != len(declared):
            raise ValueError("every block and scenario of P1 needs its own seed_group")
        for name, group in declared.items():
            if group in RESERVED_SEED_GROUPS:
                owner = RESERVED_SEED_GROUPS[group]
                raise ValueError(f"{name}: seed_group {group} is reserved for {owner}")

    def declared_seed_groups(self) -> dict[str, int]:
        """``P1.<block>.<scenario>`` -> seed_group, for the uniqueness check of ADR-028."""
        return {
            f"{PILOT_NAME}.{block}.{scenario}": spec.seed_groups.for_scenario(scenario)
            for block, spec in self.blocks.named().items()
            for scenario in SCENARIOS
        }


# ---------------------------------------------------------------- candidate values (T1-3)


@dataclass(frozen=True)
class CandidateValues:
    """Complete snapshot of the eight adjustable values of one configuration.

    ``n_plants_a`` applies to A and C (C keeps the plants of A, ADR-029); ``n_predators`` of A
    and B is fixed by P1-6 and read from the base configuration.
    """

    plant_energy: float
    regrow_delay: int
    n_plants_a: int
    n_plants_b: int
    n_predators_c: int
    prey_flee_threshold: float
    prey_cruise_fraction: float
    predator_cruise_fraction: float

    def __post_init__(self) -> None:
        for name in ("regrow_delay", "n_plants_a", "n_plants_b", "n_predators_c"):
            if not _is_int(getattr(self, name)):
                raise ValueError(f"{name} must be an integer")
        for name in (*RULE_PARAMETERS, "plant_energy"):
            value = getattr(self, name)
            if not _is_number(value) or not math.isfinite(value):
                raise ValueError(f"{name} must be a finite number")
        if self.plant_energy <= 0:
            raise ValueError("plant_energy must be > 0")
        if self.regrow_delay < 1:
            raise ValueError("regrow_delay must be >= 1")
        if not 1 <= self.n_plants_b < self.n_plants_a:
            raise ValueError("plants must satisfy 1 <= n_plants_b < n_plants_a (P1-18)")
        for name in RULE_PARAMETERS:
            if not 0.0 <= getattr(self, name) <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")

    def differing(self, other: CandidateValues) -> tuple[str, ...]:
        """Names of the values that differ from ``other``, in declaration order."""
        return tuple(name for name in PARAMETERS if getattr(self, name) != getattr(other, name))


PARAMETERS = tuple(f.name for f in dataclasses.fields(CandidateValues))
RULE_PARAMETERS = ("prey_flee_threshold", "prey_cruise_fraction", "predator_cruise_fraction")
ENVIRONMENT_PARAMETERS = tuple(p for p in PARAMETERS if p not in RULE_PARAMETERS)
STAGE_PARAMETERS: Mapping[str, tuple[str, ...]] = {
    "A": ("plant_energy", "regrow_delay", "n_plants_a"),
    "B": ("n_plants_b",),
    "C": ("n_predators_c",),
}
NO_CHANGE = "none"


def check_candidate(values: CandidateValues, grids: Grids, n_predators_a: int) -> None:
    """Static constraints of a candidate that need the grids or the base configuration."""
    if values.n_predators_c <= n_predators_a:
        raise ValueError("n_predators_c must be > n_predators of A (P1-18)")
    if values.prey_flee_threshold not in grids.prey_flee_threshold:
        raise ValueError("prey_flee_threshold must belong to its grid (P1-4)")
    for name in ("prey_cruise_fraction", "predator_cruise_fraction"):
        if getattr(values, name) not in grids.cruise_fraction:
            raise ValueError(f"{name} must belong to the cruise_fraction grid (P1-4)")


def _check_text(name: str, value: object, *, required: bool) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    if required and not value.strip():
        raise ValueError(f"{name} must not be empty (P1-19)")


@dataclass(frozen=True)
class IterationSpec:
    """Pre-registered description of one calibration iteration (P1-19)."""

    iteration: int
    stage: str
    changed_parameter: str
    values: CandidateValues
    motive: str
    exploratory_observations: str

    def __post_init__(self) -> None:
        if not _is_int(self.iteration) or self.iteration < 1:
            raise ValueError("iteration must be an integer >= 1")
        if self.stage not in STAGES:
            raise ValueError(f"stage must be one of {STAGES}, got {self.stage!r}")
        allowed = (NO_CHANGE, *STAGE_PARAMETERS[self.stage])
        if self.changed_parameter not in allowed:
            raise ValueError(
                f"stage {self.stage} can only change {STAGE_PARAMETERS[self.stage]} "
                f"(or declare {NO_CHANGE!r}), got {self.changed_parameter!r}"
            )
        _check_text("motive", self.motive, required=True)
        _check_text("exploratory_observations", self.exploratory_observations, required=False)


@dataclass(frozen=True)
class RoundSpec:
    """Pre-registered description of one rule-tuning round (P1-17, P1-19).

    ``values`` are the values in force when the round starts; ``after_iteration`` is the stage-A
    iteration the round follows, which places the round in the calibration sequence.
    """

    round_number: int
    after_iteration: int
    values: CandidateValues
    motive: str
    exploratory_observations: str

    def __post_init__(self) -> None:
        if not _is_int(self.round_number) or not 1 <= self.round_number <= ROUND_LIMIT:
            raise ValueError(f"round_number must be an integer in [1, {ROUND_LIMIT}]")
        if not _is_int(self.after_iteration) or self.after_iteration < 1:
            raise ValueError("after_iteration must be an integer >= 1")
        _check_text("motive", self.motive, required=True)
        _check_text("exploratory_observations", self.exploratory_observations, required=False)


# ---------------------------------------------------------------- static sequence validation


def _ordered(
    iterations: Sequence[IterationSpec], rounds: Sequence[RoundSpec]
) -> list[IterationSpec | RoundSpec]:
    numbers = [spec.iteration for spec in iterations]
    if numbers != list(range(1, len(iterations) + 1)):
        raise ValueError("iterations must be numbered 1, 2, ... in order")
    round_numbers = [spec.round_number for spec in rounds]
    if round_numbers != list(range(1, len(rounds) + 1)):
        raise ValueError("rounds must be numbered 1, 2, ... in order")
    stage_of = {spec.iteration: spec.stage for spec in iterations}
    previous_anchor = 0
    for spec in rounds:
        if stage_of.get(spec.after_iteration) != "A":
            raise ValueError(f"round {spec.round_number} must follow a stage-A iteration")
        if spec.after_iteration < previous_anchor:
            raise ValueError("rounds must follow non-decreasing iterations")
        previous_anchor = spec.after_iteration

    sequence: list[IterationSpec | RoundSpec] = []
    for spec in iterations:
        sequence.append(spec)
        sequence.extend(r for r in rounds if r.after_iteration == spec.iteration)
    return sequence


def check_calibration_sequence(
    iterations: Sequence[IterationSpec],
    rounds: Sequence[RoundSpec],
    grids: Grids,
    n_predators_a: int,
) -> None:
    """Static rules of P1-18 over the pre-registered specifications (no results needed).

    - iterations numbered 1, 2, ...; iteration 1 is stage A with no change;
    - stages in the order A -> B -> C, never back; at most 5 iterations per stage;
    - at most 3 rounds, each after a stage-A iteration;
    - a round starts from the values of the step before it (rule values may change only as
      the outcome of a round);
    - each iteration changes exactly the declared parameter, except the first of each stage,
      which changes nothing;
    - an A iteration right after a round is an alternation: at most 3.
    """
    if not iterations:
        raise ValueError("the sequence needs at least one iteration")
    if len(rounds) > ROUND_LIMIT:
        raise ValueError(f"at most {ROUND_LIMIT} rounds (P1-18)")
    for spec in (*iterations, *rounds):
        check_candidate(spec.values, grids, n_predators_a)

    sequence = _ordered(iterations, rounds)
    counts = dict.fromkeys(STAGES, 0)
    alternations = 0
    previous: IterationSpec | RoundSpec | None = None
    previous_stage = None
    for spec in sequence:
        after_round = isinstance(previous, RoundSpec)
        if isinstance(spec, RoundSpec):
            assert previous is not None  # _ordered places every round after an iteration
            _check_unchanged(spec.values, previous.values, rules_free=after_round, spec=spec)
            previous = spec
            continue

        stage_index = STAGES.index(spec.stage)
        expected = 0 if previous_stage is None else STAGES.index(previous_stage)
        if stage_index < expected:
            raise ValueError(
                f"iteration {spec.iteration}: no return from stage {previous_stage} "
                f"to stage {spec.stage} (P1-18)"
            )
        if stage_index > expected + (previous_stage is not None):
            raise ValueError(f"iteration {spec.iteration}: stages run A -> B -> C without gaps")
        first_of_stage = spec.stage != previous_stage
        counts[spec.stage] += 1
        if counts[spec.stage] > STAGE_ITERATION_LIMIT:
            raise ValueError(f"stage {spec.stage}: at most {STAGE_ITERATION_LIMIT} iterations")
        if after_round and spec.stage == "A":
            alternations += 1
            if alternations > ALTERNATION_LIMIT:
                raise ValueError(f"at most {ALTERNATION_LIMIT} alternations (P1-18)")

        if first_of_stage:
            if spec.changed_parameter != NO_CHANGE:
                raise ValueError(
                    f"iteration {spec.iteration}: the first iteration of stage {spec.stage} "
                    f"evaluates the values in force and must declare {NO_CHANGE!r}"
                )
            if previous is not None:
                _check_unchanged(spec.values, previous.values, rules_free=after_round, spec=spec)
        else:
            if spec.changed_parameter == NO_CHANGE:
                raise ValueError(f"iteration {spec.iteration} must change exactly one parameter")
            assert previous is not None
            _check_single_change(spec, previous.values, rules_free=after_round)
        previous, previous_stage = spec, spec.stage


def _label(spec: IterationSpec | RoundSpec) -> str:
    if isinstance(spec, RoundSpec):
        return f"round {spec.round_number}"
    return f"iteration {spec.iteration}"


def _check_unchanged(
    current: CandidateValues,
    previous: CandidateValues,
    *,
    rules_free: bool,
    spec: IterationSpec | RoundSpec,
) -> None:
    allowed = RULE_PARAMETERS if rules_free else ()
    changed = [name for name in current.differing(previous) if name not in allowed]
    if changed:
        raise ValueError(f"{_label(spec)} must not change {changed}")


def _check_single_change(
    spec: IterationSpec, previous: CandidateValues, *, rules_free: bool
) -> None:
    changed = [
        name
        for name in spec.values.differing(previous)
        if not (rules_free and name in RULE_PARAMETERS)
    ]
    if changed != [spec.changed_parameter]:
        raise ValueError(
            f"iteration {spec.iteration} declares {spec.changed_parameter!r} but changes "
            f"{changed} (exactly one parameter per iteration, D10)"
        )


# ---------------------------------------------------------------- configuration overrides


def scenario_overrides(
    values: CandidateValues, scenario: str, *, no_predators: bool = False
) -> tuple[str, ...]:
    """``--set`` overrides that give ``scenario`` the candidate values.

    Overrides are applied after the scenario file, so each scenario gets its own explicit
    ``n_plants``: a generic override would otherwise replace the plants of B.
    """
    _scenario(scenario)
    if no_predators and scenario == "C":
        raise ValueError("the no_predators batch exists only in A and B (P1-8)")
    n_plants = values.n_plants_b if scenario == "B" else values.n_plants_a
    overrides = [
        f"world.plant_energy={values.plant_energy!r}",
        f"world.regrow_delay={values.regrow_delay}",
        f"world.n_plants={n_plants}",
        f"rules.prey.flee_threshold={values.prey_flee_threshold!r}",
        f"rules.prey.cruise_fraction={values.prey_cruise_fraction!r}",
        f"rules.predator.cruise_fraction={values.predator_cruise_fraction!r}",
    ]
    if scenario == "C":
        overrides.append(f"world.n_predators={values.n_predators_c}")
    if no_predators:
        overrides.append("world.n_predators=0")
    return tuple(overrides)


def condition_overrides(values: CandidateValues, scenario: str, name: str) -> tuple[str, ...]:
    """Overrides of one condition of one scenario."""
    return scenario_overrides(values, scenario, no_predators=condition(scenario, name).no_predators)


# ---------------------------------------------------------------- state K (A1 and B7)


def k5_margin(world: WorldParams) -> float:
    """B7: R_v,prey - (r_capture + (v_pred + v_prey) * ceil(pi / omega_prey)) (ADR-030, K5)."""
    reaction_steps = math.ceil(math.pi / world.prey.omega_max)
    closing = (world.predator.v_max + world.prey.v_max) * reaction_steps
    return world.prey.vision_radius - (world.capture_radius + closing)


@dataclass(frozen=True)
class Admissibility:
    """State K of the calibration state machine for one candidate (P1-18).

    K1-K4 hold by construction: a ``WorldParams`` that violates them cannot be built.
    """

    checks: tuple[tuple[str, ConstraintCheck], ...]  # (scenario, E1/E2/E5 check)
    design_problems: tuple[str, ...]  # one-factor design of ADR-029
    b7_margin: float

    @property
    def a1(self) -> bool:
        return all(check.satisfied for _, check in self.checks) and not self.design_problems

    @property
    def b7(self) -> bool:
        return self.b7_margin >= 0


_DESIGN_FACTORS = {"B": "n_plants", "C": "n_predators"}


def admissibility(worlds: Mapping[str, WorldParams]) -> Admissibility:
    """Evaluate A1 (E1, E2, E5 and the scenario design) and the B7 margin of A, B and C."""
    if set(worlds) != set(SCENARIOS):
        raise ValueError(f"admissibility needs the worlds of {SCENARIOS}")
    reference = worlds["A"]
    checks = tuple((s, check) for s in SCENARIOS for check in calibration_checks(worlds[s]))

    problems: list[str] = []
    for scenario, factor in _DESIGN_FACTORS.items():
        world = worlds[scenario]
        others = [
            f.name
            for f in dataclasses.fields(WorldParams)
            if f.name != factor and getattr(world, f.name) != getattr(reference, f.name)
        ]
        if others:
            problems.append(f"{scenario} differs from A in {others}, not only in {factor}")
    if not worlds["B"].n_plants < reference.n_plants:
        problems.append("B must have fewer plants than A")
    if not worlds["C"].n_predators > reference.n_predators:
        problems.append("C must have more predators than A")
    return Admissibility(checks, tuple(problems), k5_margin(reference))


# ---------------------------------------------------------------- seed keys (P1-13, P1-20)

EPISODE_STREAMS: Mapping[str, Stream] = {
    "stream_env_init": Stream.ENV_INIT,
    "stream_env_dynamics": Stream.ENV_DYNAMICS,
    "stream_policy_prey": Stream.POLICY_PREY,
    "stream_policy_predator": Stream.POLICY_PREDATOR,
}
KEY_COMMON_COLUMNS = ("purpose", "seed_group", "run", "generation", "item")
KEY_COLUMNS = (*KEY_COMMON_COLUMNS, *EPISODE_STREAMS)


def episode_key_columns(seed_group: int, item: int) -> dict[str, int]:
    """The nine key columns of one P1 episode (P1-13): purpose PILOT, run 0, generation 0."""
    for stream in EPISODE_STREAMS.values():  # validates every field through make_key
        make_key(Purpose.PILOT, seed_group, 0, 0, item, stream)
    columns = {
        "purpose": int(Purpose.PILOT),
        "seed_group": seed_group,
        "run": 0,
        "generation": 0,
        "item": item,
    }
    columns.update({name: int(stream) for name, stream in EPISODE_STREAMS.items()})
    return columns


def keys_from_columns(columns: Mapping[str, int]) -> dict[str, tuple[int, ...]]:
    """The six-integer key of each of the four streams, rebuilt from the nine columns."""
    missing = [name for name in KEY_COLUMNS if name not in columns]
    if missing:
        raise ValueError(f"missing key columns: {missing}")
    common = tuple(int(columns[name]) for name in KEY_COMMON_COLUMNS)
    return {name: (*common, int(columns[name])) for name in EPISODE_STREAMS}


class Comparison(IntEnum):
    """Bootstrap comparisons of a block (P1-20)."""

    A6_B_VS_A = 1
    A6_C_VS_A = 2
    B2_PREY_A = 3
    B2_PREY_B = 4
    B2_PREY_C = 5
    B2_PREDATOR_A = 6
    B2_PREDATOR_B = 7
    B2_PREDATOR_C = 8


def bootstrap_key(block: BlockSpec, run: int, comparison: Comparison) -> tuple[int, ...]:
    """``(ANALYSIS, seed_group of A in the block, run, 0, comparison, BOOTSTRAP)`` (P1-20).

    ``run`` is the iteration number in calibration (>= 1), or 0 for the entry evaluation (with
    the calibration block) and for a confirmation block.
    """
    if not isinstance(comparison, Comparison):
        raise ValueError(f"comparison must be a Comparison member, got {comparison!r}")
    return make_key(
        Purpose.ANALYSIS, block.seed_groups.a, run, 0, int(comparison), Stream.BOOTSTRAP
    )
