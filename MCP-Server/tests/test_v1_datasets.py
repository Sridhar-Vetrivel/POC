"""The three source datasets (Sharepoint, Onedrive, Network-Drive) give the numbers written in their expected results.

Each source's PDFs are read from a local folder here (the real drive only changes WHERE the files are read from),
against the ONE shared ontology, rules and mock SAP. The expected figures were worked
out by hand from the contracts and SAP rows in generate_datasets.py, not copied from the engine's output.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest
from v1_support import REPO, isolated_env  # noqa: F401  (pytest fixtures)

from ingenus_mcp.core.models import Citation, ExtractedTerm
from ingenus_mcp.tools.compare_contract_to_sap import compare_contract_to_sap
from ingenus_mcp.tools.find_contract_files import find_contract_files
from ingenus_mcp.tools.resolve_customer import resolve_customer

SYNTHETIC = REPO / "MCP-PlugIn" / "data" / "synthetic"
GOLDEN = REPO / "slices" / "contract_to_sap_check" / "evals" / "golden" / "source_datasets.v1.json"
SOURCES = ["Sharepoint", "Onedrive", "Network-Drive"]


def golden(source):
    chains = json.loads(GOLDEN.read_text(encoding="utf-8"))["datasets"][source]["chains"]
    return (
        {cid: c["expected"] | {"customer": c["customer"]} for cid, c in chains.items()},
        {cid: c["terms"] for cid, c in chains.items()},
    )


def as_terms(raw):
    return [
        ExtractedTerm(
            kind=t["kind"],
            product=t["product"],
            rate_pct=Decimal(t["rate_pct"]),
            effective_date=date.fromisoformat(t["effective_date"]),
            citation=Citation(document=t["document"], page=t["page"], quote=t["quote"]),
        )
        for t in raw
    ]


@pytest.fixture
def use(monkeypatch):
    """Read one source's PDFs from a local folder. The ontology, rules and mock SAP are the ONE shared set."""

    def _use(source):
        monkeypatch.setenv("INGENUS_DOC_SOURCE", "local")
        monkeypatch.setenv("INGENUS_CONTRACTS_DIR", str(SYNTHETIC / source))

    return _use


@pytest.mark.parametrize("source", SOURCES)
def test_every_chain_gives_its_expected_gap_exposure_and_statuses(source, use):
    use(source)
    expected, terms = golden(source)
    assert len(expected) == 2
    for customer_id, e in expected.items():
        result = compare_contract_to_sap(
            customer_id=customer_id,
            as_of=date.fromisoformat(e["as_of"]),
            terms=as_terms(terms[customer_id]),
        )
        assert result.not_checked == [], result.not_checked
        assert result.total_monthly_gap == Decimal(e["gap"]), (customer_id, result.summary)
        assert result.total_indicative_exposure == Decimal(e["exposure"]), (
            customer_id,
            result.summary,
        )
        got = {
            ("admin_fee" if f.kind == "admin_fee" else f"rebate:{f.product}"): f.status
            for f in result.findings
        }
        assert got == e["statuses"], customer_id


@pytest.mark.parametrize("source", SOURCES)
def test_names_resolve_and_the_shared_alias_is_ambiguous(source, use):
    use(source)
    expected, _ = golden(source)
    for customer_id, e in expected.items():
        assert resolve_customer(name=e["customer"]).resolved.sap_customer_id == customer_id
    import yaml

    ontology = yaml.safe_load(
        (REPO / "slices" / "contract_to_sap_check" / "ontology" / "customers.v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    aliases = [set(c["aliases"]) for c in ontology["customers"] if c["sap_customer_id"] in expected]
    (shared,) = aliases[0] & aliases[1]  # the one name both chains of this source answer to
    result = resolve_customer(name=shared)
    assert result.resolved is None and len(result.candidates) == 2


@pytest.mark.parametrize("source", SOURCES)
def test_files_are_found_per_customer_and_the_draft_is_left_out(source, use):
    use(source)
    expected, _ = golden(source)
    drafts = 0
    for e in expected.values():
        found = find_contract_files(customer=e["customer"])
        assert found.files, e["customer"]
        assert all(e["customer"].replace(" ", "_") in f.document_id for f in found.files)
        assert {f.kind for f in found.files} >= {"master", "amendment"}
        drafts += len(found.excluded_drafts)
    assert drafts >= 1  # each dataset has at least one unsigned DRAFT


def test_the_datasets_do_not_share_customer_ids_or_chains():
    ids: list[str] = []
    chains: list[str] = []
    for source in SOURCES:
        expected, _ = golden(source)
        ids += list(expected)
        chains += [e["customer"] for e in expected.values()]
    assert len(set(ids)) == len(ids) == 6 and len(set(chains)) == 6


def test_a_source_folder_holds_only_pdfs_in_chain_folders():
    for source in SOURCES:
        files = [p for p in (SYNTHETIC / source).rglob("*") if p.is_file()]
        assert files and {p.suffix for p in files} == {".pdf"}, source
        assert all(p.parent.name.startswith("Chain_") for p in files), source


def test_the_ontology_and_mock_sap_exist_once_and_hold_every_customer():
    import yaml

    ontology = yaml.safe_load(
        (REPO / "slices" / "contract_to_sap_check" / "ontology" / "customers.v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    sap = json.loads((SYNTHETIC / "sap" / "entities.json").read_text(encoding="utf-8"))
    ids = {c["sap_customer_id"] for c in ontology["customers"]}
    assert ids == {c["customer_id"] for c in sap["customers"]}
    for source in SOURCES:
        assert set(golden(source)[0]) <= ids
    assert (
        not list(SYNTHETIC.glob("*/slice")) and not list(SYNTHETIC.glob("*/sap"))[1:]
    )  # no per-source copies
