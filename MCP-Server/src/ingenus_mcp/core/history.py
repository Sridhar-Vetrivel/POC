"""Shared check history (decision 0006): what earlier checks found, for the next person who asks.

Every `compare_contract_to_sap` run leaves one record: who, when, the customer and date, the lines
(rates, status, gap), the totals, how many items were not checked, and the version of each file it
relied on. A person asking later can read the records for a file or a customer through
`get_check_history`.

What is stored: figures and citations (file, page, clause). NOT stored: page text, the quotes, tokens, or
anything a person said to Claude (the server never receives chat text). What is shown: only records whose
files the asking person can open themselves, so history never leaks a file someone may not read.
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import UTC, datetime
from typing import Any

from ingenus_mcp.core import auth, db
from ingenus_mcp.core.config import Settings
from ingenus_mcp.core.db import Target
from ingenus_mcp.core.documents import load_document
from ingenus_mcp.core.models import (
    CheckedDocument,
    CheckHistoryResult,
    CheckLine,
    CheckRecord,
    CompareResult,
)
from ingenus_mcp.core.sources import DocumentSource, get_source

_SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS checks (
    check_id   TEXT PRIMARY KEY,
    ts         TEXT NOT NULL,
    user       TEXT NOT NULL,
    user_id    TEXT,
    customer_id TEXT NOT NULL,
    as_of      TEXT NOT NULL,
    total_gap  TEXT NOT NULL,
    total_exposure TEXT NOT NULL,
    not_checked INTEGER NOT NULL,
    lines      TEXT NOT NULL,
    summary    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS check_docs (
    check_id    TEXT NOT NULL,
    document_id TEXT NOT NULL,
    version     TEXT NOT NULL,
    PRIMARY KEY (check_id, document_id)
);
CREATE INDEX IF NOT EXISTS checks_customer ON checks (customer_id, ts);
CREATE INDEX IF NOT EXISTS check_docs_doc ON check_docs (document_id);
"""

_POSTGRES_DDL = """
CREATE TABLE IF NOT EXISTS checks (
    seq        BIGSERIAL,
    check_id   TEXT PRIMARY KEY,
    ts         TEXT NOT NULL,
    "user"     TEXT NOT NULL,
    user_id    TEXT,
    customer_id TEXT NOT NULL,
    as_of      TEXT NOT NULL,
    total_gap  TEXT NOT NULL,
    total_exposure TEXT NOT NULL,
    not_checked INTEGER NOT NULL,
    lines      TEXT NOT NULL,
    summary    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS check_docs (
    check_id    TEXT NOT NULL,
    document_id TEXT NOT NULL,
    version     TEXT NOT NULL,
    PRIMARY KEY (check_id, document_id)
);
CREATE INDEX IF NOT EXISTS checks_customer ON checks (customer_id, ts);
CREATE INDEX IF NOT EXISTS check_docs_doc ON check_docs (document_id);
"""

MAX_LIMIT = 50


def _session(target: Target):
    return db.session(target, _SQLITE_DDL, _POSTGRES_DDL)


def record_check(
    settings: Settings,
    user: str,
    user_id: str | None,
    result: CompareResult,
    source: DocumentSource,
) -> None:
    """Leave a record of this check. Never raises: a full disk must not turn a good answer into an error."""
    path = settings.history_db
    if path is None:
        return
    try:
        lines = [
            {
                "kind": f.kind,
                "product": f.product,
                "status": f.status,
                "contract_rate_pct": str(f.contract_rate_pct),
                "sap_rate_pct": None if f.sap_rate_pct is None else str(f.sap_rate_pct),
                "monthly_gap": str(f.monthly_gap),
                "document": f.citation.document,
                "page": f.citation.page,
            }
            for f in result.findings
        ]
        versions: dict[str, str] = {}
        for document in sorted({line["document"] for line in lines}):
            versions[document] = load_document(
                source, document
            ).item.version  # cached: no new download
        check_id = uuid.uuid4().hex
        with _session(path) as conn:
            conn.execute(
                'INSERT INTO checks (check_id, ts, "user", user_id, customer_id, as_of, total_gap,'
                " total_exposure, not_checked, lines, summary) VALUES (%(check_id)s, %(ts)s, %(user)s,"
                " %(user_id)s, %(customer_id)s, %(as_of)s, %(gap)s, %(exposure)s, %(not_checked)s,"
                " %(lines)s, %(summary)s)",
                {
                    "check_id": check_id,
                    "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
                    "user": user,
                    "user_id": user_id,
                    "customer_id": result.customer_id,
                    "as_of": result.as_of.isoformat(),
                    "gap": str(result.total_monthly_gap),
                    "exposure": str(result.total_indicative_exposure),
                    "not_checked": len(result.not_checked),
                    "lines": json.dumps(lines, ensure_ascii=False),
                    "summary": result.summary,
                },
            )
            for document, version in versions.items():
                conn.execute(
                    "INSERT INTO check_docs (check_id, document_id, version)"
                    " VALUES (%(check_id)s, %(document)s, %(version)s)",
                    {"check_id": check_id, "document": document, "version": version},
                )
    except Exception as exc:  # noqa: BLE001 - see the docstring (a store error, or a file that vanished)
        print(
            f"[ingenus_mcp] could not save the check record ({type(exc).__name__})", file=sys.stderr
        )


_ROWS = (
    'SELECT c.check_id, c.ts, c."user", c.customer_id, c.as_of, c.total_gap, c.total_exposure,'
    " c.not_checked, c.lines, c.summary FROM checks c"
    " WHERE (%(document)s::text IS NULL OR c.check_id IN"
    " (SELECT check_id FROM check_docs WHERE document_id = %(document)s))"
    " AND (%(customer)s::text IS NULL OR c.customer_id = %(customer)s)"
)


def _rows(
    target: Target, document_id: str | None, customer_id: str | None, limit: int
) -> list[Any]:
    # Fixed SQL: each filter is "unset, or matches". Values are bound, nothing is pasted into the text.
    text = db.pick(
        target,
        _ROWS + " ORDER BY c.ts DESC, c.rowid DESC LIMIT %(limit)s",
        _ROWS + " ORDER BY c.ts DESC, c.seq DESC LIMIT %(limit)s",
    )
    params = {
        "document": document_id,
        "customer": customer_id,
        "limit": limit * 4,
    }  # spare: some are hidden
    with _session(target) as conn:
        rows = conn.execute(text, params).fetchall()
        docs = {
            row[0]: conn.execute(
                "SELECT document_id, version FROM check_docs WHERE check_id = %(id)s",
                {"id": row[0]},
            ).fetchall()
            for row in rows
        }
    return [(row, docs[row[0]]) for row in rows]


def prune(target: Target, before: str) -> int:
    """Delete the check records older than `before` (an ISO time, UTC). Returns how many checks went."""
    with _session(target) as conn:
        conn.execute(
            "DELETE FROM check_docs WHERE check_id IN (SELECT check_id FROM checks WHERE ts < %(before)s)",
            {"before": before},
        )
        return int(
            conn.execute("DELETE FROM checks WHERE ts < %(before)s", {"before": before}).rowcount
        )


def read_history(
    settings: Settings, document_id: str | None, customer_id: str | None, limit: int
) -> CheckHistoryResult:
    if settings.history_db is None:
        return CheckHistoryResult(
            available=False,
            records=[],
            hidden_count=0,
            note="Check history is switched off on this server.",
        )
    limit = max(1, min(limit, MAX_LIMIT))
    source = get_source(settings)
    me = auth.current_user_name()
    readable: dict[str, Any] = {}  # document_id -> DocItem, or None if this person cannot open it

    def current(document: str) -> Any:
        if document not in readable:
            try:
                readable[document] = source.stat(document)
            except Exception:  # noqa: BLE001 - not allowed, gone or unreadable: treat as not openable
                readable[document] = None
        return readable[document]

    if document_id and current(document_id) is None:
        return CheckHistoryResult(
            available=True,
            records=[],
            hidden_count=0,
            note="You cannot open that file, so its check history is not shown.",
        )

    records: list[CheckRecord] = []
    hidden = 0
    for row, docs in _rows(settings.history_db, document_id, customer_id, limit):
        check_id, ts, who, cust, as_of, gap, exposure, not_checked, lines_json, summary = row
        if any(current(d) is None for d, _ in docs):
            hidden += 1  # a file this person cannot open took part: do not reveal the record
            continue
        if len(records) >= limit:
            break
        records.append(
            CheckRecord(
                when=ts,
                who=who,
                is_you=bool(me and who == me),
                customer_id=cust,
                as_of=as_of,
                total_monthly_gap=gap,
                total_indicative_exposure=exposure,
                not_checked_count=not_checked,
                lines=[CheckLine(**line) for line in json.loads(lines_json)],
                documents=[
                    CheckedDocument(
                        document_id=d, version_checked=v, changed_since=current(d).version != v
                    )
                    for d, v in docs
                ],
                summary=summary,
            )
        )
    note = (
        f"{len(records)} earlier check(s), newest first. These are figures that earlier checks produced, "
        "not new findings: a changed file (changed_since true) or a later SAP change can make them out of date. "
        "Re-run compare_contract_to_sap to check again."
    )
    if hidden:
        note += f" {hidden} more are not shown because they used a file you cannot open."
    if not records and not hidden:
        note = "No earlier check of this was recorded on this server."
    return CheckHistoryResult(available=True, records=records, hidden_count=hidden, note=note)
