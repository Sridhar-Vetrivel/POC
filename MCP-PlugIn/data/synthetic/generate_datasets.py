"""Generate the three SYNTHETIC source datasets: Sharepoint, Onedrive and Network-Drive.

Run from the repo root:  python MCP-PlugIn/data/synthetic/generate_datasets.py
Output is deterministic. Nothing here is Ingenus data: customers, products, rates and wording are invented.

Each dataset has two chains and holds, side by side:

    <Source>/contracts/   the PDFs. Copy the CONTENTS of this folder to the real drive (the folder holds
                          Chain_A/, Chain_B/ ...). Nothing else belongs on the drive.
    <Source>/slice/       what the server needs beside the contracts: topics, ontology, rules, schemas,
                          page labels and the expected results. Stays on the server side.
    <Source>/sap/         the mock SAP records for that dataset's customers.

The older data (contracts/, sap/, bulk) is made by generate_contracts.py and is not touched here.
"""

from __future__ import annotations

import json
import random
import shutil
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from generate_contracts import BOILERPLATE, write_pdf

ROOT = Path(__file__).resolve().parent
BASE_SLICE = ROOT.parents[2] / "slices" / "contract_to_sap_check"
LABEL = "SYNTHETIC: invented for the Ingenus POC. Not Ingenus data. Customers, products and numbers are made up."
AS_OF = "2026-08-31"
MONTHS = [f"2026-{m:02d}" for m in range(1, 9)]  # SAP sales exist for Jan to Aug 2026


def long_date(day: str) -> str:
    d = date.fromisoformat(day)
    return f"{d.day} {d.strftime('%B %Y')}"


def rebate_line(product: str, rate: str) -> str:
    return f"{product} rebate: {rate}% of net sales of {product}."


def fee_line(rate: str) -> str:
    return f"Administrative fee: {rate}% of total net sales of all Products."


class Doc:
    """One contract PDF: its pages, which pages hold terms, and the terms with the quote on each."""

    def __init__(self, chain: str, name: str, category: str):
        self.chain = chain
        self.rel = f"{chain}/{name}.pdf"
        self.category = category
        self.pages: list[list[str]] = []
        self.terms: list[dict[str, Any]] = []
        self.term_pages: list[int] = []

    def add_terms(
        self, page: int, effective: str, rebates: list[tuple[str, str]], fee: str | None
    ) -> None:
        """Record the terms printed on `page` (1-based). The quote is the exact line printed there."""
        for product, rate in rebates:
            self.terms.append(
                {
                    "kind": "rebate",
                    "product": product,
                    "rate_pct": rate,
                    "effective_date": effective,
                    "document": self.rel,
                    "page": page,
                    "quote": rebate_line(product, rate),
                }
            )
        if fee is not None:
            self.terms.append(
                {
                    "kind": "admin_fee",
                    "product": None,
                    "rate_pct": fee,
                    "effective_date": effective,
                    "document": self.rel,
                    "page": page,
                    "quote": fee_line(fee),
                }
            )
        self.term_pages.append(page)


def filler(rng: random.Random, n: int) -> list[str]:
    return rng.sample(BOILERPLATE, n)


def master(rng, chain, customer, effective, rebates, fee, net_days, *, scanned_page=False) -> Doc:
    doc = Doc(chain, f"{chain}_Master_Supply_Agreement_{effective[:4]}", "easy")
    products = " and ".join(p for p, _ in rebates)
    schedule = [rebate_line(p, r) for p, r in rebates] + [fee_line(fee)]
    doc.pages = [
        [
            "MASTER SUPPLY AGREEMENT",
            "",
            f"Between Synthetic Pharma Inc. (the Supplier) and {customer} (the Customer).",
            f"Effective date: {long_date(effective)}. Initial term: three years.",
        ],
        [
            "1. DEFINITIONS",
            "Net Sales means gross invoiced sales of the Products less returns and credits.",
            f"Products means {products}, each as listed in Schedule A.",
        ],
        [
            "3. SUPPLY AND PRICING",
            "The Supplier shall supply the Products at the prices on the agreed price list.",
            *filler(rng, 1),
        ],
    ]
    if scanned_page:
        doc.pages.append([])  # a page with no text, standing in for a scanned page
    doc.pages += [
        ["SCHEDULE A: REBATES AND FEES", "", *schedule],
        [
            "5. PAYMENT AND RETURNS",
            f"Payment terms: net {net_days} days from invoice date.",
            *filler(rng, 1),
        ],
        [
            "6. GENERAL",
            *filler(rng, 1),
            "Signed for the Supplier: A. Example. Signed for the Customer: B. Sample.",
        ],
    ]
    schedule_page = 5 if scanned_page else 4
    doc.add_terms(schedule_page, effective, rebates, fee)
    return doc


def amendment(
    rng, chain, customer, number, effective, rebates, fee, *, layout="plain", year=None
) -> Doc:
    year = year or effective[:4]
    doc = Doc(chain, f"{chain}_Amendment_{number}_{year}", "easy")
    head = [
        f"AMENDMENT NO. {number}",
        "",
        f"This Amendment No. {number} is effective {long_date(effective)} and amends the Master Supply "
        f"Agreement between Synthetic Pharma Inc. and {customer}.",
    ]
    if layout == "table":
        rows = [f"{p} | {r}% | rebate | quarterly" for p, r in rebates]
        # a table row keeps the product and the rate on one line, so it is its own quote
        doc.pages = [
            head,
            [
                "1. REPLACEMENT OF SCHEDULE A",
                "Schedule A is replaced as follows.",
                "",
                "Item | Rate | Type | Paid",
                *rows,
                f"Administrative fee | {fee}% | total net sales | quarterly",
            ],
            ["2. GENERAL", "Except as amended, the Master Supply Agreement remains in full force."],
        ]
        for p, r in rebates:
            doc.terms.append(
                {
                    "kind": "rebate",
                    "product": p,
                    "rate_pct": r,
                    "effective_date": effective,
                    "document": doc.rel,
                    "page": 2,
                    "quote": f"{p} | {r}% | rebate | quarterly",
                }
            )
        doc.terms.append(
            {
                "kind": "admin_fee",
                "product": None,
                "rate_pct": fee,
                "effective_date": effective,
                "document": doc.rel,
                "page": 2,
                "quote": f"Administrative fee | {fee}% | total net sales | quarterly",
            }
        )
        doc.term_pages.append(2)
        doc.category = "table_style"
        return doc
    schedule = [rebate_line(p, r) for p, r in rebates] + [fee_line(fee)]
    if layout == "split":
        doc.pages = [
            head,
            ["2. BACKGROUND", *filler(rng, 3)],
            ["3. SUPPLY", *filler(rng, 3)],
            [
                "4. REPLACEMENT OF SCHEDULE A",
                f"Schedule A is replaced with the following, effective {long_date(effective)}.",
                "",
                *schedule,
            ],
            ["5. GENERAL", "Except as amended, the Master Supply Agreement remains in full force."],
        ]
        doc.add_terms(4, effective, rebates, fee)
        doc.category = "split_pages"
        return doc
    doc.pages = [
        head,
        [
            "1. REPLACEMENT OF SCHEDULE A",
            f"Schedule A is deleted and replaced with the following, effective {long_date(effective)}.",
            "",
            *schedule,
        ],
        [
            "2. GENERAL",
            "Except as amended, the Master Supply Agreement remains in full force.",
            "Signed for the Supplier: A. Example. Signed for the Customer: B. Sample.",
        ],
    ]
    doc.add_terms(2, effective, rebates, fee)
    return doc


def draft(chain, number, effective, product, rate) -> Doc:
    doc = Doc(chain, f"{chain}_Amendment_{number}_DRAFT", "draft")
    doc.pages = [
        [
            f"DRAFT: AMENDMENT NO. {number}",
            "For discussion only. Not signed.",
            f"Effective {long_date(effective)}: {rebate_line(product, rate)}",
        ]
    ]
    doc.term_pages = [1]
    return doc


def payment_only(chain, number, effective, from_days, to_days) -> Doc:
    doc = Doc(chain, f"{chain}_Amendment_{number}_{effective[:4]}", "control_no_terms")
    doc.pages = [
        [
            f"AMENDMENT NO. {number}",
            f"This Amendment No. {number} is effective {long_date(effective)} and amends the Master Supply Agreement.",
        ],
        [
            "1. PAYMENT TERMS",
            f"Payment terms change from net {from_days} days to net {to_days} days. All other terms are unchanged.",
        ],
    ]
    return doc


def sales(customer_id: str, product: str, amount: str, months: list[str]) -> list[dict[str, str]]:
    return [
        {"customer_id": customer_id, "month": m, "product": product, "net_sales": amount}
        for m in months
    ]


def setup(
    customer_id: str,
    kind: str,
    product: str | None,
    rate: str,
    valid_from: str,
    valid_to: str | None = None,
):
    return {
        "customer_id": customer_id,
        "kind": kind,
        "product": product,
        "rate_pct": rate,
        "basis": "product_net_sales" if kind == "rebate" else "total_net_sales",
        "valid_from": valid_from,
        "valid_to": valid_to,
    }


def build_chain(rng, letter, cid, spec) -> dict[str, Any]:
    """Return the docs, SAP rows and expected figures for one chain. Specs are written out below."""
    return spec(rng, f"Chain_{letter}", f"Chain {letter} Pharmacy", cid)


# ---- the six chains ---------------------------------------------------------------------------------


def chain_a(rng, chain, customer, cid):
    """Rate variance (Product A) and an unsigned DRAFT amendment that must be ignored."""
    docs = [
        master(
            rng,
            chain,
            customer,
            "2025-03-01",
            [("Product A", "3.0"), ("Product B", "2.5")],
            "1.5",
            45,
        ),
        amendment(
            rng,
            chain,
            customer,
            1,
            "2026-02-01",
            [("Product A", "4.5"), ("Product B", "2.5")],
            "1.5",
        ),
        draft(chain, 2, "2026-11-01", "Product A", "5.5"),
        payment_only(chain, 3, "2026-04-01", 45, 30),
    ]
    sap = {
        "setup": [
            setup(cid, "rebate", "Product A", "3.0", "2025-03-01"),
            setup(cid, "rebate", "Product B", "2.5", "2025-03-01"),
            setup(cid, "admin_fee", None, "1.5", "2025-03-01"),
        ],
        "sales": sales(cid, "Product A", "120000.00", MONTHS)
        + sales(cid, "Product B", "80000.00", MONTHS),
    }
    expect = {
        "terms_from": docs[1].rel,
        "gap": "1800.00",
        "exposure": "12600.00",
        "statuses": {
            "rebate:Product A": "variance",
            "rebate:Product B": "match",
            "admin_fee": "match",
        },
    }
    return {
        "docs": docs,
        "sap": sap,
        "expect": expect,
        "story": "Amendment 1 raises the Product A rebate from 3.0% to 4.5% from 1 Feb 2026; SAP still has 3.0%. "
        "Amendment 2 is an unsigned DRAFT (Product A 5.5%) and must not be used.",
    }


def chain_b(rng, chain, customer, cid):
    """New product missing in SAP (D), a lapsed SAP setup (C, valid to 31 Mar 2026), and matching lines."""
    docs = [
        master(
            rng,
            chain,
            customer,
            "2025-06-01",
            [("Product A", "5.0"), ("Product C", "4.0")],
            "2.0",
            60,
        ),
        amendment(
            rng,
            chain,
            customer,
            1,
            "2026-06-01",
            [("Product A", "5.0"), ("Product C", "4.0"), ("Product D", "3.5")],
            "2.0",
        ),
        payment_only(chain, 2, "2026-09-01", 60, 45),
    ]
    sap = {
        "setup": [
            setup(cid, "rebate", "Product A", "5.0", "2025-06-01"),
            setup(cid, "rebate", "Product C", "4.0", "2025-06-01", "2026-03-31"),
            setup(cid, "admin_fee", None, "2.0", "2025-06-01"),
        ],
        "sales": sales(cid, "Product A", "100000.00", MONTHS)
        + sales(cid, "Product C", "60000.00", MONTHS)
        + sales(cid, "Product D", "40000.00", MONTHS[5:]),
    }
    expect = {
        "terms_from": docs[1].rel,
        "gap": "3800.00",
        "exposure": "11400.00",
        "statuses": {
            "rebate:Product A": "match",
            "rebate:Product C": "not_set_up_in_sap",
            "rebate:Product D": "not_set_up_in_sap",
            "admin_fee": "match",
        },
    }
    return {
        "docs": docs,
        "sap": sap,
        "expect": expect,
        "story": "Amendment 1 (1 Jun 2026) adds Product D at 3.5%, which SAP has no setup for. Product C's SAP setup "
        "ended on 31 Mar 2026 (expired) although the contract still pays 4.0%. Product A and the fee match.",
    }


def chain_c(rng, chain, customer, cid):
    """Variance in both directions: a lower rebate (SAP over-reserved) and a higher fee (under-reserved)."""
    docs = [
        master(
            rng,
            chain,
            customer,
            "2024-09-01",
            [("Product B", "3.5"), ("Product C", "2.0")],
            "1.0",
            30,
        ),
        amendment(
            rng,
            chain,
            customer,
            1,
            "2026-04-01",
            [("Product B", "3.0"), ("Product C", "2.0")],
            "1.75",
            layout="table",
        ),
        draft(chain, 2, "2026-12-01", "Product C", "4.0"),
        payment_only(chain, 3, "2026-05-01", 30, 45),
    ]
    sap = {
        "setup": [
            setup(cid, "rebate", "Product B", "3.5", "2024-09-01"),
            setup(cid, "rebate", "Product C", "2.0", "2024-09-01"),
            setup(cid, "admin_fee", None, "1.0", "2024-09-01"),
        ],
        "sales": sales(cid, "Product B", "150000.00", MONTHS)
        + sales(cid, "Product C", "50000.00", MONTHS),
    }
    expect = {
        "terms_from": docs[1].rel,
        "gap": "750.00",
        "exposure": "3750.00",
        "statuses": {
            "rebate:Product B": "variance",
            "rebate:Product C": "match",
            "admin_fee": "variance",
        },
    }
    return {
        "docs": docs,
        "sap": sap,
        "expect": expect,
        "story": "Amendment 1 (a table) lowers Product B from 3.5% to 3.0% (SAP over-reserved by 750.00 a month) and raises the "
        "fee from 1.0% to 1.75% (under-reserved by 1,500.00 a month): the lines go opposite ways and net to 750.00. "
        "Amendment 2 is an unsigned DRAFT.",
    }


def chain_d(rng, chain, customer, cid):
    """A new product missing in SAP (B), a lapsed SAP setup (D, valid to 28 Feb 2026), and matching lines."""
    docs = [
        master(
            rng,
            chain,
            customer,
            "2025-01-01",
            [("Product A", "6.0"), ("Product D", "2.0")],
            "3.0",
            45,
            scanned_page=True,
        ),
        amendment(
            rng,
            chain,
            customer,
            1,
            "2026-05-01",
            [("Product A", "6.0"), ("Product B", "2.5"), ("Product D", "2.0")],
            "3.0",
        ),
        payment_only(chain, 2, "2026-08-01", 45, 30),
    ]
    sap = {
        "setup": [
            setup(cid, "rebate", "Product A", "6.0", "2025-01-01"),
            setup(cid, "rebate", "Product D", "2.0", "2025-01-01", "2026-02-28"),
            setup(cid, "admin_fee", None, "3.0", "2025-01-01"),
        ],
        "sales": sales(cid, "Product A", "90000.00", MONTHS)
        + sales(cid, "Product D", "30000.00", MONTHS)
        + sales(cid, "Product B", "60000.00", MONTHS[4:]),
    }
    expect = {
        "terms_from": docs[1].rel,
        "gap": "2100.00",
        "exposure": "8400.00",
        "statuses": {
            "rebate:Product A": "match",
            "rebate:Product B": "not_set_up_in_sap",
            "rebate:Product D": "not_set_up_in_sap",
            "admin_fee": "match",
        },
    }
    return {
        "docs": docs,
        "sap": sap,
        "expect": expect,
        "story": "Amendment 1 (1 May 2026) adds Product B at 2.5% with no SAP setup. Product D's SAP setup ended on "
        "28 Feb 2026 (expired). The master has a blank page (a scanned page with no text).",
    }


def chain_e(rng, chain, customer, cid):
    """Rate variance (Product A) over a long period; the terms sit on page 4 of the amendment."""
    docs = [
        master(
            rng,
            chain,
            customer,
            "2025-02-01",
            [("Product A", "2.5"), ("Product B", "4.0")],
            "2.0",
            45,
        ),
        amendment(
            rng,
            chain,
            customer,
            1,
            "2026-01-01",
            [("Product A", "3.5"), ("Product B", "4.0")],
            "2.0",
            layout="split",
        ),
        draft(chain, 2, "2026-11-01", "Product A", "4.5"),
        payment_only(chain, 3, "2026-03-01", 45, 30),
    ]
    sap = {
        "setup": [
            setup(cid, "rebate", "Product A", "2.5", "2025-02-01"),
            setup(cid, "rebate", "Product B", "4.0", "2025-02-01"),
            setup(cid, "admin_fee", None, "2.0", "2025-02-01"),
        ],
        "sales": sales(cid, "Product A", "110000.00", MONTHS)
        + sales(cid, "Product B", "90000.00", MONTHS),
    }
    expect = {
        "terms_from": docs[1].rel,
        "gap": "1100.00",
        "exposure": "8800.00",
        "statuses": {
            "rebate:Product A": "variance",
            "rebate:Product B": "match",
            "admin_fee": "match",
        },
    }
    return {
        "docs": docs,
        "sap": sap,
        "expect": expect,
        "story": "Amendment 1 (1 Jan 2026, terms on page 4 after two pages of background) raises Product A from 2.5% to 3.5%; "
        "SAP still has 2.5%, so eight months of exposure. Amendment 2 is an unsigned DRAFT.",
    }


def chain_f(rng, chain, customer, cid):
    """New product (A) missing in SAP and a lapsed SAP setup (D, valid to 30 Apr 2026); the rest match."""
    docs = [
        master(
            rng,
            chain,
            customer,
            "2025-07-01",
            [("Product C", "4.5"), ("Product D", "3.0")],
            "1.25",
            60,
        ),
        amendment(
            rng,
            chain,
            customer,
            1,
            "2026-07-01",
            [("Product A", "2.0"), ("Product C", "4.5"), ("Product D", "3.0")],
            "1.25",
        ),
        payment_only(chain, 2, "2026-10-01", 60, 45),
    ]
    sap = {
        "setup": [
            setup(cid, "rebate", "Product C", "4.5", "2025-07-01"),
            setup(cid, "rebate", "Product D", "3.0", "2025-07-01", "2026-04-30"),
            setup(cid, "admin_fee", None, "1.25", "2025-07-01"),
        ],
        "sales": sales(cid, "Product C", "70000.00", MONTHS)
        + sales(cid, "Product D", "30000.00", MONTHS)
        + sales(cid, "Product A", "50000.00", MONTHS[6:]),
    }
    expect = {
        "terms_from": docs[1].rel,
        "gap": "1900.00",
        "exposure": "3800.00",
        "statuses": {
            "rebate:Product A": "not_set_up_in_sap",
            "rebate:Product C": "match",
            "rebate:Product D": "not_set_up_in_sap",
            "admin_fee": "match",
        },
    }
    return {
        "docs": docs,
        "sap": sap,
        "expect": expect,
        "story": "Amendment 1 (1 Jul 2026) adds Product A at 2.0% with no SAP setup. Product D's SAP setup ended on "
        "30 Apr 2026 (expired). Product C and the fee match.",
    }


DATASETS = {
    "Sharepoint": {
        "first": 1001,
        "chains": [("A", chain_a), ("B", chain_b)],
        "shared_alias": "Metro Stores",
    },
    "Onedrive": {
        "first": 2001,
        "chains": [("C", chain_c), ("D", chain_d)],
        "shared_alias": "Harbour Stores",
    },
    "Network-Drive": {
        "first": 3001,
        "chains": [("E", chain_e), ("F", chain_f)],
        "shared_alias": "Valley Stores",
    },
}


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_dataset(source: str, config: dict[str, Any]) -> int:
    base = ROOT / source
    if base.exists():
        shutil.rmtree(base)
    rng = random.Random(hash_seed(source))
    customers, setup_rows, sales_rows, labels, terms_out, expected = [], [], [], {}, {}, {}
    count = 0
    for index, (letter, builder) in enumerate(config["chains"]):
        cid = f"SYN-CUST-{config['first'] + index}"
        name = f"Chain {letter}"
        built = build_chain(rng, letter, cid, builder)
        customers.append(
            {
                "sap_customer_id": cid,
                "name": name,
                "aliases": [f"{name} Pharmacy", f"Chain-{letter}", config["shared_alias"]],
            }
        )
        setup_rows += built["sap"]["setup"]
        sales_rows += built["sap"]["sales"]
        for doc in built["docs"]:
            write_pdf(base / "contracts" / doc.rel, doc.pages)
            labels[doc.rel] = {"category": doc.category, "term_pages": doc.term_pages}
            count += 1
        source_doc = next(d for d in built["docs"] if d.rel == built["expect"]["terms_from"])
        terms_out[cid] = source_doc.terms
        expected[cid] = {
            "customer": name,
            **built["expect"],
            "story": built["story"],
            "as_of": AS_OF,
        }

    write_json(
        base / "sap" / "entities.json",
        {
            "_label": LABEL,
            "customers": [
                {"customer_id": c["sap_customer_id"], "name": c["name"]} for c in customers
            ],
            "rebate_setup": setup_rows,
            "sales_volume": sales_rows,
        },
    )

    slice_dir = base / "slice"
    header = (
        f"# {LABEL}\n# Dataset: {source}. Generated by generate_datasets.py; do not edit by hand.\n"
    )
    (slice_dir / "ontology").mkdir(parents=True)
    (slice_dir / "ontology" / "customers.v1.yaml").write_text(
        header
        + "# A name that matches more than one customer is ambiguous and must never be resolved by guessing.\n"
        + yaml.safe_dump(
            {"version": 1, "label": "SYNTHETIC", "customers": customers}, sort_keys=False
        ),
        encoding="utf-8",
    )
    # The topic keywords and the comparison rules are policy, not data: they are the base slice's, with the
    # dataset named. (Nothing in these chains needs a keyword or rule the base slice lacks.)
    (slice_dir / "rules").mkdir()
    (slice_dir / "rules" / "compare.v1.yaml").write_text(
        f"# {LABEL}\n# Dataset: {source}. Same rules as the base slice.\n"
        + (BASE_SLICE / "rules" / "compare.v1.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    shutil.copyfile(BASE_SLICE / "topics.v1.yaml", slice_dir / "topics.v1.yaml")
    (slice_dir / "schemas").mkdir()
    shutil.copyfile(
        BASE_SLICE / "schemas" / "contract_terms.v1.json",
        slice_dir / "schemas" / "contract_terms.v1.json",
    )
    write_json(slice_dir / "evals" / "golden" / "page_labels.json", dict(sorted(labels.items())))
    write_json(
        slice_dir / "evals" / "golden" / "expected_terms.v1.json",
        {"_label": LABEL, "terms_by_customer": terms_out},
    )
    write_json(
        slice_dir / "evals" / "golden" / "expected_results.v1.json",
        {"_label": LABEL, "by_customer": expected},
    )
    (slice_dir / "evals" / "golden" / "expected_results.v1.md").write_text(
        results_markdown(source, expected), encoding="utf-8"
    )
    return count


def hash_seed(text: str) -> int:
    return sum(ord(c) * (i + 1) for i, c in enumerate(text))  # stable across runs, unlike hash()


def results_markdown(source: str, expected: dict[str, Any]) -> str:
    lines = [
        f"# Expected results: {source} (SYNTHETIC)",
        "",
        f"{LABEL}",
        "",
        f"Run with as_of **{AS_OF}**, using the terms in `expected_terms.v1.json` (the signed amendment, never the DRAFT).",
        "",
    ]
    for cid, e in expected.items():
        lines += [
            f"## {e['customer']} ({cid})",
            "",
            e["story"],
            "",
            f"- Total monthly gap: **{e['gap']}**",
            f"- Indicative exposure to {AS_OF}: **{e['exposure']}**",
        ]
        lines += [f"- {line}: {status}" for line, status in e["statuses"].items()]
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    for source, config in DATASETS.items():
        count = write_dataset(source, config)
        print(f"{source}: wrote {count} contracts")


if __name__ == "__main__":
    main()
