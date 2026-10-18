---
name: extraction-schema
description: The exact fields and citation format for each rebate or admin-fee term passed to compare_contract_to_sap. Use when turning contract wording into terms.
---

# Extraction schema

Pass a list of terms to `compare_contract_to_sap`. Each term has these fields:

| Field | Meaning |
|---|---|
| `kind` | `rebate` (a percent of one product's net sales) or `admin_fee` (a percent of total net sales) |
| `product` | The product name as written in the contract. `null` for an admin fee |
| `rate_pct` | The rate as a plain number: write `6` for 6%, `5.56` for 5.56% |
| `effective_date` | When this rate starts, `YYYY-MM-DD`, per the contract |
| `citation.document` | The `document_id` exactly as returned by `find_contract_files` |
| `citation.page` | The 1-based page number the quote is on |
| `citation.clause` | The clause or section label, if there is one (for example "Schedule A") |
| `citation.quote` | **Exact words copied from that page** |

## Quote rules (code checks these, and a failed check means the term is not used)

- Copy the words exactly, including punctuation and the percent sign. Never paraphrase or tidy them.
- The quote must contain the rate, and for a rebate it must name the product.
- Quote the whole line or sentence that holds the rate, not a fragment.
- Use the page number shown by `get_contract_pages`, not a printed page number from the document.
- One term per rate. Do not combine two products into one quote.

If you cannot find an exact quote for a rate, do not guess a term. Tell the user which rate you could not support.
