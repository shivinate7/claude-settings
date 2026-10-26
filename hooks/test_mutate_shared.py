#!/usr/bin/env python3
"""Cases for hooks/mutate_shared.py's verdict. Standard library only.

    python3 hooks/test_mutate_shared.py

`report_verdict` is the line every mutation harness trusts to say a guard went red on the defect
it guards (CLAUDE.md: trust a guard only once it goes red on the defect). It is tested here with
one known-bad input per wrong verdict: a mutant the suite did not catch must read "survived",
and a red suite that never names the case must read "wrong_cause", never "killed".

The second half pins the guard-family copy: `guard_tree` copies every hooks/guard*.py, shared_names.py
and git_reads.py, and `apply_mutant` lands a find-string in the one copied file that holds it
(zero matches is STALE, two or more is an error), so a guard split into sibling modules, or into
git_reads.py, is still mutated in the right file. `build_scaffold` in janitor/mutate_sweep.py gets the same pin: a sibling is written into the
scaffold's hooks/ folder, and a mutant aimed at a sibling lands there.
"""
import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HOOKS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HOOKS)
sys.path.insert(0, os.path.join(os.path.dirname(HOOKS), "janitor"))
import mutate_shared  # noqa: E402
import mutate_sweep  # noqa: E402

REQUIRED = "case: the rule under test"
RED_RIGHT = ["FAIL  allow (want deny) [Bash] case: the rule under test"]
RED_WRONG = ["FAIL  allow (want deny) [Bash] some other case"]


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
    """The copy a harness runs must import: config_watch.py and guard_core.py need shared_names,
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


class BuildScaffoldSiblingTests(unittest.TestCase):
    """`build_scaffold` writes every guard module in `sources` (a key `guard_<name>` is
    hooks/guard_<name>.py) into <scaffold>/hooks, and a mutant aimed at one lands in that file."""

    def setUp(self):
        self.scaffold = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.scaffold, True)

    def sources(self, **extra):
        sources = {
            "sweep": "SWEEP\n", "guard": "GUARD\n", "session_end_sweep": "END\n",
            "agent_end_reap": "REAP\n", "test_sweep": "", "test_session_end_sweep": "",
            "settings_json": "{}\n",
        }
        sources.update(extra)
        return sources

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


if __name__ == "__main__":
    unittest.main()
