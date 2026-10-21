"""Tool-call log: one JSON line per call. This is the only module allowed to write files.

It records who called which tool, with what arguments, and a short summary of the result. It never
stores whole documents or page text. The log is also the adoption measure (see report.py).
Never print to stdout here: on stdio, stdout is the protocol channel.
"""

from __future__ import annotations

import getpass
import json
import os
import sys
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from pydantic_core import to_jsonable_python

from ingenus_mcp import __version__
from ingenus_mcp.core import auth

_LOCK = threading.Lock()
_SESSION = uuid.uuid4().hex[:8]
MAX_STR = 300
MAX_ITEMS = 20


def current_user() -> str:
    signed_in = auth.current_user_name()  # V1-4: the person behind the request, from their token
    if signed_in:
        return signed_in
    override = os.environ.get("INGENUS_USER")
    if override:
        return override
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001 - no user name available; the log still works
        return "unknown"


def _trim(value: Any) -> Any:
    if isinstance(value, str):
        return (
            value
            if len(value) <= MAX_STR
            else value[:MAX_STR] + f"...[+{len(value) - MAX_STR} chars]"
        )
    if isinstance(value, list):
        items = [_trim(v) for v in value[:MAX_ITEMS]]
        if len(value) > MAX_ITEMS:
            items.append(f"...[+{len(value) - MAX_ITEMS} more]")
        return items
    if isinstance(value, dict):
        return {k: _trim(v) for k, v in value.items()}
    return value


def clean_args(args: dict[str, Any]) -> dict[str, Any]:
    return _trim(to_jsonable_python(args))


def summarise(result: Any) -> dict[str, Any]:
    """Counts and short identifiers only. Lists become lengths; long text is dropped."""
    if not isinstance(result, BaseModel):
        return {"type": type(result).__name__}
    out: dict[str, Any] = {"type": type(result).__name__}
    for name, value in result:
        if isinstance(value, list):
            out[f"{name}_count"] = len(value)
        elif isinstance(value, (int, float, bool)) or value is None:
            out[name] = value
        elif isinstance(value, str):
            if len(value) <= 80:
                out[name] = value
        elif isinstance(value, BaseModel):
            out[name] = "present"
        else:
            text = str(value)
            if len(text) <= 80:
                out[name] = text
    return out


def write_record(path: Path, record: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        with _LOCK, path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError as exc:
        print(f"[ingenus_mcp] could not write the tool-call log: {exc}", file=sys.stderr)


def build_record(
    tool: str,
    args: dict[str, Any],
    result: Any,
    duration_ms: int,
    error: str | None,
) -> dict[str, Any]:
    not_checked = getattr(result, "not_checked", None)
    return {
        "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
        "user": current_user(),
        "session": _SESSION,
        "plugin_version": __version__,
        "tool": tool,
        "args": clean_args(args),
        "result": summarise(result) if error is None else None,
        "not_checked_count": len(not_checked) if isinstance(not_checked, list) else None,
        "duration_ms": duration_ms,
        "error": error,
    }
