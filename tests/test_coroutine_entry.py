# tests/test_coroutine_entry.py
"""Entry events on coroutine function targets.

Every test uses a real subprocess with sitecustomize activation and a real
event loop, because the wrapper is an async def whose records fire at the
first await; an in-process call cannot reproduce the activation path and a
mocked loop would answer nothing about cancellation. The fixture package is
imported the way a foreign src-layout consumer is, from PYTHONPATH, with
pyteman itself also on PYTHONPATH and nothing installed.
"""
import os
import pathlib
import subprocess
import sys

import pytest

HERE = pathlib.Path(__file__).parent
SRC = HERE.parent / "src" / "pyteman"


FIXTURE_INIT = """\
# Only eager is imported here; submod is deliberately lazy.
from . import eager
"""

FIXTURE_EAGER = """\
def eager_fn():
    return 8
"""

FIXTURE_SUBMOD = """\
import asyncio


async def afn(value):
    await _yield_once()
    return value * 2


async def boom(value):
    await _yield_once()
    raise ValueError("body failed")


async def hang():
    # Never resolves on its own, so a caller genuinely suspends inside the
    # original and cancellation has a real await to land on.
    await asyncio.Event().wait()


async def _yield_once():
    await asyncio.sleep(0)
"""


@pytest.fixture
def aliaspkg(sandbox):
    pkg = sandbox / "aliaspkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    return sandbox


@pytest.fixture
def sandbox(tmp_path):
    pkg = tmp_path / "coropkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(FIXTURE_INIT)
    (pkg / "eager.py").write_text(FIXTURE_EAGER)
    (pkg / "submod.py").write_text(FIXTURE_SUBMOD)
    return tmp_path


def _run(tmp, rules_body, code):
    rf = tmp / "r.yaml"
    rf.write_text(rules_body)
    env = {
        **os.environ,
        "PYTHONPATH": f"{tmp}:{SRC}",
        "PYTEMAN_RULES": str(rf),
        "PYTEMAN_LOG": str(tmp / "pyteman.log"),
    }
    return subprocess.run([sys.executable, "-c", code],
                          capture_output=True, text=True, env=env,
                          cwd=str(tmp), timeout=60)


def _records(tmp):
    log = tmp / "pyteman.log"
    if not log.exists():
        return []
    import json
    return [json.loads(line) for line in log.read_text().splitlines() if line]


RULES_ENTRY = """\
- id: stall-acquire
  point: coropkg.submod.afn
  event: entry
  action: {kind: return_value, value: 99}
  fire: {mode: always}
"""


def test_entry_override_on_a_coroutine_target_is_returned(sandbox):
    """THE feature test: the wrapper is awaited by the ordinary caller, the
    entry rule fires, and its override becomes the awaited result without the
    original body ever running."""
    code = (
        "import asyncio, coropkg.submod\n"
        "print(asyncio.run(coropkg.submod.afn(7)))\n"
    )
    r = _run(sandbox, RULES_ENTRY, code)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "99", r.stdout
    records = _records(sandbox)
    assert len(records) == 2, records
    assert records[0]["rule"] == "stall-acquire"
    assert records[0]["phase"] == "start"
    assert records[1]["phase"] == "end"
    assert "never landed" not in r.stderr, r.stderr


def test_entry_record_fires_at_first_await_not_at_call(sandbox):
    """Building the wrapper coroutine writes nothing; awaiting it writes.

    This is the timing contract the old refusal existed to protect, stated as
    an observable: the record describes the start of the work, and the work
    starts at the first await. The log file is read between the two moments
    from inside the same process, which the firing log supports because every
    record is one O_APPEND write straight to the fd.
    """
    code = (
        "import asyncio, coropkg.submod\n"
        "log = open(__import__('os').environ['PYTEMAN_LOG'])\n"
        "async def main():\n"
        "    coro = coropkg.submod.afn(7)\n"
        "    await asyncio.sleep(0.05)\n"
        "    print('before_await_lines=', len(log.read().splitlines()))\n"
        "    print('result=', await coro)\n"
        "    print('after_await_lines=', len(log.read().splitlines()))\n"
        "asyncio.run(main())\n"
    )
    rules = """\
- id: observe-entry
  point: coropkg.submod.afn
  event: entry
  action: {kind: sleep, ms: 0}
  fire: {mode: always}
"""
    r = _run(sandbox, rules, code)
    assert r.returncode == 0, r.stderr
    lines = dict(part.strip().split("= ", 1)
                 for part in r.stdout.strip().splitlines() if "=" in part)
    assert lines["before_await_lines"] == "0", r.stdout
    assert lines["after_await_lines"] == "2", r.stdout
    assert lines["result"] == "14", r.stdout


def test_exit_rule_on_a_coroutine_target_is_refused_with_the_split(sandbox):
    """Exit remains unsupported and the refusal names the subset: the operator
    is sent to the event field, not to the target."""
    rules = """\
- id: trace-exit
  point: coropkg.submod.afn
  event: exit
  action: {kind: sleep, ms: 0}
  fire: {mode: always}
"""
    # The refusal arrives out of the workload's own import, the shape every
    # lazily-imported target takes: activation itself succeeds because the
    # module is not in sys.modules yet, and the import hook raises when the
    # walk reaches the coroutine leaf. Exit 2 at startup is the already-
    # imported-module shape, covered in test_activation_suspendable_startup.
    code = "import coropkg.submod\nprint('WORKLOAD_RAN')"
    r = _run(sandbox, rules, code)
    assert r.returncode == 1, f"expected exit 1, got {r.returncode}\n{r.stderr}"
    assert "WORKLOAD_RAN" not in r.stdout, r.stdout
    assert "SuspendableTargetError" in r.stderr, r.stderr
    assert "coropkg:afn is a coroutine function" in r.stderr, r.stderr
    assert "exit cannot be timed on it" in r.stderr, r.stderr
    assert "entry events alone are available" in r.stderr, r.stderr
    assert "rule 'trace-exit'" in r.stderr, r.stderr


def test_cancellation_during_the_original_keeps_the_entry_record(sandbox):
    """Cancelling the awaiting task propagates CancelledError from the
    original await; the entry record is already written and nothing else
    records, crashes, or hangs."""
    rules = """\
- id: observe-entry
  point: coropkg.submod.hang
  event: entry
  action: {kind: sleep, ms: 0}
  fire: {mode: always}
"""
    code = (
        "import asyncio, coropkg.submod\n"
        "async def main():\n"
        "    task = asyncio.ensure_future(coropkg.submod.hang())\n"
        "    await asyncio.sleep(0.05)\n"
        "    task.cancel()\n"
        "    try:\n"
        "        await task\n"
        "    except asyncio.CancelledError:\n"
        "        print('CANCELLED')\n"
        "asyncio.run(main())\n"
    )
    r = _run(sandbox, rules, code)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "CANCELLED", r.stdout
    records = _records(sandbox)
    assert len(records) == 2, records
    assert records[0]["phase"] == "start", records


def test_exception_from_the_original_propagates_past_the_entry_record(sandbox):
    rules = """\
- id: observe-entry
  point: coropkg.submod.boom
  event: entry
  action: {kind: sleep, ms: 0}
  fire: {mode: always}
"""
    code = (
        "import asyncio, coropkg.submod\n"
        "try:\n"
        "    asyncio.run(coropkg.submod.boom(7))\n"
        "except ValueError as exc:\n"
        "    print('CAUGHT', exc)\n"
    )
    r = _run(sandbox, rules, code)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "CAUGHT body failed", r.stdout
    records = _records(sandbox)
    assert len(records) == 2, records
    assert records[0]["rule"] == "observe-entry", records


def test_never_awaited_wrapper_writes_no_record(sandbox):
    """The wrapper coroutine the caller discards writes nothing, which is the
    no-silent-record half of the timing contract: no work started, so no
    record claims any did."""
    rules = """\
- id: observe-entry
  point: coropkg.submod.afn
  event: entry
  action: {kind: sleep, ms: 0}
  fire: {mode: always}
"""
    code = (
        "import asyncio, coropkg.submod\n"
        "async def main():\n"
        "    coropkg.submod.afn(7)\n"
        "    await asyncio.sleep(0.05)\n"
        "    print('DISCARDED')\n"
        "asyncio.run(main())\n"
    )
    r = _run(sandbox, rules, code)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "DISCARDED", r.stdout
    assert _records(sandbox) == [], _records(sandbox)


def test_mixed_ruleset_sync_and_coroutine_targets_fire_together(sandbox):
    """One activation, one log, two kinds of target: the sync seam and the
    coroutine seam each fire, which is the reporter's stated use case, a
    tracer for the sync seams in the same run as the async ones."""
    rules = """\
- id: sync-seam
  point: coropkg.eager.eager_fn
  event: entry
  action: {kind: return_value, value: 1}
  fire: {mode: always}
- id: async-seam
  point: coropkg.submod.afn
  event: entry
  action: {kind: sleep, ms: 0}
  fire: {mode: always}
"""
    code = (
        "import asyncio, coropkg, coropkg.submod\n"
        "print(coropkg.eager.eager_fn())\n"
        "print(asyncio.run(coropkg.submod.afn(7)))\n"
    )
    r = _run(sandbox, rules, code)
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == ["1", "14"], r.stdout
    starts = [record for record in _records(sandbox)
              if record["phase"] == "start"]
    assert sorted(record["rule"] for record in starts) == \
        ["async-seam", "sync-seam"], starts
    assert "never landed" not in r.stderr, r.stderr


# --- TASK-179: the guards a mutation can silently disable -------------------

RULES_MIXED = """\
- id: mixed-entry
  point: coropkg.submod.afn
  event: entry
  action: {kind: return_value, value: 99}
- id: mixed-exit
  point: coropkg.submod.afn
  event: exit
  action: {kind: sleep, ms: 0}
"""

# The refusal names the module being patched and the leaf name; on the
# lazy-import road that is the parent package, whose walk passed through
# the submodule to reach the leaf. ONE literal for both doors, so a
# reword of the builder needs one synchronized edit here, not two.
def _split_refusal(target):
    return ("pyteman: " + target + " is a coroutine function, so exit"
            " cannot be timed on it; entry events alone are available on"
            " coroutine functions; refused rather than installed for ")


def test_mixed_entry_exit_ruleset_on_one_coroutine_target_is_refused(sandbox):
    """The install-site all-entry guard, with the mutation it exists to
    kill: no other test activates a mixed ruleset on ONE coroutine target,
    so `all()` mutated to `any()` installs the dispatcher with the exit
    rule in comp.exits, a rule that never fires while `applied` names it.
    This test fails under that mutation."""
    code = (
        "try:\n"
        "    import coropkg.submod\n"
        "except Exception as exc:\n"
        "    print(type(exc).__name__)\n"
        "    print(exc)\n"
    )
    r = _run(sandbox, RULES_MIXED, code)
    assert r.returncode == 0, r.stderr
    lines = r.stdout.strip().splitlines()
    assert lines[0] == "SuspendableTargetError", r.stdout
    assert lines[1] == _split_refusal("coropkg:afn") + (
        "rule 'mixed-entry' at coropkg:submod.afn; "
        "rule 'mixed-exit' at coropkg:submod.afn"), r.stdout


def test_exit_rule_via_alias_extension_is_refused(sandbox, aliaspkg):
    """The extend-site guard through the alias road: after the dispatcher
    is live, another module's attribute is pointed at it and re-patched,
    so the rule reaches the slot through _extend_dispatcher. Deleting that
    guard keeps the whole suite green; this test is what fails."""
    rules = """\
- id: seed-entry
  point: coropkg.submod.afn
  event: entry
  action: {kind: return_value, value: 99}
- id: late-exit
  point: aliaspkg.afn_alias
  event: exit
  action: {kind: sleep, ms: 0}
"""
    code = (
        "import coropkg.submod\n"
        "import aliaspkg\n"
        "aliaspkg.afn_alias = coropkg.submod.afn\n"
        "import sys\n"
        "p = sys._pyteman['patcher']\n"
        "before = coropkg.submod.afn\n"
        "try:\n"
        "    p.force_patch_module('aliaspkg')\n"
        "except Exception as exc:\n"
        "    print(type(exc).__name__)\n"
        "    print(exc)\n"
        "print('unchanged=', coropkg.submod.afn is before)\n"
        "print('still_fires=', __import__('asyncio').run("
        "coropkg.submod.afn(7)))\n"
    )
    r = _run(sandbox, rules, code)
    assert r.returncode == 0, r.stderr
    lines = r.stdout.strip().splitlines()
    assert lines[0] == "SuspendableTargetError", r.stdout
    # The extend door and the install door speak with one builder: both
    # messages are this exact text, so the two copies cannot drift.
    assert lines[1] == _split_refusal("aliaspkg:afn_alias") + (
        "rule 'late-exit' at aliaspkg:afn_alias"), r.stdout
    assert lines[2] == "unchanged= True", r.stdout
    assert lines[3] == "still_fires= 99", r.stdout


def test_entry_rule_via_alias_extension_merges_and_fires(sandbox, aliaspkg):
    """The same road with an entry rule merges into the live coroutine
    dispatcher and fires, which is what makes the exit refusal above a
    refusal about the rule and not about the road."""
    rules = """\
- id: seed-entry
  point: coropkg.submod.afn
  event: entry
  action: {kind: sleep, ms: 0}
- id: late-entry
  point: aliaspkg.afn_alias
  event: entry
  action: {kind: return_value, value: 99}
"""
    code = (
        "import coropkg.submod\n"
        "import aliaspkg\n"
        "aliaspkg.afn_alias = coropkg.submod.afn\n"
        "import sys\n"
        "sys._pyteman['patcher'].force_patch_module('aliaspkg')\n"
        "print('merged=', __import__('asyncio').run("
        "coropkg.submod.afn(7)))\n"
    )
    r = _run(sandbox, rules, code)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "merged= 99", r.stdout
    assert "never landed" not in r.stderr, r.stderr


def test_the_override_does_not_run_the_original(sandbox):
    """A RAN marker in the fixture body: the override test used a pure
    function, so `await original()` before returning the override still
    passed. The body now leaves evidence, and the override path must not."""
    body = FIXTURE_SUBMOD.replace(
        "async def afn(value):\n"
        "    await _yield_once()\n"
        "    return value * 2\n",
        "async def afn(value):\n"
        "    await _yield_once()\n"
        "    with open('ran.marker', 'w') as f:\n"
        "        f.write('ran')\n"
        "    return value * 2\n")
    assert "ran.marker" in body, (
        "the fixture rewrite did not apply; FIXTURE_SUBMOD drifted")
    pkg = sandbox / "coropkg"
    (pkg / "submod.py").write_text(body)
    code = (
        "import asyncio, coropkg.submod, os\n"
        "print(asyncio.run(coropkg.submod.afn(7)))\n"
        "print('marker=', os.path.exists('ran.marker'))\n"
    )
    r = _run(sandbox, RULES_ENTRY, code)
    assert r.returncode == 0, r.stderr
    lines = r.stdout.strip().splitlines()
    assert lines[0] == "99", r.stdout
    assert lines[1] == "marker= False", r.stdout
    # Control: without the rule the marker exists, so the assertion has
    # teeth rather than pinning a fixture that never runs.
    r_control = _run(sandbox, "[]\n", code)
    assert r_control.returncode == 0, r_control.stderr
    control_lines = r_control.stdout.strip().splitlines()
    assert control_lines[0] == "14", r_control.stdout
    assert control_lines[1] == "marker= True", r_control.stdout


# ---------------------------------------------------------------------------
# TASK-181: the async sleep vocabulary. A sleep declared `async: true`
# suspends ONE chain on asyncio.sleep while the loop keeps servicing
# everything else, the wedged-worker shape; a plain sleep keeps the
# blocking vocabulary and stalls the whole loop. The declaration rides the
# RULE, so both shapes stay expressible on the same target, and a sync
# target refuses the declaration rather than degrading it into a stall.
# ---------------------------------------------------------------------------

RULES_ASYNC_SLEEP = """\
- id: wedge-worker
  point: coropkg.submod.afn
  event: entry
  action: {kind: sleep, ms: 400, async: true}
  fire: {mode: always}
"""


def test_an_async_sleep_suspends_one_chain_while_the_loop_lives(sandbox):
    """THE feature test: the target is wedged, the loop is not.

    The discriminator is timestamps, not doneness: a task that finished
    during a blocking stall can also look unfinished at the wrong read.
    The watchdog, a 20ms sleep started while the target is mid-suspend,
    must complete long before the 400ms target does; under a blocking
    sleep the loop is frozen and it cannot complete until after.
    """
    code = (
        "import asyncio, coropkg.submod\n"
        "async def main():\n"
        "    loop = asyncio.get_running_loop()\n"
        "    started = loop.time()\n"
        "    task = asyncio.ensure_future(coropkg.submod.afn(7))\n"
        "    async def watchdog():\n"
        "        await asyncio.sleep(0.02)\n"
        "        return loop.time() - started\n"
        "    w = asyncio.ensure_future(watchdog())\n"
        "    await asyncio.sleep(0.05)\n"
        "    print('wedged=', not task.done())\n"
        "    t_watch = await w\n"
        "    result = await task\n"
        "    t_task = loop.time() - started\n"
        "    print('watchdog_s=', round(t_watch, 2))\n"
        "    print('task_s=', round(t_task, 2))\n"
        "    print('result=', result)\n"
        "asyncio.run(main())\n"
    )
    r = _run(sandbox, RULES_ASYNC_SLEEP, code)
    assert r.returncode == 0, r.stderr
    lines = dict(part.strip().split("= ", 1)
                 for part in r.stdout.strip().splitlines() if "=" in part)
    assert lines["wedged"] == "True", r.stdout
    assert float(lines["watchdog_s"]) < 0.3, r.stdout
    assert float(lines["task_s"]) >= 0.35, r.stdout
    assert lines["result"] == "14", r.stdout
    records = _records(sandbox)
    assert len(records) == 2, records
    assert records[0]["rule"] == "wedge-worker"
    assert records[1]["phase"] == "end"
    assert records[1]["status"] == "slept"
    # The action dump rides the start record, and it is what tells the two
    # sleep vocabularies apart in the log.
    assert "async" in records[0].get("note", ""), records


def test_cancellation_during_the_async_sleep_propagates_with_the_record(sandbox):
    """A cancel lands on the suspension itself and travels like one.

    The record was written before the sleep started, and the terminal says
    the attempt failed with the cancellation rather than leaving an
    unknown-outcome start behind.
    """
    code = (
        "import asyncio, coropkg.submod\n"
        "async def main():\n"
        "    task = asyncio.ensure_future(coropkg.submod.afn(7))\n"
        "    await asyncio.sleep(0.05)\n"
        "    task.cancel()\n"
        "    try:\n"
        "        await task\n"
        "    except asyncio.CancelledError:\n"
        "        print('cancelled= True')\n"
        "asyncio.run(main())\n"
    )
    r = _run(sandbox, RULES_ASYNC_SLEEP, code)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "cancelled= True", r.stdout
    records = _records(sandbox)
    assert len(records) == 2, records
    assert records[1]["status"] == "failed"
    assert "CancelledError" in str(records[1].get("outcome", "")), records


def test_a_plain_sleep_on_a_coroutine_target_still_blocks_the_loop(sandbox):
    """The other vocabulary, unchanged: no declaration, whole-loop stall.

    The watchdog started beside the target cannot complete during the
    stall, so it finishes only after the target does; under the suspended
    shape it would finish in tens of milliseconds. This is the test that
    fails if the split ever rides the dispatcher kind instead of the rule.
    """
    rules = """\
- id: freeze-loop
  point: coropkg.submod.afn
  event: entry
  action: {kind: sleep, ms: 400}
  fire: {mode: always}
"""
    code = (
        "import asyncio, coropkg.submod\n"
        "async def main():\n"
        "    loop = asyncio.get_running_loop()\n"
        "    started = loop.time()\n"
        "    task = asyncio.ensure_future(coropkg.submod.afn(7))\n"
        "    async def watchdog():\n"
        "        await asyncio.sleep(0.02)\n"
        "        return loop.time() - started\n"
        "    w = asyncio.ensure_future(watchdog())\n"
        "    result = await task\n"
        "    t_watch = await w\n"
        "    print('watchdog_s=', round(t_watch, 2))\n"
        "    print('result=', result)\n"
        "asyncio.run(main())\n"
    )
    r = _run(sandbox, rules, code)
    assert r.returncode == 0, r.stderr
    lines = dict(part.strip().split("= ", 1)
                 for part in r.stdout.strip().splitlines() if "=" in part)
    assert float(lines["watchdog_s"]) >= 0.35, r.stdout
    assert lines["result"] == "14", r.stdout


def test_an_async_sleep_on_a_synchronous_target_is_refused(sandbox):
    """No loop to yield to: the declaration is refused, not degraded.

    Silently running it as a blocking sleep would hand the operator the
    exact stall the declaration exists to opt out of, with a ruleset that
    reads as suspending one chain.
    """
    rules = """\
- id: async-on-sync
  point: coropkg.eager.eager_fn
  event: entry
  action: {kind: sleep, ms: 50, async: true}
  fire: {mode: always}
"""
    code = (
        "try:\n"
        "    import coropkg.eager\n"
        "except Exception as exc:\n"
        "    print(type(exc).__name__)\n"
        "    print(exc)\n"
    )
    r = _run(sandbox, rules, code)
    assert r.returncode == 0, r.stderr
    lines = r.stdout.strip().splitlines()
    assert lines[0] == "UnsupportedTargetError", r.stdout
    assert "is synchronous, so a sleep declared async has no event loop" \
        in lines[1], r.stdout
    assert "refused rather than degraded" in lines[1], r.stdout
    assert "rule 'async-on-sync' at coropkg:eager.eager_fn" in lines[1], \
        r.stdout


def test_an_async_sleep_added_by_extension_switches_the_live_driver(
        sandbox, aliaspkg):
    """The driver choice is per call: a dispatcher already serving plain
    rules moves to the awaiting twin the moment an extension adds the
    first async sleep, and back to nothing if none is served. A flag
    captured at construction would wedge this test's first shape only."""
    rules = """\
- id: seed-plain
  point: coropkg.submod.afn
  event: entry
  action: {kind: sleep, ms: 0}
- id: late-wedge
  point: aliaspkg.afn_alias
  event: entry
  action: {kind: sleep, ms: 300, async: true}
"""
    code = (
        "import asyncio, coropkg.submod\n"
        "import aliaspkg\n"
        "aliaspkg.afn_alias = coropkg.submod.afn\n"
        "import sys\n"
        "sys._pyteman['patcher'].force_patch_module('aliaspkg')\n"
        "async def main():\n"
        "    loop = asyncio.get_running_loop()\n"
        "    started = loop.time()\n"
        "    task = asyncio.ensure_future(coropkg.submod.afn(7))\n"
        "    async def watchdog():\n"
        "        await asyncio.sleep(0.02)\n"
        "        return loop.time() - started\n"
        "    w = asyncio.ensure_future(watchdog())\n"
        "    await asyncio.sleep(0.05)\n"
        "    t_watch = await w\n"
        "    result = await task\n"
        "    print('watchdog_s=', round(t_watch, 2))\n"
        "    print('result=', result)\n"
        "asyncio.run(main())\n"
    )
    r = _run(sandbox, rules, code)
    assert r.returncode == 0, r.stderr
    lines = dict(part.strip().split("= ", 1)
                 for part in r.stdout.strip().splitlines() if "=" in part)
    assert float(lines["watchdog_s"]) < 0.2, r.stdout
    assert lines["result"] == "14", r.stdout


@pytest.mark.parametrize("late_event", ["entry", "exit"])
def test_an_async_sleep_extending_a_sync_dispatcher_is_refused(
        sandbox, aliaspkg, late_event):
    """The extend door refuses what the install door refuses.

    An alias attribute or any later patch onto a slot a Patcher already
    took must not merge an async-declared sleep into a synchronous
    dispatcher and serve it as the blocking sleep: the degradation the
    install door refuses, arriving by the other road. Both events, for
    the same reason the install door checks every spec.
    """
    rules = (
        "- id: seed-sync\n"
        "  point: coropkg.eager.eager_fn\n"
        "  event: entry\n"
        "  action: {kind: sleep, ms: 0}\n"
        "- id: late-async\n"
        "  point: aliaspkg.eager_alias\n"
        f"  event: {late_event}\n"
        "  action: {kind: sleep, ms: 300, async: true}\n"
    )
    code = (
        "import coropkg.eager\n"
        "import aliaspkg\n"
        "aliaspkg.eager_alias = coropkg.eager.eager_fn\n"
        "import sys\n"
        "before = coropkg.eager.eager_fn\n"
        "try:\n"
        "    sys._pyteman['patcher'].force_patch_module('aliaspkg')\n"
        "except Exception as exc:\n"
        "    print(type(exc).__name__)\n"
        "    print(exc)\n"
        "print('unchanged=', coropkg.eager.eager_fn is before)\n"
        "print('still_fires=', coropkg.eager.eager_fn())\n"
    )
    r = _run(sandbox, rules, code)
    assert r.returncode == 0, r.stderr
    lines = r.stdout.strip().splitlines()
    assert lines[0] == "UnsupportedTargetError", r.stdout
    # One text, both doors: this is the install door's message verbatim,
    # so the two refusals cannot drift apart.
    assert lines[1] == (
        "pyteman: aliaspkg:eager_alias is synchronous, so a sleep declared"
        " async has no event loop to yield to and would block the thread"
        " instead; refused rather than degraded for"
        " rule 'late-async' at aliaspkg:eager_alias"), r.stdout
    assert lines[2] == "unchanged= True", r.stdout
    assert lines[3] == "still_fires= 8", r.stdout


def test_an_override_after_an_awaiting_rule_consumes_through_the_twin(sandbox):
    """The entry contract itself, driven through the awaiting road.

    The twin is the sync driver statement for statement; this pins that
    the two contract facts survive the divergence point: ruleset order
    across an awaiting rule, and an override consumed by the iteration
    that won it, nothing after it running.
    """
    rules = """\
- id: wedge-first
  point: coropkg.submod.afn
  event: entry
  action: {kind: sleep, ms: 20, async: true}
- id: override-second
  point: coropkg.submod.afn
  event: entry
  action: {kind: return_value, value: 99}
"""
    code = (
        "import asyncio, coropkg.submod\n"
        "async def main():\n"
        "    loop = asyncio.get_running_loop()\n"
        "    started = loop.time()\n"
        "    print('result=', await coropkg.submod.afn(7))\n"
        "    print('elapsed_ok=', loop.time() - started >= 0.015)\n"
        "asyncio.run(main())\n"
    )
    r = _run(sandbox, rules, code)
    assert r.returncode == 0, r.stderr
    lines = dict(part.strip().split("= ", 1)
                 for part in r.stdout.strip().splitlines() if "=" in part)
    assert lines["result"] == "99", r.stdout
    assert lines["elapsed_ok"] == "True", r.stdout
    records = _records(sandbox)
    assert len(records) == 4, records
    assert [rec["rule"] for rec in records] == [
        "wedge-first", "wedge-first", "override-second", "override-second"], \
        records
