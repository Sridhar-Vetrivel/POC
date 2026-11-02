"""Keyword search over stored passages (decision 0012): needs the local Postgres of test_v1_postgres (skips without it)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from test_v1_postgres import pg_env  # noqa: F401  (pytest fixture)
from v1_support import isolated_env, make_world  # noqa: F401  (pytest fixtures)

from ingenus_mcp.core import contracts, documents, passages
from ingenus_mcp.core.config import load_settings
from ingenus_mcp.tools.search_contracts import search_contracts


@pytest.fixture(autouse=True)
def fresh_cache():
    documents.clear_cache()
    yield
    documents.clear_cache()


@pytest.fixture
def pg(pg_env, monkeypatch):  # noqa: F811
    monkeypatch.delenv("INGENUS_RECORDS_DB")  # isolated_env points it at a file; Postgres wins here
    return load_settings().records_db


def list_files(customer: str):
    return contracts.find_contract_files(load_settings(), customer, None)


def count(target) -> int:
    with passages._session(target) as conn:
        return int(conn.execute("SELECT count(*) FROM passage").fetchone()[0])


def test_split_page_makes_a_heading_the_section_of_what_follows():
    text = "3. Returns\n\nSeller shall accept the return of expired goods.\n\n4. Payment\n\nNet 30 days."
    assert passages.split_page(text) == [
        ("3. Returns", "Seller shall accept the return of expired goods."),
        ("4. Payment", "Net 30 days."),
    ]


def test_split_page_cuts_a_long_paragraph_on_sentence_ends():
    sentence = "The seller shall pay the buyer a rebate as set out in this schedule."
    pieces = passages.split_page(" ".join([sentence] * 40))
    assert len(pieces) > 1
    assert all(len(p) <= passages.MAX_CHARS for _, p in pieces)
    assert all(p.endswith(".") for _, p in pieces)


def test_a_capitalised_heading_is_a_section_and_body_lines_with_a_colon_or_percent_are_kept():
    page = (
        "5. PAYMENT AND RETURNS\nPayment terms: net 45 days.\nReturns: none.\n"
        "Product A rebate 6.0% of sales"
    )
    assert passages.split_page(page) == [
        (
            "5. PAYMENT AND RETURNS",
            "Payment terms: net 45 days. Returns: none. Product A rebate 6.0% of sales",
        )
    ]


def test_the_heading_is_searched_with_the_text(pg, make_world):
    make_world(["5. PAYMENT AND RETURNS\nPayment terms: net 45 days from invoice date."], [], [])
    list_files("Acme")
    hit = search_contracts("returns").hits[0]
    assert hit.section == "5. PAYMENT AND RETURNS" and "net 45" in hit.text


def test_a_page_without_blank_lines_is_packed_not_lost():
    assert passages.split_page("Line one has words.\nLine two has more words.") == [
        (None, "Line one has words. Line two has more words.")
    ]


def test_nothing_is_found_before_anyone_has_listed_the_files(pg):
    result = search_contracts("rebate", "Chain X")
    assert result.available is True and result.hits == []


def test_after_listing_a_search_finds_the_clause_with_file_and_page(pg):
    list_files("Chain X")
    result = search_contracts("rebate", "Chain X")
    assert result.available and result.complete and result.hits
    top = result.hits[0]
    assert "rebate" in top.text.lower() and top.page >= 1 and top.filename.endswith(".pdf")
    assert top.document_id.endswith(top.filename)


def test_listing_twice_stores_each_passage_once(pg):
    list_files("Chain X")
    first = count(pg)
    passages._SAVED.clear()  # as after a restart: it saves again, and must not double
    list_files("Chain X")
    assert first > 0 and count(pg) == first


def test_search_is_narrowed_by_customer(pg):
    list_files("Chain X")
    assert search_contracts("rebate", "Chain X").hits
    assert search_contracts("rebate", "Chain Y").hits == []


def test_a_changed_file_replaces_its_passages(pg, make_world, tmp_path):
    rel = make_world(["Returns: expired goods may be returned within 30 days."], [], [])
    list_files("Acme")
    assert search_contracts("expired goods").hits
    (tmp_path / "contracts" / rel).write_text(
        "Payment: invoices are due in 45 days.", encoding="utf-8"
    )
    documents.clear_cache()
    list_files("Acme")
    assert search_contracts("expired goods").hits == []
    assert search_contracts("invoices").hits


def test_a_stale_passage_is_not_shown_if_the_file_changed_and_nobody_listed_it(
    pg, make_world, tmp_path
):
    rel = make_world(["Returns: expired goods may be returned within 30 days."], [], [])
    list_files("Acme")
    (tmp_path / "contracts" / rel).write_text("Payment: due in 45 days.", encoding="utf-8")
    documents.clear_cache()
    result = search_contracts(
        "expired goods"
    )  # the search itself opens the file and sees the change
    assert result.hits == []
    assert search_contracts("due days").hits  # the search saved the file as it is now


def test_a_file_the_person_cannot_open_is_left_out_and_the_result_says_so(pg, make_world, tmp_path):
    rel = make_world(["Returns: expired goods may be returned within 30 days."], [], [])
    list_files("Acme")
    (tmp_path / "contracts" / rel).unlink()
    documents.clear_cache()
    result = search_contracts("expired goods")
    assert result.hits == [] and result.complete is False
    assert [n.item for n in result.not_checked] == [rel]


def test_passage_text_never_reaches_the_audit_log(pg, make_world, tmp_path):
    make_world(["Returns: expired goods may be returned within 30 days."], [], [])
    list_files("Acme")
    assert search_contracts("expired goods").hits
    log = load_settings().log_path.read_text(encoding="utf-8")
    assert "search_contracts" in log and "may be returned within 30 days" not in log


def test_passages_are_pruned_by_last_use_and_using_them_restarts_the_clock(pg):
    list_files("Chain X")
    old = (datetime.now(UTC) - timedelta(days=91)).isoformat(timespec="milliseconds")
    cutoff = (datetime.now(UTC) - timedelta(days=90)).isoformat(timespec="milliseconds")
    with passages._session(pg) as conn:
        conn.execute("UPDATE passage SET last_used = %(old)s", {"old": old})
    assert search_contracts("rebate", "Chain X").hits  # returned passages get a new last_used
    removed = passages.prune(pg, cutoff)
    assert removed > 0 and search_contracts("rebate", "Chain X").hits


def test_an_unknown_customer_gets_a_plain_message_and_no_hits(pg):
    result = search_contracts("rebate", "Zorblax")
    assert result.hits == [] and result.note


def test_an_empty_query_is_refused_plainly(pg):
    assert search_contracts("   ").note == "Empty query."


def test_without_postgres_search_says_it_is_not_available():
    result = search_contracts("rebate")  # isolated_env: records are a SQLite file
    assert result.available is False and "not available" in result.note
    assert passages.save(load_settings(), "x.pdf", "abc", ("text",)) == 0
