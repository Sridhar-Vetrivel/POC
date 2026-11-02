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
| Last 10 tool calls and logins (PowerShell). A `login` line with no `tool_call` after it means the chat connected but Claude used no tool | `Get-Content C:\Users\sridhar.vetrivel\INGENUS\POC\MCP-Server\data\runtime\tool_calls.jsonl -Tail 10` |

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

## Is Postgres on? (PowerShell)

| Check | Command | On means |
|---|---|---|
| Windows service | `Get-Service -Name "postgresql*"` | `Status` is `Running`. The name is likely `postgresql-x64-18` **(verify)** |
| Port open | `Test-NetConnection localhost -Port 5432` | `TcpTestSucceeded : True` |
| Ready check | `& "C:\Program Files\PostgreSQL\18\bin\pg_isready.exe" -h localhost -p 5432` | `accepting connections` (path **verify**) |
| Login works | `& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -h localhost -U ingenus_server -d ingenus_audit -c "SELECT 1"` | Asks for the password, then returns `1` (path **verify**) |
| pgAdmin | Servers, right-click the server, Connect | The tree opens. A password prompt means it is running |

Is the **MCP server using it**? Look at `MCP-Server\.env`: `INGENUS_PG_HOST` must be present and not commented out (`#`). Then ask one question in Claude Desktop and run `SELECT count(*) FROM events;` in pgAdmin twice: the number should go up. If it does not, the server is writing to local files instead.

If Postgres is off while `INGENUS_PG_HOST` is set, the check history and stored terms cannot be saved; the contract check itself should still answer **(verify: not tested with Postgres stopped)**. Start it with `Start-Service <name from the first row>` (needs admin rights, which your laptop may not give; ask IT).

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

## Postgres with pgvector (dev, user-level, in WSL; no admin rights)

**Since 2 Nov 2026 the server uses this one database for everything** (audit, history, terms, later search; `INGENUS_PG_PORT=5433`, no password, decision 0012). The Windows Postgres sections above (port 5432) now describe IT's install, which the server no longer uses. If this one is stopped, start it first.

IT's Windows Postgres 18 has no `pgvector`, and installing into it needs admin. So a second Postgres 18.6 runs in WSL Ubuntu from a home folder (official PostgreSQL apt packages, `postgresql-18-pgvector` 0.8.7, sha256-checked), on **port 5433**, localhost only, no password (dev, synthetic data only). Windows can reach it at `localhost:5433`.

| What | Command (PowerShell) |
|---|---|
| Start | `wsl -d Ubuntu -- bash -c 'export LD_LIBRARY_PATH=$HOME/pg18/usr/lib/x86_64-linux-gnu; $HOME/pg18/usr/lib/postgresql/18/bin/pg_ctl -D $HOME/pgdata -o \"-p 5433 -c listen_addresses=localhost -k /tmp\" -l $HOME/pgdata.log start'` (the `\"` matters: PowerShell drops plain inner quotes and `pg_ctl` then says "no operation specified") |
| Is it already running? | same, with `status` and without the `-o ...` and `-l ...` part. If `start` says "another server might be running" and then fails, it is already up |
| Stop | same as Start, with `stop` instead of `start` |
| Check | `Test-NetConnection localhost -Port 5433` |
| Check the extension | `psql -h localhost -p 5433 -U postgres -c "select extversion from pg_extension where extname='vector'"` (needs the WSL `psql` at `~/pg18/usr/lib/postgresql/18/bin/psql`) |

Production Postgres version, OS and `pgvector` availability are **unknown** (ask Aditya).

## Meaning search (decision 0013; needs the Postgres with pgvector above)

Choose the model with one word in `MCP-Server\.env`: `INGENUS_EMBED_MODEL=nomic`, `bge` or `minilm` (or the full name). Unset or `off` means keyword search only. Synthetic data only until the AI admin answers (decision 0013).

| Short name | Model | Size, numbers | Ranking on our test (MRR) | Cut-off |
|---|---|---|---|---|
| `nomic` (chosen) | nomic-ai/nomic-embed-text-v1.5-Q | 134 MB, 768 | **0.97** | 0.55 |
| `bge` | BAAI/bge-small-en-v1.5 | 65 MB, 384 | 0.92 | 0.55 |
| `minilm` | sentence-transformers/all-MiniLM-L6-v2 | 88 MB, 384 | 0.84 | 0.30 |

| What | Command (repo root, PowerShell) |
|---|---|
| Install the runtime once | `.venv\Scripts\python.exe -m pip install fastembed` |
| **Use nomic** (set, then download once) | `(Get-Content MCP-Server\.env) -replace '^#?\s*INGENUS_EMBED_MODEL=.*','INGENUS_EMBED_MODEL=nomic' \| Set-Content MCP-Server\.env -Encoding ascii; .venv\Scripts\python.exe -m ingenus_mcp.embeddings fetch` |
| **Use bge** | same, with `INGENUS_EMBED_MODEL=bge` |
| **Use minilm** | same, with `INGENUS_EMBED_MODEL=minilm` |
| **Turn it off** (keyword search stays) | same, with `INGENUS_EMBED_MODEL=off` (and no `fetch`) |
| What is set, and does it load | `.venv\Scripts\python.exe -m ingenus_mcp.embeddings status` |
| After any change | restart the server. The next search embeds the passages again with the new model and drops the old model's vectors |
| Look at the vectors | `SELECT model, count(*) FROM passage_vec GROUP BY 1;` (pgAdmin or psql on port 5433) |

`fetch` downloads only the model named in `.env` (the only time anything is downloaded; the server never does). If the line is not in `.env` yet, add `INGENUS_EMBED_MODEL=nomic` by hand first: the replace above only changes an existing line.

## Switches in `MCP-Server\.env` (git-ignored; first definition wins)

| Setting | Meaning |
|---|---|
| `INGENUS_SOURCES=sharepoint,onedrive,network` | Search all three sources; the server picks per question. Leave `INGENUS_DOC_SOURCE` unset |
| `INGENUS_SOURCES_TIMEOUT=45` | Seconds to wait for one source before reporting it as failed |
| `INGENUS_RECORDS_DB` | Unset: Postgres when `INGENUS_PG_HOST` is set, else a local file. `off`: keep no terms |
| `INGENUS_EMBED_MODEL` | `nomic`, `bge` or `minilm` (or the full name): meaning search on (download the model first). Unset or `off`: keyword search only. `INGENUS_EMBED_MIN_SIM` changes the similarity cut-off (default 0.55) |
| `INGENUS_PG_HOST` | Present: Postgres for audit, check history and stored terms. Comment out to fall back to local files |
| `INGENUS_GUIDANCE_DIR` | Pin a guidance version, for example `...\guidance\v4`. Default is `v7` |

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
