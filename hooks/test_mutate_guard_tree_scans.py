#!/usr/bin/env python3
"""Cases for the whole-tree scan suites in the lane-lint suite selector (hooks/mutate_guard.py). Standard library only.

    python3 hooks/test_mutate_guard_tree_scans.py

Four suites scan every tracked file, not one module. So no ordinary diff picks them, and lane lint never runs them
(debt lane-lint-tree-scans-unpicked). The rule these cases hold the selector to: it picks each whole-tree suite for a
diff that touches a file the suite scans.

- A diff of merge/merge.py picks all four. Each one scans it, and lint/test_no_window_spawn.py reads .py under merge/.
- A diff of docs/debts/notes.md picks the three that scan markdown. lint/test_no_window_spawn.py reads .py and .js
  only, so these cases assert nothing about it for a markdown file.
- An empty diff picks none of the four. A control: the old code picks none either.
- The suites the selector picks for merge/merge.py today stay picked. A control.

The probes call `suites_for_paths` on the checkout this file sits in, so they read the full-size tree and copy nothing.
The empty diff also runs `--lint-suites HEAD` through the real entry point. A non-empty `--lint-suites` case needs a
fixture that holds the four suites. None is built here: a copy of a suite is banned, and a stub ties the case to how
the selector reads a suite.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "lint"))
import mutate_guard  # noqa: E402  suites_for_paths, and _tracked_files (the list lint_suites_main reads)
from test_mutate_ci import run_cli  # noqa: E402  the one home of the selector's CLI runner

WHOLE_TREE = ("lint/test_no_window_spawn.py", "lint/test_retired_names.py", "lint/test_retired_repos.py",
              "lint/test_check_glossary.py")
MARKDOWN_SCANNERS = ("lint/test_retired_names.py", "lint/test_retired_repos.py", "lint/test_check_glossary.py")
MERGE_PROBE = "merge/merge.py"
MARKDOWN_PROBE = "docs/debts/notes.md"
CONTROLS = ("merge/test_merge.py", "merge/test_lane_lint.py")  # beside merge/merge.py, picked by the selector today

PICKS = {}  # a probe path -> the suites it picks, read once per run: each read parses every suite (about 7 s)


def tracked_paths():
    """The tracked paths the selector reads, from the working folder's repository."""
    tracked, reason = mutate_guard._tracked_files()
    if tracked is None:
        raise AssertionError(reason)
    return tracked


def picks_for(path):
    """The suites `suites_for_paths` picks for one changed path, called as `lint_suites_main` calls it."""
    if path not in PICKS:
        PICKS[path] = mutate_guard.suites_for_paths([path], tracked_paths(), union=True, chain=True)
    return PICKS[path]


class WholeTreePickTests(unittest.TestCase):
    """`suites_for_paths` on the real tree. Each probe asserts the scope (the probe and the suites are tracked) before
    the subject (the picks)."""

    @classmethod
    def setUpClass(cls):
        previous = os.getcwd()
        cls.addClassCleanup(os.chdir, previous)
        os.chdir(REPO)  # the selector opens tracked files by path, relative to the working folder
        cls.tracked = tracked_paths()

    def test_a_diff_of_merge_py_picks_each_whole_tree_suite(self):
        self.assertIn(MERGE_PROBE, self.tracked, "the scope: %s is tracked" % MERGE_PROBE)
        for suite in WHOLE_TREE:
            self.assertIn(suite, self.tracked, "the scope: %s is tracked, so the probe reaches it" % suite)
        picked = picks_for(MERGE_PROBE)
        for suite in WHOLE_TREE:
            with self.subTest(suite=suite):
                self.assertIn(suite, picked,
                              "suites_for_paths must pick %s for a diff of %s, a file the suite scans" % (suite, MERGE_PROBE))

    def test_a_diff_of_a_markdown_file_picks_each_suite_that_scans_markdown(self):
        self.assertIn(MARKDOWN_PROBE, self.tracked, "the scope: %s is tracked" % MARKDOWN_PROBE)
        for suite in MARKDOWN_SCANNERS:
            self.assertIn(suite, self.tracked, "the scope: %s is tracked, so the probe reaches it" % suite)
        picked = picks_for(MARKDOWN_PROBE)
        for suite in MARKDOWN_SCANNERS:
            with self.subTest(suite=suite):
                self.assertIn(suite, picked,
                              "suites_for_paths must pick %s for a diff of %s, a file the suite scans" % (suite, MARKDOWN_PROBE))

    def test_a_diff_of_merge_py_keeps_the_suites_it_picks_now(self):  # the control
        self.assertIn(MERGE_PROBE, self.tracked, "the scope: %s is tracked" % MERGE_PROBE)
        for suite in CONTROLS:
            self.assertIn(suite, self.tracked, "the scope: %s is tracked, so the probe reaches it" % suite)
        picked = picks_for(MERGE_PROBE)
        for suite in CONTROLS:
            with self.subTest(suite=suite):
                self.assertIn(suite, picked, "suites_for_paths must keep picking %s for a diff of %s" % (suite, MERGE_PROBE))

    def test_an_empty_diff_picks_no_whole_tree_suite(self):  # the control
        for suite in WHOLE_TREE:
            self.assertIn(suite, self.tracked, "the scope: %s is tracked, so an over-pick would show" % suite)
        picked = mutate_guard.suites_for_paths([], self.tracked, union=True, chain=True)
        for suite in WHOLE_TREE:
            with self.subTest(suite=suite):
                self.assertNotIn(suite, picked, "suites_for_paths must pick no whole-tree suite for an empty diff, not %s" % suite)


class LintSuitesEmptyDiffTests(unittest.TestCase):
    """`--lint-suites BASE` through the real entry point. HEAD...HEAD is an empty diff, the same control as above."""

    def test_lint_suites_for_an_empty_diff_prints_no_whole_tree_suite(self):  # the control
        code, out, err = run_cli(["--lint-suites", "HEAD"], cwd=REPO)
        self.assertEqual(code, 0, "exit %d\n%s%s" % (code, out, err))
        printed = out.splitlines()
        for suite in WHOLE_TREE:
            with self.subTest(suite=suite):
                self.assertNotIn(suite, printed, "--lint-suites HEAD (an empty diff) must print no whole-tree suite, not %s" % suite)


if __name__ == "__main__":
    unittest.main()
