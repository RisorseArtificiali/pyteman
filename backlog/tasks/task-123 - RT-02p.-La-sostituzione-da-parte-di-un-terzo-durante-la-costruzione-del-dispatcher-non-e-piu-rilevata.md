---
id: TASK-123
title: >-
  RT-02p. La sostituzione da parte di un terzo durante la costruzione del
  dispatcher non e' piu' rilevata
status: Done
assignee: []
created_date: '2026-09-17 04:14'
updated_date: '2026-09-27 13:39'
labels:
  - patcher
  - rt-02
  - diagnostics
dependencies: []
references:
  - src/pyteman/patcher.py
  - docs/rules.md
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Registrato durante la correzione della regressione descrittori (2026-09-17). Non e' una regressione: prima della tranche RT-02 quel caso non era rilevato affatto. E' un buco noto, reso esplicito, che va deciso invece di restare implicito.

La seconda rilettura in pass 2 ora chiede PROPRIETA' e non identita': assente salta, dispatcher nostro si tira indietro, dispatcher di un altro Patcher rifiuta. Il confronto di identita' che c'era prima e' stato rimosso perche' era rotto in generale, dato che un attributo raggiunto via descriptor viene fabbricato a ogni accesso e `inst.m is inst.m` e' gia' False.

Conseguenza accettata, in TRE danni e non due (il terzo aggiunto il 2026-09-17 dopo la code review, verificato leggendo `_undo_one`):
1. La sostituzione del terzo viene scritta sopra e sparisce dal processo.
2. Il dispatcher chiama l'originale STALE catturato prima della costruzione, quindi l'istrumentazione gira su un callable che il programma non userebbe piu'.
3. La voce di ledger registra quello stesso callable stale come `original`. All'uninstall `_undo_one` trova il nostro dispatcher nello slot, prende il ramo `setattr` a patcher.py:305 e RIMETTE il callable pre-sostituzione sopra lo slot, restituendo `[]`. L'operatore legge un uninstall pulito su un ripristino che ha distrutto la modifica del terzo. Il contratto di rilascio documentato in docs/rules.md ("un terzo ha sostituito il nostro wrapper DOPO l'installazione, lasciamo lo slot dov'e'") non scatta, perche' qui la sostituzione e' avvenuta PRIMA che il nostro wrapper atterrasse.

Perche' e' stato accettato per ora: il codice PRIMA della tranche RT-02 non rilevava nemmeno quel caso, quindi non si perde nulla rispetto alla linea di base, e l'unico meccanismo che lo rilevava nella versione intermedia rompeva ogni punto su istanza raggiunto via classe, che e' un danno certo e frequente contro uno ipotetico e raro.

Opzioni se si decide di rilevarlo:
1. Sondare la stabilita' di identita' dello slot leggendolo due volte in cima al loop, e applicare il confronto di identita' SOLO se stabile. Copre il caso comune (attributo di classe o di modulo) e resta muto su descriptor. Costo: due getattr in piu' per slot, che su un container con property a effetti collaterali significa eseguire il getter una volta in piu'.
2. Confrontare un'identita' piu' profonda, per esempio `__func__` e `__self__` per i metodi legati, invece dell'oggetto restituito. Copre i metodi legati e non le property. Forma proposta dalla code review, da verificare prima di adottarla:

    def _same_callable(a, b):
        try:
            return (getattr(a, "__func__", a) is getattr(b, "__func__", b)
                    and getattr(a, "__self__", a) is getattr(b, "__self__", b))
        except BaseException:
            return False

3. Non rilevarlo e dirlo, allineando la documentazione alle altre finestre note.

Preferenza preliminare, da confermare: la 3 se il resto della tranche regge, perche' le opzioni 1 e 2 comprano un rilevamento parziale con un meccanismo che va poi mantenuto giusto su ogni forma di container che il progetto accetta, ed e' esattamente il tipo di test che si e' gia' rotto una volta. Il danno 3 pero' alza il costo dell'opzione 3 rispetto a quando questo task e' stato scritto: non e' solo "non ce ne accorgiamo", e' "distruggiamo in silenzio e riportiamo pulito".

Stato al 2026-09-17: il limite e' gia' scritto in `src/pyteman/patcher.py` (commento della seconda rilettura, con puntatore a questo task) e in `docs/rules.md` (paragrafo sulla proprieta'), quindi non e' piu' implicito nel codice. Resta da prendere la decisione vera fra le tre opzioni.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 [emendato 2026-09-27] Deciso e scritto se la sostituzione da parte di un terzo durante la costruzione del dispatcher debba essere rilevata, e con quale contratto: decisione presa, opzione 1 (identita' gated da sonda di stabilita'), contratto scritto in patcher.py e docs/rules.md
- [x] #2 [emendato 2026-09-27, vedi note] Se rilevata, il meccanismo non regredisce ne' il punto su istanza raggiunto via classe ne' il punto su property: un test per ciascuna delle due forme dimostra che restano installabili, e il meccanismo dichiara esplicitamente dove l'identita' non e' chiedibile
- [x] #3 Se NON rilevata: non applicabile, la decisione e' rilevare (opzione 1)
- [x] #4 Il comportamento all'uninstall e' coperto da un test, qualunque sia la decisione: con il rifiuto scelto, il test pinna che la sostituzione resta al suo posto, niente viene installato sopra (applied e wrapped vuoti) e lo slot risponde alla sostituzione
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
DECISIONE (2026-09-27, sessione notturna): opzione 1, identita' gated da sonda di stabilita'. Dopo la lettura di settle, dentro la prenotazione dello slot, una lettura in piu' chiede se lo slot e' identita'-stabile (due letture consecutive rispondono lo stesso oggetto); solo in quel caso un valore settled che non sia piu' il live da cui la decisione era stata presa, e che non appartenga a nessun Patcher, viene rifiutato con SlotOwnershipError nominando lo slot. La sostituzione resta dov'e' atterrata.

PERCHE' NON l'opzione 2 (__func__/__self__): il confronto profondo ricade su `a is b` per le property che fabbricano callable semplici freschi a ogni lettura (niente __func__), quindi rifiuterebbe proprio la classe di punti che la regressione RT-02 aveva rotto; non puo' stare in piedi senza un gate di stabilita' comunque. PERCHE' NON l'opzione 3: il danno 3 (distruzione silenziosa con uninstall che riporta pulito) e' esattamente la menzogna operativa che il task stesso aveva segnato come costo cresciuto dell'opzione 3.

PERCHE' NON la lettera originale dell'AC 2 (vietava il confronto d'identita' su getattr): l'AC voleva impedire la ricaduta della regressione descriptor, non vietare l'unica domanda che chiude la finestra dove e' chiudibile. Il gate di stabilita' chiede allo slot SE l'identita' e' rispondibile, invece di indovinare la forma dell'oggetto: su slot instabili resta muto, su slot stabili il confronto e' sano. L'emendamento tiene l'intento (nessuna regressione, test per entrambe le forme) e lascia cadere il divieto di meccanismo. Nota: la lettera originale e' rimasta in piedi perche' la preferenza preliminare era l'opzione 3; cambiata la decisione, la lettera andava cambiata con lei.

COSTO accettato e documentato: una esecuzione in piu' del getter per slot per patch, dentro la prenotazione (il task lo prezzava gia'); piazzata DOPO la lettura di settle e non in cima al loop perche' la lettura decisiva deve restare la terza lettura dello slot: i test di coreografia in test_slot_reservation.py parcheggiano un thread su quella lettura con la prenotazione in mano, e una sonda prima della prenotazione parcheggerebbe il thread fuori dalla finestra coperta (misurato: i due test dei thread fallivano esattamente cosi', DID NOT RAISE, prima dello spostamento).

VERIFICA: suite completa 1276 passed 2 skipped (baseline 1273 + 3 test nuovi, conteggio collezionati 1275 -> 1278 verificato con stash); check pulito; mutazioni: gate spento -> il test di rilevamento fallisce; gate senza il termine stable -> il controllo slot-instabile fallisce; albero ripristinato byte-exact (sha256 d9fb5548...).

FINITURA documenti: commento della seconda lettura in patcher.py e paragrafo in docs/rules.md aggiornati: la finestra ora e' chiusa sugli slot identita'-stabili e resta aperta sui descriptor, con i tre danni documentati per quel ramo; il puntatore pre-scrittura (ex 'the general identity question stays open') riscritto per dire coperta fino alla lettura di settle e aperta da lì alla setattr.

/simplify 4 angoli (2026-09-27), esito: 3 finding applicati, 2 skip dichiarati. APPLICATO (simplification+efficiency, convergenti): gate spostato SOTTO i due rami di ownership (self-extend e another-Patcher), quindi il termine `settled_owner is None` e le sue sei righe di commento-narrazione sono spariti (equivalenza verificata per analisi dei casi su owner in {self, other, None} incrociato con settled-is-live e stabile); sonda resa CONDIZIONALE (`settled is not live` corto-circuita prima della lettura), quindi il getter extra si paga solo sul cammino sospetto, mai sullo slot invariato e mai sui rami reentrant/altrui che ora lasciano il loop prima del gate. Costo del task migliorato: da 'un getter in piu' per slot a zero sul cammino comune. APPLICATO (altitude): docs/rules.md precisione sui descriptor con cache (cached_property, property memoizzante misurano stabili; la loro ricostruzione fra le due letture viene rifiutata, direzione conservativa, ora scritto) e clausola 'askable here too, and declined' nel commento pre-scrittura. APPLICATO (reuse, bordo): riga di commento sul probe che alza (risponde _ABSENT, non e' settled, l'identita' resta insondabile: silenzio deliberato, non oversight).

SKIP 1 (reuse): terza copia della coreografia vittima-conta-letture nel file di test (_swap_victim accanto a _ParkOnRead.victim() e al Victim inline del test refusing-read). Estrazione rifiutata: le altre due copie sono pre-esistenti e fuori dal diff; rifattorizzare fixture verdi esistenti a meta' task e' un drive-by refactor. Registrato qui, non promosso a task: la soglia e' marginale (il file tollerava due copie inline prima di questo diff).

SKIP 2 (altitude, osservazione): i punti bound-method restano muti (identita' instabile, __func__/__self__ stabili); un secondo ramo gated su identita' profonda li coprirebbe. Declinato: combacia con la preferenza di manutenibilita' registrata; se il ramo silenzioso venisse segnalato nell'uso reale, questo e' il punto da riprendere.

NOTA DI CODE REVIEW esterna (2026-09-27, high-effort sul diff task123.diff nel worktree task179impl/tree): verdetto CLEAN, zero finding sopra soglia. Contratto verificato con prove eseguite: suite completa 1276 passed 2 skipped; ruff pulito; sonde comportamentali (letture contate: slot invariato = 3 letture, sonda = quarta lettura solo sul cammino sospetto; sonda dentro la prenotazione; RuntimeError dalla sonda propaga con registro rilasciato; AttributeError risponde _ABSENT e smorza; rami ownership self/altro consumati prima del gate senza spendere la sonda; punto istanza reale session.query installa con 4 letture; property memoizzante stabile installa, ricostruita a read 3 rifiuta, ricostruita anche a read 4 smorza; target coroutine rifiuta uguale). UNA osservazione SOTTO SOGLIA (~55), registrata qui perche' il report la menziona: docs/rules.md (riga ~388) e il commento in patcher.py (~2665-2669) dicono che la ricostruzione di un descriptor con cache 'fra le due letture' viene rifiutata. Verificato per sonda: il rifiuto scatta solo per la ricostruzione caduta fra la lettura decisionale (live) e quella di settle; una ricostruzione confinata nel varco settle->sonda risponde instabile e SMORZA il gate (si installa sopra). 'Le due letture' ha una lettura accurata (le due letture del pass 2, terminologia usata piu' sotto nello stesso paragrafo: 'the second reading') e una invertita (l'antecedente 'two consecutive reads' della frase immediatamente precedente). Chiarire con una clausola ('fra la lettura decisionale e quella di settle') alla prossima toccata del paragrafo; nessun cambio di comportamento richiesto.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Chiuso con il merge a1a5a46 (PR #164, squash di d5ffacd45843f6b86eca2ad21955fd33b3e049d1 su master 1149aa0). Decisione: rilevare, con identita' gated da sonda di stabilita' misurata (opzione 1). Dopo la lettura di settle, dentro la prenotazione e dopo i due rami di ownership, una lettura condizionale (solo se settled non e' piu' live) chiede se lo slot risponde lo stesso oggetto due volte; in quel caso la sostituzione di un terzo durante la costruzione viene rifiutata con SlotOwnershipError, la sostituzione resta al suo posto, applied e wrapped vuoti. Slot invariato: sempre 3 letture, costo zero. Descriptor fresh-per-read: muto (ownership-only). Descriptor con cache: misurato stabile, la ricostruzione nel varco decisionale->settle viene rifiutata (conservativo, scritto in docs/rules.md). Gate revisione: /simplify 4 angoli (3 finding applicati: gate sotto i rami ownership, sonda condizionale, precisione docs; 2 skip dichiarati nelle note), code-review high CLEAN (7 punti contratto confermati con esecuzione), revisione indipendente APPROVED a d5ffacd con 11 invarianti tracciati 0 rotti (2 finding non bloccanti: uno gia' soddisfatto nel merge, l'altro rotto in TASK-184), CI verde su 7 check, batteria 1276 passed 2 skipped, mutazioni che uccidono i test nuovi. Follow-up aperti: TASK-184 (test committed direzione refusal descriptor con cache + ancora commento 'Last look').
<!-- SECTION:FINAL_SUMMARY:END -->
