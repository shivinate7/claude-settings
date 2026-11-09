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
StepCites: the step cite check. A `step:<slug>` cite in a record the pull request changes, or in its body, must name a step file on origin/roadmap;
git_spy counts the roadmap fetches (one with cites, none without).
Temp files: this run's folder (lint/_test_temp.py), removed at exit.
"""
import ast, atexit, contextlib, io, json, os, re, shlex, shutil, signal, subprocess, sys, tempfile, time, unittest, unittest.mock, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.append(os.path.join(os.path.dirname(HERE), "lint"))  # append: no lint module shadows one this suite imports
sys.path.append(os.path.join(os.path.dirname(HERE), "hooks"))  # append: the pin note's names (hooks/pin_note.py)
import _test_temp  # noqa: E402  test-temp-standard: this run's folder (lint/_test_temp.py)
import test_merge as tm  # noqa: E402  the git half's fixture and fakes; importing it runs none of its cases
import merge  # noqa: E402
from pin_note import MARKER as PIN_NOTE_MARKER  # noqa: E402  the one home of the pin note's marker (hooks/pin_note.py)
from workflow_steps import job_block, run_body, step_blocks, step_env, step_key, step_with  # noqa: E402  the one home of the step parser

RUN_FOLDER = _test_temp.run_folder()
atexit.register(shutil.rmtree, RUN_FOLDER, True)

PASSING = [("PASS", "record slugs"), ("PASS", "ste lint")]
FAILING = [("PASS", "record slugs"), ("FAIL", "comment narration")]
UNKNOWN = [("PASS", "record slugs"), ("unknown", "shellcheck")]
# The drift line bin/ste-changed prints under the pin note's variable: PIN_NOTE_MARKER, then this text.
PIN_NOTE_DRIFT = ("CI pins ste-lint at abc1234 (2026-10-01, .github/workflows/checks.yml:5), older than this copy's lint. "
                  "A line can pass here and fail CI. Move the pin to claude-settings main, in a lane of its own.")

STUB = '''import json, os, subprocess, sys, time
LOG, STEPS, RC, STEP_LOG, SLEEP, PARENT = __LOG__, __STEPS__, __RC__, __STEP_LOG__, __SLEEP__, os.getppid()
DETAILS = __DETAILS__  # step name -> the text after its verdict word; a step not named here reads `stub step`
def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True).stdout.strip()
detached = subprocess.run(["git", "symbolic-ref", "-q", "HEAD"], capture_output=True).returncode != 0
with open(LOG, "a", encoding="utf-8") as f:
    print(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd(), "head": git("rev-parse", "HEAD"), "detached": detached}), file=f)
if "--plan" in sys.argv:
    for state, name in STEPS:
        print("would run " + name)
    sys.exit(0)
end = time.time() + SLEEP  # a lint that runs long: it ends after SLEEP s, or at once when the run that started it is gone
while time.time() < end and os.getppid() == PARENT:
    time.sleep(0.05)
lines = ["%-15s %s: %s" % (state, name, DETAILS.get(name, "stub step")) for state, name in STEPS]
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

    def write_stub(self, steps, rc, sleep=0, details=None):
        """Write the stub ci-job: it prints `steps` ((state, step name) pairs), exits with `rc`, and runs `sleep` s first when it is set.
        `details` maps a step name to the text its line prints after the verdict word (default `stub step`)."""
        text = STUB.replace("__STEP_LOG__", repr(self.step_log)).replace("__LOG__", repr(self.log))
        tm.put(self.stub, text.replace("__STEPS__", repr(steps)).replace("__RC__", repr(rc)).replace("__SLEEP__", repr(sleep))
               .replace("__DETAILS__", repr(details or {})))
        return self.stub

    def use_ci_job(self, steps, rc, details=None):
        """merge.CI_JOB becomes a stub that prints `steps` ((state, step name) pairs) and exits with `rc`."""
        self.write_stub(steps, rc, details=details)
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


WAIT_LINE = "GitHub to show the pushed head"  # the progress text of the wait for a pushed head (merge.py wait_checks)
WAIT_CEILING = 600  # fake seconds a wait may run. The bound is the builder's choice; this ceiling only proves the wait is finite
WAIT_POLLS_CEILING = 30  # pull request reads one wait may make
RUNAWAY_PAUSES = 500  # pauses after which a wait that never ends is stopped, so a broken wait cannot hang the run
LAG_POLLS = 3  # reads that still show the stale head before GitHub shows the pushed one


class LagHost(tm.FakeHost):
    """A FakeHost whose pull request head lags a push: pr() reports `stale` for the first `lag` reads, then the head on origin.
    now() and pause() are tm.Clock's, so a wait moves a fake clock and costs no real time. lag=0 never reports the stale head."""

    def __init__(self, root, other, stale, lag, clock):
        super().__init__(root, other)
        self.stale, self.lag, self.clock, self.minute = stale, lag, clock, 60  # minute: Host's default poll interval, for a wait that reads it

    def now(self):
        return self.clock.now()

    def pause(self, seconds):
        if len(self.clock.pauses) >= RUNAWAY_PAUSES:
            raise AssertionError("the wait paused %d times and never ended" % RUNAWAY_PAUSES)
        self.clock.pause(seconds)

    def pr(self, n):
        info = super().pr(n)  # appends this read to pr_calls
        if len(self.pr_calls) <= self.lag:
            info["head"] = self.stale
        return info


class IntermediateHeadHost(LagHost):
    """A LagHost whose pull request shows `middle` on the read after its stale reads, before the pushed head: a third head GitHub shows mid-wait."""

    def __init__(self, root, other, stale, lag, middle, clock):
        super().__init__(root, other, stale, lag, clock)
        self.middle = middle

    def pr(self, n):
        info = super().pr(n)  # appends this read to pr_calls, and reports the stale or the pushed head
        if len(self.pr_calls) == self.lag + 1:
            info["head"] = self.middle
        return info


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
        text = text.replace("__STEPS__", repr(steps)).replace("__RC__", repr(rc)).replace("__SLEEP__", repr(0)).replace("__DETAILS__", "{}")
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

    def test_a_passing_lint_with_a_stale_pin_prints_the_whole_drift_line_on_its_pass_line(self):
        self.use_ci_job(PASSING, 0, details={"ste lint": PIN_NOTE_MARKER + PIN_NOTE_DRIFT})
        rc, out = self.lint_run("--lane-lint", "7")
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(pass_lines(out)), 1, out)
        self.assertIn(PIN_NOTE_MARKER + PIN_NOTE_DRIFT, out, "the PASS line lacks the whole drift line: " + out)

    def test_a_passing_lint_with_no_stale_pin_prints_no_pin_note(self):  # the control
        self.use_ci_job(PASSING, 0)
        rc, out = self.lint_run("--lane-lint", "7")
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(pass_lines(out)), 1, out)
        self.assertNotIn(PIN_NOTE_MARKER, out, "a pass with no drift printed a pin note: " + out)

    def test_a_passing_lint_names_its_skipped_ci_steps_on_the_pass_line(self):
        self.use_ci_job(PASSING + [("skipped", "Push-only lint A"), ("skipped", "Push-only lint B")], 0)
        rc, out = self.lint_run("--lane-lint", "7")
        self.assertEqual(rc, 0, out)
        lines = pass_lines(out)
        self.assertEqual(len(lines), 1, out)
        self.assertIn("Push-only lint A", lines[0], out)
        self.assertIn("Push-only lint B", lines[0], out)
        self.assertRegex(lines[0], r"\b2\b", out)

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

    def push_lane_commit(self):
        """The lane's push: one commit on the lane checkout's feat, pushed from there. -> (the head GitHub showed before it, the pushed head).
        The local head is that commit: the lane checkout's local feat, origin/feat and the pushed head are one sha."""
        stale = self.head("feat")
        tm.sh(self.co, "git", "checkout", "-q", "-B", "feat", "origin/feat")
        tm.put(os.path.join(self.co, "lane-push.txt"), "a lane pushes a commit\n")
        tm.sh(self.co, "git", "add", "-A")
        tm.sh(self.co, "git", "commit", "-q", "-m", "lane push")
        tm.sh(self.co, "git", "push", "-q", "origin", "feat")
        pushed = tm.sh(self.co, "git", "rev-parse", "feat")
        self.assertNotEqual(stale, pushed, "the case pushed nothing")
        self.assertEqual(self.head("feat"), pushed, "the push did not land on origin")
        return stale, pushed

    def lagging_host(self, stale, lag):
        """self.host becomes a LagHost on the lane checkout, with a fresh tm.Clock. -> the clock."""
        clock = tm.Clock()
        self.host = LagHost(self.co, self.other, stale, lag, clock)
        return clock

    def test_lane_lint_waits_for_github_to_show_the_pushed_head_then_lints_that_head(self):
        stale, pushed = self.push_lane_commit()
        clock = self.lagging_host(stale, LAG_POLLS)
        self.use_ci_job(PASSING, 0)
        start = clock.now()
        rc, text = self.run_lane("--lane-lint", "7")
        self.assertIn(WAIT_LINE, text, "lane_lint did not wait for GitHub to show the pushed head: " + text)
        self.assertGreater(clock.now(), start, "lane_lint printed the wait but the fake clock did not move: " + text)
        self.assertEqual(rc, 0, "lane_lint refused after GitHub showed the pushed head: " + text)
        runs = self.lint_calls()
        self.assertEqual(len(runs), 1, "the lint ran %d times, want once: %s" % (len(runs), text))
        self.assertEqual(runs[0]["head"], pushed, "the lint ran on a head other than the pushed one")
        self.assertEqual(len(pass_lines(text)), 1, text)

    def test_lane_lint_refuses_after_a_bounded_wait_when_github_never_shows_the_pushed_head(self):
        stale, pushed = self.push_lane_commit()
        clock = self.lagging_host(stale, float("inf"))
        self.use_ci_job(PASSING, 0)
        start = clock.now()
        rc, text = self.run_lane("--lane-lint", "7")
        self.assertIn(WAIT_LINE, text, "lane_lint did not wait for GitHub to show the pushed head before it refused: " + text)
        waited = clock.now() - start
        self.assertLessEqual(waited, WAIT_CEILING, "the wait had no finite bound: it ran %d fake seconds" % waited)
        self.assertLessEqual(len(self.host.pr_calls), WAIT_POLLS_CEILING, "the wait read GitHub %d times" % len(self.host.pr_calls))
        self.assertEqual(rc, 1, "lane_lint did not refuse a head GitHub never showed: " + text)
        refusal = "\n".join(line for line in text.splitlines() if WAIT_LINE not in line)
        self.assertIn("GitHub", refusal, "the refusal does not say GitHub never showed the pushed head: " + text)
        self.assertIn(pushed[:7], refusal, "the refusal does not name the local head GitHub never showed: " + text)
        self.assertEqual(pass_lines(text), [], text)
        self.assertEqual(self.lint_calls(), [], "the lint ran on a head GitHub never showed")

    def test_lane_lint_does_not_wait_when_github_already_shows_the_pushed_head(self):  # the control
        head = self.head("feat")  # nothing pushed here: origin's feat is the pushed head, and GitHub shows it
        tm.sh(self.co, "git", "checkout", "-q", "-B", "feat", "origin/feat")  # the local head is the pushed head, as in the pushed cases
        clock = self.lagging_host(head, lag=0)  # lag=0: pr() never reports a stale head
        self.use_ci_job(PASSING, 0)
        rc, text = self.lint_run("--lane-lint", "7", head=head)
        self.assertEqual(rc, 0, text)
        self.assertEqual(clock.pauses, [], "lane_lint paused although GitHub already showed the pushed head: %s" % clock.pauses)
        self.assertNotIn(WAIT_LINE, text, "lane_lint printed a wait with nothing to wait for: " + text)

    def test_lane_lint_ref_target_never_waits_for_github(self):
        sha = self.head("feat")
        clock = self.lagging_host("0" * 40, float("inf"))  # a pull request read would show a head that never matches the ref
        self.use_ci_job(PASSING, 0)
        for target in (sha, "origin/feat"):  # a commit, and a ref that names the same commit
            with self.subTest(target=target):
                rc, text = self.lint_run("--lane-lint", target, head=sha)
                self.assertEqual(rc, 0, text)
                self.assertEqual(clock.pauses, [], "a commit or ref target paused: %s" % clock.pauses)
                self.assertNotIn(WAIT_LINE, text, "a commit or ref target printed a wait: " + text)
        self.assertEqual(self.host.pr_calls, [], "a commit or ref target read the pull request, which it never needs")

    def test_lane_lint_refuses_when_the_pull_request_base_changes_during_the_wait(self):
        stale, pushed = self.push_lane_commit()
        self.lagging_host(stale, LAG_POLLS)
        self.host.base_seq = ["main", "develop"]  # the base reads main on the first read, then develop on every later one
        self.use_ci_job(PASSING, 0)
        rc, text = self.run_lane("--lane-lint", "7")
        self.assertIn(WAIT_LINE, text, "lane_lint did not wait for GitHub to show the pushed head, so the base never moved during a wait: " + text)
        self.assertEqual(rc, 1, "lane_lint did not refuse after the pull request's base moved from main to develop during the wait: " + text)
        refusal = "\n".join(line for line in text.splitlines() if WAIT_LINE not in line)
        self.assertIn("develop", refusal, "the refusal does not name the new base: " + text)
        self.assertIn("main", refusal, "the refusal does not name the base the lint was about to use: " + text)
        self.assertEqual(pass_lines(text), [], "lane_lint printed PASS against the base the pull request had before the wait: " + text)
        self.assertEqual(self.lint_calls(), [], "the lint ran although the pull request's base had changed: %s" % self.lint_calls())

    def test_lane_lint_keeps_waiting_through_an_intermediate_head_then_lints_the_pushed_head(self):
        stale, pushed = self.push_lane_commit()
        middle = self.head("main")  # a head GitHub shows after the stale ones and before the pushed one: a commit that is neither
        self.assertNotIn(middle, (stale, pushed), "the case needs a third head")
        self.host = IntermediateHeadHost(self.co, self.other, stale, LAG_POLLS, middle, tm.Clock())
        self.use_ci_job(PASSING, 0)
        rc, text = self.run_lane("--lane-lint", "7")
        self.assertIn(WAIT_LINE, text, "lane_lint did not wait for GitHub to show the pushed head: " + text)
        self.assertEqual(rc, 0, "lane_lint refused the pushed head after GitHub showed an intermediate head first: " + text)
        runs = self.lint_calls()
        self.assertEqual(len(runs), 1, "the lint ran %d times, want once: %s" % (len(runs), text))
        self.assertEqual(runs[0]["head"], pushed, "the lint ran on a head other than the pushed one")
        self.assertEqual(len(pass_lines(text)), 1, text)

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


BATCH = "batch-lint-flags"  # the batch the case lints: a pushed branch whose checks job holds the four CI steps below
BATCH_MISSING = "batch-lint-flags-no-red-run"  # the same batch with the Red-run trailer's script left out
BASE = "main"  # the base the lint runs against: lane_lint's base, and the PR base the CI steps read
BATCH_CI_STEPS = ("Silent undo check", "Comment narration check", "Red-run trailer", "STE lint")  # checks.yml's job `checks` CI steps this suite lints
STE = "STE lint"  # the one CI step whose script is bin/ste-changed, not a file of the batch
REPO = os.path.dirname(HERE)
CHECKS_YML = os.path.join(REPO, ".github", "workflows", "checks.yml")  # read at test time; no expectation comes from a copy of it
CALL_STUB = "import json, sys\nwith open(%r, 'a', encoding='utf-8') as f:\n    print(json.dumps({'argv': sys.argv}), file=f)\n"  # logs its argv, exits 0
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
        values = {"github.base_ref": BASE, "github.event.pull_request.head.sha": head}
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


STEP_FOLDER = "roadmap/data/steps"  # origin's roadmap branch holds each step as a file; a step cite names one by its stem
STEP_JSON = {"title": "t", "status": "todo", "phase": "cleanup", "order": 1, "note": "n", "updatedAt": "2026-10-26T00:00:00Z"}
ROADMAP_NAME = re.compile(r"(?:^|[/:+ ])roadmap(?=$|[/:])")  # the branch, its remote ref or its step folder, as one git argument


def names_roadmap(argv):
    """True when a git call names origin's roadmap branch or its step folder. The -C path is no name."""
    rest = argv[3:] if argv[1:2] == ["-C"] else argv[1:]
    return any(ROADMAP_NAME.search(arg) for arg in rest)


def roadmap_fetches(calls):
    return [argv for argv in calls if "fetch" in argv and names_roadmap(argv)]


def roadmap_reads(calls):
    return [argv for argv in calls if "fetch" not in argv and names_roadmap(argv)]


def decision_text(slug, body):
    """A decision record of the fixture: the frontmatter record() writes, then `body`."""
    return "---\nid: D-010\nslug: %s\ntitle: %s\n---\n%s\n" % (slug, slug.title(), body)


def debt_text(slug):
    """A debt record of the fixture that cites the step `slug`."""
    return "# Gap one\n\n- **What.** Cites `step:%s`.\n" % slug


class StepCites(CiJobStub, tm.CloudSession):
    """merge --lane-lint's step cite check. A `step:<slug>` cite in a record the pull request changes (docs/decisions/*.md, docs/debts/*.md,
    a CLAUDE.md), or for a pull request number in its body, must name a step file on origin's roadmap branch. Each case writes origin's roadmap
    (put_roadmap) and its pull request head (push_feat, push_main) from the second clone, and runs the lint stub of CiJobStub, so no real lint runs.
    git_spy logs each git call merge makes, so a case reads how often the roadmap is fetched."""

    @classmethod
    def setUpClass(cls):
        unittest.TestCase.setUpClass()  # not CloudSession's: it would make a second run folder
        cls.run_dir = RUN_FOLDER

    def setUp(self):
        with unittest.mock.patch.object(tempfile, "tempdir", RUN_FOLDER):  # Env.setUp makes its repos in the temp dir: keep them in this run's folder
            super().setUp()
        self.lock = NoLock()
        self.init_stub()
        self.use_ci_job(PASSING, 0)

    run_lane = LaneLint.run_lane  # the run and its refusal read, as LaneLint reads them
    lint_run = LaneLint.lint_run

    def put_roadmap(self, slugs, branch="roadmap"):
        """origin's record branch `branch`: an orphan holding roadmap/data/steps/<slug>.json for each of `slugs`. Each call takes its own local name."""
        o = self.other
        local = "fixture-" + branch
        tm.sh(o, "git", "fetch", "-q", "origin")
        tm.sh(o, "git", "checkout", "-q", "--orphan", local)
        tm.sh(o, "git", "rm", "-rq", "-f", ".")
        for slug in slugs:
            tm.put(os.path.join(o, STEP_FOLDER, slug + ".json"), json.dumps(STEP_JSON))
        tm.sh(o, "git", "add", "-A")
        tm.sh(o, "git", "commit", "-qm", "record branch steps")
        tm.sh(o, "git", "push", "-q", "origin", f"{local}:refs/heads/{branch}")

    def write_layout_extras(self, keys):
        """The lane checkout's extras file, as lint/layout.py reads it from the root the lint runs in: `kinds`, plus the `keys` given."""
        data = {"kinds": {}}
        data.update(keys)
        tm.put(os.path.join(self.co, ".claude", "layout-extras.json"), json.dumps(data) + "\n")

    def push_main(self, files):
        """One commit on origin's main holding `files` ({path: text}), pushed from the second clone."""
        o = self.other
        tm.sh(o, "git", "fetch", "-q", "origin")
        tm.sh(o, "git", "checkout", "-q", "-B", "main", "origin/main")
        for rel, text in files.items():
            tm.put_lf(os.path.join(o, rel), text)
        tm.sh(o, "git", "add", "-A")
        tm.sh(o, "git", "commit", "-qm", "main moves")
        tm.sh(o, "git", "push", "-q", "origin", "main")

    def push_feat(self, files):
        """The pull request head: one commit on origin's feat holding `files` ({path: text}), made after origin/main is merged in. -> the pushed head."""
        o = self.other
        tm.sh(o, "git", "fetch", "-q", "origin")
        tm.sh(o, "git", "checkout", "-q", "-B", "feat", "origin/feat")
        tm.sh(o, "git", "merge", "-q", "--no-edit", "origin/main")
        for rel, text in files.items():
            tm.put_lf(os.path.join(o, rel), text)
        tm.sh(o, "git", "add", "-A")
        tm.sh(o, "git", "commit", "-qm", "feat: step cites")
        tm.sh(o, "git", "push", "-q", "origin", "feat")
        return self.head("feat")

    @contextlib.contextmanager
    def git_spy(self, fail=lambda argv: False):
        """Log each git call merge makes and fail each call `fail` picks, with rc 128. Yields the list of logged argvs."""
        calls, real = [], merge.sh

        def spy(args, *rest, **kwargs):
            if args and args[0] == "git":
                calls.append(list(args))
                if fail(args):
                    return 128, "fatal: refused by the test"
            return real(args, *rest, **kwargs)

        with unittest.mock.patch.object(merge, "sh", spy):
            yield calls

    def test_a_missing_step_cited_inline_in_a_changed_decision_refuses_and_names_it(self):
        self.put_roadmap(["real-step"])
        self.push_feat({"docs/decisions/cites-one.md": decision_text("cites-one", "Builds on `step:ghost-alpha`.")})
        rc, text = self.run_lane("--lane-lint", "7")
        self.assertEqual(rc, 1, "a changed decision's missing step cite passed the lint: " + text)
        self.assertIn("ghost-alpha", text, "the refusal does not name the missing step: " + text)
        self.assertEqual(pass_lines(text), [], "the lint printed PASS over a missing step: " + text)

    def test_a_step_cited_in_a_changed_decision_that_is_on_the_roadmap_passes(self):  # the control
        self.put_roadmap(["real-step"])
        self.push_feat({"docs/decisions/cites-one.md": decision_text("cites-one", "Builds on `step:real-step`.")})
        rc, text = self.lint_run("--lane-lint", "7")
        self.assertEqual(rc, 0, "a cite of a step on the roadmap refused the lint: " + text)
        self.assertEqual(len(pass_lines(text)), 1, text)

    def test_a_missing_step_cited_in_the_pr_body_refuses_and_names_it(self):
        self.put_roadmap(["real-step"])
        self.host.body = "Lane summary. Builds on `step:body-ghost`.\n"
        rc, text = self.run_lane("--lane-lint", "7")
        self.assertEqual(rc, 1, "a missing step cite in the pull request body passed the lint: " + text)
        self.assertIn("body-ghost", text, "the refusal does not name the missing step in the body: " + text)
        self.assertEqual(pass_lines(text), [], "the lint printed PASS over a missing step: " + text)

    def test_a_step_cited_in_the_pr_body_that_is_on_the_roadmap_passes(self):  # the control
        self.put_roadmap(["real-step"])
        self.host.body = "Builds on `step:real-step`.\n"
        rc, text = self.lint_run("--lane-lint", "7")
        self.assertEqual(rc, 0, "a body cite of a step on the roadmap refused the lint: " + text)

    def test_a_missing_step_cited_in_a_changed_debt_or_the_claude_md_refuses_and_names_both(self):
        self.put_roadmap(["real-step"])
        self.push_feat({"docs/debts/gap-one.md": debt_text("debt-ghost"), "CLAUDE.md": "# Rules\n\nSee `step:claude-ghost`.\n"})
        rc, text = self.run_lane("--lane-lint", "7")
        self.assertEqual(rc, 1, "a missing step cite in a changed debt or CLAUDE.md passed the lint: " + text)
        self.assertIn("debt-ghost", text, "the refusal does not name the debt's missing step: " + text)
        self.assertIn("claude-ghost", text, "the refusal does not name the CLAUDE.md's missing step: " + text)

    def test_a_missing_step_cited_by_two_records_is_printed_once(self):
        self.put_roadmap(["real-step"])
        self.push_feat({"docs/decisions/cites-one.md": decision_text("cites-one", "See `step:twice-ghost`."),
                        "docs/debts/gap-one.md": debt_text("twice-ghost")})
        rc, text = self.run_lane("--lane-lint", "7")
        self.assertEqual(rc, 1, "a missing step cited by two records did not refuse: " + text)
        self.assertEqual(text.count("twice-ghost"), 1, "the one missing step is printed %d times, want once: %s" % (text.count("twice-ghost"), text))

    def test_the_missing_steps_print_in_sorted_order(self):
        self.put_roadmap(["real-step"])
        self.push_feat({"docs/decisions/cites-one.md": decision_text("cites-one", "Cites `step:zulu-ghost` then `step:alpha-ghost`.")})
        rc, text = self.run_lane("--lane-lint", "7")
        self.assertEqual(rc, 1, "two missing steps did not refuse: " + text)
        self.assertIn("alpha-ghost", text, "the refusal does not name alpha-ghost: " + text)
        self.assertIn("zulu-ghost", text, text)
        self.assertLess(text.index("alpha-ghost"), text.index("zulu-ghost"), "the missing steps are not printed in sorted order: " + text)

    def test_a_cite_inside_a_fenced_block_is_ignored_and_a_cite_after_the_fences_refuses(self):
        self.put_roadmap(["real-step"])
        body = "```\nstep:fenced-ghost\n```\n~~~\nstep:tilde-ghost\n~~~\nAfter both fences: `step:after-ghost`.\n"
        self.push_feat({"docs/decisions/cites-one.md": decision_text("cites-one", body)})
        rc, text = self.run_lane("--lane-lint", "7")
        self.assertEqual(rc, 1, "the cite after the fences passed the lint: " + text)
        self.assertIn("after-ghost", text, "the refusal does not name the cite after the fences: " + text)
        self.assertNotIn("fenced-ghost", text, "a cite inside a backtick fence was counted: " + text)
        self.assertNotIn("tilde-ghost", text, "a cite inside a tilde fence was counted: " + text)

    def test_the_placeholder_step_slug_is_no_cite_and_a_real_missing_cite_still_refuses(self):
        self.put_roadmap(["real-step"])
        self.push_feat({"docs/decisions/cites-one.md": decision_text("cites-one", "Write the cite as `step:<slug>`. Real: `step:placeholder-ghost`.")})
        rc, text = self.run_lane("--lane-lint", "7")
        self.assertEqual(rc, 1, "a real missing cite beside a placeholder did not refuse: " + text)
        self.assertIn("placeholder-ghost", text, "the refusal does not name the real missing step: " + text)
        self.assertNotIn("step:<slug>", text, "the placeholder was read as a cite: " + text)

    def test_prose_next_step_is_no_cite_and_a_real_missing_cite_still_refuses(self):
        self.put_roadmap(["real-step"])
        self.push_feat({"docs/decisions/cites-one.md": decision_text("cites-one", "The next step: prose-word is open. Real: `step:prose-ghost`.")})
        rc, text = self.run_lane("--lane-lint", "7")
        self.assertEqual(rc, 1, "a real missing cite beside prose did not refuse: " + text)
        self.assertIn("prose-ghost", text, "the refusal does not name the real missing step: " + text)
        self.assertNotIn("prose-word", text, "prose 'next step: foo' was read as a cite: " + text)

    def test_a_missing_step_cited_bare_in_prose_refuses_and_names_it(self):  # a cite needs no backticks: the repo's cite regex ignores them
        self.put_roadmap(["real-step"])
        self.push_feat({"docs/decisions/cites-one.md": decision_text("cites-one", "Builds on step:bare-ghost in prose.")})
        rc, text = self.run_lane("--lane-lint", "7")
        self.assertEqual(rc, 1, "a missing step cited bare, without backticks, passed the lint: " + text)
        self.assertIn("bare-ghost", text, "the refusal does not name the bare missing step: " + text)
        self.assertEqual(pass_lines(text), [], "the lint printed PASS over a bare missing step: " + text)

    def test_a_cite_of_a_step_on_the_fork_record_branch_passes_under_the_record_branch_key(self):
        self.put_roadmap(["roadmap-only-step"])
        self.put_roadmap(["fork-step"], branch="roadmap-fork")
        self.write_layout_extras({"record-branch": "roadmap-fork"})
        self.push_feat({"docs/decisions/cites-one.md": decision_text("cites-one", "Builds on `step:fork-step`.")})
        rc, text = self.run_lane("--lane-lint", "7")
        self.assertEqual(rc, 0, "a cite of a step on the record branch named by the extras key refused the lint: " + text)
        self.assertEqual(len(pass_lines(text)), 1, "the lint passed with no PASS line: " + text)

    def test_a_cite_of_a_step_only_on_origin_roadmap_is_refused_under_the_record_branch_key(self):
        self.put_roadmap(["roadmap-only-step"])
        self.put_roadmap(["fork-step"], branch="roadmap-fork")
        self.write_layout_extras({"record-branch": "roadmap-fork"})
        self.push_feat({"docs/decisions/cites-one.md": decision_text("cites-one", "Builds on `step:roadmap-only-step`.")})
        rc, text = self.run_lane("--lane-lint", "7")
        self.assertEqual(rc, 1, "a step only on origin/roadmap passed under the extras key that names roadmap-fork: " + text)
        self.assertIn("roadmap-only-step", text, "the refusal does not name the step missing from the named record branch: " + text)
        self.assertEqual(pass_lines(text), [], "the lint printed PASS over a step missing from the named record branch: " + text)

    def test_a_changed_record_with_an_open_fence_refuses_as_unknown_even_with_no_cite(self):
        self.put_roadmap(["real-step"])
        self.push_feat({"docs/decisions/cites-one.md": decision_text("cites-one", "```bash\nnpm test")})
        rc, text = self.run_lane("--lane-lint", "7")
        self.assertEqual(rc, 1, "a changed record with an open fence passed the lint: " + text)
        self.assertIn("unknown, not a pass", text, "the refusal does not say unknown, not a pass: " + text)
        self.assertEqual(pass_lines(text), [], "the lint printed PASS over an open fence: " + text)

    def test_a_cite_after_an_open_fence_refuses_as_unknown_and_never_passes(self):
        self.put_roadmap(["real-step"])
        self.push_feat({"docs/decisions/cites-one.md": decision_text("cites-one", "```bash\nnpm test\n\nBuilds on `step:ghost-x`.")})
        rc, text = self.run_lane("--lane-lint", "7")
        self.assertEqual(rc, 1, "a cite hidden by an open fence passed the lint: " + text)
        self.assertIn("unknown, not a pass", text, "the refusal does not say unknown, not a pass: " + text)
        self.assertEqual(pass_lines(text), [], "the lint printed PASS over a cite hidden by an open fence: " + text)

    def test_a_changed_record_with_a_closed_fence_passes(self):  # the control
        self.put_roadmap(["real-step"])
        self.push_feat({"docs/decisions/cites-one.md": decision_text("cites-one", "```bash\nnpm test\n```\n\nBuilds on `step:real-step`.")})
        rc, text = self.lint_run("--lane-lint", "7")
        self.assertEqual(rc, 0, "a changed record with a closed fence refused the lint: " + text)
        self.assertEqual(len(pass_lines(text)), 1, text)

    def test_a_lone_quote_or_a_comment_opener_before_a_cite_does_not_hide_it(self):
        lines = ["Don't: `step:lone-ghost`.", "Note // `step:slash-ghost`.", "Note # `step:hash-ghost`.",
                 "Note /* `step:block-ghost`.", 'He said "`step:double-ghost`".']
        self.put_roadmap(["real-step"])
        self.push_feat({"docs/decisions/cites-one.md": decision_text("cites-one", "\n".join(lines))})
        rc, text = self.run_lane("--lane-lint", "7")
        self.assertEqual(rc, 1, "a missing cite after a quote or a comment opener did not refuse: " + text)
        for slug in ("lone-ghost", "slash-ghost", "hash-ghost", "block-ghost", "double-ghost"):
            self.assertIn(slug, text, "a cite after a quote or an opener was hidden, so %s is not named: %s" % (slug, text))

    def test_a_missing_cite_in_a_record_the_pull_request_did_not_change_is_ignored(self):
        self.put_roadmap(["real-step"])
        self.push_main({"docs/decisions/old-bad.md": decision_text("old-bad", "Old: `step:main-only-ghost`.")})
        self.push_feat({"docs/decisions/cites-one.md": decision_text("cites-one", "New: `step:changed-ghost`.")})
        rc, text = self.run_lane("--lane-lint", "7")
        self.assertEqual(rc, 1, "the changed record's missing cite passed the lint: " + text)
        self.assertIn("changed-ghost", text, "the refusal does not name the changed record's missing step: " + text)
        self.assertNotIn("main-only-ghost", text, "a record the pull request did not change was scanned: " + text)

    def test_a_missing_cite_in_a_changed_file_outside_the_record_homes_is_ignored(self):
        self.put_roadmap(["real-step"])
        self.push_feat({"docs/plans/plan-one.md": "Plan: `step:plan-ghost`.\n",
                        "docs/decisions/cites-one.md": decision_text("cites-one", "Real: `step:decision-ghost`.")})
        rc, text = self.run_lane("--lane-lint", "7")
        self.assertEqual(rc, 1, "a changed decision's missing cite did not refuse: " + text)
        self.assertIn("decision-ghost", text, "the refusal does not name the decision's missing step: " + text)
        self.assertNotIn("plan-ghost", text, "a changed file outside the record homes was scanned: " + text)

    def test_a_ref_target_reads_no_pr_body_and_refuses_only_for_its_changed_records(self):
        self.put_roadmap(["real-step"])
        sha = self.push_feat({"docs/decisions/cites-one.md": decision_text("cites-one", "Real: `step:ref-record-ghost`.")})
        self.host.body = "Body: `step:ref-body-ghost`.\n"
        rc, text = self.run_lane("--lane-lint", sha)
        self.assertEqual(rc, 1, "a ref target's missing record cite passed the lint: " + text)
        self.assertIn("ref-record-ghost", text, "the refusal does not name the changed record's missing step: " + text)
        self.assertNotIn("ref-body-ghost", text, "a ref target scanned a pull request body: " + text)
        self.assertEqual(self.host.pr_calls, [], "a ref target read the pull request")

    def test_a_step_file_only_on_main_does_not_count_as_on_the_roadmap(self):
        self.put_roadmap(["real-step"])
        self.push_main({"roadmap/data/steps/main-only-step.json": json.dumps(STEP_JSON)})
        self.push_feat({"docs/decisions/cites-one.md": decision_text("cites-one", "Real: `step:main-only-step`.")})
        rc, text = self.run_lane("--lane-lint", "7")
        self.assertEqual(rc, 1, "a step file on main, not on origin's roadmap, passed the lint: " + text)
        self.assertIn("main-only-step", text, "the refusal does not name the step missing from the roadmap: " + text)

    def test_the_roadmap_is_fetched_once_for_every_cite_of_the_run(self):
        self.put_roadmap(["one-real", "two-real"])
        self.push_feat({"docs/decisions/cites-one.md": decision_text("cites-one", "See `step:one-real`."),
                        "docs/decisions/cites-two.md": decision_text("cites-two", "See `step:two-real` and `step:one-real`.")})
        self.host.body = "Builds on `step:two-real`.\n"
        with self.git_spy() as calls:
            rc, text = self.lint_run("--lane-lint", "7")
        self.assertTrue(calls, "the spy saw no git call, so the case proves nothing")
        self.assertEqual(rc, 0, text)
        fetches = roadmap_fetches(calls)
        self.assertEqual(len(fetches), 1, "origin's roadmap was fetched %d times for the run's cites, want once: %s" % (len(fetches), fetches))

    def test_a_run_with_no_cite_never_fetches_or_reads_the_roadmap(self):  # the control
        self.put_roadmap(["real-step"])
        self.push_feat({"docs/decisions/cites-one.md": decision_text("cites-one", "No cite here.")})
        with self.git_spy() as calls:
            rc, text = self.lint_run("--lane-lint", "7")
        self.assertTrue(calls, "the spy saw no git call, so the case proves nothing")
        self.assertEqual(rc, 0, text)
        self.assertEqual(roadmap_fetches(calls), [], "a run with no cite fetched the roadmap: %s" % roadmap_fetches(calls))
        self.assertEqual(roadmap_reads(calls), [], "a run with no cite read the roadmap: %s" % roadmap_reads(calls))

    def test_a_failed_roadmap_fetch_refuses_as_unknown_and_never_passes(self):
        self.put_roadmap(["real-step"])
        self.push_feat({"docs/decisions/cites-one.md": decision_text("cites-one", "See `step:real-step`.")})
        with self.git_spy(fail=lambda argv: "fetch" in argv and names_roadmap(argv)) as calls:
            rc, text = self.run_lane("--lane-lint", "7")
        self.assertTrue(roadmap_fetches(calls), "the roadmap fetch never ran, so the case proves nothing: " + text)
        self.assertNotEqual(rc, 0, "a failed roadmap fetch read as a pass: " + text)
        self.assertIn("unknown", text.lower(), "a failed roadmap fetch is not reported as unknown: " + text)
        self.assertEqual(pass_lines(text), [], "a failed roadmap fetch printed PASS: " + text)

    def test_a_failed_read_of_the_roadmap_refuses_as_unknown_and_never_passes(self):
        self.put_roadmap(["real-step"])
        self.push_feat({"docs/decisions/cites-one.md": decision_text("cites-one", "See `step:real-step`.")})
        with self.git_spy(fail=lambda argv: "fetch" not in argv and names_roadmap(argv)) as calls:
            rc, text = self.run_lane("--lane-lint", "7")
        self.assertTrue(roadmap_reads(calls), "no read of the roadmap ran, so the case proves nothing: " + text)
        self.assertNotEqual(rc, 0, "a failed read of the roadmap read as a pass: " + text)
        self.assertIn("unknown", text.lower(), "a failed read of the roadmap is not reported as unknown: " + text)
        self.assertEqual(pass_lines(text), [], "a failed read of the roadmap printed PASS: " + text)

    def test_a_roadmap_of_many_steps_refuses_only_the_one_cite_that_is_missing(self):
        slugs = ["bulk-step-%03d" % i for i in range(120)]
        self.put_roadmap(slugs)
        cites = " ".join("`step:%s`" % slug for slug in slugs[:60]) + " and `step:bulk-ghost`."
        self.push_feat({"docs/decisions/cites-one.md": decision_text("cites-one", cites)})
        with self.git_spy() as calls:
            rc, text = self.run_lane("--lane-lint", "7")
        self.assertTrue(calls, "the spy saw no git call, so the case proves nothing")
        self.assertEqual(rc, 1, "a run citing one missing step among many did not refuse: " + text)
        self.assertEqual(text.count("bulk-ghost"), 1, "the missing step is printed %d times, want once: %s" % (text.count("bulk-ghost"), text))
        self.assertNotIn("bulk-step-", text, "a step on the roadmap was named as missing: " + text)
        self.assertEqual(len(roadmap_fetches(calls)), 1, "origin's roadmap was fetched %d times, want once" % len(roadmap_fetches(calls)))


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
