"""Smoke test for the staged desktop-extension bundle, run WITHOUT the project's virtual environment.

    python MCP-PlugIn/packaging/build_bundle.py        # first, to stage build/mcpb
    python MCP-PlugIn/packaging/smoke_test_bundle.py   # then this (use the project venv to get the MCP client)

It starts build/mcpb/server/main.py with a plain system Python (so only the bundled libraries are
available, as on a user's laptop), talks to it over stdio, and calls two tools. It does not test
Claude Desktop itself.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters, stdio_client

POC = Path(__file__).resolve().parents[2]
STAGE = POC / "build" / "mcpb"


def system_python() -> str:
    # The bundle must not rely on the venv, so look for a Python outside it.
    for candidate in (
        os.environ.get("BUNDLE_PYTHON"),
        shutil.which("python"),
        shutil.which("python3"),
    ):
        if candidate and ".venv" not in candidate:
            return candidate
    raise SystemExit("No system Python found. Set BUNDLE_PYTHON to a Python outside the venv.")


async def main() -> None:
    if not STAGE.exists():
        raise SystemExit("Run build_bundle.py first.")
    log = Path(tempfile.mkdtemp()) / "tool_calls.jsonl"
    env = {
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "PATH": os.environ.get("PATH", ""),
        "INGENUS_CONTRACTS_DIR": str(POC / "build" / "sample_contracts"),
        "INGENUS_LOG_PATH": str(log),
        "INGENUS_SLICE_DIR": str(STAGE / "slice"),
        "INGENUS_SAP_MOCK_FILE": str(STAGE / "data" / "sap" / "entities.json"),
        "INGENUS_PROMPTS_DIR": str(STAGE / "prompts"),
        "INGENUS_SAP_ADAPTER": "mock",
    }
    params = StdioServerParameters(
        command=system_python(), args=[str(STAGE / "server" / "main.py")], env=env
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        tools = [t.name for t in (await session.list_tools()).tools]
        assert len(tools) == 6, tools
        files = await session.call_tool("find_contract_files", {"customer": "Chain X"})
        ids = [f["document_id"] for f in files.structured_content["files"]]
        assert any("Amendment_2" in i for i in ids), ids
        who = await session.call_tool("resolve_customer", {"name": "Chain X"})
        assert who.structured_content["resolved"]["sap_customer_id"] == "SYN-CUST-0001"
    assert log.exists() and len(log.read_text(encoding="utf-8").splitlines()) == 2
    print(f"OK: the bundle ran under {params.command} and answered 2 tool calls; log written.")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
