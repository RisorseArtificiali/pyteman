# tests/test_barriers.py
import threading
import pytest
from pyteman import barriers
from pyteman.barriers import wait, open as open_barrier, reset_all

# How long a wait() given a 0.1s budget may take to come back before it is
# judged to be ignoring that budget. Wide enough that a loaded machine cannot
# trip it, and a constant because the failure message quotes it.
HONOURED_TIMEOUT_S = 5
# The budget the instrumented waiter below is given. Named for the same reason
# as the one above, which the first version of that test failed to apply to
# itself: it passed 5 to wait() and then wrote "5s" into the message, two
# sources for one number. The join that outlives it is derived rather than
# written as its own literal, so the relation the comment claims is executed
# rather than asserted in prose.
WAITER_BUDGET_S = 5

@pytest.fixture(autouse=True)
def clean_barrier_state():
    # Both sides, not only the front. The test below seeds _state with an
    # instrumented Event, and leaving that behind would hand it to whatever
    # runs next. reset_all rebinds the module global rather than clearing it,
    # which suffices here only because wait() and open() re-read that global
    # on every call, so nothing carries the old mapping across the reset.
    reset_all()
    yield
    reset_all()

class WatchedEvent(threading.Event):
    """An Event that reports when a waiter has reached the blocking call.

    Instrumentation belonging to this test alone; src/pyteman/barriers.py is
    unchanged. The signal is raised from inside the call rather than from just
    before it, and that is the whole reason this class exists. barriers.wait()
    runs setdefault, then is_set(), then ev.wait(), so a thread parked between
    the first two has registered without ever blocking. A test that watched
    for registration would therefore prove nothing about whether open() had
    anyone to release, and would stay green under the inverted order.

    What it reports is arrival at that call and not a thread already parked:
    entered is set immediately before super().wait() runs, so an open() landing
    in that gap is answered by is_set() and the waiter never blocks. The claim
    this supports is therefore that the waiter reached the waiting path, which
    is what makes the inverted order detectable, and it stops there. Closing
    the gap would mean reaching into the Event's own condition variable, which
    is more coupling to CPython internals than the claim is worth.
    """
    def __init__(self):
        super().__init__()
        self.entered = threading.Event()

    def wait(self, timeout=None):
        self.entered.set()
        return super().wait(timeout)

def test_open_releases_waiter():
    """open() releases a waiter that has reached the blocking call.

    This used to sleep 100ms and hope. Measured, that sleep was not holding
    the assertion up at all: wait() and open() both call setdefault, and
    wait() short-circuits on is_set(), so the call returns True under every
    interleaving including the inverted one. The old test was green even when
    open() ran entirely before the thread started, which is why deleting the
    sleep alone would have left a test that cannot fail.
    """
    watched = WatchedEvent()
    barriers._state["b1"] = watched
    res = {}
    # daemon for the same reason the timeout test below gives: join(timeout)
    # bounds the wait but does not end the thread, and a waiter parked on
    # something watched.set() cannot reach would otherwise survive this test
    # and wedge interpreter exit, where threading._shutdown joins non-daemon
    # threads with no deadline. Measured: without this the wedged case is
    # killed by the outer ceiling with its pytest report still buffered, so it
    # reports nothing at all; with it the same case fails at line 66 and says
    # what happened.
    t = threading.Thread(
        target=lambda: res.__setitem__("w", wait("b1", timeout_s=WAITER_BUDGET_S)),
        daemon=True,
    )
    t.start()
    try:
        assert watched.entered.wait(5), (
            "the waiter never reached ev.wait(), so the open() below had "
            "nobody to release and this test would prove nothing"
        )
        open_barrier("b1")
        # Outlives the waiter's own budget on purpose, and derives from it so
        # that raising one cannot leave the other behind. The other way round
        # the join gives up first, and an unreleased waiter then surfaces as a
        # KeyError on res rather than as anything about barriers.
        t.join(WAITER_BUDGET_S * 2)
        assert not t.is_alive(), (
            f"the waiter was not released within {WAITER_BUDGET_S * 2}s"
        )
        assert res["w"] is True, (
            f"the waiter returned False, so it exhausted its own "
            f"{WAITER_BUDGET_S}s timeout instead of being released: open() "
            "did not set the event"
        )
    finally:
        # Releases the waiter on any path, including the one where it is still
        # blocked because open() never reached it.
        watched.set()
        t.join(5)

def test_timeout_returns_false():
    # Called on a thread rather than inline, and that is the whole point of
    # the extra lines. Inline, a wait() that stopped honouring timeout_s would
    # block forever with no output, which is the exact failure this tranche
    # exists to remove; a mutation confirmed it wedges the session rather than
    # going red. The thread is a daemon so even the wedged case cannot outlive
    # pytest, which a child process could not promise.
    res = {}
    t = threading.Thread(
        target=lambda: res.__setitem__("w", wait("nope", timeout_s=0.1)),
        daemon=True,
    )
    t.start()
    t.join(HONOURED_TIMEOUT_S)
    assert not t.is_alive(), (
        f"wait() had not returned {HONOURED_TIMEOUT_S}s after being given a "
        "0.1s budget, so it is not honouring timeout_s at all"
    )
    assert res["w"] is False, (
        "wait() returned True for a barrier nobody ever opened, so it is "
        "reporting a timeout as a successful release"
    )

def test_a_barrier_opened_first_releases_a_later_waiter_without_blocking():
    """The other order: open() lands before anyone has arrived.

    The companion above needs a waiter parked inside ev.wait() before open()
    runs. This one needs the opposite, and it is the case where the budget is
    never consulted: is_set() answers first, so an instrumented Event's wait()
    must never be reached. Watching for that is what separates this from a
    test that merely asserts True, which the timing test above already gets
    for free under either order.
    """
    watched = WatchedEvent()
    barriers._state["b2"] = watched
    open_barrier("b2")
    assert wait("b2", timeout_s=0.0) is True
    assert not watched.entered.is_set(), (
        "wait() entered the blocking call for a barrier that was already "
        "open, so an open() is not short-circuited and a zero budget would "
        "report a timeout"
    )

def test_open_creates_and_sets_a_fresh_barrier():
    """open() on a name nobody has used yet creates the Event and sets it.

    Every other test pre-seeds _state before calling open(), so the
    setdefault in open() always retrieves an existing Event. This is the
    only test that exercises the creation branch: open() is the first
    call to name the barrier, and a subsequent wait() must find it
    already set.

    The mutation this kills::

        def open(name):
            with _lock:
                if name in _state:
                    _state[name].set()

    Against that mutation open() is a no-op on a fresh name, wait()
    creates a new unset Event via its own setdefault, is_set() returns
    False, ev.wait() times out, and the assertion below fails.
    """
    open_barrier("fresh")
    assert wait("fresh", timeout_s=5) is True, (
        "wait() returned False for a barrier that open() should have "
        "created and set; the creation branch of open() is broken"
    )


# --- strict mode -----------------------------------------------------------

def test_refusal_is_none_unless_the_switch_is_on(monkeypatch):
    monkeypatch.delenv("PYTEMAN_STRICT_BARRIER", raising=False)
    assert barriers.refusal("b", 0.5) is None
    # Any value other than the documented "1" leaves the default in place:
    # an operator who wrote something else has not opted in, and guessing
    # that they meant to would refuse experiments they expected to run.
    monkeypatch.setenv("PYTEMAN_STRICT_BARRIER", "0")
    assert barriers.refusal("b", 0.5) is None
    monkeypatch.setenv("PYTEMAN_STRICT_BARRIER", "1")
    refused = barriers.refusal("b", 0.5)
    assert isinstance(refused, barriers.BarrierTimeoutError)
    # The name and the duration are the two facts the operator needs to find
    # the rule that failed, and they are the same two the terminal record
    # carries.
    assert "'b'" in str(refused) and "0.5" in str(refused)
