"""2.3: shared check history (decision 0006): what earlier checks found, for the next person.

Offline. People are played by `signed_in_as`; "can this person open the file?" is a stub where it matters.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

import pytest
from test_v1_compare import CHAIN_X  # noqa: F401
from v1_support import (  # noqa: F401  (pytest fixtures and helpers)
    AMEND2,
    chain_x_terms,
    isolated_env,
    make_world,
    signed_in_as,
    term,
)

from ingenus_mcp.core import history, sources
from ingenus_mcp.core.config import load_settings
from ingenus_mcp.core.registry import TOOLS
from ingenus_mcp.tools.compare_contract_to_sap import compare_contract_to_sap
from ingenus_mcp.tools.get_check_history import get_check_history

SRIDHAR = ("sridhar@example.test", "oid-sridhar")
ADITYA = ("aditya@example.test", "oid-aditya")


def check_chain_x(as_of=date(2026, 8, 31)):
    return compare_contract_to_sap(customer_id=CHAIN_X, as_of=as_of, terms=chain_x_terms())


def test_a_check_leaves_a_record_the_next_person_can_read():
    with signed_in_as(*SRIDHAR):
        check_chain_x()
    with signed_in_as(*ADITYA):
        result = get_check_history(document_id=AMEND2)
    assert result.available and len(result.records) == 1
    record = result.records[0]
    assert record.who == SRIDHAR[0] and record.is_you is False
    assert record.customer_id == CHAIN_X and record.as_of == "2026-08-31"
    assert Decimal(record.total_monthly_gap) == Decimal("8500.00")
    assert Decimal(record.total_indicative_exposure) == Decimal("17000.00")
    assert record.not_checked_count == 0
    statuses = {(line.product, line.status) for line in record.lines}
    assert ("Product A", "variance") in statuses and ("Product B", "match") in statuses
    assert [d.document_id for d in record.documents] == [AMEND2]
    assert record.documents[0].changed_since is False
    assert "not new findings" in result.note


def test_you_are_marked_as_you():
    with signed_in_as(*SRIDHAR):
        check_chain_x()
        assert get_check_history(customer_id=CHAIN_X).records[0].is_you is True


def test_records_are_newest_first_and_the_limit_applies():
    with signed_in_as(*SRIDHAR):
        check_chain_x(date(2026, 8, 31))
    with signed_in_as(*ADITYA):
        check_chain_x(date(2026, 7, 31))
        result = get_check_history(customer_id=CHAIN_X, limit=1)
    assert [r.who for r in result.records] == [ADITYA[0]]
    with signed_in_as(*ADITYA):
        both = get_check_history(customer_id=CHAIN_X)
    assert [r.who for r in both.records] == [ADITYA[0], SRIDHAR[0]]


def test_no_page_text_quotes_or_tokens_are_stored():
    with signed_in_as(*SRIDHAR):
        check_chain_x()
    db = load_settings().history_db
    dump = "\n".join(sqlite3.connect(db).iterdump())
    assert "Product A rebate: 6.0% of net sales" not in dump  # the quotes are not kept
    assert "net sales of Product" not in dump
    assert "t-oid-sridhar" not in dump  # the test token


def test_a_person_who_cannot_open_the_file_does_not_see_its_history(monkeypatch):
    with signed_in_as(*SRIDHAR):
        check_chain_x()

    real = sources.get_source

    class Denied:
        identity = "denied"
        revalidate_seconds = 0.0

        def stat(self, rel_path):
            raise PermissionError("this person may not open the file")

    monkeypatch.setattr(
        history,
        "get_source",
        lambda settings: Denied() if "bob" in (_who() or "") else real(settings),
    )

    def _who():
        from ingenus_mcp.core import auth

        return auth.current_user_name()

    with signed_in_as("bob@example.test", "oid-bob"):
        by_file = get_check_history(document_id=AMEND2)
        by_customer = get_check_history(customer_id=CHAIN_X)
    assert by_file.records == [] and "cannot open that file" in by_file.note
    assert by_customer.records == [] and by_customer.hidden_count == 1
    assert (
        "Chain_X_Amendment_2_2026" not in by_customer.model_dump_json()
    )  # nothing about the file leaks
    with signed_in_as(*ADITYA):  # someone who can open it still sees it
        assert len(get_check_history(customer_id=CHAIN_X).records) == 1


def test_a_changed_file_is_flagged(make_world):
    doc = make_world(
        ["Widget rebate: 5.0% of net sales of Widget."],
        [{"kind": "rebate", "product": "Widget", "rate_pct": "4.0", "basis": "product_net_sales"}],
        [{"month": "2026-07", "product": "Widget", "net_sales": "100000.00"}],
    )
    t = term(
        "rebate", "Widget", "5", "Widget rebate: 5.0% of net sales of Widget.", document=doc, page=1
    )
    with signed_in_as(*SRIDHAR):
        compare_contract_to_sap(customer_id="T-1", as_of=date(2026, 7, 31), terms=[t])
    with signed_in_as(*ADITYA):
        assert get_check_history(document_id=doc).records[0].documents[0].changed_since is False

    path = load_settings().contracts_dir / doc
    path.write_text("Widget rebate: 6.0% of net sales of Widget. (amended)", encoding="utf-8")
    from ingenus_mcp.core import documents

    documents.clear_cache()
    with signed_in_as(*ADITYA):
        again = get_check_history(document_id=doc)
    assert (
        again.records[0].documents[0].changed_since is True
    )  # the earlier figures may be out of date


def test_it_needs_a_file_or_a_customer():
    with pytest.raises(ValueError, match="document_id or a customer_id"):
        get_check_history()


def test_nothing_recorded_gives_a_plain_note():
    result = get_check_history(customer_id="SYN-CUST-0001")
    assert result.available and result.records == [] and "No earlier check" in result.note


def test_history_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("INGENUS_HISTORY_DB", "off")
    check_chain_x()  # still answers
    result = get_check_history(customer_id=CHAIN_X)
    assert result.available is False and "switched off" in result.note


def test_a_history_store_that_cannot_be_written_does_not_fail_the_check(
    tmp_path, monkeypatch, capsys
):
    blocker = tmp_path / "plain_file"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("INGENUS_HISTORY_DB", str(blocker / "history.sqlite"))
    result = check_chain_x()
    assert result.total_monthly_gap == Decimal("8500.00")  # the answer is unaffected
    assert "could not save the check record" in capsys.readouterr().err


def test_the_history_tool_is_read_only_and_registered():
    assert TOOLS["get_check_history"].read_only is True
