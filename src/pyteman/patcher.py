import builtins
import functools
import sys

from pyteman.actions import run_action
from pyteman.conditions import eval_condition, eval_key

_NO_OVERRIDE = object()

class Patcher:
    def __init__(self, rules, log):
        self.rules = rules
        self.log = log
        self.applied = []
        self._orig_import = None
        self._wrapped = []

    def force_patch_module(self, modname):
        mod = sys.modules.get(modname)
        if mod is not None:
            self._patch(mod, modname)

    def _patch(self, mod, modname):
        for rule in self.rules:
            if rule.module != modname:
                continue
            parts = rule.symbol.split(".")
            container = mod
            for part in parts[:-1]:
                container = getattr(container, part, None)
                if container is None:
                    break
            if container is None or not hasattr(container, parts[-1]):
                continue
            name = parts[-1]
            original = getattr(container, name)
            wrapper = self._make_wrapper(rule, original)
            setattr(container, name, wrapper)
            self._wrapped.append((container, name, original))
            self.applied.append(f"{modname}:{rule.symbol}")

    def _make_wrapper(self, rule, original):
        state = {"fires": 0, "seen_keys": set()}

        @functools.wraps(original)
        def wrapped(*args, **kwargs):
            ctx = {"args": args, "kwargs": kwargs, "fires": state["fires"]}
            if rule.event == "entry" and _gate(rule, state, ctx):
                run_action(rule, ctx, log=self.log)
            if rule.event == "entry" and "_override" in ctx:
                return ctx["_override"]
            result = None
            exc = None
            try:
                result = original(*args, **kwargs)
            except BaseException as e:
                exc = e
                raise
            finally:
                if rule.event == "exit":
                    ctx["result"] = result
                    ctx["exc"] = exc
                    if _gate(rule, state, ctx):
                        run_action(rule, ctx, log=self.log)
            override = ctx.get("_override", _NO_OVERRIDE)
            return override if override is not _NO_OVERRIDE else result

        wrapped._pyteman_state = state
        return wrapped

    def install_hook(self):
        orig = builtins.__import__

        def hooked(name, *a, **k):
            mod = orig(name, *a, **k)
            target = sys.modules.get(name)
            if target is not None:
                self._patch(target, name)
            return mod

        self._orig_import = orig
        builtins.__import__ = hooked

    def uninstall(self):
        if self._orig_import is not None:
            builtins.__import__ = self._orig_import
            self._orig_import = None
        for container, name, original in reversed(self._wrapped):
            setattr(container, name, original)
        self._wrapped.clear()


def _gate(rule, state, ctx):
    state["fires"] += 1
    ctx["fires"] = state["fires"]
    mode = rule.fire.get("mode", "always")
    pending_key = None
    if mode == "countdown":
        n = int(rule.fire.get("n", 1))
        if state["fires"] != n + 1:
            return False
    elif mode == "once_per":
        pending_key = eval_key(rule.fire.get("key"), ctx)
        if pending_key in state["seen_keys"]:
            return False
    if rule.when and not eval_condition(rule.when, ctx):
        return False
    if mode == "once_per":
        state["seen_keys"].add(pending_key)
    return True


def install(rules, log=None):
    p = Patcher(rules, log)
    p.install_hook()
    return p
