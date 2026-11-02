"""Meaning search (decision 0013): vectors in pgvector, merged with keyword search, same access rules.

Needs the local Postgres with pgvector (see test_v1_postgres.py); skips without it. Most tests use the
stand-in embedder `test-hash` (words hashed into numbers: shares words, not meaning), so they test the
plumbing. One test uses the real model and skips if its files are not on this machine.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from test_v1_postgres import pg_env  # noqa: F401  (pytest fixture)
from v1_support import isolated_env, make_world  # noqa: F401  (pytest fixtures)

from ingenus_mcp.core import contracts, documents, embeddings, passages
from ingenus_mcp.core.config import load_settings
from ingenus_mcp.tools.search_contracts import search_contracts

RETURNS = "Returns: expired goods may be returned within 30 days."


@pytest.fixture(autouse=True)
def fresh_cache():
    documents.clear_cache()
    yield
    documents.clear_cache()


@pytest.fixture
def pg(pg_env, monkeypatch):  # noqa: F811
    monkeypatch.delenv("INGENUS_RECORDS_DB")
    return load_settings().records_db


@pytest.fixture
def hashing(monkeypatch):
    monkeypatch.setenv("INGENUS_EMBED_MODEL", embeddings.TEST_MODEL)


def list_files(customer: str):
    return contracts.find_contract_files(load_settings(), customer, None)


def vector_count(target) -> int:
    with passages._vec_session(target) as conn:
        return int(conn.execute("SELECT count(*) FROM passage_vec").fetchone()[0])


def test_meaning_search_is_off_unless_a_model_is_named(pg, make_world):
    make_world([RETURNS], [], [])
    list_files("Acme")
    result = search_contracts("returns")
    assert result.hits and result.meaning_search is False
    assert all(h.matched_by == "keyword" and h.similarity is None for h in result.hits)
    assert "by keyword only" in result.note


def test_a_passage_with_no_word_in_common_in_the_query_is_found_by_meaning(pg, hashing, make_world):
    make_world([RETURNS], [], [])
    list_files("Acme")
    # "stock" is not in the passage, so the keyword search (all words must match) finds nothing
    result = search_contracts("returns expired stock goods")
    assert result.meaning_search is True and len(result.hits) == 1
    hit = result.hits[0]
    assert hit.matched_by == "meaning" and hit.similarity and hit.similarity >= 0.3
    assert "by keyword and by meaning" in result.note and "may not contain the words" in result.note


def test_a_passage_found_both_ways_is_marked_both_and_ranks_first(pg, hashing, make_world):
    make_world([RETURNS, "Payment: invoices are due in 45 days."], [], [])
    list_files("Acme")
    result = search_contracts("returns expired goods")
    assert result.hits[0].matched_by == "both" and "expired goods" in result.hits[0].text


def test_a_query_far_from_everything_gets_no_meaning_hit(pg, hashing, make_world):
    make_world([RETURNS], [], [])
    list_files("Acme")
    result = search_contracts("zebra quantum bicycle")
    assert result.hits == [] and result.meaning_search is True


def test_vectors_are_made_once_and_follow_the_passages(pg, hashing, make_world, tmp_path):
    rel = make_world([RETURNS], [], [])
    list_files("Acme")
    search_contracts("returns")
    first = vector_count(pg)
    assert first == passages_count(pg) > 0
    search_contracts("returns")
    assert vector_count(pg) == first  # not embedded again
    (tmp_path / "contracts" / rel).write_text("Payment: due in 45 days.", encoding="utf-8")
    documents.clear_cache()
    passages._SAVED.clear()
    list_files("Acme")  # the changed file replaces its passages, and their vectors go with them
    search_contracts("payment")
    assert vector_count(pg) == passages_count(pg) == 1


def passages_count(target) -> int:
    with passages._session(target) as conn:
        return int(conn.execute("SELECT count(*) FROM passage").fetchone()[0])


def test_vectors_of_another_model_are_dropped(pg, hashing, make_world):
    make_world([RETURNS], [], [])
    list_files("Acme")
    with passages._vec_session(pg) as conn:
        pid = conn.execute("SELECT passage_id FROM passage LIMIT 1").fetchone()[0]
        conn.execute(
            "INSERT INTO passage_vec (passage_id, model, embedding) VALUES (%(p)s, 'old-model',"
            " '[1,2,3]'::vector)",
            {"p": pid},
        )
    search_contracts("returns")
    with passages._vec_session(pg) as conn:
        models = [r[0] for r in conn.execute("SELECT DISTINCT model FROM passage_vec").fetchall()]
    assert models == [embeddings.TEST_MODEL]


def test_a_file_the_person_cannot_open_is_left_out_of_meaning_hits_too(
    pg, hashing, make_world, tmp_path
):
    rel = make_world([RETURNS], [], [])
    list_files("Acme")
    search_contracts("returns expired stock goods")  # vectors now exist
    (tmp_path / "contracts" / rel).unlink()
    documents.clear_cache()
    result = search_contracts("returns expired stock goods")
    assert result.hits == [] and result.complete is False
    assert [n.item for n in result.not_checked] == [rel]


def test_a_missing_model_leaves_keyword_search_working_and_says_so(
    pg, monkeypatch, make_world, tmp_path
):
    monkeypatch.setenv("INGENUS_EMBED_MODEL", "BAAI/bge-small-en-v1.5")
    monkeypatch.setenv("INGENUS_EMBED_DIR", str(tmp_path / "no_models_here"))
    make_world([RETURNS], [], [])
    list_files("Acme")
    result = search_contracts("returns")
    assert result.hits and result.meaning_search is False
    assert "Meaning search is off for this call" in result.note


def test_a_model_we_have_not_measured_is_refused_plainly(pg, monkeypatch, make_world):
    monkeypatch.setenv("INGENUS_EMBED_MODEL", "some/other-model")
    make_world([RETURNS], [], [])
    list_files("Acme")
    result = search_contracts("returns")
    assert result.hits and "not one we have measured" in result.note


def _row(pid, sim):
    return (pid, "doc", "sha", 1, None, "text", sim)


def test_a_meaning_hit_far_below_the_best_one_is_dropped_unless_the_words_match():
    rows = [_row("a", 0.80), _row("b", 0.74), _row("c", 0.66), _row("d", 0.60)]
    kept = [r[0] for r in passages.within_band(rows, set())]
    assert kept == ["a", "b"]  # within 0.10 of 0.80
    kept = [r[0] for r in passages.within_band(rows, {"d"})]
    assert kept == ["a", "b", "d"]  # a keyword match stays whatever its similarity
    assert passages.within_band([], set()) == []
    assert [r[0] for r in passages.within_band(rows, set(), band=1.0)] == ["a", "b", "c", "d"]


def test_a_short_name_chooses_the_model(monkeypatch):
    assert embeddings.resolve_name("nomic") == "nomic-ai/nomic-embed-text-v1.5-Q"
    assert embeddings.resolve_name(" BGE ") == "BAAI/bge-small-en-v1.5"
    assert embeddings.resolve_name("minilm") == "sentence-transformers/all-MiniLM-L6-v2"
    assert embeddings.resolve_name("some/other-model") == "some/other-model"
    monkeypatch.setenv("INGENUS_EMBED_MODEL", "bge")
    embedder = embeddings.get_embedder(load_settings())
    assert embedder.spec.name == "BAAI/bge-small-en-v1.5" and embedder.spec.dim == 384
    assert set(embeddings.ALIASES.values()) == set(embeddings.KNOWN)


def test_the_embedder_helpers(monkeypatch):
    assert embeddings.vector_text([0.5, -1.0]) == "[0.500000,-1.000000]"
    settings = load_settings()
    assert embeddings.get_embedder(settings) is None  # not named: off
    monkeypatch.setenv("INGENUS_EMBED_MODEL", "off")
    assert embeddings.get_embedder(load_settings()) is None
    monkeypatch.setenv("INGENUS_EMBED_MODEL", embeddings.TEST_MODEL)
    embedder = embeddings.get_embedder(load_settings())
    assert len(embedder.embed_query("a b c")) == 64
    assert embeddings.min_similarity(load_settings(), embedder) == 0.3
    monkeypatch.setenv("INGENUS_EMBED_MIN_SIM", "0.9")
    assert embeddings.min_similarity(load_settings(), embedder) == 0.9


NOMIC = "nomic-ai/nomic-embed-text-v1.5-Q"
MODEL_DIR = Path(__file__).resolve().parents[1] / "data" / "runtime" / "models"


@pytest.mark.skipif(
    not any(MODEL_DIR.rglob("model_quantized.onnx")),
    reason="the nomic model is not on this machine (python -m ingenus_mcp.embeddings fetch)",
)
def test_the_real_model_finds_a_rebate_by_a_different_word(pg, monkeypatch, make_world):
    monkeypatch.setenv("INGENUS_EMBED_MODEL", NOMIC)
    monkeypatch.setenv("INGENUS_EMBED_DIR", str(MODEL_DIR))
    make_world(
        [
            "Product C: 6.5% retrospective discount on net sales of Product C.",
            "Force majeure: a party is not liable for delay caused by events beyond its control.",
            "The supplier shall maintain records of manufacture and distribution.",
        ],
        [],
        [],
    )
    list_files("Acme")
    result = search_contracts("rebate paid back to the customer for buying more")
    assert result.meaning_search is True and result.hits
    assert "retrospective discount" in result.hits[0].text
    assert result.hits[0].matched_by == "meaning"
