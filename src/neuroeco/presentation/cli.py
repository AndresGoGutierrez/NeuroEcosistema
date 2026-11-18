"""Command-line interface."""

from __future__ import annotations

import dataclasses
import datetime as dt
import math
import statistics
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Any

import typer

from neuroeco.application.configs import ResolvedConfig
from neuroeco.application.evaluation import EpisodeIdentity, run_episode, time_episode
from neuroeco.application.metrics import EpisodeMetrics, Ratio
from neuroeco.application.seeding import Purpose
from neuroeco.application.session import run_session
from neuroeco.bootstrap import (
    DEFAULT_CONFIG_DIR,
    EXPLORATORY_SEED_GROUP,
    REFERENCE_POLICIES,
    build_policy,
    build_runtime,
)
from neuroeco.domain.neural import NeuralPolicy
from neuroeco.domain.params import ConfigurationError
from neuroeco.domain.simulator import PHASES
from neuroeco.domain.state import InitializationError
from neuroeco.infrastructure.config_loader import ConfigError, load_p0_spec
from neuroeco.infrastructure.provenance import collect_provenance
from neuroeco.infrastructure.storage import (
    new_run_directory,
    replace_json,
    write_csv,
    write_json,
)
from neuroeco.presentation.experiment import (
    experiment_analyze,
    experiment_evaluate,
    experiment_train,
)
from neuroeco.presentation.inspector import SessionInfo
from neuroeco.presentation.pilot_i2 import pilot_i2
from neuroeco.presentation.pilot_p0b import pilot_p0b
from neuroeco.presentation.pilot_p1 import pilot_p1
from neuroeco.presentation.pilot_p1_criteria import pilot_p1_criteria
from neuroeco.presentation.pilot_p1_reserve import pilot_p1_reserve
from neuroeco.presentation.pilot_p1_sequence import pilot_p1_sequence
from neuroeco.presentation.pilot_p2 import pilot_p2, pilot_p2_decide
from neuroeco.presentation.train import train_command

app = typer.Typer(no_args_is_help=True, help="NeuroEcosistema command-line interface.")
pilot_app = typer.Typer(no_args_is_help=True, help="Pilot studies.")
app.add_typer(pilot_app, name="pilot")
pilot_app.command("p1")(pilot_p1)  # F4 T3 (ADR-033)
pilot_app.command("p1-criteria")(pilot_p1_criteria)  # F4 T4-I3 (ADR-033, D1)
pilot_app.command("p1-sequence")(pilot_p1_sequence)  # F4 T4b (ADR-033 P1-18, D-T4b-1)
pilot_app.command("p1-reserve")(pilot_p1_reserve)  # F4 T4d (D-T4d-4)
pilot_app.command("i2")(pilot_i2)  # F5 (ADR-018, I2)
pilot_app.command("p0b")(pilot_p0b)  # F6 (decision A3, O4)
pilot_app.command("p2")(pilot_p2)  # F6 (ADR-035)
pilot_app.command("p2-decide")(pilot_p2_decide)  # F6 (ADR-035)
app.command("train")(train_command)  # F6 (ADR-027)
experiment_app = typer.Typer(help="Formal experiments (F8).", no_args_is_help=True)
app.add_typer(experiment_app, name="experiment")
experiment_app.command("train")(experiment_train)
experiment_app.command("evaluate")(experiment_evaluate)
experiment_app.command("analyze")(experiment_analyze)

USER_ERRORS = (ConfigError, ConfigurationError, InitializationError, ValueError)

VIEW_RECORD_SCHEMA = "neuroeco.view-session/1"


def metrics_to_json(metrics: EpisodeMetrics) -> dict[str, Any]:
    """Exact JSON form of the metrics: ratios as integers, undefined values as null."""
    data: dict[str, Any] = {}
    for field in dataclasses.fields(metrics):
        value = getattr(metrics, field.name)
        if isinstance(value, Ratio):
            data[field.name] = {"numerator": value.numerator, "denominator": value.denominator}
        elif isinstance(value, float) and math.isnan(value):
            data[field.name] = None
        else:
            data[field.name] = value
    return data


def build_view_record(
    *,
    session_id: str,
    config: ResolvedConfig,
    overrides: Sequence[str],
    prey_policy: str,
    predator_policy: str,
    identity: EpisodeIdentity,
    viewer_options: dict[str, Any],
    provenance: dict[str, Any],
) -> dict[str, Any]:
    """Initial record of a `view` session (ADR-031, decision V2); status `running`."""
    return {
        "schema": VIEW_RECORD_SCHEMA,
        "session_id": session_id,
        "status": "running",
        "ended_utc": None,
        "scenario": config.scenario,
        "overrides": list(overrides),  # literal, in the order given
        "config_hash": config.config_hash,
        "project_seed": config.project_seed,
        "seed_identity": {
            "purpose": identity.purpose.name,
            "purpose_code": int(identity.purpose),
            "seed_group": identity.seed_group,
            "run": identity.run,
            "generation": identity.generation,
            "item": identity.item,
        },
        "policies": {"prey": prey_policy, "predator": predator_policy},
        "world": dataclasses.asdict(config.world),
        "rules": dataclasses.asdict(config.rules),
        "viewer": dict(viewer_options),
        "provenance": provenance,
        "steps_completed": None,
        "metrics": None,
        "error": None,
    }


@app.callback()
def main() -> None:
    """NeuroEcosistema: predator-prey ecosystem driven by neural networks."""


@app.command()
def run(
    scenario: Annotated[str, typer.Option(help="Scenario: A, B or C.")] = "A",
    prey: Annotated[
        str, typer.Option(help=f"Prey policy: {', '.join(REFERENCE_POLICIES)} or model:<file>.")
    ] = ("rules"),
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
    except USER_ERRORS as error:
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


def _utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


@app.command()
def view(
    scenario: Annotated[str, typer.Option(help="Scenario: A, B or C.")] = "A",
    prey: Annotated[
        str, typer.Option(help=f"Prey policy: {', '.join(REFERENCE_POLICIES)} or model:<file>.")
    ] = ("rules"),
    predator: Annotated[str, typer.Option(help="Predator policy (same choices).")] = "rules",
    episode: Annotated[int, typer.Option(min=0, help="Episode index (seed item).")] = 0,
    overrides: Annotated[
        list[str] | None, typer.Option("--set", help="Override, e.g. world.n_predators=10.")
    ] = None,
    config_dir: Annotated[Path, typer.Option(help="Configuration directory.")] = (
        DEFAULT_CONFIG_DIR
    ),
    output_dir: Annotated[Path, typer.Option(help="Where session records are written.")] = Path(
        "runs/view"
    ),
    paused: Annotated[bool, typer.Option(help="Start paused at the initial state.")] = True,
    speed: Annotated[int, typer.Option(help="Initial steps per frame: 1, 2, 4, 8, 16, 32.")] = 1,
    fps: Annotated[int, typer.Option(min=0, help="Frame-rate cap (0 = unlimited).")] = 30,
    exit_at_end: Annotated[
        bool, typer.Option(help="Close the window when the episode ends.")
    ] = False,
) -> None:
    """Watch one exploratory episode (same seeds as `run`) with the HUD and the inspector."""
    try:
        # pygame is imported here only: `run` and `pilot` never load it (ADR-031).
        from neuroeco.presentation.viewer import SPEEDS, Viewer, ViewerClosed

        if speed not in SPEEDS:
            raise ValueError(f"speed must be one of {SPEEDS}, got {speed}")
        runtime = build_runtime(scenario, overrides or (), config_dir)
        config = runtime.config
        prey_policy = build_policy(prey, "prey", config)
        predator_policy = build_policy(predator, "predator", config)
    except USER_ERRORS as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=1) from error

    identity = EpisodeIdentity(Purpose.PILOT, EXPLORATORY_SEED_GROUP, item=episode)
    options = {"paused": paused, "speed": speed, "fps": fps, "exit_at_end": exit_at_end}
    # Provenance first, so `git_dirty` describes the code, not the record written below.
    provenance = collect_provenance(sys.argv, Path.cwd(), config.config_hash)
    directory = new_run_directory(output_dir, dt.datetime.now(dt.UTC))
    record_path = directory / "session.json"
    record = build_view_record(
        session_id=directory.name,
        config=config,
        overrides=overrides or (),
        prey_policy=prey,
        predator_policy=predator,
        identity=identity,
        viewer_options=options,
        provenance=provenance,
    )
    replace_json(record_path, record)  # exists before the episode starts (decision V2)
    typer.echo(f"session record: {record_path}")

    info = SessionInfo(scenario, prey, predator, episode, config.config_hash)
    viewer = None
    exit_code = 0
    try:
        networks = {
            species: policy.network
            for species, policy in (("prey", prey_policy), ("predator", predator_policy))
            if isinstance(policy, NeuralPolicy)
        }
        viewer = Viewer(
            config.world,
            info,
            paused=paused,
            speed=speed,
            fps=fps,
            exit_at_end=exit_at_end,
            networks=networks,
        )
        result = run_session(
            config.world, prey_policy, predator_policy, runtime.registry, identity, viewer
        )
        record.update(
            status="completed",
            ended_utc=_utc_now(),
            steps_completed=result.metrics.steps,
            metrics=metrics_to_json(result.metrics),
        )
        replace_json(record_path, record)
        viewer.finish()
    except ViewerClosed as closed:
        record.update(status="closed", ended_utc=_utc_now(), steps_completed=closed.step)
    except KeyboardInterrupt:
        steps = viewer.frame.step if viewer is not None and viewer.frame is not None else None
        record.update(status="interrupted", ended_utc=_utc_now(), steps_completed=steps)
        exit_code = 130
    except Exception as error:
        record.update(
            status="error", ended_utc=_utc_now(), error=f"{type(error).__name__}: {error}"
        )
        replace_json(record_path, record)
        raise
    finally:
        if viewer is not None:
            viewer.close()
    replace_json(record_path, record)
    typer.echo(f"status {record['status']}, steps {record['steps_completed']}")
    if exit_code:
        raise typer.Exit(code=exit_code)


P0_EPISODE_COLUMNS = (
    "n_prey",
    "n_predators",
    "n_plants",
    "repetition",
    "seed_item",
    "steps",
    "seconds",
    "us_per_step",
    *(f"{phase}_us_per_step" for phase in PHASES),
)
P0_SUMMARY_COLUMNS = (
    "n_prey",
    "n_predators",
    "repetitions",
    "median_us_per_step",
    "min_us_per_step",
    "max_us_per_step",
    *(f"median_{phase}_us_per_step" for phase in PHASES),
)
WARMUP_STEPS = 50


@pilot_app.command("p0")
def pilot_p0(
    spec_path: Annotated[Path, typer.Option("--spec", help="P0 specification.")] = (
        DEFAULT_CONFIG_DIR / "pilots" / "p0.yaml"
    ),
    config_dir: Annotated[Path, typer.Option(help="Configuration directory.")] = (
        DEFAULT_CONFIG_DIR
    ),
    output_dir: Annotated[Path, typer.Option(help="Output directory.")] = Path("results/pilots/p0"),
    repetitions: Annotated[
        int | None, typer.Option(min=1, help="Override the number of repetitions.")
    ] = None,
    overrides: Annotated[list[str] | None, typer.Option("--set", help="World override.")] = None,
) -> None:
    """Pilot P0: simulation cost per step over the (n_prey x n_predators) grid."""
    try:
        spec = load_p0_spec(spec_path)
        if repetitions is not None:
            spec = dataclasses.replace(spec, repetitions=repetitions)
        runtime = build_runtime(spec.scenario, overrides or (), config_dir)
        config = runtime.config
        prey_policy = build_policy(spec.prey_policy, "prey", config)
        predator_policy = build_policy(spec.predator_policy, "predator", config)
        # Provenance is captured BEFORE any output exists, so `git_dirty` describes the code
        # that is measured, not the result files this command is about to write.
        provenance = collect_provenance(sys.argv, Path.cwd(), config.config_hash)
        clock = time.perf_counter

        def identity(item: int) -> EpisodeIdentity:
            return EpisodeIdentity(Purpose.PILOT, spec.seed_group, item=item)

        warmup = dataclasses.replace(
            config.world,
            n_prey=spec.reference_prey,
            n_predators=spec.reference_predators,
            t_max=min(WARMUP_STEPS, config.world.t_max),
        )  # not recorded; uses an item outside the measured range
        time_episode(
            warmup,
            prey_policy,
            predator_policy,
            runtime.registry,
            identity(spec.repetitions),
            clock,
        )

        episodes: list[dict[str, object]] = []
        summary: list[dict[str, object]] = []
        for n_prey in spec.prey_counts:
            for n_predators in spec.predator_counts:
                params = dataclasses.replace(config.world, n_prey=n_prey, n_predators=n_predators)
                cell: list[dict[str, float]] = []
                for repetition in range(spec.repetitions):
                    timed = time_episode(
                        params,
                        prey_policy,
                        predator_policy,
                        runtime.registry,
                        identity(repetition),
                        clock,
                    )
                    row = {
                        "us_per_step": 1e6 * timed.seconds_per_step,
                        **{
                            f"{phase}_us_per_step": 1e6 * timed.phase_seconds[phase] / timed.steps
                            for phase in PHASES
                        },
                    }
                    cell.append(row)
                    episodes.append(
                        {
                            "n_prey": n_prey,
                            "n_predators": n_predators,
                            "n_plants": params.n_plants,
                            "repetition": repetition,
                            "seed_item": repetition,
                            "steps": timed.steps,
                            "seconds": f"{timed.total_seconds:.6f}",
                            **{key: f"{value:.3f}" for key, value in row.items()},
                        }
                    )
                per_step = [row["us_per_step"] for row in cell]
                summary.append(
                    {
                        "n_prey": n_prey,
                        "n_predators": n_predators,
                        "repetitions": spec.repetitions,
                        "median_us_per_step": f"{statistics.median(per_step):.3f}",
                        "min_us_per_step": f"{min(per_step):.3f}",
                        "max_us_per_step": f"{max(per_step):.3f}",
                        **{
                            f"median_{phase}_us_per_step": (
                                f"{statistics.median(r[f'{phase}_us_per_step'] for r in cell):.3f}"
                            )
                            for phase in PHASES
                        },
                    }
                )
    except USER_ERRORS as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=1) from error

    reference = next(
        row
        for row in summary
        if row["n_prey"] == spec.reference_prey and row["n_predators"] == spec.reference_predators
    )
    c_step = float(reference["median_us_per_step"])
    verdict = "PASS" if c_step <= spec.threshold_us else "FAIL"

    write_csv(output_dir / "p0_episodes.csv", P0_EPISODE_COLUMNS, episodes)
    write_csv(output_dir / "p0_summary.csv", P0_SUMMARY_COLUMNS, summary)
    write_json(
        output_dir / "p0_provenance.json",
        {
            **provenance,
            "spec": dataclasses.asdict(spec),
            "world_overrides": list(overrides or ()),
            "reference": {"n_prey": spec.reference_prey, "n_predators": spec.reference_predators},
            "reference_c_step_us": c_step,
            "threshold_us": spec.threshold_us,
            "verdict": verdict,
        },
    )

    typer.echo("n_prey  n_pred  median_us  perception  decision  rules")
    for row in summary:
        typer.echo(
            f"{row['n_prey']:>6}  {row['n_predators']:>6}  {row['median_us_per_step']:>9}  "
            f"{row['median_perception_us_per_step']:>10}  {row['median_decision_us_per_step']:>8}  "
            f"{row['median_rules_us_per_step']:>6}"
        )
    typer.echo(
        f"reference ({spec.reference_prey} prey, {spec.reference_predators} predators): "
        f"c_step = {c_step:.1f} us  threshold = {spec.threshold_us:.0f} us  -> {verdict}"
    )
    typer.echo(f"results written to {output_dir}")
