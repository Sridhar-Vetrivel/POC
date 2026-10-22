# Synthetic data

Everything in this folder is **invented** for the POC. No customer, product, number or contract here
belongs to Ingenus. Each file says SYNTHETIC in its label or footer.

## The original set (v0, and the verified Chain X demo)

- `sap/entities.json`: a stand-in for SAP records (customers, rebate and fee setup, monthly sales).
- `contracts/`: made-up contract PDFs (Chain X, Chain Y, Wholesaler Z, and 24 bulk contracts). Regenerate with
  `python MCP-PlugIn/data/synthetic/generate_contracts.py` (from the repo root).

## The three source folders (v1)

One folder per place the server reads contracts from. Each holds only PDFs, in `Chain_*/` folders, and has two chains of its own, so what the
server finds tells you which source it came from. **Copy the contents of a folder to the matching real location.**

| Folder | Put the PDFs on | Chains | Customer ids |
|---|---|---|---|
| `Sharepoint/` | the SharePoint library folder | Chain_A, Chain_B | SYN-CUST-1001, 1002 |
| `Onedrive/` | a OneDrive folder | Chain_C, Chain_D | SYN-CUST-2001, 2002 |
| `Network-Drive/` | the network share | Chain_E, Chain_F | SYN-CUST-3001, 3002 |

Where a contract is stored changes nothing else, so there is **one** of each of these, shared by every source:

- **The customer ontology:** `slices/contract_to_sap_check/ontology/customers.v1.yaml` (the six chains are added after Chain X, Y, Z and the Regionals).
- **The mock SAP:** `sap/entities.json` here (the six customers, their rebate setup and monthly sales are added; `MCP-Server/data/sap/entities.json` is kept equal).
- **Rules, topics and schema:** the slice's own files, not copied.
- **Page labels, the terms to feed the check, and the expected results:** `slices/contract_to_sap_check/evals/golden/source_datasets.v1.json` and `.md`.

What each chain contains (as of 31 Aug 2026; the full story and figures are in `source_datasets.v1.md`):

| Chain | Situations | Gap / month | Exposure |
|---|---|---|---|
| A | rate variance, unsigned DRAFT | 1,800.00 | 12,600.00 |
| B | product missing in SAP, expired SAP setup, matches | 3,800.00 | 11,400.00 |
| C | variance both ways (a table), unsigned DRAFT | 750.00 | 3,750.00 |
| D | product missing in SAP, expired SAP setup, blank page | 2,100.00 | 8,400.00 |
| E | variance over 8 months (terms on page 4), unsigned DRAFT | 1,100.00 | 8,800.00 |
| F | product missing in SAP, expired SAP setup, matches | 1,900.00 | 3,800.00 |

"Expired" means the SAP setup ended (`valid_to`) before the as-of date while the contract still pays the rate. The engine has no notion of a contract
end date, so a contract that simply ran out is not modelled.

Regenerate (deterministic; it removes and re-adds only the customers with ids from SYN-CUST-1001 up): `python MCP-PlugIn/data/synthetic/generate_datasets.py`.

### Trying a source folder locally (before it is on the drive)

Only the source changes; the ontology, rules and SAP are the defaults:

```
INGENUS_DOC_SOURCE=local
INGENUS_CONTRACTS_DIR=MCP-PlugIn/data/synthetic/Sharepoint
```

For the real source, set `INGENUS_DOC_SOURCE` to `sharepoint`, `onedrive` or `network` and its folder setting.

Public sample contracts (for example SEC filings, with their source URLs) are **not added yet**: see `../public/`.
