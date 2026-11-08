---
id: TASK-217
title: _PlanEntry namedtuple for the plan and pending records in patcher.py
status: To Do
assignee: []
created_date: '2026-11-08 10:20'
labels:
  - patcher
  - refactor
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From the TASK-113 review chain (code-review high, 2026-11-08): TASK-113 converted the patcher ledger (_wrapped) to the _LedgerEntry namedtuple, but the sibling records kept the same positional-anonymous-tuple fragility: self._plan entries are read by index at src/pyteman/patcher.py plan_entry[3] (pending()), plan_entry[0] (the import-hook retry and the rules property) and by positional unpack (rule, _, _, described = self._plan[ordinal] in displaced()); self._pending entries by entry[0] == name. A reorder or insertion of a plan field compiles clean and silently shifts every index reader, the exact defect class TASK-113 closed for the ledger. A _PlanEntry namedtuple, same pattern as _LedgerEntry and _Cell, closes the class for the plan structure; namedtuple rather than dataclass so positional unpacks elsewhere keep working.
<!-- SECTION:DESCRIPTION:END -->
