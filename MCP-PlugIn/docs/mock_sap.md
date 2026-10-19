# The mock SAP: how it is built and how it works

The plug-in has **no access to SAP**. Every SAP answer in the demo comes from a small JSON file of **synthetic**
records, read through the same interface a real SAP connection will use later. This page explains that file, the
code that reads it, and how a real adapter will replace it.

Related: [developer guide](../../developer_guide.md) · [v1 proposal](../../docs/v1_impact_analysis_and_proposal.md)

---

## 1. Why a mock

- There is no SAP access in pre-sales, and the route to Ingenus's SAP is not decided. SAP is on RISE (AWS), managed
  by SAP, reached over an IPSEC tunnel (8 Oct call, 31:58, 33:10, 43:04). Which read route (tables, CDS views or
  something else) and which read-only login are open questions for Dan.
- Only synthetic or public data may be used until Ingenus's data policy is signed off (CLAUDE.md rule 9).
- We must not invent real-looking SAP tables, T-codes or BAPIs. So the mock uses **business-level** names
  (`customers`, `rebate_setup`, `sales_volume`), not SAP object names.

## 2. The pieces

| Piece | File | What it does |
|---|---|---|
| Interface | [`mcp_servers/sap/interface.py`](../../mcp_servers/sap/interface.py) | `SapReader` with **one** method, `read(ReadQuery) -> ReadResult`. No create, change or delete method exists |
| Mock adapter | [`mcp_servers/sap/adapters/mock.py`](../../mcp_servers/sap/adapters/mock.py) | `MockSapReader`: loads the JSON file and answers `read()` from it |
| Real adapter | [`mcp_servers/sap/adapters/real_stub.py`](../../mcp_servers/sap/adapters/real_stub.py) | `RealSapReader`: a placeholder. `read()` raises `NotImplementedError` (`TODO(verify)`) |
| Data | [`data/synthetic/sap/entities.json`](../data/synthetic/sap/entities.json) | The synthetic records |
| Callers | [`src/ingenus_plugin/core/sap.py`](../src/ingenus_plugin/core/sap.py) | Picks the adapter and turns rows into typed results for the tools |

The interface lives in `mcp_servers/` (shared, domain-neutral: rule 1), so it can serve any slice and Phase 2. The
business meaning (rebates, fees) lives in the plug-in's `sap.py` and in the data, not in the interface.

## 3. The data file

`entities.json` has a label and three tables. Every value is invented.

```json
{
  "_label": "SYNTHETIC: invented for the Ingenus POC. Not Ingenus data. ...",
  "customers":     [ { "customer_id": "SYN-CUST-0001", "name": "Chain X" }, ... ],
  "rebate_setup":  [ { "customer_id": "SYN-CUST-0001", "kind": "rebate", "product": "Product A",
                       "rate_pct": "4.0", "basis": "product_net_sales",
                       "valid_from": "2025-01-01", "valid_to": null }, ... ],
  "sales_volume":  [ { "customer_id": "SYN-CUST-0001", "month": "2026-07",
                       "product": "Product A", "net_sales": "200000.00" }, ... ]
}
```

| Table | Rows | Fields | Meaning |
|---|---|---|---|
| `customers` | 5 | `customer_id`, `name` | Chain X, Chain Y, Wholesaler Z, Regional Pharmacy East, Regional Pharmacy West (`SYN-CUST-0001` to `0005`) |
| `rebate_setup` | 5 | `customer_id`, `kind` (`rebate` or `admin_fee`), `product` (null for a fee), `rate_pct`, `basis` (`product_net_sales` or `total_net_sales`), `valid_from`, `valid_to` | What "SAP" has set up: the rate it accrues at, from when to when |
| `sales_volume` | 40 | `customer_id`, `month` (`YYYY-MM`), `product`, `net_sales` | Monthly net sales, January to August 2026 |

What is in it today:

| Customer | Set up in "SAP" | Monthly net sales |
|---|---|---|
| Chain X (`SYN-CUST-0001`) | Product A rebate 4.0%, Product B rebate 3.0%, admin fee 2.0% of total. **No Product C line** | A 200,000; B 150,000; C 50,000 |
| Chain Y (`SYN-CUST-0002`) | Product A rebate 5.0% | A 80,000 |
| Wholesaler Z (`SYN-CUST-0003`) | Admin fee 1.5% of total | A 120,000 |
| Regional Pharmacy East and West | Nothing | None (used to test an ambiguous name) |

Rules the data follows:

- **Numbers are strings** (`"4.0"`, `"200000.00"`), read as `Decimal`, never as floats, so money is exact.
- **The `_label` must say SYNTHETIC.** `MockSapReader` refuses to load a file without it, and the `synthetic-label`
  gate in `scripts/check.py` checks it too.
- **Rates are percentages:** `"4.0"` means 4%.
- **No September sales:** asking "as of 30 Sep 2026" deliberately shows how missing months are reported.

## 4. How a read works

Every read is a `ReadQuery`:

| Field | Example | Used for |
|---|---|---|
| `entity` | `"rebate_setup"` | Which table |
| `filters` | `{"customer_id": "SYN-CUST-0001"}` | Exact-match filters on any field |
| `as_of` | `2026-08-31` | Keep only rows valid on that date (`valid_from <= as_of <= valid_to`, a null `valid_to` means open) |
| `period_start`, `period_end` | `"2026-07"`, `"2026-08"` | Keep only rows whose `month` is in the range |

`MockSapReader.read()` does, in order:

```
read(query)
├─ unknown entity?        → no rows, with a note ("Unknown entity ...")
├─ copy the table's rows
├─ apply each filter      → keep rows where str(row[key]) == value
├─ if as_of:              → _valid_on(row, as_of)
├─ if a period:           → _in_period(row, start, end)   (rows without a month are kept)
└─ → ReadResult(rows, source="mock adapter (synthetic data, not Ingenus data)")
```

The file is read when the reader is created, and `core/sap.py` creates a new reader for **every tool call**
(`get_reader()`), so an edit to the file shows up on the next call without a restart.

## 5. Who calls it

```
get_rebate_setup / compare_contract_to_sap
  └─ core/sap.py: rebate_setup(reader, customer_id, as_of)
       ├─ customer_exists()  → read(entity="customers", filters={customer_id})
       └─ read(entity="rebate_setup", filters={customer_id}, as_of=as_of)
            → SetupLine objects (Decimal rate, basis, validity)

get_sales_volume / compare_contract_to_sap
  └─ core/sap.py: sales_volume(reader, customer_id, period_start, period_end)
       ├─ checks both months look like YYYY-MM and start <= end
       ├─ customer_exists()
       └─ read(entity="sales_volume", filters={customer_id}, period_start, period_end)
            → MonthlyVolume objects (Decimal net sales)

resolve_customer
  └─ customer_exists()  (the name is matched in the slice's alias table; the id is then checked here)
```

Which adapter is used is set by `INGENUS_SAP_ADAPTER`: `mock` (default) or `real` (the stub, which refuses to run).
The file is set by `INGENUS_SAP_MOCK_FILE`.

## 6. How the read-only rule is enforced

- The interface has one method, `read()`. A test fails if another method appears
  (`test_the_sap_interface_has_a_single_read_method` in `tests/test_readonly.py`).
- No code outside `calllog.py` may write files (also tested), so no tool can change `entities.json`.
- The real adapter is a stub that refuses to run, so nothing can reach a real system by accident.

## 7. Changing the data for a test

| You want | Edit |
|---|---|
| A different rate in "SAP" | `rate_pct` on the `rebate_setup` row |
| A line missing from "SAP" | Delete that `rebate_setup` row |
| A rate change over time | Set `valid_to` on the old row and add a new row with a later `valid_from` |
| More months of sales | Add `sales_volume` rows (one per month and product) |
| A new customer | Add a `customers` row **and** an entry in `slices/contract_to_sap_check/ontology/customers.v1.yaml` (the alias table) |

**Which copy to edit:** the tests and `python -m ingenus_plugin.server` read `MCP-PlugIn/data/synthetic/sap/entities.json`.
The installed Claude Desktop extension reads **its own copy** (`<extension folder>/data/sap/entities.json`, set by
the manifest). Edit that copy, or rebuild and reinstall the bundle. The demo guide, section 7, has the commands.

If you change the Chain X data, the expected demo numbers (8,500.00 a month, 17,000.00 exposure) change too, and the
tests that check those numbers will fail. Restore the file afterwards.

## 8. How a real adapter replaces it

1. Implement `read()` in `real_stub.py` (or a new adapter) for the same three entities, returning rows with the same
   fields. How it gets them (report export, released API, CDS views or other) is the open question for Dan; do not
   name SAP objects until he confirms them.
2. Use a read-only service login. The adapter never writes, and the interface gives it no way to.
3. Set `INGENUS_SAP_ADAPTER=real`. Nothing above the interface changes: not `core/sap.py`, not the tools, not
   `compare.py`.

Open questions for Dan (from the plan): the route over the tunnel; ECC or S/4 and the RISE edition; how rebate and fee
setup and monthly net sales are held in their SAP; a read-only login; how fresh the data must be.
