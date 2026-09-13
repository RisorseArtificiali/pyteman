# tests/test_kill.py
import multiprocessing as mp
from pyteman.actions import run_action
from pyteman.rules import Rule

def child(q):
    try:
        run_action(Rule(id="k", module="m", symbol="f", event="entry",
                        action={"kind": "kill", "exit_code": 70}), {})
        q.put("survived")
    except SystemExit:
        q.put("systemexit")

def test_kill_uses_os_exit_not_systemexit():
    q = mp.Queue()
    p = mp.Process(target=child, args=(q,))
    p.start()
    p.join(5)
    assert p.exitcode == 70
