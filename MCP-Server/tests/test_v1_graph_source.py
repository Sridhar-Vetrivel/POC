"""V1-6: reading contracts from SharePoint through Microsoft Graph, as the signed-in user.

Offline: a fake Graph answers from the local synthetic contract folder, in the shapes the Microsoft
docs show (site by path, children by path with paging, item by path, content). No Microsoft service
is contacted. The real thing is checked by hand with MCP-Server/scripts/signin_check.py.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import pytest
from v1_support import (  # noqa: F401  (pytest fixtures)
    AMEND2,
    DRAFT3,
    REPO,
    chain_x_terms,
    isolated_env,
)

from ingenus_mcp.core import documents, graph
from ingenus_mcp.core.config import load_settings
from ingenus_mcp.core.scope import ScopeError
from ingenus_mcp.core.sources import LocalFolderSource

CONTRACTS = REPO / "MCP-PlugIn" / "data" / "synthetic" / "contracts"
FOLDER = "General/synthetic/contracts"
SITE_URL = "https://contoso.sharepoint.com/sites/poc"


class FakeResponse:
    def __init__(self, status=200, payload=None, content=b"", headers=None):
        self.status_code = status
        self._payload = payload
        self._content = content
        self.headers = headers or {}

    def json(self):
        return self._payload

    def iter_content(self, size):
        for start in range(0, len(self._content), size):
            yield self._content[start : start + size]


class FakeGraph:
    """Stands in for requests.Session. Answers like Graph, from a local folder."""

    def __init__(
        self,
        root: Path = CONTRACTS,
        page_size: int = 7,
        status: int = 200,
        drive_id: str = "drive-1",
    ):
        self.root = root
        self.drive_id = drive_id
        self.page_size = page_size
        self.status = status  # a fixed failure for every call, e.g. 403
        self.throttle_first: int | None = None  # answer the first request with 429 once
        self.etag_suffix = ""
        self.calls: list[str] = []
        self.auth: list[str] = []
        self._by_id: dict[str, Path] = {}
        self._throttled = False

    def _id(self, path: Path) -> str:
        item_id = "item-" + hashlib.sha1(path.as_posix().encode()).hexdigest()[:10]
        self._by_id[item_id] = path
        return item_id

    def _entry(self, path: Path) -> dict:
        stat = path.stat()
        entry = {
            "id": self._id(path),
            "name": path.name,
            "size": stat.st_size,
            "eTag": f'"{stat.st_mtime_ns}:{stat.st_size}{self.etag_suffix}"',
            "lastModifiedDateTime": "2026-10-20T10:00:00Z",
        }
        entry["folder" if path.is_dir() else "file"] = {} if path.is_file() else {"childCount": 1}
        return entry

    def get(self, url, headers=None, timeout=None, stream=False):
        self.calls.append(url)
        self.auth.append((headers or {}).get("Authorization", ""))
        if self.throttle_first and not self._throttled:
            self._throttled = True
            return FakeResponse(429, headers={"Retry-After": str(self.throttle_first)})
        if self.status != 200:
            return FakeResponse(self.status)
        parsed = urlparse(url)
        path = unquote(parsed.path)
        query = parse_qs(parsed.query)

        if path.startswith("/v1.0/sites/contoso.sharepoint.com:/sites/poc"):
            return FakeResponse(payload={"id": "site-1"})
        if path in ("/v1.0/sites/site-1/drive", "/v1.0/me/drive"):
            return FakeResponse(payload={"id": self.drive_id})
        drive = re.escape(self.drive_id)

        m = re.fullmatch(rf"/v1\.0/drives/{drive}/items/(item-[0-9a-f]+)/content", path)
        if m:
            return FakeResponse(content=self._by_id[m.group(1)].read_bytes())

        m = re.fullmatch(rf"/v1\.0/drives/{drive}/root:/(.+?):/children", path)
        if m:
            folder = self._local(m.group(1))
            if folder is None or not folder.is_dir():
                return FakeResponse(404)
            entries = [self._entry(p) for p in sorted(folder.iterdir())]
            start = int(query.get("$skiptoken", ["0"])[0])
            page = entries[start : start + self.page_size]
            body: dict = {"value": page}
            if start + self.page_size < len(entries):
                body["@odata.nextLink"] = (
                    f"https://graph.microsoft.com{parsed.path}?$skiptoken={start + self.page_size}"
                )
            return FakeResponse(payload=body)

        m = re.fullmatch(rf"/v1\.0/drives/{drive}/root:/([^:]+)", path)
        if m:
            item = self._local(m.group(1))
            if item is None or not item.exists():
                return FakeResponse(404)
            return FakeResponse(payload=self._entry(item))
        return FakeResponse(404)

    def _local(self, graph_path: str) -> Path | None:
        if graph_path == FOLDER:
            return self.root
        if not graph_path.startswith(FOLDER + "/"):
            return None
        return self.root / graph_path[len(FOLDER) + 1 :]


@pytest.fixture(autouse=True)
def clean_state(monkeypatch, isolated_env):
    monkeypatch.setenv("INGENUS_SP_SITE_URL", SITE_URL)
    monkeypatch.setenv("INGENUS_SP_FOLDER", FOLDER)
    graph.reset_for_tests()
    documents.clear_cache()
    yield
    graph.reset_for_tests()
    documents.clear_cache()


def source_for(user="user-a", fake=None, bearer="graph-bearer-a", sleep=lambda s: None):
    fake = fake or FakeGraph()
    return (
        graph.GraphSource(load_settings(), user, lambda: bearer, session=fake, sleep=sleep),
        fake,
    )


# --- listing and reading -----------------------------------------------------------------------


def test_it_lists_the_same_30_files_as_the_local_folder():
    source, fake = source_for()
    items = source.list_items()
    local = LocalFolderSource(CONTRACTS).list_items()
    assert [i.rel_path for i in items] == [i.rel_path for i in local]
    assert len(items) == 30
    assert {i.size for i in items} == {i.size for i in local}
    # Several folders and a page size of 7 mean the listing followed @odata.nextLink.
    assert any("skiptoken" in url for url in fake.calls)


def test_the_site_and_library_are_looked_up_once():
    source, fake = source_for()
    source.list_items()
    source.list_items()
    assert sum("/sites/contoso.sharepoint.com:" in url for url in fake.calls) == 1
    assert sum(url.endswith("/sites/site-1/drive") for url in fake.calls) == 1


def test_only_graph_is_called_with_the_users_graph_token():
    source, fake = source_for()
    source.list_items()
    documents.load_document(source, AMEND2)
    assert fake.calls
    assert all(url.startswith("https://graph.microsoft.com/v1.0/") for url in fake.calls)
    assert set(fake.auth) == {"Bearer graph-bearer-a"}


def test_the_text_read_from_sharepoint_equals_the_local_text():
    source, _ = source_for()
    remote = documents.load_document(source, AMEND2)
    local = documents.load_document(LocalFolderSource(CONTRACTS), AMEND2)
    assert remote.pages == local.pages
    assert remote.sha12 == local.sha12


def test_chain_x_over_sharepoint_gives_the_agreed_numbers(monkeypatch):
    source, _ = source_for()
    from ingenus_mcp.core import citations, contracts
    from ingenus_mcp.tools.compare_contract_to_sap import compare_contract_to_sap
    from ingenus_mcp.tools.find_contract_files import find_contract_files
    from ingenus_mcp.tools.get_contract_pages import get_contract_pages

    monkeypatch.setattr(contracts, "get_source", lambda settings: source)
    monkeypatch.setattr(citations, "get_source", lambda settings: source)

    listing = find_contract_files(customer="Chain X")
    assert AMEND2 in {f.document_id for f in listing.files}
    assert [d for d in listing.excluded_drafts] == [DRAFT3]  # a draft is left out on purpose

    pages = get_contract_pages(document_id=AMEND2, topics=["rebates"])
    assert any("Product A rebate" in p.text for p in pages.pages)

    result = compare_contract_to_sap(
        customer_id="SYN-CUST-0001", as_of=date(2026, 8, 31), terms=chain_x_terms()
    )
    assert result.total_monthly_gap == Decimal("8500.00")
    assert result.total_indicative_exposure == Decimal("17000.00")
    assert (
        result.not_checked == []
    )  # every quote was re-checked against the text read from SharePoint


# --- scope: nothing outside the configured folder ----------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "../secret.pdf",
        "Chain_X/../../x.pdf",
        "/etc/passwd",
        "C:/Windows/win.ini",
        "a\\b.pdf",
        "",
        "a//b.pdf",
        "./a.pdf",
    ],
)
def test_a_path_outside_the_folder_is_refused_before_any_request(bad):
    source, fake = source_for()
    with pytest.raises(ScopeError):
        source.stat(bad)
    assert fake.calls == []


def test_a_missing_file_is_a_clear_not_found():
    source, _ = source_for()
    with pytest.raises(FileNotFoundError):
        source.stat("Chain_X/nope.pdf")


def test_a_folder_is_not_a_document():
    source, _ = source_for()
    with pytest.raises(FileNotFoundError):
        source.stat("Chain_X")


# --- failure behaviour -------------------------------------------------------------------------


def test_a_refusal_from_sharepoint_says_who_to_ask():
    source, _ = source_for(fake=FakeGraph(status=403))
    with pytest.raises(graph.GraphAccessError, match="member of the site"):
        source.list_items()


def test_throttling_is_retried_after_the_wait_it_asks_for():
    fake = FakeGraph()
    fake.throttle_first = 2
    waits: list[float] = []
    source, _ = source_for(fake=fake, sleep=waits.append)
    assert source.list_items()
    assert waits == [2.0]


def test_an_endless_throttle_gives_up_with_an_error():
    source, _ = source_for(fake=FakeGraph(status=429), sleep=lambda s: None)
    with pytest.raises(graph.GraphError, match="429"):
        source.list_items()


def test_a_request_outside_graph_is_never_sent():
    source, fake = source_for()
    with pytest.raises(graph.GraphError, match="outside graph.microsoft.com"):
        source._get("https://evil.example/steal")
    assert fake.calls == []


def test_a_huge_file_is_refused_without_downloading(monkeypatch):
    source, fake = source_for()
    item = source.stat(AMEND2)
    monkeypatch.setattr(graph, "MAX_FILE_BYTES", 10)
    with pytest.raises(graph.GraphError, match="larger than"):
        source.read_bytes(item)
    assert not any(url.endswith("/content") for url in fake.calls)


# --- the cache must never cross people ---------------------------------------------------------


def test_an_unchanged_file_is_not_downloaded_again():
    source, fake = source_for()
    documents.load_document(source, AMEND2)
    first = len(fake.calls)
    documents.load_document(source, AMEND2)
    assert len(fake.calls) == first  # trusted for a minute: no request at all

    source.revalidate_seconds = 0  # ask again: one metadata request, same eTag, no download
    documents.load_document(source, AMEND2)
    assert len(fake.calls) == first + 1
    assert not fake.calls[-1].endswith("/content")

    fake.etag_suffix = "-edited"  # the file changed in SharePoint: fetched again
    documents.load_document(source, AMEND2)
    assert fake.calls[-1].endswith("/content")


def test_text_one_user_may_read_is_not_handed_to_another():
    a, _ = source_for(user="user-a")
    documents.load_document(a, AMEND2)  # user A reads it, so it is cached

    b, _ = source_for(user="user-b", fake=FakeGraph(status=403))  # SharePoint refuses user B
    with pytest.raises(graph.GraphAccessError):
        documents.load_document(b, AMEND2)
    assert a.identity != b.identity


# --- the Graph token: on behalf of the signed-in user ------------------------------------------


class FakeMsalApp:
    def __init__(self, result):
        self.result = result
        self.calls: list[dict] = []

    def acquire_token_on_behalf_of(self, user_assertion, scopes):
        self.calls.append({"assertion": user_assertion, "scopes": scopes})
        return self.result


def test_the_users_token_is_swapped_for_a_graph_token():
    app = FakeMsalApp({"access_token": "graph-token", "token_type": "Bearer"})
    provider = graph.OboTokenProvider(load_settings(), app=app)
    assert provider.graph_token("the-users-token") == "graph-token"
    assert app.calls == [
        {"assertion": "the-users-token", "scopes": ["https://graph.microsoft.com/.default"]}
    ]


def test_a_failed_swap_explains_without_leaking_the_token():
    app = FakeMsalApp(
        {
            "error": "interaction_required",
            "error_description": "AADSTS50079: MFA needed.\nTrace ID: x",
        }
    )
    provider = graph.OboTokenProvider(load_settings(), app=app)
    with pytest.raises(graph.GraphAuthError) as caught:
        provider.graph_token("SECRET-USER-TOKEN")
    message = str(caught.value)
    assert "interaction_required" in message and "AADSTS50079" in message
    assert "SECRET-USER-TOKEN" not in message and "Trace ID" not in message


def test_missing_settings_are_named_not_guessed():
    provider = graph.OboTokenProvider(load_settings())  # no tenant, client id, key or thumbprint
    with pytest.raises(graph.GraphAuthError, match="INGENUS_CERT_KEY_FILE"):
        provider.graph_token("t")


def test_sharepoint_needs_a_signed_in_user():
    with pytest.raises(graph.GraphAuthError, match="signed-in user"):
        graph.sharepoint_source(load_settings())


@pytest.mark.parametrize(
    "url", ["http://x.sharepoint.com/sites/a", "https://x.sharepoint.com", "not a url", ""]
)
def test_the_site_url_must_be_https_with_a_site_path(url):
    with pytest.raises(graph.GraphError, match="INGENUS_SP_SITE_URL"):
        graph.parse_site_url(url)


def test_site_url_parts():
    assert graph.parse_site_url("https://contoso.sharepoint.com/sites/poc/") == (
        "contoso.sharepoint.com",
        "/sites/poc",
    )
