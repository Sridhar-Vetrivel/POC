"""Settings for the v1 server, read from environment variables so a deployment can set them.

Defaults point at synthetic data in this repo. Real data stays off until Ingenus's data policy is
signed off (see CLAUDE.md rule 9). Contracts are read from a local folder (default: v0's synthetic
folder) or, with INGENUS_DOC_SOURCE=sharepoint, from a SharePoint document library through Microsoft
Graph as the signed-in user (V1-6). Server sign-in (V1-4) is INGENUS_AUTH=entra.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# .../POC/MCP-Server/src/ingenus_mcp/core/config.py -> POC/MCP-Server and POC
_SERVER_DIR = Path(__file__).resolve().parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[4]
_DATA = _SERVER_DIR / "data"
ENV_FILE = _SERVER_DIR / ".env"  # git-ignored; see .env.example


def load_env_file(path: Path = ENV_FILE) -> list[str]:
    """Load INGENUS_* settings from a local file into the environment, if the file exists.

    For a developer laptop only (the server calls this at start-up; load_settings and the tests never
    do). Variables already set in the environment win. The file holds ids and file paths, not secrets:
    the certificate's private key stays in its own file, outside the repository. Returns the names set.
    """
    if os.environ.get("INGENUS_NO_ENV_FILE") == "1" or not path.is_file():
        return []  # the tests set INGENUS_NO_ENV_FILE=1 so a developer's file never leaks into them
    loaded: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name, value = name.strip(), value.strip().strip('"').strip("'")
        if name.startswith("INGENUS_") and name not in os.environ:
            os.environ[name] = value
            loaded.append(name)
    return loaded


@dataclass(frozen=True)
class Settings:
    contracts_dir: Path
    slice_dir: Path
    sap_adapter: str
    sap_mock_file: Path
    log_path: Path
    prompts_dir: Path
    guidance_dir: Path
    host: str
    port: int
    stateless: bool
    # V1-6: where the contracts are read from. "local" (contracts_dir) or "sharepoint" (Graph).
    doc_source: str = "local"
    sharepoint_site_url: str = ""  # e.g. https://<tenant>.sharepoint.com/sites/<site>
    sharepoint_folder: str = (
        ""  # folder inside the site's default library, e.g. General/synthetic/contracts
    )
    # V1-4: server sign-in. "off" (loopback only) or "entra" (every request needs a valid Entra token).
    auth_mode: str = "off"
    tenant_id: str = ""
    server_client_id: str = ""  # the "Ingenus POC MCP Server" app registration
    required_scope: str = "access_as_user"
    cert_key_file: Path | None = (
        None  # private key (PEM) of the certificate uploaded to the server app
    )
    cert_thumbprint: str = ""  # SHA-1 thumbprint of that certificate, hex
    public_url: str = (
        "http://127.0.0.1:8765/mcp"  # the URL clients use; named in the sign-in metadata
    )
    jwks_uri_override: str = ""  # tests only: serve the token signing keys from a local address

    @property
    def authority(self) -> str:
        return f"https://login.microsoftonline.com/{self.tenant_id}"

    @property
    def issuer(self) -> str:
        return f"{self.authority}/v2.0"

    @property
    def jwks_uri(self) -> str:
        return self.jwks_uri_override or f"{self.authority}/discovery/v2.0/keys"

    @property
    def topics_file(self) -> Path:
        return self.slice_dir / "topics.v1.yaml"

    @property
    def customers_file(self) -> Path:
        return self.slice_dir / "ontology" / "customers.v1.yaml"

    @property
    def rules_file(self) -> Path:
        return self.slice_dir / "rules" / "compare.v1.yaml"


def _key_file(value: str) -> Path | None:
    """The certificate key path from INGENUS_CERT_KEY_FILE; a relative path is read from MCP-Server/."""
    if not value:
        return None
    candidate = Path(value).expanduser()
    return candidate if candidate.is_absolute() else _SERVER_DIR / candidate


def load_settings() -> Settings:
    def path(var: str, default: Path) -> Path:
        value = os.environ.get(var)
        return Path(value).expanduser() if value else default

    return Settings(
        contracts_dir=path(
            "INGENUS_CONTRACTS_DIR", _REPO_ROOT / "MCP-PlugIn" / "data" / "synthetic" / "contracts"
        ),
        slice_dir=path("INGENUS_SLICE_DIR", _REPO_ROOT / "slices" / "contract_to_sap_check"),
        sap_adapter=os.environ.get("INGENUS_SAP_ADAPTER", "mock"),
        sap_mock_file=path("INGENUS_SAP_MOCK_FILE", _DATA / "sap" / "entities.json"),
        log_path=path("INGENUS_LOG_PATH", _DATA / "runtime" / "tool_calls.jsonl"),
        prompts_dir=path("INGENUS_PROMPTS_DIR", _SERVER_DIR / "prompts"),
        # The guides (skills) the server serves through get_guide; decision 0003.
        guidance_dir=path("INGENUS_GUIDANCE_DIR", _SERVER_DIR / "guidance" / "v2"),
        # Loopback by default. Binding to a network address is a deployment decision (V1-4), made
        # together with server sign-in: an open port without sign-in would let anyone call the tools.
        host=os.environ.get("INGENUS_MCP_HOST", "127.0.0.1"),
        port=int(os.environ.get("INGENUS_MCP_PORT", "8765")),
        # Stateless HTTP by default: every request stands alone, no session to start first. Claude
        # Desktop's Cowork and Code sessions open with a request before any handshake, and a stateful
        # server rejects that ("Missing session ID"; seen 19 Oct 2026). Our tools keep no state.
        stateless=os.environ.get("INGENUS_MCP_STATELESS", "1") != "0",
        doc_source=os.environ.get("INGENUS_DOC_SOURCE", "local").strip().lower(),
        sharepoint_site_url=os.environ.get("INGENUS_SP_SITE_URL", "").strip(),
        sharepoint_folder=os.environ.get("INGENUS_SP_FOLDER", "").strip().strip("/"),
        auth_mode=os.environ.get("INGENUS_AUTH", "off").strip().lower(),
        tenant_id=os.environ.get("INGENUS_TENANT_ID", "").strip(),
        server_client_id=os.environ.get("INGENUS_SERVER_CLIENT_ID", "").strip(),
        required_scope=os.environ.get("INGENUS_REQUIRED_SCOPE", "access_as_user").strip(),
        cert_key_file=_key_file(os.environ.get("INGENUS_CERT_KEY_FILE", "")),
        cert_thumbprint=os.environ.get("INGENUS_CERT_THUMBPRINT", "").strip().replace(":", ""),
        public_url=os.environ.get("INGENUS_PUBLIC_URL", "http://127.0.0.1:8765/mcp").strip(),
        jwks_uri_override=os.environ.get("INGENUS_JWKS_URI", "").strip(),
    )
