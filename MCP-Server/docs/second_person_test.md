# Second-person test: two real people, one server

**Purpose:** show that the server treats each signed-in person as themselves. What one person can open, the other may not, and what the first person checked can help the second.
**Status:** **not run yet** (2 Nov 2026). Everything here is synthetic data in the dev tenant `vvrzl`. Nothing is confirmed by Ingenus.
**Time:** about 1.5 to 2 hours. **Needs:** the tenant admin (`develop.admin@vvrzl.onmicrosoft.com`, called **A** below) and one new test user (**B**).
**Related:** [demo guide](demo_guide.md) ("Per-user tests"), [cheat sheet](cheatsheet.md), decisions [0004](../../docs/decisions/0004-v1-per-user-sign-in-and-sharepoint-reading.md), [0006](../../docs/decisions/0006-v1-shared-check-history-tool.md), [0007](../../docs/decisions/0007-v1-onedrive-and-network-share-sources.md), [0011](../../docs/decisions/0011-v1-stored-contract-terms.md), [0012](../../docs/decisions/0012-v1-keyword-search-over-stored-passages.md).

Labels: **Doc** (stated in this repo), **Expected** (what the design says should happen), **Unknown** (not checked; write down what you see).

---

## 1. What this test proves

| # | Claim | Where it comes from |
|---|---|---|
| 1 | Only people in the Entra group can sign in at all | Dev tenant steps 3.1 and 3.2 (`SG-Ingenus-POC`, "Assignment required") |
| 2 | SharePoint and OneDrive are read **as each person**: B sees only what B can open | Decision 0004 |
| 3 | The network drive is read by one service account, so **everyone sees the same files** (this is by design, not a leak) | Decision 0007 |
| 4 | A check by A leaves a record that B can read, but only if B can open **every** file it used | Decision 0006 |
| 5 | Terms stored by A's check are reused for B only for files in **B's own** listing | Decision 0011 |
| 6 | Search results (keyword and meaning) show only passages of files B can open now | Decisions 0012, 0013 |
| 7 | The audit log names each person; the hash chain stays intact | Decision 0005 |

## 2. Before you start

1. **Postgres is up** (WSL, port 5433): `Test-NetConnection localhost -Port 5433` shows `TcpTestSucceeded : True` (cheat sheet has the start command).
2. **The server runs with sign-in on** (`INGENUS_AUTH=entra` in `MCP-Server\.env`). If sign-in is off, the log names a local user and **this test is not valid**. Quick check: the last `login` or `tool_call` lines in the log show `develop.admin@vvrzl.onmicrosoft.com`, not `ingenus.tester`.
3. **Meaning search is on** (`INGENUS_EMBED_MODEL=nomic` in `.env`), synthetic data only (the AI admin has not answered yet). Restart the server after any `.env` change.
4. **Baseline as A** (new Chat, Ingenus connector on): "Check Chain A against SAP as of 31 Aug 2026". Expected **1,800.00 a month, 12,600.00 exposure**. This also makes A's check record, A's stored terms and A's passages, which B's tests need. Paste nothing yet; just confirm.
5. **Amendment 3 is under its normal name** in SharePoint (`Chain_A/Chain_A_Amendment_3_2026.pdf`).
6. Open a PowerShell window for the log commands below.

Log command (last 10 lines): `Get-Content C:\Users\<username>\INGENUS\POC\MCP-Server\data\runtime\tool_calls.jsonl -Tail 10`. `C:\Users\<username>\INGENUS\POC` is a **root path**: replace `<username>` with your Windows user name (and use your own folder if the repo is somewhere else). Each line has `"user"` (the signed-in person), `"tool"` and a short result summary.

## 3. Create user B (tenant admin does this, as A)

1. **Microsoft 365 admin center** > Users > Active users > **Add a user**. Name `Ingenus Tester` (first name Ingenus, last name Tester), username `ingenus.tester@vvrzl.onmicrosoft.com` (use your tenant's domain), set a password. **Assign a licence** from the developer subscription (SharePoint and OneDrive need one; **Unknown:** confirm on screen what the tenant offers).
2. **Do not add B to anything yet.** The first test needs B outside the group.
3. Write B's sign-in name and password in a safe place (not in the repo, not in chat).

## 4. How to sign in as B on the same laptop

The server's sign-in is Entra, separate from your Claude account, so one laptop and one Claude Desktop are enough. The bridge keeps the signed-in person in a cache file.

1. **Quit Claude Desktop completely** (also from the system tray).
2. Delete `%LOCALAPPDATA%\Ingenus\bridge\msal-cache.json` (this signs the bridge out).
3. Start Claude Desktop, open a **new Chat**, and ask any Ingenus question. A browser window opens for sign-in.
4. **Use a private (InPrivate) window**, or another browser profile, and sign in as **B**. Otherwise the browser may silently sign in as A. If a consent page appears, an admin (A) approves it (**Unknown:** whether the tenant already granted consent for all users).
5. After the first answer, check the log: the `user` must be B's sign-in name.

To go back to A later: repeat 1 to 4 and sign in as A.

## 5. The tests

Use a **new Chat for every question**, in Chat (not Cowork or Code) with the Ingenus connector on. Say "contract" and the customer name. After each test, paste the answer and `-Tail 10` of the log into the Result column.

**Part 1: B is not in the group**

| # | Do | Expected | Result |
|---|---|---|---|
| TP-0 | Sign in as B (section 4) while B is **not** in `SG-Ingenus-POC` | Entra **refuses** the sign-in (typically a message that the user is not assigned to the application; **Unknown:** exact wording). No Ingenus tool works. The log has **no** `tool_call` by B | **Pass (3 Nov 2026, 09:18 UTC).** Entra refused B with AADSTS50105 ("not a direct member of a group with access"); screenshot: [evidence/tp-0_not_in_group.png](evidence/tp-0_not_in_group.png). **Log checked (3 Nov 2026):** B has no event of any kind before the first `login` at 09:26:47 UTC, which came after B was added to the group. The refusal never reached the server |

Now add B: Entra admin center > Groups > `SG-Ingenus-POC` > Members > Add `ingenus.tester`. Wait one to two minutes, then sign in as B again (section 4).

**Part 2: B is in the group but is NOT a member of the SharePoint site** (site `mcp-sharepoint-test`; do not add B to the site yet)

| # | Ask (as B) | Expected | Result |
|---|---|---|---|
| TP-1 | "Check Chain A against SAP as of 31 Aug 2026." | **No Chain A figures.** The answer must not contain 1,800.00 or 12,600.00. Either no files, or SharePoint reported as not readable and the check **incomplete**. Claude must not say "no contract exists" | **Pass on the answer (3 Nov 2026).** B is in `SG-Ingenus-POC` (group list: 3 members). Claude found no Chain A files, said the check is incomplete and "not a finding that no contract exists", and gave no figures (no 1,800.00 or 12,600.00). SharePoint was reported as refused (not a site member, or admin consent missing), OneDrive had nothing, the network drive had 7 readable files with no Chain A match. The history reported 3 earlier checks that use files B cannot open, and showed none. **Log checked (3 Nov 2026):** the `login` and every call are `ingenus.tester@vvrzl.onmicrosoft.com`. `get_contract_terms` for Chain A: `stored_count` 0, `complete` false. `get_check_history`: `records_count` 0, `hidden_count` 3. No `compare_contract_to_sap` call |
| TP-2 | "Which Chain A contract mentions payment terms?" | **No hits** from Chain A (A's passages are stored, but B cannot open the files). Nothing like "net 45" or "net 30" appears. The log's `search_contracts` line shows `hits_count` 0, or `complete: false` | **Pass on the answer (3 Nov 2026).** No payment terms, no "net 45" or "net 30". Claude said the three Chain A files in SharePoint each returned a `GraphAccessError`, so the search was incomplete, and that this was "not because none of them do". **Log checked:** `search_contracts` ("payment terms", Chain A): `hits_count` 0, `complete` false, `not_checked_count` 5, `meaning_search` true |
| TP-3 | "Search the Chain A contracts for 'retrospective discount'" | **No hits** (meaning search obeys the same rule). Log: `hits_count` 0 | **Pass on the answer (3 Nov 2026).** No passages; the search was incomplete (SharePoint refused, all three Chain A files skipped); Claude did not say the term is absent. **Log checked:** `search_contracts` ("retrospective discount", Chain A): `hits_count` 0, `complete` false, `not_checked_count` 5, `meaning_search` true |
| TP-4 | "What did earlier checks of Chain A find?" | **No records shown.** The tool may say some were hidden (`hidden_count` at least 1) but shows nothing about them: no figures, no names of files | **Run on a single laptop (3 Nov 2026), result not valid: test again on a second laptop.** A and B share one laptop and one Claude account, so Claude answered from A's earlier chats, not from the Ingenus tool. A valid result needs a second person on **another laptop with their own Claude account**. The past conversations are not switched off for this test. The answer gave A's figures (1,800 a month, 12,600, Product A 3.0% to 4.5%), but Claude said it took them "from summaries of past chats": **Claude's own chat memory**, because B and A use the same Claude account on this laptop. The log must show whether the Ingenus tool was called. Repeat on a second laptop with the second person's own Claude account. **Log checked:** the tester's session made **no** Ingenus call at all for this question, so the answer came from chat memory only. The server's own answer is on record from TP-1: `get_check_history` gave `records_count` 0 and `hidden_count` 3, so no leak from the server |
| TP-5 | "Which stored terms do you have for Chain A?" (or ask for a check and read what `get_contract_terms` returned in the log) | **No stored terms returned** (`stored_count` 0): A's terms belong to files B cannot see | **Run on a single laptop (3 Nov 2026), result not valid: test again on a second laptop.** A and B share one laptop and one Claude account, so Claude answered from A's earlier chats, not from the Ingenus tool. A valid result needs a second person on **another laptop with their own Claude account**. The past conversations are not switched off for this test. Claude used its own "Read memory" and searched unrelated notes, not the Ingenus tool, so nothing about the server was tested. Repeat on a second laptop with "Which stored **contract** terms do you have for Chain A?", then read `stored_count` in the log. **Log checked:** no Ingenus call for this question. The server's answer is on record from TP-1: `get_contract_terms` for Chain A gave `stored_count` 0 (`complete` false, `not_checked_count` 2) |
| TP-6 | "Check Chain C against SAP as of 31 Aug 2026." (Chain C is in **A's** OneDrive) | **No Chain C files and no figures** (750.00 / 3,750.00 must not appear): B reads B's own, empty OneDrive | **Pass on the answer (3 Nov 2026).** No Chain C files and no figures (no 750.00 or 3,750.00). The network drive had no Chain C files, SharePoint was refused, OneDrive had no Chain C folder. **Log checked:** `get_contract_terms` Chain C: `stored_count` 0, `complete` false; `search_contracts`: `hits_count` 0, `complete` false; no `compare_contract_to_sap` call |
| TP-7 | "Check Chain E against SAP as of 31 Aug 2026." (network drive) | **The same as for A: 1,100.00 / 8,800.00.** The network drive is read by the server's service account, so everyone sees it (decision 0007). Write this down as expected behaviour, not a failure. **Unknown:** whether Ingenus wants it this way | **Pass as expected (3 Nov 2026).** 1,100.00 a month and 8,800.00 (Product A 3.5% against SAP 2.5%; Product B and the admin fee match), the same as A. Source shown as Network; Amendment 2 draft left out. Claude marked the check incomplete because SharePoint was refused and OneDrive was empty. **Log checked:** `compare_contract_to_sap` for SYN-CUST-3001 as `ingenus.tester`: `total_monthly_gap` 1100.00, `total_indicative_exposure` 8800.00; the three files read through `network:` ids; `stored_count` 0 (no stored terms for Chain E existed) |

**Part 3: add B to the SharePoint site** (site gear > Site permissions > add `ingenus.tester` as **Member**, read is enough; wait about a minute: the server trusts a cached SharePoint file for up to 60 seconds, so a repeat sooner can still show the old state)

| # | Ask (as B) | Expected | Result |
|---|---|---|---|
| TP-8 | "Check Chain A against SAP as of 31 Aug 2026." | **1,800.00 and 12,600.00**, the same as A. Log: `get_contract_terms` shows stored terms **used** (A's earlier check) for the Master and Amendment 1, and only Amendment 3 is read with `get_contract_pages`. Claude says the stored terms are checked by code and not reviewed by a person | **Pass on the answer (3 Nov 2026).** 1,800.00 a month and 12,600.00, the same as A. Claude said Amendment 1 and the Master came from an earlier verified check (stored terms, checked by code, not reviewed by a person) and that only Amendment 3 was read. The check was marked incomplete because B's own OneDrive has no folder ("Not found in OneDrive"). **Log checked (3 Nov 2026, 09:34 UTC):** `get_contract_terms` Chain A: `stored_count` 6, `documents_count` 3, `complete` false, `not_checked_count` 1 (B's empty OneDrive); `get_contract_pages` only for `sharepoint:Chain_A/Chain_A_Amendment_3_2026.pdf`; `compare_contract_to_sap`: `total_monthly_gap` 1800.00, `total_indicative_exposure` 12600.00, `not_checked_count` 0. Stored terms were used, as expected |
| TP-9 | "What did earlier checks of Chain A find?" | **A's check is listed, marked as another person's** (`who` is A, not you), **and B's own check from TP-8**, newest first, no changed-since flag unless a file changed | **Run on a single laptop (3 Nov 2026), result not valid: test again on a second laptop.** A and B share one laptop and one Claude account, so Claude answered from A's earlier chats, not from the Ingenus tool. A valid result needs a second person on **another laptop with their own Claude account**. The past conversations are not switched off for this test. Claude used "Read memory, searched past chats" and answered with A's earlier figures from chat summaries; it did not call the Ingenus history tool. Repeat on a second laptop (the second person's own Claude account); then check `get_check_history` in the log (A's check marked as another person's, B's own TP-8 check). **Log checked:** no `get_check_history` call for this question, only `get_guide` at 09:35:13 UTC, which confirms the answer came from chat memory |
| TP-10 | "Which Chain A contract mentions payment terms?" | The **two** passages as for A (Master p.5 net 45; Amendment 3 p.2 net 30), `meaning_search` true in the log | **Pass on the answer (3 Nov 2026).** Master p.5, section 5, net 45; Amendment 3 p.2, section 1, net 30. Claude said the search only shows where to look and the effective date is not confirmed. It also listed `Chain_A_Amendment_3_2026_hidden.pdf` as one it could not open. **Unknown:** why B cannot open that file as a site member. Most likely a leftover entry for the renamed file from the MQ-5 rename test (demo guide 8e says such passages stay until the prune); the other possibility is a file with its own permissions. Check the SharePoint folder for that name. **Log checked:** `search_contracts` "payment terms" with **no customer** (Claude did not pass Chain A), `hits_count` 4, `complete` false, `not_checked_count` 1, `meaning_search` true. Four hits against two named in the answer: Claude kept the Chain A ones. Not an exact match to "two passages"; the other two hits were not looked at |
| TP-11 | "Search the Chain A contracts for 'retrospective discount'" | The same result A got in MQ-1 (the rebate schedules, by meaning) | **Pass on the answer (3 Nov 2026).** No passage with the words; closest by meaning: Master p.4 Schedule A and Amendment 1 p.2 section 1 (the rebate schedules, as in MQ-1). It also listed two payment-terms passages (Amendment 3 p.2, Master p.5) as loose matches and said none describes a retrospective discount. OneDrive reported as not readable (B's own OneDrive). **Log checked:** `search_contracts` ("retrospective discount", Chain A): `hits_count` 4, `complete` true, `not_checked_count` 0, `meaning_search` true. Claude's "OneDrive not readable" comes from the later `find_contract_files` (`complete` false, `not_checked_count` 1), not from the search |

**Part 4: back as A**

| # | Do | Expected | Result |
|---|---|---|---|
| TP-12 | Sign in as A (section 4). Ask: "What did earlier checks of Chain A find?" | **Both** checks listed: A's own (`is_you`) and B's (named). A can read B's record because A can open every file it used | **Run on a single laptop (3 Nov 2026), result not valid: test again on a second laptop.** A and B share one laptop and one Claude account, so Claude can answer from A's earlier chats instead of calling the Ingenus tool, and the answer says nothing about the server. A valid result needs the second person on **another laptop with their own Claude account**. The past conversations are not switched off for this test |

**Part 5: the audit log (PowerShell, in `POC\MCP-Server`)**

| # | Do | Expected | Result |
|---|---|---|---|
| TP-13 | `..\.venv\Scripts\python.exe -m ingenus_mcp.audit query --user ingenus.tester@vvrzl.onmicrosoft.com --limit 30` | B's logins and tool calls, with B's name, and **none** of A's | **Pass (run 3 Nov 2026, in the terminal).** 29 rows, all `ingenus.tester@vvrzl.onmicrosoft.com`: 1 `login` (09:26:47 UTC) and 28 `tool_call`, up to 09:35:42. None under A's name. With `--limit 500` the tester has 29 events, so the 30 asked for were all of them |
| TP-14 | `..\.venv\Scripts\python.exe -m ingenus_mcp.audit query --user develop.admin@vvrzl.onmicrosoft.com --limit 30` | A's events, none of B's | **Pass (run 3 Nov 2026).** 30 rows (the limit), all `develop.admin@vvrzl.onmicrosoft.com` (4 `login`, 26 `tool_call`), from 2 Nov 11:46 to 3 Nov 09:13:39, which is before B's first login at 09:26:47. None under B's name. With `--limit 500` A has 208 events; 208 + 29 = 237, every event in the log, so no third name and no event under the wrong user |
| TP-15 | `..\.venv\Scripts\python.exe -m ingenus_mcp.audit verify` | `Chain: OK` (the hash chain is intact after two people) | **Pass (run 3 Nov 2026).** `Events: 237 chained, 0 from before the chain existed` and `Chain: OK`. The chain is intact after two people used it |

**Optional extras (if time allows)**

| # | Do | Expected |
|---|---|---|
| TP-16 | Remove B from the SharePoint site again, wait over a minute, repeat TP-2 as B | The Chain A hits are gone again (access is checked at every search, not remembered) |
| TP-17 | As B, upload any small synthetic PDF to B's OneDrive folder `Ingenus_POC/contracts`, ask about it as B, then ask A the same | B sees it; A does **not** (OneDrive is each person's own) |

## 6. Pass rule

- **Pass:** every "Expected" holds. Above all: **B never sees any Chain A, Chain C figure, quote, passage or history before B has access (TP-0 to TP-6)**, and the figures match A's once B has access (TP-8).
- **Fail** (a finding to fix before real data): any Chain A or Chain C content, figure, file name or quote shown to B in TP-1 to TP-6, or B's name appearing under A's events (or the reverse).
- TP-7 is **not** a pass or fail: it records how the shared network drive behaves, for the decision "per-person access or one shared identity" (open item for Ingenus).

## 7. If something looks wrong

| Symptom | Likely cause |
|---|---|
| The log shows A's name during B's session | The bridge signed in silently as A. Quit Claude Desktop, delete the cache file, sign in again in a private window |
| B sees Chain A files before being added to the site | The SharePoint site is more open than assumed (a public site, or B is in a group with access). Check Site permissions, record it, and fix the site before judging the server |
| B is still blocked after being added | Wait over a minute (the 60 second cache), then use a **new Chat** |
| No `login` or `tool_call` line appears | The chat did not use the connector (a question about a "file" can send Claude to its own workspace). Say "contract" and the customer name |
| Meaning hits missing | `INGENUS_EMBED_MODEL` is commented out, or the server was not restarted |
| Sign-in loops or an error page | Check that B is in the group and that "Assignment required" is on for **both** apps (dev tenant steps 3.2) |

## 8. Clean up and write down

1. Sign in as A again (section 4).
2. Remove B from the SharePoint site and from `SG-Ingenus-POC`, or delete B (`ingenus.tester`).
3. Rename nothing else: no file was renamed in this test.
4. Fill in the Result column, add a summary in the demo guide (section 8f, "Second-person QA") and findings in section 13 of the demo guide. Tick the open item "second-person test" in [`../../docs/v1_open_items_checklist.md`](../../docs/v1_open_items_checklist.md).

**Status (3 Nov 2026):** step 4 done (summary in demo guide 8f, findings 14 to 17, checklist 2.6). Steps 1 to 3 are not done: signing back in as A, and removing B from the site and the group, are admin-portal actions. Keep B if the second-laptop repeat will use B.

## 9. What this test cannot show

- **Two people at the same moment.** One laptop holds one signed-in person at a time. Two machines would need the server reachable from the second machine over HTTPS, which is not set up (the server listens on this laptop only).
- **Real Ingenus permissions.** SharePoint rights, groups and the file share at Ingenus will differ. The question "per-person access or one shared identity" for the network drive and for SAP stays with Ingenus.
- **Whether Claude Teams can reach the server** (a separate test; the cloud-brokered connector path needs a publicly reachable HTTPS server).
