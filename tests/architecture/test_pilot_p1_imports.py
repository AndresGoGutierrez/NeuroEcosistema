"""F4 T3: the P1 command imports neither pygame nor the analysis layer.

pygame is allowed in ``presentation`` (ADR-031) but the P1 command never displays anything, and
the criteria of P1 are evaluated later from the CSV files by ``analysis`` (task T4), not here.
"""

import ast
from pathlib import Path

MODULE = Path(__file__).resolve().parents[2] / "src" / "neuroeco" / "presentation" / "pilot_p1.py"


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_p1_command_does_not_import_pygame_or_analysis() -> None:
    modules = imported_modules(MODULE)
    assert not {m for m in modules if m == "pygame" or m.startswith("pygame.")}
    assert not {m for m in modules if m.startswith("neuroeco.analysis")}
    assert "neuroeco.application.calibration" in modules
