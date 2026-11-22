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
    assert "Capturas: 0 " in result.output  # the untrained predator never captures


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


def test_menu_state_enforces_the_demo_rules() -> None:
    from neuroeco.presentation.launcher import MenuState

    state = MenuState(prey="compact")
    assert "compact" in state.brains()
    state.set_scenario("C")
    assert state.prey == "trained" and "compact" not in state.brains()
    assert (state.n_prey, state.n_predators) == (25, 5) and state.overrides() == []
    for _ in range(20):
        state.change("n_predators", +1)
        state.change("run", +1)
    assert state.n_predators == 10 and state.run == 9
    assert state.overrides() == ["world.n_predators=10"]
    state.change("episode", -1)
    assert state.episode == 0
    for _ in range(150):
        state.change("episode", +1)
    assert state.episode == 99


def test_menu_episode_reaches_the_viewer_and_the_quick_results(monkeypatch) -> None:
    from neuroeco.presentation import demo, launcher

    opened = iter(["view", "quit"])
    quick_lines: list[list[str]] = []

    def fake_open(self) -> str:
        self.state.episode = 7
        quick_lines.append(self.quick_run(self.state))
        return next(opened)

    viewed: list[int] = []
    monkeypatch.chdir(ROOT)
    monkeypatch.setattr(launcher.Launcher, "open", fake_open)
    monkeypatch.setattr(demo, "_view", lambda *args: viewed.append(args[4]))
    monkeypatch.setattr(
        demo, "quick_results", lambda scenario, prey, predator, overrides, episode: [episode]
    )
    demo._menu_loop(episode=3)
    assert viewed == [7]
    assert quick_lines == [[7], [7]]


def test_menu_window_clicks_choose_and_start(monkeypatch) -> None:
    import pygame

    import viewer_support  # noqa: F401  (headless SDL)
    from neuroeco.presentation.launcher import Launcher, MenuState

    monkeypatch.chdir(ROOT)
    state = MenuState()
    launcher = Launcher(state, lambda menu: ["ok"], fps=0)
    clicks = iter(
        ["B  Escasez de comida", "Azar", "Resultados rápidos", "Ver en el visor  (Enter)"]
    )

    def events():
        label = next(clicks)
        button = next(b for b in launcher.buttons if b.label == label)
        return [pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=button.rect.center)]

    launcher._events = events
    assert launcher.open() == "view"
    assert state.scenario == "B" and state.prey == "random" and state.message == ["ok"]


def test_menu_window_episode_buttons_fit_and_change_the_seed() -> None:
    import pygame

    import viewer_support  # noqa: F401  (headless SDL)
    from neuroeco.presentation.launcher import Launcher, MenuState
    from neuroeco.presentation.viewer import CANVAS_PIXELS

    state = MenuState()
    launcher = Launcher(state, lambda menu: ["ok"], fps=0)
    presses = iter([("+", 3), ("+", 3), ("-", 3), (None, None)])

    def events():
        label, group = next(presses)
        if label is None:
            return [pygame.event.Event(pygame.QUIT)]
        steppers = [b for b in launcher.buttons if b.label == label]
        button = steppers[group]
        return [pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=button.rect.center)]

    launcher._events = events
    assert launcher.open() == "quit"
    assert state.episode == 1 and state.run == 0
    rects = [b.rect for b in launcher.buttons]
    assert all(r.right <= CANVAS_PIXELS for r in rects)
    assert not any(a.colliderect(b) for i, a in enumerate(rects) for b in rects[i + 1 :])
