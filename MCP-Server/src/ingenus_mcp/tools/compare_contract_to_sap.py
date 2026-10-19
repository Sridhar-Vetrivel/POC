"""Tool: compare_contract_to_sap. Discovered at start-up by ingenus_mcp.tools.discover()."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import Field

from ingenus_mcp.core import sap as sap_access
from ingenus_mcp.core.compare import compare
from ingenus_mcp.core.config import load_settings
from ingenus_mcp.core.models import (
    CompareResult,
    ExtractedTerm,
    NotChecked,
)
from ingenus_mcp.core.registry import tool


@tool(read_only=True)
def compare_contract_to_sap(
    customer_id: Annotated[str, Field(description="SAP customer id from resolve_customer.")],
    as_of: Annotated[
        date,
        Field(description="Check up to this date (YYYY-MM-DD). SAP setup is read as at this date."),
    ],
    terms: Annotated[
        list[ExtractedTerm],
        Field(
            description=(
                "The rebate and admin-fee terms you extracted from the contract pages. Every term needs "
                "a citation: the document_id, the page, and an exact quote that contains the rate."
            )
        ),
    ],
) -> CompareResult:
    """Compare the contract terms you extracted with the rebate and fee setup in SAP, in code.

    Use this after reading the contract pages. It checks every quote really appears on the cited page
    and contains the rate; terms that fail are returned in `not_checked`, never used. It then compares
    each term with SAP and returns variances, matches, terms not set up in SAP, the monthly gap and an
    indicative exposure from each effective date to `as_of`. No AI is involved in the numbers.
    Report `not_checked` and `caveats` to the user. Read-only: it does not change SAP.
    """
    settings = load_settings()
    reader = sap_access.get_reader(settings)
    setup = sap_access.rebate_setup(reader, customer_id, as_of)
    if not setup.lines:
        return CompareResult(
            customer_id=customer_id,
            as_of=as_of,
            findings=[],
            total_monthly_gap=Decimal(0),
            total_indicative_exposure=Decimal(0),
            in_sap_not_in_contract_terms=[],
            not_checked=[
                *setup.not_checked,
                *[NotChecked(item="all terms", reason="No SAP setup to compare with.")],
            ],
            summary="Nothing compared: SAP returned no setup lines for this customer on that date.",
            caveats=[f"SAP data source: {setup.source}."],
        )
    if terms:
        earliest = min(t.effective_date for t in terms)
        start = f"{earliest.year}-{earliest.month:02d}"
    else:
        start = f"{as_of.year}-{as_of.month:02d}"
    end = f"{as_of.year}-{as_of.month:02d}"
    volumes = sap_access.sales_volume(reader, customer_id, min(start, end), end)
    return compare(terms, customer_id, as_of, setup, volumes, settings)
