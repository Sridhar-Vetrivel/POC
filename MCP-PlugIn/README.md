# MCP-PlugIn: Phase 1

A read-only MCP server with six business-level tools, a skills pack and a tool-call log. Ingenus's own Claude
calls it to check a customer contract against the rebate and fee setup in SAP. **All data in this repo is
synthetic and SAP is a mock.** Scope, decisions, steps and risks are in [Plan.md](Plan.md). The repo-wide
picture is in the [root README](../README.md), and the rules for people and AI agents are in
[CLAUDE.md](../CLAUDE.md).

## What is built (13 Oct 2026)

| Piece | Where |
|---|---|
| Six tools as plain functions | `src/ingenus_plugin/core/tools.py` (`resolve_customer`, `find_contract_files`, `get_contract_pages`, `get_rebate_setup`, `get_sales_volume`, `compare_contract_to_sap`) |
| Quote check and comparison (no AI) | `core/citations.py`, `core/compare.py` |
| Thin MCP wrapper (stdio) | `src/ingenus_plugin/server/` |
| Tool-call log and usage report | `core/calllog.py`, `report.py` |
| Skills pack (8) and the MCP prompt | `skills/v1/`, `prompts/contract_check.v1.md` |
| Desktop-extension packaging | `packaging/` (`manifest.json`, `build_bundle.py`, `smoke_test_bundle.py`) |
| Tests (offline) | `tests/` here, plus `../tests/test_no_domain_terms.py` |
| Shared with later phases | `../slices/contract_to_sap_check/` (rules, schemas, aliases, golden tests), `../mcp_servers/sap/` (read-only interface and mock adapter). Synthetic data: `data/synthetic/` (inside this folder since 19 Oct 2026) |

**Not verified:** installing the extension in Claude Desktop, any real SAP route, Ingenus's Claude plan, and
whether laptops have a matching Python. See [docs/S0_spike_results.md](docs/S0_spike_results.md).

## Run it

From the repo root (`POC/`), with the virtual environment active:

```bash
pip install -e ".[dev]"
pytest                                          # 80 offline tests
python -m ingenus_plugin.server                 # the MCP server on stdio (an MCP client talks to it)
python -m ingenus_plugin.report                 # usage report from the tool-call log
python -m ingenus_plugin.evals page-finder      # page-finder recall on the labelled contracts
python MCP-PlugIn/data/synthetic/generate_contracts.py     # regenerate the synthetic contracts and labels
python MCP-PlugIn/tools/write_schema.py         # rewrite the extraction schema (only if the model changed)
```

Settings come from environment variables (defaults point at the synthetic data): `INGENUS_CONTRACTS_DIR`,
`INGENUS_SAP_ADAPTER` (`mock`), `INGENUS_SAP_MOCK_FILE`, `INGENUS_SLICE_DIR`, `INGENUS_PROMPTS_DIR`,
`INGENUS_LOG_PATH`, `INGENUS_USER` (overrides the user name in the log).

## Try it in Claude Desktop (not yet done by us)

```bash
python MCP-PlugIn/packaging/build_bundle.py        # builds MCP-PlugIn/build/ingenus-contract-check.mcpb (24 MB)
python MCP-PlugIn/packaging/smoke_test_bundle.py   # proves the staged bundle runs without the venv
```

Then, in Claude Desktop: Settings > Extensions > Advanced settings > Extension Developer > Install Extension, pick
the `.mcpb` file, choose `MCP-PlugIn/build/sample_contracts` as the contract folder and any folder for the log. The laptop needs
Python 3.13 on PATH (the bundle's libraries are built for it). An Owner may need to allow extensions on a Team plan.
Then run the questions in
`../slices/contract_to_sap_check/evals/golden/golden_questions.v1.md` and record the results.

## The demo in one line

Chain X Amendment 2 (back-dated to 1 July 2026) against the mock SAP gives **3 lines that differ and 1 match, a
monthly gap of 8,500.00 and an indicative exposure of 17,000.00 for 1 July to 31 August**. Every number comes from
`compare_contract_to_sap`; Claude only supplies the extracted terms, each with an exact quote that code checks.

## Known limits (honest list)

- **Page finder is keyword search.** On 29 labelled synthetic contracts it found every term page when the wording was
  on its keyword list, and missed 2 of 5 documents that used unlisted wording ("retrospective discount"). Overall
  recall 0.92. It was not tuned to hide this. Real contracts may use other wording; public samples are not added yet.
- **The quote check proves the quote is on the page, holds the rate and names the product. It does not prove it is
  the right clause.** A person must confirm.
- **Spelled-out rates** ("six percent") are not recognised, so such terms land in "not checked".
- **Scanned pages are not read** (no OCR in phase 1); they are reported.
- **Only text PDFs and `.txt` files.** Other formats are listed as not checked.
- **The SAP rate as at the as_of date is assumed for the whole period.**
- **The log is per machine** unless the log folder is a shared location Ingenus agrees to.
- **No review queue, no recorded decision, no watcher, no audit of Claude's answer.** That is phase 1 by design.
