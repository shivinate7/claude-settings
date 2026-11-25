#!/usr/bin/env python3
"""Cases for lint/check_mutant_anchors.py. Standard library only.

    python3 lint/test_check_mutant_anchors.py

findings(mutations, targets, hooks) gives one `FAIL ...` line per mutant whose anchor is stale, ambiguous or aimed at an unknown
target. Each case builds its own guard folder, target file and table in a run folder, so no case reads the real hooks/ tree. The
real table is checked by the census step itself. MUTANT_ANCHORS_UNDER_TEST overrides the module path, for a mutant copy.

The sweep table, MUTATIONS of janitor/mutate_sweep.py, is read through main(). Each sweep case patches that table and the map of its
target files, and empties the guard table, so only the sweep rows of the case are judged.

Each fail case also holds a clean mutant in the same table, and checks that the clean one is absent before it checks the bad line,
so a line that names the wrong mutant cannot pass.
"""
import contextlib
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
sys.path.insert(0, os.path.join(HERE, "..", "janitor"))
import mutate_sweep  # noqa: E402  the sweep MUTATIONS table and SOURCES (target name -> file); each sweep case patches them

MODULE = os.environ.get("MUTANT_ANCHORS_UNDER_TEST") or os.path.join(HERE, "check_mutant_anchors.py")
REQUIRED = "a case name"  # the census reads only the anchor, so the required field is any text
FULL_SIZE = 1000  # about the size of the real mutant table, so the loop runs over a table of that length
RUN_FOLDER = None  # made in setUpModule, so an import leaks no folder

# A guard module holds the anchors that the anchor-quote, comment-opener and line-break cases read. `dup` appears twice on purpose.
GUARD_TEXT = (
    "def decide(x):\n"
    "    return x > 1\n"
    'url = "http://x // y"\n'
    "note = \"don't\"\n"
    'label = "# not a comment"\n'
    'block = """\n'
    "first\n"
    "second\n"
    '"""\n'
    "dup = 0\n"
    "dup = 0\n"
)
GUARD_B_SHARED = "SHARED_RULE = 'sibling'\n"  # a guard module beside guard.py, read by guard-family targets only
WATCH_TEXT = "WATCH_LIMIT = 5\nlabel = 'x'\nother = 'x'\n"  # `= 'x'` occurs twice

# A sweep target file. `suffix = 'a'` occurs twice on purpose; the two lines together occur once.
SWEEP_TEXT = (
    "def unlock(stale):\n"
    "    return not stale\n"
    "suffix = 'a'\n"
    "suffix = 'a'\n"
)
CLEAN_OLD = "return not stale"  # once in SWEEP_TEXT
STALE_OLD = "return never_written()"  # in no sweep target file
DOUBLED_OLD = "suffix = 'a'"  # twice in SWEEP_TEXT
WIDENED_OLD = "suffix = 'a'\nsuffix = 'a'"  # once in SWEEP_TEXT: the form a guard mutant takes to be found once
TABLE_FILE = "janitor/mutate_sweep.py"  # the file a sweep finding names: the table the row sits in
CLEAN_LABEL = "sweep clean: anchor present once"
STALE_LABEL = "sweep stale: anchor removed by a merge"
DOUBLED_LABEL = "sweep doubled: anchor in two places"
WIDENED_LABEL = "sweep widened: anchor spans both lines, present once"
SWAP_A_LABEL = "sweep swap A: fixture-only row"
SWAP_B_LABEL = "sweep swap B: fixture-only row"
UNKNOWN_TARGET = "nosuch"  # a sweep row's target that SOURCES does not hold
UNKNOWN_LABEL = "sweep unknown target: names no source"
CLEAN_THREE_LABEL = "sweep clean three: def line present once"
MALFORMED_SWEEP_LABEL = "sweep malformed: two fields"
UNLABELLED_INDEX = 1  # the 0-based index of the empty row in its sweep table
MALFORMED_GUARD_LABEL = "guard malformed: two fields"
GUARD_TABLE_FILE = "hooks/mutate_guard.py"  # the file a guard finding names: the table the row sits in


def sweep_row(label, old, target="sweep"):
    """One row of a sweep table, in mutate_sweep.mutation_parts' order: (label, target, old, new, required)."""
    return (label, target, old, "", REQUIRED)


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


def load_module(path):
    spec = importlib.util.spec_from_file_location("check_mutant_anchors", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


census = load_module(MODULE)


def mutant(label, old, target="guard"):
    return (label, old, "", target, REQUIRED)


class CensusFindings(unittest.TestCase):
    def setUp(self):
        self.tree = tempfile.mkdtemp(prefix="mac_", dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, self.tree, True)
        self.hooks = os.path.join(self.tree, "hooks")
        self.guard = self.put("hooks/guard.py", GUARD_TEXT)
        self.watch = self.put("hooks/config_watch.py", WATCH_TEXT)
        self.targets = {
            "guard": (self.guard, None, None, None),
            "audit": (self.guard, None, None, None),
            "watch": (self.watch, None, None, None),
            "plain": (self.guard, None, None, None),  # a non-guard-family target: a guard row named here reads this file alone
        }
        # The guard table is empty and the sweep table holds no row unless a case sets one, so no case reads the real tables.
        self.sweep_file = self.put("janitor/sweep.py", SWEEP_TEXT)
        for patcher in (mock.patch.object(census.mutate_guard, "MUTATIONS", []),
                        mock.patch.object(mutate_sweep, "MUTATIONS", []),
                        mock.patch.object(mutate_sweep, "SOURCES", dict(mutate_sweep.SOURCES, sweep=self.sweep_file))):
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_main(self, sweep_rows, guard_rows=()):
        """The census's main() with `sweep_rows` as the sweep table and `guard_rows` as the guard table -> (exit code, stdout).
        Guard rows are judged against this case's own targets, so no row reads the real hooks/ tree. A census that raises fails
        the case by assert, naming the exception, so a crash is never the red."""
        out = io.StringIO()
        with mock.patch.object(mutate_sweep, "MUTATIONS", sweep_rows), \
                mock.patch.object(census.mutate_guard, "MUTATIONS", list(guard_rows)), \
                mock.patch.object(census.mutate_guard, "TARGETS", self.targets), \
                contextlib.redirect_stdout(out):
            try:
                code = census.main()
            except Exception as error:
                self.fail("census raised %s (%s) instead of printing its FAIL lines" % (type(error).__name__, error))
        return code, out.getvalue()

    def lines_naming(self, out, label):
        return [line for line in out.splitlines() if label in line]

    def put(self, rel, text):
        path = os.path.join(self.tree, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        return path

    def findings(self, table):
        return census.findings(table, self.targets, self.hooks)

    def test_an_empty_table_has_no_findings(self):
        self.assertEqual(self.findings([]), [])

    def test_a_full_size_table_of_once_anchored_mutants_has_no_findings(self):
        self.put("hooks/guard.py", GUARD_TEXT + "".join("marker_%d = %d\n" % (i, i) for i in range(FULL_SIZE)))
        table = [mutant("marker %d" % i, "marker_%d = %d\n" % (i, i)) for i in range(FULL_SIZE)]
        self.assertEqual(self.findings(table), [])

    def test_an_anchor_present_once_passes_in_guard_and_watch(self):
        table = [mutant("guard: anchor present once", "return x > 1"),
                 mutant("watch: anchor present once", "WATCH_LIMIT = 5", "watch")]
        self.assertEqual(self.findings(table), [])

    def test_an_anchor_with_comment_openers_quotes_and_a_line_break_is_found_once(self):
        anchors = [
            'url = "http://x // y"',
            "note = \"don't\"",
            'label = "# not a comment"',
            'block = """\nfirst\nsecond\n"""',
        ]
        for old in anchors:
            with self.subTest(anchor=old):
                self.assertEqual(self.findings([mutant("guard: %s" % old, old)]), [])

    def test_a_guard_anchor_gone_fails_naming_the_mutant_and_its_folder(self):
        table = [mutant("guard clean: anchor present once", "return x > 1"),
                 mutant("guard gone: anchor removed by a merge", "return x < 9")]
        lines = self.findings(table)
        self.assertFalse(any("guard clean" in line for line in lines), "a clean mutant is reported: %r" % lines)
        self.assertEqual(len(lines), 1, "want one finding, got %r" % lines)
        self.assertTrue(lines[0].startswith("FAIL stale anchor"), lines[0])
        self.assertIn("guard gone: anchor removed by a merge", lines[0])
        self.assertIn(self.hooks, lines[0])

    def test_a_watch_anchor_gone_fails_naming_the_mutant_and_its_file(self):
        table = [mutant("watch clean: anchor present once", "WATCH_LIMIT = 5", "watch"),
                 mutant("watch gone: anchor removed by a merge", "WATCH_LIMIT = 9", "watch")]
        lines = self.findings(table)
        self.assertFalse(any("watch clean" in line for line in lines), "a clean mutant is reported: %r" % lines)
        self.assertEqual(len(lines), 1, "want one finding, got %r" % lines)
        self.assertTrue(lines[0].startswith("FAIL stale anchor, text found 0 times"), lines[0])
        self.assertIn("watch gone: anchor removed by a merge", lines[0])
        self.assertIn(self.watch, lines[0])

    def test_a_guard_anchor_twice_in_one_module_fails_as_ambiguous(self):
        table = [mutant("guard clean: anchor present once", "return x > 1"),
                 mutant("guard twice: anchor in two places", "dup = 0")]
        lines = self.findings(table)
        self.assertFalse(any("guard clean" in line for line in lines), "a clean mutant is reported: %r" % lines)
        self.assertEqual(len(lines), 1, "want one finding, got %r" % lines)
        self.assertTrue(lines[0].startswith("FAIL ambiguous anchor"), lines[0])
        self.assertIn("matches 2 times", lines[0])
        self.assertIn("guard twice: anchor in two places", lines[0])

    def test_a_guard_anchor_once_in_each_of_two_modules_fails_as_ambiguous(self):
        self.put("hooks/guard_b.py", "return x > 1\n")
        table = [mutant("guard clean: anchor present once", "url = \"http://x // y\""),
                 mutant("guard two modules: anchor in guard.py and guard_b.py", "return x > 1")]
        lines = self.findings(table)
        self.assertFalse(any("guard clean" in line for line in lines), "a clean mutant is reported: %r" % lines)
        self.assertEqual(len(lines), 1, "want one finding, got %r" % lines)
        self.assertTrue(lines[0].startswith("FAIL ambiguous anchor"), lines[0])
        self.assertIn("guard_b.py", lines[0])
        self.assertIn("guard two modules: anchor in guard.py and guard_b.py", lines[0])

    def test_a_watch_anchor_twice_in_its_file_fails_naming_the_count(self):
        table = [mutant("watch clean: anchor present once", "WATCH_LIMIT = 5", "watch"),
                 mutant("watch twice: anchor in two places", "= 'x'", "watch")]
        lines = self.findings(table)
        self.assertFalse(any("watch clean" in line for line in lines), "a clean mutant is reported: %r" % lines)
        self.assertEqual(len(lines), 1, "want one finding, got %r" % lines)
        self.assertTrue(lines[0].startswith("FAIL ambiguous anchor, text found 2 times"), lines[0])
        self.assertIn(self.watch, lines[0])
        self.assertIn("watch twice: anchor in two places", lines[0])

    def test_a_guard_family_anchor_in_a_sibling_guard_module_passes(self):
        self.put("hooks/guard_b.py", GUARD_B_SHARED)
        table = [mutant("guard sibling: anchor in guard_b.py only", "SHARED_RULE = 'sibling'", "guard"),
                 mutant("audit sibling: anchor in guard_b.py only", "SHARED_RULE = 'sibling'", "audit")]
        self.assertEqual(self.findings(table), [])

    def test_a_watch_anchor_in_a_sibling_module_is_stale(self):
        self.put("hooks/guard_b.py", GUARD_B_SHARED)
        table = [mutant("watch clean: anchor present once", "WATCH_LIMIT = 5", "watch"),
                 mutant("watch sibling: anchor in guard_b.py only", "SHARED_RULE = 'sibling'", "watch")]
        lines = self.findings(table)
        self.assertFalse(any("watch clean" in line for line in lines), "a clean mutant is reported: %r" % lines)
        self.assertEqual(len(lines), 1, "want one finding, got %r" % lines)
        self.assertTrue(lines[0].startswith("FAIL stale anchor, text found 0 times"), lines[0])
        self.assertIn(self.watch, lines[0])

    def test_an_unknown_target_fails_naming_the_target(self):
        table = [mutant("guard clean: anchor present once", "return x > 1"),
                 mutant("unknown target: names a target no table holds", "return x > 1", "nosuch")]
        lines = self.findings(table)
        self.assertFalse(any("guard clean" in line for line in lines), "a clean mutant is reported: %r" % lines)
        self.assertEqual(len(lines), 1, "want one finding, got %r" % lines)
        self.assertTrue(lines[0].startswith("FAIL unknown mutation target 'nosuch'"), lines[0])
        self.assertIn("unknown target: names a target no table holds", lines[0])

    def test_a_sweep_row_whose_anchor_matches_nothing_fails_naming_its_label_and_the_table(self):
        self.assertEqual(SWEEP_TEXT.count(STALE_OLD), 0, "fixture: the stale anchor must be absent from the sweep file")
        code, out = self.run_main([sweep_row(CLEAN_LABEL, CLEAN_OLD), sweep_row(STALE_LABEL, STALE_OLD)])
        self.assertEqual(self.lines_naming(out, CLEAN_LABEL), [], "a clean sweep row is reported: %s" % out)
        lines = self.lines_naming(out, STALE_LABEL)
        self.assertEqual(len(lines), 1, "want one finding for the stale sweep row, got:\n%s" % out)
        self.assertIn("stale", lines[0], lines[0])
        self.assertIn(TABLE_FILE, lines[0], lines[0])
        self.assertEqual(code, 1, out)

    def test_b_sweep_row_whose_anchor_matches_twice_fails_as_ambiguous(self):
        self.assertEqual(SWEEP_TEXT.count(DOUBLED_OLD), 2, "fixture: the doubled anchor must sit twice in the sweep file")
        code, out = self.run_main([sweep_row(CLEAN_LABEL, CLEAN_OLD), sweep_row(DOUBLED_LABEL, DOUBLED_OLD)])
        self.assertEqual(self.lines_naming(out, CLEAN_LABEL), [], "a clean sweep row is reported: %s" % out)
        lines = self.lines_naming(out, DOUBLED_LABEL)
        self.assertEqual(len(lines), 1, "want one finding for the doubled sweep row, got:\n%s" % out)
        self.assertIn("ambiguous", lines[0], lines[0])
        self.assertIn(TABLE_FILE, lines[0], lines[0])
        self.assertEqual(code, 1, out)

    def test_b_control_a_sweep_anchor_widened_to_one_match_has_no_finding(self):
        self.assertEqual(SWEEP_TEXT.count(WIDENED_OLD), 1, "fixture: the widened anchor must sit once in the sweep file")
        code, out = self.run_main([sweep_row(WIDENED_LABEL, WIDENED_OLD)])
        self.assertEqual([line for line in out.splitlines() if line.startswith("FAIL")], [], out)
        self.assertEqual(code, 0, out)

    def test_c_the_census_reads_the_sweep_table_it_is_given_not_a_copy_of_its_labels(self):
        code_a, out_a = self.run_main([sweep_row(SWAP_A_LABEL, STALE_OLD)])
        lines_a = self.lines_naming(out_a, SWAP_A_LABEL)
        self.assertEqual(len(lines_a), 1, "table A's row gives no finding: %s" % out_a)
        self.assertIn(TABLE_FILE, lines_a[0], lines_a[0])
        code_b, out_b = self.run_main([sweep_row(SWAP_B_LABEL, STALE_OLD)])
        self.assertEqual(self.lines_naming(out_b, SWAP_A_LABEL), [], "table A's label survives the swap to table B: %s" % out_b)
        self.assertEqual(len(self.lines_naming(out_b, SWAP_B_LABEL)), 1, "table B's row gives no finding: %s" % out_b)

    def test_sweep_control_an_empty_sweep_table_has_no_findings(self):
        code, out = self.run_main([])
        self.assertEqual([line for line in out.splitlines() if line.startswith("FAIL")], [], out)
        self.assertEqual(code, 0, out)

    def test_sweep_control_a_full_size_table_of_once_anchored_rows_has_no_findings(self):
        self.put("janitor/sweep.py", SWEEP_TEXT + "".join("sweep_marker_%d = %d\n" % (i, i) for i in range(FULL_SIZE)))
        rows = [sweep_row("sweep marker %d" % i, "sweep_marker_%d = %d\n" % (i, i)) for i in range(FULL_SIZE)]
        code, out = self.run_main(rows)
        self.assertEqual([line for line in out.splitlines() if line.startswith("FAIL")], [], out)
        self.assertEqual(code, 0, out)

    def test_an_unknown_sweep_target_fails_with_the_unknown_target_line(self):
        code, out = self.run_main([sweep_row(CLEAN_LABEL, CLEAN_OLD), sweep_row(UNKNOWN_LABEL, CLEAN_OLD, UNKNOWN_TARGET)])
        self.assertEqual(self.lines_naming(out, CLEAN_LABEL), [], "a clean sweep row is reported: %s" % out)
        want = "FAIL unknown mutation target 'nosuch' in %s: %s" % (TABLE_FILE, UNKNOWN_LABEL)
        self.assertEqual(self.lines_naming(out, UNKNOWN_LABEL), [want], out)
        self.assertEqual(code, 1, out)

    def test_the_pass_line_counts_the_guard_rows_and_the_sweep_rows(self):
        guard_rows = [mutant("guard clean: anchor present once", "return x > 1", "plain"),
                      mutant("guard clean two: anchor present once", 'url = "http://x // y"', "plain")]
        sweep_rows = [sweep_row(CLEAN_LABEL, CLEAN_OLD), sweep_row(WIDENED_LABEL, WIDENED_OLD),
                      sweep_row(CLEAN_THREE_LABEL, "def unlock(stale):")]
        code, out = self.run_main(sweep_rows, guard_rows)
        self.assertEqual([line for line in out.splitlines() if line.startswith("FAIL")], [], out)
        self.assertEqual(code, 0, out)
        self.assertIn("PASS mutant anchor census: 5 mutants", out.splitlines(), out)

    def test_a_malformed_sweep_row_fails_naming_its_label_and_the_table_with_no_traceback(self):
        code, out = self.run_main([sweep_row(CLEAN_LABEL, CLEAN_OLD), (MALFORMED_SWEEP_LABEL, "sweep")])
        self.assertEqual(self.lines_naming(out, CLEAN_LABEL), [], "a clean sweep row is reported: %s" % out)
        lines = self.lines_naming(out, MALFORMED_SWEEP_LABEL)
        self.assertEqual(len(lines), 1, "want one FAIL line for the malformed sweep row, got:\n%s" % out)
        self.assertTrue(lines[0].startswith("FAIL "), lines[0])
        self.assertIn(TABLE_FILE, lines[0], lines[0])
        self.assertNotIn("Traceback", out, out)
        self.assertEqual(code, 1, out)

    def test_a_sweep_row_with_no_label_fails_naming_its_row_index(self):
        code, out = self.run_main([sweep_row(CLEAN_LABEL, CLEAN_OLD), ()])
        self.assertEqual(self.lines_naming(out, CLEAN_LABEL), [], "a clean sweep row is reported: %s" % out)
        fails = [line for line in out.splitlines() if line.startswith("FAIL")]
        self.assertEqual(len(fails), 1, "want one FAIL line for the unlabelled sweep row, got:\n%s" % out)
        self.assertIn("row %d" % UNLABELLED_INDEX, fails[0], fails[0])
        self.assertIn(TABLE_FILE, fails[0], fails[0])
        self.assertNotIn("Traceback", out, out)
        self.assertEqual(code, 1, out)

    def test_a_malformed_guard_row_fails_naming_its_label_and_the_table_with_no_traceback(self):
        guard_rows = [mutant("guard clean: anchor present once", "return x > 1", "plain"), (MALFORMED_GUARD_LABEL, "return x > 1")]
        code, out = self.run_main([], guard_rows)
        self.assertEqual(self.lines_naming(out, "guard clean"), [], "a clean guard row is reported: %s" % out)
        lines = self.lines_naming(out, MALFORMED_GUARD_LABEL)
        self.assertEqual(len(lines), 1, "want one FAIL line for the malformed guard row, got:\n%s" % out)
        self.assertTrue(lines[0].startswith("FAIL "), lines[0])
        self.assertIn(GUARD_TABLE_FILE, lines[0], lines[0])
        self.assertNotIn("Traceback", out, out)
        self.assertEqual(code, 1, out)

    def test_a_failing_run_closes_with_the_bad_count_and_the_total_mutants(self):
        guard_rows = [mutant("guard clean: anchor present once", "return x > 1", "plain"), (MALFORMED_GUARD_LABEL, "return x > 1")]
        sweep_rows = [sweep_row(CLEAN_LABEL, CLEAN_OLD), sweep_row(CLEAN_THREE_LABEL, "def unlock(stale):"),
                      sweep_row(STALE_LABEL, STALE_OLD)]
        code, out = self.run_main(sweep_rows, guard_rows)
        self.assertEqual(out.splitlines()[-1:], ["mutant anchor census failed: 2 of 5 mutants have a bad row or anchor"], out)
        self.assertEqual(code, 1, out)


def probe_rows(label, old):
    """A folder file of one row, in the table's shape, whose anchor is `old` and whose target is a guard module."""
    return "ROWS = [\n    (%r, %r, 'x', 'guard', 'a case name'),\n]\n" % (label, old)


class FolderRowsAreCensused(unittest.TestCase):
    """The census reads the list the harness runs, folder rows included. Each case runs the real census script in a copy of
    the tree, under the run folder, with one probe file in hooks/mutants/. The copy holds hooks/ and testing/ flat, without
    test files, as the census reads them."""

    def tree(self, name):
        root = os.path.join(RUN_FOLDER, name)
        os.makedirs(os.path.join(root, "lint"))
        shutil.copyfile(os.path.join(os.path.dirname(HERE), "lint", "check_mutant_anchors.py"),
                        os.path.join(root, "lint", "check_mutant_anchors.py"))
        repo = os.path.dirname(HERE)
        for folder in ("hooks", "testing"):
            dest = os.path.join(root, folder)
            os.makedirs(dest)
            for entry in os.listdir(os.path.join(repo, folder)):
                source = os.path.join(repo, folder, entry)
                if entry.endswith(".py") and not entry.startswith("test_") and os.path.isfile(source):
                    shutil.copyfile(source, os.path.join(dest, entry))
        os.makedirs(os.path.join(root, "bin"))
        shutil.copyfile(os.path.join(repo, "bin", "sim-lease"), os.path.join(root, "bin", "sim-lease"))
        return root

    def probe(self, root, name, text):
        folder = os.path.join(root, "hooks", "mutants")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, name), "w", encoding="utf-8") as handle:
            handle.write(text)

    def census(self, root):
        script = os.path.join(root, "lint", "check_mutant_anchors.py")
        return subprocess.run([sys.executable, script], cwd=root, capture_output=True, text=True, timeout=600)

    def test_a_folder_row_with_a_stale_anchor_fails_the_census(self):
        root = self.tree("stale")
        self.probe(root, "aa-stale.py", probe_rows("census probe: stale anchor", "NO SUCH ANCHOR TEXT 4f1c"))
        proc = self.census(root)
        self.assertEqual(proc.returncode, 1, "the census passed a folder row whose anchor is in no guard module:\n" + proc.stdout)
        self.assertIn("census probe: stale anchor", proc.stdout)

    def test_a_folder_row_with_an_ambiguous_anchor_fails_the_census(self):
        root = self.tree("ambiguous")
        for name in ("guard_probe_a.py", "guard_probe_b.py"):
            with open(os.path.join(root, "hooks", name), "w", encoding="utf-8") as handle:
                handle.write("PROBE_TWICE = 1\n")
        self.probe(root, "aa-twice.py", probe_rows("census probe: ambiguous anchor", "PROBE_TWICE = 1"))
        proc = self.census(root)
        self.assertEqual(proc.returncode, 1, "the census passed a folder row whose anchor sits in two guard modules:\n" + proc.stdout)
        self.assertIn("census probe: ambiguous anchor", proc.stdout)

    def test_a_folder_row_with_a_valid_anchor_passes_the_census(self):
        # The probe file holds its own anchor text too. A census that scanned folder files would find it twice and fail.
        root = self.tree("valid")
        self.probe(root, "aa-valid.py", probe_rows("census probe: valid anchor", "    question_form.use_hooks_home(_HERE)"))
        proc = self.census(root)
        self.assertEqual(proc.returncode, 0, "the census failed a valid folder row:\n" + proc.stdout)
        self.assertIn("PASS mutant anchor census", proc.stdout)


if __name__ == "__main__":
    unittest.main()
