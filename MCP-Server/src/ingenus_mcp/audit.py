"""Audit commands: check the log's hash chain, copy it to the central store, search the store.

    python -m ingenus_mcp.audit verify [--log PATH]
    python -m ingenus_mcp.audit ship   [--log PATH] [--store PATH]
    python -m ingenus_mcp.audit prune  [--days N] [--store PATH] [--history PATH]
    python -m ingenus_mcp.audit query  [--store PATH] [--user NAME] [--tool NAME] [--event tool_call|login]
                                       [--since ISO_TIME] [--limit N]

`verify` shows whether any line of the log was edited, removed or reordered. It cannot see lines cut off
the END of the file (nothing later points back at them); keep a copy of the last hash somewhere else for
that. Reads the log and the store only, except `ship` (adds missing events to the store) and `prune`
(deletes events and check records older than N days, default INGENUS_RETENTION_DAYS = 365, from the
store and the history; the local log is never touched). With Postgres configured (INGENUS_PG_HOST) the
store and the history are the Postgres database and --store/--history are not needed.
Prints to stdout (this is a command, not the MCP server).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ingenus_mcp.core import auditstore, calllog, history
from ingenus_mcp.core.config import load_env_file, load_settings


def main(argv: list[str] | None = None) -> int:
    load_env_file()
    settings = load_settings()
    parser = argparse.ArgumentParser(prog="python -m ingenus_mcp.audit")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("verify", "ship", "query", "prune"):
        p = sub.add_parser(name)
        if name in {"verify", "ship"}:
            p.add_argument("--log", type=Path, default=settings.log_path)
        if name in {"ship", "query", "prune"}:
            p.add_argument("--store", type=Path, default=settings.audit_store)
        if name == "prune":
            p.add_argument("--history", type=Path, default=settings.history_db)
            p.add_argument("--days", type=int, default=settings.retention_days)
        if name == "query":
            p.add_argument("--user")
            p.add_argument("--tool")
            p.add_argument("--event")
            p.add_argument("--since")
            p.add_argument("--limit", type=int, default=20)
    args = parser.parse_args(argv)

    if args.command == "verify":
        if not args.log.is_file():
            print(f"No log at {args.log}")
            return 1
        report = calllog.verify_chain(args.log.read_text(encoding="utf-8").splitlines())
        print(f"Log: {args.log}")
        print(f"Events: {report.hashed} chained, {report.legacy} from before the chain existed")
        print("Chain: OK" if report.ok else f"Chain: BROKEN. {report.problem}")
        return 0 if report.ok else 2

    if args.command == "prune":
        if args.days < 1:
            print("--days must be at least 1.", file=sys.stderr)
            return 1
        before = (datetime.now(UTC) - timedelta(days=args.days)).isoformat(timespec="milliseconds")
        pruned = False
        if args.store is not None:
            print(
                f"Deleted {auditstore.prune(args.store, before)} event(s) older than {args.days} days from {args.store}."
            )
            pruned = True
        if args.history is not None:
            print(
                f"Deleted {history.prune(args.history, before)} check record(s) older than {args.days} days from {args.history}."
            )
            pruned = True
        if not pruned:
            print("Nothing to prune: no audit store and no history are set.", file=sys.stderr)
            return 1
        return 0

    if args.store is None:
        print(
            "No central store is set. Give --store PATH or set INGENUS_AUDIT_STORE.",
            file=sys.stderr,
        )
        return 1

    if args.command == "ship":
        copied, already = auditstore.ship(args.log, args.store)
        print(f"Copied {copied} event(s) to {args.store}; {already} were already there.")
        return 0

    for record in auditstore.query(
        args.store,
        user=args.user,
        tool=args.tool,
        event=args.event,
        since=args.since,
        limit=args.limit,
    ):
        print(json.dumps(record, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
