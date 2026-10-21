# 0008: v1 keeps the audit store and the check history in Postgres

**Date:** 21 Oct 2026 · **Status:** built and tested against a local Postgres 17; not yet on the VM or at Ingenus · **Phase:** 1, v1 (`MCP-Server/`)

## Context

Decisions 0005 and 0006 built the audit store and the check history on SQLite files as a reference. Aditya suggested a
custom database for the real store (**SAID**, relayed by Sridhar, 21 Oct 2026). Sridhar chose **Postgres** (**SAID**).

## Decision

1. **One setting turns it on:** `INGENUS_PG_HOST`. With it, the audit store and the check history both go to the same Postgres
   database (`INGENUS_PG_DB`, default `ingenus_audit`; schema `INGENUS_PG_SCHEMA`, default `public`). An explicit
   `INGENUS_AUDIT_STORE` or `INGENUS_HISTORY_DB` still wins. With no host set, nothing changes: SQLite files as before.
2. **The password is never a setting.** It is read from a file (`INGENUS_PG_PASSWORD_FILE`, kept under the git-ignored
   `MCP-Server/secrets/`) when a connection opens, and is never printed or logged.
3. **One storage layer** (`core/db.py`) lets both stores write their SQL once, with named placeholders; SQLite and Postgres run
   the same text. Only the schema text and the insertion-order column differ.
4. **The local JSONL log stays the source of truth.** A Postgres that is down never fails a tool call: the event stays in the
   log and `python -m ingenus_mcp.audit ship` catches the store up. Check records are best effort, as before.
5. **Retention:** `python -m ingenus_mcp.audit prune [--days N]` deletes events and check records older than N days
   (default `INGENUS_RETENTION_DAYS`, 365) from the database. It is a command to schedule, not a built-in timer. It does not
   touch the local log, so the hash chain stays whole; note that `ship` would copy pruned events back from the log.

## Assumed, to be confirmed by Ingenus (not facts)

- Keep the audit log and the check history **12 months**.
- The audit database is read by **admins only** (Sridhar, Aditya).
- The history shows other people's names.
- Where it runs: local for the POC, Psiog Azure once the VM exists (**SAID** by Sridhar), then Ingenus on-prem or Azure by a
  later decision.

## Not built or not verified

- Nothing creates or limits Postgres roles: the POC uses the `postgres` user. A real deployment needs a write-only user for the
  server and a read-only user for reviewers (**UNKNOWN** what Ingenus's DBAs require).
- No TLS to the database (it is on the same machine). A remote database needs `sslmode`, not yet configured.
- Pruning the local log, and a timer for `prune`, are not built.
- Not tested: two server processes writing together, a long outage and catch-up of many events, Postgres versions other than 17.
