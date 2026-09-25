"""TASK-92 / SQL-05: a function that owns the capture.

classify_integrity reads text; check_integrity runs the PRAGMA and
captures both the rows and the exception message before handing the
text to classify_integrity. The distinction this function exists to
make is that a file that is not a database produces NOTADB instead
of NO_OUTPUT, because the exception message reaches the classifier
instead of being lost.
"""
import sqlite3

from pyteman.sqlitekit.integrity import (
    check_integrity,
    classify_integrity,
    CLEAN,
    DAMAGED,
    NO_OUTPUT,
)


def test_a_healthy_database_reports_clean(tmp_path):
    db = tmp_path / "ok.db"
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE t(x)")
    con.execute("INSERT INTO t VALUES (1)")
    con.commit()
    con.close()
    res = check_integrity(str(db))
    assert res["status"] == CLEAN


def test_an_empty_file_is_a_valid_database_and_reports_clean(
        tmp_path):
    db = tmp_path / "empty.db"
    db.write_bytes(b"")
    res = check_integrity(str(db))
    assert res["status"] == CLEAN


def test_a_file_that_is_not_a_database_produces_notadb(tmp_path):
    """The case this function exists for.

    A caller redirecting only stdout gets nothing from a non-database
    file, because the PRAGMA raises instead of returning rows.
    classify_integrity("") reports NO_OUTPUT. check_integrity catches
    the exception and feeds the message through, so the same file
    produces NOTADB.
    """
    bad = tmp_path / "garbage.db"
    bad.write_text("this is not a database")
    res = check_integrity(str(bad))
    assert res["status"] == DAMAGED
    assert "NOTADB" in res["classes"]


def test_the_same_non_database_gives_no_output_through_classify():
    """The contrast: classify_integrity with an empty capture."""
    res = classify_integrity("")
    assert res["status"] == NO_OUTPUT


def test_a_damaged_database_reports_damage(tmp_path):
    db = tmp_path / "damaged.db"
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE t(x)")
    con.execute("CREATE INDEX idx ON t(x)")
    con.executemany(
        "INSERT INTO t VALUES (?)",
        [(("s%06d" % i) * 10,) for i in range(200)])
    con.commit()
    rootpage = con.execute(
        "SELECT rootpage FROM sqlite_schema "
        "WHERE type='index' AND name='idx'"
    ).fetchone()[0]
    con.close()
    # Hide the index from the schema so new inserts skip it,
    # then restore it: the count will be wrong.
    con = sqlite3.connect(str(db))
    con.execute("PRAGMA writable_schema=ON")
    sql_text = con.execute(
        "SELECT sql FROM sqlite_schema "
        "WHERE type='index' AND name='idx'"
    ).fetchone()[0]
    con.execute(
        "DELETE FROM sqlite_schema "
        "WHERE type='index' AND name='idx'")
    con.commit()
    con.close()
    con = sqlite3.connect(str(db))
    con.executemany(
        "INSERT INTO t VALUES (?)", [(i,) for i in range(5)])
    con.commit()
    con.close()
    con = sqlite3.connect(str(db))
    con.execute("PRAGMA writable_schema=ON")
    con.execute(
        "INSERT INTO sqlite_schema"
        "(type,name,tbl_name,rootpage,sql)"
        " VALUES('index','idx','t',?,?)",
        (rootpage, sql_text))
    con.commit()
    con.close()
    res = check_integrity(str(db))
    assert res["status"] == DAMAGED


def test_check_integrity_delegates_to_classify_integrity(
        tmp_path):
    """The verdict shape is identical to classify_integrity's."""
    db = tmp_path / "ok.db"
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE t(x)")
    con.commit()
    con.close()
    res = check_integrity(str(db))
    assert set(res) == {
        "status", "classes", "unclassified", "diagnosis", "raw"}


def test_classify_integrity_is_unchanged():
    """AC #3: classify_integrity stays public and unchanged."""
    res = classify_integrity("ok")
    assert res["status"] == CLEAN
    assert res["classes"] == []

    res = classify_integrity("file is not a database")
    assert "NOTADB" in res["classes"]


def test_a_path_that_does_not_exist_is_handled(tmp_path):
    missing = tmp_path / "nonexistent" / "missing.db"
    res = check_integrity(str(missing))
    assert res["status"] != CLEAN


def test_a_directory_is_not_a_database(tmp_path):
    res = check_integrity(str(tmp_path))
    assert res["status"] != CLEAN
