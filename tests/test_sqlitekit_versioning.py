"""Tests for pyteman.sqlitekit.versioning."""
import sqlite3

import pytest

from pyteman.sqlitekit import SchemaVersionError, ensure_schema, stored_version


def _con(tmp_path, name="v.db"):
    return sqlite3.connect(str(tmp_path / name))


def test_stored_version_returns_none_without_schema_meta(tmp_path):
    con = _con(tmp_path)
    assert stored_version(con) is None
    con.close()


def test_stored_version_returns_none_with_empty_schema_meta(tmp_path):
    con = _con(tmp_path)
    con.execute("CREATE TABLE schema_meta(key TEXT PRIMARY KEY, value TEXT)")
    con.commit()
    assert stored_version(con) is None
    con.close()


def test_stored_version_reads_stamped_version(tmp_path):
    con = _con(tmp_path)
    con.execute("CREATE TABLE schema_meta(key TEXT PRIMARY KEY, value TEXT)")
    con.execute("INSERT INTO schema_meta VALUES ('schema_version', '5')")
    con.commit()
    assert stored_version(con) == 5
    con.close()


def test_stored_version_raises_on_unreadable_value(tmp_path):
    con = _con(tmp_path)
    con.execute("CREATE TABLE schema_meta(key TEXT PRIMARY KEY, value TEXT)")
    con.execute("INSERT INTO schema_meta VALUES ('schema_version', 'abc')")
    con.commit()
    with pytest.raises(SchemaVersionError, match="unreadable"):
        stored_version(con)
    con.close()


def test_ensure_schema_calls_setup_on_fresh_database(tmp_path):
    con = _con(tmp_path)
    calls = []

    def setup(c, sv):
        calls.append(sv)
        c.execute("CREATE TABLE t(x)")

    ensure_schema(con, 1, setup=setup)
    assert calls == [None]
    assert stored_version(con) == 1
    assert list(con.execute("PRAGMA table_info(t)"))
    con.close()


def test_ensure_schema_skips_setup_when_version_matches(tmp_path):
    con = _con(tmp_path)
    con.execute("CREATE TABLE schema_meta(key TEXT PRIMARY KEY, value TEXT)")
    con.execute("INSERT INTO schema_meta VALUES ('schema_version', '3')")
    con.commit()
    calls = []
    ensure_schema(con, 3, setup=lambda c, sv: calls.append(sv))
    assert calls == []
    con.close()


def test_ensure_schema_calls_setup_on_older_version(tmp_path):
    con = _con(tmp_path)
    con.execute("CREATE TABLE schema_meta(key TEXT PRIMARY KEY, value TEXT)")
    con.execute("INSERT INTO schema_meta VALUES ('schema_version', '1')")
    con.commit()
    calls = []
    ensure_schema(con, 2, setup=lambda c, sv: calls.append(sv))
    assert calls == [1]
    assert stored_version(con) == 2
    con.close()


def test_ensure_schema_refuses_newer_version(tmp_path):
    con = _con(tmp_path)
    con.execute("CREATE TABLE schema_meta(key TEXT PRIMARY KEY, value TEXT)")
    con.execute("INSERT INTO schema_meta VALUES ('schema_version', '99')")
    con.commit()
    with pytest.raises(SchemaVersionError, match="newer version"):
        ensure_schema(con, 1, setup=lambda c, sv: None)
    con.close()


def test_ensure_schema_creates_schema_meta_table(tmp_path):
    con = _con(tmp_path)

    def setup(c, sv):
        c.execute("CREATE TABLE t(x)")

    ensure_schema(con, 1, setup=setup)
    tables = {row[1] for row in con.execute(
        "SELECT * FROM sqlite_master WHERE type='table'")}
    assert "schema_meta" in tables
    con.close()


def test_ensure_schema_stamps_version_even_when_setup_does_not(tmp_path):
    con = _con(tmp_path)
    ensure_schema(con, 5, setup=lambda c, sv: None)
    assert stored_version(con) == 5
    con.close()
