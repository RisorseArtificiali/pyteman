import json
import sqlite3

def matrix_markdown(results_db, out_path):
    con = sqlite3.connect(results_db)
    rows = con.execute("SELECT cell_id, status, result_json FROM results "
                       "ORDER BY cell_id").fetchall()
    con.close()
    lines = ["| cell | status | signature |", "|---|---|---|"]
    for cid, status, rj in rows:
        sig = ""
        try:
            r = json.loads(rj or "{}")
            sig = r.get("signature", r.get("error", ""))
        except Exception:
            sig = "?"
        lines.append(f"| {cid} | {status} | {sig} |")
    with open(out_path, "w") as fh:
        fh.write("\n".join(lines) + "\n")
