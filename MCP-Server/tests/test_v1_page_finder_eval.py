"""The page finder is keyword search. This test pins what it can and cannot do, honestly.

Baseline measured 13 Oct 2026 on 29 labelled synthetic contracts. Wording the keyword list does not
contain (for example "retrospective discount") can be missed when the terms sit far from page 1.
We did NOT add those words to the list to make the number look better: the point is to show the risk.
"""

from __future__ import annotations

from v1_support import isolated_env, make_world  # noqa: F401  (pytest fixtures)

from ingenus_mcp.evals import page_finder_eval


def test_known_wordings_are_always_found():
    result = page_finder_eval()
    for category in ("easy", "synonym_listed", "hostile_text", "scanned_page"):
        assert result["by_category"][category]["recall"] == 1.0, category


def test_overall_recall_is_reported_and_misses_are_only_unlisted_wordings():
    result = page_finder_eval()
    assert result["overall_recall"] >= 0.9
    assert result["misses"], "If this is empty the eval is too easy; add harder contracts."
    assert {m["category"] for m in result["misses"]} == {"synonym_unlisted"}


def test_the_finder_does_not_show_everything():
    # Generous, but still selective: sending every page would defeat the point (G2).
    assert page_finder_eval()["pages_shown_share"] < 0.8
