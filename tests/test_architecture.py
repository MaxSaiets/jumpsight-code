"""Package boundaries: each package may import only the packages listed for it.

This keeps every package usable on its own: the core helpers stand alone, the
coach needs only the core, and only the application composes them (the private
engine sits behind `jumpsight_app.engine_bridge`). Lazy imports inside functions count too.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
PACKAGES = ("jumpsight_core", "jumpsight_coach", "jumpsight_app")
ALLOWED = {
    "jumpsight_core": set(),
    "jumpsight_coach": {"jumpsight_core"},
    "jumpsight_app": {"jumpsight_core", "jumpsight_coach"},
}


def _imported_packages(path: Path) -> set[tuple[str, int]]:
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module]
        else:
            continue
        for name in names:
            top = name.split(".")[0]
            if top in PACKAGES:
                found.add((top, node.lineno))
    return found


@pytest.mark.parametrize("package", PACKAGES)
def test_package_imports_only_its_allowed_dependencies(package):
    bad = []
    for path in sorted((SRC / package).rglob("*.py")):
        for top, line in _imported_packages(path):
            if top != package and top not in ALLOWED[package]:
                bad.append(f"{path.relative_to(SRC)}:{line} imports {top}")
    assert not bad, "\n".join(bad)


def test_allowed_dependencies_have_no_cycle():
    seen, stack = set(), set()

    def visit(node):
        assert node not in stack, f"dependency cycle through {node}"
        if node in seen:
            return
        stack.add(node)
        for dep in ALLOWED[node]:
            visit(dep)
        stack.discard(node)
        seen.add(node)

    for package in PACKAGES:
        visit(package)
