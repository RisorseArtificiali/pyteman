---
id: TASK-185
title: >-
  Docs di attivazione: installazione editable non attiva l'hook; target in
  __main__ strumenta una copia muta
status: To Do
assignee: []
created_date: '2026-09-27 15:39'
labels:
  - docs
  - activation
  - filed-by-ccgram
dependencies: []
references:
  - README.md
  - docs/rules.md
  - src/pyteman/rules.py
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Due note di integrazione dalla verifica live di TASK-181 fatta dalla sessione ccgram (2026-09-27, checkout a ea9a378, embedding reale: uv --no-project, niente installato). La verifica stessa e' positiva: regola entry {kind: sleep, ms: 60000, async: true} su target coroutine, ticker di servizio a pieno ritmo durante la sospensione, plain sleep congela, log con 'async': True. Le due note da valutare per i docs:

1. L'installazione editable NON attiva l'hook: PYTHONPATH deve portare la directory src/pyteman del checkout (quella che contiene sitecustomize.py). Il README lo dice gia', ma la formulazione si lascia sfuggire il caso 'ho fatto pip install -e, perche' non spara?'. Valutare un rilievo piu' esplicito (probabilmente nella sezione di attivazione del README).

2. Un point che vive in uno script eseguito come __main__ strumenta silenziosamente una SECONDA copia del modulo che nessuno chiama: nessun firing, nessun errore. `python script.py` lo esegue come __main__ mentre il ruleset nomina `script`; l'hook parcheggerebbe solo il modulo importato. E' il footgun classico degli strumenti di instrumentazione Python e oggi non e' documentato da nessuna parte in pyteman. Da valutare: un paragrafo nel README (contratto dei target) o docs/rules.md, e se vale un warning a load/preflight (il loader vede module=script e potrebbe almeno dichiarare che script dev'essere importato, non eseguito).

Provenienti dall'harness README di ccgram (tools/diagnostics/task43 nel repo ccgram). Priorita' bassa: niente di rotto, solo attrito documentale.
<!-- SECTION:DESCRIPTION:END -->
