---
id: TASK-187
title: >-
  TASK-58 - EX-07. Own the no-verdict exits of the 109966 driver outside the
  classified paths
status: To Do
assignee: []
created_date: '2026-09-28 02:27'
labels:
  - examples
  - hermes-109966
  - robustness
dependencies: []
references:
  - /home/pantinor/pyteman-evidence/task29impl/task29.diff
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Cut findings from the TASK-29 code review (2026-09-28, commit a58ce16 plus the uncommitted follow-up refactor), all one theme: evidence-collection calls in examples/hermes-109966/run_repro.py that sit outside the new guards can still abort the driver with a traceback and no VERDICT line. Pre-existing shapes, unchanged by TASK-29, so they were below the review's reporting cap. 1. iter_deleted_sqlite_sidecar_holders(db_path) is called bare at run_repro.py line 230: an upstream scanner exception ends the run with a traceback and rc=1, no verdict. 2. The fresh-opener probe catches only DeletedWalGenerationError (lines 236-243): any other constructor exception (sqlite3.OperationalError, OSError) propagates the same way. 3. The early _fail exits (holder never ready, pin never engaged, restarter hung) print DRIVER-ERROR and exit 2 without a VERDICT token; loud and distinguishable from a hang, but a verdict-shaped termination (or a documented contract that DRIVER-ERROR is the third terminal token) would serve whatever greps the output. Adjacent to TASK-30 EX-05, which is the durability theme; file separately so the driver-completion contract is owned.
<!-- SECTION:DESCRIPTION:END -->


AGGIUNTO dalla revisione indipendente di TASK-29 (2026-09-28, verdetto APPROVED a 36dcc0a): due bordi nello stesso stile, il primo INTRODOTTO dal diff di TASK-29 (non pre-esistente, con quella precisazione): (1) _holder_failure crasha su error_type non-stringa in un JSON valido: getattr(modulo, 42) alza TypeError che nulla cattura, run senza VERDICT (la parita' di robustezza con le guardie '[1,2]'/'oops' che quel diff ha aggiunto; nessuno scrittore in questo repo puo' produrlo, holder.py registra sempre type(exc).__name__); fix: una guardia isinstance su error_type + pin. (2) igiene: i due test unitari nuovi assegnano sys.modules['hermes_state'] senza restore (tests/test_example_driver_isolation.py ~332 e ~383): switch a monkeypatch.setitem come gia' fa test_example_log_consumers.py:45; nessuna collisione oggi (batteria verde), solo consistenza.

AGGIUNTO dalla code review di follow-up di TASK-31 (2026-09-28, diff non committato su e8d1f07, confidenza circa 40, pre-esistente, non introdotto da TASK-31): in examples/hermes-109966/run_repro.py le chiamate di seeding (SessionDB(...), create_session, append_message, close; circa riga 274) girano PRIMA del try/finally che possiede la scratch home. Un'eccezione upstream li' ora raggiunge il wrapper di __main__ ed esce 2 con DRIVER-ERROR, ma la scratch home non viene ne' rimossa ne' riportata come SCRATCH-HOME-PRESERVED. test_a_crash_past_the_preflight_is_a_driver_error_not_a_mismatch[109966-*] di TASK-31 crasha esattamente in quel punto e non asserisce sulla scratch dir. Fix: spostare il seeding dentro il try, o riportare la home su quel percorso, e fissarlo con un'asserzione sulla scratch dir in quel test.
