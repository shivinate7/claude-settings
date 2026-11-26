#!/usr/bin/env python3
"""The progress beat of hooks/test_guard.py (decision stall-watch).

A full run of test_guard.py can print nothing for minutes, and the stall watch then reports a stall on a
healthy run. The runner owes a line at least every GUARD_HEARTBEAT seconds of quiet (default 60). The line
goes to stderr, flushed, and is appended to STALL_WATCH_BEAT when that is set. Each run class runs test_guard.py
on one family (GUARD_FAMILY=branch-worktree: 64 cases and one log check, 16-18 s per family run) and reads what it
printed. The watch classes run that family under hooks/stall_watch.py with a short limit. The defs classes run
the beat's own defs with a fake clock, so no suite runs. Two cases judge by a count, not by wall time, so machine
load cannot move them: DefaultIntervalOnFakeClock counts checkpoints on a fake clock, with the suite's own default
line, and WatcherOnFakeClock runs stall_watch.watch() in this process on a fake clock, where each sleep is one tick
and moves it 0.2 s. The run folder and its sweep are the shared helper's (lint/_test_temp.py); its sweep is proved in
lint/test_find_copies.py.

This file also holds the runner's own proofs of its crash scan and its registration hygiene (classes CrashScan and
RegistrationHygiene). Each runs the runner on a section set of its own, so no suite case is in them.

    python3 hooks/test_guard_beat.py
"""
import ast
import contextlib
import io
import math
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from collections import namedtuple
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lint"))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (the one home, lint/_test_temp.py)
sys.path.insert(0, HERE)
import stall_watch  # noqa: E402  the watcher, and its exit code on a stall (STALL_EXIT)
import guard_merge  # noqa: E402  merge_module: the merge tool's own FAIL-line parser, read by merge.failing_line
import mutate_shared  # noqa: E402  guard_tree: a copy of the guard with its siblings, for a planted crash

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
DEFAULT_RUN_SECONDS = 32  # a short quiet stretch: 64 cases, a checkpoint before and after each, 0.25 s of quiet apart
FAKE_JOB_TICKS = 150  # the fake job ends at this watcher sleep: 30 fake seconds at 0.2 s a sleep
FAKE_BEAT_TICKS = 35  # with beats on, the fake job writes one beat line every 35 sleeps: one each 7 fake seconds
FAKE_PID = 0  # the fake watch's job pid; the faked job state ignores it
MAX_TICKS = 1000  # a fake watch still running at this sleep has not returned: a failure, not a hang
MAX_READS = 20000  # a fake watch that reads the clock this often without a sleep spins: a failure, not a hang
BEAT = "test_guard: still running"  # the beat line's prefix; a case line starts with PASS, FAIL or SKIP
CASE_START = ("PASS", "FAIL", "SKIP")
SUMMARY = "test_guard PASS:"  # the last line of a family run that passed
# Set by a wrapper or an outer run. A child of this test must not read them. PYTHONUNBUFFERED would
# make stdout unbuffered whatever the runner flushes, so a missing flush could not show.
INHERITED = ("STALL_WATCH_BEAT", "GUARD_HEARTBEAT", "GUARD_FAMILY", "GUARD_SHARD", "GUARD_TESTS",
             "MUTATE_ONLY", "GUARD_TIMING", "PYTHONUNBUFFERED")

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
    """Kill a job this test started, and what it started, when the test ends while the job still runs."""
    try:
        os.killpg(job.pid, signal.SIGKILL)  # the job's own session (start_new_session)
    except (AttributeError, OSError):
        job.kill()


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


class FakeClock:
    """The watcher's clock. `monotonic` reads the fake time; `sleep` moves it by the sleep's length and counts a tick.
    The watcher's sleeps are the unit of time here, so a stall is a count of ticks. The guards turn a watch that
    never sleeps, or never returns, into an AssertionError, never a hang."""

    def __init__(self, on_tick):
        self.now = 0.0
        self.ticks = 0
        self.reads = 0
        self.on_tick = on_tick

    def monotonic(self):
        self.reads += 1
        if self.reads > MAX_READS:
            raise AssertionError("the watcher read the clock %d times without a sleep: a loop that never sleeps"
                                 % self.reads)
        return self.now

    def sleep(self, seconds):
        self.ticks += 1
        if self.ticks > MAX_TICKS:
            raise AssertionError("the watcher ran %d sleeps without returning: the fake job ended at sleep %d"
                                 % (self.ticks, FAKE_JOB_TICKS))
        self.now += seconds
        self.on_tick(self.ticks)


FakeWatch = namedtuple("FakeWatch", "rc out reports beats_written")


def watch_on_fake_clock(name, beats):
    """Run hooks/stall_watch.py's watch() in this process on a fake clock. The fake job ends at FAKE_JOB_TICKS. With
    beats on, it writes one beat line every FAKE_BEAT_TICKS sleeps, into the beat file the watch reads. A stall is
    recorded, not printed, so a stall ends the watch with a count and no ps call. The job state is faked too: no
    process starts, so nothing here depends on load."""
    beat_file = os.path.join(RUN_FOLDER, name + "-beat.txt")
    idle_file = os.path.join(RUN_FOLDER, name + "-idle.txt")  # the watch's log: idle, so only the beat file counts
    open(beat_file, "w").close()
    open(idle_file, "w").close()
    written = []

    def on_tick(tick):
        if beats and tick <= FAKE_JOB_TICKS and tick % FAKE_BEAT_TICKS == 0:
            with open(beat_file, "a", encoding="utf-8") as f:
                f.write("%s, fake job at sleep %d\n" % (BEAT, tick))
            written.append(tick)

    clock = FakeClock(on_tick)
    reports = []

    def job_state(pid):
        return stall_watch.JobState("S" if clock.ticks < FAKE_JOB_TICKS else "")

    def record(*args, **kwargs):
        reports.append(args)

    out = io.BytesIO()
    text = io.TextIOWrapper(out, encoding="utf-8", write_through=True)
    fake_time = types.SimpleNamespace(monotonic=clock.monotonic, sleep=clock.sleep)
    with mock.patch.object(stall_watch, "time", fake_time), \
            mock.patch.object(stall_watch, "job_state", job_state), \
            mock.patch.object(stall_watch, "report", record), \
            contextlib.redirect_stdout(text):
        rc = stall_watch.watch(FAKE_PID, idle_file, float(WATCH_QUIET), (), beat_file)
    return FakeWatch(rc, out.getvalue().decode("utf-8", "replace"), len(reports), len(written))


def checkpoints(defs, seconds, step):
    """One checkpoint every `step` seconds of fake quiet for `seconds`, the clock moving with them. The count of
    checkpoints is the work, so no wall second is read."""
    count = int(round(seconds / step))
    for i in range(1, count + 1):
        defs.now = i * step
        defs.call("beat", "case %d, before it runs" % i)
    return count


class Defs:
    """The named top-level defs of hooks/test_guard.py, run in one namespace with a fake clock (`now`) and a
    fake print (`printed`), so a beat is measured without running the suite. A def that is missing from the
    file fails here, so a moved beat cannot pass by vanishing."""

    def __init__(self, names, heartbeat=60.0, beat_file=""):
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
        module = ast.Module(body=[found[name] for name in names], type_ignores=[])
        ast.fix_missing_locations(module)
        exec(compile(module, SUITE, "exec"), self.ns)

    def call(self, name, *args):
        return self.ns[name](*args)

    def assign(self, name, environ):
        """Run the suite's own top-level line `name = ...` with os.environ replaced by environ, and keep the value in
        the namespace. The value is the one the suite computes, not a copy of it here."""
        with open(SUITE, encoding="utf-8") as f:
            tree = ast.parse(f.read(), SUITE)
        lines = [node for node in tree.body if isinstance(node, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == name for t in node.targets)]
        if len(lines) != 1:
            raise AssertionError("hooks/test_guard.py has %d top-level lines for %s, want 1: the setting moved, so "
                                 "this test must follow it" % (len(lines), name))
        self.ns["os"] = types.SimpleNamespace(environ=environ)
        module = ast.Module(body=lines, type_ignores=[])
        ast.fix_missing_locations(module)
        exec(compile(module, SUITE, "exec"), self.ns)
        return self.ns[name]


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


class DefaultIntervalOnFakeClock(unittest.TestCase):
    """Control: with GUARD_HEARTBEAT unset, a short quiet stretch prints no beat at the suite's default interval. No
    suite runs. The defs are the suite's parse_heartbeat and beat, and the interval is the suite's own default line,
    run with an empty environment, not a copy of it here. The stretch is counted on a fake clock: a checkpoint before
    and after each of the family's 64 cases, 0.25 s of fake quiet apart, DEFAULT_RUN_SECONDS in all."""

    def test_no_beat_in_a_short_quiet_stretch_at_the_default_interval(self):
        beat_file = os.path.join(RUN_FOLDER, "default-run-beat.txt")
        open(beat_file, "w").close()
        defs = Defs(["parse_heartbeat", "beat"], beat_file=beat_file)
        defs.assign("GUARD_HEARTBEAT", {})  # GUARD_HEARTBEAT unset
        checkpoints(defs, seconds=DEFAULT_RUN_SECONDS, step=0.25)
        self.assertEqual(len(defs.printed), 0, "%d beats printed in %d fake s of quiet under the default interval: %r"
                         % (len(defs.printed), DEFAULT_RUN_SECONDS, defs.printed[:1]))
        with open(beat_file, encoding="utf-8") as f:
            self.assertEqual(f.read(), "", "a beat was appended to the beat file in a short quiet stretch under the "
                             "default interval")
        # Control: the same instrument prints one beat once one gap runs past the same interval.
        control_file = os.path.join(RUN_FOLDER, "default-control-beat.txt")
        open(control_file, "w").close()
        control = Defs(["parse_heartbeat", "beat"], beat_file=control_file)
        interval = control.assign("GUARD_HEARTBEAT", {})
        checkpoints(control, seconds=DEFAULT_RUN_SECONDS, step=0.25)
        control.now = DEFAULT_RUN_SECONDS + interval + 1.0
        control.call("beat", "control, after one gap past the interval")
        quiet = DEFAULT_RUN_SECONDS + interval + 1.0
        self.assertEqual(len(control.printed), 1, "%.0f s of quiet past the default interval printed %d beats, want 1: "
                         "the beat cannot fire, so the quiet stretch proves nothing" % (quiet, len(control.printed)))


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

    def test_a_full_quiet_stretch_writes_one_line_per_interval(self):
        beat_file = os.path.join(RUN_FOLDER, "cost-full.txt")
        open(beat_file, "w").close()
        defs = Defs(["beat"], heartbeat=10.0, beat_file=beat_file)
        count = checkpoints(defs, seconds=100, step=0.5)  # 200 checkpoints in 100 s at I = 10 s
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


class WatcherOnFakeClock(unittest.TestCase):
    """The beat on, under stall_watch.watch() on a fake clock. No job starts: the fake job's state, its beats and its
    end are all faked, so the stall count depends on no load. The control is the same watch with no beats, which must
    stall at the same limit. The beats come every 7 fake seconds, under the 8 s limit, so a watch that stalls on a
    gap of 5 to 7 s goes red here."""

    def test_the_watcher_reports_no_stall(self):
        on = watch_on_fake_clock("fake-beat-on", beats=True)
        off = watch_on_fake_clock("fake-beat-off", beats=False)  # control: silence on the same watch must stall
        self.assertEqual(on.reports, 0, "the watcher reported a stall on a fake job that wrote a beat every %.0f fake "
                         "seconds under the %s s limit" % (FAKE_BEAT_TICKS * 0.2, WATCH_QUIET))
        self.assertEqual(on.rc, 0, "the watcher returned %r on a fake job that ended, not 0" % on.rc)
        self.assertEqual(len(beat_lines(on.out)), on.beats_written, "the watcher relayed %d beat lines of the %d the "
                         "fake job wrote" % (len(beat_lines(on.out)), on.beats_written))
        self.assertEqual(off.rc, stall_watch.STALL_EXIT, "the fake watch with no beat returned %r, not a stall: the "
                         "watch cannot fire, so the no-stall arm proves nothing" % off.rc)


class WatchedBeatOn(unittest.TestCase):
    """The beat on, under the watcher, with a real job. The job must pass first: a crash at import would also end with
    no stall. The relay case shows a real job's beat reaches the watcher. The no-stall case is WatcherOnFakeClock's,
    which starts no job."""

    @classmethod
    def setUpClass(cls):
        cls.watched = watched_run("watch-on", TINY)

    def test_the_job_exits_zero_with_its_summary(self):
        self.assertEqual(self.watched.job_rc, 0, "the watched run with the beat on exited %r, not 0"
                         % self.watched.job_rc)
        self.assertIn(SUMMARY, self.watched.job_out, "the watched run with the beat on printed no summary line")

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


# --- The runner's crash scan (decide, tests/guard/s27664-owner-judge.py) and registration hygiene (add, hooks/test_guard.py).
# Each proof runs the runner on this repository's section files plus one section of its own, with MUTATE_ONLY set to the
# proof's prefix, so only the proof's cases run. The controls pass on the old runner; the proofs fail there: the planted
# crash passes, a twin name runs, and a FAIL line has no section line.
CRASH_PROOF = "crash-scan proof:"
REG_PROOF = "registration proof:"
EXTRA_SECTION = "s99990-hygiene.py"   # the one section file this file adds: last in order, its cases on line 2
EXTRA_NUMBER = 99990
REAL_SECTIONS = os.path.join(HERE, "..", "tests", "guard")
JUDGE_CALL = "        judge(payload)\n"   # guard.py main(): the call a crash inside the guard raises from


def section_set(name, body):
    """This repository's section files, copied into a folder of the run folder named `name`, with one more: `body` as
    section 99990. The runner loads the whole set, so its ROOT and fixtures are the real ones. The copy follows
    build_with_extra in hooks/test_guard.py, which this file cannot import: that builder runs inside the runner."""
    folder = os.path.join(RUN_FOLDER, name)
    os.makedirs(folder, exist_ok=True)
    for entry in os.listdir(REAL_SECTIONS):
        if entry.endswith(".py"):
            shutil.copyfile(os.path.join(REAL_SECTIONS, entry), os.path.join(folder, entry))
    with open(os.path.join(folder, EXTRA_SECTION), "w", encoding="utf-8") as handle:
        handle.write("# section %d\n%s" % (EXTRA_NUMBER, body))
    return folder


def suite_run(folder, only, guard=None):
    """One run of the runner on the section set of `folder`, with MUTATE_ONLY=`only`, judged by `guard` when given, else
    by this repository's guard. stdout goes to a file: a `sleep` the suite leaves behind holds a pipe open, and the run
    would wait."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GUARD_", "MUTATE_ONLY"))}
    env.update(GUARD_SECTION_DIR=folder, MUTATE_ONLY=only)
    if guard:
        env["GUARD_UNDER_TEST"] = guard
    fd, out_path = tempfile.mkstemp(dir=RUN_FOLDER, suffix=".txt")
    with os.fdopen(fd, "w", encoding="utf-8") as out:
        done = subprocess.run(SUITE_CMD, stdout=out, stderr=subprocess.STDOUT, env=env, timeout=TIMEOUT)
    with open(out_path, encoding="utf-8", errors="replace") as handle:
        return Run(done.returncode, handle.read(), "")


def planted_guard(folder):
    """A copy of this repository's guard with its siblings, whose judge call raises: main() then fails open and logs a
    `crash` row, as a real crash inside the guard does. -> the copy's guard.py."""
    mutate_shared.guard_tree(folder)
    path = os.path.join(folder, "guard.py")
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    if text.count(JUDGE_CALL) != 1:
        raise RuntimeError("guard.py holds %d judge calls, want 1, so no crash can be planted" % text.count(JUDGE_CALL))
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text.replace(JUDGE_CALL, '        raise RuntimeError("planted crash")\n'))
    return path


FAIL_CLOSED_CALL = "        _question_form_module()\n"   # guard.py main(): the fail-closed writer, a refusal that logs a deny row
BROKEN_QUESTION_FORM = 'raise ImportError("this copy of the module was replaced by the case")\n'


def planted_fail_closed_guard(folder):
    """A copy of this repository's guard whose judge call is the fail-closed writer's own call, _question_form_module, with
    the copy's question_form.py unimportable. The copy refuses as guard-crash (decision install-hooks-whole) and logs its
    row as `deny`, not `crash`, which is the row decide must read too. -> the copy's guard.py."""
    mutate_shared.guard_tree(folder)
    path = os.path.join(folder, "guard.py")
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    if text.count(JUDGE_CALL) != 1:
        raise RuntimeError("guard.py holds %d judge calls, want 1, so no refusal can be planted" % text.count(JUDGE_CALL))
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text.replace(JUDGE_CALL, FAIL_CLOSED_CALL))
    with open(os.path.join(folder, "question_form.py"), "w", encoding="utf-8") as handle:
        handle.write(BROKEN_QUESTION_FORM)
    return path


def printed_lines(text, prefix, name):
    return [line for line in text.splitlines() if line.startswith(prefix) and name in line]


class CrashScan(unittest.TestCase):
    """L2: an allow case fails when its guard run logged a crash row (decide), and a row of either writer counts: the
    fail-open `crash` row and the fail-closed `deny` row under rule guard-crash. One run holds six cases: a planted crash
    and a planted refusal (the proofs), and four controls: an intact guard, a crash row written before the run, and two
    cases that declare their crash."""

    @classmethod
    def setUpClass(cls):
        planted = planted_guard(os.path.join(RUN_FOLDER, "planted-guard"))
        refusing = planted_fail_closed_guard(os.path.join(RUN_FOLDER, "refusing-guard"))
        old_row = os.path.join(RUN_FOLDER, "old-row-config")
        os.makedirs(old_row, exist_ok=True)
        with open(os.path.join(old_row, "guard.log"), "w", encoding="utf-8") as handle:
            handle.write("2026-11-25T10:00:00-06:00\t\tcrash\tguard-crash\tan earlier crash\t-\n")
        body = "\n".join([
            'add(%r, "allow", command="echo hi", guard=%r)' % (CRASH_PROOF + " planted", planted),
            'add(%r, "allow", command="echo hi")' % (CRASH_PROOF + " intact"),
            'add(%r, "allow", command="echo hi", config=%r)' % (CRASH_PROOF + " old row", old_row),
            'add(%r, "allow", command="echo hi", guard=%r, crash=True)' % (CRASH_PROOF + " declared", planted),
            'add(%r, "deny", rule="guard-crash", command="echo hi", guard=%r, carries=("guard-crash",))'
            % (CRASH_PROOF + " refused as guard-crash", refusing),
            'add(%r, "deny", rule="guard-crash", command="echo hi", guard=%r, carries=("guard-crash",), crash=True)'
            % (CRASH_PROOF + " crash declared", refusing),
        ]) + "\n"
        cls.proof = suite_run(section_set("crash-scan", body), CRASH_PROOF)

    def test_an_allow_under_a_crashing_guard_fails_its_case(self):
        self.assertTrue(printed_lines(self.proof.out, "FAIL", CRASH_PROOF + " planted"),
                        "the allow case under a crashing guard printed no FAIL line (rc %d)" % self.proof.rc)

    def test_the_failing_line_says_a_crash_row_was_logged(self):
        lines = printed_lines(self.proof.out, "FAIL", CRASH_PROOF + " planted")
        self.assertTrue(lines, "no FAIL line for the allow case under the crashing guard")
        self.assertIn("the guard logged a crash row", lines[0], "the FAIL line does not name the crash row: %s" % lines[0])

    def test_control_an_intact_guard_passes_its_allow_case(self):
        self.assertTrue(printed_lines(self.proof.out, "PASS", CRASH_PROOF + " intact"), "no PASS line for the intact allow case")

    def test_control_a_crash_row_from_before_the_run_does_not_fail_a_case(self):
        self.assertTrue(printed_lines(self.proof.out, "PASS", CRASH_PROOF + " old row"),
                        "a crash row written before the run failed a later case")

    def test_control_a_case_that_declares_its_crash_passes_beside_its_row(self):
        self.assertTrue(printed_lines(self.proof.out, "PASS", CRASH_PROOF + " declared"),
                        "the case that declares its crash failed beside its row")

    def test_a_refusal_by_the_fail_closed_writer_fails_its_case(self):
        lines = printed_lines(self.proof.out, "FAIL", CRASH_PROOF + " refused as guard-crash")
        self.assertTrue(lines, "the case the fail-closed guard refuses printed no FAIL line (rc %d): its deny row was not read"
                        % self.proof.rc)
        self.assertIn("the guard logged a crash row", lines[0], "the FAIL line does not name the crash row: %s" % lines[0])

    def test_control_a_refusal_that_declares_its_crash_passes_beside_its_row(self):
        self.assertTrue(printed_lines(self.proof.out, "PASS", CRASH_PROOF + " crash declared"),
                        "the refusal that declares its crash failed beside its row")


class RegistrationHygiene(unittest.TestCase):
    """L7: a second case under one name stops the run before any case, and a FAIL line names the case's section line and
    its input. Controls: distinct names run, and the merge tool's FAIL-line parser still reads the case name alone."""

    @classmethod
    def setUpClass(cls):
        twins = "\n".join(['add(%r, "allow", command="echo hi")' % (REG_PROOF + " twin"),
                           'add(%r, "allow", command="echo bye")' % (REG_PROOF + " twin")]) + "\n"
        cls.twins = suite_run(section_set("twin-names", twins), REG_PROOF)
        body = "\n".join(['add(%r, "allow", command="echo hi")' % (REG_PROOF + " one"),
                          'add(%r, "allow", command="echo bye")' % (REG_PROOF + " two"),
                          'add(%r, "deny", command="echo hi")' % (REG_PROOF + " wrong input")]) + "\n"
        cls.lines = suite_run(section_set("registration-lines", body), REG_PROOF)

    def test_a_name_registered_twice_stops_the_run_before_any_case(self):
        self.assertIn("is registered at", self.twins.out, "the run with a twin name printed no refusal (rc %d)" % self.twins.rc)
        self.assertNotEqual(self.twins.rc, 0, "the run with a twin name exited 0")

    def test_a_failing_line_names_its_section_line_and_input(self):
        lines = printed_lines(self.lines.out, "FAIL", REG_PROOF + " wrong input")
        self.assertTrue(lines, "no FAIL line for the case the guard allows")
        self.assertIn("at %s:4, input: echo hi" % EXTRA_SECTION, lines[0],
                      "the FAIL line names no section line or input: %s" % lines[0])

    def test_control_distinct_names_run_and_pass(self):
        self.assertTrue(printed_lines(self.lines.out, "PASS", REG_PROOF + " one"), "no PASS line for the first distinct name")
        self.assertTrue(printed_lines(self.lines.out, "PASS", REG_PROOF + " two"), "no PASS line for the second distinct name")

    def test_control_the_merge_tool_reads_the_case_name_of_a_fail_line(self):
        merge = guard_merge.merge_module()
        self.assertIsNotNone(merge, "the merge tool did not load, so its FAIL-line parser cannot be read")
        lines = printed_lines(self.lines.out, "FAIL", REG_PROOF + " wrong input")
        self.assertTrue(lines, "no FAIL line to parse")
        self.assertEqual(merge.failing_line(lines[0])[1], REG_PROOF + " wrong input",
                         "the merge tool reads a different case name from the FAIL line: %s" % lines[0])


if __name__ == "__main__":
    try:
        result = unittest.main(exit=False, verbosity=2).result
    finally:
        shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder
    sys.exit(0 if result.wasSuccessful() else 1)
