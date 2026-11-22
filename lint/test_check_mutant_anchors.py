#!/usr/bin/env python3
"""Cases for lint/check_mutant_anchors.py. Standard library only.

    python3 lint/test_check_mutant_anchors.py

findings(mutations, targets, hooks) gives one `FAIL ...` line per mutant whose anchor is stale, ambiguous or aimed at an unknown
target. Each case builds its own guard folder, target file and table in a run folder, so no case reads the real hooks/ tree. The
real table is checked by the census step itself. MUTANT_ANCHORS_UNDER_TEST overrides the module path, for a mutant copy.

Each fail case also holds a clean mutant in the same table, and checks that the clean one is absent before it checks the bad line,
so a line that names the wrong mutant cannot pass.
"""
import importlib.util
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)

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
        }

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


if __name__ == "__main__":
    unittest.main()
