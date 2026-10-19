"""Settings for the v1 server, read from environment variables so a deployment can set them.

Defaults point at synthetic data in this repo. Real data stays off until Ingenus's data policy is
signed off (see CLAUDE.md rule 9). Until the SharePoint and network-drive sources exist (V1-6, V1-8),
contracts are read from v0's synthetic folder, read-only.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# .../POC/MCP-Server/src/ingenus_mcp/core/config.py -> POC/MCP-Server and POC
_SERVER_DIR = Path(__file__).resolve().parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[4]
_DATA = _SERVER_DIR / "data"


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

    @property
    def topics_file(self) -> Path:
        return self.slice_dir / "topics.v1.yaml"

    @property
    def customers_file(self) -> Path:
        return self.slice_dir / "ontology" / "customers.v1.yaml"

    @property
    def rules_file(self) -> Path:
        return self.slice_dir / "rules" / "compare.v1.yaml"


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
    )
