# 0012: v1 keeps contract passages in the one Postgres database and searches them by keyword (`search_contracts`)

**Date:** 2 Nov 2026 · **Status:** built and tested offline and on the local Postgres 18 (synthetic data, 2 Nov 2026); **not yet tried through Claude Desktop**, guidance v6 (2 Nov 2026) tells Claude when to search; live QA SQ-1 to SQ-6 in `demo_guide.md` section 8d is **not run yet** (step 3a) · **Phase:** 1, v1 (`MCP-Server/`), step 3a of the [records and search index proposal](../proposal/records_and_search_index_impact_analysis_and_proposal.md)
**Adds:** one tool (`search_contracts`) and one table (`passage`), as the read-only rule requires a decision for each. Meaning search (step 3b) is a separate decision.

## Context

- **SAID (Sridhar, 2 Nov 2026):** "Have everything in one database. Then start doing 3a with ADR." Earlier (2 Nov): "Go with pgvector."
- Today Claude finds a clause through the page finder, which knows only a fixed list of topic words (the demo guide's "odd wording" test shows it can miss). Terms are already stored (decision 0011); passages are not.
- IT's Windows Postgres 18 has no `pgvector` and installing into it needs admin rights. A user-level Postgres 18.6 with `pgvector` 0.8.7 runs in WSL on port 5433 (cheat sheet; synthetic data only, trust authentication).

## Decision

1. **One database for everything.** Audit events, check history, stored terms and now passages (and later the vectors of step 3b) live in the **same Postgres database**: `ingenus_audit`, role `ingenus_server`, on the WSL Postgres (`INGENUS_PG_PORT=5433`). No second database to start, back up or secure. The Windows Postgres on port 5432 is no longer used by the server; its old rows (synthetic) are **not migrated** and come back as customers are checked. The audit log was copied across with `audit ship` (134 events; the local file stays the first write, decision 0008).
2. **Table `passage`** (Postgres only): `passage_id` (hash of document id, fingerprint, page, position), `customer_id`, `document_id` (with source), `fingerprint` (`sha256_12`), `page`, `section` (the heading line above it, if any), `text`, `last_used`, and a generated `tsvector` column with a GIN index for keyword search. Same retention as terms: **90 days from last use**, deleted by `audit prune`.
3. **How passages are filled: lazily, by code, no Claude.** When `find_contract_files` (which `get_contract_terms` also calls) lists a customer's files for someone, each **non-draft** file's pages are split into passages (one per paragraph or clause, long ones cut at about 1,200 characters on a sentence end) and stored for that fingerprint. A changed file replaces its passages (old fingerprint deleted). Drafts are left out, as they are from listings. One process saves a given file content once; a file opened by a search is saved again if it changed. Saving never fails a tool call (same rule as terms).
4. **New tool `search_contracts(query, customer?)`.** Runs a Postgres full-text query (`websearch_to_tsquery`, ranked with `ts_rank`), narrowed by customer when given, returns the top passages with file, page, section and a short quote, plus a note that **search results are for finding, never for numbers in a check** (a rate found by search still goes through `get_contract_pages` and the quote check). It is read-only.
5. **Who sees what.** Passages are a second copy of text, so each candidate file is checked **as the asking person**: the server asks the source for that one file (`stat`, as the signed-in user for SharePoint and OneDrive) and drops the hit if it cannot be opened. Only the top 20 candidates are checked, to keep it cheap. The network share is the service account's view (decision 0007). A source that cannot be reached means those hits are left out and the answer says so (`complete` false, as in decision 0010).
6. **Never in the logs:** passage text is not written to the audit log or the check history. The log holds the tool's arguments as for every tool (so the query words, trimmed to 300 characters) and counts of hits, never the passages.
7. **Without Postgres** the tool says search is not available (SQLite has no full-text column of this kind in our schema). Records and checks still work on SQLite.

## Options considered

| Option | Why not |
|---|---|
| A second database for search | More to run and secure; the cost of one database is nothing at POC size. Said by Sridhar: one database |
| A separate search engine (OpenSearch or similar) | A new service to host and approve at Ingenus; Postgres full-text is enough for hundreds of contracts |
| Fill the index in bulk by a crawler | Needs application-level read access; rejected in decision 0011 and the proposal (option B) |
| Let Claude choose the passages to store | Not needed: passages come from parsing, and a stored passage is only used to find a page |

## Consequences and limits

- **Search covers only files someone has read** (lazy fill). A file nobody opened is not searchable.
- **Keyword only:** it finds the words typed (and their stems), not meaning. "Retrospective discount" will not match "rebate". Step 3b adds meaning search on the same table.
- **Scanned or image-only pages** have no text and no passages (same limit as reading).
- **English text search configuration** (`english`) is assumed for the synthetic contracts; Ingenus's wording is unknown (**verify**).
- **WSL Postgres is a dev setup:** no password, localhost only, stops when WSL stops, start command in the cheat sheet. The production database (version, OS, `pgvector` availability) is **unknown**; ask Aditya. The code only needs standard Postgres 18 features for 3a; `pgvector` is needed from 3b.
- **Not verified:** speed and ranking quality on real contracts; two server processes writing passages at once.

## Tests (`tests/test_v1_search.py`, 15; they use the local Postgres and skip without it)

Passages stored once per fingerprint (idempotent); a changed file replaces its passages; a hit for a wording the page finder misses; narrowed by customer; a file the asker cannot open is dropped; a source down is reported, not "no hit"; no passage text in the audit log; pruning by last use; tool says "not available" without Postgres; (a search result cannot feed a comparison is held by the tool text and the guidance only, not by a test).

## Build order

Steps 1 to 5 are done (2 Nov 2026); step 6 is open. 1. `core/passages.py`: split pages, DDL, save, replace, search, prune. 2. Hook the save into the listing (`find_contract_files`). 3. `tools/search_contracts.py` (and its audit entry). 4. Tests and ruff and `check.py`. 5. New guidance version (v6): when to search, and that a hit is not a number. 6. Live QA in Claude Desktop.

## Related

- [Records and search index proposal](../proposal/records_and_search_index_impact_analysis_and_proposal.md) · [0008: Postgres](0008-v1-postgres-for-audit-store-and-check-history.md) · [0010: several sources](0010-v1-several-contract-sources-at-once.md) · [0011: stored terms](0011-v1-stored-contract-terms.md)
