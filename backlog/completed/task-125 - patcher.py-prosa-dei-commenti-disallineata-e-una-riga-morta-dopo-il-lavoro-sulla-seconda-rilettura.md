---
id: TASK-125
title: >-
  patcher.py: prosa dei commenti disallineata e una riga morta dopo il lavoro
  sulla seconda rilettura
status: Done
assignee: []
created_date: '2026-09-17 04:39'
updated_date: '2026-09-25 12:49'
labels:
  - patcher
  - docs
  - cleanup
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Raccolta delle segnalazioni di pulizia emerse dal gate /simplify del 2026-09-17 sul tranche RT-02. Nessuna di queste e' un bug ne' discende da un AC, quindi sono tracciate e non applicate subito: vanno raccolte in un unico passaggio quando quelle regioni verranno comunque toccate, per non aprire un ciclo di edit e review su cosmetica.

1. La docstring di `_owns_name` (patcher.py:179) dice che `_undo_one` ripone la domanda "una seconda volta" senza condizioni, ma `_undo_one:303` e' `if owned or not _owns_name(container, name)` e l'`or` corto circuita: la seconda domanda parte solo quando `owned` e' False. La proprieta' di sicurezza enunciata resta vera, perche' il delattr vive nel ramo else che richiede sia `not owned` sia una seconda risposta affermativa. E' quindi prosa imprecisa, non un'affermazione fuorviante. Stesso disallineamento nel commento a patcher.py:296.

2. `sig = None` dentro l'except a patcher.py:971 e' morta: la :954 lega gia' None e un `inspect.signature(original)` che solleva non rilega mai il bersaglio, quindi l'assegnazione ripristina un valore mai perduto.

3. Il commento su `_ABSENT` a patcher.py:11-12 argomenta il caso di `_NO_OVERRIDE`, non il proprio.

4. Riavvolgimento irregolare lasciato da modifiche in loco: patcher.py:651, patcher.py:657, README.md:64-66, docs/rules.md:244 e 248.

5. Cinque righe di commento sopra un `if` di due righe a patcher.py:928-932, sproporzionate rispetto a cio' che spiegano.

6. La storia della rientranza e' riderivata per intero in quattro punti diversi invece di essere enunciata una volta e richiamata.

7. docs/rules.md racconta la cronologia delle finestre di corsa dove enuncerebbe piu' brevemente l'invariante che ne risulta.

8. Il paragrafo di composizione in README.md ripete docs/rules.md:404-450 senza il puntatore che il README usa altrove per lo stesso scopo.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 La docstring di _owns_name e il commento a patcher.py:296 descrivono la seconda domanda come condizionata a owned False, coerentemente con il corto circuito dell'or
- [x] #2 La riga morta sig = None nell'except e' rimossa e la suite resta verde
- [x] #3 Il commento su _ABSENT parla di _ABSENT
- [x] #4 I punti di riavvolgimento irregolare elencati sono riallineati senza cambi di contenuto
- [x] #5 La storia della rientranza e' enunciata in un punto solo e richiamata dagli altri tre
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Commit ff4bbaa on branch work/patcher-comment-cleanup, PR #41.\n\nAC#1: _owns_name docstring and _undo_one comment now describe the second ownership query as conditional on owned being False, matching the or short-circuit.\nAC#2: Confirmed already resolved; no dead sig = None in any except block.\nAC#3: _ABSENT comment now describes _ABSENT (getattr sentinel) rather than _NO_OVERRIDE.\nAC#4: Irregular wrapping fixed in README.md (lines 64-77, severe short-wrap), docs/rules.md (80-char lines reflowed), and patcher.py OncePerKeyError docstring (80-81 char lines reflowed). Two patcher.py locations (original lines 651, 657) verified at natural word boundaries via textwrap; no improvement possible.\nAC#5: Re-entry history consolidated to labeled RE-ENTRY section in _patch; three satellite sites (_inflight, first re-read, second re-read) shortened to reference it.\n\nGate evidence: /simplify 3 agents all clean; code-review high no issues at >= 80% confidence; 1190 passed 2 skipped; dev.py check green.
<!-- SECTION:FINAL_SUMMARY:END -->
