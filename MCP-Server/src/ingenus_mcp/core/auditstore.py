"""A central store for audit events (decisions 0005 and 0008). SQLite file or Postgres.

The tool-call log (calllog.py) is the source of truth and the local buffer: every event is written
there first, as one JSON line with a hash chain. This module copies the same events into a queryable
store, best effort, and can catch up later (`ship`) if the store was down. Events are inserted once
(the event id is unique), so copying twice does no harm.

The store is a SQLite file (reference) or Postgres (INGENUS_PG_HOST set; decision 0008). Pruning old
events from the store never touches the local log, so the hash chain stays whole. It is a store for events
only: never page text, tokens or whole documents, because the events do not hold them.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from ingenus_mcp.core import db
from ingenus_mcp.core.db import STORE_ERRORS, Target

_SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS events (
    event_id  TEXT PRIMARY KEY,
    ts        TEXT NOT NULL,
    event     TEXT NOT NULL,
    user      TEXT,
    user_id   TEXT,
    tool      TEXT,
    outcome   TEXT,
    prev_hash TEXT,
    hash      TEXT,
    record    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_ts ON events (ts);
CREATE INDEX IF NOT EXISTS events_user ON events (user);
CREATE INDEX IF NOT EXISTS events_tool ON events (tool);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

_POSTGRES_DDL = """
CREATE TABLE IF NOT EXISTS events (
    seq       BIGSERIAL,
    event_id  TEXT PRIMARY KEY,
    ts        TEXT NOT NULL,
    event     TEXT NOT NULL,
    "user"    TEXT,
    user_id   TEXT,
    tool      TEXT,
    outcome   TEXT,
    prev_hash TEXT,
    hash      TEXT,
    record    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_ts ON events (ts);
CREATE INDEX IF NOT EXISTS events_user ON events ("user");
CREATE INDEX IF NOT EXISTS events_tool ON events (tool);
"""


def _session(target: Target):
    return db.session(target, _SQLITE_DDL, _POSTGRES_DDL)


def _outcome(record: dict[str, Any]) -> str | None:
    if record.get("event") == "login":
        return record.get("outcome")
    return "error" if record.get("error") else "ok"


def _event_id(record: dict[str, Any], raw: str | None = None) -> str:
    """The id of an event; a line from before ids existed gets a stable one from its text."""
    if record.get("event_id"):
        return str(record["event_id"])
    text = raw if raw is not None else json.dumps(record, sort_keys=True)
    return "legacy-" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:20]


def add(target: Target, record: dict[str, Any], raw: str | None = None) -> bool:
    """Insert one event. Returns False if it was already there."""
    with _session(target) as conn:
        cursor = conn.execute(
            'INSERT INTO events (event_id, ts, event, "user", user_id, tool, outcome, prev_hash, hash, record)'
            " VALUES (%(event_id)s, %(ts)s, %(event)s, %(user)s, %(user_id)s, %(tool)s, %(outcome)s,"
            " %(prev_hash)s, %(hash)s, %(record)s) ON CONFLICT DO NOTHING",
            {
                "event_id": _event_id(record, raw),
                "ts": record.get("ts", ""),
                "event": record.get("event", "tool_call"),
                "user": record.get("user"),
                "user_id": record.get("user_id"),
                "tool": record.get("tool"),
                "outcome": _outcome(record),
                "prev_hash": record.get("prev_hash"),
                "hash": record.get("hash"),
                "record": json.dumps(record, ensure_ascii=False, separators=(",", ":")),
            },
        )
        return cursor.rowcount == 1


def emit(path: Target | None, record: dict[str, Any]) -> None:
    """Copy one event to the store. Never raises: a store that is down must not stop the tools."""
    if path is None:
        return
    try:
        add(path, record)
    except STORE_ERRORS as exc:
        print(
            f"[ingenus_mcp] audit store unavailable ({type(exc).__name__}); the event stays in the "
            "local log and can be shipped later (python -m ingenus_mcp.audit ship)",
            file=sys.stderr,
        )


def ship(log_path: Path, store_path: Target) -> tuple[int, int]:
    """Copy every event of the local log that the store does not have yet. Returns (copied, already_there)."""
    copied = already = 0
    if not log_path.is_file():
        return 0, 0
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue  # a half-written line: verify will report it
        if add(store_path, record, raw=line):
            copied += 1
        else:
            already += 1
    return copied, already


_QUERY = (
    "SELECT record FROM events"
    ' WHERE (%(user)s::text IS NULL OR "user" = %(user)s) AND (%(tool)s::text IS NULL OR tool = %(tool)s)'
    " AND (%(event)s::text IS NULL OR event = %(event)s) AND (%(since)s::text IS NULL OR ts >= %(since)s)"
)


def query(
    path: Target,
    *,
    user: str | None = None,
    tool: str | None = None,
    event: str | None = None,
    since: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Events, newest first. `since` is an ISO time (UTC); `user` matches the sign-in name exactly."""
    # Fixed SQL: each filter is "unset, or equal". Values are bound, nothing is pasted into the text.
    order = db.pick(
        path,
        _QUERY + " ORDER BY ts DESC, rowid DESC LIMIT %(limit)s",
        _QUERY + " ORDER BY ts DESC, seq DESC LIMIT %(limit)s",
    )
    params = {"user": user, "tool": tool, "event": event, "since": since, "limit": limit}
    with _session(path) as conn:
        rows = conn.execute(order, params).fetchall()
    return [json.loads(r[0]) for r in rows]


def count(path: Target) -> int:
    with _session(path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    return int(total)


def prune(path: Target, before: str) -> int:
    """Delete the events older than `before` (an ISO time, UTC) from the store. Returns how many.

    The local log is not touched, so its hash chain stays whole; `ship` would copy the old lines back,
    so a retention job should prune the log's old lines away too once they are archived (not built).
    """
    with _session(path) as conn:
        return int(
            conn.execute("DELETE FROM events WHERE ts < %(before)s", {"before": before}).rowcount
        )
