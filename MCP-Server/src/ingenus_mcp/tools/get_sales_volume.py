"""Tool: get_sales_volume. Discovered at start-up by ingenus_mcp.tools.discover()."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from ingenus_mcp.core import sap as sap_access
from ingenus_mcp.core.config import load_settings
from ingenus_mcp.core.models import (
    SalesVolumeResult,
)
from ingenus_mcp.core.registry import tool


@tool(read_only=True)
def get_sales_volume(
    customer_id: Annotated[str, Field(description="SAP customer id from resolve_customer.")],
    period_start: Annotated[str, Field(description="First month, YYYY-MM.")],
    period_end: Annotated[str, Field(description="Last month, YYYY-MM.")],
) -> SalesVolumeResult:
    """Read monthly net sales by product from SAP for one customer.

    Use this when the user asks for the sales behind an exposure figure. compare_contract_to_sap
    reads sales itself, so you do not need this tool for a comparison. Read-only.
    """
    settings = load_settings()
    return sap_access.sales_volume(
        sap_access.get_reader(settings), customer_id, period_start, period_end
    )
