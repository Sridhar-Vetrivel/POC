# MCP-Server (v1)

One read-only MCP server for the Contract-to-SAP check, reached over HTTP. **Built primarily for Claude
Desktop**, which reaches it through a thin bridge on the laptop (V1-5); Claude Code is a second client. Tools are discovered from a folder; guidance (skills) will be served by
the server too. v0, the desktop-extension plug-in, stays frozen in [`../MCP-PlugIn/`](../MCP-PlugIn/) (git tag `v0`).

The design, decisions and plan are in [`../docs/v1_impact_analysis_and_proposal.md`](../docs/v1_impact_analysis_and_proposal.md).
Nothing here uses Ingenus data: contracts and SAP are synthetic.

## Status

| Step | Content | Status |
|---|---|---|
| V1-0 | Move v0's `build/` and `data/` into `MCP-PlugIn/` | Done 19 Oct 2026 (old `POC/build/` to delete after the Desktop reinstall) |
| V1-1 | [`mock_sap.md`](../MCP-PlugIn/docs/mock_sap.md) | Done |
| V1-2 | This skeleton: core copied from v0, one module per tool, HTTP server, Claude Code demo folder | **Built and tested offline** (HTTP end-to-end test gives 8,500.00 / 17,000.00). Not yet tried from a Claude client |
| V1-5 | **Claude Desktop bridge** (primary client): Node-only extension, forwards to the server | **Installed in Claude Desktop 19 Oct 2026; Chat connects.** Desktop ran it with its **built-in Node** (its log says so), so the laptop needs no Node or Python. Cowork and Code sessions failed ("Session not found"): their probe sends a request before any handshake, which a stateful server rejects. Fixed by making the server stateless by default (`INGENUS_MCP_STATELESS`). **Retested 19 Oct 2026: no start errors; the Chain X question in Chat gave 8,500.00 a month and 17,000.00 exposure** through bridge and server. Install route: **only "Install unpacked extension" worked**; the packed `.mcpb` again left Install disabled, although the bridge has no Python requirement, so that was not the cause (cause still unknown) |
| V1-3 | Guidance served by the server: skills `v2` in `guidance/v2/`, read through the `get_guide` tool (decision 0003); read fresh on every call, so a guide added on the server needs no restart | **Built and tested offline** (guides travel through HTTP and the bridge). Not yet tried in Claude Desktop |
| V1-4 | Psiog VM, server sign-in, per-user log | Waits for Psiog IT |
| V1-6, V1-7 | SharePoint and OneDrive (Graph), upload script. Site: `https://psiog0.sharepoint.com/sites/INGENUS` | Waits for the app registration |
| V1-8 | Network drive | Waits for a share and service account |
| V1-9 | Demo guide and runs | Not started |

## Layout

```
MCP-Server/
├── src/ingenus_mcp/
│   ├── core/        copied from v0 (tag v0) and owned by v1 from here on: registry, log, quote check, compare, SAP access
│   ├── tools/       one module per tool; discover() imports them all at start-up
│   ├── server/      HTTP (default) and stdio entry points
│   ├── report.py    usage report from the tool-call log
│   └── evals.py     page-finder recall on the labelled contracts
├── guidance/v2/     the guides (skills v2) served by get_guide; add a folder with a SKILL.md to add a guide
├── prompts/         contract_check.v1.md (MCP prompt)
├── data/sap/        entities.json: synthetic mock SAP (a copy of v0's; a check gate keeps them equal)
├── bridge/          Claude Desktop bridge extension: manifest.json, server/index.js (Node), build_bridge.py
├── demo/            start Claude Code here: .mcp.json and deny rules, no data
└── tests/           test_v1_*.py, offline; helpers in v1_support.py
```

Contracts are read, read-only, from v0's synthetic folder (`MCP-PlugIn/data/synthetic/contracts`) until the
SharePoint and network-drive sources exist. The log goes to `MCP-Server/data/runtime/` (git-ignored).

## Run

```powershell
python -m ingenus_mcp.server                     # HTTP on 127.0.0.1:8765, path /mcp
python -m ingenus_mcp.server --transport stdio   # stdio, for local tools
python -m ingenus_mcp.report --log MCP-Server\data\runtime\tool_calls.jsonl
```

The server binds to **loopback only** by default. Do not set `INGENUS_MCP_HOST` to a network address until
server sign-in exists (V1-4): an open port without sign-in lets anyone on the network call the tools.

Settings (environment variables): `INGENUS_CONTRACTS_DIR`, `INGENUS_SLICE_DIR`, `INGENUS_SAP_ADAPTER`,
`INGENUS_SAP_MOCK_FILE`, `INGENUS_LOG_PATH`, `INGENUS_PROMPTS_DIR`, `INGENUS_MCP_HOST`, `INGENUS_MCP_PORT`.

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

1. Start the server: `python -m ingenus_mcp.server` (for the POC on your laptop; later it runs on the Psiog VM).
2. In Claude Desktop: Settings > Extensions > Advanced settings > Extension Developer > **Install Extension...**
   and pick `MCP-Server\build\ingenus-bridge.mcpb`. If Install stays disabled (as with v0's `.mcpb`), use
   **Install unpacked extension** with `MCP-Server\build\bridge`, and record which one worked.
3. Set **Server URL** to `http://127.0.0.1:8765/mcp` (the default). A server on the network must use `https://`;
   the bridge refuses plain `http://` to another machine.
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
4. Restart the server. (V1-3 adds reload and `list_changed`, so a running Claude Code session sees it.)

## Tests

```powershell
pytest MCP-Server/tests          # v1 only
python scripts/check.py          # everything, once at the end of a change
```
