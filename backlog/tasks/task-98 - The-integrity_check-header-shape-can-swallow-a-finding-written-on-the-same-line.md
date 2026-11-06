---
id: TASK-98
title: >-
  The integrity_check header shape can swallow a finding written on the same
  line
status: Done
assignee: []
created_date: '2026-09-17 00:03'
updated_date: '2026-09-28 21:56'
labels:
  - audit-2026-09-16
  - sqlitekit
  - deferred-from-task-24
  - confirmed
milestone: m-3
dependencies:
  - TASK-24
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`_is_header` in src/pyteman/sqlitekit/integrity.py recognises the integrity_check header by shape, testing that a line starts with `*** in database ` and ends with ` ***`. The shape is deliberate and documented: the word in the middle is the attached database name, so matching the literal `*** in database main ***` would file an ATTACH-ed database header as damage.

The gap is that the test says nothing about what lies between the two ends. A single line carrying both the header shape and a finding is dropped whole:

    classify_integrity("*** in database main *** wrong # of entries in index idx ***")
    -> {"status": "inconclusive", "classes": [], "unclassified": []}

The finding is in the input and in neither output list. That contradicts the module docstring, which says `unclassified` holds every finding line no signature matched and that it is never discarded and never summarised away. The resulting verdict is an uncertain one rather than a confident wrong one, so this does not invent certainty, but it does discard evidence the module promises to keep.

Not reachable from genuine SQLite output. Real SQLite returns the header and the b-tree findings as one row with embedded newlines, so splitlines separates them before this test ever sees a combined line. The verifier could not produce the shape from SQLite.

Any fix has to keep the ATTACH case working: a header for a database attached as aux1 prints `*** in database aux1 ***` and is an observed sample in the corpus, and a database name can legitimately contain spaces. So a fix forbidding interior spaces would break a real capture, and one forbidding an interior `***` narrows an exotic but legal name.

Raised by the AC2 verification review of TASK-24 and deferred in the same turn, because no capture reaches it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A line carrying the header shape around a real finding no longer loses the finding
- [x] #2 The ATTACH header sample in the corpus still classifies as a header rather than as damage
- [x] #3 A test pins the accounting so that every input finding line reaches either classes or unclassified
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Scout ha nuovamente riprodotto input sintetico header+finding su base7286f69, ma conferma che non deriva dall'output SQLite reale. Non selezionato come prossima unità funzionale: già escluso nel precedente scout65/66 per stessa ragione. Nessuna implementazione autorizzata. Qualunque futura policy deve considerare ambiguità con nome ATTACH legale contenente spazi e sequenze di asterischi; un riconoscimento più stretto può confondere header valido con finding. Il messaggio diagnosis non è prova ulteriore di raggiungibilità. Task resta aperto, non refutato né chiuso.

Reopened 2026-09-28 (TASK-191): the tracker said Done, but PR #137 never merged and master (f2a4ea3) still drops the finding: classify_integrity('*** in database main *** wrong # of entries in index idx ***') returns status inconclusive with empty classes and unclassified. Only 3 of #137's 51 added lines exist on master. The Final Summary above describes the unmerged PR, not a merge.

Merged 2026-09-28 as #183, squash 1eb0118 on master, at approved head 44f408e with CI 7/7 green. _is_header now also refuses a name holding ' ***'. Gates: suite 1435 passed 2 skipped; check passed; seven mutants killed; /simplify; high-effort code review; independent zai review APPROVED at 44f408e (VERDICT.md in ~/pyteman-evidence/t191rev). #137 closed with a pointer to #183.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
PR #137: fix(sqlitekit): prevent header shape from swallowing appended findings\n\nA PRAGMA integrity_check line shaped as both header and finding (e.g. `*** in database main *** wrong # of entries in index idx ***`) satisfied both startswith and endswith checks in `_is_header`, so the entire line was silently dropped. The fix locates the FIRST `" ***"` after the prefix and rejects the line as a pure header when trailing content remains. Three new tests cover the regression, the anchored-needle variant, and the accounting invariant.
<!-- SECTION:FINAL_SUMMARY:END -->
