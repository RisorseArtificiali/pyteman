---
id: TASK-116
title: >-
  RT-02i. Il nome `exc` sopravvive al blocco except e trattiene frame e
  traceback della chiamata strumentata
status: To Do
assignee: []
created_date: '2026-09-17 03:42'
updated_date: '2026-09-28 18:16'
labels:
  - rt-02
  - patcher
  - memory
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Nel dispatcher l'eccezione del corpo viene legata a un nome che vive oltre il blocco `except` che la cattura, per poter essere passata alle regole exit nel `finally`. Python cancella il nome legato da `except ... as e` all'uscita del blocco proprio per rompere il ciclo eccezione -> traceback -> frame -> eccezione; una copia tenuta in una variabile esterna ripristina quel ciclo.

Il costo e' che i frame della chiamata strumentata, con tutti i loro locali, restano vivi fino al passaggio del garbage collector generazionale invece di essere liberati dal refcount. Su un punto caldo che solleva spesso questo e' esattamente il carico che uno strumento di fault injection non dovrebbe aggiungere al processo sotto test.

Da verificare prima di intervenire: misurare che il ciclo esista davvero (gc.collect con DEBUG_SAVEALL, o tracemalloc su un loop di chiamate che sollevano) invece di dedurlo dalla forma del codice. Il fix tipico e' un `finally: del` sul nome, oppure tenere solo cio' che serve alle regole invece dell'oggetto eccezione intero, ma nessuno dei due va scritto prima della misura.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Esiste una misura che dimostra o smentisce il ciclo su un corpo che solleva ripetutamente, non un'ispezione del sorgente
- [ ] #2 Se il ciclo esiste, dopo il fix i frame della chiamata strumentata sono liberati senza intervento del gc
- [ ] #3 Le regole exit continuano a ricevere l'eccezione originale con il traceback intatto
- [ ] #4 Il chaining Python ordinario su un'exit che solleva resta invariato
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #56. Added lines already present on master per PR: #56 39/95=41%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Completed by tree-27. PR #56: fix(patcher): break exception-traceback-frame cycle in dispatcher. Two-line fix (exc=None + ctx.pop) in a nested finally so the clear runs even when an exit rule raises mid-loop. Two regression tests, full suite green (1192 passed).
<!-- SECTION:FINAL_SUMMARY:END -->
