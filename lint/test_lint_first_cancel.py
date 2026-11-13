#!/usr/bin/env python3
"""Proves the lint-first half of step lane-lint-once-fail-fast (decision lanes-run-no-full-ci-job).

Batch CI runs a `lint` job beside the heavy jobs, never before them (no added wait on a green run). A red lint posts the red comment
early through the `red-lint-comment` job, which wakes a waiting session before the heavy jobs end. The run is not cancelled (coordinator,
13:55 CST Nov 12, decision uniform-over-variants: a cancelled run concludes `cancelled`, which `merge --blame` refuses, and the tool takes
no second accepted form), so no job holds `actions: write`. Both jobs sit in the needs of all-jobs-passed and ci-done; the comment job runs
after a red lint (`always()` and not a draft) and its steps carry the red-lint condition.

Stdlib only. CHECKS_YML overrides the path. Run with:  python3 lint/test_lint_first_cancel.py -v
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from test_windows_split import CHECKS  # noqa: E402  the one home of the checks.yml path
from all_jobs_passed_rules import job_block, needs_of, job_key  # noqa: E402  the one home of the job reader

LINT, COMMENT = "lint", "red-lint-comment"


def blocks():
    with open(CHECKS, encoding="utf-8") as fh:
        text = fh.read()
    return text, job_block(text, LINT), job_block(text, COMMENT)


class LintFirst(unittest.TestCase):
    def test_lint_job_runs_the_lint_mode_of_ci_job_against_the_base(self):
        _, lint, _ = blocks()
        self.assertIsNotNone(lint, "no lint job in checks.yml")
        self.assertRegex(lint, r"bin/ci-job checks --lint --base \"?origin/", "the lint job does not run `bin/ci-job checks --lint --base origin/<base>`, the one home of the lint steps")

    def test_no_heavy_job_needs_the_lint_job(self):
        text, _, _ = blocks()
        for name in re.findall(r"^  ([a-z0-9-]+):\s*$", text, re.M):
            if name in (COMMENT, "all-jobs-passed", "ci-done"):
                continue
            block = job_block(text, name)
            self.assertNotIn(LINT, needs_of(block) or [], f"{name} needs lint: lint's wall time would be added to every green run")

    def test_comment_job_runs_after_a_red_lint_and_never_on_a_draft(self):
        _, _, comment = blocks()
        self.assertIsNotNone(comment, "no red-lint-comment job in checks.yml")
        self.assertEqual(needs_of(comment), [LINT])
        self.assertEqual(job_key(comment, "if"), "${{ always() && !github.event.pull_request.draft }}", "without always() GitHub skips the job when lint fails (actions/all-jobs-passed/action.yml): no comment; without the draft guard it runs a runner on every draft push")
        steps = re.split(r"^      - ", comment.split("    steps:", 1)[1], flags=re.M)[1:]
        self.assertTrue(steps)
        for step in steps:
            self.assertIn("needs.lint.result == 'failure'", step, "a comment job step runs on something other than a red lint:\n" + step)
        self.assertIn("actions/ci-done-comment", comment, "the job posts no comment: no session wakes before the run ends")

    def test_no_job_cancels_the_run_or_holds_actions_write(self):  # a cancelled run concludes cancelled, which `merge --blame` refuses
        text, _, _ = blocks()
        self.assertNotIn("gh run cancel", text, "a job cancels the run: merge --blame refuses a cancelled run, so no lane could be dropped")
        self.assertNotRegex(text, r"actions:\s*write", "a job holds actions: write: nothing here needs it")

    def test_fan_in_jobs_need_lint_and_the_comment_job(self):
        text, _, _ = blocks()
        for fan in ("all-jobs-passed", "ci-done"):
            self.assertIn(LINT, needs_of(job_block(text, fan)) or [], f"{fan} does not need lint")
            self.assertIn(COMMENT, needs_of(job_block(text, fan)) or [], f"{fan} does not need the comment job")


if __name__ == "__main__":
    unittest.main()
