---
id: TASK-184
title: >-
  Test committed per la direzione refusal dei descriptor con cache (follow-up
  TASK-123)
status: Done
assignee: []
created_date: '2026-09-27 13:39'
updated_date: '2026-09-27 14:20'
labels:
  - patcher
  - test-coverage
  - rt-02
dependencies: []
references:
  - src/pyteman/patcher.py
  - tests/test_slot_reservation.py
  - docs/rules.md
  - /home/pantinor/pyteman-evidence/task123-review/probe_task123.py
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Follow-up di TASK-123, emerso dalla revisione indipendente del PR #164 (verdetto APPROVED a d5ffacd45843f6b86eca2ad21955fd33b3e049d1, merge a1a5a46).

La direzione 'refusal' dei descriptor con cache e' documentata (docs/rules.md: un caching descriptor misura stabile e la sua ricostruzione fra la lettura decisionale e quella di settle viene rifiutata, direzione conservativa) e verificata da probe esterni (scenario f della revisione: /home/pantinor/pyteman-evidence/task123-review/probe_task123.py), ma NESSUN test della suite la pinna: il messaggio 'was replaced while' appare in un solo test (tests/test_slot_reservation.py:339, forma swap su attributo di modulo) e l'unica copertura descriptor-shaped e' la direzione opposta (fresh-per-read smorza il gate).

Da fare:
1. Un test committed che specchia lo scenario f: una property memoizzante (o cached_property) la cui cache scade esattamente fra la lettura decisionale (read 2) e quella di settle (read 3) deve essere RIFIUTATA con 'was replaced while', nulla installato, valore ricostruito al suo posto. La vittima conta le letture come _swap_victim; attenzione alla coreografia: la scadenza deve avvenire DOPO la lettura live e PRIMA di quella di settle (una ricostruzione confinata nel varco settle->sonda smorza il gate invece: vedi la nota di copertura nella revisione). Vale la pena un secondo caso che pinni anche quella direzione di smorzamento, perche' oggi e' solo documentata nei commenti.
2. Informativa, stessa tornata: l'ancora del commento 'Last look' in src/pyteman/patcher.py (~2720 dopo il merge, la clausola 'from there to this write') si legge ancorata alla lettura di settle, ma quel varco contiene la sonda del gate stesso, che e' un ask di identita'. Riformulare l'ancora al gate come unita' ('dal gate in poi').

Vincoli: il commento e' l'unico cambio consentito fuori dai test; batteria completa verde; mutazioni (test nuovo ucciso togliendo il termine stable del gate).
<!-- SECTION:DESCRIPTION:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
GATE (2026-09-27): /simplify combinato (4 angoli) -> 5 finding minor APPLICATI tutti: _memo_victim delega il ciclo di vita del modulo a _victim (un solo proprietario di register/teardown); __set_name__ morto cancellato; l'indirezione state['build'] sostituita dalla registrazione state['built'] (che serve anche al finding principale della belt); _rule guadagna symbol= keyword e _instance_rule e' ripiegato nei tre call site; i literal 3/4 sostituiti da _DECIDING_READ e _DECIDING_READ + 1.

CODE REVIEW BELT (high): CHANGES-REQUIRED con UNA finding Important, confermata per mutazione (M3): l'assertion comportamentale handler(1) == ('handler', 1) non distingueva 'il valore ricostruito e' rimasto' da 'il patcher ha riscritto l'originale stale sopra lo slot', perche' i callable sono comportamentalmente identici; la belt ha provato che inserendo setattr(live) prima del raise il test passava. FIX applicato: il descrittore registra state['sets'] ( ogni __set__) e state['built'] (ogni costruzione); il test 1 ora asserisce sets == [], handler is built[-1], len(built) == 2 accanto alla riga comportamentale. M3 rieseguito sul candidato fissato: il test FALLISCE (prima passava). Mutazioni M1 (termine stable tolto -> disarm test fallisce) e M2 (gate spento -> refusal test fallisce) rieseguite sul candidato finale: entrambe uccidono.

Ancora del commento 'Last look': la belt conferma la sostanza e segnala una friabilita' ereditata ('that unit reaches only up to the settled read' e' vero solo in senso di ancora quando la sonda spara); riscrittura completa applicata: 'il valore che certifica e' quello della lettura di settle, e il chiederlo attraversa la lettura di sonda; da quella sonda a questa scrittura la domanda resta aperta'. Bottino della pulizia: both anchor ora precisissimi.

VERIFICA FINALE: check pulito; 1279 passed 2 skipped (1276 + 3 nuovi); 15 passed nel file; mutazioni M1/M2/M3 tutte kill sul candidato finale; albero ripristinato byte-exact dopo ogni mutazione (sha256 7bd1ac52...).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Chiuso con il merge da5b43d (PR #167, squash di a99dd8b su master a1a5a46). Tre test committed in tests/test_slot_reservation.py pinnano le direzioni descriptor-con-cache del gate TASK-123: (1) ricostruzione fra lettura decisionale e settle -> rifiuto 'was replaced while', per IDENTITA' (fixture registra builds e writes: sets == [], handler is built[-1], len(built) == 2) e non solo per comportamento; (2) controllo con cache tenuta -> installa, spara, disinstalla sull'originale in cache; (3) doppia ricostruzione settle+sonda -> la coppia non concorda, il gate smorza, si installa: la stabilita' e' una misura, non una classificazione. Commento 'Last look' ri-ancorato: il gate come unita' (sonda inclusa), il residuo aperto parte dalla sonda. Gate: /simplify 4 angoli (agente combinato, 5 finding applicati e verificati presenti nel master unito con grep); belt high CHANGES-REQUIRED per l'assertion solo-comportamentale (mutazione M3 della belt: setattr(live) prima del raise passava il primo draft), fix con registrazione builds/sets e M3 rieseguito a uccidere; M1/M2 kill; revisione indipendente APPROVED a a99dd8b (14 invarianti HOLDS, 2 note informative senza azione); CI verde 7 check; batteria 1279 passed 2 skipped.
<!-- SECTION:FINAL_SUMMARY:END -->
