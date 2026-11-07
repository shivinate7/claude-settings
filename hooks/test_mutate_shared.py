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

The fifth part pins the clean-layout control: a target's mutants count as kills only after one full-suite
run of the unmutated layout passes. A red control reads each mutant UNKNOWN, never KILLED. The control
runs inside the MUTATE_JOBS cap, and a control that raises reads its mutants UNKNOWN too.
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


class GuardMutantLayoutTests(unittest.TestCase):
    """A guard mutant runs from <root>/hooks, so its ../lint is <root>/lint. guard.py reads lint/layout.py
    from there (role_model_table, record_branch_of). Without that folder the import fails, the role-model
    table reads as unread, and every role-model arm passes unjudged: a survivor that has no bearing on
    its mutation."""

    def setUp(self):
        self.run = _test_temp.run_folder()
        self.addCleanup(shutil.rmtree, self.run, True)

    def test_copied_guard_imports_the_lint_layout_from_its_own_root(self):
        entry = next(e for e in mutate_guard.MUTATIONS
                     if mutate_guard.mutation_parts(e)[0].startswith("role-model: Explore loses its audit exemption"))
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
        hooks = os.path.dirname(copies[0])
        # -I drops the cwd from sys.path, so a lint/ in the working directory cannot satisfy the import.
        result = subprocess.run(
            [sys.executable, "-I", "-c",
             "import sys; sys.path.insert(0, sys.argv[1]); import guard; guard._layout_module()",
             hooks],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0,
                         "the copied guard cannot import lint/layout.py from its root: " + result.stderr[-300:])


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


GATE_WAIT = 0.5  # a call waits this long for a second call to join it, so overlap shows without a fixed sleep
RELEASE_WAIT = 1.0  # a held control waits this long for the mutant it is held on, so no case hangs
RUN_LIMIT = 4.0  # main must return within this long, or the case reads a stall, not a hang


class _FakeSuite:
    """A stand-in for `mutate_guard.run_suite`, called as (suite, variable, copy_path, config_dir, only).

    A call is keyed by its copy_path, which holds the name its copy was laid out under: a mutant's label,
    or a target's clean-layout control name. The key, not the text of a folder, says which call it is, so a
    watch copy stays apart from the other watch copies that share `work`. A mutant's call FAILs its required
    case. A control (`only` None) is green when `control_passes`, red otherwise.

    `hooks` maps a key to a zero-argument function that runs in place of that call's answer, so a case can
    hold a call or raise from it. `gate` holds each call up to GATE_WAIT for a second call to join it.
    `release` maps a key to an Event that is set once that call has ended and been logged. `active` and
    `peak` count the calls in flight, `events` lists each call's end by key in order, and `calls` records
    each call's key, `only`, `tree` and `mutant`. The counts sit under one lock."""

    def __init__(self, entries, control_passes, hooks=None, gate=False, release=None):
        self.names = {}  # key -> required case, or None for a target's clean-layout control
        self.required = []
        for entry in entries:
            label, _old, _new, target, required, _only_on = mutate_guard.mutation_parts(entry)
            self.names[label] = required
            self.names[mutate_guard.control_name(target)] = None
            self.required.append(required)
        self.control_passes = control_passes
        self.hooks = hooks or {}
        self.gate = gate
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
            if self.gate:
                self.cond.wait_for(lambda: self.active >= 2, timeout=GATE_WAIT)
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
    that control, a layout that crashes reads as a kill. Each target gets one full-suite control run on
    the unmutated layout. A red control reads its mutants UNKNOWN, naming "clean layout", never KILLED.
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

    def run_main_outcome(self, entries, suite, jobs=None):
        """As run_main, but return what main raised, with the lines it printed before, as (exit code or None,
        stdout lines, exception or None). main runs on its own thread, so a run that does not return reads as a
        TimeoutError here, not as a hang. main's work folder is made under this test's run folder, not the system
        temp dir."""
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
            runner.join(RUN_LIMIT)
        error = outcome.get("error")
        if runner.is_alive():
            error = TimeoutError("main did not return within %s s: the run stalled or deadlocked" % RUN_LIMIT)
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
        entries = self.guard_entries("work-tree: the tree option goes unread",
                                     "pointer-head: the git directory option goes unread")
        suite = _FakeSuite(entries, control_passes=True)
        _code, lines = self.run_main(entries, suite)
        controls = [call for call in suite.calls if not call["mutant"] and call["only"] is None]
        self.assertEqual(len(controls), 1,
                         "the target runs %d full-suite clean-layout controls, want one: %r" % (len(controls), lines))
        tree = controls[0]["tree"]
        for entry in entries:
            label, old, new = mutate_guard.mutation_parts(entry)[:3]
            self.assertIn(old, tree, "the control's tree is not the unmutated guard for: " + label)
            self.assertNotIn(new, tree, "the control's tree holds the mutated text of: " + label)

    def test_controls_count_inside_the_job_cap(self):
        entries = self.guard_entries("work-tree: the tree option goes unread")
        label = mutate_guard.mutation_parts(entries[0])[0]
        control = mutate_guard.control_name("guard")
        suite = _FakeSuite(entries, control_passes=True, gate=True)
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
    hooks/guard_<name>.py) into <scaffold>/hooks, and a mutant aimed at one lands in that file."""

    def setUp(self):
        self.scaffold = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.scaffold, True)

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
    """Controls, green on the head. `seen` is diagnostics only: the verdict reads `red` alone, so an ERROR
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


if __name__ == "__main__":
    unittest.main()
