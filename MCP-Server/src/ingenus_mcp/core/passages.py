"""Stored contract passages and keyword search over them (decision 0012).

When a customer's files are listed, the text of each (non-draft) file is split into passages, one per
paragraph or clause, and kept with the file's fingerprint (a hash of its content). `search_contracts` finds
passages by Postgres full-text search. Search only helps to FIND a clause: a rate found here still goes
through `get_contract_pages` and the quote check before it counts.

A passage is a second copy of text that one person may open and another may not, so a hit is returned only
after the asking person's own source has opened that file (as them for SharePoint and OneDrive), and only
while the file's fingerprint is the one the passage was stored with. A changed file replaces its passages.
Kept 90 days from last use (`python -m ingenus_mcp.audit prune`). Passage text is never written to a log.

Postgres only: the full-text column does not exist on SQLite, so there `enabled` is False.
"""

from __future__ import annotations

import re
import sys
from datetime import UTC, datetime
from pathlib import PurePosixPath
from threading import Lock
from typing import Any

from ingenus_mcp.core import customers, db
from ingenus_mcp.core.config import Settings
from ingenus_mcp.core.db import PgTarget, Target
from ingenus_mcp.core.documents import load_document, normalize
from ingenus_mcp.core.models import NotChecked, SearchContractsResult, SearchHit
from ingenus_mcp.core.sources import get_source

MAX_CHARS = 1200  # a longer paragraph is cut on a sentence end
HEADING_CHARS = 80  # a one-line block this short, with no full stop at the end, is a heading
CANDIDATES = 20  # hits whose files are checked for access; the caller gets at most `limit` of them

_DDL = """
CREATE TABLE IF NOT EXISTS passage (
    passage_id  TEXT PRIMARY KEY,
    customer_id TEXT,
    document_id TEXT NOT NULL,
    sha12       TEXT NOT NULL,
    page        INTEGER NOT NULL,
    section     TEXT,
    text        TEXT NOT NULL,
    last_used   TEXT NOT NULL,
    tsv         tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED
);
CREATE INDEX IF NOT EXISTS passage_tsv ON passage USING GIN (tsv);
CREATE INDEX IF NOT EXISTS passage_document ON passage (document_id);
CREATE INDEX IF NOT EXISTS passage_customer ON passage (customer_id);
"""

_SAVED: set[tuple[str, str, str]] = (
    set()
)  # (store, document, fingerprint) already saved by this process
_SAVED_LOCK = Lock()


def enabled(settings: Settings) -> bool:
    return isinstance(settings.records_db, PgTarget)


def _session(target: Target):
    return db.session(target, "", _DDL)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _cut(block: str) -> list[str]:
    """Cut a long block on sentence ends so that no piece is longer than MAX_CHARS (unless one sentence is)."""
    if len(block) <= MAX_CHARS:
        return [block]
    pieces: list[str] = []
    current = ""
    for sentence in re.split(r"(?<=[.;:!?])\s+", block):
        if current and len(current) + 1 + len(sentence) > MAX_CHARS:
            pieces.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current)
    return pieces


def _is_heading(block: str) -> bool:
    return len(block) <= HEADING_CHARS and not block.endswith((".", ";", ","))


def split_page(text: str) -> list[tuple[str | None, str]]:
    """One page into (section, passage) pairs. A short heading line becomes the section of what follows."""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    if len(blocks) == 1:  # a page with no blank lines: pack its lines instead
        packed: list[str] = []
        for line in (normalize(b) for b in blocks[0].splitlines() if b.strip()):
            if packed and len(packed[-1]) + 1 + len(line) <= MAX_CHARS and not _is_heading(line):
                packed[-1] = f"{packed[-1]} {line}"
            else:
                packed.append(line)
        blocks = packed
    out: list[tuple[str | None, str]] = []
    section: str | None = None
    for block in blocks:
        block = normalize(block)
        if _is_heading(block):
            section = block
            continue
        out.extend((section, piece) for piece in _cut(block))
    return out


def _customer_for(settings: Settings, document_id: str) -> str | None:
    """The customer whose name or alias is in the file's path (as find_contract_files matches), if any."""
    try:
        path = document_id.partition(":")[2] or document_id
        hay = f" {customers.norm(path.replace('/', ' '))} "
        for c in customers.load_customers(settings.customers_file):
            if any(f" {customers.norm(n)} " in hay for n in customers.names_for(c)):
                return str(c["sap_customer_id"])
    except Exception:  # noqa: BLE001 - a passage without a customer is still searchable
        return None
    return None


def save(settings: Settings, document_id: str, sha12: str, pages: tuple[str | None, ...]) -> int:
    """Keep the passages of one file's current content and drop those of older content. Never raises:
    a store problem must not turn a good answer into an error. Returns how many passages were kept."""
    target = settings.records_db
    if not isinstance(target, PgTarget):
        return 0
    key = (str(target), document_id, sha12)
    with _SAVED_LOCK:
        if key in _SAVED:
            return 0
    try:
        customer = _customer_for(settings, document_id)
        now = _now()
        rows: list[dict[str, Any]] = []
        for number, text in enumerate(pages, start=1):
            if not text or not text.strip():
                continue
            for position, (section, passage) in enumerate(split_page(text)):
                rows.append(
                    {
                        "id": f"{sha12}:{document_id}:{number}:{position}",
                        "customer": customer,
                        "document": document_id,
                        "sha12": sha12,
                        "page": number,
                        "section": section,
                        "text": passage,
                        "now": now,
                    }
                )
        with _session(target) as conn:
            conn.execute(
                "DELETE FROM passage WHERE document_id = %(document)s AND sha12 <> %(sha12)s",
                {"document": document_id, "sha12": sha12},
            )
            for row in rows:
                conn.execute(
                    "INSERT INTO passage (passage_id, customer_id, document_id, sha12, page, section,"
                    " text, last_used) VALUES (%(id)s, %(customer)s, %(document)s, %(sha12)s, %(page)s,"
                    " %(section)s, %(text)s, %(now)s) ON CONFLICT (passage_id) DO UPDATE SET"
                    " last_used = excluded.last_used, customer_id = excluded.customer_id",
                    row,
                )
        with _SAVED_LOCK:
            _SAVED.add(key)
        return len(rows)
    except Exception as exc:  # noqa: BLE001 - see the docstring
        print(f"[ingenus_mcp] could not save passages ({type(exc).__name__})", file=sys.stderr)
        return 0


def search(
    settings: Settings, query: str, customer_id: str | None, limit: int
) -> SearchContractsResult:
    """Keyword search, then each candidate file is opened as the asking person before its passage is shown."""
    target = settings.records_db
    if not isinstance(target, PgTarget):
        return SearchContractsResult(
            query=query,
            customer_id=customer_id,
            hits=[],
            available=False,
            note="Search is not available: this server has no Postgres database for it.",
        )
    if not query.strip():
        return SearchContractsResult(
            query=query, customer_id=customer_id, hits=[], available=True, note="Empty query."
        )
    where = "AND customer_id = %(customer)s" if customer_id else ""
    try:
        with _session(target) as conn:
            rows = conn.execute(
                "SELECT passage_id, document_id, sha12, page, section, text,"  # noqa: S608
                " ts_rank(tsv, q) AS rank FROM passage, websearch_to_tsquery('english', %(q)s) q"
                f" WHERE tsv @@ q {where} ORDER BY rank DESC, document_id, page, passage_id"
                " LIMIT %(n)s",
                {"q": query, "customer": customer_id, "n": CANDIDATES},
            ).fetchall()
    except db.STORE_ERRORS as exc:
        print(f"[ingenus_mcp] passage search failed ({type(exc).__name__})", file=sys.stderr)
        return SearchContractsResult(
            query=query,
            customer_id=customer_id,
            hits=[],
            available=False,
            note="Search is not available: the store failed.",
        )

    source = get_source(settings)
    verdict: dict[str, str | None] = {}  # document -> its current sha12 if this person can open it
    not_checked: list[NotChecked] = []
    for row in rows:
        document = row[1]
        if document in verdict:
            continue
        try:
            doc = load_document(source, document)
            verdict[document] = doc.sha12
            save(settings, document, doc.sha12, doc.pages)  # a changed file replaces its passages
        except Exception as exc:  # noqa: BLE001 - not openable by this person, or its source is down
            verdict[document] = None
            not_checked.append(
                NotChecked(
                    item=document,
                    reason=f"Could not be opened as you ({type(exc).__name__}); its passages were left out.",
                )
            )

    hits: list[SearchHit] = []
    used: list[str] = []
    for pid, document, sha12, page, section, text, rank in rows:
        if verdict.get(document) != sha12:
            continue  # not openable by this person, or the file changed since the passage was stored
        if len(hits) >= limit:
            break
        hits.append(
            SearchHit(
                document_id=document,
                filename=PurePosixPath(document.partition(":")[2] or document).name,
                source=document.partition(":")[0] if ":" in document else None,
                page=page,
                section=section,
                text=text,
                rank=round(float(rank), 4),
            )
        )
        used.append(pid)
    if used:
        try:
            with _session(target) as conn:
                now = _now()
                for pid in used:
                    conn.execute(
                        "UPDATE passage SET last_used = %(now)s WHERE passage_id = %(id)s",
                        {"now": now, "id": pid},
                    )
        except db.STORE_ERRORS:
            pass  # the clock is not worth failing a search for
    note = (
        f"{len(hits)} passage(s) found by keyword. This finds where to look: it does not understand "
        "meaning, so different wording is missed, and it covers only files already listed by someone. "
        "A number found here is not a checked term: read the page with get_contract_pages."
    )
    if not_checked:
        note += (
            " Some files could not be opened as you, or their source is down, so the result may be"
            " incomplete."
        )
    return SearchContractsResult(
        query=query,
        customer_id=customer_id,
        hits=hits,
        available=True,
        complete=not not_checked,
        not_checked=not_checked,
        note=note,
    )


def prune(target: Target, before: str) -> int:
    """Delete the passages not used since `before` (an ISO time, UTC). Returns how many went."""
    if not isinstance(target, PgTarget):
        return 0
    with _session(target) as conn:
        return int(
            conn.execute(
                "DELETE FROM passage WHERE last_used < %(before)s", {"before": before}
            ).rowcount
        )
