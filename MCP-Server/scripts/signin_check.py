"""Live check of V1-4 and V1-6 against the real dev tenant. Run by hand; not part of pytest.

1. Signs you in through the browser as the "Ingenus POC Desktop Client" app (a public client: no secret).
2. Calls the running server with the token it gets for the server app's access_as_user scope.
3. Reads the Chain X contracts (from SharePoint if the server is set to) and runs the comparison.

Start the server first, in another terminal:   python -m ingenus_mcp.server
Then:                                          python MCP-Server/scripts/signin_check.py

Settings come from MCP-Server/.env (see .env.example). Nothing secret is printed: the token is
never shown, only who signed in and what the server returned.
"""

from __future__ import annotations

import json
import os
import sys

import msal
import requests

from ingenus_mcp.core.config import load_env_file

load_env_file()
TENANT = os.environ.get("INGENUS_TENANT_ID", "")
SERVER_APP = os.environ.get("INGENUS_SERVER_CLIENT_ID", "")
CLIENT_APP = os.environ.get("INGENUS_CLIENT_ID", "")
URL = os.environ.get("INGENUS_PUBLIC_URL", "http://127.0.0.1:8765/mcp")
SCOPE = f"api://{SERVER_APP}/{os.environ.get('INGENUS_REQUIRED_SCOPE', 'access_as_user')}"
AMEND2 = "Chain_X/Chain_X_Amendment_2_2026.pdf"

TERMS = [  # what a careful Claude extracts from Chain X Amendment 2 (synthetic)
    ("rebate", "Product A", "6", "Product A rebate: 6.0% of net sales of Product A."),
    ("rebate", "Product B", "3", "Product B rebate: 3.0% of net sales of Product B."),
    ("rebate", "Product C", "5", "Product C rebate: 5.0% of net sales of Product C (new)."),
    ("admin_fee", None, "2.5", "Administrative fee: 2.5% of total net sales of all Products."),
]


def sign_in() -> tuple[str, str]:
    app = msal.PublicClientApplication(
        CLIENT_APP, authority=f"https://login.microsoftonline.com/{TENANT}"
    )
    print(
        "A browser window opens. Sign in with an account in the dev tenant (not your Psiog account)."
    )
    result = app.acquire_token_interactive(scopes=[SCOPE], prompt="select_account")
    if "access_token" not in result:
        sys.exit(
            f"Sign-in failed: {result.get('error')}: {str(result.get('error_description'))[:300]}"
        )
    claims = result.get("id_token_claims", {})
    return result["access_token"], claims.get("preferred_username", "(unknown)")


def call(token: str | None, method: str, params: dict | None = None) -> requests.Response:
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    return requests.post(URL, json=body, headers=headers, timeout=120)


def tool(token: str, name: str, arguments: dict) -> dict:
    response = call(token, "tools/call", {"name": name, "arguments": arguments})
    if response.status_code != 200:
        sys.exit(f"{name}: HTTP {response.status_code}")
    line = next(x for x in response.text.splitlines() if x.startswith("data:"))
    result = json.loads(line[5:])["result"]
    if result.get("isError"):
        sys.exit(f"{name} failed: {result['content'][0]['text'][:400]}")
    return result["structuredContent"]


def main() -> None:
    if not (TENANT and SERVER_APP and CLIENT_APP):
        sys.exit("Set INGENUS_TENANT_ID, INGENUS_SERVER_CLIENT_ID and INGENUS_CLIENT_ID in .env.")
    refused = call(None, "tools/list")
    print(f"1. No token -> HTTP {refused.status_code} (401 means the server demands sign-in)")

    token, who = sign_in()
    print(f"2. Signed in as {who}")

    files = tool(token, "find_contract_files", {"customer": "Chain X"})
    names = [f["document_id"] for f in files["files"]]
    print(
        f"3. find_contract_files: {len(names)} file(s), draft left out: {files['excluded_drafts']}"
    )
    print(f"   {files['note']}")

    terms = [
        {
            "kind": kind,
            "product": product,
            "rate_pct": rate,
            "effective_date": "2026-07-01",
            "citation": {"document": AMEND2, "page": 2, "clause": "Schedule A", "quote": quote},
        }
        for kind, product, rate, quote in TERMS
    ]
    result = tool(
        token,
        "compare_contract_to_sap",
        {"customer_id": "SYN-CUST-0001", "as_of": "2026-08-31", "terms": terms},
    )
    print(
        f"4. compare: monthly gap {result['total_monthly_gap']}, exposure "
        f"{result['total_indicative_exposure']}, not checked: {len(result['not_checked'])}"
    )
    ok = (
        result["total_monthly_gap"] == "8500.00"
        and result["total_indicative_exposure"] == "17000.00"
    )
    print("RESULT:", "PASS (8,500.00 / 17,000.00)" if ok else "numbers differ from the agreed ones")


if __name__ == "__main__":
    main()
