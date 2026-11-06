---
id: TASK-209
title: 'Pin split choice in report body_rows (PR #66)'
status: To Do
assignee: []
created_date: '2026-11-06 17:57'
labels:
  - pr-reconciliation
dependencies: []
references:
  - 'https://github.com/RisorseArtificiali/pyteman/pull/66'
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PR #66 (open, CONFLICTING, presence 10%) pins the split choice in body_rows so a value containing both newline forms cannot depend on which split runs first. Overlap check against merged #206 (TASK-68 whitespace contract) required: that merge may already state and pin the contract this test wanted.
<!-- SECTION:DESCRIPTION:END -->
