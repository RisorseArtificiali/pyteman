---
id: TASK-157
title: 'The wrapper chain limit is reachable, untested, and its justification is false'
status: Done
assignee: []
created_date: '2026-09-17 11:20'
updated_date: '2026-09-25 10:56'
labels:
  - audit-2026-09-16
  - opus-5
  - simplify-gate
  - task-3-followup
  - confirmed
dependencies: []
references:
  - 'src/pyteman/patcher.py:563-572'
  - 'src/pyteman/patcher.py:643-644'
  - 'docs/rules.md:591'
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Simplification gate on TASK-3, 2026-09-17, confirmed independently with probes on CPython 3.14.7 at /tmp/pyteman-audit-env-OOeElF/bin/python.

Four defects in one cluster around src/pyteman/patcher.py:563-572 and 643-644.

DEFECT 1, the justification comment is false. It says "partial flattens nested partials into one, even through a subclass" and "The longest measured walk is two hops". Flattening is conditional, not universal. CPython skips it as soon as the inner partial has a materialized instance __dict__, and no subclass is needed. Merely reading p.__dict__ is enough.

  plain = functools.partial(coro)
  functools.partial(plain).func is coro        -> True
  tagged = functools.partial(coro); tagged.tag = 1
  functools.partial(tagged).func is coro       -> False
  touched = functools.partial(coro); touched.__dict__
  functools.partial(touched).func is coro      -> False

A 70-link chain was built with no subclassing at all.

DEFECT 2, the bound is reachable and wrongly refuses a synchronous target. Measured against the real _suspendable_reason with patcher.__file__ printed as the repository copy:

  sync target,  62 links -> (None, None)
  sync target,  63 links -> refused, "did not end within 64 links"
  sync target,  70 links -> same refusal

An ordinary synchronous callable behind 63 or more dict-carrying partials is refused. It fails closed, which is the safe direction, but it is a real false positive and the comment tells the next maintainer it cannot happen.

DEFECT 3, the message undercounts by two. _WRAPPER_CHAIN_LIMIT is 64 and the message says "did not end within 64 links", but the deepest chain accepted is 62. The loop spends one iteration following the instance __call__ edge and one more reaching the terminating return, so 64 iterations admit only 62 wrapper links. An operator who reads the message and counts their own wrappers finds the numbers disagree.

DEFECT 4, the branch has no test. Grepping tests/ for "did not end within" and for _WRAPPER_CHAIN returns nothing. It is the one return in _suspendable_reason with no coverage, and defect 2 shows it is reachable with plain functools.partial. The constant could be changed to any value, or the final return deleted, with the suite still green. This is why defect 1 survived: a comment asserting the branch cannot fire, and no test contradicting it.

SEPARATE CORRECTION TO THE SAME COMMENT. The conclusion stands but the reason given is wrong. The comment argues that no cycle check is needed because the edges are short by construction. Defect 1 destroys that half. The correct argument, verified, is that neither remaining edge can be made to point backwards:

  p.func = p                              -> AttributeError readonly attribute
  functools.partial.func.__set__(p, p)    -> AttributeError readonly attribute
  class F(types.FunctionType): pass       -> TypeError type 'function' is not an acceptable base type
  getattr_static(type(f), '__call__')     -> wrapper_descriptor, isfunction False

A self-referential or mutually-referential partial cannot be constructed, and the __call__ edge always lands on a types.FunctionType whose own type __call__ is a wrapper_descriptor, so it terminates in one hop. Cycles are impossible because a backward edge is unbuildable, not because chains are short.

The false flattening claim was also copied into the TASK-3 implementation plan and must be corrected there in the same change.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Il commento su _WRAPPER_CHAIN_LIMIT non afferma piu' che partial appiattisce sempre i partial annidati, ne' che il cammino piu' lungo e' due salti; entrambe le affermazioni sono false e riproducibili come tali.
- [x] #2 L'argomento sull'assenza del controllo dei cicli e' riscritto sulla ragione corretta: partial.func e' readonly in entrambe le vie e types.FunctionType non e' sottoclassabile, quindi un arco all'indietro non e' costruibile. Il testo dice anche che il bound copre la camminata di questa funzione e non cio' che i predicati inspect fanno al loro interno, dove una property func ostile non ha rimedio.
- [x] #3 Esiste un test che raggiunge il ramo del limite con una catena di functools.partial portatori di __dict__, e fallisce se la costante o il return finale vengono cambiati. La soglia misurata e' 64: 63 link accettati, 64 rifiutati.
- [x] #4 Decidere se rifiutare un callable sincrono a 64 link e' il comportamento voluto, e se si' dirlo nel messaggio o nella documentazione, perche' oggi e' un falso positivo silenzioso. Il conteggio nel messaggio NON e' sbagliato: corrisponde alla soglia misurata.
- [x] #5 La stessa affermazione falsa e' corretta nel piano di TASK-3, non solo nel commento.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
SECOND FALSE CLAIM IN THE SAME BLOCK, found by the code review gate 2026-09-17. The termination argument is wrong in a way the first finding does not cover.

src/pyteman/patcher.py:563-571 claims 'a bound that guarantees termination covers what a cycle would have done anyway', and the func-property paragraph at 599-605 claims a func property 'still runs, and still decides, before this line is reached'. Both fail on the same object.

Give a functools.partial subclass a func property that returns self. inspect.iscoroutinefunction calls _has_code_flag, which calls functools._unwrap_partials, which walks .func by ordinary attribute access with no bound of its own. It spins forever INSIDE THE FIRST PREDICATE, before the bounded walk gets a single iteration. The bound at 643-644 cannot fire because control never returns to the loop.

The gate demonstrated it with a 3 second SIGALRM; the resulting TimeoutError came back out of _suspendable_reason as 'of a kind that could not be read: TimeoutError: hung'. Without the alarm it hangs the interpreter at startup, which is precisely what the bound was written to prevent.

This is deliberate hostility only, so the correct response is to fix the wording rather than the code. The honest statement is that the bound covers the walk this function performs and cannot cover what the inspect predicates do internally, and that a hostile func property is outside what any bound here can promise.

The gate also independently reproduced the flattening defect this task was filed for, with a second idiom worth recording because it is ordinary code rather than a contrived subclass:

  p1 = partial(f); functools.update_wrapper(p1, f); partial(p1).func is f  -> False

That is the standard way to give a partial a __name__. It defeats flattening through materialised __dict__, exactly as reading .__dict__ does. A Placeholder in the inner partial also blocks flattening. Subclass nesting DOES flatten on 3.14, so that half of the comment's claim holds and the __dict__ half does not.

MEASUREMENT CONFLICT RESOLVED, 2026-09-17, and one recorded defect is REFUTED. Two sources disagreed on the threshold, so I measured it myself rather than picking one.

This task records, from the simplification gate, 'sync target 62 links -> accepted, 63 links -> refused' and concludes from it that the message undercounts by two. My own probe against the real tree disagrees. Origin printed as /home/pantinor/data/repo/personal/pyteman/src/pyteman/patcher.py, _WRAPPER_CHAIN_LIMIT read as 64, chain built by applying n functools.partial wrappers and touching __dict__ on each to defeat flattening:

  60 accepted   61 accepted   62 accepted   63 accepted
  64 REFUSED    65 REFUSED    ...           71 REFUSED
  first refused at: 64

So the deepest accepted chain is 63 links and the 64th is refused, against a limit of 64 and a message reading 'did not end within 64 links'. The message and the behaviour agree. DEFECT 3 as filed, that the message undercounts by two, is refuted and must not be acted on; acceptance criterion 4 has been rewritten accordingly.

The two gates presumably counted the base callable as a link, or their construction inserted one extra wrapper. I did not reconstruct their harness, so I am not asserting which; what I am asserting is the number produced by the code under test, which is what the message has to match.

DEFECT 2 SURVIVES, with its number corrected. An ordinary synchronous callable behind 64 or more dict-carrying partials is still refused, and that is still a false positive. It fails closed, which is the safe direction, and it is still undocumented and untested. What changes is only the threshold, from 63 to 64.

DEFECT 1 and DEFECT 4 are untouched by this. The flattening claim is false and the branch still has no test.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
All five acceptance criteria were satisfied by TASK-3 (commit 3a38482 and predecessors). Verified 2026-09-25 with probes against the live tree.

AC #1: The false flattening claim ("partial flattens nested partials into one, even through a subclass") and "longest measured walk is two hops" are both gone. Replaced by a measured version table at patcher.py:842-859 showing WithDict stays at depth 2 on every supported version.

AC #2: The cycle argument at patcher.py:863-869 is rewritten. It correctly states that cycles ARE possible (a class whose __call__ is a partial over an instance closes one through the __call__+func path), and the bound catches them. Test test_a_cycle_is_caught_by_the_bound_and_is_right_to_be_refused at test_activation_atomic.py:5239 proves both the cycle and that calling such an object raises RecursionError. The task's proposed replacement ("cycles are impossible because backward edges are unbuildable") would have been wrong for the post-TASK-3 code where the __call__ edge follows partials and staticmethods, not just functions.

AC #3: Tests exist. _KeepsANest (test_activation_atomic.py:5173) is a dict-carrying partial subclass. test_a_chain_at_the_limit_is_walked_to_its_terminal parametrizes at [63, 64], both accepted. test_a_chain_one_link_past_the_limit_is_refused tests at 65, refused. Boundary: 64 accepted, 65 refused. Verified with direct probe.

AC #4: TASK-3 added the +1 to range(_WRAPPER_CHAIN_LIMIT + 1) which fixed the off-by-one. 64 links is now accepted (was previously refused at 64). Message "within 64 links" is correct. docs/rules.md:743 says "past 64 links". A synchronous callable at exactly 64 links is accepted, not falsely refused.

AC #5: The TASK-3 plan file at line 372 does not repeat the false claim as truth; it analyzes it as false ("VERA solo da 3.13 in poi. Su 3.11 e 3.12 e' falsa"). No correction needed; the analysis is accurate historical record.
<!-- SECTION:FINAL_SUMMARY:END -->
