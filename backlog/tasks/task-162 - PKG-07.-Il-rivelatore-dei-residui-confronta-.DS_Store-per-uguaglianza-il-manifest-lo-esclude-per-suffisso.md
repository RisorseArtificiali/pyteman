---
id: TASK-162
title: >-
  PKG-07. Il rivelatore dei residui confronta .DS_Store per uguaglianza, il
  manifest lo esclude per suffisso
status: Done
assignee: []
created_date: '2026-09-17 12:19'
updated_date: '2026-09-25 11:25'
labels:
  - pkg
  - audit-2026-09-16
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Stessa classe di difetto che TASK-137 ha appena chiuso un pattern piu' in la', trovata dalla review di quella tranche e misurata prima di essere scritta qui.

**La divergenza.** `MANIFEST.in` esclude con `global-exclude ... .DS_Store`. Quel pattern passa da `translate_pattern(pattern, anchor=False)` e compila in `(?s:\.DS_Store)\z`: libero all'inizio del percorso e ancorato alla fine. Misurato con setuptools 80.10.2:

    docs/.DS_Store       escluso = True
    docs/foo.DS_Store    escluso = True
    docs/.DS_Storey      escluso = False

`tests/test_packaging.py` rivela invece con `name == ".DS_Store"`, cioe' per uguaglianza esatta. Quindi un file chiamato `foo.DS_Store` in una directory concessa viene tolto dall'archivio dal manifest e lasciato dentro l'attesa da `_files_under`.

**Sintomo.** Non e' un file che sfugge: e' l'errore nella direzione opposta, un falso negativo del rivelatore. `test_the_sdist_carries_a_granted_directory_exactly` va rosso stampando una differenza di insiemi che nomina `foo.DS_Store` e nessuna ragione, e chi legge non ha modo di capire dal messaggio che il file e' stato escluso di proposito dal manifest. Il fallimento e' onesto ma muto.

**Perche' e' minore.** Nessun file di quella forma e' mai comparso in questo albero, e macOS scrive `.DS_Store` esatto. Serve che qualcuno crei a mano un nome che finisce per `.DS_Store`. Percio' e' tracciato invece che corretto dentro TASK-137: la tranche aveva perimetro sui pattern di backup e allargarlo avrebbe mescolato due difetti in una misura sola.

**Lavoro.** Decidere quale dei due lati ha ragione e allineare l'altro. Due opzioni, entrambe difendibili, e la scelta va motivata invece che presa per comodita':
1. Stringere il manifest ad ancorare anche l'inizio, cosa che `global-exclude` da solo non sa fare, quindi servirebbe un'altra direttiva.
2. Allargare il rivelatore a `name.endswith(".DS_Store")`, che e' esattamente cio' che il pattern compilato fa gia'.

La seconda e' una riga e rispecchia il comportamento reale; la prima cambia cosa viene spedito e va valutata per quello.

**Fuori perimetro.** Le concessioni `recursive-include` e le righe `prune`, decisioni gia' prese e motivate.

**Vincolo da rispettare.** `RESIDUE_SUFFIXES` e `_is_residue` restano tenuti A MANO e NON derivati dalla riga del manifest: quella riga impone, questa rileva, e un rivelatore derivato dalla propria imposizione non puo' piu' accorgersi che l'imposizione e' sbagliata. Il commento in testa a quella tupla lo dice gia'.

Segnalato dalla code review di TASK-137 il 2026-09-17.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Deciso e motivato quale dei due lati si allinea all'altro, manifest o rivelatore, invece di scegliere il piu' comodo.
- [ ] #2 Un file di prova la cui forma e' coperta dal pattern compilato ma non dal predicato, per esempio foo.DS_Store, e' piantato prima della build e il comportamento atteso e' asserito.
- [ ] #3 Dimostrato per misura che il test va rosso se la correzione viene tolta.
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed as invalid: the divergence described in the task does not exist in the actual sdist build path.

The task measured `setuptools._distutils.filelist.FileList.exclude_pattern(pattern, anchor=False)`, which uses `re.search` with `(?s:\.DS_Store)\z` and does match `foo.DS_Store`. But the actual sdist build (setuptools 84.0.0, and verified against 80.x as well) never uses that code path.

Setuptools overrides `FileList` in `setuptools.command.egg_info`. Its `global_exclude` method:
1. Joins `**` with the pattern: `os.path.join('**', '.DS_Store')` producing `**/.DS_Store`
2. Passes this through its own `translate_pattern` which returns a `_NormalizedMatcher`
3. Calls `match.match` (not `search`)

The `_NormalizedMatcher` for `**/.DS_Store` matches `.DS_Store` and `tests/.DS_Store` but NOT `foo.DS_Store` or `tests/foo.DS_Store`. Empirically confirmed: an sdist built with `foo.DS_Store` planted in `tests/` does contain that file in the archive.

The existing detector `name == ".DS_Store"` is therefore correctly aligned with the manifest. No code change needed.
<!-- SECTION:FINAL_SUMMARY:END -->
