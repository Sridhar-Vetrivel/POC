"""The comparison is plain code: same inputs, same findings. Chain X must give the agreed numbers."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from v1_support import AMEND2, DRAFT3, MASTER, chain_x_terms, isolated_env, make_world, term  # noqa: F401  (pytest fixtures)

from ingenus_mcp.tools.compare_contract_to_sap import compare_contract_to_sap

CHAIN_X = "SYN-CUST-0001"


def run(terms, as_of=date(2026, 8, 31), customer=CHAIN_X):
    return compare_contract_to_sap(customer_id=customer, as_of=as_of, terms=terms)


def test_chain_x_gives_the_agreed_numbers():
    result = run(chain_x_terms())
    by_line = {(f.kind, f.product): f for f in result.findings}

    assert by_line[("rebate", "Product A")].status == "variance"
    assert by_line[("rebate", "Product A")].monthly_gap == Decimal("4000.00")
    assert by_line[("rebate", "Product B")].status == "match"
    assert by_line[("rebate", "Product B")].monthly_gap == Decimal("0.00")
    assert by_line[("rebate", "Product C")].status == "not_set_up_in_sap"
    assert by_line[("rebate", "Product C")].monthly_gap == Decimal("2500.00")
    assert by_line[("admin_fee", None)].monthly_gap == Decimal("2000.00")

    differing = [f for f in result.findings if f.status != "match"]
    assert len(differing) == 3  # three lines differ from SAP...
    assert len(result.findings) - len(differing) == 1  # ...and one matches
    assert result.total_monthly_gap == Decimal("8500.00")
    assert result.total_indicative_exposure == Decimal("17000.00")  # 1 Jul to 31 Aug, two months
    assert result.not_checked == []


def test_five_runs_are_identical():
    runs = {run(chain_x_terms()).model_dump_json() for _ in range(5)}
    assert len(runs) == 1


def test_output_does_not_depend_on_the_order_of_terms():
    forward = run(chain_x_terms()).model_dump_json()
    backward = run(list(reversed(chain_x_terms()))).model_dump_json()
    assert forward == backward


def test_admin_fee_with_a_product_label_still_pairs_with_sap():
    # Seen in the Claude Desktop demo (Q2, run A): the fee was sent as "All Products" and the
    # compare charged the full 2.5% as a gap, giving 16,500 / 33,000 instead of 8,500 / 17,000.
    terms = chain_x_terms()
    terms[3] = term(
        "admin_fee",
        "All Products",
        "2.5",
        "Administrative fee: 2.5% of total net sales of all Products.",
    )
    result = run(terms)
    fee = next(f for f in result.findings if f.kind == "admin_fee")
    assert fee.status == "variance"
    assert fee.sap_rate_pct == Decimal("2.0")
    assert fee.monthly_gap == Decimal("2000.00")
    assert result.total_monthly_gap == Decimal("8500.00")
    assert result.total_indicative_exposure == Decimal("17000.00")
    assert result.in_sap_not_in_contract_terms == []
    assert any("'All Products'" in c and "ignored" in c for c in result.caveats)
    assert not any("ignored" in c for c in run(chain_x_terms()).caveats)


def test_fabricated_quote_is_rejected_and_listed():
    terms = chain_x_terms()
    terms[0] = term("rebate", "Product A", "9", "Product A rebate: 9.0% of net sales of Product A.")
    result = run(terms)
    assert all(f.product != "Product A" for f in result.findings)
    assert any("not found on page 2" in n.reason for n in result.not_checked)
    assert result.total_monthly_gap == Decimal("4500.00")  # C 2,500 + fee 2,000 only


def test_real_quote_on_the_wrong_page_is_rejected():
    terms = [
        term(
            "rebate", "Product A", "6", "Product A rebate: 6.0% of net sales of Product A.", page=1
        )
    ]
    result = run(terms)
    assert result.findings == []
    assert any("not found on page 1" in n.reason for n in result.not_checked)


def test_quote_that_does_not_hold_the_rate_is_rejected():
    terms = [term("rebate", "Product A", "6", "Product B rebate: 3.0% of net sales of Product B.")]
    assert any("does not mention the product" in n.reason for n in run(terms).not_checked)
    terms = [term("rebate", "Product A", "9", "Product A rebate: 6.0% of net sales of Product A.")]
    assert any("does not contain the rate" in n.reason for n in run(terms).not_checked)


def test_document_outside_the_folder_is_rejected():
    terms = [term("rebate", "Product A", "6", "Product A rebate: 6.0%", document="../../README.md")]
    result = run(terms)
    assert result.findings == []
    assert any("rejected" in n.reason for n in result.not_checked)


def test_unknown_product_is_not_checked_not_guessed(make_world):
    doc = make_world(
        ["Gizmo rebate: 5.0% of net sales of Gizmo."],
        [{"kind": "rebate", "product": "Widget", "rate_pct": "4.0", "basis": "product_net_sales"}],
        [{"month": "2026-07", "product": "Widget", "net_sales": "100000.00"}],
    )
    t = term(
        "rebate", "Gizmo", "5", "Gizmo rebate: 5.0% of net sales of Gizmo.", document=doc, page=1
    )
    result = run([t], as_of=date(2026, 7, 31), customer="T-1")
    assert result.findings == []
    assert any("No SAP setup and no SAP sales" in n.reason for n in result.not_checked)


def test_missing_sap_sales_month_gives_a_partial_result_not_nothing():
    # Seen in the Claude Desktop demo (Q6, run A): September has no SAP sales, so every line was
    # dropped and Claude compared the rates itself. Now the rates are always compared in code, the
    # exposure counts only the months that have sales, and the missing month is listed.
    result = run(chain_x_terms(), as_of=date(2026, 9, 30))
    by_line = {(f.kind, f.product): f for f in result.findings}
    assert len(result.findings) == 4
    assert by_line[("rebate", "Product A")].status == "variance"
    assert by_line[("rebate", "Product B")].status == "match"
    assert by_line[("rebate", "Product C")].status == "not_set_up_in_sap"
    assert by_line[("admin_fee", None)].status == "variance"
    # July and August only: the same figures as 31 Aug, not a guess for September.
    assert result.total_monthly_gap == Decimal("8500.00")
    assert result.total_indicative_exposure == Decimal("17000.00")
    missing = [n for n in result.not_checked if "SAP sales missing for 2026-09" in n.reason]
    assert (
        len(missing) == 3
    )  # A, C and the fee; B matches, so its exposure is nil whatever September holds
    assert all("counts only 2026-07, 2026-08" in n.reason for n in missing)
    assert any("true exposure to the as_of date is likely larger" in c for c in result.caveats)


def test_no_sales_at_all_for_a_line_is_not_checked(make_world):
    doc = make_world(
        ["Widget rebate: 5.0% of net sales of Widget."],
        [{"kind": "rebate", "product": "Widget", "rate_pct": "4.0", "basis": "product_net_sales"}],
        [{"month": "2026-05", "product": "Widget", "net_sales": "100000.00"}],
    )
    t = term(
        "rebate", "Widget", "5", "Widget rebate: 5.0% of net sales of Widget.", document=doc, page=1
    )
    result = run([t], as_of=date(2026, 7, 31), customer="T-1")
    assert result.findings == []
    assert any("SAP sales missing for 2026-07" in n.reason for n in result.not_checked)


def test_a_matching_line_with_no_sales_in_its_period_is_a_match_not_unchecked(make_world):
    # Seen live (Chain E, 23 Oct 2026): the master's rates matched SAP but SAP had no sales for 2025, so
    # three lines were reported as not checked and Claude suggested the exposure could be higher.
    doc = make_world(
        [
            "Widget rebate: 4.0% of net sales of Widget.",
            "Widget rebate: 5.0% of net sales of Widget.",
        ],
        [{"kind": "rebate", "product": "Widget", "rate_pct": "4.0", "basis": "product_net_sales"}],
        [
            {"month": "2026-01", "product": "Widget", "net_sales": "100000.00"},
            {"month": "2026-02", "product": "Widget", "net_sales": "100000.00"},
        ],
    )
    master = term(
        "rebate",
        "Widget",
        "4",
        "Widget rebate: 4.0% of net sales of Widget.",
        document=doc,
        page=1,
        effective=date(2025, 2, 1),
    )
    amendment = term(
        "rebate",
        "Widget",
        "5",
        "Widget rebate: 5.0% of net sales of Widget.",
        document=doc,
        page=2,
        effective=date(2026, 1, 1),
    )
    result = run([master, amendment], as_of=date(2026, 2, 28), customer="T-1")
    assert result.not_checked == []
    by_date = {f.effective_date: f for f in result.findings}
    earlier = by_date[date(2025, 2, 1)]
    assert earlier.status == "match" and earlier.monthly_base is None
    assert earlier.monthly_gap == Decimal("0.00") and earlier.indicative_exposure == Decimal("0.00")
    assert by_date[date(2026, 1, 1)].status == "variance"
    assert result.total_monthly_gap == Decimal("1000.00")  # 1% of 100,000
    assert result.total_indicative_exposure == Decimal("2000.00")  # January and February
    assert any("no sales base is shown" in c for c in result.caveats)


def test_a_variance_with_no_sales_in_its_period_is_still_not_checked(make_world):
    doc = make_world(
        ["Widget rebate: 5.0% of net sales of Widget."],
        [{"kind": "rebate", "product": "Widget", "rate_pct": "4.0", "basis": "product_net_sales"}],
        [{"month": "2026-05", "product": "Widget", "net_sales": "100000.00"}],
    )
    t = term(
        "rebate",
        "Widget",
        "5",
        "Widget rebate: 5.0% of net sales of Widget.",
        document=doc,
        page=1,
        effective=date(2025, 2, 1),
    )
    result = run([t], as_of=date(2025, 12, 31), customer="T-1")  # a year with no sales at all
    assert result.findings == []  # a gap that cannot be sized is never guessed
    assert any("SAP sales missing" in n.reason for n in result.not_checked)


def test_unknown_customer_is_reported():
    result = run(chain_x_terms(), customer="SYN-CUST-9999")
    assert result.findings == []
    assert any("not found in SAP" in n.reason for n in result.not_checked)


def test_term_effective_after_as_of_is_not_compared():
    result = run(chain_x_terms(), as_of=date(2026, 6, 30))
    assert result.findings == []
    assert all("after the as_of date" in n.reason for n in result.not_checked)


def test_later_rate_replaces_earlier_rate_from_its_start_date():
    first = term("rebate", "Product A", "6", "Product A rebate: 6.0% of net sales of Product A.")
    later = term(
        "rebate",
        "Product A",
        "7",
        "Product A rebate: 7.0% of net sales of Product A.",
        document=DRAFT3,
        page=1,
        effective=date(2026, 8, 1),
    )
    result = run([first, later])
    exposure = sum(f.indicative_exposure for f in result.findings)
    # July at 6% against SAP 4%: 4,000. August at 7% against SAP 4%: 6,000.
    assert exposure == Decimal("10000.00")
    assert len(result.findings) == 2


def test_two_different_rates_for_the_same_date_are_a_conflict():
    one = term("rebate", "Product A", "6", "Product A rebate: 6.0% of net sales of Product A.")
    two = term(
        "rebate",
        "Product A",
        "7",
        "Product A rebate: 7.0% of net sales of Product A.",
        document=DRAFT3,
        page=1,
    )
    result = run([one, two])
    assert result.findings == []
    assert any("Two different rates" in n.reason for n in result.not_checked)


def test_partial_first_month_is_counted_by_days(make_world):
    doc = make_world(
        ["Widget rebate: 6.0% of net sales of Widget."],
        [{"kind": "rebate", "product": "Widget", "rate_pct": "4.0", "basis": "product_net_sales"}],
        [{"month": "2026-07", "product": "Widget", "net_sales": "310000.00"}],
    )
    t = term(
        "rebate",
        "Widget",
        "6",
        "Widget rebate: 6.0% of net sales of Widget.",
        document=doc,
        page=1,
        effective=date(2026, 7, 16),
    )
    result = run([t], as_of=date(2026, 7, 31), customer="T-1")
    # 16 of 31 days at a 2-point gap on 310,000 = 6,200 * 16/31 = 3,200
    assert result.findings[0].indicative_exposure == Decimal("3200.00")
    assert result.findings[0].monthly_gap == Decimal("6200.00")


def test_small_rate_difference_is_not_ignored(make_world):
    doc = make_world(
        ["Widget rebate: 5.56% of net sales of Widget."],
        [{"kind": "rebate", "product": "Widget", "rate_pct": "5.5", "basis": "product_net_sales"}],
        [{"month": "2026-07", "product": "Widget", "net_sales": "100000.00"}],
    )
    t = term(
        "rebate",
        "Widget",
        "5.56",
        "Widget rebate: 5.56% of net sales of Widget.",
        document=doc,
        page=1,
    )
    f = run([t], as_of=date(2026, 7, 31), customer="T-1").findings[0]
    assert f.status == "variance"
    assert f.monthly_gap == Decimal("60.00")


def test_contract_lower_than_sap_is_a_negative_gap(make_world):
    doc = make_world(
        ["Widget rebate: 3.0% of net sales of Widget."],
        [{"kind": "rebate", "product": "Widget", "rate_pct": "4.0", "basis": "product_net_sales"}],
        [{"month": "2026-07", "product": "Widget", "net_sales": "100000.00"}],
    )
    t = term(
        "rebate", "Widget", "3", "Widget rebate: 3.0% of net sales of Widget.", document=doc, page=1
    )
    result = run([t], as_of=date(2026, 7, 31), customer="T-1")
    assert result.total_monthly_gap == Decimal("-1000.00")
    assert "over-reserved" in result.summary


def test_sap_lines_missing_from_the_terms_are_listed():
    only_a = [chain_x_terms()[0]]
    result = run(only_a)
    assert any("Product B" in s for s in result.in_sap_not_in_contract_terms)
    assert any("admin fee" in s for s in result.in_sap_not_in_contract_terms)


def test_result_serialises_to_plain_json():
    payload = json.loads(run(chain_x_terms()).model_dump_json())
    assert payload["total_indicative_exposure"] == "17000.00"
    assert AMEND2 in {f["citation"]["document"] for f in payload["findings"]}


def test_before_the_amendment_the_master_agreement_rates_match_sap():
    """As at 30 Jun 2026 SAP still has the master agreement rates, so every line matches."""
    master = dict(document=MASTER, page=4, effective=date(2024, 1, 1))
    terms = [
        term(
            "rebate",
            "Product A",
            "4",
            "Product A rebate: 4.0% of net sales of Product A, paid quarterly.",
            **master,
        ),
        term(
            "rebate",
            "Product B",
            "3",
            "Product B rebate: 3.0% of net sales of Product B, paid quarterly.",
            **master,
        ),
        term(
            "admin_fee",
            None,
            "2",
            "Administrative fee: 2.0% of total net sales of all Products.",
            **master,
        ),
    ]
    result = run(terms, as_of=date(2026, 6, 30))
    assert [f.status for f in result.findings] == ["match", "match", "match"]
    assert result.total_indicative_exposure == Decimal("0.00")
    assert result.not_checked == []
