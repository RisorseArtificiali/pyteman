# src/pyteman/sqlitekit/integrity.py
def classify_integrity(text: str) -> dict:
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    if lines == ["ok"]:
        return {"classes": ["CLEAN"], "raw": text}
    classes = set()
    damage = [l for l in lines if l != "*** in database main ***"]
    for l in damage:
        low = l.lower()
        if "file is not a database" in low:
            classes.add("NOTADB")
        elif "malformed database schema" in low:
            classes.add("SCHEMA")
        elif "out of order" in low:
            classes.add("CANONICAL_ROWID_DISORDER")
        elif "wrong # of entries in index" in low:
            classes.add("CANONICAL_INDEX_COUNT")
    if damage and not classes and all("_fts" in l for l in damage):
        classes.add("FTS_ONLY")
    return {"classes": sorted(classes), "raw": text}
