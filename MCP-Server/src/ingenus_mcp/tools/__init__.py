"""The tools: one module per tool, each a plain function decorated with ``@tool(read_only=True)``.

``discover()`` imports every module in this package, and importing a module registers its tool in
``core.registry.TOOLS``. Adding a tool is: add a module here, with its test and a decision record
(more tools make Claude choose worse). No list of tools is kept anywhere else.
"""

from __future__ import annotations

import importlib
import pkgutil

from ingenus_mcp.core.registry import TOOLS, ToolSpec


def discover() -> dict[str, ToolSpec]:
    """Import every tool module in this package and return the registry."""
    for module in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
        if not module.name.startswith("_"):
            importlib.import_module(f"{__name__}.{module.name}")
    return TOOLS
