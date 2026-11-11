# Plan: add the BT team's taxonomy, and move from the mock SAP to a real SAP adapter

**Status (10 Nov 2026): a plan, not a decision.** Written for Sridhar and Aditya to review. Nothing here is built. Tags: **SAID** = someone stated it; **ASSUMED** = my reading, not confirmed; **UNKNOWN** = nobody has told us yet. Effort figures are **estimates, not prototyped**.
**Starting point:** the v1.1 laptop release ([release_v1.1.md](../release_v1.1.md)): synthetic data, mock SAP, one laptop, not hosted.

## 1. The two goals, in one paragraph each

**Goal 1: taxonomy.** Bring the BT team's taxonomy (SAID: it is on their private Miro board; Sridhar will supply the contents) into the server, so contract terms and the questions about them use Ingenus's own vocabulary instead of our two hard-coded term kinds. **What the taxonomy covers is UNKNOWN until we see it** (ASSUMED: controlled lists such as rebate and fee types, contract document types, product and customer groupings, and possibly how they map to SAP). Section 3 lists what to find out first.

**Goal 2: real SAP.** Replace `MockSapReader` with a working `RealSapReader` behind the same read-only interface, so `get_rebate_setup`, `get_sales_volume` and `compare_contract_to_sap` answer from Ingenus's SAP. **The route, SAP version, login and who may read are all UNKNOWN** (the stub says so: [real_stub.py](../../mcp_servers/sap/adapters/real_stub.py)). SAP is SAID to be on RISE (AWS), managed by SAP, reached over an IPsec tunnel (8 Oct call).

**How they connect (ASSUMED, to confirm):** the taxonomy is probably the bridge between what a contract says ("volume rebate, Product A") and what SAP holds (a rebate setup line). If so, the SAP mapping depends on the taxonomy, so the two goals should share one discovery with Dan and the BT team.

## 2. What exists today, so the plan changes only what it must

| Thing | Where | Why it matters here |
|---|---|---|
| One read-only SAP interface, `read(ReadQuery) -> ReadResult`; a test fails if a write-style method appears | [interface.py](../../mcp_servers/sap/interface.py) | The real adapter implements this and nothing else. Nothing above it should change |
| Three entities the code reads: `customers`, `rebate_setup`, `sales_volume` (business names, not SAP objects) | [sap.py](../../MCP-Server/src/ingenus_mcp/core/sap.py), [mock_sap.md](../../MCP-PlugIn/docs/mock_sap.md) | The real adapter must return rows with the same fields |
| Adapter chosen by `INGENUS_SAP_ADAPTER` (`mock` today, `real` raises `NotImplementedError`) | [config.py:196](../../MCP-Server/src/ingenus_mcp/core/config.py#L196) | The switch already exists |
| Two term kinds only: `rebate` and `admin_fee` | `TermKind` in [models.py:16](../../MCP-Server/src/ingenus_mcp/core/models.py#L16) | Where a richer taxonomy would first show up |
| Page-finder topics and keywords | [topics.v1.yaml](../../slices/contract_to_sap_check/topics.v1.yaml) | Already has `payment_terms`, `returns`, `chargebacks` that nothing compares yet |
| Compare rules: tolerance, rounding, default basis per kind | [compare.v1.yaml](../../slices/contract_to_sap_check/rules/compare.v1.yaml) | Each new term kind needs a basis and a rule |
| Customer names and aliases | [customers.v1.yaml](../../slices/contract_to_sap_check/ontology/customers.v1.yaml) (SYNTHETIC) | A real customer list would replace or feed this |
| Guidance for Claude, versioned (not edited in place) | `MCP-Server/guidance/v8/` (`extraction-schema`, `rebate-and-fee-terms`) | A taxonomy change means a new guidance version |
| Sources report "ok / failed / why" and `compare` re-asks them before giving figures | [sources.py](../../MCP-Server/src/ingenus_mcp/core/sources.py), commit `c344434` | SAP needs the same honesty: "SAP unreachable" must never read as "no setup" |

## 3. Goal 1: the taxonomy

### 3.1 What to find out before any design (the intake)

Ask the BT team, or read it off the board, and write the answers down here:

1. **What is it a taxonomy of?** Rebate and fee types? Contract document types? Products? Customers and customer groups? Payment terms? Something else? (UNKNOWN)
2. **Is it a flat list, a hierarchy, or a set of mappings** (for example term type to SAP condition type)? (UNKNOWN)
3. **Is it final, in progress, or one team's draft?** Who owns changes, and how will we hear about them? (UNKNOWN)
4. **Does it name SAP objects?** If it does, those names are new facts we may use only once Dan or the BT team confirm them (CLAUDE.md rule 6).
5. **In what form will it reach us:** Miro export (CSV or image), screenshots, a document? Images are readable by me, but a structured export is far safer for a vocabulary that code will depend on. (UNKNOWN)
6. **May the board's content be pasted into Claude or stored in this repo?** The board is private. Check this against the Psiog AI policy and with the BT team before pasting; I have not classified it. Until answered, treat it as confidential and do not commit it. (UNKNOWN)

### 3.2 Where it would land (design sketch, ASSUMED until the content is seen)

- **One versioned file** under `slices/contract_to_sap_check/ontology/`, for example `taxonomy.v1.yaml`, next to `customers.v1.yaml`. Plain data, no code, with a label saying where it came from and its date. It is the single source; nothing else repeats its terms.
- **Term kinds become data-driven.** `TermKind` is a fixed `Literal["rebate", "admin_fee"]` today. A taxonomy-driven list means the extraction schema, the quote check and the compare rules read the allowed kinds from the file. This is the one code change with a real blast radius; it needs the existing 351 tests plus new ones.
- **Each new kind needs four things:** keywords for the page finder, a basis rule in `compare.v1.yaml`, a SAP mapping (Goal 2), and a line in the guidance. A kind with no SAP mapping must come back as "not checked: no SAP mapping", never as a match.
- **Guidance `v9`** teaches Claude the vocabulary. `v8` stays as it is. The existing "5 fresh chats" test should be run for `v9` before it becomes the default.
- **Unknown or new wording in a contract** must go to `not_checked` with the quote, never be forced into the nearest category.
- **Taxonomy changes are versioned** (`v1`, `v2`), and each stored term and check record keeps the version it was made under, so an old check can be read under its own vocabulary.

### 3.3 Phases

| Phase | Work | Done when |
|---|---|---|
| T0 Intake | Answer the six questions in 3.1; agree the file format with the BT team | The answers are written into this document; Sridhar and Aditya have confirmed what the taxonomy covers |
| T1 Model | Turn the content into `taxonomy.v1.yaml`; a loader with validation (duplicates, unknown parents, missing labels); a short note listing what was left out or unclear | Loader tests pass; every entry traces back to a board item |
| T2 Wire in | Make term kinds and topics read the taxonomy; add basis rules; extend the golden test data with at least one chain per new kind (synthetic) | The existing Chain A to F numbers are **unchanged** (regression), and each new kind has a golden case |
| T3 Guidance | `v9` guides; run the fresh-chat test for the guide fetch and the wording | Pass rate recorded; `v9` becomes default only if no worse than `v8` |
| T4 Review | Show the BT team the mapped result, including what was not mapped | BT team confirms or lists corrections |

**Estimate (not prototyped): 5 to 8 working days after T0 completes**, more if the taxonomy is large or ambiguous, or needs a hierarchy.

## 4. Goal 2: the real SAP adapter

### 4.1 What to find out first (discovery with Dan, plus Ingenus IT)

All UNKNOWN today. Until they are answered, nothing in section 4.3 can start:

1. **The route.** Report export, a released API, CDS views, RFC or BAPI, or something else. The README lists the options; none is chosen.
2. **SAP version and RISE edition** (ECC or S/4). This decides the route.
3. **Where rebate and fee setup, and monthly net sales, live** and how they are keyed (per customer, per product, per validity period). The three entities the code reads must be buildable from them.
4. **The login.** A read-only service account, or each person's own SAP identity? A single account sees everything it is allowed to, for everyone who asks (the same trade-off as the network drive, decision [0007](../decisions/0007-v1-onedrive-and-network-share-sources.md)). Per-person identity respects SAP authorisations but is heavier to build. **A decision for Ingenus.**
5. **Network path.** Our server is planned for an AWS VM (decision [0009](../decisions/0009-v1-poc-vm-on-aws-provisioned-by-principal-architect.md)), SAP is behind an IPsec tunnel. Who opens the route from that VM, and from which address? (ASSUMED that the VM needs allow-listing.)
6. **Data freshness and volume.** How current must the answer be, and how big is a customer's sales history? This drives timeouts and caching.
7. **A non-production system.** Is there a test client or sandbox with test data we can read first? This is the key to starting without real data.
8. **Who approves access** and how long it takes. Lead time is likely to be the longest item in the whole plan.

### 4.2 Rules that do not change

- **Read-only by construction.** The adapter implements `read()` only. The test that forbids write-style methods stays, and we add a check that the SAP login itself has no write authorisation (a fact for Ingenus to confirm, not for us to assume).
- **Real SAP data is real Ingenus data.** It cannot be used until Ingenus's data and AI policy is signed off (CLAUDE.md rule 9, checklist section 4) and Legal's view on the model licence is in. Before that, only a non-production system holding synthetic or test data may be read.
- **No SAP object names in the repo until Dan or the BT team confirm them.** Business-level names stay in the interface; any real object names live only in the adapter, behind `read()`.
- **Stop and ask before** adding a dependency (for example an RFC or OData client library): CLAUDE.md rule 5.

### 4.3 Design (ASSUMED until 4.1 is answered)

- **Same interface, new adapter.** `RealSapReader` gets the settings it needs (host, client, credentials from a secret file or the service environment, never `.env` in git), and `get_reader` passes them. `core/sap.py`, the tools and `compare.py` do not change. This is exactly the swap the mock was designed for.
- **Honest failures.** Today an empty result means "no setup lines". With a real system, "SAP could not be reached", "login refused" and "timed out" are separate states and must say so, like the source statuses. `compare`'s re-check (commit `c344434`) is extended to ask SAP too, so figures are never given as complete when SAP did not answer.
- **Timeouts and limits.** A hard timeout per read (as for the sources), a cap on rows, and a plain message when exceeded. No retries that could hammer SAP; at most one retry for a transport error.
- **Audit.** The call log records the customer id, entity, period and outcome, never SAP values beyond what the tool result already shows; the dashboard shows SAP as a health row.
- **Shape conformance.** One shared test suite runs against **both** adapters: same entities, same fields, same ordering and date rules. The mock stays, and stays the default for tests and demos.
- **Mapping to the taxonomy.** Each taxonomy kind that SAP holds gets an explicit mapping (kind to the SAP-side line it corresponds to). A kind without a mapping is "not checked". This is where Goal 1 feeds Goal 2.

### 4.4 Phases

| Phase | Work | Done when |
|---|---|---|
| S0 Discovery | Answer 4.1 with Dan and IT; get the data-policy and Legal position in writing | The answers are in this document; the route and the login type are decided by Ingenus |
| S1 Shape-compatible mock | If the real shape differs from our three entities, reshape the mock and the interface to match, still synthetic | Existing numbers unchanged; the shared conformance suite exists and passes on the mock |
| S2 Access | The login, the network route from the VM, and a non-production system with test data | A read-only connection test from the VM succeeds and is logged |
| S3 Adapter | Build `RealSapReader` for `customers`, `rebate_setup`, `sales_volume`; honest failure states; the compare re-check extended to SAP | Conformance suite passes against the non-production system; failure cases (down, refused, slow, empty) each give their own message |
| S4 Parallel run | The same checks through mock and non-production SAP; any difference is explained | Chain A to F style results match, or every difference is documented and understood |
| S5 Gate to real data | Policy and Legal sign-offs recorded; SAP read-only authorisation confirmed by Ingenus; a named owner on their side | The gate is written down and signed; only then is a production read allowed |
| S6 First real read | One customer, read by Sridhar and Aditya, with an Ingenus SAP owner watching | Result reviewed by that owner; the log shows exactly what was read |

**Estimate (not prototyped):** the adapter itself is **about 5 to 10 working days once S0 and S2 are done**. The elapsed time is dominated by access and approvals, which we do not control, and cannot be estimated until we know the route.

## 5. Order of work and dependencies

1. **Now, in parallel and cheap:** T0 (the taxonomy intake) and S0 (the SAP questions) can be one conversation, because the mapping question is the same.
2. **Then:** T1 and T2 (taxonomy in, behind the existing numbers) while S0, S2 wait on other people. The mock-based work does not wait for SAP.
3. **S1 comes before S3:** if the real shape differs, we learn it on the mock, not in front of Ingenus.
4. **Nothing real before S5.** The hosting work (VM, HTTPS, second laptop) is a separate track; real SAP data also needs the server to be hosted, so S5 and the VM item in the checklist meet there.

## 6. Risks

| Risk | What it would do | What we do about it |
|---|---|---|
| The taxonomy is large, unfinished or full of overlaps | T1 and T2 take much longer; a wrong mapping gives a confident wrong answer | Map only what is clear; send the rest to "not checked" with the quote; review with the BT team (T4) |
| Real SAP shape differs from our three entities | The adapter needs a new interface or the code above it changes | S1 before S3; keep the interface business-level |
| One SAP login sees more than a person should | Anyone asking the server sees what the account can see | Decide in S0 (account or per person); document it as we did for the network drive |
| SAP is slow or down | A check hangs, or "down" reads as "no setup" | Timeouts, separate failure states, compare re-check extended to SAP |
| Real data reaches the model before sign-off | A policy breach | S5 gate; non-production only until then; no real values in logs or in the repo |
| Access takes weeks | The plan stalls | Start S0 now; keep mock-based work moving |
| Board content is confidential | A breach by pasting it | Answer question 6 in 3.1 before anything is pasted |

## 7. Decisions and inputs needed

| # | What | From | Needed for |
|---|---|---|---|
| D1 | May the Miro board's content be shared with Claude and stored in the repo? | Psiog AI policy, BT team | T0 |
| D2 | What does the taxonomy cover, and in what form will it arrive? | BT team, Sridhar | T0, T1 |
| D3 | SAP route, version, and where the data lives | Dan, Ingenus IT | S0, everything in section 4 |
| D4 | One SAP service account or per-person identity | Ingenus | S3 |
| D5 | A non-production SAP with test data | Ingenus IT | S2 onward |
| D6 | Data and AI policy sign-off, and Legal on the model licence | Ingenus, Legal | S5 |
| D7 | Approval to add a client library for the chosen SAP route | Sridhar (CLAUDE.md rule 5) | S3 |

## 8. What I need from you to start

- The taxonomy content, in the most structured form you can get (a CSV export from Miro is best), and the answer to D1 first.
- Whether Dan is the right person for the SAP questions in 4.1, and when the next conversation with him can be.
- Whether the BT team can say how the taxonomy relates to SAP (3.1, question 4).

Related: [v1_open_items_checklist.md](../v1_open_items_checklist.md) (hosting, clearances), [mock_sap.md](../../MCP-PlugIn/docs/mock_sap.md) section 8 (how a real adapter replaces the mock), [tool_design_rules.md](../learnings/tool_design_rules.md).
