---
id: TASK-197
title: Named plan entries in Patcher._plan instead of positional 4-tuples
status: To Do
assignee: []
created_date: '2026-09-29 07:36'
labels:
  - follow-up
  - refactor
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From the /simplify altitude review of TASK-100 (2026-09-29): self._plan holds positional tuples (rule, when_code, key_code, described), read by index at several sites (the rules property, the dispatcher loop, pending()). A NamedTuple or small dataclass would make each read self-describing. Below TASK-100's scope, filed per the review-recommendation rule. Note: third copies of Hostile/NoNameMeta in tests/test_log_actions.py (566-570, 664-669) were also flagged as optional; they exercise actions.py, outside the patcher/sitecustomize parity pair, and can import from tests/hostile_fixtures.py in the same pass.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every self._plan entry is a named record and no site indexes it positionally
- [ ] #2 Full suite and dev.py check green
<!-- AC:END -->
