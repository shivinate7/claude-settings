#!/usr/bin/env python3
"""Fixture test for bin/verdict. Run: python lint/test_verdict.py -v"""
import os, re, shlex, subprocess, sys, tempfile, time, unittest
V = os.environ.get("VERDICT_UNDER_TEST") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin", "verdict")
HB_FORMAT = re.compile(r"^verdict: still running, [0-9][0-9.]*s?, log=")

def run(code, log=None, extra=None, timeout=None):
    env = dict(os.environ)
    env.pop("VERDICT_LOG", None)
    env.pop("VERDICT_HEARTBEAT", None)
    if log: env["VERDICT_LOG"] = log
    env.update(extra or {})
    with tempfile.TemporaryDirectory() as d:
        script = os.path.join(d, "fx.py")
        open(script, "w").write(code)
        return subprocess.run([sys.executable, V, sys.executable, script], capture_output=True, text=True, env=env, timeout=timeout)

def heartbeats(out):
    return [l for l in out.splitlines() if l.startswith("verdict: still running")]

def alive(pid):
    try: os.kill(pid, 0)
    except ProcessLookupError: return False
    except PermissionError: return True
    return True

class T(unittest.TestCase):
    def test_pass(self):
        r = run("print('noisy')")
        self.assertEqual(r.returncode, 0)
        self.assertTrue(r.stdout.startswith("PASS "))
        self.assertNotIn("noisy", r.stdout)

    def test_fail_line_excerpt_and_exit_code(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "v.log")
            r = run("import sys\nprint('one')\nprint('FAIL boom')\nprint('err', file=sys.stderr)\nsys.exit(7)", log)
            self.assertEqual(r.returncode, 7)
            first = r.stdout.splitlines()[0]
            self.assertTrue(first.startswith("FAIL ") and " rc=7 " in first and f"log={log}" in first, first)
            self.assertIn("FAIL boom", r.stdout.splitlines()[1:])
            self.assertNotIn("one", r.stdout.splitlines()[1:])
            full = open(log).read()
            self.assertIn("one", full)
            self.assertIn("err", full)

    def test_tail_when_no_hot_line_and_cap(self):
        r = run("print('\\n'.join(f'l{i}' for i in range(100)))\nraise SystemExit(1)")
        body = r.stdout.splitlines()[1:]
        self.assertEqual(len(body), 30)
        self.assertEqual(body[-1], "l99")

    def test_reused_log_is_not_truncated(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "v.log")
            run("print('first-run')", log)
            run("print('second-run')", log)
            full = open(log).read()
            self.assertIn("first-run", full)
            self.assertIn("second-run", full)

    @unittest.skipIf(os.name == "nt", "POSIX signals")
    def test_signal_kill(self):
        r = run("import os, signal\nos.kill(os.getpid(), signal.SIGTERM)")
        self.assertEqual(r.returncode, 128 + 15)
        self.assertIn("killed by signal 15", r.stdout)

    def test_heartbeat_while_slow(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "v.log")
            r = run("import time\ntime.sleep(3.5)\nprint('done')", log, {"VERDICT_HEARTBEAT": "1"})
            self.assertEqual(r.returncode, 0)
            beats = heartbeats(r.stdout)
            self.assertEqual(len(beats), 3, r.stdout)
            for b in beats:
                self.assertRegex(b, HB_FORMAT)
                self.assertTrue(b.endswith(f"log={log}"), b)
            self.assertTrue(r.stdout.splitlines()[-1].startswith("PASS "), r.stdout)

    def test_fast_command_prints_no_heartbeat(self):
        r = run("print('quick')", None, {"VERDICT_HEARTBEAT": "1"})
        self.assertEqual(r.returncode, 0)
        self.assertEqual(heartbeats(r.stdout), [], r.stdout)
        self.assertTrue(r.stdout.startswith("PASS "), r.stdout)

    def test_slow_fail_heartbeats_then_same_excerpt(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "v.log")
            r = run("import sys, time\nprint('one')\ntime.sleep(2.5)\nprint('FAIL boom')\nprint('err', file=sys.stderr)\nsys.exit(7)", log, {"VERDICT_HEARTBEAT": "1"})
            self.assertEqual(r.returncode, 7)
            beats = heartbeats(r.stdout)
            self.assertEqual(len(beats), 2, r.stdout)
            lines = r.stdout.splitlines()
            self.assertEqual(lines[:2], beats, r.stdout)
            first = lines[2]
            self.assertTrue(first.startswith("FAIL ") and " rc=7 " in first and f"log={log}" in first, first)
            body = lines[3:]
            self.assertIn("FAIL boom", body)
            self.assertNotIn("one", body)
            self.assertFalse(any("still running" in l for l in body), body)

    def test_heartbeat_never_carries_command_output(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "v.log")
            r = run("import time\nprint('SECRET-OUT-7731', flush=True)\ntime.sleep(2.5)\nprint('SECRET-OUT-7731 again')", log, {"VERDICT_HEARTBEAT": "1"})
            self.assertEqual(r.returncode, 0)
            beats = heartbeats(r.stdout)
            self.assertEqual(len(beats), 2, r.stdout)
            for b in beats:
                self.assertRegex(b, HB_FORMAT)
                self.assertNotIn("SECRET-OUT-7731", b)
            self.assertNotIn("SECRET-OUT-7731", r.stdout)

    def test_bad_heartbeat_value_still_runs_the_command(self):
        code = "import sys, time\nprint('MARK-RAN', flush=True)\ntime.sleep(2)\nsys.exit(7)"
        for val in ["abc", "0", "-1", "1e-9", "0.001", "inf", "nan"]:
            with self.subTest(VERDICT_HEARTBEAT=val), tempfile.TemporaryDirectory() as d:
                log = os.path.join(d, "v.log")
                r = run(code, log, {"VERDICT_HEARTBEAT": val}, timeout=30)
                self.assertEqual(r.returncode, 7, (r.stdout[:300], r.stderr[-300:]))
                self.assertIn("MARK-RAN", open(log).read())
                self.assertNotIn("Traceback", r.stdout + r.stderr)
                self.assertLess(len(heartbeats(r.stdout)), 5, len(heartbeats(r.stdout)))

    @unittest.skipIf(os.name == "nt", "POSIX shell pipe and signals")
    def test_broken_pipe_does_not_orphan_child(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "v.log")
            pidfile = os.path.join(d, "child.pid")
            script = os.path.join(d, "fx.py")
            open(script, "w").write(f"import os, time\nopen({pidfile!r}, 'w').write(str(os.getpid()))\ntime.sleep(3)\n")
            env = dict(os.environ)
            env.pop("VERDICT_HEARTBEAT", None)
            env.update({"VERDICT_HEARTBEAT": "1", "VERDICT_LOG": log})
            cmd = " ".join(shlex.quote(p) for p in [sys.executable, V, sys.executable, script]) + " | head -n 1"
            t0 = time.time()
            r = subprocess.run(cmd, shell=True, executable="/bin/bash", capture_output=True, text=True, env=env, timeout=30)
            elapsed = time.time() - t0
            self.assertTrue(os.path.exists(pidfile), "child never started")
            pid = int(open(pidfile).read())
            self.assertFalse(alive(pid), f"child {pid} still running after verdict returned")
            self.assertLess(elapsed, 6, elapsed)
            self.assertNotIn("cannot run", open(log).read())
            self.assertNotIn("cannot run", r.stdout + r.stderr)

    def test_test_failed_marker_on_exit0_is_fail(self):
        r = run("print('Test Suite All tests')\nprint('** TEST FAILED **')")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertTrue(r.stdout.startswith("FAIL "), r.stdout)
        self.assertIn("** TEST FAILED **", r.stdout)

    def test_build_failed_marker_on_exit0_is_fail(self):
        r = run("print('Build target app')\nprint('** BUILD FAILED **')")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertTrue(r.stdout.startswith("FAIL "), r.stdout)
        self.assertIn("** BUILD FAILED **", r.stdout)

    def test_zero_tests_on_exit0_is_fail_no_tests_ran(self):
        r = run("print('Test Suite All tests')\nprint('Executed 0 tests, with 0 failures (0 unexpected) in 0.000 (0.001) seconds')\nprint('** TEST SUCCEEDED **')")
        self.assertEqual(r.returncode, 1, r.stdout)
        first = r.stdout.splitlines()[0]
        self.assertTrue(first.startswith("FAIL ") and "no tests ran" in first, first)

    def test_passing_runs_raise_no_false_alarm(self):
        cases = {
            "xcodebuild success": "print('Executed 12 tests, with 0 failures (0 unexpected) in 1.2 (1.3) seconds')\nprint('** TEST SUCCEEDED **')",
            "ordinary FAIL Error assert text": "print('checking FAIL paths')\nprint('Error handler: none raised')\nprint('assert 3 == 3 passed')",
            "TEST FAILED without ** markers": "print('test_retry TEST FAILED handled, passed')",
        }
        for name, code in cases.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as d:
                r = run(code, os.path.join(d, "v.log"))
                self.assertEqual(r.returncode, 0, r.stdout)
                self.assertTrue(r.stdout.startswith("PASS "), r.stdout)

    def test_test_failed_marker_keeps_command_exit_code(self):
        r = run("print('** TEST FAILED **')\nraise SystemExit(65)")
        self.assertEqual(r.returncode, 65, r.stdout)
        first = r.stdout.splitlines()[0]
        self.assertTrue(first.startswith("FAIL ") and " rc=65 " in first, first)

    def test_marker_early_in_2mib_output_is_fail(self):
        code = ("import sys\n"
                "sys.stdout.write('** TEST FAILED **\\n')\n"
                "line = 'x' * 1023 + '\\n'\n"
                "for _ in range(2048):\n"
                "    sys.stdout.write(line)\n")
        r = run(code)
        self.assertEqual(r.returncode, 1, r.stdout[:300])
        self.assertTrue(r.stdout.startswith("FAIL "), r.stdout[:300])
        self.assertIn("runner failure marker", r.stdout.splitlines()[0])

    def test_marker_straddling_tail_boundary_is_fail(self):
        # Marker occupies bytes [1000, 1018) of the run. The last 1 MiB starts at byte 1009,
        # inside the marker, so a tail-only read sees "AILED **" and no marker.
        code = ("import sys\n"
                "sys.stdout.write('a' * 1000)\n"
                "sys.stdout.write('** TEST FAILED **\\n')\n"
                "sys.stdout.write('x' * (1048576 - 9))\n")
        r = run(code)
        self.assertEqual(r.returncode, 1, r.stdout[:300])
        self.assertTrue(r.stdout.startswith("FAIL "), r.stdout[:300])
        self.assertIn("runner failure marker", r.stdout.splitlines()[0])

    def test_zero_then_nonzero_tests_is_pass(self):
        code = ("print('Test Suite Bundle A')\n"
                "print('Executed 0 tests, with 0 failures (0 unexpected) in 0.000 (0.001) seconds')\n"
                "print('Test Suite Bundle B')\n"
                "print('Executed 12 tests, with 0 failures (0 unexpected) in 1.2 (1.3) seconds')\n"
                "print('** TEST SUCCEEDED **')")
        r = run(code)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertTrue(r.stdout.startswith("PASS "), r.stdout)

    def test_singular_one_test_is_pass(self):
        r = run("print('Executed 1 test, with 0 failures (0 unexpected) in 0.1 (0.2) seconds')")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertTrue(r.stdout.startswith("PASS "), r.stdout)

    def test_child_deleting_log_is_fail_log_unreadable(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "v.log")
            r = run("import os\nos.remove(os.environ['VERDICT_LOG'])", log)
            self.assertNotEqual(r.returncode, 0, r.stdout)
            first = r.stdout.splitlines()[0] if r.stdout else ""
            self.assertTrue(first.startswith("FAIL "), (r.stdout[:300], r.stderr[-300:]))
            self.assertIn("log unreadable", first)
            self.assertNotIn("Traceback", r.stdout + r.stderr)

if __name__ == "__main__":
    unittest.main()
