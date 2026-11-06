---
id: TASK-88
title: >-
  README and docs/rules.md both enumerate the degradation placeholders, so one
  code change falsifies two documents
status: Done
assignee: []
created_date: '2026-09-16 21:17'
updated_date: '2026-09-30 17:05'
labels:
  - rt-01
  - review-followup
  - audit-2026-09-16
  - docs
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Raised by the reuse angle of the RT-01 simplify gate, and confirmed by this round's own experience of it.

README.md's Activation contract bullet (currently lines 50-55) and docs/rules.md both enumerate the same four degradation placeholders plus the last-resort count. The README's neighbouring bullets do the right thing and defer ("see the thread-safety entry in docs/rules.md", "docs/rules.md explains why the two gentler ones do not"); this one restates the list instead.

The cost is not hypothetical. Narrowing `_describe_rule` this round changed one of those degradations from "a rule whose identity could not be read" to "<unreadable id> with the module and symbol still named". That single code change falsified BOTH documents at once, and the second site was found only by grepping for the old wording afterwards. A reference that exists in two places is a reference that will eventually be corrected in one.

The fix is to let the README bullet state the guarantee and point at docs/rules.md for the strings, the way its neighbours already do.

Not urgent, and not a correctness defect: both sites are accurate as of this commit. It is a maintenance seam that has now demonstrated exactly how it fails.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The README Activation contract bullet names the guarantee (rendering failures degrade rather than escape, in the last resort to a count of attributes left wrapped) without enumerating the individual placeholder strings
- [x] #2 docs/rules.md remains the single place that spells out <unprintable T>, <unknown type>, <notes unavailable> and <unreadable id>, and how narrow each degradation is
- [x] #3 tests/test_docs_rules.py, or an equivalent check, still pins the placeholder strings against the source so the documented contract cannot drift silently
- [x] #4 The README edit stays inside the Activation contract section, lines 13-59, and touches nothing from the '## Runner and sqlitekit' heading onward
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #45. Added lines already present on master per PR: #45 0/12=0%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.

Merged 2026-09-30 via #211 (e0d4bb7). Evidence under /home/pantinor/pyteman-evidence/t191/: diff88.patch sha256 c7057628, tree88-hold1.sha256, VERDICT-88.md in t191rev.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed by PR #211, squash-merged as e0d4bb7 on master at 2026-09-30 17:05Z. AC1: the README's Activation contract bullet names the guarantee without enumerating the individual strings. AC2: docs/rules.md is the single place spelling out each placeholder. AC3: a parametrized test pins the four placeholder strings against the reference text. AC4: the README edit stays inside the Activation contract section; no placeholder string remains anywhere in README.md. Supersedes #45, closed with a pointer. Gates at eca266e: suite 1552 passed 3 skipped, check green, delivery 41, independent verdict APPROVED (VERDICT-88.md).
<!-- SECTION:FINAL_SUMMARY:END -->
