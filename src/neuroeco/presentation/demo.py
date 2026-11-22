"""``neuroeco demo``: one command for the presentation (F9).

It asks (or takes as options) the scenario, the brain of each species and how to show the
episode, resolves them to the policies of ``run`` and ``view`` (trained networks of the formal
campaign F8) and calls those commands; it adds no simulation logic. The menu is in Spanish
because it is shown to the audience of the demo.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

RUNS = Path("results/experiments/f8/runs")
BRAINS = {
    "rules": "Reglas escritas a mano",
    "trained": "Red neuronal entrenada",
    "untrained": "Red neuronal sin entrenar (generación 0)",
    "random": "Movimiento al azar",
    "compact": "Red neuronal compacta entrenada (solo escenario A)",
}
SCENARIOS = {"A": "Abundancia", "B": "Escasez de comida", "C": "Presión de depredación"}
PREY_LIMITS = (5, 50)
PREDATOR_LIMITS = (1, 10)
RUN_LIMITS = (0, 9)
EPISODE_LIMITS = (0, 99)  # seed item of the exploratory group: never a TEST seed


def policy_for(brain: str, species: str, scenario: str, run: int, runs: Path = RUNS) -> str:
    """The ``--prey`` / ``--predator`` value of ``run`` and ``view`` for a menu choice."""
    if brain in ("rules", "random"):
        return brain
    if brain not in BRAINS:
        raise ValueError(f"unknown brain {brain!r}; choose one of {', '.join(BRAINS)}")
    if not RUN_LIMITS[0] <= run <= RUN_LIMITS[1]:
        raise ValueError(f"run must be between {RUN_LIMITS[0]} and {RUN_LIMITS[1]}")
    if brain == "compact":
        if scenario != "A":
            raise ValueError("the compact networks were trained in scenario A only (ADR-005)")
        directory = runs / f"f8_{species}_compact_A_r{run}"
    else:
        directory = runs / f"f8_{species}_base_{scenario}_r{run}"
    model = directory / ("checkpoints/gen_0000.npz" if brain == "untrained" else "selected.npz")
    if not model.exists():
        raise ValueError(f"model not found: {model}")
    return f"model:{model.as_posix()}"


def count_overrides(n_prey: int | None, n_predators: int | None) -> list[str]:
    """``--set`` overrides for the population, within the demo limits."""
    overrides = []
    for value, (low, high), key in (
        (n_prey, PREY_LIMITS, "world.n_prey"),
        (n_predators, PREDATOR_LIMITS, "world.n_predators"),
    ):
        if value is None:
            continue
        if not low <= value <= high:
            raise ValueError(f"{key} must be between {low} and {high}, got {value}")
        overrides.append(f"{key}={value}")
    return overrides


def quick_results(
    scenario: str, prey_policy: str, predator_policy: str, overrides: list[str], episode: int = 0
) -> list[str]:
    """Metrics of one episode (same seeds as the viewer), as lines for the menu."""
    from neuroeco.application.evaluation import EpisodeIdentity, run_episode
    from neuroeco.application.seeding import Purpose
    from neuroeco.bootstrap import (
        DEFAULT_CONFIG_DIR,
        EXPLORATORY_SEED_GROUP,
        build_policy,
        build_runtime,
    )

    runtime = build_runtime(scenario, overrides, DEFAULT_CONFIG_DIR)
    world = runtime.config.world
    result = run_episode(
        world,
        build_policy(prey_policy, "prey", runtime.config),
        build_policy(predator_policy, "predator", runtime.config),
        runtime.registry,
        EpisodeIdentity(Purpose.PILOT, EXPLORATORY_SEED_GROUP, item=episode),
    )
    m = result.metrics
    alive = round(m.prey_alive_fraction_end.value * world.n_prey)
    return [
        f"Partida {episode}: {m.steps} de {world.t_max} pasos (mismas semillas que el visor)",
        f"Supervivencia media de las presas: {m.prey_survival.value:.3f}",
        f"Presas vivas al final: {alive} de {world.n_prey}",
        f"Capturas: {m.captures} (fracción capturada {m.captured_fraction.value:.3f})",
        f"Presas muertas de hambre: {100 * m.starvation_incidence_end:.0f} %",
        f"Plantas comidas: {m.plants_eaten}",
        f"Depredadores vivos al final: {m.predators_alive_end} de {world.n_predators}",
    ]


def demo_command(
    scenario: Annotated[str | None, typer.Option(help="A, B or C; omit for the menu.")] = None,
    prey: Annotated[str | None, typer.Option(help=f"Prey brain: {', '.join(BRAINS)}.")] = None,
    predator: Annotated[str | None, typer.Option(help="Predator brain (same choices).")] = None,
    mode: Annotated[str, typer.Option(help="view (window) or run (terminal).")] = "view",
    run: Annotated[int, typer.Option(help="Formal run 0-9 whose networks are used.")] = 0,
    episode: Annotated[int, typer.Option(min=0, help="Episode index (seed item).")] = 0,
    n_prey: Annotated[int | None, typer.Option(help="Number of prey (5-50).")] = None,
    n_predators: Annotated[int | None, typer.Option(help="Number of predators (1-10).")] = None,
) -> None:
    """Presentation menu (a window): pick the scenario and the brains, then watch the episode.

    With --scenario, --prey and --predator it skips the menu and runs that choice directly.
    """
    if scenario is None or prey is None or predator is None:
        _menu_loop(episode)
        return
    try:
        if scenario not in SCENARIOS:
            raise ValueError(f"scenario must be A, B or C, got {scenario!r}")
        if mode not in ("view", "run"):
            raise ValueError(f"mode must be view or run, got {mode!r}")
        prey_policy = policy_for(prey, "prey", scenario, run)
        predator_policy = policy_for(predator, "predator", scenario, run)
        overrides = count_overrides(n_prey, n_predators)
    except ValueError as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=1) from error
    if mode == "run":
        lines = quick_results(scenario, prey_policy, predator_policy, overrides, episode)
        typer.echo("\n".join(lines))
    else:
        _view(scenario, prey_policy, predator_policy, overrides, episode)


def _view(
    scenario: str, prey_policy: str, predator_policy: str, overrides: list[str], episode: int
) -> None:
    # Imported here: cli imports this module to register the command.
    from neuroeco.bootstrap import DEFAULT_CONFIG_DIR
    from neuroeco.presentation import cli

    cli.view(
        scenario,
        prey_policy,
        predator_policy,
        episode,
        overrides,
        DEFAULT_CONFIG_DIR,
        Path("runs/view"),
        paused=True,
        speed=1,
        fps=30,
        exit_at_end=False,
    )


def _menu_loop(episode: int) -> None:
    from neuroeco.presentation.launcher import Launcher, MenuState

    state = MenuState(episode=min(max(episode, EPISODE_LIMITS[0]), EPISODE_LIMITS[1]))

    def quick(menu: MenuState) -> list[str]:
        prey_policy, predator_policy = menu.policies()
        return quick_results(
            menu.scenario, prey_policy, predator_policy, menu.overrides(), menu.episode
        )

    while Launcher(state, quick).open() == "view":
        prey_policy, predator_policy = state.policies()
        try:
            _view(state.scenario, prey_policy, predator_policy, state.overrides(), state.episode)
            state.message = []
        except typer.Exit:
            state.message = ["error: el visor no pudo abrir esta partida (ver la terminal)"]
