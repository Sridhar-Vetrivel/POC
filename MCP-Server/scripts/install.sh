#!/usr/bin/env bash
# Install the Ingenus MCP server on a Linux machine (tested on Ubuntu 24.04, 16 Nov 2026).
#
# What it does: makes a Python 3.13 environment in <repo root>/.venv and installs the server
# into it, with the local embedding model packages (the "meaning" extra).
# It needs no sudo and no system pip: it bootstraps `uv` from a throwaway venv, and `uv`
# downloads Python 3.13 itself (the system Python can be a different version).
#
# Run it as the user that will run the server (not as root), from anywhere:
#     bash MCP-Server/scripts/install.sh
# Safe to run again: it rebuilds the throwaway venv and reuses what is already installed.
#
# Needs: python3 (with the venv module: `apt-get install python3-venv` if missing), curl,
# and outbound internet to bootstrap.pypa.io, pypi.org and github.com (Python download).
set -euo pipefail

# The repo root is two folders up from this file (MCP-Server/scripts/install.sh).
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
echo "installing from: $ROOT"

# 1. A throwaway venv without pip, then pip from the official bootstrap script, then uv.
rm -rf .boot
python3 -m venv --without-pip .boot
curl -fsSL -o /tmp/get-pip.py https://bootstrap.pypa.io/get-pip.py
.boot/bin/python /tmp/get-pip.py -q
.boot/bin/python -m pip install -q uv

# 2. Python 3.13 and the project environment.
.boot/bin/uv python install 3.13
.boot/bin/uv venv --allow-existing --python 3.13 .venv

# 3. The server and its packages, editable, with the local embedding model extra.
.boot/bin/uv pip install --python .venv/bin/python -e ".[meaning]"

# 4. Check it imports.
.venv/bin/python -c 'import ingenus_mcp; print("import ok", ingenus_mcp.__version__)'
