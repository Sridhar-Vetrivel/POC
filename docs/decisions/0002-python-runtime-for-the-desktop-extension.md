# 0002: Python runtime for the desktop extension (open)

**Date:** 13 Oct 2026 · **Status:** OPEN, v0 uses Python · **Phase:** 1

## What we found
- Anthropic's MCPB guide says Node.js is strongly recommended: it is "included with Claude Desktop on macOS and
  Windows, so users need no separate runtime". It describes Python bundles as needing **all dependencies bundled**
  and does not say Python itself is included. So each laptop probably needs its own Python (**verify** on Ingenus's
  laptops and on a clean Windows machine).
- Our bundle (`build/ingenus-contract-check.mcpb`, 24 MB) bundles the libraries but not Python. The libraries are
  built for Windows and for the Python version that built them (3.13 here), so the laptops need that version on PATH.
- The MCP SDK needs pywin32 on Windows; its modules are found through a `.pth` file, so the entry script uses
  `site.addsitedir` (not `sys.path.insert`). This is fixed and tested with `smoke_test_bundle.py`.

## Options
| Option | For | Against |
|---|---|---|
| A. Python as now (v0) | Already built and tested; one language | Needs matching Python on each laptop; Windows only; 24 MB |
| B. Manifest type `uv` | Dependencies not bundled; smaller | Needs `uv` installed on each laptop (verify) |
| C. Binary bundle (for example PyInstaller) | No Python needed on the laptop | Windows only; larger; antivirus may flag; extra build step |
| D. Rewrite the server in Node.js | The documented best path; runtime included | Rewrites the tools; our code, tests and skills are Python |

## Decision for now
Keep A for v0 and **check what Ingenus's laptops have** (Python present? version?). If it is a problem, pick B or C
before D. Record the choice here.
