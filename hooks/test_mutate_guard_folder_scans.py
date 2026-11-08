#!/usr/bin/env python3
"""Cases for the folder-scan suites in the lane-lint suite selector (hooks/mutate_guard.py). Standard library only.

    python3 hooks/test_mutate_guard_folder_scans.py

A folder-scan suite reads every file of one folder, so a new file there changes what the suite checks. These cases pin
that lane lint picks such a suite for a new file in its folder. They call the selector in chain mode, as
`lint_suites_main` does.

- A changed or added workflow file under .github/workflows/ (not checks.yml) picks lint/test_ci_job.py, whose
  RunBodiesOfWorkflows reads every workflow file.
- An added agents/*.md file picks lint/test_check_agent_models.py, which reads each agents/*.md file.
- An added hooks/guard*.py file picks lint/test_rule_audit.py (its guard_paths globs hooks/guard*.py),
  lint/test_check_landed_dirs.py (its glob is hooks/guard*.py) and lint/test_guard_log_report.py (it reads each non-test
  .py file in hooks/ and lint/).
- An added lint/*.py file picks lint/test_guard_log_report.py.
- A control: a product file outside those folders, merge/launch.py, picks none of the five folder-scan suites.
- A control: an added hooks/*.py file that is no guard module picks neither lint/test_rule_audit.py nor
  lint/test_check_landed_dirs.py.

The probe reads are `picks_for` and `tracked_paths`, imported from hooks/test_mutate_guard_tree_scans.py, the one home
of the selector probe. The probes read the full-size tree and copy nothing.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from test_mutate_guard_tree_scans import picks_for, tracked_paths  # noqa: E402  the one home of the selector probe

CI_JOB_SUITE = "lint/test_ci_job.py"
AGENT_SUITE = "lint/test_check_agent_models.py"
RULE_AUDIT_SUITE = "lint/test_rule_audit.py"
LANDED_DIRS_SUITE = "lint/test_check_landed_dirs.py"
GUARD_LOG_SUITE = "lint/test_guard_log_report.py"
FOLDER_SUITES = (CI_JOB_SUITE, AGENT_SUITE, RULE_AUDIT_SUITE, LANDED_DIRS_SUITE, GUARD_LOG_SUITE)
GUARD_ONLY_SUITES = (RULE_AUDIT_SUITE, LANDED_DIRS_SUITE)

CHANGED_WORKFLOW_PROBE = ".github/workflows/impeccable-sync.yml"  # tracked: a changed workflow file, not checks.yml
ADDED_WORKFLOW_PROBE = ".github/workflows/new-job.yml"  # not tracked: a workflow file that a diff adds
ADDED_AGENT_PROBE = "agents/new-role.md"  # not tracked: an agent file that a diff adds
ADDED_GUARD_PROBE = "hooks/guard_probe_family.py"  # not tracked: a guard module that a diff adds
ADDED_LINT_PROBE = "lint/check_probe_family.py"  # not tracked: a lint module that a diff adds
ADDED_HOOK_PROBE = "hooks/plain_probe_family.py"  # not tracked: a hook module that no guard glob matches
PRODUCT_PROBE = "merge/launch.py"  # tracked: a product file outside every folder above


class FolderScanPickTests(unittest.TestCase):
    """`suites_for_paths` on the real tree, in chain mode. Each case asserts the scope (the suites and the probe are in the
    tree the selector reads) before the subject (the picks)."""

    @classmethod
    def setUpClass(cls):
        previous = os.getcwd()
        cls.addClassCleanup(os.chdir, previous)
        os.chdir(REPO)  # the selector reads tracked files by path, relative to the working folder
        cls.tracked = tracked_paths()

    def assertSuitesTracked(self, suites):
        for suite in suites:
            self.assertIn(suite, self.tracked, "the scope: %s is tracked, so the probe reaches it" % suite)

    def test_a_changed_workflow_file_picks_the_ci_job_suite(self):
        self.assertIn(CHANGED_WORKFLOW_PROBE, self.tracked,
                      "the scope: %s is tracked, a changed workflow file" % CHANGED_WORKFLOW_PROBE)
        self.assertSuitesTracked((CI_JOB_SUITE,))
        self.assertIn(CI_JOB_SUITE, picks_for(CHANGED_WORKFLOW_PROBE),
                      "suites_for_paths must pick %s for a diff that changes %s: its RunBodiesOfWorkflows reads every workflow file"
                      % (CI_JOB_SUITE, CHANGED_WORKFLOW_PROBE))

    def test_an_added_workflow_file_picks_the_ci_job_suite(self):
        self.assertNotIn(ADDED_WORKFLOW_PROBE, self.tracked,
                         "the scope: %s is not tracked, so the probe is a file that the diff adds" % ADDED_WORKFLOW_PROBE)
        self.assertSuitesTracked((CI_JOB_SUITE,))
        self.assertIn(CI_JOB_SUITE, picks_for(ADDED_WORKFLOW_PROBE),
                      "suites_for_paths must pick %s for a diff that adds %s: its RunBodiesOfWorkflows reads every workflow file"
                      % (CI_JOB_SUITE, ADDED_WORKFLOW_PROBE))

    def test_an_added_agent_file_picks_the_agent_models_suite(self):
        self.assertNotIn(ADDED_AGENT_PROBE, self.tracked,
                         "the scope: %s is not tracked, so the probe is a file that the diff adds" % ADDED_AGENT_PROBE)
        self.assertSuitesTracked((AGENT_SUITE,))
        self.assertIn(AGENT_SUITE, picks_for(ADDED_AGENT_PROBE),
                      "suites_for_paths must pick %s for a diff that adds %s: it reads each agents/*.md file"
                      % (AGENT_SUITE, ADDED_AGENT_PROBE))

    def test_an_added_guard_module_picks_the_rule_audit_suite(self):
        self.assertNotIn(ADDED_GUARD_PROBE, self.tracked,
                         "the scope: %s is not tracked, so the probe is a file that the diff adds" % ADDED_GUARD_PROBE)
        self.assertSuitesTracked((RULE_AUDIT_SUITE,))
        self.assertIn(RULE_AUDIT_SUITE, picks_for(ADDED_GUARD_PROBE),
                      "suites_for_paths must pick %s for a diff that adds %s: its guard_paths globs hooks/guard*.py"
                      % (RULE_AUDIT_SUITE, ADDED_GUARD_PROBE))

    def test_an_added_guard_module_picks_the_landed_dirs_suite(self):
        self.assertNotIn(ADDED_GUARD_PROBE, self.tracked,
                         "the scope: %s is not tracked, so the probe is a file that the diff adds" % ADDED_GUARD_PROBE)
        self.assertSuitesTracked((LANDED_DIRS_SUITE,))
        self.assertIn(LANDED_DIRS_SUITE, picks_for(ADDED_GUARD_PROBE),
                      "suites_for_paths must pick %s for a diff that adds %s: its glob reads hooks/guard*.py"
                      % (LANDED_DIRS_SUITE, ADDED_GUARD_PROBE))

    def test_an_added_guard_module_picks_the_guard_log_report_suite(self):
        self.assertNotIn(ADDED_GUARD_PROBE, self.tracked,
                         "the scope: %s is not tracked, so the probe is a file that the diff adds" % ADDED_GUARD_PROBE)
        self.assertSuitesTracked((GUARD_LOG_SUITE,))
        self.assertIn(GUARD_LOG_SUITE, picks_for(ADDED_GUARD_PROBE),
                      "suites_for_paths must pick %s for a diff that adds %s: it reads each non-test .py file in hooks/"
                      % (GUARD_LOG_SUITE, ADDED_GUARD_PROBE))

    def test_an_added_lint_module_picks_the_guard_log_report_suite(self):
        self.assertNotIn(ADDED_LINT_PROBE, self.tracked,
                         "the scope: %s is not tracked, so the probe is a file that the diff adds" % ADDED_LINT_PROBE)
        self.assertSuitesTracked((GUARD_LOG_SUITE,))
        self.assertIn(GUARD_LOG_SUITE, picks_for(ADDED_LINT_PROBE),
                      "suites_for_paths must pick %s for a diff that adds %s: it reads each non-test .py file in lint/"
                      % (GUARD_LOG_SUITE, ADDED_LINT_PROBE))

    def test_a_product_file_outside_the_folders_picks_no_folder_suite(self):  # the control
        self.assertIn(PRODUCT_PROBE, self.tracked, "the scope: %s is tracked" % PRODUCT_PROBE)
        self.assertSuitesTracked(FOLDER_SUITES)
        picked = picks_for(PRODUCT_PROBE)
        for suite in FOLDER_SUITES:
            with self.subTest(suite=suite):
                self.assertNotIn(suite, picked,
                                 "suites_for_paths must not pick %s for a diff of %s: it reads no file in that folder"
                                 % (suite, PRODUCT_PROBE))

    def test_an_added_hook_module_that_is_no_guard_picks_neither_guard_only_suite(self):  # the control
        self.assertNotIn(ADDED_HOOK_PROBE, self.tracked,
                         "the scope: %s is not tracked, so the probe is a file that the diff adds" % ADDED_HOOK_PROBE)
        self.assertSuitesTracked(GUARD_ONLY_SUITES)
        picked = picks_for(ADDED_HOOK_PROBE)
        for suite in GUARD_ONLY_SUITES:
            with self.subTest(suite=suite):
                self.assertNotIn(suite, picked,
                                 "suites_for_paths must not pick %s for a diff that adds %s: it matches no hooks/guard*.py"
                                 % (suite, ADDED_HOOK_PROBE))


if __name__ == "__main__":
    unittest.main()
