#!/usr/bin/env python3
"""The progress beat of hooks/test_guard.py (decision stall-watch).

A full run of test_guard.py can print nothing for minutes, and the stall watch then reports a stall on a
healthy run. The runner owes a line at least every GUARD_HEARTBEAT seconds of quiet (default 60). The line
goes to stderr, flushed, and is appended to STALL_WATCH_BEAT when that is set. Each run class runs test_guard.py
on one family (GUARD_FAMILY=branch-worktree: 64 cases and one log check, 16-18 s per family run) and reads what it
printed. The watch classes run that family under hooks/stall_watch.py with a short limit. The defs classes run
the beat's own defs with a fake clock, so no suite runs. The run folder and its sweep are the shared helper's
(lint/_test_temp.py); its sweep is proved in lint/test_find_copies.py.

    python3 hooks/test_guard_beat.py
"""
import ast
import math
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import types
import unittest
from collections import namedtuple
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lint"))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (the one home, lint/_test_temp.py)
sys.path.insert(0, HERE)
import stall_watch  # noqa: E402  the watcher, and its exit code on a stall (STALL_EXIT)
import stall_beat  # noqa: E402  the one home of the beat's append (hooks/stall_beat.py)

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
    try:
        watcher = subprocess.run([sys.executable, WATCHER, "--watch-pid", str(job.pid), "--log", idle_file,
                                  "--quiet", WATCH_QUIET, "--beat", beat_file],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=TIMEOUT)
        job_rc = job.wait(timeout=TIMEOUT)
    finally:
        if job.poll() is None:
            kill_job(job)
    with open(job_file, "rb") as f:
        job_out = f.read().decode("utf-8", "replace")
    return Watched(watcher.returncode, watcher.stdout.decode("utf-8", "replace"), job_rc, job_out)


class Defs:
    """The named top-level defs of hooks/test_guard.py, run in one namespace with a fake clock (`now`) and a
    fake print (`printed`), so a beat is measured without running the suite. A def that is missing from the
    file fails here, so a moved beat cannot pass by vanishing."""

    def __init__(self, names, heartbeat=60.0):
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
            "stall_beat": stall_beat,  # reads STALL_WATCH_BEAT at each call, so a caller sets it
            "QUIET_SINCE": [0.0],
        }
        module = ast.Module(body=[found[name] for name in names], type_ignores=[])
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
        with mock.patch.dict(os.environ, {"STALL_WATCH_BEAT": beat_file}):
            defs = Defs(["beat"], heartbeat=10.0)
            count = self.checkpoints(defs, seconds=100, step=0.5)  # 200 checkpoints in 100 s at I = 10 s
        with open(beat_file, encoding="utf-8") as f:
            lines = f.read().splitlines()
        self.assertEqual(len(lines), 100 // 10, "%d s of quiet at I = 10 s over %d checkpoints wrote %d beat "
                                                "lines, want 10: one per interval" % (100, count, len(lines)))
        self.assertEqual(len(defs.printed), len(lines), "a beat was appended to the file but not printed")

    def test_a_stretch_with_no_quiet_time_writes_nothing(self):
        beat_file = os.path.join(RUN_FOLDER, "cost-empty.txt")
        open(beat_file, "w").close()
        with mock.patch.dict(os.environ, {"STALL_WATCH_BEAT": beat_file}):
            defs = Defs(["beat"], heartbeat=10.0)
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


if __name__ == "__main__":
    try:
        result = unittest.main(exit=False, verbosity=2).result
    finally:
        shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder
    sys.exit(0 if result.wasSuccessful() else 1)
