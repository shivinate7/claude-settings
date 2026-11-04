#!/usr/bin/env python3
"""clear_rule.clears, called directly: the job-level rules of the failed-run clear (the module docstring of clear_rule.py).

Run: python3 actions/ci-alarm/test_clear_rule.py. Stdlib unittest. Each case builds its workflow text in memory; no file is read or written.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clear_rule  # noqa: E402  the one home of the failed-run clear, beside this file

PUSH = "push"
RUNS_ON = "runs-on: ubuntu-latest"
STEPS = ["steps:", "  - run: echo ok"]


def job(name, conclusion):
    return {"name": name, "status": "completed", "conclusion": conclusion}


def workflow(*jobs):
    """A workflow file text: a header, then one block per job, given as (key, body lines). Each body line sits four spaces in, under its key."""
    lines = ["name: checks", "on: [push, schedule]", "jobs:"]
    for key, body in jobs:
        lines.append(f"  {key}:")
        lines.extend(f"    {line}" for line in body)
    return "\n".join(lines) + "\n"


class ClearRuleJobs(unittest.TestCase):
    # The red run is a schedule run that failed on `checks`. `extra` was skipped there, and the newer push run skipped it too.
    R = [job("checks", "failure"), job("extra", "skipped")]
    N = [job("checks", "success"), job("extra", "skipped")]

    def test_a_multi_line_if_whose_continuation_names_the_push_event_keeps_the_job_needed(self):
        # The if: is one plain scalar over two lines, `... == 'pull_request'` then `|| ... == 'push'`, so it may run in a push run and stays
        # needed. Named failure: only the first line is read, so the job reads as pull_request-only and is left out.
        text = workflow(("checks", [RUNS_ON, *STEPS]),
                        ("extra", [RUNS_ON, "if: github.event_name == 'pull_request'", "  || github.event_name == 'push'", *STEPS]))
        self.assertFalse(clear_rule.clears(self.R, self.N, PUSH, text),
                         "a job whose if: may run in a push run must stay needed, so its skip in the push run blocks the clear")

    def test_a_single_line_if_naming_the_other_event_leaves_the_job_out(self):
        # Control for the case above: the same job with a one-line if: names pull_request only, so no push run runs it and the clear goes on.
        text = workflow(("checks", [RUNS_ON, *STEPS]),
                        ("extra", [RUNS_ON, "if: github.event_name == 'pull_request'", *STEPS]))
        self.assertTrue(clear_rule.clears(self.R, self.N, PUSH, text),
                        "a one-line if: that names only pull_request leaves the job out, so the skipped job does not block the clear")

    def test_a_job_name_shared_by_two_jobs_keeps_the_job_needed(self):
        # `pq` has no name:, so its name is its key. `other` is named pq and its if: names pull_request only. The name maps to two jobs,
        # so it maps to no job and pq stays needed. Named failure: a name: match beats a key match, so `other` decides and pq is left out.
        r = [job("checks", "failure"), job("pq", "success")]
        n = [job("checks", "success"), job("pq", "skipped")]
        text = workflow(("checks", [RUNS_ON, *STEPS]),
                        ("pq", [RUNS_ON, *STEPS]),
                        ("other", ["name: pq", RUNS_ON, "if: ${{ github.event_name == 'pull_request' }}", *STEPS]))
        self.assertFalse(clear_rule.clears(r, n, PUSH, text),
                         "an ambiguous job name maps to no job, so the job named pq stays needed and its skip blocks the clear")

    def test_a_job_matched_by_its_own_key_with_an_other_event_if_is_left_out(self):
        # Control for the case above: no other job is named pq, so the key matches the one job, whose if: names pull_request only.
        r = [job("checks", "failure"), job("pq", "success")]
        n = [job("checks", "success"), job("pq", "skipped")]
        text = workflow(("checks", [RUNS_ON, *STEPS]),
                        ("pq", [RUNS_ON, "if: ${{ github.event_name == 'pull_request' }}", *STEPS]))
        self.assertTrue(clear_rule.clears(r, n, PUSH, text),
                        "a key match with a pull_request-only if: leaves the job out, so the skip does not block the clear")


if __name__ == "__main__":
    unittest.main()
