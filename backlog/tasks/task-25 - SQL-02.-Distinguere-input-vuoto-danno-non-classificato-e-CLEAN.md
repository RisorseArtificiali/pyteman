---
id: TASK-25
title: 'SQL-02. Distinguere input vuoto, danno non classificato e CLEAN'
status: Done
assignee:
  - '@opus-5-sql02'
created_date: '2026-09-16 12:20'
updated_date: '2026-09-16 22:55'
labels:
  - audit-2026-09-16
  - opus-5
  - sql
  - confirmed
milestone: m-3
dependencies: []
references:
  - 'src/pyteman/sqlitekit/integrity.py:2-20'
  - tests/test_integrity.py
documentation:
  - doc-1
  - doc-2
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit 2026-09-16 sul commit a28b12662a46727ff806a42122db0ffe8333d760. Esecuzione futura prevista con Opus 5. Riprodurre il caso sullo stato corrente prima di correggere; non dipendere dalla conversazione originale.

**Priorità / stato:** P2, CONFIRMED, aperto.

**File:** `src/pyteman/sqlitekit/integrity.py:2-20`, `tests/test_integrity.py`.

**Evidenza:** stringa vuota, solo header, `database disk image is malformed` e messaggi di danno pagina restituiscono tutti classes vuoto. Il codice non li dichiara CLEAN, ma non distingue acquisizione mancante da corruzione non riconosciuta. In messaggi misti riconosciuti/non riconosciuti non segnala le righe rimaste fuori classificazione.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 corpus versionato di output reali SQLite più fixture sintetiche etichettate: clean, vuoto, header-only, schema, notadb, danno pagina, misti e righe sconosciute.
- [x] #2 Ogni output non-clean ha una diagnosi non vuota senza falsa precisione.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Proposta iniziale da verificare sul codice corrente, non una correzione già applicata.

stati espliciti per input mancante/inconclusivo e danno sconosciuto, con righe non classificate preservate; CLEAN solo sull'esito positivo previsto. Documentare la natura incident-specific delle categorie CANONICAL_* e il formato input testuale atteso.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Indicazioni di coordinamento del documento di origine: nessuna; coordinare SQL-01 per schema di risposta compatibile.

I prerequisiti operativi sono quelli nel campo Dependencies; i rinvii a consumer e file condivisi non impongono dipendenze reciproche. Aggiornare test e documentazione pertinente nello stesso task; riportare comandi e output reali prima di Done.

2026-09-16, SQL-02, contratto di tranche concordato col parent e registrato prima di qualunque modifica. Non e un cambio di AC deciso qui: e il perimetro entro cui gli AC esistenti vengono soddisfatti.

**Confine con TASK-24 (SQL-01).** TASK-24 dipende da questo task, quindi lo schema di risposta definito qui e la base su cui SQL-01 si innestera. Il criterio attuale di FTS_ONLY ('c'e danno, nessuna classe riconosciuta, tutte le righe di danno contengono _fts') resta invariato in questa tranche. Va fissato da un test di compatibilita etichettato esplicitamente come comportamento noto da correggere in TASK-24, non come verita semantica: senza quell'etichetta il test verrebbe letto come contratto e SQL-01 dovrebbe romperlo invece di sostituirlo. Motivo del vincolo: introducendo uno stato di danno sconosciuto, una riga _fts non riconosciuta passerebbe da FTS_ONLY a sconosciuta come effetto collaterale, e quel cambio e lavoro di SQL-01 e non di questo task.

**Schema di risposta.** Deve permettere a TASK-24 di sostituire la classificazione usando il nuovo stato unknown senza migrare di nuovo lo schema. Se la risposta porta diagnostica o righe non classificate, deve distinguere un match euristico da una conferma FTS. Vietati un campo booleano 'verified' o qualunque forma che dichiari certa la classificazione prodotta da quella euristica. Le righe raw sono sempre preservate.

**Corpus (AC #1).** Gli output reali SQLite si producono solo da database nuovi e temporanei creati dal task, mai da file dell'utente e mai da database preesistenti. Si conservano le fixture testuali, le versioni degli strumenti e la procedura di riproduzione; non si versionano binari corrotti superflui.

**Casi trovati in riproduzione, oltre a quelli citati nella Description.** `classify_integrity('*** in database main ***\nok')` ritorna [] e non ['CLEAN'], perche CLEAN e deciso da `lines == ['ok']` esatto. Resta fixture sintetica finche non viene osservato output reale in quella forma: non si dichiara una garanzia SQLite non misurata. Un input non stringa alza oggi AttributeError dall'interno; va sostituito da un errore di tipo esplicito e documentato, tenuto distinto dalla stringa vuota e dall'acquisizione assente, che sono l'altro stato che questo task introduce.

**Ownership.** src/pyteman/sqlitekit/integrity.py, tests/test_integrity.py e i nuovi test di classificazione, docs specifiche su integrity se necessarie, README la sola frase su sqlitekit nella sezione Runner. Nessuna modifica a runner o report. Fuori perimetro RUN-04 e i refactor.

**Stato di partenza riprodotto sul codice corrente**, non ripreso dall'audit: stringa vuota, solo whitespace, solo header, 'database disk image is malformed' e un danno pagina ritornano tutti []; un input misto con una riga riconosciuta e due no ritorna ['CANONICAL_INDEX_COUNT'] e scarta le altre due senza segnalarle.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Chiuso su stato hashato e approvato dal parent il 2026-09-17. Nessun commit e nessun push: la tranche resta nel working tree condiviso.

**Cosa e cambiato.** classify_integrity restituisce una mappa di cinque chiavi al posto di una lista: status, classes, unclassified, diagnosis, raw. Gli stati sono CLEAN, DAMAGED, UNKNOWN, INCONCLUSIVE, NO_OUTPUT. L'unico cambio di API e lo spostamento di CLEAN da classes a status, documentato esplicitamente in docs/integrity.md e nel docstring del modulo: una lista di firme di danno che portava anche l'assenza di danno rendeva la lista vuota portatrice di due significati opposti. classes resta non vuota esattamente quando status e DAMAGED, invariante garantita per costruzione dal costruttore unico _verdict e verificata dai test. Un input non stringa alza TypeError che nomina la funzione, il tipo ricevuto e la stringa vuota come valore da passare.

**AC #1 soddisfatto.** tests/integrity_corpus.py contiene 18 campioni etichettati per origine, 12 observed e 6 synthetic. Tutte le otto forme richieste dal criterio sono coperte: clean, vuoto, header-only, schema, notadb, danno pagina, misti e righe sconosciute. Gli output reali provengono solo da database temporanei creati per lo scopo, mai da file preesistenti, e nessun binario corrotto e versionato: docs/integrity.md registra la procedura di riproduzione di ogni campione observed, e un test parametrico verifica che nessun campione observed resti senza procedura e che nessuna procedura descriva un campione inesistente.

**AC #2 soddisfatto.** Ogni stato ha una diagnosi non vuota scritta per esteso e non assemblata da frammenti, verificata su tutti i 18 campioni. La falsa precisione e evitata su due fronti: UNKNOWN dichiara che il testo non e stato letto e si ferma li, perche il canale d'errore porta anche messaggi di database sani come 'database is locked', e la diagnosi di FTS_ONLY dichiara nel proprio testo di essere un match sul nome e non una conferma che FTS sia coinvolto.

**Fatti misurati e documentati.** Lo stato d'uscita della shell sqlite3 su un file che non e un database dipende dal contenuto: byte casuali e un header plausibile stampano 'file is not a database' su stderr e escono 1, mentre un file di testo ASCII viene letto come script SQL ed esce 0, con stdout vuoto in tutti e tre i casi. Un chiamante puo quindi ricevere cattura vuota e uscita di successo da un file che non e un database, che e esattamente l'accoppiata che NO_OUTPUT esiste per non leggere come promozione. Misurato anche che l'header appartiene al solo controllo b-tree e non alla cattura nel suo insieme, e che danni di entrambi i tipi insieme producono 62 righe.

**Criterio FTS_ONLY invariato.** L'espressione e byte per byte quella trovata, come da contratto di tranche, ed e fissata da un test etichettato come comportamento noto da correggere in TASK-24, non come verita semantica. Sono fissati tutti e tre i congiunti del criterio, non solo il caso positivo. L'unico effetto indiretto di questa tranche, una cattura con header di un database non chiamato main che ora soddisfa il criterio dove la riga header non riconosciuta lo bloccava, e misurato e scritto in docs/integrity.md invece di restare latente.

**Gate eseguiti nell'ordine concordato.** Implementazione, poi /simplify con applicazione delle correzioni, poi code review high effort sullo stato finale rieseguita da zero dopo le modifiche, poi test. Le sei rilevazioni della review sono tutte risolte. Verificando una di esse ho trovato un errore mio non segnalato da nessun revisore: quattro documenti affermavano che la shell esce 1 su un file non database, falso in generale, corretto in tutti e quattro.

**Perimetro dei test, conteggio esatto.** tests/test_integrity.py 5 piu tests/test_integrity_classification.py 99 piu tests/test_docs_integrity.py 51, totale 155 passati. Suite completa 534 passati e 0 falliti. Batteria di mutazione a 18 mutanti eseguita interamente su copia in /tmp, con isolamento provato prima di fidarsi dei risultati verificando che integrity.__file__ risolva dentro la copia: 18 mutanti su 18 uccisi.

**Hash SHA256 dello stato approvato, che questa chiusura non ha toccato.**
2090d7a96d2448d4c93f6e5024a02feaf3ad4723de86fc3c016b1370009b972b  src/pyteman/sqlitekit/integrity.py
c783723f416eea1b86517002ff417a2a0dc0cca834de19dd5d462b6552dc5d86  tests/integrity_corpus.py
7133a376d29085f3414b2ddfdde4f59f9e751574f79497c027a42000f1012940  tests/test_integrity_classification.py
b45afc1242f5e8b4dcbeb364e35740d18177a8d60032b4e957bc634b2bf377a8  tests/test_docs_integrity.py
06854f9fb0ec7593c438de1123fed3f376c0741a4866970b00cbafeba86069f6  tests/test_integrity.py
0ce8ae8f7560070296e7fa2f402a0c376968a68bddbd021897920a831f404205  docs/integrity.md

**Rilievo aperto girato a TASK-24.** La prosa chiama 'verbatim' le righe in unclassified, ma il codice applica str.strip a ogni riga: solo raw e integrale. Registrato nelle note di TASK-24 con la prova e le quattro occorrenze da correggere. Non bloccante e da sistemare senza toccare la semantica.
<!-- SECTION:FINAL_SUMMARY:END -->
