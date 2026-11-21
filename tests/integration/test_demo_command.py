"""F9: the presentation menu resolves choices to the policies of run/view."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from neuroeco.presentation.cli import app
from neuroeco.presentation.demo import count_overrides, policy_for

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "results/experiments/f8/runs"


def test_policies_point_to_the_formal_runs() -> None:
    assert policy_for("rules", "prey", "B", 0) == "rules"
    assert policy_for("random", "predator", "C", 0) == "random"
    trained = policy_for("trained", "predator", "B", 3, RUNS)
    assert trained.endswith("f8_predator_base_B_r3/selected.npz")
    untrained = policy_for("untrained", "prey", "A", 0, RUNS)
    assert untrained.endswith("f8_prey_base_A_r0/checkpoints/gen_0000.npz")
    assert policy_for("compact", "prey", "A", 9, RUNS).endswith("f8_prey_compact_A_r9/selected.npz")


@pytest.mark.parametrize(
    ("brain", "scenario", "run", "message"),
    [
        ("compact", "B", 0, "scenario A only"),
        ("trained", "A", 10, "between 0 and 9"),
        ("smart", "A", 0, "unknown brain"),
    ],
)
def test_invalid_choices_are_rejected(brain, scenario, run, message) -> None:
    with pytest.raises(ValueError, match=message):
        policy_for(brain, "prey", scenario, run, RUNS)


def test_missing_models_are_reported(tmp_path) -> None:
    with pytest.raises(ValueError, match="model not found"):
        policy_for("trained", "prey", "A", 0, tmp_path)


def test_population_limits() -> None:
    assert count_overrides(None, None) == []
    assert count_overrides(40, 6) == ["world.n_prey=40", "world.n_predators=6"]
    with pytest.raises(ValueError, match="n_prey"):
        count_overrides(51, None)
    with pytest.raises(ValueError, match="n_predators"):
        count_overrides(None, 0)


def test_options_run_one_episode_in_the_terminal(monkeypatch) -> None:
    monkeypatch.chdir(ROOT)
    options = ["--scenario", "A", "--prey", "rules", "--predator", "untrained", "--mode", "run"]
    result = CliRunner().invoke(app, ["demo", *options])
    assert result.exit_code == 0, result.output
    assert "captures            0" in result.output  # the untrained predator never captures


def test_menu_runs_and_asks_for_another_episode(monkeypatch) -> None:
    monkeypatch.chdir(ROOT)
    # scenario A, prey rules, predator trained, terminal, 25 prey, 3 predators, no more
    answers = "1\n1\n2\n2\n\n\nn\n"
    result = CliRunner().invoke(app, ["demo"], input=answers)
    assert result.exit_code == 0, result.output
    assert "=== NeuroEcosistema: demo ===" in result.output
    assert "f8_predator_base_A_r0/selected.npz" in result.output
    assert "captured fraction" in result.output


def test_invalid_option_exits_with_an_error(monkeypatch) -> None:
    monkeypatch.chdir(ROOT)
    options = ["--scenario", "B", "--prey", "compact", "--predator", "rules", "--mode", "run"]
    result = CliRunner().invoke(app, ["demo", *options])
    assert result.exit_code == 1


def test_view_mode_calls_the_viewer_with_the_resolved_options(monkeypatch) -> None:
    import neuroeco.presentation.cli as cli

    monkeypatch.chdir(ROOT)
    calls = []
    monkeypatch.setattr(cli, "view", lambda *args, **kwargs: calls.append((args, kwargs)))
    options = ["--scenario", "C", "--prey", "trained", "--predator", "rules", "--n-prey", "40"]
    result = CliRunner().invoke(app, ["demo", *options])
    assert result.exit_code == 0, result.output
    ((args, kwargs),) = calls
    assert args[0] == "C" and args[1].endswith("f8_prey_base_C_r0/selected.npz")
    assert args[2] == "rules" and args[4] == ["world.n_prey=40"]
    assert kwargs["paused"] is True and kwargs["exit_at_end"] is False
