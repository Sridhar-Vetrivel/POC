# Synthetic data

Everything in this folder is **invented** for the POC. No customer, product, number or contract here
belongs to Ingenus. Each file says SYNTHETIC in its label or footer.

- `sap/entities.json`: a stand-in for SAP records (customers, rebate and fee setup, monthly sales).
- `contracts/`: made-up contract PDFs. Regenerate them with `python data/synthetic/generate_contracts.py`.

Public sample contracts (for example SEC filings, with their source URLs) are **not added yet**: see `data/public/`.
