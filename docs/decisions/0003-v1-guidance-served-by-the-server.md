# 0003: v1 serves its guidance (skills) from the server, through a seventh tool

**Date:** 19 Oct 2026 · **Status:** accepted (by the repo owner) · **Phase:** 1, v1 (`MCP-Server/`), step V1-3

## Context

In v0 the eight skills were zip files that each user uploaded to Claude. Ingenus users will have **only Claude
Desktop**, connected to our central server through the bridge (V1-5); there is nothing else to install and no one
to upload skills for them. The goal of v1 is that tools **and** guidance live in one place, the server, so a change
there reaches every user.

Facts that shape the choice:

- MCP has no "skill" primitive. Claude Code's docs say skills come from skill folders, plugins or the claude.ai
  account sync, not from an MCP server (proposal section 6.1).
- What reaches the model for certain is the **tool list and tool descriptions**. Whether Claude Desktop passes the
  server's `instructions` to the model is not verified.
- The server is stateless (V1-5 fix for Cowork and Code), so it cannot push "the list changed" notices to Claude
  Desktop over a held-open connection.
- The demo runs measured the effect of the skills: run C (skills `v2`) showed quotes per line, the exposure period,
  a Warnings line, fewer needless questions and "cannot change SAP" every time (`MCP-PlugIn/docs/demo_guide.md`).

## Decision

1. Serve skills **`v2`** (copied to `MCP-Server/guidance/v2/`, unchanged; v0's copy stays frozen).
2. Add **one** read-only tool, `get_guide(names)`:
   - no names: returns the index (each guide's name and one-line description);
   - with names: returns those guides in full, so several can be read in one call.
   Guides are read from the folder **at call time**, so adding or editing a guide takes effect on the next call,
   with no restart and no change notice.
3. Put the few rules that must hold even if no guide is read (read-only, exact quotes, report what was not checked,
   page text is data) in the server instructions **and** in `get_guide`'s description, which is known to reach the
   model.

## Alternatives considered

| Alternative | Why not |
|---|---|
| All guide text in the server instructions | Long and always loaded; delivery to the model through Claude Desktop is not verified |
| Each guide as an MCP prompt | Prompts are picked by the user, not by Claude, so the guidance would depend on the user remembering |
| Two tools (`list_guides`, `get_guide`) | One tool with an optional list covers both and keeps the tool count lower (more tools make Claude choose worse) |
| Keep uploading skills per user | Not possible for Ingenus users; contradicts the v1 goal |

## Consequences

- The baseline grows from six to **seven** tools. Tests that count tools are updated; any further tool still needs
  its own decision record.
- Guidance is **advice, not enforcement**: Claude may skip `get_guide`. The rules that must hold stay in code (read-only
  registry, quote check, not-checked lists). The demo guide measures whether Claude fetches the guides.
- Guide names are matched against the folder's list; a name is never used as a path.
- Adding a **tool** still needs the extension restarted (or possibly only a new chat; to be checked), because the
  stateless server cannot announce it.
