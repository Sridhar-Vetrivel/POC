"""Tool-call log: one JSON line per call. This is the only module allowed to write files.

It records who called which tool, with what arguments, and a short summary of the result. It never
stores whole documents or page text. The log is also the adoption measure (see report.py).
Never print to stdout here: on stdio, stdout is the protocol channel.
"""

from __future__ import annotations

import getpass
import hashlib
import json
import os
import sys
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NamedTuple

from pydantic import BaseModel
from pydantic_core import to_jsonable_python

from ingenus_mcp import __version__
from ingenus_mcp.core import auditstore, auth

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


GENESIS = "0" * 64


@contextmanager
def _file_lock(path: Path) -> Iterator[None]:
    """Hold an exclusive lock on `<log>.lock`, so that only one PROCESS appends at a time.

    The threads of one process are already serialised by `_LOCK`. The lock file is a separate empty file
    (the log itself is opened and appended to, and a byte-range lock on it would block readers on Windows).
    """
    with path.with_name(path.name + ".lock").open("a+b") as handle:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)  # waits, retrying for about 10 s
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _canonical(record: dict[str, Any]) -> str:
    return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def chain_hash(record: dict[str, Any]) -> str:
    """Hash of an event, over everything except its own `hash` (so prev_hash is covered)."""
    body = {k: v for k, v in record.items() if k != "hash"}
    return hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()


def _last_hash(path: Path) -> str:
    if not path.is_file():
        return GENESIS
    with path.open("rb") as handle:
        handle.seek(max(0, path.stat().st_size - 65536))
        lines = handle.read().decode("utf-8", errors="replace").splitlines()
    for line in reversed(lines):
        if line.strip():
            try:
                return str(json.loads(line).get("hash") or GENESIS)
            except json.JSONDecodeError:
                return GENESIS
    return GENESIS


class ChainReport(NamedTuple):
    ok: bool
    hashed: int  # events that carry a hash
    legacy: int  # events from before the chain existed (not covered)
    problem: str | None


def verify_chain(lines: list[str]) -> ChainReport:
    """Check a log: every hashed event must hash to its own `hash` and point at the one before."""
    hashed = legacy = 0
    previous = GENESIS
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            return ChainReport(
                False, hashed, legacy, f"line {number} is not valid JSON (cut off or edited)"
            )
        if "hash" not in record:
            if hashed:
                return ChainReport(
                    False, hashed, legacy, f"line {number} has no hash after chained events"
                )
            legacy += 1
            continue
        if record.get("prev_hash") != previous:
            return ChainReport(
                False,
                hashed,
                legacy,
                f"line {number}: an event before it was removed, reordered or changed",
            )
        if chain_hash(record) != record["hash"]:
            return ChainReport(False, hashed, legacy, f"line {number} was edited")
        previous = record["hash"]
        hashed += 1
    return ChainReport(True, hashed, legacy, None)


def make_event(event: str, **fields: Any) -> dict[str, Any]:
    """The common part of a non-tool event (for example a login): time, kind, session, version."""
    return {
        "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
        "event": event,
        "session": _SESSION,
        "plugin_version": __version__,
        **fields,
    }


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


def write_record(path: Path, record: dict[str, Any], store: Path | None = None) -> None:
    """Append one event to the log with its place in the hash chain, then copy it to the central
    store if there is one. The log comes first: it is the source of truth and the local buffer.
    Several threads and several server processes may write one log: a lock file serialises the processes,
    and the previous hash is read from the log itself under that lock, so the chain cannot fork.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with _LOCK, _file_lock(path):
            previous = _last_hash(path)
            record = {
                **record,
                "event": record.get("event", "tool_call"),
                "event_id": record.get("event_id") or uuid.uuid4().hex,
                "prev_hash": previous,
            }
            record["hash"] = chain_hash(record)
            line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
    except OSError as exc:
        print(f"[ingenus_mcp] could not write the tool-call log: {exc}", file=sys.stderr)
        return
    auditstore.emit(store, record)


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
        "event": "tool_call",
        "user": current_user(),
        "user_id": auth.current_user_id(),
        "session": _SESSION,
        "plugin_version": __version__,
        "tool": tool,
        "args": clean_args(args),
        "result": summarise(result) if error is None else None,
        "not_checked_count": len(not_checked) if isinstance(not_checked, list) else None,
        "duration_ms": duration_ms,
        "error": error,
    }
