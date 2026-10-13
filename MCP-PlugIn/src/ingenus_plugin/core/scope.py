"""Scope guard: a tool may only read inside the configured folders."""

from __future__ import annotations

from pathlib import Path


class ScopeError(ValueError):
    """The request points outside the folders this plug-in is allowed to read."""


def resolve_inside(root: Path, relative: str) -> Path:
    """Resolve ``relative`` under ``root`` or raise ScopeError. Never follows a path out of root."""
    if not relative or "\x00" in relative:
        raise ScopeError("Empty or invalid document id.")
    candidate = Path(relative)
    if candidate.is_absolute() or candidate.drive:
        raise ScopeError(
            "Absolute paths are not accepted. Use a document_id from find_contract_files."
        )
    root_resolved = root.resolve()
    target = (root_resolved / candidate).resolve()
    if root_resolved != target and root_resolved not in target.parents:
        raise ScopeError("That path is outside the contract folder this plug-in may read.")
    return target
