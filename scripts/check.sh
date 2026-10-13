#!/usr/bin/env bash
# Thin wrapper around the cross-platform gate runner (scripts/check.py).
# Use this on macOS / Linux / Git Bash / WSL. On native Windows use scripts\check.bat.
# All gate logic lives in scripts/check.py so the gates are identical on every OS.
#
# Usage:
#   bash scripts/check.sh [--fast] [--fix] [--only a,b] [--skip a,b] [--bundle] [--list]
#
# Requirements (installed via `pip install -e ".[dev]"`):
#   ruff, bandit, pip-audit, pytest, reportlab

set -uo pipefail
exec python3 "$(dirname "$0")/check.py" "$@"
