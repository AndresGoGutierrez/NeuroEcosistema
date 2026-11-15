"""Inspector and HUD text, screen/world transform and agent picking (ADR-031).

Pure Python and numpy: no pygame here, so all of it is testable without a display.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from neuroeco.application.session import SPECIES, AgentInspection, Frame, HudStats


@dataclass(frozen=True)
class WorldTransform:
    """Maps world coordinates (y up) to screen pixels (y down) and back."""

    size: float  # world side L
    scale: float  # pixels per world unit
    origin: tuple[int, int] = (0, 0)  # screen pixel of the world's top-left corner (0, L)

    @property
    def pixels(self) -> int:
        return round(self.size * self.scale)

    def to_screen(self, x: float, y: float) -> tuple[float, float]:
        ox, oy = self.origin
        return ox + x * self.scale, oy + (self.size - y) * self.scale

    def to_world(self, px: float, py: float) -> tuple[float, float]:
        ox, oy = self.origin
        return (px - ox) / self.scale, self.size - (py - oy) / self.scale

    def contains(self, px: float, py: float) -> bool:
        ox, oy = self.origin
        return ox <= px < ox + self.pixels and oy <= py < oy + self.pixels


@dataclass(frozen=True)
class Selection:
    species: str
    index: int


def pick_agent(frame: Frame, point: tuple[float, float], radius: float) -> Selection | None:
    """Living agent nearest to ``point`` (world units) within ``radius``, as drawn on screen.

    Distances are plain Euclidean, matching the drawing (an agent near one border is not picked
    by a click near the opposite border). Ties: prey before predators, then lower index.
    """
    best: tuple[float, int, int] | None = None
    for rank, species in enumerate(SPECIES):
        view = frame.species(species)
        alive = np.flatnonzero(view.alive)
        if alive.size == 0:
            continue
        delta = view.positions[alive] - np.asarray(point, dtype=np.float64)
        distances = np.hypot(delta[:, 0], delta[:, 1])
        for index, distance in zip(alive.tolist(), distances.tolist(), strict=True):
            candidate = (distance, rank, index)
            if distance <= radius and (best is None or candidate < best):
                best = candidate
    if best is None:
        return None
    return Selection(SPECIES[best[1]], best[2])


def _number(value: float, digits: int = 1) -> str:
    return "—" if math.isnan(value) else f"{value:.{digits}f}"


@dataclass(frozen=True)
class SessionInfo:
    """Fixed description of a viewing session, shown in the HUD."""

    scenario: str
    prey_policy: str
    predator_policy: str
    episode: int
    config_hash: str


def hud_lines(
    stats: HudStats, info: SessionInfo, paused: bool, steps_per_frame: int, finished: bool
) -> list[str]:
    """HUD text (ADR-031, decision V5)."""
    if finished:
        status = "FINISHED"
    elif paused:
        status = "PAUSED"
    else:
        status = f"running x{steps_per_frame}"
    return [
        f"step {stats.step} / {stats.t_max}   {status}",
        f"scenario {info.scenario}   episode {info.episode}",
        f"prey: {info.prey_policy}   predator: {info.predator_policy}",
        f"config {info.config_hash[:12]}",
        "",
        f"prey       alive {stats.prey_alive}/{stats.n_prey}",
        f"           captured {stats.prey_captured}   starved {stats.prey_starved}",
        f"predators  alive {stats.predators_alive}/{stats.n_predators}",
        f"plants     active {stats.plants_active}/{stats.n_plants}",
        f"mean energy  prey {_number(stats.prey_mean_energy)}"
        f"   predators {_number(stats.predator_mean_energy)}",
        f"captures {stats.captures_total}   feedings {stats.feedings_total}",
    ]


def inspector_lines(view: AgentInspection) -> list[str]:
    """Inspector panel text (ADR-031, decision V4)."""
    if view.alive:
        status = "alive"
    elif view.death_cause == "CAPTURED":
        status = f"captured at step {view.death_step}"
    else:
        status = f"starved at step {view.death_step}"
    lines = [
        f"{view.species.upper()} #{view.index}",
        f"state S_{view.state_step}"
        + ("" if view.decision_step is None else f" (after step {view.decision_step})"),
        f"status    {status}",
        f"energy    {view.energy:.2f} ({100 * view.energy_fraction:.1f} % of E_max)",
        f"position  ({view.position[0]:.2f}, {view.position[1]:.2f})",
        f"heading   {view.heading:.3f} rad",
        "",
    ]
    if view.decision_step is None:
        lines.append("initial state: no decision yet")
        return lines

    lines.append(
        f"decision of step {view.decision_step} (inputs observed on S_{view.decision_step})"
    )
    width = max(len(name) for name, _ in view.inputs)
    lines += [f"  {name:<{width}}  {value:+.4f}" for name, value in view.inputs]
    if view.raw_action is None or view.turn is None or view.speed is None:
        raise ValueError("an inspection with a decision step must carry its action")
    lines.append(f"output    turn {view.raw_action[0]:+.4f}   throttle {view.raw_action[1]:+.4f}")
    lines.append(f"action    turn {view.turn:+.4f} rad   speed {view.speed:.4f}")
    lines.append("applied   yes" if view.action_applied else "applied   no (dead before the step)")
    return lines
