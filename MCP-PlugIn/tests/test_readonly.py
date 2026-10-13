"""Read-only rules (CLAUDE.md rules 4 and 5): no write tool, no write path, no write method."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from ingenus_plugin.core import tools as _tools  # noqa: F401  (registers the tools)
from ingenus_plugin.core.registry import TOOLS, WriteToolNotAllowed, tool
from ingenus_plugin.server.app import build_server
from mcp_servers.sap.adapters.mock import MockSapReader
from mcp_servers.sap.adapters.real_stub import RealSapReader
from mcp_servers.sap.interface import ReadQuery, SapReader

SRC = Path(__file__).resolve().parents[1] / "src" / "ingenus_plugin"
BASELINE_TOOLS = {
    "resolve_customer",
    "find_contract_files",
    "get_contract_pages",
    "get_rebate_setup",
    "get_sales_volume",
    "compare_contract_to_sap",
}


def test_every_registered_tool_is_read_only_and_the_set_is_the_baseline():
    assert set(TOOLS) == BASELINE_TOOLS, (
        "Add a tool only through a decision record (docs/decisions/)."
    )
    assert all(spec.read_only for spec in TOOLS.values())


def test_a_write_tool_cannot_be_registered():
    with pytest.raises(WriteToolNotAllowed):

        @tool(read_only=False)
        def update_something() -> None: ...


def test_the_mcp_server_marks_every_tool_read_only():
    import asyncio

    tools = asyncio.run(build_server().list_tools())
    assert {t.name for t in tools} == BASELINE_TOOLS
    for t in tools:
        assert t.annotations is not None
        assert t.annotations.read_only_hint is True
        assert t.annotations.destructive_hint is False


# Names and calls that would write, move or delete. Only calllog.py may write (the tool-call log).
# "replace" is left out because str.replace is everywhere; Path.replace is rare. Review by eye.
WRITE_ATTRS = {
    "write_text",
    "write_bytes",
    "unlink",
    "rmdir",
    "rename",
    "touch",
    "mkdir",
    "symlink_to",
    "hardlink_to",
    "chmod",
}
WRITE_FUNCS = {
    "remove",
    "removedirs",
    "rmdir",
    "unlink",
    "rename",
    "makedirs",
    "mkdir",
    "rmtree",
    "copy",
    "copy2",
    "copyfile",
    "move",
}


def _violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in WRITE_ATTRS | WRITE_FUNCS:
                found.append(f"{path.name}:{node.lineno} .{func.attr}()")
            if (
                isinstance(func, ast.Name)
                and func.id == "open"
                or (isinstance(func, ast.Attribute) and func.attr == "open")
            ):
                mode = None
                if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                    mode = node.args[1].value
                if (
                    isinstance(func, ast.Attribute)
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                ):
                    mode = node.args[0].value
                for kw in node.keywords:
                    if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                        mode = kw.value.value
                if isinstance(mode, str) and set(mode) & set("wax+"):
                    found.append(f"{path.name}:{node.lineno} open(mode={mode!r})")
    return found


def test_no_code_outside_the_log_module_can_write_files():
    offences: list[str] = []
    for path in SRC.rglob("*.py"):
        if path.name == "calllog.py":
            continue
        offences += _violations(path)
    assert not offences, "Write operations outside calllog.py:\n" + "\n".join(offences)


def test_the_scan_would_catch_a_write(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text(
        "from pathlib import Path\nPath('x').write_text('y')\nopen('f', 'w')\n", encoding="utf-8"
    )
    assert len(_violations(bad)) == 2


def test_the_sap_interface_has_a_single_read_method():
    public = {n for n in dir(SapReader) if not n.startswith("_")}
    assert public == {"read"}
    for cls in (MockSapReader, RealSapReader):
        assert {n for n in dir(cls) if not n.startswith("_")} == {"read"}


def test_the_mock_sap_refuses_data_that_is_not_labelled_synthetic(tmp_path):
    bad = tmp_path / "x.json"
    bad.write_text(json.dumps({"_label": "real extract"}), encoding="utf-8")
    with pytest.raises(ValueError, match="SYNTHETIC"):
        MockSapReader(bad)


def test_the_real_adapter_is_a_stub_that_refuses_to_run():
    with pytest.raises(NotImplementedError, match="TODO"):
        RealSapReader().read(ReadQuery(entity="anything"))
