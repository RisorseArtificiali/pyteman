---
id: TASK-62
title: Documentare applied come storico delle patch
status: Done
assignee: []
created_date: '2026-09-16 18:07'
updated_date: '2026-09-17 01:17'
labels:
  - rt
  - opus-5
  - confirmed
  - review-rt-01
dependencies: []
references:
  - src/pyteman/patcher.py
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Trovato durante la verifica skeptic di RT-01 (TASK-1) il 2026-09-16, osservato direttamente nell'output di /tmp/skep/reentr.py. NON introdotto da RT-01: verificato con `git show HEAD:src/pyteman/patcher.py`, gia' a HEAD `uninstall()` faceva il loop di restore e poi `self._wrapped.clear()` senza toccare `self.applied`. RT-01 ha solo sostituito il loop con `_restore`.

**File:** `src/pyteman/patcher.py`, `Patcher.uninstall`.

`uninstall()` ripristina ogni wrap e lascia `self.applied` popolata. Dopo un uninstall il patcher elenca quindi una strumentazione che non e' piu' installata.

L'impatto e' POTENZIALE, non attuale, ed e' questa la correzione principale apportata alla descrizione il 2026-09-17: la stesura originale affermava "`applied` e' il campo che il report legge, quindi la lettura sbagliata e' quella plausibile". Sul codice corrente quell'affermazione e' FALSA. `grep -rn 'applied' src/ --include=*.py` non trova nessun lettore di produzione: in `patcher.py` ci sono solo l'assegnazione (riga 427), l'inizializzazione locale (515), l'append (542) e l'extend (591), piu' righe di commento; le due occorrenze in `runner/` (`report.py:5`, `matrix.py:606`) sono la parola inglese dentro prosa non correlata. Non lo legge il report, non lo legge il runner, non lo legge `sitecustomize`, non lo legge `sys._pyteman`. Gli unici lettori sono asserzioni di test. La stessa cosa era gia' stata rilevata su TASK-94. Il rischio reale e' quindi su un campo pubblico che un consumatore FUTURO potrebbe leggere, non su un report oggi sbagliato, e la gravita' del task e' Low per questa ragione.

Seconda correzione di fatto, 2026-09-17: il titolo e la prima riga dicono che `uninstall()` svuota `_wrapped` incondizionatamente. Dopo TASK-5 non e' piu' vero, perche' le voci rifiutate vengono trattenute per il retry. La semantica di `applied` che questo task governa non cambia, ma la premessa va letta con quella correzione. Dettaglio tracciato su TASK-73.

Due esiti erano accettabili e la scelta e' di contratto, non di implementazione: o `applied` e' lo stato corrente e va svuotata con `_wrapped`, o e' lo storico della run e allora va detto dove viene nominata. La scelta e' stata presa, vedi Implementation Notes.

Fuori perimetro RT-01: RT-01 possiede `_patch` e il rollback, non la semantica di `applied` attraverso `uninstall`. Tracciato invece di essere corretto dentro quel task.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Dopo uninstall(), applied non descrive piu' strumentazione installata: o viene svuotata insieme a _wrapped, o diventa uno storico esplicitamente nominato tale
- [x] #2 Storico documentato dove il campo e' definito ed esposto, nessun consumer produttivo attuale: la distinzione 'applicata ora' / 'applicata durante la run' e' scritta nel sito di definizione e scrittura, e l'assenza di lettori di produzione e' provata da grep
- [x] #3 Un test copre la sequenza activate -> uninstall -> lettura di applied
- [x] #4 Verificato che nessun consumatore esistente (runner/report, sitecustomize, sys._pyteman) dipenda dal comportamento attuale prima di cambiarlo
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
DECISIONE DI CONTRATTO PRESA, 2026-09-17, dall'orchestrator durante TASK-5 (RT-05). Delle due uscite che questo task lasciava aperte sul criterio #1 si sceglie la SECONDA: `applied` e' uno STORICO, esplicitamente nominato tale, e non viene svuotato da `uninstall`. Non viene ridefinito come stato corrente in questa tranche, per compatibilita' con i lettori esistenti.

Precisazione richiesta dalla stessa decisione, perche' il comportamento storico ha due facce che vanno dette separatamente:

- una chiamata `install_hook` IDEMPOTENTE non aggiunge eventi. Installare due volte e' un no-op sul secondo passaggio, quindi non produce una seconda occorrenza;
- un `uninstall` seguito da un VERO nuovo patch puo' aggiungere una nuova occorrenza storica dello stesso `modulo:simbolo`. Questo NON e' un bug e non va trattato come tale: e' esattamente cio' che significa 'storico della run'. Il duplicato registra due applicazioni realmente avvenute in momenti diversi.

Osservazione di provenienza: il duplicato e' stato osservato direttamente durante la sonda RT-05 del 2026-09-17 sul file corrente (sequenza force_patch_module -> uninstall -> force_patch_module, `applied` risulta `['rt05_mod_e:fn', 'rt05_mod_e:fn']`). La sonda non e' lavoro svolto su questo task: fissa il dato su cui la decisione e' stata presa.

Criterio #4 gia' verificato in parte il 2026-09-17: `grep` su `src/` mostra che NESSUN consumatore di produzione fuori da `patcher.py` chiama `uninstall()`; gli unici call site sono `activate()` e i test. Resta da confermare, contestualmente al criterio #2, dove `applied` viene letto a valle.

CRITERI #1, #3, #4 SODDISFATTI il 2026-09-17 durante TASK-5. #2 NON spuntato: la sua premessa e' falsa sul codice corrente, vedi sotto.

**#1.** `applied` e' ora nominato storico nel posto in cui e' definito e scritto: docstring di `Patcher.uninstall` in `src/pyteman/patcher.py` ("`applied` is deliberately NOT cleared here... `applied` is a HISTORICAL record"), piu' il commento gia' presente in `_patch` ("`_wrapped` says what is live, `applied` says what ran"). Nessun svuotamento aggiunto, per la decisione di contratto gia' registrata sopra.

**#3.** Regression aggiunta: `test_applied_is_a_history_not_a_live_inventory` in `tests/test_activation_atomic.py`. Copre la sequenza per intero e nei due versi che la decisione distingue: patch -> `applied == ['<mod>:ok']`; secondo `force_patch_module` senza uninstall -> invariato, perche' la guardia already-wrapped salta e lo storico non guadagna un evento per una patch non avvenuta; uninstall -> `applied` invariato mentre `_wrapped` e' vuoto; secondo uninstall -> no-op; nuovo `force_patch_module` VERO -> `applied == ['<mod>:ok', '<mod>:ok']`, il duplicato storico che la decisione dichiara corretto.

Il test e' mutation-pinned, non solo verde: inserendo `self.applied = []` in `uninstall` su una COPIA dell'albero sotto /tmp il test diventa rosso (origine provata via `patcher.__file__`, sha256 del file di repo identico prima e dopo). Comando: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /tmp/pyteman-audit-env-OOeElF/bin/python -m pytest tests/ -q` -> 629 passed.

**#4 COMPLETATO, e con esso emerge un CONFLITTO con la descrizione di questo task.** `grep -rn 'applied' src/ --include=*.py` da' cinque occorrenze in `patcher.py` (due assegnazioni piu' tre righe di commento) e due sole in `runner/`, entrambe la parola inglese dentro prosa non correlata (`matrix.py:606`, `report.py:5`). Nessun consumatore di produzione legge `Patcher.applied`: non il runner, non il report, non `sitecustomize`, non `sys._pyteman`. Gli unici lettori sono asserzioni di test. Questo conferma #4 nel verso piu' forte possibile: nessun consumatore esistente dipende dal comportamento attuale, quindi la decisione di contratto non rompe niente.

Ma la descrizione di questo task afferma "`applied` e' il campo che il report legge, quindi la lettura sbagliata e' quella plausibile". Sul codice corrente quell'affermazione NON regge: il report non lo legge, e non lo legge nessuno. La stessa cosa era gia' stata rilevata su TASK-94 ("`applied` has no production reader anywhere in the package"). Non la risolvo da solo perche' cambia la gravita' del task, non solo la sua prosa: senza consumatori l'impatto reale e' ipotetico e riguarda un campo pubblico che qualcuno potrebbe leggere in futuro, non un report oggi sbagliato.

**#2 aperto per la stessa ragione.** Il criterio chiede che "il consumatore del report distingua 'applicata ora' da 'applicata durante la run', e la distinzione sia documentata DOVE IL CAMPO E' LETTO". Non esistendo alcun sito di lettura, il criterio non e' soddisfacibile alla lettera. La distinzione e' stata documentata dove il campo e' DEFINITO e SCRITTO, che e' l'unico posto che esiste. Proposta all'orchestrator, non applicata: o si riformula #2 come "documentata dove il campo e' definito" e il task si chiude, oppure #2 resta aperto come promemoria per il momento in cui un consumatore verra' scritto, e in quel caso va agganciato al task che scrive quel consumatore invece di restare qui. Segnalo e mi fermo; nessuna chiusura autonoma.

Se l'orchestrator sceglie la prima, #1/#2/#3/#4 sono tutti soddisfatti e PROPONGO questo task per la chiusura.

ALLINEAMENTO TRACKER, 2026-09-17, autorizzato esplicitamente dall'orchestrator ("autorizzo correggere TASK-62 premessa falsa e AC2 in 'storico documentato dove definito/esposto, nessun consumer produttivo attuale'; aggiungi prova grep e test gia' eseguito, proponilo insieme a TASK-5"). Nessuna modifica di codice in questo passaggio: il tranche TASK-5 e' congelato per ordine dell'orchestrator e non e' stato toccato.

**Premessa falsa corretta nella descrizione, non in appendice.** La frase "`applied` e' il campo che il report legge" e' stata riscritta inline nel paragrafo che la conteneva, perche' un'errata in coda avrebbe lasciato l'affermazione falsa in piedi nel corpo. Al suo posto la descrizione dice ora che l'impatto e' POTENZIALE e riporta la prova. Corretta nello stesso passaggio anche la seconda premessa stantia, quella per cui `uninstall()` svuoterebbe `_wrapped` incondizionatamente: dopo TASK-5 le voci rifiutate vengono trattenute per il retry. Quella seconda correzione non era nominata nell'autorizzazione; la segnalo qui perche' lasciare in piedi una frase che so essere falsa dentro il testo che stavo gia' riscrivendo sarebbe stato peggio che correggerla. Il dettaglio resta tracciato su TASK-73.

**AC2 riformulato** come da autorizzazione, in "storico documentato dove il campo e' definito ed esposto, nessun consumer produttivo attuale", con esplicitata la doppia richiesta di prova: la distinzione scritta nel sito di definizione e scrittura, piu' l'assenza di lettori di produzione provata da grep. Gli altri tre criteri sono invariati nel testo. Nota meccanica: `acceptanceCriteriaSet` riscrive l'intera lista e azzera le spunte, quindi #1/#3/#4 sono stati rispuntati subito dopo insieme a #2. Nessuno dei tre e' stato riaperto e richiuso nel merito.

**PROVA GREP, rimisurata il 2026-09-17 su `src/pyteman/patcher.py` sha256 `272b84d1...`, non citata a memoria.** Due grep, il secondo piu' stringente del primo.

`grep -rn 'applied' src/ --include=*.py` da' undici righe: `patcher.py` 427 (`self.applied = []`), 515 (`wrapped, applied, current = [], [], None`, locale), 542 (`applied.append(...)`, sul locale), 591 (`self.applied.extend(applied)`), piu' 545/548/615/716/721 che sono righe di commento e docstring; `runner/report.py:5` e `runner/matrix.py:606` sono la parola inglese "applied" dentro prosa non correlata.

`grep -rn '\.applied' src/ --include=*.py` restringe alla forma attributiva e da' DUE sole righe in tutto `src/`: 427 e 591. Entrambe SCRITTURE. Zero letture attributive in tutto il package. Questa e' la forma piu' forte della prova richiesta dall'AC2 riformulato: non serve ragionare su quali moduli importino cosa, perche' non esiste da nessuna parte in `src/` un'espressione che LEGGA quel campo.

**TEST GIA' ESEGUITO, rieseguito oggi sullo stato corrente.** `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /tmp/pyteman-audit-env-OOeElF/bin/python -m pytest tests/test_activation_atomic.py -q -k applied_is_a_history` -> `1 passed, 46 deselected in 0.15s`. La suite dei tre file di mia proprieta' (`test_activation_atomic.py`, `test_sitecustomize.py`, `test_patcher.py`) -> `78 passed in 0.77s`. Il test resta mutation-pinned come gia' registrato sopra: `self.applied = []` iniettato in `uninstall` su copia sotto /tmp lo fa diventare rosso.

Nota sullo stato della suite COMPLETA, per onesta' della misura: `pytest tests/ -q` da' oggi `3 failed, 642 passed`, e i tre fallimenti sono tutti in `tests/test_docs_integrity.py`, che non e' mio. Sono inoltre DIVERSI da quelli riportati dall'orchestrator poco fa (lui vedeva un collection error sull'unpack di `_SIGNATURES`; quello non c'e' piu', al suo posto ci sono tre fallimenti su `index_named_fts_message`). Il file e' cambiato ancora sotto di noi mentre l'altro agente lavora su SQL-01. Nessuno dei tre tocca `applied` ne' `patcher.py`.

**PROPOSTO PER LA CHIUSURA, INSIEME A TASK-5, 2026-09-17.** Tutti e quattro i criteri sono ora spuntati e ognuno ha la sua prova registrata sopra: #1 il campo e' nominato storico nella docstring di `Patcher.uninstall` e nel commento di `_patch`; #2 nella formulazione autorizzata, con la prova grep della forma attributiva; #3 `test_applied_is_a_history_not_a_live_inventory`, verde e mutation-pinned; #4 nessun consumatore di produzione, provato dallo stesso grep.

Lo stato resta **To Do** e NON viene mosso da me. L'autorizzazione ricevuta copriva la correzione della premessa, la riformulazione di AC2, l'aggiunta delle prove e la proposta di chiusura; non copriva un cambio di stato, e la regola in vigore e' 'nessuna chiusura autonoma'. Il task e' pronto: chiuderlo e' una decisione dell'orchestrator, da prendere contestualmente a TASK-5 perche' le due cose stanno in piedi sulla stessa decisione di contratto e sulle stesse misure.

Dipendenza da dichiarare prima della chiusura congiunta: la verifica finale di TASK-5 e' bloccata dall'orchestrator in attesa che la suite completa torni coerente, oggi rossa per lavoro altrui su `tests/test_docs_integrity.py`. Le prove di QUESTO task non dipendono da quel file e restano valide sullo stato corrente, ma se si vuole una singola misura pulita a copertura di entrambi i task occorre aspettare che SQL-01 si stabilizzi.

**CHIUSO il 2026-09-17, APPROVED dall'orchestrator.** Prova di chiusura verificata in modo indipendente da me prima di chiudere, non accettata sulla parola: `src/pyteman/patcher.py` sha256 `272b84d1...`, `tests/test_activation_atomic.py` `10cf431b...`, `docs/rules.md` `c5948fa4...`, identici a quelli congelati; i due file congelati da TASK-7 (`rules.py` `4154bd89...`, `targets.py` `a766eebb...`) invariati; suite COMPLETA `662 passed in 5.41s`, zero fallimenti. I fallimenti su `tests/test_docs_integrity.py` visti negli snapshot precedenti sono stati chiusi dal proprietario di SQL-01 e la serie converge come previsto.

Nessuna modifica di codice in chiusura, come autorizzato: solo operazione di tracker.

**Titolo rinominato** da "uninstall() svuota _wrapped ma non applied: dopo un uninstall il patcher elenca strumentazione non piu' installata" a "Documentare applied come storico delle patch", per ordine dell'orchestrator e nella stessa operazione. Il titolo vecchio era stantio su due fronti: descriveva un comportamento di `_wrapped` che TASK-5 ha cambiato (le voci rifiutate vengono trattenute per il retry, quindi non c'e' piu' uno svuotamento incondizionato) e inquadrava il task come un difetto da riparare, mentre l'esito e' stato una decisione di contratto piu' la sua documentazione. Il nuovo titolo dice cosa e' stato effettivamente fatto.
<!-- SECTION:NOTES:END -->
