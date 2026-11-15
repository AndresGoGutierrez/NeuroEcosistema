"""Static check of ADR-001: allow-list of imports for the inner layers.

import-linter forbids a fixed list of known packages. This test is stricter: it
parses every module of ``domain`` and ``application`` and fails on ANY import
that is not the standard library, ``numpy`` or an allowed internal package, so
that a future dependency cannot leak into the core unnoticed.
"""

import ast
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
STDLIB = set(sys.stdlib_module_names)
THIRD_PARTY_ALLOWED = {"numpy"}

INTERNAL_ALLOWED = {
    "domain": ("neuroeco.domain",),
    "application": ("neuroeco.domain", "neuroeco.application"),
}


def _module_name(path: Path) -> str:
    parts = list(path.relative_to(SRC).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _resolve(node: ast.ImportFrom, module: str, is_package: bool) -> str:
    """Absolute name targeted by a (possibly relative) ``from ... import``."""
    if node.level == 0:
        return node.module or ""
    package = module.split(".") if is_package else module.split(".")[:-1]
    base = package[: len(package) - (node.level - 1)]
    return ".".join([*base, node.module] if node.module else base)


def _imported_names(path: Path) -> list[str]:
    module = _module_name(path)
    is_package = path.name == "__init__.py"
    # utf-8-sig: tolerate a BOM written by some Windows editors.
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append(_resolve(node, module, is_package))
    return names


def _is_allowed(name: str, internal_prefixes: tuple[str, ...]) -> bool:
    top = name.split(".")[0]
    if top == "neuroeco":
        return any(name == p or name.startswith(p + ".") for p in internal_prefixes)
    return top in STDLIB or top in THIRD_PARTY_ALLOWED


@pytest.mark.parametrize("layer", sorted(INTERNAL_ALLOWED))
def test_inner_layer_imports_are_allow_listed(layer: str) -> None:
    files = sorted((SRC / "neuroeco" / layer).rglob("*.py"))
    assert files, f"layer {layer} has no modules"
    violations = [
        f"{path.relative_to(SRC)}: {name}"
        for path in files
        for name in _imported_names(path)
        if not _is_allowed(name, INTERNAL_ALLOWED[layer])
    ]
    assert not violations, "Imports not allowed by ADR-001:\n" + "\n".join(violations)
