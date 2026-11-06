---
id: TASK-14.2
title: 'LOG-01 follow-up: consider consolidating firing._annotate with patcher._note'
status: To Do
assignee: []
created_date: '2026-09-18 13:41'
updated_date: '2026-09-28 18:16'
labels:
  - log
  - reuse
  - round-4-review
dependencies: []
parent_task_id: TASK-14
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Round 4 simplify-angle review (2026-09-18) of src/pyteman/firing.py found that the new _annotate(exc, label, secondary_exc) helper (firing.py) duplicates the existing best-effort add_note guard pattern in patcher._note (patcher.py:385-401):

    def _note(exc, text):
        try:
            exc.add_note(text)
        except BaseException:
            pass

firing._annotate additionally builds the note string inside the guarded try (hardening against a hostile str(secondary_exc) or type name), which patcher._note does not do - so the firing version is arguably the better shape of the two, not a reason to keep both as-is.

Reviewer's judgment, and mine: not blocking, because sitecustomize.py imports pyteman.firing.open_log lazily and specifically to avoid the cost of importing the heavier patcher/actions/conditions/rules/targets chain on a cost-sensitive startup path. Importing patcher._note into firing.py (or vice versa) would defeat that isolation. A real fix would need a small shared leaf module (e.g. a note-guard helper) that both firing.py and patcher.py import without either depending on the other's heavier chain, then folding the string-building hardening into the shared version.

Filed per review-recommendation discipline rather than left unfixed and unfiled: the duplication is real and the two guards must be kept in sync in intent (same __notes__-not-a-list failure shape both exist for) even though consolidating them now is out of round-4's scope.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 #1 evaluate whether a shared leaf module (no dependency on actions/conditions/rules/targets) can host one best-effort add_note guard used by both firing.py and patcher.py
- [ ] #2 #2 if consolidation is not worth the churn, explicitly document in both call sites why the duplication is intentional and must be kept in sync
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #77 #125. Added lines already present on master per PR: #77 1/16=6% absentfiles=1  #125 0/12=0%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.
<!-- SECTION:NOTES:END -->
