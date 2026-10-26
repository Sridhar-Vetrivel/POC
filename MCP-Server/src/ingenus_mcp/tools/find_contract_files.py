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
    The server may read several sources (SharePoint, OneDrive, a network drive): each file says which
    one it is in. If `complete` is false a source could not be read: say which, do not treat a missing
    file as a missing contract, and do not present the check as complete. If `conflicts` is not empty,
    ask the user which copy is right. Each entry in `sources` says how many files that source holds in
    total (all customers): it does not mean the sources hold the same files.
    """
    return contracts.find_contract_files(load_settings(), customer, kind)
