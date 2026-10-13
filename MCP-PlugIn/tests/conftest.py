"""Shared fixtures. Tests run offline: no network, no Claude API calls."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from ingenus_plugin.core.models import Citation, ExtractedTerm

REPO = Path(__file__).resolve().parents[2]
MASTER = "Chain_X/Chain_X_Master_Supply_Agreement_2024.pdf"
AMEND2 = "Chain_X/Chain_X_Amendment_2_2026.pdf"
DRAFT3 = "Chain_X/Chain_X_Amendment_3_DRAFT.pdf"


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """Every test logs to its own temp file and never touches data/runtime."""
    monkeypatch.setenv("INGENUS_LOG_PATH", str(tmp_path / "tool_calls.jsonl"))
    monkeypatch.setenv("INGENUS_USER", "tester")
    for var in ("INGENUS_CONTRACTS_DIR", "INGENUS_SAP_MOCK_FILE", "INGENUS_SAP_ADAPTER"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


def term(
    kind: str,
    product: str | None,
    rate: str,
    quote: str,
    *,
    document: str = AMEND2,
    page: int = 2,
    effective: date = date(2026, 7, 1),
) -> ExtractedTerm:
    return ExtractedTerm(
        kind=kind,  # type: ignore[arg-type]
        product=product,
        rate_pct=rate,  # type: ignore[arg-type]
        effective_date=effective,
        citation=Citation(document=document, page=page, clause="Schedule A", quote=quote),
    )


def chain_x_terms() -> list[ExtractedTerm]:
    """What a careful Claude would extract from Chain X Amendment 2."""
    return [
        term("rebate", "Product A", "6", "Product A rebate: 6.0% of net sales of Product A."),
        term("rebate", "Product B", "3", "Product B rebate: 3.0% of net sales of Product B."),
        term("rebate", "Product C", "5", "Product C rebate: 5.0% of net sales of Product C (new)."),
        term(
            "admin_fee", None, "2.5", "Administrative fee: 2.5% of total net sales of all Products."
        ),
    ]


@pytest.fixture
def make_world(tmp_path, monkeypatch):
    """Build a tiny contract folder and SAP mock in tmp_path and point the plug-in at them."""

    def build(
        pages: list[str],
        sap_rebates: list[dict],
        sales: list[dict],
        name: str = "Acme_Agreement.txt",
    ) -> str:
        contracts = tmp_path / "contracts"
        (contracts / "Acme").mkdir(parents=True)
        (contracts / "Acme" / name).write_text("\f".join(pages), encoding="utf-8")
        sap = {
            "_label": "SYNTHETIC test data",
            "customers": [{"customer_id": "T-1", "name": "Acme"}],
            "rebate_setup": [
                {"customer_id": "T-1", "valid_from": "2025-01-01", "valid_to": None, **r}
                for r in sap_rebates
            ],
            "sales_volume": [{"customer_id": "T-1", **s} for s in sales],
        }
        sap_file = tmp_path / "sap.json"
        sap_file.write_text(json.dumps(sap), encoding="utf-8")
        monkeypatch.setenv("INGENUS_CONTRACTS_DIR", str(contracts))
        monkeypatch.setenv("INGENUS_SAP_MOCK_FILE", str(sap_file))
        return f"Acme/{name}"

    return build
