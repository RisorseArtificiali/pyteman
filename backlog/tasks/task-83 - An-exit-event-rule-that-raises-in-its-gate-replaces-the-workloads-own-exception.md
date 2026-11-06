---
id: TASK-83
title: >-
  An exit-event rule that raises in its gate replaces the workload's own
  exception
status: Done
assignee: []
created_date: '2026-09-16 20:51'
updated_date: '2026-09-25 10:58'
labels:
  - rt-01
  - review-followup
  - audit-2026-09-16
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found during the RT-01 review (reviewer finding 4) and reproduced directly. Filed rather than fixed because RT-01 scopes to the ACTIVATION path; this is on the FIRING path, inside the wrapper.

In `Patcher._make_wrapper`, the wrapper runs the exit-event gate from a `finally`:

```
try:
    result = original(*args, **kwargs)
except BaseException as e:
    exc = e
    raise
finally:
    if rule.event == "exit":
        ctx["result"] = result
        ctx["exc"] = exc
        if _gate(rule, state, ctx, when_code, key_code):
            run_action(rule, ctx, log=self.log)
```

An exception raised by `_gate` inside that `finally` REPLACES the exception the wrapped call was already propagating. `_gate` runs two pieces of operator-authored code that can raise: the `when` expression, and the `once_per` key expression.

Reproduced (src on sys.path, module `v4` holding `boom` which raises ValueError, one exit rule with `when: "result.anything"`):

```
workload saw: AttributeError : 'NoneType' object has no attribute 'anything'
  original, demoted to __context__: ValueError : the workload's own failure
```

`result` is None on the exception path, so any `when` reading through it raises. The operator's own ValueError survives only as `__context__`, and the failure they are shown belongs to the instrumentation rather than to their program. That is the exact substitution class RT-01 spent this tranche removing from the activation path: the reporting becoming the failure it reports.

This is a behaviour decision as much as a bug, which is why it is a task rather than a patch. Either the gate's failure is suppressed and disclosed as a note on the original (matching the rollback path's "never instead of it" rule), or it is intended that a broken rule surfaces loudly and the docs should say so. It is currently neither: undocumented and silent about what it displaced.

Note that `run_action` has the same exposure from the same `finally` and should be decided together.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A decision is recorded: either an exit-event gate/action failure is suppressed and attached to the in-flight exception as a note, or it is documented as deliberately replacing it
- [ ] #2 If suppressed: the workload's own exception propagates unchanged, and a test asserts the original type and message survive while the rule's failure is disclosed
- [x] #3 If documented: docs/rules.md states that a raising when/key expression on an exit event replaces the wrapped call's exception, and names __context__ as where the original goes
- [x] #4 run_action's exposure from the same finally is decided the same way rather than left implicit
- [x] #5 A test covers the once_per key expression as well as when, since both run inside _gate
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Scegliere ramo documentazione già previsto da AC1: preservare propagazione delle eccezioni delle exit rule, sia gate when/key sia action. Coerente con contratto già pubblicato action raise/strict/log failure; nessuna soppressione o modifica runtime. Correggere docs/rules paragrafo che parla soltanto di action e la frase 'only way', precisando che errori gate/action sostituiscono l'eccezione body come Python finally, la conservano in __context__ e fermano exit successive. Un gate fallito prima dell'azione non genera start record.

Test mirati con Patcher/actions reali: when e once_per key su body raise/return, final type+message e context identity, exit successiva non eseguita; riusare coverage action già esistente senza duplicare. AST produzione invariato. Mutazione swallow/continue discriminante in copia e cache isolata. Docs+test soltanto, simplify mirato e review indipendente finale; pubblicazione unità separata.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Scout su b082b35 segnala TASK83 riprodotto, mentre TASK106 difetto originario non riproduce (AC restanti non auditati) e TASK157 tre difetti stale con residuo documentale/AC2 da correggere, nessuna chiusura automatica. Coordinatore conferma runtime attuale con tre probe veri: exit when result.anything -> AttributeError, exit once_per key stesso -> AttributeError, exit action raise -> RuntimeError; in tutti e tre __context__ is original ValueError. Docs/rules:459-464 già sceglie sostituzione per action, LOG02/strict exit stessi limiti documentati. Decisione qui estende chiarezza a gate, non cambia policy o ribalta una garanzia come nel vecchio TASK131. Mandato implementer docs+test, no runtime/scope ampliato.

PR13 MERGED820c5a269b05bf241d1f5d12721c342d96097126, commit796a92e1c89f82809c4cfebbb8f83eb56c0d62de, CI35450970360 tutti sei job success. Review/commenti/discussion vuoti al controllo finale. Runtime invariato; review indipendente APPROVEDf0f59d2f, simplify mirato eseguito implementer, suite indipendente e shared1081/1skip opzionale. Mutazioni gate/status verificate dal reviewer. AC2 condizionale NON APPLICABILE perché scelta documentazione e non soppressione; non è un'implementazione mancante.
Transizione Done bloccata dal hook che non riconosce gate delegati nel transcript coordinator. Nessun bypass o retry identico. Stato tracker In Progress amministrativo; consegna pubblicata. Prove ~/pyteman-evidence/task83-integration-20260919-170245/.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed 2026-09-25 by backlog audit. PR#13 merged as commit 796a92e (specify exit gate and action exception precedence), CI green. Administratively stuck In Progress. Code published in v0.2.0.
<!-- SECTION:FINAL_SUMMARY:END -->
