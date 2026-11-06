---
id: TASK-34
title: >-
  PKG-03. Allargare la matrice di verifica senza confondere coverage e
  correttezza
status: Done
assignee: []
created_date: '2026-09-16 12:20'
updated_date: '2026-09-18 05:13'
labels:
  - audit-2026-09-16
  - opus-5
  - pkg
  - proposal
milestone: m-5
dependencies:
  - TASK-32
references:
  - '.github/workflows/tests.yml:13-27'
  - 'pyproject.toml:8,16-18'
  - tests/
documentation:
  - doc-1
  - doc-2
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit 2026-09-16 sul commit a28b12662a46727ff806a42122db0ffe8333d760. Esecuzione futura prevista con Opus 5. Riprodurre il caso sullo stato corrente prima di correggere; non dipendere dalla conversazione originale.

**Priorità / stato:** P2, PROPOSTA, aperto.

**File:** `.github/workflows/tests.yml:13-27`, `pyproject.toml:8,16-18` e `tests/`.

**Evidenza:** CI locale nel repository limitata a Ubuntu con Python 3.11, 3.12 e 3.13, solo editable; `requires-python >=3.11` non impone un limite superiore. L'audit passa su Python 3.14.7 ma non sostituisce una matrice automatica. Mancano verifica wheel/sdist e raccolta coverage dei subprocess.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 CI esegue la suite sulle versioni dichiarate (Ubuntu, 3.11/3.12/3.13/3.14) con setuptools nominato esplicitamente fra le dipendenze e i motivi degli skip stampati (-rs).
- [x] #2 CI installa e verifica gli artefatti costruiti, sdist estratta e wheel, in ambienti separati, senza editable install e senza il checkout su sys.path, con la provenienza dell'import verificata in ciascun ambiente.
- [x] #3 I test che usano subprocess o multiprocessing sono inclusi nella misura di coverage (sottotask dedicato: il meccanismo va confermato sulla documentazione coverage ATTUALE prima di disegnarlo).
- [x] #4 Le azioni di kind kill sono confinate a processi figli di test e sempre con timeout (sottotask dedicato).
- [x] #5 Nessun test si affida a sleep come unica prova di ordinamento (sottotask dedicato).
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Proposta iniziale da verificare sul codice corrente, non una correzione già applicata.

aggiungere Python 3.14 e installazione wheel/sdist; dichiarare le piattaforme effettivamente supportate e testarle con skip motivati per gli esempi Linux. Configurare coverage multiprocesso prima di introdurre soglie. Aggiungere test negativi e interleaving deterministici dai task precedenti, non solo una soglia numerica.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Indicazioni di coordinamento del documento di origine: PKG-01; compatibilità finale con tutte le milestone runtime.

I prerequisiti operativi sono quelli nel campo Dependencies; i rinvii a consumer e file condivisi non impongono dipendenze reciproche. Aggiornare test e documentazione pertinente nello stesso task; riportare comandi e output reali prima di Done.

## Scomposizione dell'AC monolitico (2026-09-17)

L'AC1 originale riuniva cinque requisiti eterogenei in una riga sola: versioni dichiarate, artefatti installati, coverage dei subprocess, confinamento delle azioni kill, assenza di sleep come prova di ordinamento. Scomposto in cinque criteri separati senza cancellarne nessuno. Nessun check mark perso perche' l'unico criterio presente era non spuntato.

I criteri 1 e 2 sono la tranche CI corrente. I criteri 3, 4 e 5 passano ai due sottotask nativi creati sotto questo parent. Impegno esplicito registrato: TASK-34 NON va a Done finche' tutti e cinque non sono soddisfatti o esplicitamente ridiscussi. Nessun Done parziale.

## Correzione a un mio reperto errato

Nel piano proposto avevo scritto che nei test non esiste un solo uso di kill. E' FALSO e la fonte dell'errore e' metodologica, non un refuso: avevo cercato le forme di chiamata `.kill()`, `SIGKILL` e `terminate()` e ho dedotto l'assenza da un pattern che non poteva vederla. In questo progetto `kill` e' un kind di azione del vocabolario delle regole, non una chiamata di libreria.

Misurato correttamente, cercando per vocabolario:
- `tests/test_kill.py:9` esegue `run_action` con `action={"kind": "kill", "exit_code": 70}`; `test_kill_uses_os_exit_not_systemexit` alla riga 14 lancia un `mp.Process`, fa `join(5)` e verifica `exitcode == 70`. Quindi il kill E' gia' confinato a un figlio con timeout, il che va verificato e non assunto nel sottotask.
- `tests/test_barriers.py:13` usa `time.sleep(0.1)` fra l'avvio del thread e l'apertura della barriera, che e' esattamente la forma che il criterio 5 nomina.
- Superficie reale: 2 file di test nominano kill (test_kill.py, test_rules.py), 6 nominano sleep (test_actions.py, test_barriers.py, test_docs_rules.py, test_rules.py, test_targets.py, test_activation_atomic.py).

Regola che ne segue e che vale oltre questo task: in un progetto con vocabolario proprio, cercare la forma di chiamata non prova l'assenza del concetto.

## Tranche CI (criteri 1 e 2), 2026-09-17

**Limite dichiarato per primo, perche' e' il piu' facile da perdere: nessuna esecuzione di GitHub Actions e' stata lanciata.** Tutte le prove sotto sono locali. Nessun job remoto e' verde, perche' nessun job remoto e' partito. I criteri 1 e 2 restano NON spuntati per questa ragione sola: l'implementazione c'e' ed e' verificata localmente, e cio' che manca per spuntarli e' il primo run di Actions.

### Cosa e' cambiato

- `.github/workflows/tests.yml` (backup preesistente in `.github/workflows/tests.yml.bak.1789617984`): `fail-fast: false`, `3.14` aggiunto alla matrice, `setuptools` nominato nello step di install, `-rs` su pytest, e un job `artifact` con `needs: test`, `timeout-minutes: 15`, Python 3.14, che NON installa il pacchetto e lancia `python scripts/verify_artifacts.py`.
- `scripts/verify_artifacts.py`, NUOVO: costruisce sdist e wheel da uno snapshot pulito, installa ciascuno in un ambiente separato senza editable e senza il checkout su `sys.path`, verifica la provenienza dell'import dalla directory in cui girera' la suite, ed esegue la suite dalla sdist estratta contro entrambi.
- `pyproject.toml` (backup in `pyproject.toml.bak.1789618608`): una riga, il classifier 3.14, aggiunta dopo aver misurato la suite verde su 3.14.
- `docs/packaging.md`: due sezioni nuove piu' le correzioni della disposition sotto.

NON toccati e verificati per hash: `MANIFEST.in` = `c69612faac49a0a570bf531d28cb74fda888fc9fecce766a7d7acea140fda337`, `tests/test_packaging.py` = `0e0f2ec61ff6548fc5c751632787fe523ae5e08012c86cdbf5afadc09bb08bcd`. Entrambi identici ai valori registrati in TASK-32. `publish.yml` non toccato (TASK-33/108). Nessun commit, nessun push, nessun dispatch.

### Hash dello stato finale

    60de5e10adf39cfbc91d374c87e3ee0058d247b52ca5190fb2fd3cef68315c05  scripts/verify_artifacts.py
    4343ab48c62fcb38c456caa3681e4b878afe2ae519958f1bbfda19b8cd6fd5ac  .github/workflows/tests.yml
    332096c162a1e99f12e0668aeaf94be7970dbce8144cca41c635cc168e778fbb  pyproject.toml
    c8f610aa74395e1a2bd7724ec6d5cb093f1f13218318da411770edcebce911c9  docs/packaging.md

### Prove eseguite, con i comandi

Matrice, 3 leg su 4. Non esiste un interprete 3.13 su questa macchina, quindi quel leg resta non misurato localmente. Per 3.11 e 3.12 l'albero e' stato copiato in `/tmp` prima dell'editable install, perche' `pip install -e .` scrive `src/*.egg-info` nell'albero da cui parte e il checkout e' condiviso con un altro agente.

    pip install -e <tree> pytest setuptools ; pytest -q -rs
    3.11.14  ->  719 passed, 1 skipped
    3.12.12  ->  719 passed, 1 skipped
    3.14.7   ->  719 passed, 1 skipped

Controllo negativo sullo step di install, per stabilire che nominare `setuptools` non e' decorativo. Stesso albero, 3.12, step vecchio senza `setuptools`:

    1 failed, 711 passed, 8 skipped   (exit 1)

Il fallimento e' `test_the_build_checks_cannot_be_disabled_silently`, e i 7 skip in piu' sono esattamente i check di build che sparirebbero in silenzio. Su 3.11 questo non si vedrebbe, perche' li' `ensurepip` impacchetta ancora setuptools: il difetto era invisibile proprio sul leg piu' vecchio.

Artefatti:

    /usr/bin/python3.14 scripts/verify_artifacts.py   ->  exit 0, 11.2s
    sdist: provenienza dentro venv-sdist, 713 passed, 7 skipped
    wheel: provenienza dentro venv-wheel, hook attivazione ok, 713 passed, 7 skipped

I 7 skip qui sono attesi e stampati: la suite gira dentro la sdist estratta, quindi i check di build si disattivano su `PKG-INFO`.

## Disposition della review (simplify a 4 angoli + code-review high effort), 2026-09-17

Tutti i reperti sotto riguardano codice che avevo scritto io in questa tranche. Sono elencati per intero perche' la regola e' che nessuna raccomandazione di review resti fuori da un registro.

### HIGH, riprodotto e corretto

`smoke_the_activation_hook` passava per la ragione sbagliata. Il test era `'sitecustomize' in sys.modules`, che e' vero se `site.py` ha importato un `sitecustomize` top level QUALSIASI. Gli ambienti qui sono costruiti `--system-site-packages` e Debian e Ubuntu ne installano uno in `/usr/lib/python3/dist-packages/sitecustomize.py`. Conseguenza: su un wheel che avesse smesso di spedire `pyteman/sitecustomize.py` il controllo annunciava successo.

Controllo negativo eseguito: wheel installato, `pyteman/sitecustomize.py` cancellato dal purelib, un `sitecustomize.py` estraneo piantato al top level. Il vecchio predicato stampa esattamente la coppia che accettava:

    sitecustomize in sys.modules: True | pyteman in sys.modules: False

Il nuovo controllo confronta `sys.modules['sitecustomize'].__file__` risolto contro `<purelib>/pyteman/sitecustomize.py` risolto, e sullo stesso scenario solleva nominando entrambi i path. Il peso di questo reperto e' alto perche' dentro la sdist estratta i 7 check di `TestBuiltArtifacts` sono skippati su `PKG-INFO`: questo smoke e' l'unica cosa che nel job guarda ancora il wheel.

### MEDIUM, riprodotti e corretti

1. `purelib` e i due booleani venivano letti per posizione da uno stdout in cui `capture` fonde anche stderr. Con un `.pth` rumoroso nella base, `purelib` tornava come stringa di 14 righe e `.split()` sollevava `ValueError: too many values to unpack (expected 2, got 14)`. Ora passano tutti da `echoed_values`, cioe' per nome.
2. `PYTEMAN_RULES` esportato nell'ambiente arrivava ai figli. Misurato con un file inesistente: 72 failed, 641 passed, e nulla nell'output nominava la variabile, perche' i test rifabbricano l'ambiente da `os.environ`. Ora le tre variabili `PYTEMAN_*` sono rimosse da ogni figlio, non semplicemente non impostate.
3. Il check LEAKED era vacuo. La clausola `if p` scartava `''`, che sotto `python -c` e' proprio la working directory che il docstring diceva di sorvegliare. Rimosso; la verifica di provenienza ora si regge su ORIGIN, confrontato con `is_relative_to` invece che per sottostringa.

### LOW, corretti

Marker mancante che dava `out / ""`, cioe' `out` stesso, senza eccezione; contenimento per sottostringa su path; `next(into.iterdir())` senza default ne' ordinamento ne' controllo di tipo; `copytree` che rientra in se' stesso se `TMPDIR` punta dentro il checkout (riprodotto: circa 90 livelli e `[Errno 36] File name too long`); directory di lavoro mai rimossa (206 MB accumulati in otto run, ora rimossa solo in caso di successo, perche' in caso di fallimento serve al post mortem). Aggiunto `--without-pip` agli ambienti: 0.09s contro 3.47s ciascuno, e pip resta raggiungibile dalla base.

### Documentazione corretta

Il conteggio 718 era stale, la suite e' a 719: l'albero ha guadagnato un test. La frase che diceva che lo smoke stabiliva la provenienza "from the installed package" era vera solo dopo la correzione HIGH, e ora lo e'. La giustificazione della doppia estrazione citava il bytecode, che e' sbagliato perche' `PYTHONDONTWRITEBYTECODE=1` fa si' che il primo run non ne scriva: sostituita con la ragione reale, cioe' zero stato condiviso. Chiarita l'ambiguita' fra le due "copie canoniche": il fixture in `tests/test_packaging.py` e' canonico per la BUILD, lo script per la sequenza completa.

### Skippato, con la ragione

Estrarre la ricetta di build condivisa in `tests/_artifact_build.py`. Proposto dall'angolo altitude, analizzato e respinto dall'angolo reuse, e ho seguito reuse: consumare l'helper richiede di modificare `tests/test_packaging.py`, che e' congelato, e estrarlo senza quella modifica produce tre copie invece di due. In piu' un `ImportError` a livello di modulo in un file pytest e' un errore di collection, non uno skip, quindi dentro la sdist estratta (dove `scripts/` non arriva) l'import romperebbe la raccolta.

### Segnalato e NON applicato

Due angoli hanno proposto di togliere `needs: test` dal job `artifact`, per far partire i due job in parallelo e accorciare il feedback. Non l'ho fatto: la forma con `needs: test` e' stata specificata dall'istruzione che governa la tranche, non scelta da me, quindi la decisione non e' mia da ribaltare. Resta qui come reperto aperto per chi ha quell'autorita'.

## Verifica indipendente della tranche CI da parte di un secondo agente, 2026-09-17

Un secondo agente (`pyteman-89`) ha ripetuto la verifica su uno snapshot proprio, senza riusare nulla del mio ambiente. Registrato qui perche' una prova eseguita da chi ha scritto il codice e una prova eseguita da chi non lo ha scritto non hanno lo stesso peso.

Snapshot in `/tmp/pyteman-ci-verification-sz8hxp2z/source`, con gli hash di `src/`, `tests/`, `docs/`, `scripts/`, `.github/` piu' `README`, `pyproject.toml` e `MANIFEST.in` confrontati prima della copia, dopo la copia e dopo l'esecuzione: tutti identici. Questo copre la preoccupazione reale in un checkout condiviso, cioe' che lo script muti l'albero da cui parte.

    /usr/bin/python3.14 scripts/verify_artifacts.py   ->  exit 0
    sdist:  713 passed, 7 skipped, import da venv-sdist
    wheel:  713 passed, 7 skipped, import da venv-wheel, hook identificato e inerte senza env

I numeri coincidono esattamente con quelli che avevo misurato io, inclusi i 7 skip attesi. Lo stato dei quattro file corrisponde agli hash registrati sopra.

### Perche' i criteri 1 e 2 restano NON spuntati

Entrambi sono formulati su cio' che fa la CI: il criterio 1 dice "CI esegue la suite", il criterio 2 dice "CI installa e verifica gli artefatti". Nessun job di GitHub Actions e' mai partito, e il leg 3.13 non esiste su questa macchina e non e' stato misurato in nessun modo. Due verifiche locali indipendenti stabiliscono che l'implementazione e' corretta; non stabiliscono che la CI l'abbia eseguita. Spuntarli adesso significherebbe far dire alla riga una cosa diversa da quella che dice.

Cio' che manca per spuntarli e' esattamente una cosa: il primo run di Actions, piu' il leg 3.13 che solo quel run puo' coprire.

RIEPILOGO AC PER AC DEL PARENT, scritto prima di qualunque cambio di stato e non dopo. Stato dei sottotask locali: TASK-34.1 Done con i suoi quattro AC spuntati, TASK-34.2 Done con i suoi quattro AC spuntati. Stato del parent: resta In Progress.

AC1, matrice CI su Ubuntu e 3.11/3.12/3.13/3.14 con setuptools nominato e -rs. NON spuntato, e la ragione e' precisa: il file che soddisfa questo criterio esiste ma non e' quello che gira. .github/workflows/tests.yml nell'albero di lavoro dichiara le quattro versioni, nomina setuptools nel pip install e passa -rs, ma risulta modificato e non commesso, 90 inserzioni e 3 rimozioni rispetto a HEAD. La versione a HEAD, cioe' l'unica che il remoto abbia mai eseguito, dichiara tre versioni senza 3.14, installa `pip install -e . pytest` senza setuptools ed esegue `pytest -q` senza -rs. Il criterio e' quindi soddisfatto nel testo del file e non nell'esecuzione.

AC2, installazione e verifica degli artefatti in ambienti separati. NON spuntato. Il job `artifact` che chiama scripts/verify_artifacts.py esiste solo nella versione non commessa dello stesso file, quindi non e' mai stato eseguito da nessuna parte fuori da questa macchina.

AC3, test con subprocess e multiprocessing inclusi nella misura di coverage. SPUNTATO, e va letto per cio' che regge: TASK-34.1 ha confermato il meccanismo sullo strumento realmente installato e lo ha dimostrato con un confronto prima/dopo, piu' un controllo che fallisce rumorosamente quando uno dei due canali manca. La prova e' locale. Il job `coverage` che lo eseguirebbe in CI sta anch'esso solo nella versione non commessa del workflow.

AC4, azioni di kind kill confinate a figli e sempre con timeout. SPUNTATO. Un solo call site esegue davvero l'azione, tests/test_kill.py, ed e' stato riscritto con budget nominati, join limitato, kill e reap limitati e un assert finale che nomina il pid superstite invece di lasciarlo muto.

AC5, nessun test che affida un ordinamento a una sleep. SPUNTATO. Le attese su orologio sono state sostituite da segnali osservabili, e le tre attese residue hanno una motivazione scritta sul posto.

Prova fresca presa in questo passaggio per i due criteri spuntati qui: i cinque file del perimetro danno 60 passed, exit 0, e gli hash dei due file runtime sono invariati, actions.py 7880bd0e e barriers.py 064e77c4, quindi nessuna delle spunte poggia su una modifica al runtime.

CORREZIONE A UN'AFFERMAZIONE SCRITTA PIU' VOLTE SOPRA IN QUESTE NOTE, e la correggo dove conta invece di lasciarla in piedi. Sopra si legge 'nessuna esecuzione di GitHub Actions e' stata lanciata' e 'Nessun job remoto e' verde, perche' nessun job remoto e' partito'. Come affermazione generale e' FALSA e l'ho verificata invece di ripeterla. Il workflow `tests` ha girato sul remoto piu' volte e l'ultima e' verde:

    gh run list --limit 5
    completed  success  tests  master  push  35069570388  14s  2026-09-16T07:38:35Z

    gh run view 35069570388 --json jobs
    test (3.11) success | test (3.12) success | test (3.13) success

Cio' che e' vero, ed e' l'affermazione che andava scritta al posto di quella, e' che nulla di questa milestone e' mai stato eseguito dal remoto. Il run verde ha eseguito il workflow a HEAD, non quello dell'albero di lavoro, e contro un albero di test di un'altra epoca. Misura che lo stabilisce, dal log dello stesso run:

    55 passed in 0.76s   (3.13)
    55 passed in 0.69s   (3.11)
    55 passed in 0.78s   (3.12)

Inventario che spiega il 55 contro le centinaia di test locali: a HEAD ci sono 12 file in tests/ per 55 funzioni `def test_`, mentre l'albero di lavoro ne ha 24 per 337 funzioni. Dodici file di test non sono tracciati e sette sono modificati. Quindi il verde remoto non copre 3.11 ne' 3.12 ne' 3.13 per il codice di oggi: copre un quinto scarso delle funzioni di test e nessuno dei file di questa tranche.

Perche' la distinzione e' portante e non pedanteria. Un lettore che guarda il badge vede verde e puo' concludere che la matrice sia coperta. Non lo e'. Il verde e' vero e riguarda un altro albero. Un'affermazione 'mai eseguito' e' comoda perche' nessuno la va a verificare contro un badge; questa formulazione regge anche a chi apre la pagina di Actions. Nessuna spunta cambia per effetto di questa correzione: i criteri 1 e 2 restano NON spuntati, e la ragione resta la stessa, cioe' che il workflow che li soddisfa non e' quello che ha girato.

LACUNE RESIDUE DEL PARENT, elencate perche' restino leggibili senza dover ricostruire nulla, e perche' la decisione di colmarle non e' mia.

1. Il workflow che soddisfa i criteri 1 e 2 non e' commesso. Sono 90 inserzioni sopra HEAD in .github/workflows/tests.yml, piu' scripts/verify_artifacts.py che a HEAD non esiste. Finche' restano non commessi il remoto non puo' eseguirli, qualunque cosa mostri il badge.

2. Python 3.13 non e' misurato localmente sul codice di oggi, e non e' un'omissione recuperabile qui: su questa macchina esiste il solo /usr/bin/python3.14. I leg 3.11 e 3.12 furono misurati su copie in /tmp con interpreti dedicati, 3.14 e' quello di casa, 3.13 non ha interprete. Il 3.13 verde sul remoto e' l'altro albero, quello da 55 test.

3. La piattaforma e' Ubuntu e basta. La matrice dichiara runs-on: ubuntu-latest su tutti i job, quindi macOS e Windows non sono coperti da nessuna parte, ne' localmente (questa e' una Fedora) ne' sul remoto. Non e' un difetto di questa tranche, e' l'estensione reale di cio' che il criterio 1 promette quando dice 'le versioni dichiarate': dichiara versioni, non piattaforme.

NON AUTORIZZATO e non eseguito: nessun commit, nessun push, nessun workflow_dispatch, nessuna esecuzione remota lanciata da me per colmare le tre lacune sopra. L'autorizzazione e' stata negata in modo esplicito e la registro invece di aggirarla. Nessuna delle tre lacune e' quindi colmabile dentro questo task senza una decisione di chi possiede quella leva.

SPUNTE APPLICATE IN QUESTO PASSAGGIO: criteri 3, 4 e 5, che corrispondono uno a uno ai due sottotask chiusi, TASK-34.1 per il 3 e TASK-34.2 per il 4 e il 5, entrambi Done con tutti i loro AC spuntati. I criteri 1 e 2 restano NON spuntati e il parent resta In Progress. Il parent NON va portato a Done in questo stato: mancano due criteri su cinque, e mancano per una ragione che nessuna misura locale puo' rimuovere.

**Correzione misurata 2026-09-17, inventario interpreti.** L'affermazione registrata sopra, cioe' che su questa macchina esiste solo `/usr/bin/python3.14`, e' FALSA e va letta come ritirata. Misurato con `command -v` su PATH invece che con un `ls` di una sola directory: `python3.11` risolve a `/home/pantinor/.local/bin/python3.11`, Python 3.11.14; `python3.12` risolve a `/home/pantinor/.local/bin/python3.12`, Python 3.12.12; `python3.14` risolve al linuxbrew 3.14.7; sono presenti le radici uv `cpython-3.11.14` e `cpython-3.12.12`. `python3.13` e' assente, nessun pyenv.

Il limite vero e' quindi esattamente questo e nessuna generalizzazione oltre: **3.13 non disponibile localmente, quindi non verificato**. 3.11 e 3.12 sono disponibili in locale, coerentemente con il rapporto precedente che citava 719 passed su quegli interpreti.

Causa dell'errore, nominata perche' e' la forma che conta: avevo ispezionato `/usr/bin` e riportato il risultato come se fosse l'inventario della macchina. E' un controllo per procura al posto della misura, sulla stessa riga del difetto che questo tranche esiste per rimuovere.

**Precisazione sul run remoto citato sopra, 2026-09-17.** Il run 35069570388 ha `headSha` **a28b12662a46727ff806a42122db0ffe8333d760**, che e' HEAD attuale di master. L'affermazione che sopravvive e' solo questa: quel run verde copre l'albero committato a28b126, e nessuno dei file non committati di questa tranche.

Ritiro invece il rapporto "un quinto delle funzioni". Confrontare i 55 test raccolti a HEAD con i 337 `def test_` contati nell'albero mette insieme test parametrizzati e funzioni sorgente, che non sono la stessa unita' di misura, e il rapporto che ne esce non e' una metrica di copertura. Nessuna conclusione di questo task poggiava su quel numero: AC1 e AC2 restano aperti per verifica della versione corrente del workflow, non per il rapporto.

## Primo run remoto del workflow di questa tranche, 2026-09-18

La lacuna 1 registrata sopra e' chiusa. Il workflow che soddisfa i criteri 1 e 2 non era commesso, quindi il remoto non poteva eseguirlo; ora lo e' ed e' stato eseguito.

Run **35309543689**, https://github.com/RisorseArtificiali/pyteman/actions/runs/35309543689
SHA **ac3400d9e4e29318d6e130aa45689e4cf1f9e738** su work/verified-progress, parent d7bb762, fast forward verificato con ls-remote prima e dopo. Esito completed / success su tutti e sei i job: test (3.11), test (3.12), test (3.13), test (3.14), artifact, coverage.

Push autorizzato con gate diretto nella mia sessione, non su approvazione riferita da terzi. L'utente ha interrotto una prima volta mentre verificavo i refs, mi sono fermato senza pushare, e ha confermato subito dopo.

### AC1, prova presa dal run e non dall'albero

Il blob del workflow a ac3400d dichiara `python-version: ["3.11", "3.12", "3.13", "3.14"]` alla riga 22, `pip install -e . pytest setuptools` alla riga 35 e `pytest -q -rs` alla riga 47. Le quattro gambe sono partite e sono tutte verdi.

Dal log della gamba 3.13, cioe' quella che nessuna misura locale poteva coprire perche' l'interprete non esiste su questa macchina:

    Successfully installed ... pyteman-0.1.0 pytest-9.1.1 setuptools-84.0.0
    SKIPPED [4] tests/test_report_escaping.py:425: pandoc renders the table; not a test dependency
    781 passed, 8 skipped in 3.71s

Questo stabilisce tre cose separatamente: setuptools e' installato davvero e non solo nominato nel file, `-rs` stampa le motivazioni degli skip, e 3.13 e' stato eseguito sul codice di oggi. I 788 raccolti tornano come 781 piu' 7 skip per pandoc assente piu' 1 per il secondo renderer.

### AC2, prova presa dal job artifact

    == sdist ==
      provenance ok: /tmp/.../venv-sdist/lib/python3.14/site-packages/pyteman/__init__.py
      running the suite from /tmp/.../tests-for-sdist/pyteman-0.1.0
    774 passed, 15 skipped in 11.47s
    == wheel ==
      provenance ok: /tmp/.../venv-wheel/lib/python3.14/site-packages/pyteman/__init__.py
      activation hook loads from the wheel and stays inert without PYTEMAN_RULES
    774 passed, 15 skipped in 9.74s

Due ambienti separati, provenienza dell'import verificata dentro il site-packages di ciascuno e non dal checkout, nessun editable install, suite eseguita dalla sdist estratta contro entrambi. I 15 skip sono 8 attesi piu' 7 check di build che si disattivano su PKG-INFO, esattamente la disposition gia' registrata sopra.

Lo smoke sul wheel e' quello corretto dopo il reperto HIGH: nomina il file caricato invece di accontentarsi della presenza di un `sitecustomize` qualsiasi in sys.modules.

### Job coverage, che non e' un AC ma rafforza l'AC3

L'AC3 era spuntato su prova locale, con la riserva scritta che il job `coverage` esisteva solo nella versione non commessa del workflow. Ora ha girato sul remoto:

    780 passed, 8 skipped, 1 deselected in 13.50s
    TOTAL   1249   52   472   26   95%
    lines that only a child process can execute:
    The suite ran instrumented and both child-only exits were measured.

Le due righe raggiungibili solo da un processo figlio, entrambe terminanti in `os._exit`, sono state misurate e non perse. La riserva sull'AC3 cade: il meccanismo regge anche fuori da questa macchina.

### Stato delle tre lacune residue

1. **Chiusa.** Il workflow e' commesso ed e' stato eseguito dal remoto sul codice di oggi.
2. **Chiusa per la via che restava.** 3.13 non ha interprete su questa macchina e non lo avra'; il run remoto lo copre, 781 passed sul leg 3.13.
3. **APERTA e non toccata.** `runs-on: ubuntu-latest` su tutti i job, quindi macOS e Windows non sono coperti da nessuna parte. Questo NON blocca il parent: l'AC1 dice "Ubuntu, 3.11/3.12/3.13/3.14", quindi promette versioni su una piattaforma e non piattaforme. La lacuna e' reale come estensione della copertura, non come criterio mancante, e resta leggibile qui per chi decidera' se allargare.

Resta aperto anche il reperto segnalato e non applicato sopra, cioe' la proposta di togliere `needs: test` dal job `artifact`. Non e' mia da ribaltare e non l'ho ribaltata.

### Perche' spunto AC1 e AC2 adesso

L'impegno registrato sopra era esplicito: spuntarli su prova locale avrebbe fatto dire alla riga una cosa diversa da quella che dice, perche' entrambi sono formulati su cio' che fa la CI. Quella obiezione e' ora soddisfatta dal fatto e non da un argomento: la CI ha eseguito, sul SHA ac3400d, il workflow che contiene la matrice a quattro versioni, setuptools, -rs e il job artifact. Le prove citate sopra vengono dai log del run, non dall'albero di lavoro.

Con AC1 e AC2 spuntati tutti e cinque i criteri sono soddisfatti, quindi il parent va a Done, coerentemente con l'impegno di non chiuderlo parziale.
<!-- SECTION:NOTES:END -->
