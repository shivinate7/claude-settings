#!/usr/bin/env python3
"""Fixture suite for lint/check_guardset_lists.py, and the pin that job checks runs it.

The guard set's lists name each flat module a guard file imports: the install.sh and install.ps1 copy and
set loops, and the ci-scope.sh case line. hooks/test_install_src.sh reads them in guardset4, guardset7 and
guardset8, but only job checks-install-checkout runs that file. Lane lint runs job checks alone, so a short
list can pass lane lint while the install checkout job goes red.

Each behaviour case finds the step in job checks first, then runs the command that step runs, in a fixture
built from disk. On a commit with no such step, every behaviour case fails on that one named cause.
"""
import os
import re
import shutil
import subprocess
import sys
import unittest
import uuid

HERE = os.path.dirname(os.path.realpath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import _test_temp  # noqa: E402  the one home of the run folder and its sweep (lint/_test_temp.py)
from workflow_steps import job_block, run_body, step_blocks, step_key  # noqa: E402  the one home of the step parser (lint/workflow_steps.py)

CHECK = "lint/check_guardset_lists.py"
CONTROL = "lint/check_unknown_reads_contract.py"  # a step that job checks already runs: the locator's green control
CHECKS_YML = os.path.join(REPO, ".github", "workflows", "checks.yml")
PROBE = "zz_guardset_probe.py"  # a flat module that no guard-set list names
FIXTURE_DIRS = ("hooks", "lint", "testing", os.path.join(".github", "scripts"))
FIXTURE_FILES = ("install.sh", "install.ps1", "landed-dirs.txt")
TIMEOUT = 300  # hang guard: the guard-set cases run in about 5 s
SUITE = os.path.join("hooks", "test_install_src.sh")
HANG_SUITE = "#!/bin/sh\nexec sleep 60\n"  # runs 60 s, so a cap of 1 s always ends it first
OK_THEN_EXIT_ONE = ("#!/bin/sh\necho 'ok   - guardset4: fake'\necho 'ok   - guardset7: fake'\n"
                    "echo 'ok   - guardset8: fake'\nexit 1\n")
NO_STEP = "job checks in .github/workflows/checks.yml has no step that runs `python3 %s`, so a short guard-set list passes lane lint"
RUN = ""  # this run's folder, made in setUpModule


def tail(text, lines=30):
    return "\n".join(text.splitlines()[-lines:])


def checks_steps():
    """(name, run text) of each step of job checks, read by line."""
    with open(CHECKS_YML, encoding="utf-8") as fh:
        block = job_block(fh.read(), "checks") or ""
    return [(step_key(step, "name") or "", run_body(step) or "") for step in step_blocks(block)]


def find_step(script):
    """(name, command) of the step of job checks whose run is `python3 <script>` alone, or None."""
    line = re.compile(r"^python3 %s[ \t]*$" % re.escape(script), re.M)
    for name, body in checks_steps():
        m = line.search(body)
        if m:
            return name, m.group(0).strip()
    return None


def run_command(command, cwd):
    done = subprocess.run(command.split(), cwd=cwd, capture_output=True, text=True, timeout=TIMEOUT)
    return done.returncode, done.stdout + done.stderr


def make_fixture(name, probe=False, drop_case=None, suite=None, cap=None):
    """A git-initialised copy of the guard-set tree, built from disk. `probe` adds one flat module that a guard
    file imports and no list names. `drop_case` takes one `run <case>` line out of the case list, so it never runs.
    `suite` replaces the text of the suite file, and `cap` sets the check's TIMEOUT to that many seconds."""
    root = os.path.join(RUN, name)
    os.makedirs(root)
    for d in FIXTURE_DIRS:
        shutil.copytree(os.path.join(REPO, d), os.path.join(root, d),
                        ignore=shutil.ignore_patterns("__pycache__", ".git"))
    for f in FIXTURE_FILES:
        shutil.copy2(os.path.join(REPO, f), os.path.join(root, f))
    # tracked_tree.sh lists the fixture's files with git, so the fixture is a repository of its own.
    subprocess.run(["git", "init", "-q", root], check=True, capture_output=True)
    if probe:
        with open(os.path.join(root, "hooks", PROBE), "w", encoding="utf-8") as fh:
            fh.write("# A flat module that a guard file imports. No guard-set list names it.\n")
        with open(os.path.join(root, "hooks", "guard.py"), "a", encoding="utf-8") as fh:
            fh.write("\nimport %s  # the guard-set probe\n" % PROBE[:-3])
    if drop_case:
        path = os.path.join(root, SUITE)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        line = "\nrun %s\n" % drop_case
        if text.count(line) != 1:
            raise AssertionError("the case list holds `run %s` %d times, want once" % (drop_case, text.count(line)))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text.replace(line, "\n"))
    if suite is not None:
        with open(os.path.join(root, SUITE), "w", encoding="utf-8") as fh:
            fh.write(suite)
    if cap is not None:
        path = os.path.join(root, CHECK)
        with open(path, encoding="utf-8") as fh:
            text, n = re.subn(r"^TIMEOUT = \d+", "TIMEOUT = %d" % cap, fh.read(), flags=re.M)
        if n != 1:
            raise AssertionError("the check holds `TIMEOUT = <n>` %d times, want once" % n)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
    return root


def setUpModule():
    global RUN
    RUN = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN, ignore_errors=True)


class Base(unittest.TestCase):
    def locate(self):
        """The check's step in job checks. Found before any fixture is built: the wiring is the subject."""
        found = find_step(CHECK)
        self.assertIsNotNone(found, NO_STEP % CHECK)
        return found


class WiringPin(Base):
    def test_checks_job_has_a_step_that_runs_the_check(self):
        self.locate()

    def test_ci_job_plan_lists_the_check_step(self):
        name, _ = self.locate()
        done = subprocess.run([sys.executable, os.path.join(REPO, "bin", "ci-job"), "checks", "--plan"],
                              cwd=REPO, capture_output=True, text=True, timeout=TIMEOUT)
        listed = re.search(r"^would run[ \t]+%s[ \t]*$" % re.escape(name), done.stdout, re.M)
        self.assertIsNotNone(listed, "bin/ci-job checks --plan does not list the step %r as `would run` (exit %d)"
                             % (name, done.returncode))


class LocatorControl(unittest.TestCase):
    def test_locator_finds_a_step_that_job_checks_already_runs(self):
        self.assertIsNotNone(find_step(CONTROL), "the locator finds no step in job checks that runs `python3 %s`" % CONTROL)


class GuardSetCheck(Base):
    def test_a_short_list_exits_one_and_names_the_probe(self):
        _, command = self.locate()
        code, out = run_command(command, make_fixture("short", probe=True))
        self.assertEqual(code, 1, "the step exits %d on a short list, want 1:\n%s" % (code, tail(out)))
        self.assertIn(PROBE, out, "the output does not name %s:\n%s" % (PROBE, tail(out)))
        self.assertIn("install.sh copy loop", out, "the output does not name the list:\n%s" % tail(out))

    def test_complete_lists_exit_zero(self):
        _, command = self.locate()
        code, out = run_command(command, make_fixture("complete"))
        self.assertEqual(code, 0, "the step exits %d on the repo's lists, want 0:\n%s" % (code, tail(out)))

    def test_a_case_that_does_not_run_exits_one_and_names_it(self):
        _, command = self.locate()
        code, out = run_command(command, make_fixture("dropped", drop_case="guardset7"))
        self.assertEqual(code, 1, "the step exits %d when guardset7 never runs, want 1:\n%s" % (code, tail(out)))
        self.assertIn("guardset7", out, "the output does not name guardset7:\n%s" % tail(out))

    def test_a_suite_past_its_cap_exits_one_and_says_it_did_not_finish(self):
        _, command = self.locate()
        code, out = run_command(command, make_fixture("hang", suite=HANG_SUITE, cap=1))
        self.assertEqual(code, 1, "the step exits %d when the suite runs past its cap, want 1:\n%s" % (code, tail(out)))
        self.assertIn("did not finish", out, "the output does not say the suite did not finish:\n%s" % tail(out))

    def test_every_case_ok_then_suite_exit_non_zero_exits_one(self):
        _, command = self.locate()
        code, out = run_command(command, make_fixture("exit-after-ok", suite=OK_THEN_EXIT_ONE))
        self.assertEqual(code, 1, "the step exits %d when each case prints ok and the suite exits 1, want 1:\n%s" % (code, tail(out)))
        self.assertIn("exited 1", out, "the output does not say the suite exited 1:\n%s" % tail(out))


class RunFolderSweep(unittest.TestCase):
    def test_sweep_removes_an_old_sibling_and_keeps_a_new_one(self):
        temp_root = os.path.join(RUN, "sweep")
        now = 1800000000.0  # a synthetic clock: the sweep reads ages from it, never the real date
        old = os.path.join(temp_root, "999999-%s" % uuid.uuid4().hex)
        new = os.path.join(temp_root, "999998-%s" % uuid.uuid4().hex)
        own = os.path.join(temp_root, "%d-%s" % (os.getpid(), uuid.uuid4().hex))
        for path, age in ((old, 2 * 86400), (new, 60), (own, 2 * 86400)):
            os.makedirs(path)
            os.utime(path, (now - age, now - age))
        _test_temp.sweep(temp_root, own, now=now)
        self.assertFalse(os.path.exists(old), "the sweep kept a sibling two days old")
        self.assertTrue(os.path.exists(new), "the sweep removed a sibling one minute old")
        self.assertTrue(os.path.exists(own), "the sweep removed the run's own folder")


if __name__ == "__main__":
    unittest.main()
