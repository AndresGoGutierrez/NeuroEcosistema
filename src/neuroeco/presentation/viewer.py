"""Real-time viewer (pygame-ce): a synchronous observer of the simulation (ADR-031).

The viewer receives read-only ``Frame`` objects (``application.session``); it never sees the
live world state nor any random generator. While paused, its event loop runs inside the
observer callback, so the simulation simply waits.

Controls (decision V6): space pauses and resumes, the right arrow advances one step while
paused, ``+`` and ``-`` change the speed (steps per frame), a click selects an agent for the
inspector, and Esc or closing the window quits.
"""

from __future__ import annotations

import os

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

import numpy as np
import pygame

from neuroeco.application.session import Frame, inspect_agent
from neuroeco.domain.neural import NeuralNetwork
from neuroeco.domain.params import WorldParams
from neuroeco.presentation.inspector import (
    Selection,
    SessionInfo,
    WorldTransform,
    hud_lines,
    inspector_lines,
    pick_agent,
)

SPEEDS = (1, 2, 4, 8, 16, 32)  # steps per frame
CANVAS_PIXELS = 640
PANEL_WIDTH = 520
PICK_PIXELS = 10.0
FONT_NAMES = "consolas,dejavusansmono,couriernew,monospace"
FONT_SIZE = 14
LINE_HEIGHT = 16
HELP_SIZE = 13
WRAP_VALUES = 8  # hidden-layer activations per line
HUD_HEADER = 4  # HUD lines kept above the inspector
HELP = ("space pause | -> step | +/- speed | click inspect | esc quit",)

GRID_STEP = 25.0  # world units between grid lines
TITLE_SIZE = 20

BACKGROUND = (14, 20, 24)
GRID = (24, 32, 38)
PANEL = (26, 31, 38)
CARD = (34, 40, 49)
TEXT = (225, 228, 232)
DIM_TEXT = (140, 148, 158)
ACCENT = (255, 215, 64)
PLANT = (86, 190, 96)
PLANT_GLOW = (86, 190, 96, 45)
PREY = (90, 165, 255)
PREDATOR = (240, 90, 74)
OUTLINE = (8, 10, 12)
SELECTED = (255, 215, 64)
VISION = (255, 215, 64, 28)
DEAD_MARK = (120, 120, 120)
BAR_BACK = (48, 55, 66)
ELLIPSIS = "\u2026"


class ViewerClosed(Exception):  # noqa: N818 - it is a signal, not an error
    """The user closed the viewer before the episode ended."""

    def __init__(self, step: int) -> None:
        super().__init__(f"viewer closed at step {step}")
        self.step = step


class Command(Enum):
    TOGGLE_PAUSE = auto()
    STEP = auto()
    FASTER = auto()
    SLOWER = auto()
    QUIT = auto()


@dataclass
class Controls:
    """Viewer state machine; independent of pygame."""

    paused: bool = True
    speed_index: int = 0
    step_requested: bool = False
    quit_requested: bool = False

    @property
    def steps_per_frame(self) -> int:
        return SPEEDS[self.speed_index]

    def apply(self, command: Command) -> None:
        if command is Command.TOGGLE_PAUSE:
            self.paused = not self.paused
        elif command is Command.STEP:
            self.step_requested = self.paused
        elif command is Command.FASTER:
            self.speed_index = min(self.speed_index + 1, len(SPEEDS) - 1)
        elif command is Command.SLOWER:
            self.speed_index = max(self.speed_index - 1, 0)
        elif command is Command.QUIT:
            self.quit_requested = True


def command_for(event: pygame.event.Event) -> Command | None:
    """Keyboard and window events -> commands. Mouse clicks are handled by the viewer."""
    if event.type == pygame.QUIT:
        return Command.QUIT
    if event.type != pygame.KEYDOWN:
        return None
    if event.key == pygame.K_ESCAPE:
        return Command.QUIT
    if event.key == pygame.K_SPACE:
        return Command.TOGGLE_PAUSE
    if event.key == pygame.K_RIGHT:
        return Command.STEP
    if event.key in (pygame.K_PLUS, pygame.K_KP_PLUS) or getattr(event, "unicode", "") == "+":
        return Command.FASTER
    if event.key in (pygame.K_MINUS, pygame.K_KP_MINUS) or getattr(event, "unicode", "") == "-":
        return Command.SLOWER
    return None


EventSource = Callable[[], Iterable[pygame.event.Event]]


def canvas_transform(params: WorldParams) -> WorldTransform:
    """World-to-screen transform of the viewer's canvas (the world fills a square canvas)."""
    return WorldTransform(params.size, CANVAS_PIXELS / params.size)


class Viewer:
    """Draws frames and gates the simulation (FrameObserver of ``run_session``)."""

    def __init__(
        self,
        params: WorldParams,
        info: SessionInfo,
        *,
        paused: bool = True,
        speed: int = 1,
        fps: int = 30,
        exit_at_end: bool = False,
        event_source: EventSource | None = None,
        networks: dict[str, NeuralNetwork] | None = None,
    ) -> None:
        if speed not in SPEEDS:
            raise ValueError(f"speed must be one of {SPEEDS}, got {speed}")
        if fps < 0:
            raise ValueError("fps must be >= 0 (0 = unlimited)")
        self.params = params
        self.info = info
        self.networks = networks or {}  # species -> network of a neural policy (F5)
        self.controls = Controls(paused=paused, speed_index=SPEEDS.index(speed))
        self.selected: Selection | None = None
        self.frame: Frame | None = None
        self.finished = False
        self._fps = fps
        self._exit_at_end = exit_at_end
        self._events = event_source or pygame.event.get
        self._since_render = 0
        self.transform = canvas_transform(params)

        pygame.display.init()
        pygame.font.init()
        pygame.display.set_caption("NeuroEcosistema")
        self._screen = pygame.display.set_mode((CANVAS_PIXELS + PANEL_WIDTH, CANVAS_PIXELS))
        self._font = pygame.font.SysFont(FONT_NAMES, FONT_SIZE)
        self._title_font = pygame.font.SysFont(FONT_NAMES, TITLE_SIZE, bold=True)
        self._help_font = pygame.font.SysFont(FONT_NAMES, HELP_SIZE)
        self._clock = pygame.time.Clock()

    # ------------------------------------------------------------ FrameObserver
    def start(self, frame: Frame) -> None:
        self.frame = frame
        self._render_and_poll()
        self._wait_while_paused()

    def step(self, frame: Frame) -> None:
        self.frame = frame
        self._since_render += 1
        if self.controls.paused or self._since_render >= self.controls.steps_per_frame:
            self._render_and_poll()
        self._wait_while_paused()

    # ------------------------------------------------------------ after the episode
    def finish(self) -> None:
        """Show the final state; wait for Esc unless ``exit_at_end``."""
        self.finished = True
        self._render_and_poll(check_quit=False)
        while not self._exit_at_end and not self.controls.quit_requested:
            self._render_and_poll(check_quit=False)

    def close(self) -> None:
        pygame.display.quit()
        pygame.font.quit()

    def save_screenshot(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        pygame.image.save(self._screen, str(path))

    # ------------------------------------------------------------ internals
    def _wait_while_paused(self) -> None:
        while self.controls.paused and not self.controls.step_requested:
            self._render_and_poll()
        self.controls.step_requested = False

    def _render_and_poll(self, check_quit: bool = True) -> None:
        self._since_render = 0
        for event in self._events():
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._select(event.pos)
                continue
            command = command_for(event)
            if command is not None:
                self.controls.apply(command)
        if check_quit and self.controls.quit_requested:
            raise ViewerClosed(self.frame.step if self.frame else 0)
        self._draw()
        pygame.display.flip()
        if self._fps:
            self._clock.tick(self._fps)

    def _select(self, position: tuple[int, int]) -> None:
        if self.frame is None or not self.transform.contains(*position):
            return
        point = self.transform.to_world(*position)
        self.selected = pick_agent(self.frame, point, PICK_PIXELS / self.transform.scale)

    def panel_lines(self) -> list[str]:
        """Text of the side panel for the current frame (HUD, then inspector)."""
        if self.frame is None:
            return []
        lines = hud_lines(
            self.frame.stats,
            self.info,
            self.controls.paused,
            self.controls.steps_per_frame,
            self.finished,
        )
        lines.append("")
        if self.selected is None:
            lines.append("click an agent to inspect it")
        else:
            species = self.selected.species
            inspection = inspect_agent(
                self.frame,
                self.params,
                species,
                self.selected.index,
                self.networks.get(species),
            )
            lines += inspector_lines(inspection)
        return lines

    def _draw(self) -> None:
        frame = self.frame
        if frame is None:
            return
        screen = self._screen
        screen.fill(BACKGROUND)
        self._draw_grid()
        scale = self.transform.scale

        plant_radius = max(2, round(self.params.eat_radius * scale * 0.5))
        plants = [
            self.transform.to_screen(x, y) for x, y in frame.plant_positions[frame.plant_active]
        ]
        glow = pygame.Surface((CANVAS_PIXELS, CANVAS_PIXELS), pygame.SRCALPHA)
        for center in plants:
            pygame.draw.circle(glow, PLANT_GLOW, center, plant_radius + 4)
        screen.blit(glow, (0, 0))
        for center in plants:
            pygame.draw.circle(screen, PLANT, center, plant_radius)

        if self.selected is not None:
            self._draw_vision(frame, self.selected)

        for species, color, size in (("prey", PREY, 6.0), ("predator", PREDATOR, 9.0)):
            view = frame.species(species)
            for i in np.flatnonzero(view.alive):
                x, y = view.positions[i]
                self._draw_agent(self.transform.to_screen(x, y), view.headings[i], color, size)

        if self.selected is not None:
            view = frame.species(self.selected.species)
            index = self.selected.index
            x, y = view.positions[index]
            ring = SELECTED if view.alive[index] else DEAD_MARK
            pygame.draw.circle(screen, ring, self.transform.to_screen(x, y), 13, 2)

        self._draw_panel(frame)

    # ------------------------------------------------------------ drawing helpers
    def _draw_grid(self) -> None:
        pixels = GRID_STEP * self.transform.scale
        position = 0.0
        while position <= CANVAS_PIXELS:
            offset = round(position)
            pygame.draw.line(self._screen, GRID, (offset, 0), (offset, CANVAS_PIXELS))
            pygame.draw.line(self._screen, GRID, (0, offset), (CANVAS_PIXELS, offset))
            position += pixels

    def _draw_vision(self, frame: Frame, selected: Selection) -> None:
        """Translucent disc of the selected agent's vision radius (what its sensors reach)."""
        view = frame.species(selected.species)
        if not view.alive[selected.index]:
            return
        x, y = view.positions[selected.index]
        species_params = getattr(self.params, selected.species)
        radius = round(species_params.vision_radius * self.transform.scale)
        layer = pygame.Surface((CANVAS_PIXELS, CANVAS_PIXELS), pygame.SRCALPHA)
        center = self.transform.to_screen(x, y)
        pygame.draw.circle(layer, VISION, center, radius)
        pygame.draw.circle(layer, (*SELECTED, 90), center, radius, 1)
        self._screen.blit(layer, (0, 0))

    def _draw_agent(
        self, center: tuple[float, float], heading: float, color: tuple[int, ...], size: float
    ) -> None:
        """Arrow-shaped triangle pointing along the heading (screen y grows downwards)."""
        cx, cy = center
        cos, sin = float(np.cos(heading)), float(np.sin(heading))
        tip = (cx + size * 1.6 * cos, cy - size * 1.6 * sin)
        left = (cx - size * cos - size * 0.9 * sin, cy + size * sin - size * 0.9 * cos)
        right = (cx - size * cos + size * 0.9 * sin, cy + size * sin + size * 0.9 * cos)
        notch = (cx - size * 0.4 * cos, cy + size * 0.4 * sin)
        points = (tip, left, notch, right)
        pygame.draw.polygon(self._screen, color, points)
        pygame.draw.polygon(self._screen, OUTLINE, points, 1)

    def _text(
        self,
        text: str,
        position: tuple[int, int],
        color: tuple[int, ...] = TEXT,
        font: pygame.font.Font | None = None,
    ) -> None:
        font = font or self._font
        limit = PANEL_WIDTH - 28
        if font.size(text)[0] > limit:  # keep the end of long lines: it names the run
            while text and font.size(ELLIPSIS + text)[0] > limit:
                text = text[1:]
            text = ELLIPSIS + text
        self._screen.blit(font.render(text, True, color), position)

    def _bar(
        self,
        position: tuple[int, int],
        width: int,
        label: str,
        value: int,
        total: int,
        color: tuple[int, ...],
    ) -> None:
        left, top = position
        self._text(f"{label}  {value}/{total}", (left, top), DIM_TEXT)
        top += LINE_HEIGHT + 2
        pygame.draw.rect(self._screen, BAR_BACK, (left, top, width, 7), border_radius=3)
        filled = 0 if total <= 0 else round(width * value / total)
        if filled:
            pygame.draw.rect(self._screen, color, (left, top, filled, 7), border_radius=3)

    def _draw_panel(self, frame: Frame) -> None:
        screen = self._screen
        left = CANVAS_PIXELS + 16
        right = CANVAS_PIXELS + PANEL_WIDTH - 16
        pygame.draw.rect(screen, PANEL, (CANVAS_PIXELS, 0, PANEL_WIDTH, CANVAS_PIXELS))
        pygame.draw.line(screen, CARD, (CANVAS_PIXELS, 0), (CANVAS_PIXELS, CANVAS_PIXELS), 2)

        self._text("NeuroEcosistema", (left, 12), ACCENT, self._title_font)
        legend_top = 42
        for offset, color, label, size in (
            (0, PREY, "presa", 5.0),
            (110, PREDATOR, "depredador", 7.0),
            (270, PLANT, "planta", 0.0),
        ):
            center = (left + offset + 7, legend_top + 8)
            if size:
                self._draw_agent(center, np.pi / 2, color, size)
            else:
                pygame.draw.circle(screen, color, center, 4)
            self._text(label, (left + offset + 18, legend_top), DIM_TEXT)

        stats = frame.stats
        half = (right - left - 16) // 2
        second = left + half + 16
        self._bar((left, 68), right - left, "paso", stats.step, stats.t_max, ACCENT)
        self._bar((left, 100), half, "presas", stats.prey_alive, stats.n_prey, PREY)
        self._bar(
            (second, 100), half, "depredadores", stats.predators_alive, stats.n_predators, PREDATOR
        )
        self._bar((left, 132), half, "plantas", stats.plants_active, stats.n_plants, PLANT)
        top = 160
        pygame.draw.line(screen, CARD, (left, top + 2), (right, top + 2))
        top += 10

        bottom = CANVAS_PIXELS - len(HELP) * LINE_HEIGHT - 12
        for line in self._visible_lines():
            if top > bottom:
                break
            if line:
                color = TEXT
                if line.startswith(("PREY #", "prey ")):
                    color = PREY
                elif line.startswith(("PREDATOR #", "predators ")):
                    color = PREDATOR
                elif line.startswith(("step ", "click ")):
                    color = ACCENT
                self._text(line, (left, top), color)
            top += LINE_HEIGHT
        top = CANVAS_PIXELS - len(HELP) * LINE_HEIGHT - 6
        for line in HELP:
            self._text(line, (left, top), DIM_TEXT, self._help_font)
            top += LINE_HEIGHT

    def _visible_lines(self) -> list[str]:
        """Panel text as drawn: with an agent selected, only the HUD header (the bars show the
        counts) and the inspector, with long hidden-layer lines wrapped."""
        lines = self.panel_lines()
        if self.selected is not None:
            start = next(
                i for i, line in enumerate(lines) if line.startswith(("PREY #", "PREDATOR #"))
            )
            lines = [*lines[:HUD_HEADER], "", *lines[start:]]
        inputs = [line for line in lines if line.startswith("  ")]
        width = max((len(line) for line in inputs), default=0) + 3
        rows = [
            f"{inputs[i]:<{width}}{inputs[i + 1].strip() if i + 1 < len(inputs) else ''}"
            for i in range(0, len(inputs), 2)
        ]  # sensor inputs, two per row
        wrapped: list[str] = []
        for line in lines:
            if line.startswith("  "):
                if rows and line is inputs[0]:
                    wrapped += rows
            elif line.startswith("hidden "):
                label, _, values = line.partition("  ")
                parts = values.split()
                for i in range(0, len(parts), WRAP_VALUES):
                    prefix = label if i == 0 else " " * len(label)
                    wrapped.append(f"{prefix}  " + " ".join(parts[i : i + WRAP_VALUES]))
            else:
                wrapped.append(line)
        return wrapped
