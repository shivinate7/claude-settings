#!/usr/bin/env python3
"""The red run for actions/ci-done-comment, and for its caller in this repo's gates.yml.

A run with a red job must post one comment that names each red job. A green run, or one whose
only non-green jobs were skipped, must post nothing. The gates.yml caller must need every other
job and run when a job failed, or the comment fires before the run ends or never.
Run: python3 actions/ci-done-comment/test_comment.py
"""
import json
import os
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "comment.sh")
GATES = os.path.join(HERE, "..", "..", ".github", "workflows", "gates.yml")


def body(needs):
    env = dict(os.environ, NEEDS=json.dumps(needs), CI_DONE_DRY="1", PR="1", REPO="o/r",
               SHA="0123456789abcdef", RUN_URL="https://example/run")
    out = subprocess.run(["bash", SCRIPT], env=env, capture_output=True, text=True, check=True)
    return out.stdout


class Body(unittest.TestCase):
    def test_failed_job_is_named(self):
        got = body({"scope": {"result": "success"}, "gates-macos": {"result": "failure"}})
        self.assertIn("<!-- ci-done -->", got)
        self.assertIn("CI finished red on 0123456: gates-macos (failure).", got)
        self.assertIn("Run: https://example/run", got)
        self.assertNotIn("scope", got)

    def test_cancelled_job_is_named(self):
        # A job that hits its timeout-minutes cap ends cancelled. It is red, not quiet.
        got = body({"gates": {"result": "cancelled"}, "gates-windows": {"result": "failure"}})
        self.assertIn("gates (cancelled), gates-windows (failure)", got)

    def test_green_run_posts_nothing(self):
        got = body({"gates": {"result": "success"}, "gates-macos": {"result": "skipped"}})
        self.assertNotIn("ci-done", got)
        self.assertEqual(got.strip(), "No red job: no comment.")


class GatesCaller(unittest.TestCase):
    def setUp(self):
        try:
            import yaml
        except ImportError:
            if os.environ.get("CI"):
                raise
            self.skipTest("PyYAML not installed")
        with open(GATES, encoding="utf-8") as fh:
            self.jobs = yaml.safe_load(fh)["jobs"]

    def test_needs_every_other_job(self):
        job = self.jobs.get("ci-done")
        self.assertIsNotNone(job, "gates.yml has no ci-done job")
        others = sorted(k for k in self.jobs if k != "ci-done")
        self.assertEqual(sorted(job["needs"]), others, "ci-done must need every other job")

    def test_runs_after_a_red_job(self):
        job = self.jobs["ci-done"]
        cond = job.get("if", "")
        self.assertIn("!cancelled()", cond, "without !cancelled() the job skips when a needed job fails")
        self.assertIn("github.event_name == 'pull_request'", cond)
        self.assertIn("!github.event.pull_request.draft", cond)
        self.assertEqual(job.get("permissions", {}).get("pull-requests"), "write")
        step = next((s for s in job["steps"] if s.get("uses") == "$/actions/ci-done-comment"), None)
        self.assertIsNotNone(step, "ci-done does not call actions/ci-done-comment")
        self.assertEqual(step.get("with", {}).get("needs"), "${{ toJSON(needs) }}")


if __name__ == "__main__":
    unittest.main()
