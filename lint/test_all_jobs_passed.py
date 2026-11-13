#!/usr/bin/env python3
"""Guard for the one required check of .github/workflows/checks.yml: the `all-jobs-passed` job.

Branch protection requires that one check (actions/all-jobs-passed). It fails on a needed job that failed, was
cancelled or was skipped, so every job all-jobs-passed needs must run on a non-draft pull_request. This file proves:
all-jobs-passed needs exactly the jobs that run there, derived from the file and not from a copied list; only the shard
jobs (test_windows_split.SHARD_VAR) stay off it; no needed job has a job-level if, since each scope condition sits in
its steps (test_windows_split.job_check_problems); the job's shape, its own if (non-draft pull_request only) and its
checkout pin; scope skips only a draft PR; and ci-done needs all-jobs-passed.

Stdlib only, no PyYAML. CHECKS_YML overrides the path (red runs on a scratch copy).
Run with:  python3 lint/test_all_jobs_passed.py -v
The rules live in lint/all_jobs_passed_rules.py. A child repo's workflow is checked with:
python3 lint/all_jobs_passed_rules.py --workflow PATH
"""
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from test_windows_split import CHECKS  # noqa: E402  the one home of the checks.yml path
from all_jobs_passed_rules import (all_problems, child_problems, ci_done_problems, needs_problems,  # noqa: E402  the one home of the rules
                                   needs_of, off_problems, scope_if_problems, shape_problems, steps_problems)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  test-temp-standard: teardown removes the run folder (testing/tracked_tree.py)

PIN = "08c6903cd8c0fde910a37f88322edcfb5dd907a8"
# A minimal checks.yml that passes. Its comment openers sit inside quotes and in a block body, a lone quote sits in
# text, and a trailing comment follows a value: each must read as the value it is, not as a defect.
GOOD = """jobs:
  scope:
    if: ${{ github.event_name != 'pull_request' || !github.event.pull_request.draft }}
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - run: echo scope
  checks:
    runs-on: ubuntu-latest
    needs: scope
    steps:
      - name: Lint # the name keeps its comment out of the value
        run: |
          # a comment line in a block body is text, not a key
          if: not a key
          echo "Don't stop here # not a comment"
  checks-macos:
    runs-on: macos-latest
    needs: scope
    steps:
      - name: Mac's step
        if: ${{ needs.scope.outputs.checks_macos == 'true' }}
        run: echo mac
  checks-windows-guard-2:
    runs-on: windows-latest
    needs: scope
    if: ${{ github.event_name != 'pull_request' }}
    steps:
      - run: echo shard
  all-jobs-passed:
    runs-on: ubuntu-latest
    timeout-minutes: 5 # the cap
    if: ${{ always() && github.event_name == 'pull_request' && !github.event.pull_request.draft }}
    needs:
      - scope
      # - retired-job
      - checks # the lint job
      - checks-macos
    steps:
      - uses: actions/checkout@@PIN@ # v5.0.0
        with:
          persist-credentials: false
      - uses: $/actions/all-jobs-passed
        with:
          needs: ${{ toJSON(needs) }} # every job above
  ci-done:
    runs-on: ubuntu-latest
    needs:
      - scope
      - checks
      - checks-macos
      - checks-windows-guard-2
      - all-jobs-passed
    steps:
      - run: echo done
""".replace("@PIN@", PIN)

MUTATIONS = [
    ("a needed job missing from all-jobs-passed's needs", "      - checks-macos\n    steps:\n      - uses: actions/checkout",
     "    steps:\n      - uses: actions/checkout"),
    ("a job added but not in all-jobs-passed's needs", "  ci-done:\n", "  checks-new:\n    runs-on: ubuntu-latest\n    needs: scope\n"
     "    steps:\n      - run: echo new\n  ci-done:\n"),
    ("a needed job keeps a scope job-level if", "  checks-macos:\n    runs-on: macos-latest\n    needs: scope\n",
     "  checks-macos:\n    runs-on: macos-latest\n    needs: scope\n"
     "    if: ${{ needs.scope.outputs.checks_macos == 'true' || github.event_name != 'pull_request' }}\n"),
    ("a non-shard job turned off by an event if", "  checks-macos:\n    runs-on: macos-latest\n",
     "  checks-macos:\n    runs-on: macos-latest\n    if: ${{ github.event_name != 'pull_request' }}\n"),
    ("a shard added to all-jobs-passed's needs", "      - checks-macos\n    steps:\n      - uses: actions/checkout",
     "      - checks-macos\n      - checks-windows-guard-2\n    steps:\n      - uses: actions/checkout"),
    ("all-jobs-passed's always() dropped", "if: ${{ always() && github.event_name == 'pull_request' && !github.event.pull_request.draft }}",
     "if: ${{ github.event_name == 'pull_request' && !github.event.pull_request.draft }}"),
    ("the old if runs all-jobs-passed on push too", "if: ${{ always() && github.event_name == 'pull_request' && !github.event.pull_request.draft }}",
     "if: ${{ always() && !github.event.pull_request.draft }}"),
    ("all-jobs-passed sets a name", "  all-jobs-passed:\n    runs-on", "  all-jobs-passed:\n    name: All jobs passed\n    runs-on"),
    ("all-jobs-passed runs on macOS", "  all-jobs-passed:\n    runs-on: ubuntu-latest", "  all-jobs-passed:\n    runs-on: macos-latest"),
    ("a timeout that is only a comment", "timeout-minutes: 5 # the cap", "timeout-minutes: # the cap"),
    ("the checkout is not pinned", "actions/checkout@" + PIN + " # v5.0.0", "actions/checkout@v5"),
    ("the checkout keeps its token", "persist-credentials: false\n      - uses: $/actions", "persist-credentials: true\n      - uses: $/actions"),
    ("all-jobs-passed needs ci-done", "      - checks-macos\n    steps:\n      - uses: actions/checkout",
     "      - checks-macos\n      - ci-done\n    steps:\n      - uses: actions/checkout"),
    ("the action is commented out", "      - uses: $/actions/all-jobs-passed\n", "      # - uses: $/actions/all-jobs-passed\n"),
    ("ci-done does not need all-jobs-passed", "      - all-jobs-passed\n    steps:\n      - run: echo done", "    steps:\n      - run: echo done"),
    ("an empty needs list", "    needs:\n      - scope\n      # - retired-job\n      - checks # the lint job\n      - checks-macos\n"
     "    steps:\n      - uses: actions/checkout", "    needs: []\n    steps:\n      - uses: actions/checkout"),
    ("a needed job commented out of all-jobs-passed's needs", "      - checks-macos\n    steps:\n      - uses: actions/checkout",
     "      # - checks-macos\n    steps:\n      - uses: actions/checkout"),
    ("scope runs on a draft PR", "|| !github.event.pull_request.draft }}", "|| github.event.pull_request.draft }}"),
    ("no all-jobs-passed job", "  all-jobs-passed:\n", "  all-jobs-gone:\n"),
    ("the action step sets continue-on-error", "      - uses: $/actions/all-jobs-passed\n",
     "      - uses: $/actions/all-jobs-passed\n        continue-on-error: true\n"),
    ("the action step sets its own if", "      - uses: $/actions/all-jobs-passed\n",
     "      - uses: $/actions/all-jobs-passed\n        if: ${{ github.event_name == 'pull_request' }}\n"),
]


class AllJobsPassedJob(unittest.TestCase):
    def setUp(self):
        with open(CHECKS, encoding="utf-8") as f:
            self.text = f.read()

    def test_the_all_jobs_passed_job_has_its_shape(self):
        self.assertEqual(shape_problems(self.text), [])

    def test_all_jobs_passed_needs_exactly_the_jobs_that_run_on_a_pr(self):
        # Named failure: a job that runs on a PR but is not in all-jobs-passed's needs, so its red cannot block the merge.
        self.assertEqual(needs_problems(self.text), [])

    def test_all_jobs_passed_is_a_pinned_checkout_then_the_action(self):
        self.assertEqual(steps_problems(self.text), [])

    def test_only_shard_jobs_stay_off_and_no_needed_job_has_a_job_level_if(self):
        # Named failure: a job-level if skips a needed job, and all-jobs-passed reads the skip as red.
        self.assertEqual(off_problems(self.text), [])

    def test_scope_skips_only_a_draft_pr(self):
        self.assertEqual(scope_if_problems(self.text), [])

    def test_ci_done_needs_all_jobs_passed(self):
        self.assertEqual(ci_done_problems(self.text), [])


class AllJobsPassedFixtures(unittest.TestCase):
    def test_the_passing_fixture_is_green(self):
        self.assertEqual(all_problems(GOOD), [])

    def test_the_fixture_keeps_its_scanner_cases(self):
        for case in ("# not a comment", "# a comment line in a block body", "Don't stop here", "# the cap"):
            self.assertIn(case, GOOD, case)

    def test_each_defect_is_red(self):
        for label, old, new in MUTATIONS:
            with self.subTest(defect=label):
                self.assertIn(old, GOOD, label)  # a mutation that matches nothing proves nothing
                self.assertTrue(all_problems(GOOD.replace(old, new, 1)), label)


# A child repo's workflow: the generic rules, read through `--workflow PATH`. CHILD_GOOD passes them and each
# CHILD_MUTATIONS entry breaks one. It has no scope job, no ci-done and no checkout step. Its all-jobs-passed `if` means
# GOOD's, with the terms in another order, so the rule must read the meaning and not the text.
CHILD_PIN = "3b5d2f1a9c8e7f60b4a2d1c0e9f8a7b6c5d4e3f2"
CHILD_IF = "    if: ${{ !github.event.pull_request.draft && always() && github.event_name == 'pull_request' }}\n"
NEEDED_JOB = "      - test-mac # the mac job\n"
CHILD_GOOD = """name: checks
on:
  pull_request:
  push:
jobs:
  lint:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - name: "Lint # quoted, so its hash is text"
        run: |
          # a comment line in a block body is text, not a key
          if: not a key
          echo "Don't stop here # not a comment"
  test-mac:
    runs-on: macos-latest
    if: ${{ github.event_name == 'pull_request' }}
    steps:
      - name: Mac's step
        run: echo mac
  publish:
    runs-on: ubuntu-latest
    if: ${{ github.event_name != 'pull_request' }}
    needs: lint
    steps:
      - run: echo publish
  all-jobs-passed:
    runs-on: ubuntu-latest
    timeout-minutes: 5 # the cap
    if: ${{ !github.event.pull_request.draft && always() && github.event_name == 'pull_request' }}
    needs:
      - lint
      # - retired-job
      - test-mac # the mac job
    steps:
      - uses: shivinate7/claude-settings/actions/all-jobs-passed@@PIN@ # v1.2.0
        with:
          needs: ${{ toJSON(needs) }} # every job above
""".replace("@PIN@", CHILD_PIN)
CHILD_CI_DONE = "  ci-done:\n    runs-on: ubuntu-latest\n    needs: all-jobs-passed\n    steps:\n      - run: echo done\n"
CHILD_MUTATIONS = [
    ("a needed job missing from needs", NEEDED_JOB, ""),
    ("a push-only job in needs", NEEDED_JOB, NEEDED_JOB + "      - publish\n"),
    ("an empty needs list", "    needs:\n      - lint\n      # - retired-job\n" + NEEDED_JOB, "    needs: []\n"),
    ("the action pinned to @main", "all-jobs-passed@" + CHILD_PIN, "all-jobs-passed@main"),
    ("the action pinned to @v1", "all-jobs-passed@" + CHILD_PIN, "all-jobs-passed@v1"),
    ("the draft guard dropped from the if", CHILD_IF, "    if: ${{ always() && github.event_name == 'pull_request' }}\n"),
    ("always() dropped from the if", "always() && ", ""),
    ("the if also runs on push", CHILD_IF, "    if: ${{ !github.event.pull_request.draft && always() }}\n"),
    ("the needs input is not toJSON(needs)", "needs: ${{ toJSON(needs) }}", "needs: ${{ toJSON(github.event) }}"),
    ("no all-jobs-passed job", "  all-jobs-passed:\n", "  all-jobs-gone:\n"),
]
RULES_CLI = os.path.join(HERE, "all_jobs_passed_rules.py")  # the child CLI: `--workflow PATH`
RUN_FOLDER = None  # set by setUpModule, so a `--workflow` run makes no folder of its own


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    if RUN_FOLDER and os.path.isdir(RUN_FOLDER):
        tracked_tree.rm_tree(RUN_FOLDER)  # test-temp-standard: teardown removes the run folder


def full_size_child(count=40):
    """CHILD_GOOD with `count` more jobs that run on a PR, each one in all-jobs-passed's needs after the comment line."""
    jobs = "".join("  job-%02d:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo %02d\n" % (i, i) for i in range(count))
    needs = "".join("      - job-%02d\n" % i for i in range(count))
    text = CHILD_GOOD.replace("  all-jobs-passed:\n", jobs + "  all-jobs-passed:\n", 1)
    return text.replace("      # - retired-job\n", "      # - retired-job\n" + needs, 1)


def child_check(text):
    """(exit code, output) of `--workflow` on one child workflow. The file is written into this run's folder. `text` is
    str, written as UTF-8, or bytes, written as given."""
    folder = tempfile.mkdtemp(prefix="allpassed-", dir=RUN_FOLDER)
    path = os.path.join(folder, "checks.yml")
    with open(path, "wb") as handle:
        handle.write(text if isinstance(text, bytes) else text.encode("utf-8"))
    done = subprocess.run([sys.executable, RULES_CLI, "--workflow", path], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=120)
    return done.returncode, done.stdout + done.stderr


class ChildWorkflow(unittest.TestCase):
    """The child cases call the rules CLI and assert its exit code first, so a wrong exit fails the case before any
    in-process check runs."""

    def test_the_cs_rules_reject_a_valid_child(self):
        # The cs rules reject a child that passes the generic rules, which is why the child rules exist.
        self.assertTrue(all_problems(CHILD_GOOD), "the cs rules pass a valid child: they no longer reject a child's shape")

    def test_the_child_fixture_keeps_its_scanner_cases(self):
        for case in ('"Lint # quoted', "# a comment line in a block body", "if: not a key", "Don't stop here", "Mac's step",
                     "# the cap", "# v1.2.0", "# every job above"):
            self.assertIn(case, CHILD_GOOD, case)

    def test_the_harness_runs_this_script_from_its_path(self):
        # Green control: the subprocess that the child cases start reaches this script. The selector runs one case that starts nothing.
        done = subprocess.run([sys.executable, os.path.abspath(__file__), "-k", "test_the_passing_fixture_is_green"],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
        self.assertEqual(done.returncode, 0, "the script does not run from its path: " + done.stdout + done.stderr)

    def test_a_valid_child_file_exits_0(self):
        code, out = child_check(CHILD_GOOD)
        self.assertEqual(code, 0, "a valid child: exit %d, want 0: %s" % (code, out))
        self.assertEqual(child_problems(CHILD_GOOD), [], "a valid child has problems under child_problems")

    def test_a_valid_child_with_a_ci_done_job_exits_0(self):
        text = CHILD_GOOD + CHILD_CI_DONE
        code, out = child_check(text)
        self.assertEqual(code, 0, "a child with ci-done: exit %d, want 0: %s" % (code, out))
        self.assertEqual(child_problems(text), [], "ci-done counted as a needed job or a defect")

    def test_a_full_size_child_exits_0(self):
        self.assertIn("      # - retired-job\n", CHILD_GOOD)  # the anchor the full-size fixture inserts its needs after
        text = full_size_child()
        self.assertEqual(text.count("      - job-"), 40, "the full-size fixture lost needs entries")
        code, out = child_check(text)
        self.assertEqual(code, 0, "a full-size child: exit %d, want 0: %s" % (code, out))
        self.assertEqual(child_problems(text), [], "a full-size child has problems under child_problems")

    def test_an_empty_file_exits_1_and_names_the_missing_job(self):
        code, out = child_check("")
        self.assertEqual(code, 1, "an empty file: exit %d, want 1: %s" % (code, out))
        self.assertNotIn("Traceback", out, "an empty file crashes the reader")
        self.assertIn("all-jobs-passed", out, "the output does not name the missing job: " + out)
        self.assertTrue(child_problems(""), "an empty file has no problem under child_problems")

    def test_each_child_defect_exits_1(self):
        for label, old, new in CHILD_MUTATIONS:
            with self.subTest(defect=label):
                self.assertIn(old, CHILD_GOOD, label)  # a mutation that matches nothing proves nothing
                text = CHILD_GOOD.replace(old, new, 1)
                code, out = child_check(text)
                self.assertEqual(code, 1, "%s: exit %d, want 1" % (label, code))
                self.assertNotIn("Traceback", out, "%s: a crash also exits 1" % label)
                self.assertTrue(child_problems(text), "%s: no problem under child_problems" % label)

    def test_a_child_missing_a_needed_job_exits_1_and_prints_the_problem(self):
        text = CHILD_GOOD.replace(NEEDED_JOB, "", 1)
        code, out = child_check(text)
        self.assertEqual(code, 1, "a missing needed job: exit %d, want 1: %s" % (code, out))
        self.assertNotIn("Traceback", out, "a missing needed job crashes the reader")
        problems = child_problems(text)
        self.assertTrue(problems, "a missing needed job has no problem under child_problems")
        for problem in problems:
            self.assertIn(problem, out, "the problem is not printed: " + problem)
        self.assertIn("test-mac", out, "the printed problem does not name test-mac: " + out)


# The action step must carry neither continue-on-error nor its own if: either lets the required check pass while the
# action is skipped or fails. Each false alarm is a valid child with one layout changed, and the rules must pass it.
# Input that is not UTF-8 must exit 2 with a message, not with a traceback.
CHILD_ACTION_DEFECTS = [
    ("the action step continues on error", "# v1.2.0\n", "# v1.2.0\n        continue-on-error: true\n"),
    ("the action step has its own if", "# v1.2.0\n", "# v1.2.0\n        if: ${{ github.event_name == 'pull_request' }}\n"),
]
NEEDS_BLOCK = "    needs:\n      - lint\n      # - retired-job\n" + NEEDED_JOB
CHILD_FALSE_ALARMS = [
    ("needs as a multi-line flow list", NEEDS_BLOCK, "    needs: [\n      lint,\n      test-mac ]\n"),
    ("block-list needs items indented 8 spaces", NEEDS_BLOCK,
     "    needs:\n        - lint\n        # - retired-job\n        - test-mac # the mac job\n"),
    ("block-list needs at the key's indent", NEEDS_BLOCK,
     "    needs:\n    - lint\n    # - retired-job\n    - test-mac # the mac job\n"),
    ("a comment after steps:", "    steps:\n      - uses: shivinate7", "    steps: # note\n      - uses: shivinate7"),
    ("CRLF line endings", "\n", "\r\n"),
]


class ChildActionAndLayouts(unittest.TestCase):
    def test_the_action_step_with_continue_on_error_or_its_own_if_exits_1(self):
        for label, old, new in CHILD_ACTION_DEFECTS:
            with self.subTest(defect=label):
                self.assertIn(old, CHILD_GOOD, label)  # a mutation that matches nothing proves nothing
                text = CHILD_GOOD.replace(old, new, 1)
                code, out = child_check(text)
                self.assertEqual(code, 1, "%s: exit %d, want 1" % (label, code))
                self.assertNotIn("Traceback", out, "%s: a crash also exits 1" % label)
                self.assertTrue(child_problems(text), "%s: no problem under child_problems" % label)

    def test_the_child_false_alarms_pass(self):
        for label, old, new in CHILD_FALSE_ALARMS:
            with self.subTest(false_alarm=label):
                self.assertIn(old, CHILD_GOOD, label)
                text = CHILD_GOOD.replace(old, new)
                code, out = child_check(text)
                self.assertEqual(code, 0, "%s: exit %d, want 0: %s" % (label, code, out))
                self.assertEqual(child_problems(text), [], "%s: a valid child has problems under child_problems" % label)

    def test_a_non_utf8_file_exits_2_without_a_traceback(self):
        code, out = child_check(b"\xff\xfe" + CHILD_GOOD.encode("utf-8"))
        self.assertEqual(code, 2, "a non-UTF-8 file: exit %d, want 2: %s" % (code, out))
        self.assertNotIn("Traceback", out, "a non-UTF-8 file crashes the reader")

    def test_a_push_only_job_left_out_of_needs_passes(self):
        old = "    if: ${{ github.event_name != 'pull_request' }}\n"  # the push-only job's if
        self.assertIn(old, CHILD_GOOD, "the push-only job's if")
        text = CHILD_GOOD.replace(old, "    if: ${{ github.event_name == 'push' }}\n", 1)
        code, out = child_check(text)
        self.assertEqual(code, 0, "a push-only job left out of needs: exit %d, want 0: %s" % (code, out))
        self.assertEqual(child_problems(text), [], "a push-only job left out of needs has problems under child_problems")


class NeedsOf(unittest.TestCase):
    """needs_of reads each name as YAML does: a quoted item loses its quotes, in a block list or in a flow list."""

    def test_a_block_list_with_quoted_items_reads_their_names(self):
        block = "  checks-mac:\n    runs-on: macos-latest\n    needs:\n      - 'a'\n      - \"b\"\n    steps:\n      - run: echo\n"
        self.assertEqual(needs_of(block), ["a", "b"], "a block list's quoted items must read as their names")

    def test_a_flow_list_on_one_line_with_quoted_items_reads_their_names(self):
        block = "  checks-mac:\n    runs-on: macos-latest\n    needs: ['a', 'b']\n    steps:\n      - run: echo\n"
        self.assertEqual(needs_of(block), ["a", "b"], "a flow list's quoted items must read as their names")


if __name__ == "__main__":
    unittest.main()
