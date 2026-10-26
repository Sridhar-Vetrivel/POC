"""Draws the audit-log and check-memory block diagram as SVG (docs/images/audit_and_check_memory.svg).
Turn it into PNG with a browser: see docs/audit_and_check_memory.md."""
from pathlib import Path
from xml.sax.saxutils import escape

W, H = 1600, 1280
out = []


def add(s):
    out.append(s)


def text(x, y, s, size=18, weight="400", fill="#1f2937", anchor="middle"):
    add(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}" font-family="Segoe UI, Arial, sans-serif">{escape(s)}</text>')


def box(x, y, w, h, lines, fill="#eff6ff", stroke="#3b82f6", title=True, size=17):
    add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{fill}" stroke="{stroke}" stroke-width="2"/>')
    n = len(lines)
    top = y + h / 2 - (n - 1) * 12 + 5
    for i, line in enumerate(lines):
        bold = title and i == 0
        text(x + w / 2, top + i * 24, line, size=size + (1 if bold else 0), weight="700" if bold else "400")


def arrow(x1, y1, x2, y2, label="", dy=-8, dashed=False):
    d = ' stroke-dasharray="8 6"' if dashed else ""
    add(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#475569" stroke-width="2.5"{d} marker-end="url(#a)"/>')
    if label:
        text((x1 + x2) / 2, (y1 + y2) / 2 + dy, label, size=15, fill="#334155")


add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">')
add('<defs><marker id="a" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto"><path d="M0,0 L9,4.5 L0,9 z" fill="#475569"/></marker></defs>')
add(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
text(W / 2, 48, "Ingenus contract-check server: audit log, login log and shared check memory", 28, "700")
text(W / 2, 78, "Built and tried on a local Postgres 18 with synthetic data (Oct 2026). Not on the VM or at Ingenus yet.", 16, fill="#64748b")

# ---- Diagram 1
add('<rect x="30" y="100" width="1540" height="500" rx="16" fill="#f8fafc" stroke="#cbd5e1"/>')
text(60, 138, "1. Audit log and login log, with history", 22, "700", anchor="start")
box(60, 175, 280, 90, ["Claude Desktop", "the person signs in (Entra)"], "#fef9c3", "#ca8a04")
box(430, 175, 300, 90, ["MCP server", "every tool call and every login"], "#eff6ff", "#3b82f6")
box(820, 160, 340, 120, ["One event per call or login", "who, when, tool, outcome", "never page text, never tokens"], "#f1f5f9", "#64748b")
arrow(340, 220, 430, 220, "token")
arrow(730, 220, 820, 220, "writes")
box(430, 360, 360, 120, ["Local log file (JSONL)", "written FIRST, never lost", "each line holds the hash of", "the line before it (hash chain)"], "#ecfdf5", "#10b981")
box(900, 360, 330, 120, ["Postgres: table events", "searchable history", "who did what, when"], "#ede9fe", "#7c3aed")
arrow(990, 280, 650, 360, "")
arrow(790, 420, 900, 420, "copied", dy=-10)
text(845, 510, "If Postgres is down, nothing is lost: `audit ship` copies the missing events later.", 15, fill="#64748b")
box(1290, 175, 250, 305, ["Commands", "", "audit verify", "finds an edited, removed", "or reordered line", "", "audit query", "by user, tool, event", "", "audit prune", "deletes rows older", "than N days"], "#fff7ed", "#f97316", size=15)
arrow(1230, 420, 1290, 420, "")
text(60, 560, "Limit: a cut at the very END of the log cannot be seen. Keep a copy of the last hash elsewhere. One server process per log file.", 15, fill="#64748b", anchor="start")

# ---- Diagram 2
add('<rect x="30" y="620" width="1540" height="640" rx="16" fill="#f8fafc" stroke="#cbd5e1"/>')
text(60, 658, "2. Shared memory of checks: so the next person does not start from zero", 22, "700", anchor="start")
box(60, 740, 330, 110, ["Day 1: you run a check", "compare_contract_to_sap", "(after the figures are done)"], "#eff6ff", "#3b82f6")
box(540, 690, 340, 100, ["checks", "one row per check: who, when,", "customer, as-of date, totals"], "#ede9fe", "#7c3aed")
box(540, 810, 340, 100, ["check_docs", "the files each check used,", "with the file version"], "#ede9fe", "#7c3aed")
box(540, 930, 340, 120, ["term", "each verified rate with its exact", "quote, page, file fingerprint,", "who verified it, last used"], "#ede9fe", "#7c3aed")
arrow(390, 785, 540, 745, "")
arrow(390, 795, 540, 860, "")
arrow(390, 815, 540, 980, "")
box(1030, 740, 330, 100, ["get_check_history", "what did earlier checks find,", "and has any file changed since?"], "#ecfdf5", "#10b981")
box(1030, 930, 330, 100, ["get_contract_terms", "terms already known, so Claude", "reads only new or changed files"], "#ecfdf5", "#10b981")
arrow(880, 760, 1030, 780, "reads")
arrow(880, 860, 1030, 800, "")
arrow(880, 990, 1030, 980, "reads")
box(1410, 820, 140, 130, ["Day 3:", "Aditya or", "a third", "person"], "#fef9c3", "#ca8a04", size=16)
arrow(1360, 790, 1410, 860, "")
arrow(1360, 980, 1410, 920, "")
text(60, 1090, "Rules", 18, "700", anchor="start")
for i, line in enumerate([
    "A record is shown only if the asker can open every file it used (tested with their own access).",
    "The file stays the truth: if a file changes, its stored terms are set aside and the file is read again.",
    "Stored terms are verified by code against the page, not reviewed by a person. Kept 90 days from last use.",
    "Chats are not shared: the server keeps only what passed through its tools.",
]):
    text(60, 1120 + i * 26, "• " + line, 15, anchor="start")
text(60, 1240, "Status: built and live-tested on a laptop with synthetic data. Open: VM (Aditya), Ingenus acceptance of stored quotes, Part 11 applicability, a server check for incomplete stored terms.", 15, fill="#64748b", anchor="start")
add("</svg>")
Path(__file__).with_name("audit_and_check_memory.svg").write_text("\n".join(out), encoding="utf-8")
print("ok")
