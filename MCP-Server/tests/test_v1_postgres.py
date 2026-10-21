"""2.2 and 2.3 on Postgres (decision 0008): the same audit store and check history, a different back end.

Needs a Postgres on this machine. It looks at 127.0.0.1:INGENUS_TEST_PG_PORT (default 5433), database
`ingenus_audit`, user `postgres`, password from MCP-Server/secrets/pg_password.txt (or the file named by
INGENUS_TEST_PG_PASSWORD_FILE), and SKIPS if it cannot connect. Each test works in its own schema, which is
dropped afterwards, so no real rows are touched. Tests never read MCP-Server/.env.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest
from test_v1_compare import CHAIN_X  # noqa: F401
from test_v1_history import ADITYA, SRIDHAR, check_chain_x
from v1_support import AMEND2, isolated_env, make_world, signed_in_as  # noqa: F401

from ingenus_mcp import audit
from ingenus_mcp.core import auditstore, db, history
from ingenus_mcp.core.config import load_settings
from ingenus_mcp.tools.get_check_history import get_check_history
from ingenus_mcp.tools.resolve_customer import resolve_customer

SERVER_DIR = Path(__file__).resolve().parents[1]
PASSWORD_FILE = Path(
    os.environ.get("INGENUS_TEST_PG_PASSWORD_FILE", SERVER_DIR / "secrets" / "pg_password.txt")
)
PORT = os.environ.get("INGENUS_TEST_PG_PORT", "5433")


def _connect(schema: str | None = None):
    return psycopg.connect(
        host="127.0.0.1",
        port=int(PORT),
        dbname="ingenus_audit",
        user="postgres",
        password=PASSWORD_FILE.read_text(encoding="utf-8").strip(),
        connect_timeout=3,
        autocommit=True,
    )


@pytest.fixture
def pg_env(monkeypatch):
    """Point the settings at a throwaway schema of the local Postgres; skip if there is none."""
    schema = "t_" + uuid.uuid4().hex[:12]
    try:
        admin = _connect()
    except (psycopg.Error, OSError):
        pytest.skip("no local Postgres to test against (see the module docstring)")
    monkeypatch.setenv("INGENUS_PG_HOST", "127.0.0.1")
    monkeypatch.setenv("INGENUS_PG_PORT", PORT)
    monkeypatch.setenv("INGENUS_PG_PASSWORD_FILE", str(PASSWORD_FILE))
    monkeypatch.setenv("INGENUS_PG_SCHEMA", schema)
    monkeypatch.delenv(
        "INGENUS_HISTORY_DB"
    )  # isolated_env points it at a SQLite file; Postgres wins here
    try:
        yield load_settings().audit_store
    finally:
        admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')  # noqa: S608 - our own name
        admin.close()


def test_postgres_settings_send_both_stores_to_postgres(pg_env):
    settings = load_settings()
    assert isinstance(pg_env, db.PgTarget)
    assert settings.audit_store == settings.history_db == pg_env
    assert "password" not in str(pg_env).lower() and "postgres://postgres@127.0.0.1" in str(pg_env)


def test_explicit_paths_still_win_over_postgres(pg_env, tmp_path, monkeypatch):
    monkeypatch.setenv("INGENUS_AUDIT_STORE", str(tmp_path / "a.sqlite"))
    monkeypatch.setenv("INGENUS_HISTORY_DB", str(tmp_path / "h.sqlite"))
    settings = load_settings()
    assert settings.audit_store == tmp_path / "a.sqlite"
    assert settings.history_db == tmp_path / "h.sqlite"


def test_tool_calls_reach_postgres_with_names_and_the_local_log_still_chains(pg_env):
    with signed_in_as(*SRIDHAR):
        resolve_customer(name="Chain X")
    with signed_in_as(*ADITYA):
        resolve_customer(name="Chain Y")
    rows = auditstore.query(pg_env, event="tool_call")
    assert [r["user"] for r in rows] == [ADITYA[0], SRIDHAR[0]]  # newest first
    assert auditstore.count(pg_env) == 2
    assert [r["user"] for r in auditstore.query(pg_env, user=SRIDHAR[0])] == [SRIDHAR[0]]
    assert auditstore.query(pg_env, tool="no_such_tool") == []
    # the local file is still the source of truth, and its chain verifies
    log = load_settings().log_path.read_text(encoding="utf-8").splitlines()
    assert audit.calllog.verify_chain(log).ok


def test_shipping_twice_copies_each_event_once(pg_env):
    resolve_customer(name="Chain X")
    resolve_customer(name="Chain Y")
    log = load_settings().log_path
    # the two calls were already emitted live, so shipping finds them there
    assert auditstore.ship(log, pg_env) == (0, 2)
    assert auditstore.count(pg_env) == 2


def test_a_missing_event_is_caught_up_by_ship(pg_env):
    resolve_customer(name="Chain X")
    with _connect() as admin:
        admin.execute(f'DELETE FROM "{pg_env.schema}".events')  # noqa: S608 - our own name
    assert auditstore.count(pg_env) == 0
    assert auditstore.ship(load_settings().log_path, pg_env) == (1, 0)


def test_events_in_the_same_instant_keep_their_order(pg_env):
    for n in range(5):
        auditstore.add(
            pg_env, {"ts": "2026-10-21T10:00:00.000+00:00", "event_id": f"e{n}", "tool": "t"}
        )
    assert [r["event_id"] for r in auditstore.query(pg_env)] == ["e4", "e3", "e2", "e1", "e0"]


def test_prune_deletes_only_what_is_older(pg_env):
    auditstore.add(pg_env, {"ts": "2025-01-01T00:00:00.000+00:00", "event_id": "old", "tool": "t"})
    auditstore.add(pg_env, {"ts": "2026-10-01T00:00:00.000+00:00", "event_id": "new", "tool": "t"})
    assert auditstore.prune(pg_env, "2026-01-01T00:00:00.000+00:00") == 1
    assert [r["event_id"] for r in auditstore.query(pg_env)] == ["new"]


def test_a_check_leaves_a_record_the_next_person_reads_from_postgres(pg_env):
    with signed_in_as(*SRIDHAR):
        check_chain_x()
    with signed_in_as(*ADITYA):
        result = get_check_history(document_id=AMEND2)
    assert result.available and len(result.records) == 1
    record = result.records[0]
    assert record.who == SRIDHAR[0] and record.is_you is False
    assert Decimal(record.total_monthly_gap) == Decimal("8500.00")
    assert [d.document_id for d in record.documents] == [AMEND2]
    assert record.documents[0].changed_since is False


def test_history_is_newest_first_and_the_limit_applies(pg_env):
    with signed_in_as(*SRIDHAR):
        check_chain_x(date(2026, 8, 31))
    with signed_in_as(*ADITYA):
        check_chain_x(date(2026, 7, 31))
        assert [r.who for r in get_check_history(customer_id=CHAIN_X, limit=1).records] == [
            ADITYA[0]
        ]
        assert [r.who for r in get_check_history(customer_id=CHAIN_X).records] == [
            ADITYA[0],
            SRIDHAR[0],
        ]


def test_history_prune_removes_old_checks_and_their_file_rows(pg_env):
    with signed_in_as(*SRIDHAR):
        check_chain_x()
    assert history.prune(pg_env, "2000-01-01T00:00:00.000+00:00") == 0
    assert history.prune(pg_env, "2999-01-01T00:00:00.000+00:00") == 1
    with signed_in_as(*SRIDHAR):
        assert get_check_history(customer_id=CHAIN_X).records == []
    with _connect() as admin:
        left = admin.execute(f'SELECT COUNT(*) FROM "{pg_env.schema}".check_docs').fetchone()[0]  # noqa: S608
    assert left == 0


def test_the_prune_command_uses_the_retention_days(pg_env, capsys):
    auditstore.add(
        pg_env, {"ts": "2020-01-01T00:00:00.000+00:00", "event_id": "ancient", "tool": "t"}
    )
    resolve_customer(name="Chain X")
    assert audit.main(["prune", "--days", "365"]) == 0
    out = capsys.readouterr().out
    assert "Deleted 1 event(s) older than 365 days" in out
    assert "Deleted 0 check record(s)" in out
    assert audit.main(["prune", "--days", "0"]) == 1


def test_a_postgres_that_is_down_does_not_fail_the_tools(pg_env, monkeypatch, capfd):
    monkeypatch.setenv("INGENUS_PG_PORT", "1")  # nothing listens here
    with signed_in_as(*SRIDHAR):
        assert resolve_customer(name="Chain X")  # the call still succeeds
        check_chain_x()  # and so does a check
    assert "audit store unavailable" in capfd.readouterr().err
    log = load_settings().log_path.read_text(encoding="utf-8")
    assert (
        json.loads(log.splitlines()[0])["user"] == SRIDHAR[0]
    )  # the local log has the event for `ship`
