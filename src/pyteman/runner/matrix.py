import json
import os
import sqlite3

def run_matrix(cells, run_cell, results_db, artifact_root):
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
            con.execute("INSERT OR REPLACE INTO results VALUES (?,?,?,?)",
                        (cell["id"], "done", json.dumps(result), adir))
        except Exception as e:
            result = {"error": repr(e)}
            con.execute("INSERT OR REPLACE INTO results VALUES (?,?,?,?)",
                        (cell["id"], "failed", json.dumps(result), adir))
        con.commit()
        out.append({"cell_id": cell["id"], "status": "done", "result": result})
    con.close()
    return out
