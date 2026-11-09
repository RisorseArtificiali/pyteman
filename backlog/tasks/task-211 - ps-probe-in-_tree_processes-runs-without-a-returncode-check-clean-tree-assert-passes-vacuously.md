---
id: TASK-211
title: >-
  ps probe in _tree_processes runs without a returncode check (clean-tree assert
  passes vacuously)
status: Done
assignee: []
created_date: '2026-11-06 21:19'
updated_date: '2026-11-09 02:08'
labels:
  - tests
  - review-finding
dependencies: []
references:
  - tests/test_example_process_tree.py
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found 2026-11-06 by the TASK-145 review chain (reuse same-disease sweep). tests/test_example_process_tree.py:254-256: _tree_processes() runs subprocess.run(["ps", "-eo", "pid=,stat=,args="], capture_output=True, text=True) and reads .stdout with no returncode check and no check=True. If ps fails, stdout is empty, found becomes {}, and _assert_no_tree_left's subset assert (line ~287) passes vacuously: a dead probe is indistinguishable from a clean tree, the same silent-degradation shape TASK-145 fixed for the locale probe. Fix: assert the returncode (carrying stderr in the message) before interpreting stdout, matching the suite idiom (~20 sites).
<!-- SECTION:DESCRIPTION:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Landed on master as cde29b7 (2026-11-09, set 76). The tree probe _tree_processes now refuses to answer when ps itself fails: returncode asserted before stdout is interpreted, carrying rc and both output streams in the message (a signal death leaves stderr empty and the half-written table in stdout), with timeout=10 so a wedged ps errors loudly instead of hanging the suite (the _git_rev precedent; unlike _git_rev the probe does not fold timeout into a marker). The matching loop reads its two fields from one split. The dead-ps test uses a recording fake that pins the exact argv and the timeout, so neither guard can be dropped silently. The same review's sweep also closed the file's one surviving unchecked-result leg: the real-ruleset driver test now pins the driver's own conclusion codes (0/1/3; the stub environment deterministically lands INCONCLUSIVE=3, learned by a first ==0 pin failing live), and every unplanned exception becomes exit 2 through the __main__ wrapper, which the membership pin refuses alone (measured by injecting a post-verdict raise in the finally: old stdout-only leg green, new pin red); a Traceback needle on stderr was tried and dropped with evidence, its only reachable effect being a false positive from child-side tracebacks in the inherited stderr pipe. Gates: /simplify (two nits applied), /code-review high twice (5 findings then a nothing-blocks close with 4, all applied or filed), skeptic CONFIRMED all five claims with independent mutation probes; batteries green on every candidate (final fg857jk8, floor 1627). The pre-existing matcher breadth (any argv mentioning the child names pollutes the baseline) is filed as TASK-223 and is not part of this delta.
<!-- SECTION:FINAL_SUMMARY:END -->
