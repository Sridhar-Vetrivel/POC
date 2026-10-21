# 0005: v1 audit and login log: hash chain, one event stream, a pluggable central store

**Date:** 21 Oct 2026 · **Status:** proposed design, built as a reference; **the choice of the real central store is not made** · **Phase:** 1, v1 (`MCP-Server/`)

## Context

Today the tool-call log is a JSONL file on the machine that runs the server. It is not central, not searchable across
machines, and an edit to it would go unseen. Aditya wants an audit log and a login log with a central store. What
Ingenus will accept is unknown: Ingenus leaned towards on-prem on 8 Oct 2026 (**SAID**), and whether rules such as
21 CFR Part 11 apply is **UNKNOWN**; neither is assumed here.

## Decision

1. **One event stream, two kinds of event.** `tool_call` (as before) and `login` (a token accepted or refused). Every
   event has `event`, `event_id`, `ts` (UTC), `user` (sign-in name), `user_id` (oid) and, for logins, `outcome` and a
   `reason` class. Never page text, tokens or whole documents. A login is logged **once per accepted token**, and refused
   logins at most once per reason per 10 seconds, so a flood of bad tokens cannot flood the log. A request with no token
   at all is a 401 before our code sees it and is not logged.
2. **The local JSONL file stays the source of truth and the buffer.** Every event is written there first. A store that is
   down loses nothing: `python -m ingenus_mcp.audit ship` copies the missing events later (events are unique by id, so
   copying twice is harmless).
3. **A hash chain** (`calllog.py`): each event carries `prev_hash` and `hash` (SHA-256 over the event, without its own
   hash). `python -m ingenus_mcp.audit verify` finds an edited, removed, reordered or cut-off line. **Limit:** lines
   removed from the very END cannot be seen (nothing later points back at them); keep a copy of the last hash somewhere
   else. One server process per log: a second writer would fork the chain. Logs from before the chain are tolerated.
4. **A central store behind a tiny interface** (`core/auditstore.py`): `add`, `emit`, `ship`, `query`. The reference
   implementation is SQLite (`INGENUS_AUDIT_STORE=<path>`). It proves the schema, the copying and the queries; it is
   **not** the central store (one file on one machine). Forwarding to a database, Azure Monitor Logs or Ingenus's own log
   system means one more implementation of the same few functions.
5. **Writes stay confined.** The read-only guard test now names the modules allowed to write files: `calllog.py`,
   `auditstore.py` and `history.py` (decision 0006), all under the configured data location (CLAUDE.md rule 5). Nothing
   else may.

## Still to decide (people, not code)

- Which store, and where (Psiog Azure or Ingenus on-prem); retention; who may read the audit log.
- If the store is down: keep serving and ship later (built) or stop serving (a regulated setting might require it).
- Whether Entra's own sign-in log (authoritative for MFA outcome; retention depends on the licence, **UNKNOWN**) is
  correlated or copied.

## Consequences

- 31 offline tests cover the chain (edit, delete, reorder, cut line, restart, legacy lines), the store (two people, the
  same event and hash, a store that is down, shipping twice), and login events (once per token, refused with a reason,
  rate-limited, no token in the log).
- `report.py` now ignores login events and prints how many were accepted and refused.
- **Not verified:** behaviour with two server processes on one log; log growth and rotation; SQLite under heavy
  concurrent writes (fine for the POC's volume).
