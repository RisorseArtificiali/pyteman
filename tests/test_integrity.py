# tests/test_integrity.py
from pyteman.sqlitekit.integrity import classify_integrity

INCIDENT_ROOT = """*** in database main ***
Tree 22 page 67350 cell 100: Rowid 343597390982 out of order
wrong # of entries in index idx_messages_session_id
"""
CODER_PAOLO_FTS = "malformed inverted index for FTS5 table main.messages_fts"

def test_clean():
    assert classify_integrity("ok")["classes"] == ["CLEAN"]

def test_incident_signature_is_canonical_combined():
    res = classify_integrity(INCIDENT_ROOT)
    assert "CANONICAL_ROWID_DISORDER" in res["classes"]
    assert "CANONICAL_INDEX_COUNT" in res["classes"]
    assert "FTS_ONLY" not in res["classes"]

def test_fts_only():
    assert classify_integrity(CODER_PAOLO_FTS)["classes"] == ["FTS_ONLY"]

def test_notadb():
    assert "NOTADB" in classify_integrity("file is not a database")["classes"]

def test_schema():
    assert "SCHEMA" in classify_integrity("malformed database schema (X)")["classes"]
