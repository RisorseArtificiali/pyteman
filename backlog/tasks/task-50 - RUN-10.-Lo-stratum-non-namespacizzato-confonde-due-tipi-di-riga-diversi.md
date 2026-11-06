---
id: TASK-50
title: RUN-10. Lo stratum non namespacizzato confonde due tipi di riga diversi
status: Done
assignee: []
created_date: '2026-09-16 15:44'
updated_date: '2026-09-27 20:05'
labels:
  - audit-2026-09-16
  - run
  - review-followup
  - schema
milestone: m-3
dependencies: []
references:
  - src/pyteman/runner/matrix.py
  - src/pyteman/runner/report.py
  - tests/test_matrix_identity.py
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Emersa dalla review del lavoro RUN-01 (TASK-19), 2026-09-16. Non e un difetto corrente: il comportamento e corretto ed e coperto da test. E' una rappresentazione che costa a chi legge la tabella e a chi scrivera la prossima query.

Nella colonna experiment il valore stringa vuota significa oggi due cose distinte:

1. Una riga scritta deliberatamente con experiment=None. Il chiamante ha dichiarato che quella matrice non ha identita oltre alle sue celle. La riga porta un fingerprint, perche una run lo ha calcolato.
2. Una riga migrata da un database precedente al tracciamento della provenienza. Il fingerprint e NULL, perche nessuna run lo ha mai prodotto, e cosa abbia generato quella riga e genuinamente ignoto.

Il discriminante e quindi il fingerprint, non la colonna che porta il nome della cosa da discriminare. La conseguenza pratica: _lookup(legacy_only=True) filtra su fingerprint IS NULL, e report.py deve ripetere lo stesso test in _experiment_label per non stampare l'ignoranza della riga migrata sopra la dichiarazione dell'altra. Ogni nuovo consumatore della tabella deve riscoprire la stessa convenzione implicita.

Il rischio concreto e gia stato toccato una volta. Durante RUN-01 un passo _Step costruito con source uguale allo stratum legacy per una cella senza riga memorizzata faceva cancellare a una run con nome la riga experiment=None omonima, perche il lookup legacy filtra fingerprint IS NULL e quindi non vedeva mai la riga che stava per distruggere. E' corretto adesso e pinnato da test_a_named_run_does_not_delete_a_deliberately_unnamespaced_row piu la mutazione M21, ma la forma che lo ha reso possibile e ancora quella.

Opzioni da valutare, nessuna scelta fatta: due valori sentinella distinti nella colonna experiment; una colonna esplicita per l'origine della riga; oppure lasciare cosi e promuovere il predicato a funzione unica condivisa (vedi TASK-42), documentando la convenzione dove la tabella e definita.

Qualunque strada va trattata come migrazione conservativa: nessuna riga storica persa o riscritta in silenzio.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Deciso e documentato come lo stratum non namespacizzato distingue una riga scritta con experiment=None da una riga migrata, senza che il chiamante debba conoscere la convenzione sul fingerprint
- [x] #2 Il predicato che riconosce una riga pre-provenance esiste una volta sola e sia matrix.py sia report.py lo usano
- [x] #3 Se la rappresentazione cambia, la migrazione e conservativa: nessuna riga storica persa, sovrascritta o riclassificata in silenzio, con test che lo dimostrano su un database costruito con entrambi i tipi di riga
- [x] #4 test_a_named_run_does_not_delete_a_deliberately_unnamespaced_row e test_a_deliberate_absence_of_identity_reads_apart_from_an_unknown_one restano verdi, adattati alla nuova rappresentazione ma non indeboliti
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-09-16, review Altitude sullo stato finale di RUN-01. Aggiunge un'opzione concreta alle tre gia' elencate nella descrizione, e smonta la ragione che sembrava obbligare alla conflazione.

Opzione: dare allo stratum di provenienza ignota un valore di experiment tutto suo, che `_experiment_key` non possa mai produrre. Oggi `_experiment_key` emette JSON canonico per ogni valore diverso da None e stringa vuota per None, quindi qualunque token nudo non quotato (per esempio `legacy`) e' irraggiungibile per costruzione. Conseguenze: experiment=None torna a essere un namespace ordinario; `legacy` diventa `source == _LEGACY_STRATUM`, cioe' un fatto su dove la riga vive invece che una deduzione dal fingerprint; `_lookup` perde il parametro legacy_only e la clausola AND fingerprint IS NULL; la guardia del DELETE nel run loop diventa lo stesso test dell'archivio; report.py etichetta dalla sola colonna experiment.

Punto che vale la pena registrare: la ragione scritta nel commento a matrix.py:14-18, cioe' che lo stratum migrato deve restare raggiungibile da ogni experiment perche' la migrazione possa concludersi invece di lasciare righe irraggiungibili, e' soddisfatta dal lookup di fallback in _plan, non dalla condivisione della chiave stringa vuota. Quindi quel requisito non forza la conflazione: le due cose erano state legate senza necessita'.

Censimento del costo attuale, dalla stessa review: la separazione fra le due nozioni e' pagata in sette punti (parametro legacy_only e clausola in _lookup; secondo lookup condizionale in _plan; lettura della classe dal fingerprint invece che dallo stratum; guardia del DELETE con dieci righe di commento; _remedies che deve sapere che le righe legacy sono non namespacizzate per ritirare un proprio suggerimento; _experiment_label in report.py; un paragrafo del docstring di run_matrix). La regola e' una convenzione e non un fatto di schema, quindi un lettore che la sbaglia produce una risposta plausibile e sbagliata invece di un errore.

Nessuna modifica applicata: stato di RUN-01 congelato e gia' verificato al momento della review.

IMPLEMENTAZIONE (2026-09-27, merge pendente PR #173, head 03d8ff7): opzione della nota altitude adottata. _LEGACY_EXPERIMENT = 'legacy' (token nudo irraggiungibile per costruzione: gli esperimenti con nome si scrivono come JSON canonico, sempre con virgoletta, None come stringa vuota); SCHEMA_VERSION 3->4 con _rekey_legacy_stratum (UPDATE conservativo delle sole righe ''+fingerprint NULL, v2 e v3 coperti, idempotente, errore MatrixIdentityError tipizzato sulla collisione di chiave con nome delle due righe); _lookup perde legacy_only e la clausola fingerprint; la guardia DELETE, _remedies, il docstring di run_matrix e il README riscritti (l'esperimento None scrive la stringa vuota come namespace ordinario; OGNI esperimento raggiunge lo stratum solo tramite il fallback; riga None e riga migrata coesistono nei propri stratum finche' una policy non ne risolve una); report etichetta dalla colonna, con CASE testimone per le tabelle straniere senza colonna experiment E per i db runner-written non ancora re-keyed (rilevati da schema_meta < 4: il report non scrive, nulla altro li migrerebbe mai). Il census dei sette punti si consolida: restano solo i due punti di definizione (la WHERE della migrazione e la CASE del reader).

GATE (2026-09-27): /simplify combinato, 8 finding APPLICATI (README ancora al modello v3 in due paragrafi; docstring tail di run_matrix e prose dei test residue; trasporto morto del fingerprint nel report (parametro e colonna tolti, import locale per riga sostituito da un import modulo-livello); migrazione estratta a funzione col quando-commit e l'errore tipizzato dei precedenti del file; frase di coesistenza simmetrica; helper v3_db per i due test). BELT high: CHANGES-REQUIRED con una IMPORTANT confermata da probe (il report MISLABEL-ava le righe migrate nei db v2/v3 non ancora re-keyed, perche' legge solo la colonna e il report non scrive: fix con il pre_split da schema_meta), una MINOR (IntegrityError nudo dalla re-key su collisione: fix tipizzato), una MINOR di prose nei test (fix) e una nota di copertura (riga migrata failed aggiunta al test misto). Mutazioni: re-key rimossa -> test migrazione fallisce; chiave None -> token -> test named-run fallisce; CASE appiattita -> test forma fingerprint-only fallisce; ramo pre_split cancellato -> probe del reader non re-keyed. Batteria 1318 passed 2 skipped.

PROCESSO: due script della catena /simplify hanno perso edit per la stessa modalita' gia' registrata in TASK-90 (il primo senza write_text, il secondo con ancore wrapping-mismatched); scoperti dal grep di verifica byte post-belt e rifatti con marcatori. Conferma la lezione registrata in TASK-90: ogni edit script deve marcare e il comando successivo verifica il byte.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Chiuso con il merge 640a49e (PR #173, squash di 46df89a su master 816037d, delta 46df89a sui due finding della revisione). Decisione: token dedicato per lo stratum pre-provenance ('legacy', irraggiungibile per costruzione da _experiment_key), schema v3->4 con _rekey_legacy_stratum conservativo (solo le righe ''+fingerprint NULL, v2 e v3, idempotente, collisione rifiutata con errore tipizzato che nomina le due righe), la stringa vuota torna a significare una sola cosa (riga deliberatamente senza nome). Il census dei sette punti si consolida nei due soli punti di definizione (WHERE della migrazione, CASE del reader); _lookup perde legacy_only; report etichetta dalla colonna, con la CASE testimone per le tabelle straniere senza colonna experiment e per i db runner-written non ancora re-keyed (rilevati da schema_meta < 4; il report non scrive; la CASE specchia il predicato della re-key cosi' gli esperimenti con nome restano tali). Gate: /simplify 4 angoli (agente combinato, 8 finding applicati e verificati nei byte del merge 640a49e per grep); belt high CHANGES-REQUIRED (mislabel del reader non re-keyed, IntegrityError nudo, prose) fissati e riprovati con i probe della belt; revisione indipendente CHANGES-REQUIRED due round (la CASE pre-split collassava gli esperimenti con nome e il ramo era senza pin) fissata con la CASE specchio del predicato e il test di stabilita' pre/post migrazione che uccide la mutazione 'ramo cancellato', APPROVED al secondo round su 46df89a; CI verde 7 check sullo stesso head; batteria 1319 passed 2 skipped; mutazioni che uccidono (re-key, chiave None, CASE straniera appiattita, ramo pre_split cancellato).
<!-- SECTION:FINAL_SUMMARY:END -->
