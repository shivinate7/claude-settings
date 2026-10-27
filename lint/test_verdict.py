#!/usr/bin/env python3
"""Fixture test for bin/verdict. Run: python lint/test_verdict.py -v"""
import os, re, shlex, subprocess, sys, tempfile, time, unittest
V = os.environ.get("VERDICT_UNDER_TEST") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin", "verdict")
# The Windows launcher. It always runs its sibling bin/verdict, so VERDICT_UNDER_TEST does not reach it.
CMD = [os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin", "verdict.cmd")]
UTF8 = {"PYTHONIOENCODING": "utf-8"}  # the child prints the real \u2714/\u2718 marks; a cp1252 stdout cannot
HB_FORMAT = re.compile(r"^verdict: still running, [0-9][0-9.]*s?, log=")

def run(code, log=None, extra=None, timeout=None, launcher=None):
    env = dict(os.environ)
    env.pop("VERDICT_LOG", None)
    env.pop("VERDICT_HEARTBEAT", None)
    if log: env["VERDICT_LOG"] = log
    env.update(extra or {})
    with tempfile.TemporaryDirectory() as d:
        script = os.path.join(d, "fx.py")
        open(script, "w").write(code)
        return subprocess.run((launcher or [sys.executable, V]) + [sys.executable, script], capture_output=True, text=True, env=env, timeout=timeout)

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
        """A long, quiet run must not draw a false stall alarm (Tools that are quiet by design), so check for at least one beat, never an exact count (decision stall-watch)."""
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "v.log")
            r = run("import time\ntime.sleep(3.5)\nprint('done')", log, {"VERDICT_HEARTBEAT": "1"})
            self.assertEqual(r.returncode, 0)
            beats = heartbeats(r.stdout)
            self.assertGreaterEqual(len(beats), 1, r.stdout)
            for b in beats:
                self.assertRegex(b, HB_FORMAT)
                self.assertTrue(b.endswith(f"log={log}"), b)
            self.assertTrue(r.stdout.splitlines()[-1].startswith("PASS "), r.stdout)

    def test_fast_command_prints_no_heartbeat(self):
        """A child shorter than the beat interval gets no beat; 30 s is wide enough that Python start cost cannot reach it."""
        r = run("print('quick')", None, {"VERDICT_HEARTBEAT": "30"})
        self.assertEqual(r.returncode, 0)
        self.assertEqual(heartbeats(r.stdout), [], r.stdout)
        self.assertTrue(r.stdout.startswith("PASS "), r.stdout)

    def test_no_heartbeat_after_the_child_exits(self):
        """A beat after exit is a false alarm: the beat count cannot exceed the whole seconds the verdict line reports."""
        r = run("import time\ntime.sleep(1.2)", None, {"VERDICT_HEARTBEAT": "1"})
        lines = r.stdout.splitlines()
        m = re.match(r"PASS .* \(([0-9.]+)s\)$", lines[-1])
        self.assertTrue(m, r.stdout)
        self.assertGreaterEqual(len(heartbeats(r.stdout)), 1, r.stdout)
        self.assertLessEqual(len(heartbeats(r.stdout)), int(float(m.group(1))), r.stdout)
        self.assertEqual(heartbeats(lines[-1]), [], r.stdout)

    def test_slow_fail_heartbeats_then_same_excerpt(self):
        """A long, quiet run must not draw a false stall alarm (Tools that are quiet by design), so check for at least one beat, never an exact count (decision stall-watch)."""
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "v.log")
            r = run("import sys, time\nprint('one')\ntime.sleep(2.5)\nprint('FAIL boom')\nprint('err', file=sys.stderr)\nsys.exit(7)", log, {"VERDICT_HEARTBEAT": "1"})
            self.assertEqual(r.returncode, 7)
            beats = heartbeats(r.stdout)
            self.assertGreaterEqual(len(beats), 1, r.stdout)
            lines = r.stdout.splitlines()
            self.assertEqual(lines[:len(beats)], beats, r.stdout)
            first = lines[len(beats)]
            self.assertTrue(first.startswith("FAIL ") and " rc=7 " in first and f"log={log}" in first, first)
            body = lines[len(beats) + 1:]
            self.assertIn("FAIL boom", body)
            self.assertNotIn("one", body)
            self.assertFalse(any("still running" in l for l in body), body)

    def test_heartbeat_never_carries_command_output(self):
        """A long, quiet run must not draw a false stall alarm (Tools that are quiet by design), so check for at least one beat, never an exact count (decision stall-watch)."""
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "v.log")
            r = run("import time\nprint('SECRET-OUT-7731', flush=True)\ntime.sleep(2.5)\nprint('SECRET-OUT-7731 again')", log, {"VERDICT_HEARTBEAT": "1"})
            self.assertEqual(r.returncode, 0)
            beats = heartbeats(r.stdout)
            self.assertGreaterEqual(len(beats), 1, r.stdout)
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

    # Lines captured from a real `swift test` (Swift 6.4): the XCTest summary is always there and says 0 for a Swift Testing run.
    XCT0 = "Executed 0 tests, with 0 failures (0 unexpected) in 0.000 (0.002) seconds"
    ST_PASS = "\u2714 Test run with 1 test in 0 suites passed after 0.001 seconds."
    ST_FAIL = "\u2718 Test run with 2 tests in 0 suites failed after 0.001 seconds with 1 issue."

    def test_swift_testing_pass_on_exit0_is_pass(self):
        r = run(f"print({self.XCT0!r})\nprint({ascii(self.ST_PASS)})", extra=UTF8)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertTrue(r.stdout.startswith("PASS "), r.stdout)

    def test_swift_testing_failure_on_exit0_is_fail_even_with_xctest_tests(self):
        r = run(f"print('Executed 3 tests, with 0 failures (0 unexpected) in 0.1 (0.2) seconds')\nprint({ascii(self.ST_FAIL)})", extra=UTF8)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("runner failure marker", r.stdout.splitlines()[0])

    def test_swift_testing_line_without_suite_count_is_still_read(self):
        r = run(f"print({self.XCT0!r})\nprint('Test run with 1 test passed after 0.001 seconds.')", extra=UTF8)
        self.assertEqual(r.returncode, 0, r.stdout)
        r = run("print('Executed 3 tests, with 0 failures (0 unexpected) in 0.1 (0.2) seconds')\nprint('Test run with 2 tests failed after 0.001 seconds with 1 issue.')", extra=UTF8)
        self.assertEqual(r.returncode, 1, r.stdout)

    def test_swift_testing_zero_tests_on_exit0_is_fail_no_tests_ran(self):
        r = run(f"print({self.XCT0!r})\nprint('\\u2714 Test run with 0 tests in 0 suites passed after 0.001 seconds.')", extra=UTF8)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("no tests ran", r.stdout.splitlines()[0])

    def test_singular_one_test_is_pass(self):
        r = run("print('Executed 1 test, with 0 failures (0 unexpected) in 0.1 (0.2) seconds')")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertTrue(r.stdout.startswith("PASS "), r.stdout)

    @unittest.skipIf(os.name == "nt", "Windows blocks deleting a file verdict holds open; the child exits 1 first")
    def test_child_deleting_log_is_fail_log_unreadable(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "v.log")
            r = run("import os\nos.remove(os.environ['VERDICT_LOG'])", log)
            self.assertNotEqual(r.returncode, 0, r.stdout)
            first = r.stdout.splitlines()[0] if r.stdout else ""
            self.assertTrue(first.startswith("FAIL "), (r.stdout[:300], r.stderr[-300:]))
            self.assertIn("log unreadable", first)
            self.assertNotIn("Traceback", r.stdout + r.stderr)

    def test_child_truncating_log_on_exit0_is_fail_log_unreadable(self):
        # Marker is flushed into the log, then the child empties the log: verdict cannot read its markers.
        code = ("import os\n"
                "print('** TEST FAILED **', flush=True)\n"
                "open(os.environ['VERDICT_LOG'], 'w').close()")
        with tempfile.TemporaryDirectory() as d:
            r = run(code, os.path.join(d, "v.log"))
            self.assertNotEqual(r.returncode, 0, r.stdout)
            first = r.stdout.splitlines()[0] if r.stdout else ""
            self.assertTrue(first.startswith("FAIL "), (r.stdout[:300], r.stderr[-300:]))
            self.assertIn("log unreadable", first)
            self.assertNotIn("Traceback", r.stdout + r.stderr)

    def test_child_truncating_log_on_exit7_keeps_rc_and_fails_log_unreadable(self):
        code = ("import os, sys\n"
                "print('** TEST FAILED **', flush=True)\n"
                "open(os.environ['VERDICT_LOG'], 'w').close()\n"
                "sys.exit(7)")
        with tempfile.TemporaryDirectory() as d:
            r = run(code, os.path.join(d, "v.log"))
            self.assertEqual(r.returncode, 7, r.stdout)
            first = r.stdout.splitlines()[0] if r.stdout else ""
            self.assertTrue(first.startswith("FAIL ") and " rc=7 " in first, (r.stdout[:300], r.stderr[-300:]))
            self.assertIn("log unreadable", first)
            self.assertNotIn("Traceback", r.stdout + r.stderr)

    def _fail_with_child_bytes(self, expr):
        # The child writes raw bytes itself: its own print() of a non-cp1252 character would fail first.
        # PYTHONUTF8 and PYTHONIOENCODING are removed so verdict meets the machine's default encoding.
        with tempfile.TemporaryDirectory() as d:
            script = os.path.join(d, "fx.py")
            with open(script, "w", encoding="ascii") as f:
                f.write("import sys\nsys.stdout.buffer.write(%s)\nsys.stdout.flush()\nsys.exit(7)\n" % expr)
            env = {k: v for k, v in os.environ.items()
                   if k not in ("VERDICT_LOG", "VERDICT_HEARTBEAT", "PYTHONUTF8", "PYTHONIOENCODING")}
            env["VERDICT_LOG"] = os.path.join(d, "v.log")
            return subprocess.run([sys.executable, V, sys.executable, script], capture_output=True, env=env, timeout=60)

    def test_non_ascii_excerpt_reaches_stdout_as_utf8(self):
        # Windows: a piped stdout is cp1252. print() of U+2192 raised UnicodeEncodeError, the FAIL
        # excerpt was lost, and verdict exited 1 instead of the child's 7.
        r = self._fail_with_child_bytes("'caf\\u00e9 \\u2192 ok\\n'.encode('utf-8')")
        err = r.stderr.decode("utf-8", "replace")
        self.assertEqual(r.returncode, 7, err[-300:])
        out = r.stdout.decode("utf-8")
        self.assertTrue(out.startswith("FAIL ") and " rc=7 " in out.splitlines()[0], out[:300])
        self.assertIn("→", out)
        self.assertNotIn("Traceback", err)

    def test_lone_non_utf8_byte_in_excerpt_does_not_crash_verdict(self):
        # A byte that is not valid UTF-8 decodes to U+FFFD in the excerpt, and cp1252 cannot print that either.
        r = self._fail_with_child_bytes("b'caf\\xe9 ok\\n'")
        err = r.stderr.decode("utf-8", "replace")
        self.assertEqual(r.returncode, 7, err[-300:])
        out = r.stdout.decode("utf-8", "replace")
        self.assertTrue(out.startswith("FAIL ") and " rc=7 " in out.splitlines()[0], out[:300])
        self.assertIn("caf", out)
        self.assertNotIn("Traceback", err)

    # These run bin/verdict.cmd. Only the gates-windows-rest CI job proves them.
    @unittest.skipUnless(os.name == "nt", "bin/verdict.cmd is the Windows launcher: it runs on Windows only (gates-windows-rest)")
    def test_cmd_launcher_pass(self):
        r = run("print('noisy')", launcher=CMD, timeout=60)
        self.assertEqual(r.returncode, 0, (r.stdout[:300], r.stderr[-300:]))
        self.assertTrue(r.stdout.startswith("PASS "), r.stdout)
        self.assertNotIn("noisy", r.stdout)

    @unittest.skipUnless(os.name == "nt", "bin/verdict.cmd is the Windows launcher: it runs on Windows only (gates-windows-rest)")
    def test_cmd_launcher_fail_keeps_rc_and_log(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "v.log")
            r = run("print('FAIL boom')\nraise SystemExit(7)", log, launcher=CMD, timeout=60)
            self.assertEqual(r.returncode, 7, (r.stdout[:300], r.stderr[-300:]))
            first = r.stdout.splitlines()[0]
            self.assertTrue(first.startswith("FAIL ") and " rc=7 " in first, first)
            m = re.search(r"log=(.+)$", first)
            self.assertTrue(m and os.path.exists(m.group(1)), first)
            self.assertEqual(os.path.normcase(m.group(1)), os.path.normcase(log))
            self.assertIn("FAIL boom", open(log).read())

DAY = 86400

def tmp_env(d):
    return {"TMPDIR": d, "TEMP": d, "TMP": d}

def log_folder(extra):
    """The folder bin/verdict puts its logs in: whatever tempfile resolves under the same env."""
    env = dict(os.environ); env.update(extra)
    return subprocess.run([sys.executable, "-c", "import tempfile; print(tempfile.gettempdir())"], capture_output=True, text=True, env=env, check=True).stdout.strip()

OWN_HEADER = "=== verdict run 2026-01-01 00:00:00: fx\n"  # the first line bin/verdict writes

def plant(folder, name, age_days, header=True):
    p = os.path.join(folder, name)
    open(p, "w").write((OWN_HEADER if header else "") + "old")
    t = time.time() - age_days * DAY
    os.utime(p, (t, t))
    return p

class Prune(unittest.TestCase):
    def setUp(self):
        self.sb = tempfile.TemporaryDirectory()
        self.extra = tmp_env(self.sb.name)
        self.folder = log_folder(self.extra)
        os.makedirs(self.folder, exist_ok=True)
    def tearDown(self):
        self.sb.cleanup()
    def go(self, code="raise SystemExit(3)"):
        return run(code, None, self.extra, timeout=60)

    def test_old_log_gone_recent_and_own_stay(self):
        old = plant(self.folder, "verdict-old.log", 8)
        recent = plant(self.folder, "verdict-recent.log", 6)
        r = self.go()
        self.assertEqual(r.returncode, 3, r.stdout)
        own = re.search(r"log=(.+)$", r.stdout.splitlines()[0]).group(1)
        self.assertFalse(os.path.exists(old), "8-day-old verdict log must be pruned")
        self.assertTrue(os.path.exists(recent), "6-day-old verdict log must stay")
        self.assertTrue(os.path.exists(own), "the run's own log must stay")
        self.assertEqual(os.path.dirname(os.path.normcase(own)), os.path.normcase(self.folder))

    def test_old_log_in_callers_verdict_log_folder_stays(self):
        with tempfile.TemporaryDirectory() as caller:
            audit = plant(caller, "verdict-audit-q4.log", 19)
            r = run("print('x')", os.path.join(caller, "mine.log"), self.extra, timeout=60)
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertTrue(os.path.exists(audit), "a caller's VERDICT_LOG folder must never be pruned")

    def test_old_log_without_own_header_stays(self):
        foreign = plant(self.folder, "verdict-foreign-tool.log", 30, header=False)
        old = plant(self.folder, "verdict-old.log", 30)
        r = self.go("print('x')")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertTrue(os.path.exists(foreign), "a verdict-*.log without bin/verdict's header is not ours")
        self.assertFalse(os.path.exists(old), "an old log with the header is still pruned")

    def test_non_verdict_logs_never_deleted(self):
        keep = [plant(self.folder, n, 30) for n in ("other.log", "verdict-old.txt", "xverdict-old.log", "verdict.log.bak")]
        r = self.go("print('x')")
        self.assertEqual(r.returncode, 0, r.stdout)
        for p in keep: self.assertTrue(os.path.exists(p), p)

    def test_folder_named_like_a_log_is_kept(self):
        d = os.path.join(self.folder, "verdict-x.log")
        os.mkdir(d)
        inner = plant(d, "inner.txt", 30)
        t = time.time() - 30 * DAY
        os.utime(d, (t, t))
        self.go("print('x')")
        self.assertTrue(os.path.isdir(d) and os.path.exists(inner))

    def test_symlink_named_like_a_log_leaves_target(self):
        with tempfile.TemporaryDirectory() as out:
            target = plant(out, "target.txt", 30)
            link = os.path.join(self.folder, "verdict-link.log")
            try: os.symlink(target, link)
            except (OSError, NotImplementedError) as e: self.skipTest(f"no symlink here: {e}")
            self.go("print('x')")
            self.assertTrue(os.path.exists(target), "a symlink must never delete what it points at")

    @unittest.skipUnless(os.name == "nt", "junctions are Windows only")
    def test_junction_named_like_a_log_leaves_target(self):
        with tempfile.TemporaryDirectory() as out:
            target = plant(out, "target.txt", 30)
            jn = os.path.join(self.folder, "verdict-junc.log")
            m = subprocess.run(["cmd", "/c", "mklink", "/J", jn, out], capture_output=True, text=True)
            if m.returncode: self.skipTest(f"no junction here: {m.stdout}{m.stderr}")
            self.go("print('x')")
            self.assertTrue(os.path.exists(target), "a junction must never delete what it points at")

    @unittest.skipUnless(os.name == "nt", "a locked file cannot be deleted on Windows only; POSIX has no deletion failure to build")
    def test_locked_old_log_does_not_change_verdict_or_rc(self):
        old = plant(self.folder, "verdict-locked.log", 30)
        with open(old, "rb"):
            fail = self.go("print('FAIL boom')\nraise SystemExit(7)")
            ok = self.go("print('fine')")
        self.assertEqual(fail.returncode, 7, (fail.stdout, fail.stderr[-300:]))
        self.assertTrue(fail.stdout.startswith("FAIL ") and " rc=7 " in fail.stdout.splitlines()[0], fail.stdout)
        self.assertNotIn("Traceback", fail.stderr)
        self.assertEqual(ok.returncode, 0, (ok.stdout, ok.stderr[-300:]))
        self.assertTrue(ok.stdout.startswith("PASS "), ok.stdout)
        self.assertNotIn("Traceback", ok.stderr)

class MissingVerdictLine(unittest.TestCase):
    """The verdict line is the contract: a run that dies in setup must still print FAIL."""
    def test_unwritable_verdict_log_prints_fail_line(self):
        with tempfile.TemporaryDirectory() as d:
            r = run("print('x')", os.path.join(d, "no-such-dir", "v.log"), timeout=60)
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue(any(l.startswith("FAIL ") for l in r.stdout.splitlines()), (r.stdout, r.stderr[-300:]))

if __name__ == "__main__":
    unittest.main()
