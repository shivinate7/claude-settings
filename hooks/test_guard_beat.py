#!/usr/bin/env python3
"""The guard test run prints a progress line while it is quiet (decision stall-watch; debt test-guard-no-progress-line).

A quiet tool owes a progress line at least every 120 seconds, or the stall watch cuts off a healthy run. This
case does not wait 120 seconds, and it does not run the full suite, which takes minutes. It runs one named case of
the stream family, the cheapest family that builds no fixtures.

Contract the builder codes against: GUARD_HEARTBEAT=<seconds> sets the beat interval of hooks/test_guard.py. A beat
is a stdout line that starts with "test_guard: still running". A beat never starts with PASS, FAIL or SKIP.

The default interval (120 seconds) is not measured here. The debt's retire test needs a background run over 300
seconds, which this case does not replace.

Run it from the repository root:

    python3 hooks/test_guard_beat.py
"""
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD_TEST = os.path.join(HERE, "test_guard.py")
sys.path.insert(0, os.path.join(HERE, "..", "lint"))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per test run (lint/_test_temp.py)

RUN_FOLDER = _test_temp.run_folder()  # the run's config folder comes from here, never from the system temp dir
ONE_CASE = "wait-pid: a kill -0 loop"  # a stream-family case: the run builds no fixtures and finishes in seconds
BEAT = "test_guard: still running"
RESULT_WORDS = ("PASS", "FAIL", "SKIP")
UNSET = ("GUARD_TESTS", "GUARD_SHARD", "GUARD_HEARTBEAT", "MUTATE_ONLY", "GUARD_FAMILY")


def run_one_case(heartbeat=None):
    """One named case of test_guard.py. Returns its stdout and stderr together."""
    env = dict(os.environ)
    for key in UNSET:
        env.pop(key, None)
    env.update(GUARD_FAMILY="stream", MUTATE_ONLY=ONE_CASE, CLAUDE_CONFIG_DIR=os.path.join(RUN_FOLDER, "cfg"))
    if heartbeat is not None:
        env["GUARD_HEARTBEAT"] = heartbeat
    run = subprocess.run([sys.executable, GUARD_TEST], capture_output=True, text=True, env=env, timeout=300)
    return run.returncode, run.stdout + run.stderr


def beat_lines(text):
    return [line for line in text.splitlines() if line.startswith(BEAT)]


class GuardRunBeats(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.quiet_rc, cls.quiet = run_one_case(heartbeat="0.05")  # a short interval: any run longer than it beats
        cls.default_rc, cls.default = run_one_case()  # the default interval: a run this short prints no beat

    def test_a_red_quiet_run_prints_a_progress_line(self):
        # Scope first: the named case ran and the run passed, so a beat count is read from a finished run.
        self.assertEqual(self.quiet_rc, 0, "scope: the one-case run did not pass: " + self.quiet[-300:])
        self.assertIn("test_guard PASS", self.quiet, "scope: the run did not reach its summary: " + self.quiet[-300:])
        beats = beat_lines(self.quiet)
        self.assertTrue(beats, "no progress line: GUARD_HEARTBEAT=0.05 printed no '%s' line. tail: %s"
                        % (BEAT, self.quiet[-300:]))
        for line in beats:
            self.assertFalse(line.startswith(RESULT_WORDS) or "FAIL" in line,
                             "a progress line reads as a case result: %r" % line)

    def test_c_green_default_interval_prints_no_progress_line_in_a_short_run(self):
        # Control: with the default interval a short run prints no beat, so the line is not printed on every case.
        self.assertEqual(self.default_rc, 0, "scope: the default run did not pass: " + self.default[-300:])
        self.assertEqual(beat_lines(self.default), [], "a beat printed in a short run with the default interval")


if __name__ == "__main__":
    unittest.main()
