"""Where contract files come from: a local folder, or SharePoint through Microsoft Graph (graph.py).

Both are read-only and sit behind one small interface, so the tools do not know which is in use. A
source lists files and opens them for reading; nothing here can write, move or delete anything.
"""

from __future__ import annotations

import fnmatch
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from ingenus_mcp.core import auth
from ingenus_mcp.core.config import Settings
from ingenus_mcp.core.scope import ScopeError, resolve_inside


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


def _is_link(path: Path) -> bool:
    """A symbolic link or a Windows junction (also how a DFS link looks): never followed."""
    try:
        return path.is_symlink() or path.is_junction()
    except OSError:
        return True  # cannot tell, so do not trust it


class NetworkShareSource(LocalFolderSource):
    """A shared folder reached by path: a UNC path such as \\\\server\\share\\contracts, or a mounted share.

    Read-only. Differences from a plain local folder: links (symbolic links, junctions, DFS links) are
    never followed, so nothing outside the root can be reached through one; Office lock files and temp
    files are skipped; a file that cannot be read is reported, not fatal; the folder is re-checked every
    few seconds, not on every call (a stat over a network is slow).
    The server reads as ONE account (the one it runs as), so every signed-in user sees what that account
    sees; per-user access to a share is not enforced here.
    """

    revalidate_seconds = 10.0

    def __init__(self, root: Path, exclude: tuple[str, ...] = (), timeout: float = 20.0):
        super().__init__(root)
        self._timeout = timeout
        self.identity = f"network:{root}"
        self._exclude = tuple(p.casefold() for p in exclude)
        self.skipped: list[tuple[str, str]] = []  # (path, why) for find_contract_files to report

    def _excluded(self, name: str) -> bool:
        return any(fnmatch.fnmatchcase(name.casefold(), pattern) for pattern in self._exclude)

    def _bounded(self, work: Callable[..., Any], *args: Any) -> Any:
        """Run a file operation, and give up waiting after `timeout` seconds.

        A share that hangs blocks the operating system call and Python cannot interrupt it, so the call
        runs in a daemon thread that is abandoned if it overruns (it ends when the share answers or the
        server stops). The tool call then fails with a clear message instead of hanging.
        """
        outcome: dict[str, Any] = {}

        def run() -> None:
            try:
                outcome["value"] = work(*args)
            except BaseException as exc:  # noqa: BLE001 - handed to the caller below
                outcome["error"] = exc

        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        worker.join(self._timeout)
        if worker.is_alive():
            raise TimeoutError(
                f"The network folder did not answer within {self._timeout:g} seconds. "
                "Try again later, or ask your administrator whether the share is available."
            )
        if "error" in outcome:
            raise outcome["error"]
        return outcome["value"]

    def list_items(self) -> list[DocItem]:
        return self._bounded(self._list_items)

    def stat(self, rel_path: str) -> DocItem:
        return self._bounded(self._stat, rel_path)

    def read_bytes(self, item: DocItem) -> bytes:
        return self._bounded(super().read_bytes, item)

    def _list_items(self) -> list[DocItem]:
        if not self.root.is_dir():
            raise FileNotFoundError(
                "The network folder is not available. Check the server settings."
            )
        root = self.root.resolve()
        self.skipped = []
        items: list[DocItem] = []
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            here = Path(dirpath)
            kept: list[str] = []
            for name in dirnames:
                if name.startswith("."):
                    continue
                if _is_link(here / name):
                    rel = (here / name).relative_to(root).as_posix()
                    self.skipped.append(
                        (rel, "A link was not followed (it could lead outside this folder).")
                    )
                    continue
                kept.append(name)
            dirnames[:] = kept
            for name in filenames:
                if name.startswith(".") or self._excluded(name):
                    continue
                path = here / name
                rel = path.relative_to(root).as_posix()
                if _is_link(path):
                    self.skipped.append(
                        (rel, "A link was not followed (it could lead outside this folder).")
                    )
                    continue
                try:
                    items.append(self._item(path))
                except OSError as exc:
                    self.skipped.append((rel, f"Could not be read: {type(exc).__name__}."))
        return sorted(items, key=lambda i: i.rel_path.casefold())

    def _stat(self, rel_path: str) -> DocItem:
        path = resolve_inside(self.root, rel_path)
        current = self.root.resolve()
        for part in Path(rel_path).parts:  # no link anywhere on the way down
            current = current / part
            if _is_link(current):
                raise ScopeError("Links are not followed on a network folder.")
        if not path.is_file():
            raise FileNotFoundError(
                f"No such document: {rel_path}. Use a document_id from find_contract_files."
            )
        return self._item(path)


SOURCE_KINDS = ("local", "sharepoint", "onedrive", "network")


def build_source(settings: Settings, kind: str) -> DocumentSource:
    """One source of the given kind. For SharePoint and OneDrive this needs the signed-in user's token."""
    if kind == "local":
        return LocalFolderSource(settings.contracts_dir)
    if kind == "network":
        if settings.network_root is None:
            raise ValueError("INGENUS_DOC_SOURCE=network needs INGENUS_NETWORK_ROOT.")
        return NetworkShareSource(
            settings.network_root, settings.exclude_patterns, settings.network_timeout
        )
    if kind == "onedrive":
        from ingenus_mcp.core import graph

        return graph.onedrive_source(settings)
    if kind == "sharepoint":
        # Imported here: the local route needs no Microsoft libraries.
        from ingenus_mcp.core import graph

        return graph.sharepoint_source(settings)
    raise ValueError(
        f"Unknown INGENUS_DOC_SOURCE '{kind}'. Use 'local', 'sharepoint', 'onedrive' or 'network'."
    )


def get_source(settings: Settings) -> DocumentSource:
    """The source for the current request: one source, or all the sources in INGENUS_SOURCES."""
    if settings.sources:
        return RoutedSource(settings, settings.sources)
    return build_source(settings, settings.doc_source)


# --- several sources at once -----------------------------------------------------------------


class SourceUnavailable(RuntimeError):
    """Every source failed, so there is nothing to list."""


@dataclass(frozen=True)
class SourceStatus:
    source: str
    ok: bool
    files: int
    seconds: float
    reason: str | None = None


def split_document_id(document_id: str, kinds: tuple[str, ...]) -> tuple[str, str]:
    """('sharepoint', 'Chain_A/x.pdf') from 'sharepoint:Chain_A/x.pdf'. Anything else is refused."""
    kind, sep, path = document_id.partition(":")
    if not sep or kind not in kinds or not path:
        raise ScopeError(
            "The document id does not name one of this server's sources. "
            "Use a document_id exactly as returned by find_contract_files."
        )
    return kind, path


def _reason(exc: BaseException) -> str:
    text = str(exc).strip() or type(exc).__name__
    return text if len(text) <= 200 else text[:197] + "..."


class RoutedSource:
    """All the enabled sources behind the one DocumentSource interface.

    A document_id is `<source>:<path>`; the part after the colon is checked by that source exactly as when
    it is the only source. Listing asks every source at once, each in its own thread, and gives up on a
    slow one after `sources_timeout` seconds. A source that fails does not hide the others: it is
    recorded in `statuses`, so the caller can say that the list may be incomplete. Only when every source
    fails is an error raised. Read-only, like the sources it wraps.
    """

    revalidate_seconds = 0.0  # the real window is per source: see revalidate_for

    def __init__(
        self,
        settings: Settings,
        kinds: tuple[str, ...],
        builder: Callable[[Settings, str], DocumentSource] = build_source,
    ):
        self._settings = settings
        self.kinds = tuple(kinds)
        self._builder = builder
        self._built: dict[str, DocumentSource] = {}
        self._lock = threading.Lock()
        self.statuses: list[SourceStatus] = []
        self.skipped: list[tuple[str, str]] = []

    @property
    def identity(self) -> str:
        # Who is reading, and from which sources: SharePoint and OneDrive text is per person.
        return f"multi:{auth.current_user_id() or '-'}:{','.join(self.kinds)}"

    def _source(self, kind: str) -> DocumentSource:
        with self._lock:
            if kind not in self._built:
                self._built[kind] = self._builder(self._settings, kind)
            return self._built[kind]

    def revalidate_for(self, document_id: str) -> float:
        kind, _ = split_document_id(document_id, self.kinds)
        return self._source(kind).revalidate_seconds

    def _list_one(self, kind: str, source: DocumentSource, out: dict[str, Any]) -> None:
        started = time.monotonic()
        try:
            items = source.list_items()
            out[kind] = (
                SourceStatus(kind, True, len(items), time.monotonic() - started),
                items,
                list(getattr(source, "skipped", [])),
            )
        except BaseException as exc:  # noqa: BLE001 - one source failing must not hide the others
            out[kind] = (
                SourceStatus(kind, False, 0, time.monotonic() - started, _reason(exc)),
                [],
                [],
            )

    def list_items(self) -> list[DocItem]:
        results: dict[str, Any] = {}
        # Build every source HERE, in the thread that serves the request: SharePoint and OneDrive take
        # the signed-in user from the request's context, which a new thread does not have.
        workers = []
        for kind in self.kinds:
            started = time.monotonic()
            try:
                source = self._source(kind)
            except BaseException as exc:  # noqa: BLE001 - reported for this source only
                results[kind] = (
                    SourceStatus(kind, False, 0, time.monotonic() - started, _reason(exc)),
                    [],
                    [],
                )
                continue
            workers.append(
                threading.Thread(target=self._list_one, args=(kind, source, results), daemon=True)
            )
        for worker in workers:
            worker.start()
        deadline = time.monotonic() + self._settings.sources_timeout
        for worker in workers:
            worker.join(max(0.0, deadline - time.monotonic()))

        statuses: list[SourceStatus] = []
        items: list[DocItem] = []
        skipped: list[tuple[str, str]] = []
        for kind in self.kinds:
            if kind in results:
                status, found, skips = results[kind]
                items.extend(replace(i, rel_path=f"{kind}:{i.rel_path}") for i in found)
                skipped.extend((f"{kind}:{rel}", why) for rel, why in skips)
            else:  # still running: abandoned (a daemon thread), reported as failed
                status = SourceStatus(
                    kind,
                    False,
                    0,
                    self._settings.sources_timeout,
                    f"Did not answer within {self._settings.sources_timeout:g} seconds.",
                )
            statuses.append(status)
        self.statuses, self.skipped = statuses, skipped
        if not any(st.ok for st in statuses):
            raise SourceUnavailable(
                "No contract source could be read. "
                + " ".join(f"{st.source}: {st.reason}" for st in statuses)
            )
        return sorted(items, key=lambda i: i.rel_path.casefold())

    def stat(self, rel_path: str) -> DocItem:
        kind, path = split_document_id(rel_path, self.kinds)
        item = self._source(kind).stat(path)
        return replace(item, rel_path=f"{kind}:{item.rel_path}")

    def read_bytes(self, item: DocItem) -> bytes:
        kind, path = split_document_id(item.rel_path, self.kinds)
        return self._source(kind).read_bytes(replace(item, rel_path=path))
