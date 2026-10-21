# 0007: v1 reads from the signed-in user's OneDrive and from a network share

**Date:** 21 Oct 2026 · **Status:** built and tested offline; not yet tried on a real OneDrive or share · **Phase:** 1, v1, steps V1-7 and V1-8

## Context

Ingenus's contracts sit in SharePoint, OneDrive and a network drive. SharePoint is built (decision 0004). The other two
reuse the document-source seam, so no tool changes.

## Decision

1. **OneDrive** (`INGENUS_DOC_SOURCE=onedrive`, `INGENUS_OD_FOLDER=<folder>`): the same Graph code as SharePoint; the drive
   is the signed-in user's own (`GET /me/drive`, checked against Microsoft's docs on 21 Oct 2026), so each person reads
   their own OneDrive, and the drive id and the text cache are kept per person. A **folder is required**: the server never
   lists a whole OneDrive. Read-only through the same delegated `Files.Read.All` consent.
2. **Network share** (`INGENUS_DOC_SOURCE=network`, `INGENUS_NETWORK_ROOT=<path>`, UNC such as `\\server\share\contracts`
   or a mounted share): read by ordinary file calls as **one account, the one the server runs as** (plan option N1, with a
   read-only service account from IT). Guards:
   - **links are never followed:** symbolic links, junctions and DFS links are skipped and reported as not checked, and a
     file asked for through a link is refused;
   - Office lock files and temp files are skipped (`INGENUS_EXCLUDE_PATTERNS`, default `~$*,*.tmp,Thumbs.db,desktop.ini`);
   - a file that cannot be read (locked, permission) is reported as not checked and does not stop the rest;
   - the folder is re-checked every 10 seconds, not on every call (a stat over a network is slow);
   - **a share that hangs fails the call after `INGENUS_NETWORK_TIMEOUT` seconds (default 20)** instead of hanging it; the stuck
     read runs in a daemon thread that is abandoned (tested with a simulated hang, not a real one);
   - the source never writes.

## Consequences and limits

- **A network share is read as the service account, so every signed-in user sees what that account sees.** Per-user access
  to a share is not enforced; if Ingenus's folder permissions differ by person, N1 is not enough (**UNKNOWN**).
- 21 offline tests (fake Graph for OneDrive; a temp folder, real junctions and a simulated lock for the share).
- **Not verified:** a real OneDrive (needs the 30 PDFs uploaded to a folder), a real UNC share and service account (IT),
  very long paths (>260 characters), DFS namespaces, a real hanging share (only a simulated hang is tested), and a large
  share (there is no metadata index yet).
