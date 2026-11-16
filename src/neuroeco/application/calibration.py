"""Pilot P1 (ecological calibration): ADR-020 and ADR-033.

Specification (F4 T1), with no episode results needed:

- the block specification (episodes and declared ``seed_group`` per scenario, P1-5, P1-13);
- the catalogue of the 35 conditions of a block (P1-14);
- candidate values and the iteration and round specifications (P1-17 to P1-19, T1-3);
- the translation of a candidate into per-scenario configuration overrides;
- state K of the calibration state machine: A1 and the B7 margin (P1-18);
- the episode key columns (P1-13) and the bootstrap keys (P1-20);
- the static validation of a sequence of iteration and round specifications.

Execution (F4 T2):

- the A2 invariant checker, a read-only observer of the simulation (P1-22);
- the planning and the execution of the episodes of a block.

Result rows (F4 T3), pure computations used by the ``pilot p1`` command:

- the scenarios of each stage, the independent check of a block's seed groups;
- one ``episodes.csv`` row per episode (P1-13, P1-16) and the ``bootstrap_keys.csv`` rows
  (P1-20). Columns and types are documented in ``docs/p1_data_dictionary.md``.

Protections (F4 T3b): the approved seed groups and sizes of P1-13 and P1-5 whenever a real group
is declared, and the exact plan of a block.

Checks that depend on results (S_A met, "unsuccessful" iterations in D9, alternations caused by a
failed re-evaluation) belong to the calibration sequence verifier (task T4b). The criteria are
evaluated by ``analysis`` (task T4). File writing and provenance belong to the command.
"""

from __future__ import annotations

import dataclasses
import itertools
import math
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import IntEnum

import numpy as np

from neuroeco.application.configs import ResolvedConfig
from neuroeco.application.evaluation import EpisodeIdentity, EpisodeResult, run_episode
from neuroeco.application.metrics import EARLY_CAPTURE_FRACTION_OF_T_MAX
from neuroeco.application.seeding import Purpose, SeedRegistry, Stream, make_key
from neuroeco.application.session import initial_world
from neuroeco.domain.geometry import pairwise_distances
from neuroeco.domain.params import (
    ConstraintCheck,
    SpeciesParams,
    WorldParams,
    calibration_checks,
)
from neuroeco.domain.policies import PROBE_NAMES, Policy
from neuroeco.domain.simulator import StepTrace
from neuroeco.domain.state import NOT_DEAD, DeathCause, SpeciesState, WorldState

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


# ---------------------------------------------------------------- A2 invariant checker (P1-22)

SAFE_DISTANCE = "safe_distance_at_s0"
PREY_IDENTITY = "prey_identity"
PREDATOR_IDENTITY = "predator_identity"
PREY_ENERGY = "prey_energy"
PREDATOR_ENERGY = "predator_energy"
FIRST_STEP_CAPTURE = "no_capture_in_first_step"
A2_INVARIANTS = (
    SAFE_DISTANCE,
    PREY_IDENTITY,
    PREDATOR_IDENTITY,
    PREY_ENERGY,
    PREDATOR_ENERGY,
    FIRST_STEP_CAPTURE,
)


class InvariantViolationError(RuntimeError):
    """An A2 invariant does not hold. ``step`` is None for the initial state S_0."""

    def __init__(self, invariant: str, step: int | None, detail: str) -> None:
        where = "S0" if step is None else f"step {step}"
        super().__init__(f"A2 violated ({invariant}) at {where}: {detail}")
        self.invariant = invariant
        self.step = step
        self.detail = detail


class InvariantChecker:
    """Read-only observer of one episode that checks the A2 invariants of ADR-033 (P1-22).

    - S_0: every predator is at distance >= d_safe from every prey (``check_initial``);
    - every step: living + captured + starved prey = n_prey; living + starved predators =
      n_predators; 0 < e <= E_max for every living agent; no capture in the first step (step 0).

    It only reads the state passed to it: it never writes arrays, never receives or uses a
    random generator and never changes the course of the episode. A violation raises
    ``InvariantViolationError``; nothing is corrected or hidden.
    """

    def __init__(self, params: WorldParams) -> None:
        self._params = params
        self.initial_checked = False
        self.steps_checked = 0

    def check_initial(self, world: WorldState) -> None:
        if world.step != 0:
            raise ValueError(f"S_0 must be at step 0, got step {world.step}")
        distances = pairwise_distances(
            world.predators.positions, world.prey.positions, self._params.size
        )
        d_safe = self._params.safe_distance
        if distances.size and float(distances.min()) < d_safe:
            predator, prey = np.unravel_index(int(np.argmin(distances)), distances.shape)
            raise InvariantViolationError(
                SAFE_DISTANCE,
                None,
                f"predator {predator} starts at {float(distances.min()):.6g} from prey {prey}, "
                f"below d_safe = {d_safe}",
            )
        self.initial_checked = True

    def __call__(self, trace: StepTrace) -> None:
        if trace.step != self.steps_checked:
            raise RuntimeError(
                f"the A2 checker expected step {self.steps_checked} and received {trace.step}"
            )
        world, params = trace.world, self._params
        self._check_identity(
            PREY_IDENTITY,
            world.prey,
            params.n_prey,
            (DeathCause.CAPTURED, DeathCause.STARVATION),
            trace.step,
        )
        self._check_identity(
            PREDATOR_IDENTITY,
            world.predators,
            params.n_predators,
            (DeathCause.STARVATION,),
            trace.step,
        )
        self._check_energy(PREY_ENERGY, world.prey, params.prey, trace.step)
        self._check_energy(PREDATOR_ENERGY, world.predators, params.predator, trace.step)
        if trace.step == 0 and trace.captures.consumers.size:
            raise InvariantViolationError(
                FIRST_STEP_CAPTURE,
                trace.step,
                f"{trace.captures.consumers.size} capture(s) in the first step",
            )
        self.steps_checked += 1

    @staticmethod
    def _check_identity(
        invariant: str,
        species: SpeciesState,
        expected: int,
        causes: tuple[DeathCause, ...],
        step: int,
    ) -> None:
        alive = int(np.count_nonzero(species.alive))
        dead = {
            cause.name.lower(): int(np.count_nonzero(species.death_cause == cause))
            for cause in causes
        }
        if alive + sum(dead.values()) != expected:
            raise InvariantViolationError(invariant, step, f"alive {alive} + {dead} != {expected}")

    @staticmethod
    def _check_energy(
        invariant: str, species: SpeciesState, params: SpeciesParams, step: int
    ) -> None:
        living = np.flatnonzero(species.alive)
        energy = species.energy[living]
        valid = (energy > 0.0) & (energy <= params.e_max)
        if not bool(np.all(valid)):
            first = int(np.flatnonzero(~valid)[0])
            raise InvariantViolationError(
                invariant,
                step,
                f"living agent {int(living[first])} has energy {float(energy[first])!r}, "
                f"outside (0, {params.e_max}]",
            )


# ---------------------------------------------------------------- block execution

CONFIRMATION_BLOCKS = ("confirmation", "second_confirmation")
ConfigResolver = Callable[[str, tuple[str, ...]], ResolvedConfig]
PolicyFactory = Callable[[str, str, ResolvedConfig], Policy]


@dataclass(frozen=True)
class EpisodeTask:
    """One episode of a block: scenario, condition, seed coordinates and overrides."""

    block: str
    scenario: str
    condition: Condition
    seed_group: int
    item: int
    overrides: tuple[str, ...]

    @property
    def identity(self) -> EpisodeIdentity:
        """P1-13: purpose PILOT, run 0, generation 0."""
        return EpisodeIdentity(Purpose.PILOT, self.seed_group, run=0, generation=0, item=self.item)

    @property
    def label(self) -> str:
        return (
            f"{self.block}/{self.scenario}/{self.condition.name}/"
            f"seed_group {self.seed_group}/item {self.item}"
        )


def plan_block(
    spec: P1Spec,
    block: str,
    values: CandidateValues,
    scenarios: Sequence[str] = SCENARIOS,
    conditions: Sequence[str] | None = None,
) -> tuple[EpisodeTask, ...]:
    """Episodes of ``block`` for the candidate ``values``, in a fixed order.

    Order: scenario (A, B, C) -> condition (catalogue order) -> item. ``scenarios`` and
    ``conditions`` select subsets (stages run some scenarios; rule-tuning rounds run only
    ``rules``); every selected condition must exist in every selected scenario.
    """
    blocks = spec.blocks.named()
    if block not in blocks:
        raise ValueError(f"unknown block {block!r}; expected one of {tuple(blocks)}")
    for scenario in scenarios:
        _scenario(scenario)
    if not scenarios or len(set(scenarios)) != len(scenarios):
        raise ValueError("scenarios must be a non-empty selection without repetitions")
    selected = [s for s in SCENARIOS if s in scenarios]
    if conditions is not None and (not conditions or len(set(conditions)) != len(conditions)):
        raise ValueError("conditions must be a non-empty selection without repetitions")

    block_spec = blocks[block]
    tasks: list[EpisodeTask] = []
    for scenario in selected:
        catalogue = CONDITIONS_BY_SCENARIO[scenario]
        if conditions is not None:
            for name in conditions:
                condition(scenario, name)  # rejects names missing from this scenario
        chosen = [c for c in catalogue if conditions is None or c.name in conditions]
        group = block_spec.seed_groups.for_scenario(scenario)
        for chosen_condition in chosen:
            overrides = condition_overrides(values, scenario, chosen_condition.name)
            tasks.extend(
                EpisodeTask(block, scenario, chosen_condition, group, item, overrides)
                for item in range(block_spec.episodes)
            )
    return tuple(tasks)


class A2ViolationError(RuntimeError):
    """An A2 invariant failed: the block stops and the author is consulted (P1-22)."""

    def __init__(self, task: EpisodeTask, violation: InvariantViolationError) -> None:
        super().__init__(f"{task.label}: {violation}")
        self.task = task
        self.violation = violation


@dataclass(frozen=True)
class EpisodeOutcome:
    """Everything one executed episode provides to the P1 command (T3)."""

    task: EpisodeTask
    config_hash: str
    key_columns: dict[str, int]
    result: EpisodeResult
    steps_checked: int


def iter_block(
    tasks: Sequence[EpisodeTask],
    resolve: ConfigResolver,
    make_policy: PolicyFactory,
    *,
    confirmation_authorized: bool = False,
) -> Iterator[EpisodeOutcome]:
    """Run the episodes of ``tasks`` in order, each watched by an A2 checker.

    ``resolve(scenario, overrides)`` and ``make_policy(name, species, config)`` are supplied by
    the composition root (configuration loader and reference policies). Episodes of a
    confirmation block run only with ``confirmation_authorized=True`` (P1-21, D16).

    The iteration stops at the first error. An A2 violation becomes ``A2ViolationError``; any
    other error keeps its type and gets a note naming the episode. Nothing is skipped.
    """
    tasks = tuple(tasks)
    blocked = sorted({t.block for t in tasks if t.block in CONFIRMATION_BLOCKS})
    if blocked and not confirmation_authorized:
        raise PermissionError(
            f"block(s) {blocked} need the author's explicit authorization (P1-21, D16)"
        )
    return _execute(tasks, resolve, make_policy)


def _execute(
    tasks: tuple[EpisodeTask, ...], resolve: ConfigResolver, make_policy: PolicyFactory
) -> Iterator[EpisodeOutcome]:
    configs: dict[tuple[str, tuple[str, ...]], ResolvedConfig] = {}
    registry: SeedRegistry | None = None
    for task in tasks:
        try:
            key = (task.scenario, task.overrides)
            if key not in configs:
                configs[key] = resolve(task.scenario, task.overrides)
            config = configs[key]
            if config.scenario != task.scenario:
                raise ValueError(f"resolved scenario {config.scenario!r} != {task.scenario!r}")
            if registry is None:
                registry = SeedRegistry(config.project_seed)
            elif config.project_seed != registry.project_seed:
                raise ValueError("all episodes of a block must share the project seed")
            outcome = _run_task(task, config, registry, make_policy)
        except InvariantViolationError as violation:
            raise A2ViolationError(task, violation) from violation
        except Exception as error:
            error.add_note(f"P1 episode: {task.label}")
            raise
        yield outcome


def _run_task(
    task: EpisodeTask,
    config: ResolvedConfig,
    registry: SeedRegistry,
    make_policy: PolicyFactory,
) -> EpisodeOutcome:
    params = config.world
    identity = task.identity
    checker = InvariantChecker(params)
    # S_0 is not passed to on_step: rebuild it from fresh generators of the same identity (V7).
    checker.check_initial(initial_world(params, registry, identity))
    prey_policy = make_policy(task.condition.prey_policy, "prey", config)
    predator_policy = make_policy(task.condition.predator_policy, "predator", config)
    result = run_episode(params, prey_policy, predator_policy, registry, identity, on_step=checker)
    if checker.steps_checked != result.record.steps:
        raise RuntimeError(
            f"the A2 checker observed {checker.steps_checked} of {result.record.steps} steps"
        )
    return EpisodeOutcome(
        task=task,
        config_hash=config.config_hash,
        key_columns=episode_key_columns(task.seed_group, task.item),
        result=result,
        steps_checked=checker.steps_checked,
    )


# ---------------------------------------------------------------- result rows (F4 T3)

STAGE_SCENARIOS: Mapping[str, tuple[str, ...]] = {"A": ("A",), "B": ("A", "B"), "C": ("A", "C")}
ENTRY_STAGE = "entry"
CONFIRMATION_STAGE = "confirmation"
ROW_STAGES = (*STAGES, ENTRY_STAGE, CONFIRMATION_STAGE)


def stage_scenarios(stage: str) -> tuple[str, ...]:
    """Scenarios executed by an iteration of ``stage`` (P1-18): A; A and B; A and C."""
    if stage not in STAGE_SCENARIOS:
        raise ValueError(f"stage must be one of {STAGES}, got {stage!r}")
    return STAGE_SCENARIOS[stage]


def check_block_groups(tasks: Sequence[EpisodeTask], spec: P1Spec, block: str) -> None:
    """Independent check that every task belongs to ``block`` of ``spec`` (D16, T3-9).

    It does not trust the block label alone: the seed group and the item of every task must be
    those that the specification assigns to its scenario in that block.
    """
    if not tasks:
        raise ValueError("the block has no episodes to run")
    block_spec = spec.blocks.named()[block]
    seen: set[tuple[str, str, int]] = set()
    for task in tasks:
        if task.block != block:
            raise ValueError(f"{task.label}: task of block {task.block!r}, expected {block!r}")
        expected = block_spec.seed_groups.for_scenario(task.scenario)
        if task.seed_group != expected:
            raise ValueError(
                f"{task.label}: seed_group {task.seed_group} is not the group {expected} of "
                f"scenario {task.scenario} in block {block}"
            )
        if not 0 <= task.item < block_spec.episodes:
            raise ValueError(f"{task.label}: item outside 0..{block_spec.episodes - 1}")
        identity = (task.scenario, task.condition.name, task.item)
        if identity in seen:
            raise ValueError(f"{task.label}: episode planned twice")
        seen.add(identity)


EPISODE_COLUMN_TYPES: tuple[tuple[str, str], ...] = (
    ("block", "str"),
    ("stage", "str"),
    ("iteration", "int"),
    ("scenario", "str"),
    ("condition", "str"),
    *((name, "int") for name in KEY_COLUMNS),
    ("config_hash", "str"),
    ("plant_energy", "float"),
    ("regrow_delay", "int"),
    ("n_plants_a", "int"),
    ("n_plants_b", "int"),
    ("n_predators_c", "int"),
    ("prey_flee_threshold", "float"),
    ("prey_cruise_fraction", "float"),
    ("predator_cruise_fraction", "float"),
    ("t_max", "int"),
    ("n_prey", "int"),
    ("n_predators", "int"),
    ("n_plants", "int"),
    ("steps", "int"),
    ("prey_survival_numerator", "int"),
    ("prey_survival_denominator", "int"),
    ("prey_alive_end", "int"),
    ("prey_captured", "int"),
    ("prey_starved", "int"),
    ("plants_eaten", "int"),
    ("exposure", "int"),
    ("early_captures", "int"),
    ("prey_net_energy_rate", "float"),
    ("predators_alive_end", "int"),
    ("predators_starved", "int"),
    ("predators_reaching_half", "int"),
    ("predators_censored_before_half", "int"),
    ("predators_censored_after_half", "int"),
    ("predators_alive_at_t_max", "int"),
    ("predators_alive_at_t_max_below_two_captures", "int"),
)
EPISODE_COLUMNS = tuple(name for name, _ in EPISODE_COLUMN_TYPES)


def float_text(value: float) -> str:
    """Deterministic text of a finite float: the shortest repr that round-trips exactly."""
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"a CSV value must be finite, got {value!r} (D14)")
    return repr(number)


def _count(mask: np.ndarray) -> int:
    return int(np.count_nonzero(mask))


def episode_row(
    outcome: EpisodeOutcome,
    world: WorldParams,
    *,
    stage: str,
    iteration: int,
    values: CandidateValues,
) -> dict[str, int | str]:
    """One ``episodes.csv`` row: identification, keys, values and integer outcomes (P1-16).

    Only exact integers and finite floats are written; nothing is aggregated here. B3 and B6
    use the individual survival of each predator (D2, D3): t_i is the death step, or ``steps``
    for a predator alive at the end; an episode ending before ``t_max`` censors the survivors.
    """
    if stage not in ROW_STAGES:
        raise ValueError(f"stage must be one of {ROW_STAGES}, got {stage!r}")
    task, record, metrics = outcome.task, outcome.result.record, outcome.result.metrics
    prey, predators = record.prey, record.predators
    if (record.t_max, prey.death_step.size, predators.death_step.size) != (
        world.t_max,
        world.n_prey,
        world.n_predators,
    ):
        raise ValueError(f"{task.label}: the record does not match the resolved configuration")
    t_max, steps = record.t_max, record.steps

    predator_alive = predators.death_step == NOT_DEAD
    predator_survival = np.where(predator_alive, steps, predators.death_step)
    censored = predator_alive & (steps < t_max)
    alive_at_t_max = predator_alive & (steps == t_max)
    early_limit = EARLY_CAPTURE_FRACTION_OF_T_MAX * t_max

    row: dict[str, int | str] = {
        "block": task.block,
        "stage": stage,
        "iteration": iteration,
        "scenario": task.scenario,
        "condition": task.condition.name,
        **outcome.key_columns,
        "config_hash": outcome.config_hash,
        "plant_energy": float_text(values.plant_energy),
        "regrow_delay": values.regrow_delay,
        "n_plants_a": values.n_plants_a,
        "n_plants_b": values.n_plants_b,
        "n_predators_c": values.n_predators_c,
        "prey_flee_threshold": float_text(values.prey_flee_threshold),
        "prey_cruise_fraction": float_text(values.prey_cruise_fraction),
        "predator_cruise_fraction": float_text(values.predator_cruise_fraction),
        "t_max": t_max,
        "n_prey": world.n_prey,
        "n_predators": world.n_predators,
        "n_plants": world.n_plants,
        "steps": steps,
        "prey_survival_numerator": metrics.prey_survival.numerator,
        "prey_survival_denominator": metrics.prey_survival.denominator,
        "prey_alive_end": _count(prey.death_step == NOT_DEAD),
        "prey_captured": _count(prey.death_cause == DeathCause.CAPTURED),
        "prey_starved": _count(prey.death_cause == DeathCause.STARVATION),
        "plants_eaten": metrics.plants_eaten,
        "exposure": metrics.capture_rate_per_exposure.denominator,
        "early_captures": _count(record.capture_step < early_limit),
        "prey_net_energy_rate": float_text(metrics.prey_net_energy_rate),
        "predators_alive_end": _count(predator_alive),
        "predators_starved": _count(predators.death_cause == DeathCause.STARVATION),
        "predators_reaching_half": _count(2 * predator_survival >= t_max),
        "predators_censored_before_half": _count(censored & (2 * steps < t_max)),
        "predators_censored_after_half": _count(censored & (2 * steps >= t_max)),
        "predators_alive_at_t_max": _count(alive_at_t_max),
        "predators_alive_at_t_max_below_two_captures": _count(
            alive_at_t_max & (predators.events < 2)
        ),
    }
    if tuple(row) != EPISODE_COLUMNS:
        raise RuntimeError("episode row columns do not match EPISODE_COLUMNS")
    if row["prey_captured"] != metrics.captures:
        raise RuntimeError(f"{task.label}: captured prey and capture events disagree")
    return row


COMPARISON_SCENARIOS: Mapping[Comparison, tuple[str, ...]] = {
    Comparison.A6_B_VS_A: ("A", "B"),
    Comparison.A6_C_VS_A: ("A", "C"),
    Comparison.B2_PREY_A: ("A",),
    Comparison.B2_PREY_B: ("B",),
    Comparison.B2_PREY_C: ("C",),
    Comparison.B2_PREDATOR_A: ("A",),
    Comparison.B2_PREDATOR_B: ("B",),
    Comparison.B2_PREDATOR_C: ("C",),
}
KEY_FIELDS = ("purpose", "seed_group", "run", "generation", "item", "stream")
BOOTSTRAP_COLUMNS = ("comparison", "comparison_name", "project_seed", *KEY_FIELDS)


# ---------------------------------------------------------------- protections (F4 T3b)

# The approved P1 blocks (ADR-033 P1-13 seed groups, P1-5 episodes per condition and scenario).
APPROVED_BLOCKS: Mapping[str, tuple[int, tuple[int, int, int]]] = {
    "calibration": (30, (10, 11, 12)),
    "confirmation": (50, (20, 21, 22)),
    "second_confirmation": (50, (30, 31, 32)),
}
REAL_SEED_GROUPS = range(10, 33)  # 10-32: only the approved table may declare them (D16)


def check_approved_seed_groups(spec: P1Spec) -> None:
    """A specification that declares any real P1 group must be exactly the approved one (T3b-1).

    With a real group anywhere, every block must have the groups of P1-13 and the episodes of
    P1-5, so no block can run the seeds of another (for instance, calibration on confirmation
    seeds). Synthetic specifications (no group in 10-32) are not constrained by this check.
    """
    declared = spec.declared_seed_groups()
    real = sorted(name for name, group in declared.items() if group in REAL_SEED_GROUPS)
    if not real:
        return
    for name, block in spec.blocks.named().items():
        episodes, groups = APPROVED_BLOCKS[name]
        actual = (block.seed_groups.a, block.seed_groups.b, block.seed_groups.c)
        if (block.episodes, actual) != (episodes, groups):
            raise ValueError(
                f"{real} declare real P1 seed groups (10-32), so every block must match ADR-033: "
                f"block {name} needs {episodes} episodes and seed_groups {groups}, "
                f"got {block.episodes} and {actual} (P1-5, P1-13, D16)"
            )


def check_block_plan(
    tasks: Sequence[EpisodeTask],
    spec: P1Spec,
    block: str,
    values: CandidateValues,
    scenarios: Sequence[str],
) -> None:
    """The plan is exactly the expected one, in order, with the overrides of ``values`` (T3b).

    Built independently of ``plan_block`` from the catalogue (P1-14) and the block
    specification: every scenario of ``scenarios``, every condition of the scenario, every item.
    ``check_block_groups`` runs first so that a foreign seed group gets its specific message.
    """
    if isinstance(scenarios, str) or not all(s in SCENARIOS for s in scenarios):
        raise ValueError(f"scenarios must be a sequence of {SCENARIOS}, got {scenarios!r}")
    check_block_groups(tasks, spec, block)
    block_spec = spec.blocks.named()[block]
    expected = [
        (
            block,
            scenario,
            entry,
            block_spec.seed_groups.for_scenario(scenario),
            item,
            condition_overrides(values, scenario, entry.name),
        )
        for scenario in SCENARIOS
        if scenario in scenarios
        for entry in CONDITIONS_BY_SCENARIO[scenario]
        for item in range(block_spec.episodes)
    ]
    actual = [(t.block, t.scenario, t.condition, t.seed_group, t.item, t.overrides) for t in tasks]
    if actual == expected:
        return
    for index, (got, wanted) in enumerate(zip(actual, expected, strict=False)):
        if got != wanted:
            raise ValueError(f"task {index} of the plan is {got}, expected {wanted}")
    raise ValueError(f"the plan has {len(actual)} tasks, expected {len(expected)}")


def bootstrap_rows(
    block: BlockSpec, run: int, scenarios: Sequence[str], project_seed: int
) -> list[dict[str, int | str]]:
    """``bootstrap_keys.csv`` rows (P1-20): the comparisons whose scenarios were executed.

    ``project_seed`` is written as text: it has 128 bits (ADR-023, explicit types).
    """
    executed = {_scenario(s) for s in scenarios}
    rows: list[dict[str, int | str]] = []
    for comparison in Comparison:
        if set(COMPARISON_SCENARIOS[comparison]) <= executed:
            key = bootstrap_key(block, run, comparison)
            rows.append(
                {
                    "comparison": int(comparison),
                    "comparison_name": comparison.name,
                    "project_seed": str(project_seed),
                    **dict(zip(KEY_FIELDS, key, strict=True)),
                }
            )
    return rows
