#!/usr/bin/env python3
"""Guard for the one required check of .github/workflows/checks.yml: the `all-jobs-passed` job.

Branch protection requires that one check (actions/all-jobs-passed). It fails on a needed job that failed, was
cancelled or was skipped, so every job all-jobs-passed needs must run on a non-draft pull_request. This file proves:
all-jobs-passed needs exactly the jobs that run there, derived from the file and not from a copied list; only the shard
jobs (test_windows_split.SHARD_VAR) and the macOS jobs (daily and dispatch only) stay off it; a needed job has no job-level
if; the job's shape, its own if (non-draft pull_request only) and its checkout pin; scope skips only a draft PR; and
ci-done needs all-jobs-passed.

Stdlib only, no PyYAML. CHECKS_YML overrides the path (red runs on a scratch copy).
Run with:  python3 lint/test_all_jobs_passed.py -v
The rules live in lint/all_jobs_passed_rules.py. A child repo's workflow is checked with:
python3 lint/all_jobs_passed_rules.py --workflow PATH
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from test_windows_split import CHECKS, LINUX_GUARD_JOBS, MACOS_JOBS, all_jobs, eval_with, yaml_scalar  # noqa: E402  the one home of the checks.yml path and the guard shards
from test_windows_split import ALL_JOBS_PASSED_JOB, SUITE_FLAG  # noqa: E402  the one home of the rollup job name and the suite flags
from all_jobs_passed_rules import (ALL_JOBS_PASSED_USES, all_problems, child_problems, ci_done_problems, needs_of,  # noqa: E402  the one home of the rules
                                   needs_problems, off_problems, scope_if_problems, scope_skips_problems, shape_problems, split_jobs, step_with,
                                   steps_problems, steps_part)
from workflow_steps import job_block, step_blocks, step_key  # noqa: E402  the one home of the job parser
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  test-temp-standard: teardown removes the run folder (testing/tracked_tree.py)
from test_ci_scope import run as scope_run  # noqa: E402  the scope script's one harness (lint/test_ci_scope.py)

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
          scope-skips: '{}'
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

    def test_only_shard_and_macos_jobs_stay_off_all_jobs_passed(self):
        # Named failure: a job that runs on a pull_request is off all-jobs-passed, so its red cannot block the merge.
        self.assertEqual(off_problems(self.text), [])

    def test_no_macos_job_is_needed_and_all_jobs_passed_scope_skips_is_the_empty_map(self):
        # Named failure: a macOS job is back in all-jobs-passed's needs, or the rollup's scope-skips map names a job, so a macOS job runs on a pull_request.
        needed, _, _ = split_jobs(self.text)
        self.assertEqual([j for j in MAC_JOBS if j in needed], [], "a macOS job runs on a pull_request, so it is needed by all-jobs-passed")
        self.assertEqual(scope_skips_input(self.text), "{}", "all-jobs-passed's scope-skips map names a job, which no macOS job has now")

    def test_a_rollup_with_no_scope_skips_input_is_flagged(self):
        # Named failure: without the input, check.sh reads a records-only run as red (actions/all-jobs-passed/check.sh, "Only a set SCOPE_SKIPS opts in").
        line = "          scope-skips: '{}'\n"
        self.assertEqual(self.text.count(line), 1, "the rollup's scope-skips line changed: this case must follow it")
        self.assertTrue(scope_skips_problems(self.text.replace(line, "", 1)), "a rollup with no scope-skips input passes the rules")

    def test_scope_skips_only_a_draft_pr(self):
        self.assertEqual(scope_if_problems(self.text), [])

    def test_ci_done_needs_all_jobs_passed(self):
        self.assertEqual(ci_done_problems(self.text), [])


# R61 planned shape, built from the real checks.yml: the nightly-skip job with scope waiting on it (part 3). The helper returns a
# file that already has its change as it is, so the cases hold after it lands.
MAC_JOBS = ("shell-macos", "checks-macos", "checks-macos-b")
SCOPE_IF = "    if: ${{ github.event_name != 'pull_request' || !github.event.pull_request.draft }}\n"
SKIPD_SCOPE_IF = ("    if: ${{ always() && (github.event_name != 'pull_request' || !github.event.pull_request.draft) "
                  "&& needs.nightly-skip.outputs.skip != 'true' }}\n    needs: nightly-skip\n")
SKIP_JOB = """  nightly-skip:
    if: ${{ github.event_name == 'schedule' }}
    runs-on: ubuntu-latest
    timeout-minutes: 5
    permissions:
      actions: read
      contents: read
    outputs:
      skip: ${{ steps.decide.outputs.skip }}
    steps:
      - id: gate
        run: echo skip=false >> "$GITHUB_OUTPUT"
"""


def planned_nightly_skip(text):
    """`text` with the nightly-skip job before `checks`, and scope needing it with its if reading the job's skip output."""
    if "\n  nightly-skip:\n" in text:
        return text
    assert text.count(SCOPE_IF) == 1, "scope's if changed: this fixture must follow it"
    assert text.count("\n  checks:\n") == 1, "the checks job's key changed: this fixture must follow it"
    text = text.replace(SCOPE_IF, SKIPD_SCOPE_IF, 1)
    return text.replace("\n  checks:\n", "\n" + SKIP_JOB + "  checks:\n", 1)


# checks-hooks' header and its job-level if in checks.yml. A case swaps that if line for its own, so the subject is the job's one if.
HOOKS_HEAD = "  checks-hooks:\n\n    runs-on: ubuntu-latest\n    needs: scope\n"
HOOKS_IF = "    if: ${{ needs.scope.outputs.records_only_skip != 'true' }}\n"


class PushOffRollup(unittest.TestCase):
    """Owner page item 880 (11:53 CST Nov 15): a Windows or mutation job keeps the push guard, `github.event_name != 'push'`, as its
    job-level if. all-jobs-passed runs only on a pull_request, and a pull_request runs every such job, so the rollup still needs it and
    its skip is never read there. The rule (off_problems) refused every job-level if on a needed job, which the push guard is not.
    Synthetic files: one Windows job, needed by all-jobs-passed, with the if under test."""

    def rollup_text(self, job_if):
        lines = ["jobs:", "  checks-windows:", "    runs-on: windows-latest", "    needs: scope"]
        if job_if is not None:
            lines.append(f"    if: {job_if}")
        lines += ["    steps:", "      - run: echo ok", "  all-jobs-passed:", "    runs-on: ubuntu-latest",
                  "    if: ${{ always() && github.event_name == 'pull_request' && !github.event.pull_request.draft }}",
                  "    needs:", "      - checks-windows", "    steps:", "      - run: echo ok"]
        return "\n".join(lines) + "\n"

    def test_a_needed_job_whose_job_level_if_is_the_push_guard_passes_the_rollup_rules(self):
        # Named failure on the old rules: the push guard is a job-level if on a needed job, so the rule refuses it.
        self.assertEqual(off_problems(self.rollup_text("${{ github.event_name != 'push' }}")), [],
                         "a needed job whose if is the push guard is refused, though a pull_request always runs it")

    def test_a_needed_job_whose_push_guard_reads_a_flag_is_refused(self):
        # Control: a push guard with a flag skips the job on a pull_request whose flag is off, so the rollup must refuse it.
        self.assertTrue(off_problems(self.rollup_text("${{ github.event_name != 'push' && needs.scope.outputs.checks_windows == 'true' }}")),
                        "a needed job whose push guard reads a flag is accepted, so its skip on a pull_request reads as green")

    def test_a_needed_job_with_no_job_level_if_passes_the_rollup_rules(self):
        # Control, green on the old rules: a job with no job-level if is needed and passes.
        self.assertEqual(off_problems(self.rollup_text(None)), [])


class MacOnceByBatchRollup(unittest.TestCase):
    """R61 on the one required check, read as the macOS jobs run now (owner, 01:33 CST Nov 16): each macOS job is off the rollup, and
    the nightly-skip job is an off-rollup job that is not a shard. Each case reads the real checks.yml."""

    def setUp(self):
        with open(CHECKS, encoding="utf-8") as f:
            self.text = f.read()

    def test_each_macos_job_is_off_all_jobs_passed_on_a_pull_request(self):
        # Named failure: a macOS job is needed by all-jobs-passed, so a pull_request runs it and its red blocks the merge.
        needed, _, problems = split_jobs(self.text)
        self.assertEqual(problems, [])
        self.assertTrue(needed, "the reader derived no needed job: an empty match would prove nothing")
        self.assertEqual([j for j in MAC_JOBS if j in needed], [], "a macOS job is needed by all-jobs-passed")

    def test_the_rollup_does_not_need_any_macos_job(self):
        # Named failure: all-jobs-passed names a macOS job in its needs, so the rollup reads that job's skip on every pull_request.
        rollup = needs_of(job_block(self.text, "all-jobs-passed") or "") or []
        self.assertTrue(rollup, "the rollup's needs were not read: an empty match would prove nothing")
        self.assertEqual([j for j in MAC_JOBS if j in rollup], [], "all-jobs-passed needs a macOS job")

    def test_the_nightly_skip_is_no_rollup_member_and_scope_reads_its_skip(self):
        # Named failure: the nightly-skip job is an off-rollup job that is not a shard, and scope's if reads its skip output.
        planned = planned_nightly_skip(self.text)
        self.assertEqual(off_problems(planned), [])
        self.assertEqual(needs_problems(planned), [])
        self.assertEqual(scope_if_problems(planned), [])

    def test_a_macos_job_whose_if_runs_on_a_pull_request_is_flagged(self):
        # Control: an if that is true on a pull_request makes its macOS job needed, and all-jobs-passed does not name it, so the rules refuse it.
        # The line swapped is shell-macos's own if, asserted present first, so the swap cannot be a no-op.
        jobs = all_jobs(self.text)
        old_if = jobs["shell-macos"]["if"]
        line = "    if: " + old_if + "\n"
        self.assertEqual(self.text.count(line), 1, "shell-macos's if line is not in checks.yml: this case must follow it")
        swapped = self.text.replace(line, "    if: ${{ github.event_name != 'push' }}\n", 1)
        self.assertTrue(needs_problems(swapped) or off_problems(swapped), "a macOS job whose if runs on a pull_request passes the rules")

    def test_a_flag_reading_job_level_if_on_a_job_with_no_macos_role_is_flagged(self):
        # Control: a job-level if that reads a scope flag is refused on a needed job that is no macOS job.
        self.assertEqual(self.text.count(HOOKS_HEAD + HOOKS_IF), 1, "checks-hooks' header changed: this case must follow it")
        text = self.text.replace(HOOKS_HEAD + HOOKS_IF, HOOKS_HEAD + "    if: ${{ needs.scope.outputs.checks_macos == 'true' }}\n", 1)
        self.assertTrue(off_problems(text) or needs_problems(text), "a flag-reading job-level if on an unnamed job passes the rollup rules")


# The macOS jobs run on a schedule and a dispatch only (owner, 01:33 CST Nov 16): no job-level if lets a pull_request start one,
# and all-jobs-passed needs none of them, so it names no scope-skips map. check.sh is the action's generic check, not this rule.
CHECK_SH = os.path.join(HERE, "..", "actions", "all-jobs-passed", "check.sh")
SHELL_MACOS_IF = "    if: ${{ github.event_name != 'pull_request' && github.event_name != 'push' && (needs.scope.outputs.shell_macos == 'true' || github.event_name != 'pull_request') }}\n"
# Each defect is (label, the job whose block holds old or None for all of checks.yml, old, new). Each replaces one line, once, and the
# wiring rule must add a problem for each.
DAILY_DEFECTS = [
    ("a macOS job added back to all-jobs-passed's needs", "all-jobs-passed", "      - checks-waiting-page\n",
     "      - checks-waiting-page\n      - shell-macos\n"),
    ("a scope-skips input naming a macOS job", "all-jobs-passed", "          needs: ${{ toJSON(needs) }}\n",
     "          needs: ${{ toJSON(needs) }}\n          scope-skips: '{\"shell-macos\":[\"shell_macos\"]}'\n"),
    ("the old scope skip restored on shell-macos", None, SHELL_MACOS_IF,
     "    if: ${{ github.event_name != 'push' && (needs.scope.outputs.shell_macos == 'true' || github.event_name != 'pull_request') }}\n"),
    ("shell-macos's if runs on a pull_request", None, SHELL_MACOS_IF, "    if: ${{ github.event_name != 'push' }}\n"),
]


def check_sh(needs, scope_skips_value=None):
    """(exit code, output) of the action's check.sh over one toJSON(needs). SCOPE_SKIPS is set only when given, so no
    SCOPE_SKIPS of the caller's environment reaches the check."""
    env = {k: v for k, v in os.environ.items() if k != "SCOPE_SKIPS"}
    env["NEEDS"] = json.dumps(needs)
    if scope_skips_value is not None:
        env["SCOPE_SKIPS"] = scope_skips_value
    done = subprocess.run(["bash", CHECK_SH], env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    return done.returncode, done.stdout + done.stderr


def scope_skips_input(text):
    """The scope-skips input of all-jobs-passed's action step, unquoted, or None when that step has no such input."""
    for step in step_blocks(steps_part(job_block(text, "all-jobs-passed") or "")):
        if yaml_scalar(step_key(step, "uses") or "") == ALL_JOBS_PASSED_USES:
            return step_with(step, "scope-skips")
    return None


class MacOsNeverOnPullRequest(unittest.TestCase):
    """A macOS job never starts on a pull_request, whatever its scope flags, and all-jobs-passed needs none of them, so no
    scope-skips map is read for them. Each case reads the real checks.yml."""

    def setUp(self):
        with open(CHECKS, encoding="utf-8") as f:
            self.text = f.read()

    def job_if(self, name):
        expr = all_jobs(self.text).get(name, {}).get("if")
        self.assertIsNotNone(expr, f"{name} has no job-level if")
        return expr

    def test_a_pull_request_that_touches_no_macos_path_starts_no_macos_runner(self):
        # Named failure: a macOS job runs on a pull_request, or all-jobs-passed still needs one and reads its skip as red.
        flags = scope_run(["README.md"])
        for flag in ("shell_macos", "checks_macos", "sweep"):  # scope first: a docs-only pull request sets no macOS flag
            self.assertEqual(flags[flag], "false", f"a docs-only pull request sets {flag}: {flags}")
        for name in MACOS_JOBS:
            for value in ("true", "false"):  # every flag the same: a macOS job reads none of them on a pull_request
                vals = {flag: value for flag in ("shell_macos", "checks_macos", "sweep")}
                with self.subTest(job=name, flags=value):
                    self.assertFalse(eval_with(self.job_if(name), "pull_request", vals), f"{name} runs on a pull_request with flags {value}")
        # The same pull request as all-jobs-passed sees it: every needed job passed, and no macOS job among them.
        needs = {name: {"result": "success"} for name in needs_of(job_block(self.text, "all-jobs-passed"))}
        needs["scope"] = {"result": "success", "outputs": flags}
        self.assertEqual(scope_skips_input(self.text), "{}", "all-jobs-passed's scope-skips map names a job: no macOS job has a scope skip now")
        code, out = check_sh(needs)
        self.assertEqual(code, 0, f"all-jobs-passed refuses a pull request with no macOS path: exit {code}: {out}")

    def test_a_pull_request_that_changes_install_sh_does_not_start_shell_macos(self):
        # Named failure: a pull_request that changes install.sh starts shell-macos, which runs on the daily schedule and a dispatch only.
        flags = scope_run(["install.sh"])
        self.assertEqual(flags["shell_macos"], "true", f"install.sh does not set shell_macos: {flags}")  # scope first: the path is a macOS path
        expr = self.job_if("shell-macos")
        self.assertFalse(eval_with(expr, "pull_request", {"shell_macos": "true"}),
                         f"shell-macos runs on a pull_request that changes install.sh: {expr}")
        self.assertTrue(eval_with(expr, "schedule", {"shell_macos": "false"}), f"shell-macos does not run on a schedule: {expr}")
        self.assertTrue(eval_with(expr, "workflow_dispatch", {"shell_macos": "false"}), f"shell-macos does not run on a dispatch: {expr}")


class DailyOnlyWiring(unittest.TestCase):
    """The wiring rule reads the macOS jobs as daily only: each is off all-jobs-passed, and the rollup names no scope-skips map.
    Each defect below is applied to checks.yml, and the rule must add a problem for each."""

    def setUp(self):
        with open(CHECKS, encoding="utf-8") as f:
            self.text = f.read()

    def test_the_wiring_rule_passes_the_checks_yml_on_disk(self):
        self.assertEqual(all_problems(self.text), [])

    def test_each_defect_of_the_daily_rule_is_flagged(self):
        clean = all_problems(self.text)
        for label, job, old, new in DAILY_DEFECTS:
            with self.subTest(defect=label):
                scope = job_block(self.text, job) if job else self.text
                self.assertIsNotNone(scope, f"{label}: no {job} job, so the mutation proves nothing")
                self.assertEqual(scope.count(old), 1, f"{label}: the mutation must match exactly once, or it proves nothing")
                mutated = self.text.replace(scope, scope.replace(old, new, 1), 1) if job else self.text.replace(old, new, 1)
                extra = [p for p in all_problems(mutated) if p not in clean]
                self.assertTrue(extra, f"{label}: the wiring rule passes it")

    def test_a_job_level_if_on_a_job_that_is_no_macos_job_and_runs_on_a_pull_request_is_flagged(self):
        # Control: a needed job with a job-level if that is no macOS job is refused, since all-jobs-passed would read its skip as red.
        self.assertEqual(self.text.count(HOOKS_HEAD + HOOKS_IF), 1, "checks-hooks' header changed: this case must follow it")
        text = self.text.replace(HOOKS_HEAD + HOOKS_IF, HOOKS_HEAD + "    if: ${{ github.event_name != 'push' }}\n", 1)
        clean = all_problems(self.text)
        self.assertTrue([p for p in all_problems(text) if p not in clean], "a needed job with a job-level if passes the rules")


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


# The rollup side of the merge and rest flags: a shard whose suite steps skip by its flag still ends success, because its job runs. all-jobs-passed passes that result, fails a failed shard, and needs each shard. Controls: green on the old check.sh.
class ShardsRunWithTheirFlagFalse(unittest.TestCase):
    def setUp(self):
        with open(CHECKS, encoding="utf-8") as f:
            self.text = f.read()
        self.needed = needs_of(job_block(self.text, ALL_JOBS_PASSED_JOB)) or []

    def needs_json(self, failed=None):
        needs = {name: {"result": "success"} for name in self.needed}
        if failed is not None:
            needs[failed]["result"] = "failure"
        return needs

    def test_the_rollup_needs_every_merge_and_rest_shard(self):
        missing = [name for name in SUITE_FLAG if name not in self.needed]
        self.assertEqual(missing, [], f"all-jobs-passed does not need these shards, so their results are not in the verdict: {missing}")

    def test_each_shard_job_still_runs_with_its_flag_false_on_a_ready_pull_request(self):
        # Named failure: a job-level if that skips the shard with its flag false would make its result skipped, not success.
        jobs = all_jobs(self.text)
        for name, flag in SUITE_FLAG.items():
            with self.subTest(job=name):
                self.assertIn(name, jobs, f"{name} is not a job in checks.yml")
                expr = jobs[name]["if"]
                self.assertIsNotNone(expr, f"{name} has no job-level if")
                self.assertTrue(eval_with(expr, "pull_request", {flag: "false", "records_only_skip": "false"}, default="true"),
                                f"{name} is skipped at job level on a ready pull_request with {flag} false: if {expr}")

    def test_a_green_rollup_passes_with_each_shard_success_whatever_its_steps_did(self):
        code, out = check_sh(self.needs_json())
        self.assertEqual(code, 0, f"the rollup fails with every job a success: {out}")

    def test_a_failed_shard_fails_the_rollup(self):
        for name in SUITE_FLAG:
            with self.subTest(shard=name):
                self.assertIn(name, self.needed, f"{ALL_JOBS_PASSED_JOB} does not need {name}, so its failure is no verdict")
                code, out = check_sh(self.needs_json(failed=name))
                self.assertNotEqual(code, 0, f"a failed {name} passes the rollup: {out}")


def with_job_if(text, job, expr):
    """checks.yml with `job`'s one job-level if line replaced by `expr`, or removed when expr is None. None unless the job has
    exactly one if line."""
    body = job_block(text, job) or ""
    lines = [ln for ln in body.splitlines(keepends=True) if ln.startswith("    if:")]
    if len(lines) != 1:
        return None
    return text.replace(body, body.replace(lines[0], "" if expr is None else "    if: %s\n" % expr, 1), 1)


# checks' gate if: it runs on any guard shard's result, and skips only when scope did not succeed or the records-only skip is set.
GATE_IF = "${{ !cancelled() && needs.scope.result == 'success' && needs.scope.outputs.records_only_skip != 'true' }}"


class ExemptionCases(unittest.TestCase):
    """off_problems on checks.yml with checks' job-level if swapped: a control on the workflow's own if, the ifs the rules must
    refuse (always(), a run condition that drops the scope result), and an if on another needed job, which keeps the rule. Each
    refused if is a run that could go green when scope did not succeed, or a lint suite that skips when a shard failed."""

    def setUp(self):
        with open(CHECKS, encoding="utf-8") as f:
            self.text = f.read()

    def test_a_checks_with_its_workflow_if_is_not_flagged(self):
        # Control: the if the workflow has now passes the rules, so off_problems reads checks clean.
        self.assertIsNotNone(all_jobs(self.text).get("checks", {}).get("if"), "scope: checks has no job-level if, so the control reads nothing")
        problems = off_problems(self.text)
        self.assertEqual(problems, [], "checks with its workflow if is flagged: %s" % problems)

    def test_a2_checks_with_the_gate_if_is_not_flagged(self):
        """checks runs on any shard result and skips only when scope did not succeed or the records-only skip is set (the wider
        run condition that the shards' gate needs, test_windows_split.py checks_if_problems). The rules must accept that if."""
        text = with_job_if(self.text, "checks", GATE_IF)
        self.assertIsNotNone(text, "scope: checks.yml has no single job-level if line in checks to swap")
        problems = off_problems(text)
        self.assertEqual(problems, [], "checks with the gate if is flagged: %s" % problems)

    def test_b_checks_with_always_is_flagged(self):
        text = with_job_if(self.text, "checks", "${{ always() }}")
        self.assertIsNotNone(text, "scope: checks.yml has no single job-level if line in checks to swap")
        self.assertTrue(off_problems(text), "checks with always() passes the rules: its lint suite would run when scope did not succeed")

    def test_c_checks_whose_if_drops_the_scope_result_is_flagged(self):
        shard_results = " && ".join("needs.%s.result == 'success'" % job for job in LINUX_GUARD_JOBS)
        for label, expr in (
            ("!cancelled() alone", "${{ !cancelled() }}"),
            ("the shard results without the scope result", "${{ !cancelled() && %s }}" % shard_results),
        ):
            with self.subTest(if_=label):
                text = with_job_if(self.text, "checks", expr)
                self.assertIsNotNone(text, "scope: checks.yml has no single job-level if line in checks to swap")
                self.assertTrue(off_problems(text), "checks with %s passes the rules: a skipped scope would still run its lint" % label)

    def test_d_another_needed_job_with_a_different_job_level_if_is_still_flagged(self):
        text = with_job_if(self.text, "checks-hooks", "${{ needs.scope.outputs.code == 'true' }}")
        self.assertIsNotNone(text, "scope: checks-hooks has no single job-level if line to swap")
        self.assertTrue(off_problems(text), "checks-hooks with a job-level if that is not the records-only skip passes the rules")


if __name__ == "__main__":
    unittest.main()
