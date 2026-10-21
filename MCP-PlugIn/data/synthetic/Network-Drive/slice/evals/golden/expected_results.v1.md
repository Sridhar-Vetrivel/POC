# Expected results: Network-Drive (SYNTHETIC)

SYNTHETIC: invented for the Ingenus POC. Not Ingenus data. Customers, products and numbers are made up.

Run with as_of **2026-08-31**, using the terms in `expected_terms.v1.json` (the signed amendment, never the DRAFT).

## Chain E (SYN-CUST-3001)

Amendment 1 (1 Jan 2026, terms on page 4 after two pages of background) raises Product A from 2.5% to 3.5%; SAP still has 2.5%, so eight months of exposure. Amendment 2 is an unsigned DRAFT.

- Total monthly gap: **1100.00**
- Indicative exposure to 2026-08-31: **8800.00**
- rebate:Product A: variance
- rebate:Product B: match
- admin_fee: match

## Chain F (SYN-CUST-3002)

Amendment 1 (1 Jul 2026) adds Product A at 2.0% with no SAP setup. Product D's SAP setup ended on 30 Apr 2026 (expired). Product C and the fee match.

- Total monthly gap: **1900.00**
- Indicative exposure to 2026-08-31: **3800.00**
- rebate:Product A: not_set_up_in_sap
- rebate:Product C: match
- rebate:Product D: not_set_up_in_sap
- admin_fee: match
