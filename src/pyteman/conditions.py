# The eval namespace is convenience scoping, not a security boundary: rules are trusted operator input.
_SAFE = {"len": len, "str": str, "int": int, "float": float, "bool": bool,
         "abs": abs, "min": min, "max": max, "sorted": sorted, "isinstance": isinstance}
_EVAL_GLOBALS = {"__builtins__": {}, **_SAFE}

def eval_expr(code, ctx):
    return eval(code, _EVAL_GLOBALS, ctx)
