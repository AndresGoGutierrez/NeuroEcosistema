"""F4 T3: the P1 command never imports pygame.

pygame is allowed in ``presentation`` (ADR-031) but the P1 command never displays anything.

Until T4c this test also forbade ``neuroeco.analysis``: the criteria of P1 are evaluated from
the CSV files by ``analysis`` (task T4), not while the episodes run. T4c (alternative (a),
expressly authorized by the author as a change to a test of a closed task) allows that import,
because the command now needs ``analysis`` for two approved reasons:

- before running anything, it verifies the calibration sequence with the verifier of T4b and
  the recomputed criteria (decision D-T4c-5);
- in a rule-tuning round it selects the winner of each grid with the P1-17 functions of T4
  (decisions D4 and D-T4c-2).

The command still computes no criterion while the episodes of a block run.
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


def test_p1_command_does_not_import_pygame() -> None:
    modules = imported_modules(MODULE)
    assert not {m for m in modules if m == "pygame" or m.startswith("pygame.")}
    assert "neuroeco.application.calibration" in modules
