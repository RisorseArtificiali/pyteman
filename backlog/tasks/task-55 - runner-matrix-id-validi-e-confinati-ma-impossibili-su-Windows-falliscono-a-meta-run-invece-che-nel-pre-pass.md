---
id: TASK-55
title: >-
  runner/matrix: id validi e confinati ma impossibili su Windows falliscono a
  meta' run invece che nel pre-pass
status: Done
assignee: []
created_date: '2026-09-16 17:15'
updated_date: '2026-09-30 10:13'
labels:
  - runner
  - validation
  - windows
  - follow-up
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`_check_cell_ids` esiste per rifiutare in blocco, prima che una cella giri, gli id che non possono diventare una directory. Copre quattro guasti: separatori, NUL, drive specifier, lunghezza in byte.

Restano fuori due famiglie che su un host Windows rendono `os.makedirs` impossibile pur essendo perfettamente confinate dentro `artifact_root`:

- nomi di device riservati: `CON`, `PRN`, `AUX`, `NUL`, `COM1`..`COM9`, `LPT1`..`LPT9`;
- caratteri che Windows rifiuta in un nome di file: `< > " | ? *`, e i due punti in posizione non iniziale come `a:b`, che `ntpath.splitdrive` non tratta come drive e che quindi supera il controllo aggiunto da TASK-20.

Esito su Windows: la run parte, le celle precedenti girano e committano, e la cella incriminata alza `OSError` da `src/pyteman/runner/matrix.py:187` dentro il loop. E' esattamente il modo di fallire che il pre-pass dichiara di prevenire, con la differenza che la docstring promette la protezione solo per i quattro guasti che nomina.

Nessuna fuga dalla root: questi nomi restano componenti singoli e confinati. Il problema e' il momento del fallimento, non il luogo della scrittura.

Trovato dal code review high-effort del gate di TASK-20 (RUN-02), confidenza 50, Windows-only. Non implementato in TASK-20 perche' il requisito di quel task e' il confinamento, e questi id sono confinati; rifiutarli e' una scelta di validazione a se stante.

Da decidere in sede di implementazione: se rifiutare sempre (coerente con il drive specifier, che TASK-20 rifiuta su ogni piattaforma perche' l'id viaggia con la definizione della matrice e il db sopravvive alla macchina che lo ha scritto) oppure solo su `os.name == "nt"`. La prima e' coerente con la scelta gia' fatta; la seconda evita di rifiutare su Linux nomi che su Linux funzionano.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 _check_cell_ids rifiuta i nomi di device riservati Windows (CON, PRN, AUX, NUL, COM1-9, LPT1-9), con o senza estensione, case-insensitive
- [x] #2 _check_cell_ids rifiuta i caratteri che Windows non ammette in un nome di file: < > " | ? * e i due punti in posizione non iniziale (es. a:b)
- [x] #3 La scelta fra rifiuto su ogni piattaforma e rifiuto solo su nt e' presa esplicitamente e motivata nella docstring, coerentemente con il drive specifier gia' rifiutato ovunque da TASK-20
- [ ] #4 Un test prova che il rifiuto avviene nel pre-pass, prima che una qualsiasi cella giri: calls == [] e nessuna riga nel db
- [ ] #5 Il messaggio di rifiuto dice quale nome e perche' non e' utilizzabile, senza promettere protezioni che il codice non offre
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #64. Added lines already present on master per PR: #64 8/90=8%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.

Merged 2026-09-30 via #200 (704b9a0). Evidence under /home/pantinor/pyteman-evidence/t191/: diff55.patch sha256 2616ff9c, tree55-hold2.sha256, mutants-55.log, VERDICT-55.md in t191rev.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed by PR #200, squash-merged as 704b9a0 on master at 2026-09-30 10:12Z. AC1: _check_cell_ids refuses the Windows reserved device names (CON, PRN, AUX, NUL, COM1-9, LPT1-9), case-insensitive, extension-stripped so CON.txt is caught, including the superscript-digit spellings Windows treats as the digits themselves. AC2: it refuses the characters Windows forbids in a file name (< > " | ? *, a colon not caught by the drive check, and the control characters 1 to 31), all sourced from Microsoft's current naming page by the code review. AC3: the everywhere-not-just-nt choice is explicit in the docstring, extending TASK-20's travel-with-the-definition rationale exactly as the drive specifier did; the refusal message names the actual hazard (an evidence tree Windows tools could not consume) rather than an os.makedirs call the fcntl gate precludes. Near-miss controls in both tests guard the over-matching direction, in subdirectories of their own after the emptiness claims. The reviewer's informational note (the id-is-a-prefix dependency) is filed on TASK-198. Supersedes #64, closed with a pointer. Gates at dade6af: suite 1537 passed 2 skipped, check green, delivery 41, battery 6/6, code-review high four findings all applied, independent verdict APPROVED (VERDICT-55.md).
<!-- SECTION:FINAL_SUMMARY:END -->
