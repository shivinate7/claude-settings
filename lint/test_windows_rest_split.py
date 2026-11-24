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
from test_windows_split import (CHECKS, RECORDS_ONLY_CONDITION, SPEC_JOBS, SUITE_CONDITIONED_JOBS, all_jobs, eval_if,  # noqa: E402  the one home of the checks.yml reader
                                condition_problem, job_if_without_records, spec_conditioned, suite_names)
from all_jobs_passed_rules import needs_of  # noqa: E402  the one home of the needs reader
from test_windows_split import SUITE_FLAG, WINDOWS_GUARD_JOBS, WINDOWS_MERGE_JOBS, eval_with  # noqa: E402  the one home of the merge and rest flags, the shard families and the flag evaluator
from workflow_steps import job_block  # noqa: E402  the one home of the job parser

REST_PREFIX = "checks-windows-rest"
ALL_JOBS_PASSED = "all-jobs-passed"
CI_DONE = "ci-done"
PROVISIONAL_CAP = 60
# The Windows full shards that must stay in checks.yml: every shard past the first of the guard and merge families (SHARD_COUNTS).
# The held-shard case fails if one is dropped, which would leave its untagged cases unrun.
HELD_SHARDS = WINDOWS_GUARD_JOBS[1:] + WINDOWS_MERGE_JOBS[1:]
SKIP_EVENTS = ("push", "pull_request", "schedule", "workflow_dispatch")


def if_with_condition(raw, value, event, flag, draft=False):
    """eval_if of a step's raw if: with records_only_skip set to `value` and every other scope output set to `flag`. None is no
    if:, which GitHub reads as success(). eval_if sets every scope output to one value, so records_only_skip is pinned first."""
    pinned = (raw if raw is not None else "success()").replace("needs.scope.outputs.records_only_skip", repr(value))
    return eval_if(pinned, event, flag, draft=draft)


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
            self.assertTrue(eval_if(job_if_without_records(expr), "pull_request", "true", draft=False),
                            f"{name} does not run on a ready pull request: if {expr}")

    def test_a_draft_pull_request_runs_no_held_windows_full_shard(self):
        for name in HELD_SHARDS:
            expr = self.jobs.get(name, {}).get("if")
            self.assertIsNotNone(expr, f"{name} has no job-level if, so it would run on a draft pull request")
            self.assertFalse(eval_if(job_if_without_records(expr), "pull_request", "true", draft=True),
                             f"{name} runs on a draft pull request: if {expr}")


class RecordsOnlySkipCondition(unittest.TestCase):
    """The records-only skip's condition, read off checks.yml. The scope job declares the output. Each run step the spec conditions ends in
    the condition, is off when the condition is shut, and runs as today when it is open. A run step the spec does not condition carries no condition."""

    def setUp(self):
        with open(CHECKS, encoding="utf-8") as f:
            self.text = f.read()
        self.jobs = all_jobs(self.text)

    def run_steps(self, name):
        """The `run:` steps of job `name`. A job that is missing, or has no run step, fails here, by name."""
        self.assertIn(name, self.jobs, f"{name} is not a job in checks.yml")
        runs = [st for st in self.jobs[name]["steps"] if "run" in st]
        self.assertTrue(runs, f"{name} has no run step, so the condition has nothing to check")
        return runs

    def conditioned_steps(self):
        """(job, step) for each run step the spec conditions (spec_conditioned): every run step of CONDITIONED_JOBS, and each run step of
        SUITE_CONDITIONED_JOBS that runs a suite. A suite job that runs no suite fails here, by name."""
        out = []
        for name in SPEC_JOBS:
            suites = suite_names(self.text, name)
            if name in SUITE_CONDITIONED_JOBS:
                self.assertTrue(suites, f"{name} runs no suite, so the condition has nothing to check")
            out += [(name, st) for st in self.run_steps(name) if spec_conditioned(name, st, suites)]
        return out

    def unconditioned_steps(self):
        """(job, step) for each run step the spec does not condition: each run step of SUITE_CONDITIONED_JOBS that runs no suite."""
        out = []
        for name in SUITE_CONDITIONED_JOBS:
            suites = suite_names(self.text, name)
            out += [(name, st) for st in self.run_steps(name) if not spec_conditioned(name, st, suites)]
        return out

    def test_the_scope_job_declares_the_records_only_skip_output(self):
        block = job_block(self.text, "scope")
        self.assertIsNotNone(block, "checks.yml has no scope job")
        m = re.search(r"^      records_only_skip:[ \t]*(.*?)[ \t]*$", block, re.M)
        self.assertIsNotNone(m, "the scope job declares no records_only_skip output, so the condition reads an empty value")
        self.assertIn("steps.scope.outputs.records_only_skip", m.group(1),
                      f"the scope job's records_only_skip output reads {m.group(1)!r}, not steps.scope.outputs.records_only_skip")

    def test_each_conditioned_run_step_ends_in_the_condition(self):
        for name, st in self.conditioned_steps():
            label = st.get("name") or st["run"]
            with self.subTest(job=name, step=label):
                problem = condition_problem(name, st)
                self.assertIsNone(problem, problem)

    def test_each_unconditioned_run_step_carries_no_condition(self):
        for name, st in self.unconditioned_steps():
            label = st.get("name") or st["run"]
            with self.subTest(job=name, step=label):
                self.assertNotIn(RECORDS_ONLY_CONDITION, st.get("if") or "",
                                 f"{name} / {label} carries the records-only condition, which the spec does not give this step")

    def test_the_condition_turns_each_conditioned_run_step_off_on_every_event(self):
        for name, st in self.conditioned_steps():
            label = st.get("name") or st["run"]
            with self.subTest(job=name, step=label):
                runs_on = [f"{ev} flags={fl} draft={dr}" for ev in SKIP_EVENTS for fl in ("true", "false") for dr in (False, True)
                           if if_with_condition(st.get("if"), "true", ev, fl, draft=dr)]
                self.assertEqual(runs_on, [], f"{name} / {label} still runs with records_only_skip true: {runs_on}")

    # The control: with the condition open, each step runs as it does today on a ready pull request, a push, a schedule and a dispatch.
    def test_each_conditioned_run_step_still_runs_when_the_condition_is_open(self):
        for name, st in self.conditioned_steps():
            label = st.get("name") or st["run"]
            with self.subTest(job=name, step=label):
                skipped = [ev for ev in ("push", "schedule", "workflow_dispatch", "pull_request")
                           if not if_with_condition(st.get("if"), "false", ev, "true")]
                self.assertEqual(skipped, [], f"{name} / {label} does not run with the condition open on: {skipped}")


# Each merge and rest suite step reads its job's own scope flag, the step-level gate the gated
# Windows jobs use. checks-windows quotes it on its checkout:
#   if: ${{ needs.scope.outputs.checks_windows == 'true' || github.event_name != 'pull_request' }}
# So with the flag false a ready pull_request skips the step, and push, schedule and dispatch keep their rules. Each job still runs, so its
# result is success and all-jobs-passed reads it as a pass (lint/test_all_jobs_passed.py).
def suite_steps(job):
    return [st for st in job["steps"] if "run" in st]


def runs_flagged(job, st, values, default):
    """True when step `st` of `job` runs on a ready pull_request, with the scope outputs in `values` and `default` for every other one:
    the job's own if first, then the step's."""
    if job["if"] is not None and not eval_with(job["if"], "pull_request", values, default=default):
        return False
    return st.get("if") is None or eval_with(st["if"], "pull_request", values, default=default)


class MergeAndRestScopeFlags(unittest.TestCase):
    def setUp(self):
        with open(CHECKS, encoding="utf-8") as f:
            self.text = f.read()
        self.jobs = all_jobs(self.text)

    def test_each_merge_and_rest_job_is_in_checks_yml(self):
        for name in SUITE_FLAG:
            self.assertIn(name, self.jobs, f"{name} is not a job in checks.yml, so its flag gates nothing")

    def test_with_its_flag_false_a_ready_pull_request_skips_each_suite_step(self):
        # Named failure: a suite step still runs on a ready pull_request when its job's flag is false, so no flag gates it.
        for name, flag in SUITE_FLAG.items():
            self.assertIn(name, self.jobs, f"{name} is not a job in checks.yml, so its flag gates nothing")
            job = self.jobs[name]
            self.assertTrue(suite_steps(job), f"{name} has no suite step")
            for st in suite_steps(job):
                label = st.get("name") or st["run"]
                with self.subTest(job=name, step=label):
                    runs = runs_flagged(job, st, {"records_only_skip": "false", flag: "false"}, default="true")
                    self.assertFalse(runs, f"{name} / {label} runs on a ready pull_request with {flag} false: if {st.get('if')}")

    def test_with_its_flag_alone_true_a_ready_pull_request_runs_each_suite_step(self):
        # Named failure: a suite step needs a second flag as well, so its job's own flag alone does not run it.
        for name, flag in SUITE_FLAG.items():
            self.assertIn(name, self.jobs, f"{name} is not a job in checks.yml, so its flag gates nothing")
            job = self.jobs[name]
            for st in suite_steps(job):
                label = st.get("name") or st["run"]
                with self.subTest(job=name, step=label):
                    runs = runs_flagged(job, st, {"records_only_skip": "false", flag: "true"}, default="false")
                    self.assertTrue(runs, f"{name} / {label} does not run on a ready pull_request with only {flag} true: if {st.get('if')}")


if __name__ == "__main__":
    unittest.main()
