import json
import os
import sqlite3

def run_matrix(cells, run_cell, results_db, artifact_root):
    """Run every cell once, persisting each outcome to the results db.

    Returned status reflects execution outcome: done, failed (run_cell
    raised) or skipped (a previous run already recorded done). The results
    db is the durable record; failed cells re-run on the next invocation.
    """
    # The runner owns its artifact root: create it before opening the results
    # db, so a fresh root (first run of a new matrix) works without the caller
    # having pre-created anything.
    os.makedirs(os.path.dirname(os.path.abspath(results_db)), exist_ok=True)
    con = sqlite3.connect(results_db)
    con.execute("CREATE TABLE IF NOT EXISTS results("
                "cell_id TEXT PRIMARY KEY, status TEXT, result_json TEXT, artifact_dir TEXT)")
    con.commit()
    out = []
    for cell in cells:
        row = con.execute("SELECT status FROM results WHERE cell_id=?",
                          (cell["id"],)).fetchone()
        if row and row[0] == "done":
            out.append({"cell_id": cell["id"], "status": "skipped"})
            continue
        adir = os.path.join(artifact_root, cell["id"])
        os.makedirs(adir, exist_ok=True)
        try:
            result = run_cell(cell, adir) or {}
            status = "done"
        except Exception as e:
            result = {"error": repr(e)}
            status = "failed"
        con.execute("INSERT OR REPLACE INTO results VALUES (?,?,?,?)",
                    (cell["id"], status, json.dumps(result), adir))
        con.commit()
        out.append({"cell_id": cell["id"], "status": status, "result": result})
    con.close()
    return out
