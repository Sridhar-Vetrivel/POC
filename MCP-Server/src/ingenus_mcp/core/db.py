"""Where the audit store and the check history keep their rows (decision 0008): a SQLite file or Postgres.

Both stores write their SQL once, with named placeholders (`%(name)s`) and casts (`%(name)s::text`) in
Postgres style. For SQLite the text is rewritten to `:name` and the casts are dropped, so there is one
query to read and test. The two places where the back ends differ (the insertion-order column, and the
schema text) are passed in by the caller.

Postgres: the password is read from a file (INGENUS_PG_PASSWORD_FILE) at connect time, never kept in the
settings or printed. The schema is created on first use, under an advisory lock so that two server
processes starting together do not collide.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql as pgsql

_SCHEMA_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
_PLACEHOLDER = re.compile(r"%\((\w+)\)s")
_CAST = re.compile(r"::\w+")
_LOCK_KEY = 7305  # any fixed number: serialises schema creation across processes

# Every error a store can raise. The callers that must never fail a tool call catch exactly these.
STORE_ERRORS = (sqlite3.Error, psycopg.Error, OSError)

_ready: set[tuple[str, int, str, str, str]] = set()  # schemas already created in this process


@dataclass(frozen=True)
class PgTarget:
    host: str
    port: int = 5432
    dbname: str = "ingenus_audit"
    user: str = "postgres"
    password_file: Path | None = None
    schema: str = "public"

    def __str__(self) -> str:
        return (
            f"postgres://{self.user}@{self.host}:{self.port}/{self.dbname} (schema {self.schema})"
        )

    def password(self) -> str | None:
        if self.password_file is None:
            return None
        return self.password_file.read_text(encoding="utf-8").strip()


Target = Path | PgTarget


def is_postgres(target: Target) -> bool:
    return isinstance(target, PgTarget)


def pick(target: Target, sqlite_text: str, postgres_text: str) -> str:
    """The query text for this back end (used where the insertion-order column differs)."""
    return postgres_text if is_postgres(target) else sqlite_text


class Session:
    def __init__(self, target: Target, conn: Any) -> None:
        self._target = target
        self._conn = conn

    def execute(self, text: str, params: dict[str, Any] | None = None) -> Any:
        if not is_postgres(self._target):
            text = _CAST.sub("", _PLACEHOLDER.sub(r":\1", text))
        return self._conn.execute(text, params) if params else self._conn.execute(text)


def _pg_connect(target: PgTarget, ddl: str) -> Any:
    if not _SCHEMA_NAME.match(target.schema):
        raise ValueError(f"not a usable Postgres schema name: {target.schema!r}")
    conn = psycopg.connect(
        host=target.host,
        port=target.port,
        dbname=target.dbname,
        user=target.user,
        password=target.password(),
        connect_timeout=5,
    )
    try:
        key = (target.host, target.port, target.dbname, target.schema, ddl)
        first = key not in _ready
        if first:
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (_LOCK_KEY,))
            if target.schema != "public":
                conn.execute(
                    pgsql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(
                        pgsql.Identifier(target.schema)
                    )
                )
        conn.execute("SELECT set_config('search_path', %s, false)", (target.schema,))
        if first:
            conn.execute(ddl)
            _ready.add(key)
        conn.commit()
    except BaseException:
        conn.close()
        raise
    return conn


@contextmanager
def session(target: Target, sqlite_ddl: str, postgres_ddl: str) -> Iterator[Session]:
    """One short connection: commits when the block ends normally, rolls back on an error, always closes."""
    if isinstance(target, PgTarget):
        conn = _pg_connect(target, postgres_ddl)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(target, timeout=5)
        conn.executescript(sqlite_ddl)
    try:
        yield Session(target, conn)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
