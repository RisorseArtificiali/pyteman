---
id: TASK-43
title: API-05. Base comune degli errori pyteman e rilevazione duplicati unica
status: To Do
assignee: []
created_date: '2026-09-16 13:46'
updated_date: '2026-09-17 03:10'
labels:
  - audit-2026-09-16
  - review-followup
  - reuse
  - api
dependencies: []
references:
  - src/pyteman/__init__.py
  - src/pyteman/rules.py
  - src/pyteman/runner/matrix.py
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Emersa dalla review Reuse del lavoro RUN-01 (TASK-19), 2026-09-16.

Due gerarchie di errore scollegate, verificate il 2026-09-16: rules.py definisce RuleError(Exception), runner/matrix.py definisce MatrixIdentityError(RuntimeError). Basi diverse per errori della stessa natura, cioe pyteman che rifiuta un input o uno stato invece di eseguirlo. Un chiamante che voglia distinguere un rifiuto di pyteman da un guasto dell interprete deve oggi importare entrambe le classi da due moduli e non ha comunque modo di catturare la categoria. src/pyteman/__init__.py e praticamente vuoto (1 riga) ed e la sede naturale per una base PytemanError.

Seconda meta della stessa review: la rilevazione degli id duplicati esiste in due punti. rules.py la fa con un set seen_ids attorno alle righe 250-265 (riferimento per simbolo, non per riga: quel file e in modifica concorrente), matrix.py la fa con collections.Counter in _check_duplicate_ids. Stessa regola, cioe un identificatore che indirizza una riga o una regola non puo ripetersi, con due implementazioni e due messaggi diversi.

Precondizione di coordinamento: rules.py e sotto ownership di un altro agente nell audit 2026-09-16. Questo task va schedulato quando quel lavoro e chiuso, non in parallelo.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 src/pyteman/__init__.py definisce PytemanError e sia RuleError sia MatrixIdentityError ne derivano, cosi un chiamante cattura la categoria con un solo except
- [ ] #2 Una sola funzione condivisa rileva gli identificatori duplicati e viene usata sia da rules.py sia da matrix.py, con un messaggio che nomina gli id ripetuti
- [ ] #3 I test esistenti che catturano RuleError e MatrixIdentityError per nome continuano a passare senza modifiche
- [ ] #4 Il cambio di base di MatrixIdentityError da RuntimeError a PytemanError e verificato non rompere nessun except RuntimeError esistente nel repository
- [ ] #5 Il punto di estrazione e gia preparato: durante RUN-01 il controllo dei duplicati e stato scorporato da _check_cell_ids in una funzione propria _check_duplicate_ids in src/pyteman/runner/matrix.py, perche e l'unico controllo che guarda l'insieme invece della singola cella. E' quella funzione, non il blocco dentro il ciclo, che va unificata con l'equivalente di rules.py
- [ ] #6 MatrixArtifactError (aggiunta da TASK-20/RUN-02 in runner/matrix.py) deriva anch'essa da PytemanError: il re-parenting copre tre classi, non due
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Aggiornamento del perimetro dalla review Altitude di TASK-20 (RUN-02), 2026-09-16.

TASK-20 ha introdotto una terza classe di errore, MatrixArtifactError, in src/pyteman/runner/matrix.py. Deriva da RuntimeError come MatrixIdentityError e non condivide con essa nessuna base piu stretta. La review ha rilevato che questo allarga questo task invece di lasciarlo invariato: un chiamante che voglia catturare 'pyteman ha rifiutato il run' deve ora importare due nomi da matrix.py piu RuleError da rules.py, e l'unica cattura comune resta RuntimeError, che e troppo larga.

La review proponeva di introdurre subito una base intermedia MatrixError(RuntimeError) dentro matrix.py e farne derivare entrambe, per lasciare a questo task un solo re-parenting. Non l'ho fatto: TASK-43 e fuori dal perimetro assegnato a TASK-20 e la gerarchia delle eccezioni e esattamente la sua materia. Registrato qui invece di applicarlo, cosi la proposta non si perde.

Due strade possibili quando questo task verra eseguito, da decidere allora: una base unica PytemanError da cui derivano tutte e tre, oppure PytemanError con un livello intermedio MatrixError per i due errori del runner. La seconda ha senso solo se emerge un chiamante che vuole distinguere 'errore del runner' da 'errore delle regole' senza elencare le classi.

Distinzione fra le due classi del runner, per chi eseguira il lavoro: MatrixIdentityError dice qualcosa sulla matrice (celle, id, definizioni), MatrixArtifactError dice qualcosa sul filesystem (la radice degli artefatti non e dove dice di essere) e viene alzata prima che il db venga aperto, quindi porta un contratto diverso sullo stato parziale lasciato indietro.

Ampliamento di scope dalla review /simplify di RT-02 (TASK-2), 2026-09-17. Reperto degli agenti reuse e altitude, registrato qui invece che come task nuovo perche' e' lo stesso lavoro visto da una terza porta.

RT-02 ha aggiunto a patcher.py un preflight sui duplicati di id per la porta PROGRAMMATICA, cioe' Patcher(seq) costruito a mano senza passare dal loader YAML. Serviva: il contratto di TASK-2 lo richiedeva esplicitamente ('per API programmatica valida duplicazione id in preflight prima di mutare'). L'effetto collaterale e' che ora la stessa frase di errore sui duplicati esiste in TRE punti invece di due: patcher.py intorno a riga 572, rules.py intorno a riga 306, e un terzo matcher nei test intorno a tests/test_activation_atomic.py:2177.

Questo task chiede gia' (AC #2) una sola funzione condivisa per rilevare gli id duplicati, usata sia da rules.py sia da matrix.py. Il reperto aggiunge un terzo consumatore a quell'elenco: patcher.py. Chi esegue includa la porta programmatica del Patcher fra i chiamanti della funzione condivisa, invece di lasciare il preflight come copia locale.

Suggerimento dall'agente altitude, non vincolante: la forma giusta potrebbe non essere una funzione che risponde solo sui duplicati ma una validate_rules(seq) che entrambe le porte attraversano, dentro cui i duplicati sono uno dei controlli. Il motivo e' che RT-02 ha portato alla luce un SECONDO controllo che oggi vive solo al load e non sulla porta programmatica, cioe' la validazione di event contro l'insieme chiuso (vedi TASK-114). Due cerotti puntuali affiancati sono il segnale che manca la porta unica; se si sceglie la funzione singola sui soli duplicati, va detto perche'.

Questo task resta bloccato sul proprietario di rules.py come gia' registrato; la nota serve solo perche' il reperto non si perda.
<!-- SECTION:NOTES:END -->
