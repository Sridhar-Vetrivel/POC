# 0001: Phase 1 starts with the proposed approaches as v0

**Date:** 13 Oct 2026 · **Status:** accepted for v0 (by the repo owner), revisit as noted · **Phase:** 1 (MCP plug-in)

The decisions D1 to D7 in `MCP-PlugIn/Plan.md` section 3 each had a proposed approach and an alternative. The
repo owner decided to **build the proposed approaches as v0 and move to the alternatives later if needed**.
Nothing here is confirmed with Ingenus; Aditya and Ingenus can still change any of it.

| # | Decision | v0 (built now) | Alternative (later, if needed) | Revisit when |
|---|---|---|---|---|
| D1 | How Claude reaches the server | Desktop extension per user (local, stdio) | Remote connector (needs Dan's firewall change; Anthropic's docs say Claude calls it from its cloud) | A user needs web or mobile access, or the desktop route fails on Ingenus's setup |
| D2 | Who extracts contract terms | **Option X:** Claude on the user's own plan; our code checks every quote | Option Y: our own LLM inside a tool (needs a provider approval) | S5 shows extraction errors that differ by person, or audit or validation of the reading is required |
| D3 | SAP access route | Mock adapter with synthetic data | Real route agreed with Dan (report export, API or CDS views; unknown) | Dan answers the access questions |
| D4 | Data used | Synthetic and public only | Anonymised real contracts | Data policy received and signed off |
| D5 | Scope | Contract-to-SAP only | Add order-status or packing-slip lookups | After S4, if Aditya agrees |
| D6 | Domain-neutral rule for `MCP-PlugIn/` | Exception for phase 1 (the domain-word test skips `MCP-PlugIn/` only) | Keep the rule and move tool code into the foundation | Phase 2 starts |
| D7 | Where the tool-call log goes | A configured folder (`INGENUS_LOG_PATH` / the extension's log folder setting) | Each laptop keeps its own log | Ingenus agrees a shared location; until then usage data is split per machine |

## What this means in code

- Option X: no code in this repo calls the Claude API. `compare_contract_to_sap` takes the terms Claude extracted and
  checks each quote against the page. If we move to Option Y, add an `extract_terms` function that produces the same
  `ExtractedTerm` list, behind a decision record.
- The SAP adapter interface has one `read` method. The mock adapter is the only one wired; `real_stub.py` refuses to run.
- The log path comes from settings, so changing D7 needs no code change.
