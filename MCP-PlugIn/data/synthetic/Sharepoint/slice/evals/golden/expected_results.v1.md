# Expected results: Sharepoint (SYNTHETIC)

SYNTHETIC: invented for the Ingenus POC. Not Ingenus data. Customers, products and numbers are made up.

Run with as_of **2026-08-31**, using the terms in `expected_terms.v1.json` (the signed amendment, never the DRAFT).

## Chain A (SYN-CUST-1001)

Amendment 1 raises the Product A rebate from 3.0% to 4.5% from 1 Feb 2026; SAP still has 3.0%. Amendment 2 is an unsigned DRAFT (Product A 5.5%) and must not be used.

- Total monthly gap: **1800.00**
- Indicative exposure to 2026-08-31: **12600.00**
- rebate:Product A: variance
- rebate:Product B: match
- admin_fee: match

## Chain B (SYN-CUST-1002)

Amendment 1 (1 Jun 2026) adds Product D at 3.5%, which SAP has no setup for. Product C's SAP setup ended on 31 Mar 2026 (expired) although the contract still pays 4.0%. Product A and the fee match.

- Total monthly gap: **3800.00**
- Indicative exposure to 2026-08-31: **11400.00**
- rebate:Product A: match
- rebate:Product C: not_set_up_in_sap
- rebate:Product D: not_set_up_in_sap
- admin_fee: match
