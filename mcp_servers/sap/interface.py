"""The one interface every SAP adapter implements.

It has a single method, ``read``, so no adapter can offer a way to create, change or delete
anything. What an "entity" is, and which filters it supports, is decided by the caller and the
adapter. This file stays free of business terms so it can serve any slice.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class ReadQuery(BaseModel):
    """A read-only request."""

    entity: str = Field(description="Which kind of record to read; a name the adapter understands.")
    filters: dict[str, str] = Field(default_factory=dict, description="Exact-match filters.")
    as_of: date | None = Field(
        default=None,
        description="Return only rows valid on this date (rows that carry validity dates).",
    )
    period_start: str | None = Field(default=None, description="First month, YYYY-MM (inclusive).")
    period_end: str | None = Field(default=None, description="Last month, YYYY-MM (inclusive).")


class ReadResult(BaseModel):
    rows: list[dict[str, Any]]
    source: str = Field(
        description="Where the rows came from, e.g. 'mock adapter (synthetic data)'."
    )
    notes: list[str] = Field(default_factory=list, description="Anything the caller should know.")


@runtime_checkable
class SapReader(Protocol):
    """Read-only. Do not add write-style methods; a test fails if one appears."""

    def read(self, query: ReadQuery) -> ReadResult: ...
