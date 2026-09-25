# tests/test_integrity.py
from pyteman.sqlitekit.integrity import classify_integrity

from integrity_corpus import BY_NAME

INCIDENT_ROOT = BY_NAME["incident_root"].text
CODER_PAOLO_FTS = BY_NAME["fts5_malformed_inverted_index"].text

def test_clean():
    # CLEAN moved out of 'classes' and into 'status' in TASK-25. A list of
    # damage signatures that also holds the absence of damage makes an empty
    # list mean two opposite things, and reads a healthy database as damaged
    # under a plain `if result["classes"]`.
    res = classify_integrity("ok")
    assert res["status"] == "clean"
    assert res["classes"] == []

def test_incident_signature_is_canonical_combined():
    res = classify_integrity(INCIDENT_ROOT)
    assert "CANONICAL_ROWID_DISORDER" in res["classes"]
    assert "CANONICAL_INDEX_COUNT" in res["classes"]
    assert "FTS_CORRUPTION" not in res["classes"]

def test_fts_corruption():
    # TASK-24 renamed this class from FTS_ONLY. The old name was a claim about
    # the capture as a whole, that it held nothing but FTS lines; the new one
    # is a claim about a line, that SQLite's FTS code wrote it. This message is
    # the one the original incident carried, and it is now matched because the
    # FTS module printed it rather than because the table name ends in _fts.
    assert classify_integrity(CODER_PAOLO_FTS)["classes"] == ["FTS_CORRUPTION"]

def test_notadb():
    assert "NOTADB" in classify_integrity("file is not a database")["classes"]

def test_schema():
    assert "SCHEMA" in classify_integrity("malformed database schema (X)")["classes"]
