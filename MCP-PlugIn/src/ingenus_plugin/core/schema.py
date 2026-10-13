"""The extraction schema: what Claude must pass to compare_contract_to_sap.

Generated from the Pydantic model so the two cannot drift. The published copy lives in the slice
folder (schemas/contract_terms.v1.json) and a test checks they match. To (re)write the file, run
MCP-PlugIn/tools/write_schema.py. Per CLAUDE.md, never edit a version in place once an eval has
used it: write contract_terms.v2.json instead.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import TypeAdapter

from ingenus_plugin.core.config import load_settings
from ingenus_plugin.core.models import ExtractedTerm


def current_schema() -> dict:
    return TypeAdapter(list[ExtractedTerm]).json_schema()


def schema_path() -> Path:
    return load_settings().slice_dir / "schemas" / "contract_terms.v1.json"
