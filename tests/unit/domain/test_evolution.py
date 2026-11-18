"""F6: genetic algorithm (ADR-027) and its toy problems."""

import numpy as np
import pytest

from neuroeco.domain.evolution import GAParams, GeneticAlgorithm
from neuroeco.domain.neural import PREDATOR_COMPACT, NeuralNetwork, lecun_genome

PARAMS = GAParams(population=20, elite=2, tournament=3, sigma=0.05)


def ga(params=PARAMS, seed=0) -> GeneticAlgorithm:
    return GeneticAlgorithm(PREDATOR_COMPACT, params, np.random.default_rng(seed))


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"population": 0}, "population"),
        ({"elite": 20}, "elite must be smaller"),
        ({"tournament": 21}, "tournament cannot exceed"),
        ({"sigma": 0.0}, "sigma"),
        ({"sigma": float("nan")}, "sigma"),
        ({"elite": True}, "elite"),
    ],
)
def test_params_are_validated(kwargs, message) -> None:
    values = {"population": 20, "elite": 2, "tournament": 3, "sigma": 0.05, **kwargs}
    with pytest.raises(ValueError, match=message):
        GAParams(**values)


def test_generation_zero_is_the_lecun_initialization() -> None:
    algorithm = ga(seed=4)
    rng = np.random.default_rng(4)
    expected = np.stack([lecun_genome(PREDATOR_COMPACT, rng) for _ in range(20)])
    assert np.array_equal(algorithm.ask(), expected)
    with pytest.raises(ValueError):
        algorithm.ask()[0, 0] = 1.0


def test_elites_survive_unchanged_and_first() -> None:
    algorithm = ga()
    before = algorithm.ask().copy()
    fitness = np.arange(20, dtype=float)  # genome 19 best, then 18
    algorithm.tell(fitness, np.random.default_rng(1))
    after = algorithm.ask()
    assert np.array_equal(after[0], before[19]) and np.array_equal(after[1], before[18])
    assert after.shape == before.shape and algorithm.generation == 1


def test_ties_keep_the_lower_index() -> None:
    algorithm = ga()
    before = algorithm.ask().copy()
    algorithm.tell(np.zeros(20), np.random.default_rng(1))
    assert np.array_equal(algorithm.ask()[0], before[0])
    assert np.array_equal(algorithm.ask()[1], before[1])


def test_offspring_are_mutated_copies_of_tournament_winners() -> None:
    algorithm = ga(GAParams(population=20, elite=2, tournament=20, sigma=1e-9))
    before = algorithm.ask().copy()
    fitness = np.zeros(20)
    fitness[7] = 1.0
    algorithm.tell(fitness, np.random.default_rng(2))
    # with t = N every tournament is won by the best genome
    offspring = algorithm.ask()[2:]
    assert np.allclose(offspring, before[7], atol=1e-7)
    assert not np.array_equal(offspring[0], before[7])  # mutated, no crossover


def test_the_same_seeds_give_the_same_evolution() -> None:
    def evolve():
        algorithm = ga(seed=9)
        variation = np.random.default_rng(10)
        for _ in range(5):
            genomes = algorithm.ask()
            algorithm.tell(-np.linalg.norm(genomes, axis=1), variation)
        return algorithm.ask().copy()

    assert np.array_equal(evolve(), evolve())


def test_summary_reports_fitness_diversity_and_drift() -> None:
    algorithm = ga()
    genomes = algorithm.ask().copy()
    fitness = np.linspace(0, 1, 20)
    summary = algorithm.tell(fitness, np.random.default_rng(0))
    assert summary.generation == 0 and summary.best_index == 19
    assert summary.fitness_max == 1.0 and summary.fitness_mean == pytest.approx(0.5)
    assert summary.best_norm == pytest.approx(np.linalg.norm(genomes[19]))
    assert summary.best_drift == 0.0 and summary.diversity > 0
    second = algorithm.tell(np.zeros(20), np.random.default_rng(1))
    assert second.best_drift == 0.0  # the elite of generation 0 is unchanged


def test_tell_rejects_wrong_fitness() -> None:
    with pytest.raises(ValueError, match="20 finite values"):
        ga().tell(np.zeros(19), np.random.default_rng(0))
    bad = np.zeros(20)
    bad[0] = np.inf
    with pytest.raises(ValueError, match="finite"):
        ga().tell(bad, np.random.default_rng(0))


def test_toy_problem_reaches_a_target_genome() -> None:
    """Toy problem 1: maximize -||w - w*||; the distance must fall far below the start."""
    target = np.random.default_rng(99).normal(0, 0.3, PREDATOR_COMPACT.parameter_count)
    algorithm = ga(GAParams(population=40, elite=2, tournament=3, sigma=0.02), seed=1)
    variation = np.random.default_rng(2)
    start = np.linalg.norm(algorithm.ask() - target, axis=1).min()
    for _ in range(150):
        algorithm.tell(-np.linalg.norm(algorithm.ask() - target, axis=1), variation)
    end = np.linalg.norm(algorithm.ask()[0] - target)
    assert end < 0.5 * start


def test_toy_problem_trains_a_network_to_a_mapping() -> None:
    """Toy problem 2: the network learns o0 = tanh(2 x0) and o1 = -tanh(2 x1)."""
    inputs = np.random.default_rng(5).uniform(-1, 1, (64, PREDATOR_COMPACT.schema.size))
    target = np.stack((np.tanh(2 * inputs[:, 0]), -np.tanh(2 * inputs[:, 1])), axis=1)

    def fitness(genomes):
        return np.array(
            [
                -np.mean((NeuralNetwork(PREDATOR_COMPACT, g).forward(inputs) - target) ** 2)
                for g in genomes
            ]
        )

    algorithm = ga(GAParams(population=40, elite=2, tournament=3, sigma=0.05), seed=3)
    variation = np.random.default_rng(4)
    first = fitness(algorithm.ask()).max()
    for _ in range(120):
        algorithm.tell(fitness(algorithm.ask()), variation)
    last = fitness(algorithm.ask()).max()
    assert last > first and -last < 0.25 * -first
