"""Statistical methods of ADR-013, ADR-014 and ADR-017 (implementation decisions: ADR-032).

Exact methods are implemented here by enumeration and return exact ``Fraction`` p-values; the
tests compare them with scipy and with independent naive enumerations. Only the bootstrap uses
floating point (``scipy.stats.bootstrap``).

The experimental unit is the training run (ADR-017): per-run metrics enter as integer numerators
with a common denominator, so zeros and ties are detected exactly.
"""

from __future__ import annotations

from collections.abc import Hashable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

import numpy as np

# ---------------------------------------------------------------- per-run data (ADR-017)


class PseudoReplicationError(ValueError):
    """The same run appears more than once: episodes must be aggregated per run first."""


def _check_integer(value: object, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int | np.integer):
        raise TypeError(f"{what} must be an integer numerator, got {value!r}")
    return int(value)


@dataclass(frozen=True)
class RunValues:
    """One integer numerator per training run, in insertion order."""

    values: Mapping[Hashable, int]

    @classmethod
    def from_pairs(cls, pairs: Iterable[tuple[Hashable, object]]) -> RunValues:
        values: dict[Hashable, int] = {}
        for run_id, value in pairs:
            if run_id in values:
                raise PseudoReplicationError(
                    f"run {run_id!r} appears more than once; the experimental unit is the run "
                    "(ADR-017): aggregate its episodes before the analysis"
                )
            values[run_id] = _check_integer(value, f"value of run {run_id!r}")
        if not values:
            raise ValueError("at least one run is required")
        return cls(MappingProxyType(values))

    @property
    def run_ids(self) -> tuple[Hashable, ...]:
        return tuple(self.values)

    def __len__(self) -> int:
        return len(self.values)


def paired_differences(before: RunValues, after: RunValues) -> tuple[int, ...]:
    """d_r = after_r - before_r for every run, in the order of ``before`` (exact integers)."""
    missing = [r for r in before.run_ids if r not in after.values]
    extra = [r for r in after.run_ids if r not in before.values]
    if missing or extra:
        raise ValueError(
            f"before and after must contain the same runs; only before: {missing}, "
            f"only after: {extra}"
        )
    return tuple(after.values[r] - before.values[r] for r in before.run_ids)


@dataclass(frozen=True)
class SignCounts:
    positive: int
    zero: int
    negative: int

    @property
    def n(self) -> int:
        return self.positive + self.zero + self.negative


def sign_counts(differences: Sequence[float]) -> SignCounts:
    """k+, k0 and k- of the differences (exact for integers)."""
    data = np.asarray(differences)
    if data.ndim != 1 or data.size == 0:
        raise ValueError("differences must be a non-empty one-dimensional sequence")
    if not np.all(np.isfinite(data)):
        raise ValueError("differences must be finite")
    return SignCounts(
        positive=int(np.count_nonzero(data > 0)),
        zero=int(np.count_nonzero(data == 0)),
        negative=int(np.count_nonzero(data < 0)),
    )
