#!/usr/bin/env python3
"""Pins for the Windows rest split and the Windows full shards on a ready pull request (R62, step ci-linux-windows-once).

checks-windows-rest runs in two or three parallel jobs, each capped at a provisional 60 minutes, and all-jobs-passed and
ci-done need every one of them. The Windows full shards run on a ready pull request, so the batch PR run carries them, and a
draft pull request runs none. No held shard is dropped, and each rest command runs in one job.

    python3 lint/test_windows_rest_split.py
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_windows_split import CHECKS, all_jobs, eval_if  # noqa: E402  the one home of the checks.yml reader
from all_jobs_passed_rules import needs_of  # noqa: E402  the one home of the needs reader
from workflow_steps import job_block  # noqa: E402  the one home of the job parser

REST_PREFIX = "checks-windows-rest"
ALL_JOBS_PASSED = "all-jobs-passed"
CI_DONE = "ci-done"
PROVISIONAL_CAP = 60
# The Windows full shards that must stay in checks.yml. The held-shard case fails if one is dropped, which would leave its untagged cases unrun.
HELD_SHARDS = ("checks-windows-guard-2", "checks-windows-guard-3", "checks-windows-merge-2", "checks-windows-merge-3",
               "checks-windows-merge-4", "checks-windows-merge-5")


class WindowsRestSplit(unittest.TestCase):
    def setUp(self):
        with open(CHECKS, encoding="utf-8") as f:
            self.text = f.read()
        self.jobs = all_jobs(self.text)
        self.rest = sorted(name for name in self.jobs if name.startswith(REST_PREFIX))

    def test_the_windows_rest_suites_run_in_two_or_three_parallel_jobs(self):
        self.assertIn(len(self.rest), (2, 3), f"the Windows rest suites run in {self.rest}, want two or three parallel jobs")

    def test_each_windows_rest_job_has_a_provisional_sixty_minute_cap(self):
        for name in self.rest:
            block = job_block(self.text, name)
            m = re.search(r"^    timeout-minutes:\s*(\d+)", block, re.M)
            self.assertIsNotNone(m, f"{name} has no timeout-minutes cap")
            self.assertEqual(int(m.group(1)), PROVISIONAL_CAP,
                             f"{name} is capped at {m.group(1)} minutes, want the provisional {PROVISIONAL_CAP}")
            self.assertIn("# provisional", block, f"{name} has a cap with no `# provisional` marker")

    def test_each_rest_command_runs_in_one_windows_rest_job(self):
        runs = [st["run"] for name in self.rest for st in self.jobs[name]["steps"] if "run" in st]
        repeated = sorted({run for run in runs if runs.count(run) > 1})
        self.assertEqual(repeated, [], f"these Windows rest commands run in more than one job: {repeated}")

    def test_all_jobs_passed_and_ci_done_need_every_windows_rest_job(self):
        for fan_in in (ALL_JOBS_PASSED, CI_DONE):
            needs = needs_of(job_block(self.text, fan_in)) or []
            for name in self.rest:
                self.assertIn(name, needs, f"{fan_in} does not need {name}, so that job's result is not in the verdict")

    def test_every_held_windows_full_shard_is_still_in_checks_yml(self):
        for name in HELD_SHARDS:
            self.assertIn(name, self.jobs, f"{name} is missing: the Windows full shards are held, not dropped")

    def test_each_held_windows_full_shard_runs_on_a_ready_pull_request(self):
        for name in HELD_SHARDS:
            expr = self.jobs.get(name, {}).get("if")
            self.assertIsNotNone(expr, f"{name} has no job-level if, so it cannot be held to a ready pull request")
            self.assertTrue(eval_if(expr, "pull_request", "true", draft=False),
                            f"{name} does not run on a ready pull request: if {expr}")

    def test_a_draft_pull_request_runs_no_held_windows_full_shard(self):
        for name in HELD_SHARDS:
            expr = self.jobs.get(name, {}).get("if")
            self.assertIsNotNone(expr, f"{name} has no job-level if, so it would run on a draft pull request")
            self.assertFalse(eval_if(expr, "pull_request", "true", draft=True),
                             f"{name} runs on a draft pull request: if {expr}")


if __name__ == "__main__":
    unittest.main()
