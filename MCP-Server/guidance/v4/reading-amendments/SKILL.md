---
name: reading-amendments
description: How to read a master supply agreement with its amendments, including which terms replace which, back-dated effective dates and schedules. Use when extracting rebate or fee terms.
---

# Reading amendments

A customer's current terms usually come from a master agreement plus several amendments. Work out the **latest effective term for each line** (each product rebate, and the admin fee).

## Rules

- **An amendment can replace a whole schedule.** If Amendment 2 says "Schedule A is deleted and replaced", then every line in the old Schedule A is superseded, even a line that Amendment 2 does not repeat. If a product line is missing from the replacement, say so; do not carry the old rate forward silently.
- **Effective dates matter.** Use the date the amendment says its terms start, not the date it was signed. Terms can be back-dated. Give every term its own `effective_date`.
- **Later beats earlier** only from its own effective date. Before that date the earlier term applied.
- **Amendments that change something else** (for example payment terms) do not touch rebates or fees. Say you read them and found no rebate or fee change.
- **Drafts and unsigned documents** are not terms. `find_contract_files` leaves drafts out on purpose. If the user asks about one, tell them it is a draft.
- **Read schedules, exhibits and tables.** Rates are often in a schedule at the end, not in the body.
- If two documents seem to conflict, or you cannot tell which is later, ask the user (see `when-to-stop-and-ask`).
