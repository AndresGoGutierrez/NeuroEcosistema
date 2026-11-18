"""Application-level configuration objects (ADR-022)."""

from __future__ import annotations

from dataclasses import dataclass

from neuroeco.domain.params import WorldParams


def _check_fraction(name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, int | float) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be a number in [0, 1], got {value!r}")


@dataclass(frozen=True)
class PreyRuleParams:
    flee_threshold: float
    cruise_fraction: float

    def __post_init__(self) -> None:
        _check_fraction("flee_threshold", self.flee_threshold)
        _check_fraction("cruise_fraction", self.cruise_fraction)


@dataclass(frozen=True)
class PredatorRuleParams:
    cruise_fraction: float

    def __post_init__(self) -> None:
        _check_fraction("cruise_fraction", self.cruise_fraction)


@dataclass(frozen=True)
class RuleParams:
    """Parameters of the rule-based reference policies (ADR-012); calibrated in P1."""

    prey: PreyRuleParams
    predator: PredatorRuleParams


@dataclass(frozen=True)
class P0Spec:
    """Specification of pilot P0: simulation cost per step (decisions A3, A4)."""

    pilot: str
    seed_group: int
    scenario: str
    prey_counts: tuple[int, ...]
    predator_counts: tuple[int, ...]
    repetitions: int
    reference_prey: int
    reference_predators: int
    threshold_us: float
    prey_policy: str
    predator_policy: str

    def __post_init__(self) -> None:
        if self.repetitions < 1:
            raise ValueError("repetitions must be >= 1")
        if self.threshold_us <= 0:
            raise ValueError("threshold_us must be > 0")
        if not self.prey_counts or not self.predator_counts:
            raise ValueError("the grid must not be empty")
        if self.reference_prey not in self.prey_counts:
            raise ValueError("reference_prey must belong to prey_counts")
        if self.reference_predators not in self.predator_counts:
            raise ValueError("reference_predators must belong to predator_counts")


@dataclass(frozen=True)
class ResolvedConfig:
    """Fully resolved configuration of one run: base, then scenario, then overrides."""

    project_seed: int
    scenario: str
    world: WorldParams
    rules: RuleParams
    config_hash: str


@dataclass(frozen=True)
class ReferenceSpec:
    """I2 of ADR-018: reference observations and the initial-saturation thresholds (F5)."""

    pilot: str
    seed_group: int
    scenarios: tuple[str, ...]
    episodes: int
    stride: int
    genomes: int
    s1_max: float
    s2_max: float
    s3_min: float

    def __post_init__(self) -> None:
        if not self.scenarios or len(set(self.scenarios)) != len(self.scenarios):
            raise ValueError("scenarios must be a non-empty list without repetitions")
        for name in ("episodes", "stride", "genomes"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be >= 1")
        for name in ("s1_max", "s2_max", "s3_min"):
            _check_fraction(name, getattr(self, name))


@dataclass(frozen=True)
class P0bSpec:
    """P0b (F6, decision A3): network forward cost and parallel speed-up, O4 methodology."""

    pilot: str
    seed_group: int
    scenario: str
    n_prey: tuple[int, ...]  # cells: (n_prey[i], n_predators[i])
    n_predators: tuple[int, ...]
    policies: tuple[str, ...]  # "rules" and/or "neural"
    repetitions: int
    speedup_workers: tuple[int, ...]
    speedup_genomes: int
    speedup_episodes: int
    speedup_repetitions: int

    def __post_init__(self) -> None:
        if not self.n_prey or len(self.n_prey) != len(self.n_predators):
            raise ValueError("n_prey and n_predators must be paired lists of the same length")
        if min(self.n_prey) < 1 or min(self.n_predators) < 1:
            raise ValueError("the counts must be positive")
        if not set(self.policies) <= {"rules", "neural"} or not self.policies:
            raise ValueError("policies must be rules and/or neural")
        for name in ("repetitions", "speedup_genomes", "speedup_episodes", "speedup_repetitions"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be >= 1")
        if not self.speedup_workers or min(self.speedup_workers) < 1:
            raise ValueError("speedup_workers must be positive")
        if 1 not in self.speedup_workers:
            raise ValueError("speedup_workers must include 1 (the reference of the speed-up)")

    @property
    def populations(self) -> tuple[tuple[int, int], ...]:
        return tuple(zip(self.n_prey, self.n_predators, strict=True))
