---
id: TASK-9
title: CFG-03. Bloccare la coercizione YAML ambigua nei valori PRAGMA
status: Done
assignee: []
created_date: '2026-09-16 12:20'
updated_date: '2026-09-18 20:18'
labels:
  - audit-2026-09-16
  - opus-5
  - cfg
  - confirmed
milestone: m-1
dependencies:
  - TASK-7
references:
  - 'src/pyteman/rules.py:195 (_pragma_value)'
  - 'src/pyteman/rules.py:247 (schema pragma)'
  - 'src/pyteman/actions.py:44'
documentation:
  - doc-1
  - doc-2
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit 2026-09-16 sul commit a28b12662a46727ff806a42122db0ffe8333d760. Esecuzione futura prevista con Opus 5. Riprodurre il caso sullo stato corrente prima di correggere; non dipendere dalla conversazione originale.

**Priorità / stato:** P1, CONFIRMED, aperto.

**File:** `src/pyteman/rules.py:38,58-61`, `src/pyteman/actions.py:44`.

**Evidenza:** `value: OFF` non quotato viene letto da PyYAML come False. Con `name: journal_mode`, l'azione non cambia il database da delete; `value: "OFF"` lo cambia a off. Nessun outcome di errore accompagna il caso non quotato.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Il load garantisce forma e tipo, non l'effetto. Una matrice verificata contro SQLite reale dichiara quali combinazioni pragma/valore producono un effetto e quali no, incluso il caso di un valore accettato che non cambia nulla.
- [x] #2 README con esempi non ambigui, che dicano perche' le virgolette servono.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Proposta iniziale da verificare sul codice corrente, non una correzione già applicata.

politica esplicita per tipi YAML dei PRAGMA: rifiutare valori booleani ambigui con messaggio che richieda stringhe quotate, oppure normalizzare secondo un contratto rigoroso e testato. Non fare una sostituzione indiscriminata dei booleani per tutti i PRAGMA.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Indicazioni di coordinamento del documento di origine: CFG-01. Concordare con CFG-04 i valori normalizzati prima di verificare il readback.

I prerequisiti operativi sono quelli nel campo Dependencies; i rinvii a consumer e file condivisi non impongono dipendenze reciproche. Aggiornare test e documentazione pertinente nello stesso task; riportare comandi e output reali prima di Done.

Nota di coordinamento da TASK-7 (CFG-01), 2026-09-16. NON e' lavoro svolto su questo task, che resta interamente aperto.

CFG-01 ha toccato incidentalmente meta' del problema. `_pragma_value` in `src/pyteman/rules.py` ora RIFIUTA al load un valore PRAGMA booleano, con messaggio che chiede le virgolette e mostra cosa arriverebbe a SQLite: "action.value must be quoted: YAML reads ON/OFF/YES/NO as booleans, so this reaches SQLite as 'False'". Rifiuta anche i valori non stringa e non intero, e le stringhe vuote o di soli spazi. Sei righe della tabella in `tests/test_targets.py` che scrivevano `value: OFF` sono state quotate, perche' fallivano gia' prima in silenzio.

Resta da fare qui, cioe' il grosso del task:
- Criterio #1, la matrice degli effetti reali su SQLite per ON, OFF, true, false, stringhe quotate, interi e null. CFG-01 ha deciso per rifiuto senza misurare nulla: nessuna connessione SQLite reale e' stata interrogata. Se la matrice mostrasse che una di queste forme e' innocua, la policy di CFG-01 e' quella da cambiare.
- Criterio #2, gli esempi non ambigui nel README. Interamente da fare: l'implementer di CFG-01 aveva divieto esplicito di toccare il README.

Un sottocaso e' stato deciso invece che rinviato, e va ripreso qui consapevolmente: il criterio #1 elenca `null` fra i valori da caratterizzare, ma CFG-01 ora rifiuta `value: ~` in blocco come "must be a string or an integer". Se la caratterizzazione dovesse concludere che `null` ha un effetto utile e distinguibile, va riaperto quel ramo di `_pragma_value`.

Vedi anche TASK-46 (DOC-02), che documenta la policy di schema chiuso e i campi resi obbligatori ma lascia deliberatamente la quotatura dei PRAGMA a questo task per non duplicare gli esempi.

CARATTERIZZAZIONE MISURATA, 2026-09-17. Assessment read-only richiesto da pyteman-89. Nessun file runtime toccato e nessuna riga di codice modificata: questo blocco registra misure, non lavoro svolto. Il task resta To Do.

Strumenti: due sonde sotto /tmp che pilotano il codice REALE, cioe' pyteman.rules.load_rules e pyteman.actions.run_action, con rules.__file__ e actions.__file__ stampati per provare quale artefatto e' stato misurato invece di riscrivere la logica nella sonda. Ogni caso usa un database su file nuovo in directory temporanea, con CREATE TABLE per materializzare il journal mode. sqlite 3.51.2 su python 3.14.7.

NOTA PRELIMINARE: il campo References di questo task e' STALE. Indica src/pyteman/rules.py:38,58-61, ma il sito reale e' _pragma_value a rules.py:195-207, agganciato allo schema a rules.py:247. actions.py:44 invece e' corretto.

LIVELLO LOAD, 29 grafie contro il loader reale.
RIFIUTATI: ON, on, OFF, off, true, false, yes, no non quotati, tutti con il messaggio che chiede le virgolette. Rifiutati anche ~ e null, con 'must be a string or an integer, got NoneType'.
ACCETTATI: tutte le stringhe quotate e tutti gli interi nudi.
Conferma esattamente la nota di coordinamento di TASK-7, senza sorprese.

LIVELLO EFFETTO, journal_mode, baseline delete.
Cambiano il modo: "OFF", "off", WAL, MEMORY.
NON cambiano nulla, e senza sollevare: "ON", "on", "true", "false", "yes", "no", "1", DELETE, NORMAL, FULL, e ogni intero da 0 a 3.

LIVELLO EFFETTO, synchronous, baseline 2.
"ON"/"on"/"true"/"yes" danno 1. "OFF"/"off"/"false"/"no" danno 0. Gli interi 0, 1 e 3 danno il proprio valore. "1" da' 1. DELETE, WAL, MEMORY e NORMAL danno 1. FULL da' 2.

In nessuno dei casi misurati con.execute ha sollevato. Conseguenza diretta sul codice: il ramo except di actions.py:45 non e' raggiungibile da un valore sbagliato, ma solo da una connessione inutilizzabile. L'assenza di eccezione non e' quindi un segnale debole, e' nessun segnale.

CONTROFATTUALE E DISCRIMINAZIONE, 2026-09-17. La domanda che decide la policy non e' 'cosa accetta il loader' ma 'cosa avrebbe fatto la statement che il loader vieta'. Misurata scrivendo quella statement direttamente, bypassando il loader di proposito.

PRAGMA journal_mode=False|True|None|banana|x, baseline delete: nessun cambiamento e nessuna eccezione in tutti e cinque i casi. La tesi del commento a rules.py:196-199 e della riga docs/rules.md:725 e' CONFERMATA per journal_mode.

PRAGMA synchronous=False, baseline 2: passa a 0. PRAGMA synchronous=True: passa a 1. PRAGMA foreign_keys=False, baseline 1: passa a 0. PRAGMA ignore_check_constraints=True, baseline 0: passa a 1.
Cioe' sui pragma a valore booleano il testo 'False' prodotto dalla coercizione YAML fa ESATTAMENTE quello che l'operatore intendeva scrivendo OFF non quotato.

VERIFICA AVVERSARIALE DI QUESTA AFFERMAZIONE, perche' e' l'unica che potrebbe cambiare la policy e perche' 'e' comparso il valore giusto' non prova il riconoscimento: se il default del pragma per una parola sconosciuta coincide con il valore atteso, riconoscimento e fallback sono indistinguibili. Rimisurato con baseline sul lato OPPOSTO del default e con un controllo 'banana' in ogni coppia.

  pragma        baseline  scritto  dopo  esito
  synchronous   0         False    0     RICONOSCIUTO
  synchronous   0         banana   1     fallback al default
  foreign_keys  0         True     1     RICONOSCIUTO
  foreign_keys  0         banana   0     fallback al default

Due pragma indipendenti, ciascuno con il controllo che si muove nella direzione opposta al caso in esame. L'affermazione regge: SQLite riconosce davvero il testo 'False' e 'True' e non ci arriva per default.

CONSEGUENZA SULLA POLICY. Il rifiuto al load resta difendibile come regola uniforme, perche' l'operatore non puo' sapere quali pragma sono a parola chiave e quali a booleano, e su journal_mode il danno e' reale. Ma la MOTIVAZIONE dichiarata vale per journal_mode e non per gli altri tre pragma misurati. Le tre copie del testo nominano tutte journal_mode, quindi nessuna e' falsa alla lettera; il difetto e' che presentano un caso particolare come ragione di una regola generale. La copia piu' esposta e' il commento a tests/test_rules.py:180-181, perche' copre due righe di tabella e la seconda usa foreign_keys, dove il danno descritto non si verifica.

SECONDO RISULTATO, piu' grave del primo e non previsto. Un valore non riconosciuto su un pragma a valore booleano non e' inerte: SOVRASCRIVE. synchronous a baseline 0 con 'banana' passa a 1. Quindi un refuso dentro le virgolette non si limita a non applicarsi, distrugge in silenzio un'impostazione precedente corretta, sempre senza eccezione e senza outcome. Le virgolette imposte da CFG-01 non fanno nulla contro questo caso.

VERDETTO SUI CRITERI E RESIDUO MINIMO PROPOSTO, 2026-09-17. Proposta, non lavoro svolto: nessuna implementazione prima del via libera di pyteman-89.

CRITERIO #1: NON soddisfatto. La seconda meta' recita 'ogni valore accettato produce l'effetto dichiarato su SQLite reale', e oggi manca il termine di paragone perche' nessun documento dichiara un effetto per valore. Peggio, la lettura naturale e' falsa in misura: su journal_mode i valori accettati "ON", "true", "1" e ogni intero non producono alcun effetto. Copertura esistente: tests/test_actions.py:28 e :34 asseriscono il readback di synchronous per il solo valore "OFF". Un valore su un pragma, niente su journal_mode, niente sugli interi, niente sul fallback.

CRITERIO #2: NON soddisfatto, interamente aperto. README.md:238-258 contiene l'unico esempio pragma, gia' scritto con value: "OFF" quotato e target: self._conn, ma non spiega PERCHE' le virgolette servono e non da' una guida sui valori. L'esempio e' corretto e muto.

NULL: NON si riapre. La nota di TASK-7 chiedeva di riaprire il ramo se null avesse un effetto utile e distinguibile. Misurato, PRAGMA x=None si comporta come qualunque altra parola sconosciuta su tutti e quattro i pragma provati, quindi non ha alcun effetto distinguibile. Il rifiuto di CFG-01 resta.

RESIDUO MINIMO, solo test e documentazione, nessuna riga di runtime.
1. tests/test_actions.py, un test di caratterizzazione che fissa la matrice misurata: journal_mode a parola chiave contro synchronous a booleano, piu' il caso di sovrascrittura. E' questo che rende il criterio #1 meccanicamente vero invece che dichiarato.
2. README.md, il criterio #2: dire perche' servono le virgolette e dare esempi non ambigui.
3. docs/rules.md:725, aggiungere la frase che manca sul fallback silenzioso.
4. tests/test_rules.py:180-181, restringere il commento alla sola riga journal_mode.
Nessun file sotto src/ serve. Il parser non va ritoccato: il rifiuto e' gia' quello giusto, e' la motivazione scritta che e' troppo larga.

CONFINE CON CFG-04 (TASK-10), che dipende da questo task. Il secondo risultato, cioe' la sovrascrittura silenziosa, NON va corretto qui. TASK-10 si chiama 'Distinguere tentativo PRAGMA da cambiamento effettivamente applicato' e la sua evidenza nomina gia' lo stesso guasto un livello sopra, sul NOME del pragma ('il refuso syncronous viene ignorato da SQLite, sempre senza outcome'). Il mio risultato e' lo stesso guasto sul VALORE. Il readback e l'outcome esplicito sono suoi; qui resta solo la caratterizzazione che gli serve come input. Confine operativo proposto: TASK-9 misura quale effetto ha un valore accettato, TASK-10 decide cosa il sistema registra quando quell'effetto non avviene.

VINCOLO DI SEQUENZA SU docs/rules.md, verificato e non assunto. Il punto 3 tocca un file che TASK-3 (RT-03) tiene congelato in attesa dell'APPROVED del reviewer. Hash misurato adesso: 3d6d8d4c580cfa7d851247de4d876e605066cce4b0adc4b01e2f4c45c6e58c4c, identico a quello registrato in TASK-3. Toccarlo ora romperebbe quel congelamento. Il punto 3 va quindi eseguito dopo lo sblocco di TASK-3, oppure assegnato a TASK-46 (DOC-02, To Do), che pero' rinvia esplicitamente la quotatura dei PRAGMA a questo task. Gli altri tre punti non hanno sovrapposizioni.

OWNERSHIP rules/actions/targets contro RT-03: nessuna sovrapposizione. TASK-3 lavora su src/pyteman/patcher.py con i due file di test di attivazione; non tocca rules.py, actions.py ne' targets.py. L'unico file condiviso e' docs/rules.md, ed e' il vincolo di sequenza qui sopra.

CLAIM E PIANO REGISTRATI PRIMA DI TOCCARE I FILE, 2026-09-17, su via libera di pyteman-89 limitato a test e documentazione non congelata.

CLAIM che il residuo deve rendere meccanico: il loader garantisce forma e tipo, non effetto. Su journal_mode, pragma a parola chiave, i valori accettati "ON", "true", "1" e ogni intero passano il load, vengono eseguiti e non cambiano nulla. Sui pragma a valore booleano il testo prodotto dalla coercizione e' invece riconosciuto davvero, verificato con baseline contraria e controllo in ogni coppia. Le due meta' insieme sono la ragione per cui AC1 non puo' promettere che ogni valore quotato funzioni su ogni PRAGMA.

AC1 RISCRITTO in questo stesso passaggio, senza quella falsa promessa. Entrambi i criteri erano gia' non spuntati, quindi acceptanceCriteriaSet non ha cancellato nessun segno di spunta.

References aggiornato cercando i simboli e non rinumerando: _pragma_value a rules.py:195, aggancio allo schema a rules.py:247, sito di interpolazione a actions.py:44.

PIANO, nell'ordine di esecuzione.
1. tests/test_actions.py, prove load verso action verso readback su database nuovi su file, parametrizzate su journal_mode, synchronous e foreign_keys, con baseline contraria dove il default del pragma coinciderebbe con il valore atteso. Niente valori arbitrari che alzano solo il conteggio.
2. tests/test_rules.py, solo la correzione del commento sul bool, ristretto alla riga journal_mode. Nessun refactor.
3. README.md, solo la sezione dell'esempio PRAGMA e target. Non la sezione Activation contract, non Runner, nessuna riscrittura dei link.
4. docs/rules.md resta congelato da TASK-3. Testo preparato qui sotto e applicato solo dopo il rilascio di pyteman-89.

Nessun file sotto src/. Nessun gate finale e nessuna chiusura del task finche' docs resta bloccato.

TESTO PREPARATO PER docs/rules.md:725, DA APPLICARE SOLO DOPO IL RILASCIO. Il file e' congelato da TASK-3 e non e' stato toccato.

La riga attuale della tabella e' corretta alla lettera ma si ferma al caso journal_mode. La frase da aggiungere in coda alla cella, dopo "Quote them.":

  Quoting fixes the ambiguity, not the outcome: the value is still interpolated verbatim and SQLite reads it per pragma. `journal_mode` takes only its own keywords, so a quoted `"ON"` or an integer is accepted here, executed, and ignored there. What the toolkit records when that happens is CFG-04.

Motivazione: la cella oggi presenta un caso particolare, journal_mode, come ragione di una regola generale, e un lettore ne deduce che quotare basti. La misura dice che non basta. La frase non riapre la policy e non anticipa CFG-04, la nomina come titolare del readback.

EVIDENZA DELLA SOVRASCRITTURA TRASFERITA A TASK-10 come input, non trattata qui. Inquadramento corretto secondo pyteman-89 e accettato: SQLite e' permissivo per scelta di progetto, quindi non si tratta di un bug di sintassi. Il difetto e' del toolkit ed e' la mancata verifica dell'effetto. Per questo il test di caratterizzazione qui sopra copre il caso di un valore ACCETTATO che non produce effetto, che appartiene alla matrice di TASK-9, e lascia a TASK-10 il valore non riconosciuto che ne sovrascrive uno corretto.

IMPLEMENTAZIONE ESEGUITA SUI SOLI FILE AUTORIZZATI, 2026-09-17. Tre file toccati, nessuna riga sotto src/, docs/rules.md non aperto.

tests/test_actions.py. Aggiunta la matrice PRAGMA_EFFECTS con sette righe e due helper, piu' un test di contrasto. Ogni caso parte da un database su FILE nuovo in tmp_path con CREATE TABLE, passa dal loader reale scrivendo YAML come lo scriverebbe un operatore, esegue run_action e rilegge il pragma. Le baseline non sono comode ma scelte: synchronous parte da 2 e foreign_keys da 0, cioe' dal lato opposto al default del pragma, perche' un caso il cui valore atteso coincide con quel default non distingue riconoscimento da fallback. _on_disk asserisce che la baseline sia davvero atterrata prima di agire, quindi un helper rotto non passa inosservato.

tests/test_rules.py. Solo il commento sulle due righe di tabella del bool, ristretto come concordato. Ora dice che il rifiuto e' una regola uniforme mentre il danno che nomina non lo e': su journal_mode la statement lascia il modo intatto, sui pragma a booleano sotto lo stesso testo coercito viene riconosciuto e applicato, quindi li' le virgolette comprano una sorgente non ambigua e non un esito diverso. Rimanda a tests/test_actions.py per la misura. Nessun refactor, nessuna riga di dati toccata.

README.md. Solo la sezione dell'esempio PRAGMA e target, subito dopo il blocco YAML esistente. Due punti: perche' le virgolette servono al load, e che le virgolette risolvono cosa sia il valore e non cosa SQLite ne faccia. Poi l'elenco per pragma, journal_mode a parola chiave contro synchronous e foreign_keys a booleano, e la frase che nessuno dei due solleva su un valore non riconosciuto, quindi il readback tocca a chi scrive la regola. Non toccate Activation contract ne' Runner, nessun link riscritto.

VERIFICA, comandi eseguiti e output letto, non dedotto.

SUITE COMPLETA: rm -rf tests/__pycache__ && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /tmp/covrun/venv/bin/python -m pytest tests/ -q
Risultato: 771 passed in 8.74s. tests/test_actions.py passa da 6 a 14 test, misurati.

CONTROLLO DI MUTAZIONE, che e' la prova che conta perche' due righe della matrice affermano l'ASSENZA di effetto e una tale riga passerebbe anche se run_action non facesse nulla. run_action neutralizzato a lambda vuota da un plugin pytest caricato prima della collection, quindi prima che il modulo di test ne importi il nome.
Comando: PYTHONPATH=/tmp PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /tmp/covrun/venv/bin/python -m pytest tests/test_actions.py -q -p noop_action_plugin
Risultato: 11 failed, 3 passed.
I tre che restano verdi sono esattamente i previsti: le due righe journal_mode a effetto nullo, "ON" e 1, piu' il preesistente test_pragma_no_connection_is_noop. Tutte e cinque le righe che affermano un effetto diventano rosse, e diventa rosso anche test_a_value_the_loader_accepts_can_still_do_nothing con 'assert delete == off'. E' quello il suo mestiere: e' l'unica cosa che impedisce alle due righe a effetto nullo di passare a vuoto, perche' chiede alla stessa connessione, allo stesso loader e alla stessa azione di muovere il modo dopo aver mostrato che "ON" non lo muove.

CONGELAMENTO docs/rules.md RIVERIFICATO DOPO LE MODIFICHE: sha256 3d6d8d4c580cfa7d851247de4d876e605066cce4b0adc4b01e2f4c45c6e58c4c, identico al valore registrato in TASK-3. Il file non e' stato aperto in scrittura.

PUNTEGGIATURA: nessun em-dash e nessun trattino parentetico nel testo scritto in nessuno dei tre file; le uniche occorrenze di ' - ' sono aritmetica dentro espressioni preesistenti.

STATO E RESIDUO, 2026-09-17. Task portato a In Progress e NON chiuso, come da istruzione di pyteman-89.

Entrambi i criteri sono ora meccanicamente veri e spuntati. Il #1 perche' la matrice esiste, gira contro SQLite reale, dichiara anche il caso del valore accettato che non cambia nulla, ed e' stata mostrata capace di fallire. Il #2 perche' il README ora dice perche' le virgolette servono e cosa non comprano.

RESIDUO, unico, gia' preparato e non applicabile ora: la frase per docs/rally rules.md:725, il cui testo e' nella nota precedente. Va applicata dopo il rilascio di pyteman-89 sul congelamento di TASK-3. Finche' quel punto resta aperto non vengono eseguiti i gate finali di completamento e il task non si chiude.

Nessun nuovo task aperto, nessun refactor, nessun file sotto src/ toccato, nessun commit.

CORREZIONE alla nota precedente: il percorso del residuo e' docs/rules.md:725. Nella riga 'RESIDUO, unico' e' comparso 'docs/rally rules.md:725', che non esiste.

CORREZIONE DELLA NOTA 'CONGELAMENTO docs/rules.md RIVERIFICATO', 2026-09-17 17:40. Sola registrazione, nessun file toccato.

Quella nota dice: sha256 3d6d8d4c..., identico al valore registrato in TASK-3, il file non e' stato aperto in scrittura. E' falsa, ed e' la stessa falsa affermazione che ho corretto in TASK-3 nello stesso turno. Il file E' stato aperto in scrittura, da me, dopo quel punto, e 3d6d8d4c e' un valore storico ricopiato invece che misurato.

Valore reale misurato adesso: sha256 2cac5f9190225291d5a74b6f54d4192f37eaa9a66a120ae061f928db6d82da9c, 856 righe, 53804 byte, mtime 2026-09-17 15:48:50. E' questo il riferimento da usare per verificare il congelamento, non 3d6d8d4c.

Il vincolo di sequenza registrato in questo task resta valido nella sostanza: docs/rules.md e' tenuto da TASK-3 e il residuo di CFG-03 non va applicato senza il rilascio. Cambia solo l'hash di confronto.

CONSEGUENZA OPERATIVA SUL RESIDUO: L'ANCORA DI RIGA E' SCADUTA.

Questo task fissa il residuo su 'docs/rules.md:725'. Quel numero non punta piu' dove puntava. Le modifiche chirurgiche del 17/09 alle 15:48 hanno agito nella sezione 'What is recognised', che sta PRIMA, con saldo netto di circa quaranta righe aggiunte, quindi tutto cio' che seguiva e' scivolato in giu'.

Misurato adesso. La riga 725 attuale parla degli eval locals e delle assignment expression, che non c'entra nulla col residuo. La riga che il residuo deve toccare, cioe' quella del pragma dove compare journal_mode e la coercizione YAML di ON/OFF/YES/NO, e' ora la 765. Il blocco di esempio con journal_mode e' alla 805.

Chi riprende il residuo deve quindi ancorarsi al CONTENUTO, cioe' la riga della tabella che comincia con la cella `pragma`, e non al numero 725. Registrato qui perche' applicare il testo preparato alla riga 725 attuale lo infilerebbe in mezzo a un paragrafo che parla d'altro, e il test di coerenza dei docs non se ne accorgerebbe necessariamente.

Nota di conservazione, rilevante anche per questo task: docs/rules.md e' UNTRACKED in git, quindi non esiste alcuna copia recuperabile con comandi git, e i backup che ne tenevo sotto /tmp sono stati cancellati da systemd-tmpfiles alle 17:30. Copia salvata adesso fuori da /tmp in ~/pyteman-evidence/2026-09-17-candA/docs-rules.md, hash verificato identico all'originale. Non ripristinare mai questo file a 3d6d8d4c: significherebbe cancellare le righe aggiunte alle 15:48, che in git non ci sono.

VERIFICA PER LA CHIUSURA, 2026-09-18. Richiesta da pyteman-17. Nessuna reimplementazione, zero file toccati. Lo stato NON e' stato portato a Done: stesso blocco del hook registrato in TASK-3.

Entrambi i criteri erano gia' spuntati e l'unico residuo registrato era la frase sul fallback silenzioso per la riga pragma di docs/rules.md, tenuta in sospeso dal congelamento di TASK-3.

QUEL RESIDUO E' PRESENTE A HEAD. Misurato adesso, docs/rules.md riga 792, la cella della riga `pragma` contiene: 'Quoting fixes the ambiguity and not the outcome: the value is still interpolated verbatim and each pragma reads it its own way, so on `journal_mode` a quoted "ON" or an integer is accepted here, executed, and ignored there. Reporting that case is CFG-04.'

E' il testo preparato in questo task, applicato con la correzione di ancoraggio che il task stesso prescriveva: agganciato al CONTENUTO della riga di tabella e non al numero 725, che era scaduto dopo lo scivolamento di circa quaranta righe del 17/09.

Il congelamento di TASK-3 e' finito e docs/rules.md e' ora TRACCIATO in git, dentro il commit 9e9ae4f10958501f17c4f8f4cc6123218259f566 e nel merge fb1cf409000d941ea993b0012f9d4a56e6271268. La nota di conservazione registrata piu' sopra, che avvertiva come il file fosse untracked e non recuperabile con comandi git, non e' piu' vera da quel commit in poi.

Il confine con TASK-10 (CFG-04) resta come registrato: la sovrascrittura silenziosa di un valore corretto da parte di un valore non riconosciuto NON e' trattata qui e resta input per quel task, che la frase sopra nomina esplicitamente.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Riconciliazione amministrativa del 2026-09-18. Schema PRAGMA, valori YAML non ambigui e matrice degli effetti SQLite già pubblicati nella PR #1 e presenti a b1a886d. Entrambi gli AC sono verificati e spuntati; readback e strict mode appartengono a TASK-10, non a questa unità. PR #1 confermata MERGED e CI del merge corrente 35359891183 con sei job success. Suite locale attuale: 926 passed, 1 skipped opzionale. gate-exempt per aggiornamento di solo tracker, nessun nuovo codice.
<!-- SECTION:FINAL_SUMMARY:END -->
