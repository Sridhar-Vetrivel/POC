"""V1-7: reading contracts from the signed-in user's own OneDrive, through the same Graph code.

Offline: the fake Graph from test_v1_graph_source answers `/me/drive` and the usual drive calls from the
local synthetic folder. The live check against a real OneDrive is by hand (see the checklist).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from test_v1_graph_source import (  # noqa: F401  (fixtures and helpers)
    AMEND2,
    FOLDER,
    FakeGraph,
    chain_x_terms,
    clean_state,
)
from v1_support import isolated_env  # noqa: F401

from ingenus_mcp.core import documents, graph
from ingenus_mcp.core.config import load_settings
from ingenus_mcp.core.sources import get_source
from ingenus_mcp.server.app import check_startup


@pytest.fixture(autouse=True)
def onedrive_folder(monkeypatch, clean_state):
    monkeypatch.setenv("INGENUS_OD_FOLDER", FOLDER)  # the fake serves the same tree under any drive


def onedrive_source(user="user-a", fake=None, bearer="graph-bearer-a"):
    fake = fake or FakeGraph(drive_id="od-drive-a")
    source = graph.GraphSource(
        load_settings(),
        user,
        lambda: bearer,
        session=fake,
        sleep=lambda s: None,
        location="onedrive",
    )
    return source, fake


def test_it_finds_the_users_own_drive_and_lists_the_30_files():
    source, fake = onedrive_source()
    assert len(source.list_items()) == 30
    assert any(url.endswith("/v1.0/me/drive") for url in fake.calls)
    assert not any("/sites/" in url for url in fake.calls)  # no SharePoint site is involved
    assert all("/drives/od-drive-a/" in u for u in fake.calls if "/drives/" in u)


def test_each_person_reads_their_own_drive():
    a, fake_a = onedrive_source("user-a", FakeGraph(drive_id="od-drive-a"))
    b, fake_b = onedrive_source("user-b", FakeGraph(drive_id="od-drive-b"))
    a.list_items()
    b.list_items()
    # The second person must not be sent to the first person's drive: the drive id is cached per person.
    assert all("od-drive-a" not in u for u in fake_b.calls)
    assert any("od-drive-b" in u for u in fake_b.calls)
    assert a.identity != b.identity


def test_the_text_is_cached_per_person():
    a, _ = onedrive_source("user-a", FakeGraph(drive_id="od-drive-a"))
    documents.load_document(a, AMEND2)
    b, _ = onedrive_source("user-b", FakeGraph(drive_id="od-drive-b", status=403))
    with pytest.raises(graph.GraphAccessError):
        documents.load_document(b, AMEND2)  # a's cached copy is not handed to b


def test_a_refusal_names_onedrive_and_the_consent_not_the_site():
    source, _ = onedrive_source(fake=FakeGraph(status=403))
    with pytest.raises(graph.GraphAccessError) as caught:
        source.list_items()
    assert "OneDrive refused access" in str(caught.value)
    assert "member of the site" not in str(caught.value)


def test_a_path_outside_the_folder_is_refused_before_any_request():
    from ingenus_mcp.core.scope import ScopeError

    source, fake = onedrive_source()
    with pytest.raises(ScopeError):
        source.stat("../other.pdf")
    assert fake.calls == []


def test_chain_x_from_onedrive_gives_the_agreed_numbers(monkeypatch):
    source, _ = onedrive_source()
    from ingenus_mcp.core import citations, contracts
    from ingenus_mcp.tools.compare_contract_to_sap import compare_contract_to_sap
    from ingenus_mcp.tools.find_contract_files import find_contract_files

    monkeypatch.setattr(contracts, "get_source", lambda settings: source)
    monkeypatch.setattr(citations, "get_source", lambda settings: source)
    assert find_contract_files(customer="Chain X").files
    result = compare_contract_to_sap(
        customer_id="SYN-CUST-0001", as_of=date(2026, 8, 31), terms=chain_x_terms()
    )
    assert result.total_monthly_gap == Decimal("8500.00")
    assert result.total_indicative_exposure == Decimal("17000.00")
    assert result.not_checked == []


def test_start_up_needs_sign_in_and_a_folder_for_onedrive(monkeypatch):
    monkeypatch.setenv("INGENUS_DOC_SOURCE", "onedrive")
    with pytest.raises(SystemExit, match="needs INGENUS_AUTH=entra"):
        check_startup(load_settings(), "127.0.0.1", "http")
    monkeypatch.setenv("INGENUS_AUTH", "entra")
    monkeypatch.setenv("INGENUS_TENANT_ID", "aaaaaaaa-0000-4000-8000-000000000001")
    monkeypatch.setenv("INGENUS_SERVER_CLIENT_ID", "bbbbbbbb-0000-4000-8000-000000000002")
    monkeypatch.delenv("INGENUS_OD_FOLDER")
    with pytest.raises(SystemExit, match="never the whole drive"):
        check_startup(load_settings(), "127.0.0.1", "http")
    monkeypatch.setenv("INGENUS_OD_FOLDER", FOLDER)
    check_startup(load_settings(), "127.0.0.1", "http")  # fine now


def test_get_source_knows_onedrive(monkeypatch):
    monkeypatch.setenv("INGENUS_DOC_SOURCE", "onedrive")
    with pytest.raises(graph.GraphAuthError):  # no signed-in user in a plain test, but it is routed
        get_source(load_settings())
