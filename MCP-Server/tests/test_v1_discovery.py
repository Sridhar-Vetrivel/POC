"""Tools are discovered from the tools/ package: one module, one read-only tool, same name."""

from __future__ import annotations

import ast
from pathlib import Path

from v1_support import isolated_env, make_world  # noqa: F401  (pytest fixtures)

from ingenus_mcp.tools import discover

TOOLS_DIR = Path(__file__).resolve().parents[1] / "src" / "ingenus_mcp" / "tools"


def _modules() -> list[Path]:
    return sorted(p for p in TOOLS_DIR.glob("*.py") if not p.name.startswith("_"))


def test_discover_finds_one_tool_per_module():
    found = discover()
    assert set(found) == {p.stem for p in _modules()}
    assert all(spec.read_only for spec in found.values())


def test_each_module_defines_exactly_one_tool_named_like_the_file():
    for path in _modules():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        decorated = [
            n.name
            for n in tree.body
            if isinstance(n, ast.FunctionDef)
            and any("tool" in ast.unparse(d) for d in n.decorator_list)
        ]
        assert decorated == [path.stem], f"{path.name}: {decorated}"


def test_every_tool_has_a_description_for_claude():
    for spec in discover().values():
        assert len(spec.description) > 80, f"{spec.name}: description too short"
