"""The skills pack and the MCP prompt are guidance files. Check they are well formed."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILLS = sorted((ROOT / "skills" / "v1").iterdir())
EXPECTED = {
    "contract-check-playbook",
    "reading-amendments",
    "extraction-schema",
    "rebate-and-fee-terms",
    "report-format",
    "not-checked-rules",
    "untrusted-text-handling",
    "when-to-stop-and-ask",
}


def frontmatter(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    assert match, f"{path} must start with a YAML frontmatter block"
    return yaml.safe_load(match.group(1)), match.group(2)


def test_the_eight_planned_skills_exist():
    assert {p.name for p in SKILLS} == EXPECTED


@pytest.mark.parametrize("folder", SKILLS, ids=lambda p: p.name)
def test_each_skill_has_a_matching_name_and_a_short_description(folder):
    meta, body = frontmatter(folder / "SKILL.md")
    assert meta["name"] == folder.name  # the docs say the folder name must match the skill name
    assert len(meta["name"]) <= 64
    # Anthropic's help article gives 200 characters as the description limit (verify).
    assert 20 < len(meta["description"]) <= 200
    assert len(body.strip()) > 200


def test_skills_only_refer_to_tools_that_exist():
    from ingenus_plugin.core import tools as _tools  # noqa: F401
    from ingenus_plugin.core.registry import TOOLS

    known = set(TOOLS)
    mentioned = set()
    for folder in SKILLS:
        mentioned |= set(
            re.findall(r"`([a-z_]+)`", (folder / "SKILL.md").read_text(encoding="utf-8"))
        )
    tool_like = {m for m in mentioned if m.startswith(("get_", "find_", "resolve_", "compare_"))}
    assert tool_like <= known, f"Skills mention tools that do not exist: {tool_like - known}"
    assert {
        "resolve_customer",
        "find_contract_files",
        "get_contract_pages",
        "compare_contract_to_sap",
    } <= tool_like


def test_the_prompt_file_has_the_customer_placeholder_and_names_real_tools():
    from ingenus_plugin.core import tools as _tools  # noqa: F401
    from ingenus_plugin.core.registry import TOOLS

    text = (ROOT / "prompts" / "contract_check.v1.md").read_text(encoding="utf-8")
    assert "{customer}" in text
    named = set(re.findall(r"`([a-z_]+)`", text))
    assert {n for n in named if n.startswith(("get_", "find_", "resolve_", "compare_"))} <= set(
        TOOLS
    )
