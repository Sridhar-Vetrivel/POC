---
name: when-to-stop-and-ask
description: When the contract check should stop and ask the user (ambiguous customer, no as_of date, conflicting amendments) and when it should carry on and report a gap as not checked. Use during any check.
---

# When to stop and ask, and when to carry on

Ask only when the answer would change the result. Otherwise do the check and report what you could not do. People using this will not tolerate extra questions.

## Stop and ask, in one short question

- **The customer is ambiguous or unknown.** `resolve_customer` returned several candidates or none.
- **There is no as_of date.** Ask which date to check up to. Do not assume today's date, and do not offer it as a default. Do not call any other tool first except `resolve_customer` and `find_contract_files`.
- **Two documents conflict** on the same line and date, or you cannot tell which amendment is latest.
- **No file at all matches the customer.** The folder or file names may use a different spelling. Ask for the name, or whether a draft is meant (drafts are left out on purpose).

## Do not ask: carry on and report

- **Only amendments, no master agreement.** Check what is on file, and say that other terms (other products, an admin fee) are unconfirmed because no master agreement was found.
- **A page cannot be read** (for example a scan). Report it as not checked, say what that page might hold, and ask for a readable copy as a next step.
- **The topic search found nothing.** Say the wording may be unusual and offer to look wider after the report.
- **SAP sales are missing for a month.** The tool returns the other months. Report the missing month as not checked and say the exposure covers only the months that were counted.
- **SAP has no record** of a product: report it as not checked.

## Say plainly, without a question

- **The user asks for something this server cannot do**, such as changing SAP, creating an upload file, or reading outside the contract folder. Say it cannot, and what a person would need to do.

A wrong answer here can affect a financial accrual, so never guess a missing date, customer or rate.
