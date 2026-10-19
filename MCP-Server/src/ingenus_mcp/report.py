"""Usage report from the tool-call log: the adoption measure.

    python -m ingenus_mcp.report [--log PATH] [--json]

Counts calls per user, per tool and per day, and how many users came back on more than one day.
Reads the log only. Prints to stdout (this is a command, not the MCP server).
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ingenus_mcp.core.config import load_settings


def load_records(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # a half-written line must not break the report
    return records


def summarise_usage(records: list[dict[str, Any]]) -> dict[str, Any]:
    per_tool: Counter[str] = Counter(r["tool"] for r in records)
    per_user: Counter[str] = Counter(r["user"] for r in records)
    per_day: Counter[str] = Counter(r["ts"][:10] for r in records)
    days_by_user: dict[str, set[str]] = defaultdict(set)
    for r in records:
        days_by_user[r["user"]].add(r["ts"][:10])
    errors = sum(1 for r in records if r.get("error"))
    not_checked = sum(r.get("not_checked_count") or 0 for r in records)
    return {
        "total_calls": len(records),
        "distinct_users": len(per_user),
        "returning_users": sorted(u for u, d in days_by_user.items() if len(d) > 1),
        "calls_per_tool": dict(per_tool.most_common()),
        "calls_per_user": dict(per_user.most_common()),
        "calls_per_day": dict(sorted(per_day.items())),
        "calls_with_errors": errors,
        "items_reported_not_checked": not_checked,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Usage report from the tool-call log.")
    parser.add_argument("--log", type=Path, default=None, help="Path to the JSONL log.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of text.")
    args = parser.parse_args()
    path = args.log or load_settings().log_path
    summary = summarise_usage(load_records(path))
    if args.json:
        print(json.dumps(summary, indent=2))
        return
    print(f"Log: {path}")
    print(f"Total calls: {summary['total_calls']}   Distinct users: {summary['distinct_users']}")
    print(f"Returning users (more than one day): {', '.join(summary['returning_users']) or 'none'}")
    for title, key in (
        ("Per tool", "calls_per_tool"),
        ("Per user", "calls_per_user"),
        ("Per day", "calls_per_day"),
    ):
        print(f"\n{title}:")
        for name, count in summary[key].items():
            print(f"  {name:32} {count}")
    print(f"\nCalls with errors: {summary['calls_with_errors']}")
    print(f"Items reported as not checked: {summary['items_reported_not_checked']}")


if __name__ == "__main__":
    main()
