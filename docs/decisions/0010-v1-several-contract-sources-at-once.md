# 0010: v1 reads several contract sources at once, and the question finds its source

**Date:** 23 Oct 2026 · **Status:** built and tested offline (fake and local sources); **not yet tried on a real SharePoint or OneDrive in this mode** · **Phase:** 1, v1 (`MCP-Server/`)
**Changes decision 0007:** its "one source per server run" no longer holds. The OneDrive and network readers and their guards are unchanged.

## Context

- Decisions 0004 and 0007 read **one** source, chosen at start-up by `INGENUS_DOC_SOURCE`. To test another source you edit
  `.env` and restart. That was a build shortcut, not a client request.
- **SAID (Sridhar, 23 Oct 2026):** a user must not change a setting to ask about a different customer. The server should find
  the source from the question.
- A question such as "Check Chain A against SAP" names no source. The only thing in it that points to a place is the customer,
  so the server has to look in every source, or hold a map from customer to place.
- Ingenus's contracts sit in SharePoint, OneDrive and a network drive (decision 0007, context). Whether one customer's documents
  can be spread over more than one of them is **UNKNOWN** (**ASSUMED** here).

## Decision (Psiog; to be confirmed by Aditya)

1. **Several sources can be switched on together:** `INGENUS_SOURCES=sharepoint,onedrive,network` (any of `local`, `sharepoint`,
   `onedrive`, `network`), using the per-source settings that already exist. If it is not set, `INGENUS_DOC_SOURCE` works exactly as
   before. When both are set, `INGENUS_SOURCES` wins.
2. **A `document_id` carries its source** when several are on: `<source>:<path>`, for example `network:Chain_E/Chain_E_Master.pdf`.
   The part after the colon is checked by that source exactly as when it is the only source (no `..`, no absolute path, no links
   on a share). An id with no source, an unknown source or a source that is not switched on is refused. With one source, ids look
   as they always did.
3. **`find_contract_files` asks every source at once**, each in its own thread, and gives up on a slow one after
   `INGENUS_SOURCES_TIMEOUT` seconds (default 45). Each file names its `source`. The result carries one status line per source and a
   `complete` flag. Customer names are matched against the path **without** the source name.
4. **A source that fails does not hide the others.** It is listed in `sources` with its reason, in `not_checked` as `source <name>`,
   and the note says the list may be incomplete. Only when **every** source fails does the call fail.
5. **Copies across sources:** an identical file (same name and content hash) in two sources is listed once, with the other place in
   `also_in`. A same-named file with different content is listed twice and named in `conflicts`. Two identical files in the *same*
   source are different documents and both stay.
6. **Every other tool routes by the prefix.** Reading pages, the quote check, the check history and the compare tool use the same
   `get_source(settings)` as before; it now returns a router when several sources are on. The comparison, the quote check and the
   SAP code are not changed. The parsed-text cache is keyed by who reads and which sources, as before, so one person's SharePoint
   or OneDrive text is never given to another.
7. **Start-up checks each switched-on source** (SharePoint and OneDrive need sign-in and their settings; the network source needs
   its path) and refuses an unknown name in the list.
8. **Guidance `v3`** (`MCP-Server/guidance/v3/`, served by default; `v2` kept unchanged because the demo results refer to it):
   name each file's source; if `complete` is false say the check is incomplete and which source failed, and never read "no file
   found" as "no contract exists"; if `conflicts` is not empty ask which copy is right.

## Options considered

| Option | Why not (or why later) |
|---|---|
| A customer-to-source map in the ontology | Someone must keep it right, and a wrong or missing entry hides a source **silently**. Fails when a customer spans sources. May return later as a hint to narrow the search |
| Claude chooses a `source` argument | The question rarely names a source, so it would guess |
| One tool per source | The same guessing, and more tools to choose between |
| A catalog or index of documents | **Agreed end state** (Guidelines note section 1, Ontology approach section 9, P4): see the two proposals below. This decision is its **step 1**: the first listing of the sources is what fills the catalog |

## Consequences and limits

- **The answer is only as complete as the sources that answered.** If a source is down and the newest amendment lives there, a
  check can look clean and be wrong. This is the main risk. The result says so (`complete`, per-source status, the note) and the
  guidance tells Claude to say the check is incomplete. The server is stateless, so `compare_contract_to_sap` cannot know that an
  earlier listing was incomplete. **Decided (Sridhar, 23 Oct 2026):** guidance and the flag for the POC; a re-check inside
  `compare` is left for before any real Ingenus data.
- **Speed:** a call takes as long as the slowest source (up to the limit). On 20 Oct the first SharePoint listing took 14.5 s for
  30 files; the network source can take up to `INGENUS_NETWORK_TIMEOUT`. Claude Desktop's own tool timeout is **UNKNOWN (verify)**.
  The cache makes later calls fast.
- **Matching is by name in the path.** It assumes every source names a customer's folders and files alike. **UNKNOWN** at Ingenus.
- **OneDrive is one person's drive:** two users can get different answers to the same question. Correct for permissions, but
  surprising; whether Ingenus keeps official contracts in personal OneDrive is **UNKNOWN**.
- **The network share is read as one service account** (decision 0007), while SharePoint and OneDrive are read as each user. They
  are mixed in one answer.
- **Old check-history records** (decision 0006) saved before this change hold ids with no source. They are shown only when one
  source is on; with several they cannot be opened by id and are hidden. No migration is done for the POC.
- 26 new offline tests (`tests/test_v1_multi_source.py`): files found in the right source, routing of pages and quote checks, bad or
  missing source in an id, a path escape after a valid source, one source failing, all failing, a slow source, a fake three-source
  listing, identical and differing copies, one source unchanged, the settings list, start-up checks, and the synthetic chains A, B,
  E and F giving their expected figures through two sources at once.

## Not built or not verified

- **A real SharePoint and OneDrive in this mode** (the stand-ins are fake sources and local folders). The live QA is section 8b,
  Mode B, of `MCP-Server/docs/demo_guide.md`.
- A `source` argument on `find_contract_files` ("the copy on the shared drive"), a per-customer source hint, and a way for `compare`
  to re-check source health.
- A customer split across sources (needs a new synthetic chain), and the records and search index.

## Related

- [Source routing: impact analysis and proposal](../proposal/multi_source_routing_impact_analysis_and_proposal.md)
- [Records and search index: impact analysis and proposal](../proposal/records_and_search_index_impact_analysis_and_proposal.md) (what comes after this)
- [0007: OneDrive and the network share](0007-v1-onedrive-and-network-share-sources.md) · [0004: sign-in and SharePoint](0004-v1-per-user-sign-in-and-sharepoint-reading.md)
