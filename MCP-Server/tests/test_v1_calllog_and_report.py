"""The tool-call log is the adoption measure. It records calls, never whole documents."""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import pytest
from v1_support import AMEND2, chain_x_terms, isolated_env, make_world  # noqa: F401  (pytest fixtures)

from ingenus_mcp.report import load_records, summarise_usage
from ingenus_mcp.tools.compare_contract_to_sap import compare_contract_to_sap
from ingenus_mcp.tools.find_contract_files import find_contract_files
from ingenus_mcp.tools.get_contract_pages import get_contract_pages
from ingenus_mcp.tools.resolve_customer import resolve_customer


def log_lines() -> list[dict]:
    path = Path(os.environ["INGENUS_LOG_PATH"])
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_each_call_writes_one_json_line_with_user_tool_and_result_summary():
    resolve_customer(name="Chain X")
    (record,) = log_lines()
    assert record["tool"] == "resolve_customer"
    assert record["user"] == "tester"
    assert record["args"] == {"name": "Chain X"}
    assert record["result"]["type"] == "ResolveCustomerResult"
    assert record["error"] is None
    assert record["duration_ms"] >= 0
    assert record["ts"].endswith("+00:00")


def test_the_log_never_holds_page_text():
    get_contract_pages(document_id=AMEND2)
    raw = Path(os.environ["INGENUS_LOG_PATH"]).read_text(encoding="utf-8")
    assert "Schedule A is deleted and replaced" not in raw
    assert "Administrative fee" not in raw
    (record,) = log_lines()
    assert record["result"]["pages_count"] >= 1  # counts only


def test_not_checked_count_is_logged():
    compare_contract_to_sap(customer_id="SYN-CUST-0001", as_of=date(2026, 8, 31), terms=[])
    (record,) = log_lines()
    assert record["tool"] == "compare_contract_to_sap"
    assert record["not_checked_count"] == 0


def test_compare_logs_the_extracted_terms_it_was_given():
    compare_contract_to_sap(
        customer_id="SYN-CUST-0001", as_of=date(2026, 8, 31), terms=chain_x_terms()
    )
    (record,) = log_lines()
    quotes = [t["citation"]["quote"] for t in record["args"]["terms"]]
    assert "Product A rebate: 6.0% of net sales of Product A." in quotes


def test_an_error_is_logged_and_still_raised():
    with pytest.raises(ValueError):
        get_contract_pages(document_id=AMEND2, topics=["gossip"])
    (record,) = log_lines()
    assert record["error"].startswith("ValueError")
    assert record["result"] is None


def test_a_logging_failure_never_breaks_a_tool(monkeypatch, tmp_path):
    blocked = tmp_path / "file_not_dir"
    blocked.write_text("x", encoding="utf-8")
    monkeypatch.setenv(
        "INGENUS_LOG_PATH", str(blocked / "log.jsonl")
    )  # parent is a file: cannot write
    assert find_contract_files(customer="Chain X").files  # the tool still answers


def test_usage_report_counts_users_tools_days_and_returning_users(tmp_path):
    rows = [
        {
            "ts": "2026-10-13T09:00:00+00:00",
            "user": "abhishek",
            "tool": "resolve_customer",
            "not_checked_count": None,
        },
        {
            "ts": "2026-10-13T09:01:00+00:00",
            "user": "abhishek",
            "tool": "compare_contract_to_sap",
            "not_checked_count": 2,
        },
        {
            "ts": "2026-10-14T09:00:00+00:00",
            "user": "abhishek",
            "tool": "resolve_customer",
            "not_checked_count": None,
        },
        {
            "ts": "2026-10-14T10:00:00+00:00",
            "user": "dan",
            "tool": "resolve_customer",
            "not_checked_count": None,
            "error": "ValueError: x",
        },
    ]
    path = tmp_path / "log.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n{half a line", encoding="utf-8")
    summary = summarise_usage(load_records(path))
    assert summary["total_calls"] == 4
    assert summary["distinct_users"] == 2
    assert summary["returning_users"] == ["abhishek"]
    assert summary["calls_per_tool"]["resolve_customer"] == 3
    assert summary["calls_per_day"] == {"2026-10-13": 2, "2026-10-14": 2}
    assert summary["calls_with_errors"] == 1
    assert summary["items_reported_not_checked"] == 2
