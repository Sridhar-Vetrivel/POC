"""Every v1 test module imports the isolated_env fixture, so no test writes to the real log folder."""

from __future__ import annotations

from pathlib import Path

from v1_support import isolated_env, make_world  # noqa: F401  (pytest fixtures)

TESTS = Path(__file__).resolve().parent


def test_every_v1_test_module_imports_the_isolation_fixture():
    missing = [
        p.name
        for p in sorted(TESTS.glob("test_v1_*.py"))
        if "isolated_env" not in p.read_text(encoding="utf-8")
    ]
    assert not missing, f"import isolated_env from v1_support in: {missing}"


def test_there_is_no_second_conftest():
    assert not (TESTS / "conftest.py").exists()
