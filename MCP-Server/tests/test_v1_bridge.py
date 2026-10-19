"""The Claude Desktop bridge: Desktop -> bridge (Node, stdio) -> v1 server (HTTP) -> answers.

The Python MCP client plays Claude Desktop: it starts the bridge exactly as the extension manifest
does (`node server/index.js` with INGENUS_MCP_URL) and talks to it over stdio. Offline: loopback only.
Skipped when Node or the bridge's node_modules are missing (run `npm ci` in MCP-Server/bridge).
"""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters, stdio_client
from test_v1_server_http import check_demo
from v1_support import chain_x_flow, http_server, isolated_env, make_world  # noqa: F401  (pytest fixtures)

BRIDGE = Path(__file__).resolve().parents[1] / "bridge"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(
    NODE is None or not (BRIDGE / "node_modules" / "@modelcontextprotocol" / "sdk").is_dir(),
    reason="Node or the bridge's node_modules are missing (run npm ci in MCP-Server/bridge)",
)


def run_through_bridge(url: str, timeout: float = 60.0) -> dict:
    params = StdioServerParameters(
        command=NODE,
        args=[str(BRIDGE / "server" / "index.js")],
        # The SDK passes only a few variables to the child, so pass the URL explicitly.
        env={**os.environ, "INGENUS_MCP_URL": url},
    )

    async def flow() -> dict:
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            init = await session.initialize()
            out = await chain_x_flow(session)
            out["server"] = init.server_info.name
            return out

    return asyncio.run(asyncio.wait_for(flow(), timeout))


def test_full_demo_through_the_bridge(http_server):
    check_demo(run_through_bridge(http_server))


def test_bridge_refuses_plain_http_to_another_machine():
    params = StdioServerParameters(
        command=NODE,
        args=[str(BRIDGE / "server" / "index.js")],
        env={**os.environ, "INGENUS_MCP_URL": "http://10.0.0.5:8765/mcp"},
    )

    async def attempt() -> None:
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()

    with pytest.raises(Exception):  # noqa: B017  (the bridge exits; the client sees a closed pipe)
        asyncio.run(asyncio.wait_for(attempt(), 20))
