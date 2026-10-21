# 0006: v1 keeps a record of each check and shares it through an eighth tool, `get_check_history`

**Date:** 21 Oct 2026 · **Status:** proposed, built as the smallest useful version; **what Aditya means by "memory" is not confirmed** · **Phase:** 1, v1 (`MCP-Server/`)

## Context

Aditya asked for a shared "per-process memory": Sridhar checks a file on Day 1, Aditya on Day 3, and a third person
should see what they found. What the server can and cannot do:

- It **cannot** share anyone's Claude conversation: chats live in each person's Claude account and never reach the
  server, which sees only tool calls.
- It **can** keep what passed through it: who checked what, when, the figures and where they came from.

CLAUDE.md says a tool is added only through a decision record, and that more tools make Claude choose worse.

## Decision

1. **A check record per `compare_contract_to_sap` run** (`core/history.py`, SQLite at `INGENUS_HISTORY_DB`, default
   `MCP-Server/data/runtime/history.sqlite`, `off` switches it off): who, when, customer, as-of date, each line (kind,
   product, contract rate, SAP rate, status, monthly gap, file and page), the totals, the not-checked count, a one-line
   summary, and the **version (eTag or mtime and size) of each file** the check relied on.
2. **Not stored:** page text, the quotes, tokens, and anything a person said to Claude (the server never receives it).
   Contract-derived figures (rates, gaps) are stored, which is a data-policy question for Ingenus (**UNKNOWN**); only
   synthetic data is used today.
3. **One new read-only tool, `get_check_history(document_id | customer_id, limit)`** (the eighth tool). It returns records
   newest first, each with `changed_since` per file (the file's version now differs from the one checked), and a note that
   these are figures an earlier check produced, not new findings.
4. **Access rule:** a record is shown only if the asking person can open **every** file it used, tested with their own
   access (a stat through the same source, so SharePoint applies the person's own rights). A record that is not shown is
   only counted (`hidden_count`); nothing about the file leaks. Asking by a file the person cannot open returns no records.
5. **The compare tool leaves the record** and a failure to save it never fails the check. The tool stays read-only toward
   SAP and the source files; it writes only to our own store, a location rule 5 allows. `history.py` is added to the
   modules the read-only guard test lets write.
6. The server instructions tell Claude the tool exists. The `v2` guides were **not** changed (versioned files are not
   edited in place); a `v3` playbook line "read the history first" is a later step.

## Not decided or not built

- **Notes and decisions** people add ("accepted this gap") would need a write tool, which the registry forbids today:
  a separate, larger decision.
- Whether Claude reliably calls the tool when it should: not measured (only the instructions and the tool description steer it).
- Showing other people's names is on by default; whether that is acceptable for Ingenus is **UNKNOWN**.

## Consequences

- 11 offline tests: a second person sees the first person's check; "is you" marking; newest first and the limit; no quotes
  or tokens in the store; a person who cannot open the file sees nothing and learns nothing; a changed file is flagged;
  history off; a store that cannot be written does not fail the check.
- Not verified yet: Claude Desktop with two real people. Needs the VM or a second sign-in on one server (checklist 2.3).
