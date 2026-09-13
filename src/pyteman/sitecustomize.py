# src/pyteman/sitecustomize.py
import os
import sys

def _main():
    rules_path = os.environ.get("PYTEMAN_RULES", "").strip()
    if not rules_path:
        return  # INERT: no env, no effects
    marker = os.environ.get("PYTEMAN_REQUIRE_MARKER", "").strip()
    if marker and not os.path.isfile(marker):
        sys.stderr.write(f"pyteman: refusing to start: marker file missing: {marker}\n")
        sys.stderr.flush()
        # sys.exit(2) is swallowed here: an exception escaping sitecustomize
        # during startup hits init_import_site, which exits 1 regardless of
        # the code. Hard-exit so the refusal status survives.
        os._exit(2)
    from pyteman.rules import load_rules
    from pyteman.patcher import install
    from pyteman.firing import open_log
    rules = load_rules(rules_path)
    log = open_log(os.environ.get("PYTEMAN_LOG", "pyteman.log"))
    patcher = install(rules, log=log)
    for rule in rules:
        patcher.force_patch_module(rule.module)
    sys._pyteman = {"patcher": patcher, "log": log}

_main()
