#!/usr/bin/env python3
"""Fixture suite for bin/cheap-lints. Run: python3 lint/test_cheap_lints.py

bin/cheap-lints runs the repo's merge.readyChecks (.github/stamp.json) through merge.pre_ready_rows and prints one
`pass|fail|unknown NAME` line per check, then one summary line. The cases pin this contract:
- No readyChecks (no key, an empty list, or no stamp.json) exits 2 and prints an `unknown` line. It never exits 0.
- A failing check exits 1 and prints `fail NAME`. Every check passing exits 0 and prints the summary line.
- No line of the run matches merge.READY_PASS_FMT. The merge guard reads that line as a ready run.
- A `<job>:<step>` entry runs under its own job. A bare entry is a step of job `checks`.
- A read that cannot run exits 2 with an `unknown cheap-lints:` line and no traceback: a bad call, a copy with no
  hooks/ beside it, and a run with no claude-settings checkout to find.
- The records step (`Rules and records move together`) gets the PR body only from PR_BODY. With no PR_BODY it is
  reported as not run, and it does not count against the exit. With PR_BODY set, its verdict counts, and an empty
  body is still a body.
- A check that FAILs on the checkout names its base read in its row: `passes on <sha9>: this change broke it`,
  `also fails on <sha9>`, or `base not read: <reason>`. The row stays `fail` and the run exits 1. A passing check reads no base.
  Class BaseRun holds these cases; its base is the merge base of HEAD and origin/main in the case's own repo, the commit the change started from.

Each case builds a fixture repo in its own folder of the run folder. The repo has a two-job workflow of one-line
Python steps and a stamp.json that names the case's checks. The CheapLints cases never read the real checks.yml;
CodeCheckReady reads its Code check step and the repo's real readyChecks list, and nothing else of checks.yml. The checks job's
records step is a stub: it exits 0 only when PR_BODY is non-empty, so the cases drive the no-body and body paths
without the real action.
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
      - name: Rules and records move together
        run: python3 -c "import os, sys; sys.exit(0 if os.environ.get('PR_BODY') else 1)"
  other:
    runs-on: ubuntu-latest
    steps:
      - name: Other pass
        run: python3 -c "print('other ok')"
"""
# The base cases' workflow. __PROBE__ is the case's probe.log, outside the checkout. A step that runs appends its name and the
# folder it ran in, so a case counts the runs in a copy of the base (any folder but the checkout) and the runs in the checkout.
PROBE_WORKFLOW = """\
name: cheap-lints base fixture
on: push
jobs:
  checks:
    runs-on: ubuntu-latest
    steps:
      - name: Pass one
        run: python3 -c "print('one ok')"
      - name: Breaks on change
        run: python3 -c "import os, sys; open('__PROBE__', 'a').write('Breaks on change' + chr(9) + os.path.realpath(os.getcwd()) + chr(10)); sys.exit(1 if os.path.exists('BROKEN') else 0)"
      - name: Breaks everywhere
        run: python3 -c "import os, sys; open('__PROBE__', 'a').write('Breaks everywhere' + chr(9) + os.path.realpath(os.getcwd()) + chr(10)); print('still broken'); sys.exit(1)"
      - name: Silent undo check
        run: python3 -c "import os, subprocess, sys; sys.exit(subprocess.call(['git', 'rev-parse', '--verify', '-q', 'HEAD'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) or (1 if os.path.exists('BROKEN') else 0))"
"""
# `pass NAME`, `fail NAME` or `unknown NAME`. The name ends at a `: `, at a base phrase (` (passes on `, ` (also fails on `,
# ` (base not read: `) or at the line's end, so `other:Other pass` reads whole and `fail NAME (passes on X: ...)` reads NAME.
VERDICT = re.compile(r"^(pass|fail|unknown) (.+?)(?= \((?:passes on |also fails on |base not read: )|: |$)")
RECORDS_STEP = "Rules and records move together"  # the records step the ready checks name; the checks job's stub takes this name


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
    env.update(TMPDIR=case, XDG_CACHE_HOME=case, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull,
               CLAUDE_CONFIG_DIR=os.path.join(case, "config"))  # an empty config dir: no global rules file points at a checkout
    return _test_git.apply(env)


def make_fixture(case, text, workflow=WORKFLOW):
    """A git repo at <case>/repo with `workflow` as checks.yml and .github/stamp.json holding `text`. None writes no stamp.json."""
    repo = os.path.join(case, "repo")
    os.makedirs(os.path.join(repo, ".github", "workflows"))
    with open(os.path.join(repo, ".github", "workflows", "checks.yml"), "w", encoding="utf-8") as f:
        f.write(workflow)
    if text is not None:
        with open(os.path.join(repo, ".github", "stamp.json"), "w", encoding="utf-8") as f:
            f.write(text)
    subprocess.run(["git", "init", "-q", repo], check=True, env=git_env(case), capture_output=True)
    return repo


def new_case():
    """A case folder in the run folder. Every file a case writes lives under it."""
    return tempfile.mkdtemp(prefix="cheap_", dir=RUN_FOLDER)


def run_in(case, text, script, args=(), body=None):
    """Run `script` with `args` in a fixture repo under `case` whose stamp.json is `text`. `body` is the PR_BODY the run gets;
    None leaves PR_BODY unset. -> (exit code, output lines, stderr merged in)."""
    return run_repo(make_fixture(case, text), case, script, args, body)


def run_repo(repo, case, script, args=(), body=None):
    """Run `script` with `args` in the existing fixture repo `repo` of `case`. `body` as in run_in. -> (exit code, output lines)."""
    env = git_env(case)
    if body is not None:
        env["PR_BODY"] = body
    done = subprocess.run([sys.executable, script, *args], cwd=repo, env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True, encoding="utf-8", timeout=120)
    return done.returncode, done.stdout.splitlines()


def run_cheap(text, args=()):
    """Run this checkout's bin/cheap-lints in a fresh fixture repo whose stamp.json is `text`."""
    return run_in(new_case(), text, CHEAP, args)


def copy_cheap(case, hooks):
    """Copy bin/cheap-lints to <case>/copy/bin. With `hooks`, <case>/copy/hooks links to this checkout's hooks/, the one
    folder the copy reads beside itself. Without it, the copy has no hooks/ at all. -> the copy's path."""
    bin_dir = os.path.join(case, "copy", "bin")
    os.makedirs(bin_dir)
    shutil.copy(CHEAP, os.path.join(bin_dir, "cheap-lints"))
    if hooks:
        os.symlink(os.path.join(ROOT, "hooks"), os.path.join(case, "copy", "hooks"), target_is_directory=True)
    return os.path.join(bin_dir, "cheap-lints")


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

    def test_records_step_without_a_pr_body_is_not_run_and_does_not_fail_the_run(self):
        rc, lines = run_cheap(config_text(["Pass one", RECORDS_STEP]))
        self.assertEqual(rc, 0, "exit %d with no PR body: the records step ran with no body and counted against the run" % rc)
        self.assertFalse([v for v, name in verdicts(lines) if name == RECORDS_STEP and v in ("pass", "fail")],
                         "the records step has a pass or fail line with no PR body, so it ran: %r" % lines)
        self.assertTrue(any(RECORDS_STEP in line and "not run" in line and "PR body" in line for line in lines),
                        "no line says the records step was not run for want of a PR body: %r" % lines)

    def test_records_step_with_a_pr_body_runs_and_its_verdict_counts(self):
        with self.subTest(body="a non-empty body"):
            rc, lines = run_in(new_case(), config_text([RECORDS_STEP]), CHEAP, body="Rules checked: a-record - no change\n")
            self.assertEqual(rc, 0, "exit %d with a PR body: the body did not reach the records step, so it failed for want of one" % rc)
            self.assertIn(("pass", RECORDS_STEP), verdicts(lines), "no `pass` line for the records step with a PR body: %r" % lines)
        with self.subTest(body="an empty body"):
            rc, lines = run_in(new_case(), config_text([RECORDS_STEP]), CHEAP, body="")
            self.assertEqual(rc, 1, "exit %d with an empty PR body, want 1: an empty body is a body, so the step runs and its FAIL counts" % rc)
            self.assertIn(("fail", RECORDS_STEP), verdicts(lines), "no `fail` line for the records step with an empty PR body: %r" % lines)

    def test_extra_argument_exits_two_with_an_unknown_line(self):
        rc, lines = run_cheap(config_text(["Pass one"]), args=["main", "extra"])
        self.assertEqual(rc, 2, "exit %d for `main extra`, want 2: a bad call is unknown, never 1" % rc)
        self.assertTrue(any(line.startswith("unknown ") for line in lines), "no `unknown` line for `main extra`: %r" % lines)

    def test_copy_without_hooks_exits_two_with_an_unknown_line_and_no_traceback(self):
        case = new_case()
        script = copy_cheap(case, hooks=False)
        self.assertFalse(os.path.isdir(os.path.join(case, "copy", "hooks")), "premise: the copy has a hooks/ beside it")
        rc, lines = run_in(case, config_text(["Pass one"]), script)
        self.assertEqual(rc, 2, "exit %d for a copy with no hooks/, want 2: the copy cannot run, which is unknown" % rc)
        self.assertTrue(any(line.startswith("unknown cheap-lints:") for line in lines), "no `unknown cheap-lints:` line: %r" % lines)
        self.assertFalse(any("Traceback" in line for line in lines), "a copy with no hooks/ prints a traceback: %r" % lines)

    def test_no_claude_settings_checkout_exits_two_with_an_unknown_line_and_no_traceback(self):
        case = new_case()
        script = copy_cheap(case, hooks=True)
        self.assertFalse(os.path.isdir(os.path.join(case, "copy", "merge")), "premise: the copy has a merge/ beside it")
        self.assertFalse(os.path.isfile(os.path.join(case, "config", "CLAUDE.md")), "premise: the config dir points at a checkout")
        rc, lines = run_in(case, config_text(["Pass one"]), script)
        self.assertEqual(rc, 2, "exit %d with no claude-settings checkout found, want 2: nothing can run, which is unknown" % rc)
        self.assertTrue(any(line.startswith("unknown cheap-lints: no claude-settings checkout found") for line in lines),
                        "no `unknown cheap-lints: no claude-settings checkout found` line: %r" % lines)
        self.assertFalse(any("Traceback" in line for line in lines), "a run with no checkout prints a traceback: %r" % lines)


def fixture_git(repo, case, *args):
    """A git command in the fixture repo `repo` -> its stdout, stripped. The identity is on the command: a fixture reads no global config."""
    done = subprocess.run(["git", "-c", "user.name=cheap", "-c", "user.email=cheap@example.invalid", *args], cwd=repo, env=git_env(case),
                          capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, (args, done.stdout, done.stderr)
    return done.stdout.strip()


def write_files(repo, names):
    """Write each of `names` in the fixture repo `repo`, its text its own name."""
    for name in names:
        with open(os.path.join(repo, name), "w", encoding="utf-8") as f:
            f.write(name + "\n")


def make_change(case, checks, breaking=True, origin=True, base_files=(), tip=None):
    """A repo at <case>/repo: a base commit holding PROBE_WORKFLOW, the stamp for `checks` and `base_files`, then a head commit on it. The head
    adds BROKEN when `breaking`, else note.txt, so its tree differs from the base's. With `origin`, origin/main names the base commit: a ref of
    this repo, with no remote. `tip` = (remove, add) makes origin/main name a commit T cut from the base instead: T removes and adds those
    files, so the checkout is behind the tip and the merge base of HEAD and origin/main is the base commit.
    -> (repo, the base commit's full sha, recorded as the commit is made)."""
    repo = make_fixture(case, config_text(checks), workflow=PROBE_WORKFLOW.replace("__PROBE__", os.path.join(case, "probe.log")))
    write_files(repo, base_files)
    fixture_git(repo, case, "add", "-A")
    fixture_git(repo, case, "commit", "-q", "-m", "base")
    base = fixture_git(repo, case, "rev-parse", "HEAD")
    target = base
    if tip is not None:
        remove, add = tip
        fixture_git(repo, case, "switch", "-q", "-c", "tip-side")
        for name in remove:
            fixture_git(repo, case, "rm", "-q", name)
        write_files(repo, add)
        fixture_git(repo, case, "add", "-A")
        fixture_git(repo, case, "commit", "-q", "-m", "tip")
        target = fixture_git(repo, case, "rev-parse", "HEAD")
        fixture_git(repo, case, "switch", "-q", "-")
    with open(os.path.join(repo, "BROKEN" if breaking else "note.txt"), "w", encoding="utf-8") as f:
        f.write("this change\n")
    fixture_git(repo, case, "add", "-A")
    fixture_git(repo, case, "commit", "-q", "-m", "change")
    if origin:
        fixture_git(repo, case, "update-ref", "refs/remotes/origin/main", target)
    return repo, base


def cheap_in(repo, case, args=()):
    """Run this checkout's bin/cheap-lints in the fixture repo `repo` of `case`. -> (exit code, output lines)."""
    return run_repo(repo, case, CHEAP, args)


def runs_of(case, step):
    """-> the folder of each run of `step` that the probe of `case` logged, oldest first. A run that the step cache answered logs none."""
    try:
        with open(os.path.join(case, "probe.log"), encoding="utf-8") as f:
            rows = [line.rstrip("\n").split("\t", 1) for line in f if line.strip()]
    except FileNotFoundError:
        return []
    return [folder for name, folder in rows if name == step]


def base_runs(case, step, repo):
    """-> the folders outside the checkout `repo` where `step` ran: each is a copy of the base commit."""
    here = os.path.realpath(repo)
    return [folder for folder in runs_of(case, step) if os.path.realpath(folder) != here]


def phrase_after(lines, verdict, name):
    """-> the text after `<verdict> <name> (` on the line that opens so, or None when no line does."""
    opening = "%s %s (" % (verdict, name)
    return next((line[len(opening):] for line in lines if line.startswith(opening)), None)


PASSES_ON_BASE = r"passes on ([0-9a-f]{9}): this change broke it\): .+"  # the sha form is the base commit's first nine hex digits
ALSO_FAILS_ON_BASE = r"also fails on ([0-9a-f]{9})\): .+"
BASE_NOT_READ = r"base not read: .+?\): .+"


class BaseRun(unittest.TestCase):
    """The base read of a failing check (bin/cheap-lints through merge.pre_ready_rows). A check that FAILs on the checkout runs once in a copy of
    the merge base of HEAD and origin/main. Its row then says `passes on <sha9>: this change broke it`, `also fails on <sha9>`, or `base not read: <reason>`. Every
    such row stays `fail`, and the run exits 1. A check that passes on the checkout runs no copy. Each case counts the probe's runs."""

    def test_passes_on_base_names_the_base_and_says_this_change_broke_it(self):
        case = new_case()
        repo, base = make_change(case, ["Pass one", "Breaks on change"])
        rc, lines = cheap_in(repo, case)
        copies = base_runs(case, "Breaks on change", repo)
        self.assertEqual(len(copies), 1, "the check that fails on the checkout ran in a copy of the base %d times, want once: %r" % (len(copies), lines))
        rest = phrase_after(lines, "fail", "Breaks on change")
        self.assertIsNotNone(rest, "no `fail Breaks on change (` line, so the row names no base: %r" % lines)
        match = re.match(PASSES_ON_BASE, rest)
        self.assertIsNotNone(match, "the row does not say `passes on <sha9>: this change broke it`: %r" % rest)
        self.assertEqual(match.group(1), base[:9], "the row names %s as the base, not the base commit %s" % (match.group(1), base[:9]))
        self.assertEqual(rc, 1, "exit %d with the check failing on the checkout, want 1: a base pass lifts nothing" % rc)

    def test_also_fails_on_base_says_so_and_still_exits_one(self):
        case = new_case()
        repo, base = make_change(case, ["Pass one", "Breaks everywhere"], breaking=False)
        rc, lines = cheap_in(repo, case)
        copies = base_runs(case, "Breaks everywhere", repo)
        self.assertEqual(len(copies), 1, "the check that fails on both ran in a copy of the base %d times, want once: %r" % (len(copies), lines))
        rest = phrase_after(lines, "fail", "Breaks everywhere")
        self.assertIsNotNone(rest, "no `fail Breaks everywhere (` line, so the row names no base: %r" % lines)
        match = re.match(ALSO_FAILS_ON_BASE, rest)
        self.assertIsNotNone(match, "the row does not say `also fails on <sha9>`: %r" % rest)
        self.assertEqual(match.group(1), base[:9], "the row names %s as the base, not the base commit %s" % (match.group(1), base[:9]))
        self.assertEqual(rc, 1, "exit %d when the base fails too, want 1: a base fail never turns the row into a pass" % rc)

    def test_a_passing_check_runs_no_copy_of_the_base(self):
        """The green control: a check that passes on the checkout is never read against the base, so no copy runs."""
        case = new_case()
        repo, base = make_change(case, ["Pass one", "Breaks on change"], breaking=False)
        rc, lines = cheap_in(repo, case)
        self.assertEqual(len(runs_of(case, "Breaks on change")), 1, "premise: the checkout did not run the passing check once: %r" % lines)
        self.assertTrue(any(line.startswith("pass Breaks on change") for line in lines), "premise: no `pass Breaks on change` line: %r" % lines)
        self.assertEqual(base_runs(case, "Breaks on change", repo), [], "a passing check ran in a copy of the base")
        self.assertEqual(rc, 0, "exit %d with every check passing, want 0" % rc)

    def test_base_not_read_when_origin_main_is_absent(self):
        case = new_case()
        repo, base = make_change(case, ["Pass one", "Breaks on change"], origin=False)
        rc, lines = cheap_in(repo, case)
        self.assertTrue(any(line.startswith("fail Breaks on change") for line in lines), "premise: the checkout's run did not FAIL the check: %r" % lines)
        rest = phrase_after(lines, "fail", "Breaks on change")
        self.assertIsNotNone(rest, "no `fail Breaks on change (` line, so the row names no base: %r" % lines)
        self.assertRegex(rest, BASE_NOT_READ, "a check with no origin/main names no reason it could not read the base: %r" % rest)
        self.assertEqual(rc, 1, "exit %d with the check failing and the base unread, want 1, not 2: the failure is still a failure" % rc)

    def test_two_failing_checks_each_get_one_copy_of_the_base(self):
        case = new_case()
        checks = ["Breaks on change", "Breaks everywhere"]
        repo, base = make_change(case, checks)
        rc, lines = cheap_in(repo, case)
        self.assertEqual({name: len(base_runs(case, name, repo)) for name in checks}, {name: 1 for name in checks},
                         "copies of the base per failing check, want one each: %r" % lines)
        rest_a = phrase_after(lines, "fail", "Breaks on change")
        rest_b = phrase_after(lines, "fail", "Breaks everywhere")
        self.assertIsNotNone(rest_a, "no `fail Breaks on change (` line: %r" % lines)
        self.assertIsNotNone(rest_b, "no `fail Breaks everywhere (` line: %r" % lines)
        self.assertIsNotNone(re.match(PASSES_ON_BASE, rest_a), "the first row does not say `passes on <sha9>`: %r" % rest_a)
        self.assertIsNotNone(re.match(ALSO_FAILS_ON_BASE, rest_b), "the second row does not say `also fails on <sha9>`: %r" % rest_b)
        self.assertEqual(rc, 1, "exit %d with two failing checks, want 1" % rc)

    def test_a_second_run_takes_the_passing_base_from_the_cache(self):
        case = new_case()
        repo, base = make_change(case, ["Breaks on change"])
        cheap_in(repo, case)
        self.assertEqual(len(base_runs(case, "Breaks on change", repo)), 1, "premise: the first run did not read the base once")
        rc, lines = cheap_in(repo, case)
        self.assertEqual(len(base_runs(case, "Breaks on change", repo)), 1,
                         "the second run ran the base again: its passing result was not served from the cache")
        rest = phrase_after(lines, "fail", "Breaks on change")
        self.assertIsNotNone(rest, "the second run printed no `fail Breaks on change (` line: %r" % lines)
        self.assertIsNotNone(re.match(PASSES_ON_BASE, rest), "the second run's row does not say `passes on <sha9>`: %r" % rest)

    def test_history_check_never_claims_a_base_result_it_did_not_read(self):
        """The fixture's Silent undo check is a stand-in: it runs `git rev-parse HEAD` and reads BROKEN, so a base copy's row depends on BROKEN
        alone. The real check (CI's step, `lint/check_silent_undo.py --upstream origin/<base> --head HEAD`) reads history. A base copy is a
        linked worktree, so its .git is a file and git reads that history; the real check's range origin/<base>..HEAD is empty when the copy
        is at origin/<base>, so it passes there. This case pins the row's shape: it names the base as passing or says it was not read. It
        never names a base fail, because the stand-in fails only where BROKEN is, and the base has none."""
        case = new_case()
        repo, base = make_change(case, ["Silent undo check"])
        rc, lines = cheap_in(repo, case)
        self.assertTrue(any(line.startswith("fail Silent undo check") for line in lines), "premise: the checkout's run did not FAIL the check: %r" % lines)
        rest = phrase_after(lines, "fail", "Silent undo check")
        self.assertIsNotNone(rest, "no `fail Silent undo check (` line, so the row names no base: %r" % lines)
        self.assertNotIn("also fails on", rest, "the history check claims a fail on a base it could not read: %r" % rest)
        self.assertTrue(re.match(PASSES_ON_BASE, rest) or re.match(BASE_NOT_READ, rest),
                        "the history check's row names no base it read or could not read: %r" % rest)

    def test_base_run_leaves_the_checkout_as_it_was(self):
        case = new_case()
        repo, base = make_change(case, ["Breaks on change"])
        head = fixture_git(repo, case, "rev-parse", "HEAD")
        status = fixture_git(repo, case, "status", "--porcelain")
        index = fixture_git(repo, case, "ls-files", "--stage")
        cheap_in(repo, case)
        self.assertEqual(len(base_runs(case, "Breaks on change", repo)), 1,
                         "premise: the base was not read, so nothing shows whether the read touched the checkout")
        self.assertEqual(fixture_git(repo, case, "rev-parse", "HEAD"), head, "the base run moved the checkout's HEAD")
        self.assertEqual(fixture_git(repo, case, "status", "--porcelain"), status, "the base run changed the checkout's working tree")
        self.assertEqual(fixture_git(repo, case, "ls-files", "--stage"), index, "the base run changed the checkout's index")
        self.assertTrue(os.path.isfile(os.path.join(repo, "BROKEN")), "the base run removed the checkout's BROKEN")

    def test_level_checkout_names_the_base_commit_as_before(self):
        """The control: the merge base of HEAD and origin/main is origin/main itself, so the base read is the one it always was."""
        case = new_case()
        repo, base = make_change(case, ["Pass one", "Breaks on change"])
        self.assertEqual(fixture_git(repo, case, "merge-base", "HEAD", "origin/main"), base,
                         "premise: the merge base is not origin/main, so the checkout is behind and this case is no control")
        rc, lines = cheap_in(repo, case)
        rest = phrase_after(lines, "fail", "Breaks on change")
        self.assertIsNotNone(rest, "no `fail Breaks on change (` line, so the row names no base: %r" % lines)
        match = re.match(PASSES_ON_BASE, rest)
        self.assertIsNotNone(match, "the level checkout's row does not say `passes on <sha9>: this change broke it`: %r" % rest)
        self.assertEqual(match.group(1), base[:9], "the row names %s as the base, not the base commit %s" % (match.group(1), base[:9]))
        self.assertEqual(rc, 1, "exit %d with the check failing on the checkout, want 1" % rc)

    def test_behind_the_base_tip_reads_the_merge_base_and_says_also_fails(self):
        """A lane cut before the base's tip removes BROKEN. The check fails at the merge base and on the checkout, and passes at the tip the checkout
        is behind. The row names the merge base as also failing, so it blames this change for nothing the base lacks."""
        case = new_case()
        repo, base = make_change(case, ["Pass one", "Breaks on change"], breaking=False, base_files=["BROKEN"], tip=(["BROKEN"], ["tip.txt"]))
        tip = fixture_git(repo, case, "rev-parse", "refs/remotes/origin/main")
        self.assertEqual(fixture_git(repo, case, "merge-base", "HEAD", "origin/main"), base,
                         "premise: the merge base of HEAD and origin/main is not the commit the change started from")
        self.assertNotEqual(base, tip, "premise: the merge base is the tip, so the checkout is level and this case is no behind case")
        self.assertEqual(fixture_git(repo, case, "ls-tree", "--name-only", base, "BROKEN"), "BROKEN",
                         "premise: the merge base holds BROKEN, so the check fails there")
        self.assertEqual(fixture_git(repo, case, "ls-tree", "--name-only", tip, "BROKEN"), "",
                         "premise: the tip lacks BROKEN, so the check passes there")
        rc, lines = cheap_in(repo, case)
        copies = base_runs(case, "Breaks on change", repo)
        self.assertEqual(len(copies), 1, "the failing check ran in a copy of the base %d times, want once: %r" % (len(copies), lines))
        rest = phrase_after(lines, "fail", "Breaks on change")
        self.assertIsNotNone(rest, "no `fail Breaks on change (` line, so the row names no base: %r" % lines)
        match = re.match(ALSO_FAILS_ON_BASE, rest)
        self.assertIsNotNone(match, "the row does not say `also fails on <sha9>`: the base read did not run on the merge base: %r" % rest)
        self.assertEqual(match.group(1), base[:9], "the row names %s as the base, not the merge base %s" % (match.group(1), base[:9]))
        self.assertEqual(rc, 1, "exit %d when the merge base fails too, want 1" % rc)

    def test_behind_the_base_tip_reads_the_merge_base_and_says_this_change_broke_it(self):
        """The change adds BROKEN. The check passes at the merge base and fails on the checkout and at the tip the checkout is behind. The row names the
        merge base, where the check passed, and not the tip, where it fails."""
        case = new_case()
        repo, base = make_change(case, ["Pass one", "Breaks on change"], tip=([], ["BROKEN", "tip.txt"]))
        tip = fixture_git(repo, case, "rev-parse", "refs/remotes/origin/main")
        self.assertEqual(fixture_git(repo, case, "merge-base", "HEAD", "origin/main"), base,
                         "premise: the merge base of HEAD and origin/main is not the commit the change started from")
        self.assertNotEqual(base, tip, "premise: the merge base is the tip, so the checkout is level and this case is no behind case")
        self.assertEqual(fixture_git(repo, case, "ls-tree", "--name-only", base, "BROKEN"), "",
                         "premise: the merge base lacks BROKEN, so the check passes there")
        self.assertEqual(fixture_git(repo, case, "ls-tree", "--name-only", tip, "BROKEN"), "BROKEN",
                         "premise: the tip holds BROKEN, so the check fails there too")
        rc, lines = cheap_in(repo, case)
        copies = base_runs(case, "Breaks on change", repo)
        self.assertEqual(len(copies), 1, "the failing check ran in a copy of the base %d times, want once: %r" % (len(copies), lines))
        rest = phrase_after(lines, "fail", "Breaks on change")
        self.assertIsNotNone(rest, "no `fail Breaks on change (` line, so the row names no base: %r" % lines)
        match = re.match(PASSES_ON_BASE, rest)
        self.assertIsNotNone(match, "the row does not say `passes on <sha9>: this change broke it`: the base read did not run on the merge base: %r" % rest)
        self.assertEqual(match.group(1), base[:9], "the row names %s as the base, not the merge base %s" % (match.group(1), base[:9]))
        self.assertEqual(rc, 1, "exit %d with the check failing on the checkout, want 1" % rc)

    def test_no_merge_base_reads_base_not_read(self):
        """origin/main names an unrelated root commit holding the base's tree, so HEAD and origin/main share no commit. The row says base not
        read, and no copy of that commit runs."""
        case = new_case()
        repo, base = make_change(case, ["Pass one", "Breaks on change"])
        tree = fixture_git(repo, case, "rev-parse", base + "^{tree}")
        unrelated = fixture_git(repo, case, "commit-tree", tree, "-m", "unrelated base")
        fixture_git(repo, case, "update-ref", "refs/remotes/origin/main", unrelated)
        done = subprocess.run(["git", "merge-base", "HEAD", "origin/main"], cwd=repo, env=git_env(case), capture_output=True, text=True)
        self.assertEqual(done.returncode, 1, "premise: git found a merge base of HEAD and origin/main, so the case has one to read: %r" % done.stdout)
        rc, lines = cheap_in(repo, case)
        self.assertTrue(any(line.startswith("fail Breaks on change") for line in lines), "premise: the checkout's run did not FAIL the check: %r" % lines)
        rest = phrase_after(lines, "fail", "Breaks on change")
        self.assertIsNotNone(rest, "no `fail Breaks on change (` line, so the row names no base: %r" % lines)
        self.assertRegex(rest, BASE_NOT_READ, "a check with no merge base names no reason the base was not read: %r" % rest)
        self.assertEqual(base_runs(case, "Breaks on change", repo), [], "a check with no merge base ran in a copy of origin/main, the unrelated commit")
        self.assertEqual(rc, 1, "exit %d with the check failing and no base read, want 1" % rc)


# CodeCheckReady: the checks job's Code check step (uses: $/actions/code-check) is a ready check. Its step text is read from checks.yml
# and its list entry from the repo's stamp.json, so the case fails on a repo whose list lacks the entry.
CODE_CHECK = "Code check"
REAL_CHECKS = os.path.join(ROOT, ".github", "workflows", "checks.yml")
REAL_CONFIG = os.path.join(ROOT, ".github", "stamp.json")
# What the step reads from the tree: its action, the tool table and the ruff config (the set LintTools in lint/test_ci_job.py copies).
CODE_FILES = ("actions/code-check", "lint/code_check_standard.json", "ruff.toml")
CODE_BASE = "def check():\n    return 1\n"  # origin/main's a.py: clean
CODE_CLEAN = "def check():\n    return 1\n\n\ndef other():\n    return 2\n"  # a lane's a.py that adds a second, differently named def
CODE_DUPLICATE = "def check():\n    return 1\n\n\ndef check():\n    return 2\n"  # ruff's F811: a function defined twice
# A stand-in for ruff 0.17.3: F811 for each top-level def a file repeats, exit 1; else exit 0. code_check.py calls `ruff check --force-exclude FILES`.
FAKE_RUFF = """#!/usr/bin/env python3
import re
import sys

found = False
for path in (a for a in sys.argv[1:] if a.endswith(".py")):
    seen = {}
    with open(path, encoding="utf-8") as f:
        for number, line in enumerate(f, 1):
            m = re.match(r"def (\\w+)\\(", line)
            if m and m.group(1) in seen:
                print("%s:%d:1: F811 Redefinition of unused `%s` from line %d" % (path, number, m.group(1), seen[m.group(1)]))
                found = True
            elif m:
                seen[m.group(1)] = number
sys.exit(1 if found else 0)
"""


def checks_step(name):
    """The raw text of the one step named `name` in checks.yml's job checks, read at test time. A missing or doubled step is a scope failure."""
    with open(REAL_CHECKS, encoding="utf-8") as f:
        steps = [st for st in ws.step_blocks(ws.job_block(f.read(), "checks")) if ws.step_key(st, "name") == name]
    if len(steps) != 1:
        raise AssertionError("scope: checks.yml job checks holds %d steps named %r, not one" % (len(steps), name))
    return steps[0]


def records_stub():
    """The records step's raw text, from WORKFLOW: the one fixture's stub, which passes only when PR_BODY is set."""
    return next(st for st in ws.step_blocks(ws.job_block(WORKFLOW, "checks")) if ws.step_key(st, "name") == RECORDS_STEP)


def real_ready_checks():
    """merge.readyChecks of the repo's own .github/stamp.json: the list the ready run reads on this checkout."""
    with open(REAL_CONFIG, encoding="utf-8") as f:
        return json.load(f).get("merge", {}).get("readyChecks") or []


def write_file(repo, rel, text):
    with open(os.path.join(repo, rel), "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def git_run(case, repo, *args):
    """One git command in the fixture repo, with a commit identity. Its output is read only on failure (check=True raises)."""
    env = dict(git_env(case), GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    subprocess.run(["git", "-C", repo, *args], check=True, env=env, capture_output=True)


def code_case(case, lane_text):
    """A fixture repo. origin/main holds the Code check step beside the records stub, the code-check action, its table and ruff
    config, and a clean a.py. The lane branch rewrites a.py to `lane_text`. The stamp lists the real readyChecks entries that
    this fixture's steps name, in the repo's own order. -> the repo path."""
    workflow = ("name: code-check fixture\non: push\njobs:\n  checks:\n    runs-on: ubuntu-latest\n    steps:\n"
                + records_stub() + checks_step(CODE_CHECK))
    ready_json = config_text([name for name in real_ready_checks() if name in (CODE_CHECK, RECORDS_STEP)])
    repo = make_fixture(case, ready_json, workflow=workflow)
    for rel in CODE_FILES:
        src, dst = os.path.join(ROOT, rel), os.path.join(repo, rel)
        if os.path.isdir(src):
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("tools", "__pycache__"))
        else:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)
    write_file(repo, "a.py", CODE_BASE)
    git_run(case, repo, "add", "-A")
    git_run(case, repo, "commit", "-qm", "base")
    git_run(case, repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    git_run(case, repo, "checkout", "-qb", "lane")
    write_file(repo, "a.py", lane_text)
    git_run(case, repo, "add", "-A")
    git_run(case, repo, "commit", "-qm", "lane")
    return repo


def no_pipx_dir(case):
    """A PATH folder with python3 and every tool of /bin and /usr/bin except pipx. NO_PIPX (lint/test_ci_job.py) drops each folder
    that holds pipx, and here that folder holds python3 too (/opt/homebrew/bin), so it cannot serve this case."""
    shim = os.path.join(case, "no-pipx-bin")
    os.makedirs(shim)
    os.symlink(sys.executable, os.path.join(shim, "python3"))
    for folder in ("/bin", "/usr/bin"):
        for name in os.listdir(folder):
            if name not in ("pipx", "python3") and not os.path.lexists(os.path.join(shim, name)):
                os.symlink(os.path.join(folder, name), os.path.join(shim, name))
    return shim


# A pipx body (ready_run's `pipx`) that exits 1 on stderr alone, as pipx does when no route to the index lets it fetch nothing.
FETCH_FAILS = 'echo "Could not fetch index" >&2\nexit 1'
# A pipx body that runs the stand-in ruff with the call's arguments: the tool started, and its findings are its own.
RUFF_RUNS = 'exec "%(ruff)s" "$@"'


def ready_run(case, repo, tools, pipx=None):
    """Runs bin/cheap-lints main in the fixture repo. With `tools`, the stand-in ruff comes first on PATH and CODE_CHECK_TOOLS=path, the
    switch code_check.py reads for tools already on PATH; without, PATH has no pipx. `pipx` (a sh body; %(ruff)s is the stand-in ruff's
    path) is a pipx stand-in on PATH instead, which logs each call to case/pipx-calls.txt. -> (exit code, output lines)."""
    env = git_env(case)
    env.pop("CODE_CHECK_TOOLS", None)
    env["PR_BODY"] = "a pull request body"  # the records stub runs only with a body; cheap-lints drops it without one
    if tools or pipx is not None:
        bin_dir = os.path.join(case, "ruff-bin")
        os.makedirs(bin_dir)
        write_file(bin_dir, "ruff", FAKE_RUFF)
        os.chmod(os.path.join(bin_dir, "ruff"), 0o755)
    if tools:
        env["PATH"] = os.pathsep.join([bin_dir, env.get("PATH", "")])
        env["CODE_CHECK_TOOLS"] = "path"
    elif pipx is not None:
        shim = os.path.join(case, "pipx-bin")
        os.makedirs(shim)
        calls = os.path.join(case, "pipx-calls.txt")
        write_file(shim, "pipx", '#!/bin/sh\necho "$*" >> "%s"\n%s\n' % (calls, pipx % {"ruff": os.path.join(bin_dir, "ruff")}))
        os.chmod(os.path.join(shim, "pipx"), 0o755)
        env["PATH"] = os.pathsep.join([shim, env.get("PATH", "")])
    else:
        env["PATH"] = no_pipx_dir(case)
    done = subprocess.run([sys.executable, CHEAP, "main"], cwd=repo, env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True, encoding="utf-8", timeout=300)
    return done.returncode, done.stdout.splitlines()


def pipx_calls(path):
    """The pipx stand-in's calls, one a line; empty when it was never called."""
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return f.read()


@unittest.skipUnless(os.name == "posix", "the stand-in ruff is a POSIX script that PATH reaches")
class CodeCheckReady(unittest.TestCase):
    """The ready run reads the Code check step and runs it on the tree. The list is the repo's real readyChecks; ruff is FAKE_RUFF, so no
    case installs a tool or uses the network, and the tool-miss case drops pipx from PATH. The fetch cases put a pipx stand-in on PATH
    instead, which either fails as pipx does with no route to the index or runs FAKE_RUFF."""

    def run_on(self, lane_text, tools=True):
        case = new_case()
        return ready_run(case, code_case(case, lane_text), tools)

    def test_a_ruff_error_fails_the_ready_run_on_a_code_check_line(self):
        rc, lines = self.run_on(CODE_DUPLICATE)
        self.assertIn(("fail", CODE_CHECK), verdicts(lines),
                      "the ready run printed no `fail Code check` line for a ruff error: Code check is not a ready check: %r" % lines)
        log = re.search(r"log=(\S+)", "\n".join(lines))  # the ready run prints the ci-job log it wrote; ruff's own line sits there, not in the rows
        text = ""
        if log:
            with open(log.group(1), encoding="utf-8") as f:
                text = f.read()
        self.assertIn("F811", text, "the ruff finding is not in the ci-job log the ready run names: %r" % lines)
        self.assertEqual(rc, 1, "a ready run with a failing check did not exit 1: %r" % lines)

    def test_a_clean_tree_passes_the_code_check_in_the_ready_run(self):
        rc, lines = self.run_on(CODE_CLEAN)
        self.assertIn(("pass", CODE_CHECK), verdicts(lines),
                      "the ready run printed no `pass Code check` line for a clean tree: %r" % lines)
        self.assertEqual(rc, 0, "a ready run whose checks all pass did not exit 0: %r" % lines)

    def test_the_records_stub_in_the_same_fixture_passes(self):  # the control: a listed step passes here, so the fixture and runner are sound
        rc, lines = self.run_on(CODE_CLEAN)
        self.assertIn(("pass", RECORDS_STEP), verdicts(lines), "the records stub did not pass in the fixture: %r" % lines)
        self.assertEqual(rc, 0, "the fixture's ready run did not exit 0: %r" % lines)

    def test_with_no_pipx_the_code_check_is_unknown_and_names_pipx(self):
        rc, lines = self.run_on(CODE_CLEAN, tools=False)
        self.assertNotIn(("pass", CODE_CHECK), verdicts(lines), "a Code check with no pipx reads pass: %r" % lines)
        row = [line for line in lines if line.startswith("unknown %s" % CODE_CHECK)]
        self.assertTrue(row, "the ready run printed no `unknown Code check` line with pipx absent: %r" % lines)
        self.assertIn("pipx", row[0], "the unknown Code check line does not name the missing tool: %r" % row[0])
        self.assertEqual(rc, 2, "a ready run with an unknown check did not exit 2: %r" % lines)

    def run_with_pipx(self, lane_text, body):
        """A ready run whose pipx is the stand-in `body`, which makes the stand-in ruff run. -> (exit code, lines, the calls file)."""
        case = new_case()
        rc, lines = ready_run(case, code_case(case, lane_text), False, pipx=body)
        return rc, lines, os.path.join(case, "pipx-calls.txt")

    def test_a_ruff_that_cannot_be_fetched_is_unknown_not_fail(self):
        rc, lines, calls = self.run_with_pipx(CODE_CLEAN, FETCH_FAILS)
        self.assertIn("ruff==", pipx_calls(calls), "pipx was never asked for ruff, so the unknown is not the fetch: %r" % lines)
        self.assertNotIn(("fail", CODE_CHECK), verdicts(lines),
                         "a ruff that could not be fetched reads `fail Code check`, and the ready run blames the branch: %r" % lines)
        row = [line for line in lines if line.startswith("unknown %s" % CODE_CHECK)]
        self.assertTrue(row, "the ready run printed no `unknown Code check` line for a ruff that could not be fetched: %r" % lines)
        self.assertIn("ruff", row[0], "the unknown Code check line does not name the tool that could not be fetched: %r" % row[0])
        self.assertEqual(rc, 2, "a ready run with an unknown check did not exit 2: %r" % lines)

    def test_a_ruff_finding_through_pipx_fails_the_ready_run(self):  # control: a ruff that started and found a duplicate still fails
        rc, lines, calls = self.run_with_pipx(CODE_DUPLICATE, RUFF_RUNS)
        self.assertIn("ruff==", pipx_calls(calls), "pipx was never asked for ruff, so the control proves nothing: %r" % lines)
        self.assertIn(("fail", CODE_CHECK), verdicts(lines), "a ruff finding through pipx did not fail the ready run: %r" % lines)
        self.assertEqual(rc, 1, "a ready run with a failing check did not exit 1: %r" % lines)

    def test_a_clean_ruff_through_pipx_passes_the_ready_run(self):  # control
        rc, lines, calls = self.run_with_pipx(CODE_CLEAN, RUFF_RUNS)
        self.assertIn("ruff==", pipx_calls(calls), "pipx was never asked for ruff, so the control proves nothing: %r" % lines)
        self.assertIn(("pass", CODE_CHECK), verdicts(lines), "a clean ruff through pipx did not pass the ready run: %r" % lines)
        self.assertEqual(rc, 0, "a ready run whose checks all pass did not exit 0: %r" % lines)


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
