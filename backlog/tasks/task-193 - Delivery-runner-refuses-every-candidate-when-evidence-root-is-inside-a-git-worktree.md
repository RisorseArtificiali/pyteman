---
id: TASK-193
title: >-
  Delivery runner refuses every candidate when --evidence-root is inside a git
  worktree
status: To Do
assignee: []
created_date: '2026-09-28 23:23'
labels:
  - delivery
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by the independent review of TASK-175 (finding F2, pre-existing at 1eb0118). If --evidence-root lies inside any same-owner git worktree, every run fails with 'Candidate patch has no changes': git apply --numstat runs at the candidate directory, Git discovers the enclosing repository, and from a subdirectory git apply ignores paths outside the current directory, so numstat prints nothing and exits 0. GIT_CEILING_DIRECTORIES equals the numstat call's own cwd, which does not stop discovery from that directory. The failure is closed but the message blames the patch instead of the enclosing repository.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 An evidence root inside a git worktree either works or is refused with a message naming the enclosing repository
- [ ] #2 A test reproduces the evidence root inside a repository and fails without the fix
<!-- AC:END -->
