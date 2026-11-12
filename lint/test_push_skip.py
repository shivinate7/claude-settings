#!/usr/bin/env python3
"""Tests for .github/scripts/push-skip.py, the decision that lets a push to main skip the checks its tree already passed.

The script writes skip=true to $GITHUB_OUTPUT only when the push commit's tree equals the tree of a batch-* pull request
head whose checks run concluded success. Any read failure writes skip=false and says "unknown". Two stand-ins drive it,
never the network: PUSH_TREE, the push commit's tree sha, and PRS_JSON, a JSON list of the batch pull request heads, each
{"head_branch", "tree", "status", "conclusion"}. The live read uses GH_TOKEN and REPO.

The wiring cases read checks.yml: the push-skip job decides in a step with id decide, outputs skip, is push-only, and scope
needs it, so every other job skips through needs as nightly-skip does for scope.

    python3 lint/test_push_skip.py
"""
import json
import os
import shutil
import subprocess
import sys
import unittest
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _test_temp  # noqa: E402  test-temp-standard: every temp path comes from this run's folder
from test_windows_split import CHECKS, all_jobs, eval_if  # noqa: E402  the one home of the checks.yml reader
from all_jobs_passed_rules import needs_of  # noqa: E402  the one home of the needs reader
from workflow_steps import job_block  # noqa: E402  the one home of the job parser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUSH_SKIP = os.path.join(ROOT, ".github", "scripts", "push-skip.py")
RUN_FOLDER = _test_temp.run_folder()  # one run folder per test run; teardown removes it

JOB = "push-skip"
TREE = "a" * 40  # the push commit's tree
OTHER_TREE = "b" * 40
BATCH = "batch-lane-x"
SCRIPT_MISSING = "push-skip.py is missing at .github/scripts/push-skip.py, so no decision sets the push skip"


def pr(tree=TREE, branch=BATCH, conclusion="success", status="completed"):
    """One batch pull request head in the shape the stand-in read carries."""
    return {"head_branch": branch, "tree": tree, "status": status, "conclusion": conclusion}


def decide(prs=None, raw=None, tree=TREE, token=None):
    """Run the script once on the stand-ins. Returns (exit code, the one skip value or None, printed text)."""
    out = os.path.join(RUN_FOLDER, "output-%s" % uuid.uuid4().hex)
    env = {k: v for k, v in os.environ.items() if k not in ("PUSH_TREE", "PRS_JSON", "GH_TOKEN", "REPO", "GITHUB_OUTPUT")}
    env["GITHUB_OUTPUT"] = out
    env["REPO"] = "owner/repo"
    if tree is not None:
        env["PUSH_TREE"] = tree
    if raw is not None:
        env["PRS_JSON"] = raw
    elif prs is not None:
        env["PRS_JSON"] = json.dumps(prs)
    if token is not None:
        env["GH_TOKEN"] = token
    done = subprocess.run([sys.executable, PUSH_SKIP], env=env, capture_output=True, text=True, timeout=60)
    skips = []
    if os.path.isfile(out):
        with open(out, encoding="utf-8") as f:
            skips = [line.strip()[len("skip="):] for line in f if line.startswith("skip=")]
    value = skips[0] if len(skips) == 1 else None
    return done.returncode, value, done.stdout + done.stderr


class PushSkipDecision(unittest.TestCase):
    def skip_value(self, **kwargs):
        self.assertTrue(os.path.isfile(PUSH_SKIP), SCRIPT_MISSING)
        rc, value, text = decide(**kwargs)
        self.assertEqual(rc, 0, "the script exits %d, so the push job fails on the decision: %s" % (rc, text[-300:]))
        return value, text

    def test_skip_true_when_the_push_tree_equals_a_green_batch_pull_request_head(self):
        value, _ = self.skip_value(prs=[pr()])
        self.assertEqual(value, "true", "a batch head with the push's tree and a green run must give skip=true")

    def test_skip_false_when_the_tree_differs(self):
        value, _ = self.skip_value(prs=[pr(tree=OTHER_TREE)])
        self.assertEqual(value, "false", "a batch head with another tree does not cover the push, so skip=false")

    def test_skip_false_when_the_matching_batch_run_failed(self):
        value, _ = self.skip_value(prs=[pr(conclusion="failure")])
        self.assertEqual(value, "false", "a red batch run with the push's tree must give skip=false")

    def test_skip_false_when_the_matching_batch_run_is_in_progress(self):
        value, _ = self.skip_value(prs=[pr(status="in_progress", conclusion=None)])
        self.assertEqual(value, "false", "an in-progress batch run is not a green run yet, so skip=false")

    def test_skip_false_when_the_matching_head_is_not_an_integration_branch(self):
        value, _ = self.skip_value(prs=[pr(branch="lane-x")])
        self.assertEqual(value, "false", "a lone lane's head is not a batch head, so skip=false")

    def test_skip_false_on_an_empty_pull_request_list(self):
        value, _ = self.skip_value(prs=[])
        self.assertEqual(value, "false", "an empty list has no batch head with the push's tree, so skip=false")

    def test_skip_true_in_a_full_size_list_that_holds_the_matching_green_head(self):
        full = [pr(tree=OTHER_TREE) for _ in range(99)] + [pr()]
        value, _ = self.skip_value(prs=full)
        self.assertEqual(value, "true", "a hundred-head list that holds the matching green head must give skip=true")

    def test_skip_false_in_a_full_size_list_with_no_matching_head(self):
        full = [pr(tree=OTHER_TREE) for _ in range(100)]
        value, _ = self.skip_value(prs=full)
        self.assertEqual(value, "false", "a hundred-head list with no matching tree must give skip=false")

    def test_a_read_that_is_not_json_gives_skip_false_and_says_unknown(self):
        value, text = self.skip_value(raw="not json")
        self.assertEqual(value, "false", "a read that fails must give skip=false")
        self.assertIn("unknown", text.lower(), "a read that fails must say unknown")

    def test_no_push_tree_gives_skip_false_and_says_unknown(self):
        value, text = self.skip_value(prs=[pr()], tree=None)
        self.assertEqual(value, "false", "without the push's tree the script cannot compare, so skip=false")
        self.assertIn("unknown", text.lower(), "without the push's tree the script must say unknown")

    def test_no_stand_in_and_no_token_gives_skip_false_and_says_unknown(self):
        value, text = self.skip_value(token=None)
        self.assertEqual(value, "false", "with no pull request read and no token the script must give skip=false")
        self.assertIn("unknown", text.lower(), "with no pull request read and no token the script must say unknown")


class PushSkipWiring(unittest.TestCase):
    def setUp(self):
        with open(CHECKS, encoding="utf-8") as f:
            self.text = f.read()
        self.jobs = all_jobs(self.text)

    def test_push_skip_is_a_job_that_runs_on_push_and_not_on_pull_request(self):
        expr = self.jobs.get(JOB, {}).get("if")
        self.assertIsNotNone(expr, f"checks.yml has no {JOB} job with a job-level if")
        self.assertTrue(eval_if(expr, "push", "", draft=False), f"{JOB} does not run on push: if {expr}")
        self.assertFalse(eval_if(expr, "pull_request", "", draft=False), f"{JOB} runs on pull_request: if {expr}")

    def test_push_skip_decides_in_a_step_with_id_decide_and_outputs_skip(self):
        block = job_block(self.text, JOB) or ""
        self.assertIn("id: decide", block, f"{JOB} has no step with id decide")
        self.assertIn("skip: ${{ steps.decide.outputs.skip }}", block, f"{JOB} does not output skip from steps.decide")

    def test_push_skip_has_a_timeout_cap_and_read_only_permissions(self):
        block = job_block(self.text, JOB) or ""
        self.assertIn("timeout-minutes:", block, f"{JOB} has no timeout-minutes cap")
        self.assertIn("contents: read", block, f"{JOB} does not restate contents: read")

    def test_scope_needs_push_skip_so_a_skipped_push_skips_every_job_through_needs(self):
        needs = needs_of(job_block(self.text, "scope")) or []
        self.assertIn(JOB, needs, f"scope does not need {JOB}, so a matching push would not skip the other jobs")


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


if __name__ == "__main__":
    unittest.main()
