---
id: TASK-72
title: >-
  TEST-06. Duplicazioni e costo dei test RT-01: make_rule, oggetti ostili al
  rendering, subprocess fondibili
status: To Do
assignee: []
created_date: '2026-09-16 18:46'
updated_date: '2026-09-17 03:59'
labels:
  - test
  - opus-5
  - from-review
  - audit-2026-09-16
dependencies:
  - TASK-1
references:
  - tests/test_sitecustomize.py
  - tests/test_activation_atomic.py
  - tests/test_rules.py
  - tests/test_rule_contracts.py
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Emerso dalle review Reuse ed Efficiency del finale RT-01 (2026-09-16). Declinato dentro RT-01 per due ragioni distinte, entrambe di perimetro e non di merito.

**Duplicazione di make_rule.** Un helper `make_rule` che costruisce una `Rule` minima esiste in piu' file di test. La consolidazione e' stata declinata perche' alcune delle copie vivono in `tests/test_rules.py` e `tests/test_rule_contracts.py`, congelati come TASK-7 APPROVED: spostare l'helper in `conftest.py` avrebbe lasciato le copie congelate al loro posto, producendo quattro copie piu' un import invece di una definizione sola. Va fatto quando il congelamento e' irrilevante, cioe' in un giro che possa toccare anche quei file.

**Duplicazione degli oggetti ostili.** I test di degradazione del rendering definiscono oggetti il cui `__str__` alza, e ora anche una metaclasse il cui `__name__` restituisce un oggetto non stringa. Ne esistono copie in `tests/test_sitecustomize.py` (dentro i test di `_describe`, piu' il pacchetto sintetico `FAKE_RULES`) e in `tests/test_activation_atomic.py`. Le forme non sono identiche (una deve vivere dentro un file sorgente generato per un subprocess), quindi la consolidazione non e' meccanica: va deciso che cosa e' davvero comune.

**Costo dei subprocess.** `tests/test_sitecustomize.py` lancia ora 11 interpreti, misurati a 30-45 ms ciascuno. La review Efficiency ne ha indicato due fondibili: `test_inert_without_env` e `test_inert_run_does_not_import_pyteman` lanciano lo stesso identico processo inerte e poi asseriscono su aspetti diversi dello stesso avvio. Declinato in RT-01 perche' fondere due test preesistenti scambia 30 ms contro la granularita' diagnostica: oggi, quando uno dei due fallisce, il nome del test dice gia' se il problema e' l'output o `sys.modules`. Chi esegue questo task decida se il baratto conviene; gli altri 9 subprocess sono giustificati, perche' il percorso sotto test finisce in `os._exit(2)` o richiede un environment diverso.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Una sola definizione di make_rule condivisa dai test che ne hanno bisogno, oppure una motivazione scritta del perche' le copie restano separate
- [ ] #2 Un solo posto che definisce gli oggetti ostili al rendering usati dai test di degradazione
- [ ] #3 Il numero di interpreti lanciati da test_sitecustomize.py e' giustificato: ogni subprocess che resta ha una ragione dichiarata per non poter girare in-process
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Rilievo dal gate /simplify di TASK-5 (2026-09-17), depositato qui invece di aprire un task separato, su disposizione dell'orchestrator. NON e' lavoro svolto su questo task: alimenta il criterio #2, allargandolo da "gli oggetti ostili al rendering" a "i moduli vittima", che e' la stessa duplicazione un'altezza piu' su.

**Il ciclo di vita di sys.modules e' riscritto a mano accanto alla fixture che lo incapsula.** In `tests/test_activation_atomic.py` la fixture `_victim_module` costruisce un `types.ModuleType`, lo inserisce in `sys.modules` e lo toglie nel teardown. La fixture `inheriting` rifa' esattamente quella sequenza invece di usarla, perche' le serve piazzare nel modulo una gerarchia di classi che `_victim_module` non sa costruire. I quattro test aggiunti da TASK-5 fanno lo stesso: `test_a_slot_is_restored_by_setattr_and_not_emptied_by_delattr` e `test_a_property_without_a_deleter_is_restored_rather_than_refused` aprono entrambi con la stessa tripletta `ModuleType` / `sys.modules[...] = mod` / `finally: del sys.modules[...]`, per la stessa ragione: il contenuto del modulo vittima e' diverso a ogni volta, e la fixture offre un contenuto solo.

Dichiarato in TASK-5 e non corretto li' per perimetro. La correzione onesta non e' far chiamare la fixture dagli altri, che e' impossibile finche' la fixture decide anche COSA c'e' dentro il modulo: e' spezzare `_victim_module` in due, cioe' un helper che possiede solo il ciclo di vita di `sys.modules` e accetta un modulo gia' popolato, piu' la fixture attuale costruita sopra di esso. E' una modifica a una fixture condivisa da tutta la suite di `test_activation_atomic.py`, quindi tocca test che TASK-5 non aveva motivo di aprire, e l'orchestrator aveva vincolato quella tranche con "non fare cleanup di fixture condivise salvo indispensabile".

La stessa forma della duplicazione di `make_rule` descritta sopra, con una differenza che conta per chi esegue: qui non c'e' nessun file congelato di mezzo, quindi il lavoro e' fattibile in un giro solo e senza coordinamento.

Caso concreto e piu' stretto di quanto descritto sopra, trovato dal gate /simplify il 2026-09-17 sulla tranche RT-02.

In tests/test_activation_atomic.py esistono ora TRE copie della stessa classe vettore di rientranza: ImportsAnAliasingModule a :2636-2657, ImportsASecondModule a :2451-2469, ReentrantSignature a :2358-2385. Le tre sono identiche a meno del nome del modulo che importano e della stringa restituita da __call__. Ciascuna porta un proprio flag `reentered` a livello di CLASSE, che ogni test azzera a mano in cima (:2676, :2491, :2404), e ciascun test ripete lo stesso impianto: salvare builtins.__import__, costruire i moduli, assegnare sys.modules, install_hook, guidare l'import, e un finally che ripristina l'import e cancella le voci in sys.modules.

Forma suggerita: un solo vettore parametrizzato, ReentersOnSignature(module_to_import, result), con il flag a livello di ISTANZA invece che di classe, il che elimina anche i tre azzeramenti manuali; piu' un context manager che possieda il ciclo di vita di hook e sys.modules. Circa 35 righe duplicate, e il vettore di rientranza avrebbe un solo posto in cui cambiare.

Da NON fare in questo task: il gate ha verificato che il test nuovo test_a_reentrant_patch_that_takes_the_slot_being_built_leaves_one_entry DOVEVA costruire i moduli a mano. composed() fissa il nome dell'attributo a `f` e il modulo a MODNAME5, crule() fissa module/symbol agli stessi, mentre quel test ha bisogno di due moduli, di un attributo chiamato `a`, di un legame alias e di Rule che portano una azione pragma con target param:. Non e' quindi un riuso mancato degli helper esistenti, ed estendere composed()/crule() per coprirlo non e' richiesto qui.

L'altro test nuovo, test_one_exits_condition_cannot_hide_the_body_error_from_the_next a :2009-2044, non ha questo problema: usa crule, composed e Recorder, sta subito sotto il fratello che estende, e aggiunge solo le due regole che fanno il punto. Nulla da fare li'.
<!-- SECTION:NOTES:END -->
