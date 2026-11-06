---
id: TASK-12
title: CFG-06. Definire una policy per eccezioni durante la risoluzione del target
status: Done
assignee: []
created_date: '2026-09-16 12:20'
updated_date: '2026-09-29 18:58'
labels:
  - audit-2026-09-16
  - opus-5
  - cfg
  - confirmed
  - proposal
milestone: m-1
dependencies:
  - TASK-15
references:
  - 'src/pyteman/targets.py:59-63'
  - 'src/pyteman/actions.py:38-46'
documentation:
  - doc-1
  - doc-2
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit 2026-09-16 sul commit a28b12662a46727ff806a42122db0ffe8333d760. Esecuzione futura prevista con Opus 5. Riprodurre il caso sullo stato corrente prima di correggere; non dipendere dalla conversazione originale.

**Priorità / stato:** P2, CONFIRMED per propagazione; PROPOSTA per policy, aperto.

**File:** `src/pyteman/targets.py:59-63`, `src/pyteman/actions.py:38-46`.

**Evidenza:** una property `conn` che solleva RuntimeError('pool closed') propaga fuori dall'azione e non produce outcome. Il try dell'azione copre execute, non resolve_target. L'assenza di un attributo è già gestita correttamente; non confondere questa nuova policy con il caso coperto.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 getter assente, getter che restituisce None, getter che solleva un'eccezione ordinaria e getter che interrompe il processo.
- [x] #2 Diagnostica coerente senza trasformare gli errori del target in incidenti del workload non identificati.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Proposta iniziale da verificare sul codice corrente, non una correzione già applicata.

scegliere e documentare comportamento per errori di getter diversi da AttributeError: outcome e skip, oppure errore esplicito in strict mode; preservare causa originale. Non ingoiare BaseException come KeyboardInterrupt/SystemExit.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Indicazioni di coordinamento del documento di origine: LOG-02.

I prerequisiti operativi sono quelli nel campo Dependencies; i rinvii a consumer e file condivisi non impongono dipendenze reciproche. Aggiornare test e documentazione pertinente nello stesso task; riportare comandi e output reali prima di Done.

Evidenza aggiuntiva dalla delta review di TASK-15 (LOG-02), riprodotta con probe su HEAD.

Oltre al caso gia' descritto (property `conn` che solleva), la risoluzione puo' sollevare anche mentre COSTRUISCE il motivo del miss: `targets.py:57` fa `type(obj).__name__`, quindi una metaclasse il cui `__name__` e' una property che solleva fa sollevare il resolver stesso. Probe: `PROPAGATED RuntimeError hostile type name`. E' lo stesso problema di policy di questo task, non un caso nuovo, e conferma che la superficie e' piu' ampia del solo getter del target: include il rendering diagnostico dentro il resolver.

Cambiato da LOG-02, e da tenere presente quando si sceglie la policy: l'assenza di outcome citata nell'evidenza originale non vale piu'. Un'eccezione dal resolver ora prende il percorso generico di `run_action` e produce un record terminale `status: "failed"` con la diagnostica, mentre l'eccezione originale propaga con identita' invariata. Quindi oggi il caso e' OSSERVABILE nel log; quello che resta da decidere qui e' se debba anche propagare, ed e' deliberatamente lasciato a questo task.

Durante la delta review di TASK-15 era stato introdotto un `except Exception` attorno alla risoluzione che declassava il caso a `pragma_skipped`. E' stato RIMOSSO prima del merge: cambiava la policy runtime rispetto a HEAD, ed e' una decisione che appartiene a questo task, non a un task di logging. `pragma_skipped` resta riservato al miss che il resolver RIPORTA (`con is None`); un bug del getter non va classificato come skip.

Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #102 #134. Added lines already present on master per PR: #102 10/85=11%  #134 16/125=12%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason. Policy still undecided: master keeps resolve_target deliberately unguarded (actions.py 'Deliberately unguarded', pinned by test_a_target_whose_resolution_raises_is_a_failure_not_a_skip), while #134/#102 catch Exception and return pragma_failed without propagating. The task's own notes say that choice belongs here, so it needs a decision before either PR can merge.

Merged 2026-09-29 via #188 (e1d37da). Evidence under /home/pantinor/pyteman-evidence/t191/: diff12.patch sha256 00a18503, tree12-hold4.sha256, mutants-12*.log, VERDICT-12*.md in t191rev. The reviewer's below-severity note (one targeting.md line a few columns past the usual wrap) is recorded there for the next docs pass.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed by PR #188, squash-merged as e1d37da on master at 2026-09-29 18:58Z. Both arms of pragma target resolution (the explicit target walk and the legacy _find_connection) sit in one try: an ordinary exception settles as pragma_failed with 'target resolution failed: <type>: <msg>', BaseException escapes to the workload, and FAILED rides the same strict-mode gate an execute failure does. The diagnostic renders through guarded helpers on both roads (targets.type_name for the type, a local _str for the message), so an unnameable type or an unprintable message degrades without losing the marker, and a str-subclass message is normalised rather than interpolated. A getter raising AttributeError stays a miss (indistinguishable from absence at the walk's depth), documented in targeting.md with the carve-out pinned by a parametrized row; firing.md's glossary names the second cause of pragma_failed. hostile_fixtures.py grew a name raising KeyboardInterrupt, an UnnameableError and a BoomStrError, and a parity leg drives type_name against patcher's _typename with exact pins beside it. Supersedes #102 and #134, both closed with pointers. Gates at c64ad18: suite 1501 passed 2 skipped, check green, delivery 41, battery 7/7 (mutants-12-final3.log), /simplify four angles applied, code-review high seven findings applied, independent verdicts APPROVED at ae97b1a and reissued at c64ad18 (VERDICT-12.md, VERDICT-12b.md). Follow-ups filed: TASK-200.
<!-- SECTION:FINAL_SUMMARY:END -->
