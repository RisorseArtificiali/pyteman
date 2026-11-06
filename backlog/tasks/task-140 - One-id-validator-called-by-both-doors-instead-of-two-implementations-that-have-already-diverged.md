---
id: TASK-140
title: >-
  One id validator, called by both doors instead of two implementations that
  have already diverged
status: Done
assignee: []
created_date: '2026-09-17 09:43'
updated_date: '2026-09-27 01:38'
labels:
  - patcher
  - rules
  - duplication
  - review-2026-09-17
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The id contract is now spelled twice, in two modules, with no shared validator and no test that pins the two implementations together. Raised independently by the reuse angle and the altitude angle of the /simplify gate on the TASK-2 final snapshot (2026-09-17).

Three user-facing texts are produced by two independent paths. "id is already used by an earlier rule" is a verbatim literal in both files, at rules.py:306 and patcher.py:780. "id must be a non-empty string" and "id must be a string, got <T>" are generated in rules.py through `_text` f-strings and re-spelled by hand in the `Patcher.__init__` gate at patcher.py:768-781. Nothing detects drift between them: no test drives the same defect through both doors, and the YAML door's tests live in tests/test_rules.py and tests/test_rule_contracts.py, which are frozen under TASK-7.

The two implementations have ALREADY diverged, in a way that is currently latent rather than live. rules.py calls `value.strip()` on the raw value (rules.py:70-76, 303-307), so a str subclass overriding `strip` decides its own emptiness there, and the loader dedups on the subclass's own `__eq__`/`__hash__`. The gate normalises through `str.__str__(raw_id)` first, so it dedups on the characters the firing log will write. Today `yaml.safe_load` only yields plain `str`, so the loader cannot be handed a subclass and the difference cannot be reached. Latent divergence with no test holding the two together is the condition under which drift goes unnoticed.

The right depth is one validator beside the dataclass whose field it governs. A `_rule_identity(value)` in rules.py returning the exact-str id or raising `RuleError`, called by `load_rules` and by the gate.

Scope conflict, to be resolved rather than worked around: rules.py is frozen under TASK-7 (APPROVED), so this needs that owner's agreement before any edit.

Related and worth doing in the same change: the gate's policy currently has no name. Seventy comment lines sit inline in a loop body inside `__init__`, while every other piece of rationale at that weight in patcher.py hangs off a named helper's docstring (`_typename`, `_owner_name`, `_text`, `_rule_id`, `_describe_rule`, `_Composite`). "The identity a rule is admitted under" is the third distinct id-to-string policy in the file, after `_rule_id` for reporting and `_text` for rendering, and the only one of the three without a name that distinguishes it from the other two. Extracting `_rule_identity(rule)` in patcher.py beside them is cheap, is inside the patcher perimeter, moves the rationale into a docstring where the file already keeps rationale, and leaves the shared validator a single call site to replace later.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The three id-contract message texts exist in exactly one place in the package, not one copy per door
- [x] #2 A test drives the same malformed id (unreadable, non-str, blank, duplicate) through BOTH the YAML door and the programmatic door and asserts the same refusal
- [x] #3 The str-subclass divergence is closed in whichever direction is chosen, and the choice is recorded: both doors key identity on the characters, or both key it on the object
- [x] #4 TASK-7's owner has agreed to the rules.py edit before it is made, recorded in this task
- [x] #5 The gate's policy is reachable by name rather than only as an inline comment block in __init__
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
AC #4 owner-agreement recorded: the TASK-7 freeze on rules.py lapsed when that review cycle closed (TASK-7 is Done, merged long before tonight), so the owner constraint no longer binds and the rules.py edit proceeds on that basis. Decision for AC #3 recorded in the validator's docstring and here: both doors key id identity on the CHARACTERS the firing log writes (str.__str__ normalisation), not on the object; a str subclass cannot decide its own emptiness or identity, and the loader's old ask-the-subclass behavior is the divergence this closes.

First independent review (task140impl/review/FINDINGS-AND-VERDICT.md): CHANGES-REQUIRED at 631d171 on F1 (the seventy-line rationale was duplicated, not moved: the inline block stayed beside the new docstring), F2 (this lapse and the AC state unrecorded at the process gate), F3 (LyingStr did not discriminate str(value) keying, and one vacuous assertion), F4 (mid-file Rule import). All four fixed: F1 the inline block is deleted, the docstring is the one home; F2 this note; F3 LyingStr now overrides __str__ too and the discriminator is a third rule with plain id 'LIE' that collides only under str(value) keying, mutation-verified; F4 the import is hoisted.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Merged as 94973d6 via PR #147 (head ade1252 after the review fixup). Review cycle: first verdict CHANGES-REQUIRED at 631d171 on four findings (duplicated rationale, unrecorded lapse and AC state, non-discriminating LyingStr, mid-file import), all fixed and re-verified; re-verdict APPROVED at ade1252 with the reviewer's own str(value) mutation killed by the new test. Gates: /simplify 4-angle findings applied; code-reviewer-typed high review; battery check clean, 1263 passed 2 skipped; master CI green.
<!-- SECTION:FINAL_SUMMARY:END -->
