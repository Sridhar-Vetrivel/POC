"""Read the text of a contract file, page by page. Read-only: files are only ever opened for reading."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from pypdf import PdfReader

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


@lru_cache(maxsize=64)
def _read_cached(path_str: str, mtime_ns: int, size: int) -> tuple[str | None, ...]:
    path = Path(path_str)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        reader = PdfReader(str(path))
        pages: list[str | None] = []
        for page in reader.pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception:  # noqa: BLE001 - one bad page must not hide the others
                pages.append(None)
        return tuple(pages)
    if suffix == ".txt":
        raw = path.read_text(encoding="utf-8")
        parts = raw.split("\f")
        if parts and not parts[-1].strip():
            parts = parts[:-1]
        return tuple(parts)
    raise UnsupportedFormat(
        f"Unsupported file type '{suffix}'. Supported: text PDFs and .txt files."
    )


def read_pages(path: Path) -> list[str | None]:
    """Page texts, index 0 = page 1. ``""`` = no extractable text; ``None`` = page could not be read."""
    stat = path.stat()
    return list(_read_cached(str(path), stat.st_mtime_ns, stat.st_size))
