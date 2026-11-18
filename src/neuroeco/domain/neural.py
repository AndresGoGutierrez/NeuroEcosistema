"""Neural networks of the agents (ADR-025, ADR-018, ADR-007).

A network is a fixed-topology MLP: d_in -> hidden_1 -> ... -> hidden_k -> 2, with tanh in every
hidden layer and in the output, so its raw actions already lie in [-1, 1] and go through the same
decoder as every other policy (``domain.actions.decode_actions``). The input size is derived
from the species' sensor schema, never configured by hand.

The genome (ADR-027) is the flat vector of every weight and bias, layer by layer, each layer as
its weight matrix (fan_in, fan_out) in row-major order followed by its bias vector.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

import numpy as np

from neuroeco.domain.actions import RAW_ACTION_SIZE
from neuroeco.domain.perception import PREDATOR_SCHEMA, PREY_SCHEMA, InputSchema

MIN_HIDDEN_LAYERS = 2


@dataclass(frozen=True)
class NetworkSpec:
    """Topology of a network: input schema, hidden widths and the two raw outputs."""

    name: str
    schema: InputSchema
    hidden: tuple[int, ...]

    def __post_init__(self) -> None:
        if len(self.hidden) < MIN_HIDDEN_LAYERS:
            raise ValueError(
                f"a network needs at least {MIN_HIDDEN_LAYERS} hidden layers, "
                f"got {len(self.hidden)}"
            )
        if any(not isinstance(w, int) or isinstance(w, bool) or w < 1 for w in self.hidden):
            raise ValueError(f"hidden widths must be positive integers, got {self.hidden!r}")

    @property
    def layer_sizes(self) -> tuple[int, ...]:
        return (self.schema.size, *self.hidden, RAW_ACTION_SIZE)

    @property
    def shapes(self) -> tuple[tuple[int, int], ...]:
        """(fan_in, fan_out) of each layer."""
        sizes = self.layer_sizes
        return tuple(itertools.pairwise(sizes))

    @property
    def parameter_count(self) -> int:
        return sum(fan_in * fan_out + fan_out for fan_in, fan_out in self.shapes)


PREY_BASE = NetworkSpec("prey_base", PREY_SCHEMA, (16, 16))
PREY_COMPACT = NetworkSpec("prey_compact", PREY_SCHEMA, (8, 8))
PREDATOR_BASE = NetworkSpec("predator_base", PREDATOR_SCHEMA, (16, 16))
PREDATOR_COMPACT = NetworkSpec("predator_compact", PREDATOR_SCHEMA, (8, 8))
ARCHITECTURES = {s.name: s for s in (PREY_BASE, PREY_COMPACT, PREDATOR_BASE, PREDATOR_COMPACT)}


def lecun_genome(spec: NetworkSpec, rng: np.random.Generator) -> np.ndarray:
    """ADR-018: weights ~ Normal(0, 1/fan_in), biases 0, drawn layer by layer."""
    parts: list[np.ndarray] = []
    for fan_in, fan_out in spec.shapes:
        parts.append(rng.normal(0.0, 1.0 / np.sqrt(fan_in), size=fan_in * fan_out))
        parts.append(np.zeros(fan_out))
    return np.concatenate(parts)


class NeuralNetwork:
    """An MLP built from a genome; immutable copies of its weights."""

    def __init__(self, spec: NetworkSpec, genome: np.ndarray) -> None:
        genome = np.asarray(genome, dtype=np.float64)
        if genome.ndim != 1 or genome.size != spec.parameter_count:
            raise ValueError(
                f"genome of {spec.name} must have {spec.parameter_count} values, "
                f"got shape {genome.shape}"
            )
        if not np.all(np.isfinite(genome)):
            raise ValueError("genome values must be finite")
        self.spec = spec
        self.genome = genome.copy()
        self.genome.flags.writeable = False
        self.layers: list[tuple[np.ndarray, np.ndarray]] = []
        offset = 0
        for fan_in, fan_out in spec.shapes:
            weights = self.genome[offset : offset + fan_in * fan_out].reshape(fan_in, fan_out)
            offset += fan_in * fan_out
            bias = self.genome[offset : offset + fan_out]
            offset += fan_out
            self.layers.append((weights, bias))

    def activations(self, observations: np.ndarray) -> list[np.ndarray]:
        """Outputs of every layer (hidden layers and the raw actions) for a batch (n, d_in)."""
        x = np.asarray(observations, dtype=np.float64)
        if x.ndim != 2 or x.shape[1] != self.spec.schema.size:
            raise ValueError(
                f"observations must have shape (n, {self.spec.schema.size}), got {x.shape}"
            )
        outputs = []
        for weights, bias in self.layers:
            x = np.tanh(x @ weights + bias)
            outputs.append(x)
        return outputs

    def forward(self, observations: np.ndarray) -> np.ndarray:
        """Raw actions (n, 2) in [-1, 1]."""
        return self.activations(observations)[-1]


class NeuralPolicy:
    """``Policy`` backed by a network; deterministic, so it never draws from its stream."""

    def __init__(self, network: NeuralNetwork, name: str | None = None) -> None:
        self.network = network
        self.name = name or f"neural_{network.spec.name}"

    def act(self, observations: np.ndarray, rng: np.random.Generator) -> np.ndarray:
        return self.network.forward(observations)


def input_group(schema: InputSchema, group: str) -> tuple[int, ...]:
    """Indices of a sensor group (ADR-019, X3): an object prefix such as 'plant' or 'energy'."""
    indices = tuple(
        i for i, name in enumerate(schema.names) if name == group or name.startswith(f"{group}_")
    )
    if not indices:
        raise ValueError(f"{schema.species} has no input group {group!r}")
    return indices


class InputAblationPolicy:
    """Wrapper that sets some inputs to zero before the wrapped policy decides (ADR-019, X3).

    Zero is the value of a sensor that perceives nothing, so the ablated agent behaves as if
    that group were never perceived.
    """

    def __init__(self, policy: NeuralPolicy, groups: tuple[str, ...]) -> None:
        schema = policy.network.spec.schema
        self.policy = policy
        self.groups = groups
        self.indices = tuple(sorted({i for g in groups for i in input_group(schema, g)}))
        self.name = f"{policy.name}_without_{'_'.join(groups)}"

    def act(self, observations: np.ndarray, rng: np.random.Generator) -> np.ndarray:
        ablated = np.array(observations, dtype=np.float64, copy=True)
        ablated[:, list(self.indices)] = 0.0
        return self.policy.act(ablated, rng)


def ablate_input_weights(network: NeuralNetwork, indices: tuple[int, ...]) -> NeuralNetwork:
    """A copy of ``network`` whose first-layer weights from ``indices`` are zero.

    Equivalent to ablating those inputs (``InputAblationPolicy``): it is the weight-level view
    of the same intervention, used to check that the decision really uses those weights.
    """
    genome = network.genome.copy()
    fan_in, fan_out = network.spec.shapes[0]
    first = genome[: fan_in * fan_out].reshape(fan_in, fan_out)
    first[list(indices), :] = 0.0
    return NeuralNetwork(network.spec, genome)


SATURATION_LEVEL = 0.95  # |a| above which a tanh unit counts as saturated (ADR-018, S1)
SATURATED_SHARE = 0.90  # a unit saturated in at least this share of the samples (S2)


@dataclass(frozen=True)
class SaturationStats:
    """Saturation of one network over a set of observations (ADR-018, I2).

    ``s1`` and ``s2`` have one value per layer (hidden layers and output, all tanh): the share of
    (sample, unit) pairs with |a| > 0.95 and the share of units saturated in >= 90 % of the
    samples. ``s3`` is the standard deviation of each raw output over the samples.
    """

    s1: tuple[float, ...]
    s2: tuple[float, ...]
    s3: tuple[float, ...]


def saturation_stats(network: NeuralNetwork, observations: np.ndarray) -> SaturationStats:
    if observations.shape[0] == 0:
        raise ValueError("the reference set has no observations")
    layers = network.activations(observations)
    saturated = [np.abs(a) > SATURATION_LEVEL for a in layers]
    return SaturationStats(
        s1=tuple(float(s.mean()) for s in saturated),
        s2=tuple(float((s.mean(axis=0) >= SATURATED_SHARE).mean()) for s in saturated),
        s3=tuple(float(v) for v in layers[-1].std(axis=0)),
    )
