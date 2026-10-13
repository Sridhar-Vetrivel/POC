from __future__ import annotations

import json

from ingenus_plugin.core.schema import current_schema, schema_path


def test_the_published_extraction_schema_matches_the_model():
    published = json.loads(schema_path().read_text(encoding="utf-8"))
    assert published == json.loads(json.dumps(current_schema(), sort_keys=True)), (
        "contract_terms.v1.json is out of date. If an eval already used v1, write v2 instead of editing v1."
    )
