"""Graphical menu of ``neuroeco demo`` (pygame-ce, F9).

A window with buttons to pick the scenario, the brain of each species, the population and the
formal run; it launches the viewer (``view``) or shows the metrics of one episode (``run``) in
the same window. ``MenuState`` holds the choices and is independent of pygame.
"""

from __future__ import annotations

import os

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

import pygame

from neuroeco.presentation.demo import (
    BRAINS,
    EPISODE_LIMITS,
    PREDATOR_LIMITS,
    PREY_LIMITS,
    RUN_LIMITS,
    SCENARIOS,
    count_overrides,
    policy_for,
)
from neuroeco.presentation.viewer import (
    ACCENT,
    BACKGROUND,
    BAR_BACK,
    CANVAS_PIXELS,
    CARD,
    DIM_TEXT,
    FONT_NAMES,
    PANEL,
    PANEL_WIDTH,
    PLANT,
    PREDATOR,
    PREY,
    TEXT,
)

WIDTH = CANVAS_PIXELS + PANEL_WIDTH
HEIGHT = CANVAS_PIXELS
SHORT_BRAINS = {
    "rules": "Reglas",
    "trained": "Red entrenada",
    "untrained": "Sin entrenar",
    "random": "Azar",
    "compact": "Red compacta",
}
SCENARIO_HELP = {
    "A": "25 presas, 3 depredadores, 40 plantas: escenario de referencia.",
    "B": "Solo 4 plantas: las presas compiten por la comida.",
    "C": "5 depredadores: más presión de caza.",
}
BRAIN_HELP = {
    "rules": "política escrita a mano (referencia del experimento C3)",
    "trained": "red neuronal entrenada por neuroevolución (70 generaciones)",
    "untrained": "la misma red en la generación 0, con pesos al azar (antes de C1)",
    "random": "acciones al azar en cada paso",
    "compact": "red con un tercio de los parámetros (experimento C2, solo en A)",
}
STEPPERS = (
    ("n_prey", "presas", PREY),
    ("n_predators", "depredadores", PREDATOR),
    ("run", "entrenamiento", ACCENT),
    ("episode", "partida", ACCENT),
)
STEPPER_SPACING = 150
DISABLED = (70, 76, 86)
BUTTON = (44, 51, 62)
BUTTON_HOVER = (58, 66, 80)


@dataclass
class MenuState:
    """Choices of the menu; enforces the limits of ``demo``."""

    scenario: str = "A"
    prey: str = "rules"
    predator: str = "trained"
    n_prey: int = 25
    n_predators: int = 3
    run: int = 0
    episode: int = 0
    message: list[str] = field(default_factory=list)

    @staticmethod
    def default_counts(scenario: str) -> tuple[int, int]:
        return 25, 5 if scenario == "C" else 3

    def brains(self) -> list[str]:
        return [b for b in BRAINS if b != "compact" or self.scenario == "A"]

    def set_scenario(self, scenario: str) -> None:
        self.scenario = scenario
        self.n_prey, self.n_predators = self.default_counts(scenario)
        if scenario != "A":  # compact networks exist only in A (ADR-005)
            self.prey = "trained" if self.prey == "compact" else self.prey
            self.predator = "trained" if self.predator == "compact" else self.predator

    def change(self, name: str, delta: int) -> None:
        limits = {
            "n_prey": PREY_LIMITS,
            "n_predators": PREDATOR_LIMITS,
            "run": RUN_LIMITS,
            "episode": EPISODE_LIMITS,
        }[name]
        setattr(self, name, min(max(getattr(self, name) + delta, limits[0]), limits[1]))

    def overrides(self) -> list[str]:
        prey, predators = self.default_counts(self.scenario)
        return count_overrides(
            None if self.n_prey == prey else self.n_prey,
            None if self.n_predators == predators else self.n_predators,
        )

    def policies(self) -> tuple[str, str]:
        return (
            policy_for(self.prey, "prey", self.scenario, self.run),
            policy_for(self.predator, "predator", self.scenario, self.run),
        )


@dataclass
class Button:
    rect: pygame.Rect
    label: str
    action: Callable[[], str | None]
    selected: bool = False
    enabled: bool = True
    color: tuple[int, ...] = ACCENT


EventSource = Callable[[], Iterable[pygame.event.Event]]
Runner = Callable[[MenuState], list[str]]


class Launcher:
    """Menu window. ``open`` returns "view" (launch the viewer) or "quit"."""

    def __init__(
        self,
        state: MenuState,
        quick_run: Runner,
        event_source: EventSource | None = None,
        fps: int = 30,
    ) -> None:
        self.state = state
        self.quick_run = quick_run
        self._events = event_source or pygame.event.get
        self._fps = fps
        self.buttons: list[Button] = []

    def open(self) -> str:
        pygame.display.init()
        pygame.font.init()
        pygame.display.set_caption("NeuroEcosistema - demo")
        self._screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self._font = pygame.font.SysFont(FONT_NAMES, 15)
        self._small = pygame.font.SysFont(FONT_NAMES, 13)
        self._title = pygame.font.SysFont(FONT_NAMES, 24, bold=True)
        self._section = pygame.font.SysFont(FONT_NAMES, 15, bold=True)
        clock = pygame.time.Clock()
        try:
            while True:
                self._layout()
                for event in self._events():
                    result = self._handle(event)
                    if result is not None:
                        return result
                self._draw()
                pygame.display.flip()
                if self._fps:
                    clock.tick(self._fps)
        finally:
            pygame.display.quit()
            pygame.font.quit()

    # ------------------------------------------------------------ events
    def _handle(self, event: pygame.event.Event) -> str | None:
        if event.type == pygame.QUIT:
            return "quit"
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return "quit"
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                return self._start()
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for button in self.buttons:
                if button.enabled and button.rect.collidepoint(event.pos):
                    return button.action()
        return None

    def _start(self) -> str | None:
        try:
            self.state.policies()
            self.state.overrides()
        except ValueError as error:
            self.state.message = [f"error: {error}"]
            return None
        return "view"

    def _quick(self) -> None:
        try:
            self.state.message = self.quick_run(self.state)
        except ValueError as error:
            self.state.message = [f"error: {error}"]

    # ------------------------------------------------------------ layout
    def _layout(self) -> None:
        s = self.state
        self.buttons = []
        left = 32

        def add(x, y, w, label, action, selected=False, enabled=True, color=ACCENT):
            rect = pygame.Rect(x, y, w, 34)
            self.buttons.append(Button(rect, label, action, selected, enabled, color))

        for i, key in enumerate(SCENARIOS):
            add(
                left + i * 196,
                112,
                186,
                f"{key}  {SCENARIOS[key]}",
                lambda key=key: s.set_scenario(key),
                s.scenario == key,
            )
        for row, (species, color) in enumerate((("prey", PREY), ("predator", PREDATOR))):
            for i, brain in enumerate(BRAINS):
                enabled = brain in s.brains()
                add(
                    left + i * 118,
                    206 + row * 86,
                    112,
                    SHORT_BRAINS[brain],
                    lambda species=species, brain=brain: setattr(s, species, brain),
                    getattr(s, species) == brain,
                    enabled,
                    color,
                )
        for i, (name, _label, color) in enumerate(STEPPERS):
            x = left + i * STEPPER_SPACING
            add(x, 388, 36, "-", lambda name=name: s.change(name, -1), color=color)
            add(x + 96, 388, 36, "+", lambda name=name: s.change(name, +1), color=color)
        add(
            left,
            452,
            150,
            "Restablecer",
            lambda: (
                setattr(s, "n_prey", s.default_counts(s.scenario)[0])
                or setattr(s, "n_predators", s.default_counts(s.scenario)[1])
            ),
        )
        add(left, 540, 250, "Ver en el visor  (Enter)", self._start, True)
        add(left + 266, 540, 220, "Resultados rápidos", self._quick)
        add(left + 502, 540, 100, "Salir", lambda: "quit")

    # ------------------------------------------------------------ drawing
    def _draw(self) -> None:
        screen = self._screen
        screen.fill(BACKGROUND)
        s = self.state
        left = 32
        self._blit("NeuroEcosistema", (left, 24), ACCENT, self._title)
        self._blit(
            "Elige el escenario y el cerebro de cada especie; luego abre el visor.",
            (left, 58),
            DIM_TEXT,
        )
        self._blit("1. Escenario", (left, 88), TEXT, self._section)
        self._blit("2. Cerebro de las presas", (left, 182), PREY, self._section)
        self._blit("3. Cerebro de los depredadores", (left, 268), PREDATOR, self._section)
        self._blit("4. Población, entrenamiento y partida", (left, 362), TEXT, self._section)
        values = {
            "n_prey": str(s.n_prey),
            "n_predators": str(s.n_predators),
            "run": f"r{s.run}",
            "episode": f"#{s.episode}",
        }
        for i, (name, label, color) in enumerate(STEPPERS):
            center = left + i * STEPPER_SPACING + 66
            self._blit_centered(values[name], center, 396, color, self._font)
            self._blit_centered(label, center, 424, DIM_TEXT, self._small)
        self._blit("5. Ejecutar", (left, 516), TEXT, self._section)

        mouse = pygame.mouse.get_pos()
        for button in self.buttons:
            self._draw_button(button, button.rect.collidepoint(mouse))
        self._blit(
            "Esc: salir   En el visor: espacio pausa, clic inspecciona, Esc vuelve al menú",
            (left, HEIGHT - 28),
            DIM_TEXT,
            self._small,
        )
        self._draw_summary()

    def _draw_summary(self) -> None:
        s = self.state
        x = CANVAS_PIXELS + 16
        pygame.draw.rect(self._screen, PANEL, (CANVAS_PIXELS, 0, PANEL_WIDTH, HEIGHT))
        pygame.draw.line(self._screen, CARD, (CANVAS_PIXELS, 0), (CANVAS_PIXELS, HEIGHT), 2)
        self._blit("Selección", (x, 24), ACCENT, self._section)
        lines: list[tuple[str, tuple[int, ...]]] = [
            (f"Escenario {s.scenario}: {SCENARIOS[s.scenario]}", TEXT),
            (SCENARIO_HELP[s.scenario], DIM_TEXT),
            ("", TEXT),
            (f"Presas ({s.n_prey}): {SHORT_BRAINS[s.prey]}", PREY),
            (BRAIN_HELP[s.prey], DIM_TEXT),
            ("", TEXT),
            (f"Depredadores ({s.n_predators}): {SHORT_BRAINS[s.predator]}", PREDATOR),
            (BRAIN_HELP[s.predator], DIM_TEXT),
            ("", TEXT),
            (f"Redes de la ejecución formal r{s.run} (de 0 a 9)", DIM_TEXT),
            (
                f"Partida #{s.episode}: semilla de la partida (posiciones iniciales y azar); "
                "la misma partida siempre se repite igual",
                DIM_TEXT,
            ),
        ]
        top = 56
        for text, color in lines:
            for part in self._wrap(text, PANEL_WIDTH - 32):
                self._blit(part, (x, top), color)
                top += 19
        top += 12
        pygame.draw.line(self._screen, CARD, (x, top), (x + PANEL_WIDTH - 32, top))
        top += 14
        self._blit("Resultados rápidos", (x, top), PLANT, self._section)
        top += 26
        body = s.message or ["Pulsa «Resultados rápidos» para simular", "la partida sin ventana."]
        for text in body:
            color = PREDATOR if text.startswith("error") else TEXT
            for part in self._wrap(text, PANEL_WIDTH - 32):
                self._blit(part, (x, top), color)
                top += 19

    def _draw_button(self, button: Button, hover: bool) -> None:
        rect = button.rect
        if not button.enabled:
            pygame.draw.rect(self._screen, BAR_BACK, rect, border_radius=6)
            self._center(button.label, rect, DISABLED)
            return
        if button.selected:
            pygame.draw.rect(self._screen, button.color, rect, border_radius=6)
            self._center(button.label, rect, BACKGROUND)
            return
        pygame.draw.rect(self._screen, BUTTON_HOVER if hover else BUTTON, rect, border_radius=6)
        pygame.draw.rect(self._screen, button.color, rect, 1, border_radius=6)
        self._center(button.label, rect, TEXT)

    def _center(self, text: str, rect: pygame.Rect, color: tuple[int, ...]) -> None:
        font = self._small if self._font.size(text)[0] > rect.width - 10 else self._font
        image = font.render(text, True, color)
        self._screen.blit(image, image.get_rect(center=rect.center))

    def _blit_centered(self, text, center_x, y, color, font) -> None:
        image = font.render(text, True, color)
        self._screen.blit(image, image.get_rect(midtop=(center_x, y)))

    def _blit(self, text, position, color, font=None) -> None:
        self._screen.blit((font or self._font).render(text, True, color), position)

    def _wrap(self, text: str, width: int) -> list[str]:
        words, lines, current = text.split(" "), [], ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if self._font.size(candidate)[0] <= width or not current:
                current = candidate
            else:
                lines.append(current)
                current = word
        return [*lines, current]
