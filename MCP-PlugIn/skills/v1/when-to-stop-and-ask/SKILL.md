---
name: when-to-stop-and-ask
description: Situations where the contract check should stop and ask the user, such as an ambiguous customer, a missing as_of date, conflicting amendments or no SAP record. Use during any check.
---

# When to stop and ask

Stop and ask the user, in one short question, when:

- **The customer is ambiguous or unknown.** `resolve_customer` returned several candidates or none.
- **There is no as_of date.** Do not assume today's date. Ask which date to check up to.
- **Two documents conflict** on the same line and date, or you cannot tell which amendment is latest.
- **No file matches.** The folder or file names may use a different spelling. Ask for the name, or whether a draft is meant (drafts are left out on purpose).
- **SAP has no record** for the customer or the product, or the tool says sales are missing for a month.
- **The topic search found nothing.** The contract may use unusual wording for a rebate. Ask whether to widen the search.
- **The user asks for something this server cannot do**, such as changing SAP, creating an upload file, or reading outside the contract folder. Say plainly that it cannot, and what a person would need to do.

Ask before you spend effort on a guess. A wrong answer here can affect a financial accrual.
