# tests/test_kill.py
import multiprocessing as mp
import queue
from pyteman.actions import run_action
from pyteman.rules import Rule

# How long the kill action itself may take before the child is judged stuck.
ACTION_BUDGET_S = 5
# How long the kernel may take to reap a child that has already been SIGKILLed.
# Named rather than written twice because the failure messages quote these: a
# literal in the message beside a literal in the call is two sources for one
# number, and they drift the moment either is tuned.
REAP_BUDGET_S = 5
# Deliberately not 70. actions.py reads the rule as get("exit_code", 70), so
# asking for 70 makes the fixture collide with the fallback and the assertion
# below passes even against a kill branch that ignores the rule entirely.
# Measured: with the source hardcoded to os._exit(70) this test stays green at
# 70 and goes red here. Any value other than the fallback turns the assertion
# back into evidence that the rule was read.
EXPECTED_EXIT_CODE = 66


def child(q):
    try:
        run_action(Rule(id="k", module="m", symbol="f", event="entry",
                        action={"kind": "kill", "exit_code": EXPECTED_EXIT_CODE}), {})
        q.put("survived")
    except SystemExit:
        q.put("systemexit")


def diagnosis(q):
    """Whatever the child managed to say, read without ever waiting.

    A passing child writes nothing here: os._exit ends it inside run_action,
    before either put. So a blocking read would hang precisely when the test
    is green, which is why this is get_nowait and why it is called only from
    a failure message. By then the child has been joined, so anything it did
    send has already been flushed through the feeder thread.
    """
    try:
        return q.get_nowait()
    except queue.Empty:
        return "nothing, so it died before it could report"


def test_kill_uses_os_exit_not_systemexit():
    q = mp.Queue()
    p = mp.Process(target=child, args=(q,))
    p.start()
    try:
        # join(timeout) is a bounded wait and not a termination: when it
        # expires the child is still running with a live pid, so this has to
        # be asked rather than inferred from exitcode, which reads None in
        # exactly that case and would assert as `None == 66`, naming nothing.
        p.join(ACTION_BUDGET_S)
        assert not p.is_alive(), (
            f"the child was still running after {ACTION_BUDGET_S}s, pid "
            f"{p.pid}: the kill action neither exited nor raised"
        )
        assert p.exitcode == EXPECTED_EXIT_CODE, (
            f"expected exit code {EXPECTED_EXIT_CODE}, got {p.exitcode}; the "
            f"child reported {diagnosis(q)}"
        )
    finally:
        if p.is_alive():
            p.kill()
            # SIGKILL cannot be caught, which bounds what the child may still
            # do but not when the kernel reaps it: one stuck in an
            # uninterruptible wait, or writing a core, is reaped late. An
            # unbounded join here would put back the hang this test exists to
            # remove, one path further down, so the wait has a deadline and
            # its expiry is reported rather than declared impossible.
            p.join(REAP_BUDGET_S)
        # Read before close(): is_alive() and pid both raise once the handle
        # is closed.
        leaked = p.pid if p.is_alive() else None
        if leaked is None:
            # Hygiene, and worth being exact about which: _exit_function calls
            # active_children(), whose _cleanup() already discards any child
            # whose poll() has returned, so a reaped child never reaches that
            # unbounded join whether or not this runs, and a live one cannot
            # be closed at all. What close() adds is the deterministic release
            # of the sentinel descriptor rather than waiting for the
            # collector. What forecloses the wedge is the bounded kill and
            # reap above. daemon=True would not have: the same loop sends
            # daemons a catchable SIGTERM and then joins unbounded anyway.
            p.close()
        q.close()
        q.join_thread()
        # Last, so the queue is released even on this path. Nothing in user
        # space can do more about a process that outlived SIGKILL than name
        # it, and naming it is the point: the version this replaced left no
        # pid and no output at all.
        assert leaked is None, (
            f"pid {leaked} was still alive {REAP_BUDGET_S}s after SIGKILL and "
            "is being left behind; the interpreter may still block joining it"
        )
