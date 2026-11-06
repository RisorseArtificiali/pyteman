---
id: TASK-196
title: Patch modules loaded by import forms that bypass the __import__ hook
status: To Do
assignee: []
created_date: '2026-09-29 06:46'
updated_date: '2026-09-29 16:54'
labels:
  - audit-2026-09-16
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found while executing TASK-4 (2026-09-29), probed on master 10f0f12 with /home/pantinor/pyteman-evidence/t191/probe4/probe2.py and probe3.py. The import hook wraps builtins.__import__, so three forms never reach it. The first is importlib.import_module. The second is a relative import that runs AFTER its package was imported, e.g. a function body doing `from . import sub`: the hook receives name '' with level 1, and the pending key 'pkg.sub' never matches. The third is importlib.reload, which re-executes the module and replaces our dispatcher with a fresh function. TASK-4 makes all three visible: the first two stay pending and are reported as never landed, and TASK-4 adds a report for a displaced dispatcher. This task is about SUPPORTING them. Candidates: resolve relative names in hooked() from the returned module's __name__ plus fromlist (cheap, covers the lazy relative case); a sys.meta_path loader wrapper following the importlib protocol, which would cover import_module and reload, but it has to respect the reentrancy constraints in the patcher.py module header. Decide per form with a probe before building.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Lazy relative imports (from . import x inside a function of an already-imported package) patch the target, proved in a subprocess
- [ ] #2 importlib.import_module patches the target, or the decision not to support it is documented with the reason
- [ ] #3 After importlib.reload the rules are served again, or the decision not to re-patch is documented; fire state semantics after a re-patch (once, count) are stated and tested
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Altitude review of the TASK-4 displaced-report work (2026-09-29, /simplify on tree4 at 67c9e2e): the hook sitting on builtins.__import__ is the narrowest chokepoint, and every miss form the new docs describe is an artifact of that layer rather than of Python's import forms. import_module never re-enters builtins.__import__; a function-level relative import resolves inside importlib; reload re-executes through the loader. The deeper fix named for this task is to relocate interception to module execution (loader exec_module or _bootstrap._exec), which all forms share; that would land import_module and lazy relative imports naturally, re-patch at reload time, and collapse three of the four miss forms plus the reload cause displaced() exists for. Only third-party rebinding would still need the report channel.
<!-- SECTION:NOTES:END -->
