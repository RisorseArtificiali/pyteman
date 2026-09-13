_SAFE = {"len": len, "str": str, "int": int, "float": float, "bool": bool,
         "abs": abs, "min": min, "max": max, "sorted": sorted, "isinstance": isinstance}

def eval_condition(expr, ctx):
    return bool(eval(expr, {"__builtins__": {}}, {**_SAFE, **ctx}))

def eval_key(expr, ctx):
    if not expr:
        return None
    return eval(expr, {"__builtins__": {}}, {**_SAFE, **ctx})
