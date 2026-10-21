# 0004: v1 signs each user in and reads SharePoint as that user

**Date:** 20 Oct 2026 · **Status:** accepted (by the repo owner, 20 Oct 2026: "go ahead with build the bridge sign-in") · **Phase:** 1, v1 (`MCP-Server/`), steps V1-4 (sign-in) and V1-6 (SharePoint)

## Context

The contracts will live in SharePoint, OneDrive and a network drive, not in a local folder. Claude Desktop cannot
read SharePoint, so the server must. Two ways to give the server access:

1. **One shared identity** for the server (an app permission): simple, no sign-in, but every user sees whatever the
   server account sees, and the log can only say "the server".
2. **Per-user sign-in**: the server reads SharePoint as the person who asked, so each person sees only what they may
   read, and the log names the person.

Ingenus's real folder permissions are unknown (do they differ by person?), and the audit log is a stated need.
The user's Claude account (`sridhar.vetrivel@psiog.com`) is unrelated to Microsoft: Microsoft has never heard of it,
so a separate Microsoft sign-in is needed to say who is asking.

## Decision

1. **Per-user sign-in with the on-behalf-of flow.**
   - The bridge (laptop) signs the user in as a **public client** (the "Ingenus POC Desktop Client" app, loopback
     redirect `http://localhost`, no secret) using `@azure/msal-node`, for the scope
     `api://<server app>/access_as_user`. First sign-in opens a browser; later renewals are silent.
   - The server (`core/auth.py`) accepts a request only with a valid Entra token: signed by the tenant's keys, issuer
     `https://login.microsoftonline.com/<tenant>/v2.0`, audience the server app id, not expired, tenant matches,
     scope `access_as_user` present, algorithm RS256 only. Anything else is a 401 before any tool runs.
   - The server app pins **token version 2** (`requestedAccessTokenVersion: 2`) so the issuer and audience formats are
     the version 2.0 ones.
2. **Delegated, read-only Graph access.** The server swaps the user's token for a Graph token (on-behalf-of, via
   `msal`), proving itself with a **certificate** (no client secret). Permissions: `User.Read`, `Files.Read.All`,
   `Sites.Read.All`, all delegated, admin consent granted. The user's token is never passed on and never logged.
3. **A document-source seam.** `core/sources.py` defines `DocumentSource` (list, stat, read bytes; read-only);
   `LocalFolderSource` is the v0 behaviour, `core/graph.py` has `GraphSource` for one folder of one SharePoint site.
   Selected by `INGENUS_DOC_SOURCE` (`local` or `sharepoint`). The six tools and `get_guide` did not change.
4. **Parsed text is cached per identity** (`core/documents.py`): the key starts with who is reading what, and a file's
   version (eTag) is re-checked at most once a minute. One user's cached text is never handed to another; a test
   covers it.
5. **Safe start-up.** The server refuses to listen on a non-loopback address with sign-in off, and refuses the
   SharePoint source without sign-in.
6. **The log names the person** (`preferred_username` from the token) instead of the Windows user.
7. **Settings and secrets.** Settings come from environment variables, or `MCP-Server/.env` on a developer laptop
   (git-ignored; tests never read it). The only real secret is the certificate's private key, in the git-ignored
   `MCP-Server/secrets/`. See `developer_guide.md`, section 5.1.

## Consequences

- No tool was added; the `get_guide` tool stays the seventh. Dependencies added: `msal`, `requests`, `pyjwt[crypto]`
  (Python) and `@azure/msal-node` (bridge, exact version 7.1.0).
- Verified: 150 offline v1 tests (fake Graph serving the 30 synthetic contracts gives 8,500.00 / 17,000.00), 18 Node
  tests for the bridge's sign-in code, a live check against the dev tenant (`scripts/signin_check.py`), and Claude
  Desktop (20 Oct 2026): sign-in, SharePoint read, Chain X exact, call log naming the signed-in user.
- **Not verified / open:** what Desktop does if the first sign-in is slow; Conditional Access policies that force
  re-sign-in (the bridge retries once on a 401, but a claims challenge is not implemented); delegated
  `Sites.Selected` instead of `Files.Read.All` and `Sites.Read.All` (the stricter option offered to IT); HTTPS from
  another machine (Node and an internal CA); behaviour with many files (the first call took 14.5 s for 30 files).
- The bridge's token cache is a plain file in the user's profile folder (readable by that user only, not
  encrypted). Windows DPAPI is the next step.
- Rejected: one shared server identity (kept as a fallback if per-user access turns out not to matter to Ingenus).
- Not decided here: the central audit and login store, and a shared "check history" across users (questions raised
  20 Oct 2026; each needs its own decision record).
