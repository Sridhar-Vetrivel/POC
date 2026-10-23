"""V1-8: reading contracts from a shared folder reached by path, read-only.

Offline: a temp folder stands in for the share (the same code reads a UNC path such as
\\\\server\\share\\contracts). A real share and the read-only service account come from Psiog IT; until
then this proves the guards: links are never followed, lock and temp files are skipped, an unreadable
file is reported and does not stop the rest.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import date
from decimal import Decimal

import pytest
from v1_support import REPO, chain_x_terms, isolated_env  # noqa: F401  (pytest fixtures)

from ingenus_mcp.core import contracts, documents
from ingenus_mcp.core.config import load_settings
from ingenus_mcp.core.scope import ScopeError
from ingenus_mcp.core.sources import NetworkShareSource, get_source
from ingenus_mcp.server.app import check_startup

CONTRACTS = REPO / "MCP-PlugIn" / "data" / "synthetic" / "contracts"
DEFAULT_EXCLUDES = ("~$*", "*.tmp", "Thumbs.db", "desktop.ini")


@pytest.fixture(autouse=True)
def fresh_cache():
    documents.clear_cache()
    yield
    documents.clear_cache()


def make_link(link, target) -> bool:
    """A directory link without special rights: a junction on Windows, a symlink elsewhere."""
    try:
        if sys.platform == "win32":
            result = subprocess.run(  # fixed argv, no shell
                ["cmd", "/c", "mklink", "/J", str(link), str(target)],
                capture_output=True,
                check=False,
            )
            return result.returncode == 0
        os.symlink(target, link, target_is_directory=True)
        return True
    except OSError:
        return False


def make_share(tmp_path):
    root = tmp_path / "share"
    (root / "Acme").mkdir(parents=True)
    (root / "Acme" / "Acme_Master.txt").write_text("Rebate 5%", encoding="utf-8")
    (root / "Acme" / "Acme_Amendment_1.txt").write_text("Rebate 6%", encoding="utf-8")
    return root


def test_it_reads_the_synthetic_contracts_like_a_local_folder():
    source = NetworkShareSource(CONTRACTS, DEFAULT_EXCLUDES)
    items = source.list_items()
    assert len(items) == 30
    assert source.skipped == []


def test_chain_x_from_a_network_folder_gives_the_agreed_numbers(monkeypatch):
    source = NetworkShareSource(CONTRACTS, DEFAULT_EXCLUDES)
    from ingenus_mcp.core import citations
    from ingenus_mcp.tools.compare_contract_to_sap import compare_contract_to_sap
    from ingenus_mcp.tools.find_contract_files import find_contract_files

    monkeypatch.setattr(contracts, "get_source", lambda settings: source)
    monkeypatch.setattr(citations, "get_source", lambda settings: source)
    listing = find_contract_files(customer="Chain X")
    assert len(listing.files) == 3 and len(listing.excluded_drafts) == 1
    result = compare_contract_to_sap(
        customer_id="SYN-CUST-0001", as_of=date(2026, 8, 31), terms=chain_x_terms()
    )
    assert result.total_monthly_gap == Decimal("8500.00")
    assert result.total_indicative_exposure == Decimal("17000.00")
    assert result.not_checked == []


def test_lock_and_temp_files_are_skipped(tmp_path):
    root = make_share(tmp_path)
    for name in ("~$Acme_Master.docx", "scratch.tmp", "Thumbs.db", "desktop.ini", ".hidden.txt"):
        (root / "Acme" / name).write_text("x", encoding="utf-8")
    names = [i.name for i in NetworkShareSource(root, DEFAULT_EXCLUDES).list_items()]
    assert names == ["Acme_Amendment_1.txt", "Acme_Master.txt"]


def test_a_link_to_a_folder_outside_is_not_followed_and_is_reported(tmp_path):
    root = make_share(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("not for this server", encoding="utf-8")
    if not make_link(root / "Acme" / "link_out", outside):
        pytest.skip("this machine cannot create a directory link")
    source = NetworkShareSource(root, DEFAULT_EXCLUDES)
    items = source.list_items()
    assert [i.rel_path for i in items] == ["Acme/Acme_Amendment_1.txt", "Acme/Acme_Master.txt"]
    assert [rel for rel, _ in source.skipped] == ["Acme/link_out"]
    assert "link was not followed" in source.skipped[0][1]
    with pytest.raises(ScopeError):  # asking for the file through the link by name is refused too
        source.stat("Acme/link_out/secret.txt")


def test_a_link_back_inside_the_share_is_not_followed_either(tmp_path):
    """No loops: a link to the share's own parent folder would otherwise be walked forever."""
    root = make_share(tmp_path)
    if not make_link(root / "Acme" / "loop", root):
        pytest.skip("this machine cannot create a directory link")
    source = NetworkShareSource(root, DEFAULT_EXCLUDES)
    assert len(source.list_items()) == 2
    assert [rel for rel, _ in source.skipped] == ["Acme/loop"]


def test_the_listing_reports_skipped_links_as_not_checked(tmp_path, monkeypatch):
    root = make_share(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    if not make_link(root / "Acme" / "link_out", outside):
        pytest.skip("this machine cannot create a directory link")
    monkeypatch.setenv("INGENUS_DOC_SOURCE", "network")
    monkeypatch.setenv("INGENUS_NETWORK_ROOT", str(root))
    result = contracts.find_contract_files(load_settings(), None, None)
    assert len(result.files) == 2
    assert any(n.item == "Acme/link_out" for n in result.not_checked)


def test_a_file_that_cannot_be_read_is_reported_and_the_rest_still_listed(tmp_path, monkeypatch):
    root = make_share(tmp_path)
    original = NetworkShareSource.read_bytes

    def locked(self, item):
        if item.name == "Acme_Master.txt":
            raise PermissionError("sharing violation")
        return original(self, item)

    monkeypatch.setattr(NetworkShareSource, "read_bytes", locked)
    monkeypatch.setenv("INGENUS_DOC_SOURCE", "network")
    monkeypatch.setenv("INGENUS_NETWORK_ROOT", str(root))
    result = contracts.find_contract_files(load_settings(), None, None)
    assert [f.filename for f in result.files] == ["Acme_Amendment_1.txt"]
    assert any(
        n.item == "Acme/Acme_Master.txt" and "PermissionError" in n.reason
        for n in result.not_checked
    )


def test_a_path_outside_the_root_is_refused(tmp_path):
    source = NetworkShareSource(make_share(tmp_path), DEFAULT_EXCLUDES)
    for bad in ("../x.txt", "Acme/../../x.txt", "/etc/passwd", "C:/Windows/win.ini"):
        with pytest.raises(ScopeError):
            source.stat(bad)


def test_a_missing_share_is_a_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="network folder is not available"):
        NetworkShareSource(tmp_path / "gone", DEFAULT_EXCLUDES).list_items()


def test_a_change_on_the_share_is_seen_after_the_revalidation_time(tmp_path):
    root = make_share(tmp_path)
    source = NetworkShareSource(root, DEFAULT_EXCLUDES)
    assert source.revalidate_seconds > 0  # a stat over a network is slow, so not on every call
    path = "Acme/Acme_Master.txt"
    assert documents.load_document(source, path).pages == ("Rebate 5%",)
    # A different length, so the file's version (modified time and size) changes even when the clock
    # has not ticked between the two writes: the same length was a flaky test on Windows (23 Oct 2026).
    (root / path).write_text("Rebate 9.5%", encoding="utf-8")
    assert documents.load_document(source, path).pages == ("Rebate 5%",)  # still the cached copy
    source.revalidate_seconds = 0
    assert documents.load_document(source, path).pages == ("Rebate 9.5%",)


def test_the_source_never_writes(tmp_path):
    root = make_share(tmp_path)
    before = sorted(p.as_posix() for p in root.rglob("*"))
    source = NetworkShareSource(root, DEFAULT_EXCLUDES)
    source.list_items()
    documents.load_document(source, "Acme/Acme_Master.txt")
    assert sorted(p.as_posix() for p in root.rglob("*")) == before


def test_get_source_builds_the_network_source_from_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("INGENUS_DOC_SOURCE", "network")
    monkeypatch.setenv("INGENUS_NETWORK_ROOT", str(tmp_path))
    source = get_source(load_settings())
    assert isinstance(source, NetworkShareSource)
    assert load_settings().exclude_patterns == DEFAULT_EXCLUDES
    monkeypatch.setenv("INGENUS_EXCLUDE_PATTERNS", "*.bak, ~$*")
    assert load_settings().exclude_patterns == ("*.bak", "~$*")


def test_start_up_needs_the_network_root(monkeypatch):
    monkeypatch.setenv("INGENUS_DOC_SOURCE", "network")
    with pytest.raises(SystemExit, match="INGENUS_NETWORK_ROOT"):
        check_startup(load_settings(), "127.0.0.1", "http")


# --- a share that hangs --------------------------------------------------------------------------


def test_a_hanging_share_fails_the_call_instead_of_hanging(tmp_path, monkeypatch):
    import threading
    import time

    release = threading.Event()
    monkeypatch.setattr(
        NetworkShareSource, "_list_items", lambda self: release.wait(10) or []
    )  # the share does not answer
    source = NetworkShareSource(tmp_path, timeout=0.3)
    started = time.monotonic()
    with pytest.raises(TimeoutError, match="did not answer within 0.3 seconds"):
        source.list_items()
    assert time.monotonic() - started < 3
    release.set()


def test_stat_and_read_are_bounded_too_and_errors_pass_through(tmp_path):
    (tmp_path / "a.pdf").write_bytes(b"x")
    source = NetworkShareSource(tmp_path, timeout=5)
    item = source.stat("a.pdf")
    assert source.read_bytes(item) == b"x"
    with pytest.raises(FileNotFoundError):
        source.stat("missing.pdf")
