---
id: TASK-223
title: >-
  Tree-process probe matches any argv mentioning the child names; an operator's
  suspended editor or grep pollutes the baseline
status: To Do
assignee: []
created_date: '2026-11-09 02:04'
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
Found 2026-11-09 by the TASK-211 closing code-review (finding 3 of 4, low severity, pre-existing). The tree probe _tree_processes in tests/test_example_process_tree.py matches any process whose command line mentions dashboard_sim or tui_child, so unrelated operator processes pollute it: a Ctrl-Z'd editor open on examples/hermes-111912/tui_child.py appears with stat T and fails the stopped-process assert (a stopped process survived) blaming the driver for the operator's suspended editor, and any process mentioning either name that appears between baseline and settle fails the subset assert after the full 5s window naming a phantom survivor. Pre-existing behavior inside the function TASK-211 touched for the vacuous-pass fix; filed separately to keep that delta minimal. Fix direction: match the children's actual invocation shape (the script FILE path as an argv element, e.g. a token ending in dashboard_sim.py or tui_child.py, rather than a bare substring anywhere in the line), so an editor's or grep's command line no longer matches; keep the baseline and settle paths symmetric and consider whether the stopped-process assert needs the same narrowing.
<!-- SECTION:DESCRIPTION:END -->
