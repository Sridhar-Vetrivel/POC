# Finding the document source from the question: impact analysis and proposal

**Status:** proposal, 23 Oct 2026. Nothing in it is built. Nothing is confirmed by Ingenus.
**For:** Sridhar and Aditya (Psiog).
**Ask (Sridhar, 23 Oct 2026):** a user must not have to change `INGENUS_DOC_SOURCE`. The server should work out where a customer's contracts are from the question the user asks.

> **Update, same day.** The records and search index we had already agreed are the end state, and the catalog inside them is how a question finds its source. This note is therefore **step 1** of the [records and search index proposal](records_and_search_index_impact_analysis_and_proposal.md). Option E below ("catalog / index", which I called not needed for a pilot) was wrong to dismiss: it is the agreed design. Option C (search all sources) stays as the way the catalog is first filled and re-listed.

Labels used below: **Said**, **Doc** (read in this repo), **Psiog proposal** (ours, to confirm), **Assumed**, **Unknown / verify**.

---

## 1. Verdict

**Do not make the server pick one source from the wording of the question. Make it look in every source it is set up with, every time, and say which source each file came from.** Call this option C in section 4.

Reasons, short:

- A question such as "Check Chain A against SAP as of 31 Aug 2026" says nothing about SharePoint, OneDrive or a drive. The only thing in the question that points to a place is the **customer**, and the code already resolves the customer. So there is nothing to "read" for the source. The server has to look, or to hold a map from customer to place.
- Looking everywhere is the only option that works without anyone maintaining a map, and it matches how contracts really sit: a master agreement may be on the network drive and its amendments in SharePoint (**Assumed**, see section 2).
- The cost is real and is the main risk: **if one source is down, the answer can be wrong and still sound confident.** The design below makes that visible (section 6, risk 1). It does not remove it.

**Effort (estimate, not prototyped): about 5 to 7 working days for one person.** The comparison, quote check and SAP code do not change.

---

## 2. What was said, assumed and is unknown

| | |
|---|---|
| **Said (Sridhar, 23 Oct 2026)** | The user will not change the source setting per question. The server must identify the source. |
| **Doc** | Ingenus's contracts sit in SharePoint, OneDrive and a network drive ([decision 0007](../decisions/0007-v1-onedrive-and-network-share-sources.md), context). The v1 proposal quotes Dan on 8 Oct (37:42): the shared drive and SAP are behind a firewall and *"we can never expose that outside of our own firewall"*, and Call 1 (58:32): *"keep SharePoint and the network drives in mind as well"* ([v1 proposal](../v1_impact_analysis_and_proposal.md), section 1). I have not re-read the transcripts for this note. |
| **Doc** | The server reads **one** source per run today, chosen at start by `INGENUS_DOC_SOURCE` ([config.py](../../MCP-Server/src/ingenus_mcp/core/config.py), [sources.py](../../MCP-Server/src/ingenus_mcp/core/sources.py) `get_source`). This was a build shortcut, not a client request. |
| **Assumed** | A customer's documents can be spread over more than one source. Users do not say where a document is. The same customer name appears in the folder or file names in every source. |
| **Unknown / verify** | Where each kind of contract (master, amendment, draft) lives at Ingenus. Whether one customer ever spans two sources. Whether there is a single source of truth. How many files per source. Whether OneDrive holds official contracts or only people's working copies. Claude Desktop's timeout for one tool call. |

Small correction to my earlier note: when `.env` holds several uncommented `INGENUS_DOC_SOURCE` lines, the **first** wins, because `load_env_file` only sets a name that is not already set. I said earlier I had not checked.

---

## 3. How it works today, and why that breaks the ask

Every tool call builds its source from the one global setting:

| Where | What it does |
|---|---|
| `contracts.find_contract_files` | `get_source(settings)`, lists that one source, matches the customer's names against the **folder and file names** |
| `contracts.get_contract_pages` | `get_source(settings)`, reads one file by `document_id` |
| `citations.verify_term` (inside `compare_contract_to_sap`) | `get_source(settings)`, re-reads the cited page to check the quote |
| `history.record_check`, `history.read_history` | `get_source(settings)`, reads file versions |

`document_id` is a path under the source root, with no source in it (`Chain_A/Chain_A_Master_Supply_Agreement_2025.pdf`). So even if a question could name a source, the later calls would not know which source a `document_id` belongs to. **The `document_id` has to carry the source.**

Also true today and useful: the parsed-text cache is already keyed by who reads what (`source.identity`, [documents.py](../../MCP-Server/src/ingenus_mcp/core/documents.py)), so text from one source or user is never handed to another. That stays.

---

## 4. Options considered

| | Option | How the server knows the source | Good | Bad |
|---|---|---|---|---|
| A | **Customer-to-source map** | A `sources:` list per customer in `customers.v1.yaml` | Fast, predictable, no fan-out | Someone must keep the map right. A wrong or missing entry **hides a source silently**. Fails when one customer spans sources |
| B | **Claude decides** | Tools take a `source` argument; the model guesses from the question | No server search | The question rarely names a source, so the model guesses. A guess is the thing we are trying to avoid |
| C | **Search all sources every time (recommended)** | The server asks every enabled source in parallel and tags each file with its source | No map to maintain. Handles a customer split across sources. Same answer whoever asks | Slower (slowest source wins). A failed source needs honest reporting. Duplicates and conflicts across sources must be handled |
| D | **One tool per source** (`find_contract_files_sharepoint`, ...) | Claude picks a tool | Simple code | Same guessing as B, and more tools for the model to choose between |
| E | **Catalog / index** | A background job lists every source into a table (customer, file, source, hash); tools query the table | Fast, scales to many files | A new component: freshness, a store, a job. Not needed for a pilot of this size (**Assumed**) |

**Recommendation: C now. Keep an optional `source` argument (the useful part of B) for when a user does say "the copy on the shared drive". Revisit A or E only if the numbers in section 9 say so.**

---

## 5. The proposal (Psiog proposal, to confirm)

```
User: "Check Chain A against SAP as of 31 Aug 2026"
  |
  v  Claude Desktop calls find_contract_files(customer="Chain A")
  |
  v  MCP server  ---- asks all enabled sources at once ---+
       |                    |                             |
       v                    v                             v
   SharePoint            OneDrive                   Network drive
   (as the user)         (the user's own)           (as the service account)
       |                    |                             |
       +--------- merge, tag each file with its source, ---+
                  drop exact duplicates, flag conflicts
  |
  v  result: files[] each with  source + document_id,
            sources[] one line per source: ok / failed / seconds,
            complete: true | false
```

### 5.1 The five changes

1. **Several sources can be switched on at once.** New setting `INGENUS_SOURCES=sharepoint,onedrive,network`, using the per-source settings that exist today (`INGENUS_SP_*`, `INGENUS_OD_FOLDER`, `INGENUS_NETWORK_ROOT`). If it is not set, `INGENUS_DOC_SOURCE` works exactly as now, so nothing existing breaks. Later, a real Ingenus setup with two shares needs a small sources file (YAML) instead of one folder setting per kind. That is a separate decision.
2. **The `document_id` carries the source:** `sharepoint:Chain_A/Chain_A_Master_Supply_Agreement_2025.pdf`. The part after the colon is checked exactly as now (no `..`, no absolute paths). An unknown source name is refused. A `document_id` with no source is accepted only when one source is enabled (so old records and tests still read).
3. **`find_contract_files` searches every enabled source in parallel**, each with its own time limit (the network source already has one; Graph calls have a per-request timeout). Each file gets a `source`. Identical files (same hash) in two sources are listed once with the other place named. A same-named file with **different content** in two sources is listed twice and flagged as a conflict, which the existing "two documents conflict, ask" rule then handles. The result carries one line per source (`ok`, `failed` with the plain-words reason, seconds) and a `complete` flag that is false if any source failed.
4. **The other tools route by the prefix.** `get_contract_pages`, the quote check and the check history split the prefix and use that source. The comparison itself does not change: it takes terms with citations and does not care where the page came from.
5. **The guidance says what to do about it** (a new `guidance/v3`; v2 stays untouched because the demo results refer to it): show each file's source in the report; if `complete` is false, say which source failed and **do not present the check as complete**; never read "no file found" as "no contract exists" when a source failed.

Optional, if wanted: a `source` argument on `find_contract_files` (from the enabled names) for "the one on the shared drive". And, later, a `sources:` hint per customer in the ontology to narrow the search for speed. Neither is needed to make the ask work.

### 5.2 Three example questions

| Question | What happens | What the user sees |
|---|---|---|
| "Check Chain A against SAP as of 31 Aug 2026." | All three sources searched. Only SharePoint holds Chain A. One check | The same numbers as today (1,800.00 / 12,600.00), with the source named for each file |
| "Check Chain E against SAP as of 31 Aug 2026." while the **network share is down** | SharePoint and OneDrive answer with no match; network fails | **Not** "no contracts found". It says the network drive could not be read, that the answer is incomplete, and asks to retry |
| "Check Chain X..." where the master is on the network drive and Amendment 2 is in SharePoint | Both searched; the files are merged | One check over both documents, each citation naming its source |

---

## 6. Risks, ranked

1. **A source is down and the newest amendment lives there. The check looks clean and is wrong.** Worst case, because the figure feeds an accrual. Mitigation: per-source status and `complete` in the result, and the guidance rule above. **Residual:** the server is stateless, so `compare_contract_to_sap` cannot know that an earlier `find_contract_files` call was incomplete. The protection there is the guidance and the user reading the report. State this to Aditya (**verify with Aditya** whether that is acceptable for the pilot, or whether `compare` should re-check source health itself).
2. **The same contract exists twice with different content** (a SharePoint working copy and a signed copy on the drive). The merge flags it; deciding which is right is a person's job. Without the flag, the newer file date could win by accident.
3. **Customer matching is by name in the folder or file path.** It assumes every source names things the same way. A file saved as `CHX Amend 2.pdf` in one place may be missed **silently**. Unknown at Ingenus: ask for their naming (section 8).
4. **Speed.** The call takes as long as the slowest source. Measured on 20 Oct: the first SharePoint listing took 14.5 s for 30 files ([demo guide](../../MCP-Server/docs/demo_guide.md), finding 4). The network source can take up to its 20 s timeout. Claude Desktop's own tool timeout is **unknown (verify)**. Mitigation: parallel search, the existing cache, a small catalog later (option E).
5. **OneDrive is one person's drive.** In a search over all sources, two users can get different answers to the same question because each reads their own OneDrive. That is correct for permissions but surprising for finance. Whether official contracts are kept in personal OneDrives at Ingenus is **unknown**.
6. **The network share is read as one service account** (decision 0007), so every user sees what that account sees, while SharePoint and OneDrive are per user. Mixing them in one answer is fine for the POC and a question for Ingenus's security people.
7. **Routing by prefix is a new input an outsider could shape** (a `document_id` comes back from the model). Mitigation: the source name must be on the enabled list, the path part keeps today's checks, and the read-only test suite ([test_v1_readonly.py](../../MCP-Server/tests/test_v1_readonly.py)) is extended to the new code.
8. **More moving parts for a pilot that should stay cheap.** The change is small compared with the rest of the work, and it is the same code the real Ingenus setup needs anyway (SAP and the shared drive are the sources behind their firewall).

GxP posture is unchanged: every source stays read-only, nothing writes to SAP or a source, and each call is still logged with who made it.

---

## 7. Impact analysis: what changes

| Area | File | Change | Size (estimate) |
|---|---|---|---|
| Settings | [config.py](../../MCP-Server/src/ingenus_mcp/core/config.py) | Read `INGENUS_SOURCES`; keep `INGENUS_DOC_SOURCE` as the one-source fallback | small |
| Sources | [sources.py](../../MCP-Server/src/ingenus_mcp/core/sources.py) | A registry of enabled sources by name; `resolve(document_id)` splits the prefix; keep `get_source` for the one-source case | medium |
| Find / read | [contracts.py](../../MCP-Server/src/ingenus_mcp/core/contracts.py) | Fan out in parallel with a time limit per source, merge, flag duplicates and conflicts; `get_contract_pages` routes by prefix | medium |
| Quote check | [citations.py](../../MCP-Server/src/ingenus_mcp/core/citations.py) | Use the routed source | small |
| Compare tool | [compare_contract_to_sap.py](../../MCP-Server/src/ingenus_mcp/tools/compare_contract_to_sap.py) | Pass the registry instead of one source; the comparison code is untouched | small |
| History | [history.py](../../MCP-Server/src/ingenus_mcp/core/history.py) | Version lookup and "can this person open it" use the routed source. Old records have no prefix: read them as belonging to the single source, or hide them (decision) | small |
| Start-up checks | [app.py](../../MCP-Server/src/ingenus_mcp/server/app.py) | Validate each enabled source (SharePoint and OneDrive need sign-in, network needs its path) | small |
| Result shape | [models.py](../../MCP-Server/src/ingenus_mcp/core/models.py), [find_contract_files.py](../../MCP-Server/src/ingenus_mcp/tools/find_contract_files.py) | `source` on each file; per-source status and `complete` on the result; optional `source` argument | small |
| Guidance | `MCP-Server/guidance/v3/` (new) | Playbook, extraction schema and report format learn "source" and "incomplete" (copy of v2, edited) | small |
| Tests | seven test files use the single setting (`test_v1_auth`, `datasets`, `graph_source`, `history`, `network_source`, `onedrive`, `v1_support`) | They keep working through the fallback. New tests: three sources at once, one source failing, duplicate and conflicting files, routing by prefix, a bad prefix, history across sources | medium |
| Docs | `.env.example`, [README](../../MCP-Server/README.md), [demo guide](../../MCP-Server/docs/demo_guide.md) section 8b, a new decision 0010 (replaces the "one source per server" part of decision 0007), [open items](../v1_open_items_checklist.md) | Update | small |

**Not affected:** the comparison, rules, SAP adapter, tools' read-only guarantee, per-user sign-in, the audit log, and the slice files.

**QA impact (demo guide section 8b):** the plan I gave you to switch `INGENUS_DOC_SOURCE` per source is replaced. You would set up all three once and ask all the questions in any order with no restart. The "wrong chain gives no files" tests become "the right chain is found in its source, and each file names that source". The "source down" test (rename the folder) becomes the most important new test.

---

## 8. Questions for Ingenus (Abhishek, Dan)

1. For one customer, where do the master agreement, each amendment and any draft live? Always the same place, or split?
2. Is there one source of truth for signed contracts? If a copy is in two places, which wins?
3. How are files named and foldered in each place? Does the customer's name appear in the path?
4. Roughly how many contract files per place?
5. Who can read each place, and is the shared drive read by a service account or by people?
6. Do people keep contract copies in personal OneDrive, and does the team treat those as official?

---

## 9. What would change my recommendation

- **Ingenus says each customer's contracts are in exactly one known place and there is a master list of customers and places.** Then option A is cheaper and faster, with no fan-out and no "source down" worry for the other sources.
- **There are thousands of files, or a listing takes more than a few seconds.** Then option E (a catalog) earns its place.
- **Security says the network share and personal OneDrive must never be answered in one result.** Then split by role or by tool, and the one-answer design is wrong.

---

## 10. Next steps and decisions

1. **Decide:** option C, with the optional `source` argument? (Sridhar, Aditya)
2. **Decide:** what `compare` should do when it cannot tell whether every source answered (risk 1). My view: guidance plus the flag for the pilot, and a health re-check inside `compare` before any real Ingenus data.
3. **Decide:** old check-history records without a source prefix: keep (treat as the single source) or hide.
4. Build behind the fallback, with the tests in section 7. Then set up all three sources at once and re-run section 8b of the demo guide without any restart.
5. Take section 8 to Ingenus. Their answers decide whether option A or E is needed later.

Estimate for steps 1 to 4: **5 to 7 working days** for one person, from reading the code only. Nothing has been prototyped.
