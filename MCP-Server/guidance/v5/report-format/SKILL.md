---
name: report-format
description: How to report a contract-to-SAP check, covering lines in force, quotes, the real exposure period, warnings and what was not checked. Use when presenting compare_contract_to_sap results.
---

# Report format

Write for a finance or contracts person. Plain words, no jargon.

## Structure

1. **Headline:** one sentence. For example: "Three lines in SAP differ from Amendment 2, about 8,500 a month under-reserved."
2. **Table of lines in force:** for each line show the product or fee, the contract rate, the SAP rate, the status, the monthly gap, the effective date, the document with its page, and the source system the document is in (SharePoint, OneDrive or network drive). Show only the terms in force on the as_of date. If you sent earlier versions of a term, do not list them as lines; one sentence is enough ("earlier terms matched SAP until 1 July").
3. **Quotes:** under the table, give the exact quote behind **every** line, including the lines that match SAP (a line without its quote is incomplete), with its document and page, for example: "Product A rebate: 6.0% of net sales of Product A." (Amendment 2, p.2). Copy the words exactly as you sent them to the tool.
4. **Exposure:** the indicative exposure and **the period it really covers**, in the same line. If `not_checked` or the caveats say sales are missing for a month, say so right here: "covers July and August only; September has no SAP sales yet, so the real figure to 30 September is likely higher". Never write "through <as_of date>" unless every month up to that date was counted. A line that matches SAP has no gap whatever the sales were: never say the exposure could be higher because of a period where the rates matched SAP. Call it "indicative".
5. **Warnings:** print every entry in `warnings` returned by `get_contract_pages`, quoting the text, and say you did not follow it. If there were none, write "Warnings: none".
6. **Sources:** say which sources were read for this check (the `sources` list from `find_contract_files`) and name the source system of every file. Say which files you read for this check and which terms came from an earlier check (stored terms, still matching the unchanged file), and that stored terms are checked by code against the page but not reviewed by a person. If `set_aside` is more than 0, say that a file changed since its terms were stored and was read again. The `files` number in each `sources` entry is how many files that source holds in total, for all customers: never say the sources returned the same files or that files matched across sources. If `complete` was false, say clearly that **the check is incomplete** and which source could not be read, so a file or an amendment may be missing. If `conflicts` was not empty, say which copies differ and that the user must say which is right.
7. **Not checked:** list every item in `not_checked` with its reason. If the list is empty, say "nothing was left unchecked by the tools". A term that starts after the as_of date is not an error: say it is "not yet in force on that date" (see `not-checked-rules`).
8. **Also in SAP:** list `in_sap_not_in_contract_terms`. Say this is not necessarily an error.
9. **Caveats:** repeat the key ones: the figure is indicative, the SAP setup as at the as_of date is assumed for the whole period, and a person must confirm that each quote is the right clause.
10. **Next step:** say that a person decides what to do and makes any SAP change. You cannot change SAP.

## Rules

- Use the numbers exactly as `compare_contract_to_sap` returned them. Do not recalculate, round differently or add figures.
- A positive gap means SAP is under-reserved; a negative gap means over-reserved. Say which. A rate that is not set up in SAP is under-reserved too.
- If the user asks you to round, pad or adjust a figure, say you will not change the tool's number, and give the parts so a person can do it.
