# Records and search index in the MCP server: impact analysis and proposal

**Status:** proposal, 23 Oct 2026. Nothing in it is built. Nothing is confirmed by Ingenus.
**For:** Sridhar and Aditya (Psiog).
**Ask (Sridhar, 23 Oct 2026):** build the **records** (key values plus quote) and the **search index** that we already agreed in the design. It is the answer to Abhishek's first question, "repository or fetch every time?" (his four questions and our answers are in the Guidelines note linked below).

Labels used below: **Said**, **Doc** (read in this repo or the solution-approach notes), **Psiog proposal** (ours, to confirm), **Assumed**, **Unknown / verify**.

Read with: [source routing proposal](multi_source_routing_impact_analysis_and_proposal.md) (the same work seen from "which source?").

---

## 1. Verdict

**Build it, in this order: (1) a catalog of documents with their source, (2) records, (3) a search index with keyword and meaning (vector) search, using a local embedding model.** The file stays the truth: every stored record or passage is checked against the file's fingerprint before it is used.

**Decisions taken (Sridhar, 23 Oct 2026):** per-user lazy indexing; records stay `verified` only (no accept or reject tool yet); keyword **and** meaning search from the first cut, with a **local open-source embedding model** and search on **Postgres only**; `compare` relies on guidance and a flag when a source is down. Section 8 lists them. One of them goes against my recommendation (meaning search now, not later); section 4.7 says what that costs.

A correction to my own earlier note. In the source routing proposal I listed a catalog or index as "not needed for a pilot". That contradicted the design we had already agreed ([Guidelines and Review Methodology](../../../2026/Solution_Approach/Guidelines_and_Review_Methodology.md) section 1, [Ontology approach](../../../2026/Solution_Approach/Ontology_Approach.md) section 9, [P4 MCP plug-in](../../../2026/Solution_Approach/Proposals/P4_MCP_Plugin.md)). The routing proposal is now **step 1 of this one**: the catalog is also how a question finds its source, without anyone changing a setting.

**Effort (estimate, not prototyped):** about **8 to 11 working days** for steps 2 and 3 (records, then keyword and meaning search), on top of the 5 to 7 days for source routing. About 13 to 18 working days in total for one person.

---

## 2. What was said, agreed and unknown

| | |
|---|---|
| **Said (Sridhar, 23 Oct 2026)** | The records (key values plus quote) and the search index are what we have to build; the approach was discussed before; two diagrams were given. |
| **Doc: the agreed design** | Read each important document **once**, store its facts in a fixed form with proof, and **check the source file's fingerprint before any record is used**; if it changed, set the record aside and re-read. The repository is a **working copy, not the system of record**. Records are for checks (exact numbers); the search index is for open questions and **never for numbers**. |
| **Doc: what a record holds** | Value, source file and fingerprint, page and exact quote, effective dates, what it replaces, how it was read (schema, prompt, model), review status ("accepted by Abhishek"). |
| **Doc: the stack** | One PostgreSQL database; full-text search built in; **pgvector** for meaning search (**verify** on the target tier); a **separate embedding model** because Claude does not make embeddings (**verify** provider). |
| **Doc: the tools** | P4 names `get_contract_terms` (freshness check, extract if new, value plus page plus quote checked in code) and `search_contracts` (cited passages from the index). |
| **Assumed** | Claude does the extraction (option X in P4), so no second LLM route is added. Records appear as contracts are checked. |
| **Unknown / verify** | Ingenus's contract volume and folder structure (how an amendment is linked to its master: Guidelines section "limits" names this as unknown). Whether Ingenus accepts a second stored copy of contract text. Which embedding provider Ingenus accepts. Who reviews and accepts records. |

---

## 3. What exists in the code today, and the gap

| Already built (reuse) | Where |
|---|---|
| A fingerprint per file: `sha256_12` and a version (modified time and size, or the SharePoint eTag) | [documents.py](../../MCP-Server/src/ingenus_mcp/core/documents.py), [sources.py](../../MCP-Server/src/ingenus_mcp/core/sources.py) |
| A parsed-text cache keyed by who reads what, trusted for a few seconds, re-checked against the version | `load_document` |
| Code that proves a quote is on the cited page and holds the rate | [citations.py](../../MCP-Server/src/ingenus_mcp/core/citations.py) |
| Customer names, aliases, SAP ids | [customers.py](../../MCP-Server/src/ingenus_mcp/core/customers.py) |
| A database layer that runs one SQL text on SQLite (POC) or Postgres, creates its schema on first use, and never fails a tool call | [db.py](../../MCP-Server/src/ingenus_mcp/core/db.py), [decision 0008](../decisions/0008-v1-postgres-for-audit-store-and-check-history.md) |
| A "can **this** person open that file?" check before showing stored results | [history.py](../../MCP-Server/src/ingenus_mcp/core/history.py) `read_history` |
| One comparison that picks the term in force on a date | [compare.py](../../MCP-Server/src/ingenus_mcp/core/compare.py) |

| Missing (this proposal) | |
|---|---|
| Stored terms that outlive one chat (today Claude extracts them again on every question) | records |
| Stored passages, searchable | search index |
| A list of known documents with their **source** and last-seen time | catalog |
| A freshness check that sets a record aside when the file changes | freshness |
| A way to say "this record was accepted by a person" | review status |

Today every question re-reads and re-extracts. That is slow, can give slightly different extractions, leaves nothing to review once, and the page finder is keyword-only (the demo guide's "odd wording" test shows it can miss a clause).

---

## 4. The proposal (Psiog proposal, to confirm)

### 4.1 The shape

```
Contract file (any source)
   |  fingerprint = version + sha256        <- freshness check compares this
   v
Read once by code (no LLM): pages -> passages
   |--> CATALOG   document, source, customer, kind, draft?, fingerprint, last seen
   |--> SEARCH    passage: file, page, section, text, keyword index
   v
Claude extracts terms from the returned pages (as today)
   v
Code verifies each quote on its page      (as today)
   v
RECORDS   value + effective date + file + fingerprint + page + quote + status
```

The catalog and the passages need **no LLM**: they come from parsing the file. Only records need Claude's extraction. So the catalog and the search can be filled in bulk later, while records fill in as customers are checked.

### 4.2 Tables (illustrative; the existing layer already runs one SQL text on SQLite and Postgres)

| Table | Holds | Key columns |
|---|---|---|
| `document` | One row per file in a source | `document_id` (with the source), `source`, `path`, `customer_id`, `kind`, `is_draft`, `version`, `sha256`, `pages`, `first_seen`, `last_seen` |
| `term` (the records) | One accepted-by-code term | `term_id`, `customer_id`, `kind`, `product`, `rate_pct`, `effective_date`, `document_id`, `fingerprint`, `page`, `clause`, `quote`, `extraction_version`, `status` (`verified`, `accepted`, `rejected`, `stale`), `verified_at`, `accepted_by`, `accepted_at` |
| `passage` | One passage per clause or page | `document_id`, `fingerprint`, `page`, `section`, `text`, keyword index |

"Replaces" is not stored as a link. The comparison already works out which term is in force from the effective dates, and that stays the **single** place the rule lives. A stored record only needs its date.

### 4.3 The tools

| Tool | What it does | Changes |
|---|---|---|
| `find_contract_files` (existing) | Reads the **catalog** instead of listing every source each time. Says when each source was last listed | changed |
| `get_contract_terms(customer, as_of)` (new, from P4) | Runs the freshness check on each file. Returns the **records in force** (value, quote, page, status). For any file with no record, or a changed file, returns the relevant pages so Claude can extract | new |
| `compare_contract_to_sap` (existing) | Unchanged maths. After the quote check, it **stores each term that passed** as a record (idempotent: same file, page, quote, rate gives the same record) | small change |
| `search_contracts(query, customer?)` (new, from P4) | Returns cited passages (file, page, section, quote). **Never numbers for a check.** | new |
| `record_decision(term_id, accept or reject, reason)` (new, optional) | Lets a person accept or reject a record. P4 says this brings part of the foundation back. Aditya decides | optional |

### 4.4 The freshness check, and its hole

Before a record or passage is used, the server asks the file's source for that one file's version (a cheap call) and compares it with the stored one. If it changed, the record is marked `stale` and the file is re-read.

**The hole (already named in the Guidelines note):** a changed file is caught; **a new file that supersedes an old one is not**, because the old file did not change. The only protection is to **list each source again** now and then. So: re-list every source when the catalog is older than a set time (a setting, for example 10 minutes), or when the user asks for a refresh. Every answer says when each source was last listed. A source that cannot be listed is reported as not checked, never as "no contract".

### 4.5 How a question finds its source (answer to the routing ask)

"Check Chain A against SAP" is looked up in the **catalog** by customer. The catalog row already says which source each file is in, and the `document_id` carries that source, so the other tools route by it. The first time a customer is asked about, the server lists all sources (the fan-out in the [routing proposal](multi_source_routing_impact_analysis_and_proposal.md)); after that it uses the catalog and re-lists on the timer.

### 4.6 Who can see what (the hard part)

SharePoint and OneDrive are read **as the signed-in user** (delegated; decision 0004). The network share is read as one service account (decision 0007). A stored passage or record is a **second copy** of text that one user could open and another could not.

| Option | How | Cost |
|---|---|---|
| **A. Per-user, lazy (recommended for the POC)** | Index a file when a user reads it. Before returning any stored record or passage, **check that this user can open the file** (the pattern in `read_history`). Files nobody has read are not indexed | No change to the consent we have. The catalog fills as people use it. Search covers only files someone has touched |
| B. A background crawler | A service identity reads everything on a timer | Needs **application** (not delegated) read permission and a security review at Ingenus. The dev setup chose delegated-only on purpose. Do not take this on without Ingenus IT |

Under A, the first question about a customer lists that customer's sources as that user; later questions use the catalog but still check that user's access. For the network share, access is whatever the service account sees, as today.

Stored copies are protected like the source: kept in the same database, deleted when the file is gone from the source (found at the next freshness pass), and **never written to the logs** (the logs hold pointers, fingerprints and quotes only; see the [Sensitive data note](../../../2026/Solution_Approach/Sensitive_Data_Safety_Approach.md), G7).

### 4.7 Search: keyword and meaning together (decided 23 Oct 2026)

| Part | What | Needs |
|---|---|---|
| Keyword | Full-text search on passages, narrowed by customer; finds exact words ("WAC", "§9.2") | Built into Postgres |
| Meaning | Vector search: the passage whose meaning is closest to the question, narrowed by customer first | An **embedding model** and the **pgvector** extension on Postgres (**verify** it installs on the local Postgres 17 and, later, on the VM database) |
| Combined | Run both, merge the results, show file, page, section and quote | A small ranking rule, tested on the synthetic set |

**Choices made:**
- **Embedding model: a local open-source model** run on the server. Contract text never goes to a second vendor, which also makes the later Ingenus approval simpler ([Sensitive data note](../../../2026/Solution_Approach/Sensitive_Data_Safety_Approach.md), open question 6: it is a second route for contract text only if the model is hosted). Which model, and its size, speed and quality on contract text, is **unknown (verify)**: pick two or three candidates and test them on the synthetic contracts and the 16 golden questions' wording before choosing. I name none here because I have not tested any.
- **Postgres only for search.** SQLite has no vector extension. Without Postgres the two search tools say they are not available; the catalog and the records still work on SQLite.

**What this costs against my recommendation (keyword first):** about 2 to 3 more days; a model to download, version and keep with the server (it joins the "versioned prompts, skills and schemas" rule: a changed model means re-embedding every passage); more CPU and memory on the VM; and a vector column to keep in step with the passage table. In return, search finds a clause by meaning when the wording is unusual, such as "retrospective discount" for a rebate (the demo guide's known miss).

Keyword alone already fixes part of the "unusual wording" limit of today's page finder, because it searches every passage and not a fixed list of topic words. Meaning search adds the rest.

### 4.8 What the user sees

| Question | Today | With records and the index |
|---|---|---|
| "Check Chain X against SAP as of 31 Aug 2026" (second time) | Claude reads three PDFs again and re-extracts | `get_contract_terms` returns the stored terms, each with its quote, page and status; Claude only compares. Same stored terms give the same findings every time |
| The Chain X amendment was edited after the first check | Not noticed unless re-read | The fingerprint differs, the record is set aside, the file is re-read, and the answer says so |
| "Where does the Chain X contract mention returns?" | The page finder, topic words only | `search_contracts` returns the passage with file, page, section and quote. No number from it is used in a check |
| A user who cannot open a SharePoint file asks about it | n/a | Gets nothing from the index for that file |

---

## 5. Impact analysis: what changes

| Area | File | Change | Size (estimate) |
|---|---|---|---|
| Catalog | new `core/catalog.py` | Document rows, listing on a timer, fingerprint check, purge of deleted files | medium |
| Records | new `core/records.py` | Store a verified term; read terms in force for a customer and date; mark stale; accept or reject | medium |
| Passages and search | new `core/passages.py`, `core/embeddings.py` | Split pages into passages; keyword search; local embedding model and vector search (Postgres only); combined ranking; re-embed when the model version changes | medium to large |
| Storage | [db.py](../../MCP-Server/src/ingenus_mcp/core/db.py) | Add the three tables to the schema; full-text pieces differ per engine | small |
| Tools | new `tools/get_contract_terms.py`, `tools/search_contracts.py`, optional `tools/record_decision.py` | Found automatically at start-up (the tool registry) | medium |
| Find files | [contracts.py](../../MCP-Server/src/ingenus_mcp/core/contracts.py), [find_contract_files.py](../../MCP-Server/src/ingenus_mcp/tools/find_contract_files.py) | Read the catalog; say when each source was last listed | medium |
| Compare tool | [compare_contract_to_sap.py](../../MCP-Server/src/ingenus_mcp/tools/compare_contract_to_sap.py) | After the quote check, store the passing terms as records; the maths is untouched | small |
| Check history | [history.py](../../MCP-Server/src/ingenus_mcp/core/history.py) | Overlaps with records (both keep "what a check relied on"). Keep for now; decide later whether to fold in | decision |
| Settings | [config.py](../../MCP-Server/src/ingenus_mcp/core/config.py) | Index on or off, re-list age, retention | small |
| Guidance | `MCP-Server/guidance/v3/` (new; v2 stays) | Playbook: ask for terms first, extract only what has no record; show the status of each record; say when a record was set aside; never use search results as numbers | small |
| Tests | new | A changed file sets the record aside; a new superseding file appears after a re-list; idempotent record; a user without access gets nothing; a deleted file is purged; keyword search finds a clause the page finder misses; search results never feed a number | medium |
| Docs | [demo guide](../../MCP-Server/docs/demo_guide.md), README, a new decision | New section: second check uses records; changed-file test; search question | small |

**Not affected:** the comparison rules, the SAP adapter, the quote check, per-user sign-in, the audit log, and the read-only rule for SAP and for the sources. The only new writes are to **our own** database (records, passages, catalog), the same place the audit log and history already write; nothing writes to SAP or to a document source.

---

## 6. Risks, ranked

1. **A stale record is used as truth.** The fingerprint check catches an edited file, **not** a new file that supersedes it (section 4.4). Mitigation: re-list on a timer, show the last listing time in every answer, and report a source that cannot be listed as not checked.
2. **Leaking through the index.** User B reads a passage of a file only user A may open. Mitigation: check access as the asking user on every retrieval (section 4.6, option A). For the network share, per-user access is not enforced anywhere today (decision 0007), and the index does not make that worse.
3. **A wrong record becomes sticky.** The quote check proves the rate appears on the page, **not that it is the right clause** (the check's own message says so). A wrong record then repeats reproducibly. Mitigation: records start as `verified` (code-checked), not `accepted`; the answer shows the status; a person can reject one. Who accepts is a decision (section 8).
4. **A second copy of sensitive contract text.** It needs the same protection and retention as the source, and a database role that is not the `postgres` superuser (decision 0008 notes the POC uses `postgres`). Unknown: what Ingenus's DBAs require.
5. **Search is mistaken for fact.** A passage returned by search might be quoted as a number. Mitigation: the tool says "not for checks", the guidance forbids it, and a test fails if a search result feeds a comparison.
6. **Order of amendments across sources.** The rule "later effective date replaces earlier" works on dates, not on links between files. If an amendment has no clear date or its master is in another source, the result can be wrong. The existing "two documents conflict, ask" rule is the backstop.
7. **Search runs only on Postgres.** Records and the catalog also run on SQLite, so a bug could show on one engine only. Mitigation: test both for records, and run the search tests against the local Postgres already used for decision 0008.
8. **The local embedding model is a new component to host and version.** Its quality on pharma contract wording is untested, it needs CPU and memory on the VM (**verify** the VM's size, Aditya provisions it), and changing it means re-embedding everything. Mitigation: test candidates on the synthetic set before fixing one; store the model name and version with every vector.
9. **Effort against "keep it cheap".** This adds tables, tools and a timer for a pilot. It is also the part of the agreed design that makes results repeatable and reviewable, which is what Abhishek asked for. Steps are ordered so each one stands alone (section 7).

---

## 7. Plan and estimates (not prototyped)

| Step | What | Done when | Estimate |
|---|---|---|---|
| 0 | Decisions (section 8) | Sridhar and Aditya agree | 0.5 day |
| 1 | Source routing and the **catalog** (the [routing proposal](multi_source_routing_impact_analysis_and_proposal.md)) | A question finds its files in any source; each file names its source; a failed source is reported | 5 to 7 days (already estimated there) |
| 2 | **Records**: store verified terms; `get_contract_terms`; freshness check; status | Second check of Chain X reuses stored terms; an edited file sets them aside | 3 to 4 days |
| 3a | **Keyword search**: passages; `search_contracts`; access check | A clause found that the page finder missed; no access means no passage | 3 to 4 days |
| 3b | **Meaning search**: pick and test a local embedding model; pgvector; combined ranking | "Retrospective discount" is found for a rebate question on the synthetic set; passages are re-embedded when the model version changes | 2 to 3 days |
| 4 | Accept or reject a record | **Left out for now** (decided 23 Oct 2026): records stay `verified` only | 1 to 2 days if added later |

Steps 2 and 3a can stop and still be useful. Step 2 alone gives repeatable checks.

---

## 8. Decisions and questions

**Decided (Sridhar, 23 Oct 2026):**

| # | Question | Decision |
|---|---|---|
| 1 | Who may index? | **Per-user, lazy** (option A, section 4.6). A background crawler only later and only with Ingenus IT's agreement |
| 2 | Is the `accepted` status in scope now? | **No.** Records stay `verified`; no `record_decision` tool yet |
| 3 | Keyword first, vector later? | **Keyword and meaning now** (against my recommendation; cost in section 4.7) |
| 4 | Which embedding model? | **A local open-source model** on the server; the choice is tested before it is fixed |
| 5 | Search without Postgres? | **Postgres only for search**; the catalog and records also work on SQLite |
| 6 | `compare` when a source may be down? | **Guidance and a flag** (`complete`, per-source status). The server stays stateless. Residual risk is on Claude and the reader (section 6, risk 1) |

**Also decided (Sridhar, 23 Oct 2026):**

| # | Question | Decision |
|---|---|---|
| 7 | POC storage on the VM | **Postgres**, as decision 0008 does for the audit store. Search needs it |
| 8 | Retention of stored contract text | **90 days from last use** (confirmed 23 Oct 2026): the clock restarts whenever a file is read or re-checked; an unused file's records and passages are purged. The audit log keeps its own, longer assumption (12 months, **to confirm**) |
| 9 | Who may read the database | **Through the server's tools only; direct access for admins only** (confirmed 23 Oct 2026). Signed-in users reach stored text only through the tools, which check each user's access to the file on every retrieval. Sridhar and Aditya query the database directly, with a separate role for the server (not `postgres`) and the audit tables in their own schema |

Why decision 9 is set this way: stored passages and records are copies of text that SharePoint and OneDrive show only to people who may open the file, and the same database holds the audit log with other people's names. Direct access for all signed-in users would bypass both. Direct access for all users is acceptable only on synthetic data, and is not the setup to show Ingenus.

**Still to decide (Sridhar, Aditya):** which local embedding models to test. Candidates and what to check are in section 10.

**To ask Ingenus (Abhishek, Dan, Harish):**
1. How many contract files, and how is an amendment linked to its master in your folders? (Names, folders or a register.)
2. Is a stored copy of contract text, inside your network, acceptable, and for how long?
3. Which embedding model, if any, is acceptable for meaning search?
4. Who reviews and accepts an extracted term: Abhishek, Finance, or both?
5. Where do new amendments land, and how soon after signing?

---

## 9. What would change my recommendation

- **Few contracts (tens to a few hundred) and no appetite for stored copies.** Then keep only the records (value, quote, page, fingerprint) and do search by reading the file live. Skip the passage table.
- **Ingenus refuses any stored copy of contract text, even inside its network.** Then store pointers, fingerprints and quotes only, as the Sensitive data note's G7 suggests, and drop the search index.
- **A background identity is approved.** Then option B is better: it fills the catalog and index in bulk and fixes "files nobody has read yet are not searchable".

---

## 10. Local embedding models to test (free, no Claude, no per-use cost)

Claude is not involved: embeddings come from a model that runs on the server's own CPU, from files downloaded once. The only cost is the VM they run on. Contract text stays on the server.

| Model | Licence | Why test it | Watch for |
|---|---|---|---|
| **bge-small-en-v1.5** (BAAI) | MIT (a directory lists MIT; confirm on the model card) | Small and fast, 384-dimension vectors, English. A good first baseline | English only (fine: the contracts are US English) |
| **e5-base-v2** (intfloat) | MIT (listed by a directory; confirm on the model card) | Larger than the small ones, usually better recall; same family also has a small version | From memory (**verify**): it expects the text to start with "query: " or "passage: ". Forgetting that lowers quality |
| **nomic-embed-text-v1.5** (Nomic) | Apache 2.0 (several Hugging Face pages) | Longer input, so a whole clause with its heading fits in one passage | From memory (**verify**): it may need `trust_remote_code`, which runs code from the model's repository. Prefer a model that does not, or review that code first; also needs task prefixes |
| all-MiniLM-L6-v2 (sentence-transformers), as a plain floor | Apache 2.0 (from memory; **verify**) | Very small and widely used: shows whether the bigger models are worth the weight | Older and weaker than the others |

I have not run any of these. The comparison to make is on **our** data: the synthetic contracts and the wording from the golden questions (including "retrospective discount" for a rebate). Score each model by whether the right passage is in the top 3, then pick one and record its name and version.

**Things to check before fixing one (all **verify**):**
- **Licence on the model card**, not in a directory.
- **Hardware:** these run on CPU; the corpus is small (hundreds of passages in the POC). Check the VM's memory and CPU, which Aditya provisions.
- **Libraries:** the usual route (sentence-transformers) pulls in PyTorch, which is large. A lighter ONNX route may exist; check what suits the VM.
- **Offline use:** download once, check the file hashes, then copy the model onto the VM and run it with no internet. Ingenus's network will not allow downloads at run time.
- **Versioning:** store the model name and version with every vector; a changed model means re-embedding every passage.
