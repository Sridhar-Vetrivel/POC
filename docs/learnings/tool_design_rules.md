# Tool design rules: coarse and fine tools, and how Claude chains them

**Status (10 Nov 2026):** a design note from a discussion on how the server orchestrates across sources. **Not** a decision record and **not** reviewed by Ingenus. The tool groups in section 1 describe the code as built; the rules in section 2 are our recommendation for new tools. Related: decision [0010](../decisions/0010-v1-several-contract-sources-at-once.md) (several sources at once).

## 1. How the ten tools group today

Code does what must be exact and complete. Claude decides which tool to call next and reads pages to extract terms.

| Group | Tools | What the server does | What Claude does |
|---|---|---|---|
| **Fans out across sources** | `find_contract_files`, `get_contract_terms` | Builds one reader per switched-on source, lists them in parallel (time limit per source), records each source as ok or failed, matches files to the customer, merges duplicates, flags conflicts, leaves drafts out, returns a `complete` flag and a "not checked" entry per failed source. No AI, fixed sequence | Passes the customer name |
| **Reads one thing** | `get_contract_pages`, `get_rebate_setup`, `get_sales_volume`, `resolve_customer`, `get_check_history` | Reads one document or one system. A document id such as `sharepoint:Chain_A/...` carries its source as a prefix (`split_document_id` in `core/sources.py`), so the server routes it, not Claude | Chooses the document or customer from earlier results |
| **Computes or looks up our own records** | `compare_contract_to_sap`, `search_contracts`, `get_guide` | `compare` checks each quote against its page and totals the gap in code. `search_contracts` queries our stored passages and checks access per file. `get_guide` serves the guidance text | Sends the extracted terms; reads the result |

Example, "Check Chain A against SAP as of 31 Aug 2026": `resolve_customer` (one lookup) → `get_contract_terms` (fans out) → `get_contract_pages` (one source, routed by prefix) → `get_rebate_setup` (SAP) → `compare_contract_to_sap` (computes).

Not a clean two-way split: `get_contract_terms` is a fan-out listing plus a stored-terms lookup, and `compare` is a computation, not a fetch.

## 2. Rules for adding a tool (coarse or fine)

A fine-grained tool, for example "last payment this customer made for this contract, from AR", is fine to add. It is easier to test (one source, one right answer), easier to audit and permission (the log says exactly what was read), and it leaves Claude fewer wrong turns. Conditions:

1. **One question per tool.** If a tool grows several optional filters, Claude picks badly. Add a second tool instead.
2. **"Not available" is never an empty result.** "AR could not be read" must look different from "no payments". Sources already do this ("not found", "refused", "down"), and it is what stops a wrong "no contract" answer.
3. **Read-only, one owner.** A tool reads from one named system, returns where and when the answer came from, and never changes anything. The read-only test (`test_v1_readonly.py`) holds this for the writer modules.
4. **Watch the number of tools.** Each tool's description sits in Claude's context. We have ten. Choosing between similar tools gets harder somewhere around 20 to 30 (an estimate, not measured here). Use clear names and group by area (contract, SAP, AR).
5. **Fan out in code, never in Claude.** If an answer needs several sources, one tool does the listing, with a per-source status. Do not ask Claude to call three tools and merge the results.
6. **Log it and name the person.** Like every tool, a new one writes an audit event (who, when, tool, outcome) and never page text.

## 3. Open

- **Real AR is not available to us:** SAP is a mock adapter. A "last payment from AR" tool would be designed now but not built until the real system and who may read it are known. **Unknown.**
- The 20 to 30 tool limit is an estimate. Measure it if we get near it.
