---
id: TASK-91
title: >-
  SQL-04. La firma pubblica di classify_integrity e un dict generico mentre il
  pacchetto dichiara py.typed
status: Done
assignee: []
created_date: '2026-09-16 21:21'
updated_date: '2026-09-29 22:21'
labels:
  - sql
  - follow-up-task-25
  - api
dependencies: []
references:
  - src/pyteman/sqlitekit/integrity.py
  - src/pyteman/py.typed
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Follow-up individuato durante TASK-25 (SQL-02).

`classify_integrity` e annotata `-> dict`. Il pacchetto spedisce `src/pyteman/py.typed`, quindi un consumatore con un type checker riceve `dict[Unknown, Unknown]`: nessun controllo sui nomi delle cinque chiavi, nessun tipo per i valori, e un refuso come `res["classess"]` passa la verifica statica per poi fallire a runtime dentro un incidente.

TASK-25 ha reso la forma della risposta un contratto esplicito: cinque chiavi, documentate in docs/integrity.md e verificate dai test. Un TypedDict renderebbe quel contratto leggibile dal checker invece che soltanto dalla prosa.

Deliberatamente non fatto in TASK-25 per due ragioni. Primo, avrebbe introdotto un tipo pubblico nuovo mentre TASK-24 lavora sullo stesso modulo. Secondo, i test asseriscono l'insieme esatto delle chiavi su un `dict` semplice, e il valore di quell'asserzione dipende dal fatto che l'oggetto restituito sia davvero un dict ordinario.

Verificare se il progetto voglia davvero esporre un tipo: non ci sono configurazioni mypy o pyright nel repository e la CI non esegue alcun type checker, quindi il beneficio e per i consumatori a valle e non per questa suite.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Stabilire e scrivere nel task se il progetto espone un tipo pubblico oppure resta su dict semplice con la sola documentazione
- [x] #2 Se adottato il TypedDict e un alias esportato e il checker segnala una chiave inesistente su un esempio scritto apposta
- [x] #3 I test esistenti che asseriscono l'insieme esatto delle chiavi continuano a valere sull'oggetto restituito
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #96 #131. Added lines already present on master per PR: #96 0/15=0%  #131 1/13=7%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.

Merged 2026-09-29 via #192 (4c60ec5). Evidence under /home/pantinor/pyteman-evidence/t191/: diff91.patch sha256 68c0dfe3, tree91-hold2.sha256, mutants-91c.log, VERDICT-91.md in t191rev.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed by PR #192, squash-merged as 4c60ec5 on master at 2026-09-29 22:20Z. AC1: the project exposes the type; classify_integrity returns IntegrityVerdict, a TypedDict of the six keys the verdict carries on master, with databases mapping to a nested _DatabaseSection TypedDict, so the contract TASK-25 wrote in prose is readable by a checker. AC2: demonstrated on the checker the repo already runs, basedpyright via dev.py check: an ad-hoc example reading verdict['classess'] and verdict['databases']['main']['unclassifed'] is flagged at both depths with the annotations in place, and the battery kills the plain-dict mutant (outer silent) and the bare-mapping mutant (nested silent); a constructor-annotation-only mutant was retired as equivalent by construction with the reason in the script. AC3: the exact-key set test pins the returned dict against the TypedDict's annotations; the reviewer's informational symmetry pin is filed on TASK-198 and the status-as-str choice is recorded on the verdict file. Both superseded PRs predated the six-key shape; the revival re-validated it and restored the constructor's per_database parameter. #96 and #131 closed with pointers.
<!-- SECTION:FINAL_SUMMARY:END -->
