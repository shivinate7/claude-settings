#!/usr/bin/env python3
"""A fake clock for a fetch that takes time, shared by merge/test_merge.py and lint/test_report_guard_review.py.

The cutover read's budget is merge's shared_deadline, which reads the monotonic clock, and every git call goes through
merge's `_nowindow`. `FakeFetchClock.patched(merge)` swaps both for the block, so a case times its fetches without
sleeping or reading the real clock. A `git fetch` takes `step` seconds of fake time, cut at the timeout its caller
passed, as a real process is cut. Any other git call runs for real, with no timeout, and takes no fake time.

    python3 lint/test_fake_fetch.py
"""
import contextlib
import os
import subprocess
import sys
import time
import types
import unittest
import unittest.mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)


class FakeFetchClock:
    def __init__(self, step):
        self.step = step  # fake seconds that one fetch takes
        self.now = 0.0
        self.fetches = []  # [start, timeout] of each fetch in call order; the timeout is None when the caller gave none

    def monotonic(self):
        return self.now

    def run(self, args, timeout=None, **kwargs):
        if "fetch" not in args:
            return _nowindow.run(args, timeout=None, **kwargs)
        self.fetches.append([self.now, timeout])
        if timeout is not None and self.step > timeout:
            self.now += timeout
            raise subprocess.TimeoutExpired(args, timeout)
        self.now += self.step
        return subprocess.CompletedProcess(args, 0, "", "")

    @contextlib.contextmanager
    def patched(self, merge):
        """Patch `merge`'s clock and git seam for the block. Only merge's names change, so no other module's clock moves."""
        clock = types.SimpleNamespace(monotonic=self.monotonic, time=time.time, sleep=time.sleep)
        seam = types.SimpleNamespace(run=self.run)
        with unittest.mock.patch.object(merge, "time", clock), unittest.mock.patch.object(merge, "_nowindow", seam):
            yield self


class FakeFetchClockTests(unittest.TestCase):
    def test_a_fetch_that_fits_its_timeout_takes_its_step_of_fake_time(self):
        clock = FakeFetchClock(step=0.5)
        done = clock.run(["git", "fetch", "-q", "origin"], timeout=1.0)
        self.assertEqual(done.returncode, 0, "a fetch that fits its timeout did not return 0")
        self.assertEqual(clock.now, 0.5, "a fetch that fits its timeout took %r s of fake time, not its step" % (clock.now,))

    def test_a_fetch_longer_than_its_timeout_is_cut_at_the_timeout(self):
        clock = FakeFetchClock(step=2.0)
        with self.assertRaises(subprocess.TimeoutExpired):
            clock.run(["git", "fetch", "-q", "origin"], timeout=1.0)
        self.assertEqual(clock.now, 1.0, "a cut fetch took %r s of fake time, not its timeout" % (clock.now,))

    def test_a_git_read_takes_no_fake_time_and_no_timeout(self):
        clock = FakeFetchClock(step=5.0)
        done = clock.run(["git", "--version"], timeout=0.001)
        self.assertEqual(done.returncode, 0, "the git read did not run")
        self.assertEqual(clock.now, 0.0, "a git read took %r s of fake time" % (clock.now,))
        self.assertEqual(clock.fetches, [], "a git read was recorded as a fetch")


if __name__ == "__main__":
    unittest.main()
