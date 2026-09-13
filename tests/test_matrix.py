import sqlite3

from pyteman.runner.matrix import run_matrix
from pyteman.runner.report import matrix_markdown

def test_runs_skips_and_reports(tmp_path):
    calls = []

    def run_cell(cell, adir):
        calls.append(cell["id"])
        return {"signature": "CLEAN" if cell["id"] != "c2" else "CANONICAL_INDEX_COUNT"}

    cells = [{"id": "c1", "params": {"x": 1}}, {"id": "c2", "params": {"x": 2}}]
    db = str(tmp_path / "r.db")
    run_matrix(cells, run_cell, db, str(tmp_path / "art"))
    assert calls == ["c1", "c2"]
    run_matrix(cells, run_cell, db, str(tmp_path / "art"))
    assert calls == ["c1", "c2"]
    out = tmp_path / "m.md"
    matrix_markdown(db, str(out))
    text = out.read_text()
    assert "| c1 |" in text and "| c2 |" in text and "CANONICAL_INDEX_COUNT" in text

def test_failed_cell_returns_failed_then_resumes(tmp_path):
    calls = []
    attempts = {}

    def run_cell(cell, adir):
        calls.append(cell["id"])
        attempts[cell["id"]] = attempts.get(cell["id"], 0) + 1
        if cell["id"] == "c3" and attempts["c3"] == 1:
            raise RuntimeError("first attempt fails")
        return {"signature": "OK"}

    cells = [{"id": "c1", "params": {}}, {"id": "c3", "params": {}}]
    db = str(tmp_path / "r.db")

    out1 = run_matrix(cells, run_cell, db, str(tmp_path / "art"))
    by_id1 = {r["cell_id"]: r for r in out1}
    assert by_id1["c3"]["status"] == "failed"
    con = sqlite3.connect(db)
    assert con.execute("SELECT status FROM results WHERE cell_id='c3'").fetchone()[0] == "failed"
    con.close()

    out2 = run_matrix(cells, run_cell, db, str(tmp_path / "art"))
    assert calls.count("c3") == 2
    by_id2 = {r["cell_id"]: r for r in out2}
    assert by_id2["c3"]["status"] == "done"
    assert by_id2["c1"]["status"] == "skipped"
    con = sqlite3.connect(db)
    assert con.execute("SELECT status FROM results WHERE cell_id='c3'").fetchone()[0] == "done"
    con.close()
