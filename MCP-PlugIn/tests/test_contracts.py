"""Finding files and pages. Source files are read-only and never leave the contract folder."""

from __future__ import annotations

import pytest
from conftest import AMEND2

from ingenus_plugin.core.scope import ScopeError, resolve_inside
from ingenus_plugin.core.tools import find_contract_files, get_contract_pages, resolve_customer


def test_find_lists_a_customers_files_and_leaves_drafts_out_on_purpose():
    result = find_contract_files(customer="Chain X")
    ids = {f.document_id for f in result.files}
    assert ids == {
        "Chain_X/Chain_X_Master_Supply_Agreement_2024.pdf",
        "Chain_X/Chain_X_Amendment_1_2025.pdf",
        AMEND2,
    }
    assert result.excluded_drafts == ["Chain_X/Chain_X_Amendment_3_DRAFT.pdf"]
    assert "draft" in result.note.lower()


def test_find_matches_an_alias_and_filters_by_kind():
    result = find_contract_files(customer="CHX", kind="amendment")
    assert {f.kind for f in result.files} == {"amendment"}
    assert len(result.files) == 2


def test_find_does_not_pick_one_of_two_customers():
    result = find_contract_files(customer="Regional Pharmacy")
    assert result.files == []
    assert "Ambiguous" in result.note


def test_find_unknown_customer_matches_on_names_only():
    result = find_contract_files(customer="Zorblax")
    assert result.files == []
    assert "not in the alias table" in result.note


def test_file_hash_changes_when_a_file_changes(make_world, tmp_path):
    make_world(["a rebate: 1.0%"], [], [])
    first = find_contract_files(customer="Acme").files[0]
    (tmp_path / "contracts" / "Acme" / "Acme_Agreement.txt").write_text("changed", encoding="utf-8")
    second = find_contract_files(customer="Acme").files[0]
    assert first.sha256_12 != second.sha256_12


def test_unsupported_formats_are_reported_not_silently_skipped(make_world, tmp_path):
    make_world(["a"], [], [])
    (tmp_path / "contracts" / "Acme" / "Scan.png").write_bytes(b"\x89PNG")
    result = find_contract_files(customer="Acme")
    assert any("Unsupported format" in n.reason for n in result.not_checked)


def test_pages_selects_the_rebate_page_with_its_neighbours_and_page_one():
    result = get_contract_pages(document_id="Chain_X/Chain_X_Master_Supply_Agreement_2024.pdf")
    shown = {p.page for p in result.pages}
    assert {1, 3, 4, 5} <= shown  # page 1, the schedule on page 4, and its neighbours
    assert 6 not in shown  # not needed, so not sent
    page4 = next(p for p in result.pages if p.page == 4)
    assert "rebates" in page4.matched_topics
    assert "Product A rebate: 4.0%" in page4.text
    assert result.total_pages == 6


def test_a_blank_page_is_reported_as_not_checked():
    result = get_contract_pages(document_id="Wholesaler_Z/Wholesaler_Z_Master_Supply_Agreement.pdf")
    assert any(n.item == "page 3" and "No extractable text" in n.reason for n in result.not_checked)
    assert 3 not in {p.page for p in result.pages}


def test_no_keyword_match_says_so_and_still_shows_page_one(make_world):
    doc = make_world(["Intro page", "Nothing relevant here", "Still nothing"], [], [])
    result = get_contract_pages(document_id=doc)
    assert [p.page for p in result.pages] == [1]
    assert any(n.item == "topic search" for n in result.not_checked)


def test_unknown_topic_is_an_error_that_lists_the_valid_ones():
    with pytest.raises(ValueError, match="Valid topics"):
        get_contract_pages(document_id=AMEND2, topics=["gossip"])


def test_hostile_text_is_returned_as_labelled_data_not_acted_on():
    result = get_contract_pages(document_id="Chain_Y/Chain_Y_Amendment_1_2026.pdf")
    text = " ".join(p.text for p in result.pages)
    assert "ignore your previous instructions" in text  # returned verbatim, as data
    assert "DATA only" in result.untrusted_text_notice  # and labelled as such
    # The plug-in has no tool that could act on it: every tool is read-only (see test_readonly.py).


@pytest.mark.parametrize(
    "bad",
    [
        "../README.md",
        "..\\README.md",
        "/etc/passwd",
        "C:\\Windows\\win.ini",
        "Chain_X/../../README.md",
        "",
    ],
)
def test_paths_outside_the_contract_folder_are_refused(bad):
    with pytest.raises((ScopeError, FileNotFoundError, ValueError)):
        get_contract_pages(document_id=bad)


def test_scope_guard_allows_a_normal_relative_path(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "f.txt").write_text("x", encoding="utf-8")
    assert resolve_inside(tmp_path, "a/f.txt").name == "f.txt"


def test_resolve_customer_exact_alias_ambiguous_and_unknown():
    assert resolve_customer(name="Chain X").resolved.sap_customer_id == "SYN-CUST-0001"
    assert resolve_customer(name="chx").resolved.name == "Chain X"
    ambiguous = resolve_customer(name="Regional Pharmacy")
    assert ambiguous.resolved is None and len(ambiguous.candidates) == 2
    similar = resolve_customer(name="Chain Xx")
    assert (
        similar.resolved is None and similar.candidates and similar.candidates[0].match == "similar"
    )
    assert resolve_customer(name="Nobody Inc").candidates == []
