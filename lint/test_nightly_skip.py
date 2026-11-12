#!/usr/bin/env python3
"""Tests for .github/scripts/nightly-skip.py, the step that lets the nightly run skip.

The gate writes skip=true to $GITHUB_OUTPUT only when main's head has a successful push run of checks.yml
AND the newest completed schedule run of checks.yml succeeded. Any read failure writes skip=false and says
"unknown". RUNS_JSON is the stand-in for the runs read: a JSON list of run records in the shape of the
Actions runs API. The test never reaches the network.

    python3 lint/test_nightly_skip.py
"""
import json
import os
import shutil
import subprocess
import sys
import unittest
import uuid

import _test_temp  # noqa: E402  test-temp-standard: every temp path comes from this run's folder

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP = os.path.join(ROOT, ".github", "scripts", "nightly-skip.py")
RUN_FOLDER = _test_temp.run_folder()  # one run folder per test run; teardown removes it

WORKFLOW = ".github/workflows/checks.yml"
HEAD = "1" * 40  # main's head, the sha the gate is asked about
OTHER = "2" * 40
OLDER = "2026-11-09T03:17:00Z"
NEWER = "2026-11-11T03:17:00Z"
SKIP_MISSING = "nightly-skip.py is missing at .github/scripts/nightly-skip.py, so no gate decides the nightly skip"


def run(event, sha=HEAD, conclusion="success", created=NEWER, status="completed", path=WORKFLOW, branch="main"):
    """One run record in the shape of the Actions runs API."""
    return {"path": path, "event": event, "status": status, "conclusion": conclusion,
            "head_sha": sha, "head_branch": branch, "created_at": created}


def decide(runs=None, raw=None, head=HEAD, token=None):
    """Run the gate once on a stand-in read. Returns (exit code, the one skip value or None, printed text)."""
    out = os.path.join(RUN_FOLDER, "output-%s" % uuid.uuid4().hex)
    env = {k: v for k, v in os.environ.items()
           if k not in ("RUNS_JSON", "GH_TOKEN", "REPO", "HEAD_SHA", "GITHUB_OUTPUT")}
    env["GITHUB_OUTPUT"] = out
    env["REPO"] = "owner/repo"
    if raw is not None:
        env["RUNS_JSON"] = raw
    elif runs is not None:
        env["RUNS_JSON"] = json.dumps(runs)
    if head is not None:
        env["HEAD_SHA"] = head
    if token is not None:
        env["GH_TOKEN"] = token
    done = subprocess.run([sys.executable, SKIP], env=env, capture_output=True, text=True, timeout=60)
    skips = []
    if os.path.isfile(out):
        with open(out, encoding="utf-8") as f:
            skips = [line.strip()[len("skip="):] for line in f if line.startswith("skip=")]
    value = skips[0] if len(skips) == 1 else None
    return done.returncode, value, done.stdout + done.stderr


class NightlySkip(unittest.TestCase):
    def nightly_skip(self, **kwargs):
        self.assertTrue(os.path.isfile(SKIP), SKIP_MISSING)
        rc, value, text = decide(**kwargs)
        self.assertEqual(rc, 0, "the gate exits %d, so the nightly job fails on the gate: %s" % (rc, text[-300:]))
        return value, text

    def test_skip_true_when_main_has_a_green_push_run_and_the_newest_nightly_is_green(self):
        value, _ = self.nightly_skip(runs=[run("schedule", created=OLDER), run("push"), run("schedule")])
        self.assertEqual(value, "true", "a green push run on main and a green newest nightly must give skip=true")

    def test_skip_false_when_the_newest_nightly_failed(self):
        value, _ = self.nightly_skip(runs=[run("push"), run("schedule", created=OLDER), run("schedule", conclusion="failure")])
        self.assertEqual(value, "false", "a failed newest nightly must give skip=false")

    def test_the_newest_nightly_is_picked_by_created_time_not_by_list_order(self):
        value, _ = self.nightly_skip(runs=[run("schedule", conclusion="failure", created=NEWER), run("push"),
                                   run("schedule", created=OLDER)])
        self.assertEqual(value, "false", "the newest nightly by created_at failed, so skip=false, whatever the list order")

    def test_skip_false_when_the_push_run_is_for_another_sha(self):
        value, _ = self.nightly_skip(runs=[run("push", sha=OTHER), run("schedule")])
        self.assertEqual(value, "false", "a green push run for another sha is not main's head, so skip=false")

    def test_skip_false_when_the_push_run_on_main_failed(self):
        value, _ = self.nightly_skip(runs=[run("push", conclusion="failure"), run("schedule")])
        self.assertEqual(value, "false", "a failed push run on main must give skip=false")

    def test_skip_false_when_the_push_run_is_not_on_main(self):
        value, _ = self.nightly_skip(runs=[run("push", branch="ci-batch"), run("schedule")])
        self.assertEqual(value, "false", "a push run on another branch is not main's push run, so skip=false")

    def test_skip_false_when_the_green_push_run_is_another_workflow(self):
        value, _ = self.nightly_skip(runs=[run("push", path=".github/workflows/other.yml"), run("schedule")])
        self.assertEqual(value, "false", "a green push run of another workflow is not checks.yml, so skip=false")

    def test_an_in_progress_nightly_is_not_the_newest_completed_run(self):
        value, _ = self.nightly_skip(runs=[run("push"), run("schedule", created=OLDER),
                                   run("schedule", status="in_progress", conclusion=None, created=NEWER)])
        self.assertEqual(value, "true", "an in-progress nightly is not completed, so the older green one decides")

    def test_skip_false_when_no_nightly_has_completed(self):
        value, _ = self.nightly_skip(runs=[run("push"), run("schedule", status="in_progress", conclusion=None)])
        self.assertEqual(value, "false", "with no completed nightly the gate has no green nightly, so skip=false")

    def test_skip_false_on_an_empty_run_list(self):
        value, _ = self.nightly_skip(runs=[])
        self.assertEqual(value, "false", "an empty run list has no push run on main, so skip=false")

    def test_full_size_list_with_the_green_push_run_and_nightly_gives_skip_true(self):
        full = [run("pull_request", sha=OTHER, created=OLDER) for _ in range(98)]
        value, _ = self.nightly_skip(runs=full + [run("push"), run("schedule")])
        self.assertEqual(value, "true", "a hundred-run list that holds the green push run and nightly must give skip=true")

    def test_full_size_list_without_a_green_push_run_on_main_gives_skip_false(self):
        full = [run("pull_request", sha=OTHER, created=OLDER) for _ in range(99)]
        value, _ = self.nightly_skip(runs=full + [run("schedule")])
        self.assertEqual(value, "false", "a hundred-run list with no push run on main must give skip=false")

    def test_a_read_that_is_not_json_gives_skip_false_and_says_unknown(self):
        value, text = self.nightly_skip(raw="not json")
        self.assertEqual(value, "false", "a read that fails must give skip=false")
        self.assertIn("unknown", text.lower(), "a read that fails must say unknown")

    def test_a_read_that_is_not_a_list_gives_skip_false_and_says_unknown(self):
        value, text = self.nightly_skip(raw='{"workflow_runs": []}')
        self.assertEqual(value, "false", "a runs read of the wrong shape must give skip=false")
        self.assertIn("unknown", text.lower(), "a runs read of the wrong shape must say unknown")

    def test_no_head_sha_gives_skip_false_and_says_unknown(self):
        value, text = self.nightly_skip(runs=[run("push"), run("schedule")], head=None)
        self.assertEqual(value, "false", "without a head sha the gate cannot judge main, so skip=false")
        self.assertIn("unknown", text.lower(), "without a head sha the gate must say unknown")

    def test_no_stand_in_and_no_token_gives_skip_false_and_says_unknown(self):
        value, text = self.nightly_skip(token=None)
        self.assertEqual(value, "false", "with no runs read and no token the gate must give skip=false")
        self.assertIn("unknown", text.lower(), "with no runs read and no token the gate must say unknown")


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


if __name__ == "__main__":
    unittest.main()
