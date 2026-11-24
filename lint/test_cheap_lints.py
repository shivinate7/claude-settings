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
# `pass NAME`, `fail NAME` or `unknown NAME`. The name ends at a `: ` or at the line's end, so `other:Other pass` reads whole.
VERDICT = re.compile(r"^(pass|fail|unknown) (.+?)(?=: |$)")
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
    repo = make_fixture(case, text)
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


def ready_run(case, repo, tools):
    """Runs bin/cheap-lints main in the fixture repo. With `tools`, the stand-in ruff comes first on PATH and CODE_CHECK_TOOLS=path, the
    switch code_check.py reads for tools already on PATH; without, PATH has no pipx. -> (exit code, output lines)."""
    env = git_env(case)
    env.pop("CODE_CHECK_TOOLS", None)
    env["PR_BODY"] = "a pull request body"  # the records stub runs only with a body; cheap-lints drops it without one
    if tools:
        bin_dir = os.path.join(case, "ruff-bin")
        os.makedirs(bin_dir)
        write_file(bin_dir, "ruff", FAKE_RUFF)
        os.chmod(os.path.join(bin_dir, "ruff"), 0o755)
        env["PATH"] = os.pathsep.join([bin_dir, env.get("PATH", "")])
        env["CODE_CHECK_TOOLS"] = "path"
    else:
        env["PATH"] = no_pipx_dir(case)
    done = subprocess.run([sys.executable, CHEAP, "main"], cwd=repo, env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True, encoding="utf-8", timeout=300)
    return done.returncode, done.stdout.splitlines()


@unittest.skipUnless(os.name == "posix", "the stand-in ruff is a POSIX script that PATH reaches")
class CodeCheckReady(unittest.TestCase):
    """The ready run reads the Code check step and runs it on the tree. The list is the repo's real readyChecks; ruff is FAKE_RUFF, so no
    case installs a tool or uses the network, and the tool-miss case drops pipx from PATH."""

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


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
