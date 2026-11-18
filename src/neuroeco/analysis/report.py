"""Tables and figures of the formal experiments, regenerated from the analysis (F8, F9)."""

from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # files only, no window
import matplotlib.pyplot as plt

CONDITIONAL = " (condicionado al modelo de desplazamiento)"
LABEL = {"prey": "presa (supervivencia media)", "predator": "depredador (fracción capturada)"}


def _fmt(value: float | None, digits: int = 4) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def _level(level: float | None) -> str:
    return "no alcanzable con este n" if level is None else f"{100 * level:.1f} %"


def family_table(title: str, rows: list[dict[str, Any]]) -> str:
    lines = [
        f"### {title}",
        "",
        "| Especie | Escenario | n | k⁺/k⁰/k⁻ | Mediana d | IC exacto (nivel) | p signo "
        "| p Holm | HL (sensibilidad) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        holm = _fmt(r.get("p_holm")) if r["confirmatory"] else "solo estimación (R < 8)"
        hl = (
            f"{_fmt(r['hl_estimate'])} [{_fmt(r['hl_lower'])}, {_fmt(r['hl_upper'])}]"
            if "hl_estimate" in r
            else "—"
        )
        lines.append(
            f"| {r['species']} | {r['scenario']} | {r['n']} | {r['k_plus']}/{r['k_zero']}/"
            f"{r['k_minus']} | {_fmt(r['median'])} | [{_fmt(r['ci_lower'])}, "
            f"{_fmt(r['ci_upper'])}] ({_level(r['ci_level'])}) | {_fmt(r['p_sign'])} | "
            f"{holm} | {hl} |"
        )
    return "\n".join(lines)


def c2_table(rows: list[dict[str, Any]]) -> str:
    lines = [
        "### C2: red compacta frente a red base (escenario A)",
        "",
        "| Especie | δ (HL) | IC exacto | Margen Δ | Veredicto | δ de Cliff | G_θ base "
        "| G_θ compacta | p eficiencia (Holm) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['species']} | {_fmt(r['delta_estimate'])} | [{_fmt(r['ci_lower'])}, "
            f"{_fmt(r['ci_upper'])}] | {_fmt(r['margin'])} | {r['verdict']}"
            f"{CONDITIONAL if r['shift_model_warning'] else ''} | "
            f"{_fmt(r['cliffs_delta'], 3)} | {r['generations_to_theta_base']} | "
            f"{r['generations_to_theta_compact']} | {_fmt(r.get('p_efficiency_holm'))} |"
        )
    return "\n".join(lines)


def generalization_table(rows: list[dict[str, Any]]) -> str:
    lines = [
        "### Generalización (ADR-019): ventaja de la red sobre las reglas, Adv(O)",
        "",
        "| Especie | Escenario | Oponente | Mediana Adv | IC exacto por signos |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['species']} | {r['scenario']} | {r['opponent']} | "
            f"{_fmt(r['median_advantage'])} | [{_fmt(r['ci_lower'])}, {_fmt(r['ci_upper'])}] |"
        )
    return "\n".join(lines)


def differences_figure(title: str, rows: list[dict[str, Any]]):
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for ax, species in zip(axes, ("prey", "predator"), strict=True):
        selected = [r for r in rows if r["species"] == species]
        for x, r in enumerate(selected):
            ax.scatter([x] * len(r["differences"]), r["differences"], s=18, alpha=0.7)
            ax.plot([x, x], [r["ci_lower"], r["ci_upper"]], color="black", lw=2)
            ax.plot(x, r["median"], "k_", markersize=16)
        ax.axhline(0, color="grey", lw=1, ls="--")
        ax.set_xticks(range(len(selected)), [r["scenario"] for r in selected])
        ax.set_title(LABEL[species])
        ax.set_xlabel("escenario")
        ax.set_ylabel("d por ejecución")
    fig.suptitle(title)
    fig.tight_layout()
    return fig


def validation_figure(runs_root: Path):
    curves: dict[str, list[list[tuple[int, float]]]] = {}
    for directory in sorted(runs_root.glob("f8_*_r*")):
        if not (directory / "summary.json").exists():
            continue
        config = directory.name.rsplit("_r", 1)[0].removeprefix("f8_")
        with (directory / "generations.csv").open(encoding="utf-8") as handle:
            points = [
                (int(r["generation"]), float(r["f_val"]))
                for r in csv.DictReader(handle)
                if r["f_val"]
            ]
        curves.setdefault(config, []).append(points)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, species in zip(axes, ("prey", "predator"), strict=True):
        for config, runs in sorted(curves.items()):
            if not config.startswith(species):
                continue
            generations = [g for g, _ in runs[0]]
            median = [statistics.median(run[i][1] for run in runs) for i in range(len(generations))]
            ax.plot(generations, median, marker=".", label=config)
        ax.set_title(f"F_val (mediana entre ejecuciones): {LABEL[species]}")
        ax.set_xlabel("generación")
        ax.legend(fontsize=7)
    fig.tight_layout()
    return fig


def report_documents(report: dict[str, Any], runs_root: Path) -> tuple[dict[str, str], dict]:
    """Text files and figures of the report; ``presentation`` writes them (the analysis
    layer never writes, T4d contract)."""
    sections = [
        "# Resultados de F8 (generado por `neuroeco experiment analyze`)",
        "",
        f"Ejecuciones planificadas por configuración: R = {report['runs_planned']}.",
        "",
        family_table("C1: después frente a antes de entrenar (frente a M0)", report["C1"]),
        "",
        family_table(
            "C3: red entrenada frente a la política por reglas (frente a M0)", report["C3"]
        ),
        "",
        c2_table(report["C2"]),
        "",
        generalization_table(report["generalization"]),
        "",
        "![C1](c1_differences.png)",
        "![C3](c3_differences.png)",
        "![Validación](validation_curves.png)",
    ]
    texts = {
        "analysis.json": json.dumps(report, indent=2, default=str),
        "tables.md": "\n".join(sections) + "\n",
    }
    figures = {
        "c1_differences.png": differences_figure("C1: después - antes", report["C1"]),
        "c3_differences.png": differences_figure("C3: red - reglas", report["C3"]),
        "validation_curves.png": validation_figure(runs_root),
    }
    return texts, figures
