"""Build the Claude Desktop bridge extension. Developer script; nothing here runs on a user's laptop.

    python MCP-Server/bridge/build_bridge.py

Output (git-ignored):
  MCP-Server/build/bridge/            the unpacked extension (Settings > Extensions > Install unpacked)
  MCP-Server/build/ingenus-bridge.mcpb   the packed extension (Install Extension...)

The bridge is Node only: Claude Desktop runs it with the Node it bundles (per Anthropic's MCPB guide;
verify on the target Desktop version), so the laptop needs no Python, repo or git. It contains no tools,
data or secrets; the user enters only the server URL.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILD = HERE.parent / "build"
STAGE = BUILD / "bridge"
OUT = BUILD / "ingenus-bridge.mcpb"


def run(cmd: list[str], cwd: Path) -> None:
    print("+", " ".join(cmd))
    result = subprocess.run(cmd, cwd=cwd, check=False, text=True, capture_output=True)  # fixed argv
    print(result.stdout, result.stderr)
    if result.returncode != 0:
        raise SystemExit(f"failed: {' '.join(cmd)}")


def tool(name: str) -> str:
    found = shutil.which(name) or shutil.which(f"{name}.cmd")
    if not found:
        raise SystemExit(
            f"{name} not found: install Node.js (for building only, not on user laptops)."
        )
    return found


def main() -> None:
    manifest = json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))
    package = json.loads((HERE / "package.json").read_text(encoding="utf-8"))
    if manifest["version"] != package["version"]:
        raise SystemExit("manifest.json and package.json versions differ")

    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)
    for name in ("manifest.json", "package.json", "package-lock.json"):
        shutil.copy2(HERE / name, STAGE / name)
    shutil.copytree(HERE / "server", STAGE / "server")

    # Exact versions from the lockfile; no dev dependencies.
    run([tool("npm"), "ci", "--omit=dev", "--no-audit", "--no-fund"], cwd=STAGE)
    npx = tool("npx")
    run([npx, "--yes", "@anthropic-ai/mcpb", "validate", str(STAGE / "manifest.json")], cwd=STAGE)
    if OUT.exists():
        OUT.unlink()
    run([npx, "--yes", "@anthropic-ai/mcpb", "pack", str(STAGE), str(OUT)], cwd=STAGE)
    print(f"built {OUT} ({OUT.stat().st_size / 1_000_000:.1f} MB) and the unpacked folder {STAGE}")


if __name__ == "__main__":
    main()
