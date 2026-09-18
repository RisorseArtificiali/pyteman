# The eval namespace is convenience scoping, not a security boundary: rules are trusted operator input.
_SAFE = {"len": len, "str": str, "int": int, "float": float, "bool": bool,
         "abs": abs, "min": min, "max": max, "sorted": sorted, "isinstance": isinstance}

def eval_expr(code, ctx):
    # eval() with DISTINCT globals and locals gives nested code objects
    # (lambda bodies, generator expressions) access to globals only, never to
    # locals: the same rule that keeps a class body's attributes out of a
    # method defined inside it. `ctx` alone as locals left `args`, `kwargs`,
    # `fires`, `result` and `exc` invisible the moment a condition wrapped a
    # name lookup in a lambda or a genexpr.
    #
    # One mapping serves as both, which is what makes a condition mean the
    # same thing wherever a name appears in it. Passing the snapshot as
    # globals and `ctx` as locals would fix the lookup and leave the
    # expression able to contradict itself: a name bound mid-expression by a
    # top-level walrus would land in `ctx`, be visible to flat code, and be
    # invisible to a lambda or genexpr in the same expression, which reads
    # globals. Worse, it would not even be invisible consistently, since PEP
    # 709 inlines list/set/dict comprehensions into the enclosing scope from
    # Python 3.12, so a comprehension would see the binding and a genexpr
    # beside it would not, and that split moves with the interpreter version.
    #
    # The mapping is built once per evaluation, not once per call: a gated
    # rule builds one for `when` and a second for `fire.key`. So no evaluation
    # IMPLICITLY sees another's bindings, on this call or on any other thread.
    # That is a guarantee about SCOPE, and about scope alone. `eval` returns
    # the expression's value, and a generator or a lambda IS a value, so one
    # that escapes holds this mapping for as long as it stays alive. `when`
    # does not retain the value it returns, and `_check_once_per_key` rejects
    # generator and function keys, but a condition can still stash a closure
    # into an object reachable from `ctx`, and a later condition can then call
    # it, on another call and from another thread; that is probed, not
    # assumed. None of this is a lifetime or an isolation guarantee.
    # What it costs is the one
    # write-through this used to allow: a rule's own top-level walrus no
    # longer rebinds `ctx`, so it can no longer edit what the rules after it
    # on the same call read out of `args`, `result` or `exc`. That path was a
    # hole, not a feature (see the clobber/reader test in
    # test_activation_atomic.py, whose docstring named closing it as the
    # remaining work), and conditions are questions about a call, not edits to
    # it. Nothing here is deep-copied: the mapping holds the same
    # `args`/`kwargs` OBJECTS `ctx` does, so a condition that mutates one of
    # those in place still reaches the call. Rebinding a NAME is what stops.
    ns = {**_SAFE, **ctx, "__builtins__": {}}
    return eval(code, ns, ns)
