"""Tool: get_check_history. Discovered at start-up by ingenus_mcp.tools.discover()."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from ingenus_mcp.core import history
from ingenus_mcp.core.config import load_settings
from ingenus_mcp.core.models import CheckHistoryResult
from ingenus_mcp.core.registry import tool


@tool(read_only=True)
def get_check_history(
    document_id: Annotated[
        str | None,
        Field(
            description="A document_id from find_contract_files: checks that relied on this file."
        ),
    ] = None,
    customer_id: Annotated[
        str | None,
        Field(description="A SAP customer id from resolve_customer: all checks of this customer."),
    ] = None,
    limit: Annotated[int, Field(description="How many records at most (1 to 50).")] = 10,
) -> CheckHistoryResult:
    """Show what earlier checks of a file or a customer found, by anyone who used this server.

    Use this before a new check, or when the user asks "has this been checked before?" or "what did
    others find?". Give a document_id or a customer_id. Each record says who ran it, when, the as-of
    date, the lines (contract rate, SAP rate, status, monthly gap), the totals, how many items were not
    checked, and for each file whether it changed since (`changed_since`). These are figures an earlier
    check produced, not new findings: say so, and re-run compare_contract_to_sap if the file changed or
    the user needs a current answer. Only records whose files the asking person can open are shown.
    It holds no page text and no chat history. Read-only.
    """
    if not document_id and not customer_id:
        raise ValueError("Give a document_id or a customer_id.")
    return history.read_history(load_settings(), document_id, customer_id, limit)
