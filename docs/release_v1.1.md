# v1.1 (laptop release): what is in, what is tested, what is not

**Date:** 10 Nov 2026. **Meaning of the label:** feature-complete and tested **on one laptop with synthetic data**. It is **not** hosted, **not** run by a second person on another machine, and **not** cleared for real Ingenus data. Plain "v1.1" is reserved for after those three. Tag: `v1.1`. The code version string (`__version__` 0.2.0, also in each log line as `plugin_version`) and the bridge version are unchanged on purpose, so installed bridges and old log lines stay consistent.

## 1. What is in

| Area | What it does | Decision / where |
|---|---|---|
| Contract-to-SAP check | `resolve_customer`, `get_contract_terms`, `get_contract_pages`, `get_rebate_setup`, `compare_contract_to_sap`; every quote is checked against its page in code; SAP is a mock | [0001](decisions/0001-phase1-v0-approach.md), README |
| Sign-in and per-person reading | Entra token on every request; SharePoint and OneDrive read as the signed-in person | [0004](decisions/0004-v1-per-user-sign-in-and-sharepoint-reading.md) |
| Several sources at once | SharePoint, OneDrive and a network folder listed in parallel, per-source status, `complete` flag, conflicts flagged | [0010](decisions/0010-v1-several-contract-sources-at-once.md) |
| `compare` health re-check | Just before figures, every source is asked again; if one does not answer the result is `complete: false`, with an `INCOMPLETE` summary and a `not_checked` entry. Figures never change. Adds about 2 s | checklist 2.7, demo guide 8b (HC-1 to HC-3) |
| Audit log and login log | Hash-chained log, copied to Postgres or SQLite | [0005](decisions/0005-v1-audit-log-with-hash-chain-and-central-store.md), [0008](decisions/0008-v1-postgres-for-audit-store-and-check-history.md) |
| Check history, stored terms | What earlier checks found, shown only for files the asker can open | [0006](decisions/0006-v1-shared-check-history-tool.md), [0011](decisions/0011-v1-stored-contract-terms.md) |
| Search | `search_contracts`: keyword and meaning (local embedding model, pgvector); counts files a person cannot open, never names them | [0012](decisions/0012-v1-keyword-search-over-stored-passages.md), [0013](decisions/0013-v1-meaning-search-with-a-local-embedding-model.md) |
| Guidance | Served by the server, `guidance/v8` (earlier versions kept) | [0003](decisions/0003-v1-guidance-served-by-the-server.md) |
| Operator dashboard | Read-only page, loopback only: activity, checks, audit trail, health. Reads the central store when there is one | `python -m ingenus_mcp.dashboard` |
| Concurrency fix | Stored terms lock rows in one order and retry a lost deadlock | commits `f7895dd`, `975c9bc` |

## 2. What is tested

- **Offline:** 351 tests collected; the suite passes (6 Node-bridge tests are skipped in this run). The Postgres tests run when the WSL Postgres is up.
- **Live, one laptop, dev tenant, synthetic data:** Chains A to F through SharePoint, OneDrive and the network folder (demo guide 8b); stored terms (8c); keyword and meaning search (8d, 8e); two people on one laptop (8f, `ingenus.tester`); finding 14 and finding 17 repeated live on 10 Nov; the `compare` re-check HC-1 to HC-3.
- **Load test, 10 Nov, laptop only:** 1, 5, 20 and 50 virtual users with no pauses; after the deadlock fix 0 errors at 5, 20 and 50; the log chain stayed intact and matched Postgres. Meaning search over 100,000 stored passages: about 160 ms for all customers, 12 ms for one (random vectors, so time only).

## 3. What is not done (do not claim these)

- **Not hosted.** No VM, no HTTPS, no second machine (waits on the Principal Architect, checklist 2.1).
- **Second-laptop tests not run:** earlier checks and stored terms for a second person with their own Claude account (TP-4, TP-5, TP-9, TP-12).
- **No real data.** The data policy and Legal's view on the model licence are open; the AI admin's go-ahead (4 Nov, relayed) covers the POC with synthetic data only.
- **Not measured:** SharePoint or OneDrive at real size, Claude Desktop's tool timeout, two server processes at once, a long run, server memory and CPU, real SAP, the quality of meaning search on real text.
- **Also open:** the real network share and read-only service account (IT), the break-it tests, the repeat of "the guide is fetched first" in fresh chats, and the checklist's hardening list (section 3).

Open items in full: [`v1_open_items_checklist.md`](v1_open_items_checklist.md). How to run and what each step proves: [`MCP-Server/docs/demo_guide.md`](../MCP-Server/docs/demo_guide.md).
