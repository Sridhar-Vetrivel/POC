# Design guide: why the plug-in is built the way it is

A systems-designer (TAC) view of Phase 1. It explains the **reasoning**: the problem, the forces, the
decomposition, the control points, the alternatives we rejected and what would make us change our minds. It is
the "why". For the "how to change it" read [developer_guide.md](developer_guide.md); for the "does it work" read
[MCP-PlugIn/docs/demo_guide.md](MCP-PlugIn/docs/demo_guide.md); for scope and steps read
[MCP-PlugIn/Plan.md](MCP-PlugIn/Plan.md).

> **Status and evidence key (13 Oct 2026).** Pre-sales. Nothing is confirmed with Ingenus. **Said** = the client said
> it on a call (timestamp; `[8 Oct …]` is the 8 Oct 2026 call, untagged times are the 25 Sep call). **Psiog input** =
> told to us by the Psiog team. **Assumed** = our reading. **Unknown** = to find out. **Built** = exists in this repo
> and is tested offline. **Not verified** = not yet run in Claude Desktop, against real SAP, or on Ingenus's setup.

---

## 1. The problem, as a designer sees it

**The decision being supported.** Ingenus sells generic drugs through wholesalers. Contract terms (rebates, fees,
effective dates) change by amendment. SAP must hold the matching setup, because SAP drives **accruals**, and accruals
drive gross-to-net, which senior management reads. When SAP lags the contract, the accrual is wrong and chargebacks
or claims follow. Today a person re-reads contracts and runs SAP reports by hand, then a quarterly expert looks again
(`[8 Oct 1:02:34]`).

**What an error costs.** A rate difference of one point on a large product is a material accrual error. Abhishek's
own example: 5.5% against 5.56%, missed by manual review (`[8 Oct 1:01:41]`). So the design question is not "how do
we make an AI answer" but **"how do we make a wrong answer hard to produce and easy to catch"**.

**Who uses it, and how.** A person at Ingenus asks their own Claude. About 12 Claude Teams licences (`[8 Oct 46:02]`).
Adoption and trust are the stated risks: people stop using a tool whose outputs they have not seen
(`[8 Oct 46:57]`).

**What the system is *not* asked to do.** Decide anything, change SAP, or read the contract for the person. It
produces evidence; a person decides.

## 2. The forces (constraints) that shaped the design

| Force | Source | Design consequence |
|---|---|---|
| **Read-only in SAP, writes only to set places** | Said `[39:27, 40:00]`; GxP (DP-13, DP-14) | No write tool exists, not even a mock. A test fails if one is added |
| **Control over how the AI reviews, which guidelines, which tools** | Said `[20:00]` | Business-level tools, written rules, a log. *But* phase 1 only partly meets this (section 12) |
| **Start small, simple, quick; people must actually use it** | Said `[8 Oct 46:34, 1:10:34, 1:10:39]` | One MCP server, six tools, no portal, no workflow engine |
| **No new cloud agreements for now; on-prem preferred** | Said `[8 Oct 41:40, 42:13]` | The server runs on the user's machine; no second LLM provider (Option X) |
| **SAP and shared drive stay behind the firewall** | Said `[8 Oct 37:42]` | Nothing is exposed to the internet; desktop extension, not a remote connector |
| **Cheap; two Psiog people; nobody at Ingenus to run it** | Said (DP-01, DP-06); Psiog input (DP-30) | Plain Python, one process, one thin MCP layer, no infrastructure |
| **Tokens come from Ingenus's own Claude plan** | Said `[8 Oct 38:53]` | Run cost to us is near zero; but we do not control the model or its settings |
| **Reproducible, checked results before output is presented** | Said `[00:00]` | Numbers come from code; every value carries a code-checked quote |
| **Ingenus's data policy not received** | Unknown (DP-20) | Synthetic data only; a gate in the Plan before any real data |
| **SAP version, route, login unknown** | Unknown | Mock behind a one-method interface; real route is a later swap |

Notice what is *not* on the list: scale, throughput, multi-tenancy. Volume is tiny (one to two amendments a month,
worst case one a week, `[8 Oct 1:04:12, 1:04:57, 1:05:24]`). The design is shaped by **trust and control**, not by load.

## 3. The design principles, in priority order

When principles conflict, the higher one wins. This ordering explains most of the decisions below.

1. **Never write.** SAP and source files are read-only. (Compliance; cannot be traded for convenience.)
2. **Numbers come from code, never from the model.** The same inputs give the same figures.
3. **Every value carries evidence a machine checks.** Document, page, exact quote; the code verifies it.
4. **Say what was not checked.** A visible gap beats a confident guess.
5. **A person decides.** The output is evidence for a reviewer, not a verdict.
6. **Smallest thing that gets used.** Prefer fewer parts, even at the cost of control we would like.
7. **Keep seams for growth.** Make the likely next changes cheap, but do not build them yet.

Principle 6 versus principle 5 is the main tension of phase 1: the client asked for something quick and simple, which
means **no review queue and no recorded decision**, which weakens principle 5. We accepted that for phase 1 and
state it openly (section 12).

## 4. The decomposition: who does what

The central design move is a **division of labour by cost of being wrong**.

```
 Person (reviewer)      decides; reads Claude's answer and the evidence
 ──────────────────────────────────────────────────────────────────────────────
 Claude (their plan)    understands language: finds meaning in contract text, extracts terms,
                        talks to the person, chooses the order of tool calls
 ──────────────────────────────────────────────────────────────────────────────  <- trust line
 Our code (plain)       finds files and pages, resolves names, reads SAP, VERIFIES quotes,
                        COMPARES, computes money, reports what it could not check, logs calls
 ──────────────────────────────────────────────────────────────────────────────
 Data                   contract files (read-only) · SAP (read-only, mock for now) · slice rules (YAML)
```

| Task | Who does it | Why |
|---|---|---|
| Understand "rebate rises to 6% from 1 July" | **Claude** | Language is messy; a model is good at it; a rule engine is not |
| Decide the order of steps | **Claude**, guided by a prompt and skills | Flexible; cheap; the client asked for "Claude to decide" |
| Prove the quote is on the page | **Code** | Cheap, exact, and catches invented text |
| Compute gap and exposure | **Code** | Money must be exact and repeatable. A model can do arithmetic wrong with confidence |
| Decide which SAP rate applies | **Code**, from SAP as at the date | A fact lookup, not a judgment |
| Decide whether the right clause was chosen | **Person** | Neither code nor Claude can prove it (see section 12) |
| Decide what to do about a gap | **Person** | Finance owns accruals |

**The determinism boundary** is the single most important line in the system: everything above it may vary between
runs and between people; everything below it must not. The design pushes as much as possible below the line, and
keeps above it only what genuinely needs language understanding.

## 5. System context and trust boundaries

```
  Ingenus laptop (inside the firewall)                                 Outside
 ┌────────────────────────────────────────────────────────────┐     ┌──────────────┐
 │ Claude Desktop ──stdio──> our MCP server (desktop extension)│────>│ Anthropic    │
 │   (user's own plan)         │                               │ tool│ (the model;  │
 │                             ├─> contract folder (read only) │ text│ the user's   │
 │                             ├─> SAP adapter (mock now; read)│ goes│ own plan)    │
 │                             └─> tool-call log (the only     │ to  └──────────────┘
 │                                 file we write)              │ Claude
 └────────────────────────────────────────────────────────────┘
```

**Boundaries and what crosses them**

| Boundary | What crosses | Control |
|---|---|---|
| Server to contract folder | File reads only | `resolve_inside` blocks anything outside the folder; no write path exists (tested by code scan) |
| Server to SAP | `read(entity, filters, as_of)` only | One-method interface; mock now; real adapter is a stub that refuses |
| **Server to Claude (and so to Anthropic)** | **Tool results: the pages shown, SAP numbers, findings** | **This is the data-egress surface.** Minimised: only the pages that match, not whole files; quotes, not documents, in the log. Governed by the data-policy gate |
| Claude to server | Tool arguments, including the terms and quotes Claude extracted | Validated by Pydantic; quotes checked against the page; logged |
| Server to log | One JSON line per call, counts only | Never page text; failure to log never breaks a tool |

**Where we do not have control** (and so cannot promise): which model the user's Claude uses; what the rest of that
Claude (other connectors, memory) does with the answer; whether Claude follows the skills; what Anthropic does with
data under the Teams plan (**unverified**, DP-20 policy not received).

## 6. One request, read as a design

"Check Chain X against SAP as of 31 Aug 2026." Each step names the **control** that protects it.

| # | Step | Actor | Control point |
|---|---|---|---|
| 1 | Resolve "Chain X" | tool `resolve_customer` | Ambiguity is returned, never guessed; the id must exist in SAP |
| 2 | List the contract files | `find_contract_files` | Drafts left out on purpose and named; only the contract folder; unsupported formats reported |
| 3 | Read the rebate and fee pages | `get_contract_pages` | Pages by keyword plus page 1 and neighbours (generous); unreadable pages and "no match" reported; result labelled untrusted data |
| 4 | Extract terms with exact quotes | **Claude** | Guided by skills; *not enforced*; this is the weak link that step 5 compensates for |
| 5 | Compare | `compare_contract_to_sap` | Each quote must be on the cited page, name the product and contain the rate, or the term is **not used** and listed. Duplicates and conflicts handled. Months with missing SAP sales are reported, not filled |
| 6 | Money | code, `Decimal` | Rate gap times monthly net sales, per month, partial months by days; rounded half-up; "indicative" |
| 7 | Report | Claude, from the tool's `summary`, `not_checked`, `caveats` | Skill says to use the numbers exactly as returned |
| 8 | Decide | **Person** | The only step that is allowed to change anything |
| 9 | Log | wrapper | One line: who, which tool, arguments, result counts |

**Why this order is a design choice.** Step 5 sits *after* extraction and treats Claude's output as **untrusted
input**. That is deliberate: the system does not need Claude to be right, it needs Claude's mistakes to be
**detectable** (invented quote, wrong page, wrong product, missing rate) and **contained** (the term is dropped and
reported, never silently used).

## 7. The key decisions, with alternatives

| Decision | Chosen | Alternatives considered | Why this one | What would change our mind |
|---|---|---|---|---|
| **Solution shape** | MCP plug-in only (deck **P1**; older notes **P4**) | Slice pipelines (P2), orchestrator + skills (P3), domain agents (P4 in the deck) | The client said "I like the part one for now" `[8 Oct 46:57]`; smallest, cheapest, fastest; tools are reused if we grow `[8 Oct 13:53]` | The client needs review, audit or a watcher: that means P2/P3 |
| **Where the AI loop lives** | In the user's Claude | Our own orchestrator | No agent of ours to build, host or pay for | Need for enforced steps, review queue, pause and resume |
| **How Claude reaches the server** | Desktop extension per user (local, stdio) | Remote connector | No firewall change; data stays inside the network until Claude receives results | Users need web or mobile; Dan accepts an exposed endpoint |
| **Who reads the contract (D2)** | Claude, on the user's plan (**Option X**) | Our own LLM inside a tool (Option Y) | No second provider route or agreement `[8 Oct 41:40]` | Extraction accuracy differs by person, or the reading must be audited or validated |
| **Where numbers come from** | A deterministic compare in code | Let Claude calculate | Money must be exact and repeatable | None foreseen |
| **Granularity of tools** | Few, mostly composite (6 tools; one big `compare`) | Many fine-grained tools | Reproducibility; fewer tool-choice errors `[8 Oct 12:29]`; deterministic steps inside | Reuse needs finer tools |
| **Evidence model** | Quote must be on the page and hold the rate and product | Trust the model's citation; or use a vendor citations feature | Cheap, exact, catches fabrication; vendor citation features have limits we noted | Spelled-out numbers matter (needs a smarter matcher) |
| **Finding pages** | Keyword plus first page plus neighbours | Embeddings or a search index; send whole files | No second model or provider route; transparent; measurable | Measured misses are too high on real contracts |
| **SAP access** | Mock behind a one-method `read()` interface | Wire a real route now; use SAP's MCP server | Route, version and login unknown; keeps the build unblocked | Dan confirms a route (the mock then proves nothing about it) |
| **Code shape** | Plain functions, thin MCP wrapper | MCP-first server | Lower maintenance; tools reusable in Phase 2; testable without MCP | None foreseen |
| **Language and packaging** | Python; `.mcpb` bundle | Node (documented best path) | Our skills and tests are Python | Laptops lack Python (open decision 0002) |
| **Guidance mechanism** | Skills plus one MCP prompt | Enforce in code only | Cheap to change; the client asked for policy in skills `[8 Oct 49:00]` | A rule must hold: move it into code and a test |
| **Logging** | A JSON line per call, counts only, to a configured folder | Log full answers or documents | Evidence of use without copying sensitive text | Audit of the answer is required (needs Phase 2) |

## 8. Control points and what each one prevents

This is the system's **defence list**. Each row says what it stops, where it lives and what test pins it.

| Control | Prevents | Where | Pinned by |
|---|---|---|---|
| Registry refuses `read_only=False` | A write tool being added | `core/registry.py` | `test_readonly.py` |
| No file-writing code outside `calllog.py` | Accidental writes to sources | code scan | `test_readonly.py` |
| SAP interface has one method | A write path to SAP, even by mistake | `mcp_servers/sap/interface.py` | `test_readonly.py` |
| `resolve_inside` | Reading outside the contract folder (path traversal) | `core/scope.py` | `test_contracts.py` |
| Quote check (on page, product, rate) | Invented or mis-attributed values | `core/citations.py` | `test_compare.py` |
| "Not checked" lists | Silent gaps | `compare.py`, `contracts.py` | `test_compare.py`, `test_contracts.py` |
| Untrusted-text notice, read-only tools | Prompt injection steering the AI | `models.py`, tools | `test_contracts.py` (hostile fixture) |
| Draft files excluded and named | Using an unsigned document | `contracts.py` | `test_contracts.py` |
| `Decimal`, rules in YAML, fixed rounding | Wrong or drifting money | `compare.py`, `rules/` | `test_compare.py` |
| Customer ambiguity returned | Checking the wrong customer | `customers.py` | `test_contracts.py` |
| Log holds counts only | Sensitive text copied into a log | `calllog.py` | `test_calllog_and_report.py` |
| Synthetic labels, client-material scan | Real data entering the repo | `scripts/check.py` | the quality gates |
| Manifest matches the tools | A tool exposed that the package does not declare | `scripts/check.py` | the quality gates |

**Threat-style view.** The realistic ways this goes wrong, and our position:

| Failure | Likelihood | Detectable? | Mitigation | Residual |
|---|---|---|---|---|
| Claude invents or garbles a quote | Medium | **Yes**, by the quote check | Term dropped and listed | Low |
| Claude quotes a real but **wrong** clause (for example the old schedule) | Medium | **Not by code** | Skills (`reading-amendments`); evidence shown; person confirms | **Medium. The main residual risk** |
| Page finder misses an unusual wording | Medium on real contracts | Partly (a "topic search found nothing" note) | Generous selection; measured recall 0.92 on synthetic | Medium |
| Contract text tries to steer Claude | Low to medium | Claude may report it | Tools read-only and scoped; skill; hostile-text test | Low in tools, medium in what Claude says |
| Wrong customer | Low | Yes (ambiguity returned) | Never guess | Low |
| Stale or wrong SAP assumption | Medium | Caveat says so | "SAP rate as at the as_of date applies to the whole period" is stated | Medium |
| Real data sent to a provider before policy sign-off | Depends on people | No (process control) | Gate in the Plan; synthetic only until then | Process risk |
| Different people get different answers | High | Only by comparing runs | Composite tool; golden set; two-person test | Medium |

## 9. Information design: where data lives and how it moves

- **Contracts:** read in place. Never copied, never stored by us. Only matched pages are returned.
- **SAP data:** read through the adapter on every call; no cache, so no stale copy to protect.
- **Slice knowledge as data:** `slices/contract_to_sap_check/` holds aliases, keywords, rules and schemas as versioned
  files, separate from code. Meaning changes without code changes, and a later phase reuses them.
- **The log is the only thing we store.** Counts, arguments, user, timing. It doubles as the adoption measure.
- **No memory.** The plug-in is stateless between calls. Per-user memory lives in the user's Claude; shared memory
  across users does not exist, by design (`[8 Oct 23:02, 25:03]`). A shared decisions store is Phase 2.
- **Identity (assumed, not verified).** The server runs as the laptop user; the SAP credential would be one service
  login. Per-person authorisation inside SAP is **not** enforced. This is Authorization option A in our approach note.

## 10. Seams: where change is cheap, where it is expensive

| Likely change | Cost | Why |
|---|---|---|
| Swap mock SAP for a real route | **Low if the interface fits; unknown otherwise** | One method, one file. But the interface was designed without seeing the real route (section 12) |
| Add a customer, alias, keyword or rule | Low | Data files, versioned |
| Change money rules (tolerance, rounding) | Low | YAML plus a test |
| Add a new term type | Medium | Model, compare, schema, skill, tests |
| Add a tool | Medium, and discouraged | Decision record; more tools degrade tool choice |
| Move extraction to our own LLM (Option Y) | Medium | Add `extract_terms` producing the same `ExtractedTerm` list; nothing above or below changes |
| Add a review queue, decision record, watcher, audit | **High; this is Phase 2** | Needs our own orchestrator and a records store; plug-in code becomes its tools layer |
| Replace the front door (Teams, web) | Medium | Needs a remote server and an authentication story |

**The evolution path.** Phase 1's `core/` functions are the *tools layer* of any later option. P2 (pipelines) or P3
(orchestrator) would add a control plane above them: a watcher, a queue, recorded decisions, an audit gateway. The
client has confirmed the tools carry forward (`[8 Oct 13:53, 14:11]`). What does **not** carry forward: Claude on the
user's plan as the loop (replaced by our orchestrator), and per-laptop logs (replaced by a shared audit store).

## 11. Quality attributes: an honest scorecard

| Attribute | Phase 1 | Notes |
|---|---|---|
| **Safety (no writes)** | Strong | Structural: no write path exists, and tests prove it |
| **Reproducibility of numbers** | Strong | Pure function of terms plus SAP data; 5-run test |
| **Reproducibility of answers** | Weak | Depends on the user's model and on following guidance |
| **Traceability** | Good | Every value has a page and quote the code checked |
| **Auditability** | Weak to partial | Tool calls only; the answer Claude gave is not captured |
| **Reviewability (human in the loop)** | Weak | The person reads the chat; no queue, no recorded decision |
| **Data minimisation** | Good | Pages not files; counts not text in the log |
| **Cost** | Strong | Near zero run cost to us; tokens on their plan |
| **Maintainability** | Good | Plain functions, small surface; risk is client-app variation and MCP/SDK change |
| **Adoption fit** | Good | Lives where users already are; one-click install; but desktop only |
| **GxP readiness** | Partial | Tools are testable; the end-to-end answer is not validated. COA vs spec would need more |
| **Security posture** | Reasonable for a pilot | Read-only, scoped, no network exposure; data-policy and identity still open |

## 12. Known weaknesses and open design questions

1. **The quote check proves presence, not correctness.** A real quote from the wrong clause passes. This is the
   largest residual risk. It can only be reduced by reviewer evidence and, later, by a second independent reading (for
   example Option Y with a different model) or a recorded human review.
2. **Phase 1 does not meet Abhishek's audit goal** (`[8 Oct 59:50]`: "data capture and audit controls on condition
   rebate control changes"). Review queue, recorded decision and audit of the answer are out by design. Say this in
   writing before the pilot.
3. **The SAP interface is designed against a mock.** `read(entity, filters, as_of)` is generic on purpose, but the
   real route (report export, API or CDS views) may shape data differently (for example keys, units, effective
   dating). This could force a rework of the adapter and of `core/sap.py`. Unknown until Dan answers.
4. **"The SAP rate as at the as_of date applies for the whole period."** A mid-period SAP change would be missed. A
   known simplification, stated in every result.
5. **The page finder is keyword search.** Measured on synthetic data only; real wording is unseen. Public samples are
   not added yet.
6. **Per-laptop logs split the usage data** unless Ingenus agrees a shared folder.
7. **Python on the laptops** (decision 0002) and **Windows-only bundle**.
8. **Skills and prompts are advice.** Anything that must hold is in code; the rest can be ignored by a model.
9. **Identity and authorisation are thin.** No per-person limits on what contracts or SAP data a user can reach.
10. **Teams-plan data terms are unverified**, and Ingenus's policy is not received (DP-20).

**Open design questions for review:** Is "evaluation only, nothing written" acceptable for the pilot in writing? Is the
indicative-exposure method (rate gap times monthly net sales, daily in partial months) acceptable to Finance? What
should happen when a contract uses a base other than net sales? Who is the named reviewer, and what do they see?

## 13. Traceability: from what the client said to what we built

| Client said | Design response | Where |
|---|---|---|
| "I like the part one for now" `[8 Oct 46:57]` | Phase 1 is the MCP plug-in only | `MCP-PlugIn/` |
| "extremely simple and extremely easy for Dan to accept" `[8 Oct 1:10:34]` | Six tools, no portal, read-only, a local extension | `core/tools.py` |
| "we are not going to use it to enter data right away" `[8 Oct 1:10:15]` | No write path; test-enforced | `registry.py`, `test_readonly.py` |
| "they have not seen the outputs" `[8 Oct 46:57]` | Every value shows page and exact quote | `models.Citation`, `citations.py` |
| "I lose control over how it's being reviewed, how the guidelines are set" `[20:00]` | Guidelines as versioned skills; tool-call log; business-level tools. **Only partly met** | `skills/v1/`, `calllog.py` |
| "reproducible results… checks before the output is presented" `[00:00]` | Deterministic compare; quote check before use | `compare.py` |
| "we do not want to send our data and have agreements with AWS yet" `[8 Oct 41:40]` | Option X: no second provider route | `docs/decisions/0001` |
| "we can never expose that outside of our own firewall" `[8 Oct 37:42]` | Desktop extension, nothing exposed | `packaging/` |
| Rate variance 5.5% vs 5.56% missed `[8 Oct 1:01:41]` | Tolerance zero; any difference is a finding | `rules/compare.v1.yaml`, test |
| Drafts to ignore (a nuance a custom connector can encode, `[8 Oct 14:50]`) | Drafts excluded by rule and named | `contracts.py` |
| Memory is per user and does not scale past a few people `[8 Oct 25:03]` | Stateless plug-in; no shared store | `developer_guide.md` §4 |

## 14. How to review or challenge this design

Questions a TAC reviewer should be able to answer from this repo:

1. **Can it write to SAP or a source file?** No. Show `test_readonly.py` and the one-method interface.
2. **Where do the numbers come from?** `compare.py`, `Decimal`, YAML rules. Nothing from the model.
3. **What if Claude lies?** The quote check, and what it cannot catch (section 12.1).
4. **What leaves the building?** Tool results go to Claude via the user's plan. Nothing else leaves. Policy is open.
5. **What happens when it cannot tell?** It says "not checked" with a reason.
6. **What is the audit trail?** Tool calls, not answers. Phase 2 for more.
7. **What does the client lose by choosing this?** Review queue, decision record, watcher, answer audit.
8. **How do we grow?** Section 10. Tools carry forward; a control plane is added above them.
9. **What would make us stop?** The extension cannot run on Ingenus's laptops, Dan will not allow it, or measured
   extraction accuracy is too inconsistent between people (then Option Y or Phase 2).
10. **What is proven versus claimed?** Offline tests prove the code. Nothing yet proves Claude Desktop behaviour, real SAP,
    or real contracts. The demo guide is how we change that.

**A useful way to attack the design:** list the ways a confident wrong answer could reach a reviewer, and check each
has either a code control (section 8) or an explicit human step. The wrong-clause case in section 12.1 is the one that
only a human step covers, which is why Phase 1 is positioned as "evidence for a reviewer", not as a check that
replaces one.
