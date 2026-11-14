#!/usr/bin/env python3
"""Guard for the one required check of .github/workflows/checks.yml: the `all-jobs-passed` job.

Branch protection requires that one check (actions/all-jobs-passed). It fails on a needed job that failed, was
cancelled or was skipped, so every job all-jobs-passed needs must run on a non-draft pull_request. This file proves:
all-jobs-passed needs exactly the jobs that run there, derived from the file and not from a copied list; only the shard
jobs (test_windows_split.SHARD_VAR) stay off it; a needed job has no job-level if, except a macOS job's scope gate, which
scope-skips names (testing/scope_skips.py); the job's shape, its own if (non-draft pull_request only) and its
checkout pin; scope skips only a draft PR; and ci-done needs all-jobs-passed.

Stdlib only, no PyYAML. CHECKS_YML overrides the path (red runs on a scratch copy).
Run with:  python3 lint/test_all_jobs_passed.py -v
The rules live in lint/all_jobs_passed_rules.py. A child repo's workflow is checked with:
python3 lint/all_jobs_passed_rules.py --workflow PATH
"""
import difflib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from test_windows_split import CHECKS, MACOS_JOBS, all_jobs, eval_with, yaml_scalar  # noqa: E402  the one home of the checks.yml path
from all_jobs_passed_rules import (ALL_JOBS_PASSED_USES, all_problems, child_problems, ci_done_problems, needs_of,  # noqa: E402  the one home of the rules
                                   needs_problems, off_problems, scope_if_problems, shape_problems, split_jobs, step_with,
                                   steps_problems, steps_part)
from workflow_steps import job_block, step_blocks, step_key  # noqa: E402  the one home of the job parser
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  test-temp-standard: teardown removes the run folder (testing/tracked_tree.py)
import scope_skips  # noqa: E402  the one home of the macOS gate and its scope-skips entry (testing/scope_skips.py)
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

    def test_only_shard_jobs_stay_off_and_a_needed_job_level_if_is_a_listed_gate(self):
        # Named failure: a macOS job's job-level gate is not named in all-jobs-passed's scope-skips, so its skip reads as red.
        # The planned file (the gate and its entry, testing/scope_skips.py) is red on the old rules until the change lands.
        self.assertEqual(off_problems(self.text), [])
        self.assertEqual(off_problems(scope_skips.planned_scope_gate(self.text)), [])

    def test_scope_skips_only_a_draft_pr(self):
        self.assertEqual(scope_if_problems(self.text), [])

    def test_ci_done_needs_all_jobs_passed(self):
        self.assertEqual(ci_done_problems(self.text), [])


# R61 planned shapes, built from the real checks.yml: the push guard on each macOS job (part 1) and the nightly gate with scope
# waiting on it (part 3). Each helper returns a file that already has its change as it is, so the cases hold after it lands.
MAC_JOBS = ("shell-macos", "checks-macos", "checks-macos-b")
PUSH_GUARD_IF = "    if: ${{ github.event_name != 'push' }}\n"
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


def planned_mac_push_guard(text):
    """`text` with the push guard as each macOS job's job-level if, placed after its `needs: scope` line."""
    for name in MAC_JOBS:
        head = re.compile(rf"^  {re.escape(name)}:\n    runs-on: [^\n]*\n    needs: scope\n", re.M)
        if re.search(rf"^  {re.escape(name)}:\n    runs-on: [^\n]*\n    needs: scope\n    if: ", text, re.M):
            continue
        assert len(head.findall(text)) == 1, f"{name}'s head changed: this fixture must follow it"
        text = head.sub(lambda m: m.group(0) + PUSH_GUARD_IF, text, count=1)
    return text


def planned_nightly_skip(text):
    """`text` with the nightly gate job before `checks`, and scope needing it with its if reading the gate's skip output."""
    if "\n  nightly-skip:\n" in text:
        return text
    assert text.count(SCOPE_IF) == 1, "scope's if changed: this fixture must follow it"
    assert text.count("\n  checks:\n") == 1, "the checks job's key changed: this fixture must follow it"
    text = text.replace(SCOPE_IF, SKIPD_SCOPE_IF, 1)
    return text.replace("\n  checks:\n", "\n" + SKIP_JOB + "  checks:\n", 1)


class MacOnceByBatchRollup(unittest.TestCase):
    """R61 on the one required check: the push guard keeps each macOS job needed, the rollup still needs every job, and the
    nightly gate is an off-rollup job that is not a shard. Each case is a control that holds on the old rules and on the landed
    file: the subject is built from the planned gate, with one known line swapped and asserted present, and the allowance stays
    narrow. The planned gate with its scope-skips entry is ScopeSkipsWiring's case."""

    def setUp(self):
        with open(CHECKS, encoding="utf-8") as f:
            self.text = f.read()

    def test_a_macos_job_may_keep_the_push_guard_as_its_job_level_if(self):
        # Named failure: all-jobs-passed reads a macOS job's job-level if as a skip it must refuse, so the push guard is refused.
        self.assertEqual(off_problems(planned_mac_push_guard(self.text)), [])

    def test_the_push_guard_keeps_each_macos_job_needed_on_a_pull_request(self):
        # Control: the push guard is true on a PR, so each macOS job stays in all-jobs-passed's needs.
        needed, _, problems = split_jobs(planned_mac_push_guard(self.text))
        self.assertEqual(problems, [])
        self.assertEqual([j for j in MAC_JOBS if j not in needed], [], "a macOS job left the needed set with the push guard")

    def test_the_rollup_still_needs_each_macos_job(self):
        # Control: a macOS job's red reaches the one required check through its name in all-jobs-passed's needs.
        rollup = needs_of(job_block(self.text, "all-jobs-passed") or "") or []
        self.assertEqual([j for j in MAC_JOBS if j not in rollup], [], "all-jobs-passed does not need every macOS job")

    def test_the_nightly_skip_is_no_rollup_member_and_scope_reads_its_skip(self):
        # Named failure: the gate is an off-rollup job that is not a shard, and scope's if reads the gate's skip output.
        planned = planned_nightly_skip(self.text)
        self.assertEqual(off_problems(planned), [])
        self.assertEqual(needs_problems(planned), [])
        self.assertEqual(scope_if_problems(planned), [])

    def test_a_macos_job_whose_if_skips_a_ready_pr_is_flagged(self):
        # Control: an if that is false on a ready PR still makes its job off the rollup, and is named as a non-shard. The subject is
        # the planned file, with shell-macos's gate line swapped for a push-only if. The gate line is asserted present first, so a
        # landed gate cannot turn the swap into a no-op.
        planned = scope_skips.planned_scope_gate(self.text)
        gate = "    if: ${{ " + scope_skips.gate_expr("shell-macos") + " }}\n"
        self.assertEqual(planned.count(gate), 1, "shell-macos's planned gate line is not in the planned file: this case must follow it")
        swapped = planned.replace(gate, "    if: ${{ github.event_name == 'push' }}\n", 1)
        self.assertTrue(off_problems(swapped), "an if false on a ready PR passes the rollup rules")

    def test_a_flag_reading_job_level_if_on_a_job_scope_skips_does_not_name_is_flagged(self):
        # Control: a job-level if that reads a scope flag is refused on a job that scope-skips does not name. The subject is
        # checks-hooks, which is no macOS job, so no gate or entry of the planned file covers it.
        planned = scope_skips.planned_scope_gate(self.text)
        anchor = "  checks-hooks:\n"
        self.assertEqual(planned.count(anchor), 1, "checks-hooks' header changed: this case must follow it")
        text = planned.replace(anchor, anchor + "    if: ${{ needs.scope.outputs.checks_macos == 'true' }}\n", 1)
        self.assertTrue(off_problems(text) or needs_problems(text), "a flag-reading job-level if on an unnamed job passes the rollup rules")


# The macOS gate (testing/scope_skips.py). A pull_request starts a macOS job only when one of its own flags is "true", and
# all-jobs-passed reads its skip as green only when scope-skips names the job and every flag it lists is "false" (check.sh).
CHECK_SH = os.path.join(HERE, "..", "actions", "all-jobs-passed", "check.sh")
# Each defect is one substring of the planned file, replaced by the defect. The wiring rule must add a problem for each.
SCOPE_SKIPS_DEFECTS = [
    ("the map drops shell-macos", '"shell-macos":["shell_macos"],', ""),
    ("the map gives shell-macos checks_macos", '"shell-macos":["shell_macos"]', '"shell-macos":["checks_macos"]'),
    ("the map drops sweep from checks-macos", '["checks_macos","sweep"]', '["checks_macos"]'),
    ("the map drops checks-macos-b", ',"checks-macos-b":["checks_macos"]', ""),
    ("the map names a job with no gate", '{"shell-macos"', '{"checks-hooks":["code"],"shell-macos"'),
    ("the map is not JSON", "scope-skips: '" + scope_skips.SCOPE_SKIPS_JSON + "'", "scope-skips: 'not json'"),
    ("shell-macos's gate reads checks_macos",
     "    if: ${{ github.event_name != 'push' && (needs.scope.outputs.shell_macos == 'true'",
     "    if: ${{ github.event_name != 'push' && (needs.scope.outputs.checks_macos == 'true'"),
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


class MacOsOnlyWhenScoped(unittest.TestCase):
    """(a) and (b): the scope flags decide whether a macOS job runs on a pull_request (its job-level if), and all-jobs-passed reads
    the skip as green through scope-skips. Each case reads the real checks.yml, so each is red until the change lands."""

    def setUp(self):
        with open(CHECKS, encoding="utf-8") as f:
            self.text = f.read()

    def job_if(self, name):
        expr = all_jobs(self.text).get(name, {}).get("if")
        self.assertIsNotNone(expr, f"{name} has no job-level if")
        return expr

    def test_a_pull_request_that_touches_no_macos_path_starts_no_macos_runner(self):
        # Named failure: a macOS job runs on a pull_request whose macOS flags are all off, or all-jobs-passed reads its skip as red.
        flags = scope_run(["README.md"])
        for flag in ("shell_macos", "checks_macos", "sweep"):  # scope first: a docs-only pull request sets no macOS flag
            self.assertEqual(flags[flag], "false", f"a docs-only pull request sets {flag}: {flags}")
        for name in MACOS_JOBS:
            values = {flag: flags[flag] for flag in scope_skips.MACOS_GATE[name]}
            with self.subTest(job=name):
                self.assertFalse(eval_with(self.job_if(name), "pull_request", values), f"{name} runs on a pull_request with flags {values}")
        # The same pull request as all-jobs-passed sees it: every needed job passed, and the three macOS jobs skipped.
        needs = {name: {"result": "success"} for name in needs_of(job_block(self.text, "all-jobs-passed"))}
        needs["scope"] = {"result": "success", "outputs": flags}
        for name in MACOS_JOBS:
            needs[name] = {"result": "skipped"}
        skips = scope_skips_input(self.text)
        self.assertIsNotNone(skips, "all-jobs-passed's action step has no scope-skips input: a skipped macOS job reads as red")
        code, out = check_sh(needs, skips)
        self.assertEqual(code, 0, f"all-jobs-passed refuses a pull request with no macOS path: exit {code}: {out}")

    def test_a_pull_request_that_changes_install_sh_runs_shell_macos(self):
        # Named failure: a pull_request that changes install.sh does not start shell-macos, or shell-macos runs with its flag off.
        flags = scope_run(["install.sh"])
        self.assertEqual(flags["shell_macos"], "true", f"install.sh does not set shell_macos: {flags}")  # scope first
        expr = self.job_if("shell-macos")
        self.assertTrue(eval_with(expr, "pull_request", {"shell_macos": "true"}),
                        f"shell-macos does not run on a pull_request that changes install.sh: {expr}")
        self.assertFalse(eval_with(expr, "pull_request", {"shell_macos": "false"}),
                         f"shell-macos runs on a pull_request with shell_macos off: {expr}")


class ScopeSkipsWiring(unittest.TestCase):
    """(h): the wiring rule reads each macOS gate and its scope-skips entry together. The planned file is checks.yml with the
    change applied (testing/scope_skips.py). The rules pass it once the change lands, and refuse it on the rules as they stand."""

    def setUp(self):
        with open(CHECKS, encoding="utf-8") as f:
            self.text = f.read()
        self.planned = scope_skips.planned_scope_gate(self.text)

    def test_the_planned_gate_and_its_scope_skips_entry_pass_the_wiring_rule(self):
        # Named failure: the wiring rule refuses a macOS gate that its scope-skips entry names, so all-jobs-passed cannot skip it.
        self.assertEqual(all_problems(self.planned), [])

    def test_the_wiring_rule_passes_the_checks_yml_on_disk(self):
        # Control: the file as it is passes the rules, so the planned file's problems belong to the change alone.
        self.assertEqual(all_problems(self.text), [])

    def test_the_planned_file_changes_only_the_gate_lines_and_the_input(self):
        # Control for the fixture: the comment and string lines of checks.yml (`# not a comment` inside quotes, a `#` in a
        # block body) come through unchanged. Every changed line is a macOS job's job-level if or the scope-skips input.
        changed = [line for line in difflib.unified_diff(self.text.split("\n"), self.planned.split("\n"), lineterm="", n=0)
                   if line[:1] in ("+", "-") and line[:3] not in ("+++", "---")]
        for line in changed:
            with self.subTest(line=line):
                gate = line[1:].startswith("    if: ${{ github.event_name != 'push'")
                self.assertTrue(gate or "scope-skips: '" in line, f"the planned file changes a line it should not: {line}")

    def test_a_scope_skips_entry_that_disagrees_with_a_macos_gate_is_flagged(self):
        # Named failure: the wiring rule passes a scope-skips entry that disagrees with the job-level if it names. A defect is
        # flagged when it adds a problem that the planned file does not have.
        clean = all_problems(self.planned)
        for label, old, new in SCOPE_SKIPS_DEFECTS:
            with self.subTest(defect=label):
                self.assertIn(old, self.planned, f"{label}: the mutation matches nothing, so it proves nothing")
                extra = [p for p in all_problems(self.planned.replace(old, new, 1)) if p not in clean]
                self.assertTrue(extra, f"{label}: the wiring rule passes it")

    def test_a_job_outside_scope_skips_that_keeps_a_job_level_if_is_flagged(self):
        # Control: a job that scope-skips does not name, with a job-level if, is refused, since all-jobs-passed would read its skip as red.
        anchor = "  checks-hooks:\n"
        self.assertEqual(self.planned.count(anchor), 1, "checks-hooks' header changed: this case must follow it")
        text = self.planned.replace(anchor, anchor + "    if: ${{ github.event_name != 'push' }}\n", 1)
        clean = all_problems(self.planned)
        self.assertTrue([p for p in all_problems(text) if p not in clean], "a job outside scope-skips with a job-level if passes the rules")


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


if __name__ == "__main__":
    unittest.main()
