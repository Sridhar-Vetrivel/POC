"""Operator dashboard: one read-only page over the server's own records.

    python -m ingenus_mcp.dashboard [--port 8766]

Shows four things, all read from what the server already keeps: tool-call activity (the log), contract
check results (the check history), the audit trail with its hash-chain status, and server health. It
writes nothing, calls no tool and never contacts SAP, SharePoint or OneDrive.

It is an OPERATOR view: it shows every person's calls and checks, so it listens on this machine only
(loopback) and refuses any other address. It is not part of the MCP server and needs no sign-in because
nobody else can reach it. Synthetic data only, until Ingenus's data policy is signed off. Prints to
stdout (this is a command, not the MCP server).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import psycopg

from ingenus_mcp import __version__
from ingenus_mcp.core import calllog
from ingenus_mcp.core.config import Settings, load_env_file, load_settings
from ingenus_mcp.core.db import _SCHEMA_NAME, PgTarget, Target
from ingenus_mcp.report import load_records, summarise_usage

PAGE = Path(__file__).with_name("dashboard.html")
LOOPBACK = {"127.0.0.1", "localhost", "::1"}
RECENT_CALLS = 30
RECENT_EVENTS = 20
RECENT_CHECKS = 50
DAYS_SHOWN = 14
SHARE_TIMEOUT = 3.0  # seconds to wait for the network share before calling it unreachable


# --- reading the stores (never writing) ---------------------------------------------------------


def _read(target: Target, text: str, down: dict[str, str] | None = None) -> list[Any]:
    """Run one SELECT. SQLite is opened read-only; Postgres is told the whole session is read-only.

    `down` is shared by one refresh: a store that failed once is not tried again in that refresh, so a
    stopped database costs one short wait, not one per question.
    """
    key = str(target)
    if down is not None and key in down:
        raise ConnectionError(down[key])
    try:
        return _read_now(target, text)
    except Exception as exc:
        if down is not None:
            down[key] = f"{type(exc).__name__}: {exc}"[:200]
        raise


def _read_now(target: Target, text: str) -> list[Any]:
    if isinstance(target, PgTarget):
        if not _SCHEMA_NAME.match(target.schema):
            raise ValueError(f"not a usable Postgres schema name: {target.schema!r}")
        with psycopg.connect(
            host=target.host,
            port=target.port,
            dbname=target.dbname,
            user=target.user,
            password=target.password(),
            connect_timeout=2,
            options=f"-c default_transaction_read_only=on -c search_path={target.schema},public",
        ) as conn:
            return conn.execute(text).fetchall()
    if not target.is_file():
        return []  # a SQLite store is created by the first record: no file yet means no rows
    conn = sqlite3.connect(f"{target.resolve().as_uri()}?mode=ro", uri=True, timeout=5)
    try:
        return conn.execute(text).fetchall()
    finally:
        conn.close()


def _count(target: Target, table: str, down: dict[str, str] | None = None) -> int:
    rows = _read(target, f"SELECT COUNT(*) FROM {table}", down)
    return int(rows[0][0]) if rows else 0


def _store_label(target: Target | None) -> str:
    if target is None:
        return "off"
    return "Postgres" if isinstance(target, PgTarget) else "SQLite file"


MAX_EVENTS = 20000  # newest events read from a SQLite store, which cannot total in SQL here
RECENT_FETCH = 200  # newest events read from Postgres, for the "latest" lists: totals come from SQL


def load_events(
    settings: Settings, down: dict[str, str] | None = None
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """The events the page reports on, and where they came from.

    With a central audit store (Postgres when INGENUS_PG_HOST is set), the STORE is the source: it holds
    every server's events. If it cannot be read, the local log is shown instead and the page says so.
    """
    target = settings.audit_store
    if target is None:
        return load_records(settings.log_path), {
            "kind": "log",
            "label": f"Local log: {settings.log_path}",
            "note": "",
        }
    limit = RECENT_FETCH if isinstance(target, PgTarget) else MAX_EVENTS
    try:
        rows = _read(target, f"SELECT record FROM events ORDER BY ts DESC LIMIT {limit}", down)
    except Exception as exc:  # noqa: BLE001 - fall back, and say why
        return load_records(settings.log_path), {
            "kind": "log",
            "label": f"Local log: {settings.log_path}",
            "note": f"The central store ({_store_label(target)}) could not be read "
            f"({str(exc)[:100]}), so this is the local copy on this machine.",
        }
    records = [json.loads(r[0]) for r in reversed(rows)]  # oldest first, like the log
    note = ""
    if not isinstance(target, PgTarget) and len(rows) == limit:
        note = f"Totals cover only the newest {limit:,} events (this store is a SQLite file)."
    return records, {"kind": "store", "label": f"Central store: {target}", "note": note}


# --- the four sections --------------------------------------------------------------------------


def _percentile(values: list[int], pct: float) -> int:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * pct))]


def activity(records: list[dict[str, Any]]) -> dict[str, Any]:
    calls = [r for r in records if r.get("event", "tool_call") == "tool_call"]
    usage = summarise_usage(records)
    by_tool: dict[str, list[dict[str, Any]]] = {}
    for r in calls:
        by_tool.setdefault(r["tool"], []).append(r)
    tools = []
    for name, rows in by_tool.items():
        times = [r["duration_ms"] for r in rows if isinstance(r.get("duration_ms"), int)]
        tools.append(
            {
                "tool": name,
                "calls": len(rows),
                "errors": sum(1 for r in rows if r.get("error")),
                "incomplete": sum(1 for r in rows if (r.get("not_checked_count") or 0) > 0),
                "avg_ms": round(sum(times) / len(times)) if times else None,
                "p95_ms": _percentile(times, 0.95) if times else None,
                "max_ms": max(times) if times else None,
            }
        )
    tools.sort(key=lambda t: -t["calls"])
    per_day = usage["calls_per_day"]
    days = list(per_day)[-DAYS_SHOWN:]
    errors_per_day = {d: 0 for d in days}
    for r in calls:
        if r.get("error") and r["ts"][:10] in errors_per_day:
            errors_per_day[r["ts"][:10]] += 1
    recent = [
        {
            "ts": r["ts"],
            "user": r.get("user"),
            "tool": r["tool"],
            "customer": (r.get("args") or {}).get("customer") or (r.get("args") or {}).get("name"),
            "ms": r.get("duration_ms"),
            "not_checked": r.get("not_checked_count"),
            "error": (r.get("error") or "")[:160] or None,
        }
        for r in calls[-RECENT_CALLS:][::-1]
    ]
    return {
        "total_calls": usage["total_calls"],
        "users": usage["distinct_users"],
        "returning_users": len(usage["returning_users"]),
        "errors": usage["calls_with_errors"],
        "incomplete_calls": sum(1 for r in calls if (r.get("not_checked_count") or 0) > 0),
        "logins_accepted": usage["logins_accepted"],
        "logins_refused": usage["logins_refused"],
        "per_day": [{"day": d, "calls": per_day[d], "errors": errors_per_day[d]} for d in days],
        "per_user": [{"user": u, "calls": n} for u, n in usage["calls_per_user"].items()],
        "tools": tools,
        "recent": recent,
    }


_ERR = "(record::json->>'error') IS NOT NULL"
_INCOMPLETE = "COALESCE((record::json->>'not_checked_count')::int, 0) > 0"
_MS = "(record::json->>'duration_ms')::int"


def activity_from_postgres(
    target: PgTarget, recent: list[dict[str, Any]], down: dict[str, str] | None = None
) -> dict[str, Any]:
    """The same figures as `activity`, but totalled by Postgres over EVERY event, not a recent slice."""
    calls = "FROM events WHERE event = 'tool_call'"
    total, users, errors, incomplete = _read(
        target,
        f'SELECT COUNT(*), COUNT(DISTINCT "user"), COUNT(*) FILTER (WHERE {_ERR}),'
        f" COUNT(*) FILTER (WHERE {_INCOMPLETE}) {calls}",
        down,
    )[0]
    returning = _read(
        target,
        f'SELECT COUNT(*) FROM (SELECT 1 {calls} GROUP BY "user"'
        " HAVING COUNT(DISTINCT substr(ts, 1, 10)) > 1) x",
        down,
    )[0][0]
    days = _read(
        target,
        f"SELECT substr(ts, 1, 10) d, COUNT(*), COUNT(*) FILTER (WHERE {_ERR}) {calls}"
        f" GROUP BY d ORDER BY d DESC LIMIT {DAYS_SHOWN}",
        down,
    )
    per_user = _read(
        target,
        f"SELECT COALESCE(\"user\", '?'), COUNT(*) {calls} GROUP BY 1 ORDER BY 2 DESC LIMIT 20",
        down,
    )
    tool_rows = _read(
        target,
        f"SELECT tool, COUNT(*), COUNT(*) FILTER (WHERE {_ERR}), COUNT(*) FILTER (WHERE {_INCOMPLETE}),"
        f" avg({_MS}), percentile_disc(0.95) WITHIN GROUP (ORDER BY {_MS}), max({_MS})"
        f" {calls} GROUP BY tool ORDER BY 2 DESC",
        down,
    )
    logins = dict(
        _read(target, "SELECT outcome, COUNT(*) FROM events WHERE event = 'login' GROUP BY 1", down)
    )
    shown = activity(recent)  # the latest-calls list is built from the newest events
    return {
        "total_calls": total,
        "users": users,
        "returning_users": returning,
        "errors": errors,
        "incomplete_calls": incomplete,
        "logins_accepted": logins.get("accepted", 0),
        "logins_refused": logins.get("refused", 0),
        "per_day": [{"day": d, "calls": n, "errors": e} for d, n, e in reversed(days)],
        "per_user": [{"user": u, "calls": n} for u, n in per_user],
        "tools": [
            {
                "tool": t,
                "calls": n,
                "errors": e,
                "incomplete": i,
                "avg_ms": None if a is None else round(float(a)),
                "p95_ms": p,
                "max_ms": m,
            }
            for t, n, e, i, a, p, m in tool_rows
        ],
        "recent": shown["recent"],
    }


def checks(settings: Settings, down: dict[str, str] | None = None) -> dict[str, Any]:
    target = settings.history_db
    if target is None:
        return {"enabled": False, "note": "Check history is switched off on this server."}
    rows = _read(
        target,
        'SELECT check_id, ts, "user", customer_id, as_of, total_gap, total_exposure, not_checked,'
        f" lines FROM checks ORDER BY ts DESC LIMIT {RECENT_CHECKS}",
        down,
    )
    docs: dict[str, list[str]] = {}
    for check_id, document_id in _read(
        target, "SELECT check_id, document_id FROM check_docs ORDER BY document_id", down
    ):
        docs.setdefault(check_id, []).append(document_id)
    out = []
    for check_id, ts, who, customer, as_of, gap, exposure, not_checked, lines in rows:
        out.append(
            {
                "when": ts,
                "who": who,
                "customer_id": customer,
                "as_of": as_of,
                "gap": gap,
                "exposure": exposure,
                "not_checked": not_checked,
                "lines": json.loads(lines),
                "documents": docs.get(check_id, []),
            }
        )
    return {"enabled": True, "store": _store_label(target), "checks": out}


def audit(
    settings: Settings, records: list[dict[str, Any]], down: dict[str, str] | None = None
) -> dict[str, Any]:
    path = settings.log_path
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    chain = calllog.verify_chain(lines)
    has_log = path.is_file()  # without a log there is nothing to verify: never call that "intact"
    recent = [
        {
            "ts": r.get("ts"),
            "event": r.get("event", "tool_call"),
            "user": r.get("user"),
            "what": r.get("tool") or r.get("outcome"),
            "detail": r.get("reason") or r.get("error"),
            "hash": (r.get("hash") or "")[:12] or None,
        }
        for r in records[-RECENT_EVENTS:][::-1]
    ]
    out: dict[str, Any] = {
        "chain_ok": chain.ok if has_log else None,
        "chain_problem": chain.problem if has_log else "there is no local log on this machine",
        "chained": chain.hashed,
        "legacy": chain.legacy,
        "events_in_log": len([line for line in lines if line.strip()]) if has_log else None,
        "last_hash": next((r["hash"] for r in reversed(records) if r.get("hash")), None),
        "recent": recent,
        "store": _store_label(settings.audit_store),
        "events_in_store": None,
        "store_error": None,
    }
    if settings.audit_store is not None:
        try:
            out["events_in_store"] = _count(settings.audit_store, "events", down)
        except Exception as exc:  # noqa: BLE001 - the chain below is still worth showing
            out["store_error"] = type(exc).__name__
    return out


def _share_reachable(root: Path) -> bool:
    answer: list[bool] = []
    thread = threading.Thread(target=lambda: answer.append(root.is_dir()), daemon=True)
    thread.start()
    thread.join(SHARE_TIMEOUT)
    return bool(answer and answer[0])


def _row(name: str, status: str, detail: str) -> dict[str, str]:
    return {"name": name, "status": status, "detail": detail}  # status: ok, warn, off or info


def health(
    settings: Settings,
    records: list[dict[str, Any]],
    audit_part: dict[str, Any],
    down: dict[str, str] | None = None,
) -> dict[str, Any]:
    rows: list[dict[str, str]] = []
    log = settings.log_path
    if log.is_file():
        last = records[-1]["ts"] if records else None
        rows.append(
            _row(
                "Tool-call log", "ok", f"{log.stat().st_size:,} bytes; last event {last or 'none'}"
            )
        )
    else:
        rows.append(
            _row(
                "Tool-call log",
                "info" if settings.audit_store else "warn",
                f"No local log at {log}",
            )
        )
    if audit_part["chain_ok"] is None:
        rows.append(_row("Audit hash chain", "info", f"Not checked: {audit_part['chain_problem']}"))
    elif audit_part["chain_ok"]:
        rows.append(
            _row("Audit hash chain", "ok", f"{audit_part['chained']} events chained, none altered")
        )
    else:
        rows.append(_row("Audit hash chain", "warn", f"BROKEN: {audit_part['chain_problem']}"))
    for label, target in (
        ("Audit store", settings.audit_store),
        ("Check history", settings.history_db),
    ):
        if target is None:
            rows.append(_row(label, "off", "Switched off"))
            continue
        try:
            table = "events" if label == "Audit store" else "checks"
            count = _count(target, table, down)
            rows.append(_row(label, "ok", f"{_store_label(target)} reachable; {count} row(s)"))
        except Exception as exc:  # noqa: BLE001 - any failure is a health finding, not a crash
            rows.append(
                _row(label, "warn", f"{_store_label(target)} not reachable: {str(exc)[:90]}")
            )
    rows.append(
        _row(
            "Stored contract terms",
            "ok" if settings.records_db is not None else "off",
            _store_label(settings.records_db),
        )
    )
    kinds = settings.sources or (settings.doc_source,)
    for kind in kinds:
        if kind in {"sharepoint", "onedrive"}:
            rows.append(
                _row(
                    {"sharepoint": "SharePoint", "onedrive": "OneDrive"}[kind],
                    "info",
                    "Read as each signed-in person, so it cannot be tested from here",
                )
            )
        elif kind == "network" and settings.network_root is not None:
            ok = _share_reachable(settings.network_root)
            rows.append(
                _row(
                    "Network share",
                    "ok" if ok else "warn",
                    "Reachable" if ok else "Not reachable from this machine",
                )
            )
        else:
            rows.append(
                _row(
                    kind.capitalize(),
                    "ok" if settings.contracts_dir.is_dir() else "warn",
                    str(settings.contracts_dir),
                )
            )
    guidance = settings.guidance_dir
    rows.append(
        _row(
            "Guidance",
            "ok" if guidance.is_dir() else "warn",
            f"Version {guidance.name} served by default",
        )
    )
    if settings.embed_model:
        present = settings.embed_dir.is_dir()
        rows.append(
            _row(
                "Meaning search",
                "ok" if present else "warn",
                f"Model {settings.embed_model}" + ("" if present else "; model folder not found"),
            )
        )
    else:
        rows.append(_row("Meaning search", "off", "Switched off (keyword search only)"))
    rows.append(
        _row("Sign-in", "ok" if settings.auth_mode == "entra" else "info", settings.auth_mode)
    )
    rows.append(_row("Retention", "info", f"{settings.retention_days} days"))
    return {"rows": rows, "version": __version__}


def snapshot(settings: Settings) -> dict[str, Any]:
    """Everything the page shows. A section that fails reports its error and leaves the rest intact."""
    down: dict[str, str] = {}  # stores that failed in this refresh (see _read)
    records, source = load_events(settings, down)
    out: dict[str, Any] = {
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "log_path": str(settings.log_path),
        "source": source,
    }
    parts = {
        "activity": lambda: (
            activity_from_postgres(settings.audit_store, records, down)
            if source["kind"] == "store" and isinstance(settings.audit_store, PgTarget)
            else activity(records)
        ),
        "checks": lambda: checks(settings, down),
        "audit": lambda: audit(settings, records, down),
    }
    for name, build in parts.items():
        try:
            out[name] = build()
        except Exception as exc:  # noqa: BLE001
            out[name] = {"error": f"{type(exc).__name__}: {exc}"[:240]}
    try:
        audit_part = (
            out["audit"]
            if "error" not in out["audit"]
            else {"chain_ok": None, "chain_problem": "the audit section failed", "chained": 0}
        )
        out["health"] = health(settings, records, audit_part, down)
    except Exception as exc:  # noqa: BLE001
        out["health"] = {"error": f"{type(exc).__name__}: {exc}"[:240]}
    return out


# --- serving ------------------------------------------------------------------------------------


class Handler(BaseHTTPRequestHandler):
    settings: Settings

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - keep the console quiet
        return

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'",
        )
        self.end_headers()
        self.wfile.write(body)

    def _host_ok(self) -> bool:
        # Refuses a page opened under a name that is not this machine (guards against DNS rebinding).
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
        return host in LOOPBACK

    def do_GET(self) -> None:  # noqa: N802 - the name http.server looks for
        if not self._host_ok():
            self._send(403, b"Forbidden", "text/plain; charset=utf-8")
            return
        path = urlsplit(self.path).path
        if path == "/":
            self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
        elif path == "/api/snapshot":
            body = json.dumps(snapshot(self.settings), ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
        else:
            self._send(404, b"Not found", "text/plain; charset=utf-8")


def make_server(
    settings: Settings, host: str = "127.0.0.1", port: int = 8766
) -> ThreadingHTTPServer:
    if host not in LOOPBACK:
        raise SystemExit(
            f"Refusing to listen on {host}: this page shows every person's calls and checks, "
            "so it is for this machine only."
        )
    handler = type("BoundHandler", (Handler,), {"settings": settings})
    return ThreadingHTTPServer((host, port), handler)


def main(argv: list[str] | None = None) -> None:
    load_env_file()
    settings = load_settings()
    parser = argparse.ArgumentParser(prog="python -m ingenus_mcp.dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args(argv)
    server = make_server(settings, args.host, args.port)
    print(
        f"Operator dashboard (read-only) at http://{args.host}:{server.server_address[1]}/  Ctrl+C to stop"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
