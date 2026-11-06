---
id: TASK-74
title: >-
  RT-20: activate() installs the import hook outside its own try, so a future
  failure in install() would strand it
status: Done
assignee: []
created_date: '2026-09-16 19:12'
updated_date: '2026-09-25 14:16'
labels:
  - rt-01-followup
  - hardening
  - atomicity
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`activate()` calls `p = install(rules, log)` OUTSIDE the try/except that unwinds on failure. `install()` runs `Patcher(rules, log)`, then `p.install_hook()`, then returns.

Not a present bug, verified: nothing executes after `install_hook()` inside `install()`, and `Patcher.__init__` (which CAN raise, since it compiles every expression) runs BEFORE the hook is installed. So today there is no failure window.

The exposure is structural. If `install()` ever grows a statement after `install_hook()` (a log line, a registry entry, a sanity check), a failure there leaves `builtins.__import__` hooked with no handle for `activate()` to uninstall it, and the process runs with an import hook nobody can remove. That is a fail-open of exactly the kind RT-01 exists to rule out, and no test would catch it.

Raised by the high-effort reviewer during the RT-01 / TASK-1 CHANGES REQUESTED round as a "related and also structural rather than a present bug" note under finding F6. Declined for that round because RT-01's scope was explicitly "complete exactly the RT-01 guarantees, no new features", and restructuring activate() to hold a partially-constructed Patcher is not one of them.

Fix shape: either make `install()` unwind its own hook on failure, or have `activate()` build the Patcher and install the hook inside its try so the existing except block covers both.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A failure injected anywhere inside install() after install_hook() leaves builtins.__import__ unhooked when reached through activate()
- [x] #2 A test covers that path and fails against the current code
- [x] #3 No change to the success-path behaviour of install() or activate()
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
PR #58: https://github.com/RisorseArtificiali/pyteman/pull/58\nBranch: work/activate-hook-unwind (commit 9bd9907 on master at 3a38482).\n\nInlined install()'s two steps (Patcher() + install_hook()) into activate()'s try block so a post-hook failure triggers the existing unwind path. New test confirms the fix; mutation probe confirms the old code strands the hook. Full suite: 1191 passed, 2 skipped.
<!-- SECTION:FINAL_SUMMARY:END -->
