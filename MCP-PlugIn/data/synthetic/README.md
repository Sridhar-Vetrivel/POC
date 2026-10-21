# Synthetic data

Everything in this folder is **invented** for the POC. No customer, product, number or contract here
belongs to Ingenus. Each file says SYNTHETIC in its label or footer.

## The original set (v0, and the verified Chain X demo)

- `sap/entities.json`: a stand-in for SAP records (customers, rebate and fee setup, monthly sales).
- `contracts/`: made-up contract PDFs (Chain X, Chain Y, Wholesaler Z, and 24 bulk contracts). Regenerate with
  `python MCP-PlugIn/data/synthetic/generate_contracts.py` (from the repo root).

## The three source datasets (v1)

One dataset per place the server reads from. Each has two chains of its own, so what the server finds tells you
which source it came from.

| Folder | Put the PDFs on | Chains | Customer ids |
|---|---|---|---|
| `Sharepoint/` | the SharePoint library folder | Chain_A, Chain_B | SYN-CUST-1001, 1002 |
| `Onedrive/` | a OneDrive folder | Chain_C, Chain_D | SYN-CUST-2001, 2002 |
| `Network-Drive/` | the network share | Chain_E, Chain_F | SYN-CUST-3001, 3002 |

Inside each folder:

- `contracts/`: **copy the contents of this folder to the real drive** (it holds `Chain_A/`, `Chain_B/` ...). Only PDFs; nothing else goes on the drive.
- `slice/`: what the server needs next to the contracts, and stays on the server side: `topics.v1.yaml`, `ontology/customers.v1.yaml`,
  `rules/compare.v1.yaml`, `schemas/contract_terms.v1.json`, and `evals/golden/` (page labels, the terms to feed the check, and the expected results).
- `sap/entities.json`: the mock SAP records for that dataset's customers.

The ontology and the SAP records are written for each dataset's customers. The topics, rules and schema are policy, not data, so they
are copies of the base slice (the schema is generated from code; a test keeps it in step).

What each chain contains (as of 31 Aug 2026; the full story and figures are in `slice/evals/golden/expected_results.v1.md`):

| Chain | Situations | Gap / month | Exposure |
|---|---|---|---|
| A | rate variance, unsigned DRAFT | 1,800.00 | 12,600.00 |
| B | product missing in SAP, expired SAP setup, matches | 3,800.00 | 11,400.00 |
| C | variance both ways (table), unsigned DRAFT | 750.00 | 3,750.00 |
| D | product missing in SAP, expired SAP setup, blank page | 2,100.00 | 8,400.00 |
| E | variance over 8 months (terms on page 4), unsigned DRAFT | 1,100.00 | 8,800.00 |
| F | product missing in SAP, expired SAP setup, matches | 1,900.00 | 3,800.00 |

"Expired" means the SAP setup ended (`valid_to`) before the as-of date while the contract still pays the rate. The engine has no notion of a contract
end date, so a contract that simply ran out is not modelled.

Regenerate (deterministic): `python MCP-PlugIn/data/synthetic/generate_datasets.py`.

### Trying a dataset locally (before it is on the drive)

Set these (in `MCP-Server/.env`, or the environment), pointing at one dataset:

```
INGENUS_DOC_SOURCE=local
INGENUS_CONTRACTS_DIR=MCP-PlugIn/data/synthetic/Sharepoint/contracts
INGENUS_SLICE_DIR=MCP-PlugIn/data/synthetic/Sharepoint/slice
INGENUS_SAP_MOCK_FILE=MCP-PlugIn/data/synthetic/Sharepoint/sap/entities.json
```

For the real source, change `INGENUS_DOC_SOURCE` (`sharepoint`, `onedrive` or `network`) and its folder setting; keep the slice and SAP lines.

Public sample contracts (for example SEC filings, with their source URLs) are **not added yet**: see `../public/`.
