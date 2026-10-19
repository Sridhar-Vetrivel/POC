"""Customer name resolution from the slice's alias table. Never guesses: ambiguity is reported."""

from __future__ import annotations

import difflib
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from ingenus_mcp.core.models import CustomerCandidate, ResolveCustomerResult


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


@lru_cache(maxsize=4)
def _load(path_str: str, mtime_ns: int) -> tuple[dict[str, Any], ...]:
    data = yaml.safe_load(Path(path_str).read_text(encoding="utf-8"))
    return tuple(data["customers"])


def load_customers(path: Path) -> list[dict[str, Any]]:
    return list(_load(str(path), path.stat().st_mtime_ns))


def names_for(customer: dict[str, Any]) -> list[str]:
    return [customer["name"], *customer.get("aliases", [])]


def resolve(query: str, customers_file: Path) -> ResolveCustomerResult:
    customers = load_customers(customers_file)
    q = norm(query)
    if not q:
        return ResolveCustomerResult(
            query=query, resolved=None, candidates=[], message="Empty customer name."
        )

    hits: dict[str, CustomerCandidate] = {}
    for c in customers:
        cid = c["sap_customer_id"]
        if q == norm(c["name"]) or q == norm(cid):
            hits[cid] = CustomerCandidate(name=c["name"], sap_customer_id=cid, match="exact")
        elif any(q == norm(a) for a in c.get("aliases", [])):
            hits.setdefault(
                cid, CustomerCandidate(name=c["name"], sap_customer_id=cid, match="alias")
            )

    if len(hits) == 1:
        only = next(iter(hits.values()))
        return ResolveCustomerResult(
            query=query,
            resolved=only,
            candidates=[only],
            message=f"Resolved to {only.name} ({only.sap_customer_id}) by {only.match} match.",
        )
    if len(hits) > 1:
        cands = sorted(hits.values(), key=lambda c: c.sap_customer_id)
        return ResolveCustomerResult(
            query=query,
            resolved=None,
            candidates=cands,
            message="The name matches more than one customer. Ask the user which one; do not guess.",
        )

    pool = {norm(n): c for c in customers for n in names_for(c)}
    close = difflib.get_close_matches(q, list(pool), n=3, cutoff=0.75)
    seen: dict[str, CustomerCandidate] = {}
    for key in close:
        c = pool[key]
        seen.setdefault(
            c["sap_customer_id"],
            CustomerCandidate(
                name=c["name"], sap_customer_id=c["sap_customer_id"], match="similar"
            ),
        )
    cands = sorted(seen.values(), key=lambda c: c.sap_customer_id)
    return ResolveCustomerResult(
        query=query,
        resolved=None,
        candidates=cands,
        message=(
            "No exact match. These names look similar; ask the user to confirm one."
            if cands
            else "No customer with that name or alias. Ask the user for the exact name."
        ),
    )
