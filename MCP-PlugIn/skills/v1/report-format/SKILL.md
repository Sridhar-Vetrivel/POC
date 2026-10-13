---
name: report-format
description: How to report a contract-to-SAP check, covering what differs, since when, indicative exposure and what was not checked. Use when presenting compare_contract_to_sap results.
---

# Report format

Write for a finance or contracts person. Plain words, no jargon.

## Structure

1. **Headline:** one sentence. For example: "Three lines in SAP differ from Amendment 2, about 8,500 a month under-reserved."
2. **Table of lines:** for each line show the product or fee, the contract rate, the SAP rate, the status, the monthly gap and the effective date. Add the page number of the quote.
3. **Exposure:** the indicative exposure and the period it covers. Call it "indicative".
4. **Not checked:** list every item in `not_checked` with its reason. If the list is empty, say "nothing was left unchecked by the tools".
5. **Also in SAP:** list `in_sap_not_in_contract_terms`. Say this is not necessarily an error.
6. **Caveats:** repeat the key ones: the figure is indicative, the SAP setup as at the as_of date is assumed for the whole period, and a person must confirm that each quote is the right clause.
7. **Next step:** say that a person decides what to do and makes any SAP change. You cannot change SAP.

## Rules

- Use the numbers exactly as `compare_contract_to_sap` returned them. Do not recalculate, round differently or add figures.
- A positive gap means SAP is under-reserved; a negative gap means over-reserved. Say which.
- Show the exact quote on request.
