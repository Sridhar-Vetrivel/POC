# Developer guide

How to start, work in and understand this repo. Read it once, then use the sections as a reference.
For *what* we are building and why, read [README.md](README.md) and [MCP-PlugIn/Plan.md](MCP-PlugIn/Plan.md).
For the rules every change must follow, read [CLAUDE.md](CLAUDE.md). This guide is the "how".

> **Status (13 Oct 2026).** Phase 1 v0 is built on **synthetic data and a mock SAP**. It is not yet verified
> in Claude Desktop, against real SAP, or on Ingenus's setup. Nothing in this repo is confirmed by Ingenus.

---

## 1. The idea in five lines

1. A person at Ingenus asks **Claude** (their own app) to check a customer's contract against SAP.
2. Claude calls **our tools** (an MCP server running on the person's laptop) to find the contract, read the
   right pages, and read the rebate setup from SAP.
3. **Claude** reads the contract pages and extracts each rate, with an **exact quote**.
4. **Our code** (no AI) checks every quote is really on that page, compares with SAP, and computes the gap.
5. A **person** reads Claude's answer and decides. The system never changes SAP and never decides anything.

So the split is: **Claude reads and talks; our code looks things up, checks and calculates.** That split is the
whole design. If you are unsure where something belongs, ask: "does a wrong answer here cost money?" If yes, it
is code with tests, not Claude's judgment.

## 2. Set up (Windows)

Requires Python 3.12+ (3.13 is what the bundle is built with) and, for packaging only, Node.js.

```powershell
cd C:\Users\sridhar.vetrivel\INGENUS\POC
python -m venv .venv                  # already exists on this machine
.\.venv\Scripts\Activate.ps1          # Git Bash: source .venv/Scripts/activate
pip install -e ".[dev]"
pytest                                # expect: 80 passed
ruff check . ; ruff format --check .  # expect: clean
```

`pip install -e` installs two packages from non-standard places (see `[tool.setuptools]` in `pyproject.toml`):
`ingenus_plugin` (from `MCP-PlugIn/src/`) and `mcp_servers` (from the repo root). Editing the files is enough; no
reinstall is needed.

No API key is needed. Phase 1 makes **no Claude API calls** (Claude on the user's own plan does the reading).

## 3. Map of the repo

```
POC/
├── README.md · CLAUDE.md · developer_guide.md · pyproject.toml
├── MCP-PlugIn/                  PHASE 1: everything for the plug-in
│   ├── Plan.md                  scope, decisions, build steps S0-S6, risks
│   ├── README.md                run commands, known limits
│   ├── src/ingenus_plugin/
│   │   ├── core/                the logic (plain functions)  <-- start here
│   │   ├── server/              thin MCP wrapper (stdio)
│   │   ├── report.py            usage report from the tool-call log
│   │   └── evals.py             page-finder eval
│   ├── skills/v1/               8 skills (guidance for Claude, markdown)
│   ├── prompts/                 the MCP prompt (contract_check.v1.md)
│   ├── packaging/               desktop-extension manifest, build and smoke-test scripts
│   ├── tests/                   Phase 1 tests
│   ├── tools/write_schema.py    developer script (writes the extraction schema)
│   └── docs/S0_spike_results.md what was and was not tested
├── slices/contract_to_sap_check/  the business meaning, as DATA (shared with later phases)
│   ├── topics.v1.yaml           keywords the page finder uses
│   ├── ontology/customers.v1.yaml   customer names and aliases -> SAP ids
│   ├── rules/compare.v1.yaml    comparison rules (tolerance, rounding, bases)
│   ├── schemas/contract_terms.v1.json   what Claude must pass to compare
│   └── evals/golden/            page labels (generated) and the 16 golden questions
├── mcp_servers/sap/             the read-only SAP interface and adapters (shared)
│   ├── interface.py             ONE method: read(). No write methods exist
│   └── adapters/                mock.py (used), real_stub.py (refuses to run)
├── docs/decisions/              short decision records (0001, 0002)
└── tests/test_no_domain_terms.py   repo-wide rule test

v0's data and build output live inside MCP-PlugIn/ (moved 19 Oct 2026):
MCP-PlugIn/data/synthetic/       fake SAP data and fake contract PDFs + the generator
MCP-PlugIn/data/public/          empty: public sample contracts will go here
MCP-PlugIn/data/runtime/         tool-call log (git-ignored)
MCP-PlugIn/build/                generated desktop-extension bundle (git-ignored)
```

Why `slices/` and `mcp_servers/` sit outside `MCP-PlugIn/`: a later phase reuses them unchanged. Phase 1 code may
use business words (contracts, rebates); the shared folders may not (enforced by `tests/test_no_domain_terms.py`).

## 4. How a request flows (read the code in this order)

Follow one tool call, `compare_contract_to_sap`, through the files.

1. **`core/registry.py`**: the `@tool(read_only=True)` decorator. It registers the function in `TOOLS`, wraps it so
   every call is **logged** (success or error), and **refuses** `read_only=False`.
2. **`core/tools.py`**: the six tools. Each is a plain function with typed, described arguments. **The docstring is
   what Claude reads as the tool description**, so write it for Claude: what it does, when to use it, what it
   returns, what it will not do.
3. **`core/models.py`**: the Pydantic models for every input and output (`ExtractedTerm`, `Finding`,
   `CompareResult`...). The field descriptions also reach Claude as the schema.
4. **`core/compare.py`** (the heart):
   1. verify each term's citation (`core/citations.py`): document inside the folder, page exists, quote is on the
      page, quote names the product and contains the rate; failures go to `not_checked`;
   2. remove duplicates; a later effective date replaces an earlier rate from its own date; two different rates for
      the same date are reported as a conflict;
   3. index SAP setup and monthly sales (read through `core/sap.py` and the adapter);
   4. for each term, per month from its effective date to `as_of`: `(contract rate - SAP rate) x base`; partial
      months by days; a matching line needs only the latest month's sales;
   5. build the summary and caveats. All money is `Decimal`, rounded half-up to 2 places.
5. **`core/contracts.py`** and **`core/documents.py`**: find files (drafts left out on purpose), read pages (text PDFs
   and `.txt`), pick pages by keyword (`topics.v1.yaml`) plus page 1 and neighbours. Reports unreadable pages.
6. **`core/customers.py`**: name resolution. Exact or alias match only; ambiguity is returned, never resolved.
7. **`core/scope.py`**: `resolve_inside()`. Every document path goes through it, so nothing outside the contract
   folder is read.
8. **`core/calllog.py`**: the log. The **only** module allowed to write files. One JSON line per call: time, user,
   tool, arguments, result *counts*, not-checked count, duration. Never page text.
9. **`server/app.py`**: builds the MCP server, adds every tool from `TOOLS` marked read-only, adds the prompt. No
   business logic here.

## 5. Settings (environment variables)

Defaults point at the synthetic data in this repo. The desktop extension sets them from its manifest.

| Variable | Meaning | Default |
|---|---|---|
| `INGENUS_CONTRACTS_DIR` | Contract folder the tools may read | `MCP-PlugIn/data/synthetic/contracts` |
| `INGENUS_SAP_ADAPTER` | `mock` (works), `real` (stub that refuses) | `mock` |
| `INGENUS_SAP_MOCK_FILE` | Mock SAP data (must be labelled SYNTHETIC) | `MCP-PlugIn/data/synthetic/sap/entities.json` |
| `INGENUS_SLICE_DIR` | Topics, aliases, rules | `slices/contract_to_sap_check` |
| `INGENUS_PROMPTS_DIR` | Where `contract_check.v1.md` lives | `MCP-PlugIn/prompts` |
| `INGENUS_LOG_PATH` | Tool-call log file | `MCP-PlugIn/data/runtime/tool_calls.jsonl` |
| `INGENUS_USER` | Overrides the user name in the log | OS user |

Tests set their own temp log and user (`conftest.py`), so they never touch `MCP-PlugIn/data/runtime/`.

## 6. Everyday commands

```powershell
pytest                                        # everything, offline, about 10 seconds
pytest MCP-PlugIn/tests/test_compare.py -k fabricated    # one test
python -m ingenus_plugin.server               # run the server on stdio (an MCP client talks to it)
python -m ingenus_plugin.report               # who used which tool, per day; returning users
python -m ingenus_plugin.evals page-finder    # how well the page finder finds labelled pages
python MCP-PlugIn/data/synthetic/generate_contracts.py   # regenerate fake contracts + labels (deterministic)
python MCP-PlugIn/tools/write_schema.py       # rewrite contract_terms.v1.json after a model change
python MCP-PlugIn/packaging/build_bundle.py   # build MCP-PlugIn/build/ingenus-contract-check.mcpb
python MCP-PlugIn/packaging/smoke_test_bundle.py   # run the staged bundle WITHOUT the venv
ruff check . ; ruff format .                  # lint and format (build/ is excluded)
python scripts/check.py                       # ALL quality gates, once, at the end of a complete change
python scripts/check.py --fast                # lint, format and the repo-rule scans only
python scripts/check.py --fix                 # apply safe fixes and formatting, then check
```

**About `scripts/check.py`.** It is the "did I break anything" command: ruff (lint and format), bandit, pip-audit, repo-rule
scans (no stdout in server code, no secrets, no client material, synthetic data labelled, guidance files
versioned, fixtures and labels in sync, extension manifest matches the tools, markdown links resolve) and the full
test suite. Run it **once when a complete change is finished**, not after each edit; while you work, run only the
tests you need. Read all the failures, fix them all, run it again, repeat until `0 failed`. Fix the cause: do not
weaken a gate or add `noqa`/`nosec`. The `.bat` and `.sh` files next to it are thin wrappers.

## 7. Recipes: how to change things

**Change what SAP "says" (mock data).** Edit `MCP-PlugIn/data/synthetic/sap/entities.json` (keep the `_label` that says SYNTHETIC; the
adapter refuses data without it). Tests that assert Chain X numbers will tell you what you broke.

**Add a synthetic contract.** Add it to `MCP-PlugIn/data/synthetic/generate_contracts.py` (with its `term_pages` label), run the
generator, then `python -m ingenus_plugin.evals page-finder`. Do not hand-edit PDFs. Do not add real documents.

**Add a customer or alias.** `slices/.../ontology/customers.v1.yaml` (and the `customers` list in the mock SAP data).
Versioning rule: once a recorded eval run has used `v1`, create `v2` instead of editing (and point `Settings` at it).
While v1 is only used by tests, edit in place.

**Make the page finder look for a new wording.** Add the keyword to `topics.v1.yaml`. Re-run the page-finder eval.
Be honest about why: adding a word because a *test* missed it can hide the real risk (real contracts use words we
have not seen). See the note in `tests/test_page_finder_eval.py`.

**Change a comparison rule** (tolerance, rounding, default bases). `slices/.../rules/compare.v1.yaml`. The rule is data;
the logic is `core/compare.py`. Add a test to `tests/test_compare.py` first.

**Add a new kind of term (for example a prompt-pay discount).** Extend `TermKind` and `ExtractedTerm` in
`core/models.py`, handle it in `core/compare.py` and `default_basis` in the rules, rewrite the schema
(`write_schema.py`; if an eval used v1, write v2), update the `extraction-schema` skill, and add tests.

**Add a tool.** More tools make Claude choose worse, so this needs a decision record in `docs/decisions/` first. Then:
write the function in `core/tools.py` with `@tool(read_only=True)`, a precise docstring and typed arguments;
add models to `core/models.py`; add the name to `BASELINE_TOOLS` in `tests/test_readonly.py`; add it to
`packaging/manifest.json`; mention it in the playbook skill if Claude must use it; add a golden question.

**Change a skill or the prompt.** Edit `skills/v1/<name>/SKILL.md` or `prompts/contract_check.v1.md`. Keep the YAML header
valid: `name` equals the folder name, `description` is 200 characters or fewer **and contains no `: `**. A test checks
this and that skills only mention tools that exist. Skills are guidance, not enforcement: anything that must hold
goes into tool code and tests.

**Swap the SAP adapter (later).** Implement `read(ReadQuery) -> ReadResult` in a new file under
`mcp_servers/sap/adapters/`, wire it in `core/sap.py:get_reader`. Nothing above the adapter should change. Do not
name SAP tables, T-codes or BAPIs until Dan confirms the route.

## 8. The tests, and what each protects

| File | Protects |
|---|---|
| `test_compare.py` | The numbers: Chain X, 5 identical runs, fabricated or wrong-page quotes, partial months, supersession, conflicts, tiny rate differences, negative gaps |
| `test_contracts.py` | File finding, draft exclusion, page selection, blank pages, hostile text labelled as data, path traversal refused |
| `test_readonly.py` | Exactly six tools, all read-only; a write tool cannot be registered; **no code outside `calllog.py` writes files**; the SAP interface has one method |
| `test_calllog_and_report.py` | One log line per call, no page text in the log, errors logged, logging failures never break a tool, the report |
| `test_server_stdio.py` | The real server over stdio: full demo and log, acting as Claude's client |
| `test_page_finder_eval.py` | The honest baseline of the keyword search |
| `test_skills_and_prompts.py` | Skill headers, name = folder, skills and prompt refer only to real tools |
| `test_schema_sync.py` | The published extraction schema matches the model |
| `test_sap_mock.py` | Mock SAP reads, as-of dates, bad periods, only the mock adapter is wired |
| `../tests/test_no_domain_terms.py` | Shared folders contain no business words |

Style: tests are offline, name the behaviour in the function name, and use `make_world` (in `conftest.py`) to build
a tiny contract folder and SAP in a temp directory when they need different data.

## 9. Trying it with a real MCP client

`tests/test_server_stdio.py` is the pattern: start `python -m ingenus_plugin.server` with `StdioServerParameters`, use
`ClientSession`, call tools. Note: **a stdio client passes only a few environment variables to the server**, so
pass `env={...}` explicitly. To try it in Claude Desktop, build the bundle and follow
[MCP-PlugIn/README.md](MCP-PlugIn/README.md). Then run the questions in `evals/golden/golden_questions.v1.md`.

## 10. Debugging tips

- **A tool misbehaves in Claude but passes tests?** Read the log (`python -m ingenus_plugin.report`, or open
  `tool_calls.jsonl`). It shows the arguments Claude actually sent, including the extracted terms and quotes.
- **A term lands in "not checked".** Read its `reason`. The usual causes: the quote has different spacing or
  punctuation than the page, the quote lacks the rate or the product name, or the page number is the document's
  printed number rather than the PDF page.
- **Server dies on start.** Run `python -m ingenus_plugin.server` yourself and read stderr. **Never `print()` to
  stdout in server code**: on stdio it is the protocol channel and one stray print breaks the connection. Use stderr.
- **Bundle works in the venv but not outside it.** Run `smoke_test_bundle.py`. The SDK needs pywin32 on Windows and
  finds it through a `.pth` file, which is why `server/main.py` uses `site.addsitedir`.
- **PDF text looks odd.** Extraction is `pypdf`. Hyphenated line breaks or ligatures can stop an exact quote
  matching. That is a "not checked", not a bug in the comparison.
- **`ruff --fix` rewrote something under `MCP-PlugIn/build/`.** Don't lint it; it is excluded for this reason.

## 11. The rules in one list (full text in CLAUDE.md)

1. SAP is **read-only**. No write tool, adapter or code path, not even a mock.
2. Only `calllog.py` writes files, and only to the log location. Source files are never changed.
3. **No AI in comparison or exposure.** Same inputs, same output.
4. Every extracted value carries a **citation** (`document`, `page`, `clause`, exact `quote`) that code checks.
5. **"Not checked" beats guessing.** Report gaps; never fill them.
6. **Synthetic or public data only** until Ingenus's data policy is signed off. Never add client files.
7. Never invent SAP tables, T-codes or BAPIs. Real adapters stay `TODO(verify)` stubs.
8. Version prompts, skills, schemas and rule files by filename; don't edit a version an eval has used.
9. Phase 1 has **no agent of ours**. Don't build Phase 2 pieces (`foundation/`, orchestrator, review queue) unless asked.
10. Say plainly what you did not verify.

## 12. Glossary

| Term | Meaning here |
|---|---|
| **MCP** | Model Context Protocol: the standard way an AI app (Claude) calls tools on a server |
| **Tool** | One function Claude can call (`find_contract_files`...). Ours are read-only |
| **MCP prompt** | A ready-made starting instruction the user can pick in Claude (`contract_check`) |
| **Skill** | A folder of markdown guidance Claude can load (our playbook, quote rules...). Not enforced |
| **Desktop extension (`.mcpb`)** | A package a user installs in Claude Desktop; our server then runs on their laptop |
| **Slice** | One use case's meaning and data (here: Contract-to-SAP Check), kept out of shared code |
| **Adapter** | The part that talks to SAP; the mock now, a real one later, behind one `read()` method |
| **Citation / quote check** | `{document, page, clause, quote}` and the code check that the quote is on that page |
| **Not checked** | An item the system could not support; always listed, never guessed |
| **as_of** | The date to check up to; the SAP setup is read as at this date |
| **Indicative exposure** | Rough gap summed from each effective date to `as_of`. Not an accounting number |
| **Synthetic** | Invented data (Chain X and the rest). The only data allowed until policy sign-off |
| **Option X / Y** | X: Claude on the user's plan extracts terms (built). Y: our own LLM would (not built) |

## 13. Phases and numbering (easy to confuse)

The call and the deck call this option **P1** (MCP plug-in). The older pre-sales .md files call it **P4**. In this
repo say **"Phase 1 (MCP plug-in)"**. Phase 2 (gateway, orchestrator, review queue, audit) is only a proposal.

## 14. What is not built or not verified

No install test in Claude Desktop; no real SAP route; no OCR (scanned pages are reported); only text PDFs and
`.txt`; no public sample contracts yet; no review queue, recorded decision, watcher or audit of Claude's answer;
Ingenus's Claude plan, Owner and laptops (Python version) unknown; the keyword page finder misses unlisted wording.
Details: [MCP-PlugIn/docs/S0_spike_results.md](MCP-PlugIn/docs/S0_spike_results.md) and the "Known limits" list in
[MCP-PlugIn/README.md](MCP-PlugIn/README.md).

## 15. Where to look for what

| Question | File |
|---|---|
| Why are we building this, and what is out of scope? | `MCP-PlugIn/Plan.md` sections 1-2 |
| What did we decide and what are the alternatives? | `docs/decisions/` and Plan section 3 |
| What is done and what is not? | README status tables |
| What can I change safely? | Section 7 of this guide |
| What did Ingenus actually say? | The call transcripts (outside this repo, in `2026/Call_Transcripts/`) |
