"""Stored contract terms (decision 0011): what an earlier check found in a file, kept for the next check.

When `compare_contract_to_sap` has checked that a term's quote really is on the cited page and holds the rate,
that term is kept here with its quote, page, the file and the file's fingerprint (a hash of its content). The
next person who checks the customer gets the stored terms back from `get_contract_terms` and Claude does not
have to read and extract them again, so the same file gives the same terms every time.

The file stays the truth. A stored term is used only while the file's fingerprint is the one it was stored
with. If the file changed, the term is set aside (status 'stale') and the file has to be read again. And a
stored term is only handed back for a file that the asking person's own listing shows: what SharePoint or
OneDrive hides from someone is never returned to them from here. Terms are re-checked against the page by
`compare_contract_to_sap` every time they are used, as any term Claude sends is.

What is stored: the rate, product, effective date, document id, page, clause, the exact quote, the file
fingerprint, who verified it and when. NOT stored: page text, tokens, or anything a person said to Claude.
Kept 90 days from last use (`python -m ingenus_mcp.audit prune`). Lives in the same database as the check
history (decision 0006); off when the history is off.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime
from typing import Any

from ingenus_mcp.core import citations, db
from ingenus_mcp.core.config import Settings
from ingenus_mcp.core.customers import norm
from ingenus_mcp.core.db import Target
from ingenus_mcp.core.documents import load_document
from ingenus_mcp.core.models import Citation, ContractFile, ExtractedTerm, StoredTerm
from ingenus_mcp.core.sources import DocumentSource

_DDL = """
CREATE TABLE IF NOT EXISTS term (
    term_id        TEXT PRIMARY KEY,
    customer_id    TEXT NOT NULL,
    kind           TEXT NOT NULL,
    product        TEXT,
    rate_pct       TEXT NOT NULL,
    effective_date TEXT NOT NULL,
    document_id    TEXT NOT NULL,
    sha12          TEXT NOT NULL,
    page           INTEGER NOT NULL,
    clause         TEXT,
    quote          TEXT NOT NULL,
    status         TEXT NOT NULL,
    verified_at    TEXT NOT NULL,
    verified_by    TEXT NOT NULL,
    last_used      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS term_customer ON term (customer_id, status);
CREATE INDEX IF NOT EXISTS term_document ON term (document_id);
"""


def _session(target: Target):
    return db.session(target, _DDL, _DDL)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def enabled(settings: Settings) -> bool:
    return settings.records_db is not None


def term_id(customer_id: str, term: ExtractedTerm, sha12: str) -> str:
    """The same term from the same file content always gets the same id, so saving twice is one record."""
    key = json.dumps(
        [
            customer_id,
            term.kind,
            norm(term.product or ""),
            str(term.rate_pct),
            term.effective_date.isoformat(),
            term.citation.document,
            sha12,
            term.citation.page,
            norm(term.citation.quote),
        ]
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]


_UPSERT = (
    "INSERT INTO term (term_id, customer_id, kind, product, rate_pct, effective_date, document_id, sha12,"
    " page, clause, quote, status, verified_at, verified_by, last_used) VALUES (%(term_id)s,"
    " %(customer_id)s, %(kind)s, %(product)s, %(rate_pct)s, %(effective_date)s, %(document_id)s,"
    " %(sha12)s, %(page)s, %(clause)s, %(quote)s, 'verified', %(now)s, %(user)s, %(now)s)"
    " ON CONFLICT (term_id) DO UPDATE SET status = 'verified', last_used = excluded.last_used"
)


def save_verified(
    settings: Settings,
    source: DocumentSource,
    customer_id: str,
    terms: list[ExtractedTerm],
    user: str,
) -> int:
    """Keep every term whose quote is on its page and holds the rate. Never raises: a store problem must
    not turn a good answer into an error. Returns how many terms were kept."""
    target = settings.records_db
    if target is None:
        return 0
    try:
        rows: list[dict[str, Any]] = []
        now = _now()
        for t in terms:
            if citations.verify_term(t, settings) is not None:
                continue  # the same check compare ran: a term that failed it is not kept
            sha12 = load_document(source, t.citation.document).sha12  # cached: no new download
            rows.append(
                {
                    "term_id": term_id(customer_id, t, sha12),
                    "customer_id": customer_id,
                    "kind": t.kind,
                    "product": t.product,
                    "rate_pct": str(t.rate_pct),
                    "effective_date": t.effective_date.isoformat(),
                    "document_id": t.citation.document,
                    "sha12": sha12,
                    "page": t.citation.page,
                    "clause": t.citation.clause,
                    "quote": t.citation.quote,
                    "now": now,
                    "user": user,
                }
            )
        with _session(target) as conn:
            for row in rows:
                conn.execute(_UPSERT, row)
        return len(rows)
    except Exception as exc:  # noqa: BLE001 - see the docstring
        print(
            f"[ingenus_mcp] could not save contract terms ({type(exc).__name__})", file=sys.stderr
        )
        return 0


_COLUMNS = (
    "term_id, kind, product, rate_pct, effective_date, document_id, sha12, page, clause, quote,"
    " verified_at, verified_by"
)


def lookup(
    settings: Settings,
    customer_id: str,
    files: list[ContractFile],
    changed: set[str] | None = None,
) -> tuple[list[StoredTerm], int]:
    """The stored terms that are still good for the files this person can see, and how many were set aside.

    A term is returned only if its document is in `files` (this person's own listing) and the file's
    fingerprint is the one the term was stored with. A term whose file is listed but has changed is set
    aside. A term whose file is not listed is left alone and not shown: it may belong to someone else's view.
    If `changed` is given, it is filled with the listed files that have terms stored for other content (so the
    caller can say which file changed, also on the calls after the terms were set aside).
    """
    target = settings.records_db
    if target is None:
        return [], 0
    current = {f.document_id: f.sha256_12 for f in files}
    fresh: list[StoredTerm] = []
    stale_ids: list[str] = []
    used_ids: list[str] = []
    with _session(target) as conn:
        rows = conn.execute(
            f"SELECT {_COLUMNS}, status FROM term WHERE customer_id = %(customer)s"
            " AND status IN ('verified', 'stale') ORDER BY document_id, page, term_id",
            {"customer": customer_id},
        ).fetchall()
        for r in rows:
            (
                tid,
                kind,
                product,
                rate,
                effective,
                document,
                sha12,
                page,
                clause,
                quote,
                at,
                by,
                state,
            ) = r
            if document not in current:
                continue
            if current[document] != sha12:
                if changed is not None:
                    changed.add(document)
                if state == "verified":
                    stale_ids.append(tid)
                continue
            if state != "verified":
                continue
            used_ids.append(tid)
            fresh.append(
                StoredTerm(
                    term=ExtractedTerm(
                        kind=kind,
                        product=product,
                        rate_pct=rate,
                        effective_date=effective,
                        citation=Citation(document=document, page=page, clause=clause, quote=quote),
                    ),
                    verified_at=at,
                    verified_by=by,
                )
            )
        now = _now()
        for tid in stale_ids:
            conn.execute("UPDATE term SET status = 'stale' WHERE term_id = %(id)s", {"id": tid})
        for tid in used_ids:
            conn.execute(
                "UPDATE term SET last_used = %(now)s WHERE term_id = %(id)s",
                {"id": tid, "now": now},
            )
    return fresh, len(stale_ids)


def prune(target: Target, before: str) -> int:
    """Delete the stored terms not used since `before` (an ISO time, UTC). Returns how many went."""
    with _session(target) as conn:
        return int(
            conn.execute(
                "DELETE FROM term WHERE last_used < %(before)s", {"before": before}
            ).rowcount
        )
