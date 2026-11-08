#!/usr/bin/env python3
"""Cases for the whole-tree scan suites in the lane-lint suite selector (hooks/mutate_guard.py). Standard library only.

    python3 hooks/test_mutate_guard_tree_scans.py

These cases pin which lane-lint suites the selector picks for a diff that touches a file the suite scans. The suites
are the whole-tree and whole-folder scans, and the Windows split suite, which walks every test file and the workflow
folder. The fail-safes are pinned too: a suite that cannot be read reads as picked.

- A diff of merge/merge.py picks all four. Each one scans it, and lint/test_no_window_spawn.py reads .py under merge/.
- A diff of docs/debts/notes.md picks the three that scan markdown. It does not pick lint/test_no_window_spawn.py, which
  reads .py and .js only.
- A diff that changes a test file, adds one, or changes a .github/workflows file picks lint/test_windows_split.py. Its
  CiCoverage case walks every test file and needs a checks.yml step for each. A product file does not pick it.
- `_scans_any_file` reads True when it cannot answer: a suite path that is missing, or a module with no product_kind.
- An empty diff picks none of the four. A control: the old code picks none either.
- The suites the selector picks for merge/merge.py today stay picked. A control.

The probes call `suites_for_paths` on the checkout this file sits in, so they read the full-size tree and copy nothing.
The empty diff also runs `--lint-suites HEAD` through the real entry point. A non-empty `--lint-suites` case needs a
fixture that holds the four suites. None is built here: a copy of a suite is banned, and a stub ties the case to how
the selector reads a suite.
"""
import importlib.util
import os
import shutil
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "lint"))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
import mutate_guard  # noqa: E402  suites_for_paths, _scans_any_file, and _tracked_files (the list lint_suites_main reads)
from test_mutate_ci import run_cli  # noqa: E402  the one home of the selector's CLI runner

WHOLE_TREE = ("lint/test_no_window_spawn.py", "lint/test_retired_names.py", "lint/test_retired_repos.py",
              "lint/test_check_glossary.py")
MARKDOWN_SCANNERS = ("lint/test_retired_names.py", "lint/test_retired_repos.py", "lint/test_check_glossary.py")
SPAWN_SUITE = "lint/test_no_window_spawn.py"
WINDOWS_SUITE = "lint/test_windows_split.py"
MERGE_PROBE = "merge/merge.py"
MARKDOWN_PROBE = "docs/debts/notes.md"
TEST_PROBE = "hooks/test_mutate_ci.py"  # a changed test file
ADDED_TEST_PROBE = "hooks/test_newthing.py"  # a test file that a diff adds: not tracked yet
WORKFLOW_PROBE = ".github/workflows/impeccable-sync.yml"  # no rule of the old selector reaches it, unlike checks.yml
PRODUCT_PROBE = "merge/launch.py"  # a product file that does not reach the Windows split suite
CONTROLS = ("merge/test_merge.py", "merge/test_lane_lint.py")  # beside merge/merge.py, picked by the selector

PICKS = {}  # a probe path -> the suites it picks, read once per run: each read parses every suite (about 7 s)
RUN = ""  # this run's folder, made in setUpModule and removed in tearDownModule


def setUpModule():
    global RUN
    RUN = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN, ignore_errors=True)


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

    def test_a_diff_of_a_markdown_file_does_not_pick_the_spawn_suite(self):  # the pin
        self.assertIn(MARKDOWN_PROBE, self.tracked, "the scope: %s is tracked" % MARKDOWN_PROBE)
        self.assertIn(SPAWN_SUITE, self.tracked, "the scope: %s is tracked, so the probe could reach it" % SPAWN_SUITE)
        self.assertNotIn(SPAWN_SUITE, picks_for(MARKDOWN_PROBE),
                         "suites_for_paths must not pick %s for a diff of %s: it scans .py and .js only" % (SPAWN_SUITE, MARKDOWN_PROBE))

    def test_a_changed_test_file_picks_the_windows_split_suite(self):
        self.assertIn(WINDOWS_SUITE, self.tracked, "the scope: %s is tracked, so the probe reaches it" % WINDOWS_SUITE)
        self.assertIn(TEST_PROBE, self.tracked, "the scope: %s is tracked, a changed test file" % TEST_PROBE)
        self.assertIn(WINDOWS_SUITE, picks_for(TEST_PROBE),
                      "suites_for_paths must pick %s for a diff that changes %s, a test file: its CiCoverage case walks every test file"
                      % (WINDOWS_SUITE, TEST_PROBE))

    def test_an_added_test_file_picks_the_windows_split_suite(self):
        self.assertIn(WINDOWS_SUITE, self.tracked, "the scope: %s is tracked, so the probe reaches it" % WINDOWS_SUITE)
        self.assertNotIn(ADDED_TEST_PROBE, self.tracked,
                         "the scope: %s is not tracked, so the probe is a file that the diff adds" % ADDED_TEST_PROBE)
        self.assertIn(WINDOWS_SUITE, picks_for(ADDED_TEST_PROBE),
                      "suites_for_paths must pick %s for a diff that adds %s, a test file: its CiCoverage case walks every test file"
                      % (WINDOWS_SUITE, ADDED_TEST_PROBE))

    def test_a_changed_workflow_file_picks_the_windows_split_suite(self):
        self.assertIn(WINDOWS_SUITE, self.tracked, "the scope: %s is tracked, so the probe reaches it" % WINDOWS_SUITE)
        self.assertIn(WORKFLOW_PROBE, self.tracked, "the scope: %s is tracked, a changed workflow file" % WORKFLOW_PROBE)
        self.assertIn(WINDOWS_SUITE, picks_for(WORKFLOW_PROBE),
                      "suites_for_paths must pick %s for a diff that changes %s, a workflow file" % (WINDOWS_SUITE, WORKFLOW_PROBE))

    def test_a_product_file_does_not_pick_the_windows_split_suite(self):  # the control: not for every path
        self.assertIn(PRODUCT_PROBE, self.tracked, "the scope: %s is tracked" % PRODUCT_PROBE)
        self.assertIn(WINDOWS_SUITE, self.tracked, "the scope: %s is tracked, so the probe could reach it" % WINDOWS_SUITE)
        self.assertNotIn(WINDOWS_SUITE, picks_for(PRODUCT_PROBE),
                         "suites_for_paths must not pick %s for a diff of %s: only a test file or a workflow file reaches its CiCoverage case"
                         % (WINDOWS_SUITE, PRODUCT_PROBE))

    def test_a_markdown_file_does_not_pick_the_windows_split_suite(self):  # the control: not for every path
        self.assertIn(MARKDOWN_PROBE, self.tracked, "the scope: %s is tracked" % MARKDOWN_PROBE)
        self.assertIn(WINDOWS_SUITE, self.tracked, "the scope: %s is tracked, so the probe could reach it" % WINDOWS_SUITE)
        self.assertNotIn(WINDOWS_SUITE, picks_for(MARKDOWN_PROBE),
                         "suites_for_paths must not pick %s for a diff of %s: only a test file or a workflow file reaches its CiCoverage case"
                         % (WINDOWS_SUITE, MARKDOWN_PROBE))

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


class FailSafeTests(unittest.TestCase):
    """`_scans_any_file` and `_walks_any_file` read True when they cannot answer: a suite path that is missing, or a module
    that has no product_kind or no TEST_FILE. A False there would hide the suite from lane lint."""

    def scans_any_file(self):
        fn = getattr(mutate_guard, "_scans_any_file", None)
        self.assertIsNotNone(fn, "hooks/mutate_guard.py has no _scans_any_file")
        return fn

    def walks_any_file(self):
        fn = getattr(mutate_guard, "_walks_any_file", None)
        self.assertIsNotNone(fn, "hooks/mutate_guard.py has no _walks_any_file")
        return fn

    def test_a_missing_suite_path_reads_as_picked(self):
        missing = os.path.join(RUN, "no_such_suite.py")
        self.assertFalse(os.path.exists(missing), "the scope: %s does not exist" % missing)
        self.assertTrue(self.scans_any_file()(missing, [MERGE_PROBE]),
                        "_scans_any_file must read True for a suite path that is missing")

    def test_a_module_with_no_product_kind_reads_as_picked(self):
        path = os.path.join(RUN, "no_product_kind_suite.py")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("VALUE = 1\n")
        spec = importlib.util.spec_from_file_location("no_product_kind_probe", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertFalse(hasattr(module, "product_kind"), "the scope: the module has no product_kind")
        self.assertTrue(self.scans_any_file()(path, [MERGE_PROBE]),
                        "_scans_any_file must read True for a module with no product_kind")

    def test_a_missing_windows_split_suite_path_reads_as_picked(self):
        missing = os.path.join(RUN, "no_such_windows_split.py")
        self.assertFalse(os.path.exists(missing), "the scope: %s does not exist" % missing)
        self.assertTrue(self.walks_any_file()(missing, [TEST_PROBE]),
                        "_walks_any_file must read True for a suite path that is missing")

    def test_a_windows_split_module_with_no_test_file_reads_as_picked(self):
        path = os.path.join(RUN, "no_test_file_suite.py")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("VALUE = 1\n")
        spec = importlib.util.spec_from_file_location("no_test_file_probe", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertFalse(hasattr(module, "TEST_FILE"), "the scope: the module has no TEST_FILE")
        self.assertTrue(self.walks_any_file()(path, [TEST_PROBE]),
                        "_walks_any_file must read True for a module with no TEST_FILE")


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
