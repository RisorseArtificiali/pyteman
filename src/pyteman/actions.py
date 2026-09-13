# minimal for this task; later tasks extend
def run_action(rule, ctx, log=None):
    if log is not None:
        log.record(rule, ctx, note=str(rule.action))
    kind = rule.action["kind"]
    if kind == "return_value":
        ctx["_override"] = rule.action.get("value")
        return
    if kind == "return_none":
        ctx["_override"] = None
        return
    raise NotImplementedError(f"action kind {kind} lands in tasks 4-5")
