# CLAUDE.md

Guidance for Claude Code and other AI agents working in this repository. Read this file, then `README.md` (the bigger picture), then `MCP-PlugIn/Plan.md` (the work in progress).

## What this repo is

A pre-sales POC for Ingenus, a US generics pharma company: **a read-only AI layer over SAP and document folders, built one thin slice at a time.** Nothing is confirmed by the client. There is no access to client systems or data.

It has two levels:

- **Bigger picture (Phase 2 and later, proposal, not started):** a governed foundation (policy and audit gateway, pipelines, one orchestrator agent, review queue, records store) with slices plugged in, plus a coupling test on paper. Described in `README.md`.
- **Phase 1, the current work: the MCP plug-in** in `MCP-PlugIn/`. One MCP server with about six read-only business-level tools, a skills pack and a tool-call log, used from Ingenus's own Claude (Teams plan). It is the first, smallest step, and Ingenus chose it ("I like the part one for now", 8 Oct 2026 call). Its tools are plain functions so they can become the tools layer of Phase 2.

**Unless the user says otherwise, work on Phase 1 only. Do not build `foundation/`, the orchestrator, the review queue, the gateway or the Phase 2 milestones.**

## How to work here (vibe-coding guide)

1. **Orient:** read `MCP-PlugIn/Plan.md`. Find the first step in its table (S0 to S6) that is *not started* in the `README.md` status table. That is your task unless the user names another.
2. **Stay inside the step.** Build what the step's "Done when" says, nothing more. If you see extra work, note it in your reply and leave it.
3. **Test first, offline.** Write the test that proves the step's "Done when", then the code. Tests run offline with no network and no Claude API calls.
4. **Use the defaults in `MCP-PlugIn/Plan.md` section 3** (D1 to D7) when a decision is still open. If you must deviate, write a short note in `docs/decisions/` and tell the user. Don't silently change a default.
5. **Stop and ask** before: calling the Claude API (it costs money), adding a dependency that is not obviously needed, adding a seventh tool, adding anything that writes outside the set locations, or anything involving real SAP or Ingenus data.
6. **Never guess about the real world.** SAP table names, T-codes, BAPIs, release details, Claude plan features and Anthropic or MCP behaviour that the Plan marks **verify** stay unverified until checked against a source. Say what you did not verify.
7. **Run the full check once, at the end of a complete change** (see "The check" below). Not after each edit. While you work, run only the specific tests you need, for example `pytest MCP-PlugIn/tests/test_compare.py -k name`.
8. **When a step is done**, update the status tables in `README.md` and say what you tested and what you didn't.

## The check (`scripts/check.py`)

One command runs every quality gate: ruff lint and format, bandit, pip-audit, the repo-rule scans (no stdout in server code, no secrets, no client material, synthetic data labelled, guidance files versioned, fixtures and labels in sync, manifest matches the tools, markdown links resolve) and the full pytest suite.

**When to run it:** once, when a complete change is finished: a whole step (S1 to S6), a feature, a refactor, or any change that touched several files. **Do not run it after each fix or each edit**, and do not use it as a substitute for running the one test you are working on. Small single-file edits do not need it; the final check of the larger change covers them.

**What to do with the result:**
1. Run `python scripts/check.py` and read the whole output. It lists every failing gate and why.
2. Fix **all** the failures from that run, then run it again once. Repeat until it ends with `0 failed`. Use `python scripts/check.py --fix` first when only formatting or safe lint fixes are failing.
3. Fix the cause. Do not weaken a gate, edit a gate's word list, or add a suppression (`noqa`, `nosec`) to get green. If a gate is wrong, say so and ask.
4. Only report a change as done after the check ends with `0 failed`. If you cannot get it there (for example `pip-audit` has no network), say which gate you skipped and why.

Options: `--fast` (lint, format and the repo-rule scans only), `--only a,b`, `--skip pip-audit` (when offline), `--bundle` (also build and smoke-test the desktop extension; needs Node.js), `--list`. On Windows `scripts\check.bat` does the same; on macOS, Linux or Git Bash use `bash scripts/check.sh`. All three run the same logic.

## Hard rules

Breaking one is a defect, even if the tests pass. The numbering is kept stable because `MCP-PlugIn/Plan.md` refers to these numbers. Each rule says which phase it applies to.

1. **The foundation is domain-neutral** *(Phase 2 and the shared adapters)*. Nothing under `foundation/` or `mcp_servers/` (except `mcp_servers/sap/adapters/`) may mention contracts, rebates, admin fees, chargebacks, NDCs, customers by name, or any other slice term. Slice meaning lives only in `slices/<slice>/`. `tests/test_no_domain_terms.py` enforces this with a word list. Don't weaken the test to make code pass. Move the code instead.
   - **Phase 1 exception:** code under `MCP-PlugIn/` may use domain words (decision D6). The domain-word test skips `MCP-PlugIn/` only, and nothing else. Rules, schemas, ontology terms, and golden tests still live in `slices/contract_to_sap_check/`, not in `MCP-PlugIn/`.
2. **The foundation never imports from `slices/`** *(Phase 2)*. Slices plug in through the slice package (`slice.yaml`) and the registry. Phase 1 code may read slice files (rules, schemas) as data.
3. **If a slice needs a foundation change, log it** *(Phase 2)*. Add an entry to `docs/coupling_log.md`: what changed, which slice needed it, and whether the next slice would need it too. In Phase 1 nothing touches `foundation/`, so there is nothing to log yet.
4. **SAP is read-only** *(all phases)*. No SAP tool, adapter or code path may create, change or delete SAP data. Don't add a write tool, even a mock one. In Phase 2 the gateway rejects any tool not registered as read-only. **In Phase 1 the plug-in's own tool registry enforces it:** every tool is marked read-only, and a test fails if one is not.
5. **Files are written only to set locations** *(all phases)*. Allowed: `outbox/`, and the records store and logs under `data/runtime/` (in Phase 1 the tool-call log goes to a configured location, decision D7). Nothing deletes or moves source files or creates folders in source locations.
6. **No LLM in Compare, Estimate or Verify** *(all phases)*. These steps are plain, deterministic code driven by the slice's rule files. The same inputs must give the same findings.
7. **Every extracted field carries a citation** *(all phases)*: `{document, page, clause, quote}`. Code checks that the quote appears verbatim in the extracted source text. If the check fails, the field goes to the "not checked" list instead of being used. **In Phase 1 Claude extracts and passes the fields in, and `compare_contract_to_sap` does the check.**
8. **"Not checked" beats guessing** *(all phases)*. Low confidence, unreadable pages, unmatched names and missing SAP records are reported, never filled in.
9. **Only synthetic or public data** *(all phases, until Ingenus's data policy is received and signed off)*. Every synthetic value is labelled synthetic. Public documents keep their source URL alongside. Never add client documents, transcripts or real SAP extracts. Never make up real-looking SAP tables, T-codes or BAPIs. The real adapters are stubs marked `TODO(verify)` until discovery.
10. **Only the orchestrator is an agent** *(Phase 2)*. Slice pipelines are fixed workflows that make single, bounded LLM calls. Don't add agents to a slice without a decision record explaining why a fixed path won't do. **Phase 1 has no agent of ours at all:** Claude on the user's own plan decides the order of tool calls.

## Phase 1 conventions (MCP plug-in)

- **Plain functions first, MCP last.** Tool logic lives in `MCP-PlugIn/src/ingenus_plugin/core/` as plain Python functions with Pydantic inputs and outputs. `server/` is a thin wrapper with no business logic. This keeps maintenance low and lets the functions move into Phase 2.
- **Official MCP Python SDK.** Check its current API in its docs rather than writing it from memory. Mark tools read-only using the SDK's mechanism (**verify** the current API).
- **Baseline tools (six):** `find_contract_files`, `get_contract_pages`, `resolve_customer`, `get_rebate_setup`, `get_sales_volume`, `compare_contract_to_sap`. Add a tool only through a decision record. More tools degrade Claude's tool choice.
- **Composite beats fine-grained.** Put deterministic work (quote checks, comparison, exposure) inside `compare_contract_to_sap`. Don't leave it to Claude's reasoning.
- **Tool descriptions are part of the product.** Write them for the model that reads them: what the tool does, when to use it, what it returns, what it will not do.
- **Return pages and quotes, not whole documents.** Label contract text in every result as untrusted data, never as instructions.
- **Log every tool call** as one JSON line: time, user, tool, arguments, result summary, not-checked count, duration. Never log whole documents or secrets.
- **Keep secrets out of the repo.** No credentials, keys or real hostnames in code, tests or fixtures.
- **Option X is the default:** the plug-in makes no LLM calls. If a tool needs to call the Claude API (Option Y), that needs a decision record first, and the "Claude API conventions" below then apply to that call.
- **Mock SAP only for now.** Real adapters stay `TODO(verify)` stubs. Shape the adapter interface so a real route can replace the mock with no change above it.
- **Skills and prompts are guidance, not enforcement.** Anything that must hold goes into tool code and tests.

## Claude API conventions

Apply to any code that calls the API: the Phase 2 orchestrator and pipelines, or a Phase 1 tool under Option Y.

- Use the official `anthropic` Python SDK. No raw HTTP, no OpenAI-compatible shims.
- **Models are configuration, not code.** Read them from settings (`POC_MODEL_ORCHESTRATOR`, `POC_MODEL_EXTRACTION`). The default for both is `claude-opus-5-5`. Change the model only through settings, and only after the eval set shows quality holds.
- Set `output_config.effort` explicitly on every call. On Opus 5.5 the default is `medium`. Don't try to disable thinking: on Opus 5.5 that returns a 400. Lower effort instead.
- **Classify and extract: structured outputs.** Use `client.messages.parse()` with a Pydantic model generated from the slice's JSON schema. Note that the API's built-in citations feature can't be combined with structured outputs. That is why citations are fields in our schema and are verified by our code (rule 7).
- **Phase 2 orchestrator: our own tool-use loop.** Write the loop so that every `tool_use` passes through `foundation/gateway` before it executes. Don't use the API's remote MCP connector there: it would bypass the gateway. The gateway is the MCP client to our servers and offers their tools to Claude as user-defined tools. *(Phase 1 is the opposite: the user's Claude connects to our server directly, and that is by design.)*
- Forced `tool_choice` (`any` / `tool`) returns a 400 on Opus 5.5. Use `auto` plus clear instructions, and `strict: true` on tool schemas.
- Always check `stop_reason` before reading content, and handle `refusal`. Enable server-side fallbacks (`fallbacks: "default"` with beta `server-side-fallback-2026-07-01`).
- Parse tool inputs with `json.loads` and validate them against the schema. Never match on the raw strings.
- Use streaming for long inputs or outputs (whole contracts). Don't use assistant prefill; it isn't supported.
- In Phase 2, every LLM call goes through the gateway, which logs model, prompt version, token usage and cost per run.

## Versioning

Prompts, skills, schemas and rule files carry a version in the filename (`extract.v1.md`, `contract_terms.v1.json`). Once an eval run references a version, don't edit it in place. Create `v2` and re-run the evals.

## Code conventions

- Python 3.12+, type hints throughout, Pydantic models at every boundary (tool inputs and outputs, records, findings).
- `ruff` for lint and format; `pytest` for tests. Keep tests offline: mock the Claude client by default, and put real API calls behind `pytest -m live`.
- Keep slice-specific logic in data (YAML, JSON, Markdown) wherever possible. Slice Python code is the last resort, and it lives in `slices/<slice>/`.
- Keep commits small. Commit messages say which step or milestone the commit serves (e.g. `S3: ...` for Phase 1, `M1: ...` for Phase 2).

## Commands

Phase 1 commands work today (13 Oct 2026). Phase 2 commands are planned only.

```bash
pip install -e ".[dev]"     # install (use the project .venv)
pytest                      # offline tests, including the domain-word test and the read-only test
pytest -m live              # tests that call the Claude API (cost money; ask first). None exist yet
ruff check . && ruff format .     # build/ and .spike/ are excluded in pyproject.toml
python scripts/check.py           # ALL quality gates: run ONCE at the end of a complete change
python scripts/check.py --fast    # lint, format and repo-rule scans only
python scripts/check.py --fix     # apply ruff's safe fixes and formatting, then check
python -m ingenus_plugin.server               # Phase 1: the MCP server on stdio
python -m ingenus_plugin.report               # Phase 1: usage report from the tool-call log
python -m ingenus_plugin.evals page-finder    # Phase 1: page-finder recall on labelled contracts
python data/synthetic/generate_contracts.py   # regenerate the synthetic contracts and their labels
python MCP-PlugIn/packaging/build_bundle.py   # build the desktop extension (build/*.mcpb)
python MCP-PlugIn/packaging/smoke_test_bundle.py   # run the staged bundle without the venv
python -m poc demo chain-x                    # Phase 2: end-to-end demo (planned, from M1)
python -m poc eval contract_to_sap_check      # Phase 2: extraction accuracy (planned, from M2)
```

Gotchas learned in Phase 1:
- The MCP SDK is v2: `from mcp.server import MCPServer`, `from mcp.types import ToolAnnotations`; client objects use snake_case (`input_schema`, `structured_content`).
- A stdio client passes only a few environment variables to the server process. Pass settings explicitly.
- Never print to stdout in server code: on stdio it is the protocol channel. Use stderr.
- Skill descriptions in `SKILL.md` must not contain `: ` (it breaks the YAML header). A test checks this.
- Do not run `ruff --fix` on `build/`; it rewrites third-party files in the bundle.

## Expected demo numbers (Phase 1 S3 acceptance and Phase 2 M1)

The synthetic Chain X scenario must produce exactly these results. If it doesn't, the code is wrong, not the numbers.

| Line | Contract | SAP | Gap / month |
|---|---|---|---|
| Product A rebate | 6% of $200,000 | 4% | $4,000 |
| Product B rebate | 3% of $150,000 | 3% | $0 (match) |
| Product C rebate | 5% of $50,000 | not set up | $2,500 |
| Admin fee | 2.5% of $400,000 | 2% | $2,000 |
| **Total** | | | **$8,500 / month**; indicative exposure 1 Jul–31 Aug = **$17,000** |

## Before you finish a task

- Run `python scripts/check.py` **once**, now that the whole change is finished (not after each edit), and fix every failure until it ends with `0 failed`. It includes `pytest`, the domain-word test and the read-only test.
- Phase 1: confirm no tool was added without a decision record.
- Phase 2 only: if you touched `foundation/` because of a slice need, add the `docs/coupling_log.md` entry.
- Update the status tables in `README.md`.
- Say plainly what you didn't verify, especially anything about real SAP behaviour, the Claude plan's features, or the MCP SDK and desktop-extension format.
