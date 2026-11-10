"""Operator dashboard: read-only, loopback only, and honest about what it shows.

Offline. The data is real: tool calls and checks made through the tools, written to the temp log and
history that `isolated_env` points at.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

import pytest
from test_v1_compare import CHAIN_X  # noqa: F401
from v1_support import (  # noqa: F401  (pytest fixtures and helpers)
    chain_x_terms,
    isolated_env,
    make_world,
    signed_in_as,
)

from ingenus_mcp import dashboard
from ingenus_mcp.core.config import load_settings
from ingenus_mcp.tools.compare_contract_to_sap import compare_contract_to_sap
from ingenus_mcp.tools.resolve_customer import resolve_customer


def make_activity() -> None:
    with signed_in_as("sridhar@example.test", "oid-sridhar"):
        resolve_customer(name="Chain X")
        compare_contract_to_sap(customer_id=CHAIN_X, as_of=date(2026, 8, 31), terms=chain_x_terms())


def test_an_empty_server_gives_a_complete_empty_snapshot():
    snap = dashboard.snapshot(load_settings())
    assert snap["activity"]["total_calls"] == 0
    assert snap["audit"]["chain_ok"] is None  # no log yet: nothing to verify, and not called "intact"
    assert snap["checks"] == {"enabled": True, "store": "SQLite file", "checks": []}
    assert {"error"}.isdisjoint(snap["health"])


def test_activity_counts_calls_per_tool_and_person():
    make_activity()
    act = dashboard.snapshot(load_settings())["activity"]
    assert act["total_calls"] == 2 and act["users"] == 1
    assert {t["tool"] for t in act["tools"]} == {"resolve_customer", "compare_contract_to_sap"}
    assert act["recent"][0]["tool"] == "compare_contract_to_sap"  # newest first
    assert act["per_user"] == [{"user": "sridhar@example.test", "calls": 2}]


def test_checks_show_the_figures_and_the_files_used_but_no_quotes():
    make_activity()
    snap = dashboard.snapshot(load_settings())
    (check,) = snap["checks"]["checks"]
    assert check["customer_id"] == CHAIN_X and check["who"] == "sridhar@example.test"
    assert check["gap"] == "8500.00" and check["exposure"] == "17000.00"
    assert check["documents"] and check["lines"]
    assert "quote" not in json.dumps(snap["checks"]).lower()


def test_the_chain_status_follows_the_log(isolated_env):
    make_activity()
    assert dashboard.snapshot(load_settings())["audit"]["chain_ok"] is True
    log = Path(load_settings().log_path)
    log.write_text(log.read_text(encoding="utf-8").replace("sridhar", "someone"), encoding="utf-8")
    snap = dashboard.snapshot(load_settings())
    assert snap["audit"]["chain_ok"] is False
    assert any(
        r["name"] == "Audit hash chain" and r["status"] == "warn" for r in snap["health"]["rows"]
    )


def test_a_failing_section_does_not_blank_the_others(monkeypatch):
    make_activity()
    monkeypatch.setattr(
        dashboard, "checks", lambda s, down=None: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    snap = dashboard.snapshot(load_settings())
    assert snap["checks"]["error"].startswith("RuntimeError")
    assert snap["activity"]["total_calls"] == 2


def test_a_store_that_is_down_is_reported_once_and_the_chain_still_shows(isolated_env, monkeypatch):
    make_activity()
    attempts = []

    def refuse(target, text):
        attempts.append(text)
        raise OSError("database is down")

    monkeypatch.setenv("INGENUS_AUDIT_STORE", str(isolated_env / "audit.sqlite"))
    monkeypatch.setattr(dashboard, "_read_now", refuse)
    snap = dashboard.snapshot(load_settings())
    assert snap["audit"]["chain_ok"] is True and snap["audit"]["store_error"]
    assert snap["checks"]["error"].startswith("OSError")
    assert len(attempts) == 2  # one try per store (history, audit store), then "already down"
    rows = {r["name"]: r for r in snap["health"]["rows"]}
    assert rows["Check history"]["status"] == "warn" and rows["Audit hash chain"]["status"] == "ok"


def test_with_a_central_store_the_page_reports_from_the_store_not_the_local_log(
    isolated_env, monkeypatch
):
    monkeypatch.setenv("INGENUS_AUDIT_STORE", str(isolated_env / "audit.sqlite"))
    make_activity()
    Path(
        load_settings().log_path
    ).unlink()  # this machine has no log: only the store has the events
    snap = dashboard.snapshot(load_settings())
    assert snap["source"]["kind"] == "store" and snap["source"]["note"] == ""
    assert snap["activity"]["total_calls"] == 2
    assert snap["audit"]["events_in_store"] == 2 and snap["audit"]["chain_ok"] is None
    assert "no local log" in snap["audit"]["chain_problem"]


def test_if_the_central_store_cannot_be_read_the_local_log_is_shown_and_the_page_says_so(
    isolated_env, monkeypatch
):
    monkeypatch.setenv("INGENUS_AUDIT_STORE", str(isolated_env / "audit.sqlite"))
    make_activity()

    def refuse(target, text):
        raise OSError("database is down")

    monkeypatch.setattr(dashboard, "_read_now", refuse)
    snap = dashboard.snapshot(load_settings())
    assert snap["source"]["kind"] == "log" and "local copy" in snap["source"]["note"]
    assert snap["activity"]["total_calls"] == 2


def test_without_a_central_store_the_source_is_the_local_log():
    make_activity()
    assert dashboard.snapshot(load_settings())["source"]["kind"] == "log"


def test_the_stores_are_opened_read_only(isolated_env):
    make_activity()
    history = isolated_env / "history.sqlite"
    before = history.read_bytes()
    dashboard.snapshot(load_settings())
    assert history.read_bytes() == before
    with pytest.raises(Exception, match="readonly|read-only|attempt to write"):
        dashboard._read(history, "DELETE FROM checks")


@pytest.fixture
def running():
    server = dashboard.make_server(load_settings(), port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1]
    server.shutdown()
    server.server_close()


def get(port: int, path: str, host: str | None = None):
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}")
    if host:
        request.add_header("Host", host)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers, exc.read()


def test_the_page_and_the_data_are_served(running):
    make_activity()
    status, headers, body = get(running, "/")
    assert status == 200 and b"Ingenus MCP Operations" in body
    assert (
        "no-store" in headers["Cache-Control"]
        and "default-src 'none'" in headers["Content-Security-Policy"]
    )
    status, _, body = get(running, "/api/snapshot")
    assert status == 200 and json.loads(body)["activity"]["total_calls"] == 2


def test_only_the_page_and_the_snapshot_exist(running):
    assert get(running, "/api/other")[0] == 404
    assert get(running, "/../../.env")[0] == 404
    request = urllib.request.Request(
        f"http://127.0.0.1:{running}/api/snapshot", data=b"x", method="POST"
    )
    with pytest.raises(urllib.error.HTTPError) as err:
        urllib.request.urlopen(request, timeout=10)
    assert err.value.code == 501


def test_a_page_opened_under_another_name_is_refused(running):
    assert get(running, "/api/snapshot", host="evil.example.com")[0] == 403


def test_it_refuses_to_listen_on_a_network_address():
    with pytest.raises(SystemExit, match="Refusing to listen"):
        dashboard.make_server(load_settings(), host="0.0.0.0")  # noqa: S104 - this is the refusal under test


def test_the_page_never_puts_data_in_through_inner_html():
    page = Path(dashboard.PAGE).read_text(encoding="utf-8")
    assert "innerHTML" not in page and "document.write" not in page
