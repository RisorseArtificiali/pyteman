# tests/test_sitecustomize.py
import importlib.util
import os
import pathlib
import subprocess
import sys

import pytest

HERE = pathlib.Path(__file__).parent
SRC = HERE.parent / "src" / "pyteman"  # dir on PYTHONPATH makes sitecustomize top-level importable

TARGET = "def plain(a, b=0):\n    return a + b\n"
RULES = """
- id: ov
  point: target_mod.plain
  event: entry
  action: {kind: return_value, value: 42}
"""

# Two rules, the bad expression in a different position in each. The pair is the
# point: if only the first were covered, a loader that validated lazily would
# still pass, and the second rule is the one that would have let the workload
# start.
RULES_BAD_FIRST = """
- id: r1
  point: target_mod.plain
  event: entry
  when: "("
  action: {kind: return_value, value: 1}
- id: r2
  point: target_mod.plain
  event: entry
  action: {kind: return_value, value: 2}
"""
RULES_BAD_SECOND = """
- id: r1
  point: target_mod.plain
  event: entry
  action: {kind: return_value, value: 1}
- id: r2
  point: target_mod.plain
  event: entry
  when: "("
  action: {kind: return_value, value: 2}
"""

WORKLOAD = "import target_mod; print('WORKLOAD_RAN', target_mod.plain(1))"

# Valid in every way a loader can check, and unpatchable. `int` is a C type,
# so reassigning one of its attributes raises TypeError, and `builtins` is
# always imported, so activation reaches it during startup instead of leaving
# it to the import hook.
RULES_UNPATCHABLE = """
- id: frozen
  point: builtins.int.bit_length
  event: entry
  action: {kind: return_value, value: 1}
"""

@pytest.fixture
def sandbox(tmp_path):
    """A scratch dir holding the module the rules point at.

    Every case needs it on the path, including the refusals, where the point is
    precisely that the import never happens.
    """
    (tmp_path / "target_mod.py").write_text(TARGET)
    return tmp_path

def rules_file(tmp, body=RULES):
    f = tmp / "r.yaml"
    f.write_text(body)
    return f

def run_py(tmp, env_extra, code):
    # env_extra is merged last, so a caller needing a different import path
    # overrides PYTHONPATH here rather than through a parameter of its own.
    env = {**os.environ, "PYTHONPATH": f"{tmp}:{SRC}", **env_extra}
    try:
        return subprocess.run([sys.executable, "-c", code],
                              capture_output=True, text=True, env=env,
                              cwd=str(tmp), timeout=60)
    except subprocess.TimeoutExpired as exc:
        # Every case in this module funnels through here, and TimeoutExpired
        # names only the command, which is the whole workload inlined after
        # -c and identical across most of them. The activation being tested is
        # what differs, so the note carries that instead. The exception the
        # caller sees is unchanged.
        exc.add_note(f"pyteman: activation {sorted(env_extra)} under {tmp} "
                     f"did not finish in {exc.timeout}s")
        raise

def refused(tmp, env_extra):
    """Run the workload under an activation that must fail.

    A real subprocess and not an in-process call: the behaviour under test is
    what site.execsitecustomize does with the failure, and that frame only
    exists during interpreter startup.
    """
    return run_py(tmp, env_extra, WORKLOAD)

def assert_refused(r, phase, *needles):
    # Exit 2 AND silent stdout, always together: either alone is passable for
    # the wrong reason. A non-zero exit with WORKLOAD_RAN present would mean the
    # experiment ran uninstrumented and merely reported badly afterwards, which
    # is the fail-open shape this task exists to close.
    assert r.returncode == 2, f"expected exit 2, got {r.returncode}\n{r.stderr}"
    assert "WORKLOAD_RAN" not in r.stdout, f"workload ran anyway: {r.stdout!r}"
    assert r.stderr.startswith(f"pyteman: refusing to start: {phase}:"), r.stderr
    for needle in needles:
        assert needle in r.stderr, f"{needle!r} missing from: {r.stderr}"

def test_inert_without_env(sandbox):
    r = run_py(sandbox, {},
               "import target_mod, sys; print(target_mod.plain(1)); "
               "print('hooked' if getattr(sys, '_pyteman', None) else 'clean')")
    assert r.stdout.splitlines() == ["1", "clean"]
    # Inert means silent too: no env, no effects, and nothing on stderr either.
    assert r.returncode == 0 and r.stderr == ""

def test_inert_run_does_not_import_pyteman(sandbox):
    # Inert also means absent from sys.modules. The shim is on the PYTHONPATH of
    # every process in the venv, so anything it imports unconditionally is paid
    # for, and observed, by programs that never asked for instrumentation.
    r = run_py(sandbox, {},
               "import sys; print(sorted(m for m in sys.modules "
               "if m == 'typing' or m.startswith('pyteman')))")
    assert r.stdout.strip() == "[]", r.stdout


def test_inert_run_adds_nothing_to_sys_modules_but_the_shim(sandbox):
    """The README's claim, measured against a run without the shim at all.

    The test above names the two importers worth worrying about today and would
    stay green if the shim grew an unconditional `import json` tomorrow, which
    is weaker than "nothing new reaches sys.modules beyond the shim itself".
    Naming the forbidden imports can only ever pin the ones already thought of.

    Differencing against a shim-free interpreter inverts that: the baseline is
    whatever this interpreter loads on its own, so ANY module the shim adds
    shows up without having been predicted. The one permitted difference is
    `sitecustomize`, which is the shim itself.

    That difference is permitted rather than required, because some
    interpreters ship a `sitecustomize` of their own in the stdlib. Homebrew's
    3.14 is one, and on it the baseline already holds the name, so requiring
    the difference would fail on an interpreter property rather than on
    anything this package does. The second assertion is what stops the subset
    from going slack: it names the file that actually ran, so a run where the
    shim never loaded at all cannot pass by adding nothing.
    """
    code = "import sys; print(' '.join(sorted(sys.modules)))"
    # env_extra is merged last, so this overrides run_py's PYTHONPATH and drops
    # SRC: same interpreter, same code, same cwd, no shim on the path.
    without = run_py(sandbox, {"PYTHONPATH": str(sandbox)}, code)
    with_shim = run_py(sandbox, {}, code)
    assert without.returncode == 0 and with_shim.returncode == 0, \
        (without.stderr, with_shim.stderr)
    added = set(with_shim.stdout.split()) - set(without.stdout.split())
    assert added <= {"sitecustomize"}, added
    loaded = run_py(sandbox, {},
                    "import sys; print(sys.modules['sitecustomize'].__file__)")
    assert loaded.returncode == 0, loaded.stderr
    assert loaded.stdout.strip() == str(SRC / "sitecustomize.py"), loaded.stdout

def test_active_with_rules(sandbox):
    rules_file(sandbox)
    r = run_py(sandbox, {"PYTEMAN_RULES": str(sandbox / "r.yaml")},
               "import target_mod; print(target_mod.plain(1)); "
               "print(open('pyteman.log').read().count(chr(10)))")
    assert r.stdout.splitlines()[0] == "42"
    assert int(r.stdout.splitlines()[1]) >= 1
    assert r.returncode == 0


def test_marker_refusal(sandbox):
    r = refused(sandbox, {"PYTEMAN_RULES": str(sandbox / "r.yaml"),
                          "PYTEMAN_REQUIRE_MARKER": str(sandbox / "nope" / "MARK.ok")})
    # No rules file is written: the marker is checked before the ruleset is
    # read, and the phase in the message is what proves it.
    assert_refused(r, "marker check", "marker file missing")


# --- requested activation fails closed (RT-01 criterion #1) ----------------
#
# Each case names a distinct phase, because "pyteman refused" is not actionable
# on its own: the operator has to know whether to fix the ruleset, the path, or
# the log destination.

def test_missing_rules_file_refuses(sandbox):
    missing = sandbox / "absent.yaml"
    r = refused(sandbox, {"PYTEMAN_RULES": str(missing)})
    assert_refused(r, "loading rules", str(missing), "FileNotFoundError")


def test_malformed_yaml_refuses(sandbox):
    bad = rules_file(sandbox, "- id: x\n  point: [unclosed\n")
    # The yaml exception class is not pinned: PyYAML picks between scanner and
    # parser errors by where the document breaks, and the contract here is the
    # phase plus the offending path, not the library's taxonomy.
    r = refused(sandbox, {"PYTEMAN_RULES": str(bad)})
    assert_refused(r, "loading rules", str(bad))


def test_unopenable_log_refuses(sandbox):
    # A ruleset that loads cleanly, so the only thing left to fail is the log:
    # the phase in the message is what distinguishes the two.
    r = refused(sandbox, {"PYTEMAN_RULES": str(rules_file(sandbox)),
                          "PYTEMAN_LOG": str(sandbox / "no_such_dir" / "f.log")})
    assert_refused(r, "opening the firing log", "FileNotFoundError")


def test_invalid_expression_in_first_rule_refuses(sandbox):
    r = refused(sandbox, {"PYTEMAN_RULES": str(rules_file(sandbox, RULES_BAD_FIRST))})
    assert_refused(r, "loading rules", "rule #0", "'r1'", "when")


def test_invalid_expression_in_second_rule_refuses(sandbox):
    # The first rule is valid and would have been usable: the run is refused
    # anyway, and the message counts to the rule that is actually broken.
    r = refused(sandbox, {"PYTEMAN_RULES": str(rules_file(sandbox, RULES_BAD_SECOND))})
    assert_refused(r, "loading rules", "rule #1", "'r2'", "when")
    assert "rule #0" not in r.stderr


def test_unpatchable_point_refuses(sandbox):
    """The last phase, and the only one no static check could have reached.

    Nothing about the text of this rule is wrong: it loads, it compiles, and
    the point exists. It fails at `setattr`, which is exactly where every
    earlier phase has already succeeded, so this is the case that proves the
    refusal covers the patch loop and not merely the steps leading up to it.

    The rule id in the message is the second half of the assertion. A refused
    setattr arrives as a TypeError naming an attribute, and an operator holding
    forty rules cannot act on that alone; the patcher attaches the rule as a
    note, and this is the path that proves the note survives to stderr, given
    that os._exit means no traceback is ever printed.
    """
    r = refused(sandbox, {"PYTEMAN_RULES": str(rules_file(sandbox, RULES_UNPATCHABLE))})
    assert_refused(r, "installing instrumentation", "TypeError",
                   "'frozen'", "builtins:int.bit_length")


# --- the diagnostic cannot be allowed to break the refusal ------------------
#
# _describe renders user code: __str__, the __notes__ getter, the container it
# returns, that container's own __class__, and each note inside it. _refuse
# takes the exception and renders it inside the try/finally that makes the exit
# unconditional, so the tests below are about what the MESSAGE degrades to; the
# exit itself no longer depends on any of them.
#
# test_refusal_holds_when_describing_the_error_raises, at the bottom of this
# file, is what proves that separation, and its docstring carries the history
# of why the arrangement matters. It injects the failure rather than feeding in
# a hostile value, precisely so that hardening _describe further can never
# quietly empty it out.


@pytest.fixture
def shim(monkeypatch):
    """sitecustomize loaded as an ordinary module, with activation NOT requested.

    _main() runs at import time, so clearing the environment first is what makes
    importing it inside the test process safe: with PYTEMAN_RULES set, any
    failure would take pytest itself out through os._exit(2).
    """
    monkeypatch.delenv("PYTEMAN_RULES", raising=False)
    spec = importlib.util.spec_from_file_location(
        "pyteman_shim_under_test", SRC / "sitecustomize.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_describe_renders_an_ordinary_exception_with_its_notes(shim):
    # The baseline the three hostile cases below must not be allowed to buy:
    # degrading gracefully is worthless if the ordinary rendering is lost.
    exc = TypeError("cannot set 'bit_length'")
    exc.add_note("pyteman: while patching rule 'frozen'")
    out = shim._describe(exc)
    assert "TypeError: cannot set 'bit_length'" in out
    assert "pyteman: while patching rule 'frozen'" in out


def test_describe_survives_an_exception_that_cannot_be_stringified(shim):
    class Unrenderable(Exception):
        def __str__(self):
            raise RuntimeError("stringification failed")

    out = shim._describe(Unrenderable())
    # Degraded, never silent: the class name is what is left to act on.
    assert "Unrenderable" in out and "unprintable" in out


def test_describe_survives_a_hostile_notes_getter(shim):
    class BadNotes(Exception):
        # Shadowing __notes__ with a non-list is exactly the shape under test,
        # so the type checker's objection to it is the assertion, not a problem.
        @property
        def __notes__(self):  # type: ignore[override]
            raise RuntimeError("no notes for you")

    out = shim._describe(BadNotes())
    assert "BadNotes" in out
    # The notes are where the rule id lives, so their loss is announced rather
    # than passed off as an exception that simply had none.
    assert "<notes unavailable>" in out


def test_describe_survives_a_note_that_cannot_be_stringified(shim):
    class BadNote:
        def __str__(self):
            raise RuntimeError("note refuses to render")

    exc = ValueError("real message")
    exc.__notes__ = [BadNote()]  # type: ignore[attr-defined]
    out = shim._describe(exc)
    assert "ValueError: real message" in out
    # The note DEGRADED rather than vanished. Without this the test would still
    # pass if the notes were dropped silently, which this module treats as the
    # worse outcome: the rule id lives in a note, and an operator who sees none
    # concludes the failure had nothing to do with their ruleset.
    assert "<unprintable BadNote>" in out


def test_describe_survives_a_notes_container_that_will_not_iterate(shim):
    """A container that is not an exact list loses its notes and says so.

    A hostile __notes__ GETTER is caught by the try around the attribute access.
    A list SUBCLASS gets past that, and is turned away by the type check behind
    it, which is deliberately `type(x) is list` and so rejects every subclass
    whether or not it would have behaved. The one below would not have.

    What the assertion is really about is the second half: `text` is built
    before the notes are touched, so the exception type and message survive. A
    guard that wrapped the whole function would have degraded this to nothing at
    all, throwing away more than the reporting was asked to lose.
    """

    class WillNotIterate(list):
        def __iter__(self):
            raise RuntimeError("this container refuses to iterate")

    exc = ValueError("real message")
    exc.__notes__ = WillNotIterate(["pyteman: while patching rule 'frozen'"])  # type: ignore[attr-defined]
    out = shim._describe(exc)
    assert "ValueError: real message" in out
    assert "<notes unavailable>" in out


def test_describe_survives_a_notes_container_whose_class_cannot_be_read(shim):
    """The shape that defeated the type check itself rather than any guard.

    isinstance is not a type test. Against an object whose type is not a list
    subtype it falls back to reading __class__, an ordinary attribute lookup
    that a property is free to define and free to raise from. So
    `isinstance(notes, list)` RAISED for the value below, from the one line in
    this function that sat outside every try, and the whole message went with
    it: the operator got `pyteman: refusing to start: loading rules: <path>:`
    and nothing after the colon.

    The exit survived it, because _refuse's finally does not depend on any of
    this. What did not survive was the promise made by every degradation in this
    function, which is that a hostile value costs the notes and never the
    exception type and message in front of them. Hence the assertion on both.
    """

    class NoClass:
        @property
        def __class__(self):  # type: ignore[override]
            raise RuntimeError("no class for you")

    exc = ValueError("real message")
    exc.__notes__ = NoClass()  # type: ignore[attr-defined]
    out = shim._describe(exc)
    assert "ValueError: real message" in out
    assert "<notes unavailable>" in out


def test_text_and_typename_return_exact_strings(shim):
    """Not raising is only half of what these two promise.

    The Boom/SubclassMeta fixtures here are parallel to BoomStr/_HostileNameMeta
    in test_activation_atomic.py. Both files exercise independent copies of
    _typename/_text (sitecustomize cannot import patcher). Keep the inputs
    equivalent; see the comment at test_activation_atomic.py:Hostile for why
    consolidation is deferred.

    str() hands back whatever __str__ returned as long as it is a str INSTANCE,
    and a subclass brings its own __repr__ and __format__ along. A caller
    interpolating that value runs user code after all, which is how the helpers
    written to absorb rendering failures became a source of them. The same hole
    reaches _typename through a metaclass serving __name__ from a property.

    Asserting the exact TYPE, not just the value: `isinstance(x, str)` is true
    for precisely the objects that defeat the guarantee, so an isinstance-based
    assertion would pass against the bug this closes.
    """

    class Boom(str):
        def __repr__(self):
            raise RuntimeError("no repr for you")

        def __format__(self, spec):
            raise RuntimeError("no format for you")

    class SubclassMeta(type):
        @property
        def __name__(cls):  # type: ignore[override]
            return Boom("Victim")

    class Victim(metaclass=SubclassMeta):
        def __str__(self):
            return Boom("looks-fine")

    v = Victim()
    assert type(shim._typename(v)) is str
    assert shim._typename(v) == "<unknown type>"
    # _text keeps the VALUE, since it rendered fine; what it must not keep is
    # the subclass, which is what would run inside the caller's f-string.
    assert type(shim._text(v)) is str
    assert shim._text(v) == "looks-fine"
    # The proof that the normalisation is what the callers needed: both of these
    # raise on the un-normalised value.
    assert f"{shim._text(v)!r}" == "'looks-fine'"
    assert f"{shim._text(v)}" == "looks-fine"


def test_typename_survives_a_type_whose_name_cannot_be_read(shim):
    """The other half of _typename: the LOOKUP raising, not its result.

    The test above covers a `__name__` that succeeds and returns something
    hostile. This covers the property raising outright, which is the branch the
    `try` exists for and which nothing else in this file reaches.

    Worth having in THIS file specifically, rather than relying on the matching
    test against the patcher's copy. The two copies are duplicated deliberately,
    and the argument for duplicating them is that they behave identically; that
    is only shown if both are driven by the same inputs. This copy is the one on
    the fail-closed path, so it is the one that must not be the less tested of
    the two.

    The composed case is the point of the second half. _text renders the name
    into `<unprintable ...>`, so a _typename that raised instead of degrading
    would take _text down with it, and _text is what every caller on the refusal
    path goes through.
    """

    class NoNameMeta(type):
        @property
        def __name__(cls):  # type: ignore[override]
            raise RuntimeError("no name for you")

    class Nameless(metaclass=NoNameMeta):
        def __str__(self):
            raise RuntimeError("no str either")

    n = Nameless()
    assert shim._typename(n) == "<unknown type>"
    assert type(shim._typename(n)) is str
    assert shim._text(n) == "<unprintable <unknown type>>"
    assert type(shim._text(n)) is str


# A stand-in pyteman whose loader raises something unrenderable. Synthetic
# because no exception the real loader raises behaves this way, and that is the
# point: the refusal path has to be total against whatever arrives, not against
# the classes pyteman happens to raise today. The same handler is reachable with
# real code through a container whose __setattr__ raises a custom exception.
# Parallel to Hostile(Exception) in test_activation_atomic.py; see that file's
# comment for why the duplication is deliberate.
FAKE_RULES = '''
class Unrenderable(Exception):
    def __str__(self):
        raise RuntimeError("stringification failed")

def load_rules(path):
    raise Unrenderable()
'''


def fake_pyteman(tmp, body=FAKE_RULES, patcher_body=None, firing_body=None):
    pkg = tmp / "fake" / "pyteman"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "rules.py").write_text(body)
    # Stubs: the run dies in load_rules, and these only have to be importable.
    # A caller aiming at a LATER phase overrides the one it needs, so each of
    # the four failure phases can be reached on its own terms.
    (pkg / "patcher.py").write_text(patcher_body or
                                    "def activate(rules, log, modules):\n"
                                    "    return object()\n")
    (pkg / "firing.py").write_text(firing_body or
                                   "def open_log(p):\n    return object()\n")
    return tmp / "fake"


def test_refusal_holds_when_the_error_cannot_be_rendered(sandbox):
    """A hostile __str__ costs the detail and nothing else, on the real path.

    The four _describe tests above call it directly; this one is the same
    degradation observed through interpreter startup, where the exit code and
    the workload's silence are the things actually at stake.

    What this does NOT prove is where the rendering happens. _describe absorbs
    this input and returns, so the assertions below would hold just as well with
    the rendering back in the argument to _refuse. The test underneath is the
    one that pins that down.
    """
    r = refused(sandbox, {"PYTEMAN_RULES": str(rules_file(sandbox)),
                          # Ahead of the real package, not merely alongside it.
                          "PYTHONPATH": f"{fake_pyteman(sandbox)}:{sandbox}:{SRC}"})
    assert_refused(r, "loading rules", "Unrenderable", "unprintable")


# The failure is INJECTED rather than provoked with hostile input, and that is
# the point. Every guard _describe has makes it harder to defeat with a value,
# and the last one closed the only remaining shape, so a test that fed it
# something nasty would have to be rewritten each time the renderer improves and
# would eventually assert nothing. The guarantee is not that no input defeats
# _describe; it is that _refuse exits 2 whatever _describe does. Replacing
# _describe with a function that raises tests exactly that, and keeps testing it
# however total the real one becomes.
#
# Measured both ways: against the code as written this exits 2 with stdout
# silent, and with the rendering moved back into the argument to _refuse it
# prints `Error in sitecustomize`, runs the workload and exits 0.
FAKE_RULES_HOSTILE_DESCRIBE = '''
def load_rules(path):
    import sys
    shim = sys.modules["sitecustomize"]

    def boom(exc):
        raise RuntimeError("describing the failure blew up")

    shim._describe = boom
    raise ValueError("the original failure")
'''


def test_refusal_holds_when_describing_the_error_raises(sandbox):
    """The structural guarantee: rendering runs inside the try/finally.

    _describe is user-facing code reading user data, so it can raise no matter
    how carefully it is written. It used to be called as an ARGUMENT to _refuse,
    which evaluated it before _refuse was entered and therefore outside the
    try/finally that makes os._exit unconditional. Anything raised there hit
    site.execsitecustomize's `except Exception`, which swallowed it: the process
    printed `Error in sitecustomize`, ran the workload UNINSTRUMENTED and exited
    0, reporting success for an experiment that injected nothing.

    stdout being silent is half the assertion and not a formality. A non-zero
    exit with WORKLOAD_RAN present would mean the run happened and was merely
    reported badly afterwards, which is the failure this whole path exists to
    make impossible.
    """
    r = refused(sandbox, {"PYTEMAN_RULES": str(rules_file(sandbox)),
                          "PYTHONPATH": f"{fake_pyteman(sandbox, FAKE_RULES_HOSTILE_DESCRIBE)}"
                                        f":{sandbox}:{SRC}"})
    # The phase and nothing after it: the detail is exactly what a raising
    # _describe costs, and the line naming where to look is what survives.
    assert_refused(r, "loading rules")
    assert "the original failure" not in r.stderr, r.stderr


# A refusal that is not an Exception. Ctrl-C during startup is the ordinary way
# to reach it: the operator interrupts a run that is taking too long to load a
# large ruleset, and everything below happens in the interpreter's startup, so
# there is no workload frame for the interrupt to land in.
_INTERRUPTS = "raise KeyboardInterrupt()\n"
# A loader good enough to get past its own phase, so the later three can be
# reached. activate() is handed `sorted({r.module for r in rules})`, which is
# the whole of what _main asks of a rule here.
_GOOD_LOADER = '''
class _R:
    module = "target_mod"

def load_rules(path):
    return [_R()]
'''


@pytest.mark.parametrize("phase, bodies", [
    ("importing pyteman", {"body": _INTERRUPTS}),
    ("loading rules", {"body": "def load_rules(path):\n    " + _INTERRUPTS}),
    ("opening the firing log",
     {"body": _GOOD_LOADER, "firing_body": "def open_log(p):\n    " + _INTERRUPTS}),
    ("installing instrumentation",
     {"body": _GOOD_LOADER,
      "patcher_body": "def activate(rules, log, modules):\n    " + _INTERRUPTS}),
])
def test_refusal_holds_when_the_failure_is_not_an_exception(sandbox, phase, bodies):
    """All four handlers in _main catch BaseException, and Exception is not enough.

    An activation interrupted by Ctrl-C has not happened either, so it owes the
    operator the same account as any other failed activation. Narrowed to
    Exception, the interrupt walks past _main into site.execsitecustomize, whose
    own handler is also `except Exception` and also declines it; startup then
    fails with `Fatal Python error: init_import_site`, which reports exit 1 and
    names no phase. The operator loses both things this path exists to give
    them: the code that distinguishes a refusal from an ordinary failure, and
    the word saying which of the five phases to go and look at.

    All four phases rather than a representative one. They are four separate
    handlers, so a narrowing is four independent edits, and a test covering one
    of them leaves the other three free to regress while it goes on passing.

    Injected rather than provoked, for the reason given above
    FAKE_RULES_HOSTILE_DESCRIBE: a real Ctrl-C cannot be aimed at a chosen phase
    from a test, and the guarantee is about the handler rather than about any
    particular way of reaching it.
    """
    r = refused(sandbox, {"PYTEMAN_RULES": str(rules_file(sandbox)),
                          "PYTHONPATH": f"{fake_pyteman(sandbox, **bodies)}"
                                        f":{sandbox}:{SRC}"})
    assert_refused(r, phase, "KeyboardInterrupt")
    # The shape the narrowed handler produces, asserted against by name so a
    # regression cannot pass by exiting 2 for some other reason.
    assert "init_import_site" not in r.stderr, r.stderr
