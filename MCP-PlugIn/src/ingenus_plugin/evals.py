"""Offline evals for the page finder.

    python -m ingenus_plugin.evals page-finder

For every labelled synthetic contract, did get_contract_pages show the pages that hold the terms?
Recall = share of labelled term pages that were shown. Precision proxy = share of shown pages that
were needed (page 1 and neighbours always count against it; that is the price of being generous).
Labels come from the generator: slices/contract_to_sap_check/evals/golden/page_labels.json.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from typing import Any

from ingenus_plugin.core import contracts
from ingenus_plugin.core.config import load_settings


def page_finder_eval(topics: list[str] | None = None) -> dict[str, Any]:
    settings = load_settings()
    labels_path = settings.slice_dir / "evals" / "golden" / "page_labels.json"
    labels: dict[str, dict[str, Any]] = json.loads(labels_path.read_text(encoding="utf-8"))

    per_category: dict[str, dict[str, int]] = defaultdict(
        lambda: {"docs": 0, "term_pages": 0, "found": 0, "shown": 0, "needed_shown": 0, "total": 0}
    )
    misses: list[dict[str, Any]] = []
    for doc_id, info in sorted(labels.items()):
        if info["category"] == "draft":
            continue  # drafts are excluded from listing on purpose
        result = contracts.get_contract_pages(settings, doc_id, topics)
        shown = {p.page for p in result.pages}
        needed = set(info["term_pages"])
        row = per_category[info["category"]]
        row["docs"] += 1
        row["term_pages"] += len(needed)
        row["found"] += len(needed & shown)
        row["shown"] += len(shown)
        row["needed_shown"] += len(needed & shown)
        row["total"] += result.total_pages
        missed = sorted(needed - shown)
        if missed:
            misses.append(
                {"document": doc_id, "category": info["category"], "missed_pages": missed}
            )

    def ratio(a: int, b: int) -> float | None:
        return round(a / b, 3) if b else None

    categories = {
        name: {
            "docs": r["docs"],
            "recall": ratio(r["found"], r["term_pages"]),
            "pages_shown_share": ratio(r["shown"], r["total"]),
        }
        for name, r in sorted(per_category.items())
    }
    all_needed = sum(r["term_pages"] for r in per_category.values())
    all_found = sum(r["found"] for r in per_category.values())
    return {
        "documents": sum(r["docs"] for r in per_category.values()),
        "overall_recall": ratio(all_found, all_needed),
        "pages_shown_share": ratio(
            sum(r["shown"] for r in per_category.values()),
            sum(r["total"] for r in per_category.values()),
        ),
        "by_category": categories,
        "misses": misses,
    }


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] != "page-finder":
        print("usage: python -m ingenus_plugin.evals page-finder")
        raise SystemExit(2)
    print(json.dumps(page_finder_eval(), indent=2))


if __name__ == "__main__":
    main()
