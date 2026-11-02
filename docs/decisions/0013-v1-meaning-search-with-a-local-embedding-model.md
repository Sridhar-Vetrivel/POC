# 0013: v1 adds meaning search to `search_contracts`, with a local embedding model and pgvector

**Date:** 2 Nov 2026 · **Status:** built and tested offline and on the local Postgres 18 with pgvector (synthetic data, 2 Nov 2026); **not yet tried through Claude Desktop** · **Phase:** 1, v1 (`MCP-Server/`), step 3b of the [records and search index proposal](../proposal/records_and_search_index_impact_analysis_and_proposal.md)
**Adds:** no new tool (it extends `search_contracts`, [0012](0012-v1-keyword-search-over-stored-passages.md)), one table (`passage_vec`), one local model and one command line (`python -m ingenus_mcp.embeddings`).

## Context

- **SAID (Sridhar, 2 Nov 2026):** "Go with pgvector", then "Proceed with 3b", then, after the policy check below: "No, Download an embedding model and do."
- Keyword search (0012) finds the words typed. Live QA SQ-3 showed the gap: "retrospective discount" finds nothing, because Chain A says "rebate".
- The synthetic contracts use six words for the same idea (rebate, back-end discount, retrospective discount, year-end volume bonus, volume incentive, price protection credit), which makes them a fair test.

## Policy check (Psiog AI Policy v1, revision received 27 Oct 2026)

- **Result: not addressed.** The policy has no tier for a locally run open-source model (`[TOOLS-TIERS]`), says nothing about downloading models, and `[SCOPE-COVERAGE]` leaves three tool categories "not yet covered in operating detail", with ambiguity "clarified with the AI admin". The licence of the model is a question for Legal, InfoSec and BD (`[SCOPE-ACCOUNT]`).
- **Sridhar decided to proceed (2 Nov 2026).** **Open:** the AI admin has not been asked. **Condition kept in the meantime:** the model is used with **synthetic data only**. Real Ingenus contract text is C2 at least (`[DATA-MATRIX]`: Delivery head checks the customer contract first, and `[TOOLS-CUSTWORK]` names AI, sub-processor, third-party-processing and residency clauses), so it needs that clearance **before** it reaches any model, local or not.

## Decision

1. **Model: `nomic-ai/nomic-embed-text-v1.5` (quantised ONNX, 134 MB, 768 numbers per passage).** Run in-process on the CPU through the `fastembed` package (ONNX runtime, no PyTorch), so no contract text goes to a service and no model server has to be hosted. Model file hash (first 16 hex of SHA-256): `b4342336debaea79` (the same file in two downloads).
2. **It was chosen by test, on our data** (153 passages of the synthetic contracts, 15 questions written in other words than the contracts use; scratchpad script, not in the repo):

   | Model | Size | Numbers | MRR | Mean precision@5 | Time for 153 passages (CPU) | Licence (per the package's list; **verify on the model card**) |
   |---|---|---|---|---|---|---|
   | nomic-embed-text-v1.5 (quantised) | 134 MB | 768 | **0.97** | 0.76 | 4.0 s | Apache-2.0 |
   | bge-small-en-v1.5 | 65 MB | 384 | 0.92 | 0.73 | 1.9 s | MIT |
   | all-MiniLM-L6-v2 | 88 MB | 384 | 0.84 | 0.71 | 0.8 s | Apache-2.0 |

   MRR is how high the first right passage ranks (1.00 is always first). The three are close; MiniLM missed "which law governs the agreement" completely. Precision@5 is capped because some questions have fewer than five right passages. **Small test (15 questions, one synthetic corpus): it picks a model, it does not prove quality on Ingenus's contracts.** `gemma3:4b`, the other model on this laptop, was not tested: it is a text-generating model, not an embedding model.
3. **Never downloads while running.** `get_embedder` loads files that are already in `INGENUS_EMBED_DIR` (default `MCP-Server/data/runtime/models`, git-ignored). Downloading is one explicit command: `python -m ingenus_mcp.embeddings fetch`. `python -m ingenus_mcp.embeddings status` says what is set and whether it loads.
4. **Chosen in `.env`, off unless named.** `INGENUS_EMBED_MODEL` takes `nomic`, `bge` or `minilm` (or the full name; only these three are accepted, each with its own measured cut-off and prompt prefixes). Unset or `off` means keyword search only, as in 0012. Switching model means: change the line, `fetch`, restart; the next search embeds the passages again. A model that is not downloaded, not installed, or not one we have measured leaves keyword search working, and the result says "Meaning search is off for this call".
5. **Table `passage_vec`** (Postgres with pgvector): `passage_id` (deleted with its passage), `model`, `embedding` (`vector`, any size, no index yet). One model's vectors at a time: when the model name changes, the other model's vectors are deleted and the passages are embedded again. Passages are embedded **when searched** (up to 400 per search), not when listed, so listing stays fast. `CREATE EXTENSION vector` needs pgvector on the server; without it the search says meaning search is off.
6. **Merge, then the same checks.** Keyword hits and meaning hits (cosine similarity at or above a cut-off) are merged by reciprocal rank fusion, a passage found both ways ranks above one found one way. Each hit says `matched_by` (`keyword`, `meaning`, `both`) and, for meaning, its `similarity`. Then every candidate file is opened **as the asking person** and the fingerprint is checked, exactly as in 0012. The note says a meaning hit "may not contain the words you typed".
7. **Cut-off 0.55 for nomic and bge, 0.30 for minilm** (setting `INGENUS_EMBED_MIN_SIM` overrides it). MiniLM scored 0.39 to 0.78 on real questions and 0.16 or less on unrelated ones. Measured: on the synthetic set, real questions scored 0.64 or more against their best passage and unrelated ones 0.53 or less. On Chain A's real passages (2 Nov) "retrospective discount" scored 0.58, "volume rebate" 0.68, "rebate" 0.72, "chocolate cake recipe" below the cut-off.
8. **Guidance v7** (v6 is left as it was): the playbook explains `meaning_search`, `matched_by` and `similarity`, and keeps the rule that a hit is only a pointer and never a number for a check.
9. **Same rules as 0012:** Postgres only; 90 days from last use (vectors go with their passages); no passage text in any log; no new write to SAP or to any source. The model files are not part of the repo.

## Options considered

| Option | Why not |
|---|---|
| A larger model such as `gemma3:4b` through Ollama | A text-generating model, not trained to compare meaning; slow on a CPU; thousands of numbers (pgvector indexes plain vectors up to 2,000 numbers: verify) |
| A hosted embedding service | Contract text would go to a second vendor; the policy does not cover it and the Ingenus approval would be harder |
| `sentence-transformers` with PyTorch | Several GB of dependencies for the same result; the ONNX route is a 134 MB file |
| Embed every passage when the file is listed | Slows `find_contract_files` and `get_contract_terms`; searching is rarer than listing |
| An approximate-nearest-neighbour index (HNSW) now | Not needed at hundreds or thousands of passages; add when Ingenus's volume is known |

## Consequences and limits

- **Meaning search can return something loosely related.** A cut-off cannot tell "absent" from "present in other words": on Chain A, "which law applies" (no such clause there) still scored 0.62 against unrelated clauses. That is why every hit is a pointer and the guidance says to read the page before relying on it.
- **The cut-off is tuned on synthetic text.** Ingenus's contracts will score differently. It must be checked on real wording (after the policy route above) and is one setting to change.
- **First meaning search of a process loads the model** (a few seconds) and embeds missing passages (about 0.03 s each here).
- **Production:** the model runs where the server runs, on the CPU. Memory and time on the Ingenus server are **unknown** (Aditya provisions it). pgvector availability on the production Postgres is **unknown (verify)**.
- **A model change means re-embedding** every passage (done automatically at the next search).
- **Not verified:** a live run through Claude Desktop (steps MQ-1 to MQ-5 in `MCP-Server/docs/demo_guide.md`, section 8e); two server processes embedding at once; model licences on their cards.

## Tests

`tests/test_v1_meaning.py` (10, Postgres with pgvector, skips without it; one uses the real model and skips if its files are absent): off unless named; a passage found by meaning that keyword cannot find; found both ways ranks first; a far query gets no meaning hit; vectors made once and removed with a changed file; another model's vectors dropped; a file the person cannot open is left out of meaning hits too; a missing or unmeasured model leaves keyword search working and says so; the helpers; the real model finds a rebate by a different word. `tests/test_v1_guidance.py`: v7 changes only the playbook and keeps the pointer rule.

## Related

- [0012: keyword search](0012-v1-keyword-search-over-stored-passages.md) · [0011: stored terms](0011-v1-stored-contract-terms.md) · [0008: Postgres](0008-v1-postgres-for-audit-store-and-check-history.md) · [Records and search index proposal](../proposal/records_and_search_index_impact_analysis_and_proposal.md)
