"""Tool registry. Every tool is registered here, read-only, and every call is logged.

There is no way to register a tool that is not read-only: ``tool(read_only=False)`` raises.
A test also scans the code for write operations outside calllog.py.
"""

from __future__ import annotations

import functools
import inspect
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ingenus_mcp.core import calllog
from ingenus_mcp.core.config import load_settings


class WriteToolNotAllowed(RuntimeError):
    """Phase 1 has no write tools. SAP is read-only and files go only to the set locations."""


@dataclass(frozen=True)
class ToolSpec:
    name: str
    func: Callable[..., Any]
    read_only: bool
    description: str


TOOLS: dict[str, ToolSpec] = {}


def tool(*, read_only: bool) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    if read_only is not True:
        raise WriteToolNotAllowed("Every tool must be read-only (CLAUDE.md rule 4).")

    def decorate(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            bound = inspect.signature(func).bind(*args, **kwargs)
            call_args = dict(bound.arguments)
            started = time.perf_counter()
            result: Any = None
            error: str | None = None
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                raise
            finally:
                record = calllog.build_record(
                    func.__name__,
                    call_args,
                    result,
                    int((time.perf_counter() - started) * 1000),
                    error,
                )
                settings = load_settings()
                calllog.write_record(settings.log_path, record, settings.audit_store)

        TOOLS[func.__name__] = ToolSpec(
            name=func.__name__,
            func=wrapper,
            read_only=True,
            description=(func.__doc__ or "").strip(),
        )
        return wrapper

    return decorate
