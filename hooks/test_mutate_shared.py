#!/usr/bin/env python3
"""Cases for hooks/mutate_shared.py's verdict. Standard library only.

    python3 hooks/test_mutate_shared.py

`report_verdict` is the line every mutation test trusts to say a guard went red on the defect
it guards (CLAUDE.md: trust a guard only once it goes red on the defect). It is tested here with
one known-bad input per wrong verdict: a mutant the suite did not catch must read "survived",
and a red suite that never names the case must read "wrong_cause", never "killed".

The second half pins the guard-family copy: `guard_tree` copies every hooks/guard*.py, shared_names.py
and git_reads.py, and `apply_mutant` lands a find-string in the one copied file that holds it
(zero matches is STALE, two or more is an error), so a guard split into sibling modules, or into
git_reads.py, is still mutated in the right file. `build_scaffold` in janitor/mutate_sweep.py gets the same pin: a sibling is written into the
scaffold's hooks/ folder, and a mutant aimed at a sibling lands there.

The third part pins `staged_suite`'s stage-1 verdict: when stage 1 runs the required case, its result
is the verdict and the full suite never runs. The full suite runs only when no line names the case,
or when MUTATE_FULL=1 asks for it.

The fourth part pins the layout of a guard mutant's folder: its copy must import lint/layout.py from
its own root, the folder beside its hooks/.

The fifth part pins the clean-layout control: a target's mutants count as kills only after one filtered run
(one required case fragment of its own mutations) of the unmutated layout passes. A red control reads each mutant UNKNOWN, never KILLED. The control
runs inside the MUTATE_JOBS cap, and a control that raises reads its mutants UNKNOWN too.

The sixth part pins the family suites: a suite named `path::family` runs the file `path` with GUARD_FAMILY=family in
its env, and the file part is what the profile's `tests` regex and the isfile check read.

The seventh part pins the suite timeout: a suite that outlives SUITE_TIMEOUT is CRASHED, not a kill and not a survivor.
Its mutant reads UNKNOWN, the stage-2 fallback does not run it again, and the run goes on to the next mutant.
"""
import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import unittest
from unittest import mock

HOOKS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HOOKS)
sys.path.insert(0, os.path.join(os.path.dirname(HOOKS), "janitor"))
sys.path.insert(0, os.path.join(os.path.dirname(HOOKS), "lint"))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
import mutate_guard  # noqa: E402
import mutate_shared  # noqa: E402
import mutate_sweep  # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(HOOKS), "testing"))
import tracked_tree  # noqa: E402  git's tracked files under a folder, suites left out (testing/tracked_tree.py)

REQUIRED = "case: the rule under test"
RED_RIGHT = ["FAIL  allow (want deny) [Bash] case: the rule under test"]
RED_WRONG = ["FAIL  allow (want deny) [Bash] some other case"]
PASS_RIGHT = "PASS  allow (want allow) [Bash] case: the rule under test"
FULL_RED = ["FAIL  allow (want deny) [Bash] the full suite only"]


def verdict(code, red):
    with contextlib.redirect_stdout(io.StringIO()):
        return mutate_shared.report_verdict("mutant", code, red, REQUIRED)


class ReportVerdictTests(unittest.TestCase):

    def test_red_suite_naming_the_required_case_is_killed(self):
        self.assertEqual(verdict(1, RED_RIGHT), "killed")

    def test_exit_zero_with_red_lines_survives(self):
        self.assertEqual(verdict(0, RED_RIGHT), "survived")

    def test_nonzero_exit_with_no_red_line_survives(self):
        self.assertEqual(verdict(1, []), "survived")

    def test_red_suite_missing_the_required_case_is_wrong_cause(self):
        self.assertEqual(verdict(1, RED_WRONG), "wrong_cause")

    def test_run_mutants_fails_on_one_survivor(self):
        def run_one(entry):
            return entry, 0, [], REQUIRED, None
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(mutate_shared.run_mutants(["m"], run_one), 1)

    def test_run_mutants_passes_when_every_mutant_is_killed(self):
        def run_one(entry):
            return entry, 1, RED_RIGHT, REQUIRED, None
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(mutate_shared.run_mutants(["m"], run_one), 0)


class ShardTests(unittest.TestCase):
    """MUTATE_SHARD=i/n runs entries[i-1::n]; the n shards together run every mutant once."""

    def run_shard(self, value, entries):
        ran = []

        def run_one(entry):
            ran.append(entry)
            return entry, 1, RED_RIGHT, REQUIRED, None
        env = dict(os.environ)
        env.pop("MUTATE_SHARD", None)
        if value is not None:
            env["MUTATE_SHARD"] = value
        with mock.patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(io.StringIO()):
            return mutate_shared.run_mutants(entries, run_one), ran

    def test_shards_together_run_each_mutant_once(self):
        entries = list("abcdefg")
        seen = []
        for i in (1, 2, 3):
            code, ran = self.run_shard("%d/3" % i, entries)
            self.assertEqual(code, 0)
            seen += ran
        self.assertEqual(sorted(seen), entries)

    def test_no_shard_runs_all(self):
        self.assertEqual(self.run_shard(None, list("abc"))[1], list("abc"))

    def test_bad_value_or_empty_slice_fails_without_running(self):
        for value in ("0/3", "4/3", "x", "1/0"):
            self.assertEqual(self.run_shard(value, list("abc")), (1, []))
        self.assertEqual(self.run_shard("3/3", list("ab")), (1, []))  # empty slice proved nothing

    def test_shard_runs_only_the_controls_its_mutants_read(self):
        asked = []

        def control(key):
            def run():
                asked.append(key)
                return 0, [], ["case"], []
            return run
        entries = [("a", "t1"), ("b", "t2"), ("c", "t1")]
        controls = {"t1": control("t1"), "t2": control("t2")}

        def run_one(entry):
            return entry[0], 1, RED_RIGHT, REQUIRED, None
        env = dict(os.environ, MUTATE_SHARD="2/2")
        with mock.patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(io.StringIO()):
            code = mutate_shared.run_mutants(entries, run_one, controls=controls, control_of=lambda e: e[1])
        self.assertEqual((code, asked), (0, ["t2"]))  # entries[1::2] is only ("b", "t2")

    def test_red_control_reads_unknown_in_a_shard(self):
        def red():
            return 1, ["FAIL x"], ["case"], []

        def run_one(entry):
            return entry, 1, RED_RIGHT, REQUIRED, None
        env = dict(os.environ, MUTATE_SHARD="1/2")
        with mock.patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(io.StringIO()):
            code = mutate_shared.run_mutants(["a", "b"], run_one, controls={"k": red}, control_of=lambda e: "k")
        self.assertEqual(code, 1)


def write_files(root, files):
    for rel, body in files.items():
        with open(os.path.join(root, rel), "w", encoding="utf-8", newline="\n") as f:
            f.write(body)


def read_file(root, rel):
    with open(os.path.join(root, rel), encoding="utf-8", newline="") as f:
        return f.read()


class GuardTreeTests(unittest.TestCase):
    """`guard_tree(dest)` copies hooks/guard*.py (read from `mutate_shared.HOOKS_DIR`, read at
    call time). `apply_mutant(tree, old, new)` mutates the one copied file holding `old`."""

    def setUp(self):
        self.src = tempfile.mkdtemp()
        self.dest = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.src, True)
        self.addCleanup(shutil.rmtree, self.dest, True)
        # test_guard.py and mutate_guard.py carry the anchor too: a copy that wrongly took
        # them would match twice and read as an error, so the glob is pinned by these two.
        write_files(self.src, {
            "guard.py": "alpha\n",
            "guard_x.py": "beta-anchor\n",
            "test_guard.py": "beta-anchor\n",
            "mutate_guard.py": "beta-anchor\n",
            "shared_names.py": "NAMES\n",
            "git_reads.py": "reads-anchor\n",
        })
        patcher = mock.patch.object(mutate_shared, "HOOKS_DIR", self.src, create=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_guard_tree_copies_every_guard_module_and_shared_names_and_nothing_else(self):
        mutate_shared.guard_tree(self.dest)
        self.assertEqual(sorted(os.listdir(self.dest)),
                         ["git_reads.py", "guard.py", "guard_x.py", "shared_names.py"])
        self.assertEqual(read_file(self.dest, "guard_x.py"), "beta-anchor\n")

    def test_guard_tree_copies_a_new_shared_module_but_no_suite_or_harness(self):
        # A module the guard starts to import must reach the copy, or every mutant dies on the import.
        write_files(self.src, {"new_shared.py": "X = 1\n", "prove_x.py": "p\n", "notes.md": "n\n"})
        mutate_shared.guard_tree(self.dest)
        self.assertEqual(sorted(os.listdir(self.dest)),
                         ["git_reads.py", "guard.py", "guard_x.py", "new_shared.py", "shared_names.py"])

    def test_a_mutant_anchored_in_git_reads_mutates_git_reads(self):
        # The git and session reads the guard once held now live in git_reads.py, and the guard
        # mutants anchored on them must still land: a mutant no module holds reads STALE.
        mutate_shared.guard_tree(self.dest)
        where = mutate_shared.apply_mutant(self.dest, "reads-anchor", "BROKEN")
        self.assertEqual(os.path.basename(where), "git_reads.py")
        self.assertEqual(read_file(self.dest, "git_reads.py"), "BROKEN\n")
        self.assertEqual(read_file(self.dest, "guard.py"), "alpha\n")

    def test_a_mutant_anchored_in_own_session_mutates_own_session(self):
        # The own get_session read lives in own_session.py, the one home that guard_merge.py and
        # lint/report_guard.py both import. A roadmap-one-writer mutant aimed at it must land there.
        write_files(self.src, {"own_session.py": "own-record-anchor\n"})
        mutate_shared.guard_tree(self.dest)
        where = mutate_shared.apply_mutant(self.dest, "own-record-anchor", "BROKEN")
        self.assertEqual(os.path.basename(where), "own_session.py")
        self.assertEqual(read_file(self.dest, "own_session.py"), "BROKEN\n")
        self.assertEqual(read_file(self.dest, "guard.py"), "alpha\n")

    def test_a_mutant_anchored_in_shared_names_mutates_shared_names(self):
        # The brief marker rows live in shared_names.py, the one home the guard reads them from. A mutant aimed at a row
        # must land there and not read as STALE, so it can break the row it names. An assert, not a crash, on the old code.
        write_files(self.src, {"shared_names.py": "names-anchor\n"})
        mutate_shared.guard_tree(self.dest)
        try:
            where = os.path.basename(mutate_shared.apply_mutant(self.dest, "names-anchor", "BROKEN"))
        except mutate_shared.StaleMutant:
            where = None
        self.assertEqual(where, "shared_names.py")
        self.assertEqual(read_file(self.dest, "shared_names.py"), "BROKEN\n")
        self.assertEqual(read_file(self.dest, "guard.py"), "alpha\n")

    def test_one_match_in_a_sibling_mutates_the_sibling(self):
        mutate_shared.guard_tree(self.dest)
        where = mutate_shared.apply_mutant(self.dest, "beta-anchor", "BROKEN")
        self.assertEqual(os.path.basename(where), "guard_x.py")
        self.assertEqual(read_file(self.dest, "guard_x.py"), "BROKEN\n")
        self.assertEqual(read_file(self.dest, "guard.py"), "alpha\n")

    def test_zero_matches_reports_stale_and_writes_nothing(self):
        mutate_shared.guard_tree(self.dest)
        with self.assertRaises(mutate_shared.StaleMutant) as ctx:
            mutate_shared.apply_mutant(self.dest, "no-such-text", "X")
        self.assertIn("STALE", str(ctx.exception))
        self.assertEqual(read_file(self.dest, "guard.py"), "alpha\n")
        self.assertEqual(read_file(self.dest, "guard_x.py"), "beta-anchor\n")

    def test_a_match_in_two_files_is_an_error_and_writes_nothing(self):
        mutate_shared.guard_tree(self.dest)
        write_files(self.dest, {"guard.py": "dup\n", "guard_x.py": "dup\n"})
        with self.assertRaises(mutate_shared.AmbiguousMutant):
            mutate_shared.apply_mutant(self.dest, "dup", "X")
        self.assertEqual(read_file(self.dest, "guard.py"), "dup\n")
        self.assertEqual(read_file(self.dest, "guard_x.py"), "dup\n")

    def test_two_matches_in_one_file_is_an_error(self):
        mutate_shared.guard_tree(self.dest)
        write_files(self.dest, {"guard.py": "dup dup\n"})
        with self.assertRaises(mutate_shared.AmbiguousMutant):
            mutate_shared.apply_mutant(self.dest, "dup", "X")
        self.assertEqual(read_file(self.dest, "guard.py"), "dup dup\n")


class GuardTreeImportsTests(unittest.TestCase):
    """The copy a mutation test runs must import: config_watch.py and guard_core.py need shared_names,
    and a copy without it dies on the import, a kill with no bearing on the mutation."""

    def test_copied_guard_and_watch_import_from_the_tree_alone(self):
        dest = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, dest, True)
        mutate_shared.guard_tree(dest)
        shutil.copy(os.path.join(HOOKS, "config_watch.py"), dest)
        for module in ("guard", "config_watch"):
            result = subprocess.run(
                [sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); import " + module, dest],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, module + ": " + result.stderr[-300:])


MOCKUP_HOME_ARM = "mockup-home: the refuse arm is dropped"  # the label prefix of the mockup-home guard mutant
ROLE_MODEL_ARM = "role-model: Explore loses its audit exemption"  # the label prefix of a role-model guard mutant


def git_listed(folder):
    """The paths git lists under `folder`, suites left out as tracked_tree.is_suite leaves them. The expectation
    comes from git itself, not from tracked_tree, so it does not share the helper the fix builds the root with."""
    done = subprocess.run(["git", "ls-files", "-z", "--", folder], cwd=tracked_tree.REPO, capture_output=True)
    if done.returncode != 0:
        raise RuntimeError("git ls-files failed for %s: %s" % (folder, done.stderr.decode(errors="replace")))
    names = done.stdout.decode("utf-8", "surrogateescape").split("\0")
    return sorted(name for name in names if name and not tracked_tree.is_suite(name))


class GuardMutantLayoutTests(unittest.TestCase):
    """A guard mutant runs from <root>/hooks, so its ../lint is <root>/lint. guard.py reads lint/layout.py
    from there (role_model_table, record_branch_of). Without that folder the import fails, the role-model
    table reads as unread, and every role-model arm passes unjudged: a survivor that has no bearing on
    its mutation. The same root holds the skills/ files a guard reads, from git's own list: the mockup-home
    check imports skills/waiting-page/stale_pages.py, and a root without it crashes that case."""

    def setUp(self):
        self.run = _test_temp.run_folder()
        self.addCleanup(shutil.rmtree, self.run, True)

    def built_root(self, prefix):
        """(root, copy path) of the guard mutant whose label starts with `prefix`, as run_mutant builds it. The
        suite is stubbed out, so this builds the root and runs no case."""
        entry = next(e for e in mutate_guard.MUTATIONS if mutate_guard.mutation_parts(e)[0].startswith(prefix))
        copies = []

        def record(suite, variable, copy_path, config_dir, only=None):
            copies.append(copy_path)
            return 0, [], []

        def one_stage(run, required):
            run(None)
            return 0, []

        with mock.patch.object(mutate_guard, "run_suite", side_effect=record), \
                mock.patch.object(mutate_shared, "staged_suite", side_effect=one_stage):
            mutate_guard.run_mutant({}, self.run, entry)
        self.assertEqual(len(copies), 1)
        self.assertTrue(os.path.isfile(copies[0]), "run_mutant wrote no guard.py for %s" % prefix)
        return os.path.dirname(os.path.dirname(copies[0])), copies[0]

    def stage_one(self, prefix):
        """run_mutant on the guard mutant whose label starts with `prefix`, its suite run for real, stage 1 only:
        the required case alone, never the full suite. Return (run_mutant's tuple, the case lines stage 1 printed)."""
        entry = next(e for e in mutate_guard.MUTATIONS if mutate_guard.mutation_parts(e)[0].startswith(prefix))
        lines = []

        def one_stage(run, required):
            code, red, ran = run(required)
            lines.extend(ran)
            return code, red

        with mock.patch.object(mutate_shared, "staged_suite", side_effect=one_stage):
            result = mutate_guard.run_mutant({}, self.run, entry)
        return result, lines

    def test_copied_guard_imports_the_lint_layout_from_its_own_root(self):
        _root, copy_path = self.built_root(ROLE_MODEL_ARM)
        hooks = os.path.dirname(copy_path)
        # -I drops the cwd from sys.path, so a lint/ in the working directory cannot satisfy the import.
        result = subprocess.run(
            [sys.executable, "-I", "-c",
             "import sys; sys.path.insert(0, sys.argv[1]); import guard; guard._layout_module()",
             hooks],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0,
                         "the copied guard cannot import lint/layout.py from its root: " + result.stderr[-300:])

    def test_mockup_home_mutant_dies_on_its_own_case(self):
        # One real stage-1 run serves the three claims, in order. A crashed suite's orphan sleep holds its stdout
        # pipe, so run_suite waits that out (see its comment): this case is slow only while the crash is there.
        (_label, _code, red, required, _skip, seen), lines = self.stage_one(MOCKUP_HOME_ARM)
        # Scope before subject: the FAIL line below means something only if stage 1 reached its required case.
        self.assertTrue(any(required in line for line in lines),
                        "stage 1 printed no line for %r: the suite died before its own case" % required)
        # run_mutant returns no stderr, so this stays green until the diagnostics carry a traceback.
        crashed = [line for line in red + seen if "ModuleNotFoundError" in line]
        self.assertEqual(crashed, [], "a returned line holds ModuleNotFoundError: %r" % crashed)
        own = [line for line in red if line.startswith("FAIL") and required in line]
        self.assertTrue(own, "the mutant did not die on its own case %r: no FAIL line names it" % required)

    def test_guard_mutant_root_holds_every_tracked_waiting_page_file(self):
        root, _copy = self.built_root(MOCKUP_HOME_ARM)
        listed = git_listed("skills/waiting-page")
        self.assertIn("skills/waiting-page/stale_pages.py", listed,
                      "scope: git lists no stale_pages.py under skills/waiting-page")
        missing = [rel for rel in listed if not os.path.isfile(os.path.join(root, *rel.split("/")))]
        self.assertEqual(missing, [], "the mutant root lacks tracked skills/waiting-page files")

    def test_guard_mutant_root_holds_the_impeccable_skill_file(self):
        root, _copy = self.built_root(MOCKUP_HOME_ARM)
        self.assertTrue(os.path.isfile(os.path.join(tracked_tree.REPO, "skills", "impeccable", "SKILL.md")),
                        "scope: the checkout holds no skills/impeccable/SKILL.md")
        self.assertTrue(os.path.isfile(os.path.join(root, "skills", "impeccable", "SKILL.md")),
                        "the mutant root lacks skills/impeccable/SKILL.md, which guard.py reads")


def tree_text(copy_path):
    """Every module beside `copy_path`, joined: a mutant's new text lands in one of them."""
    folder = os.path.dirname(copy_path)
    texts = []
    for name in sorted(os.listdir(folder)):
        if name.endswith(".py"):
            with open(os.path.join(folder, name), encoding="utf-8") as handle:
                texts.append(handle.read())
    return "\n".join(texts)


def fail_result(*names):
    lines = ["FAIL  allow (want deny) [Bash] " + name for name in names]
    return 1, lines, list(lines), []


def pass_result(*names):
    lines = ["PASS  allow (want allow) [Bash] " + name for name in names]
    return 0, [], lines, []


JOIN_WAIT = 0.5  # a call waits this long for a second call to join it, so overlap shows without a fixed sleep
RELEASE_WAIT = 1.0  # a held control waits this long for the mutant it is held on, so no case hangs
RUN_LIMIT = 4.0  # main must return within this long, or the case reads a stall, not a hang
HANG_SECONDS = 10  # a hung suite sleeps this long: longer than each SUITE_TIMEOUT the timeout cases set


class _FakeSuite:
    """A stand-in for `mutate_guard.run_suite`, called as (suite, variable, copy_path, config_dir, only).

    A call is keyed by its copy_path, which holds the name its copy was laid out under: a mutant's label,
    or a target's clean-layout control name. The key, not the text of a folder, says which call it is, so a
    watch copy stays apart from the other watch copies that share `work`. A mutant's call FAILs its required
    case. A control (a target's clean-layout key, whatever `only` it was asked for) is green when
    `control_passes`, red otherwise.

    `hooks` maps a key to a zero-argument function that runs in place of that call's answer, so a case can
    hold a call or raise from it. `join` holds each call up to JOIN_WAIT for a second call to join it.
    `release` maps a key to an Event that is set once that call has ended and been logged. `active` and
    `peak` count the calls in flight, `events` lists each call's end by key in order, and `calls` records
    each call's key, `only`, `tree` and `mutant`. The counts sit under one lock."""

    def __init__(self, entries, control_passes, hooks=None, join=False, release=None):
        self.names = {}  # key -> required case, or None for a target's clean-layout control
        self.required = []
        for entry in entries:
            label, _old, _new, target, required, _only_on = mutate_guard.mutation_parts(entry)
            self.names[label] = required
            self.names[mutate_guard.control_name(target)] = None
            self.required.append(required)
        self.control_passes = control_passes
        self.hooks = hooks or {}
        self.join = join
        self.release = release or {}
        self.calls = []
        self.events = []
        self.active = 0
        self.peak = 0
        self.cond = threading.Condition()

    def key_of(self, copy_path):
        for name in self.names:
            if mutate_shared.safe_name(name) in copy_path:
                return name
        raise KeyError("no entry keys the copy at " + copy_path)

    def __call__(self, suite, variable, copy_path, config_dir, only=None):
        key = self.key_of(copy_path)
        tree = tree_text(copy_path)
        with self.cond:
            self.calls.append({"key": key, "only": only, "tree": tree, "mutant": self.names[key] is not None})
            self.active += 1
            self.peak = max(self.peak, self.active)
            self.cond.notify_all()
            if self.join:
                self.cond.wait_for(lambda: self.active >= 2, timeout=JOIN_WAIT)
        try:
            if key in self.hooks:
                return self.hooks[key]()
            if self.names[key] is None:
                return pass_result(*self.required) if self.control_passes else fail_result(*self.required)
            return fail_result(self.names[key])
        finally:
            with self.cond:
                self.active -= 1
                self.events.append(key)
                self.cond.notify_all()
            if key in self.release:
                self.release[key].set()


class CleanLayoutControlTests(unittest.TestCase):
    """A mutant's FAIL lines prove a kill only when the same layout, unmutated, passes the suite. Without
    that control, a layout that crashes reads as a kill. Each target gets one control run, filtered to one
    required case fragment of its own mutations, on the unmutated layout. A red control reads its mutants UNKNOWN, naming "clean layout", never KILLED.
    The control runs inside the MUTATE_JOBS cap, never holds a job slot the other targets need, and a
    control that raises reads its own mutants UNKNOWN instead of crashing the run."""

    def setUp(self):
        self.run = _test_temp.run_folder()
        self.addCleanup(shutil.rmtree, self.run, True)

    def guard_entries(self, *prefixes):
        """The real guard entry whose label starts with each prefix, in the order given."""
        return [next(e for e in mutate_guard.MUTATIONS if mutate_guard.mutation_parts(e)[0].startswith(prefix))
                for prefix in prefixes]

    def run_main(self, entries, suite, jobs=None):
        """Run mutate_guard.main() over `entries` alone, with `suite` as run_suite. Return (exit code, stdout lines),
        or raise what main raised. `jobs` sets MUTATE_JOBS for the run."""
        code, lines, error = self.run_main_outcome(entries, suite, jobs)
        if error is not None:
            raise error
        return code, lines

    def run_main_outcome(self, entries, suite, jobs=None, limit=None):
        """As run_main, but return what main raised, with the lines it printed before, as (exit code or None,
        stdout lines, exception or None). main runs on its own thread, so a run that does not return reads as a
        TimeoutError here, not as a hang. `limit` is that stall bound in seconds, RUN_LIMIT by default. main's work
        folder is made under this test's run folder, not the system temp dir."""
        limit = RUN_LIMIT if limit is None else limit
        out = io.StringIO()
        real_mkdtemp = tempfile.mkdtemp
        outcome = {}

        def mkdtemp_in_run(suffix=None, prefix=None, dir=None):
            return real_mkdtemp(suffix=suffix, prefix=prefix, dir=self.run)

        def call_main():
            try:
                outcome["code"] = mutate_guard.main()
            except Exception as caught:  # a crash is what the caller asserts on, not a test error
                outcome["error"] = caught

        env = {} if jobs is None else {"MUTATE_JOBS": str(jobs)}
        with mock.patch.dict(os.environ, env), \
                mock.patch.object(mutate_guard, "MUTATIONS", entries), \
                mock.patch.object(mutate_guard, "run_suite", side_effect=suite), \
                mock.patch.object(tempfile, "mkdtemp", side_effect=mkdtemp_in_run), \
                contextlib.redirect_stdout(out):
            runner = threading.Thread(target=call_main, daemon=True)
            runner.start()
            runner.join(limit)
        error = outcome.get("error")
        if runner.is_alive():
            error = TimeoutError("main did not return within %s s: the run stalled or deadlocked" % limit)
        return outcome.get("code"), out.getvalue().splitlines(), error

    def test_a_red_clean_layout_reads_unknown_not_killed(self):
        entries = self.guard_entries("role-model: Explore loses its audit exemption")
        label = mutate_guard.mutation_parts(entries[0])[0]
        code, lines = self.run_main(entries, _FakeSuite(entries, control_passes=False))
        self.assertFalse([line for line in lines if line.startswith("KILLED")],
                         "a red clean layout still reads the mutant as KILLED: %r" % lines)
        self.assertTrue([line for line in lines
                         if line.startswith("UNKNOWN") and label in line and "clean layout" in line],
                        "no UNKNOWN line names the mutant and 'clean layout': %r" % lines)
        self.assertEqual(code, 1, "a red clean layout must exit 1, not %r" % code)

    def test_a_green_clean_layout_keeps_the_kill(self):
        entries = self.guard_entries("role-model: Explore loses its audit exemption")
        label = mutate_guard.mutation_parts(entries[0])[0]
        code, lines = self.run_main(entries, _FakeSuite(entries, control_passes=True))
        self.assertTrue([line for line in lines if line.startswith("KILLED") and label in line],
                        "a green clean layout lost the kill of the mutant: %r" % lines)
        self.assertFalse([line for line in lines if line.startswith("UNKNOWN")],
                         "a green clean layout still reads a mutant UNKNOWN: %r" % lines)
        self.assertEqual(code, 0, "a green clean layout with every mutant killed must exit 0, not %r" % code)

    def test_the_control_runs_once_per_target_unmutated(self):
        """One control per target, on the unmutated layout. A control is any call that is not a mutant, whatever
        `only` it asked for, so the count holds whether or not the control runs a filtered subset."""
        entries = self.guard_entries("work-tree: the tree option goes unread",
                                     "pointer-head: the git directory option goes unread")
        suite = _FakeSuite(entries, control_passes=True)
        _code, lines = self.run_main(entries, suite)
        controls = [call for call in suite.calls if not call["mutant"]]
        self.assertEqual(len(controls), 1,
                         "the target runs %d clean-layout controls, want one: %r" % (len(controls), lines))
        tree = controls[0]["tree"]
        for entry in entries:
            label, old, new = mutate_guard.mutation_parts(entry)[:3]
            self.assertIn(old, tree, "the control's tree is not the unmutated guard for: " + label)
            self.assertNotIn(new, tree, "the control's tree holds the mutated text of: " + label)

    def test_controls_count_inside_the_job_cap(self):
        entries = self.guard_entries("work-tree: the tree option goes unread")
        label = mutate_guard.mutation_parts(entries[0])[0]
        control = mutate_guard.control_name("guard")
        suite = _FakeSuite(entries, control_passes=True, join=True)
        _code, lines = self.run_main(entries, suite, jobs=1)
        keys = [call["key"] for call in suite.calls]
        self.assertTrue(control in keys and label in keys,
                        "the run must make a control call and a mutant call, or the cap is not tested: %r" % keys)
        self.assertEqual(suite.peak, 1,
                         "%d suites ran at once with MUTATE_JOBS=1: the clean-layout control sits outside the "
                         "job cap: %r" % (suite.peak, lines))

    def test_a_slow_control_does_not_stall_the_other_targets_mutants(self):
        entries = self.guard_entries("watch: never restore, only report",
                                     "watch: restore in silence",
                                     "work-tree: the tree option goes unread")
        slow = mutate_guard.control_name("watch")
        other = mutate_guard.mutation_parts(entries[2])[0]
        released = threading.Event()

        def slow_control():
            released.wait(RELEASE_WAIT)  # bounded, and the case reads only the order the calls end in
            return pass_result()

        suite = _FakeSuite(entries, control_passes=True, hooks={slow: slow_control}, release={other: released})
        self.run_main(entries, suite, jobs=2)
        self.assertIn(other, suite.events, "the other target's mutant never ended: %r" % suite.events)
        self.assertLess(suite.events.index(other), suite.events.index(slow),
                        "the other target's mutant ended after the slow control: a control that holds a job "
                        "slot stalls the mutants queued behind it. Call ends in order: %r" % suite.events)

    def test_a_raising_control_reads_unknown_for_its_target(self):
        entries = self.guard_entries("work-tree: the tree option goes unread",
                                     "pointer-head: the git directory option goes unread",
                                     "watch: never restore, only report")
        guard_labels = [mutate_guard.mutation_parts(entry)[0] for entry in entries[:2]]
        watch_label = mutate_guard.mutation_parts(entries[2])[0]

        def crash():
            raise RuntimeError("the clean layout suite crashed")

        suite = _FakeSuite(entries, control_passes=True, hooks={mutate_guard.control_name("guard"): crash})
        code, lines, error = self.run_main_outcome(entries, suite, jobs=2)
        self.assertIsNone(error, "main raised %r: a control that raises ends the whole run, where its mutants "
                                 "should read UNKNOWN" % (error,))
        for label in guard_labels:
            self.assertTrue([line for line in lines
                             if line.startswith("UNKNOWN") and label in line and "clean layout" in line],
                            "no UNKNOWN line names this mutant of the raising target, with 'clean layout': %r"
                            % lines)
        self.assertTrue([line for line in lines if line.startswith("KILLED") and watch_label in line],
                        "the other target's mutant does not read KILLED: %r" % lines)
        self.assertEqual(code, 1, "a run with an UNKNOWN mutant must exit 1, not %r" % code)

    CONTROLLED = "mutant of a guard target"  # the label the run_mutants cases below read UNKNOWN or KILLED

    def run_one_mutant_under_control(self, control_result):
        """Run run_mutants over one mutant whose key is "guard", and whose control returns `control_result` as
        run_suite does. Return (exit code, stdout lines)."""
        def run_one(entry):
            return entry, 1, RED_RIGHT, REQUIRED, None
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = mutate_shared.run_mutants([self.CONTROLLED], run_one,
                                             controls={"guard": lambda: control_result},
                                             control_of=lambda entry: "guard")
        return code, out.getvalue().splitlines()

    def test_run_mutants_reads_a_control_that_exits_zero_with_no_ran_line_as_red(self):
        """The signature these cases pin: a control is `controls[key]()`, which returns run_suite's
        (code, red, ran, seen), as it does now. run_mutants reads `ran` (today it drops it). Exit 0 with an
        empty `ran` is the crash signature: the suite ran no case, so the mutant reads UNKNOWN, never KILLED."""
        _code, lines = self.run_one_mutant_under_control((0, [], [], []))
        self.assertTrue([line for line in lines if line.startswith("UNKNOWN") and self.CONTROLLED in line],
                        "a control that exits 0 and ran no case left its mutant unjudged: no UNKNOWN line: %r"
                        % lines)

    def test_run_mutants_keeps_the_kill_when_the_control_exits_zero_with_one_ran_line(self):
        """The green control beside the red case above: the same exit 0, with one `ran` line. It reads
        KILLED, and no UNKNOWN."""
        ran = ["PASS  allow (want allow) [Bash] " + REQUIRED]
        _code, lines = self.run_one_mutant_under_control((0, [], ran, []))
        self.assertTrue([line for line in lines if line.startswith("KILLED") and self.CONTROLLED in line],
                        "a green control that ran one case lost the kill: %r" % lines)
        self.assertFalse([line for line in lines if line.startswith("UNKNOWN")],
                         "a green control that ran one case reads its mutant UNKNOWN: %r" % lines)

    def test_a_control_that_exits_zero_with_no_ran_line_reads_every_mutant_of_its_target_unknown(self):
        """Through main: two guard mutants share one clean-layout control. Its exit 0 with no ran line reads
        both UNKNOWN, with 'clean layout' named, and neither KILLED."""
        entries = self.guard_entries("work-tree: the tree option goes unread",
                                     "pointer-head: the git directory option goes unread")
        suite = _FakeSuite(entries, control_passes=True,
                           hooks={mutate_guard.control_name("guard"): lambda: (0, [], [], [])})
        _code, lines = self.run_main(entries, suite, jobs=2)
        for entry in entries:
            label = mutate_guard.mutation_parts(entry)[0]
            self.assertTrue([line for line in lines
                             if line.startswith("UNKNOWN") and label in line and "clean layout" in line],
                            "a control that ran no case left this mutant of its target unjudged: no UNKNOWN "
                            "line with 'clean layout': %r" % lines)

    def test_run_control_asks_its_suite_for_a_required_fragment_of_its_own_target(self):
        """The clean-layout control proves only that the unmutated layout does not crash, so it runs a filtered
        subset: `only`, the MUTATE_ONLY it hands run_suite, is one required case fragment from that target's own
        mutation entries (`mutation_parts`), never None (the full suite). run_suite and lay_out are stubbed."""
        asked = []

        def record(suite, variable, copy_path, config_dir, only=None):
            asked.append(only)
            return pass_result()

        def laid_out(sources, work, target, name, old, new):
            return os.path.join(self.run, mutate_shared.safe_name(name))

        bad = []
        for target in sorted({mutate_guard.mutation_parts(e)[3] for e in mutate_guard.MUTATIONS}):
            fragments = [mutate_guard.mutation_parts(e)[4] for e in mutate_guard.MUTATIONS
                         if mutate_guard.mutation_parts(e)[3] == target]
            self.assertTrue(fragments, "no mutation entry names target %s" % target)
            del asked[:]
            with mock.patch.object(mutate_guard, "lay_out", side_effect=laid_out), \
                    mock.patch.object(mutate_guard, "run_suite", side_effect=record):
                mutate_guard.run_control({}, self.run, target)
            self.assertTrue(asked, "run_control made no suite call for target %s" % target)
            bad += [(target, only) for only in asked
                    if not only or not any(only in required for required in fragments)]
        self.assertEqual(bad, [], "a clean-layout control asks its suite for no required case fragment of its "
                                  "own target, as (target, only): %r" % bad)

    def test_a_hung_mutant_reads_crashed_and_the_run_scores_the_mutant_after_it(self):
        """Through main, with the real run_suite. The first mutant's suite hangs past SUITE_TIMEOUT, the second's
        prints its FAIL line. The hung one reads UNKNOWN as crashed, the other reads KILLED, and the run exits 1.
        The scope (main returns, the control reads green) is asserted before the subject (each mutant's line)."""
        hung, failing = self.guard_entries("role-model: Explore loses its audit exemption",
                                           "role-model: the audit marker is read off any line")
        hung_label = mutate_guard.mutation_parts(hung)[0]
        failing_label, _old, _new, _target, failing_required, _only_on = mutate_guard.mutation_parts(failing)
        _path, _suite, variable, stem = mutate_guard.TARGETS["guard"]
        write_files(self.run, {"hung_or_failing_suite.py": (
            "import os, sys, time\n"
            "path = os.environ[%r]\n"
            "if %r in path:\n"
            "    time.sleep(%d)\n"
            "    sys.exit(0)\n"
            "if %r in path:\n"
            "    print(%r)\n"
            "    sys.exit(1)\n"
            "print('PASS  control')\n"
        ) % (variable, mutate_shared.safe_name(hung_label), HANG_SECONDS,
             mutate_shared.safe_name(failing_label), "FAIL  allow (want deny) [Bash] " + failing_required)})
        suite = os.path.join(self.run, "hung_or_failing_suite.py")
        with mock.patch.dict(os.environ), \
                mock.patch.dict(mutate_guard.TARGETS, {"guard": (mutate_guard.TARGETS["guard"][0], suite, variable, stem)}), \
                mock.patch.object(mutate_guard, "SUITE_TIMEOUT", 4, create=True):
            for name in ("MUTATE_FULL", "MUTATE_ONLY", "MUTATE_SHARD"):
                os.environ.pop(name, None)
            # The stall bound covers two hung runs: the old code runs a hung suite again for its stage-2 fallback.
            code, lines, error = self.run_main_outcome([hung, failing], mutate_guard.run_suite, jobs=1,
                                                       limit=2 * HANG_SECONDS + 40)
        self.assertIsNone(error, "main raised %r before it scored the mutant after the hung one" % (error,))
        self.assertFalse([line for line in lines if "clean layout" in line],
                         "the clean-layout control did not read green, so the run judged nothing: %r" % lines)
        self.assertTrue([line for line in lines
                         if line.startswith("UNKNOWN") and hung_label in line and "crashed" in line],
                        "the hung mutant does not read UNKNOWN as crashed: %r" % lines)
        self.assertTrue([line for line in lines if line.startswith("KILLED") and failing_label in line],
                        "the mutant after the hung one does not read KILLED: %r" % lines)
        self.assertEqual(code, 1, "a run with an UNKNOWN mutant must exit 1, not %r" % (code,))


class SuiteTimeoutTests(unittest.TestCase):
    """A suite that outlives SUITE_TIMEOUT is crashed: not a kill, not a survivor (decision
    `mutation-report-scores-suites`). run_suite returns code None with a CRASHED line, and run_mutant asks the suite
    once, not again for the stage-2 fallback. Each patch of SUITE_TIMEOUT uses create=True, so the name missing from
    the code before the fix fails the assert, not an AttributeError."""

    GUARD_PREFIX = "role-model: Explore loses its audit exemption"  # a real guard entry: run_mutant reads its fields

    def setUp(self):
        self.run = _test_temp.run_folder()
        self.addCleanup(shutil.rmtree, self.run, True)

    def write_suite(self, name, source):
        write_files(self.run, {name: source})
        return os.path.join(self.run, name)

    def run_suite_with_timeout(self, suite, timeout):
        """run_suite on one suite file, with SUITE_TIMEOUT set to `timeout` seconds. Return run_suite's tuple."""
        with mock.patch.object(mutate_guard, "SUITE_TIMEOUT", timeout, create=True):
            return mutate_guard.run_suite(suite, "GUARD_UNDER_TEST", os.path.join(self.run, "copy.py"), self.run)

    def run_mutant_with(self, suite_answer):
        """run_mutant on one real guard entry, its copy laid out as a stub path, and run_suite answering
        `suite_answer` on every call. Return the `only` of each suite run, in order."""
        entry = next(e for e in mutate_guard.MUTATIONS
                     if mutate_guard.mutation_parts(e)[0].startswith(self.GUARD_PREFIX))
        asked = []

        def answer(suite, variable, copy_path, config_dir, only=None):
            asked.append(only)
            return suite_answer

        with mock.patch.dict(os.environ), \
                mock.patch.object(mutate_guard, "lay_out", return_value=os.path.join(self.run, "copy.py")), \
                mock.patch.object(mutate_guard, "run_suite", side_effect=answer):
            for name in ("MUTATE_FULL", "MUTATE_ONLY", "MUTATE_SHARD"):
                os.environ.pop(name, None)
            mutate_guard.run_mutant({}, self.run, entry)
        return asked

    def test_run_suite_returns_crashed_when_the_suite_outlives_its_timeout(self):
        suite = self.write_suite("hung_suite.py", "import time\ntime.sleep(%d)\n" % HANG_SECONDS)
        try:
            code, _red, _ran, errors = self.run_suite_with_timeout(suite, 1)
        except subprocess.TimeoutExpired:
            self.fail("TimeoutExpired escaped run_suite: one hung suite would end the whole run")
        self.assertIsNone(code, "run_suite returned exit %r for a suite that outlived its timeout, not None" % (code,))
        self.assertTrue([line for line in errors if line.startswith("CRASHED") and "timed out" in line],
                        "run_suite's fourth element holds no CRASHED timed-out line: %r" % (errors,))

    def test_run_suite_keeps_a_suite_that_finishes_inside_its_timeout(self):
        """The green control beside the case above: a suite that ends in time keeps its own exit and FAIL lines."""
        fail_line = "FAIL  allow (want deny) [Bash] case: the rule under test"
        suite = self.write_suite("red_suite.py", "print(%r)\nraise SystemExit(1)\n" % fail_line)
        code, red, _ran, _errors = self.run_suite_with_timeout(suite, 60)
        self.assertEqual(code, 1, "a suite that finished inside its timeout returned exit %r, not its own 1" % (code,))
        self.assertEqual(red, [fail_line], "a suite that finished inside its timeout lost its FAIL line: %r" % (red,))

    def test_a_timed_out_suite_runs_once_not_again_for_the_stage_two_fallback(self):
        asked = self.run_mutant_with((None, [], [], ["CRASHED: suite timed out after 1s"]))
        self.assertEqual(len(asked), 1, "a timed-out suite ran %d times, not once: the stage-2 fallback re-ran it: %r"
                         % (len(asked), asked))

    def test_a_suite_that_ran_no_case_still_gets_the_full_suite_fallback(self):
        """The green control beside the case above: no timeout, so stage 2 still runs the full suite."""
        asked = self.run_mutant_with((0, [], [], []))
        self.assertEqual(len(asked), 2, "a suite that ran no case was asked %d times, not 2: the full-suite fallback "
                                        "is gone: %r" % (len(asked), asked))


def scaffold_sources(**extra):
    """The `sources` a scaffold is built from: a short text for each file, and a case replaces one
    by keyword (`test_sweep=` is the suite the scaffold runs)."""
    sources = {
        "sweep": "SWEEP\n", "guard": "GUARD\n", "session_end_sweep": "END\n",
        "agent_end_reap": "REAP\n", "test_sweep": "", "test_session_end_sweep": "",
        "settings_json": "{}\n",
    }
    sources.update(extra)
    return sources


class BuildScaffoldSiblingTests(unittest.TestCase):
    """`build_scaffold` writes every guard module in `sources` (a key `guard_<name>` is
    hooks/guard_<name>.py) into <scaffold>/hooks, and a mutant aimed at one lands in that file.
    It also lays down <scaffold>/lint with every lint/*.py module that is not a test, and the
    lint/layout.json the guard reads."""

    def setUp(self):
        self.run = _test_temp.run_folder()
        self.scaffold = os.path.join(self.run, "scaffold")
        self.addCleanup(shutil.rmtree, self.run, True)

    def sources(self, **extra):
        return scaffold_sources(**extra)

    def test_sibling_guard_module_is_copied_into_the_scaffold_unmutated(self):
        mutate_sweep.build_scaffold(self.scaffold, self.sources(guard_x="SIBLING\n"),
                                    "sweep", "MUTATED SWEEP\n")
        self.assertEqual(read_file(os.path.join(self.scaffold, "hooks"), "guard_x.py"),
                         "SIBLING\n")
        self.assertEqual(read_file(os.path.join(self.scaffold, "hooks"), "guard.py"), "GUARD\n")

    def test_mutant_aimed_at_a_sibling_lands_in_that_sibling(self):
        mutate_sweep.build_scaffold(self.scaffold, self.sources(guard_x="SIBLING\n"),
                                    "guard_x", "MUTATED SIBLING\n")
        hooks = os.path.join(self.scaffold, "hooks")
        self.assertEqual(read_file(hooks, "guard_x.py"), "MUTATED SIBLING\n")
        self.assertEqual(read_file(hooks, "guard.py"), "GUARD\n")

    def test_scaffold_carries_shared_names_so_the_copied_guard_imports(self):
        mutate_sweep.build_scaffold(self.scaffold, self.sources(), "sweep", "X")
        self.assertTrue(os.path.exists(os.path.join(self.scaffold, "hooks", "shared_names.py")))

    def test_scaffold_carries_git_reads_so_the_copied_sweep_and_guard_import(self):
        # sweep.py and guard_core.py import it. A scaffold without it fails every mutant on the
        # import, so every mutant reads killed for a cause that is not the mutation.
        mutate_sweep.build_scaffold(self.scaffold, self.sources(), "sweep", "X")
        self.assertTrue(os.path.exists(os.path.join(self.scaffold, "hooks", "git_reads.py")))

    def test_scaffold_lint_holds_every_lint_module_and_layout_json(self):
        # A suite and the copied guard load lint modules by name, from any import form. A module the
        # scaffold lacks fails the run on import, so every mutant reads survived for a cause that is
        # not the mutation. The guard also reads lint/layout.json from the scaffold.
        lint_dir = os.path.join(mutate_sweep.REPO_ROOT, "lint")
        expected = {name for name in os.listdir(lint_dir)
                    if name.endswith(".py") and not name.startswith("test_")}
        self.assertIn("layout.py", expected,
                      "the real lint/ holds no layout.py, saw %r" % (sorted(expected),))
        mutate_sweep.build_scaffold(self.scaffold, self.sources(), "sweep", "X")
        scaffold_lint = os.path.join(self.scaffold, "lint")
        self.assertTrue(os.path.isfile(os.path.join(scaffold_lint, "_test_git.py")),
                        "the scaffold lacks its control, lint/_test_git.py")
        missing = sorted(expected - set(os.listdir(scaffold_lint)))
        self.assertEqual(missing, [], "scaffold lint/ lacks module(s): " + ", ".join(missing))
        self.assertTrue(os.path.isfile(os.path.join(scaffold_lint, "layout.json")),
                        "scaffold lint/ lacks lint/layout.json, the data file the guard reads")


class FakeRun:
    """A stand-in for one mutant's suite runner. `answers` maps each `only` it may get (REQUIRED,
    or None for the full suite) to the (code, red, ran) that run returns. Every `only` it gets is
    appended to `calls`, in order, so a case can prove which stages ran."""

    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def __call__(self, only):
        self.calls.append(only)
        return self.answers[only]


def staged(answers, full=False):
    """Run `staged_suite` on a FakeRun. MUTATE_FULL is set only when `full`, and cleared otherwise,
    so a developer's own setting cannot change a case. Return the fake with `result` (what
    staged_suite returned) and `error` (what it raised). Both are kept, not raised, so a case checks
    `calls` before it reports an error."""
    fake = FakeRun(answers)
    fake.result = None
    fake.error = None
    with mock.patch.dict(os.environ):
        os.environ.pop("MUTATE_FULL", None)
        if full:
            os.environ["MUTATE_FULL"] = "1"
        try:
            fake.result = mutate_shared.staged_suite(fake, REQUIRED)
        except Exception as error:
            fake.error = error
    return fake


class StagedSuiteTests(unittest.TestCase):
    """`staged_suite(run, required)`: stage 1 runs only the required case. A stage-1 run whose `ran`
    names the case gives the verdict, and the full suite never runs. Only a run that names no line
    falls back to the full suite, once. MUTATE_FULL=1 runs the full suite alone."""

    def assertStaged(self, fake, calls, result):
        """The one assertion step for every case: the calls first, so a wrong fallback shows as a
        wrong call list, then the error, then the pair staged_suite returned."""
        self.assertEqual(fake.calls, calls)
        self.assertIsNone(fake.error, "staged_suite raised %r" % (fake.error,))
        self.assertEqual(fake.result, result)

    def test_passed_in_stage_one_is_the_verdict_and_never_falls_back(self):
        fake = staged({REQUIRED: (0, [], [PASS_RIGHT])})
        self.assertStaged(fake, [REQUIRED], (0, []))

    def test_red_without_the_name_in_stage_one_is_the_verdict_and_never_falls_back(self):
        fake = staged({REQUIRED: (1, RED_WRONG, [PASS_RIGHT] + RED_WRONG)})
        self.assertStaged(fake, [REQUIRED], (1, RED_WRONG))

    def test_named_kill_in_stage_one_is_the_verdict_and_never_falls_back(self):
        fake = staged({REQUIRED: (1, RED_RIGHT, RED_RIGHT)})
        self.assertStaged(fake, [REQUIRED], (1, RED_RIGHT))

    def test_zero_cases_selected_falls_back_to_the_full_suite_once(self):
        fake = staged({REQUIRED: (0, [], []), None: (1, FULL_RED, FULL_RED)})
        self.assertStaged(fake, [REQUIRED, None], (1, FULL_RED))

    def test_crash_before_the_case_falls_back_to_the_full_suite_once(self):
        fake = staged({REQUIRED: (1, ["ImportError: no module named guard_x"], []),
                       None: (1, FULL_RED, FULL_RED)})
        self.assertStaged(fake, [REQUIRED, None], (1, FULL_RED))

    def test_mutate_full_runs_only_the_full_suite(self):
        fake = staged({None: (1, FULL_RED, FULL_RED)}, full=True)
        self.assertStaged(fake, [None], (1, FULL_RED))


# A required case that ERRORS (a throw, not an assert) prints no FAIL line for its own name, so the
# verdict reads WRONG CAUSE. The report must still name what it saw: the ERROR block and the final
# exception. The incident read `saw: FAILED (errors=1)` and hid the TimeoutExpired.
ERROR_CASE = "test_required_fixture"
ERROR_SUITE = textwrap.dedent("""\
    import subprocess
    import unittest


    class Fixture(unittest.TestCase):
        def test_required_fixture(self):
            raise subprocess.TimeoutExpired("sleep 9", 5)


    if __name__ == "__main__":
        unittest.main(verbosity=2)
""")
# A red with FAIL lines only. No case the mutation names exists here, so the full suite runs.
FAIL_SUITE = textwrap.dedent("""\
    import unittest


    class Fixture(unittest.TestCase):
        def test_other_fixture(self):
            self.assertEqual(1, 2)


    if __name__ == "__main__":
        unittest.main(verbosity=2)
""")
LABEL = "fixture: a no-op mutant, so the suite is the only thing under test"


def verdict_seen(code, red, seen):
    """report_verdict with REQUIRED as the required case, and `seen` as its diagnostics."""
    with contextlib.redirect_stdout(io.StringIO()):
        return mutate_shared.report_verdict("mutant", code, red, REQUIRED, seen=seen)


class SeenNeverChangesTheVerdictTests(unittest.TestCase):
    """Pins that `seen` is diagnostics only: the verdict reads `red` alone, so an ERROR
    block that names the required case must not turn a WRONG CAUSE into a kill."""

    def test_an_error_in_the_required_case_with_no_fail_line_is_wrong_cause(self):
        seen = ["ERROR: " + REQUIRED + " (mod.Class.test_x)", "subprocess.TimeoutExpired: sleep 9"]
        self.assertEqual(verdict_seen(1, ["FAILED (errors=1)"], seen), "wrong_cause")

    def test_seen_lines_naming_the_required_case_never_make_a_kill(self):
        seen = ["ERROR: " + REQUIRED + " (mod.Class.test_x)"]
        self.assertEqual(verdict_seen(1, RED_WRONG, seen), "wrong_cause")


class GuardDriverErrorLinesTests(unittest.TestCase):
    """The two drivers return their ERROR lines as `seen`. The guard driver reads a suite's stdout only, and
    unittest writes its ERROR blocks to stderr, so the guard driver's `seen` misses them. The sweep driver
    reads both streams, and is the control."""

    def setUp(self):
        self.run = _test_temp.run_folder()
        self.addCleanup(shutil.rmtree, self.run, True)
        self.config = os.path.join(self.run, "cfg")
        os.makedirs(self.config)
        write_files(self.run, {"test_fixture_suite.py": ERROR_SUITE})
        self.suite = os.path.join(self.run, "test_fixture_suite.py")

    def assertErrorBlockSeen(self, seen, driver):
        self.assertTrue(any(line.startswith("ERROR: " + ERROR_CASE + " (") for line in seen),
                        "the %s driver's seen holds no ERROR line for its failing case: %r" % (driver, seen))

    def test_the_sweep_driver_returns_the_error_block_as_seen(self):
        result = mutate_sweep.run_suite(self.suite, self.config)
        self.assertErrorBlockSeen(result[3], "sweep")

    def test_the_guard_driver_returns_the_error_block_as_seen(self):
        result = mutate_guard.run_suite(self.suite, "GUARD_UNDER_TEST",
                                        os.path.join(self.run, "copy.py"), self.config)
        self.assertErrorBlockSeen(result[3], "guard")


class ErrorBlockReportTests(unittest.TestCase):
    """A mutant's suite runs through `run_mutants`, the path every mutation test takes, so each case reads
    the report a reader sees. An ERROR in the required case is WRONG CAUSE, and the report names the ERROR
    block and the final exception under `saw:`. A FAIL-only red prints no ERROR line."""

    def setUp(self):
        self.run = _test_temp.run_folder()
        self.addCleanup(shutil.rmtree, self.run, True)
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("MUTATE_FULL", None)  # a developer's setting must not change which suite runs

    def run_fixture(self, suite):
        sources = scaffold_sources(test_sweep=suite)
        entry = (LABEL, "sweep", "SWEEP", "SWEEP", ERROR_CASE)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = mutate_shared.run_mutants(
                [entry], lambda item: mutate_sweep.run_mutant(sources, self.run, 0, item))
        return code, out.getvalue().splitlines()

    def saw(self, lines):
        return [line.strip() for line in lines if line.strip().startswith("saw: ")]

    def assertWrongCause(self, code, lines):
        """The scope, checked before any saw: line: the run failed and the mutant reads WRONG CAUSE."""
        self.assertEqual(code, 1, "the run must fail: the required case did not kill the mutant")
        self.assertTrue(any(line.startswith("WRONG CAUSE ") and LABEL in line for line in lines),
                        "the mutant must read WRONG CAUSE, not killed; the report said: %r" % lines)

    def test_an_error_in_the_required_case_reads_wrong_cause(self):
        code, lines = self.run_fixture(ERROR_SUITE)
        self.assertWrongCause(code, lines)

    def test_the_report_names_the_error_block_under_saw(self):
        code, lines = self.run_fixture(ERROR_SUITE)
        self.assertWrongCause(code, lines)
        self.assertTrue(any(line.startswith("saw: ERROR: " + ERROR_CASE + " (") for line in self.saw(lines)),
                        "the WRONG CAUSE report must print the ERROR block under saw:, saw %r" % self.saw(lines))

    def test_the_report_prints_the_final_exception_line_under_saw(self):
        code, lines = self.run_fixture(ERROR_SUITE)
        self.assertWrongCause(code, lines)
        self.assertTrue(any(line.startswith("saw: subprocess.TimeoutExpired: ") for line in self.saw(lines)),
                        "the WRONG CAUSE report must print the final exception under saw:, saw %r"
                        % self.saw(lines))

    def test_a_fail_only_red_prints_no_error_line(self):
        code, lines = self.run_fixture(FAIL_SUITE)
        self.assertWrongCause(code, lines)
        self.assertTrue(any(line.startswith("saw: FAIL: test_other_fixture (") for line in self.saw(lines)),
                        "a FAIL line must still print under saw:, saw %r" % self.saw(lines))
        self.assertFalse(any(line.startswith("saw: ERROR:") for line in self.saw(lines)),
                         "a FAIL-only red printed an ERROR line under saw:, saw %r" % self.saw(lines))


# The family suites of hooks/test_guard.py: a suite named `path::family` is the file `path`, run with GUARD_FAMILY=family.
# FAMILY_SUITE prints FAIL only under family x. WIDGET_FAMILY_SUITE imports widget outside that branch, so a broken copy of
# widget.py fails it at the import, which marks the file as loaded.
FAMILY_SUITE = ("import os\nimport sys\n\n"
                "if os.environ.get('GUARD_FAMILY') == 'x':\n"
                "    print('FAIL: GUARD_FAMILY is x')\n"
                "    sys.exit(1)\n"
                "print('ok')\n")
WIDGET_FAMILY_SUITE = ("import os\nimport sys\n\n"
                       "sys.path.insert(0, os.getcwd())\n"
                       "from widget import value\n\n"
                       "if os.environ.get('GUARD_FAMILY') == 'x' and value() != 1:\n"
                       "    print('FAIL: value() is not 1 under family x')\n"
                       "    sys.exit(1)\n"
                       "print('ok')\n")


def make_files(root, files):
    """write_files, with each file's folder made first."""
    for rel in files:
        os.makedirs(os.path.dirname(os.path.join(root, rel)), exist_ok=True)
    write_files(root, files)


class FamilySuiteEngineTests(unittest.TestCase):
    """A suite named `path::family` is the file `path`, run with GUARD_FAMILY=family in its env. The profile's `tests`
    regex and the isfile check read the part before `::`. A plain suite runs with GUARD_FAMILY unset. The cases that run a
    family suite are red on the engine without the family split; the plain cases are its green control."""

    def setUp(self):
        self.run = _test_temp.run_folder()
        self.addCleanup(shutil.rmtree, self.run, True)
        self.folder = os.path.join(self.run, "folder")
        make_files(self.folder, {"suites/test_fam.py": FAMILY_SUITE})
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("GUARD_FAMILY", None)

    def test_a_family_suite_runs_with_guard_family_set_in_its_env(self):
        kind, _seconds = mutate_shared.run_suite_file(self.folder, "suites/test_fam.py::x", 60)
        self.assertEqual(kind, "assert",
                         "suites/test_fam.py::x runs with GUARD_FAMILY=x, so its FAIL line reads red, got %r" % kind)

    def test_a_plain_suite_runs_with_guard_family_unset(self):
        kind, _seconds = mutate_shared.run_suite_file(self.folder, "suites/test_fam.py", 60)
        self.assertEqual(kind, "pass", "a plain suite sets no GUARD_FAMILY, so the same file reads green, got %r" % kind)

    def test_score_target_reads_a_family_suite_by_its_path_and_kills_under_its_family(self):
        root = os.path.join(self.run, "root")
        make_files(root, {"widget.py": "def value():\n    return 1\n", "suites/test_fam.py": WIDGET_FAMILY_SUITE})
        row = mutate_shared.score_target(root, "widget.py", ["suites/test_fam.py::x"], limit=10, jobs=1)
        self.assertEqual(row["status"], "OK", "a family suite whose file exists is usable: %s" % row["reason"])
        self.assertEqual(row["unusable"], {}, "the file part of a family suite is read, so none is unusable")
        self.assertGreater(row["killers"]["suites/test_fam.py::x"], 0,
                           "the family suite kills mutants under GUARD_FAMILY=x")

    def test_score_target_marks_a_family_suite_whose_file_is_missing_as_missing(self):
        root = os.path.join(self.run, "root")
        make_files(root, {"widget.py": "def value():\n    return 1\n"})
        row = mutate_shared.score_target(root, "widget.py", ["suites/none.py::x"], limit=10, jobs=1)
        self.assertEqual(row["unusable"], {"suites/none.py::x": "missing"},
                         "the file part is checked: suites/none.py is missing")

    def test_select_lists_a_family_line_whose_file_matches_the_tests_regex(self):
        dest = os.path.join(self.run, "dest")
        make_files(dest, {"select.py": "print('suites/test_fam.py::x')\n", "suites/test_fam.py": FAMILY_SUITE})
        profile = {"tests": r"(^|/)test_[^/]*\.py$", "select": [sys.executable, "select.py", "{path}"]}
        names, note = mutate_shared._select_suites(profile, dest, "widget.py", None, 60)
        self.assertEqual(names, ["suites/test_fam.py::x"],
                         "the regex reads the file part of a family line, so it is a suite: %s" % note)

    def test_select_drops_a_family_line_whose_file_is_missing(self):
        dest = os.path.join(self.run, "dest")
        make_files(dest, {"select.py": "print('suites/test_gone.py::x')\n"})
        profile = {"tests": r"(^|/)test_[^/]*\.py$", "select": [sys.executable, "select.py", "{path}"]}
        names, note = mutate_shared._select_suites(profile, dest, "widget.py", None, 60)
        self.assertEqual(names, [], "a family line whose file is missing is no suite: %s" % note)


class LinuxOnlySweepMutationsTests(unittest.TestCase):
    """A sweep mutation whose one proving case is skipped off Linux carries `only_on="linux"`, so
    Windows and macOS count it skipped. Without it the mutation reads survived there and the job
    goes red."""

    PROVEN_ON_LINUX_ONLY = (
        "finish gate: a dead host's live lock frees its tree with no finish proof (ungated verdict)",
        "cut-short restore: a finished dead-host tree is not restored (the finish proof is read as absent)",
    )

    def test_a_mutation_proven_only_by_the_linux_only_suite_is_marked_linux(self):
        by_label = {mutate_sweep.mutation_parts(e)[0]: mutate_sweep.mutation_parts(e)[5]
                    for e in mutate_sweep.MUTATIONS}
        for label in self.PROVEN_ON_LINUX_ONLY:
            with self.subTest(label=label):
                self.assertIn(label, by_label, "the mutation is gone from the list")
                self.assertEqual(by_label[label], "linux")

    def test_linux_runs_only_on_linux_and_posix_still_runs_on_macos(self):
        for platform, linux, posix in (("linux", True, True), ("darwin", False, True), ("win32", False, False)):
            with mock.patch.object(sys, "platform", platform):
                with self.subTest(platform=platform):
                    self.assertEqual(mutate_shared.skip_reason("linux") is None, linux)
                    self.assertEqual(mutate_shared.skip_reason("posix") is None, posix)


if __name__ == "__main__":
    unittest.main()
