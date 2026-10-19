"""Tool: get_rebate_setup. Discovered at start-up by ingenus_mcp.tools.discover()."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from pydantic import Field

from ingenus_mcp.core import sap as sap_access
from ingenus_mcp.core.config import load_settings
from ingenus_mcp.core.models import (
    RebateSetupResult,
)
from ingenus_mcp.core.registry import tool


@tool(read_only=True)
def get_rebate_setup(
    customer_id: Annotated[str, Field(description="SAP customer id from resolve_customer.")],
    as_of: Annotated[date, Field(description="Date to read the setup for (YYYY-MM-DD).")],
) -> RebateSetupResult:
    """Read the rebate and admin-fee setup currently in SAP for one customer, as at a date.

    Use this to see what SAP has set up. Returns one line per rebate (per product) and per fee, with
    rate and basis. Read-only: this tool cannot change anything in SAP. Do not use it to guess what a
    contract says.
    """
    settings = load_settings()
    return sap_access.rebate_setup(sap_access.get_reader(settings), customer_id, as_of)
