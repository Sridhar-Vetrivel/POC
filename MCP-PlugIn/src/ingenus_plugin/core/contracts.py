"""Find contract files and the pages that matter, without sending whole files anywhere.

Page selection is keyword search (no outside model). It is deliberately generous, and it says what it
did not show. Source files are only ever opened for reading.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from ingenus_plugin.core import customers
from ingenus_plugin.core.config import Settings
from ingenus_plugin.core.documents import SUPPORTED, read_pages
from ingenus_plugin.core.models import (
    ContractFile,
    ContractPagesResult,
    FindContractFilesResult,
    NotChecked,
    PageText,
)
from ingenus_plugin.core.scope import resolve_inside

MAX_FILES = 200
DEFAULT_TOPICS = ["rebates", "fees", "effective_date"]


def _load_topics(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _kind(filename: str) -> str:
    name = filename.casefold()
    if "amend" in name:
        return "amendment"
    if "master" in name or "msa" in name or "supply agreement" in name:
        return "master"
    return "other"


def _sha12(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()[:12]


def _is_draft(path: Path, first_page: str | None) -> bool:
    if "draft" in path.name.casefold():
        return True
    head = (first_page or "")[:300]
    return any(word.strip(".,:;()[]").upper() == "DRAFT" for word in head.split())


def find_contract_files(
    settings: Settings, customer: str | None, kind: str | None
) -> FindContractFilesResult:
    root = settings.contracts_dir
    if not root.is_dir():
        raise FileNotFoundError("The contract folder is not available. Check the plug-in settings.")

    tokens: list[str] = []
    note_parts: list[str] = []
    if customer:
        res = customers.resolve(customer, settings.customers_file)
        if res.resolved:
            match = next(
                c
                for c in customers.load_customers(settings.customers_file)
                if c["sap_customer_id"] == res.resolved.sap_customer_id
            )
            tokens = [customers.norm(n) for n in customers.names_for(match)]
            note_parts.append(f"Customer resolved to {res.resolved.name}.")
        elif res.candidates and len(res.candidates) > 1 and res.candidates[0].match != "similar":
            return FindContractFilesResult(
                customer_query=customer,
                files=[],
                excluded_drafts=[],
                note="Ambiguous customer name. Ask the user which one: "
                + ", ".join(c.name for c in res.candidates)
                + ".",
            )
        else:
            tokens = [customers.norm(customer)]
            note_parts.append(
                "Customer not in the alias table; matched on the folder and file names only."
            )

    files: list[ContractFile] = []
    drafts: list[str] = []
    not_checked: list[NotChecked] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file() and not p.name.startswith(".")):
        rel = path.relative_to(root).as_posix()
        if tokens:
            hay = f" {customers.norm(rel.replace('/', ' '))} "
            if not any(f" {t} " in hay for t in tokens if t):
                continue
        if path.suffix.lower() not in SUPPORTED:
            if path.suffix.lower() in {".docx", ".doc", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
                not_checked.append(
                    NotChecked(
                        item=rel, reason="Unsupported format in phase 1 (text PDFs and .txt only)."
                    )
                )
            continue
        if len(files) >= MAX_FILES:
            not_checked.append(
                NotChecked(item="(more files)", reason=f"Listing stopped at {MAX_FILES} files.")
            )
            break
        try:
            pages = read_pages(path)
        except Exception as exc:  # noqa: BLE001 - one unreadable file must not hide the rest
            not_checked.append(
                NotChecked(item=rel, reason=f"Could not be read: {type(exc).__name__}.")
            )
            continue
        if _is_draft(path, pages[0] if pages else None):
            drafts.append(rel)
            continue
        file_kind = _kind(path.name)
        if kind and file_kind != kind:
            continue
        stat = path.stat()
        files.append(
            ContractFile(
                document_id=rel,
                filename=path.name,
                kind=file_kind,  # type: ignore[arg-type]
                modified=datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(timespec="seconds"),
                sha256_12=_sha12(path),
                pages=len(pages),
            )
        )

    note_parts.append(f"{len(files)} file(s) listed; {len(drafts)} draft(s) left out on purpose.")
    if customer and not files:
        note_parts.append(
            "No files matched. The folder or file names may use a different spelling."
        )
    return FindContractFilesResult(
        customer_query=customer,
        files=files,
        excluded_drafts=drafts,
        not_checked=not_checked,
        note=" ".join(note_parts),
    )


def get_contract_pages(
    settings: Settings, document_id: str, topics: list[str] | None
) -> ContractPagesResult:
    path = resolve_inside(settings.contracts_dir, document_id)
    if not path.is_file():
        raise FileNotFoundError(
            f"No such document: {document_id}. Use a document_id from find_contract_files."
        )

    config = _load_topics(settings.topics_file)
    known = config["topics"]
    chosen = list(topics) if topics else list(DEFAULT_TOPICS)
    unknown = [t for t in chosen if t not in known]
    if unknown:
        raise ValueError(f"Unknown topic(s) {unknown}. Valid topics: {sorted(known)}.")

    pages = read_pages(path)
    total = len(pages)
    not_checked: list[NotChecked] = []
    readable: dict[int, str] = {}
    for number, text in enumerate(pages, start=1):
        if text is None:
            not_checked.append(
                NotChecked(item=f"page {number}", reason="The page could not be read.")
            )
        elif not text.strip():
            not_checked.append(
                NotChecked(
                    item=f"page {number}",
                    reason="No extractable text (possibly a scan). OCR is not available in phase 1.",
                )
            )
        else:
            readable[number] = text

    matched: dict[int, list[str]] = {}
    for number, text in readable.items():
        lowered = text.casefold()
        hits = [t for t in chosen if any(k.casefold() in lowered for k in known[t]["keywords"])]
        if hits:
            matched[number] = hits

    selection = config.get("selection", {})
    chosen_pages: set[int] = set(matched)
    if selection.get("include_neighbour_pages", True):
        for number in list(matched):
            chosen_pages.update(n for n in (number - 1, number + 1) if n in readable)
    if selection.get("always_include_first_page", True) and 1 in readable:
        chosen_pages.add(1)

    if not matched:
        not_checked.append(
            NotChecked(
                item="topic search",
                reason=(
                    f"No page matched the topics {chosen}. The clause may use different wording; "
                    "ask the user, or widen the topics."
                ),
            )
        )

    selected = [
        PageText(page=n, matched_topics=matched.get(n, []), text=readable[n])
        for n in sorted(chosen_pages)
        if n in readable
    ]
    note = (
        f"Showing {len(selected)} of {total} pages: pages matching {chosen} by keyword, their "
        "neighbours, and page 1. Other pages were not shown. This is keyword search, so unusual "
        "wording can be missed: say so if a term you expect is absent."
    )
    return ContractPagesResult(
        document_id=document_id,
        total_pages=total,
        topics=chosen,
        pages=selected,
        not_checked=not_checked,
        selection_note=note,
    )
