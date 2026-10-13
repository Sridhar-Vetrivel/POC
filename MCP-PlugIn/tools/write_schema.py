"""Developer script: write the extraction schema to the slice folder.

    python MCP-PlugIn/tools/write_schema.py

This lives outside the plug-in package on purpose: the package itself only writes the tool-call log.
"""

import json

from ingenus_plugin.core.schema import current_schema, schema_path

path = schema_path()
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(current_schema(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(f"wrote {path}")
