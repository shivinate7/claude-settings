#!/usr/bin/env python3
"""Suite for `merge --lane-lint`: the lint a lane passes before it joins a batch (lanes-run-no-full-ci-job).

Run: python3 merge/test_lane_lint.py
The lint is bin/ci-job's `checks --lint`, reached through merge.CI_JOB. Each case points CI_JOB at a stub that
prints scripted step lines and exits with a scripted code, so no real lint runs. The stub logs each call, so a
case reads what the tool ran, in which tree, at which head. The repo builder, the fakes and the cloud-session
fixture come from merge/test_merge.py: a case extends that fixture, it does not copy it. The draft step's ready check
(class ReadyChecks) runs the same stub, through CiJobStub.
The SIGTERM case and the slot cases run merge in a subprocess through HARNESS, which names the same stub; they do not patch CI_JOB
in this process, except the in-process hung-lint case. That case reads the slot's lock in this process once lane_lint returns: a lock that a
subprocess leaks is freed when the subprocess exits, so only a probe here sees the leak. The other slot cases (lint slots: a lane lint
waits for one of merge.lint_slots() slots) set the slot count and the bound (merge.LINT_SECONDS) in that subprocess, and read the order
of the stub's starts and ends, never the clock.
Temp files: this run's folder (lint/_test_temp.py), removed at exit.
"""
import atexit, json, os, shutil, signal, subprocess, sys, tempfile, time, unittest, unittest.mock, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.append(os.path.join(os.path.dirname(HERE), "lint"))  # append: no lint module shadows one this suite imports
import _test_temp  # noqa: E402  test-temp-standard: this run's folder (lint/_test_temp.py)
import test_merge as tm  # noqa: E402  the git half's fixture and fakes; importing it runs none of its cases
import merge  # noqa: E402

RUN_FOLDER = _test_temp.run_folder()
atexit.register(shutil.rmtree, RUN_FOLDER, True)

PASSING = [("PASS", "record slugs"), ("PASS", "ste lint")]
FAILING = [("PASS", "record slugs"), ("FAIL", "comment narration")]
UNKNOWN = [("PASS", "record slugs"), ("unknown", "shellcheck")]

STUB = '''import json, os, subprocess, sys, time
LOG, STEPS, RC, STEP_LOG, SLEEP, PARENT, HOLD = __LOG__, __STEPS__, __RC__, __STEP_LOG__, __SLEEP__, os.getppid(), __HOLD__
def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True).stdout.strip()
def alive(pid):  # os.kill(pid, 0) only tests the pid on POSIX; a case that sets HOLD skips on Windows, where a signal ends the process
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:  # a process this user may not signal is alive
        return True
    return True
detached = subprocess.run(["git", "symbolic-ref", "-q", "HEAD"], capture_output=True).returncode != 0
with open(LOG, "a", encoding="utf-8") as f:
    print(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd(), "head": git("rev-parse", "HEAD"), "detached": detached,
                      "pid": os.getpid(), "holder_alive": alive(HOLD) if HOLD is not None and os.name != "nt" else None}), file=f)
if "--plan" in sys.argv:
    for state, name in STEPS:
        print("would run " + name)
    sys.exit(0)
end = time.time() + SLEEP  # a lint that runs long: it ends after SLEEP s, or at once when the run that started it is gone
while time.time() < end and os.getppid() == PARENT:
    time.sleep(0.05)
with open(LOG, "a", encoding="utf-8") as f:  # this run's end: the slot cases read the order of starts and ends, never a clock
    print(json.dumps({"pid": os.getpid(), "end": True}), file=f)
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

def wait_lines(text):
    """The lines of `text` that say a lint is waiting for a slot: each says both `wait` and `slot`."""
    return [line for line in text.splitlines() if "wait" in line.lower() and "slot" in line.lower()]

def most_running(events):
    """The most ci-job runs at once, read from the order of CiJobStub.lint_events: a run is running from its start to its end."""
    running, most = set(), 0
    for e in events:
        if e["kind"] == "start":
            running.add(e["pid"])
        else:
            running.discard(e["pid"])
        most = max(most, len(running))
    return most

def slot_is_free(path):
    """True when a new fd of this process takes the lock on the slot file at `path`. An open fd of this process that still holds the lock makes it read as held."""
    import guard_core  # hooks/, on sys.path from merge.py
    fd = os.open(path, os.O_RDWR)
    try:
        return guard_core.try_lock_fd(fd)
    finally:
        os.close(fd)  # closing the fd frees the lock this probe took

def harness_text(stub, slots=None, bound=None):
    """HARNESS, with the seams a case gives set before main runs: merge.lint_slots (the slot count) and merge.LINT_SECONDS (the bound).
    Both are plain assignments, so a name the code lacks still takes the value: a case reads the behaviour, never a missing name."""
    seams = ""
    if slots is not None:
        seams += "merge.lint_slots = lambda: %d\n" % slots
    if bound is not None:
        seams += "merge.LINT_SECONDS = %d\n" % bound
    text = HARNESS.replace("merge.CI_JOB = __STUB__\n", "merge.CI_JOB = __STUB__\n" + seams)
    return text.replace("__HERE__", repr(HERE)).replace("__STUB__", repr(stub))


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

    def stub_text(self, steps, rc, sleep=0, hold=None):
        """The text of a stub ci-job (STUB), each argument written as its Python literal."""
        text = STUB.replace("__STEP_LOG__", repr(self.step_log)).replace("__LOG__", repr(self.log))
        return text.replace("__STEPS__", repr(steps)).replace("__RC__", repr(rc)).replace("__SLEEP__", repr(sleep)).replace("__HOLD__", repr(hold))

    def write_stub(self, steps, rc, sleep=0, hold=None, path=None):
        """Write the stub ci-job: it prints `steps` ((state, step name) pairs), exits with `rc`, and runs `sleep` s first when it is set.
        `hold` is the pid of a run ahead of it: the stub's start record reads back whether that run is alive. -> the stub's path."""
        path = path or self.stub
        tm.put(path, self.stub_text(steps, rc, sleep, hold))
        return path

    def use_ci_job(self, steps, rc):
        """merge.CI_JOB becomes a stub that prints `steps` ((state, step name) pairs) and exits with `rc`."""
        self.write_stub(steps, rc)
        patch = unittest.mock.patch.object(merge, "CI_JOB", self.stub)
        patch.start()
        self.addCleanup(patch.stop)

    def lint_calls(self):
        """The stub's calls that ran the lint, not the plan. The end records the stub writes after each run carry no argv."""
        if not os.path.exists(self.log):
            return []
        with open(self.log, encoding="utf-8") as f:
            calls = [json.loads(line) for line in f if line.strip()]
        return [c for c in calls if "argv" in c and "--plan" not in c["argv"]]

    def lint_events(self):
        """The stub's lint runs in the order they were written: {"kind": "start", ...the start record} when a run's ci-job starts,
        {"kind": "end", "pid": pid} when it ends. A run killed before its end has no end event. The plan is no run."""
        events = []
        if not os.path.exists(self.log):
            return events
        with open(self.log, encoding="utf-8") as f:
            for line in f:
                if not line.endswith("\n"):  # a record still being written
                    break
                rec = json.loads(line)
                if "argv" in rec and "--plan" not in rec["argv"]:
                    events.append({"kind": "start", **rec})
                elif "end" in rec:
                    events.append({"kind": "end", "pid": rec["pid"]})
        return events


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

    def lane_checkout(self, name):
        """A clone of origin of its own, for one lint: a lane has a checkout of its own. Concurrent lints in one shared clone race
        in git's fetch and worktree calls, which is not the claim these cases test."""
        path = os.path.join(self.t, name)
        tm.sh(self.t, "git", "clone", "-q", self.bare, path)
        return path

    def start_lane(self, stub, *argv, checkout=None, slots=None, bound=None):
        """Start `merge <argv>` in `checkout` (default: the lane checkout), in a process of its own, with the ci-job stub at `stub` and
        the seams of harness_text. Its temp files land in this case's folder. -> the Popen; finish() reads its result."""
        harness = os.path.join(self.t, "lane-lint-%s.py" % uuid.uuid4().hex)
        tm.put(harness, harness_text(stub, slots, bound))
        tmp = os.path.join(self.t, "tmp")
        os.makedirs(tmp, exist_ok=True)
        env = {**os.environ, "CLAUDE_CONFIG_DIR": self.cfg, "TMPDIR": tmp, "TMP": tmp, "TEMP": tmp}
        env.pop("CLAUDE_CODE_REMOTE", None)
        proc = subprocess.Popen([sys.executable, harness, *argv], cwd=checkout or self.co, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.stop_run, proc)
        return proc

    def finish(self, proc):
        """-> (rc, stdout, stderr) of a start_lane process, once it has ended."""
        out, err = proc.communicate(timeout=120)
        return proc.returncode, out, err

    def quick_stub(self, hold=None):
        """A stub that ends at once, for a lint that runs after the holder. `hold` is the pid of the run ahead of it."""
        return self.write_stub(PASSING, 0, path=os.path.join(self.t, "ci-job-quick.py"), hold=hold)

    def wait_for_starts(self, n):
        """Poll the stub's log until `n` lint runs have started, for 60 s at most. -> the start events read so far."""
        deadline = time.time() + 60
        while True:
            starts = [e for e in self.lint_events() if e["kind"] == "start"]
            if len(starts) >= n or time.time() > deadline:
                return starts
            time.sleep(0.05)

    def lint_ended(self, pid):
        return any(e["kind"] == "end" and e["pid"] == pid for e in self.lint_events())

    def test_four_lane_lints_at_once_run_at_most_two_ci_jobs_with_two_slots(self):
        """With two slots, four lane lints at once run their ci-jobs two at a time, and each passes."""
        stub = self.write_stub(PASSING, 0, sleep=3)
        head = self.head("feat")
        procs = [self.start_lane(stub, "--lane-lint", head, checkout=self.lane_checkout("lane-%d" % i), slots=2) for i in range(4)]
        results = [self.finish(proc) for proc in procs]
        events = self.lint_events()
        self.assertEqual(len([e for e in events if e["kind"] == "start"]), 4,
                         "not all four lints reached ci-job: " + "".join(out + err for _, out, err in results))
        for rc, out, err in results:
            self.assertEqual(rc, 0, "a lint did not pass: " + out + err)
            self.assertEqual(len(pass_lines(out)), 1, out + err)
        self.assertLessEqual(most_running(events), 2, "%d ci-job runs ran at once; with 2 slots at most 2 may" % most_running(events))

    def test_two_lane_lints_with_two_slots_run_their_ci_jobs_together(self):
        """The control for the overlap count: with two slots, two lints run at once, and the count reads two."""
        stub = self.write_stub(PASSING, 0, sleep=3)
        head = self.head("feat")
        procs = [self.start_lane(stub, "--lane-lint", head, checkout=self.lane_checkout("lane-%d" % i), slots=2) for i in range(2)]
        results = [self.finish(proc) for proc in procs]
        events = self.lint_events()
        self.assertEqual(len([e for e in events if e["kind"] == "start"]), 2,
                         "not both lints reached ci-job: " + "".join(out + err for _, out, err in results))
        for rc, out, err in results:
            self.assertEqual(rc, 0, out + err)
            self.assertEqual(len(pass_lines(out)), 1, out + err)
        self.assertEqual(most_running(events), 2, "two lints with two slots did not run their ci-jobs together")

    def test_a_lint_that_waits_for_a_slot_keeps_the_full_bound_for_its_own_run(self):
        """The bound starts when the slot is held. The first assert is the wait: the second ci-job starts only after the first one
        ends. Then both lints pass: a run that fits the bound by itself must not time out for the time it waited."""
        stub = self.write_stub(PASSING, 0, sleep=3.5)
        head = self.head("feat")
        procs = [self.start_lane(stub, "--lane-lint", head, checkout=self.lane_checkout("lane-%d" % i), slots=1, bound=6) for i in range(2)]
        results = [self.finish(proc) for proc in procs]
        events = self.lint_events()
        starts = [e for e in events if e["kind"] == "start"]
        self.assertEqual(len(starts), 2, "the two lints did not both reach ci-job: " + "".join(out + err for _, out, err in results))
        order = [(e["kind"], e["pid"]) for e in events]
        self.assertIn(("end", starts[0]["pid"]), order, "the first lint's ci-job never ended")
        self.assertLess(order.index(("end", starts[0]["pid"])), order.index(("start", starts[1]["pid"])),
                        "the second lint's ci-job started before the first's ended: two ci-jobs ran with one slot")
        for rc, out, err in results:
            self.assertEqual(rc, 0, "a lint whose run fits the bound did not pass: " + out + err)
            self.assertEqual(len(pass_lines(out)), 1, out + err)

    def test_a_lint_whose_run_fits_the_bound_passes_with_one_slot(self):
        """The control for the bound: the stub's run fits the bound by itself, so a timeout in the case above comes from the wait."""
        stub = self.write_stub(PASSING, 0, sleep=3.5)
        rc, out, err = self.finish(self.start_lane(stub, "--lane-lint", self.head("feat"), slots=1, bound=6))
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(len(pass_lines(out)), 1, out + err)

    def test_a_hung_lint_ends_at_the_bound_and_frees_its_slot_when_lane_lint_returns(self):
        """A hung ci-job ends unknown at the bound. lane_lint returns while this process still lives, so the slot must be free here:
        lint_slot's open fd holds the lock until lint_slot closes that fd. The probe's fd takes the lock only when no open fd still holds it."""
        self.write_stub(PASSING, 0, sleep=60)  # it runs past the bound, so the bound ends it
        for patch in (unittest.mock.patch.object(merge, "CI_JOB", self.stub), unittest.mock.patch.object(merge, "LINT_SECONDS", 2),
                      unittest.mock.patch.object(merge, "lint_slots", lambda: 1)):
            patch.start()
            self.addCleanup(patch.stop)
        rc, out = self.lint_run("--lane-lint", "7")
        self.assertEqual(rc, 1, out)
        self.assertIn("did not finish", out)
        self.assertEqual(pass_lines(out), [], out)
        slot = os.path.join(self.cfg, "state", "lane-lint-slots", "slot-0.lock")
        self.assertTrue(os.path.exists(slot), "the lint took no slot: " + out)
        self.assertTrue(slot_is_free(slot), "the slot's lock was still held once lane_lint returned: the slot's fd was not closed")

    @unittest.skipIf(os.name == "nt", "a signal to the holder ends it on Windows, so its liveness cannot be read there")
    def test_a_hung_lint_ends_at_the_bound_and_frees_its_slot_for_the_next_lint(self):
        """A hung ci-job ends unknown at the bound and frees its slot. The next lint's ci-job starts only then: its start record
        reads that the hung run is no longer alive (holder_alive). The next lint then passes."""
        hung = self.write_stub(PASSING, 0, sleep=60)  # it runs past the bound, so the bound ends it
        head = self.head("feat")
        first = self.start_lane(hung, "--lane-lint", head, checkout=self.lane_checkout("holder"), slots=1, bound=8)
        holders = self.wait_for_starts(1)
        self.assertEqual(len(holders), 1, "the hung lint's ci-job never started")
        second = self.start_lane(self.quick_stub(hold=holders[0]["pid"]), "--lane-lint", head, checkout=self.lane_checkout("next"), slots=1, bound=8)
        rc1, out1, err1 = self.finish(first)
        rc2, out2, err2 = self.finish(second)
        starts = [e for e in self.lint_events() if e["kind"] == "start"]
        self.assertEqual(len(starts), 2, "the next lint's ci-job never ran: " + out2 + err2)
        self.assertIs(starts[1]["holder_alive"], False,
                      "the next lint's ci-job started while the hung one still ran: no slot was held")
        self.assertEqual(rc1, 1, out1 + err1)
        self.assertIn("did not finish", out1 + err1)
        self.assertEqual(pass_lines(out1), [], out1)
        self.assertEqual(rc2, 0, out2 + err2)
        self.assertEqual(len(pass_lines(out2)), 1, out2 + err2)

    @unittest.skipIf(os.name == "nt", "a signal to the holder ends it on Windows, so its liveness cannot be read there")
    def test_with_two_slots_a_lint_starts_beside_a_hung_one_and_reads_it_alive(self):
        """The control for the holder check: a hung run that still holds its slot reads as alive to the next lint's start."""
        hung = self.write_stub(PASSING, 0, sleep=60)
        head = self.head("feat")
        first = self.start_lane(hung, "--lane-lint", head, checkout=self.lane_checkout("holder"), slots=2, bound=8)
        holders = self.wait_for_starts(1)
        self.assertEqual(len(holders), 1, "the hung lint's ci-job never started")
        second = self.start_lane(self.quick_stub(hold=holders[0]["pid"]), "--lane-lint", head, checkout=self.lane_checkout("next"), slots=2, bound=8)
        rc2, out2, err2 = self.finish(second)
        self.finish(first)
        starts = [e for e in self.lint_events() if e["kind"] == "start"]
        self.assertEqual(len(starts), 2, "the next lint's ci-job never ran: " + out2 + err2)
        self.assertIs(starts[1]["holder_alive"], True, "the next lint's start read the hung run as ended while it still ran")
        self.assertEqual(rc2, 0, out2 + err2)
        self.assertEqual(len(pass_lines(out2)), 1, out2 + err2)

    def test_a_lint_that_waits_for_a_slot_prints_one_wait_line_on_stderr_while_it_waits(self):
        """The waiting lint prints one stderr line that says it waits for a slot, and prints it while the holder's ci-job still runs."""
        busy = self.write_stub(PASSING, 0, sleep=5)
        head = self.head("feat")
        first = self.start_lane(busy, "--lane-lint", head, checkout=self.lane_checkout("holder"), slots=1)
        holders = self.wait_for_starts(1)
        self.assertEqual(len(holders), 1, "the holding lint's ci-job never started")
        second = self.start_lane(self.quick_stub(), "--lane-lint", head, checkout=self.lane_checkout("next"), slots=1)
        err_lines, held_when_read = [], []
        for line in second.stderr:  # read live: each line is judged when it arrives, not at the end
            err_lines.append(line)
            if wait_lines(line) and not held_when_read:
                held_when_read.append(not self.lint_ended(holders[0]["pid"]))
        out, rest = second.communicate(timeout=120)
        rc = second.returncode
        err = "".join(err_lines) + rest
        self.finish(first)
        waits = wait_lines("".join(err_lines))
        self.assertEqual(len(waits), 1, "the waiting lint printed %d stderr lines that say it waits for a slot, want one: %s" % (len(waits), err))
        self.assertEqual(held_when_read, [True], "the wait line came after the holder's ci-job had ended")
        self.assertEqual(wait_lines(out), [], "the wait line went to stdout, not stderr: " + out)
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(len(pass_lines(out)), 1, out + err)

    def test_a_lint_that_finds_a_free_slot_prints_no_wait_line(self):
        """The control for the wait line: a lint with a free slot prints none."""
        stub = self.write_stub(PASSING, 0)
        rc, out, err = self.finish(self.start_lane(stub, "--lane-lint", self.head("feat"), slots=1))
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(len(pass_lines(out)), 1, out + err)
        self.assertEqual(wait_lines(err), [], "a lint with a free slot printed a wait line: " + err)


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
