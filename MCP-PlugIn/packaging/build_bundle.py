"""Build the desktop extension (.mcpb) for Claude Desktop. Developer script; not part of the plug-in.

    python MCP-PlugIn/packaging/build_bundle.py            # stage the bundle and try to pack it

What it does:
  1. Stages a clean folder (MCP-PlugIn/build/mcpb) with the manifest, a tiny entry script, the bundled
     Python libraries (server/lib), our two packages, the slice files, the prompt and the SYNTHETIC SAP data.
  2. Copies the sample contracts to MCP-PlugIn/build/sample_contracts (not inside the bundle: the user
     picks a folder).
  3. Runs the MCPB command line tool (npx @anthropic-ai/mcpb) to validate and pack.

Known limits (see MCP-PlugIn/docs/S0_spike_results.md): Python dependencies are platform and
Python-version specific, so this bundle works on Windows with the SAME Python minor version as the machine
that built it. Claude Desktop is documented to bundle Node, not Python, so each laptop needs a matching
Python on PATH (verify). Not yet installed in Claude Desktop.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

POC = Path(__file__).resolve().parents[2]
PLUGIN = POC / "MCP-PlugIn"
HERE = Path(__file__).resolve().parent
BUILD = PLUGIN / "build"
SYNTHETIC = PLUGIN / "data" / "synthetic"
STAGE = BUILD / "mcpb"
DEPENDENCIES = ["mcp>=2.3,<3", "pydantic>=2.7", "pyyaml>=6", "pypdf>=4"]

ENTRY = '''"""Entry point for the desktop extension. Adds the bundled libraries, then starts the stdio server."""
import os
import site
import sys

# addsitedir (not sys.path.insert) so .pth files in lib/ are processed. The MCP SDK needs pywin32 on
# Windows, and pywin32 puts its modules on the path through a .pth file.
site.addsitedir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

from ingenus_plugin.server.app import main  # noqa: E402

if __name__ == "__main__":
    main()
'''


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    print("+", " ".join(cmd))
    return subprocess.run(cmd, check=False, text=True, capture_output=True, **kw)


def stage() -> None:
    if BUILD.exists():
        shutil.rmtree(BUILD)
    (STAGE / "server" / "lib").mkdir(parents=True)

    shutil.copy2(HERE / "manifest.json", STAGE / "manifest.json")
    (STAGE / "server" / "main.py").write_text(ENTRY, encoding="utf-8")

    result = run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--quiet",
            "--target",
            str(STAGE / "server" / "lib"),
            *DEPENDENCIES,
        ]
    )
    if result.returncode != 0:
        print(result.stdout, result.stderr)
        raise SystemExit("pip could not bundle the dependencies")

    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    shutil.copytree(
        POC / "MCP-PlugIn" / "src" / "ingenus_plugin",
        STAGE / "server" / "lib" / "ingenus_plugin",
        ignore=ignore,
    )
    shutil.copytree(POC / "mcp_servers", STAGE / "server" / "lib" / "mcp_servers", ignore=ignore)
    shutil.copytree(
        POC / "slices" / "contract_to_sap_check",
        STAGE / "slice",
        ignore=shutil.ignore_patterns("evals", "__pycache__"),
    )
    shutil.copytree(POC / "MCP-PlugIn" / "prompts", STAGE / "prompts")
    (STAGE / "data" / "sap").mkdir(parents=True)
    shutil.copy2(SYNTHETIC / "sap" / "entities.json", STAGE / "data" / "sap" / "entities.json")
    shutil.copytree(SYNTHETIC / "contracts", BUILD / "sample_contracts")

    manifest = json.loads((STAGE / "manifest.json").read_text(encoding="utf-8"))
    manifest["compatibility"]["runtimes"]["python"] = (
        f">={sys.version_info.major}.{sys.version_info.minor},<{sys.version_info.major}.{sys.version_info.minor + 1}"
    )
    (STAGE / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def pack() -> None:
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if not npx:
        print(
            "npx not found: install Node.js, then run `npx @anthropic-ai/mcpb pack MCP-PlugIn/build/mcpb`."
        )
        return
    validate = run([npx, "--yes", "@anthropic-ai/mcpb", "validate", str(STAGE / "manifest.json")])
    print(validate.stdout, validate.stderr)
    out = BUILD / "ingenus-contract-check.mcpb"
    packed = run([npx, "--yes", "@anthropic-ai/mcpb", "pack", str(STAGE), str(out)])
    print(packed.stdout, packed.stderr)
    if out.exists():
        print(f"built {out} ({out.stat().st_size / 1_000_000:.1f} MB)")


if __name__ == "__main__":
    stage()
    pack()
