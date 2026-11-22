#!/usr/bin/env python3
"""Fixture suite for bin/cheap-lints. Run: python3 lint/test_cheap_lints.py

bin/cheap-lints runs the repo's merge.readyChecks (.github/stamp.json) through merge.pre_ready_rows and prints one
`pass|fail|unknown NAME` line per check, then one summary line. The cases pin this contract:
- No readyChecks (no key, an empty list, or no stamp.json) exits 2 and prints an `unknown` line. It never exits 0.
- A failing check exits 1 and prints `fail NAME`. Every check passing exits 0 and prints the summary line.
- No line of the run matches merge.READY_PASS_FMT. The merge guard reads that line as a ready run.
- A `<job>:<step>` entry runs under its own job. A bare entry is a step of job `checks`.

Each case builds a fixture repo in its own folder of the run folder. The repo has a two-job workflow of one-line
Python steps and a stamp.json that names the case's checks. No case reads the real checks.yml.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
import workflow_steps as ws  # noqa: E402  the one home of the step parser, read for the fixture's jobs
RUN_FOLDER = _test_temp.run_folder()
ROOT = os.path.normpath(os.path.join(HERE, ".."))
CHEAP = os.path.join(ROOT, "bin", "cheap-lints")
sys.path.insert(0, os.path.join(ROOT, "merge"))
import merge  # noqa: E402  the one home of READY_PASS_FMT and of the pattern that reads its line

WORKFLOW = """\
name: cheap-lints fixture
on: push
jobs:
  checks:
    runs-on: ubuntu-latest
    steps:
      - name: Pass one
        run: python3 -c "print('one ok')"
      - name: Pass two
        run: python3 -c "print('two ok')"
      - name: Fail one
        run: python3 -c "import sys; print('one broke'); sys.exit(1)"
  other:
    runs-on: ubuntu-latest
    steps:
      - name: Other pass
        run: python3 -c "print('other ok')"
"""
# `pass NAME`, `fail NAME` or `unknown NAME`. The name ends at a `: ` or at the line's end, so `other:Other pass` reads whole.
VERDICT = re.compile(r"^(pass|fail|unknown) (.+?)(?=: |$)")


def verdicts(lines):
    """-> [(verdict, name)] of the verdict lines of one run."""
    return [(m.group(1), m.group(2)) for m in (VERDICT.match(line) for line in lines) if m]


def config_text(checks):
    """The text of a .github/stamp.json whose merge.readyChecks is `checks`."""
    return json.dumps({"merge": {"readyChecks": checks}}) + "\n"


def git_env(case):
    """The environment of a cheap-lints run. The caller's variables that the tool reads for its own run are dropped.
    The temp files, the ci-job log and the step cache stay in the case folder."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("GITHUB_", "CI_JOB_")) and k not in ("PR_BODY", "VERDICT_LOG")}
    env.update(TMPDIR=case, XDG_CACHE_HOME=case, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
    return _test_git.apply(env)


def make_fixture(case, text):
    """A git repo at <case>/repo with the workflow and .github/stamp.json holding `text`. None writes no stamp.json."""
    repo = os.path.join(case, "repo")
    os.makedirs(os.path.join(repo, ".github", "workflows"))
    with open(os.path.join(repo, ".github", "workflows", "checks.yml"), "w", encoding="utf-8") as f:
        f.write(WORKFLOW)
    if text is not None:
        with open(os.path.join(repo, ".github", "stamp.json"), "w", encoding="utf-8") as f:
            f.write(text)
    subprocess.run(["git", "init", "-q", repo], check=True, env=git_env(case), capture_output=True)
    return repo


def run_cheap(text):
    """Run bin/cheap-lints in a fresh fixture repo whose stamp.json is `text`. -> (exit code, output lines, stderr merged in)."""
    case = tempfile.mkdtemp(prefix="cheap_", dir=RUN_FOLDER)
    repo = make_fixture(case, text)
    done = subprocess.run([sys.executable, CHEAP], cwd=repo, env=git_env(case), stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True, encoding="utf-8", timeout=120)
    return done.returncode, done.stdout.splitlines()


class CheapLints(unittest.TestCase):

    def test_no_ready_checks_exits_two_with_an_unknown_line(self):
        cases = (("no readyChecks key", json.dumps({"merge": {"method": "merge"}}) + "\n"),
                 ("empty readyChecks", config_text([])),
                 ("no stamp.json", None))
        for label, text in cases:
            with self.subTest(case=label):
                rc, lines = run_cheap(text)
                self.assertEqual(rc, 2, "exit %d with %s, want 2: a run with no list proves nothing, so it is never 0" % (rc, label))
                self.assertTrue(any(line.startswith("unknown ") for line in lines), "no `unknown` line with %s: %r" % (label, lines))

    def test_failing_check_exits_one_and_names_it(self):
        rc, lines = run_cheap(config_text(["Pass one", "Fail one"]))
        self.assertEqual(rc, 1, "exit %d with one failing check, want 1" % rc)
        self.assertIn(("fail", "Fail one"), verdicts(lines), "no `fail Fail one` line: %r" % lines)
        self.assertIn(("pass", "Pass one"), verdicts(lines), "the passing check has no `pass Pass one` line: %r" % lines)

    def test_all_passing_exits_zero_with_the_summary_line(self):
        rc, lines = run_cheap(config_text(["Pass one", "Pass two", "other:Other pass"]))
        self.assertEqual(rc, 0, "exit %d with every check passing, want 0" % rc)
        self.assertIn("cheap-lints: 3 of 3 checks pass against origin/main", lines, "no summary line: %r" % lines)

    def test_no_line_matches_the_merge_ready_pass_format(self):
        pattern = merge.ready_line_pattern(merge.READY_PASS_FMT)
        sample = merge.READY_PASS_FMT.format(checks="Pass one, Pass two", sha="b7ef443524")
        self.assertIsNotNone(pattern.search(sample), "control: the pattern misses its own sample line, so the check below proves nothing")
        rc, lines = run_cheap(config_text(["Pass one", "Pass two", "other:Other pass"]))
        self.assertTrue(verdicts(lines), "premise: the run printed no verdict line, so the check below would pass for free: %r" % lines)
        hits = [line for line in lines if pattern.search(line)]
        self.assertEqual(hits, [], "a line matches merge.READY_PASS_FMT, which the merge guard reads as a ready run: %r" % hits)

    def test_qualified_entry_runs_under_its_own_job(self):
        def steps(job):
            return [ws.step_key(st, "name") for st in ws.step_blocks(ws.job_block(WORKFLOW, job))]
        self.assertIn("Other pass", steps("other"), "premise: job other of the fixture has no step Other pass")
        self.assertNotIn("Other pass", steps("checks"), "premise: job checks of the fixture holds the step Other pass")
        rc, lines = run_cheap(config_text(["other:Other pass"]))
        self.assertEqual(rc, 0, "exit %d for other:Other pass, want 0: the step runs under job other" % rc)
        self.assertIn(("pass", "other:Other pass"), verdicts(lines), "no `pass other:Other pass` line: %r" % lines)

    def test_bare_entry_is_a_step_of_job_checks(self):
        rc, lines = run_cheap(config_text(["Other pass"]))
        self.assertEqual(rc, 2, "exit %d for a bare entry that only job other holds, want 2: job checks has no such step" % rc)
        self.assertIn(("unknown", "Other pass"), verdicts(lines), "no `unknown Other pass` line: %r" % lines)


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
