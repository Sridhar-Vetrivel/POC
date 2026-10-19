"""Read SAP data through the adapter interface. Read-only by construction."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from ingenus_mcp.core.config import Settings
from ingenus_mcp.core.models import (
    MonthlyVolume,
    NotChecked,
    RebateSetupResult,
    SalesVolumeResult,
    SetupLine,
)
from mcp_servers.sap.adapters.mock import MockSapReader
from mcp_servers.sap.adapters.real_stub import RealSapReader
from mcp_servers.sap.interface import ReadQuery, SapReader

_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def get_reader(settings: Settings) -> SapReader:
    if settings.sap_adapter == "mock":
        return MockSapReader(settings.sap_mock_file)
    if settings.sap_adapter == "real":
        return (
            RealSapReader()
        )  # raises NotImplementedError on read: route not decided (TODO(verify))
    raise ValueError(f"Unknown SAP adapter '{settings.sap_adapter}'. Use 'mock' for now.")


def customer_exists(reader: SapReader, customer_id: str) -> bool:
    result = reader.read(ReadQuery(entity="customers", filters={"customer_id": customer_id}))
    return bool(result.rows)


def rebate_setup(reader: SapReader, customer_id: str, as_of: date) -> RebateSetupResult:
    if not customer_exists(reader, customer_id):
        return RebateSetupResult(
            customer_id=customer_id,
            as_of=as_of,
            lines=[],
            source="unavailable",
            not_checked=[NotChecked(item=customer_id, reason="Customer id not found in SAP.")],
        )
    result = reader.read(
        ReadQuery(entity="rebate_setup", filters={"customer_id": customer_id}, as_of=as_of)
    )
    lines = [
        SetupLine(
            kind=r["kind"],
            product=r.get("product"),
            rate_pct=Decimal(r["rate_pct"]),
            basis=r["basis"],
            valid_from=date.fromisoformat(r["valid_from"]) if r.get("valid_from") else None,
            valid_to=date.fromisoformat(r["valid_to"]) if r.get("valid_to") else None,
        )
        for r in result.rows
    ]
    lines.sort(key=lambda x: (x.kind, x.product or ""))
    return RebateSetupResult(
        customer_id=customer_id,
        as_of=as_of,
        lines=lines,
        source=result.source,
        not_checked=[]
        if lines
        else [NotChecked(item=customer_id, reason="No setup lines valid on that date.")],
    )


def sales_volume(
    reader: SapReader, customer_id: str, period_start: str, period_end: str
) -> SalesVolumeResult:
    for label, value in (("period_start", period_start), ("period_end", period_end)):
        if not _MONTH.match(value):
            raise ValueError(f"{label} must be a month like 2026-07, got '{value}'.")
    if period_start > period_end:
        raise ValueError("period_start is after period_end.")
    if not customer_exists(reader, customer_id):
        return SalesVolumeResult(
            customer_id=customer_id,
            period_start=period_start,
            period_end=period_end,
            rows=[],
            source="unavailable",
            not_checked=[NotChecked(item=customer_id, reason="Customer id not found in SAP.")],
        )
    result = reader.read(
        ReadQuery(
            entity="sales_volume",
            filters={"customer_id": customer_id},
            period_start=period_start,
            period_end=period_end,
        )
    )
    rows = sorted(
        (
            MonthlyVolume(month=r["month"], product=r["product"], net_sales=Decimal(r["net_sales"]))
            for r in result.rows
        ),
        key=lambda x: (x.month, x.product),
    )
    return SalesVolumeResult(
        customer_id=customer_id,
        period_start=period_start,
        period_end=period_end,
        rows=rows,
        source=result.source,
        not_checked=[]
        if rows
        else [NotChecked(item=customer_id, reason="No sales rows in that period.")],
    )
