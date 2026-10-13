"""Run the real server as a subprocess over stdio, the way Claude Desktop would, and walk the demo.

The client plays Claude's part: it picks the calls and supplies the extracted terms. Offline: no
network and no Claude API.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from decimal import Decimal
from pathlib import Path

from conftest import AMEND2, chain_x_terms
from mcp import ClientSession, StdioServerParameters, stdio_client


def run_flow() -> dict:
    log_path = os.environ["INGENUS_LOG_PATH"]
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "ingenus_plugin.server"],
        # The SDK passes only a few variables to the child, so settings must be given explicitly.
        env={**os.environ, "INGENUS_LOG_PATH": log_path, "INGENUS_USER": "tester"},
    )

    async def flow() -> dict:
        out: dict = {}
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            init = await session.initialize()
            out["server"] = init.server_info.name
            tools = (await session.list_tools()).tools
            out["tools"] = {t.name: t.annotations.read_only_hint for t in tools}
            out["prompts"] = [p.name for p in (await session.list_prompts()).prompts]

            resolved = await session.call_tool("resolve_customer", {"name": "Chain X"})
            customer_id = resolved.structured_content["resolved"]["sap_customer_id"]
            files = await session.call_tool("find_contract_files", {"customer": "Chain X"})
            out["files"] = [f["document_id"] for f in files.structured_content["files"]]
            pages = await session.call_tool("get_contract_pages", {"document_id": AMEND2})
            out["pages"] = [p["page"] for p in pages.structured_content["pages"]]
            terms = [json.loads(t.model_dump_json()) for t in chain_x_terms()]
            compared = await session.call_tool(
                "compare_contract_to_sap",
                {"customer_id": customer_id, "as_of": "2026-08-31", "terms": terms},
            )
            out["compare"] = compared.structured_content
            out["compare_is_error"] = compared.is_error
            bad = await session.call_tool("get_contract_pages", {"document_id": "../README.md"})
            out["traversal_is_error"] = bad.is_error
            prompt = await session.get_prompt("contract_check", {"customer": "Chain X"})
            out["prompt_text"] = prompt.messages[0].content.text
        return out

    return asyncio.run(flow())


def test_full_demo_over_stdio():
    out = run_flow()

    assert out["server"] == "ingenus-contract-check"
    assert len(out["tools"]) == 6 and all(out["tools"].values())  # six tools, all read-only
    assert out["prompts"] == ["contract_check"]

    assert AMEND2 in out["files"] and not any("DRAFT" in f for f in out["files"])
    assert 2 in out["pages"]

    compare = out["compare"]
    assert out["compare_is_error"] is False
    assert Decimal(compare["total_monthly_gap"]) == Decimal("8500.00")
    assert Decimal(compare["total_indicative_exposure"]) == Decimal("17000.00")
    assert compare["not_checked"] == []
    assert len(compare["findings"]) == 4

    assert out["traversal_is_error"] is True
    assert "Chain X" in out["prompt_text"] and "{customer}" not in out["prompt_text"]


def test_the_server_logged_every_call():
    run_flow()
    records = [
        json.loads(x)
        for x in Path(os.environ["INGENUS_LOG_PATH"]).read_text(encoding="utf-8").splitlines()
    ]
    tools = [r["tool"] for r in records]
    assert tools == [
        "resolve_customer",
        "find_contract_files",
        "get_contract_pages",
        "compare_contract_to_sap",
        "get_contract_pages",  # the refused traversal attempt is logged too
    ]
    assert records[-1]["error"] is not None
