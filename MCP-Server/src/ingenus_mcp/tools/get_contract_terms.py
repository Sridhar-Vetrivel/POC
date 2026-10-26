"""Tool: get_contract_terms. Discovered at start-up by ingenus_mcp.tools.discover()."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from ingenus_mcp.core import contracts, customers, records
from ingenus_mcp.core.config import load_settings
from ingenus_mcp.core.models import ContractTermsResult, DocumentTerms
from ingenus_mcp.core.registry import tool


@tool(read_only=True)
def get_contract_terms(
    customer: Annotated[str, Field(description="Customer name or alias, as the user gave it.")],
) -> ContractTermsResult:
    """List a customer's contract files and the terms already stored for them, so they are not read twice.

    Use this instead of find_contract_files when you are about to check a customer. For each file it says
    `use_stored_terms` (its terms are in `stored`: pass them unchanged in `terms` of
    compare_contract_to_sap) or `read_pages` (no stored terms for this content: read it with
    get_contract_pages and extract the terms as usual). A stored term is only returned while its file is
    unchanged, and only for files you can open. Stored terms were verified by code, not reviewed by a
    person. The file stays the truth: say so if a file changed. Report `sources`, `complete` and
    `conflicts` as for find_contract_files. Read-only.
    """
    settings = load_settings()
    resolved = customers.resolve(customer, settings.customers_file)
    if resolved.resolved is None:
        return ContractTermsResult(
            customer_id=None,
            stored=[],
            documents=[],
            set_aside=0,
            storing_enabled=records.enabled(settings),
            note=resolved.message,
        )
    who = resolved.resolved
    found = contracts.find_contract_files(settings, who.name, None)
    changed: set[str] = set()
    stored, set_aside = records.lookup(settings, who.sap_customer_id, found.files, changed)
    per_document: dict[str, int] = {}
    for item in stored:
        per_document[item.term.citation.document] = (
            per_document.get(item.term.citation.document, 0) + 1
        )
    documents = [
        DocumentTerms(
            document_id=f.document_id,
            filename=f.filename,
            kind=f.kind,
            source=f.source,
            sha256_12=f.sha256_12,
            stored_terms=per_document.get(f.document_id, 0),
            changed_since_stored=f.document_id in changed and not per_document.get(f.document_id),
            action="use_stored_terms" if per_document.get(f.document_id) else "read_pages",
        )
        for f in found.files
    ]
    reuse = sum(1 for d in documents if d.action == "use_stored_terms")
    note = (
        f"{who.name} ({who.sap_customer_id}): {len(documents)} file(s); {reuse} with stored terms, "
        f"{len(documents) - reuse} to read. "
    )
    changed_names = [d.filename for d in documents if d.changed_since_stored]
    if changed_names:
        note += f"Changed since its terms were stored, so read again: {', '.join(changed_names)}. "
    if set_aside:
        note += f"{set_aside} stored term(s) were set aside because their file changed. "
    note += found.note
    return ContractTermsResult(
        customer_id=who.sap_customer_id,
        customer_name=who.name,
        stored=stored,
        documents=documents,
        set_aside=set_aside,
        excluded_drafts=found.excluded_drafts,
        sources=found.sources,
        complete=found.complete,
        conflicts=found.conflicts,
        not_checked=found.not_checked,
        storing_enabled=records.enabled(settings),
        note=note,
    )
