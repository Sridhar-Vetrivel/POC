"""V1-4, the laptop half: the bridge adds the user's token to every request.

Claude Desktop is played by the Python MCP client over stdio. The real bridge core runs under Node
(through bridge/test/run_with_token.js, which supplies a fixed token instead of a Microsoft sign-in),
and talks to a real v1 server process that demands a valid Entra token. Offline: loopback only. The
browser sign-in itself is checked by the Node unit tests and, for real, by hand.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters, stdio_client
from test_v1_auth import (  # noqa: F401  (pytest fixtures and helpers)
    USER,
    entra_env,
    jwks_server,
    make_token,
    signed_in_server,
    signing_key,
)
from test_v1_server_http import check_demo
from v1_support import chain_x_flow, isolated_env  # noqa: F401

BRIDGE = Path(__file__).resolve().parents[1] / "bridge"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(
    NODE is None or not (BRIDGE / "node_modules" / "@modelcontextprotocol" / "sdk").is_dir(),
    reason="Node or the bridge's node_modules are missing (run npm ci in MCP-Server/bridge)",
)


def through_bridge(url: str, token: str | None, flow, timeout: float = 90.0):
    env = {**os.environ, "INGENUS_MCP_URL": url}
    if token:
        env["TEST_BEARER_TOKEN"] = token
    params = StdioServerParameters(
        command=NODE, args=[str(BRIDGE / "test" / "run_with_token.js")], env=env
    )

    async def run():
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            init = await session.initialize()
            out = await flow(session)
            out["server"] = init.server_info.name
            return out

    return asyncio.run(asyncio.wait_for(run(), timeout))


def test_the_node_unit_tests_pass():
    result = subprocess.run(  # fixed argv, no shell
        [NODE, "--test", str(BRIDGE / "test" / "auth.test.js")],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-1000:]


def test_the_full_demo_through_the_bridge_with_a_signed_in_user(
    signed_in_server, signing_key, isolated_env
):
    token = make_token(signing_key)
    check_demo(through_bridge(signed_in_server, token, chain_x_flow))

    log = isolated_env / "tool_calls.jsonl"
    text = log.read_text(encoding="utf-8")
    records = [json.loads(line) for line in text.splitlines()]
    assert records and {r["user"] for r in records} == {
        USER
    }  # every call is named after the person
    assert token not in text


def test_without_a_token_the_server_refuses_and_the_bridge_reports_it(signed_in_server):
    async def only_initialize(session):
        return {}

    with pytest.raises(Exception):  # noqa: B017  (Desktop would see a JSON-RPC error)
        through_bridge(signed_in_server, None, only_initialize, timeout=40)


def test_a_token_the_server_does_not_accept_is_refused(signed_in_server, signing_key):
    wrong_scope = make_token(signing_key, scp="not_our_scope")

    async def only_initialize(session):
        return {}

    with pytest.raises(Exception):  # noqa: B017
        through_bridge(signed_in_server, wrong_scope, only_initialize, timeout=40)
