---
id: TASK-114
title: >-
  RT-02g. La divisione entry/exit non e' una partizione: una Rule con un altro
  event viene installata, finisce in applied e non puo' sparare mai
status: Done
assignee: []
created_date: '2026-09-17 03:10'
updated_date: '2026-09-25 10:58'
labels:
  - rt
  - opus-5
  - review-rt-02
  - correttezza
dependencies:
  - TASK-2
references:
  - src/pyteman/patcher.py
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Trovato dall'agente simplification della review /simplify su RT-02 (TASK-2), 2026-09-17. PREESISTENTE a RT-02: la divisione entry/exit e' solo il punto in cui il problema diventa visibile, non la sua causa.

**Il meccanismo.** `_make_dispatcher` divide le spec dello slot in due liste con due comprehension: una per `event == "entry"` e una per `event == "exit"`. Le due liste NON sono una partizione. Una `Rule` il cui `event` non sia nessuno dei due finisce in nessuna delle due liste, il dispatcher viene installato lo stesso, la regola compare in `applied`, e non puo' sparare mai. Nessun errore, nessuna nota nel log, nessun modo per l'operatore di accorgersene se non confrontando il firing log con quello che si aspettava.

**Perche' non e' gia' un bug in produzione.** Il loader dello YAML valida `event` contro l'insieme chiuso, quindi un ruleset caricato da file non puo' arrivarci. Il buco e' la porta PROGRAMMATICA: `Patcher([Rule(...)])` costruito a mano, che e' esattamente come i test costruiscono le regole e come un utente della libreria la userebbe come API.

**Nota sulla coerenza con il resto del file.** Questo e' lo stesso schema del preflight sui duplicati di id, dove la validazione esiste al load e la porta programmatica ha dovuto ricevere un controllo proprio. Chi esegue questo task valuti se la risposta giusta sia un altro controllo puntuale o la funzione di validazione condivisa gia' discussa su TASK-43: una sola `validate_rules(seq)` che entrambe le porte attraversano risolverebbe insieme i duplicati di id e l'event ignoto, invece di aggiungere il secondo cerotto accanto al primo.

**Alternativa piu' economica**, se la validazione condivisa e' troppo lavoro per ora: rendere la divisione una partizione vera, cioe' un solo passaggio che smista e solleva su cio' che non riconosce, invece di due comprehension indipendenti che per costruzione non possono accorgersi di cio' che scartano.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Una Rule con event diverso dalle stringhe entry/exit viene rifiutata alla costruzione del Patcher, prima di qualsiasi installazione.
- [x] #2 Il rifiuto nomina regola e valore trovato tramite diagnostica coerente con il preflight e avviene nel loop per-regola di __init__, non durante la patch.
- [x] #3 Un ruleset programmatico con event invalido non installa dispatcher e non pubblica entry applied; applied resta storico delle chiamate riuscite, non prova di firing.
- [x] #4 Test programmatici coprono event ignoto/case errato/non-stringa e controlli entry/exit validi; un mutante che rimuove il preflight rende rossa la regressione.
- [x] #5 docs/rules.md chiarisce validazione event sia nel loader YAML sia nel Patcher programmatico, senza promettere validazione di mutazioni successive della Rule.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Preflight puntuale in Patcher.__init__ sul vocabolario _EVENTS esistente, RuleError diagnostico con contesto regola. Nessuno schema rewrite o refactor validate_rules. Event non-stringa non deve passare tramite equality personalizzata; niente coercizione lower/strip. Getter Exception diagnosticato con causa, BaseException conservata. Test invalidi e controlli validi, seconda regola invalida senza mutazioni/hook, mutante preflight. Scope patcher/tests/docs. Implementazione in export74cb961, venv dedicato con setuptools; simplify mirato e review finale indipendente pyteman-release-review, poi verifica coordinator e PR separata.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Ripresa richiesta dall'utente 'continua'. Scout concluso ma peer idle in attesa: riattivato con incarico TASK114. Coordinatore ha riprodotto su shared74cb961 Rule(event='ENTRY'): dispatcher installato, applied claim presente, chiamata restituisce body anziché injected. Contratto chosen è rifiuto alla costruzione, già ammesso dagli AC originari. AC3 chiarito perché applied contiene stringhe di pubblicazione e non garantisce firing (TASK131 storico già deciso). TASK147 segnalato stale dal peer, non nuova implementazione; riconciliazione separata, non confondere con progresso TASK114.

Candidato2d43b34b8feaf358d056adf00af414b43350e51ec2dd19bb171d7c62ba7ce2df ricevuto/verificato hash, fresh export74cb961 e suite indipendente avviati. Review finale mirata assegnata a pyteman-release-review senza fanout. Tre file patcher/docs/test_unknown_event, nessun shared edit.
Simplify implementer completato: rimossi dead assertion e docstring errata, import test spostato, testo exact-str e read-time contract precisato. Opzionali declinati registrati: helper comune id/event evitato per contratti diversi; _EVENTS non duplicato; __hash__ espliciti nelle fixture lasciati. Nota coordinatore: motivazione del report per quest'ultimo punto non è corretta da sola, tuple membership non richiede hash; non è blocker runtime e non autorizza altro cleanup. Risultati1075/1skip e mutante8fallimenti sono ancora attribuiti al peer finché completa prova indipendente.

PR12 MERGED b082b353a8d5e3c0eb799559f98b32620473774f, commit4e5affe7fda70017ab2f73752d875899bc40f9f7. CI35449474442 sei job success; review/commenti/discussion vuoti prima merge. Suite indipendente e shared1075/1skip opzionale; reviewer APPROVED2d43b34b e simplify mirato implementer già conclusi. Backup/manifest/log ~/pyteman-evidence/task114-integration-20260919-162835/.
Osservazioni non bloccanti della review: getter Exception preservata come __context__, non __cause__, coerente preflight id; exact-str programmatico più stretto dei valori loader, deliberato e documentato. Nessuna modifica richiesta.
Transizione Done respinta dal hook che non riconosce simplify/code-review delegati nel transcript coordinator. Stato lasciato In Progress amministrativo, nessun bypass o nuovo fanout solo per marker. Consegna pubblicata e AC verificati.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed 2026-09-25 by backlog audit. PR#12 merged as commit 4e5affe (validate programmatic rule events before installation), CI green. Administratively stuck In Progress. Code published in v0.2.0.
<!-- SECTION:FINAL_SUMMARY:END -->
