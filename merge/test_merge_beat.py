"""merge.py beats into STALL_WATCH_BEAT in every phase (decision stall-watch).

Red cases: batch 138 and batch 139 build attempt 4, a batch build quiet for 300 s in a phase that printed nothing, drew a STALL.
"""
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import merge  # noqa: E402

WATCH = os.path.join(ROOT, "hooks", "stall_watch.py")
PY = sys.executable


def silent_phase(secs, seen=None):
    """A stand-in for a batch build's silent phase inside main: no output, no CPU. build_parser is the first call main makes, on main
    and on this branch alike, so the same test runs red on main's code. SystemExit ends the run as a usage error does."""
    def run(*_a, **_k):
        if seen is not None:
            seen.append(threading.active_count())
        time.sleep(secs)
        raise SystemExit(0)
    return run


def run_main():
    try:
        merge.main([])
    except SystemExit:
        pass


class PhaseBeat(unittest.TestCase):
    def setUp(self):
        d = tempfile.mkdtemp()
        self.beat = os.path.join(d, "beat")
        open(self.beat, "w").close()

    def lines(self):
        with open(self.beat) as f:
            return f.read().splitlines()

    def test_silent_phase_appends_beats(self):
        env = {"STALL_WATCH_BEAT": self.beat, "MERGE_HEARTBEAT": "0.2"}
        with mock.patch.dict(os.environ, env), mock.patch.object(merge, "build_parser", silent_phase(1.1)):
            run_main()
        self.assertGreaterEqual(len(self.lines()), 3)
        self.assertTrue(all(l.startswith("merge: still working") for l in self.lines()))

    def test_no_beat_file_set_starts_no_thread(self):
        before = threading.active_count()
        env = {k: v for k, v in os.environ.items() if k != "STALL_WATCH_BEAT"}
        seen = []
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(merge, "build_parser", silent_phase(0, seen)):
            run_main()
        self.assertEqual(seen, [before])

    def test_cost_one_thread_and_one_append_per_beat(self):
        """Cost: one thread a run, joined at return; one append per beat, nothing else written."""
        env = {"STALL_WATCH_BEAT": self.beat, "MERGE_HEARTBEAT": "0.3"}
        before = threading.active_count()
        seen, opens, real = [], [], open

        def counting_open(path, *a, **k):
            if path == self.beat:
                opens.append(a[0] if a else "r")
            return real(path, *a, **k)
        with mock.patch.dict(os.environ, env), mock.patch("builtins.open", counting_open), mock.patch.object(
                merge, "build_parser", silent_phase(1.0, seen)):
            run_main()
        self.assertEqual(seen, [before + 1])
        self.assertEqual(threading.active_count(), before)
        n = len(self.lines())
        self.assertEqual(opens, ["a"] * n)
        time.sleep(0.8)
        self.assertEqual(len(self.lines()), n, "no beat after the run returns")

    def test_watcher_draws_no_stall_in_a_silent_phase(self):
        """A job silent for 6 s with a 2 s quiet window and no CPU: the watcher reads the beat and reports no STALL."""
        log = os.path.join(os.path.dirname(self.beat), "log")
        job = (f"import sys, time; sys.path.insert(0, {HERE!r}); import merge; "
               f"merge.build_parser = lambda *a, **k: (time.sleep(6), sys.exit(0)); merge.main([])")
        env = dict(os.environ, STALL_WATCH_BEAT=self.beat, MERGE_HEARTBEAT="1")
        with open(log, "w") as lf:
            proc = subprocess.Popen([PY, "-c", job], env=env, stdout=lf, stderr=subprocess.STDOUT)
            out = subprocess.run([PY, WATCH, "--watch-pid", str(proc.pid), "--log", log, "--quiet", "2", "--beat", self.beat],
                                 capture_output=True, text=True, timeout=60)
            proc.wait()
        self.assertNotIn("STALL", out.stdout)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    def test_same_silent_job_without_the_beat_is_a_stall(self):
        """Control: the same job with no beat is a stall, so the test above proves the beat."""
        log = os.path.join(os.path.dirname(self.beat), "log2")
        with open(log, "w") as lf:
            proc = subprocess.Popen([PY, "-c", "import time; time.sleep(6)"], stdout=lf, stderr=subprocess.STDOUT)
            out = subprocess.run([PY, WATCH, "--watch-pid", str(proc.pid), "--log", log, "--quiet", "2", "--beat", self.beat],
                                 capture_output=True, text=True, timeout=60)
            proc.wait()
        self.assertEqual(out.returncode, 3, out.stdout)
        self.assertIn("STALL", out.stdout)


if __name__ == "__main__":
    unittest.main()
