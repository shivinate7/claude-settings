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
A child repo's workflow is checked with:  python3 lint/test_all_jobs_passed.py --workflow PATH
"""
import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from test_windows_split import CHECKS, ALL_JOBS_PASSED_JOB, all_jobs, eval_if, shard_base, yaml_scalar  # noqa: E402  the one home of the scope condition and scalar parsers
from workflow_steps import job_block, step_blocks, step_key  # noqa: E402  the one home of the step parser
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  test-temp-standard: teardown removes the run folder (testing/tracked_tree.py)

ALL_JOBS_PASSED_USES = "$/actions/all-jobs-passed"
ALL_JOBS_PASSED_IF = "${{ always() && github.event_name == 'pull_request' && !github.event.pull_request.draft }}"
ALL_JOBS_PASSED_RUNS_ON = "ubuntu-latest"
TO_JSON = "${{ toJSON(needs) }}"
FAN_IN = "ci-done"  # comments on a red run; it needs all-jobs-passed, and all-jobs-passed never needs it
CHECKOUT_PIN = re.compile(r"actions/checkout@[0-9a-f]{40}")


def job_key(block, key):
    """A job-level key's value (4 spaces under the job), comment removed, or None when the job lacks the key."""
    m = re.search(rf"^    {re.escape(key)}:[ \t]*(.*?)[ \t]*$", block or "", re.M)
    return yaml_scalar(m.group(1)) if m else None


def steps_part(block):
    """A job block from its `steps:` key on, so a block-list needs is never read as steps."""
    m = re.search(r"^    steps:[ \t]*$", block or "", re.M)
    return block[m.end():] if m else ""


def step_with(step, key):
    """A step's `with:` value (10 spaces under the step), comment removed, or None."""
    m = re.search(rf"^          {re.escape(key)}:[ \t]*(.*?)[ \t]*$", step, re.M)
    return yaml_scalar(m.group(1)) if m else None


def needs_of(block):
    """The job names a job block needs: a flow list, one scalar, or a block list. Comment lines are skipped.
    None when the block has no needs key."""
    m = re.search(r"^    needs:[ \t]*(.*?)[ \t]*$", block or "", re.M)
    if not m:
        return None
    inline = yaml_scalar(m.group(1))
    if inline.startswith("["):
        return [yaml_scalar(n) for n in inline.strip("[]").split(",") if n.strip()]
    if inline:
        return [inline]
    names = []
    for line in block[m.end():].split("\n"):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        item = re.match(r"^      - (.*)$", line)
        if not item:
            break
        names.append(yaml_scalar(item.group(1)))
    return names


def split_jobs(text):
    """(needed, off, problems) over the jobs of checks.yml. A job is off all-jobs-passed when its job-level if is false on a
    non-draft pull_request with every scope flag true. all-jobs-passed and ci-done are neither needed nor off."""
    needed, off, problems = [], [], []
    for name, job in all_jobs(text).items():
        if name in (ALL_JOBS_PASSED_JOB, FAN_IN):
            continue
        if job["if"] is None:
            needed.append(name)
            continue
        try:
            on = eval_if(yaml_scalar(job["if"]), "pull_request", "true")
        except Exception as ex:  # an if this reader cannot evaluate counts as needed, and is named
            problems.append(f"{name}: job-level if is unreadable ({ex!r}): {job['if']}")
            on = True
        (needed if on else off).append(name)
    return sorted(needed), sorted(off), problems


def shape_problems(text):
    """The all-jobs-passed job: no name (its job key is the required check's name), ubuntu-latest, a timeout, and the exact if."""
    block = job_block(text, ALL_JOBS_PASSED_JOB)
    if block is None:
        return [f"no {ALL_JOBS_PASSED_JOB} job in checks.yml"]
    problems = []
    if re.search(r"^    name:", block, re.M):
        problems.append(f"{ALL_JOBS_PASSED_JOB} sets name:, but its job key is the required check's name")
    if job_key(block, "runs-on") != ALL_JOBS_PASSED_RUNS_ON:
        problems.append(f"{ALL_JOBS_PASSED_JOB} runs on {job_key(block, 'runs-on')}, want {ALL_JOBS_PASSED_RUNS_ON}")
    if not (job_key(block, "timeout-minutes") or "").isdigit():
        problems.append(f"{ALL_JOBS_PASSED_JOB} has no timeout-minutes number: {job_key(block, 'timeout-minutes')!r}")
    if job_key(block, "if") != ALL_JOBS_PASSED_IF:
        problems.append(f"{ALL_JOBS_PASSED_JOB} if is {job_key(block, 'if')}, want {ALL_JOBS_PASSED_IF}")
    return problems


def needs_problems(text):
    """all-jobs-passed needs each job that runs on a non-draft PR once, and nothing else: not a shard, not ci-done."""
    block = job_block(text, ALL_JOBS_PASSED_JOB)
    if block is None:
        return [f"no {ALL_JOBS_PASSED_JOB} job in checks.yml"]
    needed, _, problems = split_jobs(text)
    got = needs_of(block)
    if got is None:
        return problems + [f"{ALL_JOBS_PASSED_JOB} has no needs key"]
    if not needed:
        problems.append("the reader derived no needed job: an empty match would prove nothing")
    if FAN_IN in got:
        problems.append(f"{ALL_JOBS_PASSED_JOB} needs {FAN_IN}, which needs it: a cycle")
    if len(set(got)) != len(got):
        problems.append(f"{ALL_JOBS_PASSED_JOB} lists a job twice: {sorted(got)}")
    if sorted(set(got)) != needed:
        problems.append(f"{ALL_JOBS_PASSED_JOB} needs differ from the jobs that run on a PR: "
                        f"missing {sorted(set(needed) - set(got))}, extra {sorted(set(got) - set(needed))}")
    return problems


def steps_problems(text):
    """all-jobs-passed's steps in order: a checkout pinned to a commit with persist-credentials false, then the action fed
    toJSON(needs)."""
    block = job_block(text, ALL_JOBS_PASSED_JOB)
    if block is None:
        return [f"no {ALL_JOBS_PASSED_JOB} job in checks.yml"]
    steps = step_blocks(steps_part(block))
    if len(steps) != 2:
        return [f"{ALL_JOBS_PASSED_JOB} has {len(steps)} steps, want 2: a pinned checkout, then the action"]
    checkout, fan = steps
    problems = []
    uses = yaml_scalar(step_key(checkout, "uses") or "")
    if not CHECKOUT_PIN.fullmatch(uses):
        problems.append(f"all-jobs-passed's checkout is not pinned to a commit: {uses!r}")
    if step_with(checkout, "persist-credentials") != "false":
        problems.append("all-jobs-passed's checkout keeps its token: persist-credentials must be false")
    if yaml_scalar(step_key(fan, "uses") or "") != ALL_JOBS_PASSED_USES:
        problems.append(f"the second step uses {step_key(fan, 'uses')}, want {ALL_JOBS_PASSED_USES}")
    if step_with(fan, "needs") != TO_JSON:
        problems.append(f"the action gets needs {step_with(fan, 'needs')!r}, want {TO_JSON}")
    return problems


def off_problems(text):
    """Only a shard job may stay off all-jobs-passed. A needed job has no job-level if, except scope (its draft rule)."""
    jobs = all_jobs(text)
    needed, off, problems = split_jobs(text)
    for name in off:
        if not shard_base(name):
            problems.append(f"{name} is off all-jobs-passed but is not a shard: its job-level if skips it on a PR")
    for name in needed:
        if shard_base(name):
            problems.append(f"shard {name} is in all-jobs-passed's needs: a shard runs only off pull_request")
        elif name != "scope" and jobs[name]["if"] is not None:
            problems.append(f"{name} is needed and keeps a job-level if: all-jobs-passed reads its skip as red, "
                            "so its scope condition belongs in its steps")
    return problems


def scope_if_problems(text):
    """scope skips a draft PR and runs everywhere else, so all-jobs-passed (which needs it) is skipped on a draft only."""
    job = all_jobs(text).get("scope")
    if job is None or job["if"] is None:
        return ["scope has no if: a draft PR would run every job"]
    expr = yaml_scalar(job["if"])
    try:
        problems = []
        if not eval_if(expr, "pull_request", "true", draft=False):
            problems.append("scope skips a ready PR")
        if eval_if(expr, "pull_request", "true", draft=True):
            problems.append("scope runs on a draft PR")
        if not eval_if(expr, "push", "false"):
            problems.append("scope skips a push")
        return problems
    except Exception as ex:
        return [f"scope if is unreadable ({ex!r}): {expr}"]


def ci_done_problems(text):
    """ci-done needs all-jobs-passed, so a red all-jobs-passed posts the comment."""
    block = job_block(text, FAN_IN)
    if block is None:
        return [f"no {FAN_IN} job in checks.yml"]
    if ALL_JOBS_PASSED_JOB not in (needs_of(block) or []):
        return [f"{FAN_IN} does not need {ALL_JOBS_PASSED_JOB}: a red all-jobs-passed would post no comment"]
    return []


def all_problems(text):
    return (shape_problems(text) + needs_problems(text) + steps_problems(text) + off_problems(text)
            + scope_if_problems(text) + ci_done_problems(text))


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
    """(exit code, output) of `--workflow` on one child workflow. The file is written into this run's folder."""
    folder = tempfile.mkdtemp(prefix="allpassed-", dir=RUN_FOLDER)
    path = os.path.join(folder, "checks.yml")
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    done = subprocess.run([sys.executable, os.path.abspath(__file__), "--workflow", path], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=120)
    return done.returncode, done.stdout + done.stderr


class ChildWorkflow(unittest.TestCase):
    """The child cases call the script's CLI and assert its exit code first. On a script without the flag the exit is 2
    (usage), so each case fails there before it reaches an in-process check."""

    def test_the_cs_rules_reject_a_valid_child(self):
        # Green control, and the gap this lane closes: the cs rules flag a child that passes the generic rules.
        self.assertTrue(all_problems(CHILD_GOOD), "the cs rules pass a valid child: the gap is closed or the cs rules changed")

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


if __name__ == "__main__":
    unittest.main()
