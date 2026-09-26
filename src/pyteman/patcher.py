import builtins
import functools
# At module level, and it has to be. The hook calls _patch on EVERY __import__,
# a cached module included, so an `import inspect` inside the per-slot loop
# re-enters _patch for module `inspect`. Pass 1 indexes only rules whose module
# is the one being imported, so that re-entry is normally a cheap no-op and
# returns before the per-slot loop; it recurses to RecursionError exactly when
# the ruleset also names `inspect`, which is a ruleset an operator is entitled
# to write. Verified by putting the import back in the loop and activating such
# a rule. A per-slot import therefore has to go, and this line is what lets the
# check run without one. It is imported before activate() installs the hook, so
# it costs no re-entry of its own.
import inspect
import sys
import threading
import types

from pyteman.actions import run_action
from pyteman.conditions import eval_expr
from pyteman.rules import RuleError, _EVENTS
from pyteman.targets import parse_target_spec

_NO_OVERRIDE = object()
# Told apart from a rule that legitimately returns None, and from an attribute
# whose value is None, which is why neither of those can serve as the signal.
_ABSENT = object()


def _compile(rule, field, source):
    """One rule expression, compiled, with the rule named if it will not.

    Rules reaching the patcher have usually been through load_rules, which
    compiles the same two fields; rules built by hand through the programmatic
    API have not. Compiling them here anyway is what makes activation atomic:
    see Patcher.__init__.
    """
    if not source:
        return None
    # Read once, before the try, and reused by the handler below. Both sites
    # name the rule, and `_text(rule.id)` would do the attribute access as an
    # argument: an id that raises on read replaced "when is not a valid
    # expression" with an unrelated RuntimeError, and in the handler it did so
    # while a SyntaxError was already being reported. See _rule_id.
    rid = _rule_id(rule)
    try:
        return compile(source, f"<pyteman:{rid}:{field}>", "eval")
    except SyntaxError as exc:
        raise RuleError(f"rule {rid!r}: {field} is not a valid "
                        f"expression: {exc.msg}") from None


def _typename(obj):
    """The type name of anything, including objects whose type resists being asked.

    Separate from _text, and taking the OBJECT rather than the name, because
    `_text(type(obj).__name__)` would evaluate the attribute access as an
    argument, before the protection is entered. That is the same evaluation-order
    trap these helpers exist to close, and it is easy to write by accident.

    The type check guards the other half. A metaclass may expose __name__ as a
    property, so the lookup can succeed and return an object that raises when
    rendered, which would make this helper the source of the failure it exists
    to absorb, _text's fallback branch included. `type(name) is str` rather than
    isinstance, because a str SUBCLASS is exactly the shape that passes an
    isinstance check and then runs its own __repr__ or __format__ when the
    caller interpolates it.
    """
    try:
        name = type(obj).__name__
    except BaseException:
        return "<unknown type>"
    return name if type(name) is str else "<unknown type>"


def _owner_name(obj):
    """What to call the thing an attribute was set ON, in a rollback note.

    _typename answers "what type is this", which is the right question about an
    exception and the wrong one about a container. A rule's container is nearly
    always a class or a module, and the type of a class is `type`, so the notes
    came out as `type.m` and `module.f`: the single fact the note exists to
    carry, WHICH callable is still wrapped, was the part it dropped. Only an
    instance container rendered usefully, and that is the rare shape.

    Classes and modules carry their own __name__, so ask the object first and
    fall back to its type for an instance, which has none. Guarded like
    _typename and for its reasons: the attribute access is user code, and a
    __name__ that is a str SUBCLASS would run its own __format__ where the
    caller interpolates this.
    """
    try:
        name = obj.__name__
    except BaseException:
        return _typename(obj)
    return name if type(name) is str else _typename(obj)


def _text(obj):
    """str() that cannot raise, returning an EXACT str.

    Everything the rollback path reports arrives from user code: the container,
    the exception its setattr raised, and that exception's message. __str__ is
    user code, so rendering it while an exception is being unwound can raise a
    SECOND exception out of the reporting, and the reporting must not be able
    to cause the failure it reports.

    Not raising is only half of what the callers need; the other half is that
    the RESULT is inert. str() accepts a str subclass from __str__ and hands it
    back unchanged, and a subclass carries its own __repr__ and __format__, so
    an f-string interpolating this value would run user code after all. The
    normalisation below is what lets every caller interpolate, repr and format
    the result freely, which is a property of the value rather than a rule each
    call site has to remember.
    """
    try:
        s = str(obj)
    except BaseException:
        # Concatenation, not an f-string: safe by construction rather than by
        # _typename keeping its own promise.
        return "<unprintable " + _typename(obj) + ">"
    return s if type(s) is str else str.__str__(s)


def _rule_id(rule):
    """One rule's id, as an inert str, or a placeholder when it will not be read.

    _text guards str(); it cannot guard the ATTRIBUTE ACCESS that produces its
    argument, because an argument is evaluated before the callee is entered. A
    Rule built through the programmatic API has never been past load_rules, so
    its `id` is whatever the caller put there, up to a property that raises on
    read. Every site that NAMES a rule goes through here, so that hazard is
    closed once rather than remembered at each call. The preflight gate in
    Patcher.__init__ is the one read that guards itself instead, because it has
    to tell an id that will not read apart from one that reads as this
    placeholder, and it refuses the first rather than reporting it.

    A rule that will not say what it is called is a diagnostic problem HERE,
    never a reason to fail: the placeholder still tells the operator a rule was
    reached. That is a promise about reporting, and only about reporting. Such
    a rule never reaches a run to be reported on, because Patcher.__init__
    refuses it at preflight; what the placeholder serves is the message
    announcing that refusal, which has to name a rule whose name will not read.
    """
    try:
        return _text(rule.id)
    except BaseException:
        return "<unreadable id>"


def _describe_rule(rule):
    """One rule's identity, rendered once, where a failure to render costs nothing.

    Built in Patcher.__init__ and carried in the plan, rather than composed in
    the except handler that reports it. _text guards str(), which is only half
    the exposure: `_text(rule.id)` does the ATTRIBUTE ACCESS as an argument, so
    a rule whose `id` is a property that raises takes the reporting down before
    _text is entered. In the handler that meant the RuntimeError from reading
    the id replaced the failure the operator has to act on, and the rollback
    disclosure below it never ran, which is the exact substitution _restore is
    written to prevent.

    Rendering here closes it for every note built from a rule, not just the one
    that was reported: __init__ mutates nothing, so there is no unwind in
    progress and no partial instrumentation for a failure to corrupt. The
    handler is left concatenating a string that is already a str.

    The guard is still here because a rule that cannot describe itself is a
    diagnostic problem, not a reason to refuse a ruleset that is otherwise
    sound. What it must not do is fail later, in the one place that cannot
    afford it.

    Two degradations rather than one, because three independent reads under a
    single handler produce a note coarser than the failure. `id` goes through
    _rule_id, so a rule whose id will not be read still says which module and
    symbol it was aimed at, which is what the operator greps their ruleset for;
    only a module or symbol that refuses costs the location. One raising
    attribute used to discard the two that read cleanly.
    """
    rid = _rule_id(rule)
    try:
        return f"rule {rid!r} at {_text(rule.module)}:{_text(rule.symbol)}"
    except BaseException:
        return f"rule {rid!r}, whose module and symbol could not be read"


def _owns_name(container, name):
    """Is `name` in the container's OWN namespace, or reached some other way?

    _patch gates on hasattr, which walks the MRO, so a rule naming an inherited
    method patches a subclass that never defined it and the setattr CREATES the
    name there. Putting the original back with setattr would make that entry
    permanent: the subclass stops inheriting the name forever, silently, and
    later edits to the base stop reaching it. The undo for those is delattr,
    and this is the question that tells the two cases apart.

    A False answer means only "not in __dict__", which is weaker than
    "inherited": a data descriptor on the type, a __slots__ member or a
    property, holds the container's OWN storage without appearing there. That
    is why _undo_one asks this a second time at undo time rather than trusting
    the recorded answer alone. Recording it at patch time is still necessary,
    since the MRO can change in between; what the second ask adds is that
    delattr runs only while our wrapper is demonstrably in the __dict__, which
    is the only state it is correct for.
    """
    try:
        return name in vars(container)
    except BaseException:
        # No readable __dict__, or one that refuses. Claim ownership, which
        # keeps the plain setattr: inventing a delattr against a namespace we
        # could not read is the destructive direction to be wrong in.
        return True


def _is_pyteman_hook(fn):
    """Is `fn` the LIVE hook of some Patcher, ours or another's?

    The marker alone is not the question. install_hook stamps it and uninstall
    never clears it, because the closure may by then be reachable only from
    inside a third party's chain, so a retired hook carries the stamp forever.
    Answering on the stamp alone would refuse an uninstall on behalf of a
    Patcher that has already left, and nothing could ever clear the refusal:
    that Patcher's `_hook` is None, so its own uninstall is a no-op. The outer
    Patcher would be wedged, wraps and all, since the refusal precedes them.

    Asking the owner whether this is still its hook is the whole fix, and it
    also disposes of anything that synthesises attributes on demand. A
    MagicMock standing in for __import__ answers the stamp with a child mock;
    it does not answer `owner._hook is fn`, so it is classified as the stranger
    it is and left alone.

    Guarded because `fn` is whatever sits in builtins.__import__ by the time
    this is asked, and a __getattr__ that raises must not turn the question
    into the failure. Unanswerable reads as "not ours", which routes the
    caller to the conservative branch that leaves the hook alone.
    """
    try:
        owner = getattr(fn, "_pyteman_patcher", None)
        return owner is not None and owner._hook is fn
    except BaseException:
        return False


def _live_dispatcher_owner(fn):
    """The Patcher still dispatching on `fn`, or None if nobody is.

    The question _is_pyteman_hook asks about the import hook, asked about an
    attribute, and it has to be asked the same way for the same reason. A stamp
    alone is a claim about the past. uninstall cannot strip the marker off a
    dispatcher a third party may by then be holding, so a retired dispatcher
    would answer "mine" forever and a Patcher that had already left would lock
    every later one out of the slot, with nothing able to lift the refusal.

    Asking the owner whether the dispatcher is still in its ledger turns the
    label into a live relationship. It retires itself the moment uninstall
    consumes the entry, and it stays true when uninstall was REFUSED on that
    slot and the entry is held back for a retry, which is exactly the state
    where the dispatcher really is still live and really is still owned.

    Guarded, and unanswerable reads as "nobody". `fn` is whatever the target
    program has in that attribute, including objects that synthesise attributes
    on demand: a MagicMock answers the stamp with a child mock and cannot answer
    the ledger lookup, so it is classified as the stranger it is.
    """
    try:
        owner = getattr(fn, "_pyteman_owner", None)
        if owner is None:
            return None
        # The in-flight map first, because the ledger cannot answer for a
        # dispatcher whose _patch call has not reached its publish yet, and that
        # call is exactly the one that can re-enter and ask.
        if owner._inflight.get(id(fn)) is fn:
            return owner
        for _, _, _, wrapper, _ in owner._wrapped:
            if wrapper is fn:
                return owner
    except BaseException:
        return None
    return None


def _undo_one(entry):
    """Settle one slot. Returns an unrendered refusal triple, or None.

    Three outcomes, and only one of them is a failure. The slot still holds OUR
    wrapper, so the original goes back: by delattr in the one case where the
    patch CREATED the name in the container's own namespace (see _owns_name),
    and by setattr everywhere else. Or the slot holds something else, because a
    third party replaced our wrapper after we installed it: the foreign object
    is left exactly where it is and the entry is dropped. That is a successful
    RELEASE of ownership rather than a refusal, and reporting it through the
    refusal channel would tell the operator a rollback failed when the truth is
    the opposite. Or the container refuses, which is the one real failure, and
    it is returned rather than raised so the loop above can finish.

    Identity, not `_pyteman_state`: every wrapper this module builds carries
    one, so with two Patchers live each would read the other's wrapper as its
    own and overwrite it. The ledger records the exact wrapper it installed for
    this reason, and `is` against that is the only question with a true answer.

    The handler sits here, around a single slot, because the caller runs this
    while another exception is being unwound. A container that refuses setattr
    must not become the exception the operator sees: that would replace "rule
    'bad': when is not a valid expression" with an unrelated failure from the
    cleanup, and the run would be refused for a reason nobody can act on.
    Callers surface what is returned here alongside the original, never instead
    of it.

    BaseException rather than Exception, because a KeyboardInterrupt arriving
    between two settled slots would otherwise leave exactly the half-restored
    module this exists to prevent.
    """
    container, name, original, wrapper, owned = entry
    try:
        if getattr(container, name) is not wrapper:
            return None
        # `owned` says the name was the container's own at patch time; this
        # asks again, because delattr is only ever right when our wrapper is
        # really sitting in the container's __dict__. A name can be absent from
        # there and still be the container's own storage, held by a data
        # descriptor: a __slots__ member, or a property with a setter. For
        # those, deleting would clear the slot and take the original with it,
        # or raise for want of a deleter, where a plain setattr restores them.
        if owned or not _owns_name(container, name):
            setattr(container, name, original)
        else:
            delattr(container, name)
    except BaseException as exc:
        return (container, name, exc)
    return None


def _restore(entries):
    """Undo wraps newest-first, best effort, and report what refused.

    Best effort rather than always completing: a ledger that shrinks BELOW the
    cursor while this walks it, something only a concurrent or re-entered
    uninstall can do, raises at the read that opens the next pass. activate()
    is written for that and catches it. What the loop does guarantee is that no
    container's refusal stops it, because each slot is settled under its own
    handler (see _undo_one).

    Nothing here is RENDERED, and that is structural rather than tidy. The
    refusals are returned as objects and described by _disclose once the loop
    is over. Describing them in the handler ran __str__ and __repr__, which are
    user code, from inside the one handler written to keep the loop going: a
    hostile object aborted the loop at whatever entry it had reached and
    stranded every entry after it. Attempting and describing are now separate
    steps, so the completion of the first cannot depend on the second.

    `entries` is CONSUMED: an entry is dropped only when the slot it names is
    SETTLED, meaning put back or released, so what survives the call is what is
    still wrapped, exactly while this call is the only writer. Consuming is
    here rather than in the callers because both of them used to discard the
    ledger on the assumption the undo worked, and a refused restore is the case
    where it did not. A wrap nobody records is a wrap nobody can remove, and
    uninstall() then reports success with nothing to do while an instrumented
    callable stays in the process. Keeping the two facts in one place means a
    third caller cannot get the pairing wrong.

    Descending index rather than `reversed`, which is the same newest-first
    order and additionally makes THIS loop's deletions safe: removing at i
    cannot shift any index below i, so the walk never skips an entry. That
    argument covers the deletes made here and nothing else, because settling a
    slot runs user code that can remove entries BELOW i. What the guard on the
    delete buys, and the wasted read it costs, is derived once in
    docs/rules.md under the thread-safety limit rather than a second time here;
    the short version is that nothing still wrapped is forgotten.
    """
    refused = []
    for i in range(len(entries) - 1, -1, -1):
        entry = entries[i]
        refusal = _undo_one(entry)
        if refusal is not None:
            refused.append(refusal)
        elif i < len(entries) and entries[i] is entry:
            # `is`, not `==`: comparing the tuples would run the container's
            # __eq__, putting user code back inside the loop written to survive
            # it. The bounds test covers a shrink to exactly i; a deeper one
            # raises at the read that opens the next iteration, not here.
            del entries[i]
    return refused


def _note(exc, text):
    """Attach context to an exception without any chance of replacing it.

    add_note is available on every interpreter this project supports (3.11+)
    and accepts any exception instance, including builtins. The guard is for the
    one shape that rejects it: a subclass shadowing __notes__ with something
    that is not a list, where add_note raises from inside an except block. That
    is the substitution the rollback path is written to avoid, so it cannot be
    allowed in by the code doing the avoiding.
    """
    try:
        exc.add_note(text)
    except BaseException:
        pass


# The wording is a contract: docs/rules.md quotes it and the tests match on it.
# Named because _disclose both writes it and reads it back to recognise its own
# earlier notes, and those two uses have to stay the same string.
_ROLLBACK = "pyteman: rollback could not restore "

# The advice half of both refusals that mean "something of ours is already
# there". A second Patcher over a live dispatcher and a second Patcher's hook
# over ours are the same situation at two altitudes, and an operator reading
# either one has the same next move, so the sentence telling them so is written
# once. Leading separator included: the two callers build different first
# halves and neither should be deciding punctuation.
_RETRY_AFTER_UNINSTALL = "; uninstall it first, then retry this one"

# The reservation refusal needs the opposite advice. Nothing is installed on
# that slot by the call being refused, and the call holding it releases when it
# unwinds, so there is no wrap to uninstall and telling an operator to look for
# one sends them after a patch that does not exist.
_RETRY_WHEN_SETTLED = ("; the reservation is dropped when that call finishes,"
                       " so retry this one, or serialise installs on this slot")


# One install per slot at a time, across every Patcher in the process.
#
# The hazard is not two Patchers racing the `setattr`. It is a stale ownership
# read: the decision to install is taken from a read of the slot, and between
# that read and the write, `setattr` and every check before it run target code.
# A second installer landing in that window is invisible to a decision already
# made, so both calls install, one dispatcher is overwritten while its Patcher
# still names the slot in `applied`, and that Patcher's rules stop firing with
# nothing reporting it. The reservation is what makes the read the decision
# rests on still true at the write.
#
# Keyed by the identity of the slot rather than by its name: a module can be
# reached under two names and a class under none, and `modname:symbol` does not
# identify a container. `id()` is used rather than the container itself so the
# registry never keeps a target alive. What keeps an id from being recycled
# under a live entry is not the entry being brief: a call patching many slots
# holds every reservation it has taken until the whole call unwinds. It is that
# the slot list this loop walks holds `slot.container` strongly for the
# duration of that call, so a reserved container cannot be collected while its
# key is live. That is the argument a change to the release point has to keep.
_SLOT_RESERVATIONS = {}

# A real lock, not the atomicity of a single `dict` method. `setdefault` is
# atomic on this interpreter, but the library FAQ's list of atomic operations
# does not include it, and the free-threading HOWTO says the thread-safety of
# built-in containers is "a description of the current implementation, not a
# guarantee of current or future behavior" and recommends a lock instead. It is
# held across the registry read, the check and the registry write, and NEVER
# across `getattr`, `setattr` or anything else that can run target code.
_RESERVATION_LOCK = threading.Lock()


def _reservation_key(container, name):
    """The registry key, built out of exact builtins only.

    Both halves are hashed while the lock is held, so a key carrying a target
    object, or a `str` subclass with a Python `__hash__`, would run target code
    under the lock. `str.__str__` is used rather than `str()` because a
    subclass can override `__str__` and answer with a different name; the
    argument is read, never mutated.
    """
    if type(name) is not str:
        name = str.__str__(name)
    return (id(container), name)


def _reserve_slot(key, owner, ident, token):
    """Take the slot for this owner on this thread, or answer False.

    Same owner on the same thread is admitted, which is what keeps a re-entrant
    patch working: an import fired from inside `setattr` runs on this stack and
    is this call continuing, not a competitor. Same owner on ANOTHER thread is
    refused, because one Patcher patching one slot from two threads produces
    two ledger entries on one slot exactly as two Patchers do. Ownership is
    asked by identity and the thread by int comparison, so no `__eq__` written
    by anyone else runs under the lock.
    """
    with _RESERVATION_LOCK:
        held = _SLOT_RESERVATIONS.get(key)
        if held is None:
            _SLOT_RESERVATIONS[key] = (owner, ident, token)
            return True
        held_owner, held_ident, _held_token = held
        return held_owner is owner and held_ident == ident


def _release_slot(key, token):
    """Drop this call's reservation, and only this call's.

    Matched on the token rather than on the owner, so a nested call by the same
    owner on the same thread, which `_reserve_slot` admits without storing
    anything, cannot release the outer call's reservation when it unwinds.

    `held` keeps the popped value alive until after the lock is released: it is
    the same tuple `pop` returns and it is never deleted, so the last reference
    to a Patcher cannot be dropped inside the `with` and no finalizer of its
    runs under the lock.
    """
    with _RESERVATION_LOCK:
        held = _SLOT_RESERVATIONS.get(key)
        if held is not None and held[2] is token:
            _SLOT_RESERVATIONS.pop(key)


def _disclose(exc, refused):
    """Say which wraps could not be undone, on the exception being raised.

    The single place that wording is built. _patch discloses the module it was
    working on and activate() the modules it unwinds from outside, and the
    string is a contract: docs/rules.md quotes it and the tests match on it, so
    two copies would be two things to keep in step with three readers.

    The rendering sits inside the guard rather than in the argument to _note,
    which is the same trap this whole path is written around. A refusal whose
    text cannot be produced is still counted, because how many callables were
    left wrapped is the part the operator cannot guess.

    A strand already disclosed on this exception is not disclosed again. Since
    _restore keeps what it could not restore, a strand survives in the ledger
    and the next unwind retries and re-refuses it, so activate() reports what
    _patch already reported and the operator reads one stranded callable as
    two. The matching is per STRAND rather than per note, because the two
    disclosures rarely cover the same set: _patch names the module it was
    working on, activate() names everything still wrapped, and that is a
    superset whenever an earlier module refuses as well. Comparing whole notes
    sees two different strings there and attaches both, naming the shared
    strand twice, which is the case this guard exists to prevent.

    Previous strands are recovered by splitting on the separator this function
    itself wrote, so the comparison is exact rather than a substring search
    that could suppress a real strand whose rendering sits inside another's. A
    rendered message containing the separator splits wrongly and the strand is
    disclosed a second time; that direction is deliberate, because a repeated
    strand is visible to whoever reads the notes and a suppressed one is not.

    The scan is guarded because it is not the string work it looks like:
    reading __notes__ and iterating it both run whatever the exception's author
    put there.
    """
    if not refused:
        return
    try:
        fresh = [f"{_owner_name(container)}.{_text(name)}: "
                 f"{_typename(exc_)}: {_text(exc_)}"
                 for container, name, exc_ in refused]
    except BaseException:
        # Nothing identifiable survived, so there is nothing a previous
        # disclosure could be matched against. Say how many and let it stand.
        _note(exc, _ROLLBACK + f"{len(refused)} attribute(s), and the details "
                               f"would not render")
        return
    already = set()
    try:
        for previous in getattr(exc, "__notes__", ()):
            if type(previous) is str and previous.startswith(_ROLLBACK):
                already.update(previous[len(_ROLLBACK):].split("; "))
    except BaseException:
        pass
    fresh = [strand for strand in fresh if strand not in already]
    if not fresh:
        return
    _note(exc, _ROLLBACK + "; ".join(fresh))


class UninstallOrderError(RuntimeError):
    """uninstall() was called on a Patcher another Patcher is hooked over.

    Nesting is supported LIFO only, and out of order is a REFUSAL rather than a
    silent abstention, because abstaining does not work. Two Patchers hooked in
    turn leave h2 over h1 over the real __import__, each holding the callable
    it displaced. If the outer one unwinds first it can only overwrite h2,
    dropping the inner Patcher's hook, or stand down; and if it stands down the
    inner one later restores what IT saved, which is h1, putting back the hook
    of a Patcher that already uninstalled. Refusing is the only outcome that
    leaves neither a dropped hook nor a resurrected one.

    Raised before anything is mutated, so a refused uninstall is a no-op the
    caller can retry: unwind the inner Patcher and the outer one becomes
    uninstallable again.
    """


class SlotOwnershipError(RuntimeError):
    """_patch reached an attribute a dispatcher it cannot join already serves.

    Composition is per Patcher. One dispatcher serves every rule of ONE ruleset
    on one attribute, in ruleset order, and a second Patcher arriving on that
    attribute has no such order to join. Both alternatives to refusing are
    wrong. Wrapping over the live dispatcher nests the attribute, and the undo
    ledger keys ownership on the exact wrapper object, so whichever Patcher
    unwinds second writes the `original` it saved over whatever is live by then,
    which is either the other Patcher's dispatcher or a callable it has already
    put back. Skipping is what this code did before RT-02: the second Patcher
    recorded nothing in `applied`, published an empty ledger, and returned
    success on instrumentation that was never installed.

    One Patcher can reach the same impasse without a second Patcher, which is
    the other place this is raised. The callable and suspendable checks in pass
    2 run target code that can import an instrumented module, so _patch
    re-enters, and whatever that nested work does to the attribute lands while
    a dispatcher for it is already built. When the thing now in the slot is
    this Patcher's own the two are reconcilable and the caller stands down;
    when it is a stranger's, the wrapper in hand was built over a callable no
    longer there and installing it would erase an object nothing recorded.

    Refusing says the true thing to the only actor who can act on it. Raised
    from inside _patch, so its handler rolls back the wraps of THIS call and
    leaves instrumentation it found in place exactly as it was found.
    """


class OncePerKeyError(RuntimeError):
    """A once_per rule produced a key the firing contract does not accept.

    once_per has to decide, atomically, whether this key has already been seen.
    Membership and insertion are the decision, and both of them RUN THE KEY's
    own `__hash__` and `__eq__`. A key is whatever the operator's `key:`
    expression evaluates to, so those two methods are operator code, and holding
    the rule's lock across them would hand an arbitrary object the power to
    block every other thread on this rule: not by being slow, but by waiting on
    a thread that is itself waiting for the lock. An RLock does not help, since
    the deadlock that matters is a wait on ANOTHER thread rather than a
    re-entry by this one.

    So the keys are restricted instead, to the exact builtin immutable types and
    recursive tuples of them, whose `__hash__` and `__eq__` are C code that
    cannot re-enter the interpreter. Subclasses are refused along with
    everything else, because a subclass is precisely how an operator-defined
    `__eq__` arrives wearing a builtin's name. Being C code bounds what the hash
    can DO but not how long it can take, so tuples carry two further limits that
    are enforced by the walk rather than hoped for: one on nesting and one on the
    number of elements visited, for the reasons given at _ONCE_PER_KEY_DEPTH and
    _ONCE_PER_KEY_NODES. Within those three limits a key cannot block another
    thread for longer than a bounded traversal of a small structure.

    One residual window is not closed by any of this and is named rather than
    left to be found. Taking the ticket and adding to the set both allocate, an
    allocation can trigger a collection, and a collection runs finalizers
    belonging to the target program. A `__del__` that calls back into an
    instrumented point re-enters `_gate` on this thread while the lock is held,
    and the lock is not reentrant. It needs a cyclic-garbage finalizer that
    re-enters instrumentation, which no ruleset causes on its own.

    This is a deliberate narrowing of what once_per used to accept, not an
    oversight, and it ships without a compatibility shim. The key is never
    converted or stringified to make it fit: two keys that Python considers
    equal are still the same key, and one outside the contract is refused here
    rather than silently merged with another.
    """


# Identity, not equality and not hashing. `t in (int, str)` would fall back to
# `==` on a metaclass that defines it, and a frozenset would hash the type, so
# both of the operations this check exists to avoid would run inside the check.
_ONCE_PER_KEY_TYPES = (type(None), bool, int, float, str, bytes)

# Nesting a tuple deeper than this is refused. The restriction on TYPES bounds
# what a key's hash and its equality check can do; it does not bound how deep
# either one goes, and the two fail differently. `tuple.__hash__` recurses
# through the C stack once per level with no guard at all, so a key nested
# deeply enough takes the interpreter down with SIGSEGV rather than raising.
# Measured on CPython 3.12 on one Linux build: 100000 levels hash, 200000
# segfault, a floor two orders of magnitude above this limit and not one this
# limit depends on. `tuple.__eq__` (`tuplerichcompare`) recurses too, but
# through `Py_EnterRecursiveCall`, which shares the interpreter's ordinary
# recursion-remaining counter with every Python-level frame already on the
# stack, the same counter `sys.setrecursionlimit` governs. On CPython 3.11
# specifically, a claim's hash-then-compare left essentially no headroom in
# that shared counter once any realistic caller stack (a lock, a thread, a
# test runner) was already on it: reproduced directly, a tuple depth of 999
# compared equal at bare module scope but raised RecursionError the moment one
# ordinary function-call frame sat above it. CPython 3.12 and 3.14 do not show
# the same cliff at that depth. This limit is chosen to clear both failure
# modes with real margin under the interpreter's DEFAULT recursion limit and
# DEFAULT thread stack size. No claim is made, and none should be assumed, for
# a process running under a custom `sys.setrecursionlimit` or a custom (in
# particular a shrunk) thread stack size; only the interpreter's own defaults
# are covered.
_ONCE_PER_KEY_DEPTH = 64

# Visiting more elements than this while walking a key is refused. Depth and size
# are two different unbounded dimensions and neither implies the other. A tuple
# may share its subtuples rather than owning distinct ones, which makes it small
# to build, shallow, and enormous to traverse: `t = (); for _ in range(60): t =
# (t, t)` is 60 levels deep, legal under the bound above, and has on the order of
# 2**60 nodes. Nothing caches a tuple's hash, so `tuple.__hash__` visits every
# one of them, and it does that inside the critical section while holding the
# rule's lock. Measured here at depths 18 through 24, both the walk and the hash
# quadruple for every two levels added: the walk took 0.24s at 18 and 19.4s at
# 24. Counting nodes bounds the walk and the hash together, because the hash
# visits the same nodes the walk does. The count is charged when a tuple's
# elements are about to be pushed rather than when each one is later popped,
# because a single very wide tuple is expanded in one uninterruptible step and a
# per-element check never gets a turn during it. Measured before that was fixed,
# a key of two references to a five million element tuple was correctly refused,
# but only after 0.489s and 306MB of transient allocation.
_ONCE_PER_KEY_NODES = 10000


def _check_once_per_key(rule, key):
    """Refuse a key outside the contract WITHOUT invoking anything it defines.

    The walk reads `type(x)` and compares it by identity; it never hashes an
    element, never compares two elements, and never renders one into the
    message. Only the type NAME reaches the text, through _typename, which is
    already hardened against a metaclass that resists being asked.

    Iterative rather than recursive, because the walk has to survive a key the
    hash could not, and it carries each element's depth so the nesting bound is
    enforced here rather than discovered later by the set. It counts what it is
    about to push for the same reason, since the traversal it is measuring is the
    one the hash is about to repeat under the lock. `len` on a tuple is C and
    cannot re-enter either, so charging a whole tuple's width before expanding it
    stays inside the same guarantee as the rest of the walk.
    """
    stack = [(key, 0)]
    # The key itself is the first node, so the rest of the structure may use one
    # less than the budget.
    remaining = _ONCE_PER_KEY_NODES - 1
    while stack:
        item, depth = stack.pop()
        item_type = type(item)
        if item_type is tuple:
            if depth >= _ONCE_PER_KEY_DEPTH:
                raise OncePerKeyError(
                    "{}: fire.key evaluated to a tuple nested deeper than {}, "
                    "which once_per does not accept. Hashing or comparing it "
                    "could exhaust the interpreter's recursion budget rather "
                    "than raise cleanly."
                    .format(_describe_rule(rule), _ONCE_PER_KEY_DEPTH))
            remaining -= len(item)
            if remaining < 0:
                raise OncePerKeyError(
                    "{}: fire.key evaluated to a tuple with more than {} "
                    "elements to visit, which once_per does not accept. Hashing "
                    "it would hold the rule's lock for as long as the walk would "
                    "take.".format(_describe_rule(rule), _ONCE_PER_KEY_NODES))
            stack.extend((element, depth + 1) for element in item)
        elif not any(item_type is allowed for allowed in _ONCE_PER_KEY_TYPES):
            raise OncePerKeyError(
                "{}: fire.key evaluated to {}, which once_per does not accept. "
                "A key must be None, bool, int, float, str, bytes, or a tuple "
                "of those, and an exact instance rather than a subclass."
                .format(_describe_rule(rule), _typename(item)))


def _new_state():
    """The per-rule firing memory, built in one place because both binding
    paths need it.

    A lock per state rather than one per slot, for the same reason `fires` and
    `seen_keys` are per rule: a shared lock would let one rule's key hashing
    serialise every other rule that happens to sit on the same callable, a
    coupling no ruleset author can see or control.
    """
    return {"fires": 0, "seen_keys": set(), "lock": threading.Lock()}


class SuspendableTargetError(RuntimeError):
    """_patch reached a callable whose work does not happen during the call.

    A dispatcher times entry before calling the original and exit after it
    returns. For a coroutine function, a generator function or an async
    generator function, the call returns a suspended object and the body has
    not run, so both timings describe a moment the operator did not ask about.
    The exit fires before the first line of the body rather than after the
    last, and an entry action that supplies a return value hands the caller an
    ordinary object where an awaitable or an iterator was expected.

    Measured on the tree this refusal was written for, the mistimed record is
    not the whole of it. An exit action with a return value discards the
    suspended object the call produced, so the body never runs at all and the
    caller gets an ordinary value instead. That happens identically for all
    three kinds; what differs is whether anyone finds out. A discarded
    coroutine leaves a RuntimeWarning whenever the garbage collector gets to
    the orphan, so that one kind reports itself. A discarded generator or async
    generator is collected in silence. An async generator function is spelled
    `async def` as well, so the line does not fall where the syntax does: it
    falls on the one object of the three that is awaitable.

    Refused rather than skipped, which is the opposite of the choice made for
    an attribute that is not there. A missing point cannot be instrumented by
    anyone and the ruleset still means what it says; a suspendable point CAN
    be reached, and skipping it would return success on a rule that silently
    never fires. Refusing before this slot's setattr means the call's own
    mutations unwind through the handler below, so no half-applied ruleset is
    left behind by the call that raised.

    How far that reaches depends on when the target module is imported. A
    module already in sys.modules when site.py runs is patched by activate(),
    inside the guard in sitecustomize, and the process refuses to start. A
    module imported later is patched by the import hook, so the refusal comes
    out of the operator's own `import` statement instead, with the rest of the
    ruleset already live. This class is a RuntimeError, so an `except
    Exception` around that import swallows it. docs/rules.md says so too.

    Correct support is a separate feature. It needs the dispatcher to await or
    to iterate on the caller's behalf, preserving cancellation and throw(), and
    none of that is what this class is standing in for.
    """


class UnsupportedTargetError(RuntimeError):
    """_patch reached a point that is not a callable this package can wrap.

    The README has listed classmethod, staticmethod, property and plain data
    attributes as unsupported since the beginning, and that warning was never
    enforcement: every one of them was wrapped on request. Two different
    failures came of it, and they fail at different moments, which is why one
    refusal covers both instead of a repair on the restore side.

    A descriptor stored on a CLASS is destroyed permanently. Attribute access
    runs the protocol, so the value the ledger records is the product of
    __get__ and never the object the namespace held; the undo writes that
    product back and reports a clean release, leaving `Sub.open` bound to a
    different class for the life of the process with no diagnostic anywhere.
    A data attribute or a property is put back faithfully and is wrong only
    WHILE patched: `f = 42` answers as a function, and a property hands the
    caller a bound dispatcher where a value was. The first group cannot be
    trusted to the undo; for the second the patch itself is the damage.

    Refused rather than skipped, for the reason SuspendableTargetError gives:
    a missing point cannot be instrumented by anyone, while this one CAN be
    reached, so skipping it would report success on a rule that silently makes
    the target program wrong. The refusal is raised before the slot's setattr,
    so the call's own mutations unwind through the handler and no half-applied
    ruleset survives. How far that reaches at startup is the same question,
    answered the same way, as the note on SuspendableTargetError.

    What it does NOT claim is support. Wrapping a classmethod correctly means
    storing a classmethod built around the dispatcher and restoring the exact
    object that was there, which is a feature this class stands in place of
    rather than a behaviour it approximates. See TASK-6.
    """


# A real bound on one edge and termination insurance on the other. How far the
# partial edge runs is a property of the interpreter, not of the language, and
# one construction out of the four below is not the same on every version this
# package supports. Layout depth, counting real `func` hops:
#
#                                          3.11  3.12  3.13  3.14
#   partial(partial(f))                       1     1     1     1
#   Plain(Plain(f)), subclass overriding      1     1     1     1
#     nothing
#   SyncOver(SyncOver(f)), subclass           2     2     1     1
#     overriding __call__
#   WithDict(WithDict(f)), subclass           2     2     2     2
#     setting an instance attribute
#
# So "a nest of subclasses" is not one behaviour: only the third row moves, and
# a subclass carrying instance state stays a nest everywhere. The walk takes one
# hop per surviving layer, whatever that number turns out to be on the version
# in hand. Measured, not assumed; docs/rules.md carries the same versions.
# The __call__ edge is the short one everywhere: it lands on a function whose
# own type __call__ is a wrapper_descriptor and stops there.
#
# The loop is therefore bounded rather than trusted, and a walk that somehow
# keeps going refuses instead of hanging the interpreter at startup. There is
# no separate cycle check, but not because cycles are impossible: a class whose
# __call__ is a partial over an instance of that same class closes one through
# the __call__ edge, and the bound is what catches it. Calling such an object
# raises RecursionError, so refusing it is right. A bound that guarantees
# termination covers what a cycle check would have done, at every depth.
_WRAPPER_CHAIN_LIMIT = 64

# What functools.partial provides for its own instances. A subclass that does
# not override __call__ finds exactly this object on a static lookup, which is
# how the walk tells "no override, follow the stored callable" from "an
# override decides, follow that". Read once, because it cannot change, and read
# off the class so a pure-Python functools (where this is an ordinary function
# rather than a wrapper_descriptor) is recognised by identity just the same.
_PARTIAL_OWN_CALL = inspect.getattr_static(functools.partial, "__call__", None)


def _call_slot(obj):
    """What calling obj reaches through its type, or None when that is opaque.

    Read off the type with getattr_static, so nothing here runs a descriptor or
    a property, and narrowed to the stored forms that hold a callable of their
    own: a staticmethod and a classmethod both keep it on __func__, and a
    functools.partial keeps it where the walk already knows to look. Everything
    else answers None, an ordinary function's C-level slot wrapper included,
    because following that would land on a wrapper describing itself rather
    than the function it belongs to.

    A classmethod is read the same way as a staticmethod because it behaves the
    same way here. Neither carries Py_TPFLAGS_METHOD_DESCRIPTOR, so neither is
    handed the instance the way a plain function in a __call__ is; the kind of
    the callable is on __func__ either way, and __func__ is read rather than
    invoked, so no binding happens and no descriptor protocol runs.

    functools.partial's own __call__ answers None as well, by identity against
    the one read off the class. A partial subclass that does not override finds
    exactly that object on a static lookup, and reporting it as a slot would
    tell the walk an override decided when nothing did. Identity rather than a
    type test, so a pure-Python functools, where this is an ordinary function
    instead of a wrapper_descriptor, is recognised just the same.

    The hop is ONE, and what is still a descriptor after it is handed back as
    the slot rather than discarded. A slot holding a descriptor that holds
    another one really does reach the inner one when it is called, so stopping
    at the first residue answered None for an object the caller can watch
    return a coroutine. Returning it lets the walk take the next layer on the
    terms it already applies to a descriptor it meets anywhere else, under the
    one budget, instead of unwrapping here on different terms and spending none
    of it.

    The narrowing is the point. This is not descriptor support in general; it
    is the spellings that were found sitting in a __call__ and carrying a kind
    the gate is supposed to see.
    """
    call = inspect.getattr_static(type(obj), "__call__", None)
    if call is _PARTIAL_OWN_CALL:
        return None
    call = _through_func(call)
    if (inspect.isfunction(call) or isinstance(call, functools.partial)
            or isinstance(call, (staticmethod, classmethod))):
        return call
    return None


def _through_func(obj):
    """One hop off a staticmethod or a classmethod, or the object unchanged.

    The read goes through the base class rather than through the instance, for
    the reason the partial arc takes `func` off functools.partial itself: a
    subclass defining __func__ as a property would otherwise choose what the
    walk follows, and choose differently from what a call does. Measured on a
    staticmethod subclass whose __func__ property returns a plain function over
    a stored `async def`: read off the instance the gate calls it
    instrumentable and executes the property body while deciding, which is
    target code running inside a check whose whole contract is to read and
    never run. Read this way it sees the coroutine function that is really
    there.

    A classmethod is treated like a staticmethod because it carries its
    callable the same way. Neither is invoked here, and neither is bound:
    __func__ is fetched from the defining class and applied to the object, so
    no __get__ of the target's own devising runs.
    """
    if isinstance(obj, staticmethod):
        return staticmethod.__func__.__get__(obj)
    if isinstance(obj, classmethod):
        return classmethod.__func__.__get__(obj)
    return obj


#: Namespaces read through the unbound getset descriptors rather than through
#: `vars()` or `.__dict__`. Both of those go through attribute lookup, and a
#: metaclass or an instance is free to answer with a custom getter, so the
#: convenient spelling would run target code inside a check whose whole claim
#: is that it does not. These bypass any such override.
_CLASS_NAMESPACE = type.__dict__["__dict__"].__get__
_CLASS_MRO = type.__dict__["__mro__"].__get__
_MODULE_NAMESPACE = types.ModuleType.__dict__["__dict__"].__get__

#: Builtin descriptor types whose `__get__(None, cls)` hands back the
#: descriptor itself, so a class-level read of one yields the object the
#: namespace holds and the undo puts that same object back. Measured, not
#: assumed: `int.bit_length` and `types.FunctionType.__call__` are both patched
#: by the existing suite and neither is corrupted. Compared by EXACT type,
#: because a subclass is free to override `__get__` and stop being one of
#: these.
_SELF_RETURNING = (types.MethodDescriptorType, types.WrapperDescriptorType,
                   types.ClassMethodDescriptorType, types.GetSetDescriptorType,
                   types.MemberDescriptorType, types.BuiltinFunctionType)


def _defines_get(cls):
    """Does this type implement the descriptor protocol, asked statically."""
    for base in _CLASS_MRO(cls):
        if "__get__" in _CLASS_NAMESPACE(base):
            return True
    return False


def _stored_reason(raw):
    """Why the object a class namespace HOLDS cannot be wrapped, or None.

    `isinstance` is avoided throughout: it reads `__class__`, which a target
    can answer for itself, and the point of this classification is that the
    target gets no vote in it. The real type and its mro are read instead, so
    a `staticmethod` subclass is still a staticmethod here.
    """
    kind = type(raw)
    mro = _CLASS_MRO(kind)
    for base, label in ((classmethod, "a classmethod"),
                        (staticmethod, "a staticmethod"),
                        (property, "a property")):
        if any(base is entry for entry in mro):
            return label
    if kind is types.FunctionType:
        # Load-bearing shortcut, not an optimisation: a function DOES define
        # __get__, so without this every plain method falls through to the
        # custom-descriptor refusal below.
        return None
    if any(kind is known for known in _SELF_RETURNING):
        # Callable-ness still decides: a GetSetDescriptorType holding no
        # callable is a data attribute wearing a descriptor's clothes.
        return None if callable(raw) else "a data attribute"
    if _defines_get(kind):
        # A descriptor nobody here can vouch for. Its `__get__` may consult
        # `obj` or `cls`, in which case the value the undo would write back is
        # a product this slot never held.
        return "a custom descriptor"
    if not callable(raw):
        return "a data attribute"
    return None


def _unsupported_reason(container, name):
    """Why this point cannot be wrapped, as (reason, cause), read statically.

    (None, None) means nothing unsupported was ESTABLISHED, which is not the
    same as a promise that the point is fine: the answer is deliberately
    narrow. Only the final name is classified, and only on a class or a module
    container, by reading namespaces and never the attribute. An instance is
    not classified at all, because a property or a `__slots__` member reached
    through one is supported and its value is knowable only by reading it;
    what stands in for this check there is the callable test in _patch, which
    every container alike has to pass.

    The class case is where the damage is. Only a class runs the descriptor
    protocol ON THE STORED OBJECT when the attribute is read, so a classmethod
    or staticmethod there is handed to the rest of _patch as the method it
    produced, and what the undo writes back is that product. A module runs no
    protocol, which is why `handler = staticmethod(coro)` at module scope is
    left for the suspendable gate to judge as the callable object it is.

    A failure to READ a namespace is refused rather than allowed, and it is not
    the same answer as an absent name. A name that is not there is skipped,
    which is a documented promise; a namespace this check could not read means
    the shape was never established, and writing on that basis is guessing in
    the destructive direction. The cause travels with the refusal.
    BaseException is not caught, for the reason every other gate here gives.
    """
    try:
        if any(entry is type for entry in _CLASS_MRO(type(container))):
            for base in _CLASS_MRO(container):
                namespace = _CLASS_NAMESPACE(base)
                if name in namespace:
                    return (_stored_reason(namespace[name]), None)
            # Provided by a metaclass, or not there at all. Neither is this
            # check's to answer: the setattr would CREATE the name on the
            # class, the undo deletes it again, and nothing stored is touched.
            return (None, None)
        if any(entry is types.ModuleType
               for entry in _CLASS_MRO(type(container))):
            namespace = _MODULE_NAMESPACE(container)
            if name in namespace and not callable(namespace[name]):
                return ("a data attribute", None)
            return (None, None)
        return (None, None)
    except Exception as exc:
        return ("a target whose namespace could not be read", exc)


def _refuse_unsupported(modname, name, reason, cause, current):
    raise UnsupportedTargetError(
        "pyteman: " + modname + ":" + name + " is " + reason + ", so wrapping"
        " it would change what the target program holds; refused rather than"
        " installed for " + current) from cause


def _suspendable_reason(obj):
    """Why obj cannot carry synchronous entry and exit, as (reason, cause).

    (None, None) means nothing suspendable was found. Otherwise `reason` is a
    phrase the caller puts after "<target> is", and `cause` is the exception to
    chain from when introspection is what failed.

    Every edge walked here carries call semantics: what invoking the object
    does. __wrapped__ is deliberately NOT walked, though it is the obvious
    candidate and an earlier draft of this gate did walk it. functools.wraps
    sets it to record where a wrapper came from, which is what inspect.signature
    wants and is not what this gate asks. Two wrappers with identical metadata,
    one returning fn(*a) and one returning a value built from it, are the same
    object shape; @contextlib.contextmanager is the second kind, and walking
    __wrapped__ refused it as "a generator function" while it is synchronous.
    CPython's own iscoroutinefunction does not follow __wrapped__ either.

    A partial is never handed to the three predicates, and that ordering is the
    whole of how nesting is handled. The predicates unwrap partials themselves:
    iscoroutinefunction(partial(coroutine)) is True, because _has_code_flag
    calls functools._unwrap_partials before reading the code flag. That helper
    walks the WHOLE nest in one step, so every layer between the outside and
    the innermost stored callable is skipped, overrides included. Asking them
    while standing on a partial therefore answers about a callable the object
    may never invoke, and it was measured doing exactly that: Plain(SyncOver(c))
    with c an `async def`, Plain a subclass that overrides nothing and SyncOver
    one whose own __call__ is synchronous, returns an int on 3.11 and 3.12 and
    was refused there as a coroutine function.

    So while the walk is on a partial it takes the effective __call__ override
    if there is one, and otherwise follows exactly ONE `func` storage arc and
    comes back round. One arc per turn is what keeps the nest honest, because
    whether a nest exists at all is a property of the interpreter: the same
    Plain(SyncOver(c)) is a two-layer nest on 3.11 and 3.12 and a single
    flattened partial holding `c` on 3.13 and 3.14, where SyncOver's override
    is discarded at construction and the object really does return a coroutine.
    Following the layout rather than asking the predicates lets each version's
    real storage decide, and the gate answers correctly on both without once
    branching on a version number.

    An override read this way decides for the same reason. Such a subclass
    calls `func` only if its own body says so, and the predicates have no way
    to ask. Both directions are wrong and both were measured. A subclass with
    an `async def __call__` over a synchronous `func` returns a coroutine while
    the predicates see a plain function, which instruments a suspendable
    target. A subclass with a synchronous __call__ over a stored coroutine
    function returns a value while the predicates report a coroutine function,
    which is a refusal of something that never suspends, the same false
    positive that walking __wrapped__ produced and the reason that walk was
    removed.

    Off the partial arc the predicates are asked directly, on a terminal that
    holds its kind itself, and only then is the type's own __call__ read. The
    `func` arc is required on every partial, and the case where the predicates
    could not have substituted for it at all is partial(instance whose type
    __call__ is async): unwrapping the partial lands on an instance, the
    predicates stop there, and the slot is what carries the kind.

    `func` is taken off functools.partial itself rather than off the instance,
    the way _text renders through str.__str__, so a partial subclass defining
    `func` as a property cannot choose what the walk follows. With the
    predicates off the partial arc that is now the only read of `func` the gate
    performs, so such a property does not run at all rather than running first
    and deciding before the walk gets there.

    What this does NOT promise is a verdict on every callable, and the gap is
    wider than the undecidable case. A plain `def` that returns a coroutine
    carries nothing saying so. Neither does a synchronous adapter built with
    functools.wraps around an `async def`: it is an ordinary function whose only
    evidence is the provenance link this gate does not read. An override that
    delegates is the same shape one layer out, a synchronous `def __call__`
    whose body returns self.func(*a), and it is statically indistinguishable
    from one that does its own synchronous work; the walk reaches it, reads a
    plain function and instruments it. Refusing on provenance instead would
    refuse every adapter written for the purpose, which AC 2 keeps
    instrumentable on purpose. A __call__ that is none of the recognised forms,
    a native one for instance, is opaque for a different reason: there is
    nothing to read. All of them are outside the static guarantee, by the same
    decision. The promise kept here is that the shapes named above are refused
    and never quietly instrumented; nothing wider is claimed, and "recognised"
    is not left to mean whatever this walk happens to reach.
    """
    current = obj
    # One iteration per link plus one for the terminal: a chain of exactly
    # _WRAPPER_CHAIN_LIMIT links is inside the budget, which is what the
    # refusal message promises. Without the +1 the loop spends its last
    # iteration taking a hop and never looks at what it landed on, so a
    # 64-layer nest over an ordinary synchronous function is refused while
    # calling it plainly returns a value.
    for _ in range(_WRAPPER_CHAIN_LIMIT + 1):
        try:
            if isinstance(current, functools.partial):
                # One layer per turn, override first. The predicates are not
                # asked here at all: they would unwrap every remaining layer
                # in one step and answer about the innermost callable, which
                # is what the paragraphs above are about.
                call = _call_slot(current)
                if call is None:
                    call = functools.partial.func.__get__(current)
                current = call
                continue
            if isinstance(current, (staticmethod, classmethod)):
                # One layer per turn, override first, on exactly the terms the
                # partial edge above uses and for the same reason: what the
                # object does when it is called is decided by its type's
                # __call__, and the storage arc is only the fallback. A
                # subclass with an `async def __call__` over a stored plain
                # function really returns a coroutine, and reading __func__
                # first would report the plain function and instrument it; the
                # mirror subclass, a synchronous __call__ over a stored
                # coroutine function, really returns a value and would be
                # refused. Both were measured.
                #
                # The fallback reads __func__ off the defining class for the
                # reason _through_func gives.
                #
                # A single descriptor read off a CLASS never arrives here:
                # getattr runs __get__ and the gate is handed the callable
                # underneath already. What does arrive is the module-level
                # attribute, because a module runs no descriptor protocol, and
                # from any container a descriptor nested inside another one or
                # reached along the partial arc. Without this hop the
                # predicates answer about the descriptor rather than about what
                # it holds, report an ordinary callable, and a coroutine
                # function is wrapped with entry semantics that return a value
                # where the caller awaits.
                call = _call_slot(current)
                if call is None:
                    call = _through_func(current)
                current = call
                continue
            if inspect.iscoroutinefunction(current):
                return "a coroutine function", None
            if inspect.isasyncgenfunction(current):
                return "an async generator function", None
            if inspect.isgeneratorfunction(current):
                return "a generator function", None
            call = _call_slot(current)
            if call is not None:
                # A callable instance keeps its kind on the type's __call__,
                # which is read here and never called.
                current = call
                continue
        except Exception as exc:
            # Exception, not BaseException, for the reason the preflight id
            # gate narrows the same way: relabelling a KeyboardInterrupt that
            # landed during introspection as a defect in the target is a lie
            # about whose fault it is, and it loses the interrupt.
            return ("of a kind that could not be read: " + _typename(exc)
                    + ": " + _text(exc)), exc
        return None, None
    return ("reached through a chain of wrappers that did not end within "
            + str(_WRAPPER_CHAIN_LIMIT) + " links"), None


class _Slot:
    """One resolved (container, attribute) and every rule that landed on it.

    Keyed on the resolved pair and not on `rule.symbol`, because two symbols can
    name one attribute: with a module-level `alias = sys.modules[__name__]`,
    `mod.f` and `mod.alias.f` are the same slot. Grouping on the text would
    build two dispatchers for one attribute and the second setattr would drop
    the first, which is the "second rule silently lost" failure this task exists
    to end, arriving by a different road.
    """

    __slots__ = ("container", "name", "specs")

    def __init__(self, container, name):
        self.container = container
        self.name = name
        self.specs = []


#: Why a `param:` target could not be bound. Each is returned verbatim as the
#: firing log's outcome, so each names what could not be established rather
#: than merely saying no.
_UNAVAILABLE = (
    "the intercepted callable's parameters cannot be read from code, so they "
    "cannot be attributed to the arguments this call passes")
_TOO_DEEP = (
    "the intercepted callable nests deeper than the binding walk is allowed to "
    "follow, so its parameters were not established")
_CLASS_CUSTOM = (
    "the intercepted callable is a class whose construction is customised, so "
    "which of its metaclass, __new__ and __init__ declares the parameters this "
    "call passes could not be established")
_PREBOUND_SHAPE = (
    "the intercepted callable pre-binds arguments in a shape whose effect on "
    "the remaining parameters could not be established")

#: How many container layers the walk will follow before refusing. The walk
#: follows attributes the workload owns, and a cycle there must not cost the
#: process. Exhausting it is a refusal, never a fall-through.
_BINDING_DEPTH = 32

#: Read through the base descriptor, never as an attribute. `functools.partial`
#: is subclassable, so a subclass may define `func`, `args` or `keywords` as a
#: property; reading them as attributes would run workload code inside the
#: patcher, triggered by nothing more than a rule mentioning a parameter name.
_PARTIAL_FUNC = functools.partial.func.__get__
_PARTIAL_ARGS = functools.partial.args.__get__
_PARTIAL_KEYWORDS = functools.partial.keywords.__get__

#: The genuine `__call__` slot of `functools.partial`, taken from its namespace
#: so a subclass that redefines `__call__` is detectable by identity.
_PARTIAL_CALL = type.__dict__["__dict__"].__get__(functools.partial)["__call__"]

#: `functools.Placeholder` reserves a positional slot for the caller instead of
#: consuming it. Added in 3.13; `None` on older interpreters, where no partial
#: can carry one, so the reserving branch is simply unreachable there.
_PLACEHOLDER = getattr(functools, "Placeholder", None)

#: The only `__new__` and `__init__` known not to declare parameters of their
#: own. Anything else means the call routes somewhere this walk did not look.
_PLAIN_NEW = object.__dict__["__new__"]
_PLAIN_INIT = object.__dict__["__init__"]

_CO_VARARGS = 0x04
_CO_VARKEYWORDS = 0x08

_POSITIONAL = (inspect.Parameter.POSITIONAL_ONLY,
               inspect.Parameter.POSITIONAL_OR_KEYWORD)


def _code_parameters(func):
    """The parameters a genuine function declares, read from its own code.

    `types.FunctionType` is final: `type(f) is types.FunctionType` therefore
    guarantees that every read below is a real slot read, which no property,
    descriptor or metaclass can intervene in. That guarantee is what lets this
    replace `inspect.signature` rather than merely precede it.

    Defaults and annotations are deliberately not read. Binding needs neither,
    and not reading them means an unresolvable annotation cannot raise here and
    a default cannot be mistaken for an argument this call passed.
    """
    code = func.__code__
    names = code.co_varnames
    n_positional = code.co_argcount
    n_keyword = code.co_kwonlyargcount
    kinds = inspect.Parameter
    params = [
        inspect.Parameter(
            names[i],
            kinds.POSITIONAL_ONLY if i < code.co_posonlyargcount
            else kinds.POSITIONAL_OR_KEYWORD)
        for i in range(n_positional)]
    extra = n_positional + n_keyword
    if code.co_flags & _CO_VARARGS:
        params.append(inspect.Parameter(names[extra], kinds.VAR_POSITIONAL))
        extra += 1
    params.extend(
        inspect.Parameter(names[i], kinds.KEYWORD_ONLY)
        for i in range(n_positional, n_positional + n_keyword))
    if code.co_flags & _CO_VARKEYWORDS:
        params.append(inspect.Parameter(names[extra], kinds.VAR_KEYWORD))
    return params


def _drop_receiver(params, count):
    """Account for a receiver the call does not pass, one per bound layer.

    NOT a blind "drop the first parameter". If the receiver is absorbed by a
    `*args`, no named parameter disappears and the list is unchanged, which is
    what a bound method of `def f(*args)` actually exposes. Dropping a name
    there would shift every later attribution one place left, which is the
    defect class this whole path exists to remove.
    """
    params = list(params)
    for _ in range(count):
        if not params:
            return None
        if params[0].kind == inspect.Parameter.VAR_POSITIONAL:
            return params          # absorbed; nothing is consumed
        if params[0].kind not in _POSITIONAL:
            return None            # nothing positional to receive it
        params.pop(0)
    return params


def _prebound_parameters(params, args, keywords):
    """What a caller can still pass to a partial, given what it pre-bound.

    Two rules, both measured against the running interpreter rather than
    reasoned out. A positional pre-bind CONSUMES a parameter, unless it is a
    `Placeholder`, which reserves the slot and leaves the parameter reachable
    only by position. A keyword pre-bind makes the parameter it names
    keyword-only AND every positional-or-keyword parameter after it, and
    removes `*args` entirely, because position zero is now spoken for.
    """
    params = list(params)
    kinds = inspect.Parameter
    cursor = 0
    for value in args:
        while cursor < len(params) and params[cursor].kind not in (
                kinds.POSITIONAL_ONLY, kinds.POSITIONAL_OR_KEYWORD,
                kinds.VAR_POSITIONAL):
            cursor += 1
        if cursor >= len(params):
            return None            # more pre-bound arguments than parameters
        if params[cursor].kind == kinds.VAR_POSITIONAL:
            break                  # the rest vanish into *args
        if _PLACEHOLDER is not None and value is _PLACEHOLDER:
            params[cursor] = params[cursor].replace(kind=kinds.POSITIONAL_ONLY)
            cursor += 1
        else:
            params.pop(cursor)
    if keywords:
        shadowed = False
        rebuilt = []
        for param in params:
            if param.kind == kinds.POSITIONAL_OR_KEYWORD and (
                    shadowed or param.name in keywords):
                shadowed = True
                rebuilt.append(param.replace(kind=kinds.KEYWORD_ONLY))
            elif param.kind == kinds.POSITIONAL_ONLY and param.name in keywords:
                # A positional-only parameter cannot be pre-bound by name at
                # all; the partial is constructible but uncallable, and what
                # the caller may pass is not established.
                return None
            else:
                rebuilt.append(param)
        if shadowed:
            rebuilt = [p for p in rebuilt if p.kind != kinds.VAR_POSITIONAL]
        params = rebuilt
    order = (kinds.POSITIONAL_ONLY, kinds.POSITIONAL_OR_KEYWORD,
             kinds.VAR_POSITIONAL, kinds.KEYWORD_ONLY, kinds.VAR_KEYWORD)
    return sorted(params, key=lambda p: order.index(p.kind))


def _own_call(klass):
    """The `__call__` a class defines, found through the REAL mro.

    `_CLASS_MRO` and `_CLASS_NAMESPACE` rather than attribute access, because a
    metaclass may define `__mro__` or `__dict__` as a property, and a forged
    mro can hide the real `__call__` behind an innocuous decoy. That is not
    hypothetical: it produces a false certification against this exact walk.
    """
    for base in _CLASS_MRO(klass):
        namespace = _CLASS_NAMESPACE(base)
        if "__call__" in namespace:
            return namespace["__call__"]
    return None


def _class_target(klass):
    """The function a plain class's construction actually routes through.

    The gate is not "can this metadata be trusted", it is "does the call reach
    `__init__` at all". `type` is the only metaclass known to forward to
    `__new__` and `__init__`, and `object.__new__` the only `__new__` known not
    to declare parameters of its own; anything else means the parameters the
    caller passes are declared somewhere this walk did not look.
    """
    if type(klass) is not type:
        return None, _CLASS_CUSTOM
    new = init = None
    for base in _CLASS_MRO(klass):
        namespace = _CLASS_NAMESPACE(base)
        if new is None:
            new = namespace.get("__new__")
        if init is None:
            init = namespace.get("__init__")
    if new is not _PLAIN_NEW:
        return None, _CLASS_CUSTOM
    if init is _PLAIN_INIT:
        return _EMPTY_CLASS, None          # takes no arguments at all
    if type(init) is not types.FunctionType:
        return None, _CLASS_CUSTOM
    return init, None


#: Sentinel for a class whose construction reaches neither a user `__new__` nor
#: a user `__init__`: it takes no arguments, which is a fact, not a refusal.
_EMPTY_CLASS = object()


def _binding_signature(original):
    """`(Signature, None)` or `(None, reason)` for the intercepted callable.

    Built from code, never from metadata. `inspect.signature` is not called on
    `original` or on anything derived from it, so no `__signature__`,
    `__wrapped__`, `__partialmethod__` or `__text_signature__` a target
    declares can steer the result: a decorated wrapper reports its own
    `(*args, **kwargs)`, which is the truth about what it receives, and a
    `param:` target on it misses on its own without any ambiguity machinery.

    The walk collects the layers outward-in, then applies them inward-out,
    because the transform nearest the function must be applied first: a partial
    over a bound method pre-binds against the parameters the receiver already
    left behind.
    """
    layer = original
    operations = []
    for _ in range(_BINDING_DEPTH):
        kind = type(layer)
        if kind is types.FunctionType:
            params = _code_parameters(layer)
            break
        if kind is types.MethodType:
            # MethodType is final, so these are real slot reads. It comes first
            # because a bound method carries the receiver whatever it wraps.
            operations.append(("receiver", 1))
            layer = layer.__func__
            continue
        if kind is functools.partial or _is_partial_subclass(kind):
            if _own_call(kind) is not _PARTIAL_CALL:
                # A subclass that redefines __call__ does not reduce to its
                # func: what it does with the pre-bound arguments is its own.
                resolved = _resolve_callable_slot(_own_call(kind))
                if resolved is None:
                    return None, _UNAVAILABLE
                layer, receivers = resolved
                operations.append(("receiver", receivers))
                continue
            operations.append(
                ("prebound", _PARTIAL_ARGS(layer), _PARTIAL_KEYWORDS(layer)))
            layer = _PARTIAL_FUNC(layer)
            continue
        if type in _CLASS_MRO(kind):
            target, reason = _class_target(layer)
            if target is None:
                return None, reason
            if target is _EMPTY_CLASS:
                params = []
                break
            operations.append(("receiver", 1))
            layer = target
            continue
        entry = _own_call(kind)
        if entry is None:
            return None, _UNAVAILABLE
        resolved = _resolve_callable_slot(entry)
        if resolved is None:
            return None, _UNAVAILABLE
        layer, receivers = resolved
        operations.append(("receiver", receivers))
    else:
        return None, _TOO_DEEP

    for operation in reversed(operations):
        if operation[0] == "receiver":
            params = _drop_receiver(params, operation[1])
        else:
            params = _prebound_parameters(params, operation[1], operation[2])
        if params is None:
            return None, _PREBOUND_SHAPE
    try:
        return inspect.Signature(params), None
    except ValueError:
        # Duplicate names across layers, or an order the constructor refuses.
        return None, _UNAVAILABLE


def _is_partial_subclass(kind):
    return kind is not functools.partial and functools.partial in _CLASS_MRO(kind)


def _resolve_callable_slot(entry):
    """`(function, receivers)` for a `__call__` slot, or `None`.

    `receivers` is how many leading positional parameters the call does not
    pass: one for a plain function (`self`) or a classmethod (`cls`), none for
    a staticmethod, which is why this returns the count rather than letting the
    caller assume it.
    """
    if type(entry) is staticmethod:
        entry = entry.__func__
        return (entry, 0) if type(entry) is types.FunctionType else None
    if type(entry) is classmethod:
        entry = entry.__func__
    return (entry, 1) if type(entry) is types.FunctionType else None


class _Composite:
    """The half of a dispatcher that a LATER _patch call can still add to.

    Everything here would otherwise be a closure local, and a closure local is
    read-only from outside the closure. That is what made a rule reaching an
    attribute an earlier call already took impossible to serve: the dispatcher
    was there, it was ours, and there was no way to put another rule into it.

    The lists are REBOUND on an extension rather than mutated in place, and the
    dispatcher reads them through this object on every call so it sees the
    rebind. In-place mutation would be cheaper and is wrong: an extension can
    run while a call is in flight on this very slot, because the getattr and
    setattr on the patch path run target code that can call the callable being
    extended, and a `for spec in entries` that grows underneath the loop skips
    or repeats a rule. Rebinding leaves any in-flight call iterating the list it
    started on, which is a complete and consistent view of the ruleset as it
    stood when that call began.

    `served` is the manifest, keyed by the rule OBJECT's id and not by `rule.id`.
    The string is the wrong key even though __init__ now refuses a rule whose
    `.id` cannot be read, is not a str, is blank, or repeats an earlier one. A
    preflight check can only speak for the moment it runs: `Rule` is a plain
    dataclass, so the caller still holds the object the plan holds and can
    rebind `.id` afterwards, and two rules answering to one string here would
    collide and silently drop the second, which is the exact failure this task
    exists to end. Object identity needs no uniqueness assumption to be exact,
    so it holds whatever the caller does later, and the ids
    cannot be recycled under the map because the dispatcher holds its Patcher,
    which holds the plan, which holds every rule.

    It is kept alongside the two lists rather than derived from them, because
    "served" and "fires" are not the same set: a rule whose event is neither
    entry nor exit belongs to this dispatcher and appears in neither list, and
    deriving the manifest would offer to add it a second time on every later
    call. That rule is reachable rather than hypothetical: the event vocabulary
    is checked in the YAML loader and nowhere else, and `Rule` is a plain
    dataclass, so a Patcher built in process can carry any event string.
    """

    __slots__ = ("original", "entries", "exits", "sig", "sig_reason",
                 "served")

    def __init__(self, original, sig, sig_reason):
        self.original = original
        self.sig = sig
        self.sig_reason = sig_reason
        self.entries = []
        self.exits = []
        self.served = {}

    def rank(self):
        """Every served spec in RULESET order, whatever order it arrived in."""
        return sorted(self.served.values(), key=lambda spec: spec[4])


def _needs_signature(specs):
    """Does any of these rules bind a parameter by name?

    Asked of a group rather than of one rule, because the signature is a fact
    about the wrapped callable and one answer serves the whole slot. Reading
    `target` only under the pragma test, never beside it: it is a key only
    pragma looks at, so parsing whatever string sits under it on some other
    action is work no rule asked for.
    """
    for spec in specs:
        rule = spec[0]
        if rule.action.get("kind") != "pragma":
            continue
        target, _reason = parse_target_spec(str(rule.action.get("target", "")))
        if target is not None and target[0] == "param":
            return True
    return False


def _unextend(extensions):
    """Take back the rules an aborted _patch added to dispatchers already live.

    The other half of the undo, for the slots where this call installed
    nothing. Those dispatchers were somebody else's success: an earlier call
    built them and an earlier `applied` names their rules, so the undo has to
    remove exactly what this call put in and leave the rest untouched. Unlike
    _restore this leaves its argument alone, because nothing here reaches a
    container: there is no refusal to record and so no residue to retry.

    By IDENTITY of the rule and never by position. An extension merges into
    ruleset order, so adding a rule that sorts early shifts every existing spec
    after it, and an index remembered before the merge names a different rule
    afterwards: the undo would drop a rule that was firing before this call
    began. Nothing here can raise, so no entry is skipped by a failure in the
    one before it.

    A signature the extension cached goes back too, and only when that
    extension is the one that cached it. It is not a fact about the rules being
    removed: the dispatcher offers `_signature_unparseable` to every `when`
    expression on the slot, so leaving one behind would let a call that failed
    change how the rules it never touched are evaluated. Reset rather than
    restored from a saved value, because the write happens only on a slot with
    no answer yet, which makes the state it found the one below. An extension
    that found an answer already there wrote nothing and takes nothing back,
    which is what leaves a re-entrant call's own answer where its rules can
    still read it.
    """
    for dispatcher, added, wrote_sig in reversed(extensions):
        comp = dispatcher._pyteman_composite
        drop = {id(spec[0]) for spec in added}
        comp.entries = [s for s in comp.entries if id(s[0]) not in drop]
        comp.exits = [s for s in comp.exits if id(s[0]) not in drop]
        for key in drop:
            comp.served.pop(key, None)
        if wrote_sig:
            comp.sig, comp.sig_reason = None, None
        dispatcher._pyteman_state = [spec[3] for spec in comp.rank()]


class Patcher:
    def __init__(self, rules, log):
        self.log = log
        self.applied = []
        self._orig_import = None
        self._hook = None
        self._wrapped = []
        # Dispatchers that are live in their attribute but not yet in _wrapped,
        # keyed by id and holding the object so no id can be recycled under the
        # map. _patch publishes to _wrapped only once the whole module is done,
        # for the reasons in its docstring, and _live_dispatcher_owner answers
        # from _wrapped; between the setattr and that publish our own dispatcher
        # would otherwise read as a stranger to us. _patch re-enters (target
        # code executed by the callable and suspendable checks can import an
        # instrumented module while the hook is live), so that gap is reachable
        # single-threaded, and what came back through it was a second wrap of a
        # slot we already held: two entries whose LIFO undo makes _undo_one see
        # a foreign object, release ownership, and drop the entry, leaving the
        # callable wrapped and firing after an uninstall that reported nothing
        # refused. Written BEFORE the setattr rather than after it, which is what
        # makes the answer true for the whole of the gap including the write: a
        # container that runs target code on its own `__setattr__` reaches the
        # width of that one statement, and registering afterwards left exactly
        # that statement uncovered by the map built to cover it.
        self._inflight = {}
        # Materialised FIRST, and everything below reads this rather than the
        # argument. `rules` is whatever iterable the caller passed, and consuming
        # it twice left the plan holding rules that `self.rules` said were not
        # there: a generator produced a full plan and an empty tuple. That is the
        # alignment failure the plan is built to rule out, so the code building
        # it cannot be the thing that reintroduces it. A tuple also means a rule
        # appended here afterwards fails where the append is written, instead of
        # going quiet by never being patched.
        self.rules = tuple(rules)
        # Every expression is compiled here rather than when the wrapper is
        # built, because __init__ is the only step in an activation that mutates
        # nothing: a ruleset that cannot compile dies before the import hook is
        # installed and before the first callable is replaced, so there is no
        # partial instrumentation to undo. Each rule's compiled pair and its
        # rendered identity travel WITH it rather than in second and third lists
        # read by index, because lists that must stay aligned eventually will
        # not, and a zip over a short one drops the tail without saying so.
        #
        # An explicit loop rather than a comprehension, because the identity has
        # to be rendered BEFORE the fields are read. `when` and `fire` are
        # attribute accesses on an object the programmatic API lets the caller
        # build, so either can be a property that raises; as arguments they were
        # evaluated before _describe_rule ran, and tuple elements evaluate left
        # to right, so the failure left here carrying NO note at all, naming no
        # rule out of a whole ruleset. The same failure on `module` arrived
        # fully described, and the asymmetry was invisible because every test
        # reached this code through a readable field.
        plan = []
        seen_ids = set()
        for r in self.rules:
            described = _describe_rule(r)
            try:
                plan.append((r, _compile(r, "when", r.when),
                             _compile(r, "fire.key", r.fire.get("key")),
                             described))
                # The id is checked in this loop rather than in a pass of its
                # own, because __init__ is already the step that mutates
                # nothing, and a raise here is attributed to the offending rule
                # by the handler below for free. After the compiles and not
                # before them, so a rule that is both unnamed and unparseable
                # still reports the defect in its own text, which is the one its
                # author can act on without reading the rest of the ruleset.
                #
                # Guarded, and deliberately not by _rule_id: `r.id` is an
                # attribute access on a hand-built object and can raise, and
                # unguarded it would leave this the one defect at
                # this gate that escapes as a raw RuntimeError instead of the
                # RuleError every other one raises, so a caller catching
                # RuleError to mean "the ruleset is wrong" would miss exactly
                # the rule that refuses to name itself. What that helper cannot
                # give this caller is the DIFFERENCE between an id that would
                # not be read and one that reads as the placeholder text, and
                # the difference decides a refusal here.
                #
                # An unreadable id is refused, not excused. _rule_id promises
                # the opposite for REPORTING and keeps it: every site that only
                # NAMES a rule still degrades to the placeholder. That promise
                # cannot extend to the run, because `FiringLog.record` reads
                # `rule.id` raw, inside the instrumented callable, to key every
                # record the rule writes. actions.py never reads the id itself:
                # it hands `record` the whole rule, once for the `phase: start`
                # record `run_action` writes before the action and once for the
                # terminal `phase: end` record `_terminal` writes after it, so
                # both reads happen inside the logger. Both sit behind a firing
                # log, and saying otherwise overstates what this gate is
                # protecting: `run_action` writes the start record only `if log
                # is not None`, and `_terminal` returns early when there is
                # none, so a run configured without a log never reads the id at
                # run time at all. The refusal is unconditional anyway, and not
                # because a guard might be forgotten. A Patcher is handed its
                # log at construction, so this gate COULD ask and decline to
                # refuse when there is none; asking would make one ruleset legal
                # or illegal according to a logging choice, and the id is the
                # operator's name for the rule under either. Under a log the
                # hazard is the concrete one: a rule that will not name itself
                # does not degrade there, it raises out of the caller's workload
                # on the first firing, with the slot already replaced and no
                # firing record written. Refusing here is what protects those
                # two reads, and preflight is the only place that can do it
                # without a guard at each one: __init__ still mutates nothing,
                # so this costs an unpatched process rather than a half-patched
                # one.
                #
                # The contract is load_rules', to the letter: a readable str,
                # non-empty once stripped, not merely something str() renders.
                # Two doors into one state that disagree about what an identity
                # is let the programmatic one admit rules the file one rejects,
                # and the id keys the same log for both.
                #
                # _text is deliberately NOT used to normalise the id, though it
                # is the house tool for rendering one. _text answers "what does
                # this object print as", which is the right question for a
                # message and the wrong one for an identity: it calls str(), and
                # on a str subclass str() dispatches to the subclass's __str__,
                # which is user code. The log does the opposite, serialising the
                # true characters, so keying on __str__ would key on a value the
                # log never writes. Two rules whose ids genuinely differ would
                # collide whenever __str__ collapses or raises, and be refused
                # for a duplicate that does not exist, while an id whose real
                # content is "" would pass the non-empty check on the strength
                # of a placeholder and then be written to the log as "". Taking
                # the characters instead answers both: str.__str__ is the same
                # spelling _text ends on, it cannot run user code, and it still
                # yields an exact str, which keeps a subclass carrying its own
                # __hash__ out of seen_ids. Emptiness is asked of that result
                # rather than of the raw value so `strip` is str's own too.
                try:
                    raw_id = r.id
                # Narrower than the BaseException this file uses almost
                # everywhere, and narrower on purpose. Elsewhere the breadth
                # protects something: _rule_id must not raise while reporting,
                # and _undo_one must not leave a module half restored if an
                # interrupt lands mid-loop. Here there is nothing to protect,
                # because __init__ mutates nothing, so catching KeyboardInterrupt
                # would buy no safety and cost a wrong diagnosis: str() of one is
                # empty, so a Ctrl-C during construction would be reported as
                # "id could not be read: ", a ruleset defect that does not exist.
                except Exception as exc:
                    raise RuleError("id could not be read: " + _text(exc))
                if not isinstance(raw_id, str):
                    raise RuleError("id must be a string, got "
                                    + _typename(raw_id))
                rid = str.__str__(raw_id)
                if not rid.strip():
                    raise RuleError("id must be a non-empty string")
                # load_rules already refuses a repeated id, and the programmatic
                # API is a second door into the same state with no lock on it. A
                # duplicate matters more here than it looks: the id keys every
                # record a rule writes to the firing log, so two rules answering
                # to one id make a run's own record unreadable.
                if rid in seen_ids:
                    raise RuleError("id is already used by an earlier rule")
                seen_ids.add(rid)
                # The same gate, for the same reason, on the other field the
                # loader validates and the programmatic door did not. `event`
                # decides which of the dispatcher's two lists a rule joins, and
                # those lists are built by comprehensions that SELECT rather
                # than partition: a value that is neither joins neither, and the
                # rule is installed, named in `applied`, and unable to fire for
                # the life of the process. The callable is replaced either way,
                # so this is not a rule that quietly does nothing; it is a slot
                # the operator was told is instrumented and is not.
                #
                # Here rather than in _make_dispatcher because that is patch
                # time, and a refusal there costs a half-patched process. This
                # loop still mutates nothing.
                #
                # What is validated is a READ of `r.event` and not a value
                # stored anywhere: `_make_dispatcher` reads the attribute again
                # at patch time, so a rule rebound after this point is out of
                # what the gate promises.
                try:
                    raw_event = r.event
                # Narrow for the reason the id read above is narrow: nothing
                # here needs protecting, and catching an interrupt would report
                # a Ctrl-C as an unreadable field.
                except Exception as exc:
                    raise RuleError("event could not be read: " + _text(exc))
                # Exactly str, and the type asked BEFORE any comparison.
                # `raw_event in _EVENTS` is `any(raw_event is e or raw_event ==
                # e)`, so membership alone would let the value answer the
                # question being asked about it: an __eq__ returning True puts a
                # rule that can never fire into the entry list. isinstance is
                # not enough either, because a str subclass is a str and still
                # chooses what it equals. Once the type is str exactly, the
                # comparison below is str's own and reads characters.
                if type(raw_event) is not str:
                    raise RuleError("event must be a string, got "
                                    + _typename(raw_event))
                # Not normalised: no strip, no case folding. load_rules compares
                # the characters as written, and a second door that forgave
                # " entry" would admit a ruleset the file door refuses, which is
                # the disagreement between the two doors that this check exists
                # to end. The refusal names what was found as well as what was
                # available, because "ENTRY" and "entry" read alike in a
                # sentence that omits the value, and that pair is the one most
                # likely to bring someone here.
                if raw_event not in _EVENTS:
                    raise RuleError("event must be one of " + repr(_EVENTS)
                                    + ", got " + repr(raw_event))
            except BaseException as exc:
                # Noted and re-raised, never replaced: the read that failed is
                # what the operator has to go and fix.
                #
                # The compiles are inside the guard rather than after it, for
                # the reason _compile cannot cover itself. Its `except
                # SyntaxError` is a claim that the SOURCE is invalid, and a
                # `when` that reads cleanly but is not a string at all
                # (`when: 5` on a hand-built rule) makes compile() raise
                # TypeError instead, past a handler that was never about it.
                # Naming the rule here holds whatever shape the field turns out
                # to be. A RuleError already names the rule and picks up the
                # location too, which is more than it had.
                #
                # "planning" rather than "patching" because nothing has been
                # wrapped yet. That is the other half of what this says: the
                # operator learns both which rule refused and that there is
                # nothing left behind to clean up.
                _note(exc, "pyteman: while planning " + described)
                raise
        self._plan = plan

    def force_patch_module(self, modname):
        mod = sys.modules.get(modname)
        if mod is not None:
            self._patch(mod, modname)

    def _patch(self, mod, modname):
        # Wraps are collected locally and published only once the whole module
        # is done. Marking an index into self._wrapped looked equivalent and is
        # not: this method both re-enters (target code executed by the callable
        # and suspendable checks can import an instrumented module) and runs
        # concurrently (two workload threads importing two instrumented modules
        # reach it on this same Patcher, since _patch runs after the per-module
        # import lock has been released). Entries from those other calls land
        # above any mark taken here, so an index-based unwind would restore and
        # forget wraps belonging to a module that has nothing to do with the
        # failing rule, leaving it silently uninstrumented.
        #
        # This buys the right SET of slots to undo, not exclusive ownership of
        # them. The two passes below resolve every rule first and write
        # afterwards, so the unsynchronised window is no longer one dispatcher
        # wide: it opens when pass 1 reads a container and closes when pass 2
        # finishes writing, and resolution of every remaining rule happens
        # inside it. Pass 2 reads each attribute twice, once before deciding
        # what to do with it and again before writing, which is what carries a
        # single thread across any re-entry the target-code checks between the
        # two reads cause. That narrows the racing case rather than closing it, and one
        # window is left: the span from the second read to the write, where both
        # invocations can find the slot unowned and the loser ends up with a
        # published entry naming an orphaned wrapper. A single thread reaches it
        # too, whenever the getattr or the setattr runs target code that imports
        # an instrumented module, which a property, a metaclass __setattr__ or a
        # module __getattr__ all can. This window is not prevented here.
        #
        # The write itself used to be a second such window, in the opposite
        # direction: a dispatcher was live in its attribute for one statement
        # before `_inflight` could answer for it, so a re-entry landing there was
        # told it belonged to nobody and wrapped it, doubling every rule
        # underneath. That one is closed, by registering in `_inflight` before
        # the setattr rather than after it; see the registration for why the
        # inverted order is harmless.
        #
        # A restore is unsynchronised for the same reason. If either invocation
        # fails, it writes the original it remembers over whichever wrapper is
        # live, which can undo a wrap the other already published. Rolling back
        # exactly these entries is still correct bookkeeping; it is not a
        # guarantee that nothing else was destroyed. See the thread-safety entry
        # under "Where each check happens" in docs/rules.md.
        wrapped, applied, current = [], [], None
        inflight = []
        reservations = []
        # Slots where this call added rules to a dispatcher that was ALREADY
        # live, so it installed nothing and `wrapped` has nothing to roll back.
        # Kept apart from `wrapped` because the two undos are different acts:
        # one puts a callable back in an attribute, the other takes rules out of
        # a dispatcher that stays exactly where it is and goes on serving the
        # rules an earlier call gave it.
        extended = []
        # Which half of the method a failure came out of. Pass 1 resolves and
        # writes nothing, pass 2 replaces callables, and the note below is the
        # only place an operator learns which, so it cannot say "patching" for
        # a `symbol` walk that raised before any setattr ran. __init__ draws the
        # same line with "planning" for the same reason.
        installing = False
        try:
            # Every rule is resolved before any attribute is written, and the
            # split into two passes is what makes grouping possible at all: two
            # rules can only be recognised as landing on ONE attribute if both
            # have been resolved while neither is installed. It buys a second
            # thing for free. Resolution now walks the target program as the
            # program actually is, instead of walking partly through wrappers
            # this same call put there a moment earlier.
            index = {}
            for ordinal, plan_entry in enumerate(self._plan):
                rule, when_code, key_code, described = plan_entry
                current = described
                if rule.module != modname:
                    continue
                parts = rule.symbol.split(".")
                container = mod
                for part in parts[:-1]:
                    container = getattr(container, part, None)
                    if container is None:
                        break
                if container is None:
                    continue
                name = parts[-1]
                # Keyed on id() and not on the container itself, because a
                # container is any object a ruleset names and need not be
                # hashable. Nothing here can be collected and have its id reused
                # under the map: the _Slot holds the container for as long as
                # the map is read. The callable itself is deliberately NOT read
                # here: pass 2 re-reads every slot before it decides anything,
                # so a value captured now would be overwritten unread, and on a
                # property or a module __getattr__ capturing it means running
                # target code for a value nobody uses.
                key = (id(container), name)
                slot = index.get(key)
                if slot is None:
                    # Existence asked once per SLOT, which is why the key is
                    # computed before it rather than after. Asking per rule read
                    # the attribute N times for N rules landing on one point,
                    # and on a property or a module __getattr__ a read RUNS
                    # target code, so the cost was not the lookup: it was the
                    # target's own side effects multiplied by how many rules the
                    # operator happened to aim at one callable.
                    # Before `hasattr`, which is the first dynamic lookup
                    # on this name and already enough to run a custom __get__
                    # or a module __getattr__. Classifying first means an
                    # unsupported shape is refused without the target being
                    # consulted about it at all. Order matters the other way
                    # too: a name that is simply ABSENT answers (None, None)
                    # here and is still skipped below, which is the promise
                    # this gate must not turn into a refusal.
                    reason, cause = _unsupported_reason(container, name)
                    if reason is not None:
                        _refuse_unsupported(modname, name, reason, cause,
                                            described)
                    if not hasattr(container, name):
                        continue
                    slot = _Slot(container, name)
                    index[key] = slot
                # The ordinal travels with the rule because ruleset order has to
                # survive being discovered late. A rule can reach this slot from
                # a LATER _patch call, through an alias or another module's
                # namespace, and it still has to take its declared place among
                # the rules already there. Position in `_plan` is that place,
                # already available and needing no field on Rule.
                slot.specs.append((rule, when_code, key_code, described,
                                   ordinal))

            # index.values() and not a second list built alongside it. A dict
            # preserves insertion order, so this is the order the slots were
            # first reached in, and keeping one container instead of two means
            # an edit cannot append to one and forget the other, which would
            # drop a slot with nothing to say so.
            installing = True
            for slot in index.values():
                # Every rule on this attribute, because a refused setattr is one
                # event for the whole group and the operator's next move is to
                # edit a rule. Joining strings rendered in __init__, never
                # reading a rule field: see the note below.
                current = "; ".join(d for _, _, _, d, _ in slot.specs)
                # Re-read, because what pass 1 saw can be gone by now. This
                # loop READS an earlier slot before it writes it, and on a
                # property or a module __getattr__ that read runs code the
                # target owns; code that imports re-enters the live hook, so
                # _patch re-enters and may install on a slot this loop has not
                # reached yet. Asking the ownership question
                # about the remembered object then answers about a callable no
                # longer in the attribute: a live dispatcher reads as unowned,
                # gets wrapped around the stale original and setattr'd over it,
                # so the rules it served stop firing for good while `applied`
                # names them as installed, and uninstall finds a stranger in the
                # slot and releases it without a word. Every question below is
                # therefore asked about the value that is actually there. That
                # covers the slots this loop has not reached; the slot being
                # built right now moves under a read taken here, so there is a
                # second read against this same hazard just before the write.
                # Asked again before the read, because pass 1 classified this
                # slot before any dispatcher existed and READING an EARLIER
                # slot in this same loop runs target code that can have
                # replaced what is stored here. Still before the `getattr`, so the classification
                # keeps costing the target nothing.
                reason, cause = _unsupported_reason(slot.container, slot.name)
                if reason is not None:
                    _refuse_unsupported(modname, slot.name, reason, cause,
                                        current)
                live = getattr(slot.container, slot.name, _ABSENT)
                if live is _ABSENT:
                    # Deleted since pass 1. A point that is not there is skipped
                    # rather than refused, and that promise holds here too.
                    continue
                owner = _live_dispatcher_owner(live)
                if owner is self:
                    # Our own dispatcher is already on the attribute. Two
                    # different histories arrive here looking identical: a
                    # re-patch of a module we have already patched, which is
                    # what force_patch_module does on purpose, and a rule
                    # reaching an attribute an EARLIER call took, through an
                    # alias created since or from another module's namespace.
                    # Grouping is scoped to one _patch call, so the second could
                    # not be recognised and both were dropped, the rule never
                    # firing and never reaching `applied`.
                    #
                    # Both are answered by adding to the dispatcher that is
                    # already there, never by wrapping it again: a second
                    # wrapper would count a fire twice for every rule the first
                    # one serves. What tells the two histories apart is the
                    # manifest the dispatcher now carries. _pyteman_state could
                    # not, holding states with no rule identity in them, and
                    # that missing identity is the whole reason the drop was
                    # silent rather than refused.
                    added, wrote_sig = self._extend_dispatcher(live, slot.specs)
                    if added:
                        extended.append((live, added, wrote_sig))
                        for spec in added:
                            applied.append(f"{modname}:{spec[0].symbol}")
                    continue
                if owner is not None:
                    raise SlotOwnershipError(
                        "pyteman: another Patcher is already dispatching on "
                        + modname + ":" + slot.name + _RETRY_AFTER_UNINSTALL)
                # Asked here, the one place every install passes through and
                # the last question about the KIND of this callable before the
                # slot is mutated. `live` is the real callable: on the two
                # extend paths, the one just above and the one further down this
                # same loop, the attribute holds OUR dispatcher, an
                # ordinary synchronous function that would answer about itself
                # rather than about what it wraps. Neither of them needs its own
                # answer, because a dispatcher is only on a slot if this check
                # passed on the original before it was built.
                #
                # The check itself imports nothing: `inspect` is bound at module
                # scope for the reason the header gives, so this runs no import
                # and opens no re-entry of that kind. It can still run target
                # code, because the three predicates reach __class__, __code__
                # and their neighbours by ordinary attribute access, and a
                # property there executes. That is the only re-entry channel
                # remaining in this section; the second re-read below sits after
                # it and covers it.
                #
                # Refusing rather than skipping, and refusing BEFORE the
                # setattr, so the handler unwinds this call's own mutations and
                # no half-applied ruleset survives the call that raised. How far
                # that reaches depends on who is calling: see the note on
                # SuspendableTargetError. The refusal names the rules through
                # the string rendered in __init__, never by reading a rule field
                # here.
                # Every container alike, and the only shape question an
                # INSTANCE point is asked: the static classification says
                # nothing there, because a property or a `__slots__` member
                # reached through an instance is supported and its value is
                # knowable only by reading it. What cannot be true of any
                # supported point is that the thing in the slot cannot be
                # called: a dispatcher around it would answer where the
                # program held a value.
                if not callable(live):
                    raise UnsupportedTargetError(
                        "pyteman: " + modname + ":" + slot.name + " is not"
                        " callable, so nothing can be dispatched on it;"
                        " refused rather than installed for " + current)
                reason, cause = _suspendable_reason(live)
                if reason is not None:
                    raise SuspendableTargetError(
                        "pyteman: " + modname + ":" + slot.name + " is "
                        + reason + ", so entry and exit cannot be timed on it;"
                        " refused rather than installed for " + current
                        ) from cause
                dispatcher = self._make_dispatcher(slot, live)
                # Re-read a SECOND time, because the one at the top of the loop
                # cannot cover this gap. Every answer above is about `live`, and
                # the callable and suspendable checks between that read and this
                # write run target code that can import an instrumented module,
                # re-entering _patch. The nested call reaches THIS attribute,
                # which the re-read above cannot see because it happened before
                # the dispatcher existed.
                # Writing anyway leaves two entries on one slot, the older
                # naming a wrapper no longer there, and `applied` naming a rule
                # that never fires again.
                #
                # Asked as an ownership question, not an identity one. Comparing
                # against the value remembered a few lines up looks like the
                # stronger test and is a broken one: an attribute reached
                # through the descriptor protocol is BUILT on each access, so
                # `inst.m is inst.m` is already False and the comparison reports
                # "replaced" for a slot nobody touched. Every instance point
                # whose function lives on the class failed that way, with a
                # diagnostic naming a race that had not happened. Identity is
                # simply unanswerable here, so ownership is the strongest
                # question this gap can be asked. It is not the whole of it: a
                # value that is nobody's dispatcher is written over, so a
                # non-pyteman replacement landing in this gap goes undetected,
                # the dispatcher goes on calling the callable captured before
                # the build, and uninstall later writes that stale callable
                # back over the replacement and reports a clean release. The
                # identity test caught that case by accident. See TASK-123.
                # Taken before the read the install decision is made from, not
                # before the write. Taken after it, the decision would rest on
                # a value another thread can already have replaced and the
                # reservation would be acquired free: A reads, parks, B
                # installs and releases, A acquires an empty registry and
                # writes over B. Everything the decision depends on, this read,
                # the ownership question below and the `setattr`, is inside it.
                #
                # It does NOT cover the ownership question asked further up
                # from the read at the top of the loop. Both of that one's
                # exits, the extend and the refusal, leave this iteration
                # before there is a reservation to take, so a call that finds
                # its own dispatcher already live extends it holding nothing.
                # This reserves the install write, and claims nothing about
                # patching as a whole.
                #
                # The tracking entry is appended BEFORE the registry write. An
                # entry we never acquired releases nothing, because the release
                # matches on the token; an acquisition with no entry is never
                # released at all, and the registry outlives the call, so that
                # slot would be unpatchable for the life of the process.
                res_key = _reservation_key(slot.container, slot.name)
                res_token = object()
                reservations.append((res_key, res_token))
                if not _reserve_slot(res_key, self, threading.get_ident(),
                                     res_token):
                    raise SlotOwnershipError(
                        "pyteman: " + modname + ":" + slot.name + " is being"
                        " installed right now, by another Patcher or by this"
                        " one on another thread" + _RETRY_WHEN_SETTLED)
                settled = getattr(slot.container, slot.name, _ABSENT)
                if settled is _ABSENT:
                    # Deleted while we were building. Same promise as the read at
                    # the top of the loop, and here skipping is not merely
                    # consistent but required: the write would resurrect a name
                    # the target program removed.
                    continue
                settled_owner = _live_dispatcher_owner(settled)
                if settled_owner is self:
                    # The nested call installed here while we were building for
                    # the same attribute. Its dispatcher is live and recorded,
                    # ours is neither, so the one on the attribute stays and the
                    # one just built is dropped: that is what keeps ONE entry on
                    # the slot and `applied` naming only what actually fires.
                    #
                    # Standing down used to cost this call's rules whenever the
                    # nested call had resolved different ones. It no longer
                    # does. The rules go into the dispatcher that won the slot,
                    # exactly as they would have at the top of the loop, and the
                    # two branches ask the same question and give the same
                    # answer. When the nested call resolved the same rules,
                    # which is what a re-entry into the same module does, the
                    # manifest recognises them and nothing is added twice.
                    added, wrote_sig = self._extend_dispatcher(
                        settled, slot.specs)
                    if added:
                        extended.append((settled, added, wrote_sig))
                        for spec in added:
                            applied.append(f"{modname}:{spec[0].symbol}")
                    continue
                if settled_owner is not None:
                    raise SlotOwnershipError(
                        "pyteman: another Patcher took " + modname + ":"
                        + slot.name + " while its dispatcher was being built"
                        + _RETRY_AFTER_UNINSTALL)
                # Asked after the re-entry rather than before it, so the answer
                # describes the namespace the setattr below actually lands in.
                owned = _owns_name(slot.container, slot.name)
                # Answerable as ours BEFORE the write, never after it. `setattr`
                # is not inert: a metaclass `__setattr__` or a `ModuleType`
                # subclass runs target code on the write itself, and one that
                # calls super() first leaves this dispatcher live in its
                # attribute while the map that speaks for it is still empty. A
                # nested call landing there is told the dispatcher belongs to
                # nobody, so it neither extends nor refuses: it WRAPS it, and one
                # attribute ends up with two of our dispatchers and two ledger
                # entries whose LIFO undo leaves the inner one installed under an
                # uninstall that reports nothing refused.
                #
                # Registering first inverts the window into a harmless one, and
                # not by making the dispatcher unreachable: `setattr` hands the
                # object to `__setattr__` as its `value` before super() stores
                # it, so a container can publish it into a namespace of its own
                # and re-enter from there, and the re-entry then reads it off a
                # real attribute. What changes is the ANSWER it gets. Told
                # "ours", it takes the `owner is self` branch and extends,
                # installing nothing and adding no ledger entry; told "nobody",
                # as it was before this order, it wrapped. Every route into this
                # window therefore lands on extend rather than on wrap, which is
                # the invariant to preserve if that branch is ever changed.
                #
                # A setattr that raises is undone by the finally: `inflight` is
                # appended to here, not after the write, so the id is already on
                # the list the cleanup reads. The id is remembered separately
                # because _restore consumes entries out of `wrapped`, so by the
                # finally that list no longer says everything this call
                # installed.
                # Last look before the write. _make_dispatcher ran between
                # the gates above and this line. It no longer runs code the
                # target owns: the parameters for a `param:` target are read
                # from type dicts and base slot descriptors, not from
                # __signature__ or __wrapped__. The GAP is still real, because
                # the `setattr` below is itself target code on a container with
                # a custom __setattr__, and because other threads exist, so a
                # classmethod can still arrive where a plain callable was.
                # Catching a changed SHAPE here is all this claims; the general
                # identity question in this window stays open and is TASK-123.
                reason, cause = _unsupported_reason(slot.container, slot.name)
                if reason is not None:
                    _refuse_unsupported(modname, slot.name, reason, cause,
                                        current)
                self._inflight[id(dispatcher)] = dispatcher
                inflight.append(id(dispatcher))
                # A 5-tuple because the undo needs two things settled here and
                # unanswerable later: whether this setattr CREATED an inherited
                # name (see _owns_name), and which exact wrapper went in (see
                # _undo_one). One entry per attribute, not per rule: the
                # dispatcher is one object and uninstall puts the real callable
                # back in one write.
                #
                # Recorded BEFORE the write, like `_inflight` above but against
                # a different hazard, so the two no longer bracket the write at
                # all. `__setattr__` is target code and can commit the store and
                # then raise, which left the dispatcher live in the attribute
                # with no entry naming it: the handler below had nothing to undo,
                # `uninstall()` answered that it had refused nothing, and the
                # point went on firing.
                # The entry is a CLAIM about a write that is about to be
                # attempted, not a record that it succeeded, and nothing reads
                # it as the latter: `_undo_one` re-reads the slot and settles
                # only what still holds this exact wrapper, so a `setattr` that
                # refused without storing drops its entry without reporting a
                # refusal. Ordering, not a new handler, is what tells the two
                # apart, because from outside the write they are indeducible.
                #
                # Safe to claim early only because `wrapped` is local and is
                # published to `self._wrapped` at the end of the call: a
                # re-entry during `__setattr__` cannot see this entry, and the
                # answer it gets about ownership still comes from `_inflight`.
                wrapped.append((slot.container, slot.name, live,
                                dispatcher, owned))
                setattr(slot.container, slot.name, dispatcher)
                for spec in slot.specs:
                    applied.append(f"{modname}:{spec[0].symbol}")
        except BaseException as exc:
            refused = _restore(wrapped)
            # Both undos run, because this call can have done both: installed a
            # dispatcher on one slot and added rules to a dispatcher already
            # live on another. Rolling back only the installs would leave the
            # additions firing under a `applied` that was never published, which
            # is the same divergence between what runs and what is recorded that
            # the branch below exists to prevent.
            _unextend(extended)
            # `applied` is deliberately NOT published on this path. The
            # invariant in uninstall's docstring is that it names published
            # wraps only, and these were rolled back as far as the container
            # allowed: `_wrapped` says what is live, `applied` says what this
            # Patcher published, and a rolled-back experiment must not read as
            # one that ran. What is withheld is THIS call's names. Names a
            # nested call published before we failed stay: that call succeeded,
            # its rules can have reached their actions through the dispatcher
            # while we were still running, and deleting its history would deny
            # firings the log already carries.
            if current is not None:
                # False is unreachable as written, and the branch is kept
                # anyway, like the last one in sitecustomize._describe. Both
                # loops in the try assign `current` before anything in their
                # body can raise, and the second cannot run at all unless the
                # first produced a slot, so no path reaches this handler with
                # `current` still None. That is a property of code an edit could
                # change, and the cost of being wrong here is a TypeError from
                # concatenating None, raised inside an except block on the
                # fail-closed path: the exact substitution the rest of this
                # function exists to prevent.
                #
                # Which rule, not just which phase. A refused setattr arrives as
                # a bare TypeError naming the attribute and not the ruleset, and
                # the operator's next move is to edit a rule. Concatenation of a
                # string built in __init__, not an f-string over rule fields:
                # this runs inside an except block, where evaluating an argument
                # is outside _note's guard and reading an attribute can raise.
                # See _describe_rule.
                phase = "patching " if installing else "resolving "
                _note(exc, "pyteman: while " + phase + current)
            # The unwind is best effort, and a refused restore is the one
            # outcome nobody can infer from the exception they are handed. It
            # says a callable OTHER than the one named above is still wrapped,
            # in a process that is being told its patch failed. Silence here
            # reads as "nothing was left behind", which is precisely the
            # opposite of what happened.
            _disclose(exc, refused)
            raise
        finally:
            # Every exit publishes, because there is only one publish. What is
            # left in `wrapped` is what is still live: on the way out normally
            # that is every wrap, and on the way out through the handler
            # _restore has already consumed the ones it undid, leaving the
            # strands. Written as `finally` rather than a copy of this line on
            # each path because the bug this ledger exists to fix WAS an exit
            # that forgot to publish, and two copies leave that shape standing
            # for a third exit to get wrong. It also covers the handler coming
            # apart: _restore is the first thing it does. _restore can raise,
            # but only on a ledger another actor shrinks under it, which is
            # uninstall's shared `_wrapped` and not this local `wrapped`; the
            # `finally` costs nothing and does not rest on that staying true.
            self._wrapped.extend(wrapped)
            # The handoff, and it happens on every exit for the same reason the
            # publish does. A dispatcher this call installed is now answerable
            # from `_wrapped` if it survived, and is not live at all if _restore
            # took it back, so the in-flight map has nothing left to say about
            # either. Discarded by id rather than by rebuilding the map, because
            # a re-entrant call's ids are in there too and must survive ours.
            for wrapper_id in inflight:
                self._inflight.pop(wrapper_id, None)
            # Released on every exit, and released LAST: the reservation is
            # what makes this call's window exclusive, and the undo above is
            # part of the window. Nothing here can raise over a primary
            # exception on its way out: the key is a tuple of an int and a
            # str, the match is `is`, and the pop happens under a lock this
            # call is not already holding.
            for res_key, res_token in reservations:
                _release_slot(res_key, res_token)
        self.applied.extend(applied)

    def _make_dispatcher(self, slot, original):
        """One callable serving every rule on one attribute, in ruleset order.

        One dispatcher and not one wrapper per rule nested inside the last.
        Nesting would put N ledger entries on a single (container, name), and
        the undo is correct there only because _undo_one re-asks _owns_name at
        undo time; resting a new design on a guard that had to be fixed to make
        it work is the wrong kind of cheap. The flat form also shows its work:
        uninstall puts the real callable back in ONE write, so a refused unwind
        cannot leave a half-peeled onion where some rules still fire and others
        do not.
        """
        # A state per rule, never one shared across the slot. `fires` and
        # `seen_keys` are precisely what countdown and once_per count, so a
        # shared counter would make each rule's gate depend on how many OTHER
        # rules happen to sit on the same callable, which is a coupling no
        # ruleset author can see or control. The ordinal rides along so a rule
        # added by a LATER call can be merged into its declared place instead of
        # appended after rules it was written before.
        bound = [(rule, when_code, key_code, _new_state(), ordinal)
                 for rule, when_code, key_code, _, ordinal in slot.specs]

        # Patch-time analysis, once per wrapped callable rather than per firing,
        # and not install time: this runs from _patch, on import or on a
        # force_patch_module, long after the expressions compiled in __init__. A
        # param: target needs the real signature to bind positional-or-keyword
        # arguments by name, so compute it once here and never mutate the user's
        # callable. The kind comes from the same parser the resolver uses, so
        # whitespace or a typo cannot make the two disagree. Once for the slot
        # and not once per rule, because `original` is one object and every rule
        # here would ask it the same question.
        sig = None
        sig_reason = None
        if _needs_signature(slot.specs):
            # No try here, and nothing to place relative to one. This call
            # imports nothing and runs no code the intercepted object
            # controls, so the failure the old placement existed to separate
            # cannot arise: a different rule's refused setattr can no longer
            # reach this line as a TypeError indistinguishable from "this
            # callable has no readable signature". An unreadable callable is
            # reported through the returned reason and never as an exception,
            # so anything raised here belongs to someone else and stays loud.
            sig, sig_reason = _binding_signature(original)

        # On `comp` rather than in closure locals, for the reason _Composite
        # gives. The split itself is still made once here rather than tested
        # per call, and the filters preserve ruleset order within each event
        # because that IS the declared order: there is no priority field and
        # adding one was refused.
        comp = _Composite(original, sig, sig_reason)
        comp.entries = [spec for spec in bound if spec[0].event == "entry"]
        comp.exits = [spec for spec in bound if spec[0].event == "exit"]
        comp.served = {id(spec[0]): spec for spec in bound}
        # Bound here so a firing costs no attribute traversal. `self` is already
        # in the closure for nothing else, and `log` is written once in
        # __init__ and never reassigned, so the live read bought nothing.
        # `original` stays a closure local too, even though `comp` holds it:
        # the call below is the hot line of the whole library, and unlike the
        # rule lists this one can never change.
        log = self.log

        @functools.wraps(original)
        def dispatcher(*args, **kwargs):
            ctx = {"args": args, "kwargs": kwargs}
            # Read once into a local, because an extension can rebind it between
            # this call and the next and reading it twice could see both answers.
            sig = comp.sig
            # Only param:-targeted rules pay for the ctx entry.
            if sig is not None:
                ctx["_signature"] = sig
            if comp.sig_reason is not None:
                ctx["_signature_unavailable"] = comp.sig_reason
            # No `fires` seeded here. With one rule there was one state to seed
            # it from; with N there is no single answer, and none is needed:
            # _gate writes ctx["fires"] from the firing rule's own state before
            # it evaluates anything that can read it.
            for rule, when_code, key_code, state, _ in comp.entries:
                if _gate(rule, state, ctx, when_code, key_code):
                    run_action(rule, ctx, log=log)
                    # pop and not get, so the key is CONSUMED. One ctx serves
                    # every rule on the slot and `when` expressions are eval'd
                    # against it, so a value left behind is one rule's pending
                    # return value sitting in the namespace the NEXT rule's
                    # condition is read in. No ruleset can observe the
                    # difference today, because every action that sets an
                    # override is consumed in the iteration that ran it. This
                    # is what keeps that true, not a fix for a live bug.
                    override = ctx.pop("_override", _NO_OVERRIDE)
                    if override is not _NO_OVERRIDE:
                        # The body does not run and no exit runs either. An exit
                        # rule is a statement about a call that happened, and
                        # this call did not happen. Returning straight out also
                        # means there is no finally to fake: an entry that
                        # RAISES leaves by this same path, having run nothing
                        # below it, without a handler here having to arrange it.
                        return override
            result = None
            exc = None
            try:
                result = original(*args, **kwargs)
            except BaseException as e:
                exc = e
                raise
            finally:
                for rule, when_code, key_code, state, _ in comp.exits:
                    # Both re-seeded per rule, for two different reasons.
                    # `result` is the handoff itself, rewritten after every
                    # override so the next exit reads the previous one's
                    # answer. `exc` cannot change between iterations, and was
                    # set once above this loop until a condition was found able
                    # to overwrite it: eval_expr used to hand `ctx` to eval as
                    # the LOCALS mapping, so an assignment expression in one
                    # rule's `when` stored straight into it and every exit
                    # after that one read what that rule left instead of what
                    # the body raised. CFG-02 closed that channel at the
                    # source by evaluating against a namespace built from
                    # `ctx` rather than against `ctx` itself, which also shut
                    # the same route to `args`, `kwargs` and the `_signature`
                    # keys. The `exc` seed stays here anyway: contract 4 says
                    # every exit reached sees the body's own exception, and
                    # that guarantee should not rest on a detail of how
                    # conditions happen to be evaluated.
                    ctx["result"] = result
                    ctx["exc"] = exc
                    if _gate(rule, state, ctx, when_code, key_code):
                        run_action(rule, ctx, log=log)
                        # Popped on both paths so it cannot leak into the next
                        # rule's context, and consumed on only one. An exit rule
                        # has never been able to swallow an exception the body
                        # raised, and RT-02 does not grant it that: on the
                        # failing path every exit still runs and still sees the
                        # original `exc` with `result` None, and its override is
                        # discarded rather than turned into a return value. An
                        # exit that RAISES is a different matter and needs no
                        # code: raising inside this finally replaces the
                        # in-flight exception with __context__ already set,
                        # which is the ordinary Python chaining the contract
                        # asks for, and it stops the exits after it.
                        override = ctx.pop("_override", _NO_OVERRIDE)
                        if override is not _NO_OVERRIDE and exc is None:
                            # Visible to every exit after this one through
                            # ctx["result"], and the last one to set it wins.
                            result = override
            return result

        # Kept under the name the module and the tests already ask for, now
        # holding one state per rule. It answers "is this ours"; the separate
        # question "whose, and still live" belongs to _pyteman_owner, because a
        # marker that cannot name an owner is how a second Patcher came to be
        # dropped in silence. Set after functools.wraps, which copies the
        # original's __dict__ and would otherwise hand us a retired dispatcher's
        # markers.
        dispatcher._pyteman_state = [spec[3] for spec in bound]
        dispatcher._pyteman_owner = self
        # The handle a later call needs to add a rule here instead of dropping
        # it. Published in the same breath as the owner, because the two answer
        # halves of one question: _pyteman_owner says the dispatcher is ours,
        # and only this says WHICH rules it already serves. Owning without
        # knowing is precisely the state in which a rule reaching an attribute
        # an earlier call took could be neither recognised nor refused, so it
        # vanished.
        dispatcher._pyteman_composite = comp
        return dispatcher

    def _extend_dispatcher(self, dispatcher, specs):
        """Add rules to a dispatcher that is already live.

        Returns the specs it added and whether it was the call that settled the
        slot's signature. _unextend needs both: the specs say what to take out,
        and the flag says whether the cached signature is this call's to drop.

        The alternative to dropping them. `specs` are the rules this _patch call
        resolved onto an attribute that already holds a dispatcher of ours, and
        the empty return is the honest answer to a re-patch: every rule is
        already served, so nothing is added, nothing fires twice, and `applied`
        does not grow. That is the historical idempotence contract, now resting
        on rule identity instead of on the mere presence of a marker.

        Membership is by rule identity and never by rule CONTENT. Two rules
        written identically but given different ids are two rules the operator
        meant to have, and deduplicating them here would be this function
        committing the silent drop it exists to prevent.
        """
        comp = dispatcher._pyteman_composite
        fresh = [spec for spec in specs if id(spec[0]) not in comp.served]
        if not fresh:
            return [], False

        # BEFORE anything is rebound. _binding_signature does NOT run target
        # code: it reads type dicts and base slot descriptors, so a
        # __signature__ property, a __wrapped__ chain or a forged __mro__
        # cannot call back into this dispatcher from here. The order is kept
        # anyway, because it costs nothing and the reads BELOW it do open that
        # window, so a reader who moves this line has to think about those
        # rather than about this one.
        #
        # Only asked when a new rule needs it and the slot has no answer yet. A
        # signature that could not be built is a settled fact about `original`,
        # which the extension does not change, so it is never recomputed:
        # retrying would re-run a failing resolution on every later alias.
        computed = None
        if (comp.sig is None and comp.sig_reason is None
                and _needs_signature(fresh)):
            computed = _binding_signature(comp.original)

        # Rules already bound keep the state object they were given, lock
        # included, because the specs carrying them are reused by reference
        # rather than rebuilt here.
        added = [(rule, when_code, key_code, _new_state(), ordinal)
                 for rule, when_code, key_code, _, ordinal in fresh]
        entries = [spec for spec in added if spec[0].event == "entry"]
        exits = [spec for spec in added if spec[0].event == "exit"]

        # Filtered a SECOND time, against the manifest as it stands NOW, and
        # UNCONDITIONALLY: a read above can run target code, and a re-entry one
        # of them causes does not only READ this dispatcher, it can reach this
        # same slot and merge the very rules `fresh` names, publishing them in
        # `applied` as its own. Merging them again below would put two specs
        # carrying two separate states on one rule, so its `countdown` would
        # reach the threshold on a call the operator never wrote and its
        # `once_per` would fire twice for one key. Nothing would report it
        # either: `served` keeps one spec per rule, so a duplicate hides from
        # the very manifest that exists to make a drop visible.
        #
        # TWO reads open that window, and both are reads of RULE attributes,
        # not of the target: `_needs_signature` reads `action` and stringifies
        # `target`, and the split above reads `event`. The signature
        # computation between them is no longer one of them, because
        # _binding_signature reads type dicts and base slot descriptors and so
        # runs nothing the target controls. That is why the re-filter stays
        # unconditional rather than being narrowed to the signature branch: the
        # earliest window is `_needs_signature`, which is also a term of the
        # condition guarding the computation, so a rule that re-enters from
        # `action` and then answers "no signature needed" would skip a
        # signature-gated re-filter entirely and merge itself twice. Nothing
        # below reads a rule attribute, so here is the last window.
        merged = comp.served
        added = [spec for spec in added if id(spec[0]) not in merged]
        if not added:
            return [], False
        entries = [spec for spec in entries if id(spec[0]) not in merged]
        exits = [spec for spec in exits if id(spec[0]) not in merged]

        # Written only if the slot STILL has no answer. A re-entry during the
        # read above may have published one, and rules it installed have been
        # dispatched against that answer ever since; two reads of a callable
        # whose introspectability changes between them disagree, and the one
        # already in use is the one the ruleset has seen. The flag travels out
        # because a cached signature is not a fact about the rules: the
        # dispatcher hands `_signature_unparseable` to every `when` expression
        # on the slot, so a call that writes one and then fails has changed the
        # namespace the rules it did not touch are evaluated in.
        wrote_sig = False
        if (computed is not None
                and comp.sig is None and comp.sig_reason is None):
            comp.sig, comp.sig_reason = computed
            wrote_sig = True
        # Sorted by ordinal rather than appended, because a rule discovered late
        # is not a rule declared late. An alias can bring a rule written at the
        # top of the ruleset to a slot whose rules were all resolved on an
        # earlier import, and appending would run it after rules it precedes in
        # the file the operator wrote. Rebound rather than mutated in place: see
        # _Composite for why an in-flight call must not watch its own list grow.
        comp.entries = sorted(comp.entries + entries, key=lambda s: s[4])
        comp.exits = sorted(comp.exits + exits, key=lambda s: s[4])
        for spec in added:
            comp.served[id(spec[0])] = spec
        # Rebuilt rather than extended, so the states stay in ruleset order and
        # the marker keeps meaning what its name says for a dispatcher that grew.
        dispatcher._pyteman_state = [spec[3] for spec in comp.rank()]
        return added, wrote_sig

    def install_hook(self):
        """Hook __import__ so modules imported later get patched. Idempotent.

        A second call used to install a second hook over the first and save the
        first as `_orig_import`, so the "original" this Patcher promised to put
        back was its own wrapper, and uninstall restored a hook instead of
        removing one. There is nothing for a second call to add anyway: the
        first hook already sees every import.

        The closure tests `self._hook is hooked` before doing any work, which is
        what lets uninstall DEACTIVATE a hook it has no way to remove. A third
        party that wrapped us holds our closure inside its own and we cannot
        edit theirs; a deactivated hook still delegates, so their chain keeps
        working, and it applies no new patches. Keyed on identity rather than a
        flag so that a reinstall retires the old closure for good, `_hook`
        naming a different one from then on.
        """
        if self._hook is not None:
            return
        orig = builtins.__import__

        def hooked(name, *a, **k):
            mod = orig(name, *a, **k)
            if self._hook is hooked:
                target = sys.modules.get(name)
                if target is not None:
                    self._patch(target, name)
            return mod

        # Read by uninstall, through _is_pyteman_hook, to tell another
        # Patcher's hook from a stranger's.
        hooked._pyteman_patcher = self
        self._orig_import = orig
        self._hook = hooked
        builtins.__import__ = hooked

    def uninstall(self):
        """Reverse the hook and every wrap. Returns the restores that refused.

        Each refusal is a `(container, name, exception)` triple, unrendered, so
        the caller decides how to report it and a hostile __str__ cannot reach
        back into the loop; _disclose is the one place that turns them into
        words. The list is empty in every ordinary case, and it is not an error
        channel: see _restore for why this has to be best effort.

        The live `__import__` is classified BEFORE anything is written, and it
        is one of three things. Ours, the LIFO-correct case, so the callable it
        displaced goes back. Another Patcher's, meaning one nested inside us is
        still hooked, which raises UninstallOrderError before the hook is
        touched and before any wrap is restored (see there for why standing
        down instead would resurrect a dead hook, and why a refusal is a no-op
        the caller can retry). Or a stranger's, installed over us afterwards,
        which is left exactly where it is: we cannot know what it saved, and
        writing over it would drop a third party's instrumentation to tidy up
        our own. In that last case clearing `_hook` deactivates our closure, so
        if the stranger delegates to it, it delegates to a pass-through that
        applies no new patches.

        `applied` is deliberately NOT cleared here, and the asymmetry with
        `_wrapped` is worth stating because it looks like an oversight. _patch
        maintains the invariant that a name appears there only for a wrap that
        was published, which is what keeps a rolled-back experiment from being
        described as one that ran. That invariant is scoped to _patch. Across a
        successful _patch and a later uninstall, `applied` is a HISTORICAL
        record of what this Patcher ever wrapped, not a description of what is
        wrapped now. So an uninstall followed by a genuine re-patch appends a
        second occurrence of the same name, which is the history being accurate
        rather than a double count. Nothing in the package reads it after an
        uninstall today; a caller that wants live state should read `_wrapped`.

        `_wrapped` is not cleared here either, and that is the point rather than
        a second oversight: _restore consumes it (see there), so clearing it
        unconditionally threw away the record of wraps that are demonstrably
        still in place. What that buys the caller is a retry. A container that
        refused once, say one sealed for the duration of a test, can be retried
        once it stops refusing, and the same triples come back until it does.
        """
        if self._hook is not None:
            live = builtins.__import__
            if live is self._hook:
                builtins.__import__ = self._orig_import
            elif _is_pyteman_hook(live):
                raise UninstallOrderError(
                    "pyteman: another Patcher's import hook is installed over "
                    "this one" + _RETRY_AFTER_UNINSTALL)
            self._hook = None
            self._orig_import = None
        return _restore(self._wrapped)


def _gate(rule, state, ctx, when_code=None, key_code=None):
    """Whether this visit fires, decided so that concurrent visits cannot agree.

    The decision is a check followed by an act, and what sits between them is
    the operator's condition, which is code of unbounded duration. So the claim
    is made under the rule's lock, in three sections short enough that none of
    them can run anything the operator wrote, which is what the key contract in
    OncePerKeyError exists to guarantee:

      1. the ticket, so this visit has a count of its own;
      2. the membership read, which lets an already-consumed key skip the
         condition rather than evaluate it pointlessly;
      3. the re-check and the claim, which is the decision itself.

    The ticket comes FIRST and every later count is read from it, never from
    `state["fires"]` again. That ordering is not cosmetic. `ctx["fires"]` is
    published before the key is evaluated because `key: fires` is a legal rule,
    and a key that read the shared counter after other threads had advanced it
    would collide with keys belonging to visits it has nothing to do with.

    A raise from the key expression, from validation, or from the condition
    leaves the visit counted and the key unclaimed. The action runs outside
    every critical section.
    """
    lock = state["lock"]
    mode = rule.fire.get("mode", "always")

    with lock:
        state["fires"] += 1
        ticket = state["fires"]
    ctx["fires"] = ticket

    if mode == "countdown":
        n = int(rule.fire.get("n", 1))
        if ticket != n + 1:
            return False

    # Bound here rather than only inside the branch, so the claim section's two
    # reads are unconditionally bound for a reader and for a checker, instead of
    # resting on the fact that both branches test the same mode.
    pending_key = None
    if mode == "once_per":
        pending_key = eval_expr(key_code, ctx) if key_code is not None else None
        _check_once_per_key(rule, pending_key)
        with lock:
            if pending_key in state["seen_keys"]:
                return False

    if when_code is not None and not eval_expr(when_code, ctx):
        return False

    if mode == "once_per":
        # Read again, because the condition just ran and another thread may have
        # claimed this key while it did. A false condition still does not
        # consume the key, so a later visit with the same key can fire.
        with lock:
            if pending_key in state["seen_keys"]:
                return False
            state["seen_keys"].add(pending_key)
    return True


def install(rules, log=None):
    p = Patcher(rules, log)
    p.install_hook()
    return p


def activate(rules, log=None, modules=()):
    """Install the hook and patch `modules` as one unit, unwinding on failure.

    install() on its own hooks `__import__` and patches lazily, so callers that
    already know which loaded modules they need patched come through here
    instead. A failure anywhere in the loop removes the import hook and
    ATTEMPTS every wrap made so far before it propagates.

    Attempts, not guarantees, and the difference is the container's to make. One
    that refuses setattr keeps its wrap, and that is reported on the exception
    rather than hidden (see _restore and _disclose). Unwinding completely is the
    ordinary outcome, not something this function is in a position to promise.

    _patch unwinds each module on its own (see there); what this adds is the
    hook and the modules patched BEFORE the one that failed, which nothing
    inside a single _patch call can reach.
    """
    p = install(rules, log)
    try:
        for modname in modules:
            p.force_patch_module(modname)
    except BaseException as exc:
        # uninstall() first, on its own line: _disclose guards its rendering,
        # but an argument is evaluated before the callee is entered, so work
        # done there would sit outside that guard.
        try:
            refused = p.uninstall()
        except BaseException as cleanup:
            # The unwind itself came apart. _restore walks a fixed index range,
            # so a ledger that SHRINKS under it, which only a concurrent or
            # re-entered uninstall can do, can leave an index the list no
            # longer has: a shrink to exactly the cursor is survived, a deeper
            # one raises (the thread-safety limit in docs/rules.md). Letting
            # that propagate would hand the operator a symptom of the cleanup
            # in place of the failure they have to act on, so it travels as a
            # note on that failure instead. Rendered through the helpers, which
            # return an exact str, so the interpolation cannot run the cleanup
            # exception's code.
            refused = []
            _note(exc, "pyteman: the rollback did not finish: "
                       f"{_typename(cleanup)}: {_text(cleanup)}")
        # Attached to the original rather than raised over it: the reason
        # activation failed is what the operator has to act on.
        _disclose(exc, refused)
        raise
    return p
