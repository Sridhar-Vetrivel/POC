# 0011: v1 keeps the contract terms a check has verified, and hands them back while the file is unchanged

**Date:** 23 Oct 2026 · **Status:** built and tested offline and on the local Postgres 18 (synthetic data); **not yet tried through Claude Desktop** · **Phase:** 1, v1 (`MCP-Server/`), step 2 of the [records and search index proposal](../proposal/records_and_search_index_impact_analysis_and_proposal.md)
**Adds:** one tool (`get_contract_terms`) and one store (`records.py`), as the read-only rule requires a decision for each.

## Context

- **SAID (Sridhar, 23 Oct 2026):** build the records (key values plus quote) and the search index we agreed. The agreed design (Guidelines note section 1, Ontology approach section 9, P4): read a document once, keep its facts with proof of where they came from, check the file's fingerprint before using them, and let the file stay the truth.
- Today Claude reads and extracts the same terms again on every question. That is slow, can give slightly different terms each time, and leaves nothing to review once.
- Decisions taken on 23 Oct 2026 and carried here: per-user (lazy) access; records stay `verified` only (no accept or reject tool yet); Postgres on the VM.

## Decision

1. **A term is kept when code has verified it.** After `compare_contract_to_sap` runs, every term whose quote is on the cited page and holds the rate (the same check `compare` applies) is stored: kind, product, rate, effective date, document id, page, clause, the exact quote, the file's content fingerprint (`sha256_12`), who verified it and when. Saving the same term from the same content twice is one record. A term that fails the check is not stored. A store error never fails the check.
2. **Not stored:** page text, tokens, anything a person said to Claude. The quote is stored on purpose (it is the proof); that is why this is **its own store** (`INGENUS_RECORDS_DB`) and not the check history, which promises to keep no quotes (decision 0006).
3. **New tool `get_contract_terms(customer)`.** It resolves the customer, lists that customer's files (all sources, as `find_contract_files` does) and, for each file, says `use_stored_terms` (its terms are in `stored`) or `read_pages` (none stored for this content: read it and extract as today). Stored terms are returned as ready-made `ExtractedTerm` objects to pass unchanged in `terms` of `compare_contract_to_sap`, which **checks every quote against the page again**, so a stored term gets no shortcut past the proof.
4. **Freshness: the file stays the truth.** A stored term is returned only while the file's fingerprint equals the one it was stored with. If the file is listed and its fingerprint differs, the term is set aside (`status` stale) and is not returned; the file shows `read_pages`. The result says how many were set aside.
5. **Who sees what.** Stored terms are returned only for files in **the asking person's own listing**. SharePoint and OneDrive list as that person, so a file they cannot open is not listed and its terms are not returned. A term whose file is not listed is left alone, neither shown nor set aside. The network share is listed as the service account, as in decision 0007.
6. **Retention (Sridhar, 23 Oct 2026): 90 days from last use.** Returning a term restarts its clock. `python -m ingenus_mcp.audit prune` deletes terms not used for N days (`--days`; the audit and history use their own, longer limit, so run it with `--days 90` for terms or keep one schedule). **Assumed:** the same N for everything is acceptable for the POC (**to confirm**).
7. **Who reads the database (Sridhar, 23 Oct 2026):** users reach stored terms only through the tool; direct database access is for admins, with a separate server role (`ingenus_server`, not `postgres`).
8. **Where it lives:** `INGENUS_RECORDS_DB`: a file (default `MCP-Server/data/runtime/records.sqlite`), `off`, or, when `INGENUS_PG_HOST` is set, the Postgres database. With `off`, no term is kept and every file shows `read_pages`.

## Options considered

| Option | Why not |
|---|---|
| Store terms in the check history | It promises to keep no quotes (0006); mixing them breaks that promise and its test |
| Records written by Claude through a new "save" tool | A write tool by Claude would let a wrong term in without the quote check. Saving only what `compare` verified keeps the proof in code |
| A background crawler that extracts everything | Needs application-level read access and a second LLM route (the proposal, option B and "Option Y"); not for the POC |
| Fingerprint by modified time or eTag | Changes without content changing, and differs per source. The content hash (`sha256_12`) is already computed |

## Consequences and limits

- **Records appear only as customers are checked.** A file nobody has checked shows `read_pages`. There is no bulk load.
- **A file with no rebate or fee terms** (for example Chain E's Amendment 3, which changes payment terms only) has no stored terms, so it always shows `read_pages` and is read again. It is cached and cheap; marking "read, nothing to store" is a possible follow-up.
- **A stored term is verified by code, not accepted by a person.** The quote check proves the rate is on the page, not that it is the right clause (the check's own message says so). A wrong term repeats until its file changes. A reject or accept step is left out for now (decision 23 Oct 2026) and is the main risk to revisit.
- **A new file that supersedes an old one is not caught by the fingerprint** (the old file did not change). Each `get_contract_terms` call lists the sources again, so a new file appears as `read_pages` in the same call; there is no stale catalog.
- **A source down** is reported as in decision 0010 (`complete` false); stored terms of files in that source are not returned, because those files are not listed.
- **The earlier terms of a replaced amendment** are stored as well as the new ones; `compare` already works out which applies from the effective dates, so nothing else decides it.
- Tests (`tests/test_v1_records.py`, 13): kept after a check, returned to the next person, same numbers when passed back to `compare`, idempotent, a failed quote is not kept, a changed file sets terms aside and stays set aside, no listing means no terms, quotes stored but no tokens, pruning by last use, using a term restarts the clock, store off, unknown customer, a store error does not fail the check. The Postgres path was exercised on the local database with synthetic Chain X data and cleaned up afterwards.

## Not built or not verified

- A live run through Claude Desktop: guidance that tells Claude to call `get_contract_terms` first (a new guidance version) is not written yet, so Claude does not use the tool unprompted today.
- The search index (`search_contracts`), meaning search, and an accept or reject tool.
- Two server processes writing at once, and Postgres roles with less than ownership of the tables.

## Related

- [Records and search index proposal](../proposal/records_and_search_index_impact_analysis_and_proposal.md) · [0006: check history](0006-v1-shared-check-history-tool.md) · [0008: Postgres](0008-v1-postgres-for-audit-store-and-check-history.md) · [0010: several sources](0010-v1-several-contract-sources-at-once.md)
