"""Tool: find_contract_files. Discovered at start-up by ingenus_mcp.tools.discover()."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from ingenus_mcp.core import contracts
from ingenus_mcp.core.config import load_settings
from ingenus_mcp.core.models import (
    FindContractFilesResult,
)
from ingenus_mcp.core.registry import tool


@tool(read_only=True)
def find_contract_files(
    customer: Annotated[
        str | None,
        Field(description="Customer name or alias. Leave empty to list every contract file."),
    ] = None,
    kind: Annotated[
        Literal["master", "amendment", "other"] | None,
        Field(description="Only files of this kind."),
    ] = None,
) -> FindContractFilesResult:
    """List a customer's contract files (master agreements, amendments) with their document_id.

    Use this to see which files exist before reading pages. Draft files are left out on purpose and
    listed by name in `excluded_drafts`; mention them if relevant. Returns file names, kind, date and
    hash only, not the contents. Read-only. Never opens a file outside the configured contract folder.
    """
    return contracts.find_contract_files(load_settings(), customer, kind)
