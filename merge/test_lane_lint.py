#!/usr/bin/env python3
"""Suite for `merge --lane-lint`: the lint a lane passes before it joins a batch (lanes-run-no-full-ci-job).

Run: python3 merge/test_lane_lint.py
The lint is bin/ci-job's `checks --lint`, reached through merge.CI_JOB. Each case points CI_JOB at a stub that
prints scripted step lines and exits with a scripted code, so no real lint runs. The stub logs each call, so a
case reads what the tool ran, in which tree, at which head. The repo builder, the fakes and the cloud-session
fixture come from merge/test_merge.py: a case extends that fixture, it does not copy it. The draft step's ready check
(class ReadyChecks) runs the same stub, through CiJobStub.
The SIGTERM case and the slot cases run merge in a subprocess through HARNESS, which names the same stub; they do not patch CI_JOB
in this process. The slot cases (lint slots: a lane lint waits for one of merge.lint_slots() slots) set the slot count and the bound
(merge.LINT_SECONDS) in that subprocess, and read the order of the stub's starts and ends, never the clock.
The load cases (a lane lint waits while the load is high) set a fake load reader, a fake clock and the lints running in that
subprocess (LOAD_SEAMS), so no case reads the real load. HARNESS sets no real reader by default (NO_LOAD); LaneLint and
BatchLintFlags patch merge.read_cpu_load in process (no_load_reading).
The marker cases (class LintMarkers) call the real merge.lints_running and merge.lint_running in this process, on a temp config
folder (CLAUDE_CONFIG_DIR), and a child process holds a marker's lock for the other-process case; no case patches them.
BatchLintFlags runs the real bin/ci-job through merge.lane_lint on a batch's four checks.yml lint CI steps, each script logged once with its argv; cost per case: one ci-job copy and run, one worktree, four CI step runs, 0.5 s measured (3 runs of 2 cases). Its two lint-set cases (no lint step; a step that runs only off a pull request) run the same way with their own checks job.
Temp files: this run's folder (lint/_test_temp.py), removed at exit.
"""
import ast, atexit, contextlib, io, json, os, re, shlex, shutil, signal, subprocess, sys, tempfile, time, unittest, unittest.mock, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.append(os.path.join(os.path.dirname(HERE), "lint"))  # append: no lint module shadows one this suite imports
import _test_temp  # noqa: E402  test-temp-standard: this run's folder (lint/_test_temp.py)
import test_merge as tm  # noqa: E402  the git half's fixture and fakes; importing it runs none of its cases
import merge  # noqa: E402
import guard_core  # noqa: E402  hooks/, on sys.path from merge's import: the lock a lint's markers and slots take
from workflow_steps import job_block, run_body, step_blocks, step_env, step_key, step_with  # noqa: E402  the one home of the step parser

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
__LOAD__
sys.exit(merge.main(sys.argv[1:]))
'''

NO_LOAD = "merge.read_cpu_load = lambda: None  # merge reads no real load: a case that tests the wait sets its own reader after this line\n"

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

def seam_lines(slots=None, bound=None):
    """The plain assignments a case gives before main runs: merge.lint_slots (the slot count) and merge.LINT_SECONDS (the bound).
    Both are plain assignments, so a name the code lacks still takes the value: a case reads the behaviour, never a missing name."""
    seams = ""
    if slots is not None:
        seams += "merge.lint_slots = lambda: %d\n" % slots
    if bound is not None:
        seams += "merge.LINT_SECONDS = %d\n" % bound
    return seams

def harness_for(stub, seams="", load=NO_LOAD):
    """HARNESS for the stub at `stub`: `load` is its reader line (NO_LOAD, or "" to keep merge's own reader), then `seams`."""
    return HARNESS.replace("__LOAD__\n", load + seams).replace("__HERE__", repr(HERE)).replace("__STUB__", repr(stub))

def harness_text(stub, slots=None, bound=None):
    """HARNESS with the seams of seam_lines set before main runs."""
    return harness_for(stub, seam_lines(slots, bound))

# The seams of a load case: plain assignments, like the slot seams. The clock is fake, on merge's own `time` name only (never the
# global module, which subprocess reads): a sleep moves it on, and a read of it moves it on a millisecond, so a loop that only
# reads the clock still ends. Each sleep, reading and bound is logged in order, next to the stub's starts and ends.
LOAD_SEAMS = '''import json as _json, time as _real_time
_LOG = __LOG__
def _note(rec):
    with open(_LOG, "a", encoding="utf-8") as f:
        print(_json.dumps(rec), file=f)
class _FakeClock:
    now = 0.0
    def monotonic(self):
        _FakeClock.now += 0.001
        return _FakeClock.now
    def sleep(self, seconds):
        _FakeClock.now += seconds
        _note({"slept": seconds})
    def __getattr__(self, name):
        return getattr(_real_time, name)
merge.time = _FakeClock()
merge.LOAD_WAIT_SECONDS = __WAIT__
merge.lints_running = lambda: __RUNNING__
_real_sh = merge.sh
def _sh(args, *rest, **kwargs):
    if "--lint" in args:  # a ci-job lint run: the bound it is given
        _note({"bound": kwargs.get("timeout")})
    return _real_sh(args, *rest, **kwargs)
merge.sh = _sh
'''

# The readings (load1, cpus) in order, the last one repeating. Each reading logs whether the lint's slot lock is held, tested on a
# fresh fd: a second open file description conflicts with a flock held in this process too.
LOAD_READS = '''import fcntl, os
_READS = __READS__
_seen = [0]
def _read_cpu_load():
    i = min(_seen[0], len(_READS) - 1)
    _seen[0] += 1
    path = os.path.join(os.environ["CLAUDE_CONFIG_DIR"], "state", "lane-lint-slots", "slot-0.lock")
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o666)
    held = False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fd, fcntl.LOCK_UN)
    except BlockingIOError:
        held = True
    finally:
        os.close(fd)
    _note({"read": list(_READS[i]), "slot_held": held})
    return _READS[i]
merge.read_cpu_load = _read_cpu_load
'''

def load_seams(log, reads, running, wait, no_getloadavg):
    """The seam text of a load run: LOAD_SEAMS; LOAD_READS when `reads` names readings; and, with `no_getloadavg`, os.getloadavg
    deleted, as on Windows, so merge's own reader must find no load."""
    text = LOAD_SEAMS.replace("__LOG__", repr(log)).replace("__WAIT__", repr(wait)).replace("__RUNNING__", repr(running))
    if reads is not None:
        text += LOAD_READS.replace("__READS__", repr([tuple(r) for r in reads]))
    if no_getloadavg:
        text += "import os\ndel os.getloadavg\n"
    return text

def high_load(read, running):
    """A reading holds a lint back while the 1-minute load, less the lints running, is at or above the CPU count the reader gave."""
    return read["load"] - running >= read["cpus"]

def no_load_reading(case):
    """merge's own reader gives no reading in this process, so no case here waits for the real load. create=True: the patch also
    holds on a merge with no reader yet, and its stop removes what it made."""
    patch = unittest.mock.patch.object(merge, "read_cpu_load", lambda: None, create=True)
    patch.start()
    case.addCleanup(patch.stop)


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

    def run_events(self):
        """This case's log in the order it was written. The stub's runs: {"kind": "start", ...the start record} when a run's ci-job
        starts, {"kind": "end", "pid": pid} when it ends (a run killed before its end has no end event; the plan is no run). A load run
        adds {"kind": "read", "load", "cpus", "slot_held"}, {"kind": "sleep", "seconds"} and {"kind": "bound", "seconds"} (LOAD_SEAMS)."""
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
                elif "read" in rec:
                    events.append({"kind": "read", "load": rec["read"][0], "cpus": rec["read"][1], "slot_held": rec["slot_held"]})
                elif "slept" in rec:
                    events.append({"kind": "sleep", "seconds": rec["slept"]})
                elif "bound" in rec:
                    events.append({"kind": "bound", "seconds": rec["bound"]})
        return events

    def lint_events(self):
        """The stub's runs only, in the order written: run_events without the load records."""
        return [e for e in self.run_events() if e["kind"] in ("start", "end")]


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
        no_load_reading(self)

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
        tm.put(harness, harness_for(self.stub))
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
        tm.put(harness, harness_for(self.stub))
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

    def start_lane(self, stub, *argv, checkout=None, slots=None, bound=None, text=None):
        """Start `merge <argv>` in `checkout` (default: the lane checkout), in a process of its own, with the ci-job stub at `stub` and
        the seams of harness_text, or the harness `text` a case gives (load_run). Its temp files land in this case's folder. -> the Popen;
        finish() reads its result."""
        harness = os.path.join(self.t, "lane-lint-%s.py" % uuid.uuid4().hex)
        tm.put(harness, text if text is not None else harness_text(stub, slots, bound))
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

    def load_run(self, *argv, reads=None, running=0, wait=30, no_getloadavg=False, stub=None, checkout=None, bound=None):
        """Run `merge <argv>` in a process of its own with the load seams (LOAD_SEAMS). `reads` are the (load1, cpus) readings in order,
        the last one repeating; `running` is what lints_running reads; `wait` is LOAD_WAIT_SECONDS; `bound` is LINT_SECONDS. `reads=None`
        keeps merge's own reader, which must then find no os.getloadavg (`no_getloadavg`, as on Windows), so no real load is read.
        One slot, so the lint's own lock is the slot the readings check. -> (rc, stdout and stderr together, run_events())."""
        assert reads is not None or no_getloadavg, "a load case must give readings or delete os.getloadavg: it reads no real load"
        stub = stub or self.write_stub(PASSING, 0)
        if os.path.exists(self.log):
            os.remove(self.log)
        seams = seam_lines(slots=1, bound=bound) + load_seams(self.log, reads, running, wait, no_getloadavg)
        text = harness_for(stub, seams, load=NO_LOAD if reads is not None else "")
        rc, out, err = self.finish(self.start_lane(stub, *argv, checkout=checkout, text=text))
        return rc, out + err, self.run_events()

    def first_start(self, events):
        """The index of the first ci-job start in `events`, or the number of events when none started."""
        return next((i for i, e in enumerate(events) if e["kind"] == "start"), len(events))

    def sleeps_before_first_start(self, events):
        """The load-wait sleeps that came before the first ci-job start."""
        return [e for e in events[:self.first_start(events)] if e["kind"] == "sleep"]

    def assert_waited_then_started(self, events, running):
        """The load wait, read from the run's events: the ci-job starts after at least two readings, every reading before the last is
        high, the last is low, and each reading was taken with the lint's slot held."""
        self.assertLess(self.first_start(events), len(events), "the ci-job never started: " + repr(events))
        reads = [e for e in events[:self.first_start(events)] if e["kind"] == "read"]
        self.assertGreaterEqual(len(reads), 2, "the ci-job started after %d load reading(s), with no wait for the load to fall: %r" % (len(reads), reads))
        self.assertTrue(all(high_load(r, running) for r in reads[:-1]), "the ci-job started while a load reading was still high: %r" % reads)
        self.assertFalse(high_load(reads[-1], running), "the ci-job started on a high load reading: %r" % reads[-1])
        self.assertTrue(all(r["slot_held"] for r in reads), "a load reading was taken without the lint's slot held: %r" % reads)

    def test_a_lint_waits_while_the_load_is_at_or_above_the_cpu_count_then_passes_once_it_falls(self):
        """Two high readings, then a low one: the ci-job starts after the low reading, with the lint's slot held, and its PASS is the verdict."""
        rc, out, events = self.load_run("--lane-lint", self.head("feat"), reads=[(10.0, 4), (10.0, 4), (1.0, 4)])
        self.assert_waited_then_started(events, running=0)
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(pass_lines(out)), 1, out)

    def test_a_lint_that_waits_for_the_load_then_fails_refuses_with_the_fail_verdict(self):
        """The same wait, then a ci-job that FAILs: the lint refuses on the FAIL line and never reads the run as a pass."""
        rc, out, events = self.load_run("--lane-lint", self.head("feat"), reads=[(10.0, 4), (1.0, 4)], stub=self.write_stub(FAILING, 1))
        self.assert_waited_then_started(events, running=0)
        self.assertEqual(rc, 1, out)
        self.assertTrue(any("comment narration" in line and "FAIL" in line for line in out.splitlines()), out)
        self.assertEqual(pass_lines(out), [], out)

    def test_a_load_that_stays_high_past_the_bound_reads_unknown_and_the_ci_job_never_starts(self):
        """A load of 9.75 on 3 CPUs that never falls, with a 37 s bound on the wait: the ci-job never starts, the verdict is unknown and
        never a PASS, the line names the load, the CPU count and the seconds waited, and the lint's tree is gone."""
        rc, out, events = self.load_run("--lane-lint", self.head("feat"), reads=[(9.75, 3)], wait=37)
        self.assertEqual([e for e in events if e["kind"] == "start"], [], "the ci-job started under a load of 9.75 on 3 CPUs: " + out)
        self.assertEqual(rc, 1, out)
        self.assertEqual(pass_lines(out), [], out)
        load_lines = [line for line in out.splitlines() if "load" in line.lower()]
        self.assertTrue(load_lines, "no line names the load: " + out)
        numbers = [float(n) for line in load_lines for n in re.findall(r"\d+(?:\.\d+)?", line)]
        seconds = [float(n) for line in load_lines for n in re.findall(r"(\d+(?:\.\d+)?) s\b", line)]
        self.assertIn(9.75, numbers, "the load line does not name the load 9.75: " + "\n".join(load_lines))
        self.assertIn(3.0, numbers, "the load line does not name the 3 CPUs: " + "\n".join(load_lines))
        self.assertTrue(any(s >= 37 for s in seconds), "the load line does not name 37 s or more of waiting: " + "\n".join(load_lines))
        self.assertEqual(self.worktrees(), 1)

    def test_the_ci_job_bound_stays_lint_seconds_and_counts_from_the_ci_job_start(self):
        """The bound on the ci-job run stays LINT_SECONDS and counts from the ci-job's start: after a load wait the run is still handed the
        full bound. The case reads the timeout ci_job_run gives sh; the stub's run is quick and passes."""
        self.assertEqual(merge.LINT_SECONDS, 1200)
        rc, out, events = self.load_run("--lane-lint", self.head("feat"), reads=[(10.0, 4), (1.0, 4)], bound=6)
        self.assertTrue(self.sleeps_before_first_start(events), "no load wait came before the ci-job start: " + repr(events))
        self.assertEqual([e["seconds"] for e in events if e["kind"] == "bound"], [6], "the ci-job run was not handed LINT_SECONDS as its bound")
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(pass_lines(out)), 1, out)

    def test_with_no_load_reading_the_lint_starts_at_once_and_never_waits(self):
        """os.getloadavg is missing, as on Windows: merge reads no load, so the lint waits for none and starts at once."""
        rc, out, events = self.load_run("--lane-lint", self.head("feat"), no_getloadavg=True)
        self.assertEqual(self.sleeps_before_first_start(events), [], "the lint waited with no load reading: " + repr(events))
        self.assertEqual(len([e for e in events if e["kind"] == "start"]), 1, out)
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(pass_lines(out)), 1, out)

    def test_a_low_load_starts_the_ci_job_at_once(self):
        """The control: a load under the CPU count starts the ci-job at once, with no wait."""
        rc, out, events = self.load_run("--lane-lint", self.head("feat"), reads=[(0.5, 4)])
        self.assertEqual(self.sleeps_before_first_start(events), [], "a low load still waited: " + repr(events))
        self.assertEqual(len([e for e in events if e["kind"] == "start"]), 1, out)
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(pass_lines(out)), 1, out)

    def test_the_lints_that_run_come_off_the_load_before_it_is_compared(self):
        """One lint runs its ci-job now. 5.0 less 1 is 4.0, at 4 CPUs, so the lint waits; 4.5 less 1 is 3.5, under 4, so it starts.
        Without the subtraction, the second reading would hold the lint too."""
        rc, out, events = self.load_run("--lane-lint", self.head("feat"), reads=[(5.0, 4), (4.5, 4)], running=1)
        self.assert_waited_then_started(events, running=1)
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(pass_lines(out)), 1, out)

    def test_a_load_exactly_at_the_cpu_count_holds_the_lint(self):
        """At or above holds: a reading of 4.0 on 4 CPUs holds the lint, and 3.0 lets it start."""
        rc, out, events = self.load_run("--lane-lint", self.head("feat"), reads=[(4.0, 4), (3.0, 4)])
        self.assert_waited_then_started(events, running=0)
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(pass_lines(out)), 1, out)


HOOKS_DIR = os.path.join(os.path.dirname(HERE), "hooks")  # guard_core, the lock a lint's run marker and slot take
HOLD_CHILD = '''import os, sys
sys.path.insert(0, __HOOKS__)
import guard_core
fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o666)
if not guard_core.try_lock_fd(fd):
    print("busy", flush=True)
    sys.exit(3)
print("held", flush=True)
sys.stdin.read()  # the lock is held until the parent closes stdin; this process's exit frees it
'''


class LintMarkers(unittest.TestCase):
    """The running markers the load wait counts: merge.lints_running and merge.lint_running, run for real in this process on a temp
    config folder. The load cases above patch lints_running to a constant, so these cases read the count and the marker hold.
    The slot count is 2, so the full state does not depend on the CPU count. Cost per case: one temp folder, at most one child process."""

    def setUp(self):
        cfg = tempfile.mkdtemp(prefix="lint-markers-", dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, cfg, True)
        for patch in (unittest.mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": cfg}),
                      unittest.mock.patch.object(merge, "lint_slots", lambda: 2)):
            patch.start()
            self.addCleanup(patch.stop)
        self.folder = merge.lint_slot_folder()

    def make_markers(self):
        """The full state: every marker file exists and none is held, as a lint leaves its marker when it exits. -> the marker files."""
        os.makedirs(self.folder, exist_ok=True)
        for path in merge.run_marker_paths(create=True):
            open(path, "a").close()
        return merge.run_marker_paths()

    def locked(self, path):
        """True when another holder has the lock on `path`: a fresh fd's try fails while the lock is held."""
        fd = os.open(path, os.O_RDWR)
        try:
            if guard_core.try_lock_fd(fd):
                guard_core.unlock_fd(fd)
                return False
            return True
        finally:
            os.close(fd)

    def hold_in_child(self, path):
        """A child process takes the lock on `path` the way a lint does, and holds it until release_child closes its stdin.
        -> the child's Popen, once the child reports `held`. A child that cannot take the lock fails the case."""
        os.makedirs(self.folder, exist_ok=True)
        code = HOLD_CHILD.replace("__HOOKS__", repr(HOOKS_DIR))
        proc = subprocess.Popen([sys.executable, "-c", code, path], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.release_child, proc)
        line = proc.stdout.readline()
        if line.strip() != "held":
            proc.wait(timeout=60)
            self.fail("the child did not hold %s (it said %r): %s" % (path, line.strip(), proc.stderr.read()))
        return proc

    def release_child(self, proc):
        """Close the child's stdin, so it exits and frees its lock, then wait for it. Safe to call twice."""
        if not proc.stdin.closed:
            proc.stdin.close()
        proc.wait(timeout=60)
        proc.stdout.close()
        proc.stderr.close()

    def test_with_no_marker_held_lints_running_counts_none(self):
        """The empty state: no lint folder yet, so no marker is counted, and the count writes no file. The full state: every marker
        file exists and none is held, so none is counted either."""
        self.assertFalse(os.path.exists(self.folder), "the case starts with a lint folder already made")
        empty = merge.lints_running()
        self.assertEqual(empty, 0, "lints_running counted %d with no lint folder, want 0" % empty)
        self.assertFalse(os.path.exists(self.folder), "lints_running made the lint folder: a count must write no file")
        markers = self.make_markers()
        self.assertEqual(len(markers), 2, "the full state did not get one marker file per slot: %r" % markers)
        held = merge.lints_running()
        self.assertEqual(held, 0, "lints_running counted %d unheld marker file(s), want 0" % held)

    def test_inside_lint_running_the_count_is_one_and_zero_after_it_exits(self):
        """The marker a lint holds counts for the lint's body, and stops counting when lint_running exits."""
        with merge.lint_running():
            inside = merge.lints_running()
            self.assertEqual(inside, 1, "lints_running counted %d inside lint_running, want 1: the marker this lint holds" % inside)
        after = merge.lints_running()
        self.assertEqual(after, 0, "lints_running counted %d after lint_running exited, want 0" % after)

    def test_a_marker_another_process_holds_is_counted_until_that_process_exits(self):
        """A run marker that another process holds counts, and stops counting when that process exits."""
        holder = self.hold_in_child(merge.run_marker_paths(create=True)[0])
        held = merge.lints_running()
        self.assertEqual(held, 1, "lints_running counted %d while another process held a run marker, want 1" % held)
        self.release_child(holder)
        released = merge.lints_running()
        self.assertEqual(released, 0, "lints_running still counted %d after the other process exited, want 0" % released)

    def test_a_marker_another_process_holds_and_a_lint_here_takes_the_next_one_and_both_count(self):
        """Two markers held at once: run-0 by another process, then lint_running in this process takes the first free marker, run-1.
        lints_running counts both. The marker check comes first, so the count is read with the lint's marker in place."""
        self.hold_in_child(merge.run_marker_paths(create=True)[0])
        with merge.lint_running():
            run1 = os.path.join(self.folder, "run-1.lock")
            self.assertTrue(os.path.exists(run1) and self.locked(run1),
                            "lint_running did not take run-1 while run-0 was held by another process")
            both = merge.lints_running()
            self.assertEqual(both, 2, "lints_running counted %d with two markers held, one by another process and one by this lint, want 2" % both)

    def test_a_lint_that_holds_a_slot_and_no_run_marker_is_not_counted(self):
        """A waiting lint holds a slot (lint_slot) and no run marker. The slot lock is first shown held, then the count reads 0."""
        self.make_markers()
        with merge.lint_slot():
            self.assertTrue(self.locked(os.path.join(self.folder, "slot-0.lock")), "lint_slot did not hold slot-0, so the case tests no waiting lint")
            counted = merge.lints_running()
            self.assertEqual(counted, 0, "lints_running counted %d for a lint that holds a slot and no run marker, want 0" % counted)


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
        no_load_reading(self)
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
