"""Stored contract passages and keyword search over them (decision 0012).

When a customer's files are listed, the text of each (non-draft) file is split into passages, one per
paragraph or clause, and kept with the file's fingerprint (a hash of its content). `search_contracts` finds
passages by Postgres full-text search. Search only helps to FIND a clause: a rate found here still goes
through `get_contract_pages` and the quote check before it counts.

A passage is a second copy of text that one person may open and another may not, so a hit is returned only
after the asking person's own source has opened that file (as them for SharePoint and OneDrive), and only
while the file's fingerprint is the one the passage was stored with. A changed file replaces its passages.
Kept 90 days from last use (`python -m ingenus_mcp.audit prune`). Passage text is never written to a log.

The heading (section) is searched together with the text, so "returns" finds the clause under
"5. PAYMENT AND RETURNS".

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
from ingenus_mcp.core.embeddings import (
    Embedder,
    EmbedderUnavailable,
    get_embedder,
    min_similarity,
    vector_text,
)
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
    tsv         tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(section, '') || ' ' || text)) STORED
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


_NUMBERED_TITLE = re.compile(r"^\d+(?:\.\d+)*[.)]?\s+[A-Z][^.:;,%]*$")


def _is_heading(block: str) -> bool:
    """A short line that looks like a title: mostly capitals ("5. PAYMENT AND RETURNS") or a numbered title
    ("3. Returns"). A line with a colon, a percent sign or a full stop is body text, so it is never dropped."""
    if (
        len(block) > HEADING_CHARS
        or block.endswith((".", ";", ","))
        or "%" in block
        or ":" in block
    ):
        return False
    letters = [c for c in block if c.isalpha()]
    if not letters:
        return False
    upper = sum(c.isupper() for c in letters) / len(letters)
    return upper >= 0.6 or bool(_NUMBERED_TITLE.match(block))


def split_page(text: str) -> list[tuple[str | None, str]]:
    """One page into (section, passage) pairs. A short heading line becomes the section of what follows."""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    if len(blocks) == 1:  # a page with no blank lines: pack its lines instead
        packed: list[str] = []
        for line in (normalize(b) for b in blocks[0].splitlines() if b.strip()):
            if (
                packed
                and len(packed[-1]) + 1 + len(line) <= MAX_CHARS
                and not _is_heading(line)
                and not _is_heading(packed[-1])
            ):
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


_VEC_DDL = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS passage_vec (
    passage_id TEXT PRIMARY KEY REFERENCES passage (passage_id) ON DELETE CASCADE,
    model      TEXT NOT NULL,
    embedding  vector NOT NULL
);
"""
BACKFILL_MAX = 400  # passages embedded in one search; the rest are done by the next searches
RRF_K = 60  # reciprocal rank fusion constant: a hit's score is the sum of 1/(RRF_K + rank) over the lists


def _vec_session(target: Target):
    return db.session(target, "", _DDL + _VEC_DDL)


def _backfill(target: PgTarget, embedder: Embedder, customer_id: str | None) -> int:
    """Embed the passages that have no vector for this model yet (and drop vectors of any other model)."""
    where = "AND p.customer_id = %(customer)s" if customer_id else ""
    with _vec_session(target) as conn:
        conn.execute(
            "DELETE FROM passage_vec WHERE model <> %(model)s", {"model": embedder.spec.name}
        )
        rows = conn.execute(
            "SELECT p.passage_id, p.section, p.text FROM passage p"  # noqa: S608
            " LEFT JOIN passage_vec v ON v.passage_id = p.passage_id AND v.model = %(model)s"
            f" WHERE v.passage_id IS NULL {where} ORDER BY p.passage_id LIMIT %(n)s",
            {"model": embedder.spec.name, "customer": customer_id, "n": BACKFILL_MAX},
        ).fetchall()
        if not rows:
            return 0
        texts = [f"{section}. {text}" if section else text for _pid, section, text in rows]
        for (pid, _s, _t), vector in zip(rows, embedder.embed_documents(texts), strict=True):
            conn.execute(
                "INSERT INTO passage_vec (passage_id, model, embedding) VALUES"
                " (%(id)s, %(model)s, %(vec)s::vector) ON CONFLICT (passage_id) DO UPDATE SET"
                " model = excluded.model, embedding = excluded.embedding",
                {"id": pid, "model": embedder.spec.name, "vec": vector_text(vector)},
            )
        return len(rows)


def _meaning_rows(
    target: PgTarget, embedder: Embedder, query: str, customer_id: str | None, floor: float
) -> list[tuple]:
    """The passages closest in meaning to the query, nearest first, none below the similarity floor."""
    where = "AND p.customer_id = %(customer)s" if customer_id else ""
    vector = vector_text(embedder.embed_query(query))
    with _vec_session(target) as conn:
        rows = conn.execute(
            "SELECT p.passage_id, p.document_id, p.sha12, p.page, p.section, p.text,"  # noqa: S608
            " 1 - (v.embedding <=> %(q)s::vector) AS sim FROM passage_vec v"
            " JOIN passage p ON p.passage_id = v.passage_id"
            f" WHERE v.model = %(model)s {where} ORDER BY v.embedding <=> %(q)s::vector LIMIT %(n)s",
            {"q": vector, "model": embedder.spec.name, "customer": customer_id, "n": CANDIDATES},
        ).fetchall()
    return [r for r in rows if float(r[6]) >= floor]


def search(
    settings: Settings, query: str, customer_id: str | None, limit: int
) -> SearchContractsResult:
    """Keyword search and, if a model is set, meaning search; each candidate file is opened as the asking
    person before its passage is shown."""
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
            keyword = conn.execute(
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

    # Meaning search, when a model is set. Any problem here leaves keyword search as it was.
    meaning: list[tuple] = []
    meaning_note = ""
    meaning_on = False
    try:
        embedder = get_embedder(settings)
        if embedder is not None:
            _backfill(target, embedder, customer_id)
            meaning = _meaning_rows(
                target, embedder, query, customer_id, min_similarity(settings, embedder)
            )
            meaning_on = True
    except (EmbedderUnavailable, *db.STORE_ERRORS) as exc:
        meaning_note = f" Meaning search is off for this call ({type(exc).__name__}: {exc})."
        print(f"[ingenus_mcp] meaning search skipped ({type(exc).__name__})", file=sys.stderr)

    # Merge the two lists by reciprocal rank fusion: a passage in both lists ranks above one in a single list.
    merged: dict[str, dict[str, Any]] = {}
    for position, row in enumerate(keyword, start=1):
        entry = merged.setdefault(row[0], {"row": row[:6], "score": 0.0, "kw": False, "sim": None})
        entry["score"] += 1 / (RRF_K + position)
        entry["kw"] = True
    for position, row in enumerate(meaning, start=1):
        entry = merged.setdefault(row[0], {"row": row[:6], "score": 0.0, "kw": False, "sim": None})
        entry["score"] += 1 / (RRF_K + position)
        entry["sim"] = float(row[6])
    ranked = sorted(merged.values(), key=lambda e: (-e["score"], e["row"][1], e["row"][3]))[
        :CANDIDATES
    ]

    source = get_source(settings)
    verdict: dict[str, str | None] = {}  # document -> its current sha12 if this person can open it
    not_checked: list[NotChecked] = []
    for entry in ranked:
        document = entry["row"][1]
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
    for entry in ranked:
        pid, document, sha12, page, section, text = entry["row"]
        if verdict.get(document) != sha12:
            continue  # not openable by this person, or the file changed since the passage was stored
        if len(hits) >= limit:
            break
        found = ("both" if entry["sim"] is not None else "keyword") if entry["kw"] else "meaning"
        hits.append(
            SearchHit(
                document_id=document,
                filename=PurePosixPath(document.partition(":")[2] or document).name,
                source=document.partition(":")[0] if ":" in document else None,
                page=page,
                section=section,
                text=text,
                rank=round(entry["score"], 5),
                matched_by=found,
                similarity=round(entry["sim"], 3) if entry["sim"] is not None else None,
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
    how = "by keyword and by meaning" if meaning_on else "by keyword only"
    note = (
        f"{len(hits)} passage(s) found {how}. This finds where to look, not a fact: "
        + (
            "a 'meaning' hit is similar in sense and may not contain the words you typed. "
            if meaning_on
            else "it does not understand meaning, so different wording is missed. "
        )
        + "It covers only files already listed by someone. "
        "A number found here is not a checked term: read the page with get_contract_pages."
        + meaning_note
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
        meaning_search=meaning_on,
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
