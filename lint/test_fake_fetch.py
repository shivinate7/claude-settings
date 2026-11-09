#!/usr/bin/env python3
"""A fake clock for a fetch that takes time, shared by merge/test_merge.py and lint/test_report_guard_review.py.

The cutover read's budget is merge's shared_deadline, which reads the monotonic clock, and every git call goes through
merge's `_nowindow`. `FakeFetchClock.patched(merge)` swaps both for the block, so a case times its fetches without
sleeping or reading the real clock. A `git fetch` takes `step` seconds of fake time, cut at the timeout its caller
passed, as a real process is cut. Any other git call runs for real, with no timeout, and takes no fake time.

A gh call takes the fake seconds of the first `read_steps` key that one of its arguments holds, and none when no key
matches. It is cut at its timeout the same way, then the real stand-in answers it. `patched_process()` swaps the
process's own clock and child-start seam for the block, for a hook run in a process of its own.

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
    def __init__(self, step, read_steps=None):
        self.step = step  # fake seconds that one fetch takes
        self.read_steps = read_steps  # None, or {text: fake seconds} for gh calls: the first key an argument holds sets the seconds
        self.now = 0.0
        self.fetches = []  # [start, timeout] of each fetch in call order; the timeout is None when the caller gave none
        self.reads = []  # [start, timeout, argv] of each gh call in call order, when read_steps is given
        self.real_run = None  # set by patched_process: the child start the fake passes through, saved before its patch

    def monotonic(self):
        return self.now

    def run(self, args, timeout=None, **kwargs):
        if self.read_steps is not None and args[0] == "gh":
            return self.read(args, timeout, **kwargs)
        if "fetch" not in args:
            return self.passthrough(args, **kwargs)
        self.fetches.append([self.now, timeout])
        if timeout is not None and self.step > timeout:
            self.now += timeout
            raise subprocess.TimeoutExpired(args, timeout)
        self.now += self.step
        return subprocess.CompletedProcess(args, 0, "", "")

    def read(self, args, timeout, **kwargs):
        """A gh call: it takes its fake seconds, cut at its timeout as a real process is. The real stand-in then answers it."""
        self.reads.append([self.now, timeout, list(args)])
        step = next((seconds for key, seconds in self.read_steps.items() if any(key in arg for arg in args)), 0)
        if timeout is not None and step > timeout:
            self.now += timeout
            raise subprocess.TimeoutExpired(args, timeout)
        self.now += step
        return self.passthrough(args, **kwargs)

    def passthrough(self, args, **kwargs):
        """The real child start, with no timeout: the one patched_process saved, else the module's own."""
        run = self.real_run or _nowindow.run
        return run(args, timeout=None, **kwargs)

    @contextlib.contextmanager
    def patched(self, merge):
        """Patch `merge`'s clock and git seam for the block. Only merge's names change, so no other module's clock moves."""
        clock = types.SimpleNamespace(monotonic=self.monotonic, time=time.time, sleep=time.sleep)
        seam = types.SimpleNamespace(run=self.run)
        with unittest.mock.patch.object(merge, "time", clock), unittest.mock.patch.object(merge, "_nowindow", seam):
            yield self

    @contextlib.contextmanager
    def patched_process(self):
        """Patch this process's monotonic clock and child-start seam for the block. Only a hook run in a process of its own
        calls this, so every module of that process reads the fake clock and no other process does."""
        self.real_run = _nowindow.run
        with unittest.mock.patch.object(time, "monotonic", self.monotonic), unittest.mock.patch.object(_nowindow, "run", self.run):
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
