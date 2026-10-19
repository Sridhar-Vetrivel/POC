"""The guides (skills) the server serves through get_guide (decision 0003). Read-only.

A guide is a folder with a ``SKILL.md``: a YAML header with ``name`` and ``description``, then Markdown.
The folder is read on every call, so a guide added or edited on the server is served on the next call.
A requested name is only ever matched against the guides found; it is never used as a path.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from ingenus_mcp.core.models import Guide, GuideResult, GuideSummary

GUIDE_FILE = "SKILL.md"


class GuideFormatError(ValueError):
    """A SKILL.md without a valid YAML header (name and description)."""


def parse_guide(path: Path) -> Guide:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise GuideFormatError(f"{path}: no YAML header")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise GuideFormatError(f"{path}: the YAML header is not closed")
    header = yaml.safe_load(parts[1]) or {}
    name, description = header.get("name"), header.get("description")
    if not isinstance(name, str) or not isinstance(description, str):
        raise GuideFormatError(f"{path}: the header needs a name and a description")
    if name != path.parent.name:
        raise GuideFormatError(f"{path}: name '{name}' does not match the folder name")
    return Guide(name=name, description=description.strip(), content=parts[2].strip())


def load_guides(folder: Path) -> dict[str, Guide]:
    """Every valid guide in the folder, by name. A broken guide is skipped, not fatal."""
    guides: dict[str, Guide] = {}
    if not folder.is_dir():
        return guides
    for path in sorted(folder.glob(f"*/{GUIDE_FILE}")):
        try:
            guide = parse_guide(path)
        except (GuideFormatError, yaml.YAMLError, OSError):
            continue
        guides[guide.name] = guide
    return guides


def get_guides(folder: Path, names: list[str] | None) -> GuideResult:
    guides = load_guides(folder)
    available = [GuideSummary(name=g.name, description=g.description) for g in guides.values()]
    if not guides:
        return GuideResult(
            available=[],
            guides=[],
            note="No guidance is available on this server. Use the tool descriptions.",
        )
    wanted = list(dict.fromkeys(n.strip() for n in names or [] if n and n.strip()))
    found = [guides[n] for n in wanted if n in guides]
    missing = [n for n in wanted if n not in guides]
    if not wanted:
        note = (
            "These are the guides. Read the ones that fit the task by calling get_guide with their "
            "names; for a contract check, start with contract-check-playbook and report-format."
        )
    elif missing:
        note = f"Not found: {', '.join(missing)}. Use a name from 'available'."
    else:
        note = "Follow these guides for this task."
    return GuideResult(available=available, guides=found, not_found=missing, note=note)
