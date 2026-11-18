"""F5: networks, initialization I1, neural policy and ablation (ADR-025, ADR-018, ADR-019)."""

import numpy as np
import pytest

from neuroeco.domain.actions import decode_actions
from neuroeco.domain.neural import (
    ARCHITECTURES,
    PREDATOR_BASE,
    PREY_BASE,
    InputAblationPolicy,
    NetworkSpec,
    NeuralNetwork,
    NeuralPolicy,
    ablate_input_weights,
    input_group,
    lecun_genome,
)
from neuroeco.domain.params import SpeciesParams
from neuroeco.domain.perception import PREDATOR_SCHEMA, PREY_SCHEMA
from neuroeco.domain.policies import Policy

SPECIES = SpeciesParams(
    v_max=1.0,
    omega_max=0.5,
    vision_radius=20.0,
    e_max=100.0,
    initial_energy_fraction=0.8,
    c_basal=0.16,
    c_move=0.32,
)


def network(spec=PREY_BASE, seed=0) -> NeuralNetwork:
    return NeuralNetwork(spec, lecun_genome(spec, np.random.default_rng(seed)))


def observations(schema, n=50, seed=1) -> np.ndarray:
    return np.random.default_rng(seed).uniform(-1.0, 1.0, size=(n, schema.size))


@pytest.mark.parametrize("hidden", [(), (16,)])
def test_spec_rejects_fewer_than_two_hidden_layers(hidden) -> None:
    with pytest.raises(ValueError, match="at least 2 hidden layers"):
        NetworkSpec("bad", PREY_SCHEMA, hidden)


@pytest.mark.parametrize("hidden", [(16, 0), (16, -1), (16, 2.0), (16, True)])
def test_spec_rejects_invalid_widths(hidden) -> None:
    with pytest.raises(ValueError, match="positive integers"):
        NetworkSpec("bad", PREY_SCHEMA, hidden)


def test_parameter_counts_match_adr_025() -> None:
    counts = {name: spec.parameter_count for name, spec in ARCHITECTURES.items()}
    assert counts == {
        "prey_base": 482,
        "prey_compact": 178,
        "predator_base": 434,
        "predator_compact": 154,
    }


def test_input_size_is_derived_from_the_sensor_schema() -> None:
    assert PREY_BASE.layer_sizes == (10, 16, 16, 2)
    assert PREDATOR_BASE.layer_sizes == (7, 16, 16, 2)


def test_i1_lecun_variance_with_fan_in_16() -> None:
    """I1 (ADR-018): 10^6 weights with fan_in 16 have sample variance 1/16 within 2 %."""
    spec = NetworkSpec("wide", PREY_SCHEMA, (16, 62500))
    genome = lecun_genome(spec, np.random.default_rng(2026))
    fan_in, fan_out = spec.shapes[1]
    start = spec.shapes[0][0] * spec.shapes[0][1] + spec.shapes[0][1]
    weights = genome[start : start + fan_in * fan_out]
    assert weights.size == 10**6
    assert abs(weights.var() / (1 / 16) - 1) < 0.02


def test_lecun_genome_has_zero_biases_and_layer_deviations() -> None:
    genome = lecun_genome(PREY_BASE, np.random.default_rng(3))
    net = NeuralNetwork(PREY_BASE, genome)
    for (weights, bias), (fan_in, _) in zip(net.layers, PREY_BASE.shapes, strict=True):
        assert np.all(bias == 0.0)
        assert 0.6 < weights.std() * np.sqrt(fan_in) < 1.4


def test_genome_layout_is_weights_then_bias_per_layer() -> None:
    genome = np.arange(PREDATOR_BASE.parameter_count, dtype=float) / 1000
    net = NeuralNetwork(PREDATOR_BASE, genome)
    weights, bias = net.layers[0]
    assert weights.shape == (7, 16) and weights[0, 1] == genome[1] and weights[1, 0] == genome[16]
    assert bias[0] == genome[7 * 16]
    assert net.layers[-1][1][-1] == genome[-1]


def test_network_rejects_wrong_or_non_finite_genomes() -> None:
    with pytest.raises(ValueError, match="482 values"):
        NeuralNetwork(PREY_BASE, np.zeros(481))
    bad = np.zeros(482)
    bad[3] = np.nan
    with pytest.raises(ValueError, match="finite"):
        NeuralNetwork(PREY_BASE, bad)


def test_genome_is_copied_and_read_only() -> None:
    genome = lecun_genome(PREY_BASE, np.random.default_rng(4))
    net = NeuralNetwork(PREY_BASE, genome)
    before = net.forward(observations(PREY_SCHEMA))
    genome[:] = 0.0
    assert np.array_equal(net.forward(observations(PREY_SCHEMA)), before)
    with pytest.raises(ValueError):
        net.genome[0] = 1.0


def test_forward_matches_a_manual_computation_and_stays_in_range() -> None:
    net = network(PREDATOR_BASE, seed=5)
    obs = observations(PREDATOR_SCHEMA)
    x = obs
    for weights, bias in net.layers:
        x = np.tanh(x @ weights + bias)
    out = net.forward(obs)
    assert np.array_equal(out, x)
    assert out.shape == (50, 2) and np.all(np.abs(out) <= 1.0)
    assert [a.shape[1] for a in net.activations(obs)] == [16, 16, 2]


def test_forward_rejects_observations_of_another_schema() -> None:
    with pytest.raises(ValueError, match=r"shape \(n, 10\)"):
        network(PREY_BASE).forward(observations(PREDATOR_SCHEMA))


def test_neural_policy_is_a_deterministic_policy_that_never_draws() -> None:
    policy = NeuralPolicy(network())
    assert isinstance(policy, Policy)
    rng = np.random.default_rng(6)
    state = rng.bit_generator.state
    obs = observations(PREY_SCHEMA)
    assert np.array_equal(policy.act(obs, rng), policy.act(obs, rng))
    assert rng.bit_generator.state == state


def test_decoded_output_is_the_applied_action() -> None:
    """ADR-025: o0 -> turn = o0 * omega_max, o1 -> speed = v_max (o1 + 1) / 2."""
    net = network()
    raw = NeuralPolicy(net).act(observations(PREY_SCHEMA), np.random.default_rng(0))
    turns, speeds = decode_actions(raw, SPECIES)
    assert np.allclose(turns, raw[:, 0] * SPECIES.omega_max)
    assert np.allclose(speeds, SPECIES.v_max * (raw[:, 1] + 1) / 2)


def test_input_groups_follow_the_schema() -> None:
    assert input_group(PREY_SCHEMA, "plant") == (0, 1, 2)
    assert input_group(PREY_SCHEMA, "predator2") == (6, 7, 8)
    assert input_group(PREY_SCHEMA, "energy") == (9,)
    assert input_group(PREDATOR_SCHEMA, "prey1") == (0, 1, 2)
    with pytest.raises(ValueError, match="no input group"):
        input_group(PREDATOR_SCHEMA, "plant")


def test_input_ablation_zeroes_the_group_without_touching_the_caller() -> None:
    policy = NeuralPolicy(network())
    ablated = InputAblationPolicy(policy, ("plant",))
    obs = observations(PREY_SCHEMA)
    original = obs.copy()
    zeroed = obs.copy()
    zeroed[:, [0, 1, 2]] = 0.0
    rng = np.random.default_rng(0)
    assert np.array_equal(ablated.act(obs, rng), policy.act(zeroed, rng))
    assert np.array_equal(obs, original)
    assert ablated.name == "neural_prey_base_without_plant"


def test_weight_ablation_equals_input_ablation_and_changes_the_decision() -> None:
    net = network(seed=7)
    obs = observations(PREY_SCHEMA)
    indices = input_group(PREY_SCHEMA, "predator1")
    by_weights = NeuralPolicy(ablate_input_weights(net, indices))
    by_inputs = InputAblationPolicy(NeuralPolicy(net), ("predator1",))
    rng = np.random.default_rng(0)
    assert np.allclose(by_weights.act(obs, rng), by_inputs.act(obs, rng), atol=1e-15)
    assert not np.allclose(by_weights.act(obs, rng), NeuralPolicy(net).act(obs, rng))
    assert np.array_equal(net.forward(obs), NeuralPolicy(net).act(obs, rng))  # original intact


def test_all_weights_ablated_gives_inert_outputs() -> None:
    zero = NeuralNetwork(PREY_BASE, np.zeros(PREY_BASE.parameter_count))
    assert np.array_equal(zero.forward(observations(PREY_SCHEMA)), np.zeros((50, 2)))


def test_saturation_stats_count_saturated_pairs_units_and_output_spread() -> None:
    from neuroeco.domain.neural import saturation_stats

    spec = PREDATOR_BASE
    genome = np.zeros(spec.parameter_count)
    # first layer: unit 0 copies 10 * input 0 (saturates when |x0| > ~0.18), the rest is zero
    genome[0] = 10.0
    net = NeuralNetwork(spec, genome)
    obs = np.zeros((10, 7))
    obs[:9, 0] = 1.0  # unit 0 saturated in 9 of 10 samples (>= 90 %)
    stats = saturation_stats(net, obs)
    assert stats.s1 == (0.9 / 16, 0.0, 0.0)
    assert stats.s2 == (1 / 16, 0.0, 0.0)
    assert stats.s3 == (0.0, 0.0)
    with pytest.raises(ValueError, match="no observations"):
        saturation_stats(net, np.zeros((0, 7)))
