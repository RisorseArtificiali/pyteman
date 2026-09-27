# Quickstart

A complete path from an installed wheel to an instrumented workload, with
every output below captured from a real run of these exact commands; paths,
patch versions and repeated lines are abbreviated where marked with `...`.
No checkout of this repository is needed past building the wheel, and
nothing about the editable layout must be known: the activation path is
derived from the installed package itself.

## 1. Install the wheel into a fresh environment

How the wheel is built, and the checks it must pass, live in
[packaging.md](packaging.md); this page starts from the built artifact.

```
$ uv venv demo-env --python 3.12
Using CPython 3.12.x
Creating virtual environment at: demo-env
Activate with: source demo-env/bin/activate
$ uv pip install --python demo-env/bin/python pyteman-0.2.0-py3-none-any.whl
 + pyteman==0.2.0 (from file:///.../pyteman-0.2.0-py3-none-any.whl)
 + pyyaml==6.0.3
```

The activation contract is a `sitecustomize` one, and `sitecustomize` must
be importable as a top-level module, so `PYTHONPATH` must name the
directory that contains it. In an installed environment that directory is
the installed `pyteman` package itself, and it is derived, never guessed:

```
$ PKGDIR=$(demo-env/bin/python -c "import pyteman, os; print(os.path.dirname(pyteman.__file__))")
```

which prints `.../demo-env/lib/python3.12/site-packages/pyteman`. The name
collision this `PYTHONPATH` entry creates, what it risks, and why
`sitecustomize` is the only name pyteman itself needs, are in the README's
activation contract.

## 2. The workload and the rules

One module, two functions, no dependencies, in a scratch directory the
marker pins the run to:

```python
# target_demo.py
def checkout(order_id):
    return {"status": "ok", "order": order_id}


def notify(order_id):
    return {"status": "sent", "order": order_id}
```

```yaml
# rules.yaml
- id: fail-third-checkout
  point: target_demo.checkout
  event: entry
  when: "fires >= 3"
  action: {kind: raise, exc: RuntimeError, message: "injected by pyteman"}
  fire: {mode: always}
- id: slow-notify
  point: target_demo.notify
  event: entry
  action: {kind: sleep, ms: 50}
  fire: {mode: always}
```

The third and every later `checkout` call raises an injected
`RuntimeError`; every `notify` call stalls 50 milliseconds at entry.

```python
# run_demo.py
import time

import target_demo

for i in range(1, 5):
    try:
        result = target_demo.checkout(f"order-{i}")
    except RuntimeError:
        result = {"status": "raised"}
    print(f"checkout {i}: {result['status']}")

t0 = time.perf_counter()
target_demo.notify("order-1")
print(f"notify took {time.perf_counter() - t0:.2f}s")
```

Every field these rules use, the values each accepts, and where each
check happens are in [rules.md](rules.md).

## 3. Run instrumented

```
$ touch scratch.marker
$ PYTHONPATH="$PKGDIR" PYTEMAN_RULES=rules.yaml PYTEMAN_LOG=firing.jsonl \
  PYTEMAN_REQUIRE_MARKER=scratch.marker demo-env/bin/python run_demo.py
checkout 1: ok
checkout 2: ok
checkout 3: raised
checkout 4: raised
notify took 0.05s
```

`PYTEMAN_REQUIRE_MARKER` gates activation on a file that must exist,
pinning the run to this scratch directory. The firing log is one JSON
line per record, a `phase: start` before the action and a `phase: end`
after it, joined by `attempt`:

```
{"schema": 2, ..., "rule": "fail-third-checkout", "point": "target_demo.checkout",
 "event": "entry", "phase": "start", "visit": 3,
 "note": "{'kind': 'raise', 'exc': 'RuntimeError', 'message': 'injected by pyteman'}",
 "seq": 1, "attempt": 1}
{"schema": 2, ..., "phase": "end", "attempt": 1, "status": "raised",
 "outcome": "RuntimeError: injected by pyteman", "seq": 2}
{"schema": 2, ..., "rule": "slow-notify", "phase": "start", "seq": 5, "attempt": 5}
{"schema": 2, ..., "phase": "end", "attempt": 5, "status": "slept", "seq": 6}
```

Everything not shown is elided with `...`, including the fourth
checkout's pair at `seq` 3 and 4 and every identity and context field;
[firing.md](firing.md) documents each one and what it promises.

## 4. When a run is not instrumented

Without `PYTEMAN_RULES` the sitecustomize does nothing and says nothing;
the workload runs clean, which is the baseline to compare against:

```
$ PYTHONPATH="$PKGDIR" demo-env/bin/python run_demo.py
checkout 1: ok
...
checkout 4: ok
notify took 0.00s
```

A requested activation that cannot proceed fails closed, before the
workload starts, with the phase named and exit code 2. Here the marker
file is absent:

```
$ PYTHONPATH="$PKGDIR" PYTEMAN_RULES=rules.yaml PYTEMAN_LOG=x.jsonl \
  PYTEMAN_REQUIRE_MARKER=absent.marker demo-env/bin/python run_demo.py
pyteman: refusing to start: marker check: marker file missing: absent.marker
```

And a rule whose point does not exist yet costs exactly that rule, not
the run: the workload executes, every other rule fires, and the exit
report names what never landed. With `point: target_demo.chechout`
(a typo) in place of the checkout rule:

```
$ PYTHONPATH="$PKGDIR" PYTEMAN_RULES=rules-typo.yaml PYTEMAN_LOG=t.jsonl \
  PYTEMAN_REQUIRE_MARKER=scratch.marker demo-env/bin/python run_demo.py
checkout 1: ok
...
checkout 4: ok
notify took 0.05s
pyteman: never landed: rule 'fail-third-checkout' at target_demo:chechout
```

One direction is quieter than all of these and has no command to show: a
workload whose own `sitecustomize` shadows pyteman's runs uninstrumented,
exits 0, and the firing log's absence is the only tell. The README's
activation contract says who wins that collision and how to check.

## Where to go next

The rule vocabulary and where each check happens: [rules.md](rules.md).
The firing log's schema and its identity guarantees: [firing.md](firing.md).
Points on classes, instances and `param:` targets: [targeting.md](targeting.md).
Building and checking the artifacts: [packaging.md](packaging.md).
Development setup, fast checks and the full battery:
[development.md](development.md).
