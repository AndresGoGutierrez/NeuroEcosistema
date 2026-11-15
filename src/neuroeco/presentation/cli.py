"""Command-line interface."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from neuroeco.application.evaluation import EpisodeIdentity, run_episode
from neuroeco.application.seeding import Purpose
from neuroeco.bootstrap import (
    DEFAULT_CONFIG_DIR,
    EXPLORATORY_SEED_GROUP,
    REFERENCE_POLICIES,
    build_policy,
    build_runtime,
)
from neuroeco.domain.params import ConfigurationError
from neuroeco.domain.state import InitializationError
from neuroeco.infrastructure.config_loader import ConfigError

app = typer.Typer(no_args_is_help=True, help="NeuroEcosistema command-line interface.")


@app.callback()
def main() -> None:
    """NeuroEcosistema: predator-prey ecosystem driven by neural networks."""


@app.command()
def run(
    scenario: Annotated[str, typer.Option(help="Scenario: A, B or C.")] = "A",
    prey: Annotated[str, typer.Option(help=f"Prey policy: {', '.join(REFERENCE_POLICIES)}.")] = (
        "rules"
    ),
    predator: Annotated[str, typer.Option(help="Predator policy (same choices).")] = "rules",
    episode: Annotated[int, typer.Option(min=0, help="Episode index (seed item).")] = 0,
    overrides: Annotated[
        list[str] | None, typer.Option("--set", help="Override, e.g. world.n_plants=20.")
    ] = None,
    config_dir: Annotated[Path, typer.Option(help="Configuration directory.")] = (
        DEFAULT_CONFIG_DIR
    ),
) -> None:
    """Run one exploratory episode and print its metrics."""
    try:
        runtime = build_runtime(scenario, overrides or (), config_dir)
        config = runtime.config
        identity = EpisodeIdentity(Purpose.PILOT, EXPLORATORY_SEED_GROUP, item=episode)
        result = run_episode(
            config.world,
            build_policy(prey, "prey", config),
            build_policy(predator, "predator", config),
            runtime.registry,
            identity,
        )
    except (ConfigError, ConfigurationError, InitializationError, ValueError) as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=1) from error

    m = result.metrics
    lines = [
        f"scenario            {scenario}   prey={prey}   predator={predator}   episode={episode}",
        f"config hash         {config.config_hash[:12]}",
        f"steps               {m.steps} / {config.world.t_max}",
        f"prey survival       {m.prey_survival.value:.4f}",
        f"prey alive at end   {m.prey_alive_fraction_end.value:.4f}",
        f"plants eaten        {m.plants_eaten}",
        f"captures            {m.captures}  (captured fraction {m.captured_fraction.value:.4f})",
        f"capture incidence   {m.capture_incidence_end:.4f}",
        f"starvation incid.   {m.starvation_incidence_end:.4f}",
        f"predators alive     {m.predators_alive_end} / {config.world.n_predators}",
    ]
    typer.echo("\n".join(lines))
