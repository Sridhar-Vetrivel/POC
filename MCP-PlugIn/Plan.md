# Plan: Phase 1, the MCP plug-in for Contract-to-SAP

**Ingenus × Psiog** · Internal, pre-sales · Draft for Aditya's review · written after the 8 Oct 2026 call
**Read with:** [README.md](../README.md) (the bigger picture and the status tables) · [CLAUDE.md](../CLAUDE.md) (rules for people and AI agents) · [Call 2 notes](../../2026/Call_Notes/Ingenus_Call2_Notes_8Oct.md) · [P4 MCP plug-in proposal](../../2026/Solution_Approach/Proposals/P4_MCP_Plugin.md) (the .md files number this option P4; the deck and the call call it P1)

> **Pre-sales status.** Nothing here is confirmed with Ingenus, and there is no access to their systems or data. This plan is **our proposal**. Items marked **verify** are not yet checked against a source. **Said** facts carry a timestamp from the 8 Oct call, written `[8 Oct h:mm:ss]`. Phase 1 uses **synthetic and public data only** until Ingenus's data policy is received and signed off (DP-20, DP-29).

> **Build status (13 Oct 2026).** v0 is built on synthetic data and a mock SAP, using the proposed approach for every decision in section 3 (recorded in [`../docs/decisions/0001-phase1-v0-approach.md`](../docs/decisions/0001-phase1-v0-approach.md)). Steps S1 to S3 are done, S0 and S5 are partly done, and S4 is built but **not yet verified in Claude Desktop**. The live status table is in the [README](../README.md); what was and was not tested is in [`docs/S0_spike_results.md`](docs/S0_spike_results.md). New open decision: the Python runtime for the desktop extension ([`../docs/decisions/0002-python-runtime-for-the-desktop-extension.md`](../docs/decisions/0002-python-runtime-for-the-desktop-extension.md)).

---

## 1. What phase 1 is

**One MCP server with a few read-only, business-level tools, plus a small skills pack, that Ingenus's own Claude (Teams plan) calls.** Their Claude decides the order of calls; our code does the lookups, the comparison and the citation checks.

**Why this and why now (said):**

- Abhishek: *"I like the part one for now"* [8 Oct 46:57]. He wants it *"extremely simple and extremely easy for Dan to accept"* [8 Oct 1:10:34], *"quick and dirty so that we can actually test it out"* [8 Oct 1:10:39], and *"we are not going to use it to enter data right away, we are going to use the evaluation"* [8 Oct 1:10:15].
- Adoption and trust come first: *"they don't trust it because they have not seen the outputs"* [8 Oct 46:57].
- Aditya's estimate for the pilot: *"about a month"* [8 Oct 53:30]. That is a verbal estimate, not a commitment.

**Phase 1 is done when** Abhishek (or a named SME) can ask Claude to check a contract against SAP, get a result where every value shows its page and exact quote, and we can show from the log who used which tool and when. The first run on synthetic data reproduces the README's Chain X numbers exactly.

### In scope

- Contract-to-SAP check for **customer contracts and amendments** (the focus Abhishek named [8 Oct 56:17]).
- Read-only access: a mock SAP now, a real route later (section 7).
- A network-drive stand-in (a local folder of synthetic and public contracts).
- A skills pack and one MCP prompt to guide Claude.
- A tool-call log and a simple usage report.

### Out of scope (stated up front, so no one is surprised)

- **No watcher or scheduler.** Nothing runs unless someone asks.
- **No review queue, no recorded accept/reject decision, no pause and resume.** The person reads the chat answer.
- **No audit of the answer.** We log tool calls, not what Claude said.
- **No SAP writes, and no draft rebate upload file yet.** SAP has an upload function [8 Oct 7:10]; a human-reviewed draft file is a phase-2 idea.
- No COA vs filed-spec check, no GxP validation, no web portal, no orchestrator of ours.
- **Abhishek's stated end goal** (*"data capture and audit controls on condition rebate control changes"* [8 Oct 59:50]) is **not delivered** by phase 1. Say so in writing before we start.

## 2. How this relates to the existing README and CLAUDE.md

The README describes a larger POC: an orchestrator, a policy and audit gateway, pipelines, a review queue and a coupling test. Phase 1 builds only the bottom half of that picture: **the tools**. Nothing in the README is wrong; it is the later shape. What carries over and what differs:

| Item                                                                                                       | Carries over to phase 1                               | Differs in phase 1                                                                                                                                                                                          |
| ---------------------------------------------------------------------------------------------------------- | ----------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Synthetic and public data only; Chain X demo and numbers                                                   | Yes, unchanged ($8,500 a month; $17,000 for Jul–Aug) |                                                                                                                                                                                                             |
| SAP read-only; files written only to`outbox/` and `data/runtime/`                                      | Yes (rules 4 and 5)                                   |                                                                                                                                                                                                             |
| No LLM in compare or estimate; citations on every field, code-checked quotes; "not checked" beats guessing | Yes (rules 6, 7, 8)                                   |                                                                                                                                                                                                             |
| Versioned prompts, skills, schemas, rules                                                                  | Yes                                                   |                                                                                                                                                                                                             |
| Rules, schemas, ontology terms and golden tests live in`slices/contract_to_sap_check/`                   | Yes: keeps the work reusable for P2 later             |                                                                                                                                                                                                             |
| Foundation is domain-neutral (rule 1)                                                                      |                                                       | **Proposed exception for `MCP-PlugIn/` only** (section 4). The domain-word test skips `MCP-PlugIn/`                                                                                               |
| Only the orchestrator is an agent (rule 10)                                                                |                                                       | **Phase 1 has no agent of ours.** Claude on their plan drives                                                                                                                                         |
| Every tool and LLM call goes through our gateway; the API's remote MCP connector is not used               |                                                       | **Our gateway is not in the path** of Claude's calls. The plug-in itself enforces read-only, scope and logging. If we later call an LLM from a tool (Option Y), the gateway rule applies to that call |
| Claude API conventions (models, structured outputs, effort)                                                | Only if a tool calls the API (Option Y)               | Under Option X (default below) the server makes**no LLM calls**                                                                                                                                       |

**The README and CLAUDE.md have been updated to match this plan** (Phase 1 is now the current work; the larger design is Phase 2; each hard rule says which phase it applies to). The exceptions above are recorded there as proposals, pending Aditya's approval. If they conflict with this plan, this plan is the authority for `MCP-PlugIn/`.

## 3. Decisions the plan depends on

The plan is written with a **default** for each, so work can start. Each default is changeable.

| #  | Decision                               | Default in this plan                                                                                                    | Why                                                                                                                                                                                                                                                  | Who decides           |
| -- | -------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------- |
| D1 | How Claude reaches the server          | **Desktop extension per user** (local server, stdio)                                                              | Needs no firewall change; Dan said SAP and the shared drive can*"never"* be exposed [8 Oct 37:42]. Anthropic's docs say a remote connector is reached from Anthropic's cloud and won't connect to a private network (**verify** on their plan) | Aditya, then Dan      |
| D2 | Who extracts contract terms            | **Option X: Claude, on their own plan, extracts from the pages our tool returns.** Our code checks every quote    | No second LLM route and no new agreement [8 Oct 41:40]. Option Y (our own LLM inside a tool) needs its own provider approval                                                                                                                         | Aditya                |
| D3 | SAP access route                       | **Mock adapter now.** Real route decided with Dan (report export, API/CDS views or other; **unknown**)      | SAP version and route unknown; SAP is on RISE, reached over IPSEC [8 Oct 33:10, 43:04]                                                                                                                                                               | Dan                   |
| D4 | Data used                              | **Synthetic and public** until the policy is signed                                                               | DP-20, DP-29                                                                                                                                                                                                                                         | Dan, Abhishek, Harith |
| D5 | Scope beyond contract-to-SAP           | **Contract-to-SAP only.** Daily-use lookups (order status, packing slip [8 Oct 16:39]) are an option after step 4 | Keep it small [8 Oct 46:34]                                                                                                                                                                                                                          | Aditya                |
| D6 | Domain-neutral rule for`MCP-PlugIn/` | **Exception for phase 1**                                                                                         | Quick start; tool code is plain functions that can move later                                                                                                                                                                                        | Aditya                |
| D7 | Where tool-call logs go                | **A configured shared folder** (a set location Ingenus agrees to)                                                 | A desktop extension logs on each laptop, which would split the usage data. DP-14 says our own stores need agreement                                                                                                                                  | Dan, Abhishek         |

## 4. Design

### 4.1 Shape

```
Claude (their Teams plan, Claude Desktop)   ← drives the steps, extracts terms (Option X)
        │  calls tools, reads the results
        ▼
MCP server (stdio, desktop extension)       ← thin wrapper; no business logic
        │
        ▼
core/  (plain Python functions, Pydantic in and out)
   scope + read-only guard · tool-call log · quote checker · compare (no LLM)
        │                         │
        ▼                         ▼
SAP adapter (mock now)     Contract folder (local stand-in for the network drive)
```

- **Plain functions first, MCP layer last.** This keeps maintenance low and lets the same functions move into P2 later. It is also the earlier "rely more on API calls than MCP" guidance.
- **Use the official MCP Python SDK;** check its current API in its docs before writing (CLAUDE.md).
- **Packaging:** a desktop extension (`.mcpb`, **verify** the current manifest format in Anthropic's docs), plus an optional HTTP transport for a remote connector if D1 changes. Anthropic describes an allowlist an Owner controls, a minimum Claude Desktop version, and per-user install (**verify**).

### 4.2 Layout (matches the README's target layout)

```
POC/
├── MCP-PlugIn/                     # Phase 1 (this folder)
│   ├── Plan.md                     # this file
│   ├── src/ingenus_plugin/
│   │   ├── core/                   # tool functions, scope guard, log, quote checker, compare
│   │   └── server/                 # MCP wrapper, stdio entry point
│   ├── skills/                     # skills pack (markdown, versioned)
│   ├── prompts/                    # MCP prompt(s)
│   ├── packaging/                  # desktop extension manifest and build script
│   └── tests/
├── slices/contract_to_sap_check/   # rules, schemas, ontology terms, evals/golden (shared with later phases)
├── mcp_servers/sap/adapters/       # mock adapter (reused); real adapters are TODO(verify) stubs
├── data/synthetic/ · data/public/  # fixtures and sample contracts
└── data/runtime/                   # tool-call log (set location, D7); ignored by git
```

### 4.3 Tool catalogue (proposal; business-level, all read-only)

Composite first: one comparison tool carries the deterministic work, because Abhishek wants reproducible results and Aditya warned that many tools degrade tool selection [8 Oct 12:29]. Six tools in the baseline.

| Tool                                                | Purpose                                                                                                                                                                                                                                            | Notes                                                                                                                                                                                |
| --------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `find_contract_files(customer, kind?)`            | List a customer's contract and amendment files with date, hash and status                                                                                                                                                                          | Excludes drafts by rule: Abhishek's own example of a nuance a custom connector can encode [8 Oct 14:50]. Source files are never modified                                             |
| `get_contract_pages(document_id, topics)`         | Return only the pages on the asked topics (rebates, fees, effective dates) with page numbers and text                                                                                                                                              | Keyword and heading search first (no outside model). Pages are returned generously, with a "not checked" list.**Whether contracts are scanned is unknown**; OCR only if needed |
| `resolve_customer(name)`                          | Map "Chain X" to SAP customer candidates                                                                                                                                                                                                           | Alias table from the ontology terms. Ambiguous names return candidates, never a guess                                                                                                |
| `get_rebate_setup(customer, as_of)`               | Return the SAP rebate and fee setup                                                                                                                                                                                                                | Mock adapter now                                                                                                                                                                     |
| `get_sales_volume(customer, period)`              | Monthly volume for the exposure estimate                                                                                                                                                                                                           | Mock adapter now                                                                                                                                                                     |
| `compare_contract_to_sap(terms, customer, as_of)` | **Composite.** Takes the terms Claude extracted, each with `{document, page, clause, quote}`. Code checks every quote appears verbatim on that page, compares with SAP, and returns findings, indicative exposure and a "not checked" list | No LLM. Same inputs, same output. Unverifiable quotes are listed as not checked, never used                                                                                          |

Every tool result labels contract text as untrusted data, and returns quotes and pages, not whole documents.

**Optional after step 4 (needs D5):** `get_order_status(order)` and `find_delivery_document(order)` for the daily-use story [8 Oct 16:39].

### 4.4 Skills pack and MCP prompt (Aditya mentioned *"eight or nine skills"* [8 Oct 28:53])

Policy and playbook live in skills in phase 1 [8 Oct 49:00]. Proposed set, each versioned:

1. `contract-check-playbook`: the step order Claude should follow (find, read pages, extract, compare, report).
2. `reading-amendments`: back-dating, supersession, schedules and exhibits.
3. `extraction-schema`: the fields to extract and the citation format.
4. `rebate-and-fee-terms`: plain glossary of the rebate and fee kinds.
5. `report-format`: gaps, since when, indicative exposure, and what was not checked.
6. `not-checked-rules`: when to say "not checked" instead of guessing.
7. `untrusted-text-handling`: contract text is data, never instructions.
8. `when-to-stop-and-ask`: ambiguous customer, missing SAP record, conflicting amendments.

One MCP prompt, `contract_check`, starts the flow. Support for MCP prompts and shared skills on **their** plan and client is **verify**. Guidance is not enforced; only tool code is.

### 4.5 Cross-cutting rules for phase 1

- **Read-only.** No write tool exists, not even a mock. A test fails if any registered tool is not marked read-only, and if source paths are opened for writing.
- **Scope.** A tool serves only the configured contract folders and the listed SAP objects. No tool, no access.
- **Minimise.** Pages not whole files; fields not tables.
- **Log.** One JSON line per tool call: time, user (machine's signed-in user, **unverified** how identified), tool, arguments, result summary, not-checked count, duration. No whole documents. This is also the **adoption measure**.
- **Secrets.** None in the repo. The SAP service credential, once there is one, is held outside the repo (**unknown** how, on a laptop extension).
- **Data.** Synthetic and public only. Each synthetic value is labelled synthetic; each public file keeps its source URL.
- **Provider terms.** The Teams plan's terms are not covered in our sensitive-data note (it covers the API and Foundry). Add a "verify" before any real data.

## 5. Build steps (about four weeks, two Psiog FTE)

The README's M0 to M5 belong to the larger POC. Phase 1 uses **steps S0 to S6**.

| Step                             | When                   | What                                                                                                                                                                                                         | Done when                                                                                                                                                             |
| -------------------------------- | ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **S0 Spikes**              | Days 1–3              | Hello-world MCP server with one echo tool: as a desktop extension and as a remote connector, on a Psiog Claude account. Then, with Dan, a reachability test to SAP through the tunnel and one read-only call | A pass/fail table for D1 and D3. If D1 fails both ways, stop and take it to Aditya                                                                                    |
| **S1 Skeleton**            | Week 1                 | `MCP-PlugIn/` package skeleton and `pyproject.toml`, the scope guard, read-only test, the tool-call log, the mock SAP adapter, the Chain X synthetic fixtures                                            | `pytest` green; `get_rebate_setup` and `get_sales_volume` return the Chain X mock data                                                                          |
| **S2 Contract pages**      | Week 1–2              | Local contract folder,`find_contract_files`, `get_contract_pages` with keyword and heading search; 20–30 synthetic and public contracts with labelled rebate pages                                      | Miss rate on the labelled pages measured and reported; the "not checked" list works                                                                                   |
| **S3 Compare**             | Week 2                 | `resolve_customer`, the quote checker, `compare_contract_to_sap` using the rule and schema files in the slice package                                                                                    | Chain X:**3 variances + 1 match, $8,500 a month, $17,000 for 1 Jul–31 Aug**, identical across 5 runs. A fabricated quote is rejected and listed as not checked |
| **S4 Package and skills**  | Week 3                 | MCP wrapper, desktop-extension packaging, skills pack, MCP prompt, usage report from the log                                                                                                                 | The Chain X demo runs end to end in Claude Desktop with the extension installed                                                                                       |
| **S5 Evals and hardening** | Week 3–4              | 15–20 golden questions run in Claude; tool-selection accuracy noted; hostile contract text; out-of-scope requests; log inspection; read-only checks                                                         | Results in a short report; failures fixed or listed as known limits                                                                                                   |
| **S6 Pilot**               | Week 4,**gated** | 3–5 users, real data only if the gate below is met; usage and spot checks against known contracts                                                                                                           | A readout on adoption and trust, and a list of what to do in step 2                                                                                                   |

**Suggested split of the two FTE (not decided):** one on tools, the SAP adapter and compare (S1, S3); one on the contract side, packaging and evals (S2, S4, S5). Both on S0.

### Gate for real data (S6)

Real contracts or SAP data enter only when all of these hold:

1. Ingenus's data and AI policy is received and Dan has signed off.
2. The Teams-plan terms are checked against it.
3. A read-only SAP service login and a route exist.
4. The tool-call log location is agreed (D7).
5. Abhishek has confirmed in writing that phase 1 is evaluation only.

If any item is missing, the pilot runs on synthetic data and says so.

## 6. Success measures

| Measure                 | How we show it                                                                     |
| ----------------------- | ---------------------------------------------------------------------------------- |
| **Deterministic** | Same inputs give the same findings across 5 runs (S3)                              |
| **Traceable**     | Every value carries document, page, clause and a code-verified quote               |
| **Honest**        | Every result lists what was not checked                                            |
| **Read-only**     | Tests prove no write path exists                                                   |
| **Adopted**       | Weekly calls per user from the log; number of users who come back                  |
| **Trusted**       | Spot checks against known contracts; each answer's quotes inspected by a named SME |

Value for management (Aditya: *"we will also anchor it to value"* [8 Oct 1:09:03]) needs a baseline from Ingenus: today's hours per contract change and how often a change is missed (**unknown**).

## 7. Dependency checklist

| #  | Dependency                                                                                                       | Owner                  | Needed by | If missing                        |
| -- | ---------------------------------------------------------------------------------------------------------------- | ---------------------- | --------- | --------------------------------- |
| 1  | Decisions D1–D7                                                                                                 | Aditya (then Dan)      | S0        | Plan defaults apply               |
| 2  | A Psiog Claude account on a Team (or equivalent) plan for spikes                                                 | Psiog                  | S0        | Spike delayed                     |
| 3  | Ingenus's Claude plan, Owner, admin settings, Desktop version on the ~12 laptops [8 Oct 46:02]                   | Abhishek               | S4        | Extension route unproven          |
| 4  | SAP access: route, version (ECC or S/4: unknown), read-only service login                                        | Dan                    | S6        | Mock adapter only                 |
| 5  | Reachability to SAP through the IPSEC tunnel                                                                     | Dan                    | S0        | Cannot test the real route        |
| 6  | Contract samples (anonymised if needed): master agreements, amendments, a few scanned if any                     | Abhishek               | S2        | Synthetic and public only         |
| 7  | Whether contracts are scanned                                                                                    | Abhishek               | S2        | Assume text; plan OCR as a risk   |
| 8  | Labelled test cases with known answers, including rate-variance cases such as 5.5% against 5.56% [8 Oct 1:01:41] | Abhishek               | S5        | Our synthetic set only            |
| 9  | A named SME to judge answers                                                                                     | Abhishek               | S5        | Psiog self-check only             |
| 10 | Data and AI policy; Dan's sign-off                                                                               | Dan                    | S6        | No real data                      |
| 11 | Tool-call log location agreed                                                                                    | Dan                    | S6        | Logs stay local, usage data split |
| 12 | Pricing and budget call                                                                                          | Harith [8 Oct 1:09:10] | Before S6 | Scope fixed to this plan          |
| 13 | Whether Ruby can call an MCP server                                                                              | Dan                    | Phase 2   | No reuse by Ruby                  |

## 8. Risks

| Risk                                                                     | Impact                               | Mitigation                                                                                    |
| ------------------------------------------------------------------------ | ------------------------------------ | --------------------------------------------------------------------------------------------- |
| Their Claude plan cannot reach our server as planned                     | No pilot                             | S0 first; two routes; escalate on day 3                                                       |
| Dan won't accept a laptop extension or an exposed endpoint               | Blocks the route                     | Show him the read-only guard, log and tests; offer a reverse-proxied endpoint only if he asks |
| The page finder misses a clause in an amendment or schedule              | A wrong "no change"                  | Select pages generously, show quotes and pages, measure the miss rate in S2                   |
| Scanned contracts                                                        | Poor text                            | OCR step; measure; decide with Abhishek                                                       |
| Claude extracts a wrong value and states it with confidence              | Wrong answer                         | Quote must match the page text; otherwise "not checked". Numbers come only from code          |
| Different people get different answers                                   | Distrust                             | Composite tool; skills; a golden set; per-user runs logged                                    |
| Tool count grows and selection degrades                                  | Wrong tool calls                     | Hold to six baseline tools; add tools only through a decision                                 |
| Expectation gap: phase 1 has no review queue, decision record or watcher | A "this isn't what we wanted" moment | State it in writing now (section 1)                                                           |
| Teams-plan data terms differ from what we assume                         | Policy breach                        | Verify before any real data; the gate above                                                   |
| Prompt injection through contract text                                   | Steered answer                       | Tools read-only and scoped; contract text labelled as data; hostile-text test in S5           |
| Maintenance when the MCP spec or Claude Desktop changes                  | Rework                               | Plain functions plus a thin wrapper; pin versions; one server                                 |

## 9. How a later phase builds on this

The same `core/` functions become the tools layer of P2 (pipelines) or P3 (orchestrator). That is the path Aditya described: the MCP base stays and orchestration is added [8 Oct 13:53, 14:11]. Step 2 would add the watcher, a review queue, a recorded decision, a shared records store and an audit of the answer, which is where Abhishek's audit goal is met. Per-user memory is a known ceiling: a shared decisions store *"might not scale… beyond, say, four or five users"* [8 Oct 25:03].

## 10. Open items to verify (nothing here is checked yet)

- Current MCP Python SDK API and the desktop-extension (`.mcpb`) manifest format.
- Whether Ingenus's Teams plan supports custom connectors, desktop extensions, MCP prompts and shared skills, and who the Owner is.
- Whether Anthropic's docs still say a remote connector must be reachable from Anthropic's IP ranges.
- How a laptop extension identifies the user and holds a credential.
- The Teams plan's data-retention and training terms.
- The real SAP route; do not name SAP tables, T-codes or BAPIs until Dan confirms them (CLAUDE.md rule 9).
- ECC or S/4, and the RISE edition.
