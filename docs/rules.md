# Rule reference

Every field a rule can carry, the values each one accepts, and where the
check happens. The narrative introduction is in the README; this is the
reference the loader actually implements, in `src/pyteman/rules.py`.

## Where each check happens

`sitecustomize` calls `load_rules` before it installs the import hook, so a
ruleset that fails validation never half instruments the workload: the run is
refused outright. Setting `PYTEMAN_RULES` is the request; any failure from
there up to and including the patch loop writes `pyteman: refusing to start:
<phase>: <detail>` on stderr and exits 2 with the workload never started.
Without
`PYTEMAN_RULES` the module does nothing at all, and says nothing either.

The exit is taken with `os._exit`, which looks heavy-handed and is the only
route that works. CPython imports `sitecustomize` inside a `try/except
Exception` in `site.execsitecustomize`, so a `RuleError` raised there is
swallowed: one `Error in sitecustomize` line reaches stderr while the workload
runs UNINSTRUMENTED and the process exits 0, which is a successful-looking run
of an experiment that injected nothing. `SystemExit` escapes that handler,
being a `BaseException`, but startup then fails with `Fatal Python error:
init_import_site` and substitutes exit 1 for the code requested. Only
`os._exit` both stops the workload and keeps the code.

Activation is also atomic, and so is every later patch. The patch loop keeps
the wraps it makes to itself and publishes them only once the module is
finished; anything that fails partway through undoes them first and then lets
the failure propagate, so no half-patched module is left behind. Keeping them
local rather than marking a position in a shared list is what makes this hold
under re-entry: the loop is re-entered while it builds a wrapper, and the
entries that nested call publishes are interleaved with its own, so they could
not be told apart by position. It is also what makes the set correct when two
threads run the loop at once, though that is not the same as being safe under
threads; the known limit below says what is left. The programmatic entry point
is `pyteman.patcher.activate`, which adds the one thing the loop cannot reach
from inside: it also removes the import hook and the modules patched before the
one that failed.

Before either of those runs, the ruleset is PLANNED. Every expression is
compiled and every rule's identity is checked and rendered while nothing has
been mutated
yet, so a ruleset that cannot be planned fails with no hook installed and no
callable replaced. Rules loaded from YAML have been validated already and reach
this step intact; rules built by hand through the programmatic API have not, and
their fields are whatever the caller put there, up to a `when` that is a
property raising on read or a `fire` that is not a mapping at all. Checking the
identity is part of planning for that reason: a rule whose `id` is missing,
blank, not a string, unreadable, or already used by an earlier rule is refused
here, and the Ids section below says why that refusal is a refusal rather than
a warning. A failure
there arrives carrying `pyteman: while planning <rule>`, which names the rule
the same way the patching note does and differs from it deliberately: it also
tells you the failure happened before the first wrap, so there is nothing left
behind to clean up.

One shape of ruleset makes that loop re-enter itself, and the re-entry is
visible in what you are handed. It is a consequence of how `param:` targets are
implemented rather than a property of patching in general: a rule using one
makes the loop import `inspect` to read the wrapped callable's signature, and
because that import happens while the hook is live it is served by the hook,
which patches `inspect` against the whole ruleset before the outer rule is
finished. A rule that fails there surfaces through the outer loop, and the
failure arrives carrying one `pyteman: while patching <rule>` note per level,
innermost first. Read them as a stack: the FIRST note names the rule that
actually failed, and the ones after it say what was being patched when it
surfaced. A ruleset with no `param:` target never nests, and gets one note.

The undo is best effort, because putting an attribute back is a `setattr` and a
container is free to refuse it. A module or class that accepted the wrapper and
then rejects the original keeps that wrap for as long as it goes on refusing.
What is guaranteed is the disclosure, the finishing, and the record: every
remaining entry is still attempted, since each one is attempted separately, and
each refusal is attached to the failure you receive as a note reading
`pyteman: rollback could not restore <container>.<attr>: <exc-type>:
<why>`. The container is named by its own `__name__`, and by its type when it
has none, as a plain instance does. That is usually the name the rule spells,
but it is the CONTAINER's name rather than the rule's, and the two come apart
where a `symbol:` does not name its container directly: an alias reports what
it points at, so `Shim.run` against `Shim = Engine` reports `Engine.run`, and a
path several levels deep reports only the last container it walked to. The
example has to be an alias to something that ACCEPTS the wrap and then refuses
the restore, since the misnamed note exists only where the rollback was turned
away; an alias to a built-in is no example at all, `setattr` on an immutable
type failing at patch time, which leaves no entry to roll back and no note to
misname. The rule's own spelling is on the note naming the rule.
What the container is never named by is its own RENDERING: calling
`str` or `repr` on a container would run its code at the moment it has just
demonstrated it is hostile. So a failed
patch normally means either that nothing was left behind, or that a note says
precisely what was. Two things break that, and neither is one the wording
should paper over. The first is a failure that cannot carry notes at all:
an exception shadowing `__notes__` with something that is not a list makes
`add_note` raise, and pyteman drops the note rather than let the reporting throw
its own error over the one you have to act on. In that case a wrap can survive
with nothing announcing it, and the only signal is the failure itself. It is
rare and it is the failing object's own doing. The second is an unwind that
does not finish: the refusals are gathered as the walk goes, so if the walk
itself raises, which under the thread-safety limit below it can, what it had
gathered goes with the frame. `activate()` still says `pyteman: the rollback
did not finish` and still hands you the failure you have to act on, but on that
path it does not go on to name what is left wrapped.
Those notes reach stderr on the refusal path, where no traceback is
ever printed; through the programmatic API they are on the exception, in
`__notes__`, and a traceback shows them.

A refusal is REMEMBERED as well as reported, which is what makes the note
actionable rather than just informative. The entry stays on the Patcher, so
`uninstall()` attempts it again and succeeds once the container has stopped
refusing, the ordinary case for one sealed only while a test runs. Calling
`uninstall()` a second time is therefore meaningful rather than a no-op, and it
keeps returning the same triples until the restore goes through. An entry is
dropped once its undo SETTLED, which is three outcomes rather than one: the
original written back, a name the patch CREATED in the container's own
namespace deleted so the class inherits from its base again, or the slot
RELEASED because it no longer holds our wrapper and is no longer ours to give
back. Deleting is reserved for that first case, confirmed by looking rather
than by the flag alone: a `__slots__` member or a property is the container's
own storage and never appears in its `__dict__`, and deleting one of those
would clear the slot and take the original with it.

So what the Patcher holds is what it still has wrapped, on the failure path as
much as the successful one, with two exceptions. A name DELETED from its
container after we wrapped it makes the read itself fail, and that lands on the
refusal channel today, so the entry is kept and re-reported although nothing is
wrapped any more. And nothing else must write to that record: another thread is
the obvious way that breaks, and a re-entrant `uninstall` driven from a
container's own `__setattr__` is the same break on a single thread. The
concurrency limit below is where it stops holding. That retry belongs to
whoever HOLDS the Patcher, which means callers of `install()` and
`force_patch_module()`. `activate()` is the exception: when it refuses it
raises instead of returning, and the Patcher it built is a local that goes with
the frame, so the notes on the exception are the whole of what survives a
failed activation.

A release is a success and not a refusal, and it is reported as neither: the
entry simply goes. Something replaced the callable after we wrapped it, and the
replacement is the newer decision. Writing our saved original over it would
delete a live object to restore a dead one, so pyteman lets go of the slot
instead, and says nothing, because there is nothing left for the caller to act
on.

`uninstall()` reverses the import hook as well, and there it supports nesting
in LIFO order ONLY. Patchers installed one over another must be uninstalled
innermost first; asked out of order, `uninstall()` raises `UninstallOrderError`
before it mutates anything, so the refused call is a no-op and the same call
succeeds once the inner Patcher is gone. Abstaining would not be enough: the
inner Patcher saved OUR hook as the import to put back, so its own perfectly
correct uninstall would then reinstate a hook that had already been asked to
leave. What gets asked is whether the live hook is some Patcher's CURRENT one,
not whether it carries a pyteman marker. The marker outlives the hook, and a
hook whose Patcher has already uninstalled is inert: nobody can be asked to
clear it, so refusing on its behalf would wedge the Patcher underneath it for
good, its wraps included, since the refusal comes before them. A live hook
belonging to nobody we recognise, a third party who installed after us, is left
exactly where it is; pyteman does not delete someone else's hook to tidy up its
own. Ours may still be reachable inside theirs, and a closure another object
holds cannot be removed from it, so it is retired rather than removed: it goes
on delegating and applies no new patches.

Because the entry survives, a later unwind re-attempts it and would report it
a second time. The disclosure drops any STRAND it has already written,
matching the individual `<container>.<attr>: <exc-type>: <why>` pieces rather
than whole notes, because the two disclosures rarely cover the same set: the
module-level unwind names the module it was working on, and `activate()` names
everything still wrapped, which is a superset whenever an earlier module
stranded something too. Compared whole, those are two different strings and
both would be attached, naming the shared strand twice. So one stranded
callable reads as one. Two distinct strands that render identically, meaning
the same attribute name on containers whose names match, are the price and are
reported once. A refusal whose own message contains `; ` is reported twice
instead, which is the deliberate direction: a repeated strand is visible to
whoever reads the notes and a suppressed one is not. A refusal whose message
VARIES between attempts, carrying a clock reading or a retry count, is reported
each time, which is that same safe direction arrived at by a different route.

Building those messages CAN fail, and the design is about what a failure there
costs. Everything in them comes from your code: `__str__` on an exception,
`__repr__` or `__format__` on a container, the `__notes__` attribute and the
container it returns, and even the `__name__` a metaclass serves for a type.
Raising is not the only way they fail, and it was not the hardest one: a
`__str__` returning a `str` SUBCLASS satisfies every check that asks whether a
value is text, and then runs its own `__repr__` when somebody interpolates it,
which put the failure back inside the helpers written to absorb it. So the two
helpers guarantee an exact `str` rather than merely a `str` instance, which
makes the result inert for every caller instead of making each call site
remember. On top of that, the rendering is never worth more than the guarantee
it describes, and it is never done anywhere a failure could reach the
guarantee. Restoring attributes and describing the refusals are two separate
steps rather than one loop, so an object that cannot be rendered can no longer
cut the unwind short at whatever entry it had reached. The same principle moves
work earlier as well as apart: which rule was being patched is rendered when the
`Patcher` is built, before the import hook exists and before any callable has
been replaced, because a rule whose `id` is a property that raises would
otherwise take the reporting down at the one moment the reporting is all you
have. Guarding `str()` does not reach that case, since the attribute is read in
order to produce the argument being guarded. The refusal path builds
its diagnostic inside the same `try/finally` that calls `os._exit`, so an
exception raised while describing a failure costs the message and never the
exit. Before that split, it escaped into CPython's `try/except Exception`
around the sitecustomize import and was swallowed there, which let the workload
run uninstrumented and report success.

What you get instead of a message is a smaller one. An object that will not
stringify becomes `<unprintable T>`, a type whose name will not render becomes
`<unknown type>`, notes that cannot be read become `<notes unavailable>`, a rule
whose id will not be read is reported as `<unreadable id>` with the module and
symbol it was aimed at still named, and a
refusal that defeats even those degradations still reports how many attributes
were left wrapped, because that count is the part you cannot work out from
anywhere else. The degradations are also kept as narrow as the failure: a
`__notes__` container pyteman will not read loses the notes and not the
exception type and message in front of them, and a rule whose id refuses to be
read loses the id and not the location, which is what you would grep your
ruleset for. Only a rule that will not give up its module or symbol either is
reduced to its id alone.

Holding that last one took one step more than it looks. The container is tested
with `type(x) is list` and not with `isinstance`, because `isinstance` is not a
type test. Against an object whose type is not a list subtype it falls back to
reading `__class__`, an ordinary attribute lookup that a property is free to
define and free to raise from, so the CHECK was user code too. When it raised it
did so from the one line in the function sitting outside every guard, and the
whole line went with it: the operator got the phase, a colon, and nothing. The
exit held throughout, since it does not depend on any of this, but losing the
exception type and message is exactly what these degradations exist to prevent.
`add_note` only ever builds an exact list, so the narrower test gives up nothing
pyteman itself produces.

Known limit: what differs between the two paths is how the failure REACHES you,
not what it leaves behind. A rule whose module is not yet imported is patched
later by the import hook, while the workload is running, and a `setattr`
refused at that point (an immutable type, a descriptor) comes out as an
ordinary traceback from your own `import` statement rather than as a refusal on
stderr, because by then the process belongs to your program and not to startup.
The wraps that patch had already made are undone either way, and the rest of
the ruleset stays live: the hook is still installed, since the modules that
have nothing to do with the failing rule are still correctly instrumented.

Known limit: the patch loop is not thread-safe, and neither is the rollback
under threads. Each slot is read, tested for a wrap pyteman already made, read a
second time, and written, with the wrapper built between the two reads and
nothing held across any of it. That second read is why the ordinary re-entry
that building a wrapper performs does not leave a single thread with a broken
ledger; the residual single-threaded case, where target code runs inside the
`getattr` or the `setattr` itself, is in the windows paragraph below. The
ownership paragraph below says what the read does when it finds the slot taken,
and "More than one rule on one point" says what becomes of the rules this call
had resolved for it. Two invocations that both clear it before either writes
still hold the same unwrapped original, so the second
write wins and the first wrapper is orphaned: its rule is silently
uninstrumented while the applied list still names it. Should either invocation
then fail, its rollback writes the saved original over whichever wrapper is
live, which can remove a wrap the other one completed. Two threads importing
the same instrumented module can race this way, and so can `force_patch_module`
running against the import hook. A concurrent `uninstall` is a third case: it
walks the wrap list by descending index and drops each entry as it restores it,
so a wrap published while it runs sits above the index it started from and that
pass neither sees nor removes it. It stays on the list, and the next
`uninstall` takes it. That is the one corner of this paragraph the ledger
change improves: the wrap is missed, not forgotten. A list that SHRINKS under
that walk is the other direction and is worse. The index range is computed
once, before the loop, so a removal by a concurrent or re-entered `uninstall`
leaves indices the list no longer has. A shrink to exactly the cursor is
survived: the delete tests its index before using it, so the walk carries on
and finishes the unwind. A deeper shrink is not survived, and it raises at the
unguarded read that opens the next pass rather than at the delete. `activate()`
is written for that: it calls `uninstall()` from inside its own handler,
catches whatever the unwind raises, and attaches it as a `pyteman: the rollback
did not finish` note on the failure being handled, rather than letting a
symptom of the cleanup replace the rule you have to go and edit. That is also
where the second hole in the disclosure above comes from. Callers of
`install()` and `force_patch_module()` invoke `uninstall()` themselves and see
it raise.

A shrink BELOW the cursor is the quiet one, and it used to be the worst of the
three. Every index from the cursor up then addresses a different entry than it
did a moment earlier, and the walk deleted by that index, so it dropped the
record of whatever had moved into position rather than the entry it had just
restored. Where the displaced entry was a retained refusal the cost was total:
that callable is still wrapped, its original was then recorded nowhere, and the
walk carried on to empty the list, after which `uninstall` reported success
with instrumentation live in the process. Reaching it needs an entry above the
cursor that the walk will not itself remove, and there are two of those: a
retained refusal, which is exactly what stops the list shrinking in step with
the walk, and a wrap a concurrent patch published past the end of the range
this walk fixed when it started. The second involves no refusal anywhere. The
delete now confirms the entry is still the one it put back and leaves the list
alone when it is not, so nothing still wrapped is forgotten.

What a shrink costs now is a wasted read. Sliding the entry down puts it on an
index the descending walk has yet to reach, so it is visited a second time. The
second visit reads the slot, finds the original rather than the exact wrapper
that entry records, and releases instead of writing. The doubled restore that
used to follow is gone with it, and so is its worst case: a write landing on a
value nobody recorded, a hot swap or a double installed by hand, which was lost
as finally as a forgotten strand. Every write `uninstall` makes is now a write
onto a slot it has just confirmed still holds its own wrapper.

One duplicate survives, on the other branch. A restore that REFUSED keeps its
entry, so a shift can put it back in front of the walk; the second attempt finds
the wrapper still there, tries again, and refuses again. The cost is the same
strand named twice in one note, which this change neither caused nor removes.
And recording the wrapper makes a WRONG write impossible, not a missed one: a
wrap published above the index this walk fixed when it started is still missed
by this pass, and still taken by the next.

None of this doubles the fire count, and the ownership test that used to be the
whole reason no longer carries it alone. That test now asks about the value
actually in the attribute rather than the one the resolving pass remembered, and
a dispatcher answers as its Patcher's from the statement after the one that
installs it. It is asked twice, and the second asking is what closed the long
gap. An invocation that read an unwrapped original, spent the whole of building
a dispatcher, and came back to find a dispatcher in the slot does not write over
it: finding its own Patcher's it stands down, losing that attribute's rules and
naming none of them in `applied`, since the publish sits below the point it
leaves from; finding a stranger's it refuses and rolls back. Finding the
attribute gone it skips, since writing would put back a name the program
deleted. What it asks is who owns the value that is there, not whether that
value is the object it remembered: an attribute reached through the descriptor
protocol is built fresh on every read, so `inst.m is inst.m` is already False,
and an identity test would call a point replaced when nothing had touched it,
for every instance point whose function lives on the class. That is what keeps
the re-entry building a dispatcher performs from leaving two entries on one
slot, since it imports inspect and runs whatever `__signature__` the callable
carries, and either can reach back into the very attribute being built for. It
says nothing about an actor that is not pyteman: a replacement landing in that
gap is written over, and the uninstall that follows puts the pre-replacement
callable back and reports a clean release.

It narrows the single-threaded case rather than closing it. The second reading
and the write are two statements, and both `getattr` and `setattr` can run
target code: a container that is a `property`, a metaclass with `__setattr__`, a
`ModuleType` subclass with `__getattr__`. Should that code import an
instrumented module, the nested call installs between the two and this one
writes over it, which reaches the window below without a second thread.

One window is left, the span between the second reading and the write: both
invocations can clear that reading holding the same original, and then the
second write wins and the first wrapper is orphaned as described above. A wrap
is lost, and the uninstall that follows reports a clean release over a callable
that is still instrumented. The race itself is tracked rather than fixed here.
Instrument from a single thread until it is closed, which is the ordinary case
anyway, since activation happens during startup and the hook patches on import.

A second window used to sit at the write itself and fail in the opposite
direction. A dispatcher was live in its attribute for one statement before the
in-flight map could answer for it, so a call arriving there read a LIVE
dispatcher, was told it belonged to nobody because neither that map nor the
ledger knew it yet, and wrapped it: one attribute with two of our dispatchers,
every rule underneath firing twice per call, and an uninstall that reported
nothing refused while leaving the inner one installed. A `ModuleType` subclass
whose `__setattr__` re-enters after calling `super()` reaches that statement
from a single thread, so it was never only a threading concern. It is closed by
writing the map before the setattr rather than after it. Not because the
dispatcher becomes unreachable: `setattr` hands it to `__setattr__` as the value
before the write lands, so a container can publish it elsewhere and re-enter
from there. What changes is the answer. A call that reaches it is now told the
dispatcher is ours, takes the branch that extends an existing dispatcher, and
installs nothing; before, it was told the dispatcher belonged to nobody, and
wrapped.

A rule that fails at firing is worse than either, having already let the
experiment produce data under conditions nobody authored, which is why
validation is deliberately strict.

Checked at load: types, ranges, required fields, unknown fields, the grammar
of every `target:` spec, and whether every expression compiles. One semantic
check happens at load too: `target: result` on an `entry` rule is rejected,
because that name is structurally absent from the entry context rather than
merely unresolved.

Checked later, by design:

- Whether the point exists. The target module is usually not imported yet,
  so the attribute path is walked when the import hook patches it.
- Whether the names inside `when` and `fire.key` resolve. They are looked up
  in the evaluation namespace the first time the expression is evaluated. A
  partial load-time check was implemented and then removed, because it could
  not see a name read inside a nested scope or before a walrus assignment,
  and rejecting the plain spelling while accepting those two is a guarantee
  that misleads.
- Whether a `target:` spec resolves in a given call. A miss is recorded in
  the firing log with its reason rather than raising, because an argument
  that is absent on one call may be present on the next.

## Compatibility policy: the schema is closed

An unknown key is an error, never an ignored extra. The failures these
typos cause are silent, which is worse than a rejected ruleset:

| typo | what it would do if ignored |
| --- | --- |
| `ms: 1` with `mss: 250` | the sleep keeps its own `ms`, injecting one millisecond instead of 250 |
| `wehn: "fires > 3"` | the rule loses its condition and fires on every call |
| `fire: {mode: always, n: 3}` | `n` belongs to `countdown`, so the gate is not what was written |

Extending the language means extending `_ACTION_SCHEMA` and `_FIRE_SCHEMA`
in `rules.py`, not relaxing this.

## Rule fields

| field | required | value |
| --- | --- | --- |
| `id` | yes | non-empty string, unique in the ruleset. It keys the firing log, so a duplicate is rejected rather than merged. |
| `point` | yes | `module.symbol`, at least two dot components, each a valid identifier. The module is everything before the FIRST dot; the rest is an attribute path walked from it. |
| `event` | yes | `entry` or `exit`. |
| `action` | yes | mapping, see below. |
| `when` | no | expression string, see below. |
| `fire` | no | mapping, defaults to `{mode: always}`. |

A `when` that is present must be a non-empty string. `when:`, `when: ''` and
`when: false` are each rejected rather than read as "no condition": all three
are typos for a condition, not requests to fire always.

## More than one rule on one point

Every rule the ruleset aims at a point applies, in the order it appears in the
ruleset. There is no priority field; position in the file is the ordering, and
it holds however the rules arrive, which "Rules are grouped by the attribute
they resolve to" below describes.

`entry` rules run before the callable, in ruleset order. The first one whose
action returns a value ends the call there: the callable is not invoked, and
no `exit` rule runs, because an `exit` rule is a statement about a call that
happened. An `entry` action that raises stops the call the same way.

If the callable returns, `exit` rules run in ruleset order. Each sees the
result the previous one left in `result`, and the last action that returns a
value is the one the caller gets.

If the callable raises, the `exit` rules still run, each seeing the original
exception in `exc` and `None` in `result`. A `return_value` or `return_none`
there is discarded, because an `exit` rule cannot swallow the callable's
exception.

On either path, an `exit` action that raises stops the `exit` rules after it,
and its exception is the one that leaves the call. Chaining is ordinary
Python. After a callable that raised, the injected exception carries the
original as its `__context__`; after a callable that returned, there was
nothing in flight and `__context__` is `None`. That is the only way an `exit`
rule ends the sequence early. Returning a value never does.

Rules are grouped by the attribute they resolve to, not by the text of their
`point`. Two rules reaching the same attribute by different paths, through a
module alias for instance, land on the same callable and both apply.

Grouping is not limited to one patch of one module. A rule that reaches an
attribute this same Patcher is already dispatching on, because it arrives on a
later import or names the attribute through another module, joins the
dispatcher already there, and `applied` names it when it does. It fires in
ruleset order like any other: the rules arriving late are merged into position
rather than appended, so which import happened first decides nothing about
which rule runs first. The rules already live keep the state they had reached,
so a `countdown` halfway through its count does not restart because another
rule joined it.

`applied` is the one list that reads in arrival order. It accumulates across
every patch call and no single call sees the whole of it, so it can name a
late-arriving rule after one that fires ahead of it. Read it as what was
installed, never as what runs first.

### What short-circuiting means for `fire`

Each rule counts its own reaches. `countdown` and `once_per` advance only when
that rule is actually reached, so a rule jumped over by an earlier return or
raise does not move. Rules on one point therefore do not stay in step: with an
`entry` rule that fires on its second reach ahead of another, the second rule
is not reached on that call, and its own schedule slips by one. Read `fire` as
counting the times that rule ran, never the times the point was called.

### One Patcher at a time

Composition is within a single ruleset. Two rulesets installed separately, by
two `Patcher` instances, do not compose: the second is refused on any point the
first is still dispatching on, with a `SlotOwnershipError` that names the
attribute it refused and every rule of yours aimed at it, and that call undoes
the points it had already patched. Uninstall the first, then install the
second. Points no other Patcher holds are unaffected, so two rulesets aimed at
disjoint targets coexist.

Before this, the second ruleset was discarded in silence. It reported success
and patched nothing, so a run could claim instrumentation that was never
installed.

### Ids

`id` is unique in the ruleset, and that is the only deduplication. Two rules
with identical contents and different ids are two rules and both fire, which
is how a ruleset asks for an action twice. A repeated id is refused before
anything is patched, whether the ruleset was loaded from a file or built
through the Python API.

The rest of the contract is enforced through both doors as well, and for the
same reason. A rule built in Python is refused if its `id` is not a string, if
it is empty once stripped, or if reading the attribute raises at all. That last
case is the one worth naming, because it looks harmless. Everywhere a rule is
only being NAMED, an unreadable id degrades to `<unreadable id>` and the
location survives, so it reads like a reporting problem you can live with. From
the moment a firing log is configured, at run time it is not one. Every record a
rule writes reads `id` directly, inside the instrumented call, where no
degradation applies: the `phase: start` record written before the action and
the terminal `phase: end` record written after it. Both of those reads are
guarded by the presence of a log, so a run configured without one never reads
the id at run time at all.
The refusal does not ask, and not because the guards are in doubt: one ruleset
being legal under one logging choice and illegal under another would make the id
mean less than the name you gave it. Under a log, a rule that will not name
itself does not lose a label there, it raises out of your own code on the first
firing, with the slot already replaced and no firing record written to tell you
why. The refusal happens while the `Patcher` is being built,
which is the one step that changes nothing, so it costs you an unpatched process
rather than a half-patched one. What the placeholder is still for is the
refusal message itself, which has to name a rule whose name will not read.

One limit is worth stating plainly, because it is a property of preflight and
not something the check could be written to cover. A check that runs while the
`Patcher` is built speaks for the moment it runs. `Rule` is a plain dataclass,
so you still hold the object the plan holds, and the firing record reads `id`
again each time the rule fires. Rebinding `id` after the `Patcher` exists, or
giving it a property that answers once and then stops, puts back exactly the
hazard the refusal removed, and no preflight can see it coming. Treat a rule as
frozen once it has been handed to a `Patcher`.

## Points whose work does not happen during the call

A rule times entry before the call and exit after it returns. That is the whole
model, and it does not fit a callable that returns something for you to drive
later. Calling a coroutine function builds a coroutine and runs none of the
body; calling a generator function builds a generator and runs none of the
body; an async generator function is the same. Both records would describe the
construction of the object rather than the work, and an `entry` action
supplying a return value would hand your caller an ordinary object where an
awaitable or an iterator was expected.

The mistimed record is not the whole of it. An `exit` action with a
`return_value` discards the suspended object the call produced, so the body
never runs at all and your caller gets the value you configured instead. That is
true of all three kinds equally. What differs is whether you find out: a
discarded coroutine leaves a `RuntimeWarning` about a coroutine that was never
awaited, delivered whenever the collector reaches the orphan, while a discarded
generator or async generator is collected in silence.

So such a point is refused rather than instrumented. You get a
`SuspendableTargetError` naming the kind, the attribute and the rule:

```
pyteman: mypkg.tasks:fetch is a coroutine function, so entry and exit cannot be
timed on it; refused rather than installed for rule 'trace-fetch' at
mypkg.tasks:fetch
```

The refusal is raised before the slot is written, so it travels out through the
same rollback every other patch failure uses, and the call that raised undoes
the points it had already patched. How far that reaches depends on when the
target module is imported. A module already in `sys.modules` when `site.py`
runs is patched during startup, and the process refuses with exit 2 and never
runs the workload, so you get the whole ruleset or none of it. A module
imported later is patched by the import hook, so the refusal comes out of your
own `import` statement with the rest of the ruleset already live, and
`SuspendableTargetError` is a `RuntimeError`, which means an `except Exception`
around that import will swallow it.

Refused, and deliberately not skipped, which is the opposite of the choice made
for an attribute that is not there. A point that is missing cannot be
instrumented by anyone and your ruleset still means what it says without it. A
suspendable point CAN be reached, so skipping it would report success on a rule
that then silently never fires, and a rule you believe is firing is worse than
a run that refused to start.

### What is recognised

The kind is read off the callable, never by calling it. Three things are read:
the coroutine, generator and async generator predicates; `functools.partial`
through its `func`; and, for a callable instance, the type's `__call__`, read
and not invoked. Every one of those says what calling the object does.

While the walk is standing on a `partial` it never asks the predicates. They
unwrap `func` before reading a code flag, and the helper they use for it walks
the whole nest in one step, so every layer in between is skipped, overrides
included. That is right for a single exact `functools.partial`, whose
`__call__` really does invoke `func`, and wrong for a subclass whose own body
may never touch it.

So each turn round the loop handles one layer and one only: the effective
`__call__` override when the subclass defines one, otherwise one step along the
stored `func`, and then round again. Both directions of the override case were
measured. An `async def __call__` over a synchronous `func` returns a coroutine
while the predicates see a plain function, which would instrument a suspendable
point. A synchronous `__call__` over a stored coroutine function returns a
value while the predicates report a coroutine function, which would refuse
something that never suspends.

One layer per turn matters because whether a nest survives construction is a
property of the interpreter rather than of your code. `partial(partial(f))`
flattens into one on every version this package supports, and so does a nest of
a subclass that overrides nothing. A subclass that carries instance state stays
a nest on every version. The one construction that moves is a subclass that
overrides `__call__`: it stays a nest on 3.11 and 3.12 and flattens on 3.13 and
3.14. Take `Plain(SyncOverride(coro))`, where `Plain` overrides nothing and
`SyncOverride` has a synchronous `__call__`. On 3.11 and 3.12 both layers
survive, calling it reaches the synchronous override and returns a value, and
refusing it would be a false positive. On 3.13 and 3.14 the construction
discards `SyncOverride` and keeps `coro`, calling it really does return a
coroutine, and refusing it is correct. Walking the layout rather than asking
the predicates lets each version's real storage decide, so the check answers
correctly on all four without ever branching on a version number. Measured on
3.11.14, 3.12.12, 3.13.15 and 3.14.7.

In that slot a `staticmethod` and a `classmethod` are both read through
`__func__`, and a `functools.partial` re-enters the walk, because those are the
spellings found holding a callable of their own. A `classmethod` is read the
same way as a `staticmethod` because it behaves the same way here. Neither is
handed the instance when CPython invokes the slot, the kind is on `__func__`
either way, and `__func__` is read rather than invoked, so nothing is bound and
no descriptor runs. Nothing else is followed. An ordinary function's `__call__`
is a slot wrapper describing itself rather than the function it belongs to, a
native `__call__` says nothing at all, and the `__call__` that `functools.partial`
supplies to its own instances is not an override and is not read as one.

Exactly one read is taken in that slot, and when it uncovers another descriptor
that one is handed back as the slot rather than dropped, so the layer after it
is taken on the descriptor edge and spends the same budget every other link
spends. Dropping it answered "not a callable instance" for an object whose call
really does reach the coroutine underneath.

`__wrapped__` is deliberately not read, though it is the obvious fourth. It
records where a wrapper came from, which is what `inspect.signature` wants and
is a different question from this one. A function decorated with
`@contextlib.contextmanager` is synchronous and wraps a generator function; a
synchronous adapter written with `functools.wraps` around an `async def` is an
ordinary function. Following provenance would refuse both, and both are correct
to instrument. CPython's own `inspect.iscoroutinefunction` does not follow it
either.

The `partial` step is required on every partial, and the case where the
predicates could not have substituted for it at all is the composite they do
not reduce, a partial of an instance whose type's `__call__` is `async def`,
where unwrapping lands on the instance and the predicates stop there. Off the
partial arc they are asked directly, on a terminal that carries its own kind,
and only then is the type's `__call__` read.

Introspection that raises is a refusal, with the exception chained onto it, and
so is a chain that somehow runs past 64 links. Not knowing is a refusal here,
because an object that went to trouble to hide what it is, is exactly the one
worth not wrapping.

What this does not promise is a verdict on every callable, and the gap is wider
than the undecidable case. An ordinary `def` that happens to return a coroutine
carries nothing saying so. Neither does a synchronous wrapper that really does
hand back the awaitable it got from an `async def`: it is an ordinary function,
and its only evidence is the provenance link this check does not read. Both are
outside the guarantee, by the same decision, and both stay instrumentable.

A `partial` subclass whose `__call__` is synchronous and delegates, returning
`self.func(*args)` over a stored `async def`, is that same shape one layer out.
The walk reaches the override, reads a plain function and instruments it.
Nothing static separates it from an override that does its own synchronous
work, or from the adapter above, so refusing it would mean refusing every
adapter written on purpose. It is outside the guarantee too, and named here
rather than left to be discovered.

A `__call__` that is not a Python function, a `staticmethod`, a `classmethod`
or a `partial`, a native one for instance, is outside the guarantee for the
same reason and stays instrumentable. The promise is therefore the list read
exactly as written: a shape in it is refused and never quietly instrumented.

A `staticmethod` or a `classmethod` is followed wherever the walk meets it, not
only as the content of a `__call__` slot. It costs one hop like any other link,
so a descriptor chained inside another one and a descriptor reached as the
terminal of the partial arc are both carried to the callable underneath:
`staticmethod(staticmethod(coro))` and `partial(staticmethod(coro))` are refused
as coroutine functions, and the same spellings over a synchronous function stay
instrumentable.

The hop takes the same order the partial arc takes: the type's `__call__`
decides, and `__func__` is the fallback when there is no override. A subclass
that overrides `__call__` really is what its override says, whatever it stores,
so an `async def __call__` over a stored synchronous function is refused and a
synchronous `__call__` over a stored `async def` stays instrumentable. Reading
`__func__` first would get both backwards.

That order holds wherever the descriptor is a value the walk is handed, and it
inverts in the one position where the descriptor is not called at all. A
descriptor sitting in a type's `__call__` is resolved by CPython through
`__get__` before the call happens, so its own override never runs and what the
caller reaches is what it stores. There the storage is read first, which is why
the first layer of a nest is taken inside the `__call__` read rather than on the
descriptor edge. Both directions were measured on a subclass storing the
opposite kind to the one its override returns: in that slot a synchronous
override over a stored `async def` is refused, and the same subclass reached
along the partial arc is instrumented. One plain `staticmethod` wrapped around
it in the slot puts it back on the first terms, because then it is the outer
descriptor CPython resolves and the subclass is reached as a value like any
other. The inversion belongs to the position, not to the subclass.

A single descriptor read off a class never reaches this check as a descriptor:
`getattr` runs `__get__` and hands it the callable underneath already. The
top-level spelling that does reach it is a module-level attribute, because a
module runs no descriptor protocol, so `handler = staticmethod(coro)` at module
scope arrives as the descriptor itself. A descriptor nested inside another one,
or one reached along the partial arc, arrives from any container. Without the
hop the predicates answer about the descriptor rather than about what it holds,
report an ordinary callable, and a coroutine function is wrapped with entry
semantics that return a value where every caller awaits.

`__func__` is read off `staticmethod` and `classmethod` themselves rather than
off the object in hand, so a subclass that defines `__func__` as a property
cannot choose what the walk follows, and reading it runs no code of the
target's. That matters twice over: such a property could report a plain
function while the object really holds an `async def`, and merely consulting it
would execute target code inside a check that is supposed to read and never
run.

Instrumenting these points properly is a separate feature. It needs the
dispatcher to await or to iterate on your behalf while preserving cancellation
and `throw()`, and this refusal is not a partial version of that.

## Conditions

`when` and `fire.key` are Python expressions evaluated with a namespace that
holds `args`, `kwargs` and `fires` on every call, plus `result` and `exc` on
exit events only. `fires` is the number of times *this rule* has been reached,
counted before the condition is evaluated. It is a per-rule count, not a count
of calls to the point: a rule the call never reached, because an earlier rule
on the same point returned or raised, does not advance.

Builtins are emptied. Only these ten names are available: `len`, `str`,
`int`, `float`, `bool`, `abs`, `min`, `max`, `sorted`, `isinstance`.

Four consequences worth stating plainly, because none of them is caught at
load:

- An `entry` rule that names `result` or `exc` raises `NameError` from inside
  the instrumented call, but only where the expression actually reaches that
  name as a context lookup. The lookup happens while the expression runs, so
  a branch that short-circuits away never raises: `False and result` and
  `result if False else 1` both load and then evaluate cleanly. A `result`
  the expression binds for itself is a different name altogether and resolves
  to that binding, which is what a comprehension target does on Python 3.12
  and later. Where the name IS reached, the failure lands on the first call
  whose condition is evaluated, and that is not the same as the first call
  that fires: under `always` and `once_per` it is the first call that reaches
  the rule, because neither mode returns before the condition is evaluated on
  that call. Under `countdown n` it survives until the rule's `n + 1`th reach,
  where the gate stops returning early. `once_per` evaluates its key before
  the condition, so a key naming those names dies first, and on a later call
  whose key has been seen already the gate returns before the condition is
  reached at all.
- A condition calling any builtin outside the ten above raises `NameError` by
  the same route and under the same rule, so `any(...)` and `sum(...)` do not
  work in a branch that is evaluated.
- Any other exception a condition raises leaves by the same door, out of the
  instrumented call rather than as a rule error. `kwargs['sid']` on a call
  that passed no such keyword raises `KeyError`, `.startswith` on a non-string
  raises `AttributeError`, and a `fire.key` evaluating to a value `once_per`
  does not accept raises `OncePerKeyError` before the key is stored, as
  described under [What `once_per` accepts as a
  key](#what-once_per-accepts-as-a-key).
- A CONTEXT name read as a free variable inside a lambda body, inside the
  body of a generator expression, or inside a list, set or dict comprehension
  is found on every Python version this project supports, the same as it
  would be read flat. `max(x < kwargs['limit'] for x in args)` and
  `(lambda: fires >= 3)()` see `kwargs`, `args` and `fires` exactly as
  `kwargs['limit']` and `fires >= 3` would on their own; a lambda parameter,
  a comprehension target and the ten builtins keep resolving as they always
  did. Nested scopes see context through a namespace built from it at the
  start of evaluating the condition, not through the context object itself,
  so a read is exact while a write stays inside the condition: see the next
  point.
- A condition CANNOT write into the context. It is evaluated against a
  namespace built from the context rather than against the context object,
  and that namespace belongs to that one evaluation, so an assignment
  expression binds a name for the rest of that one condition and
  nothing else. `(exc := None) is None` is still a legal condition and still
  true, but the rules evaluated after it on the same call read the `exc` the
  body raised, and the rule that wrote it reads that one too. The same holds
  wherever the assignment sits: at the top level, inside a lambda body, or
  inside a generator expression or comprehension, where PEP 572 targets the
  binding at the nearest enclosing scope that is not itself a comprehension.
  What a condition CAN still do is mutate an object the context holds,
  because the namespace carries the same `args` and `kwargs` objects rather
  than copies; appending to a list the call was passed reaches the call.
  Rebinding a name does not. Conditions are questions about a call, and a
  condition that needs to change one wants an action instead.
- A name bound at the top of a condition reads back the same everywhere in
  that condition, including inside a lambda, a generator expression or a
  comprehension. This is worth stating because it is the part a split
  namespace would get wrong, and wrong differently per interpreter: PEP 709
  inlines list, set and dict comprehensions into the enclosing scope from
  Python 3.12, so a comprehension would have seen such a binding while a
  generator expression beside it raised `NameError`.
- What the namespace guarantees is scoping, and scoping alone: neither
  lifetime nor isolation. It is built once per evaluation, so no evaluation
  implicitly sees another's bindings. It is not destroyed on a
  schedule either: a generator or a lambda a condition RETURNED would hold
  the namespace it was built against for as long as that value stayed alive.
  `when` does not retain the value it returns, and a `fire.key` is checked
  against the types [`once_per` accepts](#what-once_per-accepts-as-a-key)
  before it is stored, so a key evaluating to a generator or a function is
  refused. Neither of those closes the question: a condition can stash a
  closure into an object reachable from the context, and a later condition
  can call it, on another call and from another thread. What a condition CAN
  still reach past its own evaluation is the objects the context holds,
  described in the previous point.

Conditions are trusted operator input and are not sandboxed. The namespace
is convenience scoping, not a security boundary.

```yaml
- id: late-writes-only
  point: hermes_state.SessionDB._execute_write
  event: entry
  when: "fires > 3 and kwargs.get('sid', '').startswith('stress-')"
  action: {kind: sleep, ms: 250}
- id: stall-after-a-failed-commit
  point: hermes_state.SessionDB.commit
  event: exit
  when: "exc is not None"
  action: {kind: sleep, ms: 100}
```

## Actions

`action.kind` selects the shape. Unknown fields for the chosen kind are
rejected, and `target:` is accepted only by `pragma`.

| kind | fields | values |
| --- | --- | --- |
| `sleep` | `ms` required | integer, `0` to `9223372036000`, which is `threading.TIMEOUT_MAX` in milliseconds. The bound is on the conversion, not on the wait: `time.sleep` counts against an absolute deadline, so the longest delay it will really sleep is its int64-nanosecond ceiling minus whatever the monotonic clock currently reads, and the bound itself already fails with `OSError` on a machine that has been up for any time at all. Every value near it means centuries, so what this check actually catches is the ordinary typo. `true` is rejected, since Python would otherwise read it as one millisecond. |
| `raise` | `exc`, `message`, both optional | `exc` is a builtin exception class, defaulting to `RuntimeError`. The action calls `exc(message)`, so the five classes that reject a single message argument are refused at load: `BaseExceptionGroup`, `ExceptionGroup`, `UnicodeDecodeError`, `UnicodeEncodeError`, `UnicodeTranslateError`. |
| `return_value` | `value` optional | any YAML scalar or structure, `null` included. |
| `return_none` | none | |
| `kill` | `exit_code` optional | integer `0` to `255`, defaulting to `70`. Calls `os._exit` at the injection point. |
| `pragma` | `name`, `value` required; `target` optional | `name` is a non-empty string. `value` is a string or an integer, and a bare `ON`/`OFF`/`YES`/`NO` is rejected: YAML 1.1 reads those as booleans, so `journal_mode: OFF` would reach SQLite as `False`, a statement it accepts while leaving the mode untouched. Quote them. Quoting fixes the ambiguity and not the outcome: the value is still interpolated verbatim and each pragma reads it its own way, so on `journal_mode` a quoted `"ON"` or an integer is accepted here, executed, and ignored there. That case is reported rather than prevented: the value reaches SQLite as written, and the readback then records it as `pragma_unknown`. Verification covers the pragmas in the perimeter listed in the README, each against its documented grammar; anything else executes and is reported unknown. The perimeter is `pragmas._PERIMETER`, and the outcome text names it from there, so a verdict never disagrees with the code about what is verified. |
| `barrier` | `barrier` required; `role`, `timeout_s` optional | `role` is `wait` (the default) or `open`. `timeout_s` is a positive finite number up to `9223372036.0`, again `threading.TIMEOUT_MAX`, and defaults to 30. |

Both numeric ceilings above are `threading.TIMEOUT_MAX`, which CPython
documents as platform dependent. The loader derives them instead of spelling
them out, and a test asserts that the figures printed here are the ones the
running interpreter produces, so a platform where they differ fails the suite
rather than shipping a reference that lies.

`return_value` and `return_none` follow Byteman RETURN semantics and depend
on the event: on `entry` the wrapped body is skipped and the override is
returned in its place, on `exit` the body has already run and the override
replaces the result it produced.

On `exit` that second half holds only when the body RETURNED. If the body
raised, the exception propagates and the override is discarded. The firing is
still recorded, and the record is not wrong to be there: it is written before
the action runs, so it attests the attempt rather than the outcome. What no
record carries today is whether the override actually reached the caller.

Whether an override SHOULD suppress a pending exception is an open contract
decision rather than settled semantics, so nothing here promises it either
way. Until it is decided, pair `when: "exc is not None"` with an action that
means something under an exception, such as `sleep`, `kill` or `barrier`,
rather than with a return override.

`target:` reaches state the callable holds rather than receives, such as a
connection stored as `self._conn`. Omit it and the `pragma` action scans the
call's positional arguments and keyword values instead, taking the first
`sqlite3.Connection` it finds and noting `no target spec and no
sqlite3.Connection in the call arguments` when there is none. The spec
grammar lives in [targeting.md](targeting.md) and is checked at load, so an
unknown root, a bare `param:` or an empty walk step such as `self..a` is
rejected there. What cannot be settled until a call arrives is whether the
spec resolves against that call's arguments.

```yaml
- id: wal-off-mid-run
  point: hermes_state.SessionDB._execute_write
  event: entry
  action: {kind: pragma, name: journal_mode, value: 'DELETE', target: self._conn}
- id: crash-after-commit
  point: hermes_state.SessionDB.commit
  event: exit
  action: {kind: kill, exit_code: 70}
```

## Fire gating

`fire:` chooses how often a rule that matches actually fires. Both
`countdown` and `once_per` require their field explicitly, with no default,
because a typo in the field name would otherwise retime the experiment in
silence.

| mode | field | semantics |
| --- | --- | --- |
| `always` | none | fires on every reach where `when` passes. The default. |
| `countdown` | `n` required | fires once, on the rule's `n + 1`th reach. `n: 0` fires the first time the rule is reached. |
| `once_per` | `key` required | fires once per distinct value of the key expression, which must evaluate to one of the types listed under [What `once_per` accepts as a key](#what-once_per-accepts-as-a-key). `key: "sorted(args)"` loads and then raises `OncePerKeyError` out of the instrumented call. |

The two modes count differently, and the asymmetry is deliberate:

- `countdown` counts REACHES of the rule, not calls that satisfy `when`. A
  rule whose condition happens to be false on its `n + 1`th reach never fires.
- `once_per` consumes a key only when the condition passes, so a key seen
  under a false condition remains available for a later call.

Both counts belong to the rule, not to the point. A rule is reached whenever
the call arrives at it, which on a point carrying one rule is every call, and
on a point carrying several is every call an earlier rule did not end first.
See [More than one rule on one point](#more-than-one-rule-on-one-point).

```yaml
- id: one-stall-per-session
  point: hermes_state.SessionDB._execute_write
  event: entry
  when: "kwargs.get('sid', '').startswith('stress-')"
  action: {kind: sleep, ms: 250}
  fire: {mode: once_per, key: "kwargs.get('sid')"}
- id: crash-on-the-51st-commit
  point: hermes_state.SessionDB.commit
  event: exit
  action: {kind: kill, exit_code: 70}
  fire: {mode: countdown, n: 50}
```

### What `once_per` accepts as a key

A key must evaluate to `None`, a `bool`, an `int`, a `float`, a `str`, `bytes`,
or a tuple built recursively out of those. Anything else is refused, and the
refusal comes out of the instrumented call as `OncePerKeyError` naming the rule
and the type it got. Subclasses are refused too, so a `str` subclass is not a
`str` for this purpose. A tuple also has to stay within two limits of size: it
may not be nested more than sixty-four levels deep, and walking it may not
visit more than ten thousand elements.

The restriction exists because `once_per` has to decide atomically whether a key
has been seen before, and deciding means hashing the key and comparing it. For
an arbitrary object those two operations are code the operator wrote, running
while the rule's decision is held open. An object that blocks there, or that
re-enters the instrumented call, stalls every other thread reaching the same
rule. The accepted types hash and compare in C, so they cannot re-enter.

The depth limit is what it is, and not a rounder or larger number, because
hashing and comparing a tuple fail differently and at very different depths.
`tuple.__hash__` recurses through the C stack with no guard and only crashes
the interpreter outright somewhere past a hundred thousand levels; that failure
mode has nothing to do with the limit here. `tuple.__eq__` recurses through
CPython's own recursion accounting instead, the same shared budget
`sys.setrecursionlimit` governs, and on CPython 3.11 that budget turned out to
have essentially no margin left at a nesting depth in the high nine hundreds
once any ordinary caller stack, a lock or a test runner among them, was already
on it. Sixty-four levels leaves comfortable headroom under both failure modes,
under the interpreter's default recursion limit and default thread stack size.
Nothing here is claimed, or should be assumed, for a process running under a
custom recursion limit or a custom thread stack size.

The element limit exists for a separate reason: being C code says nothing about
how long that code runs. A tuple's hash is not cached, so hashing one walks
every element underneath it, and a tuple that shares its subtuples instead of
owning distinct ones is shallow and cheap to build while being astronomically
expensive to walk. Forty levels of `t = (t, t)` is well within the depth limit
and has more nodes than there are seconds in the age of the universe. The
element budget is what turns that from a stalled interpreter into a refused
key. A tuple's width is charged against that budget before its elements are
examined, so a single very wide tuple is refused without being copied rather
than after.

Keys are never converted to make them fit. Two keys Python considers equal are
still one key, so `key: "kwargs.get('sid')"` behaves exactly as the string
comparison suggests, and a key outside the contract is reported rather than
quietly folded into a neighbouring one.

Under concurrent calls, a rule fires once per key no matter how many threads
arrive together, including threads whose `when` expressions overlap in time. A
false condition still leaves the key available for a later call, and a key
refused by the contract still costs the visit the rule was counting.

## Error messages

Every rejection names the rule by list index and, once it has been read, by
id: `rule #1 (id 'crash-at-commit'): action.ms must be at most ...`. The id
is read before any other field precisely so it can label the messages about
the fields that follow, including the missing ones.
