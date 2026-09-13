# tests/test_barriers.py
import threading
import time
from pyteman.barriers import wait, open as open_barrier, reset_all

def setup_function(fn):
    reset_all()

def test_open_releases_waiter():
    res = {}
    t = threading.Thread(target=lambda: res.__setitem__("w", wait("b1", timeout_s=5)))
    t.start()
    time.sleep(0.1)
    open_barrier("b1")
    t.join(2)
    assert res["w"] is True

def test_timeout_returns_false():
    assert wait("nope", timeout_s=0.1) is False
