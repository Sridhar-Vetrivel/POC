# MCP-Server (v1)

One read-only MCP server for the Contract-to-SAP check, reached over HTTP. **Built primarily for Claude
Desktop**, which reaches it through a thin bridge on the laptop (V1-5); Claude Code is a second client. Tools are discovered from a folder; guidance (skills) is served by
the server too. v0, the desktop-extension plug-in, stays frozen in [`../MCP-PlugIn/`](../MCP-PlugIn/) (git tag `v0`).

The design, decisions and plan are in [`../docs/v1_impact_analysis_and_proposal.md`](../docs/v1_impact_analysis_and_proposal.md).
Nothing here uses Ingenus data: contracts and SAP are synthetic.

## Status

| Step | Content | Status |
|---|---|---|
| V1-0 | Move v0's `build/` and `data/` into `MCP-PlugIn/` | Done 19 Oct 2026 (old `POC/build/` to delete after the Desktop reinstall) |
| V1-1 | [`mock_sap.md`](../MCP-PlugIn/docs/mock_sap.md) | Done |
| V1-2 | This skeleton: core copied from v0, one module per tool, HTTP server, Claude Code demo folder | **Built and tested offline** (HTTP end-to-end test gives 8,500.00 / 17,000.00). and tried from Claude Desktop (see V1-5 and the demo guide) |
| V1-5 | **Claude Desktop bridge** (primary client): Node-only extension, forwards to the server | **Installed in Claude Desktop 19 Oct 2026; Chat connects.** Desktop ran it with its **built-in Node** (its log says so), so the laptop needs no Node or Python. Cowork and Code sessions failed ("Session not found"): their probe sends a request before any handshake, which a stateful server rejects. Fixed by making the server stateless by default (`INGENUS_MCP_STATELESS`). **Retested 19 Oct 2026: no start errors; the Chain X question in Chat gave 8,500.00 a month and 17,000.00 exposure** through bridge and server. Install route: **only "Install unpacked extension" worked**; the packed `.mcpb` again left Install disabled, although the bridge has no Python requirement, so that was not the cause (cause still unknown) |
| V1-3 | Guidance served by the server: skills in `guidance/v8/` (`v2` to `v7` are kept: the earlier demo results refer to them), read through the `get_guide` tool (decision 0003); read fresh on every call, so a guide added on the server needs no restart | **Built, tested offline and tried in Claude Desktop** (`get_guide` is called first; see `docs/demo_guide.md`, section 8) |
| V1-4 | Server sign-in (Entra token check on every request), bridge sign-in (browser, then silent), per-user log (decision 0004) | **Built; verified live in the dev tenant and in Claude Desktop (20 Oct 2026):** the log names the signed-in person. **Not done:** moving to the AWS VM the Principal Architect provisions (decision 0009), HTTPS from another machine (the central store is Postgres, see Audit) |
| V1-6 | SharePoint through Microsoft Graph, read as the signed-in user (on-behalf-of, certificate, per-user cache, scope guard) | **Built; verified live (20 Oct 2026):** Chain X gives 8,500.00 / 17,000.00 from the 30 synthetic PDFs in the dev tenant's `mcp-sharepoint-test` site. The first call took 14.5 s (cold), later ones 12 to 69 ms |
| V1-7 | OneDrive (same Graph code, the signed-in user's own drive), decision 0007 | **Built; verified live (23 Oct 2026, demo guide 8b):** Chains C and D from the signed-in user's own OneDrive gave the expected figures (Chain C 750.00 / 3,750.00), alone and with the other sources |
| V1-8 | Network drive (UNC or mounted share, read-only, links never followed), decision 0007 | **Built; verified live on a folder path (23 Oct 2026, demo guide 8b):** Chains E and F (Chain E 1,100.00 / 8,800.00), and a missing share is reported as not complete. Also tested offline with real junctions and locked files. **A real Windows (UNC) share and a read-only service account are not tested** (they wait for IT) |
| Audit | Audit log and login log: hash chain, login events, a central store (SQLite or Postgres), `python -m ingenus_mcp.audit` (decisions 0005, 0008) | **Built; runs on Postgres.** Since 2 Nov 2026 on a user-level Postgres 18.6 with pgvector in WSL on the laptop: one database for audit, check history, stored terms and search. **Not done:** the production database (version, OS and pgvector availability are unknown), retention and readers are still assumed, Ingenus to confirm |
| History | Check records and the `get_check_history` tool (the eighth tool; decision 0006) | **Built and tested offline and on Postgres;** live checks write the records. Not tried with two real people; what the Principal Architect means by "memory" is not confirmed |
| Sources | Several sources at once (`INGENUS_SOURCES=sharepoint,onedrive,network`): the server lists all, routes by the `document_id` prefix and reports a source that is down (decision 0010) | **Built; verified live (23 Oct 2026, demo guide 8b, Mode B)**, including the source-down tests |
| Terms | `get_contract_terms` (the ninth tool): terms a check verified are kept and reused while the file is unchanged, with a completeness check (decision 0011) | **Built; verified live (26 to 29 Oct 2026, demo guide 8c).** Stored terms are checked by code, not reviewed by a person |
| Search | `search_contracts` (the tenth tool): keyword search over stored passages, and meaning search with a local embedding model and pgvector (decisions 0012, 0013) | **Built; verified live (2 Nov 2026, demo guide 8d and 8e).** **Not done:** the AI admin's answer on local models (synthetic data only until then), tuning the cut-off on Ingenus's real wording, a second person's view |
| V1-9 | Demo guide and runs | **In progress:** live results for sources (8b), stored terms (8c), keyword search (8d) and meaning search (8e). **Not done:** a run with two real people, a run on the AWS VM |

What is left, in order, with the decisions waiting on people: [`../docs/v1_open_items_checklist.md`](../docs/v1_open_items_checklist.md).

## Layout

```
MCP-Server/
├── src/ingenus_mcp/
│   ├── core/        copied from v0 (tag v0) and owned by v1 from here on: registry, log, quote check, compare, SAP access; plus auth.py (sign-in check), sources.py and graph.py (document sources), db.py (SQLite or Postgres), auditstore.py, history.py, records.py and passages.py (the stores), embeddings.py (the local model)
│   ├── tools/       one module per tool; discover() imports them all at start-up
│   ├── server/      HTTP (default) and stdio entry points
│   ├── report.py    usage report from the tool-call log
│   ├── audit.py     verify, ship, query and prune the audit log, check records, stored terms and passages
│   ├── embeddings.py  fetch and status of the local embedding model (the only place a model is downloaded)
│   └── evals.py     page-finder recall on the labelled contracts
├── guidance/v8/     the guides served by get_guide (v2 to v7 kept as they were); add a folder with a SKILL.md to add a guide
├── prompts/         contract_check.v1.md (MCP prompt)
├── data/sap/        entities.json: synthetic mock SAP (a copy of v0's; a check gate keeps them equal)
├── bridge/          Claude Desktop bridge extension: manifest.json, server/ (index.js, bridge.js, auth.js), test/ (Node tests), build_bridge.py
├── scripts/         signin_check.py: live check against the dev tenant (run by hand)
├── secrets/         git-ignored; the certificate's private key (see developer_guide.md, section 5.1)
├── .env.example     the settings, with blanks; copy to .env (git-ignored)
├── demo/            start Claude Code here: .mcp.json and deny rules, no data
├── docs/            demo_guide.md (live QA results), cheatsheet.md (commands)
└── tests/           test_v1_*.py, offline; helpers in v1_support.py
```

Contracts are read, read-only, from v0's synthetic folder (`MCP-PlugIn/data/synthetic/contracts`) by default, or from
SharePoint with `INGENUS_DOC_SOURCE=sharepoint`, from the signed-in user's OneDrive with `onedrive` (both need
sign-in), or from a network share with `network`; or from several at once with `INGENUS_SOURCES=sharepoint,onedrive,network`. The log, the local
files and the embedding model live under `MCP-Server/data/runtime/` (git-ignored); with `INGENUS_PG_HOST` set, the audit store, check
records, stored terms and search passages are in Postgres.

## Run

```powershell
python -m ingenus_mcp.server                     # HTTP on 127.0.0.1:8765, path /mcp
python -m ingenus_mcp.server --transport stdio   # stdio, for local tools
python -m ingenus_mcp.report --log MCP-Server\data\runtime\tool_calls.jsonl
```

The server binds to **loopback only** by default, and refuses to start on a network address with sign-in off
(`INGENUS_AUTH=off`): an open port without sign-in lets anyone on the network call the tools. With
`INGENUS_AUTH=entra` every request needs a valid Entra token.

Settings are environment variables, or `MCP-Server/.env` on a developer laptop (copy `.env.example`). The full list,
what is and is not a secret, and how to create the certificate key are in `../developer_guide.md`, section 5.1.
Older ones: `INGENUS_CONTRACTS_DIR`, `INGENUS_SLICE_DIR`, `INGENUS_SAP_ADAPTER`, `INGENUS_SAP_MOCK_FILE`,
`INGENUS_LOG_PATH`, `INGENUS_PROMPTS_DIR`, `INGENUS_MCP_HOST`, `INGENUS_MCP_PORT`. New: `INGENUS_DOC_SOURCE`,
`INGENUS_SP_SITE_URL`, `INGENUS_SP_FOLDER`, `INGENUS_AUTH`, `INGENUS_TENANT_ID`, `INGENUS_SERVER_CLIENT_ID`,
`INGENUS_CERT_KEY_FILE`, `INGENUS_CERT_THUMBPRINT`, `INGENUS_OD_FOLDER`, `INGENUS_NETWORK_ROOT`,
`INGENUS_EXCLUDE_PATTERNS`, `INGENUS_AUDIT_STORE`, `INGENUS_HISTORY_DB`, and for Postgres `INGENUS_PG_HOST`, `INGENUS_PG_PORT`, `INGENUS_PG_DB`, `INGENUS_PG_USER`, `INGENUS_PG_PASSWORD_FILE`, `INGENUS_PG_SCHEMA`, `INGENUS_RETENTION_DAYS`; later: `INGENUS_SOURCES`, `INGENUS_SOURCES_TIMEOUT`, `INGENUS_NETWORK_TIMEOUT`, `INGENUS_RECORDS_DB`, `INGENUS_GUIDANCE_DIR`, and for meaning search `INGENUS_EMBED_MODEL` (`nomic`, `bge`, `minilm` or `off`), `INGENUS_EMBED_DIR`, `INGENUS_EMBED_MIN_SIM`. `python -m ingenus_mcp.audit prune` deletes events and check records older than the retention, and stored terms and passages not used for that long. All the commands are in [`docs/cheatsheet.md`](docs/cheatsheet.md).

Meaning search is off until a model is named and downloaded: `python -m ingenus_mcp.embeddings fetch`, then `status` (the server never downloads a model; decision 0013).

Audit commands: `python -m ingenus_mcp.audit verify` (is the log's hash chain intact), `ship` (copy the log's events
to the central store; safe to repeat) and `query --user NAME --tool NAME --event login`.

Live check against the dev tenant (server running in another terminal):
`python MCP-Server\scripts\signin_check.py` signs you in in the browser, calls the server and runs the Chain X
comparison from SharePoint.

## Connect Claude Desktop (primary)

The step-by-step demo with expected results is in [`docs/demo_guide.md`](docs/demo_guide.md).

A user's laptop has **only Claude Desktop**: no repo, no Python, no git. Claude Desktop reaches the server
through the **bridge extension** ([`bridge/`](bridge/)): a few lines of Node that forward every MCP message to
the server and back. It has no tools, data or secrets; Claude Desktop runs it with the Node it bundles
(Anthropic's MCPB guide; **verify** on the target Desktop version).

Build it (developer machine, needs Node.js):

```powershell
cd MCP-Server\bridge; npm ci; cd ..\..
python MCP-Server/bridge/build_bridge.py   # -> MCP-Server/build/ingenus-bridge.mcpb (about 4 MB) and MCP-Server/build/bridge/
```

Use it:

1. Start the server: `python -m ingenus_mcp.server` (for the POC on your laptop; later it runs on the POC's AWS VM (Ingenus's own host is a later decision)).
2. In Claude Desktop: Settings > Extensions > Advanced settings > Extension Developer > **Install Extension...**
   and pick `MCP-Server\build\ingenus-bridge.mcpb`. If Install stays disabled (as with v0's `.mcpb`), use
   **Install unpacked extension** with `MCP-Server\build\bridge`, and record which one worked.
3. Set **Server URL** to `http://127.0.0.1:8765/mcp` (the default). A server on the network must use `https://`;
   the bridge refuses plain `http://` to another machine. If the server has sign-in on (`INGENUS_AUTH=entra`), also
   fill in **Tenant ID**, **Desktop client app ID** and **Server app ID** (all three, or none for a server with
   sign-in off). The first chat opens a browser to sign in with an account of that tenant (not your Claude account);
   later starts are silent. The sign-in cache is `%LOCALAPPDATA%\Ingenus\bridge\msal-cache.json`: delete it to sign out.
4. Disable v0's extension while testing, so Claude does not see two sets of the same tools.
5. New chat: "Check Chain X's contract against SAP as of 31 Aug 2026." Expected: 8,500.00 a month, 17,000.00.

Bridge errors go to Claude Desktop's MCP logs (stderr, prefixed `[ingenus-bridge]`).

## Connect Claude Code (second client)

See [`demo/README.md`](demo/README.md): run the server, then start `claude` from `MCP-Server/demo`.

## Add a tool

1. Write a decision record in `../docs/decisions/` (more tools make Claude choose worse).
2. Add `src/ingenus_mcp/tools/<tool_name>.py` with one function `<tool_name>` decorated `@tool(read_only=True)`.
   The docstring is the description Claude reads.
3. Add its test. `test_v1_discovery.py` checks one tool per module, named like the file.
4. Restart the server. (Guidance files are read fresh and need no restart; a new tool does.)

## Tests

```powershell
pytest MCP-Server/tests          # v1 only
python scripts/check.py          # everything, once at the end of a change
```

The tests for Postgres, search and meaning search (`test_v1_postgres.py`, `test_v1_search.py`, `test_v1_meaning.py`) need a Postgres with pgvector on `127.0.0.1:5433` and skip without one (the cheat sheet says how to start it).
