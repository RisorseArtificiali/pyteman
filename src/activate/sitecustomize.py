# src/activate/sitecustomize.py
#
# Activation shim for pyteman.
#
# Put THIS directory on PYTHONPATH rather than src/pyteman, so that only
# sitecustomize is importable as a top-level module and the workload's own
# module names (rules, targets, actions, conditions, firing) are never
# shadowed by pyteman's internal modules.
#
# pyteman itself resolves via the editable install (or pip install).
#
# Inert path (no PYTEMAN_RULES): imports only os, touches nothing else.
# Active path: loads the real sitecustomize.py by absolute path, so the
# import does not go through the pyteman package namespace and cannot be
# intercepted by a package of the same name earlier on sys.path.
import os

_rules = os.environ.get("PYTEMAN_RULES", "").strip()
if _rules:
    import importlib.util
    import sys

    _here = os.path.dirname(os.path.abspath(__file__))
    _real = os.path.join(_here, os.pardir, "pyteman", "sitecustomize.py")
    try:
        _spec = importlib.util.spec_from_file_location("_pyteman_activate", _real)
        if _spec is None or _spec.loader is None:
            raise ImportError(f"cannot locate {_real}")
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
    except BaseException:
        try:
            sys.stderr.write(
                "pyteman: refusing to start: loading activation shim:"
                f" could not load {_real}\n")
            sys.stderr.flush()
        finally:
            os._exit(2)
    sys.modules[__name__] = _mod
    _mod._main()
del _rules
