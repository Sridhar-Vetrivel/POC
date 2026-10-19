# Demo folder (v1)

Start Claude Code **from this folder** to use the v1 server. It holds no data on purpose: in Claude Code, Claude
also has its own file and shell tools, and the contracts and SAP mock must be reachable only through our
read-only tools (proposal section 6.6).

- `.mcp.json` connects Claude Code to the server at `http://127.0.0.1:8765/mcp`. Claude Code asks once before
  using a project-scoped server; approve it.
- `.claude/settings.json` denies reading or editing anything outside this folder. Whether Claude Code accepts
  `../` in these rules is **not verified**: check with `/permissions` in the session, and treat any file or shell
  access to contract data during a demo as a failure.

```powershell
# terminal 1: the server (repo root, venv active)
python -m ingenus_mcp.server
# terminal 2: Claude Code
cd MCP-Server\demo
claude
```

In Claude Code, `/mcp` shows the server and its six tools. Then ask, for example:
"Check Chain X's contract against SAP as of 31 Aug 2026." Expected: monthly gap 8,500.00, exposure 17,000.00.
