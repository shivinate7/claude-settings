#!/usr/bin/env python3
"""Suite for the phase-timing lines of merge.confirm (roadmap step merge-tool-phase-timing).

Run: python3 merge/test_merge_phase_timing.py
merge.timed_phase(name) prints `merge: phase <name>: start`, then `merge: phase <name>: done in <N> s` on a normal exit. When the
block raises, it prints `merge: phase <name>: stopped after <N> s` and re-raises. confirm wraps six phases in this order: lock,
main-run, debt-check, head-checks, prove, merge-call.
Cases 1 and 2 drive the helper with a fake clock (merge.time.time), so no case sleeps. Cases 3 and 4 run merge.main through the
scripted host of merge/test_merge.py: the Env fixture and its model guard come from there, a case extends it, and nothing is copied.
Importing test_merge runs none of its cases.
Cost per case: a successful run prints 12 phase lines, starts no thread, and leaves no file in its temp root or in its clone (case 4).
Temp files: each case's folder comes from tm.Env, which takes this run's folder (lint/_test_temp.py) and removes it at exit.
"""
import contextlib, io, os, re, sys, tempfile, threading, unittest, unittest.mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import merge  # noqa: E402
import test_merge as tm  # noqa: E402  the Env fixture, the scripted host and the fake clock (Clock); importing it runs none of its cases

PHASES = ("lock", "main-run", "debt-check", "head-checks", "prove", "merge-call")  # the six phases confirm wraps, in the order it runs them
PHASE_LINE = re.compile(r"merge: phase ([a-z-]+): (?:(start)|done in (\d+) s|stopped after (\d+) s)")


def setUpModule():
    tm.install_model_guard()  # the base of test_merge: a join here runs the prose judge, and no case starts `claude -p`


def phase(name):
    """merge.timed_phase(name), or a no-op context while merge.py has none. The red run then fails on the lines the block printed (none),
    and not on a missing name."""
    make = getattr(merge, "timed_phase", None)
    return make(name) if make is not None else contextlib.nullcontext()


def phase_forms(text):
    """-> (name, kind, seconds) for each `merge: phase` line of `text`, in order. kind is start, done or stopped; seconds is None for a start.
    A phase line in none of the three forms comes back as ("?", its text, None), so the comparison that reads it fails on that line."""
    forms = []
    for line in text.splitlines():
        if not line.startswith("merge: phase "):
            continue
        m = PHASE_LINE.fullmatch(line)
        if m is None:
            forms.append(("?", line, None))
            continue
        name, start, done, stopped = m.groups()
        if start:
            forms.append((name, "start", None))
        elif done is not None:
            forms.append((name, "done", int(done)))
        else:
            forms.append((name, "stopped", int(stopped)))
    return forms


def phase_pairs(text):
    """-> (name, kind) for each `merge: phase` line of `text`: the form without its seconds, for a run whose seconds are real."""
    return [(name, kind) for name, kind, _ in phase_forms(text)]


class TimedPhaseLines(unittest.TestCase):
    """timed_phase prints one start line, then one done or stopped line, with whole seconds of the fake clock. The clock is tm.Clock: the
    block moves it on, so no case sleeps and no assert reads the real clock."""

    def printed(self, advance, fail=None):
        """-> (the text the block prints, the exception the block raised or None). The block is one phase named lock. It moves the fake clock
        by `advance` s, then raises `fail` when one is given."""
        clock = tm.Clock(1000.0)
        out, err = io.StringIO(), None
        with unittest.mock.patch.object(merge.time, "time", clock.now), contextlib.redirect_stdout(out):
            try:
                with phase("lock"):
                    clock.t += advance
                    if fail is not None:
                        raise fail
            except Exception as e:  # the block's own error: the case reads it below, it is never a crash of this helper
                err = e
        return out.getvalue(), err

    def test_one_start_line_then_one_done_line_in_whole_seconds(self):
        # The empty state (0 s), a fraction that rounds up (4.6 s, so round and not int), and a long phase (7200.4 s).
        for advance, want in ((0, 0), (4.6, 5), (7200.4, 7200)):
            with self.subTest(advance=advance):
                text, err = self.printed(advance)
                self.assertIsNone(err, f"the block raised {err!r} with no fault set")
                self.assertEqual(phase_forms(text), [("lock", "start", None), ("lock", "done", want)],
                                 f"the block advanced the clock {advance} s; the printed phase lines are wrong")

    def test_a_block_that_raises_prints_stopped_and_reraises_the_same_exception(self):
        boom = merge.Stop("the head's own checks are not green")
        text, err = self.printed(3.2, fail=boom)
        self.assertIs(err, boom, f"the block's exception was not re-raised as it was raised: {err!r}")
        self.assertEqual(phase_forms(text), [("lock", "start", None), ("lock", "stopped", 3)],
                         "a block that raised after 3.2 s did not print start, then stopped after 3 s, and no done line")


class TimedPhaseStartsNoThread(unittest.TestCase):
    """The decision's cost sentence: timed_phase starts no thread. The count is of Thread.start calls made while a phase runs, so a thread
    that starts and is joined inside the helper is seen."""

    def test_a_phase_makes_no_thread_start_call(self):
        starts = []
        real_start = threading.Thread.start

        def counting_start(thread):
            starts.append(thread.name)
            return real_start(thread)
        with unittest.mock.patch.object(threading.Thread, "start", counting_start), contextlib.redirect_stdout(io.StringIO()):
            with phase("lock"):
                pass
            try:
                with phase("prove"):
                    raise merge.Stop("a refusal")
            except merge.Stop:
                pass
        self.assertEqual(starts, [], "timed_phase started a thread")


class BrokenStdout:
    """A stdout whose pipe reader is gone (`merge N --confirm | head -1`): every write fails as the OS fails it."""
    encoding = "utf-8"

    def write(self, _text):
        raise BrokenPipeError(32, "Broken pipe")

    def flush(self):
        raise BrokenPipeError(32, "Broken pipe")


class TimingLineNeverStopsTheRun(unittest.TestCase):
    """A timing line that cannot be written must not change what the phase does: a failed print after the lock is taken would leave the
    lock held, because confirm releases it in a try that starts after the lock phase."""

    def run_block(self, fail=None):
        """-> (whether the block ran to its end, the exception that left the phase or None), with stdout broken for the whole phase."""
        ran, err = [], None
        with unittest.mock.patch.object(sys, "stdout", BrokenStdout()):
            try:
                with phase("lock"):
                    ran.append("start")
                    if fail is not None:
                        raise fail
                    ran.append("end")
            except BaseException as e:  # the case reads it below
                err = e
        return ran, err

    def test_a_block_runs_to_its_end_when_the_start_and_done_lines_cannot_be_written(self):
        ran, err = self.run_block()
        self.assertEqual(ran, ["start", "end"], "the block did not run to its end with stdout broken")
        self.assertIsNone(err, f"a broken stdout stopped the phase with {err!r}")

    def test_the_blocks_own_exception_leaves_the_phase_as_it_was_raised_when_the_stopped_line_cannot_be_written(self):
        boom = merge.Stop("the head's own checks are not green")
        ran, err = self.run_block(fail=boom)
        self.assertEqual(ran, ["start"])
        self.assertIs(err, boom, f"a broken stdout replaced the block's exception with {err!r}")


class ConfirmPhases(tm.Env):
    """A scripted confirm run through merge.main, on the fixture's FakeHost. leave_no_pending_record leaves the lane nothing to claim, so the
    one run reaches merge-call. A run with a claim to push stops after prove and merges on a second run: that run is not a one-run case."""

    def test_a_successful_run_prints_each_phase_start_then_done_in_order(self):
        self.leave_no_pending_record()
        rc, out = self.run_merge_once("7", "--confirm")
        self.assertEqual(rc, 0, out)  # scope first: the run merged, so every phase ran
        self.assertTrue(getattr(self.host, "merged", False), out)
        self.assertEqual(phase_pairs(out), [(p, k) for p in PHASES for k in ("start", "done")],
                         "the phase lines of a successful run are not each phase's start then done, in confirm's order, and no others")

    def test_a_head_that_is_not_green_stops_inside_head_checks_and_goes_no_further(self):
        self.host.state = "red: checks: fail"  # refused before the claim: the lane's pending record is still there, and nothing is pushed
        rc, out = self.run_merge_once("7", "--confirm")
        self.assertNotEqual(rc, 0, out)  # scope first: the head was refused
        self.assertIn("a check is red: checks: fail", out)
        self.assertFalse(getattr(self.host, "merged", False), out)
        self.assertEqual(phase_pairs(out), [("lock", "start"), ("lock", "done"), ("main-run", "start"), ("main-run", "done"),
                                            ("debt-check", "start"), ("debt-check", "done"), ("head-checks", "start"), ("head-checks", "stopped")],
                         "a refused head's phase lines do not end at head-checks stopped, with no prove or merge-call line")

    def test_a_successful_run_costs_twelve_lines_no_thread_and_no_file(self):
        self.leave_no_pending_record()
        tmp_root = os.path.join(self.t, "run-tmp")  # the run's own temp root: the worktree tree is made under it, and removed by the run
        os.makedirs(tmp_root)
        threads_before = set(threading.enumerate())  # a set, not a count: a daemon thread of an earlier case may end during the run
        with unittest.mock.patch.object(tempfile, "tempdir", tmp_root):
            rc, out = self.run_merge_once("7", "--confirm")
        self.assertEqual(rc, 0, out)  # scope first: the run merged
        new_threads = [t.name for t in threading.enumerate() if t not in threads_before]
        self.assertEqual(new_threads, [], "the run left a thread alive that was not alive before it")
        self.assertEqual(os.listdir(tmp_root), [], "the run left a file in its temp root")
        self.assertEqual(tm.sh(self.co, "git", "status", "--porcelain", "--untracked-files=all"), "", "the run left a file in its clone")
        self.assertEqual(len([line for line in out.splitlines() if line.startswith("merge: phase ")]), 12,
                         "a successful run must print 12 phase lines: 6 phases, a start and a done each")


if __name__ == "__main__":
    unittest.main()
