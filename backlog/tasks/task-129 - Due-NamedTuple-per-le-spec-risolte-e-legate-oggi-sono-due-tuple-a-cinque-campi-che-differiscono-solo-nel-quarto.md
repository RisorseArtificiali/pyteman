---
id: TASK-129
title: >-
  Due NamedTuple per le spec risolte e legate: oggi sono due tuple a cinque
  campi che differiscono solo nel quarto
status: Done
assignee: []
created_date: '2026-09-17 05:13'
updated_date: '2026-09-27 07:39'
labels:
  - audit-2026-09-17
  - simplify-gate
  - opus-5
  - rt
dependencies:
  - TASK-2
references:
  - 'src/pyteman/patcher.py:839'
  - 'src/pyteman/patcher.py:1072'
  - 'src/pyteman/patcher.py:1266'
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Rilievo del gate /simplify del 2026-09-17, classificato dal revisore stesso come l'unica opzione strutturale e non come pulizia dovuta. NON e' un bug.

**Il fatto.** In `src/pyteman/patcher.py` circolano due tuple a cinque campi che differiscono solo nel quarto:

- la spec RISOLTA, `(rule, when_code, key_code, described, ordinal)`, costruita in `_patch` intorno a :839;
- la spec LEGATA, `(rule, when_code, key_code, state, ordinal)`, prodotta da `_make_dispatcher` :1072 e da `_extend_dispatcher` :1266.

Si incrociano proprio nelle due funzioni che prendono la prima e producono la seconda. Niente nel codice dice che sono due tipi: hanno la stessa arieta', quindi uno scambio non fallisce alla costruzione e si manifesta solo quando qualcuno legge `spec[3]` aspettandosi l'altro.

**Quanto e' letto posizionalmente.** `spec[4]` a :566 e :1279-1280; `spec[3]` che vale `described` a :853 e `state` a :610, :1213, :1285; `spec[0]` a :579, :605-607, :897, :959, :1113-1115, :1241, :1269-1270, :1282. Piu' i test.

**Costo concreto.** `spec[3]` non e' leggibile senza risalire a quale produttore ha costruito quella lista. E la chiave del merge, `key=lambda s: s[4]`, e' la decisione di ordinamento su cui poggia l'intera tranche di estensione, scritta come indice intero nudo: se qualcuno riordina i campi della tupla, il merge continua a compilare e ordina per il campo sbagliato.

**Perche' non costa prestazioni.** Entrambi i loop del dispatcher spacchettano invece di indicizzare (`for rule, when_code, key_code, state, _ in comp.entries`), quindi due `NamedTuple` lasciano il percorso caldo identico e trasformano `s[4]` in `s.ordinal` e `spec[3]` in `spec.state`.

**Perche' non applicato nella tranche.** Tocca circa una dozzina di siti piu' i test, e il vincolo di coordinamento in vigore limita le modifiche al core alias a bug e criteri di accettazione. Una conversione parziale sarebbe peggio di nessuna: due tipi dove uno e' nominato e l'altro no invitano proprio lo scambio che la conversione previene.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 _Resolved e _Bound sono due NamedTuple distinte e ogni lettura posizionale di quei campi passa per un nome, compresa la chiave del merge per ordinale
- [x] #2 La conversione e' completa: nessun sito continua a indicizzare quelle tuple per intero, verificato con un grep esaustivo riportato nelle note
- [x] #3 Il percorso caldo del dispatcher continua a spacchettare e non a indicizzare, e la suite completa resta verde
- [x] #4 Un test dimostra che scambiare una spec risolta con una legata viene ora respinto invece di passare inosservato
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Merged as df08268 via PR #156 (head 9540e0f). Gates: /simplify four-angle findings applied (the missed merge sort keys and two test fires reads); code-reviewer-typed high review CLEAN with the construction sweep, cross-type tuple equality, and pickling cleared by probe, and its one-line TASK-182 follow-up applied in the same diff (the refusal join reads spec.described; TASK-182 closed as applied); mutation reverting both types to bare tuples kills the swap-refusal test; battery check clean, 1265 passed 2 skipped (one suite run hit the documented mid-run /tmp wipe by the tmpfiles daemon; immediate rerun green); independent review APPROVED at 9540e0f with the mutation re-run by the reviewer; PR CI green; master CI green. The reviewer also filed TASK-183 (a pre-existing stale _State name in a comment) as an open follow-up.
<!-- SECTION:FINAL_SUMMARY:END -->
