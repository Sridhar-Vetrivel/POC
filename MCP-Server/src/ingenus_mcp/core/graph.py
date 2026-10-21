"""Read SharePoint through Microsoft Graph, as the signed-in user, read-only (V1-6).

Two parts:

- ``OboTokenProvider`` swaps the token the user signed in with for a Microsoft Graph token (the
  on-behalf-of flow). The server proves who it is with a certificate; the user's token is never
  passed on to Graph or logged. The Graph token carries only the user's own rights.
- ``GraphSource`` lists and reads the files under one configured folder of one SharePoint site.

Only GET requests are sent, only to graph.microsoft.com. Checked against Microsoft's docs on
20 Oct 2026: the on-behalf-of token request (v2-oauth2-on-behalf-of-flow), site by path
(`/sites/{hostname}:/{path}`), list children by path (`/drives/{id}/root:/{path}:/children`) and
download (`/drives/{id}/items/{id}/content`, a 302 to a pre-authenticated URL).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from typing import Any
from urllib.parse import quote, urlparse

import requests

from ingenus_mcp.core import auth
from ingenus_mcp.core.config import Settings
from ingenus_mcp.core.scope import check_relative
from ingenus_mcp.core.sources import DocItem

GRAPH = "https://graph.microsoft.com/v1.0"
GRAPH_DEFAULT_SCOPE = "https://graph.microsoft.com/.default"
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_FOLDERS = 500
TIMEOUT = (5, 30)  # connect, read (seconds)
_RETRY_STATUS = {429, 502, 503, 504}
_SELECT = "id,name,size,eTag,lastModifiedDateTime,file,folder"


class GraphError(RuntimeError):
    """A SharePoint or sign-in problem, with a message safe to show the user (no tokens)."""


class GraphAuthError(GraphError):
    """The server could not get a Graph token for this user."""


class GraphAccessError(GraphError):
    """SharePoint refused the request for this user."""


class OboTokenProvider:
    """Exchange the user's token for a Graph token, using the server's certificate."""

    def __init__(self, settings: Settings, app: Any | None = None):
        self._settings = settings
        self._app = app
        self._lock = threading.Lock()

    def _confidential_app(self) -> Any:
        with self._lock:
            if self._app is None:
                s = self._settings
                if not (
                    s.tenant_id and s.server_client_id and s.cert_key_file and s.cert_thumbprint
                ):
                    raise GraphAuthError(
                        "Server sign-in settings are incomplete: INGENUS_TENANT_ID, "
                        "INGENUS_SERVER_CLIENT_ID, INGENUS_CERT_KEY_FILE and INGENUS_CERT_THUMBPRINT "
                        "are all needed to read SharePoint."
                    )
                try:
                    private_key = s.cert_key_file.read_text(encoding="utf-8")
                except OSError as exc:
                    raise GraphAuthError(
                        f"The server's certificate key file cannot be read ({type(exc).__name__})."
                    ) from exc
                import msal  # imported here: only the SharePoint route needs it

                self._app = msal.ConfidentialClientApplication(
                    s.server_client_id,
                    authority=s.authority,
                    client_credential={"private_key": private_key, "thumbprint": s.cert_thumbprint},
                )
            return self._app

    def graph_token(self, user_assertion: str) -> str:
        result = self._confidential_app().acquire_token_on_behalf_of(
            user_assertion=user_assertion, scopes=[GRAPH_DEFAULT_SCOPE]
        )
        token = result.get("access_token") if isinstance(result, dict) else None
        if not token:
            code = (result or {}).get("error", "unknown_error") if isinstance(result, dict) else ""
            detail = str((result or {}).get("error_description", "")).split("\n")[0][:200]
            raise GraphAuthError(
                f"The server could not get SharePoint access for this user ({code}). {detail}".strip()
            )
        return token


_OBO: OboTokenProvider | None = None
_OBO_LOCK = threading.Lock()
_DRIVES: dict[tuple[str, str], str] = {}  # (host, site path) or ('onedrive', user id) -> drive id


def _obo(settings: Settings) -> OboTokenProvider:
    global _OBO
    with _OBO_LOCK:
        if _OBO is None:
            _OBO = OboTokenProvider(settings)
        return _OBO


def reset_for_tests() -> None:
    global _OBO
    with _OBO_LOCK:
        _OBO = None
    _DRIVES.clear()


def parse_site_url(url: str) -> tuple[str, str]:
    """('contoso.sharepoint.com', '/sites/team') from 'https://contoso.sharepoint.com/sites/team'."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    if parsed.scheme != "https" or not parsed.hostname or not path.startswith("/"):
        raise GraphError(
            "INGENUS_SP_SITE_URL must look like https://<tenant>.sharepoint.com/sites/<site>."
        )
    return parsed.hostname, path


class GraphSource:
    """The files under one folder of a SharePoint site's default library, or of the signed-in user's
    own OneDrive, read as that user. Both are Microsoft Graph drives: only how the drive is found differs."""

    revalidate_seconds = 60.0  # a file's eTag is checked against SharePoint at most once a minute

    def __init__(
        self,
        settings: Settings,
        user_id: str,
        token: Callable[[], str],
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        location: str = "sharepoint",
    ):
        self._location = location
        if location == "onedrive":
            self._label = "OneDrive"
            self._drive_key = ("onedrive", user_id)  # each person has their own drive
            self._folder = settings.onedrive_folder.strip("/")
            self.identity = f"graph:{user_id}:onedrive/{self._folder}"
        else:
            self._label = "SharePoint"
            host, site_path = parse_site_url(settings.sharepoint_site_url)
            self._host, self._site_path = host, site_path
            self._drive_key = (host, site_path)
            self._folder = settings.sharepoint_folder.strip("/")
            self.identity = f"graph:{user_id}:{host}{site_path}/{self._folder}"
        self._token = token
        self._session = session or requests.Session()
        self._sleep = sleep

    # -- HTTP -----------------------------------------------------------------------------------
    def _get(self, url: str, *, stream: bool = False) -> requests.Response:
        if not url.startswith("https://graph.microsoft.com/"):
            raise GraphError("Refusing to send a request outside graph.microsoft.com.")
        headers = {"Authorization": f"Bearer {self._token()}", "Accept": "application/json"}
        response: requests.Response | None = None
        for attempt in range(4):
            response = self._session.get(url, headers=headers, timeout=TIMEOUT, stream=stream)
            if response.status_code not in _RETRY_STATUS or attempt == 3:
                break
            try:
                wait = min(float(response.headers.get("Retry-After", "1")), 10.0)
            except ValueError:
                wait = 1.0
            self._sleep(wait)
        assert response is not None
        if response.status_code in (401, 403):
            raise GraphAccessError(
                f"{self._label} refused access for this user. Check that "
                + (
                    "they are a member of the site and that "
                    if self._location == "sharepoint"
                    else ""
                )
                + "admin consent was granted for the server's Graph permissions."
            )
        if response.status_code == 404:
            raise FileNotFoundError(f"Not found in {self._label}.")
        if response.status_code >= 400:
            raise GraphError(f"{self._label} returned HTTP {response.status_code}.")
        return response

    def _json(self, url: str) -> dict[str, Any]:
        return self._get(url).json()

    # -- site and library -----------------------------------------------------------------------
    def _drive_id(self) -> str:
        key = self._drive_key
        if key not in _DRIVES:
            if self._location == "onedrive":
                drive = self._json(f"{GRAPH}/me/drive")  # the signed-in user's own drive
            else:
                site = self._json(f"{GRAPH}/sites/{self._host}:{quote(self._site_path, safe='/')}")
                drive = self._json(f"{GRAPH}/sites/{site['id']}/drive")
            _DRIVES[key] = drive["id"]
        return _DRIVES[key]

    def _full_path(self, rel: str) -> str:
        return "/".join(p for p in (self._folder, rel) if p)

    def _children_url(self, drive: str, rel: str) -> str:
        full = self._full_path(rel)
        base = f"{GRAPH}/drives/{drive}/root"
        base += f":/{quote(full, safe='/')}:" if full else ""
        return f"{base}/children?$top=200&$select={_SELECT}"

    @staticmethod
    def _item(rel: str, entry: dict[str, Any]) -> DocItem:
        return DocItem(
            rel_path=rel,
            name=entry["name"],
            size=int(entry.get("size", 0)),
            modified=str(entry.get("lastModifiedDateTime", "")),
            version=str(entry.get("eTag", "")),
            item_id=str(entry["id"]),
        )

    def _pages(self, url: str) -> Iterator[list[dict[str, Any]]]:
        next_url: str | None = url
        while next_url:
            body = self._json(next_url)
            yield body.get("value", [])
            next_url = body.get("@odata.nextLink")

    # -- DocumentSource -------------------------------------------------------------------------
    def list_items(self) -> list[DocItem]:
        drive = self._drive_id()
        items: list[DocItem] = []
        pending = [""]
        folders_seen = 0
        while pending:
            folder = pending.pop()
            folders_seen += 1
            if folders_seen > MAX_FOLDERS:
                break
            for entries in self._pages(self._children_url(drive, folder)):
                for entry in entries:
                    name = entry.get("name", "")
                    if not name or name.startswith("."):
                        continue
                    rel = f"{folder}/{name}" if folder else name
                    if "folder" in entry:
                        pending.append(rel)
                    elif "file" in entry:
                        items.append(self._item(rel, entry))
        return sorted(items, key=lambda i: i.rel_path.casefold())

    def stat(self, rel_path: str) -> DocItem:
        check_relative(rel_path)  # raises ScopeError for '..', absolute paths and the like
        drive = self._drive_id()
        full = quote(self._full_path(rel_path), safe="/")
        entry = self._json(f"{GRAPH}/drives/{drive}/root:/{full}?$select={_SELECT}")
        if "file" not in entry:
            raise FileNotFoundError(
                f"No such document: {rel_path}. Use a document_id from find_contract_files."
            )
        return self._item(rel_path, entry)

    def read_bytes(self, item: DocItem) -> bytes:
        if item.size > MAX_FILE_BYTES:
            raise GraphError(f"{item.name} is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB.")
        drive = self._drive_id()
        response = self._get(f"{GRAPH}/drives/{drive}/items/{item.item_id}/content", stream=True)
        data = bytearray()
        for chunk in response.iter_content(65536):
            data.extend(chunk)
            if len(data) > MAX_FILE_BYTES:
                raise GraphError(
                    f"{item.name} is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB."
                )
        return bytes(data)


def _graph_source(settings: Settings, location: str) -> GraphSource:
    user = auth.current_token()
    if user is None:
        raise GraphAuthError(
            "Reading SharePoint or OneDrive needs a signed-in user. Start the server with "
            "INGENUS_AUTH=entra and connect through the sign-in bridge."
        )
    provider = _obo(settings)
    return GraphSource(
        settings,
        user_id=user.user_id,
        token=lambda: provider.graph_token(user.token),
        location=location,
    )


def sharepoint_source(settings: Settings) -> GraphSource:
    """A source that reads SharePoint as the user whose token arrived with this request."""
    return _graph_source(settings, "sharepoint")


def onedrive_source(settings: Settings) -> GraphSource:
    """A source that reads a folder of the signed-in user's own OneDrive."""
    return _graph_source(settings, "onedrive")
