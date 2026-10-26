"""Several contract sources at once (INGENUS_SOURCES): a file is found wherever it is, without changing a setting.

Offline: a folder stands in for the local source and another for the network share. SharePoint and OneDrive
are replaced by fake sources handed to RoutedSource, which is the same code path the server uses.
"""

from __future__ import annotations

import time

import pytest
from v1_support import isolated_env, signed_in_as, term  # noqa: F401  (pytest fixtures)

from ingenus_mcp.core import citations, contracts, documents
from ingenus_mcp.core.config import load_settings
from ingenus_mcp.core.scope import ScopeError
from ingenus_mcp.core.sources import (
    DocItem,
    RoutedSource,
    SourceUnavailable,
    get_source,
)
from ingenus_mcp.server.app import check_startup

PAGES = ["Master agreement. Parties.", "Product A rebate: 6.0% of net sales of Product A."]


@pytest.fixture(autouse=True)
def fresh_cache():
    documents.clear_cache()
    yield
    documents.clear_cache()


def write(root, relative, pages=PAGES):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\f".join(pages), encoding="utf-8")


@pytest.fixture
def two_sources(tmp_path, monkeypatch):
    """A local folder holding Acme and a network folder holding Zed."""
    local, share = tmp_path / "local", tmp_path / "share"
    write(local, "Acme/Acme_Master.txt")
    write(local, "Acme/Acme_Amendment_1.txt")
    write(share, "Zed/Zed_Master.txt")
    monkeypatch.setenv("INGENUS_SOURCES", "local,network")
    monkeypatch.setenv("INGENUS_CONTRACTS_DIR", str(local))
    monkeypatch.setenv("INGENUS_NETWORK_ROOT", str(share))
    return local, share


def test_a_file_is_found_in_whichever_source_holds_it(two_sources):
    settings = load_settings()
    acme = contracts.find_contract_files(settings, "Acme", None)
    zed = contracts.find_contract_files(settings, "Zed", None)
    assert {f.source for f in acme.files} == {"local"}
    assert {f.source for f in zed.files} == {"network"}
    assert all(f.document_id.startswith("local:Acme/") for f in acme.files)
    assert zed.files[0].document_id == "network:Zed/Zed_Master.txt"
    assert acme.complete and zed.complete
    assert [(s.source, s.ok) for s in zed.sources] == [("local", True), ("network", True)]


def test_pages_and_quote_checks_follow_the_source_in_the_document_id(two_sources):
    settings = load_settings()
    pages = contracts.get_contract_pages(settings, "network:Zed/Zed_Master.txt", ["rebates"])
    assert any("6.0%" in p.text for p in pages.pages)
    good = term(
        "rebate",
        "Product A",
        "6",
        "Product A rebate: 6.0% of net sales of Product A.",
        document="network:Zed/Zed_Master.txt",
    )
    assert citations.verify_term(good, settings) is None
    wrong_place = good.citation.model_copy(update={"document": "local:Zed/Zed_Master.txt"})
    missing = good.model_copy(update={"citation": wrong_place})
    assert "No such document" in citations.verify_term(missing, settings)


def test_the_source_name_is_not_used_to_match_a_customer(two_sources):
    settings = load_settings()
    result = contracts.find_contract_files(settings, "network", None)
    assert result.files == []  # "network" is a source, not part of any folder or file name


@pytest.mark.parametrize(
    "document_id",
    [
        "Acme/Acme_Master.txt",  # no source: ambiguous when there is more than one
        "ftp:Acme/Acme_Master.txt",  # not a source of this server
        "sharepoint:Acme/Acme_Master.txt",  # a real kind, but not switched on here
        "local:",
    ],
)
def test_a_document_id_must_name_one_of_the_enabled_sources(two_sources, document_id):
    with pytest.raises(ScopeError):
        contracts.get_contract_pages(load_settings(), document_id, None)


@pytest.mark.parametrize("path", ["../secret.txt", "/etc/passwd", "Acme/../../x.txt", "C:/x.txt"])
def test_the_path_after_the_source_name_is_still_checked(two_sources, path):
    with pytest.raises(ScopeError):
        contracts.get_contract_pages(load_settings(), f"local:{path}", None)


def test_a_source_that_cannot_be_read_does_not_hide_the_others(two_sources, tmp_path, monkeypatch):
    monkeypatch.setenv("INGENUS_NETWORK_ROOT", str(tmp_path / "gone"))
    result = contracts.find_contract_files(load_settings(), "Acme", None)
    assert len(result.files) == 2  # the local files are still found
    assert result.complete is False
    net = next(s for s in result.sources if s.source == "network")
    assert net.ok is False and net.reason
    assert any(n.item == "source network" for n in result.not_checked)
    assert "could not be read: network" in result.note
    assert "do not present the check as complete" in result.note


def test_no_file_found_while_a_source_is_down_is_not_called_a_missing_contract(
    two_sources, tmp_path, monkeypatch
):
    monkeypatch.setenv("INGENUS_NETWORK_ROOT", str(tmp_path / "gone"))
    result = contracts.find_contract_files(load_settings(), "Zed", None)  # Zed is on the share
    assert result.files == []
    assert result.complete is False
    assert "Do not read 'no file found' as 'no contract'" in result.note


def test_when_every_source_fails_the_call_fails(two_sources, tmp_path, monkeypatch):
    monkeypatch.setenv("INGENUS_NETWORK_ROOT", str(tmp_path / "gone"))
    monkeypatch.setenv("INGENUS_CONTRACTS_DIR", str(tmp_path / "also-gone"))
    with pytest.raises(SourceUnavailable) as caught:
        contracts.find_contract_files(load_settings(), "Acme", None)
    assert "local" in str(caught.value) and "network" in str(caught.value)


# --- the routing layer on its own, with fake sources -----------------------------------------


class FakeSource:
    revalidate_seconds = 5.0

    def __init__(self, name, files, delay=0.0, error=None):
        self.identity = f"fake:{name}"
        self._files, self._delay, self._error = files, delay, error

    def list_items(self):
        time.sleep(self._delay)
        if self._error:
            raise self._error
        return [
            DocItem(rel_path=p, name=p.rsplit("/", 1)[-1], size=1, modified="2026-01-01", version=v)
            for p, v in self._files.items()
        ]

    def stat(self, rel_path):
        return next(i for i in self.list_items() if i.rel_path == rel_path)

    def read_bytes(self, item):
        return self._files[item.rel_path].encode()


def routed(settings, sources: dict[str, FakeSource]) -> RoutedSource:
    return RoutedSource(settings, tuple(sources), builder=lambda _settings, kind: sources[kind])


def test_three_fake_sources_are_listed_together_in_name_order(isolated_env):
    settings = load_settings()
    src = routed(
        settings,
        {
            "sharepoint": FakeSource("sp", {"Chain_A/a.pdf": "1"}),
            "onedrive": FakeSource("od", {"Chain_C/c.pdf": "1"}),
            "network": FakeSource("nw", {"Chain_E/e.pdf": "1"}),
        },
    )
    ids = [i.rel_path for i in src.list_items()]
    assert ids == ["network:Chain_E/e.pdf", "onedrive:Chain_C/c.pdf", "sharepoint:Chain_A/a.pdf"]
    assert all(s.ok for s in src.statuses)
    assert src.stat("onedrive:Chain_C/c.pdf").rel_path == "onedrive:Chain_C/c.pdf"
    item = src.stat("network:Chain_E/e.pdf")
    assert src.read_bytes(item) == b"1"
    assert src.revalidate_for("network:Chain_E/e.pdf") == 5.0


def test_a_slow_source_is_given_up_on_after_the_limit(isolated_env, monkeypatch):
    monkeypatch.setenv("INGENUS_SOURCES_TIMEOUT", "0.3")
    settings = load_settings()
    src = routed(
        settings,
        {
            "sharepoint": FakeSource("sp", {"A/a.pdf": "1"}, delay=3.0),
            "network": FakeSource("nw", {"E/e.pdf": "1"}),
        },
    )
    started = time.monotonic()
    items = src.list_items()
    assert time.monotonic() - started < 2.0  # did not wait for the slow one
    assert [i.rel_path for i in items] == ["network:E/e.pdf"]
    slow = next(s for s in src.statuses if s.source == "sharepoint")
    assert slow.ok is False and "Did not answer" in slow.reason


def test_a_source_that_raises_is_reported_with_its_reason(isolated_env):
    src = routed(
        load_settings(),
        {
            "sharepoint": FakeSource("sp", {}, error=PermissionError("SharePoint refused access.")),
            "network": FakeSource("nw", {"E/e.pdf": "1"}),
        },
    )
    src.list_items()
    bad = next(s for s in src.statuses if s.source == "sharepoint")
    assert bad.ok is False and bad.reason == "SharePoint refused access."


def test_the_same_file_in_two_sources_is_listed_once_and_a_differing_one_is_flagged(
    two_sources,
):
    local, share = two_sources
    write(local, "Acme/Same.txt", ["identical"])
    write(share, "Acme/Same.txt", ["identical"])  # same name, same content
    write(local, "Acme/Differs.txt", ["version one"])
    write(share, "Acme/Differs.txt", ["version two"])  # same name, different content
    result = contracts.find_contract_files(load_settings(), "Acme", None)
    same = [f for f in result.files if f.filename == "Same.txt"]
    assert len(same) == 1 and same[0].source == "local" and same[0].also_in == ["network"]
    assert len([f for f in result.files if f.filename == "Differs.txt"]) == 2
    assert result.conflicts == ["differs.txt in local, network"]
    assert "different content" in result.note


def test_two_identical_files_in_the_same_source_are_both_kept(two_sources):
    local, _ = two_sources
    write(local, "Acme/Sub/Template.txt", ["same"])
    write(local, "Acme/Other/Template.txt", ["same"])
    result = contracts.find_contract_files(load_settings(), "Acme", None)
    assert len([f for f in result.files if f.filename == "Template.txt"]) == 2


def test_one_source_behaves_exactly_as_before(tmp_path, monkeypatch):
    write(tmp_path / "c", "Acme/Acme_Master.txt")
    monkeypatch.setenv("INGENUS_CONTRACTS_DIR", str(tmp_path / "c"))
    settings = load_settings()
    assert not isinstance(get_source(settings), RoutedSource)
    result = contracts.find_contract_files(settings, "Acme", None)
    assert result.files[0].document_id == "Acme/Acme_Master.txt"  # no source in the id
    assert result.files[0].source is None
    assert result.sources == [] and result.complete is True


# --- settings and start-up ---------------------------------------------------------------------


def test_the_source_list_is_read_in_order_without_repeats(isolated_env, monkeypatch):
    monkeypatch.setenv("INGENUS_SOURCES", " SharePoint, onedrive ,network,network,")
    assert load_settings().sources == ("sharepoint", "onedrive", "network")


def settings_with(monkeypatch, **env):
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return load_settings()


def test_start_up_checks_every_source_that_is_switched_on(isolated_env, monkeypatch):
    settings = settings_with(monkeypatch, INGENUS_SOURCES="sharepoint,onedrive,network")
    with pytest.raises(SystemExit) as caught:
        check_startup(settings, "127.0.0.1", "http")
    text = str(caught.value)
    assert "INGENUS_AUTH=entra" in text
    assert "INGENUS_SP_SITE_URL" in text
    assert "INGENUS_OD_FOLDER" in text
    assert "INGENUS_NETWORK_ROOT" in text


def test_start_up_refuses_an_unknown_source_name(isolated_env, monkeypatch):
    with pytest.raises(SystemExit) as caught:
        check_startup(settings_with(monkeypatch, INGENUS_SOURCES="local,ftp"), "127.0.0.1", "http")
    assert "ftp" in str(caught.value)


def test_start_up_accepts_a_complete_three_source_setup(isolated_env, monkeypatch, tmp_path):
    settings = settings_with(
        monkeypatch,
        INGENUS_SOURCES="sharepoint,onedrive,network",
        INGENUS_AUTH="entra",
        INGENUS_TENANT_ID="t",
        INGENUS_SERVER_CLIENT_ID="c",
        INGENUS_SP_SITE_URL="https://x.sharepoint.com/sites/s",
        INGENUS_OD_FOLDER="Ingenus_POC/contracts",
        INGENUS_NETWORK_ROOT=str(tmp_path),
    )
    check_startup(settings, "127.0.0.1", "http")  # does not raise


# --- the synthetic chains, read through two sources at once -----------------------------------


@pytest.mark.parametrize(
    ("dataset", "kind", "chains"),
    [
        ("Sharepoint", "local", ("Chain_A", "Chain_B")),
        ("Network-Drive", "network", ("Chain_E", "Chain_F")),
    ],
)
def test_the_synthetic_chains_give_their_expected_numbers_through_two_sources(
    dataset, kind, chains, monkeypatch
):
    """Chain A and B stand in for SharePoint (as the local source), E and F for the network drive."""
    from datetime import date
    from decimal import Decimal

    from test_v1_datasets import SYNTHETIC, as_terms, golden

    from ingenus_mcp.tools.compare_contract_to_sap import compare_contract_to_sap

    monkeypatch.setenv("INGENUS_SOURCES", "local,network")
    monkeypatch.setenv("INGENUS_CONTRACTS_DIR", str(SYNTHETIC / "Sharepoint"))
    monkeypatch.setenv("INGENUS_NETWORK_ROOT", str(SYNTHETIC / "Network-Drive"))
    expected, terms = golden(dataset)
    for customer_id, e in expected.items():
        raw = terms[customer_id]
        for t in raw:  # the same terms, with the source in front of each document id
            t["document"] = f"{kind}:{t['document'].split(':', 1)[-1]}"
        found = contracts.find_contract_files(load_settings(), e["customer"], None)
        assert found.files and {f.source for f in found.files} == {kind}
        assert found.complete
        result = compare_contract_to_sap(
            customer_id=customer_id, as_of=date.fromisoformat(e["as_of"]), terms=as_terms(raw)
        )
        assert result.not_checked == [], result.not_checked
        assert result.total_monthly_gap == Decimal(e["gap"])
        assert result.total_indicative_exposure == Decimal(e["exposure"])


def test_each_source_is_built_in_the_request_thread_so_it_can_see_the_signed_in_user(isolated_env):
    """SharePoint and OneDrive read the user from the request context, which a worker thread lacks.

    Seen live on 23 Oct 2026: both were reported as 'needs a signed-in user' although the user was signed in.
    """
    from ingenus_mcp.core import auth

    def builder(_settings, kind):
        if auth.current_token() is None:
            raise PermissionError("Reading SharePoint or OneDrive needs a signed-in user.")
        return FakeSource(kind, {f"{kind}/x.pdf": "1"})

    src = RoutedSource(load_settings(), ("sharepoint", "onedrive"), builder=builder)
    with signed_in_as("tester@example.com", "oid-1"):
        items = src.list_items()
    assert sorted(i.rel_path for i in items) == [
        "onedrive:onedrive/x.pdf",
        "sharepoint:sharepoint/x.pdf",
    ]
    assert all(s.ok for s in src.statuses), [s.reason for s in src.statuses]


def test_a_source_that_cannot_be_built_is_reported_and_the_others_still_list(isolated_env):
    def builder(_settings, kind):
        if kind == "sharepoint":
            raise PermissionError("no sign-in")
        return FakeSource(kind, {"E/e.pdf": "1"})

    src = RoutedSource(load_settings(), ("sharepoint", "network"), builder=builder)
    assert [i.rel_path for i in src.list_items()] == ["network:E/e.pdf"]
    bad = next(s for s in src.statuses if s.source == "sharepoint")
    assert bad.ok is False and bad.reason == "no sign-in"
