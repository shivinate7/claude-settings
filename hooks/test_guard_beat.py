#!/usr/bin/env python3
"""The progress beat of hooks/test_guard.py (decision stall-watch).

A full run of test_guard.py can print nothing for minutes, and the stall watch then reports a stall on a
healthy run. The runner owes a line at least every GUARD_HEARTBEAT seconds of quiet (default 60). The line
goes to stderr, flushed, and is appended to STALL_WATCH_BEAT when that is set. Each run class runs test_guard.py
on one family (GUARD_FAMILY=branch-worktree: 64 cases and one log check, 16-18 s per family run) and reads what it
printed. The watch classes run that family under hooks/stall_watch.py with a short limit. The defs classes run
the beat's own defs with a fake clock, so no suite runs. The run folder and its sweep are the shared helper's
(lint/_test_temp.py); its sweep is proved in lint/test_find_copies.py. The class HoldersEndWithTheRun proves that
a run which exits early stops the holders its kill cases started.

    python3 hooks/test_guard_beat.py
"""
import ast
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from collections import namedtuple
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lint"))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (the one home, lint/_test_temp.py)
sys.path.insert(0, HERE)
import stall_watch  # noqa: E402  the watcher, and its exit code on a stall (STALL_EXIT)

RUN_FOLDER = _test_temp.run_folder()
CONFIG_DIR = os.path.join(RUN_FOLDER, "config")
os.makedirs(CONFIG_DIR)
SUITE = os.path.join(HERE, "test_guard.py")
SUITE_CMD = [sys.executable, SUITE]
WATCHER = os.path.join(HERE, "stall_watch.py")
FAMILY = "branch-worktree"
TINY = "0.001"  # a quiet stretch of a millisecond: every checkpoint that finds one beats
OFF = "100000"  # a quiet stretch no run reaches: the beat never fires
WATCH_QUIET = "8"  # the watcher's limit in seconds: above the ~2 s import and registration, far below 300 s
TIMEOUT = 900  # a bound against a hang, never an assert
CLEAN_WAIT = 10.0  # seconds for a run's holders to end once the run is down: a hang cap, never a pause
REAL_SECTIONS = os.path.normpath(os.path.join(HERE, "..", "tests", "guard"))  # the section files the runner loads
PY_SLEEP = [sys.executable, "-c", "import time; time.sleep(300)"]  # a holder: it ends when the test ends it
PY_IGNORES_TERM = [sys.executable, "-c", "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                                         "print('ready', flush=True); time.sleep(300)"]
BEAT = "test_guard: still running"  # the beat line's prefix; a case line starts with PASS, FAIL or SKIP
CASE_START = ("PASS", "FAIL", "SKIP")
SUMMARY = "test_guard PASS:"  # the last line of a family run that passed
# Set by a wrapper or an outer run. A child of this test must not read them. PYTHONUNBUFFERED would
# make stdout unbuffered whatever the runner flushes, so a missing flush could not show.
INHERITED = ("STALL_WATCH_BEAT", "GUARD_HEARTBEAT", "GUARD_FAMILY", "GUARD_SHARD", "GUARD_TESTS",
             "MUTATE_ONLY", "GUARD_TIMING", "PYTHONUNBUFFERED", "GUARD_SECTION_DIR", "GUARD_HOLDER_RECORD")

Run = namedtuple("Run", "rc out err")
Watched = namedtuple("Watched", "watch_rc watch_out job_rc job_out")


def case_lines(text):
    return [line for line in text.splitlines() if line.startswith(CASE_START)]


def beat_lines(text):
    return [line for line in text.splitlines() if line.startswith(BEAT)]


def suite_env(heartbeat=None, beat_file=None):
    """The environment of one family run: the caller's, minus the knobs of an outer run, plus this run's."""
    env = {k: v for k, v in os.environ.items() if k not in INHERITED}
    env["GUARD_FAMILY"] = FAMILY
    env["CLAUDE_CONFIG_DIR"] = CONFIG_DIR
    if heartbeat is not None:
        env["GUARD_HEARTBEAT"] = heartbeat
    if beat_file is not None:
        env["STALL_WATCH_BEAT"] = beat_file
    return env


def run_suite(heartbeat=None, beat_file=None, merged=False):
    """Run test_guard.py on FAMILY and return a Run. With merged, stdout and stderr share one file, so
    the order of lines is the order they were written; otherwise stdout is a pipe and stderr is a file.
    stderr is never a pipe: a `sleep` the suite leaves behind holds a pipe open, and the run would wait."""
    env = suite_env(heartbeat, beat_file)
    with tempfile.TemporaryFile(dir=RUN_FOLDER) as err:
        if merged:
            with tempfile.TemporaryFile(dir=RUN_FOLDER) as out:
                rc = subprocess.run(SUITE_CMD, stdout=out, stderr=subprocess.STDOUT, env=env,
                                    timeout=TIMEOUT).returncode
                out.seek(0)
                return Run(rc, out.read().decode("utf-8", "replace"), "")
        done = subprocess.run(SUITE_CMD, stdout=subprocess.PIPE, stderr=err, env=env, timeout=TIMEOUT)
        err.seek(0)
        return Run(done.returncode, done.stdout.decode("utf-8", "replace"),
                   err.read().decode("utf-8", "replace"))


def kill_job(job):
    """End a job this test started, and what it started, when the test ends while the job still runs. TERM goes to the
    job's own pid first, so a runner that handles it runs its holder reap. After CLEAN_WAIT the job's session gets
    SIGKILL, which reaches a child that did not handle TERM."""
    try:
        os.kill(job.pid, signal.SIGTERM)
    except OSError:
        pass
    try:
        job.wait(timeout=CLEAN_WAIT)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(job.pid, signal.SIGKILL)  # the job's own session (start_new_session)
    except (AttributeError, OSError):
        job.kill()


EARLY_EXIT = "refused-by-the-test"  # a GUARD_TESTS value the runner refuses before any case runs
EARLY_EXIT_RC = 2  # the runner's exit for a value it refuses
NOTHING_RAN = "Nothing ran."


def read_pids(path):
    """The pids in a record file the runner wrote, or [] when it wrote none."""
    try:
        with open(path, encoding="utf-8") as record:
            return [int(line) for line in record.read().split()]
    except OSError:
        return []


def group_members(group):
    """The pids of the live processes in process group `group`. The child leads its own group (start_new_session),
    so a holder that did not call setsid is in it. A zombie is not listed: its exit is over."""
    rows = subprocess.run(["ps", "-axo", "pid=,pgid=,stat="], capture_output=True, text=True,
                          timeout=30).stdout.splitlines()
    members = []
    for row in rows:
        fields = row.split()
        if len(fields) == 3 and fields[1] == str(group) and not fields[2].startswith("Z"):
            members.append(int(fields[0]))
    return members


def still_alive(pids):
    """The pids that have not ended. A zombie has ended: its exit waits only to be collected."""
    alive = []
    for pid in pids:
        stat = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True,
                              timeout=30).stdout.strip()
        if stat and not stat.startswith("Z"):
            alive.append(pid)
    return alive


def start_time(pid):
    """The start time ps gives `pid` now: what a holder's record holds from the moment it starts."""
    return subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True,
                          timeout=30).stdout.strip()


def pids_and_cwds():
    """{pid: cwd} for each live process: /proc on Linux, lsof -Fn on macOS (lsof prints a cwd path, never arguments)."""
    pids = [int(row) for row in subprocess.run(["ps", "-axo", "pid="], capture_output=True, text=True,
                                              timeout=30).stdout.split() if row.isdigit()]
    cwds = {}
    if os.path.isdir("/proc/self/cwd"):
        for pid in pids:
            try:
                cwds[pid] = os.readlink("/proc/%d/cwd" % pid)
            except OSError:
                pass
        return cwds
    done = subprocess.run(["lsof", "-a", "-d", "cwd", "-Fn", "-p", ",".join(str(pid) for pid in pids)],
                          capture_output=True, text=True, timeout=120)
    pid = None
    for line in done.stdout.splitlines():
        if line.startswith("p"):
            pid = int(line[1:])
        elif line.startswith("n") and pid is not None:
            cwds[pid] = line[1:]
    return cwds


def run_holders(child_pid, folders):
    """The live pids a kill child started, found without its help: each process whose working directory lies under one
    of `folders` (the child's own cwd, which its holders inherit) or in the child's run folder (<child pid>-<32 hex>,
    where its cases keep their fixtures). The test's own pid and the child's are left out."""
    run = re.compile(r"(^|/)%d-[0-9a-f]{32}(/|$)" % child_pid)
    real = [os.path.realpath(folder) for folder in folders]
    skip = (child_pid, os.getpid())
    found = []
    for pid, cwd in pids_and_cwds().items():
        if pid in skip:
            continue
        if run.search(cwd) or any(cwd == folder or cwd.startswith(folder + os.sep) for folder in real):
            found.append(pid)
    return found


class NoOwned:
    """Stands in for the kill section's OWNED sleep, which the reap kills and waits for."""

    def kill(self):
        pass

    def wait(self, timeout=None):
        return 0


def reap_namespace(pids, starts, cap=5.0):
    """hooks/test_guard.py's reap in a namespace of its own, over the holders `pids` with the start times `starts` they
    recorded. The os, subprocess and clock are real. The signal module is a stand-in, since the reap's TERM handling
    would otherwise change this test process. HOLDER_WAIT is `cap`, a hang cap. The names the file has are run:
    stop_holders and holder_ended always, and the newer helpers when the file has them."""
    fake_signal = types.SimpleNamespace(SIGTERM=signal.SIGTERM, SIG_IGN=signal.SIG_IGN, signal=lambda *args: None)
    return Defs(["stop_holders", "holder_ended"], optional=["reap_holders", "holder_start"],
                extra={"os": os, "subprocess": subprocess, "signal": fake_signal, "time": time,
                       "OWNED": NoOwned(), "ORPHAN_PIDS": list(pids), "HOLDER_STARTS": dict(starts),
                       "HOLDER_RECORD": "", "HOLDER_WAIT": cap, "HOLDERS_STOPPED": []})


def section_folder_with_unknown_family(name):
    """A section folder: a symlink to each real section, and one more section, numbered above them all, that sets a FAMILY
    FAMILIES does not name and holds one case under it. The sections load and the kill section starts its holders, and
    the run then stops at its family check. Symlinks, so no section is copied."""
    folder = os.path.join(RUN_FOLDER, name)
    os.makedirs(folder)
    for entry in sorted(os.listdir(REAL_SECTIONS)):
        if entry.endswith(".py"):
            os.symlink(os.path.join(REAL_SECTIONS, entry), os.path.join(folder, entry))
    with open(os.path.join(folder, "s99999-unknown-family.py"), "w", encoding="utf-8") as f:
        f.write('# section 99999\nFAMILY = "not-a-family"\n'
                'sh("holders: a case under a family FAMILIES does not name", "echo hi", "allow", cwd=NOGIT)\n')
    return folder


class KillRun:
    """One runner child, in its own session, its own cwd and its own record file. The holders it starts inherit that cwd,
    so finish() can find them when the runner's own reap cannot be trusted to have run."""

    def __init__(self, name, family="kill", tests=None, section_dir=None, record=None):
        self.cwd = os.path.join(RUN_FOLDER, name + "-cwd")
        os.makedirs(self.cwd, exist_ok=True)
        self.record = record or os.path.join(RUN_FOLDER, name + "-holders.txt")
        self.out_path = os.path.join(RUN_FOLDER, name + "-out.txt")
        env = suite_env()
        env["GUARD_HOLDER_RECORD"] = self.record
        if family:
            env["GUARD_FAMILY"] = family
        if tests:
            env["GUARD_TESTS"] = tests
        if section_dir:
            env["GUARD_SECTION_DIR"] = section_dir
        with open(self.out_path, "wb") as out:
            self.child = subprocess.Popen(SUITE_CMD, stdout=out, stderr=subprocess.STDOUT, env=env, cwd=self.cwd,
                                          start_new_session=True)

    def output(self):
        with open(self.out_path, encoding="utf-8", errors="replace") as f:
            return f.read()

    def wait_exit(self, cap):
        """The run's exit code once it ends, or None when it is still running after `cap` seconds."""
        try:
            return self.child.wait(timeout=cap)
        except subprocess.TimeoutExpired:
            return None

    def wait_for_output(self, prefixes, cap):
        """True once the run has printed a line that starts with one of `prefixes`. False when `cap` seconds pass first,
        or the run ends first. A hang cap, never a pause: it polls the output file."""
        deadline = time.monotonic() + cap
        while True:
            if any(line.startswith(prefixes) for line in self.output().splitlines()):
                return True
            if time.monotonic() >= deadline or self.child.poll() is not None:
                return False
            time.sleep(0.05)

    def holders_alive(self):
        """The holders of this run still alive: the pids its record lists, its process group, and the processes its
        cwd and run folder place in it. The record misses a run that died before its reap; the group misses a holder
        that called setsid; the cwd finds both."""
        pids = set(read_pids(self.record)) | set(group_members(self.child.pid)) | set(run_holders(self.child.pid, [self.cwd]))
        pids.discard(self.child.pid)
        return still_alive(sorted(pids))

    def finish(self):
        """End the run and every holder it left, and return the holders still alive once the run was down, before that
        cleanup. A run still up is ended by kill_job, which is the timeout path. The caller asserts on the return value.
        Whatever it returns, this leaves none running: the test ends what it finds, so a red run leaks none."""
        if self.child.poll() is None:
            kill_job(self.child)
        else:
            self.child.wait()
        left = self.holders_alive()
        deadline = time.monotonic() + CLEAN_WAIT
        while left and time.monotonic() < deadline:
            time.sleep(0.05)
            left = self.holders_alive()
        for pid in left:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        return left


def watched_run(name, heartbeat):
    """Run one family in the background under hooks/stall_watch.py, as the stall watch runs a background job.
    The job writes its output to a file the watcher does not read, and the watcher's --log is an idle file,
    so the beat file is the only thing the watcher reads. The watcher exits 0 when the job ends, or 3 after
    WATCH_QUIET seconds with no byte. After a stall the job runs on and is waited for, so its own cleanup runs."""
    beat_file = os.path.join(RUN_FOLDER, name + "-beat.txt")
    job_file = os.path.join(RUN_FOLDER, name + "-job.txt")
    idle_file = os.path.join(RUN_FOLDER, name + "-idle.txt")
    open(beat_file, "w").close()  # the stall-watch wrapper creates the beat file first (`: > BEAT`)
    open(idle_file, "w").close()
    with open(job_file, "wb") as out:
        job = subprocess.Popen(SUITE_CMD, stdout=out, stderr=subprocess.STDOUT,
                               env=suite_env(heartbeat, beat_file), start_new_session=True)
    # The watcher counts the CPU time of the process tree it watches as life (decision stall-watch), and a family
    # run works all the while. So it watches a stand-in that blocks on a pipe, uses no CPU, and exits when the
    # job ends: the beat file stays the only thing it can read.
    standin = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.read()"], stdin=subprocess.PIPE)
    waiter = threading.Thread(target=lambda: (job.wait(), standin.stdin.close()), daemon=True)
    waiter.start()
    try:
        watcher = subprocess.run([sys.executable, WATCHER, "--watch-pid", str(standin.pid), "--log", idle_file,
                                  "--quiet", WATCH_QUIET, "--beat", beat_file],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=TIMEOUT)
        job_rc = job.wait(timeout=TIMEOUT)
    finally:
        if job.poll() is None:
            kill_job(job)
        waiter.join(timeout=30)
        standin.wait(timeout=30)
    with open(job_file, "rb") as f:
        job_out = f.read().decode("utf-8", "replace")
    return Watched(watcher.returncode, watcher.stdout.decode("utf-8", "replace"), job_rc, job_out)


class Defs:
    """The named top-level defs of hooks/test_guard.py, run in one namespace with a fake clock (`now`) and a
    fake print (`printed`), so a beat is measured without running the suite. A def that is missing from the
    file fails here, so a moved beat cannot pass by vanishing."""

    def __init__(self, names, heartbeat=60.0, beat_file="", extra=None, optional=()):
        with open(SUITE, encoding="utf-8") as f:
            tree = ast.parse(f.read(), SUITE)
        found = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
        missing = [name for name in names if name not in found]
        if missing:
            raise AssertionError("hooks/test_guard.py has no top-level def %s: the beat moved, so this test "
                                 "must follow it" % missing[0])
        self.now = 0.0
        self.printed = []
        self.ns = {
            "math": math,
            "sys": sys,
            "time": types.SimpleNamespace(monotonic=lambda: self.now),
            "print": lambda *args, **kw: self.printed.append(" ".join(str(a) for a in args)),
            "GUARD_HEARTBEAT": float(heartbeat),
            "BEAT_FILE": beat_file,
            "QUIET_SINCE": [0.0],
        }
        self.ns.update(extra or {})  # a caller's stand-ins for the names the defs use: a fake signal, or the real os
        # `optional` names run when the file has them, so a def a later change adds does not fail an older file
        chosen = [found[name] for name in names] + [found[name] for name in optional if name in found]
        module = ast.Module(body=chosen, type_ignores=[])
        ast.fix_missing_locations(module)
        exec(compile(module, SUITE, "exec"), self.ns)

    def call(self, name, *args):
        return self.ns[name](*args)


class UnderPipe(unittest.TestCase):
    """stdout is a pipe, as under `| tail`. The beat must still reach stderr and the beat file, and the run
    must still pass: the beat changes no verdict."""

    @classmethod
    def setUpClass(cls):
        cls.beat_file = os.path.join(RUN_FOLDER, "stall-watch-beat.txt")
        open(cls.beat_file, "w").close()  # the stall-watch wrapper creates the beat file first (`: > BEAT`)
        cls.captured = run_suite(heartbeat=TINY, beat_file=cls.beat_file)

    def test_the_run_exits_zero_with_its_summary(self):
        self.assertEqual(self.captured.rc, 0, "the run with the beat on exited %d, not 0" % self.captured.rc)
        self.assertIn(SUMMARY, self.captured.out, "the run with the beat on printed no summary line")

    def test_the_run_reaches_its_cases(self):
        self.assertTrue(case_lines(self.captured.out), "no case line on stdout: the run never reached a case")

    def test_the_beat_reaches_stderr_under_a_pipe(self):
        self.assertTrue(beat_lines(self.captured.err), "no beat line on stderr while stdout was a pipe")

    def test_the_beat_file_is_appended(self):
        with open(self.beat_file, encoding="utf-8", errors="replace") as f:
            self.assertTrue(beat_lines(f.read()), "STALL_WATCH_BEAT holds no beat line after the run")


class BetweenCases(unittest.TestCase):
    """stdout and stderr share one file. A beat must fall between two case lines: that shows the beat
    fires during the run, not at import, and that each case line is flushed as it is printed (a held
    line would land after every beat). The run must also exit 0 with its summary."""

    @classmethod
    def setUpClass(cls):
        cls.captured = run_suite(heartbeat=TINY, merged=True)
        cls.lines = cls.captured.out.splitlines()

    def test_the_run_exits_zero_with_its_summary(self):
        self.assertEqual(self.captured.rc, 0, "the run with the beat on exited %d, not 0" % self.captured.rc)
        self.assertIn(SUMMARY, self.captured.out, "the run with the beat on printed no summary line")

    def test_a_beat_falls_between_the_first_two_case_lines(self):
        cases = [i for i, line in enumerate(self.lines) if line.startswith(CASE_START)]
        self.assertGreaterEqual(len(cases), 2, "fewer than two case lines: the run did not reach two cases")
        beats = [i for i, line in enumerate(self.lines) if line.startswith(BEAT)]
        self.assertTrue([i for i in beats if cases[0] < i < cases[1]],
                        "no beat between case lines %d and %d" % (cases[0] + 1, cases[1] + 1))


class DefaultRun(unittest.TestCase):
    """Control: with GUARD_HEARTBEAT unset, a short run prints no beat."""

    @classmethod
    def setUpClass(cls):
        cls.lines = run_suite(merged=True).out.splitlines()

    def test_a_short_default_run_prints_no_beat(self):
        text = "\n".join(self.lines)
        self.assertTrue(case_lines(text), "no case line in the default run")
        beats = beat_lines(text)
        self.assertFalse(beats, "a beat in a short default run: %r" % beats[:1])


class InvalidHeartbeat(unittest.TestCase):
    def test_an_invalid_value_exits_with_a_message(self):
        for value in ("abc", "0", "nan"):
            with self.subTest(value=value):
                run = run_suite(heartbeat=value, merged=True)
                self.assertNotEqual(run.rc, 0, "GUARD_HEARTBEAT=%s was accepted: the run exited 0" % value)
                self.assertIn("GUARD_HEARTBEAT", run.out,
                              "GUARD_HEARTBEAT=%s exited with no message that names it" % value)
                self.assertFalse(case_lines(run.out), "GUARD_HEARTBEAT=%s ran cases before it failed" % value)


class DefaultInterval(unittest.TestCase):
    def test_the_unset_interval_is_at_most_120_seconds(self):
        value = Defs(["parse_heartbeat"]).call("parse_heartbeat", "")  # "" is GUARD_HEARTBEAT unset
        self.assertTrue(0 < value <= 120, "the unset GUARD_HEARTBEAT is %r seconds: decision stall-watch wants "
                                          "a line at least every 120 s" % value)


class BeatCost(unittest.TestCase):
    """A quiet stretch of N seconds at interval I writes about N / I beat lines to the beat file, however
    many checkpoints it holds: the cost is set by the quiet time, not by the number of cases."""

    def checkpoints(self, defs, seconds, step):
        """One checkpoint every `step` seconds for `seconds` of quiet, the clock moving with them."""
        count = int(round(seconds / step))
        for i in range(1, count + 1):
            defs.now = i * step
            defs.call("beat", "case %d, before it runs" % i)
        return count

    def test_a_full_quiet_stretch_writes_one_line_per_interval(self):
        beat_file = os.path.join(RUN_FOLDER, "cost-full.txt")
        open(beat_file, "w").close()
        defs = Defs(["beat"], heartbeat=10.0, beat_file=beat_file)
        count = self.checkpoints(defs, seconds=100, step=0.5)  # 200 checkpoints in 100 s at I = 10 s
        with open(beat_file, encoding="utf-8") as f:
            lines = f.read().splitlines()
        self.assertEqual(len(lines), 100 // 10, "%d s of quiet at I = 10 s over %d checkpoints wrote %d beat "
                                                "lines, want 10: one per interval" % (100, count, len(lines)))
        self.assertEqual(len(defs.printed), len(lines), "a beat was appended to the file but not printed")

    def test_a_stretch_with_no_quiet_time_writes_nothing(self):
        beat_file = os.path.join(RUN_FOLDER, "cost-empty.txt")
        open(beat_file, "w").close()
        defs = Defs(["beat"], heartbeat=10.0, beat_file=beat_file)
        for i in range(50):  # the clock never moves: no quiet time at all
            defs.call("beat", "case %d, before it runs" % i)
        with open(beat_file, encoding="utf-8") as f:
            self.assertEqual(f.read(), "", "a beat was written with no quiet time: the interval check is gone")


class WatchedBeatOn(unittest.TestCase):
    """The beat on, under the watcher. The watcher reads only the beat file, so a run with no stall proves the
    beat reached the watcher. The job must pass first: a crash at import would also end with no stall."""

    @classmethod
    def setUpClass(cls):
        cls.watched = watched_run("watch-on", TINY)

    def test_the_job_exits_zero_with_its_summary(self):
        self.assertEqual(self.watched.job_rc, 0, "the watched run with the beat on exited %r, not 0"
                         % self.watched.job_rc)
        self.assertIn(SUMMARY, self.watched.job_out, "the watched run with the beat on printed no summary line")

    def test_the_watcher_reports_no_stall(self):
        self.assertNotIn("STALL", self.watched.watch_out, "the watcher reported a stall with the beat on")
        self.assertEqual(self.watched.watch_rc, 0, "the watcher exited %r, not 0" % self.watched.watch_rc)

    def test_the_watcher_relays_the_beat_from_the_beat_file(self):
        self.assertTrue(beat_lines(self.watched.watch_out), "the watcher relayed no beat line from the beat file")


class WatchedBeatOff(unittest.TestCase):
    """Control: the beat off, at the same watcher limit. No byte reaches the watcher for WATCH_QUIET seconds,
    so it must report a stall on a healthy run. Without it, the no-stall arm would pass on a watcher that
    never fires."""

    @classmethod
    def setUpClass(cls):
        cls.watched = watched_run("watch-off", OFF)

    def test_the_job_exits_zero_with_its_summary(self):
        self.assertEqual(self.watched.job_rc, 0, "the watched run with the beat off exited %r, not 0"
                         % self.watched.job_rc)
        self.assertIn(SUMMARY, self.watched.job_out, "the watched run with the beat off printed no summary line")

    def test_the_watcher_reports_a_stall(self):
        self.assertEqual(self.watched.watch_rc, stall_watch.STALL_EXIT,
                         "the watcher exited %r with the beat off, not a stall" % self.watched.watch_rc)
        self.assertIn("STALL", self.watched.watch_out, "the watcher exited with no STALL report")


class HoldersEndWithTheRun(unittest.TestCase):
    """The kill cases start holders: sleeps, python jobs and shell stubs that outlive the run, one of them a python
    holder that calls setsid. The run stops them at its end. A run that stops early must stop them too. The child is
    refused before any case runs, after its holders exist. Its holders are found two ways: those in its process group
    (a holder that did not call setsid shares it) and those the run recorded (GUARD_HOLDER_RECORD), since a holder that
    called setsid leads a group of its own."""

    @unittest.skipIf(os.name == "nt", "the holders are POSIX processes: a process group, and ps")
    def test_no_holder_of_the_run_is_alive_after_an_early_exit(self):
        run = KillRun("holders-early-exit", tests=EARLY_EXIT)
        rc = run.wait_exit(TIMEOUT)
        left = run.finish()
        output = run.output()
        recorded = read_pids(run.record)
        self.assertEqual(rc, EARLY_EXIT_RC, "the run exited %r, not the refusal's %r" % (rc, EARLY_EXIT_RC))
        self.assertIn(NOTHING_RAN, output, "the run did not stop at the refusal: it printed no %r" % NOTHING_RAN)
        self.assertEqual(left, [], "%d holder(s) of the run are alive after its early exit: pids %s"
                         % (len(left), left))
        self.assertTrue(recorded, "the run recorded no holder, so the check above proved nothing")


@unittest.skipIf(os.name == "nt", "the sections symlink, and the holders are POSIX processes: a process group, and ps")
class HoldersEndOnAnExit(unittest.TestCase):
    """The kill section starts its holders at import. A run that ends at a section check, after the section started them,
    must stop them too. This run ends at its family check (a case under a family FAMILIES does not name), which no
    reap that runs only from main() sees."""

    @classmethod
    def setUpClass(cls):
        cls.kill_run = KillRun("unknown-family", family=None, section_dir=section_folder_with_unknown_family("unknown-family"))
        cls.rc = cls.kill_run.wait_exit(TIMEOUT)
        cls.left = cls.kill_run.finish()
        cls.output = cls.kill_run.output()

    @unittest.skipIf(os.name == "nt", "the sections symlink and the holders are POSIX")
    def test_no_holder_is_alive_after_the_run_ends(self):
        self.assertEqual(self.left, [], "%d holder(s) of the run are alive after it ended at a section check: pids %s"
                         % (len(self.left), self.left))

    @unittest.skipIf(os.name == "nt", "the sections symlink and the holders are POSIX")
    def test_the_run_ends_at_the_family_check(self):
        self.assertEqual(self.rc, 1, "the run exited %r, not the family check's 1" % self.rc)
        self.assertTrue("families not in FAMILIES" in self.output, "the run did not stop at the family check")


@unittest.skipIf(os.name == "nt", "SIGTERM to a process group, and the holders, are POSIX")
class HoldersEndOnTerm(unittest.TestCase):
    """A run that is sent SIGTERM mid-run stops its holders and exits with the code for the signal (128 + 15)."""

    @classmethod
    def setUpClass(cls):
        cls.kill_run = KillRun("sigterm-mid-run")
        cls.reached = cls.kill_run.wait_for_output(CASE_START, cap=300)
        cls.rc = None
        if cls.reached:
            os.kill(cls.kill_run.child.pid, signal.SIGTERM)  # the runner alone: its group is not signalled
            cls.rc = cls.kill_run.wait_exit(TIMEOUT)
        cls.left = cls.kill_run.finish()

    @unittest.skipIf(os.name == "nt", "SIGTERM to a process group, and the holders, are POSIX")
    def test_the_run_reached_a_case_before_the_signal(self):
        self.assertTrue(self.reached, "the run printed no case line within 300 s, so it was never sent SIGTERM mid-run")

    @unittest.skipIf(os.name == "nt", "SIGTERM to a process group, and the holders, are POSIX")
    def test_no_holder_is_alive_after_sigterm(self):
        self.assertEqual(self.left, [], "%d holder(s) of the run are alive after SIGTERM: pids %s"
                         % (len(self.left), self.left))

    @unittest.skipIf(os.name == "nt", "SIGTERM to a process group, and the holders, are POSIX")
    def test_the_exit_code_is_the_signal_code(self):
        self.assertEqual(self.rc, 128 + signal.SIGTERM, "the run exited %r after SIGTERM, not %d"
                         % (self.rc, 128 + signal.SIGTERM))


@unittest.skipIf(os.name == "nt", "the holders are POSIX processes: a process group, and ps")
class HoldersEndWhenTheRecordCannotBeWritten(unittest.TestCase):
    """GUARD_HOLDER_RECORD names a directory, so the reap cannot write the record. The reap reports that on stderr and
    still stops every holder, and the run keeps its own exit code: the refusal's 2."""

    @classmethod
    def setUpClass(cls):
        folder = os.path.join(RUN_FOLDER, "record-is-a-folder")
        os.makedirs(folder)
        cls.kill_run = KillRun("record-is-a-folder", tests=EARLY_EXIT, record=folder)
        cls.rc = cls.kill_run.wait_exit(TIMEOUT)
        cls.left = cls.kill_run.finish()

    @unittest.skipIf(os.name == "nt", "the holders are POSIX processes: a process group, and ps")
    def test_no_holder_is_alive_when_the_record_cannot_be_written(self):
        self.assertEqual(self.left, [], "%d holder(s) of the run are alive after a failed record write: pids %s"
                         % (len(self.left), self.left))

    @unittest.skipIf(os.name == "nt", "the holders are POSIX processes: a process group, and ps")
    def test_the_exit_code_is_the_refusal_code(self):
        self.assertEqual(self.rc, EARLY_EXIT_RC, "the run exited %r after a failed record write, not the refusal's %r"
                         % (self.rc, EARLY_EXIT_RC))


@unittest.skipIf(os.name == "nt", "the holders are POSIX processes: a process group, and ps")
class HoldersEndAtTheTimeoutPath(unittest.TestCase):
    """A run still up when the wait for it runs out: the test's timeout path ends it. Its holders must end with it, not
    only the group the kill reaches."""

    @classmethod
    def setUpClass(cls):
        cls.kill_run = KillRun("timeout-path")
        cls.reached = cls.kill_run.wait_for_output(CASE_START, cap=300)
        cls.left = cls.kill_run.finish()  # the run is still up here: this is the timeout path

    @unittest.skipIf(os.name == "nt", "the holders are POSIX processes: a process group, and ps")
    def test_the_run_was_up_with_its_holders(self):
        self.assertTrue(self.reached, "the run printed no case line within 300 s: nothing was running to time out")

    @unittest.skipIf(os.name == "nt", "the holders are POSIX processes: a process group, and ps")
    def test_no_holder_is_alive_after_the_timeout_path(self):
        self.assertEqual(self.left, [], "%d holder(s) of the run are alive after the timeout path: pids %s"
                         % (len(self.left), self.left))


class StopHoldersChecksStartTime(unittest.TestCase):
    """The reap signals a holder only while ps still gives the start time recorded when it started. A pid that a later
    process took has another start time, so the reap leaves it alone. Real sleeps, in the reap's own namespace."""

    @unittest.skipIf(os.name == "nt", "the reap reads start times with ps, which Windows does not have")
    def test_a_pid_whose_start_time_does_not_match_is_not_signalled(self):
        holder = subprocess.Popen(PY_SLEEP)
        try:
            reap = reap_namespace([holder.pid], {holder.pid: "Mon Jan  1 00:00:00 2001"}, cap=2.0)
            reap.call("stop_holders")
            self.assertIsNone(holder.poll(), "the reap signalled pid %d, whose start time is not the one recorded for it"
                              % holder.pid)
        finally:
            holder.kill()
            holder.wait()

    @unittest.skipIf(os.name == "nt", "the reap reads start times with ps, which Windows does not have")
    def test_a_pid_whose_start_time_matches_is_signalled(self):
        holder = subprocess.Popen(PY_SLEEP)
        try:
            reap = reap_namespace([holder.pid], {holder.pid: start_time(holder.pid)}, cap=2.0)
            reap.call("stop_holders")
            self.assertIsNotNone(holder.poll(), "the reap did not signal pid %d, whose start time matches the one "
                                 "recorded for it" % holder.pid)
        finally:
            holder.kill()
            holder.wait()


class StopHoldersNamesAHolderLeftAlive(unittest.TestCase):
    """A holder that ignores SIGTERM outlives the reap's cap. The reap names it on stderr, so the run's output says which
    holder is still running."""

    @unittest.skipIf(os.name == "nt", "the reap reads start times with ps, which Windows does not have")
    def test_a_holder_that_ignores_the_signal_is_named(self):
        holder = subprocess.Popen(PY_IGNORES_TERM, stdout=subprocess.PIPE)
        try:
            ready = holder.stdout.readline()  # the holder has set its handler: a signal before that would end it
            self.assertEqual(ready.strip(), b"ready", "the holder did not start: it printed %r" % ready)
            reap = reap_namespace([holder.pid], {holder.pid: start_time(holder.pid)}, cap=0.5)
            reap.call("stop_holders")
            named = [line for line in reap.printed if str(holder.pid) in line]
            self.assertTrue(named, "no line names holder pid %d, which is still alive after the reap's cap: %r"
                            % (holder.pid, reap.printed[:3]))
        finally:
            holder.kill()
            holder.wait()
            holder.stdout.close()


class SuiteEnvDropsTheCallersKnobs(unittest.TestCase):
    """A family run's environment is this test's own: a value the caller set for its own run must not reach the child."""

    def test_a_callers_section_folder_is_not_passed_on(self):
        with mock.patch.dict(os.environ, {"GUARD_SECTION_DIR": "/no/such/section/folder"}):
            env = suite_env()
        # A boolean, not assertNotIn: its message would print the whole environment, secrets included.
        self.assertFalse("GUARD_SECTION_DIR" in env, "the family run would read the caller's section folder, and a "
                                                      "caller's value would give a false red")

    def test_a_callers_holder_record_is_not_passed_on(self):
        with mock.patch.dict(os.environ, {"GUARD_HOLDER_RECORD": "/no/such/record"}):
            env = suite_env()
        self.assertFalse("GUARD_HOLDER_RECORD" in env, "the family run would write its holders to the caller's record")


if __name__ == "__main__":
    try:
        result = unittest.main(exit=False, verbosity=2).result
    finally:
        shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder
    sys.exit(0 if result.wasSuccessful() else 1)
