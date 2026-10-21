"""V1-4: server sign-in. Every request needs a valid Entra token; the call log names the person.

Offline: tokens are signed with a throw-away key, and the tenant's key set is served from a local
address (INGENUS_JWKS_URI is a test-only override). No Microsoft service is contacted.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import jwt
import pytest
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from v1_support import _free_port, _wait_for_port, isolated_env  # noqa: F401  (pytest fixtures)

from ingenus_mcp.core import auth
from ingenus_mcp.core.config import load_settings
from ingenus_mcp.server.app import check_startup

TENANT = "aaaaaaaa-0000-4000-8000-000000000001"  # made-up ids: the real ones live only in .env
SERVER_APP = "bbbbbbbb-0000-4000-8000-000000000002"
CLIENT_APP = "cccccccc-0000-4000-8000-000000000003"
ISSUER = f"https://login.microsoftonline.com/{TENANT}/v2.0"
USER = "tester.one@example.test"
KID = "test-key"


def _pem(key) -> bytes:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


@pytest.fixture(scope="module")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def jwks_server(signing_key):
    """Serve the public half of the signing key as a JWKS document on a loopback port."""
    jwk = json.loads(RSAAlgorithm.to_jwk(signing_key.public_key()))
    jwk.update(kid=KID, use="sig", alg="RS256")
    body = json.dumps({"keys": [jwk]}).encode()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - http.server API
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # keep test output quiet
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/keys"
    server.shutdown()


@pytest.fixture
def entra_env(monkeypatch, jwks_server):
    monkeypatch.setenv("INGENUS_AUTH", "entra")
    monkeypatch.setenv("INGENUS_TENANT_ID", TENANT)
    monkeypatch.setenv("INGENUS_SERVER_CLIENT_ID", SERVER_APP)
    monkeypatch.setenv("INGENUS_JWKS_URI", jwks_server)


def make_token(key, **overrides) -> str:
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": SERVER_APP,
        "tid": TENANT,
        "oid": "11111111-2222-3333-4444-555555555555",
        "preferred_username": USER,
        "scp": "access_as_user",
        "azp": CLIENT_APP,
        "ver": "2.0",
        "iat": now,
        "nbf": now,
        "exp": now + 3600,
    }
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, _pem(key), algorithm="RS256", headers={"kid": KID})


# --- the token check ---------------------------------------------------------------------------


def verifier():
    return auth.EntraTokenVerifier(load_settings())


def test_a_valid_token_is_accepted_and_names_the_user(entra_env, signing_key):
    access = verifier().verify(make_token(signing_key))
    assert access is not None
    assert access.scopes == ["access_as_user"]
    assert access.claims["preferred_username"] == USER
    assert access.subject == "11111111-2222-3333-4444-555555555555"
    assert access.resource == SERVER_APP


@pytest.mark.parametrize(
    "change",
    [
        {"aud": "00000000-0000-0000-0000-000000000000"},  # meant for another app
        {"aud": f"api://{SERVER_APP}"},  # a version 1.0 style audience: pinned to 2.0 on purpose
        {"iss": f"https://sts.windows.net/{TENANT}/"},  # a version 1.0 issuer
        {"iss": "https://login.microsoftonline.com/other-tenant/v2.0"},
        {"tid": "other-tenant"},
        {"scp": "something_else"},
        {"scp": None},  # no scope claim at all
        {"exp": int(time.time()) - 3600},  # expired
        {"exp": None},  # no expiry
    ],
    ids=[
        "wrong-audience",
        "v1-audience",
        "v1-issuer",
        "other-issuer",
        "other-tenant",
        "wrong-scope",
        "no-scope",
        "expired",
        "no-expiry",
    ],
)
def test_a_bad_token_is_refused(entra_env, signing_key, change):
    assert verifier().verify(make_token(signing_key, **change)) is None


def test_a_token_signed_by_another_key_is_refused(entra_env):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert verifier().verify(make_token(other)) is None


def test_an_unsigned_token_is_refused(entra_env):
    now = int(time.time())
    unsigned = jwt.encode(
        {
            "iss": ISSUER,
            "aud": SERVER_APP,
            "tid": TENANT,
            "scp": "access_as_user",
            "exp": now + 3600,
        },
        key=None,
        algorithm="none",
        headers={"kid": KID},
    )
    assert verifier().verify(unsigned) is None


def test_a_shared_secret_token_is_refused(entra_env, signing_key):
    """The classic downgrade: sign with HS256 using the public key as the shared secret."""
    import base64
    import hashlib
    import hmac

    def b64(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    public_pem = signing_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    now = int(time.time())
    header = b64(json.dumps({"alg": "HS256", "typ": "JWT", "kid": KID}).encode())
    payload = b64(
        json.dumps(
            {
                "iss": ISSUER,
                "aud": SERVER_APP,
                "tid": TENANT,
                "scp": "access_as_user",
                "exp": now + 3600,
            }
        ).encode()
    )
    signature = b64(hmac.new(public_pem, f"{header}.{payload}".encode(), hashlib.sha256).digest())
    assert verifier().verify(f"{header}.{payload}.{signature}") is None
    assert verifier().verify("not.a.token") is None
    assert verifier().verify("") is None


def test_the_token_is_never_logged(entra_env, signing_key, capsys):
    token = make_token(signing_key, scp="nope")
    assert verifier().verify(token) is None
    captured = capsys.readouterr()
    assert token not in captured.out + captured.err


# --- who is calling ----------------------------------------------------------------------------


def test_the_call_log_names_the_signed_in_person(entra_env, signing_key):
    from mcp.server.auth.middleware.auth_context import auth_context_var
    from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser

    from ingenus_mcp.core import calllog

    access = verifier().verify(make_token(signing_key))
    marker = auth_context_var.set(AuthenticatedUser(access))
    try:
        assert auth.current_user_name() == USER
        assert calllog.current_user() == USER  # wins over INGENUS_USER=tester and the Windows user
    finally:
        auth_context_var.reset(marker)
    assert auth.current_user_name() is None
    assert calllog.current_user() == "tester"


# --- start-up guards ---------------------------------------------------------------------------


def settings_with(monkeypatch, **env):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return load_settings()


def test_start_up_refuses_a_network_address_without_sign_in(monkeypatch):
    s = settings_with(monkeypatch)
    check_startup(s, "127.0.0.1", "http")  # loopback is fine
    with pytest.raises(SystemExit, match="anyone who can reach the port"):
        check_startup(s, "0.0.0.0", "http")


def test_start_up_needs_sign_in_for_sharepoint(monkeypatch):
    s = settings_with(
        monkeypatch,
        INGENUS_DOC_SOURCE="sharepoint",
        INGENUS_SP_SITE_URL="https://x.sharepoint.com/sites/y",
    )
    with pytest.raises(SystemExit, match="needs INGENUS_AUTH=entra"):
        check_startup(s, "127.0.0.1", "http")


def test_start_up_needs_the_ids_for_sign_in(monkeypatch):
    s = settings_with(monkeypatch, INGENUS_AUTH="entra")
    with pytest.raises(SystemExit, match="INGENUS_TENANT_ID"):
        check_startup(s, "127.0.0.1", "http")


def test_start_up_rejects_unknown_modes(monkeypatch):
    with pytest.raises(SystemExit, match="INGENUS_AUTH must be"):
        check_startup(settings_with(monkeypatch, INGENUS_AUTH="maybe"), "127.0.0.1", "http")
    with pytest.raises(SystemExit, match="INGENUS_DOC_SOURCE must be"):
        check_startup(settings_with(monkeypatch, INGENUS_DOC_SOURCE="ftp"), "127.0.0.1", "http")


def test_sign_in_is_not_available_over_stdio(entra_env):
    with pytest.raises(SystemExit, match="needs the HTTP transport"):
        check_startup(load_settings(), "127.0.0.1", "stdio")


def test_sign_in_is_off_by_default():
    s = load_settings()
    assert s.auth_mode == "off" and s.doc_source == "local"


# --- a real server process with sign-in on -----------------------------------------------------


@pytest.fixture
def signed_in_server(tmp_path, entra_env):
    port = _free_port()
    with (tmp_path / "server.err").open("w", encoding="utf-8") as err:
        proc = subprocess.Popen(  # fixed argv, no shell
            [
                sys.executable,
                "-m",
                "ingenus_mcp.server",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            env={**os.environ},
            stdout=subprocess.DEVNULL,
            stderr=err,
        )
        try:
            _wait_for_port(port, proc)
            yield f"http://127.0.0.1:{port}/mcp"
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


def rpc(url, method, params=None, token=None):
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    session = requests.Session()
    session.trust_env = False  # never go through a proxy for a loopback call
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    return session.post(url, json=body, headers=headers, timeout=30)


def test_no_token_means_401(signed_in_server):
    response = rpc(signed_in_server, "tools/list")
    assert response.status_code == 401
    assert "bearer" in response.headers.get("WWW-Authenticate", "").lower()
    assert "compare_contract_to_sap" not in response.text


def test_a_bad_token_means_401(signed_in_server, signing_key):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    for token in ("garbage", make_token(other), make_token(signing_key, scp="nope")):
        assert rpc(signed_in_server, "tools/list", token=token).status_code == 401


def test_a_good_token_reaches_the_tools_and_the_log_names_the_person(
    signed_in_server, signing_key, isolated_env
):
    token = make_token(signing_key)
    listed = rpc(signed_in_server, "tools/list", token=token)
    assert listed.status_code == 200 and "compare_contract_to_sap" in listed.text

    called = rpc(
        signed_in_server,
        "tools/call",
        {"name": "resolve_customer", "arguments": {"name": "Chain X"}},
        token=token,
    )
    assert called.status_code == 200 and "SYN-CUST-0001" in called.text

    log = isolated_env / "tool_calls.jsonl"
    records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert [r["tool"] for r in records] == ["resolve_customer"]
    assert (
        records[0]["user"] == USER
    )  # the person from the token, not INGENUS_USER or the Windows user
    assert token not in log.read_text(encoding="utf-8")
