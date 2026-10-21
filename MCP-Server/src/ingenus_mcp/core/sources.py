"""Where contract files come from: a local folder, or SharePoint through Microsoft Graph (graph.py).

Both are read-only and sit behind one small interface, so the tools do not know which is in use. A
source lists files and opens them for reading; nothing here can write, move or delete anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from ingenus_mcp.core.config import Settings
from ingenus_mcp.core.scope import resolve_inside


@dataclass(frozen=True)
class DocItem:
    rel_path: str  # the document_id: a path under the source root, with forward slashes
    name: str
    size: int
    modified: str  # ISO 8601, UTC
    version: str  # changes when the file changes (mtime and size locally, the eTag on SharePoint)
    item_id: str = ""  # SharePoint item id; empty for a local file


class DocumentSource(Protocol):
    identity: str  # cache key part: who is reading what. Never share cached text across identities
    revalidate_seconds: float  # how long a cached copy is trusted without asking the source again

    def list_items(self) -> list[DocItem]: ...

    def stat(self, rel_path: str) -> DocItem:
        """The item for one document id. Raises ScopeError if the id points outside the root and
        FileNotFoundError if there is no such file."""
        ...

    def read_bytes(self, item: DocItem) -> bytes: ...


class LocalFolderSource:
    """A folder on this machine (the v0 behaviour; also what the offline tests use)."""

    revalidate_seconds = 0.0  # a stat is cheap, so always check

    def __init__(self, root: Path):
        self.root = root
        self.identity = f"local:{root}"

    def _item(self, path: Path) -> DocItem:
        stat = path.stat()
        return DocItem(
            rel_path=path.relative_to(self.root.resolve()).as_posix(),
            name=path.name,
            size=stat.st_size,
            modified=datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(timespec="seconds"),
            version=f"{stat.st_mtime_ns}:{stat.st_size}",
        )

    def list_items(self) -> list[DocItem]:
        if not self.root.is_dir():
            raise FileNotFoundError(
                "The contract folder is not available. Check the plug-in settings."
            )
        root = self.root.resolve()
        files = [p for p in root.rglob("*") if p.is_file() and not p.name.startswith(".")]
        return sorted((self._item(p) for p in files), key=lambda i: i.rel_path.casefold())

    def stat(self, rel_path: str) -> DocItem:
        path = resolve_inside(self.root, rel_path)
        if not path.is_file():
            raise FileNotFoundError(
                f"No such document: {rel_path}. Use a document_id from find_contract_files."
            )
        return self._item(path)

    def read_bytes(self, item: DocItem) -> bytes:
        return resolve_inside(self.root, item.rel_path).read_bytes()


def get_source(settings: Settings) -> DocumentSource:
    """The source for the current request. For SharePoint this needs the signed-in user's token."""
    if settings.doc_source == "local":
        return LocalFolderSource(settings.contracts_dir)
    if settings.doc_source == "sharepoint":
        # Imported here: the local route needs no Microsoft libraries.
        from ingenus_mcp.core import graph

        return graph.sharepoint_source(settings)
    raise ValueError(
        f"Unknown INGENUS_DOC_SOURCE '{settings.doc_source}'. Use 'local' or 'sharepoint'."
    )
