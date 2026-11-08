#!/usr/bin/env python3
"""Suite for `merge --lane-lint`: the lint a lane passes before it joins a batch (lanes-run-no-full-ci-job).

Run: python3 merge/test_lane_lint.py
The lint is bin/ci-job's `checks --lint`, reached through merge.CI_JOB. Each case points CI_JOB at a stub that
prints scripted step lines and exits with a scripted code, so no real lint runs. The stub logs each call, so a
case reads what the tool ran, in which tree, at which head. The repo builder, the fakes and the cloud-session
fixture come from merge/test_merge.py: a case extends that fixture, it does not copy it. The draft step's ready check
(class ReadyChecks) runs the same stub, through CiJobStub.
The SIGTERM case runs merge in a subprocess through HARNESS, which names the same stub; it is the one case that does not patch CI_JOB.
The shallow cases make the lane checkout a shallow clone (testing/shallow_clone.py). git's trace2 log (GIT_TRACE2_EVENT) lists the git calls a case makes.
Temp files: this run's folder (lint/_test_temp.py), removed at exit.
"""
import atexit, contextlib, json, os, shutil, signal, subprocess, sys, tempfile, time, unittest, unittest.mock, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.append(os.path.join(os.path.dirname(HERE), "lint"))  # append: no lint module shadows one this suite imports
sys.path.append(os.path.join(os.path.dirname(HERE), "testing"))  # append: no testing module shadows one this suite imports
import _test_temp  # noqa: E402  test-temp-standard: this run's folder (lint/_test_temp.py)
import shallow_clone  # noqa: E402  the one shallow-clone fixture (testing/shallow_clone.py)
import test_merge as tm  # noqa: E402  the git half's fixture and fakes; importing it runs none of its cases
import merge  # noqa: E402

RUN_FOLDER = _test_temp.run_folder()
atexit.register(shutil.rmtree, RUN_FOLDER, True)

PASSING = [("PASS", "record slugs"), ("PASS", "ste lint")]
FAILING = [("PASS", "record slugs"), ("FAIL", "comment narration")]
UNKNOWN = [("PASS", "record slugs"), ("unknown", "shellcheck")]

STUB = '''import json, os, subprocess, sys, time
LOG, STEPS, RC, STEP_LOG, SLEEP, PARENT = __LOG__, __STEPS__, __RC__, __STEP_LOG__, __SLEEP__, os.getppid()
JOBS, VERBATIM = __JOBS__, __VERBATIM__  # {job: (steps, rc) or (steps, rc, lines)} for a job a case scripts on its own; lines the checks lint prints as they are
JOB = sys.argv[1] if len(sys.argv) > 1 else ""
JOB_LINES = []  # the lines a job's own run prints after its step lines, as ci-job prints them
if JOB in JOBS:
    STEPS, RC, *EXTRA = JOBS[JOB]
    JOB_LINES = EXTRA[0] if EXTRA else []
if "--step" in sys.argv:  # ci-job's --step NAME: only the named steps print
    wanted = [sys.argv[i + 1] for i, arg in enumerate(sys.argv[:-1]) if arg == "--step"]
    STEPS = [pair for pair in STEPS if pair[1] in wanted]
def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True).stdout.strip()
detached = subprocess.run(["git", "symbolic-ref", "-q", "HEAD"], capture_output=True).returncode != 0
with open(LOG, "a", encoding="utf-8") as f:
    print(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd(), "head": git("rev-parse", "HEAD"), "detached": detached,
                      "shallow": git("rev-parse", "--is-shallow-repository") == "true"}), file=f)
if "--plan" in sys.argv:
    for state, name in STEPS:
        print("would run " + name)
    sys.exit(0)
end = time.time() + SLEEP  # a lint that runs long: it ends after SLEEP s, or at once when the run that started it is gone
while time.time() < end and os.getppid() == PARENT:
    time.sleep(0.05)
lines = ["%-15s %s: stub step" % (state, name) for state, name in STEPS]
if JOB == "checks":
    lines += VERBATIM
lines += JOB_LINES
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

# The workflow of the other jobs, committed on the lane's head. checks-merge-install and checks-guard are Linux, checks-macos is not.
# Each picked suite's step is named here, so a case reads the step a follow-up run names.
OTHER_JOB, MACOS_JOB = "checks-merge-install", "checks-macos"
MERGE_SUITE, MACOS_SUITE = "Merge tool git-half fixture suite", "Idle-lanes reader fixture suite"  # python3 merge/test_merge.py, python3 merge/test_idle_lanes.py
NODE_JOB, NODE_STEP, NODE_SUITE = "checks-guard", "Guard hook suite", "hooks/test_guard.py"  # the Linux job whose suite step sets NODE_PATH
OTHER_JOBS_WORKFLOW = """name: t
on: push
jobs:
  checks:
    runs-on: ubuntu-latest
    steps:
      - name: Lint one
        run: python3 lint/a.py
  checks-merge-install:
    runs-on: ubuntu-latest
    steps:
      - name: Merge tool git-half fixture suite
        run: python3 merge/test_merge.py
  checks-macos:
    runs-on: macos-latest
    steps:
      - name: Idle-lanes reader fixture suite
        run: python3 merge/test_idle_lanes.py
  checks-guard:
    runs-on: ubuntu-latest
    steps:
      - name: Install the pinned Playwright and Chromium
        uses: $/actions/playwright-setup
        with:
          package-dir: .github/shoot
      - name: Guard hook suite
        env:
          NODE_PATH: tools/guard-node-modules
        run: python3 hooks/test_guard.py
"""
OTHER_JOB_RUNS_ON = "  checks-merge-install:\n    runs-on: ubuntu-latest\n"  # the exact text of that job's runs-on in OTHER_JOBS_WORKFLOW (checks has the same line)
COLLISION = "error: cannot lock ref 'refs/remotes/origin/main': is at %s but expected %s" % ("a" * 40, "b" * 40)  # git's text when another fetch moved the ref


def pass_lines(text):
    return [line for line in text.splitlines() if line.startswith("PASS:")]


def not_run_line(job, suites):
    """The line bin/ci-job prints for the picked suites of another job, as it prints it: the checks lint names each such job."""
    return "%-15s job %s: picked %s; job %s runs them, not checks" % ("not run", job, ", ".join(suites), job)


def unknown_line(step, detail):
    """A step's unknown line as bin/ci-job's main prints it: `%-15s %s: %s`, the state padded to 15 columns."""
    return "%-15s %s: %s" % ("unknown", step, detail)




class QuietClock:
    """merge's clock, with sleep recorded and not waited: a retry pause costs no wall-clock time in a case. -> the waits asked for."""
    def __init__(self):
        self.waits = []

    def __getattr__(self, name):
        return getattr(time, name)

    def sleep(self, secs):
        self.waits.append(secs)


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

    def stub_text(self, steps, rc, sleep=0, jobs=None, verbatim=()):
        """The stub's source. `jobs` ({job: (steps, rc)} or {job: (steps, rc, lines)}) scripts a job's own run, by its name as argv[0];
        its `lines` (a third element) print after its step lines, as ci-job prints a verdict it words itself, with `steps` empty when
        that is the only line. `verbatim` lines follow the checks lint's step lines, as ci-job prints its not-run lines."""
        text = STUB.replace("__STEP_LOG__", repr(self.step_log)).replace("__LOG__", repr(self.log))
        return (text.replace("__STEPS__", repr(steps)).replace("__RC__", repr(rc)).replace("__SLEEP__", repr(sleep))
                .replace("__JOBS__", repr(dict(jobs or {}))).replace("__VERBATIM__", repr(list(verbatim))))

    def write_stub(self, steps, rc, sleep=0, jobs=None, verbatim=()):
        """Write the stub ci-job: it prints `steps` ((state, step name) pairs), exits with `rc`, and runs `sleep` s first when it is set."""
        tm.put(self.stub, self.stub_text(steps, rc, sleep, jobs, verbatim))
        return self.stub

    def use_ci_job(self, steps, rc, jobs=None, verbatim=()):
        """merge.CI_JOB becomes a stub that prints `steps` ((state, step name) pairs) and exits with `rc`; see stub_text for `jobs` and `verbatim`."""
        self.write_stub(steps, rc, jobs=jobs, verbatim=verbatim)
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

    def lint_run(self, *argv, base="main", head=None, cloud=False, other_runs=0):
        """Run merge in the lane checkout. -> (rc, stdout and stderr together). The lint must have run once, as
        `checks --lint --base origin/<base>`, in a detached tree at the head, and that tree must be gone afterwards.
        `other_runs` is the number of runs of a picked suite in another job the lane lint makes on top of that one."""
        head = head or self.head("feat")
        if os.path.exists(self.log):
            os.remove(self.log)
        rc, text = self.run_lane(*argv, cloud=cloud)
        self.assert_lint_calls(text, head, base, other_runs)
        return rc, text

    def assert_lint_calls(self, text, head, base="main", other_runs=0):
        """The calls the stub logged: one checks lint and `other_runs` runs of other jobs, each in a detached tree at `head`, gone afterwards."""
        runs = self.lint_calls()
        self.assertEqual(len(runs), 1 + other_runs, "the lint ran %d times, want %d (the checks lint and %d run of a picked suite in another job): %s"
                         % (len(runs), 1 + other_runs, other_runs, text))
        lint = [run for run in runs if run["argv"][:1] == ["checks"]]
        self.assertEqual(len(lint), 1, "the checks lint ran %d times, want once: %s" % (len(lint), text))
        self.assertEqual(lint[0]["argv"], ["checks", "--lint", "--base", "origin/" + base])
        for run in runs:
            self.assertEqual(run["head"], head, "a lint run was not at the lane head: %s" % run["argv"])
            self.assertTrue(run["detached"], "the lint ran on a branch, not a detached tree")
            self.assertNotEqual(run["cwd"], os.path.realpath(self.co), "the lint ran in the lane checkout")
            self.assertFalse(os.path.exists(run["cwd"]), "the lint tree is still on disk")
            self.assertFalse(tm.tree_listed(self.co, run["cwd"]), "git still lists the lint tree")
        self.assertEqual(self.worktrees(), 1)

    def push_release_branch(self):
        sh = tm.sh
        sh(self.other, "git", "fetch", "-q", "origin")
        sh(self.other, "git", "push", "-q", "origin", "origin/main:refs/heads/release")

    def progress_run(self, steps, rc, *argv):
        """Run merge in a subprocess through HARNESS, with the stub of `steps` (see PROGRESS). -> (rc, stdout, stderr).
        stderr is read live: the case creates the GO file at the first `start:` line, so a stderr that merge captures
        instead of passing on reads to the end only after the stub's bound."""
        go = os.path.join(self.t, "go")
        text = self.stub_text(steps, rc)
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

    def make_shallow_lane(self, source=None):
        """Make the lane checkout a shallow clone of `source` (default origin, testing/shallow_clone.py): the history is cut at feat,
        as a cloud clone's is. The source is not changed. The full clone stays on disk, unused. -> the head of feat."""
        pin = self.head("feat")
        dest = os.path.join(self.t, "shallow-lane")
        error = shallow_clone.make(source or self.bare, dest, pin)
        if error:
            self.fail("the shallow lane checkout could not be built: " + error)
        self.co, self.host.root = dest, dest  # the lane run and the host's head read name the checkout
        return pin

    def is_shallow_lane(self, pin):
        return shallow_clone.facts(self.co, pin)["shallow"]

    @contextlib.contextmanager
    def traced_git(self):
        """Every git process started in the block logs its argv to git's trace2 event log (GIT_TRACE2_EVENT), so a case reads the
        calls merge made, whichever helper made them. -> the log's path, read with git_argvs."""
        path = os.path.join(self.t, "git-trace2.jsonl")
        with unittest.mock.patch.dict(os.environ, {"GIT_TRACE2_EVENT": path}):
            yield path

    def trace_events(self, path):
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def git_argvs(self, path):
        """The argv of each git process a traced_git block started."""
        return [e["argv"] for e in self.trace_events(path) if e.get("event") == "start"]

    def unshallow_fetches(self, argvs):
        """The git calls that fetched with --unshallow."""
        return [argv for argv in argvs if "fetch" in argv and "--unshallow" in argv]

    def unshallow_exit_codes(self, path):
        """The exit code of each git call that fetched with --unshallow, read from the trace2 log: the call's own exit event, which
        carries the same sid as its start event. Child processes have longer sids, so they are not counted."""
        events = self.trace_events(path)
        sids = {e["sid"] for e in events if e.get("event") == "start" and self.unshallow_fetches([e["argv"]])}
        return [e["code"] for e in events if e.get("event") == "exit" and e.get("sid") in sids]

    def break_unshallow_fetch(self):
        """Make `git fetch --unshallow origin` fail: the configured fetch names a branch origin lacks, and the unshallow fetch reads that
        refspec. The lint's own fetches name their refs on the command line, so they still reach origin."""
        tm.sh(self.co, "git", "config", "remote.origin.fetch", "+refs/heads/gone:refs/remotes/origin/gone")

    @contextlib.contextmanager
    def stalled_unshallow_fetch(self):
        """Each `git fetch --unshallow` in the block meets a stalled origin: the fake raises subprocess.TimeoutExpired at once, at the
        bound the call was given. A call given no bound returns a failed exit instead, so the case reads the missing bound as its
        failed assert and never waits on a real hang. -> the bound of each unshallow fetch, None for no bound."""
        bounds = []
        real = merge._nowindow.run

        def run(args, *rest, **kwargs):
            if "fetch" in args and "--unshallow" in args:
                bounds.append(kwargs.get("timeout"))
                if kwargs.get("timeout") is None:
                    return subprocess.CompletedProcess(args, 124, "", "no bound on the unshallow fetch")
                raise subprocess.TimeoutExpired(args, kwargs["timeout"])
            return real(args, *rest, **kwargs)

        with unittest.mock.patch.object(merge._nowindow, "run", run):
            yield bounds

    @contextlib.contextmanager
    def odd_shallow_probe(self, answer):
        """The probe `git rev-parse --is-shallow-repository` answers `answer` with exit 0, as a probe that prints neither true nor
        false does. Every other call runs as it is. -> the counts of probe calls and of `git fetch --unshallow` calls."""
        seen = {"probes": 0, "unshallow_fetches": 0}
        real = merge.sh

        def sh(args, *rest, **kwargs):
            if "--is-shallow-repository" in args:
                seen["probes"] += 1
                return 0, answer
            if "fetch" in args and "--unshallow" in args:
                seen["unshallow_fetches"] += 1
            return real(args, *rest, **kwargs)

        with unittest.mock.patch.object(merge, "sh", sh):
            yield seen

    @contextlib.contextmanager
    def traced_shallow_probe(self):
        """The probe `git rev-parse --is-shallow-repository` runs with GIT_TRACE=1: git writes its trace to stderr while the answer
        stays on stdout. Only the probe's child gets the variable. In the whole run's environment, merge's own reads of git's
        combined output (the root discovery) would take the trace as part of the path, which is not this case's claim."""
        real = merge.sh

        def sh(args, *rest, **kwargs):
            if "--is-shallow-repository" in args:
                kwargs["env"] = {**os.environ, "GIT_TRACE": "1"}
            return real(args, *rest, **kwargs)

        with unittest.mock.patch.object(merge, "sh", sh):
            yield

    def lint_shallow_lane_passes_unshallowed(self, *argv):
        """A shallow lane checkout linted by merge `argv`: it is unshallowed before the lint runs, and the lint passes."""
        pin = self.make_shallow_lane()
        self.assertTrue(self.is_shallow_lane(pin), "precondition: the lane checkout is not shallow, so the case proves nothing")
        self.use_ci_job(PASSING, 0)
        rc, out = self.lint_run(*argv)
        self.assertFalse(self.is_shallow_lane(pin), "the lane checkout is still shallow after the lane lint: " + out)
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(pass_lines(out)), 1, out)
        self.assertFalse(self.lint_calls()[0]["shallow"], "the lint ran on a shallow clone, so its history checks read the cut history")

    def test_a_shallow_lane_checkout_is_unshallowed_before_the_lint_and_the_lint_passes(self):
        self.lint_shallow_lane_passes_unshallowed("--lane-lint", "7")

    def test_a_shallow_lane_with_a_ref_target_is_unshallowed_before_the_lint_and_the_lint_passes(self):
        self.lint_shallow_lane_passes_unshallowed("--lane-lint", "feat")

    def test_a_shallow_lane_whose_unshallow_fetch_fails_ends_unknown_and_lints_nothing(self):
        pin = self.make_shallow_lane()
        self.assertTrue(self.is_shallow_lane(pin), "precondition: the lane checkout is not shallow, so the case proves nothing")
        self.break_unshallow_fetch()
        self.use_ci_job(PASSING, 0)
        with self.traced_git() as trace:
            rc, out = self.run_lane("--lane-lint", "7")
        self.assertNotEqual(rc, 0, "a lane whose unshallow fetch failed read as a pass: " + out)
        self.assertEqual(pass_lines(out), [], "a PASS line printed after the unshallow fetch failed: " + out)
        self.assertNotIn("Traceback", out, "the failed unshallow fetch raised instead of ending the lint: " + out)
        self.assertTrue(self.unshallow_fetches(self.git_argvs(trace)), "the lint never tried `git fetch --unshallow origin`: " + out)
        self.assertIn("unknown", out.lower(), "the refusal does not say the lint is unknown: " + out)
        self.assertIn("git fetch --unshallow origin", out, "the refusal does not name the command to run: " + out)
        self.assertIn("couldn't find remote ref", out, "the refusal does not name git's error: " + out)
        self.assertEqual(self.lint_calls(), [], "ci-job ran after the unshallow fetch failed")

    def test_a_shallow_lane_that_stays_shallow_after_the_unshallow_fetch_ends_unknown_and_lints_nothing(self):
        # origin is itself shallow, so `git fetch --unshallow origin` succeeds and has no more history to send: the lane stays shallow.
        pin = self.make_shallow_lane(source=shallow_clone.origin(self.bare, os.path.join(self.t, "shallow-origin.git")))
        self.assertTrue(self.is_shallow_lane(pin), "precondition: the lane checkout is not shallow, so the case proves nothing")
        self.use_ci_job(PASSING, 0)
        with self.traced_git() as trace:
            rc, out = self.run_lane("--lane-lint", "7")
        self.assertTrue(self.unshallow_fetches(self.git_argvs(trace)), "the lint never tried `git fetch --unshallow origin`: " + out)
        self.assertEqual(self.unshallow_exit_codes(trace), [0], "the unshallow fetch did not succeed, so this case proves nothing: " + out)
        self.assertTrue(self.is_shallow_lane(pin), "the unshallow fetch made the lane checkout full, so this case proves nothing")
        self.assertEqual(rc, 1, "a lane checkout that stayed shallow after the unshallow fetch read as a pass: " + out)
        self.assertEqual(pass_lines(out), [], "a PASS line printed on a clone that stayed shallow: " + out)
        self.assertIn("unknown", out.lower(), "the refusal does not say the lint is unknown: " + out)
        self.assertRegex(out, r"(?i)origin (?:itself )?is (?:itself )?shallow", "the refusal does not say origin itself is shallow, one cause to fix: " + out)
        self.assertRegex(out, r"(?i)\brefspec\b", "the refusal does not name a fetch refspec that leaves history out, the other cause to fix: " + out)
        self.assertNotIn("git fetch --unshallow origin", out, "the refusal tells the reader to run the command that just ran, which cannot fix a shallow origin: " + out)
        self.assertEqual(self.lint_calls(), [], "ci-job ran on a clone that stayed shallow")

    def test_a_shallow_lane_whose_unshallow_fetch_times_out_ends_unknown_at_a_plain_stop_and_lints_nothing(self):
        pin = self.make_shallow_lane()
        self.assertTrue(self.is_shallow_lane(pin), "precondition: the lane checkout is not shallow, so the case proves nothing")
        self.use_ci_job(PASSING, 0)
        with self.stalled_unshallow_fetch() as bounds:
            rc, out = self.run_lane("--lane-lint", "7")
        self.assertTrue(bounds, "the lint never ran `git fetch --unshallow origin`: " + out)
        self.assertIsNotNone(bounds[0], "the unshallow fetch has no timeout, so a stalled origin hangs the lint with no Stop: " + out)
        self.assertNotIn("Traceback", out, "the timed-out unshallow fetch raised instead of ending the lint: " + out)
        self.assertNotEqual(rc, 0, "a lane whose unshallow fetch timed out read as a pass: " + out)
        self.assertEqual(pass_lines(out), [], "a PASS line printed after the unshallow fetch timed out: " + out)
        self.assertIn("unknown", out.lower(), "the refusal does not say the lint is unknown: " + out)
        self.assertRegex(out, r"(?i)timed out|timeout", "the refusal does not name the timeout: " + out)
        self.assertIn("No override lifts this refusal", out, "the refusal is not a plain Stop, which no flag lifts: " + out)
        self.assertEqual(self.lint_calls(), [], "ci-job ran after the unshallow fetch timed out")

    def test_a_probe_answer_other_than_true_or_false_ends_unknown_at_a_plain_stop_and_fetches_and_lints_nothing(self):
        pin = self.make_shallow_lane()
        self.assertTrue(self.is_shallow_lane(pin), "precondition: the lane checkout is not shallow, so the case proves nothing")
        self.use_ci_job(PASSING, 0)
        with self.odd_shallow_probe("maybe") as seen:
            rc, out = self.run_lane("--lane-lint", "7")
        self.assertGreater(seen["probes"], 0, "the probe never ran, so the case proves nothing: " + out)
        self.assertNotEqual(rc, 0, "a probe that answered neither true nor false read as a pass: " + out)
        self.assertEqual(pass_lines(out), [], "a PASS line printed after a probe that answered neither true nor false: " + out)
        self.assertEqual(seen["unshallow_fetches"], 0, "the lint ran `git fetch --unshallow` after a probe that answered neither true nor false")
        self.assertIn("unknown", out.lower(), "the refusal does not say the lint is unknown: " + out)
        self.assertIn("No override lifts this refusal", out, "the refusal is not a plain Stop, which no flag lifts: " + out)
        self.assertEqual(self.lint_calls(), [], "ci-job ran after a probe that answered neither true nor false")

    def test_git_trace_on_stderr_does_not_change_the_probe_and_a_shallow_lane_still_unshallows_and_lints(self):
        pin = self.make_shallow_lane()
        self.assertTrue(self.is_shallow_lane(pin), "precondition: the lane checkout is not shallow, so the case proves nothing")
        traced = subprocess.run(["git", "-C", self.co, "rev-parse", "--is-shallow-repository"], capture_output=True, text=True,
                                env={**os.environ, "GIT_TRACE": "1"})
        self.assertTrue(traced.stderr.strip(), "precondition: GIT_TRACE=1 wrote nothing to stderr, so the case proves nothing")
        self.assertEqual(traced.stdout.strip(), "true", "precondition: the probe under GIT_TRACE=1 did not answer true")
        self.use_ci_job(PASSING, 0)
        with self.traced_shallow_probe():
            rc, out = self.run_lane("--lane-lint", "7")
        self.assertFalse(self.is_shallow_lane(pin), "the probe read git's trace on stderr as part of its answer, so the shallow lane was never unshallowed: " + out)
        self.assertEqual(rc, 0, "a shallow lane lint with GIT_TRACE=1 did not pass: " + out)
        self.assertEqual(len(pass_lines(out)), 1, out)
        runs = self.lint_calls()
        self.assertEqual(len(runs), 1, "the lint ran %d times, want once: %s" % (len(runs), out))
        self.assertFalse(runs[0]["shallow"], "the lint ran on a shallow clone, so its history checks read the cut history")

    def lint_in_trace_env(self, env, target="7"):
        """A full lane checkout linted by merge `target`, with `env` set in the environment of the whole run, so every git call and
        root discovery run with it. -> (the lane's head, what root discovery read back, the lint's rc, its output)."""
        pin = self.head("feat")
        self.assertFalse(self.is_shallow_lane(pin), "precondition: the lane checkout is shallow, so the case proves nothing")
        self.use_ci_job(PASSING, 0)
        if os.path.exists(self.log):
            os.remove(self.log)
        roots = []
        real = merge.sh

        def sh(args, *rest, **kwargs):  # records what root discovery reads back, the call's own text
            c, out = real(args, *rest, **kwargs)
            if list(args) == ["git", "rev-parse", "--show-toplevel"]:
                roots.append(out)
            return c, out

        with unittest.mock.patch.dict(os.environ, env), unittest.mock.patch.object(merge, "sh", sh):
            rc, out = self.run_lane("--lane-lint", target)
        return pin, roots, rc, out

    def assert_lint_passed_on_real_root(self, pin, roots, rc, out):
        self.assertEqual(roots, [os.path.realpath(self.co)], "root discovery did not read back the lane checkout's root: " + out)
        self.assertEqual(rc, 0, "a lane lint with the trace variables set did not pass: " + out)
        self.assertEqual(len(pass_lines(out)), 1, out)
        runs = self.lint_calls()
        self.assertEqual(len(runs), 1, "the lint ran %d times, want once: %s" % (len(runs), out))
        self.assertEqual(runs[0]["head"], pin, "the lint ran on a head other than the lane's: " + out)
        self.assertFalse(os.path.exists(runs[0]["cwd"]), "the lint tree is still on disk: " + out)

    def test_git_trace_variables_in_the_environment_leave_the_root_discovery_on_the_real_root_and_the_lint_passes(self):
        self.assert_lint_passed_on_real_root(*self.lint_in_trace_env({"GIT_TRACE": "1", "GIT_TRACE_SETUP": "1"}))

    def test_git_trace2_variables_in_the_environment_leave_the_git_reads_on_the_real_root_and_the_lint_passes(self):
        self.assert_lint_passed_on_real_root(*self.lint_in_trace_env({"GIT_TRACE2": "1", "GIT_TRACE2_PERF": "1"}))

    def test_a_git_trace2_event_path_in_the_environment_still_writes_its_file(self):
        path = os.path.join(self.t, "trace2-event.jsonl")
        pin, roots, rc, out = self.lint_in_trace_env({"GIT_TRACE2_EVENT": path})
        self.assert_lint_passed_on_real_root(pin, roots, rc, out)
        self.assertTrue(os.path.exists(path) and os.path.getsize(path) > 0, "GIT_TRACE2_EVENT named a path, and no trace was written to it: " + out)

    def test_lint_unknown_ok_does_not_lift_a_failed_unshallow_fetch(self):
        pin = self.make_shallow_lane()
        self.assertTrue(self.is_shallow_lane(pin), "precondition: the lane checkout is not shallow, so the case proves nothing")
        self.break_unshallow_fetch()
        self.use_ci_job(PASSING, 0)
        rc, out = self.run_lane("--lane-lint", "7", "--lint-unknown-ok", "the clone is shallow")
        self.assertEqual(rc, 1, "--lint-unknown-ok lifted a failed unshallow fetch: " + out)
        self.assertEqual(pass_lines(out), [], "a PASS line printed after the unshallow fetch failed: " + out)
        self.assertIn("git fetch --unshallow origin", out, "the refusal does not name the command to run: " + out)
        self.assertEqual(self.lint_calls(), [], "ci-job ran after the unshallow fetch failed")
        # A plain Stop prints this line and a Liftable does not. lane_lint raises a Liftable for the lint unknowns that
        # --lint-unknown-ok may lift, so this line pins the failed fetch as a plain Stop.
        self.assertIn("No override lifts this refusal", out, "the refusal is a Liftable, which a flag may lift: " + out)

    def test_a_full_lane_checkout_runs_no_unshallow_fetch_and_the_lint_passes(self):
        pin = self.head("feat")
        self.assertFalse(self.is_shallow_lane(pin), "precondition: the lane checkout is shallow, so the case proves nothing")
        self.use_ci_job(PASSING, 0)
        with self.traced_git() as trace:
            rc, out = self.lint_run("--lane-lint", "7")
        argvs = self.git_argvs(trace)
        self.assertTrue(argvs, "the git trace logged no git process, so the no-unshallow check proves nothing")
        self.assertEqual(self.unshallow_fetches(argvs), [], "a full lane checkout ran `git fetch --unshallow`")
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(pass_lines(out)), 1, out)

    def other_jobs_head(self, runs_on=None):
        """The lane's head with the workflow of the other jobs committed on feat. RecordsEnv.on is the one home of that push; it
        reads only self.other and sh, so this case calls it on itself. `runs_on` (the lines of the key, as the workflow writes
        them) replaces checks-merge-install's runs-on; None keeps OTHER_JOBS_WORKFLOW as it is. -> feat's head."""
        text = OTHER_JOBS_WORKFLOW
        if runs_on is not None:
            self.assertIn(OTHER_JOB_RUNS_ON, text, "OTHER_JOB_RUNS_ON is not in OTHER_JOBS_WORKFLOW, so the swap would change nothing")
            text = text.replace(OTHER_JOB_RUNS_ON, "  %s:\n" % OTHER_JOB + runs_on)
            self.assertNotIn(OTHER_JOB_RUNS_ON, text, "the runs-on swap left the workflow's own runs-on in place")
        tm.RecordsEnv.on(self, "feat", {".github/workflows/checks.yml": text}, "feat: the workflow of the other jobs")
        return self.head("feat")

    def test_a_picked_suite_in_another_linux_job_runs_there_and_its_failure_fails_the_lane_lint(self):
        head = self.other_jobs_head()
        self.use_ci_job(PASSING, 0, jobs={OTHER_JOB: ([("FAIL", MERGE_SUITE)], 1)},
                        verbatim=[not_run_line(OTHER_JOB, ["merge/test_merge.py"])])
        rc, out = self.lint_run("--lane-lint", head, head=head, other_runs=1)  # the other job's run is asserted first: scope before subject
        self.assertEqual(rc, 1, "a FAIL of the picked suite in %s read as a pass of the lane lint: %s" % (OTHER_JOB, out))
        self.assertTrue(any(line.startswith("FAIL") and MERGE_SUITE in line for line in out.splitlines()),
                        "the refusal does not name the failing suite of %s: %s" % (OTHER_JOB, out))
        self.assertEqual(pass_lines(out), [], out)

    def test_the_same_suite_passing_in_the_other_job_passes_the_lane_lint_and_the_output_names_the_suite(self):
        head = self.other_jobs_head()
        self.use_ci_job(PASSING, 0, jobs={OTHER_JOB: ([("PASS", MERGE_SUITE)], 0)},
                        verbatim=[not_run_line(OTHER_JOB, ["merge/test_merge.py"])])
        rc, out = self.lint_run("--lane-lint", head, head=head, other_runs=1)
        self.assertEqual(rc, 0, out)
        named = [line for line in out.splitlines() if line.startswith("PASS") and ("merge/test_merge.py" in line or MERGE_SUITE in line)]
        self.assertTrue(named, "the picked suite run in %s is not named as run in the output: %s" % (OTHER_JOB, out))

    def test_a_picked_suite_past_its_own_limit_reads_unknown_names_the_suite_and_leaves_the_checks_lint_alone(self):
        head = self.other_jobs_head()
        self.use_ci_job(PASSING, 0, jobs={OTHER_JOB: ([("PASS", MERGE_SUITE)], 0)},
                        verbatim=[not_run_line(OTHER_JOB, ["merge/test_merge.py"])])
        bounds, real = {}, merge.sh

        def sh(args, *rest, **kwargs):  # each ci-job run ends at once, at the bound it was given: a stall with no wait (stalled_unshallow_fetch)
            if self.stub in args:
                bounds["other" if OTHER_JOB in args else "checks"] = kwargs.get("timeout")
                if OTHER_JOB in args:
                    if kwargs.get("timeout") is None:
                        return 124, "no bound on the picked suite's run"
                    raise subprocess.TimeoutExpired(args, kwargs["timeout"])
            return real(args, *rest, **kwargs)

        with unittest.mock.patch.object(merge, "sh", sh):
            rc, out = self.run_lane("--lane-lint", head)
        self.assertIn("other", bounds, "the picked suite of %s never ran as a ci-job run of its own: %s" % (OTHER_JOB, out))
        self.assertIsNotNone(bounds["other"], "the picked suite's run has no time limit, so a stall never ends: " + out)
        self.assertEqual(bounds.get("checks"), merge.LINT_SECONDS, "the checks lint's own bound moved: " + out)
        self.assertNotEqual(rc, 0, "a picked suite past its limit read as a pass: " + out)
        self.assertEqual(pass_lines(out), [], out)
        self.assertTrue(any("timed out" in line.lower() and ("merge/test_merge.py" in line or MERGE_SUITE in line)
                            for line in out.splitlines()), "the refusal does not say the suite timed out: " + out)
        self.assertRegex(out, r"(?i)unknown")
        self.assertEqual(len([run for run in self.lint_calls() if run["argv"][:1] == ["checks"]]), 1, out)
        self.assertEqual(self.worktrees(), 1)

    def test_a_picked_suite_only_in_a_macos_job_is_one_not_run_line_and_the_lane_lint_passes(self):
        head = self.other_jobs_head()
        self.use_ci_job(PASSING, 0, jobs={MACOS_JOB: ([("PASS", MACOS_SUITE)], 0)},
                        verbatim=[not_run_line(MACOS_JOB, ["merge/test_idle_lanes.py"])])
        rc, out = self.lint_run("--lane-lint", head, head=head)  # no run in any job but checks: the macOS job is never run here
        self.assertEqual(rc, 0, out)
        notes = [line for line in out.splitlines() if MACOS_JOB in line]
        self.assertEqual(len(notes), 1, "the macOS job's picked suite is not printed as one `not run` line: %s" % out)
        self.assertTrue(notes[0].startswith("not run"), out)

    def test_runs_on_a_quoted_or_flow_linux_label_runs_the_picked_suite_there(self):
        self.use_ci_job(PASSING, 0, jobs={OTHER_JOB: ([("PASS", MERGE_SUITE)], 0)},
                        verbatim=[not_run_line(OTHER_JOB, ["merge/test_merge.py"])])
        for runs_on in ('    runs-on: "ubuntu-latest"\n', "    runs-on: 'ubuntu-22.04'\n", "    runs-on: [ubuntu-latest]\n"):
            with self.subTest(runs_on=runs_on.strip()):
                head = self.other_jobs_head(runs_on)
                rc, out = self.lint_run("--lane-lint", head, head=head, other_runs=1)  # the other job's run is asserted first: scope before subject
                self.assertEqual(rc, 0, "a Linux runs-on that is quoted or a flow list did not run the picked suite in %s: %s" % (OTHER_JOB, out))
                self.assertFalse(any("runs-on" in line for line in out.splitlines()), "a Linux job is printed as not run: " + out)
                self.assertTrue(any(line.startswith("PASS") and OTHER_JOB in line and "merge/test_merge.py" in line for line in out.splitlines()),
                                "the PASS line does not name the suite run in %s: %s" % (OTHER_JOB, out))

    def test_runs_on_an_expression_a_map_or_no_value_reads_unknown_naming_the_job(self):
        self.use_ci_job(PASSING, 0, jobs={OTHER_JOB: ([("PASS", MERGE_SUITE)], 0)},
                        verbatim=[not_run_line(OTHER_JOB, ["merge/test_merge.py"])])
        for runs_on in ("    runs-on: ${{ matrix.os }}\n", "    runs-on:\n      group: big\n      labels: ubuntu-latest\n", "    runs-on:\n"):
            with self.subTest(runs_on=repr(runs_on)):
                head = self.other_jobs_head(runs_on)
                rc, out = self.lint_run("--lane-lint", head, head=head)  # no run of the other job: its runs-on names no OS this lint can read
                self.assertNotEqual(rc, 0, "a runs-on this lint cannot read passed the lint of %s: %s" % (OTHER_JOB, out))
                self.assertEqual(pass_lines(out), [], out)
                self.assertTrue(any("unknown" in line and OTHER_JOB in line for line in out.splitlines()),
                                "no unknown line names %s for a runs-on this lint cannot read: %s" % (OTHER_JOB, out))

    def test_runs_on_a_quoted_windows_label_stays_not_run_and_the_lane_lint_passes(self):
        self.use_ci_job(PASSING, 0, jobs={OTHER_JOB: ([("PASS", MERGE_SUITE)], 0)},
                        verbatim=[not_run_line(OTHER_JOB, ["merge/test_merge.py"])])
        head = self.other_jobs_head('    runs-on: "windows-latest"\n')
        rc, out = self.lint_run("--lane-lint", head, head=head)  # no run of the other job: a quoted Windows label is not Linux
        self.assertEqual(rc, 0, out)
        notes = [line for line in out.splitlines() if OTHER_JOB in line]
        self.assertEqual(len(notes), 1, "the quoted Windows job's picked suite is not one `not run` line: %s" % out)
        self.assertTrue(notes[0].startswith("not run"), out)

    def test_control_no_picked_suite_in_another_job_makes_no_extra_run(self):
        head = self.other_jobs_head()
        self.use_ci_job(PASSING, 0, jobs={OTHER_JOB: ([("PASS", MERGE_SUITE)], 0)})  # the checks lint picks nothing in another job
        rc, out = self.lint_run("--lane-lint", head, head=head)
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(pass_lines(out)), 1, out)

    def test_a_picked_suite_whose_node_path_its_own_playwright_setup_step_installs_reads_its_verdict_never_not_run(self):
        head = self.other_jobs_head()  # checks-guard holds its own playwright-setup step before the suite, as CI runs it
        verbatim = [not_run_line(NODE_JOB, [NODE_SUITE])]
        self.use_ci_job(PASSING, 0, jobs={NODE_JOB: ([("PASS", NODE_STEP)], 0)}, verbatim=verbatim)
        rc, out = self.lint_run("--lane-lint", head, head=head, other_runs=1)  # the guard job's run is asserted first: scope before subject
        self.assertEqual(rc, 0, "a picked suite whose install is its own job's step refused the lane lint: " + out)
        notes = [line for line in out.splitlines() if line.startswith("not run") and NODE_JOB in line]
        self.assertEqual(notes, [], "the picked suite of %s reads as a `not run` line: %s" % (NODE_JOB, out))
        passed = pass_lines(out)
        self.assertEqual(len(passed), 1, out)
        self.assertIn(NODE_JOB, passed[0], "the PASS line does not name the suite run in %s: %s" % (NODE_JOB, out))

    def test_control_a_picked_suite_of_a_node_path_job_whose_unknown_is_other_text_still_refuses(self):
        head = self.other_jobs_head()
        verbatim = [not_run_line(NODE_JOB, [NODE_SUITE])]
        other_text = [unknown_line(NODE_STEP, "env NODE_PATH needs an expression this runner cannot read: ${{ matrix.node }}"),
                      unknown_line(NODE_STEP, "tool missing: node")]
        self.use_ci_job(PASSING, 0, jobs={NODE_JOB: ([], 2, other_text[:1])}, verbatim=verbatim)
        for line in other_text:
            with self.subTest(line=line):
                self.write_stub(PASSING, 0, jobs={NODE_JOB: ([], 2, [line])}, verbatim=verbatim)
                rc, out = self.lint_run("--lane-lint", head, head=head, other_runs=1)
                self.assertNotEqual(rc, 0, "an unknown line of other text read as a pass: " + out)
                self.assertEqual(pass_lines(out), [], out)
                self.assertRegex(out, r"(?i)unknown")

    def run_with_main_fetch_failing(self, target, fails, failure):
        """Run the lane lint of `target` with the first `fails` fetches of main answered `failure` (exit, text), as a fetch that another
        lint's fetch moved answers; every other git call runs as it is. -> (rc, output, fetches of main, the waits a retry asked for)."""
        main = "+refs/heads/main:refs/remotes/origin/main"
        seen, clock, real = {"main": 0}, QuietClock(), merge.git

        def git(cwd, *a, **kwargs):
            if a[:3] == ("fetch", "-q", "origin") and main in a:
                seen["main"] += 1
                if seen["main"] <= fails:
                    return failure
            return real(cwd, *a, **kwargs)

        if os.path.exists(self.log):
            os.remove(self.log)
        with unittest.mock.patch.object(merge, "git", git), unittest.mock.patch.object(merge, "time", clock):
            rc, out = self.run_lane("--lane-lint", target)
        return rc, out, seen["main"], clock.waits

    def test_a_fetch_of_main_that_collides_with_another_lints_fetch_is_retried_and_the_lint_goes_on(self):
        head = self.head("feat")
        self.use_ci_job(PASSING, 0)
        for target in ("7", head):  # a PR target fetches main in open_worktree, a ref target in lane_head_and_base
            with self.subTest(target=target):
                rc, out, fetches, _ = self.run_with_main_fetch_failing(target, 1, (1, COLLISION))
                self.assertGreaterEqual(fetches, 2, "the fetch of main that collided with another lint's fetch was not retried: " + out)
                self.assertEqual(rc, 0, "a fetch that collided with another lint's read as a failed lint: " + out)
                self.assertEqual(len(pass_lines(out)), 1, out)
                self.assert_lint_calls(out, head)

    def test_control_a_fetch_of_main_that_fails_for_another_reason_stops_after_one_fetch(self):
        head = self.head("feat")
        self.use_ci_job(PASSING, 0)
        rc, out, fetches, _ = self.run_with_main_fetch_failing(head, 99, (128, "fatal: couldn't find remote ref main"))
        self.assertEqual(fetches, 1, "a fetch that failed for another reason was retried: " + out)
        self.assertNotEqual(rc, 0, out)
        self.assertIn("fetch origin main", out)
        self.assertEqual(self.lint_calls(), [], "ci-job ran after the fetch failed")

    def test_control_a_lint_run_past_its_bound_reads_unknown_and_prints_no_fail_line(self):
        """The bound: ci-job runs past LINT_SECONDS, set to 1 s here. The fake ends the run at once, at the bound it was given, so nothing waits."""
        head = self.head("feat")
        self.use_ci_job(PASSING, 0)
        bounds, real = [], merge.sh

        def sh(args, *rest, **kwargs):
            if self.stub in args and "checks" in args:
                bounds.append(kwargs.get("timeout"))
                if kwargs.get("timeout") is None:
                    return 124, "no bound on the lint"
                raise subprocess.TimeoutExpired(args, kwargs["timeout"])
            return real(args, *rest, **kwargs)

        with unittest.mock.patch.object(merge, "LINT_SECONDS", 1), unittest.mock.patch.object(merge, "sh", sh):
            rc, out = self.run_lane("--lane-lint", head)
        self.assertEqual(bounds, [1], "the lint run was not bounded by LINT_SECONDS: " + out)
        self.assertNotEqual(rc, 0, "a lint run past its bound read as a pass: " + out)
        self.assertEqual(pass_lines(out), [], out)
        self.assertEqual([line for line in out.splitlines() if line.startswith("FAIL")], [], "a run past its bound printed a FAIL line: " + out)
        self.assertRegex(out, r"(?i)unknown")
        self.assertRegex(out, r"did not finish in 1 s|timed out")


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
