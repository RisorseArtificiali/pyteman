import json
import sqlite3
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))

LEGACY_SCHEMA = ("CREATE TABLE results("
                 "cell_id TEXT PRIMARY KEY, status TEXT, result_json TEXT, artifact_dir TEXT)")


def legacy_db(path, cell_id="same", status="done", result=None):
    con = sqlite3.connect(path)
    con.execute(LEGACY_SCHEMA)
    con.execute("INSERT INTO results VALUES (?,?,?,?)",
                (cell_id, status, json.dumps(result if result is not None else {"x": 1}),
                 "/old/art"))
    con.commit()
    con.close()
