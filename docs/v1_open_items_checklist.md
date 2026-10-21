# v1 open items: checklist

**As of 21 Oct 2026, updated after building 2.2 to 2.5 offline.** What is left after V1-0 to V1-6 (see [the proposal](v1_impact_analysis_and_proposal.md) and
[`MCP-Server/README.md`](../MCP-Server/README.md)). Tick a box only when the "done when" is shown, not when the code is
written. Tags: **SAID** = someone stated it; **ASSUMED** = my reading, not confirmed; **UNKNOWN** = nobody knows yet.

## 1. Done (for context)

- [X] V1-0 move, V1-1 `mock_sap.md`, V1-2 HTTP server, V1-5 Claude Desktop bridge, V1-3 guidance served by the server
- [X] V1-4 (the sign-in half): server checks the Entra token on every request; bridge signs the user in; log names the person
- [X] V1-6 SharePoint reading as the signed-in user; verified live and in Claude Desktop (20 Oct 2026), decision [0004](decisions/0004-v1-per-user-sign-in-and-sharepoint-reading.md)
- [X] 2.2, 2.3, 2.4 and 2.5 built and tested offline (21 Oct 2026; 206 v1 tests): audit log and login log, check history, OneDrive and network share. What each still needs is below

## 2. Next up (suggested order)

**Order locked 21 Oct 2026 (Sridhar):** build the project end to end on the local machine first, then host it at the end. So 2.1 (the AWS VM) is the last item, and every other item below is worked locally.

### 2.1 Put the server on a VM and reach it from another machine (rest of V1-4) — **LAST: build and test everything locally first, host at the end (Sridhar, 21 Oct 2026)**

Why: so a second person (Aditya, a tester) can use it. Today it listens on `127.0.0.1` of one laptop.
Depends on: **Aditya, who provisions the VM on AWS (SAID, 21 Oct 2026; decision [0009](decisions/0009-v1-poc-vm-on-aws-provisioned-by-aditya.md)).** Psiog IT is not on this path, so steps 5 and 6 of [`psiog_it_steps_v1-4_v1-6.md`](psiog_it_steps_v1-4_v1-6.md) are not sent to them.

- [ ] **Ask Aditya:** AWS account and region, OS (Windows or Linux; Linux is untested), who provides the DNS name and HTTPS certificate, who may reach the port, Postgres on the VM or managed (all **UNKNOWN**)
- [ ] Aditya delivers: the AWS VM, a DNS name, an HTTPS certificate (public CA, or a private CA plus its root `.cer`)
- [ ] Install Python and the server on the VM; run it as a service account (no admin rights)
- [ ] Make a **new** certificate key pair **on the VM** (do not copy the laptop's key); upload its `.cer` to the server app; set the thumbprint and key path as service environment variables, with no `.env` file ([`developer_guide.md`](../developer_guide.md) section 5.1)
- [ ] Put HTTPS in front of the server (the bridge refuses plain `http://` to another machine)
- [ ] Set `INGENUS_PUBLIC_URL` and `INGENUS_MCP_HOST`; sign-in stays on (the server refuses a network address without it)
- [ ] Check the SDK's host-header protection accepts the VM's name (**UNKNOWN**: not tested; it protects loopback by default)
- [ ] Bridge on a second laptop: Server URL = the HTTPS address, plus the three IDs; first sign-in works
- [ ] **Done when:** a second person's Claude Desktop runs Q1 against the VM, and the log shows that person's name
- [ ] **Purpose of the AWS VM (Sridhar, 21 Oct): QA of multiple users calling and the logging.** QA list: two or more people calling at the same time; each call logged under the right name; login events (accepted, refused); the hash chain verifies after concurrent writes (**not tested yet**: two processes or threads on one log); Postgres receives every event; check history seen across people; `audit ship` and `prune` against the real database

- Unknown: whether Node (inside Claude Desktop) trusts the certificate chain; Psiog's Conditional Access policies; which Entra tenant the AWS-hosted POC signs people in against, and who creates the app registrations there (the dev tenant is for testing only)

### 2.2 Central audit log and login log (built and tested offline; the real store is not chosen)

Built (decision [0005](decisions/0005-v1-audit-log-with-hash-chain-and-central-store.md)): one event stream, with `tool_call` and `login` events.
- [x] Login events: once per accepted token; refused ones with a reason class, at most one per reason per 10 s; never a token
- [x] The local JSONL file is always written first (source of truth and buffer); each event is also copied to a central store (SQLite reference, `INGENUS_AUDIT_STORE`); `python -m ingenus_mcp.audit ship` catches up and is safe to repeat; a store that is down stops nothing
- [x] A hash chain with `python -m ingenus_mcp.audit verify` (finds an edited, removed, reordered or cut-off line); `audit query` searches the store; the usage report ignores logins but counts them
- [x] 31 offline tests

Still open:
- [~] **Real store, partly decided (21 Oct 2026):**
  - **SAID** (Aditya suggested a custom database; Sridhar chose **Postgres**).
  - **Where, SAID by Sridhar:** local for the POC, the AWS VM Aditya provisions for the POC only (SAID, relayed 21 Oct; replaces "Psiog Azure"), then Ingenus's choice, possibly Azure or on-prem, by a later decision (Ingenus leaned on-prem on 8 Oct, SAID).
  - **ASSUMED for the POC, Ingenus to confirm:** keep audit log 12 months; keep check history 12 months; audit database read by admins only (Sridhar, Aditya); history shows other people's names.
  - **Built and tested (decision 0008):** a Postgres back end for the audit store and the check history (`INGENUS_PG_HOST`), tested on a local Postgres 17 (12 tests), and `python -m ingenus_mcp.audit prune` for the 12-month delete (a command to schedule; no timer yet).
  - **Not built or not verified:** separate Postgres roles (write-only for the server, read-only for reviewers), TLS to a remote database, the VM copy, and pruning the local log.
- [ ] **Decide:** store down means keep serving and ship later (built) or stop serving (a regulated setting might require it). Whether 21 CFR Part 11 or similar applies: **UNKNOWN**, do not assume
- [ ] Implement the chosen store: one more implementation of `add`, `emit` and `query` in `core/auditstore.py`
- [ ] Correlate with Entra's own sign-in log (authoritative for MFA; retention depends on the licence, **UNKNOWN**)
- [ ] Keep a copy of the last hash elsewhere (lines cut off the END of the log cannot be seen); log rotation is not designed; one server process per log
- [ ] **Done when (live):** calls from two real people appear in the central store with the right names, a refused token appears as a login event, and stopping the store loses no events. The offline tests prove the mechanism; two real people need 2.1 or a second sign-in on one server

### 2.3 Shared check history across people (built and tested offline; the meaning of "memory" is not confirmed)

Built (decision [0006](decisions/0006-v1-shared-check-history-tool.md)): every `compare_contract_to_sap` run leaves a record, and an eighth read-only tool, `get_check_history`, returns them.
- [x] A record keeps who, when, customer, as-of date, each line (rates, status, gap, file, page), the totals, the not-checked count and the **version of each file**; never page text, quotes or tokens; never anything said to Claude (the server cannot see it)
- [x] `changed_since` per file, and a note that these are figures from an earlier check, not new findings
- [x] Access rule: a record is shown only if the asking person can open every file it used, tested with their own access; hidden records are only counted
- [x] 11 offline tests (a second person sees the first person's check; a person who cannot open the file sees nothing)

Still open:
- [x] **"Memory" means findings only** (what the server can reach): **SAID** by Sridhar, relaying Aditya, 21 Oct 2026. Notes and decisions (a write tool) are out of scope.
- [ ] Data policy: may contract-derived figures (rates, gaps) be stored? Is showing other people's names acceptable? (**UNKNOWN**; synthetic data only today)
- [ ] Guidance: the `v2` guides are not edited in place; add a `v3` playbook line "read the history first". Today only the server instructions and the tool description steer Claude
- [ ] **Done when (live):** in Claude Desktop, person B's Claude shows person A's earlier check of the same file, without being told to, and a person who cannot read the file sees nothing. Needs two real sign-ins on one server (2.1, or two accounts in the dev tenant)

### 2.4 OneDrive (V1-7: built and tested offline)

Built (decision [0007](decisions/0007-v1-onedrive-and-network-share-sources.md)): `INGENUS_DOC_SOURCE=onedrive`, `INGENUS_OD_FOLDER=<folder>`; the same Graph code on the signed-in user's own drive (`/me/drive`, checked against Microsoft's docs); a folder is required (never the whole drive); the drive id and the text cache are per person. Offline tests share 21 tests with 2.5.
- [ ] Upload the 30 synthetic PDFs by hand to a folder in the dev tenant's OneDrive (for example `Ingenus_POC/contracts`), keeping the sub-folders
- [ ] In `MCP-Server/.env` set `INGENUS_DOC_SOURCE=onedrive` and `INGENUS_OD_FOLDER=Ingenus_POC/contracts`; restart the server
- [ ] **Done when (live):** `scripts/signin_check.py`, then Q1 in Claude Desktop, give 8,500.00 / 17,000.00 from the real OneDrive. Not verified: a real OneDrive; a person whose OneDrive is not set up (Microsoft says `/me/drive` provisions it when licensed, else 404)

### 2.5 Network drive (V1-8: built and tested offline; the real share needs IT)

Built (decision [0007](decisions/0007-v1-onedrive-and-network-share-sources.md)): `INGENUS_DOC_SOURCE=network`, `INGENUS_NETWORK_ROOT=<path>` (UNC or mounted share), read-only, as the one account the server runs as.
- [x] Links (symbolic links, junctions, DFS links) are never followed and are reported as not checked; asking for a file through a link is refused (tested with real Windows junctions)
- [x] Office lock files and temp files are skipped; an unreadable or locked file is reported and does not stop the rest; re-checked every 10 s; never writes
- [ ] A real UNC path: the `\\localhost\c$` admin share was not reachable on the developer laptop. Make a share on a machine you control (needs admin rights) or use IT's
- [ ] Send the **second IT request**: a Windows file share with the synthetic contracts, a read-only service account, a Windows VM in the domain (draft: Appendix A of the proposal)
- [ ] Test: paths longer than 260 characters, DFS namespaces, a share that hangs (no timeout is set yet), a large share (no metadata index yet)
- [ ] **Decide:** the server reads a share as ONE account, so every signed-in user sees what that account sees. If Ingenus's folder permissions differ by person (**UNKNOWN**), this is not enough
- [ ] **Done when (live):** Q1 exact from the real share; a link or path outside the root is refused; a locked file is reported, not fatal

### 2.6 More demo runs (V1-9)

- [ ] Run the 16 questions with sign-in and SharePoint, not only Q1 (record in [`MCP-Server/docs/demo_guide.md`](../MCP-Server/docs/demo_guide.md))
- [ ] Two people, same questions (section 8 of the guide is still empty): the main thing this stage is for
- [ ] Repeat test for guidance: the same question in 5 fresh chats, count how often `get_guide` is called first (one run is not a measure)
- [ ] Break-it tests (change the SAP file, bad quote, paraphrase) for v1

## 3. Hardening backlog (from the findings)

- [ ] Slow first call: 14.5 s for 30 files on SharePoint. List folders in parallel; measure with a larger library; find Desktop's tool timeout (**UNKNOWN**)
- [ ] Encrypt the bridge's sign-in cache (Windows DPAPI); it is a plain file readable by the user only
- [ ] Note how long Claude Desktop waits at the first sign-in and whether it times out (not recorded; delete `%LOCALAPPDATA%\Ingenus\bridge\msal-cache.json` and retry)
- [ ] Conditional Access that forces a new sign-in or MFA: the bridge retries once on a 401, but a claims challenge is not implemented
- [ ] Try the stricter delegated `Sites.Selected` instead of `Files.Read.All` and `Sites.Read.All` (offered to Psiog IT; not verified that it covers our calls)
- [ ] Install route for Ingenus users: the packed `.mcpb` still leaves Install disabled; only "Install unpacked" works. Try signing it, check the Desktop log and whether a Team Owner can allow it (finding 1)
- [ ] Stateless mode cannot push "tool list changed": check whether a new tool needs a new chat or an extension restart
- [ ] Rotate the server certificate before it expires on **18 Apr 2027** (new pair, upload the new `.cer`, update the thumbprint)

## 4. Moving beyond the dev tenant

The apps, certificate, group and site were made in a developer tenant (`vvrzl`) by the repo owner. Its lifetime is **UNKNOWN**: check the expiry in the developer programme. For Psiog's tenant, and later Ingenus's, the same steps repeat with their admins ([`psiog_it_steps_v1-4_v1-6.md`](psiog_it_steps_v1-4_v1-6.md)); the IDs and the site URL are settings, not code. What was done in the dev tenant, step by step: [`dev_tenant_setup_steps.md`](dev_tenant_setup_steps.md).

- [ ] Check when the developer tenant expires
- [ ] Update the Psiog IT request: the app, group and SharePoint parts are proven in the dev tenant; the VM and HTTPS no longer go to Psiog IT (AWS, Aditya; decision 0009); what may still need IT is the app registration in the real tenant and, later, the file share
- [ ] Before any real data: Ingenus's data policy signed off (CLAUDE.md rule 9); until then synthetic only

## 5. Decisions waiting on people

| Decision                                                             | Who                                               | Blocks                           |
| -------------------------------------------------------------------- | ------------------------------------------------- | -------------------------------- |
| Central log store, location, retention, readers, fail open or closed | Aditya, then Ingenus                              | 2.2, 2.3                         |
| What "per-process memory" means                                      | Aditya                                            | 2.3                              |
| Ingenus on-prem or cloud for the store and the server (later; the POC VM is AWS) | Aditya, Ingenus                                   | 2.1, 2.2                         |
| Per-person access or one shared server identity                      | Ingenus (do folder permissions differ by person?) | 2.5, the design in decision 0004 |
| Does Ingenus's data policy allow storing contract-derived figures    | Ingenus                                           | 2.3                              |
