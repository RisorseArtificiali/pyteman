---
id: TASK-132
title: '`served` keyed by rule identity disagrees with a plan holding one rule twice'
status: Done
assignee: []
created_date: '2026-09-17 05:40'
updated_date: '2026-09-17 10:21'
labels:
  - patcher
  - design
  - consistency
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`_Composite.served` is keyed by `id(rule)` while the plan can legitimately hold the same Rule object twice, so the two disagree on how many rules a slot serves.

The id-uniqueness guard in `__init__` (patcher.py:~695-712) refuses a duplicate id, but skips the check when `r.id` cannot be read. Two planned entries for the same object therefore reach `_make_dispatcher`, which builds one spec per planned entry, while `served[id(rule)]` keeps one.

Confirmed by probe (/tmp/probe_duplicate_plan_entry.py), same Rule object listed twice with an id property that raises:

    entries (what fires):    2
    rank() (what publishes): 1
    served keys:             1
    _pyteman_state length:   2
    distinct state dicts:    2
    applied:                 ['probe_dup_victim:f', 'probe_dup_victim:f']
    DIVERGENCE: True

Severity is lower than the re-entrant double merge that shares its shape, and the reason is worth recording. There the duplicate was invented by the patcher and the operator never wrote it; here the rule genuinely is in the ruleset twice, `applied` names it twice honestly, and a freshly built dispatcher is self-consistent because the fresh path derives `_pyteman_state` from the spec list rather than from `rank()`.

The inconsistency is LATENT rather than immediate. It surfaces only when such a dispatcher is later extended, because `_extend_dispatcher` and `_unextend` rebuild the marker from `rank()`. At that point `_pyteman_state` shrinks from 2 to 1 while `comp.entries` still fires twice, so the marker under-reports what runs.

Not a small fix, and the tension is the point. Keying `served` by `id(rule)` is what makes the re-entrant re-filter in `_extend_dispatcher` able to say "this rule is already merged"; keying it per planned entry would count duplicates correctly and reopen the double-merge bug. Resolving this means first deciding what a rule listed twice means, which is a design call rather than a defect to patch.

Reachable programmatically only: the YAML loader cannot build a rule whose id refuses to be read, so this needs a hand-built object, the same reachability the `_EVENTS` guard at :546-550 rests on.

Raised as one of three findings a review of the RT-02 tranche cut for length, then confirmed and re-scoped here. Introduced by that tranche rather than pre-existing: HEAD's patcher.py is 146 lines and contains no `_Composite`, `served` or `rank` at all.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Decide and document what a ruleset listing the same Rule object twice on one slot MEANS: two independent firings with independent `countdown`/`once_per` state (today's behaviour), or one rule.
- [x] #2 NON APPLICABILE: la costruzione è rifiutata. `comp.entries`, `comp.rank()`, `comp.served` e `dispatcher._pyteman_state` non possono disaccordarsi sul conteggio perché non esiste più un percorso pubblico a un dispatcher che tiene la stessa Rule due volte: `Patcher([r, r])` solleva `id is already used by an earlier rule`, leggibile o meno l'id. Torna un requisito attivo solo se la pianificazione duplicata viene riaperta come funzionalità.
- [x] #3 The re-entrant double-merge guard keeps working: the second filter of `fresh` against `comp.served` in `_extend_dispatcher` must still detect a rule merged by a re-entry. A mutation test that removes it must still be caught.
- [x] #4 NON APPLICABILE: la costruzione è rifiutata. Non esiste oggetto da costruire per il test di regressione, perché un dispatcher con una rule pianificata due volte non è più ottenibile dal percorso pubblico. Torna un requisito attivo solo se la pianificazione duplicata viene riaperta come funzionalità.
- [x] #5 If the resolution is to refuse the duplicate at plan time instead, the refusal must not depend on reading `r.id`, since an unreadable id is exactly what lets the duplicate through today.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Measurement on the EXTENSION path (2026-09-17), which complements the fresh-path probe already recorded in the description.

The comment at patcher.py:1317-1318 claims that when a duplicate spec does get merged, `served` keyed by rule identity keeps one spec per rule, so the duplicate hides from the very manifest that exists to make a drop visible. That claim was asserted but never measured. It is now measured, and it holds.

Method: a COPY of src/ in a temp dir, mutated by /tmp/mutate_a1.py to restore the pre-fix placement of the second `served` filter (nested inside the signature block) and to delete the unconditional re-filter. Origin proved by printing `pyteman.patcher.__file__` = /tmp/pyteman-b2-hlKN2c/src/pyteman/patcher.py, and by the pre/post sha256 pair 4ffb0d88... -> 973d6d7f.... The real src/pyteman/patcher.py was re-hashed afterwards and is unchanged at 4ffb0d8800cedd76ebbf0182e25340cae0abecaebf10810f12bb03b79e321bab. The temp tree was then removed.

Probe /tmp/probe_a1_refilter_skipped.py against the mutated copy:

    entries (what fires):    3
    rank() (what publishes): 2
    served keys:             2
    _pyteman_state length:   2
    distinct state dicts in entries: 3
    applied: ['probe_a1_victim:f', 'probe_a1_alias:via.f', 'probe_a1_alias:via.f']
    call 1: fired ['early']
    call 2: fired ['early', 'late', 'late']
    call 3: fired ['early']

Three readings matter. The manifest under-reports by exactly the duplicate: three specs fire, two publish. The marker `_pyteman_state` is rebuilt from `rank()` and so carries two state dicts while three are live in `entries`, which is the same marker-shrinkage this task already describes for the latent fresh-path case, reached here by a different route. And the duplicated rule's `countdown` reaches its threshold on call 2 and fires twice inside that one call, which is the operator-visible damage rather than a bookkeeping discrepancy.

Disposition: no code change and no new test. The re-filter is in place and correct, and the regression test `test_an_extension_that_needs_no_signature_still_re_asks_the_manifest` (tests/test_activation_atomic.py) fails against exactly this mutant. The reason this lands here rather than closing is that the numbers are evidence for AC #2 and AC #3 of this task: they quantify the disagreement AC #2 must remove, and they are the mutant AC #3 says must keep being caught, so the future resolution has a concrete before-picture to test against instead of a description.

COVERED IN TASK-2, with one question left open pending review (2026-09-17). Moved here from deferred design decision at the reviewing peer's direction: they stated that unique preflight ids were already a settled choice for the programmatic API, so the guard that skipped an unreadable identity was not preserving an open decision, it was manufacturing this incoherence.

What the preflight gate in `Patcher.__init__` now closes.

The route this task's DESCRIPTION documents is gone. The fresh-path divergence needed the same Rule object planned twice, and reaching that needed an id the duplicate check would skip. Both halves are now refused: an id that cannot be read is refused outright, and an id that can be read is compared, so `Patcher([r, r])` raises `id is already used by an earlier rule` whether or not `r.id` is readable. The measured picture in the description (entries 2, rank() 1, served keys 1, `_pyteman_state` 2, `applied` naming the point twice) is no longer constructible through the programmatic door.

Against the acceptance criteria as written.

AC #1, what a ruleset listing the same Rule object twice MEANS, is answered by refusal rather than by choosing between the two readings it offered. That is a real answer and it is the one the peer had already made: the id is what keys the firing log and the outcome dedup, so two entries answering to one identity make a run's own record unreadable, and the ruleset is refused instead.

AC #5 is satisfied, though not in the shape it anticipated. It asked that a plan-time refusal not DEPEND on reading `r.id`, because an unreadable id was exactly what let the duplicate through. The gate still reads `r.id`, but an unreadable id no longer slips past it; it is the first thing refused. The hazard the criterion was written against is removed rather than routed around.

AC #3 is intact and independently evidenced. The re-entrant double-merge guard was not touched, and the A1 mutant recorded in the implementation notes above still kills `test_an_extension_that_needs_no_signature_still_re_asks_the_manifest`.

AC #4 is no longer constructible through the public path, since a dispatcher with a rule planned twice cannot be built. That is a resolution of the criterion, not a satisfaction of it, and it is recorded as such.

What this does NOT close, and why the task is not being marked Done yet.

The EXTENSION-path measurement in the implementation notes above reaches a duplicate spec by a different route entirely: re-entrant merging, with no duplicate Rule object and no id involvement at all. That route is guarded by the unconditional re-filter, which is in place and correct, but nothing about it depends on the new gate, so the gate cannot be credited with it.

The open question is whether `self.rules` or `self._plan` can be mutated AFTER `__init__` returns, which would let a rule bypass preflight and reach the raw `rule.id` reads at firing.py:19 and actions.py:81. I have asked the review now running to answer it specifically rather than assuming the answer. This task stays open until that answer is in, because closing it on an assumption is exactly the failure mode that produced it.

Evidence for the above: TASK-2 carries the implementation, the tests, and a mutation battery run against a green 635-test perimeter baseline on the final snapshot. patcher.py sha256 fb3bd456be256a70ef9b035f74fc9871ad96dfb1985bac5b1bb713a4517fa4f8, full suite 735 passed.

Bypass question answered, and the answer is what keeps this task from closing clean.

Nothing in src/ opens a second door into the plan. `self.rules` is a tuple assigned once (patcher.py:666) and `self._plan` once (patcher.py:769), read at 687 and 842 only, and there is no .append/.extend/.insert on either anywhere in the package. `install`, `activate` and `force_patch_module` add no second construction path. I established that by grep, and the high-effort reviewer reached the same conclusion independently.

What the reviewer found that I had not: preflight can only speak for the moment it runs. `Rule` is a plain dataclass and is not frozen (rules.py:39), so the caller still holds the object the plan holds, and firing.py:19 and actions.py:81 read `id` AGAIN on every firing. Rebinding `r.id = None` after the Patcher is built, or giving `id` a property that answers once and then stops, puts back exactly the hazard the gate removes. The reviewer demonstrated it end to end: the firing log recorded {"rule": null}.

This is a limit of preflight, not a defect in the gate, and it cannot be closed from here. The two fixes that would close it are freezing `Rule` (rules.py is frozen under TASK-7, APPROVED) and snapshotting the id into the plan so firing.py and actions.py read the snapshot (both files belong to another runtime I was told not to touch). Documented instead, in docs/rules.md under Ids: a rule should be treated as frozen once it has been handed to a Patcher.

CLOSING (2026-09-17). Reviewer verdict on the integrated resolution: APPROVED, with the explicit criterion that this closes on refusal in preflight plus tests, without redesign. Recorded here with the criteria marked honestly rather than uniformly.

Checked, genuinely satisfied.

AC #1 is answered. What a ruleset listing the same Rule object twice on one slot MEANS is: it is refused. That is a decision, not an evasion of the two readings the criterion offered, and it follows from a contract that was already settled for the programmatic door. The id keys the firing record and the outcome dedup, so two plan entries answering to one identity make the run's own record unreadable. Refusing the ruleset is cheaper than making an unreadable record coherent.

AC #3 is intact and independently evidenced. The re-entrant double-merge guard was never touched by this work. The A1 mutant recorded in the implementation notes above, which restores the pre-fix placement of the second `served` filter and deletes the unconditional re-filter, still kills `test_an_extension_that_needs_no_signature_still_re_asks_the_manifest`.

AC #5 is satisfied, though not in the shape it anticipated. It asked that a plan-time refusal not DEPEND on reading `r.id`, because an unreadable id was exactly what let the duplicate through. The gate does still read `r.id`, but an unreadable id no longer slips past it: it is the first thing refused, before the duplicate comparison runs. The hazard the criterion was written against is removed rather than routed around.

Left unchecked, and the reason is the point.

AC #2 asked that `comp.entries`, `comp.rank()`, `comp.served` and `dispatcher._pyteman_state` agree on the count for a rule planned twice, on a fresh dispatcher and after `_extend_dispatcher` or `_unextend` rebuilds the marker. AC #4 asked for a regression test that builds such a dispatcher, extends it, and asserts `_pyteman_state` does not shrink below what `entries` fires.

Neither is satisfied as written, because neither is constructible any more. `Patcher([r, r])` now raises `id is already used by an earlier rule` whether or not `r.id` is readable, so there is no public path to a dispatcher holding one rule twice, and therefore no state for the four counters to disagree about and no object for the regression test to build. These are RESOLVED BY REMOVING CONSTRUCTIBILITY, not satisfied. Marking them checked would claim a measurement that was never taken. They are left unchecked deliberately so that anyone who reopens duplicate planning as a feature finds the two criteria still waiting, which is exactly when they would become reachable again.

What this closure does NOT cover, carried forward rather than absorbed.

The extension-path measurement in the implementation notes above reaches a duplicate spec by a completely different route: re-entrant merging, with no duplicate Rule object and no id involvement at all. That route is guarded by the unconditional re-filter, which is in place and correct, but nothing about it depends on the new gate, so the gate cannot be credited with it. It is guarded elsewhere, not closed here.

The post-preflight mutation hole is tracked in TASK-138 and is not closed by this task. `Rule` is not frozen, and `firing.py:19` and `actions.py:81` read `id` again on every firing, so a rule that passed the gate can be rebound afterwards. The reviewer demonstrated it end to end, with `{"rule": null}` in the firing log. Both candidate fixes reach files outside this perimeter. Documentation is the mitigation in the meantime, and it is labelled as a mitigation rather than a fix.

Three further items were filed today from the /simplify gate on the final snapshot and are NOT blockers for this closure: TASK-140 (one id validator called by both doors, since the contract is now spelled twice and has latently diverged on str subclasses), TASK-141 (the preflight rationale in the patcher comment and in docs/rules.md overstates what the gate protects), and TASK-143 (record the duck-typed Patcher door as a decision). None of them changes behaviour and none was applied, because the approval carried an explicit instruction of no code change after approval.

Artifact hashes at closure, re-verified this turn in a checkout shared with another active agent rather than quoted from earlier in the session: src/pyteman/patcher.py sha256 2f0a96d0565a8c6c80bdd1cb7532945a29b53bc24a7f752bf789f6c6c0876ada.

AC #2 and AC #4 reworded to NON APPLICABILE and marked (2026-09-16), at the reviewing peer's direction.

The closure record above left them unchecked on purpose, and the reason it gave was sound at the time: checking a criterion that asks for a MEASUREMENT would have claimed a measurement nobody took. What that reasoning missed is the cost of the alternative. Two unticked boxes on a Done task read as work still owed, and nothing in the box text told a later reader that the requirement had been dissolved rather than skipped. The task was carrying a false open balance.

The fix is to move the disposition out of the notes and into the criteria themselves. Both now say what actually happened: the construction is refused, `Patcher([r, r])` raises `id is already used by an earlier rule` whether or not `r.id` is readable, and there is no public path to a dispatcher holding one rule twice. There is no state for the four counters to disagree about and no object for the regression test to build. A criterion whose text is `NON APPLICABILE` and whose box is ticked claims only that the disposition is settled, which is true and which is exactly what the earlier honesty argument was protecting.

The forward-looking clause the earlier note wanted to preserve is preserved, and it is now inside the criteria rather than several paragraphs below them: each one ends by saying it becomes an active requirement again only if duplicate planning is reopened as a feature. Anyone who reopens that feature finds the requirement at the point where they would look for it.

No behaviour, code, test or hash changed. This is a tracker-record correction only, and the substantive closure above stands as written.

Hash pointer, so a later reader does not read a mismatch as tampering.

The closure record above quotes src/pyteman/patcher.py sha256 2f0a96d0565a8c6c80bdd1cb7532945a29b53bc24a7f752bf789f6c6c0876ada, which was correct for the snapshot this task closed on. That hash no longer matches the file. TASK-3 edited patcher.py afterwards, adding the suspendable-target refusal and correcting the preflight id-gate comment under TASK-141, and the file now hashes 4070e70748479154d4da9f97f1a00dd339dfced394c800ce8059ad3aba040874.

Nothing this task depends on was touched by that change. The preflight id gate itself, the duplicate-id comparison and the unconditional re-filter in `_extend_dispatcher` are byte-identical; what changed inside the gate was the explanatory comment, not the check. TASK-3 carries its own hashes and its own verification.
<!-- SECTION:NOTES:END -->
