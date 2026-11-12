#!/usr/bin/env python3
"""Cases for skills/project-ops/templates/starter-ci/checks.yml, the starter CI a repo with no CI gets. Standard library only.

    python3 skills/project-ops/tests/test_starter_ci.py

The starter is the caller workflow. Its `checks` job runs the opt-in quick-checks action (actions/quick-checks, decision
opt-in-ci-templates-composite). Lane lint reaches that action through `ci-job checks`: lint/test_ci_job.py and
merge/test_lane_lint.py pin it. Its `all-jobs-passed` job is the shared rollup
over that job, judged by lint/all_jobs_passed_rules.py `child_problems`, the one home of a child repo's rollup rules.
Its `pull_request` trigger lists the four types that run the rollup on a ready pull request, ready_for_review among them.
The cases also prove that the step the no-CI refusals name (STARTER_STEP in merge/test_merge.py and merge/test_lane_lint.py)
is a numbered step of SKILL.md. The quick checks themselves are judged in actions/quick-checks/test_quick_checks.py.
This suite reads files only and makes no temp files.
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
ROOT = os.path.abspath(os.path.join(SKILL, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "lint"))
from all_jobs_passed_rules import child_problems, needs_of  # noqa: E402  the one home of a child repo's rollup rules
from workflow_steps import job_block  # noqa: E402  the one home of the step parser

STARTER = os.path.join(SKILL, "templates", "starter-ci", "checks.yml")
STEP_SIX = re.compile(r"(?ms)^6\. \*\*Add the starter CI\.\*\*.*?(?=^7\. )")  # SKILL.md's step 6, to the next step
PR_TYPES = ("opened", "synchronize", "reopened", "ready_for_review")  # the pull_request types that run the rollup on a ready PR
STARTER_STEP = "Add the starter CI"  # the same name as merge/test_merge.py and merge/test_lane_lint.py name in their refusals
# The quick-checks action, pinned to a commit: a caller that names a tag or a branch can move under the check.
QUICK_CHECKS_USES = re.compile(r"uses:[ \t]*['\"]?shivinate7/claude-settings/actions/quick-checks@[0-9a-f]{40}\b")


class StarterCI(unittest.TestCase):
    def read_starter(self):
        """The starter's text. The scope comes first: a missing starter fails here, once, with its cause."""
        self.assertTrue(os.path.isfile(STARTER), "the skill ships no starter CI: templates/starter-ci/checks.yml is missing")
        with open(STARTER, encoding="utf-8") as f:
            return f.read()

    def test_the_skill_has_the_starter_step_the_refusals_name(self):
        with open(os.path.join(SKILL, "SKILL.md"), encoding="utf-8") as f:
            text = f.read()
        self.assertTrue(re.search(r"(?m)^\d+\. \*\*%s\.\*\*" % re.escape(STARTER_STEP), text),
                        "SKILL.md has no numbered step named %r: the no-CI refusals name a step that is not there" % STARTER_STEP)

    def test_the_checks_job_runs_the_quick_checks_action_at_a_commit(self):
        block = job_block(self.read_starter(), "checks")
        self.assertIsNotNone(block, "the starter has no `checks` job: lane lint runs `ci-job checks`, so the quick checks must sit in it")
        self.assertRegex(block, QUICK_CHECKS_USES,
                         "the checks job does not run shivinate7/claude-settings/actions/quick-checks at a 40-hex commit")

    def test_the_rollup_passes_the_child_rules(self):
        self.assertEqual(child_problems(self.read_starter()), [],
                         "the starter's all-jobs-passed job breaks the child rules (lint/all_jobs_passed_rules.py child_problems)")

    def test_the_rollup_needs_the_checks_job_alone(self):
        block = job_block(self.read_starter(), "all-jobs-passed")
        self.assertIsNotNone(block, "the starter has no all-jobs-passed job: branch protection requires that one check")
        self.assertEqual(needs_of(block), ["checks"],
                         "the rollup does not need the checks job alone: the quick checks would sit outside the required check")

    def test_the_starter_reruns_on_ready_for_review(self):
        # Without ready_for_review in the types, a red draft marked ready reruns nothing: GitHub's default types omit it.
        m = re.search(r"^  pull_request:[ \t]*\n    types: \[([^\]\n]*)\]", self.read_starter(), re.M)
        self.assertIsNotNone(m, "the starter's pull_request trigger has no `types: [...]` flow list, as main's checks.yml has: "
                                "GitHub's default (opened, synchronize, reopened) never reruns a red draft marked ready")
        types = [t.strip() for t in m.group(1).split(",")]
        for want in PR_TYPES:
            self.assertIn(want, types, "the starter's pull_request types lack %s: a red draft marked ready reruns nothing" % want)

    def read_skill(self):
        """SKILL.md's step 6 text. The scope comes first: a missing step fails here, once, with its cause."""
        with open(os.path.join(SKILL, "SKILL.md"), encoding="utf-8") as f:
            m = STEP_SIX.search(f.read())
        self.assertIsNotNone(m, "SKILL.md has no step 6 named %r" % STARTER_STEP)
        return m.group(0)

    def test_the_skill_does_not_say_the_action_gives_the_rollup_job(self):
        # The action is one step. The caller writes the all-jobs-passed job, so the sentence never says the action supplies it.
        step = self.read_skill()
        self.assertNotRegex(step, r"job from `?actions/all-jobs-passed",
                            "SKILL.md step 6 says the action gives the all-jobs-passed job: the action is a step, the caller writes the job")
        self.assertNotRegex(step, r"(?i)\baction (gives|gets|supplies|provides|adds)\b[^.\n]*all-jobs-passed",
                            "SKILL.md step 6 says the action gives the all-jobs-passed job: the action is a step, the caller writes the job")

    def test_the_skill_says_the_caller_writes_the_rollup_job(self):
        # Pins the claim, not the wording: the caller writes an all-jobs-passed job, and the action is a step inside it.
        self.assertRegex(self.read_skill(), r"(?i)caller writes\b[^.\n]*all-jobs-passed` job",
                         "SKILL.md step 6 does not say the caller writes the all-jobs-passed job")


if __name__ == "__main__":
    unittest.main()
