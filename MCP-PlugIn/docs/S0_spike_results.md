# S0 spike results (13 Oct 2026)

Step S0 of `MCP-PlugIn/Plan.md` is **partly done**. What could be tested on a developer machine is done. What
needs Claude Desktop on a real plan, Ingenus's settings, or Dan is **not done**. Nothing here was tested on
Ingenus systems.

## Done and verified by running it

| Check | Result |
|---|---|
| Hello-world MCP server and client over stdio with the official SDK (`mcp` 2.3.0) | Works. Tool list, a read-only hint on the tool, a tool call and a prompt all returned |
| The real server over stdio, driven by an MCP client (plays Claude's part) | Works. Six tools, all marked read-only, full Chain X flow gives 8,500.00 a month and 17,000.00 exposure. Covered by `tests/test_server_stdio.py` |
| Desktop-extension bundle (`.mcpb`) | The manifest passes `mcpb validate`. `mcpb pack` builds a 24 MB file (58 MB unpacked, about 3,000 files) |
| Bundle runs outside the project's virtual environment | Works with a plain system Python 3.13, using only the bundled libraries, after one fix (below). `packaging/smoke_test_bundle.py` |

## Read from Anthropic's documentation (13 Oct 2026), not tested

- A **remote** custom connector is reached from Anthropic's cloud. A server on a private network, behind a VPN or
  a firewall "won't connect" unless Anthropic's addresses are allowed. Only Owners and Primary Owners can add one to a
  Team plan. ([custom connectors](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp))
- A **desktop extension** (`.mcpb`) runs locally over stdio and can reach systems behind the user's firewall.
  Users install it themselves: Settings > Extensions > Advanced settings > Extension Developer > Install Extension.
  Installation is per user. Owners can control an allowlist.
  ([MCPB guide](https://claude.com/docs/connectors/building/mcpb),
  [local servers](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop),
  [allowlist](https://support.claude.com/en/articles/12592343-enabling-and-using-the-desktop-extension-allowlist))
- The guide recommends Node.js because Claude Desktop includes it. A Python bundle must bundle all its libraries.
  It does not say Python itself is included.
- The skills help article (limits are **verify**): a skill is a folder with a `SKILL.md` that has `name` and `description`
  in a YAML header; the folder name should match the name; the description is limited to 200 characters.

## Not done (needs a person)

| Item | Needs |
|---|---|
| Install the `.mcpb` in Claude Desktop and run the demo | A person at a machine with Claude Desktop (it is installed on this laptop; the install is a UI step) |
| Test a remote connector from claude.ai | A public URL, OAuth, and an Owner on a Claude plan |
| Ingenus's Claude plan, Owner, admin settings, Desktop version, and whether laptops have Python | Abhishek |
| Whether MCP prompts and shared skills work on their Teams plan | A test on that plan |
| SAP reachability through the tunnel, the route, a read-only login | Dan |

## Findings that change the plan

1. **Python on the laptops.** Our bundle includes libraries but not Python, and they are built for Windows and the
   builder's Python version (3.13). See `docs/decisions/0002-python-runtime-for-the-desktop-extension.md`.
2. **The MCP SDK is on v2.** The import is `from mcp.server import MCPServer` and client objects use snake_case
   (`input_schema`, `structured_content`). Older examples (`FastMCP`) do not apply. `pyproject.toml` pins `mcp>=2.3,<3`.
3. **A stdio client passes only a few environment variables to the server.** Settings must be given explicitly. The
   extension manifest does this through its `env` block.
4. **pywin32 needs a `.pth` file.** The SDK needs it on Windows. A plain `sys.path` insert is not enough; the entry
   script uses `site.addsitedir`. Found by the smoke test.
5. **Skill descriptions must avoid `: `.** Four skill headers failed to parse as YAML until the colons were removed
   (caught by `tests/test_skills_and_prompts.py`).

6. **The packed `.mcpb` would not install on the test laptop (16 Oct 2026).** Settings > Extensions > Install
   Extension showed the install dialog with the Install button disabled. **Install unpacked extension**, pointed at
   `build\mcpb`, worked, and the six tools ran. Observed, not explained. Candidate causes: bundle size (24 MB), the
   Python requirement warning shown in the dialog, or a plan or policy setting. A Claude chat called it a known
   Desktop bug on Windows and named a size limit and error text; none of that was checked against a source, so treat
   it as a lead only (demo guide finding 7). This matters for D1: Ingenus would receive a `.mcpb`, not a folder, so
   the install route must be proven on a clean machine before Phase 1 is called deliverable. A smaller bundle (for
   example one that does not ship the libraries, see decision 0002) may also help; untested.

## Pass or fail for the decisions

| Decision | Status |
|---|---|
| D1: desktop extension per user | **Partly proven.** The bundle builds and runs over stdio. Not yet installed in Claude Desktop; Python on laptops unknown |
| D3: SAP route | **Not tested.** Mock adapter only |
