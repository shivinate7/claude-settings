#!/usr/bin/env python3
"""Fixture test for bin/wait-until. Run: python3 lint/test_wait_until.py -v

`wait-until TIME [--timeout SECS]` waits until one clock time, then exits. TIME is an ISO-8601 instant with
a zone: `Z`, or a numeric offset. The helper only waits. It runs no command and signals no process.
Exit 0: the time has come, at once when it is already past. Exit 124: still short of the time at --timeout.
Exit 2: a bad argument, a bad time, or a time with no zone, returned at once with no wait.
While it waits, it prints "wait-until: still waiting until TIME, <s>s" every $WAIT_UNTIL_HEARTBEAT seconds
(default 120), so a quiet background run does not trip the stall watch.

Bounds. A case that waits is judged against the instant the test itself sets, not against a duration it
guesses: a helper that returns before that instant fails. Load cannot make a lower bound false, so only
lower bounds read the clock. The one upper bound on a wait is the subprocess timeout. A case that must not
wait allows AT_ONCE seconds.
"""
import math
import os
import shutil
import subprocess
import sys
import time
import unittest
from collections import namedtuple
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_temp  # noqa: E402  test-temp-standard: every temp path comes from this run's folder
RUN_FOLDER = _test_temp.run_folder()  # one run folder per test run, removed at teardown
HELPER = os.environ.get("WAIT_UNTIL_UNDER_TEST") or os.path.join(HERE, "..", "bin", "wait-until")
HEARTBEAT_LINE = "wait-until: still waiting"  # the heartbeat starts with this
EXIT_REACHED, EXIT_TIMEOUT, EXIT_BAD = 0, 124, 2
AT_ONCE = 5  # seconds: a case that must not wait returns well inside this
Result = namedtuple("Result", "rc out end_wall elapsed")


def run_helper(args, heartbeat=None, timeout=20):
    """Run bin/wait-until itself, so its executable bit and shebang count. stdout and stderr are one stream.
    rc is None when it did not return in `timeout` seconds."""
    if not os.path.isfile(HELPER):
        raise AssertionError("bin/wait-until does not exist, so no wait for a clock time is built")
    env = {k: v for k, v in os.environ.items() if k != "WAIT_UNTIL_HEARTBEAT"}
    if heartbeat:
        env["WAIT_UNTIL_HEARTBEAT"] = str(heartbeat)
    start = time.monotonic()
    try:
        done = subprocess.run([HELPER] + [str(a) for a in args], stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env,
                              timeout=timeout)
        rc, out = done.returncode, done.stdout
    except subprocess.TimeoutExpired as e:
        rc, out = None, (e.stdout.decode() if isinstance(e.stdout, bytes) else e.stdout) or ""
    return Result(rc, out, time.time(), time.monotonic() - start)


def iso_utc(epoch):
    """`epoch` as an ISO-8601 instant in UTC, to the second, with a Z."""
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def whole_second_ahead(seconds):
    """(epoch, ISO text) of the first whole second at or after `seconds` from now."""
    epoch = math.ceil(time.time() + seconds)
    return epoch, iso_utc(epoch)


def helper_timeout(path, argv):
    """The timeout the helper at `path` takes from `argv`. It imports the helper's own PROG and USAGE and calls
    its split_args, so the seam is the helper's real argument path and no wait happens."""
    import importlib.machinery
    import importlib.util
    name = "helper_" + os.path.basename(path).replace("-", "_")
    loader = importlib.machinery.SourceFileLoader(name, path)
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader))
    loader.exec_module(module)  # __name__ is not "__main__", so the helper's main does not run
    return module.wait_common.split_args(module.PROG, module.USAGE, argv)[1]


class T(unittest.TestCase):
    # The file itself.
    def test_helper_is_an_executable_python_script(self):
        self.assertTrue(os.path.isfile(HELPER), "bin/wait-until does not exist")
        self.assertTrue(os.access(HELPER, os.X_OK), "bin/wait-until is not executable")
        with open(HELPER, encoding="utf-8") as handle:
            first = handle.readline()
        self.assertTrue(first.startswith("#!") and "python" in first, first)

    # A time already past returns at once.
    def test_time_already_past_exits_0_at_once(self):
        r = run_helper([iso_utc(time.time() - 60)])
        self.assertEqual(r.rc, EXIT_REACHED, r.out)
        self.assertLess(r.elapsed, AT_ONCE, "did not return at once: " + r.out)

    def test_time_with_a_numeric_offset_is_read(self):
        """A zone given as an offset is a zone: a past time with +02:00 returns at once, exit 0."""
        local = timezone(timedelta(hours=2))
        text = datetime.fromtimestamp(time.time() - 60, local).strftime("%Y-%m-%dT%H:%M:%S+02:00")
        r = run_helper([text])
        self.assertEqual(r.rc, EXIT_REACHED, "the offset form was refused or waited: %r" % (r.out,))
        self.assertLess(r.elapsed, AT_ONCE, "did not return at once: " + r.out)

    # A time two seconds ahead holds until that time, then exits 0.
    def test_time_two_seconds_ahead_exits_0_no_earlier_than_that_time(self):
        epoch, text = whole_second_ahead(2.0)
        r = run_helper([text])
        self.assertEqual(r.rc, EXIT_REACHED, r.out)
        self.assertGreaterEqual(r.end_wall, epoch, "returned before %s: %s" % (text, r.out))

    # --timeout ends the wait with exit 124, and the time has not come.
    def test_timeout_one_second_with_time_one_hour_ahead_exits_124(self):
        r = run_helper([iso_utc(time.time() + 3600), "--timeout", "1"])
        self.assertEqual(r.rc, EXIT_TIMEOUT, r.out)
        self.assertGreaterEqual(r.elapsed, 0.9, "gave up before its --timeout: " + r.out)

    # Arguments: a time with no zone, a bad time and no time are refused at once, with no wait.
    def test_time_without_a_zone_exits_2_at_once(self):
        naive = datetime.fromtimestamp(time.time() + 3600, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        r = run_helper([naive])
        self.assertEqual(r.rc, EXIT_BAD, "a time with no zone was not refused: rc %r, %r" % (r.rc, r.out))
        self.assertLess(r.elapsed, AT_ONCE, "waited on a time with no zone: " + r.out)

    def test_bad_time_exits_2_at_once(self):
        for text in ("tomorrow", "2026-13-40T99:00:00Z", ""):
            with self.subTest(time=text):
                r = run_helper([text])
                self.assertEqual(r.rc, EXIT_BAD, "time %r: rc %r, %r" % (text, r.rc, r.out))
                self.assertLess(r.elapsed, AT_ONCE, "time %r: did not return at once" % (text,))

    def test_no_time_exits_2_at_once(self):
        r = run_helper([])
        self.assertEqual(r.rc, EXIT_BAD, r.out)
        self.assertLess(r.elapsed, AT_ONCE, "did not return at once: " + r.out)

    # Heartbeat: a long, quiet wait must not draw a false stall alarm, so check for at least one beat, never a count.
    def test_heartbeat_while_waiting(self):
        _epoch, text = whole_second_ahead(3.2)
        r = run_helper([text], heartbeat="1")
        self.assertEqual(r.rc, EXIT_REACHED, r.out)
        beats = [line for line in r.out.splitlines() if line.startswith(HEARTBEAT_LINE)]
        self.assertGreaterEqual(len(beats), 1, r.out)

    # With no --timeout, the target time bounds a wait-until, so its default is no cap (0). wait-pid keeps its
    # 540 s cap, since the pid it waits on may never exit.
    def test_wait_until_with_no_timeout_has_no_cap(self):
        self.assertEqual(helper_timeout(HELPER, []), 0,
                         "wait-until with no --timeout must have no cap, so the target time alone ends the wait")

    def test_wait_pid_with_no_timeout_keeps_its_540_second_cap(self):
        self.assertEqual(helper_timeout(os.path.join(HERE, "..", "bin", "wait-pid"), []), 540)

    def test_timeout_flag_sets_the_cap_it_is_given(self):
        self.assertEqual(helper_timeout(HELPER, ["--timeout", "7"]), 7)


def tearDownModule():
    """test-temp-standard: teardown removes this run's folder."""
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)


if __name__ == "__main__":
    if os.name == "nt":
        print("SKIP wait-until: the helper runs as a POSIX executable with a shebang")
        sys.exit(0)
    unittest.main()
