#!/usr/bin/env python3
"""Proves the lint-first half of step lane-lint-once-fail-fast (owner ruling R4, 14:56 CST Nov 10; decision lanes-run-no-full-ci-job).

Batch CI runs a `lint` job beside the heavy jobs, never before them (no added wait on a green run). A red lint ends the run through the
`cancel-on-red-lint` job: it posts the red comment first (a cancelled run's ci-done job is skipped, so no other job wakes the session),
then cancels the run. Only that job holds `actions: write`. Both jobs sit in the needs of all-jobs-passed and ci-done; the cancel job runs after a red lint (`always()` and not a draft) and its steps carry the red-lint condition.

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

LINT, CANCEL = "lint", "cancel-on-red-lint"


def blocks():
    with open(CHECKS, encoding="utf-8") as fh:
        text = fh.read()
    return text, job_block(text, LINT), job_block(text, CANCEL)


class LintFirst(unittest.TestCase):
    def test_lint_job_runs_the_lint_mode_of_ci_job_against_the_base(self):
        _, lint, _ = blocks()
        self.assertIsNotNone(lint, "no lint job in checks.yml")
        self.assertRegex(lint, r"bin/ci-job checks --lint --base \"?origin/", "the lint job does not run `bin/ci-job checks --lint --base origin/<base>`, the one home of the lint steps")

    def test_lint_job_does_not_gate_the_heavy_jobs(self):
        text, _, _ = blocks()
        for name in re.findall(r"^  ([a-z0-9-]+):\s*$", text, re.M):
            if name in (CANCEL, "all-jobs-passed", "ci-done"):
                continue
            block = job_block(text, name)
            self.assertNotIn(LINT, needs_of(block) or [], f"{name} needs lint: lint's wall time would be added to every green run")

    def test_lint_job_is_not_cancelled_by_its_own_cancel_job(self):
        _, lint, cancel = blocks()
        self.assertIsNotNone(cancel, "no cancel-on-red-lint job in checks.yml")
        self.assertEqual(needs_of(cancel), [LINT])
        self.assertEqual(job_key(cancel, "if"), "${{ always() && !github.event.pull_request.draft }}", "without always() GitHub skips the cancel job when lint fails (actions/all-jobs-passed/action.yml): no comment, no cancel; without the draft guard it runs a runner on every draft push")
        steps = re.split(r"^      - ", cancel.split("    steps:", 1)[1], flags=re.M)[1:]
        self.assertTrue(steps)
        for step in steps:
            self.assertIn("needs.lint.result == 'failure'", step, "a cancel job step runs on something other than a red lint:\n" + step)

    def test_only_the_cancel_job_holds_actions_write(self):
        text, _, cancel = blocks()
        self.assertIsNotNone(cancel)
        self.assertRegex(cancel, r"actions:\s*write")
        self.assertEqual(len(re.findall(r"actions:\s*write", text)), 1, "actions: write sits on more than the cancel job")

    def test_cancel_job_posts_the_red_comment_before_it_cancels(self):
        _, _, cancel = blocks()
        self.assertIsNotNone(cancel)
        comment, cancelled = cancel.find("actions/ci-done-comment"), cancel.find("gh run cancel")
        self.assertGreater(comment, -1, "the cancel job posts no comment: a cancelled run's ci-done is skipped, so no session wakes")
        self.assertGreater(cancelled, comment, "the cancel job cancels the run before it posts the comment, and the cancel ends the job")

    def test_cancel_waits_for_the_posted_comment(self):  # a failed post exits 0 by default; a cancelled run skips ci-done, so a cancel after a failed post wakes nobody
        _, _, cancel = blocks()
        self.assertIsNotNone(cancel)
        self.assertRegex(cancel, r"id: comment\b", "the comment step has no id for the cancel step to read")
        comment_step = cancel[cancel.index("name: Comment that lint ended red"):cancel.index("name: Cancel the run")]
        self.assertRegex(comment_step, r"strict:\s*['\"]?true", "the comment step is not strict: a failed post would not fail the step")
        cancel_step = cancel[cancel.index("name: Cancel the run"):]
        self.assertIn("steps.comment.outcome == 'success'", cancel_step, "the cancel step does not wait for the comment step's success")

    def test_fan_in_jobs_need_lint_and_the_cancel_job(self):
        text, _, _ = blocks()
        for fan in ("all-jobs-passed", "ci-done"):
            self.assertIn(LINT, needs_of(job_block(text, fan)) or [], f"{fan} does not need lint")
            self.assertIn(CANCEL, needs_of(job_block(text, fan)) or [], f"{fan} does not need the cancel job")
        self.assertIn(CANCEL, needs_of(job_block(text, "all-jobs-passed")) or [], "all-jobs-passed does not need the cancel job")


if __name__ == "__main__":
    unittest.main()
