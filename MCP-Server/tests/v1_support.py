"""Shared test helpers and fixtures for v1.

Not a conftest.py on purpose: v0's tests import helpers with `from conftest import`, so a second
conftest.py would clash when both suites run together. Every v1 test module imports the fixtures it
needs from here, and always `isolated_env` (test_v1_support_guard.py checks this).
"""

from __future__ import annotations

import contextlib
import json
import os
import socket
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

import pytest

from ingenus_mcp.core.models import Citation, ExtractedTerm

REPO = Path(__file__).resolve().parents[2]
MASTER = "Chain_X/Chain_X_Master_Supply_Agreement_2024.pdf"
AMEND2 = "Chain_X/Chain_X_Amendment_2_2026.pdf"
DRAFT3 = "Chain_X/Chain_X_Amendment_3_DRAFT.pdf"


def term(
    kind: str,
    product: str | None,
    rate: str,
    quote: str,
    *,
    document: str = AMEND2,
    page: int = 2,
    effective: date = date(2026, 7, 1),
) -> ExtractedTerm:
    return ExtractedTerm(
        kind=kind,  # type: ignore[arg-type]
        product=product,
        rate_pct=rate,  # type: ignore[arg-type]
        effective_date=effective,
        citation=Citation(document=document, page=page, clause="Schedule A", quote=quote),
    )


def chain_x_terms() -> list[ExtractedTerm]:
    """What a careful Claude would extract from Chain X Amendment 2."""
    return [
        term("rebate", "Product A", "6", "Product A rebate: 6.0% of net sales of Product A."),
        term("rebate", "Product B", "3", "Product B rebate: 3.0% of net sales of Product B."),
        term("rebate", "Product C", "5", "Product C rebate: 5.0% of net sales of Product C (new)."),
        term(
            "admin_fee", None, "2.5", "Administrative fee: 2.5% of total net sales of all Products."
        ),
    ]


@contextlib.contextmanager
def signed_in_as(name: str, oid: str):
    """Make the code under test think `name` is the signed-in caller (as the server does per request)."""
    from mcp.server.auth.middleware.auth_context import auth_context_var
    from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
    from mcp.server.auth.provider import AccessToken

    access = AccessToken(
        token="t-" + oid,
        client_id="test-app",
        scopes=["access_as_user"],
        expires_at=None,
        resource="test",
        subject=oid,
        claims={"preferred_username": name, "oid": oid},
    )
    marker = auth_context_var.set(AuthenticatedUser(access))
    try:
        yield
    finally:
        auth_context_var.reset(marker)


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """Every test logs to its own temp file and never touches MCP-Server/data/runtime."""
    monkeypatch.setenv("INGENUS_LOG_PATH", str(tmp_path / "tool_calls.jsonl"))
    monkeypatch.setenv("INGENUS_USER", "tester")
    monkeypatch.setenv("INGENUS_HISTORY_DB", str(tmp_path / "history.sqlite"))
    monkeypatch.setenv("INGENUS_RECORDS_DB", str(tmp_path / "records.sqlite"))
    monkeypatch.setenv("INGENUS_NO_ENV_FILE", "1")  # never read a developer's MCP-Server/.env
    for var in (
        "INGENUS_CONTRACTS_DIR",
        "INGENUS_SAP_MOCK_FILE",
        "INGENUS_SAP_ADAPTER",
        "INGENUS_MCP_HOST",
        "INGENUS_MCP_PORT",
        "INGENUS_AUTH",
        "INGENUS_DOC_SOURCE",
        "INGENUS_SP_SITE_URL",
        "INGENUS_SP_FOLDER",
        "INGENUS_TENANT_ID",
        "INGENUS_SERVER_CLIENT_ID",
        "INGENUS_CERT_KEY_FILE",
        "INGENUS_CERT_THUMBPRINT",
        "INGENUS_JWKS_URI",
        "INGENUS_AUDIT_STORE",
        "INGENUS_OD_FOLDER",
        "INGENUS_NETWORK_ROOT",
        "INGENUS_EXCLUDE_PATTERNS",
        "INGENUS_SOURCES",
        "INGENUS_SOURCES_TIMEOUT",
    ):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


@pytest.fixture
def make_world(tmp_path, monkeypatch):
    """Build a tiny contract folder and SAP mock in tmp_path and point the server at them."""

    def build(
        pages: list[str],
        sap_rebates: list[dict],
        sales: list[dict],
        name: str = "Acme_Agreement.txt",
    ) -> str:
        contracts = tmp_path / "contracts"
        (contracts / "Acme").mkdir(parents=True)
        (contracts / "Acme" / name).write_text("\f".join(pages), encoding="utf-8")
        sap = {
            "_label": "SYNTHETIC test data",
            "customers": [{"customer_id": "T-1", "name": "Acme"}],
            "rebate_setup": [
                {"customer_id": "T-1", "valid_from": "2025-01-01", "valid_to": None, **r}
                for r in sap_rebates
            ],
            "sales_volume": [{"customer_id": "T-1", **s} for s in sales],
        }
        sap_file = tmp_path / "sap.json"
        sap_file.write_text(json.dumps(sap), encoding="utf-8")
        monkeypatch.setenv("INGENUS_CONTRACTS_DIR", str(contracts))
        monkeypatch.setenv("INGENUS_SAP_MOCK_FILE", str(sap_file))
        return f"Acme/{name}"

    return build


# --- A real v1 server process over HTTP (used by the HTTP and bridge tests) -------------------


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(port: int, proc: subprocess.Popen, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("server exited early; see server.err in the test's temp folder")
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.2)
    raise TimeoutError(f"server did not open port {port} in {timeout}s")


@pytest.fixture
def http_server(tmp_path):
    """Start `python -m ingenus_mcp.server` on a free loopback port; yield its /mcp URL."""
    port = _free_port()
    env = {**os.environ, "INGENUS_USER": "tester"}
    # The server logs to stderr. Send it to a file: an unread pipe fills up and freezes the server.
    with (tmp_path / "server.err").open("w", encoding="utf-8") as err:
        proc = subprocess.Popen(  # fixed argv, no shell
            [
                sys.executable,
                "-m",
                "ingenus_mcp.server",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=err,
        )
        try:
            _wait_for_port(port, proc)
            yield f"http://127.0.0.1:{port}/mcp"
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


async def chain_x_flow(session) -> dict:
    """Walk the demo on an initialised MCP ClientSession, playing Claude's part."""
    out: dict = {}
    tools = (await session.list_tools()).tools
    out["tools"] = {t.name: t.annotations.read_only_hint for t in tools}
    out["prompts"] = [p.name for p in (await session.list_prompts()).prompts]
    guide = await session.call_tool(
        "get_guide", {"names": ["contract-check-playbook", "report-format"]}
    )
    out["guides"] = [g["name"] for g in guide.structured_content["guides"]]
    out["guide_chars"] = sum(len(g["content"]) for g in guide.structured_content["guides"])
    resolved = await session.call_tool("resolve_customer", {"name": "Chain X"})
    customer_id = resolved.structured_content["resolved"]["sap_customer_id"]
    files = await session.call_tool("find_contract_files", {"customer": "Chain X"})
    out["files"] = [f["document_id"] for f in files.structured_content["files"]]
    terms = [json.loads(t.model_dump_json()) for t in chain_x_terms()]
    compared = await session.call_tool(
        "compare_contract_to_sap",
        {"customer_id": customer_id, "as_of": "2026-08-31", "terms": terms},
    )
    out["compare"] = compared.structured_content
    bad = await session.call_tool("get_contract_pages", {"document_id": "../README.md"})
    out["traversal_is_error"] = bad.is_error
    return out
