"""Many writers, one log: the hash chain must still verify (several threads, and several server processes)."""

from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path

from v1_support import isolated_env  # noqa: F401

from ingenus_mcp.core import calllog

_WRITER = """
import sys
from pathlib import Path
from ingenus_mcp.core import calllog
path, name, n = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
for i in range(n):
    calllog.write_record(path, {"ts": "2026-10-21T10:00:00.000+00:00", "tool": "t", "user": name, "i": i})
"""


def _verify(path: Path, expected: int) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    report = calllog.verify_chain(lines)
    assert report.ok, report.problem
    assert report.hashed == expected == len(lines)


def test_threads_writing_together_keep_the_chain(tmp_path):
    path = tmp_path / "log.jsonl"
    threads = [
        threading.Thread(
            target=lambda n=n: [
                calllog.write_record(path, {"tool": "t", "user": f"u{n}", "i": i})
                for i in range(40)
            ]
        )
        for n in range(6)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    _verify(path, 240)


def test_several_processes_writing_together_keep_the_chain(tmp_path):
    path = tmp_path / "log.jsonl"
    procs = [
        subprocess.Popen([sys.executable, "-c", _WRITER, str(path), f"p{n}", "40"])
        for n in range(4)
    ]
    assert [p.wait(timeout=120) for p in procs] == [0, 0, 0, 0]
    _verify(path, 160)
