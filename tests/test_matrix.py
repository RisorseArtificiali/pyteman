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
