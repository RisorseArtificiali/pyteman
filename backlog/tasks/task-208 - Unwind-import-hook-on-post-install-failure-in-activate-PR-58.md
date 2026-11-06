---
id: TASK-208
title: 'Unwind import hook on post-install failure in activate() (PR #58)'
status: To Do
assignee: []
created_date: '2026-11-06 17:57'
labels:
  - pr-reconciliation
dependencies: []
references:
  - 'https://github.com/RisorseArtificiali/pyteman/pull/58'
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PR #58 (open, CONFLICTING, presence 16%) unwinds the installed import hook when a post-install step fails inside activate(), so a failed activation does not leave a live hook with a half-built dispatcher (RT-01 fail-closed family). Real robustness fix, not cosmetics: verify current activate() still leaks the hook on post-install failure, then revive through the gate chain.
<!-- SECTION:DESCRIPTION:END -->
