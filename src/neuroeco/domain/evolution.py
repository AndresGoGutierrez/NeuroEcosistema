"""Genetic algorithm with direct encoding (ADR-027).

ask/tell interface over flat genomes (``domain.neural``):

- generation 0: N genomes from the LeCun initialization (ADR-018), drawn from GA_INIT;
- ``tell(fitness)`` ranks the population (higher is better; ties keep the lower index), keeps
  the k best unchanged (elitism; they are re-evaluated in the next generation on its new seeds)
  and fills the rest with tournament selection of size t and additive Gaussian mutation of all
  weights with the architecture's sigma, drawn from GA_VARIATION. There is no crossover.

The algorithm never sees episodes: fitness values come from the caller, so the same code serves
the toy problem and the ecosystem.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from neuroeco.domain.neural import NetworkSpec, lecun_genome


@dataclass(frozen=True)
class GAParams:
    population: int  # N
    elite: int  # k
    tournament: int  # t
    sigma: float  # mutation standard deviation

    def __post_init__(self) -> None:
        for name in ("population", "elite", "tournament"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer, got {value!r}")
        if self.elite >= self.population:
            raise ValueError("elite must be smaller than the population")
        if self.tournament > self.population:
            raise ValueError("the tournament cannot exceed the population")
        if not np.isfinite(self.sigma) or self.sigma <= 0:
            raise ValueError("sigma must be a finite number > 0")


@dataclass(frozen=True)
class GenerationSummary:
    """What ADR-027 logs per generation (fitness statistics and weight geometry)."""

    generation: int
    fitness_max: float
    fitness_mean: float
    fitness_median: float
    fitness_std: float
    zero_share: float  # share of genomes with fitness 0 (curriculum rule, ADR-026)
    diversity: float  # mean distance of the genomes to their centroid
    best_norm: float  # ||w|| of the best genome
    best_drift: float  # ||w - w0|| of the best genome, w0 = its generation-0 ancestor
    best_index: int


class GeneticAlgorithm:
    """One evolving population. Call ``ask`` then ``tell`` once per generation."""

    def __init__(self, spec: NetworkSpec, params: GAParams, init_rng: np.random.Generator):
        self.spec = spec
        self.params = params
        self.generation = 0
        self.population = np.stack([lecun_genome(spec, init_rng) for _ in range(params.population)])
        self.initial = self.population.copy()
        self.ancestor = np.arange(params.population)  # generation-0 ancestor of each genome

    def ask(self) -> np.ndarray:
        """The genomes of the current generation (a read-only view), (N, n_parameters)."""
        view = self.population.view()
        view.flags.writeable = False
        return view

    def ranking(self, fitness: np.ndarray) -> np.ndarray:
        """Indices from best to worst; equal fitness keeps the lower index first."""
        return np.argsort(-fitness, kind="stable")

    def tell(self, fitness: np.ndarray, rng: np.random.Generator) -> GenerationSummary:
        """Record the fitness of ``ask()`` and build the next generation with ``rng``."""
        fitness = np.asarray(fitness, dtype=np.float64)
        n = self.params.population
        if fitness.shape != (n,) or not np.all(np.isfinite(fitness)):
            raise ValueError(f"fitness must be {n} finite values")
        order = self.ranking(fitness)
        best = int(order[0])
        centroid = self.population.mean(axis=0)
        summary = GenerationSummary(
            generation=self.generation,
            fitness_max=float(fitness.max()),
            fitness_mean=float(fitness.mean()),
            fitness_median=float(np.median(fitness)),
            fitness_std=float(fitness.std()),
            zero_share=float((fitness == 0.0).mean()),
            diversity=float(np.linalg.norm(self.population - centroid, axis=1).mean()),
            best_norm=float(np.linalg.norm(self.population[best])),
            best_drift=float(
                np.linalg.norm(self.population[best] - self.initial[self.ancestor[best]])
            ),
            best_index=best,
        )

        k, t = self.params.elite, self.params.tournament
        elites = order[:k]
        parents = np.empty(n - k, dtype=np.int64)
        for child in range(n - k):
            contenders = rng.choice(n, size=t, replace=False)
            # the best contender; ties go to the lower index, as in the ranking
            parents[child] = min(contenders, key=lambda i: (-fitness[i], i))
        noise = rng.normal(0.0, self.params.sigma, size=(n - k, self.population.shape[1]))
        self.population = np.concatenate(
            (self.population[elites], self.population[parents] + noise)
        )
        self.ancestor = np.concatenate((self.ancestor[elites], self.ancestor[parents]))
        self.generation += 1
        return summary
