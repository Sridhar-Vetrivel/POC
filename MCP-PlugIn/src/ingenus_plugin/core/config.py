"""Settings, read from environment variables so a desktop extension can set them per user.

Defaults point at the repo's synthetic data. Real data stays off until Ingenus's data policy is
signed off (see CLAUDE.md rule 9).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# .../POC/MCP-PlugIn/src/ingenus_plugin/core/config.py -> POC
_REPO_ROOT = Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class Settings:
    contracts_dir: Path
    slice_dir: Path
    sap_adapter: str
    sap_mock_file: Path
    log_path: Path
    prompts_dir: Path

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
            "INGENUS_CONTRACTS_DIR", _REPO_ROOT / "data" / "synthetic" / "contracts"
        ),
        slice_dir=path("INGENUS_SLICE_DIR", _REPO_ROOT / "slices" / "contract_to_sap_check"),
        sap_adapter=os.environ.get("INGENUS_SAP_ADAPTER", "mock"),
        sap_mock_file=path(
            "INGENUS_SAP_MOCK_FILE", _REPO_ROOT / "data" / "synthetic" / "sap" / "entities.json"
        ),
        log_path=path("INGENUS_LOG_PATH", _REPO_ROOT / "data" / "runtime" / "tool_calls.jsonl"),
        prompts_dir=path("INGENUS_PROMPTS_DIR", _REPO_ROOT / "MCP-PlugIn" / "prompts"),
    )
