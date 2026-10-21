"""Check that a quote Claude extracted is really on the cited page, and that it holds the rate."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from ingenus_mcp.core.config import Settings
from ingenus_mcp.core.documents import UnsupportedFormat, load_document, normalize
from ingenus_mcp.core.models import ExtractedTerm
from ingenus_mcp.core.scope import ScopeError
from ingenus_mcp.core.sources import get_source

MIN_QUOTE_CHARS = 8


def verify_term(term: ExtractedTerm, settings: Settings) -> str | None:
    """Return None if the citation holds, otherwise the reason it does not."""
    cite = term.citation
    try:
        pages = load_document(get_source(settings), cite.document).pages
    except ScopeError as exc:
        return f"Document id rejected: {exc}"
    except FileNotFoundError:
        return f"No such document: {cite.document}."
    except UnsupportedFormat as exc:
        return str(exc)
    if cite.page > len(pages):
        return f"Page {cite.page} does not exist; the document has {len(pages)} pages."
    text = pages[cite.page - 1]
    if not text or not text.strip():
        return f"Page {cite.page} has no readable text, so the quote cannot be checked."

    quote = normalize(cite.quote)
    if len(quote) < MIN_QUOTE_CHARS:
        return (
            "The quote is too short to check. Quote the sentence or table row that holds the rate."
        )
    if quote not in normalize(text):
        return f"The quote was not found on page {cite.page}."

    if term.product and term.product.casefold() not in quote.casefold():
        return f"The quote does not mention the product '{term.product}'. Quote the line for that product."

    numbers = re.findall(r"\d+(?:\.\d+)?", quote)
    for raw in numbers:
        try:
            if Decimal(raw) == term.rate_pct:
                return None
        except InvalidOperation:
            continue
    return (
        f"The quote is on page {cite.page} but does not contain the rate {term.rate_pct}. "
        "It may be the wrong clause (spelled-out numbers are not recognised)."
    )
