"""SAP reads through the adapter interface (mock data only)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from ingenus_plugin.core.config import load_settings
from ingenus_plugin.core.sap import get_reader
from ingenus_plugin.core.tools import get_rebate_setup, get_sales_volume


def test_rebate_setup_for_chain_x():
    result = get_rebate_setup(customer_id="SYN-CUST-0001", as_of=date(2026, 8, 31))
    lines = {(line.kind, line.product): line.rate_pct for line in result.lines}
    assert lines == {
        ("admin_fee", None): Decimal("2.0"),
        ("rebate", "Product A"): Decimal("4.0"),
        ("rebate", "Product B"): Decimal("3.0"),
    }
    assert "synthetic" in result.source


def test_setup_respects_the_as_of_date():
    assert get_rebate_setup(customer_id="SYN-CUST-0001", as_of=date(2024, 6, 1)).lines == []


def test_unknown_customer_is_reported_not_guessed():
    result = get_rebate_setup(customer_id="NOPE", as_of=date(2026, 8, 31))
    assert result.lines == [] and "not found in SAP" in result.not_checked[0].reason


def test_sales_volume_for_a_period():
    result = get_sales_volume(
        customer_id="SYN-CUST-0001", period_start="2026-07", period_end="2026-08"
    )
    assert len(result.rows) == 6  # three products, two months
    assert {r.net_sales for r in result.rows if r.product == "Product A"} == {Decimal("200000.00")}


@pytest.mark.parametrize(
    "start,end", [("2026-7", "2026-08"), ("2026-13", "2026-12"), ("2026-09", "2026-08")]
)
def test_bad_periods_are_refused(start, end):
    with pytest.raises(ValueError):
        get_sales_volume(customer_id="SYN-CUST-0001", period_start=start, period_end=end)


def test_only_the_mock_adapter_is_wired_and_unknown_names_are_refused(monkeypatch):
    monkeypatch.setenv("INGENUS_SAP_ADAPTER", "prod")
    with pytest.raises(ValueError, match="Unknown SAP adapter"):
        get_reader(load_settings())
    monkeypatch.setenv("INGENUS_SAP_ADAPTER", "real")
    with pytest.raises(NotImplementedError):
        get_rebate_setup(customer_id="SYN-CUST-0001", as_of=date(2026, 8, 31))
