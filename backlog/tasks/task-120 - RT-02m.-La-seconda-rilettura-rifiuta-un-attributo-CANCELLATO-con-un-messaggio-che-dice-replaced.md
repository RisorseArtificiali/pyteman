---
id: TASK-120
title: >-
  RT-02m. La seconda rilettura rifiuta un attributo CANCELLATO con un messaggio
  che dice "replaced"
status: Done
assignee: []
created_date: '2026-09-17 03:58'
updated_date: '2026-09-17 04:41'
labels:
  - patcher
  - diagnostics
  - docs
  - rt-02
dependencies: []
references:
  - src/pyteman/patcher.py
  - README.md
  - docs/rules.md
  - tests/test_activation_atomic.py
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Trovato dal gate /simplify sulla tranche RT-02 (2026-09-17), riportato come contraddizione commento/codice e non come bug.

In pass 2 la seconda rilettura faceva `settled = getattr(slot.container, slot.name, _ABSENT)` e confrontava con `slot.original`. Se la chiamata rientrante aveva CANCELLATO l'attributo invece di sostituirlo, `settled` valeva `_ABSENT`, il confronto `settled is not slot.original` era vero, `_live_dispatcher_owner(_ABSENT)` restituiva `None` perche' e' un semplice getattr di `_pyteman_owner`, e lo slot veniva rifiutato con `SlotOwnershipError` sotto il messaggio "was replaced while its dispatcher was being built".

Due problemi distinti:

1. Il messaggio era impreciso. Diceva "replaced" per un caso che e' una cancellazione. Chi legge la diagnostica va a cercare il valore che avrebbe sostituito l'originale e non ne trova nessuno.

2. Il commento a patcher.py, sulla PRIMA rilettura, dice "A point that is not there is skipped rather than refused, and that promise holds here too". Lo stesso contratto e' affermato in README.md:35-44. Alla prima rilettura l'assenza veniva effettivamente saltata (`if live is _ABSENT: continue`), alla seconda veniva rifiutata. Il commento diceva al lettore che la promessa copre entrambe le letture, e non era piu' vero.

CONCLUSIONE ADOTTATA (2026-09-17), che ROVESCIA la valutazione preliminare registrata qui in origine. La valutazione di partenza diceva di tenere il rifiuto e allargare il messaggio, sul ragionamento che alla seconda lettura l'attributo c'era ed e' stato rimosso, quindi saltare in silenzio avrebbe perso le regole di quello slot. Il ragionamento e' stato scartato leggendo cosa il rifiuto fa davvero: `SlotOwnershipError` non salta lo slot, propaga e ABORTISCE la patch dell'intero modulo con rollback, quindi il prezzo della cancellazione di un singolo attributo sarebbe stato la perdita di TUTTE le regole del modulo, non di quelle di uno slot. E il caso non e' nemmeno esotico: la costruzione del dispatcher esegue codice bersaglio, quindi una property o un `__getattr__` di modulo puo' cancellare l'attributo da dentro la finestra senza alcuna concorrenza.

Al secondo punto di lettura saltare non e' soltanto coerente con la prima, e' obbligatorio: la `setattr` che seguirebbe RESUSCITEREBBE un nome che il programma bersaglio ha appena rimosso, cioe' pyteman aggiungerebbe al bersaglio un attributo che il bersaglio non ha. Le altre regole del modulo restano installate e la regola sullo slot sparito non compare ne' in `applied` ne' nel ledger, che e' esattamente il contratto gia' documentato per un punto assente.

Il messaggio "replaced" non e' stato allargato perche' non viene piu' emesso per la cancellazione: quel ramo ora fa `continue`. Il rifiuto sopravvive sul solo caso che lo merita, uno slot preso da un ALTRO Patcher, con diagnostica propria.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 I commenti su entrambe le riletture dichiarano la stessa promessa skip-invece-di-rifiuto, e quello sulla seconda dice perche' li' saltare non e' solo coerente ma obbligatorio (la scrittura resusciterebbe il nome)
- [x] #2 docs/rules.md e README concordano con il comportamento effettivo su assenza alla prima lettura e rimozione alla seconda
- [x] #3 L'assenza dell'attributo alla seconda rilettura e' saltata e non rifiutata, come alla prima, e nessuna altra regola del modulo cade per causa sua
- [x] #4 Un test di regressione raggiunge il ramo in cui la chiamata rientrante cancella l'attributo, e asserisce che lo slot e' saltato, che il nome non viene resuscitato, che applied e ledger non lo nominano e che le altre regole del modulo restano installate
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Conclusione ribaltata rispetto alla valutazione preliminare, sull'evidenza. La valutazione iniziale diceva di conservare il rifiuto alla seconda rilettura. L'ho scartata dopo aver letto che cosa fa davvero quel rifiuto: `SlotOwnershipError` non salta lo slot, si propaga e fa abortire la patch dell'intero modulo con rollback. Un solo attributo cancellato sotto i piedi sarebbe percio' costato tutte le regole del modulo. La ragione indipendente e piu' forte e' che il `setattr` successivo avrebbe rimesso al suo posto un nome che il programma bersaglio aveva appena tolto, il che viola la promessa che il README e docs/rules.md danno al lettore.

Verificato sugli artefatti reali prima della transizione, non sulla memoria del lavoro fatto: i commenti a patcher.py:754-756 e 808-813, il ramo `continue` alla :808, la promessa in README.md:35-44 e in docs/rules.md:317-318, e il test di regressione `test_an_attribute_deleted_while_its_dispatcher_was_built_is_skipped` a tests/test_activation_atomic.py:2807.

L'AC #1 e' stato riformulato prima di essere spuntato. Nella stesura originale chiedeva che il commento spiegasse perche' le due letture rispondono diversamente, clausola scritta dando per scontato che la correzione avrebbe conservato il rifiuto. La correzione effettiva fa rispondere le due letture allo stesso modo, quindi quel criterio era insoddisfacibile dal codice costruito. L'ho allineato a cio' che il codice fa, e lo dico qui invece di lasciare che sembri soddisfatto come scritto.

Suite completa: PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /tmp/pyteman-audit-env-OOeElF/bin/python -m pytest tests/ -q dava 720 passed in 3.59s.

Gate /simplify rieseguito in questa sessione dopo la compattazione del contesto, perche' la precedente esecuzione era anteriore alle modifiche che contano qui: la rimozione del campo `original` da `_Slot`, il nuovo test sul rifiuto e le riscritture dei commenti sono tutte atterrate dopo. Le segnalazioni emerse sono state smistate: TASK-125, TASK-126, TASK-127 e TASK-128 per quelle fuori dallo scopo di questo task, e una sezione nel piano di TASK-2 per quelle che cadono nelle regioni che TASK-2 riscrive.
<!-- SECTION:NOTES:END -->
