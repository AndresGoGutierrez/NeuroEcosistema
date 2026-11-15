"""Helpers for viewer tests: headless SDL and scripted input events."""

import os

# Headless SDL before pygame initializes; an explicit value set by the developer is respected.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame


def script(*batches):
    """Event source: one batch of events per call (one rendered frame), then nothing."""
    queue = [list(batch) for batch in batches]

    def source():
        return queue.pop(0) if queue else []

    source.remaining = lambda: len(queue)
    return source


def key(code, unicode=""):
    return pygame.event.Event(pygame.KEYDOWN, key=code, unicode=unicode, mod=0)


def click(position):
    return pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=position, button=1)


def close_window():
    return pygame.event.Event(pygame.QUIT)


SPACE = pygame.K_SPACE
RIGHT = pygame.K_RIGHT
ESCAPE = pygame.K_ESCAPE
PLUS = pygame.K_PLUS
MINUS = pygame.K_MINUS
