---
id: TASK-17
title: CON-02. Non ignorare un timeout della barrier action
status: Done
assignee: []
created_date: '2026-09-16 12:20'
updated_date: '2026-09-25 10:57'
labels:
  - audit-2026-09-16
  - opus-5
  - con
  - confirmed
milestone: m-2
dependencies:
  - TASK-7
  - TASK-15
references:
  - 'src/pyteman/actions.py:50-56'
  - 'src/pyteman/patcher.py:77-81,93-94'
  - 'src/pyteman/barriers.py:7-12'
documentation:
  - doc-1
  - doc-2
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit 2026-09-16 sul commit a28b12662a46727ff806a42122db0ffe8333d760. Esecuzione futura prevista con Opus 5. Riprodurre il caso sullo stato corrente prima di correggere; non dipendere dalla conversazione originale.

**Priorità / stato:** P1, CONFIRMED nel flusso del codice, aperto.

**File:** `src/pyteman/actions.py:50-56`, `src/pyteman/patcher.py:77-81,93-94`, `src/pyteman/barriers.py:7-12`.

**Evidenza:** barriers.wait restituisce False al timeout; run_action lo restituisce, ma il wrapper ignora quel risultato e prosegue il corpo originale senza outcome. Una coreografia fallita può quindi sembrare riuscita.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 attesa che scade, open precedente e open successivo all'attesa; timeout visibile con nome e durata, strict mode non esegue il corpo dopo fallimento della barriera.
- [x] #2 Nessuna dipendenza da sleep per dimostrare l'ordine.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Implementazione minima in copia isolata base d6c9ec5. Loader rifiuta timeout_s esplicito con role=open perché quel ramo non attende e non consuma il campo; role=wait e default30 invariati. Strict opt-in PYTEMAN_STRICT_BARRIER=1 valutato a firing time; BarrierTimeoutError dedicato via _Dispatched.to_raise preserva terminal barrier_timeout prima del raise e primaria rispetto a errori di log. Default preserva return False di run_action, nessun override del ritorno del workload. Strict entry impedisce body; strict exit non annulla ciò che è già avvenuto.

Test timeout reale, open precedente, open dopo ingresso effettivo in wait coordinato da Event senza sleep come ordinamento, join limitati e errori thread osservabili. Env on/off, no-log, identity errore primaria/log failure, una sola coppia start/end; test loader con posizione diagnostica. Sweep consumer/documenti per timeout non-successo. Scope actions/barriers/rules, test/docs pertinenti; niente reset generations o framework strict generale. Review indipendente finale pyteman-release-review, verifica coordinator e PR separata.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Indicazioni di coordinamento del documento di origine: CFG-01, LOG-02.

I prerequisiti operativi sono quelli nel campo Dependencies; i rinvii a consumer e file condivisi non impongono dipendenze reciproche. Aggiornare test e documentazione pertinente nello stesso task; riportare comandi e output reali prima di Done.

EVIDENZA AGGIUNTIVA DA TASK-7 (CFG-01), 2026-09-17. Nota di collegamento, non lavoro svolto: questo task resta interamente To Do e nessuna riga di codice e' stata modificata.

La review del candidato A ha trovato un secondo modo, piu' a monte, in cui un timeout di barrier viene ignorato. Qui il timeout non viene perso al firing: viene accettato al LOAD e non raggiunge mai il codice che potrebbe onorarlo.

  action: {kind: barrier, barrier: b, role: open, timeout_s: 5}    ACCETTATO

Verificato eseguendolo contro il loader reale del candidato. src/pyteman/actions.py legge timeout_s solo sul ramo wait, quindi su role: open quel 5 non fa assolutamente niente e nessun messaggio lo segnala. L'operatore scrive un limite e ottiene un'attesa senza limite, che e' la stessa classe di guasto gia' descritta nella Evidenza di questo task, un livello piu' in alto.

Perche' e' incoerente e non solo incompleto: due righe sopra, in src/pyteman/rules.py, il loader intercetta ESPLICITAMENTE target su un'azione non-pragma con il messaggio "'target' is only consumed by pragma actions", e il commento dice che il messaggio generico sui campi sconosciuti manderebbe l'operatore a caccia di un refuso. La stessa regola e' applicata a un operando e non all'altro: timeout_s su role: open e' esattamente un campo consumato da un solo ramo.

NON corretto in TASK-7. src/pyteman/rules.py e' congelato nel candidato A, e pyteman-89 ha deciso che il candidato A viene accorpato al futuro blocco motore invece di essere emesso da solo. La correzione appartiene a questo task, che possiede gia' la policy sul timeout della barrier: la decisione da prendere qui e' se un timeout_s con role: open sia un errore di load o un campo da onorare anche in apertura, e le due risposte vanno insieme all'esito strutturato gia' previsto nel piano.

Metodo, dichiarato perche' pesa sul peso di questa evidenza: l'agente di review era stato dispacciato con un tipo privo di shell, quindi non ha confermato nulla eseguendolo. Il caso qui sopra e' stato verificato eseguendolo a mano contro il loader del candidato, non accettato dall'agente.

Scout raccomanda TASK17 con dipendenze7/15 Done. Conferma indipendente coordinatore: load_rules accetta open+timeout_s5 e run_action restituisce True/apre subito. Correzione della nota storica: role=open non produce 'attesa senza limite'; non attende affatto, il timeout è ignorato. LOG02 ha già introdotto barrier_timeout osservabile; residuo funzionale è strict opt-in e schema operandi. Nessun cambiamento del default non-strict. Mandato pyteman-backlog-audit Opus5/zai in copia isolata, nessun shared/tracker/Git/forge/config/memory write.
TASK4 solo candidato alternativo non riprodotto dal nuovo scout, non avviato. TASK147/TASK157 segnalati come potenzialmente stale, non chiusi sulla sola sintesi: richiedono riconciliazione propria.

Checkpoint implementatore letto da herdr: suite riportata1045 passed/1skip su candidato isolato, ancora da verificare indipendentemente; strict policy in barriers.refusal e to_raise preserva status barrier_timeout. Gate simplify propone backslash->parentesi coerente con package (accettato una volta) e trim tabella docs (declinato se non già applicato, opzionale). Reuse della frase timeout tra policy/dispatcher declinato per non spostare ownership; guard kind=='barrier' mantenuto perché determina diagnostica corretta per altre action con role spurio. High reviewer interno già concluso ma verdetto non ancora nel handoff; richiesto hash finale, eventuale delta stesso reviewer e nessun nuovo fanout/simplify. Shared intatto.

Candidato6c40fe67459e373919f4280ae82ac11c5f46630dda298e9899381ed37e205e0c verificato hash, avviata suite indipendente da patch immutabile su exportd6c9ec5. Nove file, nessuna applicazione shared. Peer dichiara quattro findings obbligatori corretti: exit strict può sostituire errore body e saltare exit successive (ora documentato, entry raccomandato); test open non deve bypassare loader con timeout illegale; actions doc enumera entrambe classi strict; fixture reset stato globale barrier. Reviewer interno in delta review, accettazione finale mirata inviata a pyteman-release-review senza altro fanout.
Mutazione significativa riportata: togliere solo to_raise rende rossi quattro test strict, quinto negativo; full revert causava import failure e non viene contato come prova detector. Opzionali wording/guard/trim docs già disposti nelle note, nessun nuovo task o cleanup.

Candidato6c40fe67 APPROVED dal reviewer high persistente e accettazione indipendente pyteman-release-review. Integrati nove file byte-exact con fresh export verificato; suite indipendente e shared1045 passed/1skip opzionale, shared-suite.log con versione/import in ~/pyteman-evidence/task17-integration-20260919-073831/. Commit137e84c561dacd8c45792c5ffba7ae218460f9f5 pubblicato PR10 https://github.com/RisorseArtificiali/pyteman/pull/10. CI35424974831 in corso, nessuna review/commento pendente al controllo iniziale. Non Done né merged ancora.
Nota accettazione indipendente: refusal() fa un os.environ.get su ciascun timeout anche a switch spento; costo trascurabile, comportamento previsto per firing-time policy, nessun fix richiesto. Simplify è stato eseguito dall'implementer, non dal reviewer di accettazione; non confondere i due ruoli.

PR10 MERGED f19f26a79c22602bcfb5893ede0e3d5aadbd899a, commit137e84c561dacd8c45792c5ffba7ae218460f9f5. CI35424974831 tutti sei job success; review/commenti/discussion vuoti al controllo finale. Suite indipendente e shared1045/1skip, peer high e accettazione finale APPROVED stesso6c40fe67. Runtime e pubblicazione conclusi.
Transizione Done bloccata dal dod-completion-gate che non trova /simplify nel transcript coordinator, benché eseguito dall'implementer e registrato in EVIDENCE.md. Nessun retry identico o bypass; tracker resta In Progress amministrativo. Non dichiarare gate locale eseguito né avviare duplicati solo per creare un marker.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed 2026-09-25 by backlog audit. PR#10 merged as commit 137e84c, CI green, reviewer APPROVED. Task was administratively stuck In Progress because dod-completion-gate could not find /simplify in the coordinator's transcript (it was run by the implementer). All ACs satisfied; code published in v0.2.0.
<!-- SECTION:FINAL_SUMMARY:END -->
