"""Stored contract terms (decision 0011): kept after a check, returned while the file is unchanged, set aside when it changes."""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from v1_support import chain_x_terms, isolated_env, make_world, term  # noqa: F401  (pytest fixtures)

from ingenus_mcp.core import documents, records
from ingenus_mcp.core.config import load_settings
from ingenus_mcp.tools.compare_contract_to_sap import compare_contract_to_sap
from ingenus_mcp.tools.get_contract_terms import get_contract_terms

CHAIN_X = "SYN-CUST-0001"


@pytest.fixture(autouse=True)
def fresh_cache():
    documents.clear_cache()
    yield
    documents.clear_cache()


def check(terms=None, as_of=date(2026, 8, 31)):
    return compare_contract_to_sap(customer_id=CHAIN_X, as_of=as_of, terms=terms or chain_x_terms())


def by_action(result):
    return {d.filename: d.action for d in result.documents}


def test_before_any_check_nothing_is_stored_and_every_file_is_to_be_read():
    result = get_contract_terms("Chain X")
    assert result.customer_id == CHAIN_X and result.stored == []
    assert set(by_action(result).values()) == {"read_pages"}
    assert result.storing_enabled is True


def test_a_checked_term_comes_back_for_the_next_person_and_the_file_is_not_read_again():
    check()
    result = get_contract_terms("Chain X")
    assert len(result.stored) == 4  # A, B, C and the fee, from Amendment 2
    assert by_action(result)["Chain_X_Amendment_2_2026.pdf"] == "use_stored_terms"
    assert by_action(result)["Chain_X_Master_Supply_Agreement_2024.pdf"] == "read_pages"
    first = result.stored[0]
    assert first.status == "verified" and first.verified_by
    assert first.term.citation.quote and first.term.citation.page >= 1


def test_the_stored_terms_give_the_same_numbers_when_passed_back_to_compare():
    original = check()
    stored = [s.term for s in get_contract_terms("Chain X").stored]
    again = check(stored)
    assert again.total_monthly_gap == original.total_monthly_gap == Decimal("8500.00")
    assert again.total_indicative_exposure == original.total_indicative_exposure
    assert again.not_checked == []


def test_saving_the_same_terms_twice_is_one_record():
    check()
    check()
    assert len(get_contract_terms("Chain X").stored) == 4


def test_a_term_that_fails_the_quote_check_is_not_stored():
    bad = term("rebate", "Product A", "6", "A quote that is not on the page at all.")
    check([bad])
    assert get_contract_terms("Chain X").stored == []


def test_a_changed_file_sets_its_terms_aside_and_is_read_again(make_world, tmp_path, monkeypatch):
    doc = make_world(
        ["Widget rebate: 5.0% of net sales of Widget."],
        [{"kind": "rebate", "product": "Widget", "rate_pct": "4.0", "basis": "product_net_sales"}],
        [{"month": "2026-05", "product": "Widget", "net_sales": "100000.00"}],
    )
    t = term(
        "rebate", "Widget", "5", "Widget rebate: 5.0% of net sales of Widget.", document=doc, page=1
    )
    compare_contract_to_sap(customer_id="T-1", as_of=date(2026, 5, 31), terms=[t])
    stored = records.lookup(load_settings(), "T-1", _files(doc))
    assert len(stored[0]) == 1 and stored[1] == 0

    contract = tmp_path / "contracts" / doc
    contract.write_text("Widget rebate: 6.0% of net sales of Widget.", encoding="utf-8")  # changed
    documents.clear_cache()
    again = records.lookup(load_settings(), "T-1", _files(doc))
    assert again[0] == [] and again[1] == 1  # set aside, not returned
    assert records.lookup(load_settings(), "T-1", _files(doc)) == ([], 0)  # and stays set aside
    changed: set[str] = set()
    records.lookup(load_settings(), "T-1", _files(doc), changed)
    assert changed == {_files(doc)[0].document_id}  # still named as changed on the next call


def _files(doc):
    from ingenus_mcp.core import contracts

    return contracts.find_contract_files(load_settings(), "Acme", None).files


def test_a_file_that_is_not_in_the_listing_returns_nothing(monkeypatch):
    check()
    settings = load_settings()
    assert records.lookup(settings, CHAIN_X, []) == (
        [],
        0,
    )  # a person who cannot see the files sees no terms


def test_the_store_keeps_quotes_but_no_page_text_or_tokens():
    check()
    path = load_settings().records_db
    with sqlite3.connect(path) as conn:
        dump = "\n".join(conn.iterdump())
    assert "Product A rebate: 6.0% of net sales of Product A." in dump  # the quote, by design
    assert "BEGIN TRANSACTION" in dump and "Bearer" not in dump and "access_token" not in dump


def test_stored_terms_are_pruned_after_the_retention_time():
    check()
    target = load_settings().records_db
    old = (datetime.now(UTC) - timedelta(days=91)).isoformat(timespec="milliseconds")
    with sqlite3.connect(target) as conn:
        conn.execute("UPDATE term SET last_used = ?", (old,))
    cutoff = (datetime.now(UTC) - timedelta(days=90)).isoformat(timespec="milliseconds")
    assert records.prune(target, cutoff) == 4
    assert get_contract_terms("Chain X").stored == []


def test_using_the_terms_keeps_them_from_expiring():
    check()
    target = load_settings().records_db
    old = (datetime.now(UTC) - timedelta(days=91)).isoformat(timespec="milliseconds")
    with sqlite3.connect(target) as conn:
        conn.execute("UPDATE term SET last_used = ?", (old,))
    get_contract_terms("Chain X")  # reading them restarts the clock
    cutoff = (datetime.now(UTC) - timedelta(days=90)).isoformat(timespec="milliseconds")
    assert records.prune(target, cutoff) == 0


def test_with_the_store_off_nothing_is_kept_and_every_file_is_read(monkeypatch):
    monkeypatch.setenv("INGENUS_RECORDS_DB", "off")
    check()
    result = get_contract_terms("Chain X")
    assert result.storing_enabled is False and result.stored == []
    assert set(by_action(result).values()) == {"read_pages"}


def test_an_unknown_customer_gets_a_plain_message_and_no_files():
    result = get_contract_terms("Zorblax")
    assert result.customer_id is None and result.documents == []
    assert result.note


def test_a_store_error_never_fails_the_check(monkeypatch, tmp_path):
    monkeypatch.setenv("INGENUS_RECORDS_DB", str(tmp_path / "no_such_dir" / "x" / "records.sqlite"))
    result = check()  # the answer still comes back
    assert result.total_monthly_gap == Decimal("8500.00")
