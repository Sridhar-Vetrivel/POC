"""Deterministic comparison of contract terms against SAP. Plain code: no AI, same inputs, same output.

Money uses Decimal. Rules come from the slice's compare.v1.yaml. The SAP rate as at the as_of date is
assumed to apply to the whole period, and the result says so.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import yaml

from ingenus_mcp.core import citations
from ingenus_mcp.core.config import Settings
from ingenus_mcp.core.customers import norm
from ingenus_mcp.core.models import (
    CompareResult,
    ExtractedTerm,
    Finding,
    NotChecked,
    RebateSetupResult,
    SalesVolumeResult,
    SetupLine,
)

HUNDRED = Decimal(100)
_KIND_ORDER = {"rebate": 0, "admin_fee": 1}


def load_rules(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _money(value: Decimal, places: int) -> Decimal:
    return value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def _label(kind: str, product: str | None) -> str:
    return "admin fee" if kind == "admin_fee" else f"{product or '(no product)'} rebate"


def covered_months(start: date, end: date) -> list[tuple[str, Decimal]]:
    """(month, fraction of that month covered) from start to end inclusive. Partial months by days."""
    if end < start:
        return []
    out: list[tuple[str, Decimal]] = []
    year, month = start.year, start.month
    while date(year, month, 1) <= end:
        days_in_month = calendar.monthrange(year, month)[1]
        first = max(start, date(year, month, 1))
        last = min(end, date(year, month, days_in_month))
        days = (last - first).days + 1
        out.append((f"{year}-{month:02d}", Decimal(days) / Decimal(days_in_month)))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return out


def compare(
    terms: list[ExtractedTerm],
    customer_id: str,
    as_of: date,
    setup: RebateSetupResult,
    volumes: SalesVolumeResult,
    settings: Settings,
) -> CompareResult:
    rules = load_rules(settings.rules_file)
    places = int(rules["rounding_places"])
    tolerance = Decimal(str(rules["rate_tolerance_pct"]))
    default_basis = rules["default_basis"]

    not_checked: list[NotChecked] = []

    # 0. An admin fee applies to total net sales, so it has no product. Claude sometimes labels it
    # ("All Products"); left in, that label stops it pairing with SAP's admin-fee line.
    ignored_fee_labels: list[str] = []
    cleaned: list[ExtractedTerm] = []
    for term in terms:
        if term.kind == "admin_fee" and term.product:
            ignored_fee_labels.append(term.product)
            term = term.model_copy(update={"product": None})
        cleaned.append(term)
    terms = cleaned

    # 1. Keep only terms whose quote is really on the cited page and holds the rate.
    verified: list[ExtractedTerm] = []
    for term in terms:
        reason = citations.verify_term(term, settings)
        if reason:
            not_checked.append(NotChecked(item=_label(term.kind, term.product), reason=reason))
        else:
            verified.append(term)

    # 2. Same line and date twice: identical rate is a duplicate; different rates conflict.
    by_key: dict[tuple[str, str], list[ExtractedTerm]] = {}
    for term in verified:
        by_key.setdefault((term.kind, norm(term.product or "")), []).append(term)
    usable: list[tuple[ExtractedTerm, date]] = []  # (term, last day this rate applies)
    for group in by_key.values():
        by_date: dict[date, list[ExtractedTerm]] = {}
        for term in group:
            by_date.setdefault(term.effective_date, []).append(term)
        kept: list[ExtractedTerm] = []
        for day in sorted(by_date):
            same_day = by_date[day]
            if len({t.rate_pct for t in same_day}) > 1:
                not_checked.append(
                    NotChecked(
                        item=_label(same_day[0].kind, same_day[0].product),
                        reason=f"Two different rates were supplied for {day}. Resolve which one applies.",
                    )
                )
            else:
                kept.append(same_day[0])
        for i, term in enumerate(kept):
            end = as_of
            if i + 1 < len(kept):
                end = min(as_of, kept[i + 1].effective_date - timedelta(days=1))
            usable.append((term, end))

    # 3. Index SAP data.
    setup_by_key: dict[tuple[str, str], SetupLine] = {
        (line.kind, norm(line.product or "")): line for line in setup.lines
    }
    sales: dict[tuple[str, str], Decimal] = {}
    totals: dict[str, Decimal] = {}
    products_with_sales: set[str] = set()
    for row in volumes.rows:
        sales[(row.month, norm(row.product))] = row.net_sales
        totals[row.month] = totals.get(row.month, Decimal(0)) + row.net_sales
        products_with_sales.add(norm(row.product))

    # 4. Compare each term over the months it applies.
    findings: list[Finding] = []
    partial = False
    no_base: list[str] = []  # lines that match SAP but have no SAP sales in their period
    for term, end in sorted(
        usable,
        key=lambda x: (_KIND_ORDER[x[0].kind], norm(x[0].product or ""), x[0].effective_date),
    ):
        label = _label(term.kind, term.product)
        key = (term.kind, norm(term.product or ""))
        sap_line = setup_by_key.get(key)
        basis = sap_line.basis if sap_line else default_basis[term.kind]
        if basis == "product_net_sales" and not term.product:
            not_checked.append(
                NotChecked(item=label, reason="A rebate needs a product name to find its sales.")
            )
            continue
        if (
            sap_line is None
            and basis == "product_net_sales"
            and norm(term.product or "") not in products_with_sales
        ):
            not_checked.append(
                NotChecked(
                    item=label,
                    reason="No SAP setup and no SAP sales found for this product name. It may be new or named differently.",
                )
            )
            continue
        months = covered_months(term.effective_date, end)
        if not months:
            not_checked.append(
                NotChecked(
                    item=label,
                    reason=f"Effective {term.effective_date} is after the as_of date {as_of}; nothing to compare yet.",
                )
            )
            continue

        def base_for(
            month: str, basis: str = basis, product: str | None = term.product
        ) -> Decimal | None:
            if basis == "total_net_sales":
                return totals.get(month)
            return sales.get((month, norm(product or "")))

        sap_rate = sap_line.rate_pct if sap_line else None
        diff = term.rate_pct - (sap_rate if sap_rate is not None else Decimal(0))
        if sap_rate is None:
            status = "not_set_up_in_sap"
        elif abs(diff) <= tolerance:
            status = "match"
        else:
            status = "variance"

        # The rate status never depends on sales. A matching line has no exposure, so it only needs
        # the latest month that has sales (for the base shown). A line that differs is counted over
        # the months that have SAP sales; a month without sales is listed as not checked and is
        # never guessed or filled in.
        bases = {m: base_for(m) for m, _ in months}
        with_sales = [(m, f) for m, f in months if bases[m] is not None]
        if not with_sales:
            if status == "match":
                # The rates agree, so there is no gap whatever the sales were: only the base is unknown.
                # This is an earlier term that a later amendment replaced, or a new line with no sales yet.
                # It is not "not checked": the rate status never depends on sales.
                no_base.append(f"{label} ({months[0][0]} to {months[-1][0]})")
                findings.append(
                    Finding(
                        kind=term.kind,
                        product=term.product,
                        status="match",
                        contract_rate_pct=term.rate_pct,
                        sap_rate_pct=sap_rate,
                        effective_date=term.effective_date,
                        monthly_base=None,
                        monthly_gap=_money(Decimal(0), places),
                        indicative_exposure=_money(Decimal(0), places),
                        citation=term.citation,
                    )
                )
                continue
            not_checked.append(
                NotChecked(
                    item=label,
                    reason=f"SAP sales missing for {', '.join(m for m, _ in months)}.",
                )
            )
            continue
        needed = with_sales[-1:] if status == "match" else with_sales
        missing = [m for m, _ in months if bases[m] is None]
        if missing and status != "match":
            partial = True
            not_checked.append(
                NotChecked(
                    item=label,
                    reason=(
                        f"SAP sales missing for {', '.join(missing)}. The exposure counts only "
                        f"{', '.join(m for m, _ in needed)}."
                    ),
                )
            )

        exposure = sum(
            (diff / HUNDRED * bases[m] * fraction for m, fraction in needed),  # type: ignore[operator]
            Decimal(0),
        )
        latest_base = bases[needed[-1][0]]
        assert latest_base is not None
        monthly_gap = diff / HUNDRED * latest_base
        findings.append(
            Finding(
                kind=term.kind,
                product=term.product,
                status=status,  # type: ignore[arg-type]
                contract_rate_pct=term.rate_pct,
                sap_rate_pct=sap_rate,
                effective_date=term.effective_date,
                monthly_base=_money(latest_base, places),
                monthly_gap=_money(monthly_gap, places),
                indicative_exposure=_money(exposure, places),
                citation=term.citation,
            )
        )

    total_gap = sum((f.monthly_gap for f in findings), Decimal(0))
    total_exposure = sum((f.indicative_exposure for f in findings), Decimal(0))

    mentioned = {(t.kind, norm(t.product or "")) for t, _ in usable}
    not_mentioned = [
        f"{_label(line.kind, line.product)} at {line.rate_pct}% in SAP; not in the terms supplied"
        for key, line in sorted(setup_by_key.items())
        if key not in mentioned
    ]

    counts = {
        s: sum(1 for f in findings if f.status == s)
        for s in ("variance", "match", "not_set_up_in_sap")
    }
    direction = (
        "SAP under-reserved"
        if total_gap > 0
        else ("SAP over-reserved" if total_gap < 0 else "no net gap")
    )
    differ = counts["variance"] + counts["not_set_up_in_sap"]
    summary = (
        f"{differ} line(s) differ from SAP ({counts['variance']} variance, "
        f"{counts['not_set_up_in_sap']} not set up in SAP) and {counts['match']} match. "
        f"Total monthly gap {total_gap:,.2f} ({direction}). "
        f"Indicative exposure from the effective dates to {as_of}: {total_exposure:,.2f}. "
        f"{len(not_checked)} item(s) not checked."
    )
    caveats = [
        "Indicative figure, not an accounting number. Finance owns the accrual figure.",
        "The SAP setup as at the as_of date is assumed to apply to the whole period.",
        (
            "Each quote was checked to exist on the cited page and to contain the rate. "
            "Whether it is the right clause still needs a person to confirm."
        ),
        f"SAP data source: {setup.source}.",
    ]
    if partial:
        caveats.append(
            "Some months have no SAP sales yet. The exposure counts only the months that do, so the "
            "true exposure to the as_of date is likely larger. Do not present it as complete."
        )
    if no_base:
        caveats.append(
            "These lines match SAP, but SAP has no sales for their period, so no sales base is shown. "
            "There is no gap and no exposure from them: " + "; ".join(no_base) + "."
        )
    for label in sorted(set(ignored_fee_labels)):
        caveats.append(
            f"The admin fee was supplied with the product label '{label}'. An admin fee applies to "
            "total net sales, so the label was ignored."
        )
    return CompareResult(
        customer_id=customer_id,
        as_of=as_of,
        findings=findings,
        total_monthly_gap=_money(total_gap, places),
        total_indicative_exposure=_money(total_exposure, places),
        in_sap_not_in_contract_terms=not_mentioned,
        not_checked=not_checked,
        summary=summary,
        caveats=caveats,
    )
