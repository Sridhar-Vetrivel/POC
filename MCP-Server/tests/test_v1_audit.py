"""2.2: the audit log and login log: hash chain, central store, login events (decision 0005).

Offline. The central store here is SQLite; a real one only has to offer the same add, emit and query.
"""

from __future__ import annotations

import json
import time

import pytest
from test_v1_auth import (  # noqa: F401  (pytest fixtures and helpers)
    USER,
    entra_env,
    jwks_server,
    make_token,
    signing_key,
)
from v1_support import isolated_env, make_world, signed_in_as  # noqa: F401

from ingenus_mcp import audit, report
from ingenus_mcp.core import auditstore, auth, calllog
from ingenus_mcp.core.config import load_settings
from ingenus_mcp.tools.resolve_customer import resolve_customer


def log_path():
    return load_settings().log_path


def lines():
    return log_path().read_text(encoding="utf-8").splitlines()


def three_calls():
    for name in ("Chain X", "Chain Y", "Wholesaler Z"):
        resolve_customer(name=name)


# --- the hash chain ----------------------------------------------------------------------------


def test_every_event_is_chained_and_the_chain_verifies():
    three_calls()
    report_ = calllog.verify_chain(lines())
    assert report_.ok and report_.hashed == 3 and report_.legacy == 0
    first = json.loads(lines()[0])
    assert (
        first["prev_hash"] == calllog.GENESIS
        and first["event"] == "tool_call"
        and first["event_id"]
    )


def test_an_edited_line_is_found():
    three_calls()
    rows = lines()
    record = json.loads(rows[1])
    record["user"] = "someone else"
    rows[1] = json.dumps(record, separators=(",", ":"))
    result = calllog.verify_chain(rows)
    assert not result.ok and "line 2 was edited" in result.problem


def test_a_removed_line_is_found():
    three_calls()
    rows = lines()
    del rows[1]
    result = calllog.verify_chain(rows)
    assert not result.ok and "line 2" in result.problem


def test_reordered_lines_are_found():
    three_calls()
    rows = lines()
    rows[1], rows[2] = rows[2], rows[1]
    assert not calllog.verify_chain(rows).ok


def test_a_cut_off_line_is_found():
    three_calls()
    rows = lines()
    rows[2] = rows[2][:40]
    result = calllog.verify_chain(rows)
    assert not result.ok and "not valid JSON" in result.problem


def test_lines_cut_off_the_end_cannot_be_seen_and_that_is_documented():
    """Nothing after the last line points back at it. Keep the last hash elsewhere to catch this."""
    three_calls()
    assert calllog.verify_chain(lines()[:-1]).ok


def test_the_chain_carries_on_after_a_restart():
    three_calls()
    calllog._CHAIN.clear()  # a new server process knows nothing but the file
    three_calls()
    assert calllog.verify_chain(lines()).ok and len(lines()) == 6


def test_a_log_from_before_the_chain_existed_is_tolerated_then_chained():
    log_path().parent.mkdir(parents=True, exist_ok=True)
    log_path().write_text(
        json.dumps({"ts": "2026-10-01T00:00:00Z", "user": "old", "tool": "x"}) + "\n",
        encoding="utf-8",
    )
    three_calls()
    result = calllog.verify_chain(lines())
    assert result.ok and result.legacy == 1 and result.hashed == 3
    # but a line without a hash AFTER chained events is a problem
    assert not calllog.verify_chain([*lines(), json.dumps({"ts": "x", "tool": "y"})]).ok


def test_the_verify_command_reports_ok_and_broken(capsys):
    three_calls()
    assert audit.main(["verify", "--log", str(log_path())]) == 0
    assert "Chain: OK" in capsys.readouterr().out
    rows = lines()
    rows[0] = rows[0].replace("Chain X", "Edited")
    log_path().write_text("\n".join(rows) + "\n", encoding="utf-8")
    assert audit.main(["verify", "--log", str(log_path())]) == 2
    assert "BROKEN" in capsys.readouterr().out


# --- the central store -------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path, monkeypatch):
    path = tmp_path / "central" / "audit.sqlite"
    monkeypatch.setenv("INGENUS_AUDIT_STORE", str(path))
    return path


def test_two_people_calls_reach_the_store_with_their_names(store):
    with signed_in_as("sridhar@example.test", "oid-1"):
        resolve_customer(name="Chain X")
    with signed_in_as("aditya@example.test", "oid-2"):
        resolve_customer(name="Chain Y")
    assert auditstore.count(store) == 2 == len(lines())
    assert [r["user"] for r in auditstore.query(store, user="aditya@example.test")] == [
        "aditya@example.test"
    ]
    row = auditstore.query(store, user="sridhar@example.test")[0]
    assert row["user_id"] == "oid-1" and row["tool"] == "resolve_customer"
    assert len(auditstore.query(store, tool="resolve_customer", limit=1)) == 1
    assert auditstore.query(store, since="2999-01-01") == []


def test_the_store_copy_is_the_same_event_with_the_same_hash(store):
    resolve_customer(name="Chain X")
    assert auditstore.query(store)[0] == json.loads(lines()[0])


def test_a_store_that_is_down_does_not_stop_the_tool_or_lose_the_event(
    tmp_path, monkeypatch, capsys
):
    blocker = tmp_path / "not_a_folder"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("INGENUS_AUDIT_STORE", str(blocker / "audit.sqlite"))  # cannot be created
    assert resolve_customer(name="Chain X").resolved is not None  # the tool still answers
    assert len(lines()) == 1  # the local log has the event
    assert "audit store unavailable" in capsys.readouterr().err


def test_shipping_catches_up_and_is_safe_to_repeat(tmp_path, monkeypatch):
    three_calls()  # no store yet: only the local log has them
    store_path = tmp_path / "later.sqlite"
    assert auditstore.ship(log_path(), store_path) == (3, 0)
    assert auditstore.ship(log_path(), store_path) == (0, 3)  # nothing is copied twice
    assert auditstore.count(store_path) == 3


def test_the_query_command_prints_events(store, capsys):
    resolve_customer(name="Chain X")
    assert audit.main(["query", "--store", str(store), "--tool", "resolve_customer"]) == 0
    printed = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [p["tool"] for p in printed] == ["resolve_customer"]


# --- login events ------------------------------------------------------------------------------


def logins():
    return [json.loads(x) for x in lines() if json.loads(x).get("event") == "login"]


def test_an_accepted_token_is_one_login_event_per_token(entra_env, signing_key, store):
    verifier = auth.EntraTokenVerifier(load_settings())
    token = make_token(signing_key)
    for _ in range(5):
        assert verifier.verify(token) is not None
    events = logins()
    assert len(events) == 1
    assert events[0]["outcome"] == "accepted" and events[0]["user"] == USER and events[0]["user_id"]
    assert token not in log_path().read_text(encoding="utf-8")
    assert auditstore.query(store, event="login")[0]["outcome"] == "accepted"  # also in the store


def test_a_new_token_for_the_same_person_is_a_new_login_event(entra_env, signing_key):
    verifier = auth.EntraTokenVerifier(load_settings())
    verifier.verify(make_token(signing_key))
    verifier.verify(make_token(signing_key, exp=int(time.time()) + 7200))
    assert len(logins()) == 2


def test_a_refused_token_is_logged_with_the_reason_and_no_token(entra_env, signing_key):
    verifier = auth.EntraTokenVerifier(load_settings())
    bad = make_token(signing_key, scp="nope")
    assert verifier.verify(bad) is None
    [event] = logins()
    assert event["outcome"] == "refused" and event["reason"] == "missing scope"
    assert event["user"] is None  # a refused token proves nobody
    assert bad not in log_path().read_text(encoding="utf-8")


def test_refusals_of_the_same_kind_are_rate_limited(entra_env, signing_key):
    verifier = auth.EntraTokenVerifier(load_settings())
    for _ in range(20):
        verifier.verify(make_token(signing_key, scp="nope"))
    assert len(logins()) == 1  # one per reason per 10 seconds, so an attack cannot flood the log
    verifier.verify(make_token(signing_key, exp=int(time.time()) - 3600))  # a different reason
    assert len(logins()) == 2


def test_login_events_are_chained_with_the_tool_calls(entra_env, signing_key):
    verifier = auth.EntraTokenVerifier(load_settings())
    verifier.verify(make_token(signing_key))
    resolve_customer(name="Chain X")
    assert calllog.verify_chain(lines()).ok


def test_the_usage_report_ignores_logins_but_counts_them(entra_env, signing_key):
    verifier = auth.EntraTokenVerifier(load_settings())
    verifier.verify(make_token(signing_key))
    verifier.verify(make_token(signing_key, scp="nope"))
    resolve_customer(name="Chain X")
    summary = report.summarise_usage(report.load_records(log_path()))
    assert summary["total_calls"] == 1
    assert summary["logins_accepted"] == 1 and summary["logins_refused"] == 1
