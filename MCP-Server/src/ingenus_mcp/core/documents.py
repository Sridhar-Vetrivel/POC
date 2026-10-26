"""Read the text of a contract file, page by page. Read-only: files are only ever opened for reading."""

from __future__ import annotations

import hashlib
import io
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

from ingenus_mcp.core.sources import DocItem, DocumentSource

SUPPORTED = {".pdf", ".txt"}

_QUOTE_MAP = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
        " ": " ",
    }
)


class UnsupportedFormat(ValueError):
    """Only text PDFs and .txt files are read. Other formats are reported as not checked."""


def normalize(text: str) -> str:
    """Make text comparable: plain quotes and dashes, single spaces."""
    return re.sub(r"\s+", " ", text.translate(_QUOTE_MAP)).strip()


def parse_pages(data: bytes, suffix: str) -> tuple[str | None, ...]:
    """Page texts, index 0 = page 1. ``""`` = no extractable text; ``None`` = page could not be read."""
    suffix = suffix.lower()
    if suffix == ".pdf":
        reader = PdfReader(io.BytesIO(data))
        pages: list[str | None] = []
        for page in reader.pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception:  # noqa: BLE001 - one bad page must not hide the others
                pages.append(None)
        return tuple(pages)
    if suffix == ".txt":
        parts = data.decode("utf-8").split("\f")
        if parts and not parts[-1].strip():
            parts = parts[:-1]
        return tuple(parts)
    raise UnsupportedFormat(
        f"Unsupported file type '{suffix}'. Supported: text PDFs and .txt files."
    )


def read_pages(path: Path) -> list[str | None]:
    """Page texts of a local file, for callers that already hold a path."""
    return list(parse_pages(path.read_bytes(), path.suffix))


@dataclass(frozen=True)
class LoadedDoc:
    item: DocItem
    pages: tuple[str | None, ...]
    sha12: str


@dataclass
class _Entry:
    doc: LoadedDoc
    checked: float


# Parsed text of recently read files. The key starts with the source identity (who is reading what),
# so text one user may read is never handed to another. Entries are small: page text only.
_CACHE: OrderedDict[tuple[str, str], _Entry] = OrderedDict()
_LOCK = threading.Lock()
_MAX_ENTRIES = 128


def clear_cache() -> None:
    with _LOCK:
        _CACHE.clear()


def load_document(source: DocumentSource, rel_path: str, item: DocItem | None = None) -> LoadedDoc:
    """Read one document through the source, re-using the parsed text while the file is unchanged."""
    key = (source.identity, rel_path)
    now = time.monotonic()
    # Several sources at once: how long a copy is trusted depends on the source the file is in.
    window_for = getattr(source, "revalidate_for", None)
    window = window_for(rel_path) if window_for else source.revalidate_seconds
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and window and now - hit.checked < window:
            _CACHE.move_to_end(key)
            return hit.doc
    item = item or source.stat(rel_path)
    if hit and hit.doc.item.version == item.version:
        with _LOCK:
            hit.checked = now
            _CACHE.move_to_end(key)
        return hit.doc
    data = source.read_bytes(item)
    doc = LoadedDoc(
        item=item,
        pages=parse_pages(data, Path(item.name).suffix),
        sha12=hashlib.sha256(data).hexdigest()[:12],
    )
    with _LOCK:
        _CACHE[key] = _Entry(doc, now)
        _CACHE.move_to_end(key)
        while len(_CACHE) > _MAX_ENTRIES:
            _CACHE.popitem(last=False)
    return doc
