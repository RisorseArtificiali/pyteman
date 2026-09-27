# tests/sqlite_harness.py
"""The sqlite read/write helpers shared by the matrix and identity tests.

Promoted from test_matrix_identity.py's query (the try/finally shape the
reuse audit named as the one worth keeping) and its LEGACY_SCHEMA/legacy_db
pair (TASK-45): a pre-provenance database is the same thing any future
migration test needs. Every read closes its connection even when the
caller's assert fails, which connect/execute/close without finally never
promised.
"""
import json
import sqlite3

LEGACY_SCHEMA = ("CREATE TABLE results("
                 "cell_id TEXT PRIMARY KEY, status TEXT, result_json TEXT, artifact_dir TEXT)")


def query(db, sql):
    """One read, one closed connection, whatever the caller does next."""
    con = sqlite3.connect(db)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def legacy_db(path, cell_id="same", status="done", result=None):
    """A pre-provenance database holding one migrated row."""
    con = sqlite3.connect(path)
    try:
        con.execute(LEGACY_SCHEMA)
        con.execute("INSERT INTO results VALUES (?,?,?,?)",
                    (cell_id, status,
                     json.dumps(result if result is not None else {"x": 1}),
                     "/old/art"))
        con.commit()
    finally:
        con.close()
