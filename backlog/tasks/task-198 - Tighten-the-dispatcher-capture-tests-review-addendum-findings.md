---
id: TASK-198
title: Tighten the dispatcher capture tests (review addendum findings)
status: To Do
assignee: []
created_date: '2026-09-29 10:10'
updated_date: '2026-09-30 12:18'
labels:
  - follow-up
  - test-tightening
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Three informational findings from the independent review addendum of TASK-100 (VERDICT-100c.md, APPROVED at 5499db7, none blocking), filed the same turn they were read. All three live in tests/test_patcher.py. A1: _closure_cells compares cell values by identity; a future route to the Patcher through a cell's CONTENTS (e.g. the composite gaining a self reference) would pass unnoticed. Probed honest today (gc referent walk, depth 3, no Patcher reachable); a one-line walk of the cells' referents makes it future-proof. A2: the exit-road logging test asserts a superset of {start,end} while the entry test asserts exactly two records; a duplicate-record regression confined to the exit road would survive. len(records)==2 holds today. A3: PR #86's vacuousness guard assert len(freevars)>0 was not carried over literally; assert _closure_cells(target_mod.plain) restores it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A1: the closure check also rejects Patcher instances reachable through cell contents
- [ ] #2 A2: the exit-road test asserts exactly two records with exact phases
- [ ] #3 A3: the vacuousness guard asserts the dispatcher is a closure at all
- [ ] #4 Full suite and dev.py check green
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Two informational findings from the TASK-14.2 independent verdict (VERDICT-14.md, APPROVED at 7fb14aa, 2026-09-29), filed the same turn they were read. 1) No test pins that the leaf keeps the add_note attribute FETCH inside its guard: the existing RefusesNotes shape raises at CALL time, while an exception whose add_note is a raising property raises at FETCH time; one test with that shape would pin it. 2) The firing road has no hostile-PRIMARY test (RefusesNotes lives on the patcher side), so an unguarded-inline mutant on the firing road is distinguishable in principle but unpinned; the pin needs the leaf's guard proven on that road, which for the internally-raised FiringLogError primary may require a leaf-level unit test rather than an end-to-end row.

From closing TASK-82 against master (2026-09-29): the read-only rules property landed via #186, but no test pins the AC4 rebind half, that a post-construction assignment to p.rules is refused (the property has no setter, verified by reviewer191 during TASK-100); a three-line test beside test_a_ruleset_handed_over_as_an_iterator_is_read_exactly_once closes it.

From the TASK-91 verdict (VERDICT-91.md, APPROVED at 2f06dce, 2026-09-30): the exact-key runtime pin covers the outer verdict keys only; a nested key ADDED to the constructor would pass unseen while the type would not know it. One line in test_verdict_has_exactly_the_typed_keys, set(section) == set(_DatabaseSection.__annotations__) on a per-database sample, makes the two depths symmetric. F2 (status as str rather than a Literal of the six constants) is recorded as a deliberate choice on the verdict file, not a task.

From the TASK-117 verdict (VERDICT-117.md, APPROVED at 03976e9, 2026-09-30): the re-entry order test's module names sort in completion order by coincidence (..._inner before ..._outer alphabetically), so a sort-at-publication mutant passes the new test and is caught only by the older re-entry test whose names sort the other way. Renaming the inner module's fixture constant to a name sorting after the outer's makes the new pin self-sufficient; one rename, nothing more.

From the TASK-55 verdict (VERDICT-55.md, APPROVED at dade6af, 2026-09-30): the completeness argument leans on a construction detail the checker does not state, that the id is a PREFIX of the real component (fingerprint and token always follow it inside _attempt_dir), which is what makes trailing-dot, trailing-space and bare-dot shapes unreachable; one docstring sentence stating the dependency would pin it against a future caller naming a directory with the bare id.

From the TASK-33 verdict (VERDICT-33.md, APPROVED at 646a6ed, 2026-09-30), pin gaps closed the same turn in the evidence pins: the check-job segment now asserts it holds no id-token (F1's compromise shape), and the build step is pinned in the check job's segment. Documented residuals that are safe at runtime: single-line drops inside the smoke step beyond the whole-step anchor (the import is pinned; the print is not), and the unquoted tag comparison failing loudly in the safe direction on spaced tags.

From the TASK-59 verdict (VERDICT-59.md, APPROVED at fa6c5a7, 2026-09-30), same family one layer out, filed the same turn: (a) a read-only db file surfaces as a bare sqlite3.OperationalError from _ensure_schema (connect succeeds lazily; only SchemaVersionError is caught there) and would arrive named by wrapping the DDL failures in MatrixStorageError's vocabulary; (b) an unwritable artifact root surfaces as a bare PermissionError from _prepare_experiment_dir's os.makedirs, arguably MatrixArtifactError which already exists for the containment refusal; (c) informational: the class docstring's two-shapes taxonomy rounds off four in-loop sites, the begin-attempt one naming a cell whose outcome was never produced (the site's own message is precise; a clause would make the docstring exact). Also recorded: the lock layer pre-empts the connect guard for directory-permission shapes, acceptable naming through a different door.
<!-- SECTION:NOTES:END -->
