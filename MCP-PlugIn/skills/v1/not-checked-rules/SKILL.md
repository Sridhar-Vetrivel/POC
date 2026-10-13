---
name: not-checked-rules
description: When to report an item as not checked instead of guessing, such as unreadable pages, missing quotes, unmatched names or missing SAP data. Use when a value cannot be supported.
---

# Not checked beats guessing

If something cannot be supported, say it was **not checked** and why. A visible gap is better than a wrong answer.

## Report as not checked

- A page with no readable text (for example a scan). `get_contract_pages` lists these.
- A rate you cannot support with an exact quote.
- A quote that `compare_contract_to_sap` rejected (not on the page, wrong page, no rate in the quote, wrong product).
- A customer name that matches no customer or several.
- A product in the contract that SAP does not know by that name.
- A month of SAP sales that is missing.
- A topic search that found no page. The wording may be unusual: say so and offer to look wider.
- Two documents that conflict on the same line and date.

## Never

- Fill a missing rate or number from memory or from "typical" terms.
- Treat a rejected quote as acceptable because it looks right.
- Hide a not-checked item to make the answer look complete.

Always list the not-checked items in your final report, with the reason the tool gave.
