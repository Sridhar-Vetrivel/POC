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


def test_the_server_serves_the_eight_v2_guides():
    assert set(load_guides(load_settings().guidance_dir)) == V2


def test_the_served_guides_are_an_exact_copy_of_skills_v2():
    served = load_settings().guidance_dir
    for name in V2:
        assert (served / name / "SKILL.md").read_bytes() == (
            V0_SKILLS / name / "SKILL.md"
        ).read_bytes(), f"{name} differs from MCP-PlugIn/skills/v2"


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
