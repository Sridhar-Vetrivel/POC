"""Guidance served by the server (decision 0003): get_guide lists and returns the guides, read fresh."""

from __future__ import annotations

from pathlib import Path

from v1_support import isolated_env, make_world  # noqa: F401  (pytest fixtures)

from ingenus_mcp.core.config import load_settings
from ingenus_mcp.core.guidance import load_guides
from ingenus_mcp.tools.get_guide import get_guide

V2 = {
    "contract-check-playbook",
    "extraction-schema",
    "not-checked-rules",
    "reading-amendments",
    "rebate-and-fee-terms",
    "report-format",
    "untrusted-text-handling",
    "when-to-stop-and-ask",
}
V0_SKILLS = Path(__file__).resolve().parents[2] / "MCP-PlugIn" / "skills" / "v2"


def _write_guide(folder: Path, name: str, description: str, body: str = "Do the thing.") -> None:
    (folder / name).mkdir(parents=True)
    (folder / name / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n", encoding="utf-8"
    )


GUIDANCE = Path(__file__).resolve().parents[1] / "guidance"
UNCHANGED_IN_V3 = ("reading-amendments", "rebate-and-fee-terms", "untrusted-text-handling")


def test_the_server_serves_the_eight_guides():
    assert set(load_guides(load_settings().guidance_dir)) == V2


def test_the_default_guidance_is_v5():
    assert load_settings().guidance_dir.name == "v5"


def test_guidance_v2_is_still_an_exact_copy_of_skills_v2():
    # v2 is what the demo results refer to: it must not be edited in place.
    for name in V2:
        assert (GUIDANCE / "v2" / name / "SKILL.md").read_bytes() == (
            V0_SKILLS / name / "SKILL.md"
        ).read_bytes(), f"{name} differs from MCP-PlugIn/skills/v2"


def test_guidance_v3_changes_only_the_guides_that_know_about_sources():
    for name in V2:
        same = (GUIDANCE / "v3" / name / "SKILL.md").read_bytes() == (
            GUIDANCE / "v2" / name / "SKILL.md"
        ).read_bytes()
        assert same == (name in UNCHANGED_IN_V3), name


def test_guidance_v3_tells_claude_what_to_do_when_a_source_is_down():
    served = load_settings().guidance_dir
    text = {n: (served / n / "SKILL.md").read_text(encoding="utf-8") for n in V2}
    assert "complete" in text["contract-check-playbook"]
    assert "no contract exists" in text["contract-check-playbook"]
    assert "the check is incomplete" in text["report-format"]
    assert "Sources" in text["report-format"]
    assert "conflicts" in text["when-to-stop-and-ask"]
    assert "source <name>" in text["not-checked-rules"]
    assert "source name before the colon" in text["extraction-schema"]


def test_no_names_returns_the_index_only():
    result = get_guide()
    assert {g.name for g in result.available} == V2
    assert all(g.description for g in result.available)
    assert result.guides == []
    assert "contract-check-playbook" in result.note


def test_names_return_the_full_guides_in_one_call():
    result = get_guide(names=["contract-check-playbook", "report-format"])
    assert [g.name for g in result.guides] == ["contract-check-playbook", "report-format"]
    assert "resolve_customer" in result.guides[0].content
    assert not result.guides[0].content.startswith("---")  # header stripped
    assert result.not_found == []


def test_unknown_and_path_like_names_are_not_found_never_read(tmp_path, monkeypatch):
    secret = tmp_path / "secret"
    secret.mkdir()
    (secret / "SKILL.md").write_text(
        "---\nname: secret\ndescription: x\n---\nhidden", encoding="utf-8"
    )
    guides = tmp_path / "guides"
    _write_guide(guides, "real-guide", "A real guide")
    monkeypatch.setenv("INGENUS_GUIDANCE_DIR", str(guides))

    result = get_guide(names=["../secret", "nope", "real-guide"])
    assert [g.name for g in result.guides] == ["real-guide"]
    assert result.not_found == ["../secret", "nope"]


def test_a_guide_added_on_the_server_is_served_on_the_next_call(tmp_path, monkeypatch):
    guides = tmp_path / "guides"
    _write_guide(guides, "first", "The first guide")
    monkeypatch.setenv("INGENUS_GUIDANCE_DIR", str(guides))
    assert {g.name for g in get_guide().available} == {"first"}

    _write_guide(guides, "second", "Added while the server runs")
    assert {g.name for g in get_guide().available} == {"first", "second"}
    assert get_guide(names=["second"]).guides[0].description == "Added while the server runs"


def test_a_broken_guide_is_skipped_not_fatal(tmp_path, monkeypatch):
    guides = tmp_path / "guides"
    _write_guide(guides, "good", "Fine")
    (guides / "bad").mkdir()
    (guides / "bad" / "SKILL.md").write_text("no header here", encoding="utf-8")
    (guides / "mismatch").mkdir()
    (guides / "mismatch" / "SKILL.md").write_text(
        "---\nname: other\ndescription: x\n---\nbody", encoding="utf-8"
    )
    monkeypatch.setenv("INGENUS_GUIDANCE_DIR", str(guides))
    assert {g.name for g in get_guide().available} == {"good"}


def test_no_guidance_folder_says_so(tmp_path, monkeypatch):
    monkeypatch.setenv("INGENUS_GUIDANCE_DIR", str(tmp_path / "missing"))
    result = get_guide()
    assert result.available == [] and "No guidance" in result.note


def test_get_guide_is_logged_like_every_tool(isolated_env):
    get_guide(names=["report-format"])
    log = (isolated_env / "tool_calls.jsonl").read_text(encoding="utf-8")
    assert '"tool":"get_guide"' in log
    assert "Contract" not in log.split('"result"')[1]  # counts only, never the guide text


CHANGED_IN_V4 = (
    "contract-check-playbook",
    "report-format",
    "not-checked-rules",
    "when-to-stop-and-ask",
)


def test_guidance_v4_changes_only_four_guides_and_leaves_v3_alone():
    # v3 is what the first live runs (23 Oct 2026) used: it must not be edited in place.
    for name in V2:
        same = (GUIDANCE / "v4" / name / "SKILL.md").read_bytes() == (
            GUIDANCE / "v3" / name / "SKILL.md"
        ).read_bytes()
        assert same == (name not in CHANGED_IN_V4), name


def test_guidance_v4_fixes_what_the_live_runs_showed():
    served = load_settings().guidance_dir
    text = {n: (served / n / "SKILL.md").read_text(encoding="utf-8") for n in V2}
    report = text["report-format"]
    assert "**every** line, including the lines that match SAP" in report
    assert "source system" in report
    assert "never say the sources returned the same files" in report
    assert "never say the exposure could be higher" in report
    assert "known customer" in text["contract-check-playbook"]
    assert "Never say the customer does not exist" in text["contract-check-playbook"]
    assert "A match with no sales is not a gap" in text["not-checked-rules"]
    assert "Say which sources were searched" in text["when-to-stop-and-ask"]


CHANGED_IN_V5 = ("contract-check-playbook", "report-format")


def test_guidance_v5_changes_only_two_guides_and_leaves_v4_alone():
    # v4 is what the live runs of 23 Oct 2026 used: it must not be edited in place.
    for name in V2:
        same = (GUIDANCE / "v5" / name / "SKILL.md").read_bytes() == (
            GUIDANCE / "v4" / name / "SKILL.md"
        ).read_bytes()
        assert same == (name not in CHANGED_IN_V5), name


def test_guidance_v5_tells_claude_to_use_the_stored_terms_first():
    served = load_settings().guidance_dir
    playbook = (served / "contract-check-playbook" / "SKILL.md").read_text(encoding="utf-8")
    assert "Call `get_contract_terms`" in playbook
    assert "Read only the files marked `read_pages`" in playbook
    assert "**unchanged**" in playbook
    assert "not reviewed by a person" in playbook
    report = (served / "report-format" / "SKILL.md").read_text(encoding="utf-8")
    assert "stored terms" in report and "`set_aside`" in report
