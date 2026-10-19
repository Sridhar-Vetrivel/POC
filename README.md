# Ingenus POC: a read-only AI layer over SAP and document folders

A proof of concept for Psiog's pre-sales proposal to Ingenus: **one reusable, read-only AI layer over SAP and document folders**, built **one thin slice at a time**.

> **Pre-sales status.** Nothing in this repo is confirmed by Ingenus. There is **no access to Ingenus systems or data**. Every SAP record, customer, product and contract here is either **synthetic** (invented, labelled as such) or a **public document** (e.g. SEC filings). Do not add client files to this repo.

---

## Start here (for people and AI agents)

1. **Current work is Phase 1: the MCP plug-in.** Everything for it is in [`MCP-PlugIn/`](MCP-PlugIn/). Read [`MCP-PlugIn/Plan.md`](MCP-PlugIn/Plan.md) first: scope, tools, build steps (S0 to S6), decisions, risks.
2. **Then read [`CLAUDE.md`](CLAUDE.md).** It holds the rules every change must follow, and says which rules apply to which phase.
3. **The rest of this file is the bigger picture**: where Phase 1 sits, and the larger foundation that later phases would add. **Do not build Phase 2 work unless the repo owner asks.**
4. When you finish a step, update the status table below.

**Guides:** [`developer_guide.md`](developer_guide.md) (how to work in the code) · [`design_guide.md`](design_guide.md) (why it is built this way, from a systems-design view) · [`MCP-PlugIn/docs/demo_guide.md`](MCP-PlugIn/docs/demo_guide.md) (hands-on test in Claude Desktop).

### Where we are now

| Phase | What | Status |
|---|---|---|
| **1. MCP plug-in** (`MCP-PlugIn/`) | Read-only MCP server with a few business-level tools, a skills pack and a tool-call log, used from Ingenus's own Claude | **Current. v0 built on synthetic data and a mock SAP** (13 Oct 2026). 80 offline tests pass. **Not yet verified in Claude Desktop, against real SAP, or on Ingenus's setup** |
| 2. Governed foundation | Gateway, pipelines, orchestrator, review queue, audit (the larger design below) | Proposal only. Not started. Not chosen by Ingenus |
| 3+. More slices | COA vs filed spec, order-status Q&A, others | Paper only |

| Phase 1 step | Status (13 Oct 2026) |
|---|---|
| S0 Spikes (connectivity) | **Partly done.** Local stdio server and the `.mcpb` bundle verified. **Not done:** install in Claude Desktop, remote connector, Ingenus plan and laptops, SAP reachability. See [`MCP-PlugIn/docs/S0_spike_results.md`](MCP-PlugIn/docs/S0_spike_results.md) |
| S1 Skeleton | **Done.** Scope guard, read-only tests, tool-call log, mock SAP adapter, Chain X fixtures |
| S2 Contract pages | **Done on synthetic data.** 29 labelled contracts; overall recall 0.92; 2 misses on unlisted wording, reported not hidden. Public sample contracts **not added yet** |
| S3 Compare | **Done.** Chain X gives 3 lines that differ + 1 match, 8,500.00 a month, 17,000.00 for 1 Jul to 31 Aug, identical across 5 runs; a fabricated quote is rejected |
| S4 Package and skills | **Built, not verified in Claude Desktop.** MCP wrapper, `.mcpb` bundle (builds and runs under a system Python), 8 skills, MCP prompt, usage report. The "demo runs in Claude Desktop" criterion is **not met yet** |
| S5 Evals and hardening | **Partly done.** Automated tests cover hostile text, out-of-scope paths, read-only checks and log contents. 16 golden questions are written but **not yet run in Claude** |
| S6 Pilot (gated) | not started (the gate in the Plan still applies) |

The directories under "Repository layout" that Phase 1 uses now exist. `foundation/`, the Phase 2 MCP servers and `probes/` do not.

---

## The bigger picture

### What Ingenus asked for
A reusable AI layer over SAP (read-only) and their document folders and SharePoint, not a new workflow per request. They want to start small and prove adoption first. The first use case is the **Contract-to-SAP Check**.

### How Ingenus chose to start (8 Oct 2026 call)
Of the four options Psiog presented, Ingenus's Abhishek said *"I like the part one for now"* [8 Oct 46:57] and asked for something simple, quick and cheap that people will actually use. **Part one is the MCP plug-in.** The tools built for it carry forward if the solution grows [8 Oct 13:53, 14:11]. Timestamps are from the call transcript, which is kept outside this repo.

| Name in decks and the call | Name in the older pre-sales .md files | What it is |
|---|---|---|
| **P1** MCP plug-in | P4 | Our tools only; the client's own Claude drives. **This is Phase 1** |
| P2 Slice pipelines | P1 | Fixed workflows, one per use case |
| P3 Orchestrator + skills | P2 | One agent following a playbook |
| P4 Domain agents | P3 | Many specialist agents |

The numbering differs between documents. In this repo, say **"Phase 1 (MCP plug-in)"** and avoid bare "P1" or "P4".

### Phase 1 in one paragraph
One MCP server with about six read-only tools. Ingenus's Claude (a Teams plan, about 12 licences) calls them. Our code finds the contract pages, reads the SAP setup (a **mock** for now), checks that every quote Claude extracted really appears on its page, and compares contract against SAP in plain code. A log of tool calls gives the usage and adoption numbers. **Not included in Phase 1:** a watcher, a review queue, a recorded decision, an audit of the answer, SAP writes, any agent of ours. Details and defaults are in [`MCP-PlugIn/Plan.md`](MCP-PlugIn/Plan.md).

### The use case
When a customer contract changes, the system reads the new terms, compares them with the rebate and fee setup in SAP, and shows a person where SAP is now wrong, since when, and roughly how much money that affects. A person approves and makes any SAP change. The system **never writes to SAP**.

**Demo scenario (synthetic):** "Chain X" signs Amendment 2, back-dated to 1 Jul. Product A rebate goes from 4% to 6%, Product C is added at 5%, and the admin fee goes from 2% to 2.5%. SAP still has the old setup. On $400,000 a month of purchases, that is **$8,500 a month under-reserved**. The full walk-through is in the pre-sales note *Contract_to_SAP_Check_Explained.md*, which is kept outside this repo. The exact expected numbers are in `CLAUDE.md`.

### Phase 2 and later (proposal, not started): the governed foundation
The larger design below is what Psiog would add if Ingenus wants control over review and audit, which Phase 1 does not give. It also keeps the earlier idea of a **coupling test**: write two more slices on paper (COA vs filed spec, order-status Q&A) and log every foundation change they would need. This is the original purpose of the repo. It is on hold until Phase 1 is delivered and Ingenus decides.

```
 Front door (CLI for the POC)                                   FOUNDATION
 └─ Orchestrator agent (chat / on-demand)   ── skill registry ──┐
 └─ Slice pipelines (fixed workflows, not agents)               │
        │  every tool and LLM call goes through ↓               │
 Policy & audit gateway  (read-only enforced, role access, audit log, cost caps)
        │
 ┌──────┴─────────┬────────────────┬──────────────────┐
 SAP MCP          Knowledge MCP     Records MCP         Ontology / entity resolution
 (read-only;      (files, text,     (typed records,     (aliases, NDC↔material,
  mock adapter)    versions)         lineage, as-of)     customer names↔SAP ids)
        │
 Comparison engine (standard × actual × rules → findings)  ·  Review & verify  ·  Evals
───────────────────────────────────────────────────────────────────────────────────────
 slices/contract_to_sap_check/   ← slice package: config, schemas, rules,      SLICE
                                    skills, prompts, ontology terms, test set
```

**Phase 1 builds only the "tools" row of this picture** (the SAP and knowledge tools, the comparison, the quote check), without the gateway, orchestrator, records store or review queue above it. It is written as plain functions so that it can become the tools layer of Phase 2.

| Phase 2 component | Kind | Notes |
|---|---|---|
| Orchestrator | **The only agent** | Handles open-ended requests ("here's a file, where is SAP off?"). |
| `contract_check` pipeline | Fixed workflow | Detect → Classify → Extract → Match → Compare → Estimate → Review → (person acts) → Verify |
| Classify, Extract, Resolve (fallback) | Single LLM calls with structured output | Bounded tasks with fixed output schemas. |
| Compare, Estimate, Verify | Plain code | No LLM. Same inputs give the same answer. |

---

## Repository layout (target)

```
POC/
├── README.md · CLAUDE.md · pyproject.toml
├── MCP-PlugIn/                 # PHASE 1 (current): the MCP plug-in
│   ├── Plan.md                 # scope, tools, steps S0-S6, decisions, risks
│   ├── src/ingenus_plugin/
│   │   ├── core/               # tool functions, scope guard, log, quote checker, compare
│   │   └── server/             # thin MCP wrapper, stdio entry point
│   ├── skills/                 # skills pack for Claude (markdown, versioned)
│   ├── prompts/                # MCP prompt(s)
│   ├── packaging/              # desktop extension manifest and build script
│   └── tests/
├── slices/
│   ├── contract_to_sap_check/  # slice.yaml, schemas/, rules/, skills/, prompts/,
│   │                           # ontology/, evals/golden/   (used by Phase 1 and later)
│   └── _paper/                 # Phase 2 coupling-test packages: coa_vs_spec, order_status_qa
├── mcp_servers/
│   ├── sap/                    # tool interface + adapters/: mock (Phase 1), ecc/s4 (later, TODO(verify))
│   ├── knowledge/              # PHASE 2 only: local folder standing in for the network drive
│   └── records/                # PHASE 2 only: exposes foundation.records as tools
├── data/
│   ├── synthetic/              # fake SAP fixtures and fake contracts (committed)
│   ├── public/                 # public sample contracts (committed, with source URLs)
│   └── runtime/                # tool-call log and any records store (ignored by git)
├── outbox/                     # the ONE folder the system may write files to (ignored by git)
├── docs/
│   ├── decisions/              # short architecture decision records
│   └── coupling_log.md         # Phase 2: every foundation change a slice needed, and why
├── foundation/                 # PHASE 2 only, not started; domain-neutral
│   ├── gateway/ · orchestrator/ · registry/ · records/ · compare/
│   ├── review/ · ingestion/ · ontology/ · evals/
├── probes/live_order_status/   # PHASE 2 only: live-read + per-user identity probe
└── tests/                      # repo-wide tests, including the domain-word test
```

Shared by both phases: `slices/contract_to_sap_check/` (rules, schemas, ontology terms, golden tests), and the mock SAP adapter. Keeping them outside `MCP-PlugIn/` is what lets Phase 2 reuse them. Since 19 Oct 2026 v0's synthetic data and build output live in `MCP-PlugIn/data/` and `MCP-PlugIn/build/` (v1 keeps its own copy; see `docs/v1_impact_analysis_and_proposal.md`).

## Phase 1 milestones

Phase 1 uses **steps S0 to S6** from [`MCP-PlugIn/Plan.md`](MCP-PlugIn/Plan.md). In short:

| Step | Done when |
|---|---|
| S0 Spikes | A hello-world MCP server works in Claude Desktop as a desktop extension and as a remote connector, and SAP reachability is tested. A pass/fail table exists |
| S1 Skeleton | Scope guard, read-only test, tool-call log and mock SAP adapter work; Chain X fixtures load |
| S2 Contract pages | `find_contract_files` and `get_contract_pages` work; the miss rate on labelled pages is reported |
| S3 Compare | Chain X gives **3 variances + 1 match, $8,500 a month, $17,000 for 1 Jul–31 Aug**, identical across 5 runs; a fabricated quote is rejected |
| S4 Package and skills | The demo runs end to end in Claude Desktop with the extension installed |
| S5 Evals and hardening | Golden questions, hostile text, out-of-scope and read-only checks reported |
| S6 Pilot (gated) | Real data only after the gate in the Plan; otherwise synthetic |

## Phase 2 milestones (proposal; on hold)

| # | Milestone | Done when |
|---|---|---|
| M0 | Skeleton + slice package format | `slice.yaml` schema written; loader validates it; the domain-word test is in place and passing |
| M1 | Happy path, end to end | `Chain X` demo produces the 3 variances + 1 match and **$17,000** indicative exposure (Jul–Aug), identical across 5 runs |
| M2 | Extraction you can trust | Test set of 20–30 labelled contracts (synthetic + public); per-field accuracy reported; every cited quote verified against the source text; "not checked" list populated |
| M3 | Review and verify loop | Findings accepted/rejected/corrected with comments; verify job closes lines after a (simulated) SAP update; audit log shows every tool and LLM call |
| M4 | Adapter swap + live probe | A second mock SAP adapter with a different shape (ECC-like vs S/4-like) swapped in with **zero slice changes**; `get_order_status` answered live through the gateway with a per-user identity |
| M5 | Coupling test | `coa_vs_spec` and `order_status_qa` packages written; every foundation change they need logged in `docs/coupling_log.md`; foundation interfaces frozen |

## Success measures

**Both phases:**
- **Deterministic:** the same inputs give the same findings, every run.
- **Traceable:** every finding cites document, page, clause and a verbatim quote that code has checked.
- **Honest:** every run lists what it could not check.
- **Read-only:** no code path can write to SAP; files are written only to the set locations.

**Phase 1 adds:** **adopted** (calls per user from the log, users who come back) and **trusted** (answers spot-checked against known contracts by a named SME).

**Phase 2 adds:** **decoupled** (the adapter swap needs no slice change; coupling-log entries are counted and explained).

## Explicitly out of scope

**Both phases:** real SAP or Ingenus data · writing to SAP · production hardening · GxP validation (noted as a cost for the COA slice, not done here) · chargebacks.

**Phase 1 also excludes:** a watcher or scheduler · a review queue, recorded decision or pause and resume · an audit of the AI's answer · any agent of ours · a portal or Teams front door · the COA slice.

## Getting started

**Phase 1 needs:** Python 3.12+, and Claude Desktop with a Claude plan for the spikes and the demo. **Phase 1 makes no Claude API calls by default** (Claude on the user's own plan does the extraction), so no API key is needed unless a decision record says otherwise. Phase 2 needs Claude API access.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
pytest                                   # 80 offline tests, including the domain-word and read-only tests
ruff check . && ruff format .
python scripts/check.py                  # all quality gates; run once at the end of a complete change
python -m ingenus_plugin.server          # the MCP server on stdio (an MCP client talks to it)
python -m ingenus_plugin.report          # usage report from the tool-call log
python -m ingenus_plugin.evals page-finder
```

More commands (build the desktop extension, regenerate the synthetic contracts) are in [`MCP-PlugIn/README.md`](MCP-PlugIn/README.md). Do not run `ruff` on the generated `MCP-PlugIn/build/` folder; it is excluded in `pyproject.toml`.

## Open decisions

**Phase 1** has its own list, D1 to D7, each with a default, in `MCP-PlugIn/Plan.md` section 3: how Claude reaches the server, who extracts the terms, the SAP route, data policy, scope, the domain-neutral exception and the log location. Record any change in `docs/decisions/`.

**Phase 2 and general:**
- Review mode: advisory or blocking (an Ingenus decision; the POC supports both).
- Who may see contract terms: Finance and contracts only, or Sales as well.
- Real SAP access route (RFC/BAPI, OData, desktop-flow exports, SAP-managed): depends on ECC vs S/4, which is unknown. SAP is on RISE (hosted and managed by SAP) and reached over an IPSEC tunnel [8 Oct 33:10, 43:04].
- Where the records store and audit log would live at Ingenus, given the "write only to set locations" rule.
- Data and AI policy: **not received**. No real data until it is.

## Repo hygiene

- Keep this repo **private**.
- If this folder lives inside OneDrive, git and OneDrive sync can conflict. Consider cloning the GitHub repo to a non-synced path (e.g. `C:\dev\ingenus-poc`) once it is pushed.
