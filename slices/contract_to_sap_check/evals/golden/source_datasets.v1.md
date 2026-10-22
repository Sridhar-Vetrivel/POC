# Expected results for the source datasets (SYNTHETIC)

SYNTHETIC: invented for the Ingenus POC. Not Ingenus data. Customers, products and numbers are made up.

Run with as_of **2026-08-31**, using the terms in `source_datasets.v1.json` (the signed amendment, never the DRAFT). The customers are in the shared ontology and the shared mock SAP; the source only says where the PDFs are.

## Sharepoint

### Chain A (SYN-CUST-1001)

Amendment 1 raises the Product A rebate from 3.0% to 4.5% from 1 Feb 2026; SAP still has 3.0%. Amendment 2 is an unsigned DRAFT (Product A 5.5%) and must not be used.

- Total monthly gap: **1800.00**
- Indicative exposure to 2026-08-31: **12600.00**
- rebate:Product A: variance
- rebate:Product B: match
- admin_fee: match

### Chain B (SYN-CUST-1002)

Amendment 1 (1 Jun 2026) adds Product D at 3.5%, which SAP has no setup for. Product C's SAP setup ended on 31 Mar 2026 (expired) although the contract still pays 4.0%. Product A and the fee match.

- Total monthly gap: **3800.00**
- Indicative exposure to 2026-08-31: **11400.00**
- rebate:Product A: match
- rebate:Product C: not_set_up_in_sap
- rebate:Product D: not_set_up_in_sap
- admin_fee: match

## Onedrive

### Chain C (SYN-CUST-2001)

Amendment 1 (a table) lowers Product B from 3.5% to 3.0% (SAP over-reserved by 750.00 a month) and raises the fee from 1.0% to 1.75% (under-reserved by 1,500.00 a month): the lines go opposite ways and net to 750.00. Amendment 2 is an unsigned DRAFT.

- Total monthly gap: **750.00**
- Indicative exposure to 2026-08-31: **3750.00**
- rebate:Product B: variance
- rebate:Product C: match
- admin_fee: variance

### Chain D (SYN-CUST-2002)

Amendment 1 (1 May 2026) adds Product B at 2.5% with no SAP setup. Product D's SAP setup ended on 28 Feb 2026 (expired). The master has a blank page (a scanned page with no text).

- Total monthly gap: **2100.00**
- Indicative exposure to 2026-08-31: **8400.00**
- rebate:Product A: match
- rebate:Product B: not_set_up_in_sap
- rebate:Product D: not_set_up_in_sap
- admin_fee: match

## Network-Drive

### Chain E (SYN-CUST-3001)

Amendment 1 (1 Jan 2026, terms on page 4 after two pages of background) raises Product A from 2.5% to 3.5%; SAP still has 2.5%, so eight months of exposure. Amendment 2 is an unsigned DRAFT.

- Total monthly gap: **1100.00**
- Indicative exposure to 2026-08-31: **8800.00**
- rebate:Product A: variance
- rebate:Product B: match
- admin_fee: match

### Chain F (SYN-CUST-3002)

Amendment 1 (1 Jul 2026) adds Product A at 2.0% with no SAP setup. Product D's SAP setup ended on 30 Apr 2026 (expired). Product C and the fee match.

- Total monthly gap: **1900.00**
- Indicative exposure to 2026-08-31: **3800.00**
- rebate:Product A: not_set_up_in_sap
- rebate:Product C: match
- rebate:Product D: not_set_up_in_sap
- admin_fee: match
