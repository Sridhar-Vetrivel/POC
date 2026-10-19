"""Tool: resolve_customer. Discovered at start-up by ingenus_mcp.tools.discover()."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from ingenus_mcp.core import customers
from ingenus_mcp.core import sap as sap_access
from ingenus_mcp.core.config import load_settings
from ingenus_mcp.core.models import (
    ResolveCustomerResult,
)
from ingenus_mcp.core.registry import tool


@tool(read_only=True)
def resolve_customer(
    name: Annotated[
        str, Field(description="Customer name or alias as the user wrote it, e.g. 'Chain X'.")
    ],
) -> ResolveCustomerResult:
    """Map a customer name to its SAP customer id. Use this first, before any other tool needs an id.

    Returns the matched customer, or a list of candidates when the name is ambiguous or only similar.
    If `resolved` is null, ask the user which customer they mean. Never pick one yourself.
    Read-only. Does not create or change anything.
    """
    settings = load_settings()
    result = customers.resolve(name, settings.customers_file)
    if result.resolved:
        reader = sap_access.get_reader(settings)
        if not sap_access.customer_exists(reader, result.resolved.sap_customer_id):
            return ResolveCustomerResult(
                query=name,
                resolved=None,
                candidates=result.candidates,
                message="The name is known but that customer id was not found in SAP. Tell the user.",
            )
    return result
