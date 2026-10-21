# v1: impact analysis and solution proposal

**Status:** proposal, decisions taken 19 Oct 2026 (section 10). Nothing in it is built. Nothing is confirmed by Ingenus.
**For:** Sridhar and Aditya (Psiog).
**Asks covered:** (0) move `build/` and `data/` into `MCP-PlugIn/`, keeping v0 intact; (i) connect to a real SharePoint and OneDrive (Psiog's own tenant); (ii) put the mock data there and make Claude read it from there; (iii) a document on how the mock SAP works; (iv) one MCP server that carries the tools and skills, connected to Claude Code, so a new tool or skill is picked up without separate uploads; (v) read contracts from a network drive as well (added 19 Oct 2026). v1 is built in a new folder.

Labels used below: **Said** (in a transcript, with timestamp), **Doc** (read in Anthropic's or the repo's documentation, with source), **Assumed**, **Unknown / verify**.

---

## 1. Summary

| Ask | Feasible? | Recommendation | Effort (estimate) |
|---|---|---|---|
| 0. Move `build/`, `data/` into `MCP-PlugIn/` | Yes | Do it, but fix the `.gitignore` first (section 3.2: the tool-call log would otherwise become committable) | 0.5 day |
| i. SharePoint and OneDrive | Yes | Our server reads them through Microsoft Graph with **delegated, read-only** permissions. Needs an app registration in Psiog's Entra tenant: an IT step we do not control | 3 to 5 days, plus IT lead time |
| ii. Mock data there | Partly | Move the **synthetic contracts** to SharePoint. **Keep the mock SAP local**: SAP is not a document store, and putting it in SharePoint would test a route Ingenus will never use | Included in i |
| iii. Mock SAP document | Yes | `MCP-PlugIn/docs/mock_sap.md` (v0) and a copy in v1 | 0.5 day |
| iv. One MCP server for tools and skills (**primary client: Claude Desktop**, decided 19 Oct 2026; Claude Code is a second client) | Tools: yes, natively. Skills: **not a documented MCP feature**, so we serve them as server-side guidance (section 6) | One **central HTTP MCP server on a Psiog VM**, reached from laptops by **Claude Desktop through a thin local bridge** (6.5) and by Claude Code (`.mcp.json`); server sign-in and per-user logging; tools and guidance load from folders; `list_changed` refreshes Claude Code | 5 to 7 days |
| v. Network drive | Yes | The server reads a Windows file share (SMB) directly, as a **read-only service account**, through the same `DocumentSource` seam. A Psiog file share with the synthetic contracts stands in for Ingenus's drive. This is the route closest to where Ingenus's contracts actually are (section 4.5) | 2 to 3 days, plus IT lead time |

Total: about **12 to 17 working days** for one person, excluding Psiog IT's lead time. These are estimates; nothing has been prototyped.

**Target after the POC (direction set 19 Oct 2026):** the same server is hosted inside Ingenus's network, next to the routes to SAP and the shared drive. Laptops on Ingenus's network or VPN reach it directly, so no inbound firewall opening is needed. A Claude **custom (remote) connector** would not reach it, because those calls come from Anthropic's cloud (section 6.4).

**Three points to settle before building (TAC view):**

1. **Contracts at Ingenus are on the network drive, not SharePoint.** Dan: *"the SharePoint isn't hard, but the shared drive and our SAP system, which are behind a firewall, ... we can never expose that outside of our own firewall"* **[Said, 8 Oct 37:42]**. Call 1 also placed contracts on the network drive. A SharePoint connector is still worth building, because SharePoint is a stated Ingenus source (*"keep SharePoint and the network drives in mind as well"* **[Said, Call 1 58:32]**) and Aditya proposed it **[Said, 8 Oct 12:29, 14:12]**. SharePoint alone would prove the SharePoint connector, **not** Ingenus's contract route, so **v1 also reads a network drive** (section 4.5). What stays open is Ingenus's actual share: its path, size, folder layout, file types and the read-only account (questions in 4.5.6).
2. **Claude Code is a developer tool; the client chose a plug-in in their own Claude.** (Decided 19 Oct 2026: v1 is built **primarily for Claude Desktop**, through the bridge in 6.5; Claude Code is kept as a second client.) *"I like the part one for now"* **[Said, 8 Oct 46:57]** referred to the MCP plug-in in their Claude (Teams, about 12 licences **[Said, 46:02]**). Claude Code is included in Team seats, Standard and Premium **[Doc: support.claude.com, "What is the Team plan"]**, so licensing is not the issue. The issue is the users: Ingenus's contract and finance staff are unlikely to work in a terminal or IDE (**Assumed**). Recommendation: build v1's server so that it works from **both** Claude Code (our build and test harness) and Claude Desktop (the client's agreed route). Section 6.5.
3. **Claude Code can read and edit files by itself.** In Claude Desktop Chat, our tools are Claude's only way to the data. In Claude Code, Claude also has its own file, edit and shell tools. With the **central server**, the SAP mock, the document cache and the log live on the VM, not the laptop, so those tools cannot reach them. The remaining gap is a laptop that also has a synced copy of the documents or a repo checkout with the synthetic data (section 6.6). State this when v1 is shown.

---

## 2. What v0 is today (the baseline)

- One local stdio MCP server, `ingenus_plugin`, with six read-only tools, one MCP prompt, eight skills uploaded separately to Claude, and a JSONL tool-call log.
- Packaged as a Claude Desktop extension. On 16 Oct the packed `.mcpb` would not install (Install disabled); the unpacked install from `build\mcpb` worked (demo guide finding 7).
- Contracts are read from a local folder; SAP is a mock adapter reading `data/synthetic/sap/entities.json` through the shared `mcp_servers/sap` interface (one `read()` method).
- Code fixes from the first demo run are committed (`4a7a907`).

v0 stays as it is, as the reference and fallback. v1 is a new folder.

---

## 3. Ask 0: move `build/` and `data/` into `MCP-PlugIn/`

### 3.1 What moves

| Today | After |
|---|---|
| `POC/build/` (generated; gitignored) | `POC/MCP-PlugIn/build/` |
| `POC/data/synthetic/` (contracts, SAP mock, generator) | `POC/MCP-PlugIn/data/synthetic/` |
| `POC/data/public/` (README only) | `POC/MCP-PlugIn/data/public/` |
| `POC/data/runtime/` (tool-call log; gitignored) | `POC/MCP-PlugIn/data/runtime/` |

`slices/`, `mcp_servers/`, `scripts/`, `tests/` and `docs/` stay at the root: they are shared by v0, v1 and Phase 2.

### 3.2 Impact: every place that must change

Found by searching the repo (18 files, about 80 references).

| File | What changes | Risk if missed |
|---|---|---|
| **`.gitignore`** | `data/runtime/` and `data/client/` contain a middle slash, so they only match at the repo root. Change to `MCP-PlugIn/data/runtime/` and `**/data/client/` (or `**/data/runtime/`). `build/` has no middle slash and already matches anywhere | **High.** `tool_calls.jsonl` holds the quotes Claude sent, which are contract text. It would show up in `git status` and could be committed |
| `MCP-PlugIn/src/ingenus_plugin/core/config.py` | Defaults for the contracts folder, SAP mock file and log path move under `MCP-PlugIn/data/`. `slices/` default unchanged | Server falls back to a missing folder |
| `MCP-PlugIn/packaging/build_bundle.py` | `BUILD` and the data sources it copies | Bundle missing data |
| `MCP-PlugIn/packaging/smoke_test_bundle.py` | `STAGE` and the sample-contracts path | Smoke test fails |
| `MCP-PlugIn/data/synthetic/generate_contracts.py` | `ROOT.parents[1]` to `slices/` becomes `parents[2]`; the "run from" line in the docstring | Page labels written to the wrong place; the `fixtures` gate then fails |
| `scripts/check.py` | `PY_DIRS` (`data/synthetic`), the `synthetic-label` and `fixtures` gates, the `data/client` check, the "regenerate with" message | Gates silently check nothing, or fail |
| `pyproject.toml` | `extend-exclude = [".spike", "build"]`. Ruff probably matches a bare name at any depth (**verify**); add `MCP-PlugIn/build` explicitly to be safe | `ruff --fix` rewrites third-party files in the bundle again (a Phase 1 gotcha) |
| Docs | `README.md`, `CLAUDE.md`, `developer_guide.md` (13 references), `MCP-PlugIn/Plan.md`, `MCP-PlugIn/README.md`, `docs/demo_guide.md` (15), `S0_spike_results.md`, `docs/decisions/0002`, `data/synthetic/README.md` | Wrong commands; the `docs-links` gate catches broken links but not wrong command text |
| **Claude Desktop** | The unpacked extension was installed from `POC\build\mcpb`. After the move it points at a folder that no longer exists | Extension stops working; reinstall from `MCP-PlugIn\build\mcpb` |
| `MCP-PlugIn/tests/conftest.py` | Nothing needed (it uses the config defaults), but run the suite to prove it | None if tests pass |

### 3.3 One design concern

The synthetic data was the shared fixture set for Phase 1 and Phase 2 (`README.md`). Once it lives inside `MCP-PlugIn/`, v1 either reaches into v0's folder or keeps its own copy. **Recommendation:** move it as asked, and give v1 its own small `data/` (the SAP mock JSON and the upload manifest). The contracts themselves live in SharePoint for v1. The cost is two copies of `entities.json`; a check-script gate can compare them.

### 3.4 Steps

1. `git tag v0` on the current commit, so v0 can always be rebuilt.
2. Fix `.gitignore` first, then `git mv data MCP-PlugIn/data`.
3. Update the files in 3.2, delete the old `build/`, rebuild the bundle.
4. Run `python scripts/check.py` once at the end; expect `0 failed`.
5. Reinstall the unpacked extension in Claude Desktop from the new path and re-run demo question 1.

---

## 4. Document sources: SharePoint and OneDrive (asks i and ii), network drive (ask v)

### 4.1 Options

| Option | How | For | Against |
|---|---|---|---|
| **A. Our server reads through Microsoft Graph (recommended)** | Our document tools call Graph with the signed-in user's delegated, read-only token | Our code still sees the exact page text, so the quote check (rule 7), draft exclusion and scope guard keep working. Matches Aditya's point that our own search can carry Ingenus nuances such as ignoring drafts **[Said, 8 Oct 14:50]**. Delegated tokens *"can never exceed the current user's existing permissions"* (already quoted in `Authorization_Approach.md`) | Needs an Entra app registration and consent in Psiog's tenant. More code: auth, paging, caching |
| B. Claude's own Microsoft 365 connector | Claude reads SharePoint directly through Anthropic's connector | No code from us | Our server never sees the text, so the quote check cannot run: Claude's quotes cannot be verified against a file we cannot read. Its search is Microsoft's (*"they decide the way the search algorithm works"* **[Said, 8 Oct 14:12]**). Connector traffic runs from Anthropic's cloud **[Doc]**, which for Ingenus means data leaving their environment |
| C. OneDrive sync client | Sync the library to a local folder and point the existing setting at it | Zero code; works today | Still local file access, so it does not meet "instead of local" |

**Recommendation: A.** C stays as a zero-code fallback if the app registration is refused.

### 4.2 Design (option A)

- **A document-source seam, like the SAP one.** A new `DocumentSource` interface with read-only methods only: list items under the configured folder (id, path, name, modified time, eTag or hash, size) and read one item's bytes. Two adapters: `LocalFolderSource` (v0 behaviour; used by the offline tests) and `GraphSource` (SharePoint document library or OneDrive). The six tools stay the same; only the adapter changes.
- **Configuration, not code:** source type (`local`, `sharepoint`, `onedrive`), site URL or drive, folder path, tenant id, client id.
- **Sign-in (central server, 6.4):** the user signs in to our server; the server uses MSAL for Python and the **on-behalf-of** flow to get a delegated Graph token for that user. On-behalf-of needs the server to be a confidential client, so the server holds **one credential** (a certificate is preferred over a client secret; **verify** Psiog IT's policy). It lives in the VM's secret store or environment, never in the repo. Per-user Graph tokens are cached on the server, not on laptops.
- **Permissions (verify against Microsoft's docs at build time):** delegated `Files.Read.All` and `Sites.Read.All`, or `Sites.Selected` limited to the one POC site (least privilege, but needs an admin grant per site). Read scopes only, so Graph itself refuses writes: the read-only rule is enforced at the source too.
- **Scope guard:** `document_id` becomes the path relative to the configured folder, as today. The server resolves it and checks that the item's parent path is inside the configured folder before reading. It never accepts a raw Graph item id or URL from Claude.
- **Cache:** downloaded files are cached by eTag in a configured cache folder, so the same PDF is not downloaded for every tool call. That folder is on the server VM and becomes a new "set location" for writes (rule 5), declared in the docs.
- **Graph calls used (verify exact endpoints at build time):** resolve the site from its URL, list the drive's children under a folder path, download an item's content; `/me/drive` for OneDrive.
- **Data move:** an upload script that reads the 30 synthetic PDFs and uploads them once to a POC folder in a Psiog SharePoint site (and optionally OneDrive). This script is the **only** writer, it runs by hand, and it is not part of the server. Every file stays labelled synthetic; the folder name says so.

### 4.3 What we need from Psiog IT (blocking; Sridhar raises it, draft in Appendix A)

1. An app registration in Psiog's Entra tenant (or IT registers it for us): one for the server (confidential client, certificate) exposing an API that the clients sign in to.
2. Consent for the delegated read permissions (some may need admin consent; **verify**).
3. A SharePoint site and library for the POC, and confirmation that synthetic files named after a client may be stored there. **Site created by Sridhar (19 Oct 2026):** `https://psiog0.sharepoint.com/sites/INGENUS`, default library "Documents" (`Shared Documents`). Still needed from IT: items 1, 2 and 4, and the confirmation in item 3. Not requested yet.
4. A small VM on Psiog's internal network for the server, reachable from team laptops over the network or VPN.

### 4.4 Why not the mock SAP in SharePoint

Putting `entities.json` (or an Excel version) in SharePoint is technically easy, but SAP will never be read from SharePoint. It would add a Graph dependency to the SAP path and prove nothing about the real SAP route, which is still Dan's open question (IPSEC tunnel, CDS views or tables, read-only login). **Recommendation:** the mock SAP stays a local file behind the existing `SapReader` interface. If you still want it in SharePoint, it is one more adapter (`GraphJsonSapReader`) behind the same interface, about half a day.

---

### 4.5 Network drive (ask v)

#### 4.5.1 Why it matters

Ingenus's contracts are PDFs on a network drive, with no contract system (**Said**, 8 Oct, opening of the call; Call 1). Dan put the shared drive behind the firewall with SAP **[Said, 8 Oct 37:42]**. Aditya proposed building an index *"very close to the network drive instead of ... processing the whole network drive for every query"* **[Said, 8 Oct 12:29]**. Abhishek has an in-progress PowerShell watcher on those folders (Call 1, 04:21, as recorded in the Call 1 notes). With the central server inside Ingenus's network (6.4), the server can read the share directly, and no firewall change is needed for it.

#### 4.5.2 Options

| Option | How | For | Against |
|---|---|---|---|
| **N1. Server reads the share by UNC path (recommended)** | Server on a **Windows** VM runs as a domain service account with **read-only** rights on the share; it reads `\\server\share\Contracts\...` with ordinary file calls | Least code: v0's folder reader already works on a path; Windows enforces read-only through share and NTFS permissions | The server must run on Windows in the domain (or have the account's credentials) |
| N2. Linux server mounts the share read-only | `mount -t cifs ... -o ro` with the service account, then read the mount as a folder | Works on a Linux VM; read-only twice (mount option and permissions) | Mount credentials on the VM; one more moving part to run |
| N3. SMB client library in Python | The server speaks SMB itself (for example the `smbprotocol` package; **verify** licence and maturity) | No mount, no domain join | New dependency; more code than N1 |
| N4. Per-user access (each user's own rights) | Kerberos delegation from the user's sign-in to the share | Each person sees only their folders | Complex; Phase 2-sized. Not for v1 |

**Recommendation: N1**, with one read-only service account, which matches `Authorization_Approach.md` option A ("SAP and the network drive through service identities with scopes"). Use N2 only if the VM must be Linux. Per-user access (N4) waits until Ingenus says folder permissions differ by person (**unknown**).

#### 4.5.3 Design

- **`NetworkShareSource`**, a third adapter behind the same `DocumentSource` interface as SharePoint and the local folder. The six tools do not change; only the configuration says which source a customer's contracts come from.
- **Configuration:** source type `share`, root path (UNC or mount point), optional include and exclude patterns (for example `*DRAFT*` and `~$*` Office lock files). The service account's password is never in configuration: on Windows the service runs **as** the account; on Linux the mount uses a credentials file readable only by the service.
- **Read-only, three ways:** the account has Read only on the share and in NTFS; the adapter has no write method; the existing write scan (`calllog.py` is the only writer) still applies.
- **Scope guard:** `resolve_inside` already rejects absolute paths and `..`. For a share it must also refuse links that point outside the root: symbolic links, junctions, and DFS links (**verify** how `Path.resolve` treats each on a UNC path).
- **Index near the drive (Aditya's point):** the v0 listing walks the folder on every `find_contract_files` call. That is fine for 30 files, not for a large share. v1 keeps a small **metadata index** on the server (path, size, modified time, hash, page count, draft flag), refreshed by a timed rescan that only re-reads changed files. A page-text cache keyed by path, size and modified time already exists in v0 (`documents.py`). Abhishek's watcher could later trigger rescans instead of a timer (to confirm with him).
- **Robustness:** a file locked by someone editing it, a path longer than 260 characters, a permission error on one folder, or the share being offline becomes a **not checked** entry naming the file and the reason, never a failed call. Very long listings stop at a limit and say so (v0 already does this at 200 files).
- **File types:** v0 reads text PDFs and `.txt` only. A real share likely holds `.docx` and scanned PDFs (**assumed**; scanned is **unknown**, 8 Oct notes). v1 reports them as not checked, as v0 does. `.docx` reading and OCR are separate decisions, not in v1.

#### 4.5.4 The Psiog stand-in

A Windows file share on Psiog's network (on the server VM or a Psiog file server), for example `\\<vm>\IngenusPOC\Contracts`, holding the 30 synthetic PDFs in the same folder layout (`Chain_X/`, `Chain_Y/`, `Wholesaler_Z/`, `bulk/`), labelled synthetic. A domain service account with Read only. The same upload step that fills SharePoint can copy the files here.

To show the multi-source design, the demo can put some customers on SharePoint and others on the share. A customer's contracts must come from **one** source, because mixing would make "which amendment is latest" ambiguous.

#### 4.5.5 What changes at Ingenus

Only configuration and the account: the share path, the read-only service account (Dan or Ingenus IT), the VM joined to Ingenus's domain, and the include and exclude patterns for their folder names. No code change is expected, if their contracts are text PDFs in per-customer folders (**unknown**).

#### 4.5.6 Questions for Ingenus (through Aditya)

1. Share path(s) for contracts, and roughly how many files and how much data?
2. Folder layout: one folder per customer, by year, or mixed? Are drafts marked in the name?
3. File types: PDF only, or also Word? Any scanned PDFs?
4. Does access differ by person, or can one read-only service account read all contract folders?
5. Can our server VM join their domain, and who issues the service account (Dan)?
6. Is Abhishek's PowerShell watcher running, and could it signal changes to our server?

## 5. Ask iii: how the mock SAP works (document)

Deliverable: `MCP-PlugIn/docs/mock_sap.md`, copied into v1. Content:

1. Why a mock exists (no SAP access; rule 9: synthetic only; the real route is undecided).
2. The interface: `SapReader.read(ReadQuery) -> ReadResult`, one method, which is why nothing can write.
3. The data file: the `_label` (must say SYNTHETIC or the adapter refuses to load), and the three tables: `customers` (5 rows), `rebate_setup` (5 rows: kind, product, rate, basis, validity dates) and `sales_volume` (40 rows: month, product, net sales).
4. How a read works: pick the table, exact-match filters, validity by `as_of`, months by period.
5. Who calls it: `core/sap.py` (`customer_exists`, `rebate_setup`, `sales_volume`) and, through those, `compare_contract_to_sap`.
6. How to change the data for a test, and which copy the running extension reads (the installed copy, not the repo).
7. How a real adapter replaces it: implement `read()` for the same entities; nothing above the interface changes. The open questions for Dan.

---

## 6. Ask iv: one MCP server for tools and skills, in Claude Code

### 6.1 What the platform does and does not do

| Fact | Source |
|---|---|
| Claude Code connects to MCP servers over `http` (recommended for remote), `stdio`, or `sse` (deprecated) | **Doc:** code.claude.com/docs/en/mcp |
| A project can share its servers through `.mcp.json` at the repo root; Claude Code asks before using a project-scoped server | **Doc:** same |
| If a server changes its tools, prompts or resources while connected and sends `list_changed`, an interactive Claude Code session fetches the new list with no reconnect. `/mcp` can also reconnect | **Doc:** same. Prompts and resources are covered by the same sentence; not separately confirmed |
| MCP prompts appear as slash commands, `/server:prompt (MCP)`; resources can be attached with `@server:...` | **Doc:** same |
| **An MCP server cannot deliver Agent Skills.** Skills come from skill folders, plugins, or the claude.ai account sync, not from MCP | **Doc:** code.claude.com/docs/en/skills (not a documented feature) |
| A Claude Code **plugin** can bundle skills **and** MCP server definitions together; installed from a marketplace (a GitHub repo or a local path works); auto-update is off by default for private marketplaces | **Doc:** code.claude.com/docs/en/plugins |
| An HTTP server added to Claude Code is contacted from the user's machine | **Inferred** (Claude Code is the MCP client); not stated in the docs |
| Claude Desktop **custom connectors** are contacted from Anthropic's cloud; servers behind a firewall *"won't connect"*. Local servers in `claude_desktop_config.json` use the local network | **Doc:** support.claude.com custom-connectors article |

So the honest answer to "add a skill to the MCP server and Claude uses it" is: **for tools, yes; for skills, only if the server serves them as guidance**, because MCP has no skill primitive.

### 6.2 Options for skills

| Option | How it works | Meets "add once, on the server"? | Trade-off |
|---|---|---|---|
| **S1. Server-hosted guidance (recommended)** | Each skill stays a `SKILL.md` in the server's `guidance/` folder. The server (a) lists every guide's name and one-line description in its instructions, (b) exposes `list_guides` and `get_guide(name)` as read-only tools, (c) exposes the user-started ones as MCP prompts (slash commands). Claude reads the list, then fetches the full guide when relevant, which works like a skill's load-on-demand | Yes. Drop a folder in `guidance/`, the server reloads and sends `list_changed` | Not a native skill: no automatic triggering, and fetching a guide costs one tool call. Works in every MCP client, including Claude Desktop |
| S2. Claude Code plugin | A plugin repo with `skills/` and a `.mcp.json` pointing at our server. Users install it once from a private marketplace | No. The skills live in the plugin, not the server; users must update the plugin (auto-update is off for private marketplaces) | Native skills with automatic use. Claude Code and Desktop's Code sessions only (**verify** whether Desktop Chat's "Add plugins" is the same mechanism) |
| S3. Both | Plugin carries the connection and the few skills that must trigger automatically; the server carries the rest | Partly | Two places to maintain |

**Recommendation: S1**, because it is what you asked for: one place, the server. Revisit S2 if Claude ignores the guides in testing (the run A and run B comparison in the demo guide measures exactly this).

### 6.3 How tools get added

Today every tool is a function with `@tool(read_only=True)` in `core/tools.py`, and the registry exposes whatever it finds. v1 keeps that, with one change: tools live as one module per tool in `tools/`, discovered at start-up. Adding a tool is: write the function and its test, restart the server (or let a file watcher reload it), and the server sends `list_changed`. The rules stay: read-only only, and a decision record for each new tool, because more tools make Claude choose worse (Aditya made the same point **[Said, 8 Oct 12:29]**).

Tools are code, so they are **not** loaded from SharePoint or any shared drive: loading code from a document store would let anyone with write access to that folder run code on every user's machine.

### 6.4 Hosting and identity (decided: central server)

**POC:** one HTTP MCP server on a **separate Psiog VM**, reached from laptops over Psiog's internal network or VPN, not over localhost. This mirrors the Ingenus target, so the laptop-to-server route is proven before handover.

**After the POC:** the same server inside Ingenus's network.

| How Claude connects | Where the call comes from | Reaches a server inside the network? |
|---|---|---|
| Claude Code, server added over HTTP | The user's laptop (**inferred**, 6.1) | Yes, if the laptop is on the network or VPN |
| Claude Desktop, local entry or thin extension that forwards to the server | The user's laptop (local servers *"use your local network"*, **Doc**) | Yes, through the bridge (6.5) |
| Custom (remote) connector, Desktop or claude.ai | Anthropic's cloud (**Doc**) | No, unless Dan allows inbound traffic from Anthropic. Not used |

**Identity.** One server for about 12 people must know who is calling:

- **Server sign-in:** MCP authorization (OAuth) on the server, so every call has a real user, the log records it, and access can be limited per person. For the Psiog POC the identity provider is Psiog's Entra tenant; at Ingenus it becomes theirs (**unknown**: Ingenus's identity provider).
- **SharePoint and OneDrive:** the server exchanges the user's sign-in for a delegated Graph token (on-behalf-of flow), so each user still sees only what they may see. It does not pass the client's token through to Graph (MCP spec, already cited in `Authorization_Approach.md`).
- **SAP (mock now):** one read-only service identity for the server, as in `Authorization_Approach.md` option A.

**Things hosting inside does not change:**

1. **Data still reaches Anthropic.** Tool results (page text, quotes, SAP rates and sales) go into Claude's context in Anthropic's cloud wherever the server sits. Dan's *"never expose"* **[Said, 37:42]** was about SAP and the shared drive as systems; whether Ingenus accepts their content reaching Claude is part of the pending data-policy check.
2. **SAP is on RISE (AWS), managed by SAP, over an IPSEC tunnel** **[Said, 31:58, 33:10, 43:04]**. A server in Ingenus's network uses that tunnel like their other systems, but still needs Dan's read route and a read-only login.
3. **Someone must run it** (patches, monitoring, restarts). The driving principles say Ingenus has no team to run it. Agree early: Ingenus IT, or Psiog under support.

### 6.5 Keeping Claude Desktop working: the thin bridge

Claude Desktop's local entry starts a program on the laptop; it does not call a URL directly. So each laptop gets a **thin bridge**: a tiny local MCP server that forwards every request to the central server and the replies back. Options (**verify** at build time):

- a small desktop extension written in Node (Claude Desktop includes Node, so no Python on laptops; this also resolves decision 0002 for v1);
- or an existing stdio-to-HTTP bridge in `claude_desktop_config.json` (third-party; check its licence and trust before use).

The bridge holds no tools, no skills and no data. Tools, guidance, Python and adapters all live on the server, so an update is one deploy. The bridge changes only if the protocol or the sign-in changes. It keeps the client's agreed shape **[Said, 46:57]**, and the S1 guidance works through it, which removes v0's separate skill upload.

**Optional test:** expose a Psiog test endpoint holding only synthetic data and try a custom connector, to learn what Ingenus would need if they ever chose that route.

### 6.6 Claude Code guardrails (new for v1)

In Claude Code, Claude has its own Read, Edit and Bash tools. The central server removes most of the risk, because the data sits on the VM. What is left is on the laptop:

- run demos from a **demo folder with no data in it** (`MCP-Server/demo/`, with its own `.mcp.json`), not from the repo root, which holds the synthetic contracts and SAP mock;
- in that folder's `.claude/settings.json`, deny `Read` and `Edit` on any synced SharePoint or OneDrive folder, and keep `Bash` on ask (the default);
- the demo guide treats any shell or file access to contract data during a demo as a failure.

Claude Desktop Chat has no such gap.

---

## 7. Proposed v1 layout

```
POC/
├── MCP-PlugIn/                 v0, frozen (tag v0); now holds its own build/ and data/
├── MCP-Server/                 v1 (new)
│   ├── README.md, Plan.md
│   ├── src/ingenus_mcp/        new package name, so v0 and v1 install side by side
│   │   ├── server/             HTTP entry point, server sign-in, list_changed on reload
│   │   ├── core/               copied from v0 at tag v0, then owned by v1
│   │   ├── tools/              one module per tool, discovered at start-up
│   │   └── sources/            DocumentSource: local, sharepoint, onedrive, network share (+ metadata index)
│   ├── guidance/               the v1 skills (SKILL.md), served by the server
│   ├── prompts/
│   ├── data/sap/entities.json  mock SAP copy (synthetic); lives on the VM at run time
│   ├── bridge/                 thin Claude Desktop bridge (forwards to the server)
│   ├── deploy/                 VM setup: service or container, configuration template (no secrets)
│   ├── demo/                   demo folder with no data: .mcp.json and .claude/settings.json (6.6)
│   ├── scripts/upload_to_sharepoint.py
│   ├── docs/mock_sap.md, demo_guide.md
│   └── tests/                  offline: local source and recorded Graph responses; live tests behind -m live
├── mcp_servers/sap/            shared SAP interface and mock adapter (unchanged)
├── slices/contract_to_sap_check/  shared rules, schemas, golden questions (unchanged)
└── scripts/check.py            extended to cover MCP-Server/
```

**Why copy `core/` rather than share it:** you asked to keep v0 intact. Sharing would mean every v1 change can break v0. The cost is that a fix found in v1 does not reach v0 automatically; with v0 frozen, that is acceptable.

---

## 8. Plan

| Step | Content | Done when | Estimate |
|---|---|---|---|
| V1-0 | Ask 0: the move (section 3) | `check.py` 0 failed; Desktop demo Q1 gives 8,500.00 and 17,000.00 from the new path | 0.5 d |
| V1-1 | `mock_sap.md` (section 5) | Reviewed by you | 0.5 d |
| V1-2 | `MCP-Server/` skeleton: copy core, new package, HTTP entry point, tool discovery, demo folder with `.mcp.json` and deny rules | Claude Code on a laptop lists the six tools; Q1 numbers exact with the local source (server on the same laptop at this step) | 2 d |
| V1-3 | Guidance served by the server (S1) and `list_changed` on reload | Adding a guide folder shows up in a running Claude Code session without a restart | 1 to 1.5 d |
| V1-4 | Move to the Psiog VM: deployment, server sign-in (Entra), per-user log | A second laptop reaches the VM over the network or VPN; the log shows the real user per call | 2 d (after the VM and app registration) |
| V1-5 | Thin Claude Desktop bridge | Claude Desktop on a laptop runs Q1 through the bridge to the VM; no Python on the laptop | 1 d |
| V1-6 | `DocumentSource` and `GraphSource`, on-behalf-of Graph token, cache, scope guard, offline tests | Q1 numbers exact with contracts read from SharePoint; a path outside the folder is refused | 3 to 5 d (after IT) |
| V1-7 | Upload script; OneDrive variant | The 30 files in SharePoint, labelled synthetic; one test from OneDrive | 0.5 d |
| V1-8 | `NetworkShareSource` (4.5): UNC reading as a read-only service account, link-safe scope guard, metadata index with rescan, not-checked handling for locked, long-path and unreadable files; offline tests on a temp folder | Q1 numbers exact with Chain X read from the Psiog share; a link or path outside the root is refused; a locked file is reported, not fatal | 2 to 3 d (after the share and account) |
| V1-9 | v1 demo guide, run in Claude Code and in Claude Desktop, with customers on SharePoint and on the share | Results recorded, as for v0 | 1 d |

**Status (19 Oct 2026):** V1-0 done (tag `v0`; `data/` moved; bundle rebuilt in `MCP-PlugIn/build/`; `check.py` 13 passed, 0 failed), except deleting the old `POC/build/` after the Claude Desktop extension is reinstalled from the new path. V1-1 done: [`MCP-PlugIn/docs/mock_sap.md`](../MCP-PlugIn/docs/mock_sap.md). V1-2 built and tested offline: [`MCP-Server/`](../MCP-Server/README.md) (HTTP server, one module per tool, demo folder; an HTTP end-to-end test gives 8,500.00 and 17,000.00; `check.py` 13 passed, 0 failed); not yet tried from a Claude client. V1-5 built and tested offline: a Node-only bridge extension (`MCP-Server/bridge/`, official MCP TypeScript SDK 1.32.1 pinned; packed `.mcpb` 3.9 MB, no Python) carries the full Chain X flow to the server, packed and unpacked; **installed in Claude Desktop on 19 Oct 2026 and working**: Desktop ran it with its built-in Node; Chat answered the Chain X question with 8,500.00 and 17,000.00 from the server; Cowork and Code sessions start after the server was made stateless. Only "Install unpacked extension" worked; the packed `.mcpb` left Install disabled again, so the Python requirement was not the cause, and how Ingenus users would install one file is still open. Client laptops have only Claude Desktop (no repo, Python or git), so the bridge is the only thing installed there. V1-3 built and tested offline (19 Oct 2026): skills v2 served by the server through a seventh tool, `get_guide` (decision 0003), read fresh on every call; not yet tried in Claude Desktop.

**Status (20 Oct 2026):** V1-3 tried in Claude Desktop (19 Oct). **V1-4 and V1-6 built and verified in the dev tenant** (`develop.admin@vvrzl.onmicrosoft.com`; apps, certificate, group and a SharePoint site made by the repo owner, so no wait for Psiog IT): per-user Entra sign-in on the server and in the bridge, delegated read-only Graph access, a document-source seam, the log naming the signed-in person (decision [0004](decisions/0004-v1-per-user-sign-in-and-sharepoint-reading.md)). Offline: 150 v1 tests and 18 Node tests; live: `signin_check.py` and Claude Desktop both gave 8,500.00 and 17,000.00 from SharePoint. Still open: the Psiog VM and HTTPS from another machine (the IT request still applies for those), OneDrive (V1-7), the network drive (V1-8), a central audit and login store, and a shared check history.

V1-0 to V1-3 do not depend on IT and can start now. V1-4, V1-6 and V1-8 wait for Psiog IT (Appendix A). V1-8 does not depend on the Graph work, so it can run before V1-6 if the share arrives first.

---

## 9. Risks

| Risk | Likelihood | Effect | Mitigation |
|---|---|---|---|
| Psiog IT will not allow the app registration or consent | Medium (**unknown**) | Blocks i and ii | Ask now; fallback is the OneDrive sync client (option C) |
| v1 is shown to Ingenus as "the contract route" before their own share is tested | Medium | Wrong expectations | Say plainly that v1 reads a Psiog share; their share's size, layout, file types and permissions are still open (4.5.6) |
| Ingenus's share is large, slow or mixed with Word and scanned files | Medium (**unknown**) | Slow listings; many not-checked files | Metadata index and rescan (4.5.3); report unsupported files; `.docx` and OCR as separate decisions |
| A link on the share points outside the contract root | Low | A file outside scope is read | Link-safe scope guard and a test (V1-8) |
| No domain join or service account allowed for the VM | Medium (**unknown**) | Blocks N1 | N2 (Linux mount) or N3 (SMB library) |
| Claude Code users bypass the tools through file or shell access | Medium | Read-only and quote-check promises weaken | Deny rules (6.6); prefer Desktop for client demos |
| Claude ignores server-hosted guidance more than it ignored native skills | Unknown | Order and wording drift (v0 run A findings) | Measure with the golden questions; fall back to S2 for the critical guides |
| `.gitignore` misses the moved log | High if not fixed | Contract text committed | Fix first (3.4 step 2) |
| Graph throttling or slow downloads on repeated reads | Low for 30 files | Slow answers | eTag cache |
| Scope creep into Phase 2 (review queue, gateway, orchestrator) | Medium | Time | v1 adds a central server and sign-in only; anything beyond that goes to Phase 2 |
| Server sign-in and on-behalf-of take longer than estimated | Medium | V1-4 and V1-6 slip | Build V1-0 to V1-3 first; time-box sign-in; fall back to one shared read-only service identity for the POC if needed, and say so |
| Nobody owns running the server after handover | Medium | Unpatched, unmonitored server at Ingenus | Agree the operator before hosting at Ingenus (6.4) |
| Ingenus laptops are not on the network or VPN when people use Claude | **Unknown** | Laptops cannot reach the server | Ask Abhishek and Dan |

---

## 10. Decisions (taken 19 Oct 2026)

| # | Decision | Answer |
|---|---|---|
| 1 | Mock SAP location | **Keep local**, behind the `SapReader` interface |
| 2 | Skills delivery | **Served by the server** (S1): guidance folders, `list_guides` / `get_guide`, prompts |
| 3 | Hosting for the POC | **Central server on a Psiog VM**, reached from laptops; server sign-in and per-user logging. Target after the POC: inside Ingenus's network |
| 4 | Clients | **Claude Desktop is the primary client**, through the thin bridge to the HTTP server (our own bridge on the official MCP TypeScript SDK, no third-party bridge). **Claude Code is a second client.** Demos and acceptance are in Claude Desktop |
| 8 | Order | **Bridge (V1-5) before guidance (V1-3)**, so every later step is tested in Claude Desktop |
| 5 | Folder and package | **`MCP-Server/`** and **`ingenus_mcp`** |
| 6 | Psiog IT request | **Sridhar** raises it (draft in Appendix A) |
| 7 | Document sources | **SharePoint first, then OneDrive** (same Graph code), **plus the network drive** (added 19 Oct 2026; option N1, read-only service account, section 4.5) |

## 11. What was not verified

- Exact Graph permission names, which need admin consent, and the msal-extensions encryption on Windows.
- Whether Claude Code applies `list_changed` to prompts and resources as it does to tools (the doc's one sentence covers all three).
- Whether Claude Desktop Chat's "Add plugins" uses the same plugin mechanism as Claude Code.
- That an HTTP server added to Claude Code is reached from the laptop (inferred, not stated).
- The MCP SDK v2 call for running the server over HTTP, and its support for MCP authorization on the server.
- How Claude Desktop's local entry or a thin extension forwards to an HTTP server.
- Whether Ingenus laptops are on their network or VPN when people use Claude, and Ingenus's identity provider.
- Ruff's matching of a bare `build` exclude at any depth.
- How `Path.resolve` treats symbolic links, junctions and DFS links on a UNC path; the `smbprotocol` package's licence and maturity (only if N3 is used).
- Everything about Ingenus's share (4.5.6).

---

## Appendix A. Draft request to Psiog IT

> **Superseded for V1-4 and V1-6 (19 Oct 2026)** by the fuller request [psiog_it_request_v1-4_v1-6.md](psiog_it_request_v1-4_v1-6.md): two app registrations, server sign-in, assignment, and the HTTPS certificate. The draft below is kept for the file-share item.

> **Subject:** Entra app registration, SharePoint site, file share and a small VM for a client POC (synthetic data only)
>
> Hi team,
>
> For the Ingenus pre-sales proof of concept we are building a read-only AI helper (an MCP server) that Claude uses to read contract files and compare them with mock SAP data. All data is **synthetic**: invented contracts and numbers, no client data. We would like to run it inside Psiog and need the following:
>
> 1. **App registration in our Entra tenant** for the server: a confidential client with a **certificate** (not a secret), exposing an API scope that our Claude clients sign in to.
> 2. **Delegated, read-only Microsoft Graph permissions** for that app: `Files.Read.All` and `Sites.Read.All`, or `Sites.Selected` limited to the POC site if you prefer least privilege. No write permissions. Please tell us which need admin consent.
> 3. **A SharePoint site (or a library in an existing site)** for the POC, for example "Ingenus POC – Synthetic", where we will upload about 30 synthetic PDF contracts. File and folder names include the client's name; please confirm that is acceptable for synthetic files.
> 4. **A small VM on the internal network** (2 vCPU, 4 GB RAM is plenty; Windows or Linux), reachable from the POC team's laptops over the office network or VPN, not from the internet. It runs one Python service on one HTTPS port. Windows and joined to the domain is preferred, so it can read the file share below as a service account.
> 5. **A Windows file share** (on that VM or an existing file server), for example `\\<server>\IngenusPOC\Contracts`, and a **domain service account** with **Read only** on the share and its folders. The service runs as that account. Same synthetic contracts, about 30 PDFs.
>
> Users: Sridhar Vetrivel and Aditya Manthena (and one or two testers). Duration: about four to six weeks. We will remove the app, site, share, service account and VM at the end, or hand them back for reuse.
>
> Happy to walk through the design. Thanks,
> Sridhar

Adjust the VM size, duration and names before sending; they are estimates.
