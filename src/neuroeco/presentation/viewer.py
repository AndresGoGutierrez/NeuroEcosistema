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
PANEL_WIDTH = 460
PICK_PIXELS = 10.0
FONT_NAMES = "consolas,dejavusansmono,couriernew,monospace"
FONT_SIZE = 15
LINE_HEIGHT = 17
HELP = ("space pause | -> step | +/- speed", "click inspect | esc quit")

BACKGROUND = (18, 22, 26)
PANEL = (32, 36, 42)
TEXT = (225, 228, 232)
DIM_TEXT = (150, 156, 164)
PLANT = (70, 165, 80)
PREY = (90, 165, 255)
PREDATOR = (235, 85, 70)
SELECTED = (255, 215, 64)
DEAD_MARK = (120, 120, 120)


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
        scale = self.transform.scale

        plant_radius = max(2, round(self.params.eat_radius * scale * 0.5))
        for x, y in frame.plant_positions[frame.plant_active]:
            pygame.draw.circle(screen, PLANT, self.transform.to_screen(x, y), plant_radius)

        for species, color, radius in (("prey", PREY, 4), ("predator", PREDATOR, 6)):
            view = frame.species(species)
            for i in np.flatnonzero(view.alive):
                x, y = view.positions[i]
                center = self.transform.to_screen(x, y)
                heading = view.headings[i]
                tip = (
                    center[0] + (radius + 5) * np.cos(heading),
                    center[1] - (radius + 5) * np.sin(heading),
                )
                pygame.draw.circle(screen, color, center, radius)
                pygame.draw.line(screen, color, center, tip, 2)

        if self.selected is not None:
            view = frame.species(self.selected.species)
            index = self.selected.index
            x, y = view.positions[index]
            ring = SELECTED if view.alive[index] else DEAD_MARK
            pygame.draw.circle(screen, ring, self.transform.to_screen(x, y), 11, 2)

        panel = pygame.Rect(CANVAS_PIXELS, 0, PANEL_WIDTH, CANVAS_PIXELS)
        pygame.draw.rect(screen, PANEL, panel)
        top = 10
        for line in self.panel_lines():
            if line:
                screen.blit(self._font.render(line, True, TEXT), (CANVAS_PIXELS + 12, top))
            top += LINE_HEIGHT
        top = CANVAS_PIXELS - len(HELP) * LINE_HEIGHT - 6
        for line in HELP:
            screen.blit(self._font.render(line, True, DIM_TEXT), (CANVAS_PIXELS + 12, top))
            top += LINE_HEIGHT
