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


def _ask_int(label: str, default: int, low: int, high: int) -> int:
    while True:
        value = typer.prompt(label, default=default, type=int)
        if low <= value <= high:
            return value
        typer.echo(f"  elige un número entre {low} y {high}")


def _choose(title: str, options: dict[str, str], default: str) -> str:
    keys = list(options)
    typer.echo(f"\n{title}")
    for number, key in enumerate(keys, start=1):
        typer.echo(f"  [{number}] {options[key]}")
    return keys[_ask_int("  >", keys.index(default) + 1, 1, len(keys)) - 1]


def _optional_count(label: str, limits: tuple[int, int], default: int) -> int | None:
    value = _ask_int(f"  {label} ({limits[0]}-{limits[1]})", default, *limits)
    return None if value == default else value


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
    """Presentation menu: pick the scenario and the brain of each species, then watch it."""
    # Imported here: cli imports this module to register the command.
    from neuroeco.bootstrap import DEFAULT_CONFIG_DIR
    from neuroeco.presentation.cli import run as run_command
    from neuroeco.presentation.cli import view as view_command

    interactive = scenario is None or prey is None or predator is None
    if interactive:
        typer.echo("=== NeuroEcosistema: demo ===")
    while True:
        if interactive:
            scenario = _choose("1) Escenario:", SCENARIOS, scenario or "A")
            brains = (
                BRAINS if scenario == "A" else {k: v for k, v in BRAINS.items() if k != "compact"}
            )
            prey = _choose("2) Cerebro de las PRESAS:", brains, "rules")
            predator = _choose("3) Cerebro de los DEPREDADORES:", brains, "trained")
            mode = _choose(
                "4) ¿Cómo quieres verlo?",
                {"view": "Visor (ventana)", "run": "Solo resultados en la terminal"},
                "view",
            )
            typer.echo("\n5) Cantidad de agentes (Enter = valores del escenario):")
            n_prey = _optional_count("Presas", PREY_LIMITS, 25)
            n_predators = _optional_count(
                "Depredadores", PREDATOR_LIMITS, 5 if scenario == "C" else 3
            )
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

        typer.echo(
            f"\nescenario {scenario} ({SCENARIOS[scenario]}): presas = {BRAINS[prey]}, "
            f"depredadores = {BRAINS[predator]}"
        )
        if mode == "run":
            run_command(
                scenario, prey_policy, predator_policy, episode, overrides, DEFAULT_CONFIG_DIR
            )
        else:
            view_command(
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
        if not interactive or not typer.confirm("\n¿Ver otra partida?", default=True):
            return
