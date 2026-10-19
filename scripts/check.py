#!/usr/bin/env python3
"""Cross-platform quality-gate runner for the Ingenus POC (single source of gate logic).

Run it after any big change. It runs every gate, prints what failed and why, and exits non-zero if
any gate fails. scripts/check.sh and scripts/check.bat are thin wrappers around this file. Each
tool is invoked as `python -m <tool>` so it works without a POSIX shell or console-script .exe
resolution, and the script re-executes itself under the repo's .venv when started by another Python.

    python scripts/check.py              # all gates (about a minute with pip-audit)
    python scripts/check.py --fast       # quick gates only: lint, format and the repo-rule scans
    python scripts/check.py --fix        # first apply ruff's safe fixes and formatting, then check
    python scripts/check.py --only pytest,manifest-sync
    python scripts/check.py --skip pip-audit      # e.g. when offline
    python scripts/check.py --bundle     # also build the desktop extension and smoke-test it
    python scripts/check.py --list       # show the gates and exit

Gates (in order): ruff, ruff-format, bandit, pip-audit, no-stdout, no-secrets, client-material,
synthetic-label, versioning, fixtures, manifest-sync, docs-links, pytest (+ bundle with --bundle).
They check the rules in CLAUDE.md that a linter cannot see. No output is suppressed.

For an AI agent: after a big change run this, read every FAIL, fix the cause (do not weaken a gate
or add a suppression to get green), and run it again until it ends with "0 failed".
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _reexec_in_venv() -> None:
    """Re-exec under the repo's .venv interpreter when launched by a different one.

    A bare `python scripts/check.py` may run under a system Python that lacks the project's tools,
    so every tool-based gate would fail for the wrong reason. Prefer the repo virtualenv so the
    caller need not activate it. No-op when the venv is missing (CI that installs into its own
    interpreter) or is already the active interpreter.
    """
    venv_py = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not venv_py.exists() or os.environ.get("_CHECK_PY_REEXEC"):
        return
    try:
        if os.path.samefile(str(venv_py), sys.executable):
            return
    except OSError:
        pass
    os.environ["_CHECK_PY_REEXEC"] = "1"
    # Deliberate no-shell exec into a repo-relative interpreter path (not user input).
    os.execv(str(venv_py), [str(venv_py), str(Path(__file__).resolve()), *sys.argv[1:]])


# Python source roots that the linters and security scanners cover.
PY_DIRS = [
    "MCP-PlugIn",
    "MCP-Server",
    "mcp_servers",
    "tests",
    "scripts",
]  # MCP-PlugIn includes data/synthetic
# v0's synthetic data (contracts, SAP mock, generator) lives inside MCP-PlugIn since 19 Oct 2026.
SYNTHETIC = "MCP-PlugIn/data/synthetic"
# v1 keeps its own copy of the mock SAP data; it must stay equal to v0's (synthetic-label gate).
V1_SAP_COPY = "MCP-Server/data/sap/entities.json"
# Code that ships in the server process: stdout there is the protocol channel.
SERVER_DIRS = [
    "MCP-PlugIn/src/ingenus_plugin/core",
    "MCP-PlugIn/src/ingenus_plugin/server",
    "MCP-Server/src/ingenus_mcp/core",
    "MCP-Server/src/ingenus_mcp/tools",
    "MCP-Server/src/ingenus_mcp/server",
]
BANDIT_DIRS = ["MCP-PlugIn/src", "MCP-Server/src", "mcp_servers", "scripts"]

# Never scanned or walked: environments, generated output, caches.
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "build",
    ".spike",
    "__pycache__",
    "node_modules",
    ".pytest_cache",
    ".ruff_cache",
}

# Known and accepted pip-audit advisories (none yet). Add the id with a comment saying why.
PIP_AUDIT_IGNORE: list[str] = []

TEXT_EXTS = {".py", ".md", ".yaml", ".yml", ".json", ".toml", ".txt", ".bat", ".sh", ".cfg", ".ini"}


def _py(*args: str) -> list[str]:
    """Build a `python -m ...` command using the current interpreter."""
    return [sys.executable, "-m", *args]


def run_cmd(cmd: list[str], *, ok_returncodes: tuple[int, ...] = (0,)) -> bool:
    return subprocess.run(cmd, cwd=ROOT).returncode in ok_returncodes


def _walk(suffixes: set[str] | None = None) -> list[Path]:
    """All files under ROOT except the skipped directories (optionally filtered by suffix)."""
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.endswith(".egg-info")]
        for name in filenames:
            path = Path(dirpath) / name
            if suffixes is None or path.suffix.lower() in suffixes:
                found.append(path)
    return sorted(found)


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _report(title: str, offenders: list[str], hint: str = "") -> bool:
    if not offenders:
        return True
    print(f"  {title}")
    for item in offenders:
        print(f"    {item}")
    if hint:
        print(f"  {hint}")
    return False


# --------------------------------------------------------------------------------------------
# Tool gates
# --------------------------------------------------------------------------------------------
def run_ruff() -> bool:
    return run_cmd(_py("ruff", "check", *PY_DIRS))


def run_ruff_format() -> bool:
    return run_cmd(_py("ruff", "format", "--check", *PY_DIRS))


def run_bandit() -> bool:
    return run_cmd(
        _py(
            "bandit",
            "-r",
            *BANDIT_DIRS,
            "--severity-level",
            "medium",
            "--confidence-level",
            "medium",
            "-q",
        )
    )


def run_pip_audit() -> bool:
    """Audit the installed environment. Needs network access to the vulnerability database."""
    cmd = _py("pip_audit", "--progress-spinner", "off")
    for vuln in PIP_AUDIT_IGNORE:
        cmd += ["--ignore-vuln", vuln]
    ok = subprocess.run(cmd, cwd=ROOT).returncode == 0
    if not ok:
        print(
            "  (pip-audit also fails when it cannot reach the network: use --skip pip-audit offline)"
        )
    return ok


def run_pytest() -> bool:
    # Exit code 5 means "no tests collected": treat as pass.
    return run_cmd(_py("pytest", "-q", "--tb=short"), ok_returncodes=(0, 5))


# --------------------------------------------------------------------------------------------
# Repo-rule gates (the rules in CLAUDE.md that a linter cannot see)
# --------------------------------------------------------------------------------------------
def run_no_stdout() -> bool:
    """Rule: never print to stdout in server code. On stdio, stdout is the protocol channel.

    Scans the server process code (core/ and server/). A print() must name a file= (stderr). The
    command-line tools (report.py, evals.py) are outside these folders and may print.
    """
    offenders: list[str] = []
    for d in SERVER_DIRS:
        for path in (ROOT / d).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "print"
                    and not any(kw.arg == "file" for kw in node.keywords)
                ):
                    offenders.append(f"{_rel(path)}:{node.lineno}: print() to stdout")
    return _report(
        "stdout used in server code (breaks the stdio protocol):",
        offenders,
        "Use print(..., file=sys.stderr), or remove it.",
    )


_SECRET_PATTERNS = {
    "Anthropic API key": re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}"),
    "OpenAI-style key": re.compile(r"\bsk-[A-Za-z0-9]{32,}\b"),
    "AWS access key id": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "private key block": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    "hard-coded credential": re.compile(
        r"""(?i)\b(?:password|passwd|secret|api[_-]?key|token)\s*[:=]\s*["'][^"'\s]{8,}["']"""
    ),
}


def run_no_secrets() -> bool:
    """Rule: no credentials, keys or real hostnames in code, tests or fixtures."""
    offenders: list[str] = []
    for path in _walk(TEXT_EXTS):
        if path == Path(__file__).resolve():  # this file holds the patterns themselves
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(lines, start=1):
            for label, pattern in _SECRET_PATTERNS.items():
                if pattern.search(line):
                    offenders.append(f"{_rel(path)}:{number}: looks like a {label}")
    return _report(
        "possible secret in the repo:",
        offenders,
        "Move it to an environment variable or a key vault, and rotate it if it was ever real.",
    )


_CLIENT_SUFFIXES = {".docx", ".doc", ".msg", ".eml", ".pst", ".xlsx", ".xls", ".pptx"}
_CLIENT_NAME_HINTS = ("confidential", "ingenus_internal", "transcript")


def run_client_material() -> bool:
    """Rule: only synthetic or public data. Never add client documents, transcripts or SAP extracts."""
    offenders: list[str] = []
    for client_dir in (ROOT / "data" / "client", ROOT / "MCP-PlugIn" / "data" / "client"):
        if client_dir.exists():
            offenders.append(f"{_rel(client_dir)}/ exists (client data must never be in this repo)")
    for path in _walk():
        name = path.name.lower()
        if path.suffix.lower() in _CLIENT_SUFFIXES:
            offenders.append(f"{_rel(path)}: Office or mail file (looks like client material)")
        elif any(hint in name for hint in _CLIENT_NAME_HINTS):
            offenders.append(f"{_rel(path)}: name suggests client material")
    return _report(
        "possible client material in the repo:",
        offenders,
        "Remove it. Only synthetic or public data belongs here (CLAUDE.md rule 9).",
    )


def run_synthetic_label() -> bool:
    """Rule: every synthetic value is labelled synthetic."""
    offenders: list[str] = []
    sap = ROOT / SYNTHETIC / "sap" / "entities.json"
    if sap.is_file():
        label = str(json.loads(sap.read_text(encoding="utf-8")).get("_label", ""))
        if "SYNTHETIC" not in label.upper():
            offenders.append(f"{_rel(sap)}: _label does not say SYNTHETIC")
    customers = ROOT / "slices" / "contract_to_sap_check" / "ontology"
    for path in customers.glob("customers*.yaml") if customers.is_dir() else []:
        if "SYNTHETIC" not in path.read_text(encoding="utf-8").upper():
            offenders.append(f"{_rel(path)}: no SYNTHETIC label")

    from pypdf import PdfReader  # imported here so the other gates run even if it is missing

    for path in sorted((ROOT / SYNTHETIC / "contracts").rglob("*.pdf")):
        text = " ".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
        if "SYNTHETIC" not in text:
            offenders.append(f"{_rel(path)}: no SYNTHETIC footer in the text")

    v1_sap = ROOT / V1_SAP_COPY
    if v1_sap.is_file() and sap.is_file():
        if json.loads(v1_sap.read_text(encoding="utf-8")) != json.loads(
            sap.read_text(encoding="utf-8")
        ):
            offenders.append(
                f"{V1_SAP_COPY}: differs from {_rel(sap)} (copy the changed file across, or record why)"
            )
    return _report("synthetic data without a label:", offenders)


_VERSIONED = re.compile(r"\.v\d+\.[A-Za-z]+$")


def run_versioning() -> bool:
    """Rule: prompts, schemas, rule files and ontology files carry a version in the filename."""
    slice_dir = ROOT / "slices" / "contract_to_sap_check"
    folders = [
        slice_dir / "rules",
        slice_dir / "schemas",
        slice_dir / "ontology",
        ROOT / "MCP-PlugIn" / "prompts",
        ROOT / "MCP-Server" / "prompts",
    ]
    offenders = [
        f"{_rel(p)}: filename has no .vN version"
        for folder in folders
        if folder.is_dir()
        for p in sorted(folder.iterdir())
        if p.is_file() and not _VERSIONED.search(p.name)
    ]
    for p in sorted(slice_dir.glob("*.yaml")) + sorted(slice_dir.glob("*.json")):
        if not _VERSIONED.search(p.name):
            offenders.append(f"{_rel(p)}: filename has no .vN version")
    skills = ROOT / "MCP-PlugIn" / "skills"
    if skills.is_dir():
        for p in sorted(skills.iterdir()):
            if p.is_dir() and not re.fullmatch(r"v\d+", p.name):
                offenders.append(
                    f"{_rel(p)}: skills must sit under a versioned folder such as skills/v1/"
                )
    return _report(
        "unversioned guidance files:",
        offenders,
        "Never edit a version an eval run used; create v2 beside it (CLAUDE.md, Versioning).",
    )


def run_fixtures() -> bool:
    """Every synthetic contract has a label, and every label points at a real file."""
    labels_file = (
        ROOT / "slices" / "contract_to_sap_check" / "evals" / "golden" / "page_labels.json"
    )
    contracts = ROOT / SYNTHETIC / "contracts"
    if not labels_file.is_file() or not contracts.is_dir():
        return _report("fixtures missing:", [f"{_rel(labels_file)} or {SYNTHETIC}/contracts"])
    labels = json.loads(labels_file.read_text(encoding="utf-8"))
    on_disk = {p.relative_to(contracts).as_posix() for p in contracts.rglob("*.pdf")}
    offenders = [f"{doc}: has a label but no file" for doc in sorted(set(labels) - on_disk)]
    offenders += [f"{doc}: file has no label" for doc in sorted(on_disk - set(labels))]
    return _report(
        "contract fixtures and labels disagree:",
        offenders,
        f"Regenerate with: python {SYNTHETIC}/generate_contracts.py",
    )


def run_manifest_sync() -> bool:
    """The desktop-extension manifest lists exactly the registered tools, and matches the version."""
    manifest = json.loads(
        (ROOT / "MCP-PlugIn" / "packaging" / "manifest.json").read_text(encoding="utf-8")
    )
    from ingenus_plugin import __version__
    from ingenus_plugin.core import tools as _tools  # noqa: F401  (importing registers the tools)
    from ingenus_plugin.core.registry import TOOLS

    offenders: list[str] = []
    listed = {t["name"] for t in manifest.get("tools", [])}
    if listed != set(TOOLS):
        offenders.append(
            f"tools differ: only in manifest {sorted(listed - set(TOOLS))}, only in code {sorted(set(TOOLS) - listed)}"
        )
    if manifest.get("version") != __version__:
        offenders.append(
            f"manifest version {manifest.get('version')} != ingenus_plugin {__version__}"
        )
    prompt_names = {p["name"] for p in manifest.get("prompts", [])}
    if "contract_check" not in prompt_names:
        offenders.append("manifest has no contract_check prompt")
    return _report("manifest and code disagree:", offenders)


_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def run_docs_links() -> bool:
    """Relative links in the markdown files must resolve. Links that leave the repo are warned about.

    Links that reach out of this repo (for example to the pre-sales notes in ../2026) work on this
    workstation but break for anyone who clones only this repo, so they are listed as warnings and
    do not fail the gate.
    """
    broken: list[str] = []
    outside: list[str] = []
    for path in _walk({".md"}):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for target in _LINK.findall(line):
                if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target) or target.startswith("#"):
                    continue
                clean = target.split("#", 1)[0].replace("%20", " ").replace("%26", "&")
                if not clean:
                    continue
                resolved = (path.parent / clean).resolve()
                try:
                    resolved.relative_to(ROOT)
                except ValueError:
                    outside.append(f"{_rel(path)}:{number}: {target}")
                    continue
                if not resolved.exists():
                    broken.append(f"{_rel(path)}:{number}: {target}")
    if outside:
        print(
            f"  note: {len(outside)} link(s) point outside this repo (fine here, broken in a lone clone)"
        )
    return _report("broken links:", broken)


def run_bundle() -> bool:
    """Build the desktop extension and run the staged bundle outside the venv. Needs Node.js."""
    return run_cmd([sys.executable, "MCP-PlugIn/packaging/build_bundle.py"]) and run_cmd(
        [sys.executable, "MCP-PlugIn/packaging/smoke_test_bundle.py"]
    )


# --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Gate:
    name: str
    fn: Callable[[], bool]
    fast: bool  # cheap enough for --fast
    what: str


GATES = [
    Gate("ruff", run_ruff, True, "lint (pyflakes, pycodestyle, isort, pyupgrade, bugbear)"),
    Gate("ruff-format", run_ruff_format, True, "code is formatted"),
    Gate("bandit", run_bandit, False, "security scan of the shipped code (medium and above)"),
    Gate(
        "pip-audit",
        run_pip_audit,
        False,
        "known vulnerabilities in installed packages (needs network)",
    ),
    Gate("no-stdout", run_no_stdout, True, "no print() to stdout in server code"),
    Gate("no-secrets", run_no_secrets, True, "no keys, tokens or hard-coded credentials"),
    Gate("client-material", run_client_material, True, "no client documents in the repo"),
    Gate("synthetic-label", run_synthetic_label, True, "synthetic data is labelled SYNTHETIC"),
    Gate("versioning", run_versioning, True, "guidance files carry a .vN version"),
    Gate("fixtures", run_fixtures, True, "synthetic contracts and page labels agree"),
    Gate(
        "manifest-sync", run_manifest_sync, True, "extension manifest matches the registered tools"
    ),
    Gate("docs-links", run_docs_links, True, "relative markdown links resolve"),
    Gate("pytest", run_pytest, False, "the offline test suite"),
]
BUNDLE_GATE = Gate("bundle", run_bundle, False, "build the .mcpb and smoke-test it (needs Node.js)")


def _apply_fixes() -> None:
    print("[fix] ruff check --fix, then ruff format (safe fixes only)")
    subprocess.run(_py("ruff", "check", "--fix", *PY_DIRS), cwd=ROOT, check=False)
    subprocess.run(_py("ruff", "format", *PY_DIRS), cwd=ROOT, check=False)


def _split(value: str) -> set[str]:
    return {v.strip() for v in value.split(",") if v.strip()}


def main() -> int:
    args = sys.argv[1:]
    gates = list(GATES)
    if "--bundle" in args:
        gates.append(BUNDLE_GATE)
    known = {g.name for g in gates} | {BUNDLE_GATE.name}

    if "--list" in args:
        for g in gates:
            print(f"{g.name:16} {'fast' if g.fast else 'full':5} {g.what}")
        return 0

    only: set[str] = set()
    skip: set[str] = set()
    for i, arg in enumerate(args):
        if arg == "--only" and i + 1 < len(args):
            only = _split(args[i + 1])
        elif arg == "--skip" and i + 1 < len(args):
            skip = _split(args[i + 1])
    unknown = (only | skip) - known
    if unknown:
        print(f"[check.py] unknown gate(s): {', '.join(sorted(unknown))}. Use --list to see them.")
        return 2

    if "--fast" in args:
        gates = [g for g in gates if g.fast]
        print(
            "[check.py] --fast: lint, format and repo-rule scans only (run the full check before you finish)"
        )
    if only:
        gates = [g for g in gates if g.name in only]
    gates = [g for g in gates if g.name not in skip]

    if "--fix" in args:
        _apply_fixes()

    passed: list[str] = []
    failed: list[str] = []
    for gate in gates:
        print(f"\n[{gate.name}]")
        try:
            ok = gate.fn()
        except Exception as exc:  # a gate runner itself blew up
            print(f"  runner error: {type(exc).__name__}: {exc}")
            ok = False
        print("  PASS" if ok else "  FAIL")
        (passed if ok else failed).append(gate.name)

    print("\n" + "=" * 40)
    print(f"Results: {len(passed)} passed, {len(failed)} failed")
    print("=" * 40)
    if failed:
        print(f"Failed: {', '.join(failed)}")
        print("\nFix the failures above, then run this again until it ends with 0 failed.")
        print("Do not weaken a gate or add a suppression to get green: fix the cause.")
        return 1
    return 0


if __name__ == "__main__":
    _reexec_in_venv()
    raise SystemExit(main())
