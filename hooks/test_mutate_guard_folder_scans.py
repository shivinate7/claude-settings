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
- An added hooks/*.py file, guard or not, picks lint/test_rule_audit.py, whose _hooks_world reads every non-test
  hooks/*.py.
- An added skills/*/SKILL.md file picks lint/test_check_agent_models.py (its fixtures run the check's skill-file rule)
  and lint/test_check_landed_dirs.py (its fixture copies the skills folder, and repo_skills reads skills/*/SKILL.md).
- A control: a product file outside those folders, merge/launch.py, picks none of the five folder-scan suites.
- A control: an added hooks/*.py file that is no guard module picks not lint/test_check_landed_dirs.py.
- A load of a folder-scan suite, for a workflow file and for a lint module, leaves no run folder of this process in the
  temp root and no change to os.environ. That case calls `suites_for_paths` itself, since `picks_for` caches a pick and a
  cached pick loads nothing.

The probe reads are `picks_for` and `tracked_paths`, imported from hooks/test_mutate_guard_tree_scans.py, the one home
of the selector probe. The probes read the full-size tree and copy nothing.
"""
import os
import re
import shutil
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from test_mutate_guard_tree_scans import picks_for, tracked_paths  # noqa: E402  the one home of the selector probe
sys.path.insert(0, os.path.join(REPO, "lint"))
import _test_temp  # noqa: E402  the temp root the suites name (lint/_test_temp.py, TEMP_ROOT)
import mutate_guard  # noqa: E402  suites_for_paths and _load_suite, the selector under test

CI_JOB_SUITE = "lint/test_ci_job.py"
AGENT_SUITE = "lint/test_check_agent_models.py"
RULE_AUDIT_SUITE = "lint/test_rule_audit.py"
LANDED_DIRS_SUITE = "lint/test_check_landed_dirs.py"
GUARD_LOG_SUITE = "lint/test_guard_log_report.py"
FOLDER_SUITES = (CI_JOB_SUITE, AGENT_SUITE, RULE_AUDIT_SUITE, LANDED_DIRS_SUITE, GUARD_LOG_SUITE)
GIT_CONFIG_KEY = re.compile(r"GIT_CONFIG_(COUNT|KEY_[0-9]+|VALUE_[0-9]+)\Z")  # the opt-out lint/_test_git.py adds at import

CHANGED_WORKFLOW_PROBE = ".github/workflows/impeccable-sync.yml"  # tracked: a changed workflow file, not checks.yml
ADDED_WORKFLOW_PROBE = ".github/workflows/new-job.yml"  # not tracked: a workflow file that a diff adds
ADDED_AGENT_PROBE = "agents/new-role.md"  # not tracked: an agent file that a diff adds
ADDED_GUARD_PROBE = "hooks/guard_probe_family.py"  # not tracked: a guard module that a diff adds
ADDED_LINT_PROBE = "lint/check_probe_family.py"  # not tracked: a lint module that a diff adds
ADDED_HOOK_PROBE = "hooks/plain_probe_family.py"  # not tracked: a hook module that no guard glob matches
ADDED_JUDGE_PROBE = "hooks/judge_probe.py"  # not tracked: a hook module that is no guard
ADDED_SKILL_PROBE = "skills/new/SKILL.md"  # not tracked: a skill file that a diff adds
PRODUCT_PROBE = "merge/launch.py"  # tracked: a product file outside every folder above


def own_run_folders():
    """The run folders this process made in the temp root, named `<pid>-<hex>` (lint/_test_temp.py). Other processes share
    the root, so their folders are not counted, and a missing root reads as none."""
    prefix = "%d-" % os.getpid()
    try:
        return {name for name in os.listdir(_test_temp.TEMP_ROOT) if name.startswith(prefix)}
    except OSError:
        return set()


def remove_run_folders_made_since(before):
    """Remove the run folders this process made after `before` (the set `own_run_folders` read then), so a failing case
    leaves none in the temp root."""
    for name in own_run_folders() - before:
        shutil.rmtree(os.path.join(_test_temp.TEMP_ROOT, name), ignore_errors=True)


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

    def test_an_added_hook_module_that_is_no_guard_picks_the_rule_audit_suite(self):
        self.assertNotIn(ADDED_HOOK_PROBE, self.tracked,
                         "the scope: %s is not tracked, so the probe is a file that the diff adds" % ADDED_HOOK_PROBE)
        self.assertSuitesTracked((RULE_AUDIT_SUITE,))
        self.assertIn(RULE_AUDIT_SUITE, picks_for(ADDED_HOOK_PROBE),
                      "suites_for_paths must pick %s for a diff that adds %s: its _hooks_world reads every non-test hooks/*.py"
                      % (RULE_AUDIT_SUITE, ADDED_HOOK_PROBE))

    def test_an_added_judge_hook_picks_the_rule_audit_suite(self):
        self.assertNotIn(ADDED_JUDGE_PROBE, self.tracked,
                         "the scope: %s is not tracked, so the probe is a file that the diff adds" % ADDED_JUDGE_PROBE)
        self.assertSuitesTracked((RULE_AUDIT_SUITE,))
        self.assertIn(RULE_AUDIT_SUITE, picks_for(ADDED_JUDGE_PROBE),
                      "suites_for_paths must pick %s for a diff that adds %s: its _hooks_world reads every non-test hooks/*.py"
                      % (RULE_AUDIT_SUITE, ADDED_JUDGE_PROBE))

    def test_an_added_skill_file_picks_the_agent_models_suite(self):
        self.assertNotIn(ADDED_SKILL_PROBE, self.tracked,
                         "the scope: %s is not tracked, so the probe is a file that the diff adds" % ADDED_SKILL_PROBE)
        self.assertSuitesTracked((AGENT_SUITE,))
        self.assertIn(AGENT_SUITE, picks_for(ADDED_SKILL_PROBE),
                      "suites_for_paths must pick %s for a diff that adds %s: its fixtures run the check's skill-file rule"
                      % (AGENT_SUITE, ADDED_SKILL_PROBE))

    def test_an_added_skill_file_picks_the_landed_dirs_suite(self):
        self.assertNotIn(ADDED_SKILL_PROBE, self.tracked,
                         "the scope: %s is not tracked, so the probe is a file that the diff adds" % ADDED_SKILL_PROBE)
        self.assertSuitesTracked((LANDED_DIRS_SUITE,))
        self.assertIn(LANDED_DIRS_SUITE, picks_for(ADDED_SKILL_PROBE),
                      "suites_for_paths must pick %s for a diff that adds %s: its fixture copies the skills folder, and repo_skills reads skills/*/SKILL.md"
                      % (LANDED_DIRS_SUITE, ADDED_SKILL_PROBE))

    def test_an_added_hook_module_that_is_no_guard_picks_no_landed_dirs_suite(self):  # the control
        self.assertNotIn(ADDED_HOOK_PROBE, self.tracked,
                         "the scope: %s is not tracked, so the probe is a file that the diff adds" % ADDED_HOOK_PROBE)
        self.assertSuitesTracked((LANDED_DIRS_SUITE,))
        self.assertNotIn(LANDED_DIRS_SUITE, picks_for(ADDED_HOOK_PROBE),
                         "suites_for_paths must not pick %s for a diff that adds %s: it matches no hooks/guard*.py"
                         % (LANDED_DIRS_SUITE, ADDED_HOOK_PROBE))

    def test_loading_a_folder_scan_suite_leaves_no_temp_folder_or_environment_change(self):
        # Each probe starts as a fresh `--lint-suites` process does: the git opt-out is out of os.environ and
        # lint/_test_git.py is out of sys.modules, so the import that a load makes is the one measured. The scope comes
        # first: the probe picks the suite and the load reads a module, so the checks after it test a real load.
        real_load = mutate_guard._load_suite
        loaded = {}

        def record(suite):
            loaded[suite] = real_load(suite)
            return loaded[suite]

        for probe, suite in ((ADDED_WORKFLOW_PROBE, CI_JOB_SUITE), (ADDED_LINT_PROBE, GUARD_LOG_SUITE)):
            with self.subTest(probe=probe), mock.patch.dict(os.environ):
                for key in [key for key in os.environ if GIT_CONFIG_KEY.match(key)]:
                    del os.environ[key]
                cached = sys.modules.pop("_test_git", None)
                folders_before = own_run_folders()
                self.addCleanup(remove_run_folders_made_since, folders_before)
                environment_before = dict(os.environ)
                loaded.clear()
                try:
                    with mock.patch.object(mutate_guard, "_load_suite", new=record):
                        picked = mutate_guard.suites_for_paths([probe], self.tracked, union=True, chain=True)
                finally:
                    sys.modules.pop("_test_git", None)
                    if cached is not None:
                        sys.modules["_test_git"] = cached
                environment_after = dict(os.environ)
                self.assertIn(suite, picked, "the scope: %s is picked for %s, so its load runs" % (suite, probe))
                self.assertIsNotNone(loaded.get(suite),
                                     "the scope: %s reads a module for %s, so the checks below test a real load"
                                     % (suite, probe))
                with self.subTest("temp root"):
                    new = own_run_folders() - folders_before
                    self.assertEqual(new, set(),
                                     "a load of %s for %s keeps its run folder in the temp root: %s"
                                     % (suite, probe, sorted(new)))
                with self.subTest("environment"):
                    changed = sorted(key for key in set(environment_before) | set(environment_after)
                                     if environment_before.get(key) != environment_after.get(key))
                    self.assertEqual(changed, [],
                                     "a load of %s for %s changes these os.environ keys: %s" % (suite, probe, changed))


if __name__ == "__main__":
    unittest.main()
