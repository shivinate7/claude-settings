#!/usr/bin/env python3
"""Suite for `merge --lane-lint`: the lint a lane passes before it joins a batch (lanes-run-no-full-ci-job).

Run: python3 merge/test_lane_lint.py
The lint is bin/ci-job's `checks --lint`, reached through merge.CI_JOB. Each case points CI_JOB at a stub that
prints scripted step lines and exits with a scripted code, so no real lint runs. The stub logs each call, so a
case reads what the tool ran, in which tree, at which head. The repo builder, the fakes and the cloud-session
fixture come from merge/test_merge.py: a case extends that fixture, it does not copy it. The draft step's ready check
(class ReadyChecks) runs the same stub, through CiJobStub.
The SIGTERM case runs merge in a subprocess through HARNESS, which names the same stub; it is the one case that does not patch CI_JOB.
BatchLintFlags runs the real bin/ci-job through merge.lane_lint on a batch's four checks.yml lint CI steps, each script logged once with its argv; cost per case: one ci-job copy and run, one worktree, four CI step runs, 0.5 s measured (3 runs of 2 cases). Its two lint-set cases (no lint step; a step that runs only off a pull request) run the same way with their own checks job.
The review-range cases (LaneLint's test_review_range_*) answer the parent pull requests a body names from ParentHost, so no case reads a parent from git or GitHub.
Temp files: this run's folder (lint/_test_temp.py), removed at exit.
"""
import ast, atexit, contextlib, io, json, os, re, shlex, shutil, signal, subprocess, sys, tempfile, time, unittest, unittest.mock, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.append(os.path.join(os.path.dirname(HERE), "lint"))  # append: no lint module shadows one this suite imports
import _test_temp  # noqa: E402  test-temp-standard: this run's folder (lint/_test_temp.py)
import test_merge as tm  # noqa: E402  the git half's fixture and fakes; importing it runs none of its cases
import merge  # noqa: E402
from workflow_steps import job_block, run_body, step_blocks, step_env, step_key, step_with  # noqa: E402  the one home of the step parser

RUN_FOLDER = _test_temp.run_folder()
atexit.register(shutil.rmtree, RUN_FOLDER, True)

PASSING = [("PASS", "record slugs"), ("PASS", "ste lint")]
FAILING = [("PASS", "record slugs"), ("FAIL", "comment narration")]
UNKNOWN = [("PASS", "record slugs"), ("unknown", "shellcheck")]

STUB = '''import json, os, subprocess, sys, time
LOG, STEPS, RC, STEP_LOG, SLEEP, PARENT = __LOG__, __STEPS__, __RC__, __STEP_LOG__, __SLEEP__, os.getppid()
def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True).stdout.strip()
detached = subprocess.run(["git", "symbolic-ref", "-q", "HEAD"], capture_output=True).returncode != 0
with open(LOG, "a", encoding="utf-8") as f:
    print(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd(), "head": git("rev-parse", "HEAD"), "detached": detached, "pr_body": os.environ.get("CI_JOB_PR_BODY")}), file=f)
if "--plan" in sys.argv:
    for state, name in STEPS:
        print("would run " + name)
    sys.exit(0)
end = time.time() + SLEEP  # a lint that runs long: it ends after SLEEP s, or at once when the run that started it is gone
while time.time() < end and os.getppid() == PARENT:
    time.sleep(0.05)
lines = ["%-15s %s: stub step" % (state, name) for state, name in STEPS]
print("\\n".join(lines))
if RC == 1:
    with open(STEP_LOG, "w", encoding="utf-8") as f:
        f.write("\\n".join(lines) + "\\n")
    print("log=" + STEP_LOG)  # the last line: the refusal reads it as the failing run's log
sys.exit(RC)
'''

# merge.py fixes CI_JOB at import, so a subprocess run names the stub here, before main runs. Same argv and exit code as merge.py's __main__.
HARNESS = '''import sys
sys.path.insert(0, __HERE__)
import merge
merge.CI_JOB = __STUB__
sys.exit(merge.main(sys.argv[1:]))
'''

# Added to STUB before its verdict lines: one `start:` line per step on stderr, then a wait for the GO file. The wait is
# a bound only (20 s): the case creates GO once it has read the first announcement from merge's stderr, so the lint
# cannot end before the announcement is read.
PROGRESS = '''GO = __GO__
for _state, _name in STEPS:
    print("start: " + _name, file=sys.stderr, flush=True)
end = time.time() + 20
while not os.path.exists(GO) and time.time() < end:
    time.sleep(0.05)
'''

WORKFLOW = """name: t
on: push
jobs:
  checks:
    runs-on: ubuntu-latest
    steps:
      - name: Lint one
        run: python3 lint/a.py
      - name: Make lint-py
        run: make lint-py
      - name: Lint two
        run: python3 lint/b.py
"""


def pass_lines(text):
    return [line for line in text.splitlines() if line.startswith("PASS:")]


class NoLock:
    """The lane run takes no merge lock: a lock call fails the case."""
    def acquire(self, *args, **kwargs):
        raise AssertionError("merge --lane-lint took the merge lock")

    def release(self, *args, **kwargs):
        raise AssertionError("merge --lane-lint released a merge lock")

    def unlock(self, *args, **kwargs):
        raise AssertionError("merge --lane-lint unlocked a merge lock")


class LintStepNames(unittest.TestCase):
    """merge's lint_steps reads each `would run ` line of ci-job's plan as a step name. The plan's summary line names no
    step, so it must not come back as one."""

    def test_the_plan_summary_is_not_a_step_name(self):
        root = tempfile.mkdtemp(prefix="lint-steps-", dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, root, True)
        os.makedirs(os.path.join(root, ".github", "workflows"))
        tm.put(os.path.join(root, ".github", "workflows", "checks.yml"), WORKFLOW)
        names = merge.lint_steps(root, "origin/main")
        self.assertEqual(names, {"Lint one", "Lint two"}, "lint_steps read a line that is no step: %s" % sorted(names - {"Lint one", "Lint two"}))


class CiJobStub:
    """The stub ci-job of this suite, for a class with self.t. Its setUp calls init_stub(). use_ci_job points merge.CI_JOB at
    a stub that prints `steps` and exits `rc`; lint_calls reads back every run the stub logged, never a plan."""

    def init_stub(self):
        self.log = os.path.join(self.t, "ci-calls.jsonl")
        self.stub = os.path.join(self.t, "ci-job-stub.py")
        self.step_log = os.path.join(self.t, "ci-job-step.log")

    def write_stub(self, steps, rc, sleep=0):
        """Write the stub ci-job: it prints `steps` ((state, step name) pairs), exits with `rc`, and runs `sleep` s first when it is set."""
        text = STUB.replace("__STEP_LOG__", repr(self.step_log)).replace("__LOG__", repr(self.log))
        tm.put(self.stub, text.replace("__STEPS__", repr(steps)).replace("__RC__", repr(rc)).replace("__SLEEP__", repr(sleep)))
        return self.stub

    def use_ci_job(self, steps, rc):
        """merge.CI_JOB becomes a stub that prints `steps` ((state, step name) pairs) and exits with `rc`."""
        self.write_stub(steps, rc)
        patch = unittest.mock.patch.object(merge, "CI_JOB", self.stub)
        patch.start()
        self.addCleanup(patch.stop)

    def lint_calls(self):
        """The stub's calls that ran the lint, not the plan."""
        if not os.path.exists(self.log):
            return []
        with open(self.log, encoding="utf-8") as f:
            calls = [json.loads(line) for line in f if line.strip()]
        return [c for c in calls if "--plan" not in c["argv"]]


# The review-range check on lane_lint's PR-number path. A body's `Merge after: #N` line names a parent pull request, and each
# backticked `git diff <start> <end>` in the body must start at that parent's head.
PARENT_PR = 1785  # the parent the real body names
PARENT_HEAD = "ad6274e3d816d58a1c34c063d08684eae5f992e0"  # the parent's head, as ParentHost reports it
PARENT_BRANCH = "silent-undo-base"  # the parent's head branch, as ParentHost reports it
SECOND_PARENT_PR = 1700  # a second parent, for a body that names two
SECOND_PARENT_HEAD = "3f9a0c2b7e41d5a86c0f1e2b9d7a4c5e6f8091a2"
SECOND_PARENT_BRANCH = "notes-base"
FIRST_PARENT_PR = 1676  # the first of two parents on one Merge after line
FIRST_PARENT_HEAD = "5b2e7d91c0a4f3e8d6b1a97c2f0e4d8b3a6c9f15"
FIRST_PARENT_BRANCH = "notes-first-base"
LAST_PARENT_PR = 1742  # the second of the two, and the one a range starts at
LAST_PARENT_HEAD = "c81f4a0e9d3b7261f5e8a2c0d4b9e7f1a3c6d802"
LAST_PARENT_BRANCH = "notes-last-base"
PARENTS = {PARENT_PR: (PARENT_HEAD, PARENT_BRANCH)}
BELOW_START = "c05c0e626"  # #1969's range start, seven commits below PARENT_HEAD
PR_1969_BODY = """Lane notes-fix-page, step silent-undo-cli-ignores-pr-body. Owner ruling: item 411 a, 2026-11-08 06:11 CST, "The CLI reads the body through the merge tool's reader". This branch stacks on #1785. Review only `git diff c05c0e626 nfp-undo-pr-body` (its base is #1785 at c05c0e626).

Merge after: #1785

Before: a `Drops-lines: <path> -- <reason>` line in the PR body's last paragraph counted only in the merge tool. CI and the lane lint read commit trailers only, so a PR could pass the merge tool and fail CI (seen on #1785).

- lint/check_silent_undo.py: `--pr-body TEXT`, else env `PR_BODY` (flag wins), read through the same `allowed`/`last_paragraph` reader merge/merge.py uses. One reader.
- .github/workflows/checks.yml and actions/silent-undo/action.yml: `PR_BODY: ${{ github.event.pull_request.body }}` in env, never inline in the script.
- Lane lint: bin/ci-job maps that expression to env `CI_JOB_PR_BODY`; merge/merge.py `lane_lint` passes the PR body it already reads.
- `last_paragraph` now skips a bare `https://claude.ai/code/session_…` paragraph under the attribution line. Every lane PR body ends that way, so a body excuse counted nowhere before, in the merge tool too.
- Decision silent-undo-check-design rewritten in place, citing the ruling.

Red first: a051865b8 (CLI ignores PR_BODY; no --pr-body), cc162d532 (lane_lint passes no body), 5e236a8b5 (session-link footer hides the excuse). 00c35770d re-points a stale value list. Green on 1a482e946: lint/test_check_silent_undo.py, merge/test_lane_lint.py, lint/test_ci_job.py, lint/test_check_debt_retire.py, merge/test_merge.py.

---
_Generated by [Claude Code](https://claude.ai/code/session_013NEJKzjkypcToggneCjJN8)_
"""


class ParentHost(tm.FakeHost):
    """FakeHost that also answers the parent pull requests a body names: `parents` maps a number to (head, branch). The lane is answered as FakeHost answers it."""

    def __init__(self, root, other, parents):
        super().__init__(root, other)
        self.parents = parents

    def pr(self, n):
        if n not in self.parents:
            return super().pr(n)
        self.pr_calls.append(n)
        head, branch = self.parents[n]
        return {"head": head, "branch": branch, "base": "main", "state": "OPEN", "mergeable": "MERGEABLE",
                "merge_state": "CLEAN", "draft": False, "body": ""}


class LaneLint(CiJobStub, tm.CloudSession):
    @classmethod
    def setUpClass(cls):
        unittest.TestCase.setUpClass()  # not CloudSession's: it would make a second run folder
        cls.run_dir = RUN_FOLDER

    def setUp(self):
        with unittest.mock.patch.object(tempfile, "tempdir", RUN_FOLDER):  # Env.setUp makes its repos in the temp dir: keep them in this run's folder
            super().setUp()
        self.lock = NoLock()
        self.init_stub()

    def run_lane(self, *argv, cloud=False):
        """-> (rc, stdout and stderr together) of merge in the lane checkout. A refused command line fails the case with its reason."""
        rc, out, err = self.run_main(*argv, **({} if cloud else {"CLAUDE_CODE_REMOTE": None}))
        if rc == 2 and "error:" in err:  # argparse refused the command line
            last = err.strip().splitlines()[-1]
            if "unrecognized arguments" in last and "--lane-lint" in last:
                self.fail("the mode does not exist: " + last)
            self.fail("argparse refused the command line: " + last)
        return rc, out + err

    def lint_run(self, *argv, base="main", head=None, cloud=False):
        """Run merge in the lane checkout. -> (rc, stdout and stderr together). The lint must have run once, as
        `checks --lint --base origin/<base>`, in a detached tree at the head, and that tree must be gone afterwards."""
        head = head or self.head("feat")
        if os.path.exists(self.log):
            os.remove(self.log)
        rc, text = self.run_lane(*argv, cloud=cloud)
        runs = self.lint_calls()
        self.assertEqual(len(runs), 1, "the lint ran %d times, want once: %s" % (len(runs), text))
        run = runs[0]
        self.assertEqual(run["argv"], ["checks", "--lint", "--base", "origin/" + base])
        self.assertEqual(run["head"], head)
        self.assertTrue(run["detached"], "the lint ran on a branch, not a detached tree")
        self.assertNotEqual(run["cwd"], os.path.realpath(self.co), "the lint ran in the lane checkout")
        self.assertFalse(os.path.exists(run["cwd"]), "the lint tree is still on disk")
        self.assertFalse(tm.tree_listed(self.co, run["cwd"]), "git still lists the lint tree")
        self.assertEqual(self.worktrees(), 1)
        return rc, text

    def push_release_branch(self):
        sh = tm.sh
        sh(self.other, "git", "fetch", "-q", "origin")
        sh(self.other, "git", "push", "-q", "origin", "origin/main:refs/heads/release")

    def progress_run(self, steps, rc, *argv):
        """Run merge in a subprocess through HARNESS, with the stub of `steps` (see PROGRESS). -> (rc, stdout, stderr).
        stderr is read live: the case creates the GO file at the first `start:` line, so a stderr that merge captures
        instead of passing on reads to the end only after the stub's bound."""
        go = os.path.join(self.t, "go")
        text = STUB.replace("__STEP_LOG__", repr(self.step_log)).replace("__LOG__", repr(self.log))
        text = text.replace("__STEPS__", repr(steps)).replace("__RC__", repr(rc)).replace("__SLEEP__", repr(0))
        tm.put(self.stub, text.replace("lines = [", PROGRESS.replace("__GO__", repr(go)) + "lines = [", 1))
        harness = os.path.join(self.t, "lane_lint_progress.py")
        tm.put(harness, HARNESS.replace("__HERE__", repr(HERE)).replace("__STUB__", repr(self.stub)))
        env = {**os.environ, "CLAUDE_CONFIG_DIR": self.cfg}
        env.pop("CLAUDE_CODE_REMOTE", None)
        proc = subprocess.Popen([sys.executable, harness, *argv], cwd=self.co, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.stop_run, proc)
        err = []
        for line in proc.stderr:
            err.append(line)
            if line.startswith("start:"):
                open(go, "w", encoding="utf-8").close()
                break
        out, rest = proc.communicate(timeout=120)
        return proc.returncode, out, "".join(err) + rest

    def test_a_progress_line_from_ci_job_reaches_the_callers_stderr_live_and_the_pass_still_reads_from_stdout(self):
        rc, out, err = self.progress_run(PASSING, 0, "--lane-lint", self.head("feat"))
        self.assertTrue(any(line.startswith("start:") for line in err.splitlines()),
                        "no ci-job start line reached merge's stderr while the lint ran: " + err)
        self.assertEqual(len(self.lint_calls()), 1, out + err)
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(len(pass_lines(out)), 1, out)
        self.assertEqual([line for line in out.splitlines() if line.startswith("start:")], [], out)

    def test_a_failed_step_with_a_progress_line_still_refuses_and_names_the_step(self):
        rc, out, err = self.progress_run(FAILING, 1, "--lane-lint", self.head("feat"))
        self.assertTrue(any(line.startswith("start:") for line in err.splitlines()),
                        "no ci-job start line reached merge's stderr while the lint ran: " + err)
        self.assertEqual(rc, 1, out + err)
        self.assertTrue(any("comment narration" in line and "FAIL" in line for line in (out + err).splitlines()), out + err)
        self.assertEqual(pass_lines(out), [], out)

    def test_a_passing_lint_prints_one_pass_line_naming_head_and_base(self):
        self.use_ci_job(PASSING, 0)
        rc, out = self.lint_run("--lane-lint", "7")
        self.assertEqual(rc, 0, out)
        lines = pass_lines(out)
        self.assertEqual(len(lines), 1, out)
        self.assertIn(self.head("feat")[:7], lines[0])
        self.assertIn("main", lines[0])
        self.assertIn("batch runner", lines[0])

    def test_a_passing_lint_names_its_skipped_ci_steps_on_the_pass_line(self):
        self.use_ci_job(PASSING + [("skipped", "Push-only lint A"), ("skipped", "Push-only lint B")], 0)
        rc, out = self.lint_run("--lane-lint", "7")
        self.assertEqual(rc, 0, out)
        lines = pass_lines(out)
        self.assertEqual(len(lines), 1, out)
        self.assertIn("Push-only lint A", lines[0], out)
        self.assertIn("Push-only lint B", lines[0], out)
        self.assertRegex(lines[0], r"\b2\b", out)

    def test_lane_lint_gives_ci_job_the_live_pr_body_as_ci_job_pr_body(self):
        """The silent-undo step reads the PR body from env PR_BODY, and ci-job takes that from env CI_JOB_PR_BODY, so lane_lint passes
        the body the host reports for the pull request now. The states are an empty body and the largest body GitHub keeps."""
        self.use_ci_job(PASSING, 0)
        bodies = ("", "Summary.\n\nDrops-lines: lint/gone.py -- the file is gone\n\nGenerated with Claude Code\n\nhttps://claude.ai/code/session_X",
                  "x" * 65536)
        for body in bodies:
            with self.subTest(length=len(body)):
                self.host.body = body
                rc, out = self.lint_run("--lane-lint", "7")
                self.assertEqual(rc, 0, out)
                runs = self.lint_calls()
                self.assertEqual(len(runs), 1, "the lint ran %d times, want once: %s" % (len(runs), out))
                got = runs[0].get("pr_body")
                self.assertTrue(got == body, "lane_lint gave ci-job CI_JOB_PR_BODY %s, want the PR's body of %d characters"
                                % ("nothing" if got is None else "a value of %d characters" % len(got), len(body)))

    def test_a_lane_lint_merges_nothing_takes_no_lock_and_waits_for_no_check(self):
        self.use_ci_job(PASSING, 0)
        before = self.refs()
        rc, out = self.lint_run("--lane-lint", "7")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.refs(), before, "the lane run pushed a ref")
        self.assertFalse(getattr(self.host, "merged", False))
        self.assertEqual(self.host.readies, [])
        self.assertEqual(self.host.waits, [])

    def test_a_failed_step_refuses_names_each_failing_step_and_gives_the_remedy(self):
        self.use_ci_job(FAILING, 1)
        before = self.refs()
        rc, out = self.lint_run("--lane-lint", "7")
        self.assertEqual(rc, 1, out)
        self.assertTrue(any("comment narration" in line and "FAIL" in line for line in out.splitlines()), out)
        self.assertRegex(out, r"(?i)push")
        self.assertRegex(out, r"(?i)again")
        self.assertEqual(pass_lines(out), [], out)
        self.assertEqual(self.refs(), before, "a refused lane pushed a ref")

    def test_an_unknown_reason_does_not_lift_a_failed_step(self):
        self.use_ci_job(FAILING, 1)
        rc, out = self.lint_run("--lane-lint", "7", "--lint-unknown-ok", "shellcheck is not on this box")
        self.assertEqual(rc, 1, out)
        self.assertEqual(pass_lines(out), [], out)

    def test_an_unknown_step_refuses_and_never_reads_as_a_pass(self):
        self.use_ci_job(UNKNOWN, 2)
        rc, out = self.lint_run("--lane-lint", "7")
        self.assertEqual(rc, 1, out)
        self.assertTrue(any("shellcheck" in line and "unknown" in line.lower() for line in out.splitlines()), out)
        self.assertEqual(pass_lines(out), [], out)

    def test_an_unknown_step_with_a_reason_passes_with_one_logged_line(self):
        self.use_ci_job(UNKNOWN, 2)
        reason = "shellcheck is not on this box"
        rc, out = self.lint_run("--lane-lint", "7", "--lint-unknown-ok", reason)
        self.assertEqual(rc, 0, out)
        logged = [line for line in out.splitlines() if reason in line]
        self.assertEqual(len(logged), 1, out)
        self.assertIn("unknown", logged[0].lower())
        self.assertEqual(pass_lines(out), [], "an unknown read was printed as a pass")

    def test_a_blank_unknown_reason_still_refuses(self):
        self.use_ci_job(UNKNOWN, 2)
        for reason in ("", "   "):
            with self.subTest(reason=reason):
                rc, out = self.lint_run("--lane-lint", "7", "--lint-unknown-ok", reason)
                self.assertEqual(rc, 1, out)
                self.assertEqual(pass_lines(out), [], out)

    def test_a_ref_target_lints_against_main_by_default(self):
        self.use_ci_job(PASSING, 0)
        sha = self.head("feat")
        rc, out = self.lint_run("--lane-lint", sha, head=sha)
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(pass_lines(out)), 1, out)

    def test_a_base_flag_names_the_base_the_lint_runs_against_for_a_ref_target(self):
        self.push_release_branch()
        self.use_ci_job(PASSING, 0)
        sha = self.head("feat")
        rc, out = self.lint_run("--lane-lint", sha, "--base", "release", base="release", head=sha)
        self.assertEqual(rc, 0, out)

    def test_a_pr_target_takes_its_head_and_base_from_the_pull_request(self):
        self.push_release_branch()
        self.host.base = "release"
        self.use_ci_job(PASSING, 0)
        rc, out = self.lint_run("--lane-lint", "7", base="release")
        self.assertEqual(rc, 0, out)

    def test_a_ref_target_gives_ci_job_an_empty_pr_body_whatever_the_run_holds(self):
        """A commit or ref has no PR body, so lane_lint gives ci-job an empty CI_JOB_PR_BODY. The host body and the env of
        the run are not empty here, so a body passed on from either source shows as a value."""
        self.use_ci_job(PASSING, 0)
        body = "Summary.\n\nDrops-lines: lint/gone.py -- the file is gone\n\nhttps://claude.ai/code/session_X"
        self.host.body = body
        for target in ("feat", self.head("feat")):
            with self.subTest(target=target), unittest.mock.patch.dict(os.environ, {"CI_JOB_PR_BODY": body, "PR_BODY": body}):
                rc, out = self.lint_run("--lane-lint", target, head=self.head("feat"))  # asserts: one lint run, at this head
                self.assertEqual(rc, 0, out)
                self.assertEqual(self.lint_calls()[0].get("pr_body"), "", "ci-job got a PR body for a ref target: %r" % (target,))

    def test_an_exception_in_the_lint_run_still_removes_the_worktree(self):
        self.use_ci_job(PASSING, 0)
        real_sh, seen = merge.sh, []

        def time_out_the_lint(args, *rest, **kwargs):
            if any(isinstance(a, str) and os.path.basename(a) == os.path.basename(self.stub) for a in args):
                cwd = kwargs.get("cwd")
                seen.append((cwd, bool(cwd) and os.path.isdir(cwd)))
                raise subprocess.TimeoutExpired(args, 1)
            return real_sh(args, *rest, **kwargs)

        with unittest.mock.patch.object(merge, "sh", time_out_the_lint):
            try:
                rc, out = self.run_lane("--lane-lint", "7")
            except subprocess.TimeoutExpired:
                rc, out = None, ""  # the exception may leave the tool: the worktree check below still applies
        self.assertTrue(seen, "the lint run never started, so the case proves nothing")
        cwd, existed = seen[0]
        self.assertIsNotNone(cwd, "the lint run had no directory")
        self.assertTrue(existed, "the lint tree was not on disk when the lint run failed")
        self.assertNotEqual(rc, 0, "an exception in the lint run read as a pass")
        self.assertEqual(pass_lines(out), [])
        self.assertFalse(os.path.exists(cwd), "the lint tree is still on disk after an exception")
        self.assertFalse(tm.tree_listed(self.co, cwd), "git still lists the lint tree after an exception")
        self.assertEqual(self.worktrees(), 1)

    def stop_run(self, proc):
        """Cleanup for a run this case started: it is ours, so a live one is killed. The stub ends by itself when its run is gone."""
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=30)

    @unittest.skipIf(os.name == "nt", "SIGTERM is not delivered as a signal on Windows: a send ends the process at once")
    def test_a_sigterm_during_the_lint_removes_the_lint_tree_and_its_temp_dir(self):
        self.write_stub(PASSING, 0, sleep=120)
        harness = os.path.join(self.t, "lane_lint_run.py")
        tm.put(harness, HARNESS.replace("__HERE__", repr(HERE)).replace("__STUB__", repr(self.stub)))
        tmp_root = tempfile.mkdtemp(dir=self.run_dir, prefix="sigterm-")  # the lint tree's temp dir lands here, not in the system temp dir
        env = {**os.environ, "CLAUDE_CONFIG_DIR": self.cfg, "TMPDIR": tmp_root, "TMP": tmp_root, "TEMP": tmp_root}
        env.pop("CLAUDE_CODE_REMOTE", None)
        text_path = os.path.join(self.t, "lane-lint-run.txt")
        with open(text_path, "w", encoding="utf-8") as text:
            proc = subprocess.Popen([sys.executable, harness, "--lane-lint", self.head("feat")], cwd=self.co, env=env,
                                    stdout=text, stderr=subprocess.STDOUT)
        self.addCleanup(self.stop_run, proc)

        def run_text():
            with open(text_path, encoding="utf-8") as f:
                return f.read()

        deadline = time.time() + 60
        while not self.lint_calls() and proc.poll() is None and time.time() < deadline:
            time.sleep(0.05)
        self.assertIsNone(proc.poll(), "the run ended before its lint started: " + run_text())
        self.assertTrue(self.lint_calls(), "the lint did not start within 60 s: " + run_text())
        lint_tree = self.lint_calls()[0]["cwd"]
        temp_dir = os.path.dirname(lint_tree)
        self.assertTrue(os.path.isdir(lint_tree), "the lint tree was not on disk while the lint ran")
        self.assertEqual(self.worktrees(), 2, "git did not list the lint tree while the lint ran")

        proc.send_signal(signal.SIGTERM)
        try:
            rc = proc.wait(timeout=60)
        except subprocess.TimeoutExpired:
            self.fail("the run did not exit within 60 s of SIGTERM: " + run_text())
        out = run_text()
        self.assertNotEqual(rc, 0, "SIGTERM read as a clean exit: " + out)
        self.assertEqual(pass_lines(out), [], out)
        self.assertEqual(self.worktrees(), 1, "git still lists the lint tree after SIGTERM: " + out)
        self.assertFalse(tm.tree_listed(self.co, lint_tree), "git still lists the lint tree after SIGTERM")
        self.assertFalse(os.path.exists(lint_tree), "the lint tree is still on disk after SIGTERM")
        self.assertFalse(os.path.exists(temp_dir), "the lint tree's temp dir is still on disk after SIGTERM")
        self.assertEqual([n for n in os.listdir(tmp_root) if n.startswith("merge-wt-")], [], "a merge temp dir is left after SIGTERM")

    def has_local_branch(self, name):
        return subprocess.run(["git", "-C", self.co, "rev-parse", "-q", "--verify", f"refs/heads/{name}"], capture_output=True).returncode == 0

    def local_feat_one_past_origin(self):
        """Make the lane checkout's local feat one commit past origin/feat. -> (local sha, origin sha)."""
        tm.sh(self.co, "git", "checkout", "-q", "-b", "feat", "origin/feat")
        tm.put(os.path.join(self.co, "local-only.txt"), "committed here, not pushed\n")
        tm.sh(self.co, "git", "add", "-A")
        tm.sh(self.co, "git", "commit", "-q", "-m", "local only")
        return tm.sh(self.co, "git", "rev-parse", "feat"), tm.sh(self.co, "git", "rev-parse", "origin/feat")

    def test_a_bare_branch_name_with_no_local_branch_lints_origin(self):
        self.use_ci_job(PASSING, 0)
        self.assertFalse(self.has_local_branch("feat"), "the case needs no local feat")
        rc, out = self.lint_run("--lane-lint", "feat", head=self.head("feat"))
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(pass_lines(out)), 1, out)

    def test_a_bare_branch_name_refuses_when_local_and_origin_differ_and_names_both_shas(self):
        local, origin = self.local_feat_one_past_origin()
        self.use_ci_job(PASSING, 0)
        before = self.refs()
        rc, out = self.run_lane("--lane-lint", "feat")
        self.assertEqual(self.lint_calls(), [], "a bare name linted its local branch while origin/feat differs: " + out)
        self.assertNotEqual(rc, 0, "a bare name whose local branch differs from origin/feat read as a pass: " + out)
        self.assertEqual(pass_lines(out), [], out)
        self.assertIn(local[:7], out, "the refusal does not name the local sha")
        self.assertIn(origin[:7], out, "the refusal does not name the origin sha")
        self.assertEqual(self.refs(), before, "a refused lane pushed a ref")

    def test_an_explicit_origin_ref_is_taken_as_given_while_the_local_branch_differs(self):
        _, origin = self.local_feat_one_past_origin()
        self.use_ci_job(PASSING, 0)
        rc, out = self.lint_run("--lane-lint", "origin/feat", head=origin)
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(pass_lines(out)), 1, out)

    def test_a_full_sha_is_taken_as_given_while_the_local_branch_differs(self):
        _, origin = self.local_feat_one_past_origin()
        self.use_ci_job(PASSING, 0)
        rc, out = self.lint_run("--lane-lint", origin, head=origin)
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(pass_lines(out)), 1, out)

    def test_a_failed_lint_refusal_shows_the_ci_job_log_line(self):
        self.use_ci_job(FAILING, 1)
        rc, out = self.lint_run("--lane-lint", "7")
        self.assertEqual(rc, 1, out)
        self.assertTrue(os.path.exists(self.step_log), "the stub wrote no step log")
        self.assertIn("log=" + self.step_log, out.splitlines(), out)

    def test_a_cloud_lane_session_with_no_merge_role_may_run_lane_lint(self):
        self.use_ci_job(PASSING, 0)
        rc, out = self.lint_run("--lane-lint", "7", cloud=True)
        self.assertNotIn("may not merge", out)
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(pass_lines(out)), 1, out)
        rc, out, err = self.run_main("7", "--confirm")  # control: the same cloud session may not merge, so the role check is live
        self.assertEqual(rc, 1, out + err)
        self.assertIn("may not merge", out + err)

    def test_the_hand_off_refusal_names_lane_lint(self):
        rc, out, err = self.run_main("7", "--confirm")
        self.assertEqual(rc, 1, out + err)
        self.assertIn("may not merge", err)
        self.assertIn("--lane-lint", err)

    def test_the_role_refusal_names_lane_lint_and_no_valid_tier(self):
        rc, out, err = self.run_main("--role", "lane")
        self.assertEqual(rc, 1, out + err)
        self.assertIn("--lane-lint", err)
        self.assertNotIn("coordinator", err.lower())
        self.assertNotIn("batch-runner", err.lower())
        self.assertFalse(os.path.exists(self.role_file), "a refused role wrote the role file")

    def use_review_range_host(self, body, parents=PARENTS):
        """The host of a lane whose PR 7 has `body`. `parents` ({number: (head, branch)}) answers the parent pull requests the body names."""
        self.host = ParentHost(self.co, self.other, parents)
        self.host.body = body

    def review_range_run(self, body, parents=PARENTS):
        """Run the lane lint of PR 7 with `body`, with no lint assertion. -> (rc, stdout and stderr together, the lint runs)."""
        self.use_review_range_host(body, parents)
        if os.path.exists(self.log):
            os.remove(self.log)
        rc, text = self.run_lane("--lane-lint", "7")
        return rc, text, self.lint_calls()

    def assert_review_range_refused(self, body, start, what, parents=PARENTS):
        """The lint refuses `body` before ci-job runs: rc 1, no lint run, and a refusal that names the start, the parent PR and its head.
        `what` names the range in each message."""
        self.assertRegex(body, "(?i)merge after", "the body names no parent, so the check is not in play")  # scope before subject (P7)
        self.assertIn("`git diff", body, "the body holds no backticked range, so the check is not in play")
        rc, text, runs = self.review_range_run(body, parents)
        self.assertEqual(rc, 1, "the lint passed %s, whose start %s is not the parent's head:\n%s" % (what, start, text))
        self.assertEqual(runs, [], "ci-job ran for %s, whose start %s is refused: %s" % (what, start, runs))
        self.assertIn(start, text, "the refusal for %s does not name its start %s:\n%s" % (what, start, text))
        self.assertIn(str(PARENT_PR), text, "the refusal for %s does not name the parent PR #%d:\n%s" % (what, PARENT_PR, text))
        self.assertIn(PARENT_HEAD[:7], text, "the refusal for %s does not name the parent's head:\n%s" % (what, text))
        self.assertEqual(self.worktrees(), 1, "the refused lint left a tree behind")

    def test_review_range_refuses_a_start_below_the_parent_head_before_ci_job_runs(self):
        """#1969's own body: its range starts at c05c0e626, seven commits below the head of its parent #1785."""
        self.use_ci_job(PASSING, 0)
        self.assertFalse(PARENT_HEAD.startswith(BELOW_START), "the fixture starts at the parent's head, so the case tests no refusal")
        self.assert_review_range_refused(PR_1969_BODY, BELOW_START, "the #1969 range")

    def test_review_range_refuses_a_start_above_the_parent_head_before_ci_job_runs(self):
        self.use_ci_job(PASSING, 0)
        above = self.head("feat")  # the lane's own head: a commit above the parent, and no prefix of the parent's head
        self.assertFalse(PARENT_HEAD.startswith(above), "the lane's head is the parent's head, so the case tests no refusal")
        self.assert_review_range_refused(PR_1969_BODY.replace(BELOW_START, above), above, "a range that starts above the parent head")

    def test_review_range_refuses_a_start_that_names_another_branch_before_ci_job_runs(self):
        self.use_ci_job(PASSING, 0)
        self.assert_review_range_refused(PR_1969_BODY.replace(BELOW_START, "some-other-branch"), "some-other-branch",
                                         "a range that starts at another branch")

    def test_review_range_refuses_a_hex_start_under_seven_characters_before_ci_job_runs(self):
        self.use_ci_job(PASSING, 0)
        short = PARENT_HEAD[:6]  # a prefix of the parent's head, one character short of the seven a start needs
        self.assert_review_range_refused(PR_1969_BODY.replace(BELOW_START, short), short, "a range with a 6-character start")

    def test_review_range_refuses_a_bad_range_after_a_good_one_before_ci_job_runs(self):
        """Each range is checked: the first starts at the parent's head, the second at c05c0e626, and the second is refused."""
        self.use_ci_job(PASSING, 0)
        good = PARENT_HEAD[:9]
        body = PR_1969_BODY.replace(BELOW_START, good) + "\nAlso `git diff %s nfp-undo-pr-body`.\n" % BELOW_START
        self.assertIn("`git diff %s " % good, body, "the good range is not in the body")
        self.assert_review_range_refused(body, BELOW_START, "the second range")

    def test_review_range_refuses_a_below_start_in_the_dotdot_and_triple_dot_forms_before_ci_job_runs(self):
        self.use_ci_job(PASSING, 0)
        for sep in ("..", "..."):
            rng = "`git diff %s%snfp-undo-pr-body`" % (BELOW_START, sep)
            body = PR_1969_BODY.replace("`git diff %s nfp-undo-pr-body`" % BELOW_START, rng)
            self.assertIn(rng, body, "the fixture did not take the %r form" % sep)
            self.assert_review_range_refused(body, BELOW_START, "the range " + rng)

    def test_review_range_passes_a_start_at_the_parent_head_in_nine_or_seven_characters(self):
        self.use_ci_job(PASSING, 0)
        for short in (PARENT_HEAD[:9], PARENT_HEAD[:7]):
            with self.subTest(start=short):
                self.use_review_range_host(PR_1969_BODY.replace(BELOW_START, short))
                rc, out = self.lint_run("--lane-lint", "7")
                self.assertEqual(rc, 0, out)
                self.assertEqual(len(pass_lines(out)), 1, out)

    def test_review_range_passes_a_start_naming_the_parent_branch_bare_or_as_origin(self):
        self.use_ci_job(PASSING, 0)
        for start in (PARENT_BRANCH, "origin/" + PARENT_BRANCH):
            with self.subTest(start=start):
                self.use_review_range_host(PR_1969_BODY.replace(BELOW_START, start))
                rc, out = self.lint_run("--lane-lint", "7")
                self.assertEqual(rc, 0, out)
                self.assertEqual(len(pass_lines(out)), 1, out)

    def test_review_range_passes_a_lowercase_merge_after_without_a_colon_with_the_dotdot_form(self):
        self.use_ci_job(PASSING, 0)
        body = PR_1969_BODY.replace("Merge after: #1785", "merge after #1785").replace(
            "`git diff %s nfp-undo-pr-body`" % BELOW_START, "`git diff %s..nfp-undo-pr-body`" % PARENT_HEAD[:9])
        self.assertIn("merge after #1785", body, "the fixture did not take the lowercase line")
        self.use_review_range_host(body)
        rc, out = self.lint_run("--lane-lint", "7")
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(pass_lines(out)), 1, out)

    def test_review_range_passes_a_full_sha_start_with_the_triple_dot_form(self):
        self.use_ci_job(PASSING, 0)
        body = PR_1969_BODY.replace("`git diff %s nfp-undo-pr-body`" % BELOW_START, "`git diff %s...nfp-undo-pr-body`" % PARENT_HEAD)
        self.assertIn("`git diff %s...nfp-undo-pr-body`" % PARENT_HEAD, body, "the fixture did not take the triple-dot form")
        self.use_review_range_host(body)
        rc, out = self.lint_run("--lane-lint", "7")
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(pass_lines(out)), 1, out)

    def test_review_range_skips_the_check_when_no_merge_after_line_names_a_parent(self):
        self.use_ci_job(PASSING, 0)
        cases = (
            ("the #1969 body without its Merge after line", PR_1969_BODY.replace("Merge after: #1785\n", "")),
            ("an empty body", ""),
            ("a body at the largest size GitHub keeps", "x" * 65536 + "\n`git diff %s nfp-undo-pr-body`\n" % BELOW_START),
        )
        for name, body in cases:
            with self.subTest(name):
                self.assertNotIn("Merge after", body, "the fixture still names a parent")
                self.use_review_range_host(body)
                rc, out = self.lint_run("--lane-lint", "7")
                self.assertEqual(rc, 0, out)
                self.assertEqual(len(pass_lines(out)), 1, out)

    def test_review_range_passes_a_start_at_the_head_of_either_named_parent(self):
        self.use_ci_job(PASSING, 0)
        body = PR_1969_BODY.replace("Merge after: #1785\n", "Merge after: #1785\nMerge after: #1700\n").replace(BELOW_START, SECOND_PARENT_HEAD[:9])
        self.assertEqual(body.count("Merge after: #"), 2, "the fixture does not name two parents")
        parents = {PARENT_PR: (PARENT_HEAD, PARENT_BRANCH), SECOND_PARENT_PR: (SECOND_PARENT_HEAD, SECOND_PARENT_BRANCH)}
        self.use_review_range_host(body, parents)
        rc, out = self.lint_run("--lane-lint", "7")
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(pass_lines(out)), 1, out)

    def test_review_range_passes_a_parent_named_with_no_range(self):
        self.use_ci_job(PASSING, 0)
        self.use_review_range_host("Merge after: #1785\n\nThis body holds no range.\n")
        rc, out = self.lint_run("--lane-lint", "7")
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(pass_lines(out)), 1, out)

    def assert_review_range_passes(self, body, what, parents=PARENTS):
        """The check passes `body` and the lint runs once: rc 0, one lint run, one PASS line. `what` names the body in each message."""
        rc, text, runs = self.review_range_run(body, parents)
        self.assertEqual(rc, 0, "the check refused %s, which it must pass:\n%s" % (what, text))
        self.assertEqual(len(runs), 1, "the lint ran %d times for %s, want once: %s" % (len(runs), what, text))
        self.assertEqual(len(pass_lines(text)), 1, "no PASS line for %s: %s" % (what, text))

    def test_review_range_passes_a_placeholder_start_beside_a_real_range(self):
        """`<start>` and `{reviewed-head}` are placeholders in prose: a start holding any of <>{} is skipped, and the real range is judged."""
        self.use_ci_job(PASSING, 0)
        body = ("Merge after: #1785\n\n"
                "Review the range `git diff <start> <end>`, or `git diff {reviewed-head}..{head}`, against the parent. "
                "The range to read is `git diff %s nfp-undo-pr-body`.\n") % PARENT_HEAD[:9]
        self.assert_review_range_passes(body, "a body with placeholder ranges in prose beside a real range")

    def test_review_range_passes_a_git_diff_inside_a_fenced_block(self):
        """A range inside a fenced block is an example: the wrong start in the fence is skipped, and the real range outside it is judged."""
        self.use_ci_job(PASSING, 0)
        body = ("Merge after: #1785\n\n"
                "```\n`git diff %s nfp-undo-pr-body`\n```\n\n"
                "Review only `git diff %s nfp-undo-pr-body`.\n") % (BELOW_START, PARENT_HEAD[:9])
        self.assert_review_range_passes(body, "a body whose only wrong range sits in a fenced block")

    def test_review_range_passes_every_number_on_a_merge_after_line(self):
        """`Merge after: #1676, #1742` names two parents, so a range at the head of #1742 passes."""
        self.use_ci_job(PASSING, 0)
        body = PR_1969_BODY.replace("Merge after: #1785", "Merge after: #%d, #%d" % (FIRST_PARENT_PR, LAST_PARENT_PR))
        body = body.replace(BELOW_START, LAST_PARENT_HEAD[:9])
        self.assertIn("Merge after: #1676, #1742", body, "the fixture did not take the two-number line")
        parents = {FIRST_PARENT_PR: (FIRST_PARENT_HEAD, FIRST_PARENT_BRANCH), LAST_PARENT_PR: (LAST_PARENT_HEAD, LAST_PARENT_BRANCH)}
        self.assert_review_range_passes(body, "a Merge after line that names #1676 and #1742", parents)

    def test_review_range_refuses_a_start_below_a_bold_merge_after_line(self):
        self.use_ci_job(PASSING, 0)
        body = PR_1969_BODY.replace("Merge after: #1785", "**Merge after: #1785**")
        self.assert_review_range_refused(body, BELOW_START, "the #1969 range under a bold Merge after line")

    def test_review_range_refuses_a_start_below_a_bulleted_merge_after_line(self):
        self.use_ci_job(PASSING, 0)
        body = PR_1969_BODY.replace("Merge after: #1785", "- Merge after: #1785")
        self.assert_review_range_refused(body, BELOW_START, "the #1969 range under a bulleted Merge after line")

    def test_review_range_refuses_a_start_below_a_mid_line_merge_after(self):
        self.use_ci_job(PASSING, 0)
        body = PR_1969_BODY.replace("Merge after: #1785", "Built on the notes lane, and merge after #1785.")
        self.assert_review_range_refused(body, BELOW_START, "the #1969 range under a mid-line merge after")

    def test_review_range_refuses_a_start_followed_by_a_flag(self):
        self.use_ci_job(PASSING, 0)
        body = PR_1969_BODY.replace("`git diff %s nfp-undo-pr-body`" % BELOW_START, "`git diff %s nfp-undo-pr-body --stat`" % BELOW_START)
        self.assertIn("--stat`", body, "the fixture did not take the flag")
        self.assert_review_range_refused(body, BELOW_START, "the #1969 range followed by --stat")

    def test_review_range_refuses_a_start_followed_by_a_path(self):
        self.use_ci_job(PASSING, 0)
        body = PR_1969_BODY.replace("`git diff %s nfp-undo-pr-body`" % BELOW_START, "`git diff %s nfp-undo-pr-body -- merge/merge.py`" % BELOW_START)
        self.assertIn("-- merge/merge.py`", body, "the fixture did not take the path")
        self.assert_review_range_refused(body, BELOW_START, "the #1969 range followed by a path")


BATCH = "batch-lint-flags"  # the batch the case lints: a pushed branch whose checks job holds the four CI steps below
BATCH_MISSING = "batch-lint-flags-no-red-run"  # the same batch with the Red-run trailer's script left out
BASE = "main"  # the base the lint runs against: lane_lint's base, and the PR base the CI steps read
SILENT_UNDO = "Silent undo check"  # the CI step that reads the pull request body, as env PR_BODY
BATCH_CI_STEPS = (SILENT_UNDO, "Comment narration check", "Red-run trailer", "STE lint")  # checks.yml's job `checks` CI steps this suite lints
STE = "STE lint"  # the one CI step whose script is bin/ste-changed, not a file of the batch
PR_BODY_EXPR = "${{ github.event.pull_request.body }}"  # the value checks.yml gives PR_BODY
REPO = os.path.dirname(HERE)
CHECKS_YML = os.path.join(REPO, ".github", "workflows", "checks.yml")  # read at test time; no expectation comes from a copy of it
CALL_STUB = ("import json, os, sys\nwith open(%r, 'a', encoding='utf-8') as f:\n"
             "    print(json.dumps({'argv': sys.argv, 'pr_body': os.environ.get('PR_BODY')}), file=f)\n")  # logs its argv and env PR_BODY, exits 0
BATCH_NO_LINT = "batch-lint-flags-no-lint"  # a batch whose checks job holds NO_LINT_STEPS: no lint step at all
NO_LINT_STEPS = (("Build", "      - name: Build\n        run: make build\n"),
                 ("Unit tests", "      - name: Unit tests\n        run: python3 -m pytest -q\n"))
BATCH_PUSH_ONLY = "batch-lint-flags-push-only"  # a batch whose checks job adds one lint step that runs only off a pull request
PUSH_ONLY = "Push-only lint"
PUSH_ONLY_STEP = (PUSH_ONLY, "      - name: Push-only lint\n        if: ${{ github.event_name != 'pull_request' }}\n"
                             "        run: python3 lint/check_push_only.py\n")


def real_ci_steps():
    """(name, CI step text) of BATCH_CI_STEPS in checks.yml's checks job, in file order, read by the shared parser."""
    with open(CHECKS_YML, encoding="utf-8") as f:
        block = job_block(f.read(), "checks")
    return [(step_key(st, "name"), st) for st in step_blocks(block) if step_key(st, "name") in BATCH_CI_STEPS]


def workflow_text(found):
    """A workflow of one job, `checks`, holding the given CI step texts in order."""
    return "name: checks\non: pull_request\njobs:\n  checks:\n    runs-on: ubuntu-latest\n    steps:\n" + "".join(text for _, text in found)


def script_of(ci_step):
    """The script a CI step's run: line names, read as its argv reads it, before any env is expanded."""
    return shlex.split(run_body(ci_step).strip())[1]


def github_text(raw, values):
    """The value of one `${{ NAME }}` env value of checks.yml, from `values`: the PR's context as this suite sets it."""
    m = re.fullmatch(r"\$\{\{\s*([\w.]+)\s*\}\}", raw.strip())
    if not m:
        raise AssertionError("checks.yml gives an env value this suite does not read: %r" % raw)
    return values[m.group(1)]


def expected_argv(ci_step, values):
    """The argv checks.yml gives a CI step's run: line, its env: expanded for `values` and split as a shell splits it."""
    env = {name: github_text(raw, values) for name, raw in step_env(ci_step).items()}
    run = run_body(ci_step).strip()
    if "${{" in run:
        raise AssertionError("a run: line of checks.yml holds an expression this suite does not read: %r" % run)
    return shlex.split(re.sub(r"\$(\w+)", lambda m: env[m.group(1)], run))


def gh_eval(expr, inputs):
    """The value of a `${{ }}` of checks.yml made of inputs.NAME, quoted strings, !, && and ||, as GitHub reads those operators."""
    m = re.fullmatch(r"\$\{\{\s*(.*?)\s*\}\}", expr.strip())
    if not m:
        raise AssertionError("checks.yml gives an expression this suite does not read: %r" % expr)
    py = re.sub(r"inputs\.([\w-]+)", lambda x: "INPUTS[%r]" % x.group(1), m.group(1))
    py = re.sub(r"!(?!=)", "not ", py.replace("&&", " and ").replace("||", " or ")).strip()
    tree = ast.parse(py, mode="eval")
    allowed = (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not, ast.Constant, ast.Subscript, ast.Name, ast.Load)
    for node in ast.walk(tree):
        if not isinstance(node, allowed):
            raise AssertionError("checks.yml gives an expression with %s, which this suite does not read: %r" % (type(node).__name__, expr))
    return eval(compile(tree, "<checks.yml>", "eval"), {"__builtins__": {}}, {"INPUTS": inputs})


def gh_text(value):
    """A GitHub expression's value as the env of a CI step holds it: booleans are the words true and false."""
    return "true" if value is True else "false" if value is False else str(value)


def ste_changed_env(path):
    """{name: constant} of the env dict bin/ste-changed builds for its run, read from its source: the file is parsed, never run. None if absent."""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "dict" and any(k.arg == "SCOPE" for k in node.keywords):
            return {k.arg: k.value.value for k in node.keywords if isinstance(k.value, ast.Constant)}
    return None


def link_or_copy(src, dst):
    """A link at `dst` to `src`, or a copy where the system refuses links (Windows without the symlink right)."""
    try:
        os.symlink(src, dst, target_is_directory=os.path.isdir(src))
    except OSError:
        (shutil.copytree if os.path.isdir(src) else shutil.copy2)(src, dst)


class BatchLintFlags(tm.Env):
    """`merge --lane-lint <batch>` runs the real bin/ci-job on the batch's checks job: each of its four lint CI steps runs once, with the argv checks.yml gives it."""

    def setUp(self):
        with unittest.mock.patch.object(tempfile, "tempdir", RUN_FOLDER):  # Env.setUp makes its repos in the temp dir: keep them in this run's folder
            super().setUp()
        self.found = real_ci_steps()
        self.calls = os.path.join(self.t, "calls")
        os.makedirs(self.calls)
        self.ci_job = self.copy_ci_job()

    def call_log(self, script):
        return os.path.join(self.calls, os.path.basename(script) + ".jsonl")

    def stub_calls(self, script):
        """The logged calls of the stub of `script`, oldest first: empty when it never ran."""
        if not os.path.exists(self.call_log(script)):
            return []
        with open(self.call_log(script), encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def copy_ci_job(self):
        """A copy of bin/ci-job in <t>/ci/bin, with a logging ste-changed beside it: ci-job runs its STE CI step as the file beside its
        own BIN, never the one in the fixture. ci-job imports hooks and lint from the folder above BIN, and runs verdict beside itself."""
        bin_dir = os.path.join(self.t, "ci", "bin")
        os.makedirs(bin_dir)
        shutil.copy2(os.path.join(REPO, "bin", "ci-job"), bin_dir)
        link_or_copy(os.path.join(REPO, "bin", "verdict"), os.path.join(bin_dir, "verdict"))
        for name in ("hooks", "lint"):
            link_or_copy(os.path.join(REPO, name), os.path.join(self.t, "ci", name))
        self.ste_path = os.path.join(bin_dir, "ste-changed")
        tm.put(self.ste_path, "#!/usr/bin/env python3\n" + CALL_STUB % self.call_log("ste-changed"))
        os.chmod(self.ste_path, 0o755)
        return os.path.join(bin_dir, "ci-job")

    def push_batch(self, branch, skip=(), found=None):
        """Push `branch` to origin: one commit on main holding checks.yml's checks job (`found`, else the four lint CI steps) and a
        logging stub for each check script of the four, except the scripts in `skip`. -> the branch's head sha."""
        o = self.other
        tm.sh(o, "git", "fetch", "-q", "origin")
        tm.sh(o, "git", "checkout", "-q", "-B", branch, "origin/" + BASE)
        tm.put(os.path.join(o, ".github", "workflows", "checks.yml"), workflow_text(self.found if found is None else found))
        for name, ci_step in self.found:
            if name != STE and script_of(ci_step) not in skip:
                tm.put(os.path.join(o, script_of(ci_step)), CALL_STUB % self.call_log(script_of(ci_step)))
        tm.sh(o, "git", "add", "-A")
        tm.sh(o, "git", "commit", "-q", "-m", branch + ": the checks job's lint CI steps and their stubs")
        tm.sh(o, "git", "push", "-q", "origin", branch)
        return tm.sh(o, "git", "rev-parse", "HEAD")

    def lane_lint(self, target, out):
        """merge.lane_lint of `target` against BASE, in the lane checkout, through the copy of ci-job. Its output goes to `out`. A refusal raises."""
        env = {"VERDICT_LOG": os.path.join(self.t, "verdict.log")}  # one log for the run: no ci-job log lands in the system temp dir
        with unittest.mock.patch.object(tempfile, "tempdir", RUN_FOLDER), unittest.mock.patch.object(merge, "CI_JOB", self.ci_job), \
                unittest.mock.patch.dict(os.environ, env), contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            return merge.lane_lint(self.co, target, self.host, base=BASE)

    def test_lane_lint_runs_each_batch_check_once_with_the_argv_checks_yml_gives(self):
        head = self.push_batch(BATCH)
        self.assertEqual(sorted(name for name, _ in self.found), sorted(BATCH_CI_STEPS),
                         "checks.yml's checks job does not hold exactly the four CI steps this suite lints")
        out = io.StringIO()
        rc = self.lane_lint(BATCH, out)
        text = out.getvalue()
        self.assertEqual(rc, 0, text)
        self.assertEqual(len(pass_lines(text)), 1, text)
        values = {"github.base_ref": BASE, "github.event.pull_request.head.sha": head, "github.event.pull_request.body": ""}
        for name, ci_step in self.found:
            if name == STE:
                continue
            with self.subTest(check=name):
                want = expected_argv(ci_step, values)
                self.assertEqual(want[0], "python3", "checks.yml's run: of %s is not a python3 line" % name)
                calls = self.stub_calls(want[1])
                self.assertEqual(len(calls), 1, "%s: its script ran %d times, want once: %s" % (name, len(calls), text))
                self.assertEqual(calls[0]["argv"], want[1:], "%s: ran with %s, checks.yml gives %s" % (name, calls[0]["argv"], want[1:]))
        with self.subTest(check=STE):
            calls = self.stub_calls("ste-changed")
            self.assertEqual(len(calls), 1, "STE lint: ste-changed ran %d times, want once: %s" % (len(calls), text))
            argv = calls[0]["argv"]
            self.assertEqual(os.path.realpath(argv[0]), os.path.realpath(self.ste_path),
                             "STE lint ran a ste-changed other than the one beside ci-job")
            self.assertEqual(argv[1:], ["origin/" + BASE], "STE lint: ste-changed got %s, want origin/%s" % (argv[1:], BASE))
            with_ = step_with(dict(self.found)[STE])
            self.assertEqual(sorted(with_), ["fail", "scope"], "checks.yml's STE lint CI step has other with: keys than scope and fail")
            source = ste_changed_env(os.path.join(REPO, "bin", "ste-changed"))
            self.assertIsNotNone(source, "bin/ste-changed builds no env dict with SCOPE")
            inputs = {"full_ste_audit": ""}  # the PR run: the input is empty
            self.assertEqual(source.get("SCOPE"), gh_eval(with_["scope"], inputs),
                             "bin/ste-changed sets SCOPE to other than the PR-path scope of checks.yml")
            self.assertEqual(source.get("FAIL"), gh_text(gh_eval(with_["fail"], inputs)),
                             "bin/ste-changed sets FAIL to other than the PR-path fail of checks.yml")

    def test_a_missing_check_script_refuses_and_never_passes(self):
        red_run = dict(self.found)["Red-run trailer"]
        self.push_batch(BATCH_MISSING, skip={script_of(red_run)})
        out = io.StringIO()
        with self.assertRaises(merge.Stop) as raised:
            self.lane_lint(BATCH_MISSING, out)
        self.assertNotIsInstance(raised.exception, merge.Liftable, "a missing check script reads as unknown, not as a failed check: " + out.getvalue())
        self.assertIn("FAILs:", str(raised.exception), "the refusal does not say the lint FAILs: " + out.getvalue())
        self.assertIn("Red-run trailer", str(raised.exception), "the refusal does not name the CI step whose script is missing: " + out.getvalue())
        self.assertEqual(pass_lines(out.getvalue()), [], "a lint with a check script missing read as a pass: " + out.getvalue())

    def test_a_batch_whose_checks_job_runs_no_lint_step_refuses_as_unknown_and_never_passes(self):
        self.push_batch(BATCH_NO_LINT, found=NO_LINT_STEPS)
        root = tempfile.mkdtemp(prefix="lint-steps-", dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, root, True)
        tm.put(os.path.join(root, ".github", "workflows", "checks.yml"), workflow_text(NO_LINT_STEPS))
        plan = subprocess.run([sys.executable, merge.CI_JOB, "checks", "--lint", "--plan", "--base", "origin/" + BASE],
                              cwd=root, capture_output=True, text=True)  # the exit code is not read: a zero-step plan may exit 2
        self.assertEqual([ln for ln in plan.stdout.splitlines() if ln.startswith("would run ")], [],
                         "the checks job of the batch holds a lint step: " + plan.stdout)  # the scope
        out = io.StringIO()
        with self.assertRaises(merge.Liftable) as raised:
            self.lane_lint(BATCH_NO_LINT, out)
        self.assertIn("no lint CI step ran", str(raised.exception), out.getvalue())
        self.assertEqual(pass_lines(out.getvalue()), [], "a lint run that picked no lint step read as a pass: " + out.getvalue())

    def test_a_lint_step_that_runs_only_off_a_pull_request_is_named_on_the_pass_line(self):
        self.push_batch(BATCH_PUSH_ONLY, found=self.found + [PUSH_ONLY_STEP])
        out = io.StringIO()
        rc = self.lane_lint(BATCH_PUSH_ONLY, out)
        text = out.getvalue()
        self.assertEqual(rc, 0, text)
        lines = pass_lines(text)
        self.assertEqual(len(lines), 1, text)
        self.assertIn(PUSH_ONLY, lines[0], text)

    def test_the_silent_undo_step_sees_env_pr_body_as_the_pull_requests_body(self):
        """A pull request's lint gives the silent-undo step env PR_BODY as the PR's body: lane_lint takes the body from the host,
        ci-job maps it to `${{ github.event.pull_request.body }}`, and checks.yml names it as the step's PR_BODY. The body holds a Drops-lines line."""
        body = "Summary.\n\nDrops-lines: lint/gone.py -- the file is gone\n\nhttps://claude.ai/code/session_X\n"
        self.push_batch(BATCH)
        self.host.branch, self.host.body = BATCH, body
        out = io.StringIO()
        rc = self.lane_lint("7", out)
        text = out.getvalue()
        self.assertEqual(rc, 0, text)
        calls = self.stub_calls(script_of(dict(self.found)[SILENT_UNDO]))
        self.assertEqual(len(calls), 1, "the silent-undo step's script ran %d times, want once: %s" % (len(calls), text))
        self.assertEqual(calls[0]["pr_body"], body, "the silent-undo step saw env PR_BODY %r, want the PR's body" % calls[0]["pr_body"])


def under(lines, key, indent):
    """(the rest of the `key:` line, the lines under it) for the key at column `indent`; None when there is no such key line."""
    for i, line in enumerate(lines):
        m = re.match(r"^ {%d}%s:(.*)$" % (indent, re.escape(key)), line)
        if m:
            kids = []
            for nxt in lines[i + 1:]:
                if nxt.strip() and len(nxt) - len(nxt.lstrip(" ")) <= indent:
                    break
                kids.append(nxt)
            return m.group(1).strip(), kids
    return None


def pull_request_types(text):
    """The names in checks.yml's `on:` `pull_request:` `types:`, read from its lines: a flow list or a block list. Raises when a key is missing."""
    on = under(text.split("\n"), "on", 0)
    pr = on and under(on[1], "pull_request", 2)
    types = pr and under(pr[1], "types", 4)
    if not types:
        raise AssertionError("checks.yml has no on: pull_request: types: list this suite reads")
    rest, kids = types
    if rest.startswith("["):
        return [name.strip() for name in rest.strip("[]").split(",") if name.strip()]
    return [ln.strip()[len("- "):].strip() for ln in kids if ln.strip().startswith("- ")]


class PrBodyPins(unittest.TestCase):
    """checks.yml gives the silent-undo step the pull request body as PR_BODY, and its pull_request types leave out `edited`,
    so a body-only edit does not rerun the checks job. Each pin parses the YAML it reads, never a grep of one of its lines."""

    def test_the_silent_undo_step_takes_pr_body_from_the_pull_request_body(self):
        env = step_env(dict(real_ci_steps())[SILENT_UNDO])
        self.assertEqual(env.get("PR_BODY"), PR_BODY_EXPR, "checks.yml's silent-undo step gives PR_BODY %r, want the pull request body" % env.get("PR_BODY"))

    def test_the_pull_request_types_do_not_list_edited(self):
        with open(CHECKS_YML, encoding="utf-8") as f:
            types = pull_request_types(f.read())
        self.assertIn("synchronize", types, "the parse of checks.yml's pull_request types lost synchronize: %r" % types)
        self.assertNotIn("edited", types, "checks.yml's pull_request types list edited, so a body-only edit reruns the checks job: %r" % types)


class ReadyChecks(CiJobStub, tm.RecordsEnv):
    """The ready check of the draft step (merge.draft_step): before a draft goes ready, the repo's declared merge.readyChecks
    run through ci-job as `checks --step NAME ... --base origin/<base>`, on the tree that would be pushed. A FAIL or an
    unknown stops the draft: nothing pushed, no ready mark, and no unknown-ok flag. The stub logs each run. Each red case
    asserts that run first, so a missing check fails there by name. On main a declared key is refused as an unknown field
    before the draft step runs, so the red cases never reach the draft step on main."""

    def setUp(self):
        with unittest.mock.patch.object(tempfile, "tempdir", RUN_FOLDER):  # Env.setUp makes its repos in the temp dir: keep them in this run's folder
            super().setUp()
        self.use_fake_records()
        self.init_stub()

    def declare(self, names, stamp_kinds=False):
        """Put the base's stamp on main with merge.readyChecks `names` (None: no key). Stamp kinds stay off, so no claim,
        unless stamp_kinds gives the repo's own kinds: a claim head needs its pending record."""
        block = dict(tm.CONFIG["merge"])
        if names is not None:
            block["readyChecks"] = names
        kinds = tm.CONFIG["kinds"] if stamp_kinds else []
        tm.put_base_config(self, json.dumps(dict(tm.CONFIG, kinds=kinds, merge=block)))

    def stale_feat(self):
        """feat carries a debt its page does not list, so a draft run rebuilds the page and would push it."""
        self.on("feat", {"debts/gap-one.md": tm.DEBT_TEXT})

    def base_stamp(self, base, names):
        """A branch `base` on origin, made from main, whose stamp declares `names`. The pull request's base becomes it:
        a pull request's config is read from its own base, so the declaration lives there."""
        o = self.other
        tm.sh(o, "git", "fetch", "-q", "origin")
        tm.sh(o, "git", "checkout", "-q", "-B", base, "origin/main")
        tm.put(os.path.join(o, ".github", "stamp.json"), json.dumps(dict(tm.CONFIG, merge=dict(tm.CONFIG["merge"], readyChecks=names))))
        tm.sh(o, "git", "commit", "-qam", f"{base}: declare the ready checks")
        tm.sh(o, "git", "push", "-q", "origin", base)
        self.host.base = base

    def test_a_declared_step_that_fails_stops_the_draft_before_any_push_or_ready(self):
        self.declare(["check invariants"])
        self.stale_feat()
        self.use_ci_job([("FAIL", "check invariants")], 1)
        refs_before = self.refs()
        rc, out = self.draft_confirm()
        self.assertEqual(len(self.lint_calls()), 1, "the ready check did not run the declared step once: " + out)
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.refs(), refs_before, "a page was pushed on a red ready check")
        self.assertEqual(self.host.readies, [], "the pull request went ready on a red ready check")
        self.assertNotIn("ready after its draft run shows", out)

    def test_declared_steps_that_pass_run_ci_job_once_on_the_tree_pushed_and_mark_ready(self):
        names = ["check invariants", "records page"]  # two steps, one run
        self.declare(names)
        self.stale_feat()
        self.use_ci_job([("PASS", name) for name in names], 0)
        before = self.head()
        rc, out = self.draft_confirm()
        runs = self.lint_calls()
        self.assertEqual(len(runs), 1, "the ready check ran ci-job %d times, want once: %s" % (len(runs), out))
        self.assertNotEqual(runs[0]["head"], before, "the check ran on the old head, not on the page commit it would push")
        argv = runs[0]["argv"]
        self.assertEqual(argv[:1], ["checks"], out)
        self.assertNotIn("--lint", argv, out)
        self.assertEqual([argv[i + 1] for i, arg in enumerate(argv) if arg == "--step"], names, out)
        self.assertIn("--base", argv, out)
        self.assertEqual(argv[argv.index("--base") + 1], "origin/main", out)
        self.assertEqual(runs[0]["head"], self.head(), "the ready check ran on a tree other than the one pushed")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.host.readies, [7], out)
        self.assertEqual(self.show("feat", merge.RECORDS_PAGE), tm.page("gap-one").strip())

    def test_a_declared_step_that_passes_on_a_current_page_runs_ci_job_on_the_pr_head(self):
        self.declare(["check invariants"])
        self.on("feat", {merge.RECORDS_PAGE: tm.page()})  # the page is current: nothing to rebuild or push
        self.use_ci_job([("PASS", "check invariants")], 0)
        before = self.head()
        rc, out = self.draft_confirm()
        runs = self.lint_calls()
        self.assertEqual(len(runs), 1, "the ready check ran ci-job %d times, want once: %s" % (len(runs), out))
        self.assertEqual(runs[0]["head"], before, "the ready check ran on a tree other than the PR head")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.host.readies, [7], out)

    def test_a_declared_name_with_no_step_refuses_as_unknown_with_no_unknown_ok_escape(self):
        self.declare(["no such step"])
        self.stale_feat()
        self.use_ci_job([("unknown", "no such step")], 2)
        refs_before = self.refs()
        rc, out = self.draft_confirm()
        self.assertEqual(len(self.lint_calls()), 1, "the declared name did not reach ci-job: " + out)
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.refs(), refs_before, "a page was pushed on an unknown ready check")
        self.assertEqual(self.host.readies, [], "the pull request went ready on an unknown ready check")
        self.assertNotIn("--lint-unknown-ok", out, "the ready check offers the lint's unknown-ok flag")
        self.assertNotIn("ready after its draft run shows", out)

    def test_a_declared_step_that_fails_on_a_non_default_base_still_stops_the_draft(self):
        self.base_stamp("integ", ["check invariants"])
        self.use_ci_job([("FAIL", "check invariants")], 1)
        rc, out = self.draft_confirm()
        runs = self.lint_calls()
        self.assertEqual(len(runs), 1, "the ready check did not run on a non-default base: " + out)
        self.assertIn("--base", runs[0]["argv"], out)
        self.assertEqual(runs[0]["argv"][runs[0]["argv"].index("--base") + 1], "origin/integ", out)
        self.assertEqual(runs[0]["head"], self.head("feat"), "the ready check ran on a tree other than the PR head")
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.host.readies, [], out)

    def test_a_record_claim_head_that_fails_its_declared_step_gets_no_ready_by_hand_remedy(self):
        self.declare(["check invariants"], stamp_kinds=True)  # the config first: a merge after the claim would hide its trailer
        self.claim_head()
        self.assertEqual(self.log1("%(trailers:key=Record-claim,valueonly)", "origin/feat").strip(), "D-002")  # precondition: a claim head
        self.use_ci_job([("FAIL", "check invariants")], 1)
        refs_before = self.refs()
        rc, out = self.draft_confirm()
        self.assertEqual(len(self.lint_calls()), 1, "the Record-claim head's ready check did not run: " + out)
        self.assertNotIn("ready by hand", out)
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.refs(), refs_before, "a push on a red ready check")
        self.assertEqual(self.host.readies, [], out)

    def test_a_record_claim_head_with_no_declared_ready_check_keeps_the_manual_ready_remedy(self):  # the control
        self.claim_head()  # the seed's own stamp: stamp kinds on, no ready checks declared
        self.use_ci_job([("PASS", "check invariants")], 0)
        refs_before = self.refs()
        rc, out = self.draft_confirm()
        self.assertEqual(self.lint_calls(), [], "ci-job ran with no ready checks declared")
        self.assertIn("ready by hand", out)
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.refs(), refs_before, out)
        self.assertEqual(self.host.readies, [], out)

    def test_a_ready_check_that_reads_the_pr_body_gets_the_pull_requests_body(self):
        """The ready check's ci-job run gets the PR's body as CI_JOB_PR_BODY, as the PR's own lint does, so a step that reads
        PR_BODY (silent-undo) sees the body it sees in CI."""
        body = "Summary.\n\nDrops-lines: docs/decisions/first.md -- the lines are dead\n"
        self.host.body = body
        self.declare([SILENT_UNDO])
        self.stale_feat()
        self.use_ci_job([("PASS", SILENT_UNDO)], 0)
        rc, out = self.draft_confirm()
        runs = self.lint_calls()
        self.assertEqual(len(runs), 1, "the ready check did not run ci-job once: " + out)
        self.assertEqual(runs[0].get("pr_body"), body, "the ready check's ci-job run got CI_JOB_PR_BODY %r, want the PR's body" % runs[0].get("pr_body"))
        self.assertEqual(rc, 0, out)

    def test_a_repo_that_declares_no_ready_checks_marks_ready_and_runs_no_ci_job(self):  # the control
        self.declare(None)
        self.stale_feat()
        self.use_ci_job([("PASS", "check invariants")], 0)
        rc, out = self.draft_confirm()
        self.assertEqual(self.lint_calls(), [], "ci-job ran with no ready checks declared")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.host.readies, [7], out)

    def test_a_repo_that_declares_no_ready_checks_says_so_in_one_line(self):
        self.declare(None)
        self.stale_feat()
        self.use_ci_job([("PASS", "check invariants")], 0)
        rc, out = self.draft_confirm()
        notes = [line for line in out.splitlines() if "declares no ready checks" in line.lower()]
        self.assertEqual(len(notes), 1, out)
        self.assertEqual(rc, 0, out)


class RunFolderSweep(unittest.TestCase):
    def test_an_old_sibling_run_folder_goes_and_a_new_one_stays(self):
        root = os.path.join(RUN_FOLDER, "sweep-root")
        os.makedirs(root)
        old = os.path.join(root, "4242-" + uuid.uuid4().hex)
        new = os.path.join(root, "4343-" + uuid.uuid4().hex)
        os.makedirs(old)
        os.makedirs(new)
        two_days_ago = time.time() - 2 * 24 * 60 * 60
        os.utime(old, (two_days_ago, two_days_ago))
        own = _test_temp.run_folder(root)
        self.assertFalse(os.path.exists(old), "the sweep kept a run folder two days old")
        self.assertTrue(os.path.isdir(new), "the sweep removed a run folder made now")
        self.assertTrue(os.path.isdir(own))


if __name__ == "__main__":
    unittest.main()
