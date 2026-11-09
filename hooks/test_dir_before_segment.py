#!/usr/bin/env python3
"""Cases for dir_before_segment (hooks/guard_core.py): the folder the shell is in when a segment runs.

Run it from the repository root:

    python3 hooks/test_dir_before_segment.py

A `cd` to a literal path is read. A `cd "$VAR"`, `cd $VAR` or `cd "${VAR}"` is not: its target holds
`$`, so the walk drops it and the folder becomes unknown. The cases pin the folder a variable target
resolves to (through guard_frozen._resolve_vars, the one resolver), the folder an unresolvable target
stays unknown as, and the walk's own state (`cd -`, subshells, pipes, a failed cd) around a variable.

Each case names its segment by text and checks that exactly one segment holds that text before it reads
the folder of that segment. Folders are real directories under this run's folder (lint/_test_temp.py),
so a `cd` into them is trusted. A folder that is never made stands for a `cd` that fails.

Green controls pass on the current code and must stay green. A red case fails there for the one stated
cause: the folder a variable names is not read. A case that waits on another step is kept, not run, and
printed as SKIP with that step's name.
"""
import os
import shutil
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "lint"))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
sys.path.insert(0, HERE)
import guard_core  # noqa: E402
import guard_frozen  # noqa: E402  the one resolver a variable target reads through (_resolve_vars)

ROOT = _test_temp.run_folder()
CASES = []
FAILED = []


def folder(*parts):
    """A real folder under this run's folder."""
    path = os.path.join(ROOT, *parts)
    os.makedirs(path, exist_ok=True)
    return path


SHELL = folder("shell")                 # the folder the shell is in when the command starts
TARGET = folder("real", "dir")          # a folder a variable names
PARENT = folder("real")                 # a folder a variable names, one level up
CHILD = folder("real", "x")             # PARENT/x: the folder a variable built from PARENT names
SECOND = folder("second")               # the folder a cd moves to before a `cd -`
MISSING = os.path.join(ROOT, "missing")  # never made: a cd into it fails


def check(label, ok, detail=""):
    if not ok:
        FAILED.append("%s: %s" % (label, detail) if detail else label)


def expect(label, command, scope, want, cwd=SHELL, failed_cd_stays=False):
    """The folder dir_before_segment gives the segment that holds SCOPE, which must be the one segment
    that holds it. `want` is None when the walk cannot tell the folder."""
    ends = []
    segments = guard_core.split_segments(command, ends)
    named = [number for number, segment in enumerate(segments) if scope in segment]
    check(label + " (scope)", len(named) == 1, "%d segments hold %r in %r" % (len(named), scope, command))
    if len(named) != 1:
        return
    got = guard_core.dir_before_segment(segments, named[0], cwd, ends, failed_cd_stays=failed_cd_stays)
    check(label, got == want, "got %r, want %r" % (got, want))


SKIPPED = []  # (label, reason): a case that waits on another step. It stays listed and prints its reason.


def case(label, command, scope, want, cwd=SHELL, failed_cd_stays=False, skip=None):
    if skip is not None:
        SKIPPED.append((label, skip))
        CASES.append((label, None))
        return
    CASES.append((label, lambda: expect(label, command, scope, want, cwd, failed_cd_stays)))


# --- A variable target is read: the folder is the one it holds (red on the current code).
case("cd \"$R\" reads R as the folder it holds",
     'R=%s; cd "$R" && git status' % TARGET, "git status", TARGET)
case("cd $R, unquoted, reads R as the folder it holds",
     'R=%s; cd $R && git status' % TARGET, "git status", TARGET)
case("cd \"${R}\", braced, reads R as the folder it holds",
     'R=%s; cd "${R}" && git status' % TARGET, "git status", TARGET)
case("a variable built from another, B=\"$A\"/x, reads as A/x",
     'A=%s; B="$A"/x; cd "$B" && git status' % PARENT, "git status", CHILD,
     skip="waits on step 847 resolve-vars-quote-split")
case("a variable built from another, B=$A/x, unquoted, reads as A/x",
     'A=%s; B=$A/x; cd "$B" && git status' % PARENT, "git status", CHILD)
case("a relative variable after an earlier cd reads from the folder that cd made",
     'cd %s && R=real/x; cd "$R" && git status' % ROOT, "git status", CHILD)
case("a variable cd in a subshell reads its folder, and the command in the group runs there",
     'R=%s; ( cd "$R" && git status )' % TARGET, "git status", TARGET)
case("a variable cd with a missing folder, joined by ;, leaves the shell where it was",
     'R=%s; cd "$R"; git status' % MISSING, "git status", SHELL, failed_cd_stays=True)
case("a chain of 200 variable cds reads the one folder they all hold",
     'R=%s; ' % TARGET + 'cd "$R"; ' * 200 + "git status", "git status", TARGET)

# --- The walk keeps its own state around a variable target (green controls: today's walk gets these).
case("cd - after a variable cd goes back to the folder before the last move",
     'cd %s && R=%s; cd "$R" && cd - && git status' % (SECOND, TARGET), "git status", SECOND)
case("a variable cd in a pipe moves nothing, as a literal cd in a pipe moves nothing",
     'R=%s; cd "$R" | cat; git status' % TARGET, "git status", SHELL)
case("a subshell cd that ends at its paren moves nothing after it",
     'R=%s; ( cd "$R" ) && git status' % TARGET, "git status", SHELL)
case("a missing folder from a variable cd, joined by &&, stops the chain: None",
     'R=%s; cd "$R" && git status' % MISSING, "git status", None, failed_cd_stays=True)
case("a missing folder from a variable cd, with failed_cd_stays off: None",
     'R=%s; cd "$R"; git status' % MISSING, "git status", None)
case("a literal missing cd, joined by ;, leaves the shell where it was (the twin of the variable case)",
     'cd %s; git status' % MISSING, "git status", SHELL, failed_cd_stays=True)
case("a literal missing cd, joined by &&, stops the chain: None (the twin of the variable case)",
     'cd %s && git status' % MISSING, "git status", None, failed_cd_stays=True)
case("an empty command reads the shell's folder",
     "", "", SHELL)

# --- A variable the walk cannot read stays unknown: None, as today (green controls).
case("an unassigned variable is unknown: None",
     'cd "$X" && git status', "git status", None)
case("a variable set by command substitution is unknown: None",
     'R=$(pwd); cd "$R" && git status', "git status", None)
case("a variable set by backticks is unknown: None",
     'R=`pwd`; cd "$R" && git status', "git status", None)
case("a variable unset after its assignment is unknown: None",
     'R=%s; unset R; cd "$R" && git status' % TARGET, "git status", None)
case("a variable built from an unknown one is unknown: None",
     'R=$(pwd); A="$R"/x; cd "$A" && git status', "git status", None)


def case_home():
    """`$HOME` reads as `~`, the one mapping _resolve_vars makes, so `cd "$HOME"` is the folder `cd ~` is.
    HOME and USERPROFILE point at a folder of this run, and both are put back after the case."""
    home = folder("home")
    saved = {name: os.environ.get(name) for name in ("HOME", "USERPROFILE")}
    os.environ["HOME"] = home
    os.environ["USERPROFILE"] = home
    try:
        expect("cd \"$HOME\" reads the home folder, as cd ~ does", 'cd "$HOME" && git status',
               "git status", home)
        expect("cd ~ is the home folder (the literal twin of cd \"$HOME\")", 'cd ~ && git status',
               "git status", home)
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def case_inline_script():
    """guard_frozen reads a `python3 -c` script's relative paths in the folder the segment runs in
    (_interpreter_write_hit takes dir_before_segment). After a variable cd that folder is the one held."""
    seen = []

    def predicate(path, where):
        seen.append((path, where))
        return False

    command = '''R=%s; cd "$R" && python3 -c "open('note.txt', 'w').write('x')"''' % TARGET
    guard_frozen.interpreter_write_hit(command, SHELL, predicate)
    check("an inline script after a variable cd: the write is judged (scope)", bool(seen),
          "the predicate was never asked about %r" % command)
    if seen:
        check("an inline script after a variable cd: its path is judged in the folder the cd holds",
              seen[0][1] == TARGET, "path %r judged in %r, want %r" % (seen[0][0], seen[0][1], TARGET))


def case_sweep():
    """lint/_test_temp.sweep, the one home of the run-folder sweep: a sibling run folder older than a day
    goes, a newer one stays, and the own folder stays. A fixed epoch stands for the clock."""
    now = 1800000000.0
    sweep_root = folder("sweep")
    old = os.path.join(sweep_root, "1-" + uuid.uuid4().hex)
    new = os.path.join(sweep_root, "2-" + uuid.uuid4().hex)
    own = os.path.join(sweep_root, "3-" + uuid.uuid4().hex)
    for path, age in ((old, 2 * 24 * 60 * 60 + 60), (new, 60), (own, 2 * 24 * 60 * 60 + 60)):
        os.makedirs(path)
        os.utime(path, (now - age, now - age))
    _test_temp.sweep(sweep_root, own, now=now)
    check("the sweep removes a sibling run folder older than a day", not os.path.exists(old),
          "the old sibling is still there")
    check("the sweep keeps a newer sibling run folder", os.path.isdir(new), "the newer sibling was removed")
    check("the sweep keeps the own run folder", os.path.isdir(own), "the own folder was removed")


CASES.append(("$HOME as ~, and its literal twin", case_home))
CASES.append(("an inline python script after a variable cd reads the folder the cd holds", case_inline_script))
CASES.append(("the run-folder sweep removes an old sibling and keeps a new one", case_sweep))


def main():
    red = []
    run_count = 0
    try:
        for label, run in CASES:
            if run is None:
                continue
            run_count += 1
            before = len(FAILED)
            try:
                run()
            except Exception as exc:  # a case that cannot run is red, never silently green
                check(label + " (case ran)", False, "%s: %s" % (type(exc).__name__, exc))
            if len(FAILED) > before:
                red.append(label)
    finally:
        shutil.rmtree(ROOT, ignore_errors=True)
    for label, reason in SKIPPED:
        print("SKIP %s: %s" % (label, reason))
    if FAILED:
        print("test_dir_before_segment FAIL: %d of %d run cases red, %d skipped"
              % (len(red), run_count, len(SKIPPED)))
        for line in FAILED:
            print("  " + line)
        return 1
    print("test_dir_before_segment PASS: all %d run cases green, %d skipped" % (run_count, len(SKIPPED)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
