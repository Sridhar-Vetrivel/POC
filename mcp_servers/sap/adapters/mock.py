"""Mock SAP adapter. Reads a JSON file of SYNTHETIC records; never talks to any real system."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from mcp_servers.sap.interface import ReadQuery, ReadResult

SOURCE = "mock adapter (synthetic data, not Ingenus data)"


class MockSapReader:
    def __init__(self, data_file: Path) -> None:
        self._file = Path(data_file)
        raw = json.loads(self._file.read_text(encoding="utf-8"))
        if "SYNTHETIC" not in str(raw.get("_label", "")).upper():
            raise ValueError("Mock SAP data must carry a _label that says SYNTHETIC.")
        self._tables: dict[str, list[dict[str, Any]]] = {
            k: v for k, v in raw.items() if not k.startswith("_")
        }

    def read(self, query: ReadQuery) -> ReadResult:
        if query.entity not in self._tables:
            return ReadResult(
                rows=[], source=SOURCE, notes=[f"Unknown entity '{query.entity}' in the mock data."]
            )
        rows = [dict(r) for r in self._tables[query.entity]]
        for key, value in query.filters.items():
            rows = [r for r in rows if str(r.get(key)) == value]
        if query.as_of is not None:
            rows = [r for r in rows if _valid_on(r, query.as_of)]
        if query.period_start or query.period_end:
            rows = [r for r in rows if _in_period(r, query.period_start, query.period_end)]
        return ReadResult(rows=rows, source=SOURCE)


def _valid_on(row: dict[str, Any], day: date) -> bool:
    start = row.get("valid_from")
    end = row.get("valid_to")
    if start and date.fromisoformat(start) > day:
        return False
    return not (end and date.fromisoformat(end) < day)


def _in_period(row: dict[str, Any], start: str | None, end: str | None) -> bool:
    month = row.get("month")
    if month is None:
        return True
    return not ((start and month < start) or (end and month > end))
