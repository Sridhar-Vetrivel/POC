"""Rule 1: the shared foundation and MCP building blocks name no business terms.

Scans foundation/ and mcp_servers/ (except mcp_servers/sap/adapters/). Phase 1 code under MCP-PlugIn/
is deliberately outside this scan (decision D6). Do not weaken this test to make code pass: move the
code instead.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCANNED = [ROOT / "foundation", ROOT / "mcp_servers"]
EXEMPT = [ROOT / "mcp_servers" / "sap" / "adapters"]
SUFFIXES = {".py", ".md", ".yaml", ".yml", ".json", ".toml"}

# Slice terms. Add to this list; never remove from it to get green.
WORDS = [
    r"contracts?",
    r"rebates?",
    r"admin(?:istrative)?[ _-]fees?",
    r"charge-?backs?",
    r"ndcs?",
    r"chain[ _-]x",
    r"amendments?",
]
PATTERN = re.compile(r"\b(?:" + "|".join(WORDS) + r")\b", re.IGNORECASE)


def _files() -> list[Path]:
    found: list[Path] = []
    for base in SCANNED:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in SUFFIXES or "__pycache__" in path.parts:
                continue
            if any(ex in path.parents for ex in EXEMPT):
                continue
            found.append(path)
    return found


def test_scan_actually_covers_files() -> None:
    names = {p.name for p in _files()}
    assert "interface.py" in names, "the scan must reach mcp_servers/sap/interface.py"


def test_no_domain_words_in_shared_code() -> None:
    offences = []
    for path in _files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            match = PATTERN.search(line)
            if match:
                offences.append(f"{path.relative_to(ROOT)}:{number}: '{match.group(0)}'")
    assert not offences, (
        "Business terms in shared code (move it into a slice or an adapter):\n"
        + "\n".join(offences)
    )
