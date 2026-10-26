# Command cheat sheet (MCP-Server, POC)

Run from the repo root `C:\Users\sridhar.vetrivel\INGENUS\POC` unless a line says otherwise. Commands are for the dev laptop and synthetic data. Anything marked **(verify)** was not run while writing this sheet.

## Run the server

| What | Command |
|---|---|
| Start (HTTP, 127.0.0.1:8765, path `/mcp`) | `python -m ingenus_mcp.server` |
| Start for local tools (stdio) | `python -m ingenus_mcp.server --transport stdio` |
| Stop | `Ctrl+C`, then start again after any `.env` or code change (guidance files are read fresh, no restart needed) |
| Live sign-in check (server running in another terminal) | `python MCP-Server\scripts\signin_check.py` |
| Tool-call report from the log | `python -m ingenus_mcp.report --log MCP-Server\data\runtime\tool_calls.jsonl` |

## Tests and checks

The repo's virtual environment is `.venv`; the system Python has no pytest.

| What | Command |
|---|---|
| Full test suite | `.venv\Scripts\python.exe -m pytest MCP-Server\tests -q` |
| One test file | `.venv\Scripts\python.exe -m pytest MCP-Server\tests\test_v1_records.py -q` |
| Format | `.venv\Scripts\python.exe -m ruff format MCP-Server` |
| Lint | `.venv\Scripts\python.exe -m ruff check MCP-Server` |
| All gates (10) | `python scripts\check.py --fast` |

## Audit, history and stored terms

| What | Command |
|---|---|
| Is the log's hash chain intact | `python -m ingenus_mcp.audit verify` |
| Copy log events to the central store (safe to repeat) | `python -m ingenus_mcp.audit ship` |
| Look up events | `python -m ingenus_mcp.audit query --user NAME --tool compare_contract_to_sap --since 2026-10-23 --limit 20` |
| Delete events, check records and stored terms older than N days | `python -m ingenus_mcp.audit prune --days 90` |

Stored terms are kept 90 days from last use (decision 0011). `prune` uses one number for all three stores.

## Postgres (pgAdmin Query Tool, database `ingenus_audit`, role `ingenus_server`)

Read-only looks. Column names come from the tables; `SELECT *` is safest.

```sql
-- stored contract terms (records)
SELECT customer_id, kind, product, rate_pct, document_id, page, status, verified_by, last_used
FROM term ORDER BY customer_id, document_id, page;

-- how many terms per status
SELECT status, count(*) FROM term GROUP BY status;

-- latest tool calls and checks
SELECT * FROM events ORDER BY 1 DESC LIMIT 20;
SELECT * FROM checks ORDER BY 1 DESC LIMIT 10;
SELECT * FROM check_docs LIMIT 20;
```

If the tables are not found, the server may use a schema other than `public` (`INGENUS_PG_SCHEMA`): put it in front of the table name **(verify)**. The password is in `MCP-Server\secrets\pg_password.txt` (git-ignored; never paste it into chat or commit it).

## Switches in `MCP-Server\.env` (git-ignored; first definition wins)

| Setting | Meaning |
|---|---|
| `INGENUS_SOURCES=sharepoint,onedrive,network` | Search all three sources; the server picks per question. Leave `INGENUS_DOC_SOURCE` unset |
| `INGENUS_SOURCES_TIMEOUT=45` | Seconds to wait for one source before reporting it as failed |
| `INGENUS_RECORDS_DB` | Unset: Postgres when `INGENUS_PG_HOST` is set, else a local file. `off`: keep no terms |
| `INGENUS_PG_HOST` | Present: Postgres for audit, check history and stored terms. Comment out to fall back to local files |
| `INGENUS_GUIDANCE_DIR` | Pin a guidance version, for example `...\guidance\v4`. Default is `v5` |

## Git

| What | Command |
|---|---|
| Where am I | `git status -sb` and `git log --oneline -8` |
| Branches | `main` (no multi-source or stored terms yet), `feature/multi-source-routing`, `feature/records-store` (has both) |
| Switch | `git checkout feature/records-store` |
| Push the current branch | `git push` |
| Pull request to main (merge multi-source first, then records) | `gh pr create --base main --head feature/multi-source-routing` |

## Live QA in Claude Desktop

1. `git checkout feature/records-store`, restart the server.
2. Open a **new chat** for every question.
3. Questions and expected answers: `docs\demo_guide.md` section 8b (sources) and 8c (stored terms, SR-1 to SR-6).
4. Paste the chat and the last lines of `MCP-Server\data\runtime\tool_calls.jsonl` back to Claude to record the result.

## Test customers (synthetic)

| Chain | Source | Chain | Source |
|---|---|---|---|
| A, B | SharePoint | C, D | OneDrive |
| E, F | Network folder | X | Local synthetic set only (no files in the three QA sources) |

## Rules to keep

- SAP is read-only (GxP). No tool writes to SAP.
- Use `document_id` exactly as returned (source name before the colon).
- Stored terms are verified by code, not reviewed by a person. Never call them confirmed.
