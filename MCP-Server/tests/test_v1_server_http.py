"""Run the v1 server as a real process over HTTP (as Claude Code reaches it) and walk the demo.

The client plays Claude's part: it picks the calls and supplies the extracted terms. Offline: the
server listens on loopback only, and there is no Claude API call.
"""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from v1_support import (  # noqa: F401  (pytest fixtures)
    AMEND2,
    chain_x_flow,
    http_server,
    isolated_env,
    make_world,
)


def run_over_http(url: str) -> dict:
    async def flow() -> dict:
        async with streamable_http_client(url) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                init = await session.initialize()
                out = await chain_x_flow(session)
                out["server"] = init.server_info.name
                return out

    return asyncio.run(flow())


def check_demo(out: dict) -> None:
    assert out["server"] == "ingenus"
    assert len(out["tools"]) == 6 and all(out["tools"].values())
    assert out["prompts"] == ["contract_check"]
    assert AMEND2 in out["files"]
    result = out["compare"]
    assert Decimal(result["total_monthly_gap"]) == Decimal("8500.00")
    assert Decimal(result["total_indicative_exposure"]) == Decimal("17000.00")
    assert result["not_checked"] == []
    assert out["traversal_is_error"] is True


def test_full_demo_over_http(http_server, isolated_env):
    check_demo(run_over_http(http_server))

    # The server process wrote the tool-call log to the test's temp folder (set by isolated_env).
    log = isolated_env / "tool_calls.jsonl"
    records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert [r["tool"] for r in records][:3] == [
        "resolve_customer",
        "find_contract_files",
        "compare_contract_to_sap",
    ]
    assert {r["user"] for r in records} == {"tester"}


def test_a_request_without_a_handshake_is_answered(http_server):
    """Claude Desktop's Cowork and Code sessions send a request before any initialize. A stateful
    server rejects it ("Missing session ID", seen 19 Oct 2026); the stateless default answers it."""
    import urllib.request

    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}).encode()
    request = urllib.request.Request(  # loopback URL from the fixture
        http_server,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        assert response.status == 200
        text = response.read().decode("utf-8")
    assert "compare_contract_to_sap" in text


def test_server_is_stateless_by_default():
    from ingenus_mcp.core.config import load_settings

    assert load_settings().stateless is True


def test_server_binds_to_loopback_by_default():
    from ingenus_mcp.core.config import load_settings

    assert load_settings().host == "127.0.0.1"
