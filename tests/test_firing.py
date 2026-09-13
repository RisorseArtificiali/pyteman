# tests/test_firing.py
import json
from pyteman.firing import FiringLog
from pyteman.rules import Rule

def test_log_records_sequenced_lines(tmp_path):
    p = tmp_path / "f.jsonl"
    log = FiringLog(str(p))
    r = Rule(id="r1", module="m", symbol="f", event="entry", action={"kind": "return_none"})
    log.record(r, {"args": (1,), "kwargs": {}, "fires": 1}, note="x")
    log.record(r, {"args": (), "kwargs": {}, "fires": 2})
    lines = [json.loads(l) for l in p.read_text().splitlines()]
    assert [l["seq"] for l in lines] == [1, 2]
    assert lines[0]["rule"] == "r1" and lines[0]["thread"]
    assert lines[0]["note"] == "x"
