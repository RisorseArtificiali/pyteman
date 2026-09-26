"""Schema versioning for SQLite databases.

Manages a ``schema_meta`` table that records the schema version, refuses
databases written by a newer version than the caller understands, and
delegates creation and migration to a caller-supplied callback so the
versioning infrastructure is reusable across tables.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Callable


class SchemaVersionError(RuntimeError):
    """The database schema version is incompatible with this code."""


def stored_version(con: sqlite3.Connection) -> int | None:
    """Read the schema version from ``schema_meta``, or ``None`` if absent.

    Returns ``None`` for a database that predates schema versioning (no
    ``schema_meta`` table, or no ``schema_version`` row).  Raises
    ``SchemaVersionError`` for unreadable values.
    """
    if not list(con.execute("PRAGMA table_info(schema_meta)")):
        return None
    row = con.execute(
        "SELECT value FROM schema_meta WHERE key='schema_version'"
    ).fetchone()
    if row is None:
        return None
    try:
        return int(row[0])
    except (TypeError, ValueError):
        raise SchemaVersionError(
            f"schema_meta carries an unreadable schema_version {row[0]!r}"
        ) from None


def ensure_schema(
    con: sqlite3.Connection,
    version: int,
    *,
    setup: Callable[[sqlite3.Connection, int | None], None],
) -> None:
    """Create or migrate the database schema to ``version``.

    Reads the stored version first.  Raises ``SchemaVersionError`` when the
    database was written by a newer version than ``version``.

    Calls ``setup(con, stored_version)`` which handles both creation (when
    ``stored_version`` is ``None``) and migration (when ``stored_version``
    is older than ``version``).  The callback is skipped when the stored
    version already equals ``version``.

    After ``setup`` returns, ``schema_meta`` is created if absent and the
    version is stamped.  The whole sequence ends with ``con.commit()``.
    """
    sv = stored_version(con)
    if sv is not None and sv > version:
        raise SchemaVersionError(
            f"database was written by a newer version (schema v{sv}; "
            f"this code understands v{version}), so its rows cannot be "
            "shown to mean what this code would read into them"
        )
    if sv != version:
        setup(con, sv)
    con.execute(
        "CREATE TABLE IF NOT EXISTS "
        "schema_meta(key TEXT PRIMARY KEY, value TEXT)"
    )
    if stored_version(con) != version:
        con.execute(
            "INSERT OR REPLACE INTO schema_meta "
            "VALUES ('schema_version', ?)",
            (str(version),),
        )
    con.commit()
