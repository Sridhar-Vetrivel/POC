# Expected results: Onedrive (SYNTHETIC)

SYNTHETIC: invented for the Ingenus POC. Not Ingenus data. Customers, products and numbers are made up.

Run with as_of **2026-08-31**, using the terms in `expected_terms.v1.json` (the signed amendment, never the DRAFT).

## Chain C (SYN-CUST-2001)

Amendment 1 (a table) lowers Product B from 3.5% to 3.0% (SAP over-reserved by 750.00 a month) and raises the fee from 1.0% to 1.75% (under-reserved by 1,500.00 a month): the lines go opposite ways and net to 750.00. Amendment 2 is an unsigned DRAFT.

- Total monthly gap: **750.00**
- Indicative exposure to 2026-08-31: **3750.00**
- rebate:Product B: variance
- rebate:Product C: match
- admin_fee: variance

## Chain D (SYN-CUST-2002)

Amendment 1 (1 May 2026) adds Product B at 2.5% with no SAP setup. Product D's SAP setup ended on 28 Feb 2026 (expired). The master has a blank page (a scanned page with no text).

- Total monthly gap: **2100.00**
- Indicative exposure to 2026-08-31: **8400.00**
- rebate:Product A: match
- rebate:Product B: not_set_up_in_sap
- rebate:Product D: not_set_up_in_sap
- admin_fee: match
