---
id: TASK-27
title: 'EX-02. Garantire cleanup del process tree di #111912 su ogni uscita'
status: Done
assignee: []
created_date: '2026-09-16 12:20'
updated_date: '2026-09-28 00:23'
labels:
  - audit-2026-09-16
  - opus-5
  - ex
  - confirmed
milestone: m-4
dependencies: []
references:
  - 'examples/hermes-111912/run_repro.py:67-156'
  - 'examples/hermes-111912/dashboard_sim.py:16-25'
documentation:
  - doc-1
  - doc-2
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit 2026-09-16 sul commit a28b12662a46727ff806a42122db0ffe8333d760. Esecuzione futura prevista con Opus 5. Riprodurre il caso sullo stato corrente prima di correggere; non dipendere dalla conversazione originale.

**Priorità / stato:** P1, CONFIRMED, aperto.

**File:** `examples/hermes-111912/run_repro.py:67-156`, `dashboard_sim.py:16-25`.

**Evidenza:** il driver non ha un `try/finally` attorno al ciclo di vita dei processi. Una `_kill_pids_posix` sintetica che solleva `RuntimeError('controlled upstream failure')` lascia il percorso senza alcuna chiamata di cleanup. Il ramo di readiness timeout termina solo il parent. Dopo SIGSTOP, un'eccezione SQLite o uno scanner fallito saltano la terminazione del child.

**Impatto:** processi orfani, eventualmente fermati con SIGSTOP e ancora detentori del database. Una seconda esecuzione può convivere con residui della prima.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 test di failure injection dopo spawn, prima del ready, dentro lo stop upstream, dopo SIGSTOP e durante la rotazione.
- [x] #2 Nessun processo del test resta vivo o fermato.
- [x] #3 Nessun segnale a processi estranei.
- [x] #4 Test reali del lifecycle solo in processi isolati con timeout esterno.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Proposta iniziale da verificare sul codice corrente, non una correzione già applicata.

registrare le risorse appena create e chiuderle in `finally`; terminare e attendere il parent, gestire esplicitamente il discendente, identificare solo i processi creati dal driver. Rendere osservabile il fallimento di cleanup senza mascherare quello originale.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Indicazioni di coordinamento del documento di origine: nessuna; coordinare EX-05 per conservare artefatti senza conservare processi.

I prerequisiti operativi sono quelli nel campo Dependencies; i rinvii a consumer e file condivisi non impongono dipendenze reciproche. Aggiornare test e documentazione pertinente nello stesso task; riportare comandi e output reali prima di Done.

Verification probe (2026-09-18, own scratch processes only in /tmp, cleaned up after, NOT the real hermes-agent/tui_child scenario): synthetic three-process tree driver -> mid_parent -> grandchild. mid_parent spawned via subprocess.Popen(start_new_session=True) so pgid == parent.pid is valid immediately at spawn time; no later os.getpgid() lookup, which avoids the race where the parent may already be reaped or its PID reused before cleanup reads the group.

Scenario A - os.kill(parent.pid, SIGKILL) only: grandchild remained alive (proc state S) after the parent was killed and reaped. Reproduces the orphaning defect this task tracks.

Scenario B - os.killpg(pgid, SIGKILL): grandchild stopped running and ended in zombie state (Z), not immediately removed from /proc. Correction to how this was first described: that is a residual process-table entry awaiting reap by whatever became its subreaper after re-parenting, not 'no residue' - the correct claim is that the process stops running and releases its resources (fds, DB locks) immediately on SIGKILL, not that the /proc entry vanishes instantly.

Scope and limits: entirely synthetic (time.sleep loops), no sqlite/-wal/-shm, no real tui_child.py or hermes-agent code exercised. Capturing pgid at spawn removes the read-time race against an already-reaped parent, but does not by itself eliminate PID/PGID reuse in general (e.g. long-running systems where the OS recycles PIDs); killpg is only as safe as the interval between capturing pgid and firing the signal staying free of reuse. No safety claim should rest on a bare child PID alone; scope kill actions to the driver's own captured group, and treat ESRCH from killpg as benign (group already gone) without masking the original error.

No repo code changed by this probe. Any change to run_repro.py/dashboard_sim.py based on this needs explicit user confirmation before implementation.

IMPLEMENTAZIONE (2026-09-28, PR #177, head 2e63a9d): _TreeHandle possiede l'albero (spawn con start_new_session=True quindi pgid == parent.pid catturato allo spawn, nessuna lettura a tempo di kill; kill() = killpg del gruppo catturato + kill difensivo del child pid appreso, ESRCH benigno, idempotente, reap del parent posseduto, errori restituiti non sollevati); tutto il ciclo di vita sotto try/finally con righe CLEANUP-ERROR; il ramo readiness-timeout si limita a _fail (il finally uccide l'albero intero, non solo il parent come prima). Sette test: unitari con alberi reali (orfanizzato dopo spawn; discendente SIGSTOPped ucciso con prova di stato T per polling; killpg osservato solo col pgid catturato e gruppo effettivo del figlio asserito essere quello che guida, non una disuguaglianza di pid che varrebbe anche senza sessione fresca; idempotenza) e a livello driver (run_repro.py reale come processo isolato con timeout esterno 60s, stub upstream per l'iniezione _kill_pids_posix-raises, la gamba scanner-raises sotto la vera pin del teardown cosicche' un orfano vivo e SIGSTOPped esiste al momento del crash: lo scenario esatto dell'audit; piu' una corsa completa con il ruleset reale fino al verdetto). README documenta il contratto di cleanup e il token CLEANUP-ERROR.

GATE (2026-09-28): /simplify combinato 5 finding APPLICATI (protocollo marker per il discendente nei test al posto del pgrep-polling duplicato; settle a polling con deadline invece di sleep fisso; helper _run_driver con ruleset param + _assert_no_tree_left condiviso; guardia morta child_pid != pgid tolta col commento riscritto sulla ragione vera (un discendente che esce dal gruppo, non il leader che non puo' coincidere); README). NOTA DI PROCESSO: il primo script di applicazione mori' su NameError DOPO i marcatori per-edit senza scrivere nulla (la lezione della memoria si e' ripresentata esattamente); rifatto con write verificato per grep. BELT high: CLEAN con 2 finding MINOR di test APPLICATE (l'asserzione-titolo AC3 non pinnava la proprieta' nominata: os.getpgid(parent.pid) == parent.pid; la gamba scanner-raise era vuota rispetto al cleanup sotto ruleset vuoto, misurato con kill-neutered che passava: ora gira sotto la vera pin) + 1 LOW teorico (finestra di riciclo pid fra reap e kill: wrap da 4.2M pid in secondi, non costruito) + 1 INFO (il check T copre anche i pid del baseline: fail-loud accettato). MUTAZIONI: kill-neutered e killpg-neutered uccidono i test UNITARI (le gambe driver NON discriminano killpg perche' dashboard_sim auto-termina quando il figlio muore: misurato e dichiarato nel body del PR); finally svuotato uccide la gamba upstream-stop; la gamba scanner tornata al ruleset vuoto fa passare kill-neutered (la vacuita' che la pin ha chiuso). Un flake in sviluppo (lettura singola dello stato T prima che il segnale atterri) fisso col polling a deadline: 3+ run stabili. Batteria 1351 passed 2 skipped.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Chiuso con il merge fa81110 (PR #177, squash di 2e63a9d su master 623933d). Il driver 111912 ora possiede il suo albero di processi: _TreeHandle cattura il pgid allo spawn (start_new_session, quindi pgid == parent.pid senza letture a tempo di kill), kill() segnala solo il gruppo catturato piu' il child pid appreso (ESRCH benigno, idempotente, errori restituiti non sollevati, parent posseduto reappato), e tutto il ciclo di vita corre sotto try/finally con righe CLEANUP-ERROR: lo stop upstream che solleva, lo scanner che fallisce, un fault di rotazione e il timeout di readiness uccidono l'albero intero su ogni uscita, dove prima il ramo readiness uccideva solo il parent e le eccezioni post-SIGSTOP saltavano la terminazione. Sette test (unitari con alberi veri inclusi il discendente SIGSTOPped ucciso e il gruppo effettivo del figlio asserito; a livello driver con iniezione tramite stub upstream, la gamba scanner sotto la vera pin del teardown cosicche' l'orfano fermo esiste al momento del crash, e la corsa completa col ruleset reale fino al verdetto). README documenta il contratto e il token CLEANUP-ERROR. Gate: /simplify 5 finding applicati (marker protocol, polling settle, helper condivisi, guardia morta, README); belt high CLEAN con 2 finding minor di test applicati (asserzione che pinnava la proprieta' sbagliata; gamba scanner vacua sotto ruleset vuoto, misurata con kill-neutered) e il fatto onesto dichiarato nel body (le gambe driver non discriminano killpg perche' dashboard_sim auto-termina); revisione indipendente APPROVED a 2e63a9d con 4 finding non bloccanti registrati qui: LOW la home /tmp/h111912-* resta sulle uscite fallite (pre-esistente, chiusa da tmpfiles; muovere la rmtree nel finally e' il fix se si vuole), LOW la gamba real-ruleset non asserisce pin_engaged=True (una riga, se il wiring della pin deriva altrove la gamba si svuota in silenzio), INFO il README under-describe il kill diretto del child, INFO residuo. CI verde 7 check; batteria 1351 passed 2 skipped; mutazioni che uccidono al livello che puo' vederle.
<!-- SECTION:FINAL_SUMMARY:END -->
