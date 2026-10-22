# Handover: continuing on the new laptop

**Written 22 Oct 2026.** For Sridhar and for the first Claude Code session on the new laptop. It holds no secrets and no IDs: those stay in `MCP-Server/.env` and `MCP-Server/secrets/`, which are not in git. The state of the work is in [`v1_open_items_checklist.md`](v1_open_items_checklist.md) and the decision records in [`decisions/`](decisions/); this note only says how to pick it up.

## 1. Set up the new laptop

1. Install Python 3.13, Git, Node (only if you rebuild the bridge) and Claude Code; sign in to the same Claude account.
2. `git clone` the repo, then in `POC/`: create `.venv`, `pip install -e ".[dev]"`. Run `python scripts/check.py`: it should end `13 passed, 0 failed`.
3. Copy from the old laptop, over a safe channel (not email or chat):
   - `MCP-Server/.env` and the whole `MCP-Server/secrets/` folder. `server_key.pem` is the private key of the certificate on the server app in the dev tenant: without it the Entra sign-in cannot work. (If you would rather not copy it, make a new key and upload its `.cer` to the app: [`developer_guide.md`](../developer_guide.md) section 5.1.)
   - The `INGENUS/` folder's files that are outside `POC/` (pre-sales notes). They are not in git.
4. Postgres: install it the normal way (the app installer, port 5432), create the database `ingenus_audit`, put the password in `MCP-Server/secrets/pg_password.txt`, and set `INGENUS_PG_HOST`, `INGENUS_PG_PORT`, `INGENUS_PG_PASSWORD_FILE` in `.env` ([`.env.example`](../MCP-Server/.env.example)). Without `INGENUS_PG_HOST` the server uses SQLite files and still works.
5. Claude Desktop: reinstall the bridge as an unpacked extension (`MCP-Server/bridge`; steps are in [`MCP-Server/README.md`](../MCP-Server/README.md)), enter the server URL and the three IDs, and sign in again. The old sign-in cache does not move.

## 2. Resume the Claude Code session

The session files are in `claude_sessions_backup_2026-10-22.zip` (made on the old laptop). Unzip them into `C:\Users\<user>\.claude\projects\<folder>\`, where `<folder>` is the working directory path with `:` and `\` replaced by `-` (for `C:\Users\sridhar.vetrivel\INGENUS` it was `c--Users-sridhar-vetrivel-INGENUS`). If the path differs on the new laptop, rename the folder to match. Then open Claude Code in `INGENUS/` and use `/resume`. The `memory/` folder inside it holds the notes Claude loads each session.

The big session file is about 126 MB. If resuming is slow, start a fresh session instead; the memory notes plus this repo carry the context.

## 3. Where things stood (22 Oct 2026)

- **Built and tested offline (221 v1 tests):** server sign-in and SharePoint reading (live-verified in Claude Desktop), OneDrive and network-share sources, audit and login log with hash chain (several processes safe), shared check history (`get_check_history`), Postgres store, three source datasets with one shared ontology and mock SAP.
- **Not verified live:** OneDrive, a real network share, two real people on one server, Claude calling `get_check_history` unprompted.
- **Order locked by Sridhar:** build and test everything locally first, host last. The POC VM is on AWS, provisioned by Aditya, for the POC only, to QA multi-user calls and logging (decision 0009). Ingenus's own hosting may be Azure or on-prem: later.
- **Your next steps:** copy `Sharepoint/*`, `Onedrive/*` and `Network-Drive/*` from `MCP-PlugIn/data/synthetic/` to the matching real locations; then ask Claude to set the folder settings and run the live check per source (expected figures are in the checklist, section 2.0).
- **Waiting on people:** Ingenus confirms retention (12 months assumed), readers (admins only assumed) and the data policy; Aditya gives the AWS details (account, OS, DNS name, HTTPS).

## 4. Standing instructions (also in Claude's memory)

- You are Psiog pre-sales on Ingenus; Aditya is the boss. Keep **SAID** (with timestamps), **ASSUMED** and **UNKNOWN** apart; never write an assumption as fact.
- SAP is read-only; synthetic or public data only; never invent SAP tables or T-codes.
- Keep it cheap. Do not publish or contact anyone beyond what is asked. Use they/them for unstated pronouns.
- Commits: **no `Co-Authored-By` line.** Run `scripts/check.py` only at the end of one complete change.
- Client laptops have only Claude Desktop, connected to our MCP server. v1 is built for Claude Desktop, not Claude Code.

## 5. Dates to remember

- The server certificate expires on **18 Apr 2027** (rotate it: new pair, upload the new `.cer`, update the thumbprint).
- The dev tenant's lifetime is **UNKNOWN**: check its expiry in the developer programme.
- `pip-audit` finds new advisories now and then; fix by upgrading the package in the venv, not by suppressing.
