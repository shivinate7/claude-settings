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
"""
import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
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


if __name__ == "__main__":
    unittest.main()
