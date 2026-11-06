---
id: TASK-28
title: EX-03. Isolare anche il processo driver dal profilo Hermes dell'operatore
status: Done
assignee: []
created_date: '2026-09-16 12:20'
updated_date: '2026-09-28 01:46'
labels:
  - audit-2026-09-16
  - opus-5
  - ex
  - confirmed
  - upstream-verification-needed
milestone: m-4
dependencies: []
references:
  - 'examples/hermes-109966/run_repro.py:73-103,161'
  - 'examples/hermes-111912/run_repro.py:43-66'
documentation:
  - doc-1
  - doc-2
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit 2026-09-16 sul commit a28b12662a46727ff806a42122db0ffe8333d760. Esecuzione futura prevista con Opus 5. Riprodurre il caso sullo stato corrente prima di correggere; non dipendere dalla conversazione originale.

**Priorità / stato:** P1, CONFIRMED per il passaggio ambiente; effetto sulla configurazione upstream da verificare, aperto.

**File:** `examples/hermes-109966/run_repro.py:73-103,161`, `examples/hermes-111912/run_repro.py:43-66`.

**Evidenza:** con `HERMES_HOME=/tmp/operator-home-sentinel`, una SessionDB sintetica osserva il sentinel durante il seed del driver; il child riceve invece la directory scratch. Il driver importa Hermes prima di costruire l'ambiente isolato. Non è stato verificato su una revisione upstream compatibile quali configurazioni vengano effettivamente lette o memorizzate all'import.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 profilo esterno con journal mode contrastante e sentinel di accesso; tutte le operazioni previste usano il profilo scratch e nessun file esterno viene modificato.
- [x] #2 Test su upstream fissato prima di attribuire conseguenze reali al bug.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Proposta iniziale da verificare sul codice corrente, non una correzione già applicata.

creare e impostare il contesto scratch prima degli import upstream anche nel driver, oppure spostare tutte le operazioni upstream in un worker con ambiente esplicito. Gestire consapevolmente le variabili PYTEMAN ereditate, incluso `PYTEMAN_REQUIRE_MARKER`, senza indebolire il controllo di sicurezza dell'operatore; fornire un marker appropriato o fallire chiaramente.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Indicazioni di coordinamento del documento di origine: EX-06 per la verifica upstream riproducibile.

I prerequisiti operativi sono quelli nel campo Dependencies; i rinvii a consumer e file condivisi non impongono dipendenze reciproche. Aggiornare test e documentazione pertinente nello stesso task; riportare comandi e output reali prima di Done.
EX-06 integra e verifica a valle. Per questo task predisporre prima il checkout compatibile e un preflight minimo, senza attendere il completamento del job di integrazione EX-06.

Review (simplify angles, 2026-09-28) on the work/task28-driver-profile tree. FINDING (medium, altitude): the ambient boundary is enumerated while the child env is a wholesale copy. Both drivers build the child env with dict(os.environ) (examples/hermes-109966/run_repro.py:120, examples/hermes-111912/run_repro.py:140) and overwrite only HERMES_HOME, PYTEMAN_RULES and PYTEMAN_LOG, so ambient PYTEMAN_REQUIRE_MARKER reaches the children. Verified by running both drivers with PYTEMAN_REQUIRE_MARKER=<missing file>: the child refuses at sitecustomize's marker check (src/pyteman/sitecustomize.py:186-188, os._exit(2)) and the driver reports a readiness timeout that names the ruleset ('child never became ready in 10s (ruleset=...)' and 'holder never became ready in 10s', rc=2; the 109966 leg also preserves a scratch home under /tmp). With the marker file present the run is unaffected (control run reached VERDICT). PYTEMAN_STRICT_PRAGMA, PYTEMAN_STRICT_BARRIER and PYTEMAN_RUN_ID ride through the same copy; inert for the sleep-only rulesets, live for any future pragma or barrier rule. The plan line 'gestire consapevolmente le variabili PYTEMAN ereditate, incluso PYTEMAN_REQUIRE_MARKER ... fornire un marker appropriato o fallire chiaramente' is met only for RULES and LOG. Alternative: at each driver's single child-env site, strip the prefix (env = {k: v for k, v in os.environ.items() if not k.startswith('PYTEMAN_')}) before setting RULES/LOG, which makes the preflight refusal the only ambient boundary and covers future PYTEMAN vars; smaller option: add PYTEMAN_REQUIRE_MARKER to the refusal tuple.

FINDING (low, readability) from the same review: tests/test_example_driver_isolation.py:107 _run passes str(ruleset) as argv[2] to both drivers, but 109966's argv[2] is the expected verdict (examples/hermes-109966/run_repro.py usage line and argv parse at :77), so for 109966 the empty.yaml path lands in `expected`, never matches a verdict, and the run always ends via EXPECTATION-MISMATCH exit 1, absorbed by `assert r.returncode in (0, 1)`; _empty_ruleset is load-bearing only for 111912. Alternative: per-driver args in the test, or one comment line in _run stating 109966 reads argv[2] as the expected verdict.

IMPLEMENTAZIONE (2026-09-28, PR #178, head b17c86a): riprodotta la perdita sul tip upstream verificato 2cfb655d52 PRIMA del fix (HERMES_HOME su un sentinel: il driver 109966 crea l'intero albero del profilo dell'operatore, SOUL.md/cache/sessions/backups; nuance fedele registrata dalla belt: il config.yaml non viene sovrascritto ma backup-ato sotto backups/config/, la creazione dell'albero e' il leak provato). Fix: entrambi i driver rifiutano l'attivazione pyteman ambientale (PYTEMAN_RULES/LOG) con messaggio chiaro, costruiscono lo scratch e esportano os.environ['HERMES_HOME'] PRIMA del primo import upstream, e i figli partono da un ambiente SPOLPATO di ogni nome PYTEMAN_* (solo rules e log dell'esempio vengono impostati: il REQUIRE_MARKER ambientale con file assente prima rifiutava i figli in sitecustomize mentre il driver riportava un readiness timeout, fallimento mis-attribuito), e l'env dei figli 111912 porta lo scratch home. Sei test con stub recorder (record in APPEND perche' i figli 109966 importano lo stesso stub e un record troncante accecava la gamba alla propria regressione, trovato e fissato dalla belt; il raddoppio di backslash nel sorgente del test e' la trappola documentata). READMEs aggiornati.

GATE (2026-09-28): /simplify combinato 2 finding APPLICATI (il buco ambientale REQUIRE_MARKER/STRICT_*/RUN_ID nel env copiato wholesale: strip di tutti i PYTEMAN_* + test marker; la verita' CLI del helper _run: argv per-driver documentato). BELT high: CHANGES-REQUIRED con 1 finding IMPORTANT confermata per esperimento (la gamba 109966 era cieca ESATTAMENTE alla propria regressione: record truncate cancellato dai figli; reorder genuino del 109966 passava) FIX applicato e riverificato (reorder genuino 109966 ora FALLISCE la gamba; ordine dei byte verificato prima di ogni mutazione perche' la prima era uno swap no-op) + 1 minor strutturale (child-env line drop non pinnato: l'argomento strutturale regge, l'export os.environ prima della copia e' pinnato dalla gamba genuina) + 1 nit (argv: gia' sistemato da /simplify) + 1 pre-esistente FILED dalla belt come TASK-186 (le home h111912-* abbandonate sulle uscite anomale, ~140 directory accumulate). MUTAZIONI: reorder genuino per ciascun driver uccide la propria gamba; refusal block tolto per ciascuno uccide la gamba refusal; strip revertita a dict(os.environ) uccide la gamba marker in entrambi. Batteria 1357 passed 2 skipped.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Chiuso con il merge feaded9 (PR #178, squash di b17c86a su master fa81110). Riprodotta la perdita sul tip upstream fissato 2cfb655d52 (AC2) prima del fix: il driver 109966 con HERMES_HOME su un sentinel creava l'intero albero del profilo dell'operatore (SOUL.md, cache, sessions, backups; il config.yaml non viene sovrascritto ma backup-ato, nuance registrata). Fix (AC1): entrambi i driver rifiutano l'attivazione pyteman ambientale con messaggio chiaro, esportano lo scratch come proprio HERMES_HOME prima del primo import upstream (import-time e first-use risolvono entrambi nello scratch), spogliano l'env dei figli di OGNI nome PYTEMAN_* (il REQUIRE_MARKER ambientale con file assente prima rifiutava i figli in sitecustomize con il driver che riportava un readiness timeout mis-attribuito), e i figli 111912 ricevono lo scratch home. Sei test con stub recorder in append (la belt ha trovato e la coordinazione ha fissato la gamba 109966 cieca alla propria regressione per il record troncante). Gate: /simplify 2 finding applicati; belt CHANGES-REQUIRED (la gamba cieca) fissata e riverificata con reorder genuino per entrambi i driver + TASK-186 aperta dalla belt per le home abbandonate del 111912; revisione indipendente APPROVED a b17c86a con 1 LOW (docstring del test helper che descrive il meccanismo di uscita pre-fix, errato anche per quello) e 1 INFO (fallback path condiviso dello stub) registrati qui; CI verde 7 check; batteria 1357 passed 2 skipped; mutazioni che uccidono (reorder genuino per driver, refusal block, strip reverts).
<!-- SECTION:FINAL_SUMMARY:END -->
