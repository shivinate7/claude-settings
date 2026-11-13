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
Temp files: this run's folder (lint/_test_temp.py), removed at exit.
"""
import ast, atexit, contextlib, importlib.util, io, json, os, re, shlex, shutil, signal, subprocess, sys, tempfile, time, unittest, unittest.mock, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.append(os.path.join(os.path.dirname(HERE), "lint"))  # append: no lint module shadows one this suite imports
sys.path.append(os.path.join(os.path.dirname(HERE), "hooks"))  # append: the pin note's names (hooks/pin_note.py)
sys.path.append(os.path.join(os.path.dirname(HERE), "testing"))  # append: no testing module shadows one this suite imports
import _test_temp  # noqa: E402  test-temp-standard: this run's folder (lint/_test_temp.py)
import test_merge as tm  # noqa: E402  the git half's fixture and fakes; importing it runs none of its cases
from test_merge import LANE_LINT_MARKER, NOT_OWNER, lint_comment  # noqa: E402  the lint comment's one form, in test_merge.py (decision lanes-run-no-full-ci-job)
from required_check import REQUIRED_CHECK  # noqa: E402  the one home of the required check's name (hooks/required_check.py)
import merge  # noqa: E402
import shallow_clone  # noqa: E402  the one shallow-clone fixture (testing/shallow_clone.py)
from pin_note import MARKER as PIN_NOTE_MARKER  # noqa: E402  the one home of the pin note's marker (hooks/pin_note.py)
from workflow_steps import job_block, run_body, step_blocks, step_env, step_key, step_with  # noqa: E402  the one home of the step parser

RUN_FOLDER = _test_temp.run_folder()
atexit.register(shutil.rmtree, RUN_FOLDER, True)


def setUpModule():
    tm.install_model_guard()  # the test base of test_merge: a join here runs the prose judge, and no case starts `claude -p`

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
body_file = os.environ.get("CI_JOB_PR_BODY_FILE")  # the body ci-job is given: a UTF-8 file, read whole; None when no file is named
body = None if body_file is None else open(body_file, encoding="utf-8", newline="").read()
with open(LOG, "a", encoding="utf-8") as f:
    print(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd(), "head": git("rev-parse", "HEAD"), "detached": detached, "pr_body": body}), file=f)
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


def rollup_skip_lines(text):
    """-> the `merge:` lines that say the lane lint was skipped. One line carries the words, so a case reads its keywords off one line."""
    return [line for line in text.splitlines() if line.startswith("merge:") and re.search(r"(?i)\blint\b", line) and re.search(r"(?i)\bskip", line)]


RUN_STATE = {"pass": ("completed", "success"), "fail": ("completed", "failure"), "pending": ("in_progress", ""), "skipping": ("completed", "skipped")}  # the run each bucket's row stands for: a copy of test_merge's RUN_OF, which sits in the fake gh shim's text and cannot be imported

def rollup_by_run(runs):
    """-> (checks_seq, runs_seq) for a head whose all-jobs-passed rows come from `runs`: (run id, bucket) pairs, oldest first. Each row links its
    run, as GitHub's check run does, and the run list names the same runs, newest first, as gh lists them. A head whose rows name no run is
    built with the state of refused_with_rollup, not with this."""
    seq = [("checks", "pass", ""), *[(REQUIRED_CHECK, bucket, tm.job_link(rid, 1)) for rid, bucket in runs]]
    listed = [("checks", *RUN_STATE[bucket], rid, 7) for rid, bucket in reversed(runs)]
    return [seq], [listed]


class NoLock:
    """The lane run takes no merge lock: a lock call fails the case."""
    def acquire(self, *args, **kwargs):
        raise AssertionError("merge --lane-lint took the merge lock")

    def release(self, *args, **kwargs):
        raise AssertionError("merge --lane-lint released a merge lock")

    def unlock(self, *args, **kwargs):
        raise AssertionError("merge --lane-lint unlocked a merge lock")




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


WAIT_LINE ="GitHub to show the pushed head"  # the progress text of the wait for a pushed head (merge.py wait_checks)
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


class LaneFixture(CiJobStub, tm.CloudSession):
    """The lane-lint fixture: the repo pair, the stub ci-job and the run helpers. LaneLint and CrossMeasure share it."""
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

    def merge_into_feat(self, ref):
        """The lane's head merges `ref` (a ref the second clone sees) in with a merge commit, and is pushed. -> the new head sha."""
        o = self.other
        tm.sh(o, "git", "checkout", "-q", "-B", "feat", "origin/feat")
        tm.sh(o, "git", "merge", "-q", "--no-ff", "-m", "merge %s into feat" % ref, ref)
        tm.sh(o, "git", "push", "-q", "origin", "feat")
        return self.head("feat")


class LaneLint(LaneFixture):
    """The lane-lint cases: the lint's verdicts, the stack check, the shallow reads and the ref targets."""

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

    def test_lane_lint_gives_ci_job_the_live_pr_body_in_its_body_file(self):
        """ci-job takes the PR body from the UTF-8 file named by CI_JOB_PR_BODY_FILE, so lane_lint passes the body the host reports
        for the pull request now. The states are an empty body and the largest body GitHub keeps."""
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
                self.assertIsNotNone(got, "lane_lint named no body file for ci-job: CI_JOB_PR_BODY_FILE was unset")
                self.assertEqual(got, body, "lane_lint gave ci-job a body of %d characters, want the PR's body of %d characters"
                                 % (len(got), len(body)))

    def test_a_ref_target_gives_ci_job_an_empty_pr_body_whatever_the_run_holds(self):
        """A commit or ref has no PR body, so lane_lint gives ci-job an empty body file. The host body, and the body file and
        event file the run inherits, all hold the body, so a body passed on from any of them shows as a value."""
        self.use_ci_job(PASSING, 0)
        body = "Summary.\n\nDrops-lines: lint/gone.py -- the file is gone\n\nhttps://claude.ai/code/session_X"
        self.host.body = body
        inherited = os.path.join(self.t, "inherited-body.txt")
        with open(inherited, "w", encoding="utf-8", newline="") as f:
            f.write(body)
        event = os.path.join(self.t, "inherited-event.json")
        with open(event, "w", encoding="utf-8") as f:
            json.dump({"pull_request": {"body": body}}, f)
        inherit = {"CI_JOB_PR_BODY": body, "CI_JOB_PR_BODY_FILE": inherited, "GITHUB_EVENT_PATH": event, "PR_BODY": body}
        for target in ("feat", self.head("feat")):
            with self.subTest(target=target), unittest.mock.patch.dict(os.environ, inherit):
                rc, out = self.lint_run("--lane-lint", target, head=self.head("feat"))  # asserts: one lint run, at this head
                self.assertEqual(rc, 0, out)
                got = self.lint_calls()[-1].get("pr_body")
                self.assertIsNotNone(got, "ci-job got no body file for a ref target: the empty body file is missing")
                self.assertEqual(got, "", "ci-job got a PR body for a ref target: %r" % (got,))

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

    def stacked_pr_on_release(self):
        """PR 7 is feat, based on release, not main. release moves one commit on after feat forked from it. -> (feat sha, release sha)."""
        self.push_release_branch()
        self.host.base = "release"
        o = self.other
        tm.sh(o, "git", "fetch", "-q", "origin")
        tm.sh(o, "git", "checkout", "-q", "-B", "release", "origin/release")
        tm.put(os.path.join(o, "release-moved.txt"), "release moved after feat forked\n")
        tm.sh(o, "git", "add", "-A")
        tm.sh(o, "git", "commit", "-q", "-m", "release moves on")
        tm.sh(o, "git", "push", "-q", "origin", "release")
        return self.head("feat"), tm.sh(o, "git", "rev-parse", "HEAD")

    def contains(self, head, base):
        """True when `base` is an ancestor of `head`. Read in the second clone, which made both commits, so the lane checkout
        is not fetched here: the lint must fetch its own base."""
        return subprocess.run(["git", "-C", self.other, "merge-base", "--is-ancestor", base, head], capture_output=True).returncode == 0

    def merge_release_into_feat(self):
        """The stacked head merges its base in and is pushed. -> the new head sha."""
        return self.merge_into_feat("origin/release")

    def shallow_lane_checkout(self, pin):
        """self.co becomes a shallow clone of origin with `pin` fetched at depth 1 (testing/shallow_clone.py, the one fixture).
        The host reads the same checkout, so its root moves with it."""
        self.co = os.path.join(self.t, "shallow")
        error = shallow_clone.make(self.bare, self.co, pin)
        if error:
            self.fail("the shallow clone could not be built: " + error)
        self.host.root = self.co

    def test_a_stacked_pr_whose_head_lacks_its_bases_head_fails_and_names_the_base_its_missing_sha_and_the_merge_commit_remedy(self):
        """The incident: a stacked pull request that lacked its base's head conflicted at merge. The lint passes here, so the
        refusal comes from the stack check alone."""
        feat, release = self.stacked_pr_on_release()
        self.assertFalse(self.contains(feat, release), "precondition: the head already holds the base's head, so the case probes nothing")
        self.use_ci_job(PASSING, 0)
        before = self.refs()
        rc, out = self.run_lane("--lane-lint", "7")
        self.assertEqual(rc, 1, "a stacked PR whose head lacks its base's head did not refuse: " + out)
        self.assertEqual(self.lint_calls(), [], "the ci-job lint ran before the stack check refused: " + out)
        self.assertEqual(pass_lines(out), [], "a stacked PR whose head lacks its base's head printed a PASS line: " + out)
        self.assertIn("release", out, "the refusal does not name the base branch: " + out)
        self.assertIn(release[:7], out, "the refusal does not name the base's missing sha: " + out)
        self.assertRegex(out, r"(?i)merge commit", "the refusal lacks the merge-commit remedy: " + out)
        self.assertEqual(self.refs(), before, "a refused lane pushed a ref")
        self.assertEqual(self.worktrees(), 1, "a refused lane left a worktree behind")

    def test_a_stacked_pr_whose_head_merged_its_base_in_passes_with_the_one_pass_line(self):
        _, release = self.stacked_pr_on_release()
        head = self.merge_release_into_feat()
        self.assertTrue(self.contains(head, release), "precondition: the merge did not bring the base's head into the head")
        self.use_ci_job(PASSING, 0)
        rc, out = self.lint_run("--lane-lint", "7", base="release", head=head)
        self.assertEqual(rc, 0, out)
        lines = pass_lines(out)
        self.assertEqual(len(lines), 1, out)
        self.assertIn(head[:7], lines[0], out)

    def test_a_pr_on_main_whose_head_lacks_mains_head_gets_no_stack_row_and_still_passes(self):
        """Main moving is not this check's job: a PR based on main gets no stack row."""
        self.main_moves()
        new_main = tm.sh(self.other, "git", "rev-parse", "HEAD")
        self.assertFalse(self.contains(self.head("feat"), new_main), "precondition: the head already holds main's head, so the case probes nothing")
        self.use_ci_job(PASSING, 0)
        rc, out = self.lint_run("--lane-lint", "7")
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(pass_lines(out)), 1, out)
        self.assertNotIn(new_main[:7], out, "a PR on main got a stack row that names main's head: " + out)

    def test_the_stack_refusal_is_a_fail_that_no_unknown_ok_reason_lifts(self):
        feat, release = self.stacked_pr_on_release()
        self.assertFalse(self.contains(feat, release), "precondition: the head already holds the base's head, so the case probes nothing")
        self.use_ci_job(UNKNOWN, 2)
        before = self.refs()
        rc, out = self.run_lane("--lane-lint", "7", "--lint-unknown-ok", "shellcheck is not on this box")
        self.assertEqual(rc, 1, "--lint-unknown-ok lifted the stacked PR's refusal: " + out)
        self.assertEqual(pass_lines(out), [], "the stacked PR's refusal printed a PASS line: " + out)
        self.assertRegex(out, r"FAIL", "the stacked PR's refusal does not read as a FAIL: " + out)
        self.assertIn(release[:7], out, "the stacked PR's refusal does not name the base's missing sha: " + out)
        rc, out = self.run_lane("--lane-lint", "7")
        self.assertEqual(rc, 1, "the stacked PR passed without a reason: " + out)
        self.assertRegex(out, r"FAIL", "the stacked PR's refusal without a reason does not read as a FAIL: " + out)
        self.assertIn(release[:7], out, "the stacked PR's refusal without a reason does not name the base's missing sha: " + out)
        self.assertEqual(self.refs(), before, "a refused lane pushed a ref")

    def test_an_unreadable_stack_read_stops_as_unknown_and_no_unknown_ok_reason_lifts_it(self):
        """git could not tell whether the head holds the base's head (merge.ancestor reads None). The stop is unknown: never a FAIL,
        never a PASS, and --lint-unknown-ok does not lift it. The lint does not run."""
        self.stacked_pr_on_release()
        self.use_ci_job(PASSING, 0)
        before = self.refs()
        with unittest.mock.patch.object(merge, "ancestor", return_value=None) as seam:
            rc, out = self.run_lane("--lane-lint", "7", "--lint-unknown-ok", "shellcheck is not on this box")
        self.assertTrue(seam.called, "the stack read did not run, so the case probes nothing")
        self.assertEqual(rc, 1, "--lint-unknown-ok lifted an unreadable stack read: " + out)
        self.assertEqual(pass_lines(out), [], "an unreadable stack read printed a PASS line: " + out)
        self.assertNotRegex(out, r"FAIL", "an unreadable stack read reads as a FAIL: " + out)
        self.assertRegex(out, r"stack check of .* is unknown", "an unreadable stack read does not stop as unknown: " + out)
        self.assertEqual(self.lint_calls(), [], "the lint ran past an unreadable stack read: " + out)
        with unittest.mock.patch.object(merge, "ancestor", return_value=None) as seam:
            rc, out = self.run_lane("--lane-lint", "7")
        self.assertTrue(seam.called, "the stack read did not run on the run without a reason")
        self.assertEqual(rc, 1, "an unreadable stack read passed without a reason: " + out)
        self.assertEqual(pass_lines(out), [], "an unreadable stack read printed a PASS line without a reason: " + out)
        self.assertNotRegex(out, r"FAIL", "an unreadable stack read reads as a FAIL without a reason: " + out)
        self.assertRegex(out, r"stack check of .* is unknown", "an unreadable stack read does not stop as unknown without a reason: " + out)
        self.assertEqual(self.lint_calls(), [], "the lint ran past an unreadable stack read without a reason: " + out)
        self.assertEqual(self.refs(), before, "a refused lane pushed a ref")

    def test_the_stack_refusal_claims_no_conflict_and_no_base_move(self):
        """The head may merge clean, and the lane may never have been based on its base, so the refusal says what is missing and no more."""
        feat, release = self.stacked_pr_on_release()
        self.assertFalse(self.contains(feat, release), "precondition: the head already holds the base's head, so the case probes nothing")
        self.use_ci_job(PASSING, 0)
        rc, out = self.run_lane("--lane-lint", "7")
        self.assertEqual(rc, 1, "a stacked PR whose head lacks its base's head did not refuse: " + out)
        self.assertNotRegex(out, r"(?i)conflict|moved on", "the stack refusal claims a conflict or a base move the lint cannot see: " + out)

    def test_a_shallow_lane_whose_stacked_head_lacks_its_bases_head_fails_and_names_the_base_its_missing_sha_and_the_merge_commit_remedy(self):
        """A shallow clone cuts the path, so `merge-base --is-ancestor` exits 1 and branch_is_ancestor reads unknown. The head lacks the base's
        head in full history (checked on the other clone), so the refusal is a FAIL that names the base, its missing sha and the remedy."""
        feat, release = self.stacked_pr_on_release()
        self.assertFalse(self.contains(feat, release), "precondition: the head already holds the base's head, so the case probes nothing")
        self.shallow_lane_checkout(feat)
        tm.sh(self.co, "git", "fetch", "-q", "origin", "+refs/heads/release:refs/remotes/origin/release")
        facts = shallow_clone.facts(self.co, release, feat)
        self.assertTrue(facts["shallow"], "precondition: the lane checkout is not shallow: " + repr(facts))
        self.assertEqual(facts["ancestor_rc"], 1, "precondition: the cut does not make the read unknown, so the case probes nothing: " + repr(facts))
        self.use_ci_job(PASSING, 0)
        before = self.refs()
        rc, out = self.run_lane("--lane-lint", "7")
        self.assertEqual(rc, 1, "a shallow stacked PR whose head lacks its base's head did not refuse: " + out)
        self.assertEqual(pass_lines(out), [], "a shallow stacked PR whose head lacks its base's head printed a PASS line: " + out)
        self.assertRegex(out, r"FAIL", "a shallow stacked PR whose head lacks its base's head reads as unknown, not a FAIL: " + out)
        self.assertIn(release[:7], out, "the shallow FAIL does not name the base's missing sha: " + out)
        self.assertRegex(out, r"(?i)merge commit", "the shallow FAIL lacks the merge-commit remedy: " + out)
        self.assertEqual(self.refs(), before, "a refused lane pushed a ref")
        self.assertEqual(self.worktrees(), 1, "a refused lane left a worktree behind")

    def test_a_shallow_lane_whose_stacked_head_holds_its_bases_head_passes_at_depth_one(self):
        """The merge commit alone, in a depth-1 clone: its parents are cut, so the stack read must reach past the cut to see the base's
        head. On the current code it reads unknown here. A fix that maps every shallow unknown to a FAIL fails this case too."""
        _, release = self.stacked_pr_on_release()
        head = self.merge_release_into_feat()
        self.shallow_lane_checkout(head)
        tm.sh(self.co, "git", "fetch", "-q", "origin", "+refs/heads/release:refs/remotes/origin/release")
        facts = shallow_clone.facts(self.co, release, head)
        self.assertTrue(facts["shallow"], "precondition: the lane checkout is not shallow: " + repr(facts))
        self.assertTrue(facts["pin_present"], "precondition: the base's head is not in the clone: " + repr(facts))
        self.assertEqual(facts["ancestor_rc"], 1, "precondition: the cut does not hide the base's head, so the case probes nothing: " + repr(facts))
        self.assertTrue(self.contains(head, release), "precondition: the merge did not bring the base's head into the head")
        self.use_ci_job(PASSING, 0)
        rc, out = self.run_lane("--lane-lint", "7")
        self.assertEqual(rc, 0, "a shallow stacked head that holds its base's head reads as unknown, not a pass: " + out)
        self.assertEqual(len(pass_lines(out)), 1, "a shallow stacked head that holds its base's head printed no single PASS line: " + out)
        self.assertEqual(len(self.lint_calls()), 1, "the ci-job lint did not run once on the passing shallow head: " + out)

    def test_a_shallow_lane_whose_stacked_head_holds_its_bases_head_at_depth_two_passes(self):
        """The control beside the depth-1 case: with the merge commit's parents fetched, the path to the base's head is in the clone,
        so the read is an ancestor and the lint passes."""
        _, release = self.stacked_pr_on_release()
        head = self.merge_release_into_feat()
        self.shallow_lane_checkout(head)
        tm.sh(self.co, "git", "fetch", "-q", "--depth", "2", "origin", head)  # the merge commit's parents: the path to the base's head
        tm.sh(self.co, "git", "fetch", "-q", "origin", "+refs/heads/release:refs/remotes/origin/release")
        facts = shallow_clone.facts(self.co, release, head)
        self.assertTrue(facts["shallow"], "precondition: the lane checkout is not shallow: " + repr(facts))
        self.assertEqual(facts["ancestor_rc"], 0, "precondition: the path to the base's head is cut, so the control probes nothing: " + repr(facts))
        self.use_ci_job(PASSING, 0)
        rc, out = self.lint_run("--lane-lint", "7", base="release", head=head)
        self.assertEqual(rc, 0, out)
        lines = pass_lines(out)
        self.assertEqual(len(lines), 1, out)
        self.assertIn(head[:7], lines[0], out)

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


# The stack cross-measure (roadmap step stack-cross-measure): `merge --lane-lint <pr>` checks the PR's head against each other open PR of its
# lane, and against the PRs --with names, with `git merge-tree --write-tree`. The same lane is decided by one rule, in one helper pair
# (session_of, same_lane): the session URL line of the PR body.
OWN = "session_01OwnLaneSeven"  # the session that opened the lane's PR, PR 7
OTHER = "session_01OtherLaneSeven"  # another session's PR
SESSION_URL = "https://claude.ai/code/%s"  # the line a PR body carries for its session


def lane_body(session_id, text="Lane work."):
    """A PR body with its session's URL line, as a lane's PR carries it."""
    return "%s\n\n%s\n" % (text, SESSION_URL % session_id)


def session_of(body):
    """-> the session id a PR body names by its URL line, or None. The one home of the same-lane key: a rule change moves this and same_lane."""
    found = re.search(r"claude\.ai/code/(session_[A-Za-z0-9]+)", body or "")
    return found.group(1) if found else None


def same_lane(body, other):
    """True when two PR bodies name the same session. The cases use it for their preconditions; merge.py holds the rule."""
    mine = session_of(body)
    return mine is not None and mine == session_of(other)


def branch_of(n):
    """The branch a case pushes for PR n. Letters only, so no PR number shows up in a branch name."""
    return "lane-" + str(n).translate(str.maketrans("0123456789", "abcdefghij"))


INTEGRATION_NAME = "cross-measure"  # the batch the integration cases lint; its branch is merge.integration_branch(INTEGRATION_NAME)


def names_pr(text, number):
    """True when `text` names PR `number`, as #N or as a bare N. A hex run, such as a commit's sha, never counts."""
    return re.search(r"(?<![0-9a-f])#?%d(?![0-9a-f])" % number, text) is not None


def lane_lint_usage():
    """-> the `merge --lane-lint` entry of merge.py's usage text (its module docstring), from its first line to the next entry. None when absent."""
    lines = (merge.__doc__ or "").splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith("  merge --lane-lint")]
    if not starts:
        return None
    end = next((i for i in range(starts[0] + 1, len(lines)) if lines[i].startswith("  merge ")), len(lines))
    return "\n".join(lines[starts[0]:end])


class CrossMeasure(LaneFixture):
    """`merge --lane-lint <pr>` checks the PR's head against each other open PR of its lane and against the PRs --with names: one
    open-PR list read, then `git merge-tree --write-tree` against main for the head and for each checked PR, and one more against the
    head. A pair conflict FAILs before the ci-job run and names each conflicting PR and file; a pair that clashes only through main is
    a report line. A stack pair is skipped. The counts come from the fake host (FakeHost.pulls, pull_list_reads) and from
    the merge.sh call log (tree_calls)."""

    contains = LaneLint.contains  # the ancestor read the stack cases use: one home, LaneLint's

    def setUp(self):
        super().setUp()
        self.host.body = lane_body(OWN)
        self.host.pulls = {}
        self.tree_reply, self.tree_calls = None, []  # tree_reply: the (rc, text) every merge-tree call returns, when a case sets one
        self.tree_fault, self.tree_faulted = None, []  # tree_fault: (base ref, head sha, reply), set by fault_merge_tree; tree_faulted: the calls it answered
        real_sh = merge.sh

        def log_merge_tree(args, *rest, **kwargs):
            if "merge-tree" in args:
                self.tree_calls.append(list(args))
                if self.tree_reply is not None:
                    return self.tree_reply
                if self.tree_fault is not None and list(args[-2:]) == list(self.tree_fault[:2]):
                    self.tree_faulted.append(list(args))
                    return self.tree_fault[2]
            return real_sh(args, *rest, **kwargs)

        patch = unittest.mock.patch.object(merge, "sh", log_merge_tree)
        patch.start()
        self.addCleanup(patch.stop)

    def clash(self, a, b):
        """-> "clean" or "conflict": `git merge-tree --write-tree` of commits a and b, run in the second clone with no merge.py code, so a
        precondition does not depend on what it probes. Any other exit fails the case: the answer is unknown, not clean."""
        r = subprocess.run(["git", "-C", self.other, "merge-tree", "--write-tree", a, b], capture_output=True, text=True)
        if r.returncode == 0:
            return "clean"
        if r.returncode == 1 and "CONFLICT" in r.stdout:
            return "conflict"
        raise AssertionError("precondition: git merge-tree of %s and %s read neither clean nor conflict (exit %d): %s"
                             % (a, b, r.returncode, r.stdout + r.stderr))

    def second_parent(self, head):
        """-> the second parent of commit `head`, or None when it has fewer than two parents."""
        parts = tm.sh(self.other, "git", "rev-list", "--parents", "-n", "1", head).split()
        return parts[2] if len(parts) == 3 else None

    def fault_merge_tree(self, base_ref, head, reply):
        """The one `git merge-tree` of commit `head` against `base_ref` returns `reply` (rc, text). Every other merge-tree runs for real,
        so the case flips only the read it names. The calls it answered are in self.tree_faulted."""
        self.tree_fault = (base_ref, head, reply)

    def assert_conflict_line_names(self, text, base, what):
        """The refusal has a line that names a conflict or an unclean merge, and that line names `base`, the base the lint ran against."""
        lines = [line for line in text.splitlines() if re.search(r"(?i)conflict|not clean", line)]
        self.assertTrue(any(re.search(r"\b%s\b" % re.escape(base), line) for line in lines),
                        "%s: no conflict line names %s: %s" % (what, base, text))

    def commit_on(self, name, files, start):
        """Commit `files` ({path: text}) on branch `name`, cut from `start` in the second clone, and push it. -> the commit's sha."""
        o, sh = self.other, tm.sh
        sh(o, "git", "fetch", "-q", "origin")
        sh(o, "git", "checkout", "-q", "-B", name, start)
        for path, text in files.items():
            tm.put(os.path.join(o, path), text)
        sh(o, "git", "add", "-A")
        sh(o, "git", "commit", "-q", "-m", "%s: %s" % (name, ", ".join(sorted(files))))
        sh(o, "git", "push", "-q", "origin", name)
        return sh(o, "git", "rev-parse", "HEAD")

    def own_writes(self, files):
        """The lane's head gains a commit with `files`. -> its sha."""
        return self.commit_on("feat", files, "origin/feat")

    def listing(self, n, head, body, state="open", draft=False):
        """PR n on `head` with `body`, as the fake host's open-PR list and its PR read carry it. -> the head."""
        self.host.pulls[n] = tm.REST.list_item(n, head, branch_of(n), "main", body=body, draft=draft, state=state)
        return head

    def list_pr(self, n, head, body, state="open", draft=False):
        """PR n on the existing commit `head`: its branch is pushed, so the lane can fetch it, and then it is listed."""
        tm.sh(self.other, "git", "push", "-q", "origin", "%s:refs/heads/%s" % (head, branch_of(n)))
        return self.listing(n, head, body, state=state, draft=draft)

    def pr_writes(self, n, files, body, start="origin/main", state="open", draft=False):
        """PR n: a commit with `files`, cut from `start`, listed as PR n. -> its head sha."""
        head = self.commit_on(branch_of(n), files, start)
        return self.listing(n, head, body, state=state, draft=draft)

    def measured(self, *argv):
        """Run merge in the lane checkout, cloud off, with the counters reset. -> (rc, text, lint runs, PR-list reads, merge-tree calls).
        A refused flag reads as its rc and text (no argparse guard), so each case asserts the outcome, not the parser."""
        if os.path.exists(self.log):
            os.remove(self.log)
        self.host.pull_list_reads = 0
        self.tree_calls.clear()
        rc, out, err = self.run_main(*argv, CLAUDE_CODE_REMOTE=None)
        return rc, out + err, len(self.lint_calls()), self.host.pull_list_reads, len(self.tree_calls)

    def cost_lane(self):
        """The cost pins' lane. PR 8 is checked (same lane, disjoint). PR 9 is a stack pair, so it is skipped. PR 10 is another
        session's and conflicts, so it is read only when --with names it."""
        self.own_writes({"own-b.txt": "lane 7\n"})
        self.pr_writes(8, {"elsewhere.txt": "lane 8\n"}, lane_body(OWN))
        stacked = self.pr_writes(9, {"stack.txt": "stacked on this head\n"}, lane_body(OWN), start="origin/feat")
        self.assertTrue(self.contains(stacked, self.head("feat")), "precondition: PR 9 does not contain this head, so it is no stack pair")
        self.pr_writes(10, {"own-b.txt": "lane 10\n"}, lane_body(OTHER))

    def test_a_same_lane_pr_whose_head_conflicts_fails_and_names_its_number_and_file(self):
        self.own_writes({"shared-a.txt": "lane 7\n"})
        self.pr_writes(8, {"shared-a.txt": "lane 8\n"}, lane_body(OWN))
        self.assertTrue(same_lane(self.host.body, self.host.pulls[8]["body"]), "precondition: PR 8 is not in this lane, so the case probes nothing")
        self.use_ci_job(PASSING, 0)
        rc, text, _, _, _ = self.measured("--lane-lint", "7")
        self.assertEqual(rc, 1, "a same-lane PR whose head conflicts with this head did not refuse: " + text)
        self.assertTrue(names_pr(text, 8), "the refusal does not name the conflicting PR #8: " + text)
        self.assertIn("shared-a.txt", text, "the refusal does not name the conflicting file: " + text)
        self.assertRegex(text, r"FAIL", "the refusal does not read as a FAIL: " + text)
        self.assertEqual(pass_lines(text), [], "a conflicting same-lane PR printed a PASS line: " + text)
        self.assertRegex(text, r"(?i)again", "the refusal lacks its remedy: " + text)

    def test_two_conflicting_same_lane_prs_are_both_named_each_with_its_files(self):
        self.own_writes({"shared-a.txt": "lane 7\n", "shared-b.txt": "lane 7\n", "shared-c.txt": "lane 7\n", "shared-d.txt": "lane 7\n"})
        self.pr_writes(8, {"shared-a.txt": "lane 8\n", "shared-b.txt": "lane 8\n"}, lane_body(OWN))
        self.pr_writes(9, {"shared-c.txt": "lane 9\n", "shared-d.txt": "lane 9\n"}, lane_body(OWN))
        self.use_ci_job(PASSING, 0)
        rc, text, _, _, _ = self.measured("--lane-lint", "7")
        self.assertEqual(rc, 1, "two conflicting same-lane PRs did not refuse: " + text)
        for number, files in ((8, ("shared-a.txt", "shared-b.txt")), (9, ("shared-c.txt", "shared-d.txt"))):
            self.assertTrue(names_pr(text, number), "the refusal does not name conflicting PR #%d: %s" % (number, text))
            for name in files:
                self.assertIn(name, text, "the refusal does not name %s, a file of PR #%d: %s" % (name, number, text))

    def test_a_same_lane_pr_with_a_disjoint_change_passes_with_no_row(self):  # control
        self.own_writes({"own-only.txt": "lane 7\n"})
        self.pr_writes(8, {"elsewhere.txt": "lane 8\n"}, lane_body(OWN))
        self.assertTrue(same_lane(self.host.body, self.host.pulls[8]["body"]), "precondition: PR 8 is not in this lane, so the case probes nothing")
        self.use_ci_job(PASSING, 0)
        rc, text, lints, _, _ = self.measured("--lane-lint", "7")
        self.assertEqual(rc, 0, "a disjoint same-lane PR refused the lane: " + text)
        self.assertEqual(len(pass_lines(text)), 1, text)
        self.assertEqual(lints, 1, "the ci-job lint did not run once on the passing lane: " + text)
        self.assertFalse(names_pr(text, 8), "a disjoint same-lane PR got a row: " + text)

    def test_a_pr_of_another_session_is_not_read_as_this_lane_and_passes(self):  # control
        self.own_writes({"shared-a.txt": "lane 7\n"})
        self.pr_writes(8, {"shared-a.txt": "lane 8\n"}, lane_body(OTHER))
        self.assertFalse(same_lane(self.host.body, self.host.pulls[8]["body"]), "precondition: PR 8 is in this lane, so the case probes nothing")
        self.use_ci_job(PASSING, 0)
        rc, text, _, _, _ = self.measured("--lane-lint", "7")
        self.assertEqual(rc, 0, "a conflicting PR of another session refused this lane: " + text)
        self.assertEqual(len(pass_lines(text)), 1, text)
        self.assertFalse(names_pr(text, 8), "a PR of another session is named: " + text)

    def test_a_stack_pair_is_skipped_and_a_conflicting_pr_beside_it_still_fails(self):
        """The stack pair (PR 9 contains this head) is never merge-tree'd. PR 10 conflicts, so the run FAILs naming PR 10 only."""
        self.own_writes({"shared-a.txt": "lane 7\n"})
        stacked = self.pr_writes(9, {"stack.txt": "stacked on this head\n"}, lane_body(OWN), start="origin/feat")
        self.pr_writes(10, {"shared-a.txt": "lane 10\n"}, lane_body(OWN))
        self.assertTrue(self.contains(stacked, self.head("feat")), "precondition: PR 9 does not contain this head, so it is no stack pair")
        self.use_ci_job(PASSING, 0)
        rc, text, lints, _, trees = self.measured("--lane-lint", "7")
        self.assertEqual(rc, 1, "the conflicting PR beside a stack pair did not refuse: " + text)
        self.assertTrue(names_pr(text, 10), "the refusal does not name the conflicting PR #10: " + text)
        self.assertFalse(names_pr(text, 9), "the refusal names the stack pair PR #9, which is skipped: " + text)
        self.assertEqual(trees, 3, "git merge-tree ran %d times, want three (the head against main, then PR #10 against main and against the head): the stack pair was read" % trees)
        self.assertEqual(lints, 0, "the ci-job lint ran past the refusal: " + text)

    def test_a_stack_pair_whose_head_lies_behind_this_head_passes_and_reads_the_list_once(self):
        before = self.head("feat")
        self.own_writes({"own-b.txt": "lane 7\n"})
        behind = self.list_pr(9, before, lane_body(OWN))
        self.assertTrue(self.contains(self.head("feat"), behind), "precondition: this head does not contain PR 9's head, so it is no stack pair")
        self.use_ci_job(PASSING, 0)
        rc, text, _, reads, trees = self.measured("--lane-lint", "7")
        self.assertEqual(rc, 0, "a stack pair whose head lies behind this one refused the lane: " + text)
        self.assertEqual(len(pass_lines(text)), 1, text)
        self.assertEqual(reads, 1, "the open PRs were read %d times, want once" % reads)
        self.assertEqual(trees, 1, "git merge-tree ran %d times for a stack pair, want one: the head against main, and none for the pair" % trees)

    def test_with_names_a_pr_of_another_session_and_its_conflict_fails(self):
        self.own_writes({"shared-a.txt": "lane 7\n"})
        self.pr_writes(9, {"shared-a.txt": "lane 9\n"}, lane_body(OTHER))
        self.assertFalse(same_lane(self.host.body, self.host.pulls[9]["body"]), "precondition: PR 9 is in this lane, so --with probes nothing")
        self.use_ci_job(PASSING, 0)
        rc, text, _, _, _ = self.measured("--lane-lint", "7")  # control: without --with, another session's PR is not read
        self.assertEqual(rc, 0, "a PR of another session, not named by --with, refused the lane: " + text)
        rc, text, lints, _, _ = self.measured("--lane-lint", "7", "--with", "9")
        self.assertEqual(rc, 1, "--with 9 did not refuse a conflicting PR of another session: " + text)
        self.assertTrue(names_pr(text, 9), "the refusal does not name the --with PR #9: " + text)
        self.assertIn("shared-a.txt", text, "the refusal does not name the conflicting file: " + text)
        self.assertEqual(lints, 0, "the ci-job lint ran past the --with refusal: " + text)

    def test_with_names_a_pr_that_does_not_exist_and_stops_unknown(self):
        self.use_ci_job(PASSING, 0)
        rc, text, lints, _, _ = self.measured("--lane-lint", "7", "--with", "99")
        self.assertEqual(rc, 1, "--with 99, a PR that does not exist, did not stop: " + text)
        self.assertTrue(names_pr(text, 99), "the stop does not name PR #99: " + text)
        self.assertRegex(text, r"(?i)unknown|not found|does not exist|no such|404", "the stop does not say it could not read PR #99: " + text)
        self.assertEqual(pass_lines(text), [], "--with of a missing PR printed a PASS line: " + text)
        self.assertEqual(lints, 0, "the ci-job lint ran past the stop: " + text)

    def test_with_names_a_closed_pr_and_stops_unknown(self):
        self.own_writes({"shared-a.txt": "lane 7\n"})
        self.pr_writes(9, {"shared-a.txt": "lane 9\n"}, lane_body(OTHER), state="closed")
        self.use_ci_job(PASSING, 0)
        rc, text, lints, _, _ = self.measured("--lane-lint", "7", "--with", "9")
        self.assertEqual(rc, 1, "--with 9, a closed PR, did not stop: " + text)
        self.assertTrue(names_pr(text, 9), "the stop does not name the closed PR #9: " + text)
        self.assertEqual(pass_lines(text), [], "--with of a closed PR printed a PASS line: " + text)
        self.assertEqual(lints, 0, "the ci-job lint ran past the stop: " + text)

    def test_a_with_list_reads_each_named_pr(self):
        self.own_writes({"shared-a.txt": "lane 7\n", "shared-b.txt": "lane 7\n"})
        self.pr_writes(11, {"shared-a.txt": "lane 11\n"}, lane_body(OTHER))
        self.pr_writes(12, {"shared-b.txt": "lane 12\n"}, lane_body(OTHER))
        self.use_ci_job(PASSING, 0)
        rc, text, lints, reads, trees = self.measured("--lane-lint", "7", "--with", "11,12")
        self.assertEqual(rc, 1, "--with 11,12 did not refuse the conflicts of both named PRs: " + text)
        self.assertTrue(names_pr(text, 11), "the refusal does not name the --with PR #11: " + text)
        self.assertTrue(names_pr(text, 12), "the refusal does not name the --with PR #12: " + text)
        self.assertEqual(trees, 5, "git merge-tree ran %d times for --with 11,12, want five: the head against main, then PRs #11 and #12 against main and against the head" % trees)
        self.assertEqual(reads, 1, "the open PRs were read %d times, want once" % reads)
        self.assertEqual(lints, 0, "the ci-job lint ran past the --with refusal: " + text)

    def test_a_with_list_with_a_blank_or_non_digit_item_stops_at_parse_and_never_passes(self):
        """The list is parsed before any PR is read: a blank or non-digit item is a Stop, so no PR is read, no merge-tree runs and no lint runs."""
        self.pr_writes(11, {"elsewhere.txt": "lane 11\n"}, lane_body(OTHER))  # a real PR, so a lenient parse would read it and could pass
        self.use_ci_job(PASSING, 0)
        for value in ("", " ", "11,", "11,,12", "11,x"):
            with self.subTest(value=value):
                rc, text, lints, reads, trees = self.measured("--lane-lint", "7", "--with", value)
                self.assertEqual(rc, 1, "--with %r did not stop at parse: %s" % (value, text))
                self.assertEqual(pass_lines(text), [], "--with %r printed a PASS line: %s" % (value, text))
                self.assertEqual(reads, 0, "--with %r read the open PRs before the parse refused it" % value)
                self.assertEqual(trees, 0, "--with %r ran git merge-tree before the parse refused it" % value)
                self.assertEqual(lints, 0, "--with %r ran the ci-job lint: %s" % (value, text))

    def test_a_with_list_that_repeats_a_number_reads_that_pr_once(self):
        self.own_writes({"shared-a.txt": "lane 7\n"})
        self.pr_writes(11, {"shared-a.txt": "lane 11\n"}, lane_body(OTHER))
        self.use_ci_job(PASSING, 0)
        rc, text, lints, reads, trees = self.measured("--lane-lint", "7", "--with", "11,11")
        self.assertEqual(rc, 1, "--with 11,11 did not refuse the conflict of PR #11: " + text)
        self.assertTrue(names_pr(text, 11), "the refusal does not name the --with PR #11: " + text)
        self.assertEqual(trees, 3, "git merge-tree ran %d times for --with 11,11, want three: the head against main, then PR #11 against main and against the head, once" % trees)
        self.assertEqual(reads, 1, "the open PRs were read %d times, want once" % reads)
        self.assertEqual(lints, 0, "the ci-job lint ran past the --with refusal: " + text)

    def test_a_closed_same_lane_pr_is_skipped_and_an_open_one_beside_it_fails(self):
        self.own_writes({"shared-a.txt": "lane 7\n"})
        self.pr_writes(8, {"shared-a.txt": "lane 8\n"}, lane_body(OWN), state="closed")
        self.pr_writes(9, {"shared-a.txt": "lane 9\n"}, lane_body(OWN))
        self.use_ci_job(PASSING, 0)
        rc, text, _, _, _ = self.measured("--lane-lint", "7")
        self.assertEqual(rc, 1, "the open same-lane PR beside a closed one did not refuse: " + text)
        self.assertTrue(names_pr(text, 9), "the refusal does not name the open PR #9: " + text)
        self.assertFalse(names_pr(text, 8), "the refusal names the closed PR #8, which is skipped: " + text)

    def test_a_draft_same_lane_pr_is_still_open_and_its_conflict_fails(self):
        """A draft is an open PR, so the lane's list read counts it. A closed PR beside it is skipped (the case above)."""
        self.own_writes({"shared-a.txt": "lane 7\n"})
        self.pr_writes(8, {"shared-a.txt": "lane 8\n"}, lane_body(OWN), draft=True)
        self.use_ci_job(PASSING, 0)
        rc, text, _, _, _ = self.measured("--lane-lint", "7")
        self.assertEqual(rc, 1, "a conflicting draft of this lane did not refuse: " + text)
        self.assertTrue(names_pr(text, 8), "the refusal does not name the draft PR #8: " + text)

    def test_an_unreadable_merge_tree_stops_unknown_and_no_unknown_ok_reason_lifts_it(self):
        self.pr_writes(8, {"elsewhere.txt": "lane 8\n"}, lane_body(OWN))
        self.tree_reply = (128, "fatal: merge-tree could not read the trees")  # exit 128: neither clean (0) nor conflict (1)
        self.use_ci_job(PASSING, 0)
        rc, text, lints, _, trees = self.measured("--lane-lint", "7")
        self.assertGreater(trees, 0, "git merge-tree was not run, so the case probes nothing")
        self.assertEqual(rc, 1, "an unreadable merge-tree passed the lane: " + text)
        self.assertEqual(pass_lines(text), [], "an unreadable merge-tree printed a PASS line: " + text)
        self.assertRegex(text, r"(?i)unknown", "an unreadable merge-tree does not stop as unknown: " + text)
        self.assertEqual(lints, 0, "the ci-job lint ran past an unreadable merge-tree: " + text)
        rc, text, lints, _, _ = self.measured("--lane-lint", "7", "--lint-unknown-ok", "shellcheck is not on this box")
        self.assertEqual(rc, 1, "--lint-unknown-ok lifted an unreadable merge-tree: " + text)
        self.assertEqual(pass_lines(text), [], "--lint-unknown-ok printed a PASS line for an unreadable merge-tree: " + text)
        self.assertRegex(text, r"(?i)unknown", "--lint-unknown-ok does not leave the unknown stop: " + text)
        self.assertEqual(lints, 0, "the ci-job lint ran past an unreadable merge-tree with a reason: " + text)

    def test_a_conflict_fail_is_never_lifted_by_an_unknown_ok_reason(self):
        self.own_writes({"shared-a.txt": "lane 7\n"})
        self.pr_writes(8, {"shared-a.txt": "lane 8\n"}, lane_body(OWN))
        self.use_ci_job(PASSING, 0)
        rc, text, lints, _, _ = self.measured("--lane-lint", "7", "--lint-unknown-ok", "shellcheck is not on this box")
        self.assertEqual(rc, 1, "--lint-unknown-ok lifted a conflict FAIL: " + text)
        self.assertTrue(names_pr(text, 8), "the refusal does not name conflicting PR #8: " + text)
        self.assertEqual(pass_lines(text), [], "a conflict FAIL printed a PASS line: " + text)
        self.assertEqual(lints, 0, "the ci-job lint ran past a conflict FAIL: " + text)

    def test_with_no_other_open_pr_the_run_reads_the_list_once_and_merge_tree_only_for_the_head(self):  # the empty state
        self.use_ci_job(PASSING, 0)
        rc, text, _, reads, trees = self.measured("--lane-lint", "7")
        self.assertEqual(rc, 0, text)
        self.assertEqual(len(pass_lines(text)), 1, text)
        self.assertEqual(reads, 1, "the open PRs were read %d times with no other PR, want once" % reads)
        self.assertEqual(trees, 1, "git merge-tree ran %d times with no other PR, want one: the head against main" % trees)

    def test_the_cost_is_one_list_read_and_two_merge_trees_for_each_checked_pr_plus_one_for_the_head(self):
        self.cost_lane()
        self.use_ci_job(PASSING, 0)
        rc, text, _, reads, trees = self.measured("--lane-lint", "7")
        self.assertEqual(rc, 0, "the cost lane refused, so a PR that is not checked was read: " + text)
        self.assertEqual(reads, 1, "the open PRs were read %d times, want once" % reads)
        self.assertEqual(trees, 3, "git merge-tree ran %d times, want three (the head against main, then PR #8 against main and against the head): the stack pair or another session's PR was read" % trees)

    def test_with_adds_two_merge_trees_for_each_named_pr(self):
        self.cost_lane()
        self.use_ci_job(PASSING, 0)
        rc, text, lints, reads, trees = self.measured("--lane-lint", "7", "--with", "10")
        self.assertEqual(rc, 1, "--with 10 did not refuse PR #10's conflict: " + text)
        self.assertTrue(names_pr(text, 10), "the refusal does not name the --with PR #10: " + text)
        self.assertFalse(names_pr(text, 8), "the refusal names PR #8, which does not conflict: " + text)
        self.assertEqual(reads, 1, "the open PRs were read %d times, want once" % reads)
        self.assertEqual(trees, 5, "git merge-tree ran %d times with --with 10, want five (the head against main, then PR #8 and PR #10 against main and against the head)" % trees)

    def test_the_usage_text_names_the_cost_of_the_cross_measure(self):
        block = lane_lint_usage()
        self.assertIsNotNone(block, "the usage text has no merge --lane-lint entry")
        self.assertRegex(block, r"merge-tree", "the lane-lint usage does not name git merge-tree as a cost: " + block)
        self.assertRegex(block, r"(?i)(PR|pull[ -]request)[ -]list", "the lane-lint usage does not name the PR-list read as a cost: " + block)
        self.assertRegex(block, r"(?i)(two|2) [^.]*merge-trees?[^.]*per other", "the lane-lint usage does not say two merge-trees run per other PR: " + block)
        self.assertRegex(block, r"(?i)merge-tree[^.]*against main", "the lane-lint usage does not say the head's merge-tree runs against main: " + block)

    def test_a_long_open_list_costs_one_list_read_and_merge_trees_only_for_the_lane(self):  # the full-size state
        self.own_writes({"shared-a.txt": "lane 7\n"})
        head = self.head("feat")
        for n in range(100, 219):  # 119 other sessions' open PRs: none is read
            self.listing(n, head, lane_body(OTHER))
        self.pr_writes(219, {"shared-a.txt": "lane 219\n"}, lane_body(OWN))
        self.use_ci_job(PASSING, 0)
        rc, text, _, reads, trees = self.measured("--lane-lint", "7")
        self.assertEqual(rc, 1, "the conflicting same-lane PR in a long list did not refuse: " + text)
        self.assertTrue(names_pr(text, 219), "the refusal does not name PR #219: " + text)
        self.assertFalse(names_pr(text, 150), "the refusal names another session's PR #150: " + text)
        self.assertEqual(reads, 1, "the open PRs were read %d times in a long list, want once" % reads)
        self.assertEqual(trees, 3, "git merge-tree ran %d times in a long list, want three (the head against main, then PR #219 against main and against the head)" % trees)

    def test_the_cross_measure_runs_before_the_ci_job_and_a_fail_never_runs_it(self):
        self.own_writes({"shared-a.txt": "lane 7\n"})
        self.pr_writes(8, {"shared-a.txt": "lane 8\n"}, lane_body(OWN))
        self.use_ci_job(PASSING, 0)  # the stub would pass, so only the cross-measure can stop the lint
        rc, text, lints, _, _ = self.measured("--lane-lint", "7")
        self.assertEqual(rc, 1, "a conflicting same-lane PR did not refuse: " + text)
        self.assertEqual(lints, 0, "the ci-job lint ran although the cross-measure refused: " + text)

    def test_the_usage_text_says_a_pr_under_another_session_id_is_missed_unless_with_names_it(self):
        block = lane_lint_usage()
        self.assertIsNotNone(block, "the usage text has no merge --lane-lint entry")
        self.assertRegex(block, r"(?i)another session[^.]*--with|--with[^.]*another session",
                         "the lane-lint usage does not say a PR posted under another session id is not found unless --with names it: " + block)


    def unfetched_pr(self, n, body):
        """PR n whose head is a commit only the second clone holds, as a fork's head is to origin: the lane cannot fetch it. -> its sha."""
        o = self.other
        tm.sh(o, "git", "fetch", "-q", "origin")
        tm.sh(o, "git", "checkout", "-q", "-B", "fork-only", "origin/main")
        tm.put(os.path.join(o, "fork-only.txt"), "not on origin\n")
        tm.sh(o, "git", "add", "-A")
        tm.sh(o, "git", "commit", "-q", "-m", "fork-only")
        return self.listing(n, tm.sh(o, "git", "rev-parse", "HEAD"), body)

    def assert_remedy_names_a_merge_or_a_rebase(self, text):
        """The conflict remedy holds for any base: it says to merge one head into the other, or to rebase one on the other."""
        self.assertRegex(text, r"(?i)merge[^.]*into the other", "the conflict remedy does not say to merge one head into the other: " + text)
        self.assertRegex(text, r"(?i)rebase[^.]*on the other", "the conflict remedy does not say to rebase one head on the other: " + text)

    def test_an_unreadable_head_of_a_compared_pr_stops_unknown_and_no_unknown_ok_reason_lifts_it(self):
        """A compared PR whose head cannot be read is a stop: skipping it would read as a pass."""
        self.own_writes({"own-b.txt": "lane 7\n"})
        self.unfetched_pr(8, lane_body(OWN))
        self.use_ci_job(PASSING, 0)
        rc, text, lints, _, _ = self.measured("--lane-lint", "7")
        self.assertEqual(rc, 1, "a compared PR whose head cannot be read passed the lane: " + text)
        self.assertEqual(pass_lines(text), [], "a compared PR whose head cannot be read printed a PASS line: " + text)
        self.assertRegex(text, r"(?i)unknown", "a compared PR whose head cannot be read does not stop as unknown: " + text)
        self.assertEqual(lints, 0, "the ci-job lint ran past an unreadable compared head: " + text)
        rc, text, lints, _, _ = self.measured("--lane-lint", "7", "--lint-unknown-ok", "shellcheck is not on this box")
        self.assertEqual(rc, 1, "--lint-unknown-ok lifted an unreadable compared head: " + text)
        self.assertEqual(pass_lines(text), [], "--lint-unknown-ok printed a PASS line for an unreadable compared head: " + text)
        self.assertEqual(lints, 0, "the ci-job lint ran past an unreadable compared head with a reason: " + text)

    def test_a_head_the_lane_cannot_fetch_stops_unknown_names_the_pr_and_never_says_run_again(self):
        self.own_writes({"own-b.txt": "lane 7\n"})
        self.unfetched_pr(8, lane_body(OWN))
        self.use_ci_job(PASSING, 0)
        rc, text, lints, _, _ = self.measured("--lane-lint", "7")
        self.assertEqual(rc, 1, "a head the lane cannot fetch did not stop: " + text)
        self.assertEqual(pass_lines(text), [], "a head the lane cannot fetch printed a PASS line: " + text)
        self.assertTrue(names_pr(text, 8), "the stop does not name the PR whose head could not be fetched: " + text)
        self.assertRegex(text, r"(?i)could not be fetched", "the stop does not say the head could not be fetched: " + text)
        self.assertNotRegex(text, r"(?i)run again", "the stop says to run again, which a head the lane cannot fetch does not clear: " + text)
        self.assertEqual(lints, 0, "the ci-job lint ran past a head the lane cannot fetch: " + text)

    def test_with_names_the_linted_pr_itself_and_stops_before_any_read(self):
        self.use_ci_job(PASSING, 0)
        rc, text, lints, reads, trees = self.measured("--lane-lint", "7", "--with", "7")
        self.assertEqual(rc, 1, "--with 7, the linted PR itself, did not stop: " + text)
        self.assertEqual(pass_lines(text), [], "--with 7 printed a PASS line: " + text)
        self.assertEqual(self.host.pr_calls, [], "--with 7 read a PR before the parse refused it: %r" % (self.host.pr_calls,))
        self.assertEqual(reads, 0, "--with 7 read the open PRs before the parse refused it: " + text)
        self.assertEqual(trees, 0, "--with 7 ran git merge-tree before the parse refused it: " + text)
        self.assertEqual(lints, 0, "--with 7 ran the ci-job lint: " + text)

    def test_the_usage_text_says_the_pr_list_read_still_runs_with_no_other_pr(self):
        block = lane_lint_usage()
        self.assertIsNotNone(block, "the usage text has no merge --lane-lint entry")
        self.assertRegex(block, r"(?i)list read[^.]*still runs[^.]*no other PR",
                         "the lane-lint usage does not say the PR-list read still runs when there is no other PR: " + block)

    def test_the_usage_text_says_the_origin_heads_fetch_covers_every_origin_branch(self):
        block = lane_lint_usage()
        self.assertIsNotNone(block, "the usage text has no merge --lane-lint entry")
        self.assertRegex(block, r"(?i)every origin branch", "the lane-lint usage does not say the origin-heads fetch covers every origin branch: " + block)

    def test_the_usage_text_says_a_shallow_clone_runs_fetch_unshallow_once(self):
        block = lane_lint_usage()
        self.assertIsNotNone(block, "the usage text has no merge --lane-lint entry")
        self.assertRegex(block, r"(?i)shallow[^.]*fetch --unshallow[^.]*once",
                         "the lane-lint usage does not say a shallow clone runs fetch --unshallow once: " + block)

    def test_the_conflict_remedy_names_a_merge_or_a_rebase_for_a_main_base_pr(self):
        self.own_writes({"shared-a.txt": "lane 7\n"})
        self.pr_writes(8, {"shared-a.txt": "lane 8\n"}, lane_body(OWN))
        self.use_ci_job(PASSING, 0)
        rc, text, _, _, _ = self.measured("--lane-lint", "7")
        self.assertEqual(rc, 1, "a conflicting same-lane PR did not refuse: " + text)
        self.assert_remedy_names_a_merge_or_a_rebase(text)

    def test_the_conflict_remedy_names_a_merge_or_a_rebase_for_a_release_base_pr(self):
        self.push_release_branch()  # release is main's tip, so the lane's head holds it and the stack check passes
        self.host.base = "release"
        self.own_writes({"shared-a.txt": "lane 7\n"})
        self.pr_writes(8, {"shared-a.txt": "lane 8\n"}, lane_body(OWN))
        self.use_ci_job(PASSING, 0)
        rc, text, _, _, _ = self.measured("--lane-lint", "7")
        self.assertEqual(rc, 1, "a conflicting same-lane PR under a release-base PR did not refuse: " + text)
        self.assert_remedy_names_a_merge_or_a_rebase(text)

    # The main-net cases (R1-R10, step cross-measure-main-net). A pair clash counts only when both heads merge clean with main; the
    # lane head itself is checked against its base; a counted FAIL refuses before the ci-job run, so the ci-job never runs beside it.

    def test_a_stale_sibling_that_clashes_only_through_main_passes_with_a_report_line_naming_it(self):  # R1: a sibling that clashes with main but not with the lane head is stale. The lane passes, and the report names the sibling.
        sib = self.pr_writes(8, {"shared-a.txt": "sibling\n"}, lane_body(OWN))  # cut before main moves
        self.commit_on("main", {"shared-a.txt": "main\n"}, "origin/main")  # main moves on the same path after the sibling was cut
        head = self.merge_into_feat("origin/main")  # the lane head merges main, so it holds main's change
        self.assertTrue(same_lane(self.host.body, self.host.pulls[8]["body"]), "precondition: PR 8 is not in this lane, so the case probes nothing")
        self.assertEqual(self.clash(sib, "origin/main"), "conflict", "precondition: PR 8 does not clash with main, so it is no stale sibling")
        self.assertEqual(self.clash(head, "origin/main"), "clean", "precondition: the lane head does not merge clean with main")
        self.assertEqual(self.clash(head, sib), "conflict", "precondition: the lane head and PR 8 do not clash, so the case probes nothing")
        self.use_ci_job(PASSING, 0)
        rc, text, _, _, _ = self.measured("--lane-lint", "7")
        self.assertEqual(rc, 0, "a stale sibling that clashes only through main refused the lane: " + text)
        self.assertEqual(len(pass_lines(text)), 1, "the lane did not print one PASS line: " + text)
        report = [line for line in text.splitlines() if names_pr(line, 8)]
        self.assertTrue(report, "the PASS names no report line for the stale sibling #8: " + text)
        self.assertNotIn("FAIL", "\n".join(report), "the report line for the stale sibling #8 reads as a FAIL: " + text)

    def test_two_siblings_that_are_each_clean_with_main_and_edit_the_same_lines_fail(self):  # R2, the green control of R1
        head = self.own_writes({"shared-a.txt": "lane 7\n"})
        sib = self.pr_writes(8, {"shared-a.txt": "lane 8\n"}, lane_body(OWN))
        self.assertTrue(same_lane(self.host.body, self.host.pulls[8]["body"]), "precondition: PR 8 is not in this lane, so the case probes nothing")
        self.assertEqual(self.clash(head, "origin/main"), "clean", "precondition: the lane head does not merge clean with main")
        self.assertEqual(self.clash(sib, "origin/main"), "clean", "precondition: PR 8 does not merge clean with main, so it is not the pair R2 names")
        self.assertEqual(self.clash(head, sib), "conflict", "precondition: the lane head and PR 8 do not clash, so the case probes nothing")
        self.use_ci_job(PASSING, 0)
        rc, text, _, _, _ = self.measured("--lane-lint", "7")
        self.assertEqual(rc, 1, "two siblings, each clean with main, that edit the same lines did not refuse: " + text)
        self.assertTrue(names_pr(text, 8), "the refusal does not name PR #8: " + text)
        self.assertIn("shared-a.txt", text, "the refusal does not name the shared file: " + text)
        self.assertEqual(pass_lines(text), [], "the refusal printed a PASS line: " + text)

    def test_a_head_that_conflicts_with_main_with_no_sibling_fails_names_main_and_posts_nothing(self):  # R3
        self.commit_on("main", {"shared-a.txt": "main\n"}, "origin/main")
        head = self.own_writes({"shared-a.txt": "lane 7\n"})
        self.assertEqual(self.clash(head, "origin/main"), "conflict", "precondition: the head merges clean with main, so the case probes nothing")
        self.assertEqual(self.host.pulls, {}, "precondition: another PR is listed, so the case has a sibling")
        self.use_ci_job(PASSING, 0)
        rc, text, _, _, _ = self.measured("--lane-lint", "7")
        self.assertEqual(rc, 1, "a head that conflicts with main passed the lane: " + text)
        self.assert_conflict_line_names(text, "main", "the refusal")
        self.assertEqual(pass_lines(text), [], "a head that conflicts with main printed a PASS line: " + text)
        self.assertEqual(self.host.posted, [], "a head that conflicts with main posted a lane-lint comment: " + text)

    def test_a_counted_clash_exits_fail_and_the_ci_job_never_runs_beside_it(self):  # R4
        head = self.own_writes({"shared-a.txt": "lane 7\n"})
        sib = self.pr_writes(8, {"shared-a.txt": "lane 8\n"}, lane_body(OWN))
        self.assertTrue(same_lane(self.host.body, self.host.pulls[8]["body"]), "precondition: PR 8 is not in this lane, so the case probes nothing")
        self.assertEqual(self.clash(head, "origin/main"), "clean", "precondition: the lane head does not merge clean with main")
        self.assertEqual(self.clash(sib, "origin/main"), "clean", "precondition: PR 8 does not merge clean with main, so the clash is not counted")
        self.assertEqual(self.clash(head, sib), "conflict", "precondition: the lane head and PR 8 do not clash, so the case probes nothing")
        self.use_ci_job(FAILING, 1)  # the stub would FAIL, so its line shows in the refusal if it ran
        rc, text, lints, _, _ = self.measured("--lane-lint", "7")
        self.assertEqual(rc, 1, "a counted clash beside a FAILING ci-job did not refuse: " + text)
        self.assertTrue(names_pr(text, 8), "the refusal does not name the clashing PR #8: " + text)
        self.assertIn("shared-a.txt", text, "the refusal does not name the clashing file: " + text)
        self.assertEqual(lints, 0, "the ci-job lint ran beside a counted clash: " + text)
        self.assertNotIn("comment narration", text, "the ci-job FAIL line is in the refusal beside a counted clash: " + text)

    def test_a_counted_clash_beside_a_passing_ci_job_still_refuses_and_no_unknown_reason_lifts_it(self):  # R5
        head = self.own_writes({"shared-a.txt": "lane 7\n"})
        sib = self.pr_writes(8, {"shared-a.txt": "lane 8\n"}, lane_body(OWN))
        self.assertTrue(same_lane(self.host.body, self.host.pulls[8]["body"]), "precondition: PR 8 is not in this lane, so the case probes nothing")
        self.assertEqual(self.clash(head, sib), "conflict", "precondition: the lane head and PR 8 do not clash, so the case probes nothing")
        self.assertEqual(self.clash(sib, "origin/main"), "clean", "precondition: PR 8 does not merge clean with main, so the clash is not counted")
        self.use_ci_job(PASSING, 0)  # the stub would pass, so only the counted clash can refuse
        rc, text, lints, _, _ = self.measured("--lane-lint", "7")
        self.assertEqual(rc, 1, "a counted clash beside a PASSING ci-job did not refuse: " + text)
        self.assertEqual(lints, 0, "the ci-job lint ran beside a counted clash: " + text)
        self.assertEqual(pass_lines(text), [], "a counted clash beside a PASSING ci-job printed a PASS line: " + text)
        self.assertEqual(self.host.posted, [], "a counted clash posted a lane-lint comment: " + text)
        with unittest.mock.patch.object(merge, "CI_JOB", self.write_stub(UNKNOWN, 2)):  # an unknown ci-job, which --lint-unknown-ok may lift
            rc, text, lints, _, _ = self.measured("--lane-lint", "7", "--lint-unknown-ok", "shellcheck is not on this box")
        self.assertEqual(rc, 1, "--lint-unknown-ok lifted a counted clash beside an unknown ci-job: " + text)
        self.assertEqual(lints, 0, "the unknown ci-job ran beside a counted clash: " + text)
        self.assertEqual(pass_lines(text), [], "--lint-unknown-ok printed a PASS line beside a counted clash: " + text)
        self.assertEqual(self.host.posted, [], "a counted clash beside an unknown ci-job posted a lane-lint comment: " + text)

    def test_an_integration_head_with_an_outside_pr_that_clashes_fails_names_it_and_runs_no_ci_job(self):  # R6
        self.own_writes({"shared-a.txt": "lane 7\n"})
        tip = self.pr_writes(8, {"lane-eight.txt": "lane 8\n"}, lane_body(OTHER))  # a lane tip: another session's open PR
        head = self.merge_into_feat("origin/" + branch_of(8))  # the integration head: PR 8's head is a merge's second parent
        outside = self.pr_writes(9, {"shared-a.txt": "outside\n"}, lane_body(OTHER))  # clean with main, clashes with the head
        self.assertEqual(self.second_parent(head), tip, "precondition: PR 8's head is not a parent of the head, so the head is no integration head")
        self.assertFalse(same_lane(self.host.body, self.host.pulls[9]["body"]), "precondition: PR 9 is in this lane, so it is read without --with")
        self.assertEqual(self.clash(outside, "origin/main"), "clean", "precondition: PR 9 does not merge clean with main")
        self.assertEqual(self.clash(head, "origin/main"), "clean", "precondition: the integration head does not merge clean with main")
        self.assertEqual(self.clash(head, outside), "conflict", "precondition: the integration head and PR 9 do not clash, so the case probes nothing")
        self.use_ci_job(PASSING, 0)
        rc, text, lints, _, _ = self.measured("--lane-lint", "7", "--with", "9")
        self.assertEqual(rc, 1, "an outside PR that clashes with an integration head passed the lane: " + text)
        self.assertTrue(names_pr(text, 9), "the refusal does not name the clashing PR #9: " + text)
        self.assertIn("shared-a.txt", text, "the refusal does not name the clashing file: " + text)
        self.assertEqual(pass_lines(text), [], "the refusal printed a PASS line: " + text)
        self.assertEqual(lints, 0, "the ci-job lint ran beside a counted clash: " + text)
        self.assertEqual(self.host.posted, [], "the refusal posted a lane-lint comment: " + text)

    def test_an_integration_head_that_conflicts_with_main_fails_and_names_main(self):  # R7, an integration head
        self.pr_writes(8, {"lane-eight.txt": "lane 8\n"}, lane_body(OTHER))  # cut before main moves, so it holds no shared-a.txt
        self.commit_on("main", {"shared-a.txt": "main\n"}, "origin/main")
        self.own_writes({"shared-a.txt": "lane 7\n"})
        head = self.merge_into_feat("origin/" + branch_of(8))
        self.assertEqual(self.second_parent(head), self.host.pulls[8]["head"]["sha"], "precondition: PR 8's head is not a parent of the head, so the head is no integration head")
        self.assertEqual(self.clash(head, "origin/main"), "conflict", "precondition: the integration head merges clean with main, so the case probes nothing")
        self.use_ci_job(PASSING, 0)
        rc, text, _, _, _ = self.measured("--lane-lint", "7")
        self.assertEqual(rc, 1, "an integration head that conflicts with main passed the lane: " + text)
        self.assert_conflict_line_names(text, "main", "the refusal")
        self.assertEqual(pass_lines(text), [], "an integration head that conflicts with main printed a PASS line: " + text)
        self.assertEqual(self.host.posted, [], "an integration head that conflicts with main posted a lane-lint comment: " + text)

    def test_a_ref_target_that_conflicts_with_main_fails_and_names_main(self):  # R7, a ref target
        self.commit_on("main", {"shared-a.txt": "main\n"}, "origin/main")
        sha = self.own_writes({"shared-a.txt": "lane 7\n"})
        self.assertEqual(self.clash(sha, "origin/main"), "conflict", "precondition: the ref target merges clean with main, so the case probes nothing")
        self.use_ci_job(PASSING, 0)
        rc, text, _, _, _ = self.measured("--lane-lint", sha)
        self.assertEqual(rc, 1, "a ref target that conflicts with main passed the lane: " + text)
        self.assert_conflict_line_names(text, "main", "the refusal")
        self.assertEqual(pass_lines(text), [], "a ref target that conflicts with main printed a PASS line: " + text)

    def test_a_head_whose_base_read_is_unknown_with_no_sibling_stops_unknown_before_the_ci_job(self):  # R8, the lane head's own base read
        head = self.own_writes({"own-a.txt": "lane 7\n"})
        self.assertEqual(self.host.pulls, {}, "precondition: another PR is listed, so the case has a sibling")
        self.assertEqual(self.clash(head, "origin/main"), "clean", "precondition: the head does not merge clean with main, so its read would not come from the fault alone")
        self.fault_merge_tree("refs/remotes/origin/main", head, (128, "fatal: merge-tree could not read the trees"))  # exit 128: neither clean (0) nor conflict (1)
        self.use_ci_job(PASSING, 0)
        rc, text, lints, _, _ = self.measured("--lane-lint", "7")
        self.assertTrue(self.tree_faulted, "scope: the head's merge-tree against origin/main was not read, so the fault probes nothing")
        self.assertEqual({tuple(c[-2:]) for c in self.tree_faulted}, {("refs/remotes/origin/main", head)},
                         "scope: the fault answered a merge-tree that is not the head against origin/main")
        self.assertEqual(rc, 1, "an unreadable base read of the head passed the lane: " + text)
        self.assertEqual(pass_lines(text), [], "an unreadable base read of the head printed a PASS line: " + text)
        self.assertRegex(text, r"(?i)unknown", "an unreadable base read of the head does not stop as unknown: " + text)
        self.assertEqual(lints, 0, "the ci-job lint ran past an unreadable base read of the head: " + text)

    def test_a_sibling_whose_base_read_is_unknown_beside_a_clash_stops_unknown_before_the_ci_job(self):  # R9, the other head's base read
        head = self.own_writes({"shared-a.txt": "lane 7\n"})
        sib = self.pr_writes(8, {"shared-a.txt": "lane 8\n"}, lane_body(OWN))
        self.assertTrue(same_lane(self.host.body, self.host.pulls[8]["body"]), "precondition: PR 8 is not in this lane, so the case probes nothing")
        self.assertEqual(self.clash(head, "origin/main"), "clean", "precondition: the lane head does not merge clean with main")
        self.assertEqual(self.clash(sib, "origin/main"), "clean", "precondition: PR 8 does not merge clean with main, so its read would not come from the fault alone")
        self.assertEqual(self.clash(head, sib), "conflict", "precondition: the lane head and PR 8 do not clash, so the case probes nothing")
        self.fault_merge_tree("refs/remotes/origin/main", sib, (128, "fatal: merge-tree could not read the trees"))  # exit 128: neither clean (0) nor conflict (1)
        self.use_ci_job(PASSING, 0)
        rc, text, lints, _, _ = self.measured("--lane-lint", "7")
        self.assertTrue(self.tree_faulted, "scope: PR 8's merge-tree against origin/main was not read, so the fault probes nothing")
        self.assertEqual({tuple(c[-2:]) for c in self.tree_faulted}, {("refs/remotes/origin/main", sib)},
                         "scope: the fault answered a merge-tree that is not PR #8 against origin/main")
        self.assertTrue(any(c[-2:] == ["refs/remotes/origin/main", head] for c in self.tree_calls),
                        "scope: the lane head's merge-tree against origin/main did not run, so the case probes nothing")
        self.assertEqual(rc, 1, "PR #8's unreadable base read passed the lane beside a clash: " + text)
        self.assertRegex(text, r"(?i)unknown", "PR #8's unreadable base read does not stop as unknown: " + text)
        self.assertEqual(pass_lines(text), [], "PR #8's unreadable base read printed a PASS line: " + text)
        self.assertEqual(lints, 0, "the ci-job lint ran past PR #8's unreadable base read: " + text)
        self.assertEqual(self.host.posted, [], "PR #8's unreadable base read posted a lane-lint comment: " + text)

    def test_a_lane_head_that_merged_a_same_lane_sibling_fails_on_a_clash_with_a_third_same_lane_pr(self):  # R10, a head that merged a same-lane sibling
        self.own_writes({"shared-a.txt": "lane 7\n"})
        sib = self.pr_writes(8, {"lane-eight.txt": "lane 8\n"}, lane_body(OWN))  # PR 8: a same-lane sibling, cut from main, disjoint from the head
        head = self.merge_into_feat("origin/" + branch_of(8))  # the lane head merges PR 8, so PR 8's head is its second parent
        third = self.pr_writes(9, {"shared-a.txt": "lane 9\n"}, lane_body(OWN))  # PR 9: same lane, edits the lines the head edits
        self.assertEqual(self.second_parent(head), sib, "scope: PR 8's head is not a parent of the head, so the head merged no sibling")
        self.assertTrue(same_lane(self.host.body, self.host.pulls[8]["body"]), "precondition: PR 8 is not in this lane, so the case probes nothing")
        self.assertTrue(same_lane(self.host.body, self.host.pulls[9]["body"]), "precondition: PR 9 is not in this lane, so the case probes nothing")
        self.assertEqual(self.clash(head, "origin/main"), "clean", "precondition: the lane head does not merge clean with main")
        self.assertEqual(self.clash(third, "origin/main"), "clean", "precondition: PR 9 does not merge clean with main, so the clash is not the pair the case names")
        self.assertEqual(self.clash(head, third), "conflict", "precondition: the lane head and PR 9 do not clash, so the case probes nothing")
        self.use_ci_job(PASSING, 0)  # the stub would pass, so only the counted clash can refuse
        rc, text, lints, _, _ = self.measured("--lane-lint", "7")
        self.assertEqual(rc, 1, "a counted clash between the lane head and PR #9 passed the lane beside a merged sibling: " + text)
        self.assertTrue(names_pr(text, 9), "the refusal does not name the clashing PR #9: " + text)
        self.assertIn("shared-a.txt", text, "the refusal does not name the clashing file: " + text)
        self.assertEqual(pass_lines(text), [], "the refusal printed a PASS line: " + text)
        self.assertEqual(lints, 0, "the ci-job lint ran beside a counted clash: " + text)
        self.assertEqual(self.host.posted, [], "the refusal posted a lane-lint comment: " + text)

    # The batch integration PRs (the integration rule). PR 7 is a batch integration PR when its body holds a freeze block and its branch is
    # merge.integration_branch of that block's name. A clash of its head with a same-lane PR is a report line, not a FAIL; a base conflict stays a FAIL.

    def integration_body(self):
        """The body of PR 7 on INTEGRATION_NAME: its freeze block with one frozen lane, then the session line a lane PR carries, so PR #8
        reads as a same-lane PR (same_lane)."""
        base = tm.sh(self.other, "git", "rev-parse", "origin/main")
        return lane_body(OWN, "\n".join(merge.freeze_lines(INTEGRATION_NAME, {6: base})))

    def assert_integration_scope(self):
        """Precondition: PR 7's body holds a freeze block for INTEGRATION_NAME, and PR 7 is on that batch's integration branch."""
        block = merge.parse_freeze(self.host.body)
        self.assertIsNotNone(block, "precondition: PR 7's body holds no freeze block, so the case probes a lane PR")
        self.assertEqual(block["name"], INTEGRATION_NAME, "precondition: the freeze block names another batch")
        self.assertEqual(self.host.branch, merge.integration_branch(INTEGRATION_NAME),
                         "precondition: PR 7 is not on its batch's integration branch, so it is a lane PR")

    def test_an_integration_pr_whose_head_conflicts_with_a_same_lane_pr_passes_and_reports_the_clash(self):
        """A batch integration PR does not FAIL on a clash with a same-lane PR: the lanes rebase after the merge, so the clash is one report
        line after the PASS line, naming PR #8 and its file."""
        head = self.commit_on(merge.integration_branch(INTEGRATION_NAME), {"shared-a.txt": "integration 7\n"}, "origin/main")
        sib = self.pr_writes(8, {"shared-a.txt": "lane 8\n"}, lane_body(OWN))
        self.host.branch, self.host.body = merge.integration_branch(INTEGRATION_NAME), self.integration_body()
        self.assert_integration_scope()
        self.assertTrue(same_lane(self.host.body, self.host.pulls[8]["body"]), "precondition: PR 8 is not in this lane, so the case probes nothing")
        self.assertEqual(self.clash(head, "origin/main"), "clean", "precondition: the integration head does not merge clean with main")
        self.assertEqual(self.clash(sib, "origin/main"), "clean", "precondition: PR 8 does not merge clean with main, so the clash is not the pair the case names")
        self.assertEqual(self.clash(head, sib), "conflict", "precondition: the integration head and PR 8 do not clash, so the case probes nothing")
        self.use_ci_job(PASSING, 0)
        rc, text, lints, _, _ = self.measured("--lane-lint", "7")
        self.assertEqual(rc, 0, "a clash of a batch integration PR with a same-lane PR refused the lane: " + text)
        self.assertEqual(len(pass_lines(text)), 1, "the lane did not print one PASS line: " + text)
        lines = text.splitlines()
        pass_at = next(i for i, line in enumerate(lines) if line.startswith("PASS:"))
        report = [line for line in lines[pass_at + 1:] if names_pr(line, 8)]
        self.assertTrue(report, "no report line after the PASS names the clashing PR #8: " + text)
        self.assertIn("shared-a.txt", "\n".join(report), "the report line for PR #8 does not name the clashing file: " + text)
        self.assertRegex("\n".join(report), r"(?i)rebase[^\n]*after[^\n]*merge", "the report line for PR #8 does not say the lanes rebase after the merge: " + text)
        self.assertNotIn("FAIL", "\n".join(report), "the report line for PR #8 reads as a FAIL: " + text)
        self.assertEqual(lints, 1, "the ci-job lint did not run once on the passing integration PR: " + text)

    def freeze_only_body(self):
        """The body batch_build writes on an integration PR: its freeze block and nothing else, so no session line names a lane."""
        base = tm.sh(self.other, "git", "rev-parse", "origin/main")
        return "\n".join(merge.freeze_lines(INTEGRATION_NAME, {6: base})) + "\n"

    def test_a_batch_integration_pr_with_a_freeze_only_body_passes_and_reports_a_clash_with_pr_8(self):
        """Why: batch_build writes the integration PR's body as the freeze block alone. Without a session line the lane set is empty, so PR #8 is
        named by --with, and the clash is still a report line, not a FAIL, since the lanes rebase after the merge. Green on the old code."""
        head = self.commit_on(merge.integration_branch(INTEGRATION_NAME), {"shared-a.txt": "integration 7\n"}, "origin/main")
        sib = self.pr_writes(8, {"shared-a.txt": "lane 8\n"}, lane_body(OWN))
        self.host.branch, self.host.body = merge.integration_branch(INTEGRATION_NAME), self.freeze_only_body()
        self.assert_integration_scope()
        self.assertIsNone(session_of(self.host.body), "precondition: PR 7's body names a session, so it is not the freeze-only body")
        self.assertEqual(self.clash(head, "origin/main"), "clean", "precondition: the integration head does not merge clean with main")
        self.assertEqual(self.clash(sib, "origin/main"), "clean", "precondition: PR 8 does not merge clean with main, so the clash is not the pair the case names")
        self.assertEqual(self.clash(head, sib), "conflict", "precondition: the integration head and PR 8 do not clash, so the case probes nothing")
        self.use_ci_job(PASSING, 0)
        rc, text, lints, _, _ = self.measured("--lane-lint", "7", "--with", "8")
        self.assertEqual(rc, 0, "a freeze-only batch integration PR with a clash on PR #8 refused the lane: " + text)
        self.assertEqual(len(pass_lines(text)), 1, "the lane did not print one PASS line: " + text)
        lines = text.splitlines()
        pass_at = next(i for i, line in enumerate(lines) if line.startswith("PASS:"))
        report = [line for line in lines[pass_at + 1:] if names_pr(line, 8)]
        self.assertTrue(report, "no report line after the PASS names the clashing PR #8: " + text)
        self.assertNotIn("FAIL", "\n".join(report), "the report line for PR #8 reads as a FAIL: " + text)
        self.assertRegex("\n".join(report), r"(?i)rebase[^\n]*after[^\n]*merge", "the report line for PR #8 does not say the lanes rebase after the merge: " + text)
        self.assertEqual(lints, 1, "the ci-job lint did not run once on the passing integration PR: " + text)

    def test_an_integration_pr_whose_head_conflicts_with_main_still_fails_and_names_main(self):
        """The integration rule lifts only a clash with a PR's head. A batch head that conflicts with main still FAILs, names main, and runs no ci-job."""
        head = self.commit_on(merge.integration_branch(INTEGRATION_NAME), {"shared-a.txt": "integration 7\n"}, "origin/main")
        self.commit_on("main", {"shared-a.txt": "main\n"}, "origin/main")
        self.host.branch, self.host.body = merge.integration_branch(INTEGRATION_NAME), self.integration_body()
        self.assert_integration_scope()
        self.assertEqual(self.clash(head, "origin/main"), "conflict", "precondition: the integration head merges clean with main, so the case probes nothing")
        self.use_ci_job(PASSING, 0)
        rc, text, lints, _, _ = self.measured("--lane-lint", "7")
        self.assertEqual(rc, 1, "a batch integration head that conflicts with main passed the lane: " + text)
        self.assert_conflict_line_names(text, "main", "the refusal")
        self.assertEqual(pass_lines(text), [], "a batch integration head that conflicts with main printed a PASS line: " + text)
        self.assertEqual(lints, 0, "the ci-job lint ran past a base conflict of a batch integration head: " + text)

    def test_a_freeze_block_on_a_branch_that_is_not_its_integration_branch_is_a_lane_pr_and_fails(self):
        """A freeze block makes a PR an integration PR only on its integration branch. On any other branch it is a lane PR, so a clash
        with a same-lane PR FAILs. Each branch is a subTest; the second is another batch's branch name."""
        head = self.own_writes({"shared-a.txt": "lane 7\n"})
        sib = self.pr_writes(8, {"shared-a.txt": "lane 8\n"}, lane_body(OWN))
        tm.sh(self.other, "git", "push", "-q", "origin", "%s:refs/heads/batch-elsewhere" % head)
        self.host.body = self.integration_body()
        self.assertIsNotNone(merge.parse_freeze(self.host.body), "precondition: PR 7's body holds no freeze block, so the case probes no integration rule")
        self.assertTrue(same_lane(self.host.body, self.host.pulls[8]["body"]), "precondition: PR 8 is not in this lane, so the case probes nothing")
        self.assertEqual(self.clash(sib, "origin/main"), "clean", "precondition: PR 8 does not merge clean with main, so the clash is not counted")
        self.assertEqual(self.clash(head, sib), "conflict", "precondition: the lane head and PR 8 do not clash, so the case probes nothing")
        self.use_ci_job(PASSING, 0)
        for branch in ("feat", "batch-elsewhere"):
            with self.subTest(branch=branch):
                self.host.branch = branch
                self.assertNotEqual(branch, merge.integration_branch(INTEGRATION_NAME), "precondition: the branch is the integration branch, so the case probes nothing")
                rc, text, lints, _, _ = self.measured("--lane-lint", "7")
                self.assertEqual(rc, 1, "a freeze block on branch %s passed as an integration PR: %s" % (branch, text))
                self.assertTrue(names_pr(text, 8), "the refusal does not name the same-lane PR #8: " + text)
                self.assertIn("shared-a.txt", text, "the refusal does not name the clashing file: " + text)
                self.assertRegex(text, r"FAIL", "the refusal does not read as a FAIL: " + text)
                self.assertEqual(pass_lines(text), [], "a lane PR on branch %s printed a PASS line: %s" % (branch, text))
                self.assertEqual(lints, 0, "the ci-job lint ran past the FAIL on branch %s: %s" % (branch, text))


BATCH = "batch-lint-flags"  # the batch the case lints: a pushed branch whose checks job holds the four CI steps below
BATCH_MISSING = "batch-lint-flags-no-red-run"  # the same batch with the Red-run trailer's script left out
BASE = "main"  # the base the lint runs against: lane_lint's base, and the PR base the CI steps read
BATCH_CI_STEPS = ("Silent undo check", "Comment narration check", "Red-run trailer", "STE lint")  # checks.yml's job `checks` CI steps this suite lints
STE = "STE lint"  # the one CI step whose script is bin/ste-changed, not a file of the batch
REPO = os.path.dirname(HERE)
CHECKS_YML = os.path.join(REPO, ".github", "workflows", "checks.yml")  # read at test time; no expectation comes from a copy of it
CALL_STUB = ("import json, os, sys\n"
             "body = json.load(open(os.environ['GITHUB_EVENT_PATH'], encoding='utf-8')).get('pull_request', {}).get('body') if os.environ.get('GITHUB_EVENT_PATH') else None\n"
             "with open(%r, 'a', encoding='utf-8') as f:\n    print(json.dumps({'argv': sys.argv, 'pr_body': body}), file=f)\n")  # logs its argv and the PR body its event file holds, exits 0
BATCH_NO_LINT = "batch-lint-flags-no-lint"  # a batch whose checks job holds NO_LINT_STEPS: no lint step at all
NO_LINT_STEPS = (("Build", "      - name: Build\n        run: make build\n"),
                 ("Unit tests", "      - name: Unit tests\n        run: python3 -m pytest -q\n"))
BATCH_PUSH_ONLY = "batch-lint-flags-push-only"  # a batch whose checks job adds one lint step that runs only off a pull request
PUSH_ONLY = "Push-only lint"
PUSH_ONLY_STEP = (PUSH_ONLY, "      - name: Push-only lint\n        if: ${{ github.event_name != 'pull_request' }}\n"
                             "        run: python3 lint/check_push_only.py\n")
BATCH_FLOOR = "batch-lint-flags-floor"  # a batch whose checks job holds checks.yml's two Python 3.9 floor steps, read by name
FLOOR_NAMES = ("Python 3.9 floor check", "Python 3.9 floor fixture suite")
FLOOR_CHECK = "lint/check_python_floor.py"  # the script the floor check runs, and the file the suite reads: a lint tree lacked it in the incident
FLOOR_SUITE = "lint/test_check_python_floor.py"  # the fixture suite that failed on FileNotFoundError for that file
WORKFLOW_PATH = ".github/workflows/checks.yml"  # the file the lint reads its steps from: the other file a lint tree lacked in the incident
LINT_TREE_FILE_TEXT = "# a file the head's tree holds and the lint tree is made without\n"  # the body of a file the LintTreeFileMain cases push; the lint never reads it
SELECTOR = os.path.join(REPO, ".github", "scripts", "touched-tests.py")  # read at test time: its tables give the skip reasons, and the lint tree loads it
LOAD_4 = "def load():\n    return 4\n"  # main's lint/load.py
LOAD_8 = "def load():\n    return 8\n"  # lane-b's change to it
BUDGET = "from load import load\nassert load() + 3 <= 10, 'the budget is over: load() + 3 > 10'\n"  # lane-a's test: holds on LOAD_4, fails on LOAD_8


def selector_table(name):
    """The table `name` of the selector, loaded by importlib from its file (the filename has a hyphen, so no import statement names it)."""
    spec = importlib.util.spec_from_file_location("touched_tests_under_test", SELECTOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, name)


def logged_test(log, path, tail=""):
    """A test file at `path`. When it runs it appends one tab-separated line to `log`: its path, the interpreter that runs it as the
    interpreter reports itself (sys.executable, $BASH, process.execPath), and its cwd. Then it runs `tail`, code in the file's own language."""
    if path.endswith(".py"):
        return ("import os, sys\n"
                "with open(%r, 'a', encoding='utf-8') as f:\n"
                "    f.write('\\t'.join([%s, sys.executable, os.getcwd()]) + '\\n')\n" % (log, json.dumps(path))) + tail
    if path.endswith(".sh"):
        return ("#!/bin/bash\n"
                "printf '%%s\\t%%s\\t%%s\\n' %s \"$BASH\" \"$(pwd -P)\" >> %s\n" % (shlex.quote(path), shlex.quote(log))) + tail
    if path.endswith(".mjs"):
        return ("import fs from 'node:fs';\n"
                "fs.appendFileSync(%s, [%s, process.execPath, process.cwd()].join('\\t') + '\\n');\n" % (json.dumps(log), json.dumps(path))) + tail
    return "# a .ps1 test: this suite never runs one on Linux\n"


OLD_MODULE = "def value():\n    return 2\n"  # lib/old.py on main: a module whose test a lane deletes with it
OLD_CHECK = "from old import value\nassert value() == 2, 'the old module changed'\n"  # lib/test_old.py on main: passes


def pwsh_absent():
    """A patch under which shutil.which finds no pwsh, whatever this machine has installed. Every other name is looked up as usual."""
    real = shutil.which

    def which(name, *args, **kwargs):
        return None if name == "pwsh" else real(name, *args, **kwargs)
    return unittest.mock.patch.object(shutil, "which", which)


def names_count(line, n, word):
    """True when `line` names the count `n` beside `word`, as `1 run`, `run 1` or `1 tests run`, in either order and never across a comma."""
    return bool(re.search(r"\b%d\b[^,;]*\b%s\b" % (n, word), line) or re.search(r"\b%s\b[^,;]*\b%d\b" % (word, n), line))


def pass_has_counts(line, run, skipped):
    """True when a PASS line names `run` tests run and `skipped` skipped."""
    return names_count(line, run, "run") and names_count(line, skipped, "skipped")


class TouchedTests(LaneFixture):
    """`merge --lane-lint <pr|ref> --touched-tests`: once the lint passes, each test file the batch's diff touches runs in the lint tree.
    Each case builds its own lane branches on origin. A touched test that runs writes its line to self.touched_log, so a case reads
    which tests ran, and in which tree, from that log. Without the flag the lane run is unchanged."""

    def setUp(self):
        super().setUp()
        self.touched_log = os.path.join(self.t, "touched-runs.log")
        self.pwsh_log = os.path.join(self.t, "pwsh-calls.log")  # the stub pwsh of pwsh_stub_on_path writes its argv here
        with open(SELECTOR, encoding="utf-8") as f:
            selector = f.read()
        self.push_commit("main", {
            ".github/scripts/touched-tests.py": selector,
            "lint/load.py": LOAD_4,
            "lint/test_stale.py": logged_test(self.touched_log, "lint/test_stale.py", "raise AssertionError('the stale test ran')\n"),
        })

    def push_commit(self, branch, files):
        """Push one commit on `branch`, made from origin/main with `files` ({path: text}) written. -> the pushed sha."""
        o = self.other
        tm.sh(o, "git", "fetch", "-q", "origin")
        tm.sh(o, "git", "checkout", "-q", "-B", branch, "origin/main")
        for path, text in files.items():
            tm.put(os.path.join(o, path), text)
        tm.sh(o, "git", "add", "-A")
        tm.sh(o, "git", "commit", "-q", "-m", branch + ": one commit")
        tm.sh(o, "git", "push", "-q", "origin", branch)
        return tm.sh(o, "git", "rev-parse", "HEAD")

    def push_integration(self, lanes):
        """feat, the batch's integration pull request (7): origin/main with each lane merged in, forced over the fixture's feat. -> its sha."""
        o = self.other
        tm.sh(o, "git", "fetch", "-q", "origin")
        tm.sh(o, "git", "checkout", "-q", "-B", "feat", "origin/main")
        for lane in lanes:
            tm.sh(o, "git", "merge", "-q", "--no-ff", "-m", "merge " + lane, "origin/" + lane)
        tm.sh(o, "git", "push", "-q", "-f", "origin", "feat")
        return tm.sh(o, "git", "rev-parse", "HEAD")

    def batch_69(self):
        """The batch-69 shape. lane-a adds a test that holds while load() reads 4. lane-b makes load() read 8. Each lane alone passes its
        touched tests (lane-b touches none). feat, both lanes merged, fails lane-a's test, and lane-lint alone passes it."""
        self.push_commit("lane-a", {"lint/test_budget.py": logged_test(self.touched_log, "lint/test_budget.py", BUDGET)})
        self.push_commit("lane-b", {"lint/load.py": LOAD_8})
        self.push_integration(["lane-a", "lane-b"])

    def flagged(self, *argv):
        """-> (rc, stdout and stderr together) of merge in the lane checkout, after clearing the touched log and the lint's call log. A usage
        error is its rc and text here: each case asserts what the run did, so an argparse refusal fails the case by its own message."""
        for path in (self.touched_log, self.log):  # self.log is the lint stub's call log (CiJobStub.init_stub)
            if os.path.exists(path):
                os.remove(path)
        rc, out, err = self.run_main(*argv, CLAUDE_CODE_REMOTE=None)
        return rc, out + err

    def flagged_or_fail(self, *argv):
        """flagged(), where an exception that escapes merge is the named cause: a traceback is never the answer to a touched test."""
        try:
            return self.flagged(*argv)
        except Exception as e:  # merge's exits are SystemExit, which flagged returns; anything else escaped
            self.fail("merge raised %s instead of refusing or passing: %s" % (type(e).__name__, e))

    def pwsh_stub_on_path(self):
        """A `pwsh` on PATH that appends its argv to self.pwsh_log and exits 0. -> the patch that puts it on PATH."""
        bindir = os.path.join(self.t, "pwsh-bin")
        os.makedirs(bindir)
        stub = os.path.join(bindir, "pwsh")
        tm.put(stub, "#!/bin/sh\nprintf '%%s\\n' \"$*\" >> %s\nexit 0\n" % shlex.quote(self.pwsh_log))
        os.chmod(stub, 0o755)
        return unittest.mock.patch.dict(os.environ, {"PATH": bindir + os.pathsep + os.environ.get("PATH", "")})

    def touched_lines(self):
        """The rows the touched tests wrote in the last run, oldest first: [path, interpreter, cwd] each."""
        if not os.path.exists(self.touched_log):
            return []
        with open(self.touched_log, encoding="utf-8") as f:
            return [line.rstrip("\n").split("\t") for line in f if line.strip()]

    def ran(self, path):
        """The rows the touched test `path` wrote in the last run: one per run."""
        return [row for row in self.touched_lines() if row[0] == path]

    def lint_tree(self):
        """-> the directory of the one lint run of the last run. The touched tests must have run in it."""
        calls = self.lint_calls()
        self.assertEqual(len(calls), 1, "the lint ran %d times, want once" % len(calls))
        return calls[0]["cwd"]

    def test_without_the_flag_the_batch_that_fails_a_touched_test_passes_and_runs_no_test(self):  # the control
        self.batch_69()
        self.use_ci_job(PASSING, 0)
        rc, text = self.lint_run("--lane-lint", "7")
        self.assertEqual(rc, 0, "lane-lint without --touched-tests refused the batch: " + text)
        self.assertEqual(len(pass_lines(text)), 1, text)
        self.assertEqual(self.touched_lines(), [], "a run without --touched-tests ran a test: " + text)
        self.assertEqual([line for line in text.splitlines() if line.startswith("skip ")], [],
                         "a run without --touched-tests printed a skip line: " + text)

    def test_the_flag_refuses_the_batch_that_lane_lint_alone_passes_and_names_the_failing_test(self):
        self.batch_69()
        self.use_ci_job(PASSING, 0)
        rc, text = self.flagged("--lane-lint", "7", "--touched-tests")
        self.assertEqual(rc, 1, "--touched-tests did not refuse the batch whose merged tree fails a touched test (rc %r): %s" % (rc, text))
        self.assertTrue(any("FAIL" in line and "lint/test_budget.py" in line for line in text.splitlines()),
                        "the refusal does not name the failing touched test: " + text)
        self.assertIn("the budget is over", text, "the refusal does not show the failing test's last output: " + text)
        self.assertEqual(pass_lines(text), [], "the refused batch also printed a PASS line: " + text)
        self.assertEqual(self.ran("lint/test_stale.py"), [], "a test no lane touched ran in the batch")
        self.lint_tree()

    def test_the_batch_69_lanes_each_pass_the_flag_alone_and_the_touched_test_runs_once_in_the_lint_tree(self):
        self.batch_69()
        self.use_ci_job(PASSING, 0)
        rc, text = self.flagged("--lane-lint", "lane-a", "--touched-tests")
        self.assertEqual(rc, 0, "lane-a alone was refused with --touched-tests: " + text)
        tree = self.lint_tree()
        runs = self.ran("lint/test_budget.py")
        self.assertEqual(len(runs), 1, "lane-a's touched test ran %d times alone, want once: %s" % (len(runs), text))
        self.assertEqual(runs[0][2], tree, "lane-a's touched test did not run in the lint tree: " + "\t".join(runs[0]))
        lines = pass_lines(text)
        self.assertEqual(len(lines), 1, text)
        self.assertTrue(pass_has_counts(lines[0], 1, 0), "the PASS line does not name 1 run and 0 skipped: " + lines[0])
        rc, text = self.flagged("--lane-lint", "lane-b", "--touched-tests")
        self.assertEqual(rc, 0, "lane-b alone was refused with --touched-tests: " + text)
        self.assertEqual(self.touched_lines(), [], "lane-b touches no test, yet a test ran: " + text)
        lines = pass_lines(text)
        self.assertEqual(len(lines), 1, text)
        self.assertTrue(pass_has_counts(lines[0], 0, 0), "the PASS line does not name 0 run and 0 skipped: " + lines[0])

    def test_touched_tests_without_lane_lint_is_refused_before_any_read_and_the_refusal_names_lane_lint(self):
        self.batch_69()
        self.use_ci_job(PASSING, 0)
        rc, text = self.flagged("7", "--touched-tests")
        self.assertEqual(rc, 2, "--touched-tests without --lane-lint did not refuse with a usage error (rc %r): %s" % (rc, text))
        error_lines = [line for line in text.splitlines() if "error:" in line]  # the usage line always names --lane-lint: only the error line counts
        self.assertTrue(any("--lane-lint" in line for line in error_lines),
                        "the error does not name --lane-lint, the mode --touched-tests goes with: " + text)
        self.assertEqual(self.host.pr_calls, [], "the refused flag read the pull request first")
        self.assertEqual(self.lint_calls(), [], "the refused flag ran the lint")

    def test_a_failed_lint_refuses_and_no_touched_test_runs(self):
        self.push_commit("lane-a", {"lint/test_budget.py": logged_test(self.touched_log, "lint/test_budget.py", BUDGET)})
        self.use_ci_job(FAILING, 1)
        rc, text = self.flagged("--lane-lint", "lane-a", "--touched-tests")
        self.assertEqual(rc, 1, "a lint that FAILs did not refuse under --touched-tests (rc %r): %s" % (rc, text))
        self.assertTrue(any("comment narration" in line and "FAIL" in line for line in text.splitlines()),
                        "the refusal does not name the failed lint step: " + text)
        self.assertEqual(pass_lines(text), [], text)
        self.assertEqual(self.touched_lines(), [], "a touched test ran after the lint FAILed: " + text)

    def test_a_lint_read_unknown_and_lifted_by_a_reason_runs_no_touched_test(self):
        self.push_commit("lane-a", {"lint/test_budget.py": logged_test(self.touched_log, "lint/test_budget.py", BUDGET)})
        self.use_ci_job(UNKNOWN, 2)
        rc, text = self.flagged("--lane-lint", "lane-a", "--touched-tests", "--lint-unknown-ok", "shellcheck is not on this box")
        self.assertEqual(rc, 0, "a lint read unknown and lifted by a reason was refused (rc %r): %s" % (rc, text))
        self.assertEqual(pass_lines(text), [], "an unknown lint read printed a PASS line: " + text)
        self.assertEqual(self.touched_lines(), [], "a touched test ran after the lint read unknown, not pass: " + text)
        self.assertTrue(any("touched" in line and ("not run" in line or "did not run" in line) for line in text.splitlines()),
                        "a lifted unknown lint printed no line saying the touched tests did not run: " + text)

    def test_a_heavy_touched_test_is_skipped_with_its_reason_and_never_run(self):
        heavy = selector_table("HEAVY")
        self.assertIn("merge/test_merge.py", heavy, "the selector's HEAVY table does not name merge/test_merge.py, so the case probes nothing")
        self.push_commit("lane-h", {"merge/test_merge.py": logged_test(self.touched_log, "merge/test_merge.py")})
        self.use_ci_job(PASSING, 0)
        rc, text = self.flagged("--lane-lint", "lane-h", "--touched-tests")
        self.assertEqual(rc, 0, "a batch whose only touched test is HEAVY was refused (rc %r): %s" % (rc, text))
        self.assertIn("skip merge/test_merge.py: " + heavy["merge/test_merge.py"], text,
                      "the HEAVY test was not skipped with its reason: " + text)
        self.assertEqual(self.ran("merge/test_merge.py"), [], "a HEAVY test ran in the lint tree")
        lines = pass_lines(text)
        self.assertEqual(len(lines), 1, text)
        self.assertTrue(pass_has_counts(lines[0], 0, 1), "the PASS line does not name 0 run and 1 skipped: " + lines[0])

    def test_a_needs_setup_touched_test_is_skipped_with_its_reason_and_never_run(self):
        needs = selector_table("NEEDS_SETUP")
        self.assertIn("lint/test_ios_ship.sh", needs, "the selector's NEEDS_SETUP table does not name lint/test_ios_ship.sh, so the case probes nothing")
        self.push_commit("lane-n", {"lint/test_ios_ship.sh": logged_test(self.touched_log, "lint/test_ios_ship.sh")})
        self.use_ci_job(PASSING, 0)
        rc, text = self.flagged("--lane-lint", "lane-n", "--touched-tests")
        self.assertEqual(rc, 0, "a batch whose only touched test needs setup was refused (rc %r): %s" % (rc, text))
        self.assertIn("skip lint/test_ios_ship.sh: " + needs["lint/test_ios_ship.sh"], text,
                      "the NEEDS_SETUP test was not skipped with its reason: " + text)
        self.assertEqual(self.ran("lint/test_ios_ship.sh"), [], "a NEEDS_SETUP test ran in the lint tree")
        lines = pass_lines(text)
        self.assertEqual(len(lines), 1, text)
        self.assertTrue(pass_has_counts(lines[0], 0, 1), "the PASS line does not name 0 run and 1 skipped: " + lines[0])

    def test_a_powershell_touched_test_is_skipped_for_no_pwsh_when_pwsh_is_absent_and_is_neither_a_pass_nor_a_fail(self):
        self.push_commit("lane-p", {"lint/widget.test.ps1": logged_test(self.touched_log, "lint/widget.test.ps1")})
        self.use_ci_job(PASSING, 0)
        with pwsh_absent():
            rc, text = self.flagged("--lane-lint", "lane-p", "--touched-tests")
        self.assertEqual(rc, 0, "a batch whose only touched test is a .ps1 was refused (rc %r): %s" % (rc, text))
        self.assertIn("skip lint/widget.test.ps1: no pwsh on this runner", text, "the .ps1 test was not skipped for no pwsh: " + text)
        self.assertFalse(any("FAIL" in line for line in text.splitlines()), "a skipped .ps1 read as a FAIL: " + text)
        lines = pass_lines(text)
        self.assertEqual(len(lines), 1, text)
        self.assertTrue(pass_has_counts(lines[0], 0, 1), "the PASS line does not name 0 run and 1 skipped: " + lines[0])

    def test_each_touched_test_runs_under_the_interpreter_its_extension_names_in_the_lint_tree(self):
        files = ("lint/test_one.py", "lint/two.test.sh", "lint/three.test.mjs")
        self.push_commit("lane-i", {path: logged_test(self.touched_log, path) for path in files})
        self.use_ci_job(PASSING, 0)
        rc, text = self.flagged("--lane-lint", "lane-i", "--touched-tests")
        self.assertEqual(rc, 0, "a batch of three touched tests was refused (rc %r): %s" % (rc, text))
        tree = self.lint_tree()
        real = {"lint/test_one.py": sys.executable, "lint/two.test.sh": shutil.which("bash"), "lint/three.test.mjs": shutil.which("node")}
        for path in files:
            with self.subTest(test=path):
                runs = self.ran(path)
                self.assertEqual(len(runs), 1, "%s ran %d times, want once: %s" % (path, len(runs), text))
                logged = runs[0][1]
                self.assertEqual(os.path.realpath(logged), os.path.realpath(real[path]),
                                 "%s ran under %r, not the interpreter its extension names, %r" % (path, logged, real[path]))
                self.assertEqual(runs[0][2], tree, "%s did not run in the lint tree: %r" % (path, runs[0][2]))
        lines = pass_lines(text)
        self.assertEqual(len(lines), 1, text)
        self.assertTrue(pass_has_counts(lines[0], 3, 0), "the PASS line does not name 3 run and 0 skipped: " + lines[0])

    def test_a_failing_touched_test_is_a_fail_that_names_each_failing_test_with_its_last_output_and_no_pass_hides_it(self):
        self.push_commit("lane-f", {
            "lint/test_one_fail.py": logged_test(self.touched_log, "lint/test_one_fail.py", "raise AssertionError('marker-py-fail')\n"),
            "lint/two_fail.test.sh": logged_test(self.touched_log, "lint/two_fail.test.sh", "echo marker-sh-fail\nexit 3\n"),
            "lint/three_ok.test.mjs": logged_test(self.touched_log, "lint/three_ok.test.mjs"),
        })
        self.use_ci_job(PASSING, 0)
        rc, text = self.flagged("--lane-lint", "lane-f", "--touched-tests")
        self.assertEqual(rc, 1, "a touched test that exits non-zero did not refuse (rc %r): %s" % (rc, text))
        fails = [line for line in text.splitlines() if "FAIL" in line]
        for path in ("lint/test_one_fail.py", "lint/two_fail.test.sh"):
            self.assertTrue(any(path in line for line in fails), "the refusal does not name the failing test %s: %s" % (path, text))
        self.assertFalse(any("lint/three_ok.test.mjs" in line for line in fails), "a passing test is named as a FAIL: " + text)
        self.assertIn("marker-py-fail", text, "the refusal lacks the last output of the Python test: " + text)
        self.assertIn("marker-sh-fail", text, "the refusal lacks the last output of the bash test: " + text)
        self.assertEqual(pass_lines(text), [], "a refused batch printed a PASS line: " + text)

    def test_a_touched_test_that_times_out_is_unknown_never_a_pass_and_only_a_reason_lifts_it(self):
        self.push_commit("lane-t", {"lint/test_slow.py": logged_test(self.touched_log, "lint/test_slow.py")})
        self.use_ci_job(PASSING, 0)
        real_sh = merge.sh
        timeouts = []  # the timeout= each touched-test run was given: a run with none would never end

        def time_out_the_touched_test(args, *rest, **kwargs):  # a run that never ends: the one way a child of the lint tree times out
            if any(isinstance(a, str) and a.endswith("lint/test_slow.py") for a in args):
                timeouts.append(kwargs.get("timeout"))
                raise subprocess.TimeoutExpired(args, 1)
            return real_sh(args, *rest, **kwargs)

        with unittest.mock.patch.object(merge, "sh", time_out_the_touched_test):
            rc, text = self.flagged("--lane-lint", "lane-t", "--touched-tests")
            self.assertEqual(rc, 1, "a touched test that timed out did not refuse (rc %r): %s" % (rc, text))
            self.assertTrue(timeouts, "the touched test never ran through sh, so the case probes nothing: " + text)
            bound = timeouts[0]
            self.assertIsInstance(bound, (int, float), "the touched test ran with no numeric timeout: %r" % (bound,))
            self.assertGreater(bound, 0, "the touched test ran with a timeout that is not positive: %r" % (bound,))
            self.assertLessEqual(bound, merge.LINT_SECONDS, "the touched test ran with a timeout past LINT_SECONDS: %r" % (bound,))
            self.assertRegex(text, r"(?i)unknown", "a timed-out touched test does not read as unknown: " + text)
            self.assertEqual(pass_lines(text), [], "a timed-out touched test printed a PASS line: " + text)
            rc, text = self.flagged("--lane-lint", "lane-t", "--touched-tests", "--lint-unknown-ok", "the test box is slow")
            self.assertEqual(rc, 0, "a timed-out touched test was not lifted by a reason (rc %r): %s" % (rc, text))
            self.assertIn("the test box is slow", text, "the lifted timeout does not log its reason: " + text)
            self.assertEqual(pass_lines(text), [], "a lifted timeout printed a PASS line: " + text)

    def test_an_unloadable_selector_is_unknown_never_a_pass_and_only_a_reason_lifts_it(self):
        self.push_commit("lane-s", {
            ".github/scripts/touched-tests.py": "def broken(:\n",
            "lint/test_budget.py": logged_test(self.touched_log, "lint/test_budget.py", BUDGET),
        })
        self.use_ci_job(PASSING, 0)
        rc, text = self.flagged("--lane-lint", "lane-s", "--touched-tests")
        self.assertEqual(rc, 1, "a selector that cannot be loaded did not refuse (rc %r): %s" % (rc, text))
        self.assertRegex(text, r"(?i)unknown", "a selector that cannot be loaded does not read as unknown: " + text)
        self.assertEqual(pass_lines(text), [], "a selector that cannot be loaded printed a PASS line: " + text)
        self.assertEqual(self.touched_lines(), [], "a test ran with no selector loaded: " + text)
        rc, text = self.flagged("--lane-lint", "lane-s", "--touched-tests", "--lint-unknown-ok", "the selector is being fixed")
        self.assertEqual(rc, 0, "a selector that cannot be loaded was not lifted by a reason (rc %r): %s" % (rc, text))
        self.assertIn("the selector is being fixed", text, "the lifted selector read does not log its reason: " + text)
        self.assertEqual(pass_lines(text), [], "a lifted selector read printed a PASS line: " + text)




    def push_tree_change(self, branch, write=None, remove=()):
        """Push one commit on `branch`, made from origin/main: each path of `remove` deleted with git rm, each of `write` ({path: text}) written.
        -> the pushed sha."""
        o = self.other
        tm.sh(o, "git", "fetch", "-q", "origin")
        tm.sh(o, "git", "checkout", "-q", "-B", branch, "origin/main")
        for path in remove:
            tm.sh(o, "git", "rm", "-q", path)
        for path, text in (write or {}).items():
            tm.put(os.path.join(o, path), text)
        tm.sh(o, "git", "add", "-A")
        tm.sh(o, "git", "commit", "-q", "-m", branch + ": one commit")
        tm.sh(o, "git", "push", "-q", "origin", branch)
        return tm.sh(o, "git", "rev-parse", "HEAD")

    def push_selector_override(self, lane, def_text):
        """Push `lane` whose selector is the real one plus `def_text`: a definition that overrides one of the selector's functions. The lint
        tree loads the lane's own selector, so the override is what run_touched_tests calls. The lane also touches a test that holds."""
        with open(SELECTOR, encoding="utf-8") as f:
            selector = f.read()
        self.push_commit(lane, {
            ".github/scripts/touched-tests.py": selector + "\n\n" + def_text,
            "lint/test_budget.py": logged_test(self.touched_log, "lint/test_budget.py", BUDGET),
        })

    def assert_unknown_then_lifted(self, lane, cause):
        """The lane's touched-test stage reads unknown: it refuses without a reason, with no PASS line, and a reason lifts it. `cause` names
        the fault in every message. An exception that escapes merge fails the case by name."""
        self.use_ci_job(PASSING, 0)
        rc, text = self.flagged_or_fail("--lane-lint", lane, "--touched-tests")
        self.assertEqual(rc, 1, "%s did not refuse as unknown (rc %r): %s" % (cause, rc, text))
        self.assertRegex(text, r"(?i)unknown", "%s does not read as unknown: %s" % (cause, text))
        self.assertEqual(pass_lines(text), [], "%s printed a PASS line: %s" % (cause, text))
        rc, text = self.flagged_or_fail("--lane-lint", lane, "--touched-tests", "--lint-unknown-ok", "the selector is being fixed")
        self.assertEqual(rc, 0, "%s was not lifted by a reason (rc %r): %s" % (cause, rc, text))
        self.assertIn("the selector is being fixed", text, "%s did not log its lifting reason: %s" % (cause, text))
        self.assertEqual(pass_lines(text), [], "%s printed a PASS line once lifted: %s" % (cause, text))

    def test_a_touched_test_with_a_non_ascii_name_that_fails_refuses_the_batch(self):
        name = "lint/test_ünï.py"  # git quotes this name in `diff --name-only` and `ls-files` unless they run with -z
        self.push_commit("lane-u", {name: logged_test(self.touched_log, name, "raise AssertionError('marker-unicode-fail')\n")})
        self.use_ci_job(PASSING, 0)
        rc, text = self.flagged("--lane-lint", "lane-u", "--touched-tests")
        self.assertEqual(rc, 1, "a failing touched test with a non-ASCII name passed (rc %r): %s" % (rc, text))
        self.assertTrue(any("FAIL" in line and name in line for line in text.splitlines()),
                        "the refusal does not name the non-ASCII touched test %s: %s" % (ascii(name), text))
        self.assertIn("marker-unicode-fail", text, "the refusal lacks the non-ASCII test's last output: " + text)

    def test_a_touched_test_with_a_space_in_its_name_that_fails_refuses_the_batch(self):
        name = "lint/test_two words.py"
        self.push_commit("lane-w", {name: logged_test(self.touched_log, name, "raise AssertionError('marker-space-fail')\n")})
        self.use_ci_job(PASSING, 0)
        rc, text = self.flagged("--lane-lint", "lane-w", "--touched-tests")
        self.assertEqual(rc, 1, "a failing touched test with a space in its name passed (rc %r): %s" % (rc, text))
        self.assertTrue(any("FAIL" in line and name in line for line in text.splitlines()),
                        "the refusal does not name the touched test with a space %s: %s" % (ascii(name), text))

    def test_a_powershell_touched_test_runs_under_pwsh_when_pwsh_is_on_the_path(self):
        self.push_commit("lane-q", {"lint/widget.test.ps1": logged_test(self.touched_log, "lint/widget.test.ps1")})
        self.use_ci_job(PASSING, 0)
        with self.pwsh_stub_on_path():
            rc, text = self.flagged("--lane-lint", "lane-q", "--touched-tests")
        self.assertEqual(rc, 0, "a batch whose only touched test is a .ps1 was refused with pwsh on the PATH (rc %r): %s" % (rc, text))
        self.assertNotIn("skip lint/widget.test.ps1", text, "a .ps1 was skipped although pwsh is on the PATH: " + text)
        calls = []
        if os.path.exists(self.pwsh_log):
            with open(self.pwsh_log, encoding="utf-8") as f:
                calls = f.read().splitlines()
        self.assertTrue(any("lint/widget.test.ps1" in call for call in calls),
                        "pwsh was on the PATH, yet no pwsh run named the .ps1 test: " + text)
        lines = pass_lines(text)
        self.assertEqual(len(lines), 1, text)
        self.assertTrue(pass_has_counts(lines[0], 1, 0), "the PASS line does not name 1 run and 0 skipped: " + lines[0])

    def test_a_missing_interpreter_at_run_time_is_unknown_and_lifted_by_a_reason_not_a_traceback(self):
        self.push_commit("lane-m", {"lint/test_budget.py": logged_test(self.touched_log, "lint/test_budget.py", BUDGET)})
        self.use_ci_job(PASSING, 0)
        real_sh = merge.sh

        def no_interpreter(args, *rest, **kwargs):  # the program is gone between the selection and the run
            if any(isinstance(a, str) and a.endswith("lint/test_budget.py") for a in args):
                raise FileNotFoundError(2, "No such file or directory", args[0])
            return real_sh(args, *rest, **kwargs)

        with unittest.mock.patch.object(merge, "sh", no_interpreter):
            rc, text = self.flagged_or_fail("--lane-lint", "lane-m", "--touched-tests")
            self.assertEqual(rc, 1, "a touched test whose interpreter was missing did not refuse (rc %r): %s" % (rc, text))
            self.assertRegex(text, r"(?i)unknown", "a missing interpreter does not read as unknown: " + text)
            self.assertEqual(pass_lines(text), [], "a missing interpreter printed a PASS line: " + text)
            rc, text = self.flagged_or_fail("--lane-lint", "lane-m", "--touched-tests", "--lint-unknown-ok", "node is not on this box")
            self.assertEqual(rc, 0, "a missing interpreter was not lifted by a reason (rc %r): %s" % (rc, text))
            self.assertIn("node is not on this box", text, "the lifted missing interpreter does not log its reason: " + text)

    def test_a_selector_whose_candidates_raises_is_unknown_not_a_traceback(self):
        self.push_selector_override("lane-c", "def candidates(path, tracked):\n    raise RuntimeError('selector candidates broke')\n")
        self.assert_unknown_then_lifted("lane-c", "a selector whose candidates() raises")

    def test_a_selector_whose_reason_raises_is_unknown_not_a_traceback(self):
        self.push_selector_override("lane-r", "def reason(path, table):\n    raise RuntimeError('selector reason broke')\n")
        self.assert_unknown_then_lifted("lane-r", "a selector whose reason() raises")


    def test_a_lane_that_deletes_a_test_and_its_module_passes_and_runs_no_deleted_path(self):
        """A deleted test path is still a test name, so candidates() returns it, and the run of it fails "can't open file". The deleted path
        is never selected: the lane passes, no test runs, and the PASS line counts 0 run and 0 skipped."""
        self.push_tree_change("main", write={"lib/old.py": OLD_MODULE, "lib/test_old.py": logged_test(self.touched_log, "lib/test_old.py", OLD_CHECK)})
        self.push_tree_change("lane-d", remove=["lib/test_old.py", "lib/old.py"])
        self.use_ci_job(PASSING, 0)
        rc, text = self.flagged("--lane-lint", "lane-d", "--touched-tests")
        self.assertEqual(rc, 0, "a lane that deletes a test and its module was refused, so the deleted test path was selected and run: rc %r: %s" % (rc, text))
        self.assertEqual(self.ran("lib/test_old.py"), [], "the deleted test path ran in the lint tree")
        lines = pass_lines(text)
        self.assertEqual(len(lines), 1, text)
        self.assertTrue(pass_has_counts(lines[0], 0, 0), "the PASS line does not name 0 run and 0 skipped: " + lines[0])

    def test_a_lane_that_renames_a_test_passes_and_runs_only_the_new_path(self):
        """A rename is a deleted path and a new one. The deleted path is never selected: the lane passes, the renamed test runs once in the
        lint tree, and the PASS line counts 1 run and 0 skipped."""
        self.push_tree_change("main", write={"lib/test_moved.py": logged_test(self.touched_log, "lib/test_moved.py")})
        self.push_tree_change("lane-e", remove=["lib/test_moved.py"], write={"lib/test_renamed.py": logged_test(self.touched_log, "lib/test_renamed.py")})
        self.use_ci_job(PASSING, 0)
        rc, text = self.flagged("--lane-lint", "lane-e", "--touched-tests")
        self.assertEqual(rc, 0, "a lane that renames a test was refused, so the deleted path was selected and run: rc %r: %s" % (rc, text))
        self.assertEqual(self.ran("lib/test_moved.py"), [], "the renamed-away test path ran in the lint tree")
        runs = self.ran("lib/test_renamed.py")
        self.assertEqual(len(runs), 1, "the renamed test ran %d times, want once: %s" % (len(runs), text))
        self.assertEqual(runs[0][2], self.lint_tree(), "the renamed test did not run in the lint tree: " + "\t".join(runs[0]))
        lines = pass_lines(text)
        self.assertEqual(len(lines), 1, text)
        self.assertTrue(pass_has_counts(lines[0], 1, 0), "the PASS line does not name 1 run and 0 skipped: " + lines[0])


def real_ci_steps(names=BATCH_CI_STEPS):
    """(name, CI step text) of `names` in checks.yml's checks job, in file order, read by the shared parser."""
    with open(CHECKS_YML, encoding="utf-8") as f:
        block = job_block(f.read(), "checks")
    return [(step_key(st, "name"), st) for st in step_blocks(block) if step_key(st, "name") in names]


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


def missing_from_lint_tree(rels):
    """A patch: the lint tree merge.add_worktree makes lacks each of `rels`, as the incident's tree did. The head's branch holds them; the tree
    on disk does not. The one home of that tree shape: BatchLintFlags and LintTreeFileMain both patch through it."""
    made = merge.add_worktree

    def add_worktree_without(root, head):
        tmp, wt = made(root, head)
        for rel in rels:
            os.remove(os.path.join(wt, *rel.split("/")))
        return tmp, wt

    return unittest.mock.patch.object(merge, "add_worktree", add_worktree_without)


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
        logging stub for each lint script of that job (a step that runs `lint/...`), except the scripts in `skip`. -> the branch's head sha."""
        o = self.other
        tm.sh(o, "git", "fetch", "-q", "origin")
        tm.sh(o, "git", "checkout", "-q", "-B", branch, "origin/" + BASE)
        job = self.found if found is None else found
        tm.put(os.path.join(o, ".github", "workflows", "checks.yml"), workflow_text(job))
        for name, ci_step in job:
            if name != STE and script_of(ci_step).startswith("lint/") and script_of(ci_step) not in skip:
                tm.put(os.path.join(o, script_of(ci_step)), CALL_STUB % self.call_log(script_of(ci_step)))
        tm.sh(o, "git", "add", "-A")
        tm.sh(o, "git", "commit", "-q", "-m", branch + ": the checks job's lint CI steps and their stubs")
        tm.sh(o, "git", "push", "-q", "origin", branch)
        return tm.sh(o, "git", "rev-parse", "HEAD")

    def lane_lint(self, target, out, missing=(), unknown_ok=""):
        """merge.lane_lint of `target` against BASE, in the lane checkout, through the copy of ci-job. Its output goes to `out`. A refusal raises.
        `missing` names paths the lint tree lacks once it is made, as the incident's tree did: the branch holds them, the tree on disk does not.
        `unknown_ok` is the --lint-unknown-ok reason, passed as the command line passes it."""
        env = {"VERDICT_LOG": os.path.join(self.t, "verdict.log")}  # one log for the run: no ci-job log lands in the system temp dir
        with unittest.mock.patch.object(tempfile, "tempdir", RUN_FOLDER), unittest.mock.patch.object(merge, "CI_JOB", self.ci_job), \
                missing_from_lint_tree(missing), \
                unittest.mock.patch.dict(os.environ, env), contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            return merge.lane_lint(self.co, target, self.host, base=BASE, unknown_ok=unknown_ok)

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

    def test_the_silent_undo_step_reads_the_pull_requests_body_from_its_event_file(self):
        """A pull request's lint gives the silent-undo step the PR's body in its event file: lane_lint takes the body from the host,
        and ci-job gives the step the event file that CI gives it, with no body in the step's env. The body holds a Drops-lines line."""
        body = "Summary.\n\nDrops-lines: lint/gone.py -- the file is gone\n\nhttps://claude.ai/code/session_X\n"
        self.push_batch(BATCH)
        self.host.branch, self.host.body = BATCH, body
        out = io.StringIO()
        rc = self.lane_lint("7", out)
        text = out.getvalue()
        self.assertEqual(rc, 0, text)
        calls = self.stub_calls(script_of(dict(self.found)["Silent undo check"]))
        self.assertEqual(len(calls), 1, "the silent-undo step's script ran %d times, want once: %s" % (len(calls), text))
        self.assertEqual(calls[0].get("pr_body"), body, "the silent-undo step read %r from its event file, want the PR's body" % (calls[0].get("pr_body"),))

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

    def floor_steps(self):
        """checks.yml's two Python 3.9 floor CI steps, read from the real file by name: each runs the script the batch stubs."""
        found = real_ci_steps(FLOOR_NAMES)
        self.assertEqual([name for name, _ in found], list(FLOOR_NAMES), "checks.yml does not hold the two floor steps in this order")
        self.assertEqual([script_of(st) for _, st in found], [FLOOR_CHECK, FLOOR_SUITE], "checks.yml's floor steps run other scripts than this suite reads")
        return found

    def test_a_present_floor_pair_passes_and_each_step_runs_once(self):
        self.push_batch(BATCH_FLOOR, found=self.floor_steps())
        out = io.StringIO()
        rc = self.lane_lint(BATCH_FLOOR, out)
        text = out.getvalue()
        self.assertEqual(rc, 0, text)
        self.assertEqual(len(pass_lines(text)), 1, text)
        for script in (FLOOR_CHECK, FLOOR_SUITE):
            calls = self.stub_calls(script)
            self.assertEqual(len(calls), 1, "%s ran %d times, want once: %s" % (script, len(calls), text))

    def test_a_missing_check_file_in_the_lint_tree_refuses_as_unknown_that_names_the_file(self):
        head = self.push_batch(BATCH_FLOOR, found=self.floor_steps())
        self.assertEqual(tm.sh(self.other, "git", "ls-tree", "--name-only", head, "--", FLOOR_CHECK), FLOOR_CHECK,
                         "the branch does not hold the check file the lint tree is made without")
        out = io.StringIO()
        with self.assertRaises(merge.Stop) as raised:
            self.lane_lint(BATCH_FLOOR, out, missing=(FLOOR_CHECK,))
        self.assertIn("is unknown", str(raised.exception), "a missing check file did not read as unknown: " + out.getvalue())
        self.assertNotIsInstance(raised.exception, merge.Liftable, "a missing check file is liftable by --lint-unknown-ok: " + out.getvalue())
        self.assertIn(FLOOR_CHECK, str(raised.exception), "the refusal does not name the missing check file: " + out.getvalue())
        self.assertEqual(pass_lines(out.getvalue()), [], "a lint of a tree missing its check file read as a pass: " + out.getvalue())

    def test_a_missing_check_file_in_the_lint_tree_prints_no_floor_step_verdict(self):
        self.push_batch(BATCH_FLOOR, found=self.floor_steps())
        out = io.StringIO()
        with self.assertRaises(merge.Stop) as raised:
            self.lane_lint(BATCH_FLOOR, out, missing=(FLOOR_CHECK,))
        text = str(raised.exception) + out.getvalue()  # the refusal carries the ci-job lines it read
        verdicts = [line for line in text.splitlines() if FLOOR_NAMES[0] in line and line.lstrip().startswith(("FAIL", "PASS", "unknown"))]
        self.assertEqual(verdicts, [], "the floor check printed a verdict, so a step ran before the lint refused the missing file: " + text)

    def test_a_reason_does_not_lift_a_missing_check_file_in_the_lint_tree(self):
        self.push_batch(BATCH_FLOOR, found=self.floor_steps())
        out = io.StringIO()
        with self.assertRaises(merge.Stop) as raised:
            self.lane_lint(BATCH_FLOOR, out, missing=(FLOOR_CHECK,), unknown_ok="a reason the lint must not take")
        self.assertIn("is unknown", str(raised.exception), "a missing check file did not read as unknown with a reason given: " + out.getvalue())
        self.assertNotIsInstance(raised.exception, merge.Liftable, "a --lint-unknown-ok reason lifted a missing check file: " + out.getvalue())

    def test_a_missing_check_file_in_the_lint_tree_runs_no_later_floor_suite(self):
        self.push_batch(BATCH_FLOOR, found=self.floor_steps())
        out = io.StringIO()
        with self.assertRaises(merge.Stop):
            self.lane_lint(BATCH_FLOOR, out, missing=(FLOOR_CHECK,))
        self.assertEqual(self.stub_calls(FLOOR_SUITE), [], "the floor suite ran after its check file was found missing: " + out.getvalue())

    def test_a_missing_workflow_file_in_the_lint_tree_refuses_as_unknown_that_names_the_file(self):
        head = self.push_batch(BATCH_FLOOR, found=self.floor_steps())
        self.assertEqual(tm.sh(self.other, "git", "ls-tree", "--name-only", head, "--", WORKFLOW_PATH), WORKFLOW_PATH,
                         "the branch does not hold the workflow file the lint tree is made without")
        out = io.StringIO()
        with self.assertRaises(merge.Stop) as raised:
            self.lane_lint(BATCH_FLOOR, out, missing=(WORKFLOW_PATH,))
        self.assertIn("is unknown", str(raised.exception), "a missing workflow file did not read as unknown: " + out.getvalue())
        self.assertNotIsInstance(raised.exception, merge.Liftable, "a missing workflow file is liftable by --lint-unknown-ok: " + out.getvalue())
        self.assertIn(WORKFLOW_PATH, str(raised.exception), "the refusal does not name the missing workflow file: " + out.getvalue())
        self.assertEqual(pass_lines(out.getvalue()), [], "a lint of a tree missing its workflow file read as a pass: " + out.getvalue())

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


class LintTreeFileMain(LaneFixture):
    """`merge --lane-lint <ref>` through main(): a lint tree that lacks a file its head's git tree holds is UNKNOWN. The refusal exits 1
    (every lane-lint refusal does; exit 2 is argparse's usage code), names the file, runs no step, and --lint-unknown-ok never lifts it.
    The control is a head whose tree never held those files: this check does not stop it."""

    def setUp(self):
        super().setUp()
        self.use_ci_job(PASSING, 0)  # a step that ran would pass: a refusal that ran one reads as a pass here

    def push_feat_files(self, files):
        """One commit on origin's feat, made from origin/feat with `files` ({path: text}) written: the head's git tree holds them.
        The lane checkout fetches it. -> the pushed sha."""
        o = self.other
        tm.sh(o, "git", "fetch", "-q", "origin")
        tm.sh(o, "git", "checkout", "-q", "-B", "feat", "origin/feat")
        for path, text in files.items():
            tm.put(os.path.join(o, *path.split("/")), text)
        tm.sh(o, "git", "add", "-A")
        tm.sh(o, "git", "commit", "-q", "-m", "feat: files the lint tree is made without")
        tm.sh(o, "git", "push", "-q", "origin", "feat")
        tm.sh(self.co, "git", "fetch", "-q", "origin")
        return tm.sh(o, "git", "rev-parse", "HEAD")

    def lint(self, head, *extra, missing=()):
        """merge --lane-lint <head> through main(), the lint tree made without `missing`. -> (rc, stdout and stderr together)."""
        with missing_from_lint_tree(missing):
            return self.run_lane("--lane-lint", head, *extra)

    def test_a_head_holding_the_floor_check_whose_lint_tree_lacks_it_exits_1_names_the_file_as_unknown_and_runs_no_step(self):
        head = self.push_feat_files({FLOOR_CHECK: LINT_TREE_FILE_TEXT})
        self.assertEqual(tm.sh(self.co, "git", "ls-tree", "--name-only", head, "--", FLOOR_CHECK), FLOOR_CHECK,
                         "the head's tree does not hold the file the lint tree is made without")
        rc, text = self.lint(head, missing=(FLOOR_CHECK,))
        self.assertEqual(rc, 1, "a lint tree that lacks a file its head holds exits %r, want 1: %s" % (rc, text))
        self.assertIn("unknown", text, "the refusal does not say unknown: " + text)
        self.assertIn(FLOOR_CHECK, text, "the refusal does not name the missing file: " + text)
        self.assertEqual(pass_lines(text), [], "a lint of a tree missing its file read as a pass: " + text)
        self.assertEqual(self.lint_calls(), [], "a lint step ran after its tree was found missing a file: " + text)

    def test_a_reason_does_not_lift_the_missing_floor_check_file(self):
        head = self.push_feat_files({FLOOR_CHECK: LINT_TREE_FILE_TEXT})
        self.assertEqual(tm.sh(self.co, "git", "ls-tree", "--name-only", head, "--", FLOOR_CHECK), FLOOR_CHECK,
                         "the head's tree does not hold the file the lint tree is made without")
        rc, text = self.lint(head, "--lint-unknown-ok", "a reason the lint must not take", missing=(FLOOR_CHECK,))
        self.assertNotEqual(rc, 0, "--lint-unknown-ok lifted a lint tree that lacks a file its head holds: " + text)
        self.assertEqual(rc, 1, "a refusal that the reason does not lift exits %r, want 1: %s" % (rc, text))
        self.assertIn("unknown", text, "the refusal does not say unknown: " + text)
        self.assertIn(FLOOR_CHECK, text, "the refusal does not name the missing file: " + text)
        self.assertEqual(pass_lines(text), [], "a lint of a tree missing its file read as a pass: " + text)
        self.assertEqual(self.lint_calls(), [], "a lint step ran after its tree was found missing a file: " + text)

    def test_a_head_holding_the_workflow_whose_lint_tree_lacks_it_exits_1_names_the_file_as_unknown_and_runs_no_step(self):
        head = self.push_feat_files({WORKFLOW_PATH: WORKFLOW})
        self.assertEqual(tm.sh(self.co, "git", "ls-tree", "--name-only", head, "--", WORKFLOW_PATH), WORKFLOW_PATH,
                         "the head's tree does not hold the workflow the lint tree is made without")
        rc, text = self.lint(head, missing=(WORKFLOW_PATH,))
        self.assertEqual(rc, 1, "a lint tree that lacks the workflow its head holds exits %r, want 1: %s" % (rc, text))
        self.assertIn("unknown", text, "the refusal does not say unknown: " + text)
        self.assertIn(WORKFLOW_PATH, text, "the refusal does not name the missing workflow: " + text)
        self.assertEqual(pass_lines(text), [], "a lint of a tree missing its workflow read as a pass: " + text)
        self.assertEqual(self.lint_calls(), [], "a lint step ran after its tree was found missing the workflow: " + text)

    def test_a_head_whose_tree_never_held_those_files_is_not_stopped_by_this_check(self):  # the control: green on the old code
        head = self.head("feat")
        self.assertEqual(tm.sh(self.co, "git", "ls-tree", "--name-only", head, "--", FLOOR_CHECK, WORKFLOW_PATH), "",
                         "the head's tree holds a lint-tree file, so this is not the control")
        rc, text = self.lint(head)
        self.assertEqual(rc, 0, "a head that never held the lint-tree files was refused: " + text)
        self.assertEqual(len(pass_lines(text)), 1, text)
        self.assertEqual(len(self.lint_calls()), 1, "the lint did not run once on the control head: " + text)


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

    def test_a_ready_check_that_reads_the_pr_body_gets_the_pull_requests_body(self):
        """The ready check's ci-job run gets the PR's body in its body file (CI_JOB_PR_BODY_FILE), as the PR's own lint does, so a step
        that reads the body (silent-undo) sees the body it sees in CI."""
        body = "Summary.\n\nDrops-lines: docs/decisions/first.md -- the lines are dead\n"
        self.host.body = body
        self.declare(["Silent undo check"])
        self.stale_feat()
        self.use_ci_job([("PASS", "Silent undo check")], 0)
        rc, out = self.draft_confirm()
        runs = self.lint_calls()
        self.assertEqual(len(runs), 1, "the ready check did not run ci-job once: " + out)
        self.assertIsNotNone(runs[0].get("pr_body"), "the ready check's ci-job run named no body file (CI_JOB_PR_BODY_FILE was unset)")
        self.assertEqual(runs[0].get("pr_body"), body, "the ready check's ci-job run got a different body than the PR's")
        self.assertEqual(rc, 0, out)

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


class BatchReadyBody(CiJobStub, unittest.TestCase):
    """`merge --batch-build --ready` runs the repo's ready checks on the batch head through ci-job. A batch has no PR body, so the run
    gives ci-job an empty body file: the empty body is known, and a step that reads the body sees "", not an unread body."""

    def setUp(self):
        self.t = tempfile.mkdtemp(prefix="batch-ready-body-", dir=_test_temp.run_folder())
        self.addCleanup(shutil.rmtree, self.t, True)
        self.init_stub()

    def test_the_batch_ready_checks_give_ci_job_an_empty_body_file(self):
        self.use_ci_job([("PASS", "Silent undo check")], 0)
        wt = os.path.join(self.t, "wt")
        os.makedirs(wt)
        cfg = {"merge": {"readyChecks": ["Silent undo check"]}}
        with unittest.mock.patch.object(merge, "fetch_branch", lambda *a, **k: "deadbeef"), \
                unittest.mock.patch.object(merge, "add_worktree", lambda root, head: (self.t, wt)), \
                unittest.mock.patch.object(merge, "drop_worktree", lambda *a, **k: None), contextlib.redirect_stdout(io.StringIO()):
            merge.batch_ready_checks(self.t, cfg, 7, "batch", "batch-branch", "main")
        runs = self.lint_calls()
        self.assertEqual(len(runs), 1, "the batch's ready checks ran ci-job %d times, want once" % len(runs))
        self.assertIsNotNone(runs[0].get("pr_body"), "the batch's ready checks named no body file for ci-job (CI_JOB_PR_BODY_FILE was unset)")
        self.assertEqual(runs[0]["pr_body"], "", "the batch's ready checks gave ci-job a body of %r, want the empty body a batch has" % (runs[0]["pr_body"],))


class LaneLintRepoDir(tm.RepoDirRuns, LaneFixture):
    """`merge --lane-lint` with -C PATH or --repo-dir PATH lints the named checkout's pull request. Its worktree is cut from that checkout at
    its head, and the pull request is read through a host in that checkout. The stub logs the head it linted, so a case reads which head that was."""

    def setUp(self):
        super().setUp()
        self.b_co, self.b_other = tm.second_checkout(os.path.join(self.t, "mailaudit"))
        self.assertNotEqual(self.head("feat"), self.b_feat(), "fixture: both checkouts' feat heads are the same")

    def b_feat(self):
        return tm.sh(self.b_co, "git", "ls-remote", "origin", "refs/heads/feat").split("\t")[0]

    def test_without_the_flag_the_lint_cuts_its_worktree_from_the_process_directory(self):
        """A control: with no flag, the process directory is the checkout, and its head is the one linted."""
        self.use_ci_job(PASSING, 0)
        if os.path.exists(self.log):
            os.remove(self.log)
        rc, out, seen = self.run_from(self.b_co, ["--lane-lint", "7"])
        self.assertEqual(rc, 0, out)
        self.assertEqual([c["head"] for c in self.lint_calls()], [self.b_feat()], "the lint did not run at the process directory's head")

    def test_the_lint_cuts_its_worktree_from_the_named_checkout_at_its_head(self):
        self.use_ci_job(PASSING, 0)
        for argv in self.spellings("--lane-lint", "7"):
            with self.subTest(spelling=argv[0]):
                if os.path.exists(self.log):
                    os.remove(self.log)
                rc, out, seen = self.run_from(self.co, argv)
                self.assertEqual(rc, 0, out)
                self.assertEqual([c["head"] for c in self.lint_calls()], [self.b_feat()],
                                 "the lint did not run at the named checkout's pull request head")

    def test_the_lint_reads_the_pull_request_through_a_host_in_the_named_checkout(self):
        self.use_ci_job(PASSING, 0)
        for argv in self.spellings("--lane-lint", "7"):
            with self.subTest(spelling=argv[0]):
                rc, out, seen = self.run_from(self.co, argv, tree=True)  # the read comes before the worktree: the stop ends the run there
                self.assertTrue(seen["hosts"], "the lane lint built no host, so it did not read the named checkout: " + out)
                cwd = seen["hosts"][0].built_with.get("cwd")
                self.assertEqual(cwd, self.b_co, "the lane lint's pull request read ran in %r, not the named checkout" % (cwd,))


class DraftRun(LaneFixture):
    """`merge --lane-lint <pr>` reads the draft's touched-tests run at the lane's live head (decision lanes-run-no-full-ci-job; workflow
    lane-touched-tests.yml). A failed `run (windows-latest)` or `run (macos-latest)` row refuses the lane and names its link. A row not yet
    finished, or no touched row on the head, is unknown: refused, and lifted only by --lint-unknown-ok. A run on an older head is never read
    for the live one. A ref or commit target reads nothing. Each case scripts the rows of each head in self.host.draft_rows (FakeHost's
    default is a pass, so the other cases keep their lane). The cases read the scripted rows through the real Host judge (tm.DraftRunReads)."""

    def run_case(self, rows, *argv):
        """Runs merge on argv in the lane checkout with `rows` as each head's draft rows (None: no rows scripted, a pass). Clears the reads and the
        lint's log first, so each run reads alone. -> (rc, stdout and stderr together)."""
        self.host.draft_rows, self.host.draft_reads = rows, []
        if os.path.exists(self.log):
            os.remove(self.log)
        return self.run_lane(*argv)

    def refused_by_failed_run(self, name):
        self.use_ci_job(PASSING, 0)
        head = self.head("feat")
        rows = {head: [tm.draft_row("touched"), tm.draft_row(name, "failure", job=2)]}
        rc, out = self.run_case(rows, "--lane-lint", "7")
        self.assertEqual(tm.check_run_reads(self.host.draft_reads), [head], "the lint did not read the draft's runs of the live head for a %s failure:\n%s" % (name, out))
        self.assertEqual(rc, 1, "a failed %s run on the live head did not refuse the lane (exit %s):\n%s" % (name, rc, out))
        self.assertIn(tm.job_link(tm.DRAFT_RUN, 2), out, "the refusal of a failed %s run does not name its link:\n%s" % (name, out))
        self.assertEqual(self.lint_calls(), [], "the lint ran past a failed %s run:\n%s" % (name, out))
        self.assertEqual(pass_lines(out), [], "a lane with a failed %s run printed a PASS line:\n%s" % (name, out))

    def test_a_failed_windows_run_on_the_live_head_refuses_the_lane_and_names_its_link(self):
        self.refused_by_failed_run("run (windows-latest)")

    def test_a_failed_macos_run_on_the_live_head_refuses_the_lane_and_names_its_link(self):
        self.refused_by_failed_run("run (macos-latest)")

    def test_a_draft_whose_touched_job_passed_and_that_ran_no_test_job_passes_on_one_read_of_its_head(self):
        self.use_ci_job(PASSING, 0)
        head = self.head("feat")
        rc, out = self.run_case({head: [tm.draft_row("touched")]}, "--lane-lint", "7")
        self.assertEqual(self.host.draft_reads, [f"commits/{head}/check-runs"], "the lint did not read the live head's check runs once, and no status:\n" + out)
        self.assertEqual(rc, 0, "a draft with a passed touched job and no test job was refused (exit %s):\n%s" % (rc, out))
        self.assertEqual(len(pass_lines(out)), 1, out)

    def test_test_job_rows_that_passed_or_skipped_do_not_refuse_the_lane(self):
        self.use_ci_job(PASSING, 0)
        head = self.head("feat")
        for name, conclusion in (("run (windows-latest)", "success"), ("run (macos-latest)", "skipped")):
            with self.subTest(job=name, conclusion=conclusion):
                rc, out = self.run_case({head: [tm.draft_row("touched"), tm.draft_row(name, conclusion, job=2)]}, "--lane-lint", "7")
                self.assertEqual(tm.check_run_reads(self.host.draft_reads), [head], "the lint did not read the live head's draft runs:\n" + out)
                self.assertEqual(rc, 0, "a %s %s row refused the lane (exit %s):\n%s" % (name, conclusion, rc, out))
                self.assertEqual(len(pass_lines(out)), 1, out)

    def test_a_draft_run_not_yet_finished_waits_and_is_lifted_only_by_a_reason(self):
        self.use_ci_job(PASSING, 0)
        head = self.head("feat")
        cases = (("touched", [tm.draft_row("touched", status="in_progress")]),
                 ("run (windows-latest)", [tm.draft_row("touched"), tm.draft_row("run (windows-latest)", status="in_progress", job=2)]))
        for name, head_rows in cases:
            with self.subTest(job=name):
                rc, out = self.run_case({head: head_rows}, "--lane-lint", "7")
                self.assertEqual(tm.check_run_reads(self.host.draft_reads), [head], "the lint did not read the live head's draft runs for an unfinished %s:\n%s" % (name, out))
                self.assertEqual(rc, 1, "an unfinished %s did not refuse the lane (exit %s):\n%s" % (name, rc, out))
                self.assertNotIn("FAILs:", out, "an unfinished %s was read as a failed lint:\n%s" % (name, out))
                self.assertIn(name, out, "the refusal does not name the unfinished %s:\n%s" % (name, out))
                self.assertIn("--lint-unknown-ok", out, "the refusal of an unfinished %s cannot be lifted by name:\n%s" % (name, out))
                self.assertEqual(self.lint_calls(), [], "the lint ran past an unfinished %s:\n%s" % (name, out))
                rc, out = self.run_case({head: head_rows}, "--lane-lint", "7", "--lint-unknown-ok", "the windows run is still going")
                self.assertEqual(rc, 0, "a reason did not lift an unfinished %s (exit %s):\n%s" % (name, rc, out))
                self.assertIn("the windows run is still going", out, "the reason that lifted an unfinished %s is not logged:\n%s" % (name, out))
                self.assertEqual(len(self.lint_calls()), 1, "the lint did not run once after an unfinished %s was lifted:\n%s" % (name, out))

    def test_no_touched_row_on_the_live_head_is_unknown_and_is_lifted_only_by_a_reason(self):
        self.use_ci_job(PASSING, 0)
        head = self.head("feat")
        cases = (("no rows on the head", {}),
                 ("a run row and no touched row", {head: [tm.draft_row("run (windows-latest)", job=2)]}))
        for label, rows in cases:
            with self.subTest(case=label):
                rc, out = self.run_case(rows, "--lane-lint", "7")
                self.assertEqual(tm.check_run_reads(self.host.draft_reads), [head], "the lint did not read the live head's draft runs (%s):\n%s" % (label, out))
                self.assertEqual(rc, 1, "%s did not refuse the lane (exit %s):\n%s" % (label, rc, out))
                self.assertNotIn("FAILs:", out, "%s was read as a failed lint:\n%s" % (label, out))
                self.assertIn("--lint-unknown-ok", out, "%s cannot be lifted by name:\n%s" % (label, out))
                self.assertEqual(self.lint_calls(), [], "the lint ran past %s:\n%s" % (label, out))
                rc, out = self.run_case(rows, "--lane-lint", "7", "--lint-unknown-ok", "no touched row yet")
                self.assertEqual(rc, 0, "a reason did not lift %s (exit %s):\n%s" % (label, rc, out))

    def stale_head_case(self, old_rows):
        """The lane's head moves after its draft run was judged: the old head has `old_rows`, the live head has none. -> (rc, output)."""
        self.use_ci_job(PASSING, 0)
        old = self.head("feat")
        self.competitor_push()
        new = self.head("feat")
        self.assertNotEqual(new, old, "setup: the push did not move the lane's head")
        rc, out = self.run_case({old: old_rows}, "--lane-lint", "7")
        self.assertEqual(tm.check_run_reads(self.host.draft_reads), [new], "the lint read the draft's runs of the old head, not the live head:\n" + out)
        self.assertNotIn(tm.job_link(tm.DRAFT_RUN, 2), out, "the lint named a run of the old head for the live head:\n" + out)
        self.assertEqual(rc, 1, "a run on an older head counted for the live head (exit %s):\n%s" % (rc, out))
        self.assertNotIn("FAILs:", out, "a run on an older head was read as a failed lint for the live head:\n" + out)
        self.assertIn("--lint-unknown-ok", out, "the live head's missing run cannot be lifted by name:\n" + out)
        self.assertEqual(self.lint_calls(), [], "the lint ran past a live head with no draft run:\n" + out)
        return rc, out

    def test_a_green_run_on_an_older_head_is_not_read_for_the_live_head(self):
        self.stale_head_case([tm.draft_row("touched"), tm.draft_row("run (windows-latest)", job=2)])

    def test_a_red_run_on_an_older_head_is_not_read_for_the_live_head(self):
        self.stale_head_case([tm.draft_row("touched"), tm.draft_row("run (windows-latest)", "failure", job=2)])

    def test_a_ref_target_reads_no_draft_run_so_a_failed_run_on_its_sha_does_not_refuse(self):  # control: green on the old code
        self.use_ci_job(PASSING, 0)
        sha = self.head("feat")
        rc, out = self.run_case({sha: [tm.draft_row("touched"), tm.draft_row("run (windows-latest)", "failure", job=2)]}, "--lane-lint", sha)
        self.assertEqual(self.host.draft_reads, [], "a ref target read the draft's runs:\n" + out)
        self.assertEqual(rc, 0, "a ref target refused on a failed draft run it does not read (exit %s):\n%s" % (rc, out))

    def real_host_run(self, rows, *argv):
        """-> (rc, output) of merge with the real Host, which reads the head's check runs through the gh shim. The shim answers `rows` for every
        read, so a head of more than one page serves the same rows on each page. Run outside the cloud, as LintPostsPassComment runs its real-host cases."""
        tm.install_gh_shim(self)
        tm.GhHalf.set(self, checks_seq=[rows])
        with self.cloud(CLAUDE_CODE_REMOTE=None):
            rc, out = self.run_merge(*argv, host=merge.Host())
        return rc, out

    def test_a_real_host_reads_a_failed_windows_run_on_page_two_of_the_head_rows(self):
        head = self.head("feat")
        link = tm.job_link(tm.DRAFT_RUN, 2)
        rows = [("touched", "pass", "")] + [("lint-%d" % k, "pass", "") for k in range(100)] + [("run (windows-latest)", "fail", link)]
        self.use_ci_job(PASSING, 0)
        rc, out = self.real_host_run(rows, "--lane-lint", "7")
        calls = tm.GhHalf.calls(self).splitlines()
        self.assertTrue(any(line.startswith(f"GET commits/{head}/check-runs") and "page=2" in line for line in calls),
                        "the lint did not read page 2 of the live head's check runs:\n" + "\n".join(calls))
        self.assertEqual(rc, 1, "a failed windows run on page 2 did not refuse the lane (exit %s):\n%s" % (rc, out))
        self.assertIn(link, out, "the refusal does not name the failed run's link:\n" + out)

    def test_a_real_host_passes_the_same_rows_when_the_windows_run_passed(self):  # control: green on the old code
        self.head("feat")
        rows = [("touched", "pass", "")] + [("lint-%d" % k, "pass", "") for k in range(100)] + [("run (windows-latest)", "pass", tm.job_link(tm.DRAFT_RUN, 2))]
        self.use_ci_job(PASSING, 0)
        rc, out = self.real_host_run(rows, "--lane-lint", "7")
        self.assertEqual(rc, 0, "a passed windows run on page 2 refused the lane (exit %s):\n%s" % (rc, out))
        self.assertEqual(len(pass_lines(out)), 1, out)

    def test_a_skipped_touched_row_with_no_test_rows_is_unknown_and_is_lifted_only_by_a_reason(self):
        self.use_ci_job(PASSING, 0)
        head = self.head("feat")
        rows = {head: [tm.draft_row("touched", "skipped")]}
        rc, out = self.run_case(rows, "--lane-lint", "7")
        self.assertEqual(tm.check_run_reads(self.host.draft_reads), [head], "the lint did not read the live head's draft runs:\n" + out)
        self.assertEqual(rc, 1, "a lane whose touched job was skipped, as a ready lane's is, passed the lint with no proof a touched test ran (exit %s):\n%s" % (rc, out))
        self.assertNotIn("FAILs:", out, "a skipped touched job was read as a failed lint:\n" + out)
        self.assertIn("--lint-unknown-ok", out, "the refusal of a skipped touched job cannot be lifted by name:\n" + out)
        self.assertEqual(self.lint_calls(), [], "the lint ran past a skipped touched job:\n" + out)
        rc, out = self.run_case(rows, "--lane-lint", "7", "--lint-unknown-ok", "the skipped touched job is accepted")
        self.assertEqual(rc, 0, "a reason did not lift a skipped touched job (exit %s):\n%s" % (rc, out))
        self.assertIn("the skipped touched job is accepted", out, "the reason that lifted a skipped touched job is not logged:\n" + out)

    def test_a_batch_integration_pr_reads_no_draft_run_and_its_queued_or_missing_touched_row_does_not_refuse_it(self):
        self.use_ci_job(PASSING, 0)
        head = self.head("feat")
        branch = merge.integration_branch("nightly")
        tm.sh(self.other, "git", "fetch", "-q", "origin")
        tm.sh(self.other, "git", "push", "-q", "origin", "%s:refs/heads/%s" % (head, branch))
        base = tm.sh(self.other, "git", "rev-parse", "origin/main")
        self.host.branch, self.host.body = branch, "\n".join(merge.freeze_lines("nightly", {6: base})) + "\n"
        self.assertTrue(merge.is_integration_pr({"branch": self.host.branch, "body": self.host.body}),
                        "precondition: PR 7 is not a batch integration PR, so the case probes a lane PR")
        cases = (("its touched job queued", [tm.draft_row("touched", status="queued")]), ("no rows on the head", []))
        for label, head_rows in cases:
            with self.subTest(case=label):
                rc, out = self.run_case({head: head_rows}, "--lane-lint", "7")
                self.assertEqual(self.host.draft_reads, [], "the lint read the draft runs of a batch integration PR's head (%s):\n%s" % (label, out))
                self.assertEqual(rc, 0, "a batch integration PR with %s was refused (exit %s):\n%s" % (label, rc, out))
                self.assertEqual(len(pass_lines(out)), 1, out)

    def test_a_failed_windows_or_macos_run_is_not_lifted_by_a_reason_and_is_named_as_a_failure(self):  # control: green on the old code
        self.use_ci_job(PASSING, 0)
        head = self.head("feat")
        for name, job in (("run (windows-latest)", 2), ("run (macos-latest)", 3)):
            with self.subTest(job=name):
                rows = {head: [tm.draft_row("touched"), tm.draft_row(name, "failure", job=job)]}
                rc, out = self.run_case(rows, "--lane-lint", "7", "--lint-unknown-ok", "the run is still going")
                self.assertEqual(rc, 1, "a reason lifted a failed %s run (exit %s):\n%s" % (name, rc, out))
                self.assertIn("FAILs:", out, "the refusal of a failed %s run does not read as a FAIL:\n%s" % (name, out))
                self.assertIn(tm.job_link(tm.DRAFT_RUN, job), out, "the refusal of a failed %s run does not name its link:\n%s" % (name, out))
                self.assertNotIn("is unknown", out, "a failed %s run was refused as unknown:\n%s" % (name, out))
                self.assertNotIn("not finished", out, "a failed %s run was refused as unfinished:\n%s" % (name, out))
                self.assertEqual(self.lint_calls(), [], "the lint ran past a failed %s run:\n%s" % (name, out))
                self.assertEqual(pass_lines(out), [], "a lane with a failed %s run printed a PASS line:\n%s" % (name, out))

    def test_a_rerun_of_a_test_job_is_judged_by_its_newest_row_in_either_order(self):  # control: green on the old code
        self.use_ci_job(PASSING, 0)
        head = self.head("feat")
        failed_older, passed_newer = tm.draft_row("run (windows-latest)", "failure", job=2), tm.draft_row("run (windows-latest)", job=5)
        passed_older, failed_newer = tm.draft_row("run (windows-latest)", job=2), tm.draft_row("run (windows-latest)", "failure", job=5)
        cases = (("older failed, newer passed", (failed_older, passed_newer), 0),
                 ("older passed, newer failed", (passed_older, failed_newer), 1))
        for label, pair, want_rc in cases:
            for order in (pair, pair[::-1]):  # each pair in both list orders: a mutant that takes the first listed row fails one of them
                with self.subTest(case=label, listed=[r["id"] for r in order]):
                    rows = {head: [tm.draft_row("touched"), *order]}
                    rc, out = self.run_case(rows, "--lane-lint", "7")
                    self.assertEqual(rc, want_rc, "a re-run (%s) gave exit %s, want %s:\n%s" % (label, rc, want_rc, out))


class DraftRunJobNames(unittest.TestCase):
    """The job names the draft judge reads (merge.Host.DRAFT_TOUCHED, merge.Host.DRAFT_TEST_JOB) match the jobs of lane-touched-tests.yml. A renamed job
    leaves the judge no row to read, so a red run is skipped or a lane waits with no end. The workflow is read with workflow_steps, the one step parser,
    and the selector's OS names with ast. The pin passes on today's names; its red is a mutant of a name, run on a scratch copy."""

    ROOT = os.path.dirname(HERE)

    def read_workflow(self):
        with open(os.path.join(self.ROOT, ".github", "workflows", "lane-touched-tests.yml"), encoding="utf-8") as f:
            return f.read()

    def check_run_name(self, block, job):
        """The name GitHub gives a job's check run: its `name:` line when it has one, else the job's id."""
        m = re.search(r"^    name:[ \t]*(.*?)[ \t]*$", block, re.M)
        return m.group(1) if m else job

    def test_the_touched_job_is_the_check_run_the_judge_reads(self):
        block = job_block(self.read_workflow(), "touched")
        self.assertIsNotNone(block, "lane-touched-tests.yml has no `touched` job, so the judge reads no touched row")
        self.assertEqual(self.check_run_name(block, "touched"), merge.Host.DRAFT_TOUCHED,
                         "the touched job's check run is not named the judge's DRAFT_TOUCHED")

    def test_each_windows_or_macos_test_job_the_selector_names_is_one_the_judge_matches(self):
        block = job_block(self.read_workflow(), "run")
        self.assertIsNotNone(block, "lane-touched-tests.yml has no `run` job, so the judge reads no test row")
        template = self.check_run_name(block, "run")
        self.assertIn("${{ matrix.os }}", template, "the test job's name is not built from the matrix os: %r" % template)
        with open(os.path.join(self.ROOT, ".github", "scripts", "touched-tests.py"), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        oses = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.endswith("-latest")}
        self.assertTrue({"windows-latest", "macos-latest"} <= oses, "the selector names no windows or macos matrix entry: %s" % sorted(oses))
        for os_name in sorted(o for o in oses if not o.startswith("ubuntu")):  # the Linux lint runs ubuntu's own tests, so no row of it is read
            shown = template.replace("${{ matrix.os }}", os_name)
            with self.subTest(os=os_name):
                self.assertIsNotNone(merge.Host.DRAFT_TEST_JOB.match(shown),
                                     "the judge reads no test job named %r, so a red %s run is skipped" % (shown, os_name))


def other_comment(cid, n=7):
    """A comment that is no lint: the filler that pushes a later comment onto the next page."""
    return {"id": cid, "created_at": "2026-10-02T00:00:00Z", "issue_url": f"https://api.github.com/repos/o/r/issues/{n}",
            "body": "LGTM", "user": {"login": NOT_OWNER["login"]}, "author_association": NOT_OWNER["association"]}


class LintPostsPassComment(CiJobStub, tm.CloudSession):
    """`merge --lane-lint <pr>` posts one comment on the pull request when the lint passes (decision lanes-run-no-full-ci-job): the marker, the
    head the lint read, and the verdict. A FAIL, an unknown (with or without a reason) and a commit target post nothing. The lint still runs
    once, through lane_lint. The fake host's post_comment records each post; the real-Host case reads its comment through the gh shim.
    setUp mirrors LaneLint.setUp, because subclassing LaneLint would run its cases again."""

    @classmethod
    def setUpClass(cls):
        unittest.TestCase.setUpClass()  # not CloudSession's: it would make a second run folder
        cls.run_dir = RUN_FOLDER

    def setUp(self):
        with unittest.mock.patch.object(tempfile, "tempdir", RUN_FOLDER):
            super().setUp()
        self.lock = NoLock()
        self.init_stub()
        self.posts = []
        self.host.post_comment = lambda n, body: self.posts.append((n, body))  # the fake host's seam, recorded for each case

    def lane(self, *argv, host=None):
        """-> (rc, stdout and stderr together) of merge in the lane checkout, outside the cloud as LaneLint runs it. host None is the fake."""
        out, err = io.StringIO(), io.StringIO()
        with self.cloud(CLAUDE_CODE_REMOTE=None):
            try:
                rc = self.run_merge(*argv, host=host, stdout=out, stderr=err)[0]
            except SystemExit as e:
                rc = e.code
        return rc, out.getvalue() + err.getvalue()

    def assert_pass_comment(self, posts, head, out):
        """`posts` holds one (pull request, body) pair: the body opens with the marker, names the head the lint read, and says PASS."""
        self.assertEqual(len(posts), 1, "lane-lint on a PASS posted %d comments, want one:\n%s" % (len(posts), out))
        n, body = posts[0]
        self.assertEqual(int(n), 7, "the comment went to pull request %s, not #7" % n)
        lines = body.splitlines()
        self.assertEqual(lines[:1], [LANE_LINT_MARKER], "the comment does not open with the lane-lint marker:\n" + body)
        self.assertIn(f"Head: {head}", lines, "the comment does not name the head the lint read:\n" + body)
        self.assertIn("Result: PASS", lines, "the comment does not say PASS:\n" + body)

    def test_a_pass_posts_one_comment_naming_the_marker_the_head_and_the_verdict(self):
        head = self.head("feat")
        self.use_ci_job(PASSING, 0)
        rc, out = self.lane("--lane-lint", "7")
        self.assertEqual(rc, 0, out)
        self.assert_pass_comment(self.posts, head, out)

    def test_a_real_host_posts_the_pass_as_one_rest_comment_on_the_pull_request(self):
        tm.install_gh_shim(self)
        tm.GhHalf.set(self, checks_seq=[[("touched", "pass", "")]])  # the draft's touched job passed: the lint's read of the head's draft run
        head = self.head("feat")
        self.use_ci_job(PASSING, 0)
        rc, out = self.lane("--lane-lint", "7", host=merge.Host())
        self.assertEqual(rc, 0, out)
        posted = [(p["n"], p["body"]) for p in (tm.GhHalf.gh_state(self, "posted") or [])]
        self.assert_pass_comment(posted, head, out)

    def test_a_fail_posts_no_comment_and_refuses(self):  # control: green on the old code
        self.use_ci_job(FAILING, 1)
        rc, out = self.lane("--lane-lint", "7")
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.posts, [], "a FAIL posted a comment:\n" + out)

    def test_an_unknown_posts_no_comment_and_refuses(self):  # control: green on the old code
        self.use_ci_job(UNKNOWN, 2)
        rc, out = self.lane("--lane-lint", "7")
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.posts, [], "an unknown posted a comment:\n" + out)

    def test_an_unknown_lifted_by_a_reason_posts_no_comment(self):  # control: green on the old code
        self.use_ci_job(UNKNOWN, 2)
        rc, out = self.lane("--lane-lint", "7", "--lint-unknown-ok", "shellcheck is not installed on this machine")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.posts, [], "an unknown lifted by a reason posted a comment:\n" + out)

    def test_a_commit_target_that_passes_posts_no_comment(self):  # control: green on the old code
        self.use_ci_job(PASSING, 0)
        rc, out = self.lane("--lane-lint", self.head("feat"))
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.posts, [], "a commit target posted a comment, and it has no pull request:\n" + out)

    def test_a_failed_post_after_a_pass_prints_the_pass_and_a_reason_and_exits_zero(self):
        tm.install_gh_shim(self)
        tm.GhHalf.set(self, post_fail=tm.rest_err(502, "Bad Gateway"), checks_seq=[[("touched", "pass", "")]])
        head = self.head("feat")
        self.use_ci_job(PASSING, 0)
        rc, out = self.lane("--lane-lint", "7", host=merge.Host())
        self.assertEqual(rc, 0, "a PASS whose comment failed to post did not exit 0:\n" + out)
        self.assertTrue(pass_lines(out), "a PASS whose comment failed to post printed no PASS line:\n" + out)
        reasons = [l for l in out.splitlines() if "lane-lint" in l.lower() and "comment" in l.lower() and not l.startswith("PASS:")]
        self.assertTrue(reasons, "a PASS whose comment failed to post printed no reason line that names the lane-lint comment:\n" + out)
        printed = out[out.index(reasons[0]):]  # the reason on, where the comment body to post by hand must print
        for part in (LANE_LINT_MARKER, "PR: #7", f"Head: {head}", "Result: PASS"):
            self.assertIn(part, printed, "a failed post printed no `%s` line of the comment body to post by hand, after the reason:\n%s" % (part, out))
        self.assertEqual(tm.GhHalf.gh_state(self, "posted") or [], [], "the failed post was kept as a posted comment")


class LintCheckReviewed(tm.ReviewEnv):
    """`merge --reviewed` leaves a pull request not done unless a lane-lint PASS names its live head (decision lanes-run-no-full-ci-job). The
    one review record here is done, so only the lint comment decides. A PASS for an older head, a FAIL, and a PASS by a non-owner each leave
    the pull request not done, and name `merge --lane-lint 7`. The lint comments come from the one comment list read the records use (decision
    pr-review-record, the cost)."""

    def listing(self, comments, head=tm.REVIEW_HEAD):
        """-> (rc, stdout and stderr, host) of `merge --reviewed` for pull request 7 at `head`: one done review record, then `comments`."""
        record = tm.review_comment(1, 7, tm.record_text(rounds=tm.REVIEW_PASS))
        host = tm.PullsHost([tm.batch_pull(7, head)], {}, comments=[record, *comments])
        rc, out, err = self.run_args("--reviewed", host=host)
        return rc, out + err, host

    def assert_not_ready(self, out):
        self.assertNotIn(" done: ", tm.list_line(self, out, 7), "#7 reads done with no lane-lint PASS at its live head:\n" + out)
        self.assertIn("merge --lane-lint 7", out, "#7 is not ready, and no line names `merge --lane-lint 7`:\n" + out)

    def test_a_lint_result_with_no_readable_verdict_shows_lint_unknown_and_is_not_done(self):
        unreadable = dict(lint_comment(2, tm.REVIEW_HEAD), body=f"{LANE_LINT_MARKER}\nPR: #7\nHead: {tm.REVIEW_HEAD}\n")  # no Result line
        rc, out, host = self.listing([unreadable])
        self.assertEqual(rc, 0, out)
        line = tm.list_line(self, out, 7)
        self.assertIn("lint unknown", line, "#7 does not read lint unknown when its lint comment at the live head has no readable result:\n" + out)
        self.assertNotIn(" done: ", line, "#7 reads done with an unreadable lint result at its live head:\n" + out)

    def test_a_done_record_with_no_lint_pass_is_not_ready_and_names_the_lane_lint(self):
        rc, out, host = self.listing([])
        self.assertEqual(rc, 0, out)
        self.assert_not_ready(out)

    def test_a_lint_pass_at_the_live_head_leaves_a_done_record_done_with_no_remedy(self):  # control: green on the old code
        rc, out, host = self.listing([lint_comment(2, tm.REVIEW_HEAD)])
        self.assertEqual(rc, 0, out)
        self.assertIn(" done: ", tm.list_line(self, out, 7), out)
        self.assertNotIn("merge --lane-lint 7", out, "a pull request with its lint PASS at the live head is told to lint again:\n" + out)

    def test_a_lint_pass_for_an_older_head_does_not_make_the_live_head_ready(self):
        rc, out, host = self.listing([lint_comment(2, tm.REVIEW_OLD_HEAD)])
        self.assertEqual(rc, 0, out)
        self.assert_not_ready(out)

    def test_a_lint_fail_at_the_live_head_does_not_make_it_ready(self):
        rc, out, host = self.listing([lint_comment(2, tm.REVIEW_HEAD, verdict="FAIL")])
        self.assertEqual(rc, 0, out)
        self.assert_not_ready(out)

    def test_a_lint_pass_by_a_non_owner_does_not_make_the_live_head_ready(self):
        rc, out, host = self.listing([lint_comment(2, tm.REVIEW_HEAD, by=NOT_OWNER)])
        self.assertEqual(rc, 0, out)
        self.assert_not_ready(out)


class LintCheckJoin(tm.CloudSession):
    """The batch runner's join: `merge <pr> --confirm` in a cloud session with the batch-runner role refuses a pull request whose live head has
    no lane-lint PASS (decision lanes-run-no-full-ci-job). The refusal comes before any claim, push or merge, and names `merge --lane-lint <pr>`.
    The comment list is read through the gh shim, the list the review record reads. A failed read of it refuses the join as lane lint unknown. GhHalf's helpers are called unbound and its setUp is mirrored: subclassing GhHalf would run its cases again."""

    def setUp(self):
        super().setUp()
        tm.gh_case_setup(self)  # GhHalf's setUp: the shim on PATH, the wait's clock, and one green check

    def join(self, comments, ran_on=None, once=False, **state):
        """-> (rc, stdout and stderr) of `merge 7 --confirm --head <ran_on>` run by the batch runner, with `comments` as the repo's issue comments.
        `ran_on` defaults to the live head of feat, read when the call is made (main's runner_confirm does the same). once: one run of
        merge, so a join that pushes its claim stops there (two-step confirm), where the default runs both steps."""
        tm.GhHalf.set(self, issue_comments=comments, **state)
        self.put_role("batch-runner")
        ran_on = ran_on or self.head("feat")
        run = self.run_merge_once if once else self.run_merge
        with self.cloud():
            return run("7", "--confirm", "--head", ran_on, host=tm.GhHalf.gh_host(self))

    def claim_steps(self, linted, claimed):
        """Two joins of a claim-only head, with a record still pending, so the first join pushes its own claim (two-step confirm). The lane-lint
        PASS carries across the claim commits: the first join does not refuse for lane lint, and it stops at its claim without reading that
        claim's check runs. Those are read at the second join, on the claim head, which merges once its checks answer green."""
        rc, out = self.join([lint_comment(2, linted)], once=True)
        self.assertNotIn("merge --lane-lint 7", out, "the lane lint refused a claim-only commit on the linted head:\n" + out)
        self.assertEqual(rc, 0, "the first join refused instead of stopping at the claim it pushes:\n" + out)
        self.assertTrue(tm.claim_pushed_line(out), "the first join has no stop line for its claim:\n" + out)
        self.assertNotIn("PUT pulls/7/merge", tm.GhHalf.calls(self), "the first join merged in one run:\n" + out)
        new_head = self.head("feat")
        self.assertNotEqual(new_head, claimed, "the first join pushed no claim")
        self.assertNotIn(f"commits/{new_head}/check-runs", tm.GhHalf.calls(self), "the first join read the check runs of its own claim commit")
        rc, out = self.join([lint_comment(2, linted)], once=True)
        self.assertEqual(rc, 0, "the second join refused its claim head:\n" + out)
        self.assertIn("PUT pulls/7/merge", tm.GhHalf.calls(self), out)

    def assert_refused(self, comments, cause, **state):
        """The join with `comments` and `state` is refused: rc 1, the remedy named, no merge call, no push. `cause` names the case in a failure. -> the output."""
        before = self.refs()
        rc, out = self.join(comments, **state)
        self.assertEqual(rc, 1, f"{cause}: the join went ahead:\n{out}")
        self.assertIn("merge --lane-lint 7", out, f"{cause}: the refusal does not name `merge --lane-lint 7`:\n{out}")
        self.assertNotIn("PUT pulls/7/merge", tm.GhHalf.calls(self), f"{cause}: the join merged #7")
        self.assertEqual(self.refs(), before, f"{cause}: the join pushed to origin before it refused")
        return out

    def test_a_join_with_no_lint_pass_at_the_live_head_is_refused_before_any_push(self):
        self.assert_refused([], "no lane-lint PASS on the pull request")

    def test_a_join_on_a_lint_pass_for_an_older_head_is_refused(self):
        self.assert_refused([lint_comment(2, tm.REVIEW_OLD_HEAD)], "a lane-lint PASS for an older head")

    def test_a_join_on_a_lint_pass_by_a_non_owner_is_refused(self):
        self.assert_refused([lint_comment(2, self.head("feat"), by=NOT_OWNER)], "a lane-lint PASS by a non-owner")

    def test_a_join_on_a_lint_fail_at_the_live_head_is_refused(self):
        self.assert_refused([lint_comment(2, self.head("feat"), verdict="FAIL")], "a lane-lint FAIL at the live head")

    def test_a_join_on_a_lint_pass_at_the_live_head_merges(self):  # control: green on the old code
        rc, out = self.join([lint_comment(2, self.head("feat"))])
        self.assertEqual(rc, 0, out)
        self.assertIn("PUT pulls/7/merge", tm.GhHalf.calls(self), out)

    def test_a_lint_pass_on_a_later_comment_page_still_joins(self):  # control: green on the old code, a page-two read by the new one
        comments = [other_comment(i) for i in range(1, 101)] + [lint_comment(200, self.head("feat"))]
        rc, out = self.join(comments)
        self.assertEqual(rc, 0, out)
        self.assertIn("PUT pulls/7/merge", tm.GhHalf.calls(self), out)

    def test_a_failed_comment_read_refuses_the_join_as_lane_lint_unknown(self):
        out = self.assert_refused([], "a failed comment read", comments_fail=tm.rest_err(500, "Server Error"))
        self.assertIn("lane lint unknown", out, "a failed comment read was refused with no line that reads `lane lint unknown`:\n" + out)


    def test_the_join_reads_the_comment_list_once_a_page(self):
        # one read per page of the comment list, and no second read: 101 comments are two pages at per_page 100
        comments = [other_comment(i) for i in range(1, 101)] + [lint_comment(200, self.head("feat"))]
        rc, out = self.join(comments)
        self.assertEqual(rc, 0, out)
        reads = [l for l in tm.GhHalf.calls(self).splitlines() if l.startswith("GET issues/comments ")]
        # two runs (the claim run, the merge run), each reading two pages: the calls log holds no run split, so the total is pinned
        self.assertEqual(len(reads), 2 * len(self.run_texts), "the join read the comment list %d times, want 2 per run, one per page:\n%s" % (len(reads), "\n".join(reads)))

    def test_a_head_that_moves_after_the_lint_read_is_refused_before_the_merge(self):
        # The lint reads the head the PR shows first, and the PASS names it. The branch then moves in origin, and the first head read still
        # shows the linted head (the lag). confirm reads the PR again under the lock, so the join must refuse the new head before any merge call.
        linted = self.head("feat")
        self.competitor_push()
        # ran_on is the linted head: a live head would be refused by the join's head check before the lint, and confirm's recheck would not run
        rc, out = self.join([lint_comment(2, linted)], ran_on=linted, lag={"n": 1, "prior": linted})
        self.assertEqual(rc, 1, "a join whose head moved after the lint read went ahead and merged the new head unchecked:\n" + out)
        self.assertNotIn("PUT pulls/7/merge", tm.GhHalf.calls(self), "the join merged a head the lint did not read:\n" + out)

    def test_a_rival_claim_commit_on_a_non_record_file_that_lands_after_the_lint_read_is_refused_by_the_lane_lint_head_check(self):
        # relayed_head_holds reads only the Record-claim trailer, so the join's head check and confirm's relayed-yes check both pass this commit.
        # Only confirm's linted_head check refuses it, so the refusal must be the linted-head one, not HEAD_MOVED.
        linted = self.head("feat")
        new = self.feat_commit({"rival.py": "rival = 1\n"}, "Add a rival change", "Record-claim: D-907")
        out = self.assert_refused([lint_comment(2, linted)], "a Record-claim commit on a non-record file that lands after the lint read", ran_on=linted, lag={"n": 1, "prior": linted})
        moved = [line for line in out.splitlines() if "moved from" in line]
        self.assertTrue(moved, "the refusal is not the linted-head refusal (no line says the head moved):\n" + out)
        self.assertIn(linted[:9], moved[0], "the moved-head refusal does not name the linted head:\n" + out)
        self.assertIn(new[:9], moved[0], "the moved-head refusal does not name the new head:\n" + out)
        self.assertNotIn("since the owner's yes was relayed", out, "the refusal is HEAD_MOVED, so the lane-lint head check did not refuse:\n" + out)


    def integration_body(self):
        """The body batch_build writes on an integration PR: its freeze block alone, so no session line names a lane."""
        base = tm.sh(self.other, "git", "rev-parse", "origin/main")
        return "\n".join(merge.freeze_lines(INTEGRATION_NAME, {6: base})) + "\n"

    @contextlib.contextmanager
    def integration_pr(self):
        """PR #7 is a batch integration PR for the duration of the block: its body is the freeze block (set by the caller in the join's state), and
        its head branch is the integration branch, which origin holds at feat's head. The gh shim names feat for every head ref, so the Host read
        of PR #7 is rewritten to the integration branch, as the real pull request names it. Its base is `integ`, not the default branch, so a
        join claims no record numbers and pushes nothing to the head, and the shim's head (feat) is the head the join sees move."""
        branch = merge.integration_branch(INTEGRATION_NAME)
        tm.sh(self.other, "git", "fetch", "-q", "origin")
        tm.sh(self.other, "git", "push", "-q", "origin", f"{self.head('feat')}:refs/heads/{branch}")
        tm.sh(self.other, "git", "push", "-q", "origin", "origin/main:refs/heads/integ")
        tm.GhHalf.set(self, base="integ")
        real = merge.Host.pr

        def pr(host, n):
            info = real(host, n)
            return {**info, "branch": branch} if n == 7 else info

        with unittest.mock.patch.object(merge.Host, "pr", pr):
            yield branch

    def test_a_join_with_all_jobs_passed_green_on_the_live_head_skips_the_lane_lint_and_says_so(self):
        """Why: the join needs a lane-lint PASS only to prove the head was checked. When the all-jobs-passed rollup is green on the exact head
        the merge takes, CI already proved it on that head (rule roles-each-layer-proves-once), so the join skips the local lane lint and its
        merge line names the skip, the rollup and the head. The skip is for a batch integration PR only: its clash is report-only, and a lane
        PR keeps the lint need (the next cases). Red on the old code: lint_check refuses the head for its missing lane-lint PASS, whatever CI shows."""
        head = self.head("feat")
        with self.integration_pr():
            rc, out = self.join([], body=self.integration_body(), checks_seq=[[("checks", "pass", ""), (REQUIRED_CHECK, "pass", "")]])
        self.assertEqual(rc, 0, "a join with all-jobs-passed green on the live head was refused for the lane lint, not merged:\n" + out)
        self.assertIn("PUT pulls/7/merge", tm.GhHalf.calls(self), "a join with all-jobs-passed green on the live head did not merge #7:\n" + out)
        skips = rollup_skip_lines(out)
        self.assertTrue(skips, "the merge printed no line that says the lane lint was skipped:\n" + out)
        self.assertIn(REQUIRED_CHECK, skips[0], "the skip line does not name the all-jobs-passed rollup:\n" + out)
        self.assertIn("green", skips[0], "the skip line does not say the rollup is green:\n" + out)
        self.assertIn(head[:9], skips[0], "the skip line does not name the head it skipped:\n" + out)

    def refused_with_rollup(self, name, seq, **state):
        """The join of an integration PR whose live head shows the rollup in `seq` (no lint PASS): refused, with no skip line. `state` adds the
        fake's workflow runs (runs_seq, from rollup_by_run) for a head whose rollup rows name their runs."""
        with self.integration_pr():
            out = self.assert_refused([], f"all-jobs-passed {name} on the live head of an integration PR", checks_seq=seq, body=self.integration_body(), **state)
        self.assertEqual(rollup_skip_lines(out), [], f"all-jobs-passed {name} on the live head printed a line that says the lane lint was skipped:\n{out}")

    def test_an_integration_pr_with_no_all_jobs_passed_on_the_live_head_still_needs_the_lane_lint(self):
        """Why: a rollup that is absent does not clear the lint on an integration PR. The join names `merge --lane-lint 7` and merges and pushes
        nothing. Red under a mutant that reads every rollup as green: the join then skips the lint and merges."""
        self.refused_with_rollup("absent", [[("checks", "pass", "")]])

    def test_an_integration_pr_with_a_red_all_jobs_passed_on_the_live_head_still_needs_the_lane_lint(self):
        """Why: a red rollup on the live head does not clear the lint on an integration PR. Red under a mutant that reads every rollup as green."""
        self.refused_with_rollup("red", [[("checks", "pass", ""), (REQUIRED_CHECK, "fail", "https://x/y")]])

    def test_an_integration_pr_with_a_pending_all_jobs_passed_on_the_live_head_still_needs_the_lane_lint(self):
        """Why: a pending rollup on the live head does not clear the lint on an integration PR. Red under a mutant that reads every rollup as green."""
        self.refused_with_rollup("pending", [[("checks", "pass", ""), (REQUIRED_CHECK, "pending", "")]])

    def test_an_integration_pr_with_a_skipped_all_jobs_passed_on_the_live_head_still_needs_the_lane_lint(self):
        """Why: a skipped rollup (a draft run skips it) does not clear the lint on an integration PR. Red under a mutant that reads every rollup
        as green."""
        self.refused_with_rollup("skipped", [[("checks", "pass", ""), (REQUIRED_CHECK, "skipping", "")]])

    def joined_on_rollup_skip(self, seq, runs):
        """The join of an integration PR whose live head shows the rollup rows `seq` and the workflow runs `runs`: merged, with a skip line that
        names the rollup and the head. -> the output."""
        head = self.head("feat")
        with self.integration_pr():
            rc, out = self.join([], body=self.integration_body(), checks_seq=seq, runs_seq=runs)
        self.assertEqual(rc, 0, "a join whose rollup rows name a newer pass was refused, not merged:\n" + out)
        self.assertIn("PUT pulls/7/merge", tm.GhHalf.calls(self), "a join whose rollup rows name a newer pass did not merge #7:\n" + out)
        skips = rollup_skip_lines(out)
        self.assertTrue(skips, "the merge printed no line that says the lane lint was skipped:\n" + out)
        self.assertIn(REQUIRED_CHECK, skips[0], "the skip line does not name the all-jobs-passed rollup:\n" + out)
        self.assertIn("green", skips[0], "the skip line does not say the rollup is green:\n" + out)
        self.assertIn(head[:9], skips[0], "the skip line does not name the head it skipped:\n" + out)
        return out

    def test_an_integration_pr_whose_newest_all_jobs_passed_run_passes_clears_an_older_run_that_skipped_on_the_live_head(self):
        """Why: a draft run skips the rollup job, and the ready run after it passes the job, so both rows sit on the live head. The newer run
        decides: its pass proves the head, and the older skip does not hold the lane lint. The join skips the lint, and its merge line names the
        skip, the rollup and the head. Red on the old code: rollup_green needs every rollup row to pass, so the older skip refuses the join with
        `merge --lane-lint 7` and merges nothing."""
        self.joined_on_rollup_skip(*rollup_by_run([(100, "skipping"), (200, "pass")]))

    def test_an_integration_pr_whose_newest_all_jobs_passed_run_skipped_still_needs_the_lane_lint_over_an_older_pass(self):
        """Why: the newer run decides, so a newer run that skips the rollup does not take an older run's pass. The join names `merge --lane-lint 7`
        and merges nothing. Red under a mutant that lets an older run's pass clear the rollup."""
        seq, runs = rollup_by_run([(100, "pass"), (200, "skipping")])
        self.refused_with_rollup("skipped newest run beside an older pass", seq, runs_seq=runs)

    def test_an_integration_pr_whose_newest_all_jobs_passed_run_failed_still_needs_the_lane_lint_over_an_older_pass(self):
        """Why: the newer run decides, so a newer run that fails the rollup does not take an older run's pass.
        Red under a mutant that lets an older run's pass clear the rollup."""
        seq, runs = rollup_by_run([(100, "pass"), (200, "fail")])
        self.refused_with_rollup("failed newest run beside an older pass", seq, runs_seq=runs)

    def test_an_integration_pr_whose_newest_all_jobs_passed_run_pending_still_needs_the_lane_lint_over_an_older_pass(self):
        """Why: the newer run decides, so a newer run still pending on the rollup does not take an older run's pass.
        Red under a mutant that lets an older run's pass clear the rollup."""
        seq, runs = rollup_by_run([(100, "pass"), (200, "pending")])
        self.refused_with_rollup("pending newest run beside an older pass", seq, runs_seq=runs)

    def test_an_integration_pr_whose_older_all_jobs_passed_run_failed_still_needs_the_lane_lint_under_a_newer_pass(self):
        """Why: an older run's red rollup row holds the rollup not green, even when a newer run passes it, because the merge check reads the older
        red. A skip line here would name a head the check then refuses. The join names `merge --lane-lint 7` and merges and pushes nothing.
        Red under a mutant that lets an older run's fail drop out of the rollup."""
        seq, runs = rollup_by_run([(100, "fail"), (200, "pass")])
        with self.integration_pr():
            before = self.refs()
            rc, out = self.join([], body=self.integration_body(), checks_seq=seq, runs_seq=runs)
        self.assertEqual(rollup_skip_lines(out), [], "the lane lint was skipped on a head whose older run's rollup row is red:\n" + out)
        self.assertEqual(rc, 1, "the join went ahead on a head whose older run's rollup row is red:\n" + out)
        self.assertIn("merge --lane-lint 7", out, "the refusal does not name `merge --lane-lint 7`:\n" + out)
        self.assertNotIn("PUT pulls/7/merge", tm.GhHalf.calls(self), "the join merged #7:\n" + out)
        self.assertEqual(self.refs(), before, "the join pushed to origin before it refused:\n" + out)

    def test_an_integration_pr_with_an_unlinked_all_jobs_passed_fail_beside_a_newer_pass_still_needs_the_lane_lint(self):
        """Why: a rollup row that names no run cannot be placed in a newer run, so it decides whatever the newest run says, and its fail holds
        the rollup red. Red under a mutant that leaves rows that name no run out of the decision."""
        seq, runs = rollup_by_run([(200, "pass")])
        self.refused_with_rollup("unlinked failed row beside a newer pass", [[*seq[0], (REQUIRED_CHECK, "fail", "")]], runs_seq=runs)

    def test_an_integration_pr_whose_run_ids_differ_in_width_reads_the_newer_run_by_value_and_skips_the_lint(self):
        """Why: a run id orders by its value, so 100 is the newer run beside 99. Read as text, 99 would be the newer run, and its skip would hold
        the rollup. The join skips the lint and its merge line names the skip, the rollup and the head. Red under a mutant that compares run ids
        as text."""
        self.joined_on_rollup_skip(*rollup_by_run([(99, "skipping"), (100, "pass")]))

    def test_an_integration_pr_with_all_jobs_passed_rows_that_name_no_run_still_needs_every_row_to_pass(self):
        """Why: a rollup row with no run link cannot be placed in a newer run, so rows that name no run keep the all-must-pass rule: a pass beside
        a skip is not green. Red under a mutant that takes the newest of rows that name no run as the verdict."""
        self.refused_with_rollup("pass beside a skip, neither row naming a run", [[("checks", "pass", ""), (REQUIRED_CHECK, "pass", ""), (REQUIRED_CHECK, "skipping", "")]])

    def moved_after_green_skip(self):
        """A batch integration PR whose head moves after its green-rollup read: -> (rc, out) of its join. The first head read shows the linted head;
        a claim commit then moves feat, which confirm's read under the lock sees. The claim is a Record-claim commit, so confirm's relayed-yes
        check passes it and only the linted-head check can refuse the join."""
        linted = self.head("feat")
        with self.integration_pr() as branch:
            moved = self.feat_commit({"rival.py": "rival = 1\n"}, "Add a rival change", "Record-claim: D-907")
            tm.sh(self.other, "git", "push", "-q", "origin", f"{moved}:refs/heads/{branch}")  # the integration branch is the PR's head: it moves with feat
            return self.join([], body=self.integration_body(), ran_on=linted, lag={"n": 1, "prior": linted},
                             checks_seq=[[("checks", "pass", ""), (REQUIRED_CHECK, "pass", "")]])

    def test_a_head_that_moves_after_a_green_rollup_skip_is_refused_before_the_merge(self):
        """Why: a skip on a green rollup must still hand the head it read to confirm, which sets `checked` from it. A head that moves before the
        lock is then refused by the linted-head check, before any merge call. The refusal names the move."""
        rc, out = self.moved_after_green_skip()
        self.assertEqual(rc, 1, "a head that moved after a green-rollup skip went ahead:\n" + out)
        self.assertTrue([l for l in out.splitlines() if "moved from" in l], "the moved head was not refused by the linted-head check:\n" + out)
        self.assertNotIn("PUT pulls/7/merge", tm.GhHalf.calls(self), "a head that moved after a green-rollup skip was merged:\n" + out)

    def test_the_moved_head_refusal_on_a_green_rollup_skip_does_not_say_a_lint_was_read(self):
        """Why: on the skip path no lane lint was read, so the refusal line that names the moved head must not say a lint was read. The
        refusal's wording is the builder's fix; this case holds the line to the claim it can make. Red on the code that words the refusal
        with the lane-lint's read: the refusal line says `after its lane-lint was read` on the skip path."""
        rc, out = self.moved_after_green_skip()
        moved = [l for l in out.splitlines() if "moved from" in l]
        self.assertTrue(moved, "the moved head was not refused by the linted-head check, so the wording is not read:\n" + out)
        self.assertNotIn("lint was read", moved[0], "the moved-head refusal on a green-rollup skip says a lint was read, though none was:\n" + out)

    def test_a_lane_pr_with_all_jobs_passed_green_on_the_live_head_still_needs_the_lane_lint(self):
        """Why: the skip is for a batch integration PR only. A lane PR's head can clash with a sibling PR, and the lane lint is what counts that
        clash, so a green rollup on a lane PR's head does not replace it: the join refuses with `no lane-lint PASS`, prints no skip line, and
        merges and pushes nothing. Red on the code that skips for any PR: the lane PR joins on green CI."""
        head = self.head("feat")
        out = self.assert_refused([], "all-jobs-passed green on the live head of a lane PR", checks_seq=[[("checks", "pass", ""), (REQUIRED_CHECK, "pass", "")]])
        self.assertIn("no lane-lint PASS", out, "the lane PR's refusal does not say no lane-lint PASS names its head:\n" + out)
        self.assertIn(head[:9], out, "the lane PR's refusal does not name its live head:\n" + out)
        self.assertEqual(rollup_skip_lines(out), [], "a lane PR printed a line that says the lane lint was skipped:\n" + out)

    def feat_commit(self, files, subject, trailer=None):
        """One commit on feat, pushed from the second clone: `files` maps a path to its text, and `trailer` (a Record-claim line, or None) ends
        the message. -> its sha."""
        o = self.other
        tm.sh(o, "git", "fetch", "-q", "origin")
        tm.sh(o, "git", "checkout", "-q", "-B", "feat", "origin/feat")
        for path, text in files.items():
            tm.put(os.path.join(o, path), text)
        tm.sh(o, "git", "add", "-A")
        tm.sh(o, "git", "commit", "-q", "-m", subject, *(["-m", trailer] if trailer else []))
        tm.sh(o, "git", "push", "-q", "origin", "feat")
        return tm.sh(o, "git", "rev-parse", "HEAD")

    def test_a_pass_under_one_claim_commit_lets_the_join_go_ahead(self):
        # the join resumed after a claim push: the PASS names the head before the claim, and the newest commit is the claim alone
        linted = self.head("feat")
        self.feat_commit({"docs/decisions/d901.md": tm.record("D-901", "d901")}, "Claim record numbers", "Record-claim: D-901")
        self.claim_steps(linted, self.head("feat"))

    def test_a_pass_under_two_stacked_claim_commits_lets_the_join_go_ahead(self):
        linted = self.head("feat")
        self.feat_commit({"docs/decisions/d901.md": tm.record("D-901", "d901")}, "Claim record numbers", "Record-claim: D-901")
        self.feat_commit({"docs/decisions/d902.md": tm.record("D-902", "d902")}, "Claim record numbers", "Record-claim: D-902")
        self.claim_steps(linted, self.head("feat"))


    def side_commit(self):
        """A commit on a branch of its own, off main: in origin, and in no history of feat. -> its sha."""
        o = self.other
        tm.sh(o, "git", "fetch", "-q", "origin")
        tm.sh(o, "git", "checkout", "-q", "-B", "side", "origin/main")
        tm.put(os.path.join(o, "side.txt"), "side\n")
        tm.sh(o, "git", "add", "-A")
        tm.sh(o, "git", "commit", "-q", "-m", "A side commit")
        tm.sh(o, "git", "push", "-q", "origin", "side")
        return tm.sh(o, "git", "rev-parse", "HEAD")

    def test_a_forged_claim_trailer_on_a_non_record_file_is_refused(self):
        # a trailer alone is no claim: the newer commit must touch only record files
        linted = self.head("feat")
        self.feat_commit({"notes.txt": "forged\n"}, "Claim record numbers", "Record-claim: D-903")
        self.assert_refused([lint_comment(2, linted)], "a Record-claim trailer on a commit that touches a non-record file")

    def test_a_record_only_commit_with_no_trailer_is_refused(self):
        linted = self.head("feat")
        self.feat_commit({"docs/decisions/d904.md": "# D904\n"}, "Add a decision")
        self.assert_refused([lint_comment(2, linted)], "a commit that touches only record files and has no Record-claim trailer")

    def test_a_normal_commit_after_a_claim_commit_is_refused(self):
        linted = self.head("feat")
        self.feat_commit({"docs/decisions/d905.md": "# D905\n"}, "Claim record numbers", "Record-claim: D-905")
        self.feat_commit({"notes.txt": "normal\n"}, "Fix the notes")
        self.assert_refused([lint_comment(2, linted)], "a normal commit after a claim commit")

    def test_a_pass_for_a_head_the_live_head_does_not_descend_from_is_refused(self):
        # the newer commits are claim-only, so only the ancestry of the PASS's head is wrong: it is a commit of its own branch
        side = self.side_commit()
        self.feat_commit({"docs/decisions/d906.md": "# D906\n"}, "Claim record numbers", "Record-claim: D-906")
        self.assert_refused([lint_comment(2, side)], "a lint PASS for a head that is not an ancestor of the live head")


class LintCheckRollup(unittest.TestCase):
    """lint_check's rollup read is per head. The host is the real Host, with its check runs read per sha from tm.PullsHost, so no gh shim
    answers for the live head: one head is green, and the live head has no check run."""

    def test_a_green_rollup_on_an_older_head_does_not_clear_the_live_head(self):
        """Why: when the head moved, the live head's lane lint is still owed. Green on the old head proves nothing about the new head, which has
        its own run. The PR is a batch integration PR, the only kind whose green rollup can clear the lint, so the rollup read decides. Red under a
        mutant that reads every rollup as green: the lint is skipped on the live head."""
        old, live = "1" * 40, "2" * 40
        host = tm.PullsHost([], {old: [tm.batch_run(REQUIRED_CHECK, status="completed", conclusion="success")], live: []})
        self.assertEqual(len(host.pages(f"commits/{old}/check-runs", "check_runs")), 1, "precondition: the older head has no green rollup row, so the case probes nothing")
        self.assertEqual(host.pages(f"commits/{live}/check-runs", "check_runs"), [], "precondition: the live head has a check run, so the case probes nothing")
        info = {"head": live, "branch": merge.integration_branch(INTEGRATION_NAME), "base": "main", "created": None,
                "body": "\n".join(merge.freeze_lines(INTEGRATION_NAME, {6: old})) + "\n"}
        self.assertTrue(merge.is_integration_pr(info), "precondition: the info is a lane PR, so the case probes no rollup")
        root = tempfile.mkdtemp(prefix="lint-rollup-", dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, root, True)
        with self.assertRaises(merge.Stop) as cm:
            merge.lint_check(host, 7, info, root, ".claude/merge.json")
        self.assertIn("merge --lane-lint 7", str(cm.exception), "a green rollup on an older head cleared the live head's lane lint: %s" % cm.exception)


if __name__ == "__main__":
    unittest.main()
