# tests/test_integrity.py
from pyteman.sqlitekit.integrity import IntegrityVerdict, classify_integrity

from integrity_corpus import BY_NAME

INCIDENT_ROOT = BY_NAME["incident_root"].text

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

# The fts5_malformed_inverted_index sample's verdict is pinned once, by the
# FTS4/FTS5 pairing loop in test_integrity_classification.py, which asserts
# the status and the classes together; TASK-24's FTS_ONLY-to-FTS_CORRUPTION
# rename rationale lives in docs/integrity.md beside the class name.

def test_notadb():
    assert "NOTADB" in classify_integrity("file is not a database")["classes"]

def test_schema():
    assert "SCHEMA" in classify_integrity("malformed database schema (X)")["classes"]


def test_verdict_has_exactly_the_typed_keys():
    """The runtime dict carries exactly the keys IntegrityVerdict declares."""
    res = classify_integrity("ok")
    assert set(res) == set(IntegrityVerdict.__annotations__)
