#!/usr/bin/env python3
"""Fixture test for bin/verdict. Run: python lint/test_verdict.py -v"""
import ast, os, re, shlex, shutil, signal, subprocess, sys, tempfile, time, types, unittest
from unittest import mock
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
sys.path.insert(0, os.path.join(HERE, "..", "hooks"))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (the one home, lint/_test_temp.py)
from proc_fixture import alive, default_sigint, kill_all, stop_group, wait_for, wait_gone, zombie  # noqa: E402  the one home of the signal-test helpers (testing/proc_fixture.py)
import _nowindow  # noqa: E402  the module bin/verdict imports too; its reaped_readable() is the seam the hang-stop cases patch
RUN_FOLDER = _test_temp.run_folder()  # its sweep is proved in test_find_copies.py
V = os.environ.get("VERDICT_UNDER_TEST") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin", "verdict")
# The Windows launcher. It always runs its sibling bin/verdict, so VERDICT_UNDER_TEST does not reach it.
CMD = [os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin", "verdict.cmd")]
UTF8 = {"PYTHONIOENCODING": "utf-8"}  # the child prints the real \u2714/\u2718 marks; a cp1252 stdout cannot
HB_FORMAT = re.compile(r"^verdict: still running, [0-9][0-9.]*s?, log=")
POSIX_SKIP = "the form runs through a POSIX shell (bash -c), which Windows does not have"
HANG_SKIP = "the hang stop reads CPU through a POSIX ps and stops a process group, which Windows does not have"
HANG_CAP = 30  # the hang cases' guard: a stop takes about 2 N s, so 30 s sits well above a run of 1-2 s
HANG_EARLY = "print('EARLY-HANG-MARK', flush=True)\nfor i in range(40): print(f'filler {i}', flush=True)\n"  # a line 40 lines before the stop
PS_SCOPE = "import os, subprocess\nsubprocess.run(['ps', '-p', str(os.getpid())], capture_output=True)\n"  # the child's own ps start: proves the counting shim is on its PATH
WALL_JUMP = ("import runpy, sys, time\n"  # the launcher: verdict runs in this process with its wall clock patched; the child is a separate process
             "real, reads = time.time, [0]\n"
             "def jumped():\n"  # each wall read lands an hour further on than the one before, so any two reads are 3600 s or more apart
             "    reads[0] += 1\n"
             "    return real() + 3600.0 * reads[0]\n"
             "time.time = jumped\n"  # time.monotonic is left as it is
             "sys.argv = sys.argv[1:]\n"
             "runpy.run_path(sys.argv[0], run_name='__main__')\n")

_VERDICT_MODULE = {}

def load_verdict_module():
    """bin/verdict loaded into this process, so a case can call its functions with fabricated samples. Its entry line calls
    main() and exits, so that line is swapped for `pass` before it runs: a `pass` still loads when the entry line sits under an
    `if __name__` guard. The swap must find the line (scope). No .pyc is written."""
    if "mod" not in _VERDICT_MODULE:
        with open(V, encoding="utf-8") as h: src = h.read()
        entry = "sys.exit(main(sys.argv[1:]))"
        if entry not in src: raise RuntimeError("bin/verdict's entry line moved, so the in-process load cannot swap it")
        mod = types.ModuleType("verdict_in_process")
        mod.__file__ = V
        exec(compile(src.replace(entry, "pass", 1), V, "exec"), mod.__dict__)
        _VERDICT_MODULE["mod"] = mod
    return _VERDICT_MODULE["mod"]

class OsNoWaitid:  # bin/verdict's `os` where os.waitid is missing (macOS before Python 3.13): reading waitid raises AttributeError, every other name is the real os module's
    def __init__(self, real): self.real = real
    def __getattr__(self, name):
        if name == "waitid": raise AttributeError("module 'os' has no attribute 'waitid'")
        return getattr(self.real, name)

def run(code=None, log=None, extra=None, timeout=None, launcher=None, shell=None, argv=None, shim=None, cwd=None):
    """`shell` is an sh -c line in which {cmd} stands for the verdict command, e.g. a pipe or a redirect.
    `argv` runs `verdict <argv...>` in place of the script. `shim` is (name, body): a fake executable `name`
    in a folder that comes first on PATH, so verdict sees argv[0] as that fake. `cwd` is the child's folder."""
    env = dict(os.environ)
    env.pop("VERDICT_LOG", None)
    env.pop("VERDICT_HEARTBEAT", None)
    env.pop("STALL_WATCH_BEAT", None)  # an inherited beat file would take the beat lines of these runs
    env.pop("VERDICT_HANG_SECONDS", None)  # the hang stop is off unless a case sets it (decision hang-stop)
    env.pop("VERDICT_FULL_LOG", None)  # the full log is off unless a case sets it (decision hang-stop)
    if log: env["VERDICT_LOG"] = log
    env.update(extra or {})
    with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
        if shim:
            bindir = os.path.join(d, "bin")
            os.mkdir(bindir)
            fake = os.path.join(bindir, shim[0])
            with open(fake, "w") as g: g.write(shim[1])
            os.chmod(fake, 0o755)
            env["PATH"] = bindir + os.pathsep + env.get("PATH", "")
        if argv is not None:
            cmd = [sys.executable, V] + argv
        else:
            script = os.path.join(d, "fx.py")
            open(script, "w").write(code)
            cmd = (launcher or [sys.executable, V]) + [sys.executable, script]
        if shell: cmd = ["sh", "-c", shell.replace("{cmd}", " ".join(shlex.quote(p) for p in cmd))]
        return subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=timeout, cwd=cwd)

def heartbeats(out):
    return [l for l in out.splitlines() if l.startswith("verdict: still running")]

def beats_on_stderr_only(case, r):
    """The beat goes to stderr, never stdout: the stall watch reads the task's output file, which keeps
    stderr when a pipe on stdout (`verdict ... | grep`) swallows the rest. Returns the beats."""
    beats = heartbeats(r.stderr)
    case.assertGreaterEqual(len(beats), 1, (r.stdout, r.stderr))
    case.assertEqual(heartbeats(r.stdout), [], r.stdout)
    return beats

class T(unittest.TestCase):
    def test_pass(self):
        r = run("print('noisy')")
        self.assertEqual(r.returncode, 0)
        self.assertTrue(r.stdout.startswith("PASS "))
        self.assertNotIn("noisy", r.stdout)

    def test_fail_line_excerpt_and_exit_code(self):
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
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

    def test_fail_excerpt_keeps_every_failing_case_name(self):
        # A CI step shows only this excerpt, so a FAIL must name each failing case. Twelve failing unittest cases make 36 hot lines,
        # and the 30-line excerpt cut the first cases' names (decision hang-stop: a wrapped step's log is the excerpt).
        lines = []
        for i in range(12):
            lines += [f"print('FAIL: test_case_{i:02d} (m.T.test_case_{i:02d})')", "print('Traceback (most recent call last):')",
                      f"print('AssertionError: {i} != -1')"]
        r = run("\n".join(lines) + "\nprint('FAILED (failures=12)')\nraise SystemExit(1)\n")
        self.assertEqual(r.returncode, 1)
        missing = [f"test_case_{i:02d}" for i in range(12) if f"test_case_{i:02d}" not in r.stdout]
        self.assertEqual(missing, [], "the FAIL excerpt drops the names of these failing cases")

    def test_reused_log_is_not_truncated(self):
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
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
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
            log = os.path.join(d, "v.log")
            r = run("import time\ntime.sleep(3.5)\nprint('done')", log, {"VERDICT_HEARTBEAT": "1"})
            self.assertEqual(r.returncode, 0)
            beats = beats_on_stderr_only(self, r)
            for b in beats:
                self.assertRegex(b, HB_FORMAT)
                self.assertTrue(b.endswith(f"log={log}"), b)
            self.assertTrue(r.stdout.splitlines()[-1].startswith("PASS "), r.stdout)

    @unittest.skipIf(os.name == "nt", "POSIX sh pipe")
    def test_heartbeat_reaches_the_output_file_through_a_stdout_pipe(self):
        """`verdict ... | grep` swallows stdout, so the beat must come on stderr to reach the output file the stall watch reads (decision stall-watch)."""
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
            log, out = os.path.join(d, "v.log"), os.path.join(d, "out")
            run("import time\ntime.sleep(3)", log, {"VERDICT_HEARTBEAT": "1"}, timeout=30,
                shell="({cmd} | grep nomatch) > " + shlex.quote(out) + " 2>&1")  # grep's exit 1 is no verdict here
            merged = open(out).read()
            self.assertIn("=== verdict run", open(log).read(), "verdict never ran")
            beats = heartbeats(merged)
            self.assertGreaterEqual(len(beats), 1, repr(merged))
            for b in beats:
                self.assertRegex(b, HB_FORMAT)
                self.assertTrue(b.endswith(f"log={log}"), b)
            self.assertFalse(any(l.startswith("PASS ") for l in merged.splitlines()), "grep passed stdout through: the pipe proves nothing")

    def test_heartbeat_also_appends_to_stall_watch_beat_file(self):
        """With STALL_WATCH_BEAT set, each beat line is appended to that file, so a watch reading it sees the job alive. Stderr keeps the same line (decision stall-watch)."""
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
            log, beat = os.path.join(d, "v.log"), os.path.join(d, "stall-watch-x.beat")
            open(beat, "w").write("keep\n")
            r = run("import time\ntime.sleep(2.5)\nprint('done')", log,
                    {"VERDICT_HEARTBEAT": "1", "STALL_WATCH_BEAT": beat})
            self.assertEqual(r.returncode, 0, r.stdout)
            beats = beats_on_stderr_only(self, r)
            lines = open(beat).read().splitlines()
            self.assertEqual(lines[:1], ["keep"], "the beat file was truncated or not appended to")
            self.assertEqual(lines[1:], beats, "the beat file lines differ from the stderr beat lines")

    def test_fast_command_prints_no_heartbeat(self):
        """A child shorter than the beat interval gets no beat; 30 s is wide enough that Python start cost cannot reach it."""
        r = run("print('quick')", None, {"VERDICT_HEARTBEAT": "30"})
        self.assertEqual(r.returncode, 0)
        self.assertEqual(heartbeats(r.stdout + r.stderr), [], (r.stdout, r.stderr))
        self.assertTrue(r.stdout.startswith("PASS "), r.stdout)

    def test_no_heartbeat_after_the_child_exits(self):
        """A beat after exit is a false alarm: the beat count cannot exceed the whole seconds the verdict line reports."""
        r = run("import time\ntime.sleep(1.2)", None, {"VERDICT_HEARTBEAT": "1"})
        lines = r.stdout.splitlines()
        m = re.match(r"PASS .* \(([0-9.]+)s\)$", lines[-1])
        self.assertTrue(m, r.stdout)
        beats = beats_on_stderr_only(self, r)
        self.assertLessEqual(len(beats), int(float(m.group(1))), (r.stdout, r.stderr))
        self.assertEqual(heartbeats(lines[-1]), [], r.stdout)

    def test_slow_fail_heartbeats_then_same_excerpt(self):
        """A long, quiet run must not draw a false stall alarm (Tools that are quiet by design), so check for at least one beat, never an exact count (decision stall-watch)."""
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
            log = os.path.join(d, "v.log")
            r = run("import sys, time\nprint('one')\ntime.sleep(2.5)\nprint('FAIL boom')\nprint('err', file=sys.stderr)\nsys.exit(7)", log, {"VERDICT_HEARTBEAT": "1"})
            self.assertEqual(r.returncode, 7)
            beats_on_stderr_only(self, r)
            lines = r.stdout.splitlines()
            first = lines[0]
            self.assertTrue(first.startswith("FAIL ") and " rc=7 " in first and f"log={log}" in first, first)
            body = lines[1:]
            self.assertIn("FAIL boom", body)
            self.assertNotIn("one", body)
            self.assertFalse(any("still running" in l for l in body), body)

    def test_heartbeat_never_carries_command_output(self):
        """A long, quiet run must not draw a false stall alarm (Tools that are quiet by design), so check for at least one beat, never an exact count (decision stall-watch)."""
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
            log = os.path.join(d, "v.log")
            r = run("import time\nprint('SECRET-OUT-7731', flush=True)\ntime.sleep(2.5)\nprint('SECRET-OUT-7731 again')", log, {"VERDICT_HEARTBEAT": "1"})
            self.assertEqual(r.returncode, 0)
            beats = beats_on_stderr_only(self, r)
            for b in beats:
                self.assertRegex(b, HB_FORMAT)
                self.assertNotIn("SECRET-OUT-7731", b)
            self.assertNotIn("SECRET-OUT-7731", r.stdout + r.stderr)

    def test_bad_heartbeat_value_still_runs_the_command(self):
        code = "import sys, time\nprint('MARK-RAN', flush=True)\ntime.sleep(2)\nsys.exit(7)"
        for val in ["abc", "0", "-1", "1e-9", "0.001", "inf", "nan"]:
            with self.subTest(VERDICT_HEARTBEAT=val), tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
                log = os.path.join(d, "v.log")
                r = run(code, log, {"VERDICT_HEARTBEAT": val}, timeout=30)
                self.assertEqual(r.returncode, 7, (r.stdout[:300], r.stderr[-300:]))
                self.assertIn("MARK-RAN", open(log).read())
                self.assertNotIn("Traceback", r.stdout + r.stderr)
                self.assertLess(len(heartbeats(r.stdout + r.stderr)), 5, (r.stdout, r.stderr))

    @unittest.skipIf(os.name == "nt", "POSIX shell pipe and signals")
    def test_broken_pipe_does_not_orphan_child(self):
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
            log = os.path.join(d, "v.log")
            pidfile = os.path.join(d, "child.pid")
            script = os.path.join(d, "fx.py")
            open(script, "w").write(f"import os, time\nopen({pidfile!r}, 'w').write(str(os.getpid()))\ntime.sleep(3)\n")
            env = dict(os.environ)
            env.pop("VERDICT_HEARTBEAT", None)
            env.pop("STALL_WATCH_BEAT", None)
            env.update({"VERDICT_HEARTBEAT": "1", "VERDICT_LOG": log})
            # 2>&1: the beat is on stderr, so the pipe must carry it or no beat meets the closed reader.
            cmd = " ".join(shlex.quote(p) for p in [sys.executable, V, sys.executable, script]) + " 2>&1 | head -n 1"
            r = subprocess.run(cmd, shell=True, executable="/bin/bash", capture_output=True, text=True, env=env, timeout=30)
            self.assertTrue(os.path.exists(pidfile), "child never started")
            pid = int(open(pidfile).read())
            self.assertFalse(alive(pid), f"child {pid} still running after verdict returned")
            self.assertNotIn("cannot run", open(log).read())
            self.assertNotIn("cannot run", r.stdout + r.stderr)

    @unittest.skipIf(os.name == "nt", "POSIX signals")
    def test_sigterm_forwards_to_child(self):
        """A TERM or HUP to verdict ends its child and the child's child before verdict returns. Verdict killed alone
        leaves its test run going."""
        for sig in (signal.SIGTERM, signal.SIGHUP):
            with self.subTest(signal=sig.name):
                self.assert_signal_ends_child_tree(sig)

    def start_child_tree(self, d, preexec=None, env_extra=None, output=None, before_sleep=""):
        """Starts verdict in its own group, running a child that starts a grandchild. -> (the verdict Popen, child pid, grandchild pid).
        The pids are read from a marker the child writes once both run. A red run's pids are killed at cleanup.
        env_extra sets verdict's environment. output (an open file) takes verdict's stdout and stderr; else both go to nowhere.
        before_sleep is Python source the child runs after the marker, before it sleeps 300 s."""
        ready = os.path.join(d, "ready.txt")
        script = os.path.join(d, "fx.py")
        # The child starts a grandchild, then writes both pids. The marker is renamed into place, so a reader sees it whole.
        body = ("import os, subprocess, sys, time\n"
                "grand = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(300)'])\n"
                "tmp = READY + '.tmp'\n"
                "open(tmp, 'w').write('%d %d' % (os.getpid(), grand.pid))\n"
                "os.replace(tmp, READY)\n"
                + before_sleep +
                "time.sleep(300)\n").replace("READY", repr(ready))
        with open(script, "w", encoding="utf-8") as handle:
            handle.write(body)
        found = []
        self.addCleanup(kill_all, found)  # the pids a red run leaves running are killed here
        env = dict(os.environ)
        env.pop("VERDICT_HEARTBEAT", None)
        env.pop("STALL_WATCH_BEAT", None)
        env.pop("VERDICT_HANG_SECONDS", None)
        env.pop("VERDICT_FULL_LOG", None)
        env.update(env_extra or {})
        env["VERDICT_LOG"] = os.path.join(d, "v.log")
        sink = output if output is not None else subprocess.DEVNULL
        proc = subprocess.Popen([sys.executable, V, sys.executable, script], env=env, start_new_session=True,
                                stdout=sink, stderr=subprocess.STDOUT if output is not None else subprocess.DEVNULL, preexec_fn=preexec)
        self.addCleanup(stop_group, proc)
        self.assertTrue(wait_for(ready, 60, proc), "fixture: verdict's child never wrote its pids")
        child, grand = (int(x) for x in open(ready, encoding="utf-8").read().split())
        found += [child, grand]
        return proc, child, grand

    def assert_signal_ends_child_tree(self, sig):
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
            proc, child, grand = self.start_child_tree(d)
            self.assertTrue(alive(child) and alive(grand), "scope: the child and its child must run before %s" % sig.name)
            proc.send_signal(sig)
            try:
                proc.wait(timeout=60)
            except subprocess.TimeoutExpired:
                self.fail("verdict did not exit within 60 s of %s" % sig.name)
            self.assertFalse(alive(child), "%s to verdict did not reach its child %d, which runs after verdict returned" % (sig.name, child))
            self.assertFalse(alive(grand), "%s to verdict did not reach the child's child %d, which runs after verdict returned" % (sig.name, grand))

    @unittest.skipIf(os.name == "nt", "POSIX signals")
    def test_sigkill_to_the_group_that_started_verdict_ends_the_child_tree(self):
        """A KILL to the group that started verdict ends verdict's child and that child's child. The harness stops a background
        task by its own group, and no handler runs on a KILL, so the group is the only reach."""
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
            proc, child, grand = self.start_child_tree(d)
            self.assertEqual(os.getpgid(proc.pid), proc.pid, "scope: verdict must lead its own group, the one the KILL goes to")
            self.assertTrue(alive(child) and alive(grand), "scope: the child and its child must run before the KILL")
            os.killpg(proc.pid, signal.SIGKILL)
            try:
                proc.wait(timeout=60)
            except subprocess.TimeoutExpired:
                self.fail("verdict did not exit within 60 s of a KILL to its group")
            self.assertTrue(wait_gone(child, 30), "a KILL to the group that started verdict did not end its child %d" % child)
            self.assertTrue(wait_gone(grand, 30), "a KILL to the group that started verdict did not end the child's child %d" % grand)

    @unittest.skipIf(os.name == "nt", "POSIX signals")
    def test_sigint_to_verdict_ends_the_child_tree(self):
        """An INT to verdict alone ends its child and that child's child before verdict returns."""
        # A process that inherits SIG_IGN for INT never gets Python's KeyboardInterrupt, so verdict starts with the default action.
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
            proc, child, grand = self.start_child_tree(d, preexec=default_sigint())
            self.assertTrue(alive(child) and alive(grand), "scope: the child and its child must run before INT")
            proc.send_signal(signal.SIGINT)
            try:
                proc.wait(timeout=60)
            except subprocess.TimeoutExpired:
                self.fail("verdict did not exit within 60 s of INT")
            self.assertTrue(wait_gone(child, 30), "INT to verdict did not end its child %d, which runs after verdict returned" % child)
            self.assertTrue(wait_gone(grand, 30), "INT to verdict did not end the child's child %d, which runs after verdict returned" % grand)

    def run_hang_case(self, d, seconds, before_sleep="", extra_env=None):
        """Runs verdict over a child tree with VERDICT_HANG_SECONDS set and waits for verdict to return. A verdict that does not return
        within HANG_CAP fails here. extra_env adds verdict's other variables. -> (verdict's rc, its output, child pid, grandchild pid, the time it returned)."""
        out = os.path.join(d, "out.txt")
        env = {"VERDICT_HANG_SECONDS": str(seconds)}
        env.update(extra_env or {})
        with open(out, "wb") as fh:
            proc, child, grand = self.start_child_tree(d, env_extra=env, output=fh, before_sleep=before_sleep)
            self.assertTrue(alive(child) and alive(grand), "scope: the child and its child must run before the stop")
            try:
                proc.wait(timeout=HANG_CAP)
            except subprocess.TimeoutExpired:
                self.fail("verdict did not stop a hang within %d s with VERDICT_HANG_SECONDS=%d" % (HANG_CAP, seconds))
            returned = time.time()
        with open(out, encoding="utf-8", errors="replace") as fh:
            return proc.returncode, fh.read(), child, grand, returned

    def count_ps_starts(self, code, seconds):
        """Runs verdict over code with VERDICT_HANG_SECONDS set and a counting `ps` first on PATH. -> (the number of ps starts, the run).
        Each start writes one line to the counter file, so every ps call verdict or the child makes is counted."""
        real = shutil.which("ps")
        if real is None: raise unittest.SkipTest("no ps on PATH to count")
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
            counter = os.path.join(d, "ps-starts.txt")
            body = "#!/bin/sh\necho start >> %s\nexec %s \"$@\"\n" % (shlex.quote(counter), shlex.quote(real))
            r = run(code, os.path.join(d, "v.log"), {"VERDICT_HANG_SECONDS": str(seconds)}, timeout=60, shim=("ps", body))
            starts = 0
            if os.path.exists(counter):
                with open(counter, encoding="utf-8") as h: starts = h.read().count("start")
        return starts, r

    @unittest.skipIf(os.name == "nt", HANG_SKIP)
    def test_hang_stop_idle_silent_child_is_stopped_with_its_tree(self):
        """An idle child that printed one line, then went silent, is stopped at N = 1 s. The output holds one HANG line,
        the process tree (both pids) and the log tail, and the child and its child are gone (decision hang-stop)."""
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
            rc, out, child, grand, _ = self.run_hang_case(d, 1, before_sleep="print('LAST-LINE-BEFORE-SILENCE', flush=True)\n")
            self.assertNotEqual(rc, 0, out)
            self.assertTrue(any(l.startswith("HANG ") for l in out.splitlines()), "verdict printed no HANG line: " + out)
            self.assertIn(str(child), out, "the HANG output names no child pid: the process tree was not printed")
            self.assertIn(str(grand), out, "the HANG output names no grandchild pid: the process tree was not printed")
            self.assertIn("LAST-LINE-BEFORE-SILENCE", out, "the HANG output has no log tail")
            self.assertTrue(wait_gone(child, 30), "the stop left the child %d running" % child)
            self.assertTrue(wait_gone(grand, 30), "the stop left the child's child %d running" % grand)

    def test_hang_stop_busy_silent_child_is_not_stopped(self):
        """Control. A child that burns CPU for 4 s with no output advances its CPU, so at N = 2 s it is not stopped.
        It runs to its end and reads PASS."""
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
            log = os.path.join(d, "v.log")
            r = run("import time\nend = time.time() + 4\nwhile time.time() < end: pass\nprint('END-MARK')", log,
                    {"VERDICT_HANG_SECONDS": "2"}, timeout=60)
            self.assertFalse(any(l.startswith("HANG ") for l in r.stdout.splitlines()), r.stdout)
            with open(log, encoding="utf-8") as h: full = h.read()
            self.assertIn("END-MARK", full, "the busy child was stopped before its end")
            self.assertTrue(r.stdout.startswith("PASS "), r.stdout)

    def test_hang_stop_child_printing_a_byte_each_window_is_not_stopped(self):
        """Control. A child that prints a byte every 0.5 s for 4 s is never silent for N = 2 s, so it is not stopped."""
        code = "import time\nfor _ in range(8):\n    print('.', flush=True)\n    time.sleep(0.5)\nprint('END-MARK')"
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
            log = os.path.join(d, "v.log")
            r = run(code, log, {"VERDICT_HANG_SECONDS": "2"}, timeout=60)
            self.assertFalse(any(l.startswith("HANG ") for l in r.stdout.splitlines()), r.stdout)
            with open(log, encoding="utf-8") as h: full = h.read()
            self.assertIn("END-MARK", full, "the printing child was stopped before its end")
            self.assertTrue(r.stdout.startswith("PASS "), r.stdout)

    def test_hang_stop_is_off_without_the_env_var(self):
        """Control. With VERDICT_HANG_SECONDS unset, an idle silent child is never stopped: it runs its 3 s and reads
        PASS. Session use never stops (decision hang-stop)."""
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
            log = os.path.join(d, "v.log")
            r = run("import time\ntime.sleep(3)\nprint('END-MARK')", log, timeout=60)  # run() strips the variable from the caller's environment
            self.assertFalse(any(l.startswith("HANG ") for l in r.stdout.splitlines()), r.stdout)
            with open(log, encoding="utf-8") as h: full = h.read()
            self.assertIn("END-MARK", full, "the idle child was stopped with the env var unset")
            self.assertTrue(r.stdout.startswith("PASS "), r.stdout)

    @unittest.skipIf(os.name == "nt", HANG_SKIP)
    def test_hang_stop_waits_for_cpu_to_go_still_too(self):
        """The child prints once, burns CPU silently for 3 s, then sits idle. At N = 2 s the stop needs the CPU still for
        N s as well as the output, so verdict returns no earlier than the busy run's end plus N - 1 s (ps counts whole seconds).
        A stop that reads output alone would land inside the busy run and never write its end marker."""
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
            busy = os.path.join(d, "busy-end.txt")
            before = ("print('FIRST-BYTE', flush=True)\n"
                      "end = time.time() + 3\n"
                      "while time.time() < end: pass\n"
                      "with open(%r, 'w') as mark: mark.write(repr(time.time()))\n" % busy)
            rc, out, child, grand, returned = self.run_hang_case(d, 2, before_sleep=before)
            self.assertTrue(os.path.exists(busy), "the child was stopped during its busy run: it never wrote its busy end")
            with open(busy, encoding="utf-8") as h: busy_end = float(h.read())
            self.assertTrue(any(l.startswith("HANG ") for l in out.splitlines()), "verdict printed no HANG line: " + out)
            self.assertGreaterEqual(returned, busy_end + 2 - 1.0,
                                    "verdict returned %.1f s after the busy run's end, before the CPU had been still for N s" % (returned - busy_end))

    @unittest.skipIf(os.name == "nt", HANG_SKIP)
    def test_hang_stop_printing_child_makes_no_process_table_read(self):
        """Control. While the child prints a byte every 0.1 s, verdict starts no ps: a process-table read happens only on
        a silent wake (decision hang-stop). The child's own ps start first proves the counting shim is on the child's PATH."""
        code = PS_SCOPE + "import time\nfor _ in range(30):\n    print('.', flush=True)\n    time.sleep(0.1)\nprint('END-MARK')"
        starts, r = self.count_ps_starts(code, 2)
        self.assertGreaterEqual(starts, 1, "scope: the child's own ps start never reached the counting shim")
        self.assertTrue(r.stdout.startswith("PASS "), r.stdout)
        self.assertEqual(starts, 1, "verdict started a process-table read while the child was printing")

    @unittest.skipIf(os.name == "nt", HANG_SKIP)
    def test_hang_stop_silent_child_makes_a_process_table_read(self):
        """While the child sits silent for 4 s at N = 1 s, verdict reads the process table on a silent wake. Main reads
        none, so the count stays at the child's one ps start."""
        code = PS_SCOPE + "import time\ntime.sleep(4)\nprint('END-MARK')"
        starts, r = self.count_ps_starts(code, 1)
        self.assertGreaterEqual(starts, 1, "scope: the child's own ps start never reached the counting shim")
        self.assertGreater(starts, 1, "verdict read no process table during 4 s of silence")

    @unittest.skipIf(os.name == "nt", HANG_SKIP)
    def test_hang_stop_verdict_line_is_one_bounded_hang_line(self):
        """A hang's verdict line is one HANG line, bounded in length, that names the command and its log. No other verdict
        word prints, and verdict exits non-zero."""
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
            rc, out, child, grand, _ = self.run_hang_case(d, 1)
            lines = out.splitlines()
            hang = [l for l in lines if l.startswith("HANG ")]
            self.assertEqual(len(hang), 1, "want one HANG line, got %d: %s" % (len(hang), out))
            self.assertLessEqual(len(hang[0]), 300, "the HANG line is not bounded: %d chars" % len(hang[0]))
            self.assertIn("fx.py", hang[0], "the HANG line does not name the command")
            self.assertIn("log=", hang[0], "the HANG line names no log")
            self.assertFalse(any(l.startswith(("FAIL ", "PASS ", "SKIP ")) for l in lines), "a second verdict word printed: " + out)
            self.assertNotEqual(rc, 0, "a hang exits zero")

    @unittest.skipIf(os.name == "nt", HANG_SKIP)
    def test_full_log_hang_prints_the_verdict_line_first(self):
        """With VERDICT_FULL_LOG=1 the HANG line is the first printed line, then the log (decision hang-stop). Today the process tree
        and the log tail print before it, so this fails on the old code."""
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
            _, out, _, _, _ = self.run_hang_case(d, 1, before_sleep=HANG_EARLY, extra_env={"VERDICT_FULL_LOG": "1"})
        first = out.splitlines()[:1]
        self.assertTrue(first and first[0].startswith("HANG "), "the first line with VERDICT_FULL_LOG=1 is not the HANG line: %r" % first)

    @unittest.skipIf(os.name == "nt", HANG_SKIP)
    def test_full_log_hang_prints_a_line_more_than_30_before_the_stop(self):
        """With VERDICT_FULL_LOG=1 the HANG output keeps a child's line 40 lines before the stop: the log tail is 30 lines."""
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
            _, out, _, _, _ = self.run_hang_case(d, 1, before_sleep=HANG_EARLY, extra_env={"VERDICT_FULL_LOG": "1"})
        self.assertEqual(sum(l.startswith("HANG ") for l in out.splitlines()), 1, "want one HANG line: " + out)
        self.assertIn("EARLY-HANG-MARK", out.splitlines(), "the HANG output with VERDICT_FULL_LOG=1 drops a line 40 lines before the stop")

    @unittest.skipIf(os.name == "nt", HANG_SKIP)
    def test_hang_without_the_switch_keeps_the_excerpt(self):
        """Control, green on the old code: with the switch unset the early line stays out, and the HANG line is still there."""
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
            _, out, _, _, _ = self.run_hang_case(d, 1, before_sleep=HANG_EARLY)
        self.assertTrue(any(l.startswith("HANG ") for l in out.splitlines()), out)
        self.assertNotIn("EARLY-HANG-MARK", out.splitlines(), "the HANG excerpt with the switch unset carries a line 40 before the stop")

    def run_bounded(self, *args, **kwargs):
        """run() with HANG_CAP as its timeout: a verdict that does not return fails the case."""
        try: return run(*args, timeout=HANG_CAP, **kwargs)
        except subprocess.TimeoutExpired: self.fail("verdict did not return within %d s" % HANG_CAP)

    @unittest.skipIf(os.name == "nt", HANG_SKIP)
    def test_hang_stop_wall_clock_jump_does_not_stop_a_quiet_child(self):
        """Silence is measured on a clock a wall-clock jump cannot move. The launcher's wall clock jumps an hour between reads,
        and verdict's wakes are 1 s apart, so the wall gap from the baseline to the next wake is an hour while N = 4 s of real
        time has not passed. The child prints once, sits idle for 4 s, then prints END-MARK: it runs to that end and reads PASS.
        N is 4, not 2: a wake is at least 1 s, so with N = 2 the child would have to end inside a 1 s window the wakes do not fix."""
        code = "import time\nprint('LAST-LINE-BEFORE-SILENCE', flush=True)\ntime.sleep(4)\nprint('END-MARK')"
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
            log = os.path.join(d, "v.log")
            r = self.run_bounded(code, log, {"VERDICT_HANG_SECONDS": "4"}, launcher=[sys.executable, "-c", WALL_JUMP, V])
            self.assertFalse(any(l.startswith("HANG ") for l in r.stdout.splitlines()),
                             "a wall-clock jump stopped a child that had not been silent for N s of real time: " + r.stdout)
            with open(log, encoding="utf-8") as h: full = h.read()
            self.assertIn("END-MARK", full, "the child was stopped before its end")
            self.assertTrue(r.stdout.startswith("PASS "), r.stdout)

    @unittest.skipIf(os.name == "nt", HANG_SKIP)
    def test_hang_stop_reaped_children_are_work(self):
        """A step that prints nothing, and each second starts a short CPU-burning child that exits and is reaped, is working.
        At N = 2 s verdict runs it to END-MARK and reads PASS: the CPU of a child reaped between two samples still counts (decision hang-stop)."""
        burst = "%s -c 'for i in range(6000000): pass'" % shlex.quote(sys.executable)
        script = "for i in 1 2 3 4 5 6 7 8; do %s; sleep 1; done; echo END-MARK" % burst
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
            log = os.path.join(d, "v.log")
            r = self.run_bounded(None, log, {"VERDICT_HANG_SECONDS": "2"}, argv=["bash", "-c", script])
            self.assertFalse(any(l.startswith("HANG ") for l in r.stdout.splitlines()),
                             "a step whose reaped children burn CPU was stopped as a hang: " + r.stdout)
            with open(log, encoding="utf-8") as h: full = h.read()
            self.assertIn("END-MARK", full, "the step was stopped before its end")
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertTrue(r.stdout.startswith("PASS "), r.stdout)

    def hang_check_on_new_idle_pid(self, readable):
        """hang_check at N = 2 s over fabricated samples, with reaped_readable() patched to `readable`. The first silent wake takes
        the baseline: pid 100 at 1.5 s of CPU. At 2 s of silence pid 100 is still at 1.5 s and a fresh idle pid 101 (0 s) has joined.
        -> hang_check's answer on that second wake. Patching the seam with create=True keeps a missing seam a failed assert."""
        verdict = load_verdict_module()
        samples = iter([({}, {"100": 1.5}), ({}, {"100": 1.5, "101": 0.0})])
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d, open(os.path.join(d, "log.txt"), "ab") as f:
            f.write(b"LAST-LINE-BEFORE-SILENCE\n")
            f.flush()
            watch = {"seen": os.fstat(f.fileno()).st_size, "quiet": None, "base": None}
            proc = types.SimpleNamespace(pid=1)
            with mock.patch.object(verdict, "hang_sample", lambda p: next(samples)), \
                 mock.patch.object(_nowindow, "reaped_readable", lambda: readable, create=True):
                first = verdict.hang_check(proc, f, watch, 2, 0.0)
                second = verdict.hang_check(proc, f, watch, 2, 2.0)
        self.assertIsNone(first, "scope: the first silent wake takes the baseline and must stop nothing")
        return second

    def test_hang_stop_new_idle_pid_is_stopped_where_reaped_cpu_reads(self):
        """P2, the red half. Where reaped CPU can be read, a new pid with no CPU is no work: at 2 s of silence with the child's CPU
        still, hang_check returns the sample to stop on. Under the new-pid clause it returns None (decision hang-stop)."""
        stop = self.hang_check_on_new_idle_pid(True)
        self.assertIsNotNone(stop, "a fresh idle pid with no CPU counted as work where reaped CPU reads: no stop at 2 s of silence")

    def test_hang_stop_new_idle_pid_is_work_where_reaped_cpu_cannot_read(self):
        """P2, the green control. Where reaped CPU cannot be read, a new pid is the only sign of work, so hang_check does not stop (decision hang-stop)."""
        stop = self.hang_check_on_new_idle_pid(False)
        self.assertIsNone(stop, "a fresh idle pid was not counted as work where reaped CPU cannot be read: a stop at 2 s of silence")

    def hang_check_from_quiet_mark(self, verdict, proc, f):
        """hang_check at N = 2 s: quiet since 0 s, with the baseline read from the process table now, checked at 10 s with no output
        since. The baseline is a real sample, so the case reads what ps shows for the child (decision hang-stop)."""
        watch = {"seen": os.fstat(f.fileno()).st_size, "quiet": 0.0, "base": None}
        sample = verdict.hang_sample(proc)
        self.assertIsNotNone(sample, "scope: the process table gives no row for child %d, so there is no baseline to compare" % proc.pid)
        watch["base"] = sample[1]
        return verdict.hang_check(proc, f, watch, 2, 10.0)

    def wait_until(self, cond, what):
        """Polls cond() until it holds, at most HANG_CAP s. A poll on the child's state, never a fixed sleep."""
        end = time.monotonic() + HANG_CAP
        while not cond():
            if time.monotonic() > end: self.fail("fixture: %s did not happen within %d s" % (what, HANG_CAP))
            time.sleep(0.02)

    @unittest.skipIf(os.name == "nt", HANG_SKIP)
    def test_hang_stop_finished_child_not_yet_reaped_is_not_a_hang(self):
        """P2, the red half. A child that has exited 0 but is not reaped keeps a zombie row in ps, with its CPU frozen. At 10 s of
        silence after a quiet mark at 0 s, hang_check stopped it, so verdict would print HANG and exit 124 for a step that
        finished. A finished step is never a hang: hang_check returns None (decision hang-stop)."""
        verdict = load_verdict_module()
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d, open(os.path.join(d, "log.txt"), "ab") as f:
            proc = subprocess.Popen(["bash", "-c", "echo END-MARK; exit 0"], stdout=f, stderr=subprocess.DEVNULL)
            try:
                self.wait_until(lambda: zombie(proc.pid), "the child exits without being reaped")
                stop = self.hang_check_from_quiet_mark(verdict, proc, f)
            finally:
                proc.wait()  # reaps the child here, so the case leaves no zombie behind
        self.assertTrue(stop is None, "hang_check stopped a child that had exited 0 and was not yet reaped: a finished step read as a hang")

    def hang_check_from_quiet_mark_without_waitid(self, verdict, proc, f):
        """hang_check_from_quiet_mark with bin/verdict's os missing os.waitid, as on macOS before Python 3.13: exited() then reads False.
        The scope assert keeps a patch that did nothing from passing a case."""
        with mock.patch.object(verdict, "os", OsNoWaitid(os)):
            self.assertFalse(hasattr(verdict.os, "waitid"), "scope: bin/verdict's os still has waitid, so the case does not test the missing read")
            return self.hang_check_from_quiet_mark(verdict, proc, f)

    @unittest.skipIf(os.name == "nt", HANG_SKIP)
    def test_hang_stop_finished_child_not_reaped_without_waitid_is_not_a_hang(self):
        """P2, the red half, with os.waitid missing as on macOS before Python 3.13. The child is the one the case above makes: exited 0,
        not reaped, a zombie row with its CPU frozen. exited() then answers False for it, so the zombie reads as a hang and hang_check
        stops it. A finished step is never a hang: hang_check returns None (decision hang-stop)."""
        verdict = load_verdict_module()
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d, open(os.path.join(d, "log.txt"), "ab") as f:
            proc = subprocess.Popen(["bash", "-c", "echo END-MARK; exit 0"], stdout=f, stderr=subprocess.DEVNULL)
            try:
                self.wait_until(lambda: zombie(proc.pid), "the child exits without being reaped")
                stop = self.hang_check_from_quiet_mark_without_waitid(verdict, proc, f)
            finally:
                proc.wait()  # reaps the child here, so the case leaves no zombie behind
        self.assertTrue(stop is None, "hang_check stopped a child that had exited 0 and was not yet reaped, with os.waitid missing: a finished step read as a hang")

    @unittest.skipIf(os.name == "nt", HANG_SKIP)
    def test_hang_stop_live_silent_child_is_stopped_from_the_same_quiet_mark(self):
        """Control, green. A live child that prints once and then sleeps is silent and idle. Under the same quiet mark hang_check returns
        the stop, so the finished-child case cannot pass by never stopping (decision hang-stop)."""
        verdict = load_verdict_module()
        code = "import time\nprint('LAST-LINE-BEFORE-SILENCE', flush=True)\ntime.sleep(60)\n"
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d, open(os.path.join(d, "log.txt"), "ab") as f:
            proc = subprocess.Popen([sys.executable, "-c", code], stdout=f, stderr=subprocess.DEVNULL)
            try:
                self.wait_until(lambda: os.fstat(f.fileno()).st_size > 0, "the child prints its last line")
                stop = self.hang_check_from_quiet_mark(verdict, proc, f)
            finally:
                proc.kill()
                proc.wait()
        self.assertTrue(stop is not None, "hang_check did not stop a live silent idle child under the same quiet mark: the finished-child case would pass by never stopping")

    @unittest.skipIf(os.name == "nt", HANG_SKIP)
    def test_hang_stop_live_silent_child_is_stopped_without_waitid(self):
        """Control, green. With os.waitid missing, a live child that prints once and then sleeps is silent and idle, so hang_check still
        returns the stop. The zombie case beside the live control cannot pass by never stopping (decision hang-stop)."""
        verdict = load_verdict_module()
        code = "import time\nprint('LAST-LINE-BEFORE-SILENCE', flush=True)\ntime.sleep(60)\n"
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d, open(os.path.join(d, "log.txt"), "ab") as f:
            proc = subprocess.Popen([sys.executable, "-c", code], stdout=f, stderr=subprocess.DEVNULL)
            try:
                self.wait_until(lambda: os.fstat(f.fileno()).st_size > 0, "the child prints its last line")
                stop = self.hang_check_from_quiet_mark_without_waitid(verdict, proc, f)
            finally:
                proc.kill()
                proc.wait()
        self.assertTrue(stop is not None, "hang_check did not stop a live silent idle child with os.waitid missing: the zombie case would pass by never stopping")

    @unittest.skipIf(os.name == "nt", HANG_SKIP)
    def test_hang_stop_ps_down_is_no_stop(self):
        """Control. When the process-table read fails, verdict has no table to judge CPU by, so a silent child is not stopped:
        at the baseline and after N = 1 s of silence it runs its 5 s and reads PASS. Two ways for ps to fail: a ps that exits
        non-zero (an empty table, no note), and a ps that cannot start (the PS_DOWN note). Only the second reaches the mutant at bin/verdict:156."""
        code = "import time\nprint('LAST-LINE-BEFORE-SILENCE', flush=True)\ntime.sleep(5)\nprint('END-MARK')"
        for label in ("exits non-zero", "cannot start"):
            with self.subTest(ps=label), tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
                log = os.path.join(d, "v.log")
                if label == "exits non-zero":
                    counter = os.path.join(d, "ps-starts.txt")
                    body = "#!/bin/sh\necho start >> %s\nexit 1\n" % shlex.quote(counter)
                    r = self.run_bounded(code, log, {"VERDICT_HANG_SECONDS": "1"}, shim=("ps", body))
                    starts = 0
                    if os.path.exists(counter):
                        with open(counter, encoding="utf-8") as h: starts = h.read().count("start")
                    self.assertGreaterEqual(starts, 2, "scope: verdict read no process table at the baseline and after silence")
                else:
                    no_ps = os.path.join(d, "no-ps")
                    os.mkdir(no_ps)
                    self.assertIsNone(shutil.which("ps", path=no_ps), "scope: the PATH with no ps still finds a ps")
                    r = self.run_bounded(code, log, {"VERDICT_HANG_SECONDS": "1", "PATH": no_ps})
                self.assertFalse(any(l.startswith("HANG ") for l in r.stdout.splitlines()),
                                 "a ps with no process table stopped a silent child: " + r.stdout)
                with open(log, encoding="utf-8") as h: full = h.read()
                self.assertIn("END-MARK", full, "the silent child was stopped before its end")
                self.assertTrue(r.stdout.startswith("PASS "), r.stdout)

    def test_hang_stop_bad_env_value_says_off_and_the_step_runs(self):
        """A VERDICT_HANG_SECONDS that is no whole number (10m, 1.5) turns the hang stop off and says so once on stderr. The
        step still runs: verdict exits 0 and reads PASS, and no HANG line prints. Control: with the variable unset, the
        stop-off line does not print (decision hang-stop)."""
        code = "print('END-MARK', flush=True)"
        for value in ("10m", "1.5"):
            with self.subTest(VERDICT_HANG_SECONDS=value), tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
                r = self.run_bounded(code, os.path.join(d, "v.log"), {"VERDICT_HANG_SECONDS": value})
                self.assertEqual(r.returncode, 0, "the step ran to its end, so verdict exits 0: " + r.stdout + r.stderr)
                self.assertTrue(r.stdout.startswith("PASS "), r.stdout)
                self.assertFalse(any(l.startswith("HANG ") for l in r.stdout.splitlines()), r.stdout)
                self.assertEqual(r.stderr.count("hang stop is off"), 1, "want one stop-off line on stderr: " + r.stderr)
        with self.subTest(VERDICT_HANG_SECONDS="unset"), tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
            r = self.run_bounded(code, os.path.join(d, "v.log"))
            self.assertTrue(r.stdout.startswith("PASS "), r.stdout)
            self.assertNotIn("hang stop is off", r.stdout + r.stderr, "the stop-off line printed with the variable unset")

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
            with self.subTest(name), tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
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
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
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
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
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
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
            r = run(code, os.path.join(d, "v.log"))
            self.assertEqual(r.returncode, 7, r.stdout)
            first = r.stdout.splitlines()[0] if r.stdout else ""
            self.assertTrue(first.startswith("FAIL ") and " rc=7 " in first, (r.stdout[:300], r.stderr[-300:]))
            self.assertIn("log unreadable", first)
            self.assertNotIn("Traceback", r.stdout + r.stderr)

    def _fail_with_child_bytes(self, expr):
        # The child writes raw bytes itself: its own print() of a non-cp1252 character would fail first.
        # PYTHONUTF8 and PYTHONIOENCODING are removed so verdict meets the machine's default encoding.
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
            script = os.path.join(d, "fx.py")
            with open(script, "w", encoding="ascii") as f:
                f.write("import sys\nsys.stdout.buffer.write(%s)\nsys.stdout.flush()\nsys.exit(7)\n" % expr)
            env = {k: v for k, v in os.environ.items()
                   if k not in ("VERDICT_LOG", "VERDICT_HEARTBEAT", "STALL_WATCH_BEAT", "PYTHONUTF8", "PYTHONIOENCODING")}
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

    # These run bin/verdict.cmd. Only the checks-windows-rest CI job proves them.
    @unittest.skipUnless(os.name == "nt", "bin/verdict.cmd is the Windows launcher: it runs on Windows only (checks-windows-rest)")
    def test_cmd_launcher_pass(self):
        r = run("print('noisy')", launcher=CMD, timeout=60)
        self.assertEqual(r.returncode, 0, (r.stdout[:300], r.stderr[-300:]))
        self.assertTrue(r.stdout.startswith("PASS "), r.stdout)
        self.assertNotIn("noisy", r.stdout)

    @unittest.skipUnless(os.name == "nt", "bin/verdict.cmd is the Windows launcher: it runs on Windows only (checks-windows-rest)")
    def test_cmd_launcher_fail_keeps_rc_and_log(self):
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
            log = os.path.join(d, "v.log")
            r = run("print('FAIL boom')\nraise SystemExit(7)", log, launcher=CMD, timeout=60)
            self.assertEqual(r.returncode, 7, (r.stdout[:300], r.stderr[-300:]))
            first = r.stdout.splitlines()[0]
            self.assertTrue(first.startswith("FAIL ") and " rc=7 " in first, first)
            m = re.search(r"log=(.+)$", first)
            self.assertTrue(m and os.path.exists(m.group(1)), first)
            self.assertEqual(os.path.normcase(m.group(1)), os.path.normcase(log))
            self.assertIn("FAIL boom", open(log).read())


class FullLog(unittest.TestCase):
    """VERDICT_FULL_LOG=1: a FAIL and a HANG print the verdict line first, then the whole log, every line unchanged and in order.
    A wrapped CI step shows only verdict's output, and its full log stays on the runner (decision hang-stop). PASS and SKIP print
    no log. Unset or any other value keeps the excerpt."""
    EARLY_PLAIN ="print('EARLY-PLAIN-MARK')\nfor i in range(35): print(f'ValueError: later {i}')\nraise SystemExit(1)\n"  # no hot word on the first line

    def run_logged(self, code, extra=None):
        """Runs code under verdict with its log in this run's folder. -> (verdict's run, the log's lines)."""
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
            log = os.path.join(d, "v.log")
            r = run(code, log, extra)
            with open(log, encoding="utf-8") as h: full = h.read().splitlines()
        return r, full

    def test_full_log_fail_prints_a_plain_line_more_than_30_before_the_end(self):
        # The excerpt keeps the last 30 hot lines, so the plain first line, 35 hot lines before the end, is dropped without the switch.
        r, _ = self.run_logged(self.EARLY_PLAIN, {"VERDICT_FULL_LOG": "1"})
        self.assertTrue(r.stdout.startswith("FAIL "), r.stdout[:300])
        self.assertIn("EARLY-PLAIN-MARK", r.stdout.splitlines(), "the FAIL output with VERDICT_FULL_LOG=1 drops a plain line 35 hot lines before the end")

    def test_full_log_fail_prints_the_verdict_line_then_the_whole_log_in_order(self):
        code = ("print('EARLY-PLAIN-MARK')\n"
                "print('FAIL: test_one (m.T.test_one)')\n"
                "print('Traceback (most recent call last):')\n"
                "print('  File \"m.py\", line 5, in test_one')\n"
                "for i in range(40): print(f'step {i} done')\n"
                "print('AssertionError: 1 != 2')\n"
                "raise SystemExit(1)\n")
        r, full = self.run_logged(code, {"VERDICT_FULL_LOG": "1"})
        lines = r.stdout.splitlines()
        self.assertTrue(lines and lines[0].startswith("FAIL "), r.stdout[:300])
        self.assertEqual(lines[1:], full, "the FAIL output is not the whole log after its verdict line: %d lines printed, %d in the log"
                         % (len(lines) - 1, len(full)))

    def test_full_log_fail_names_every_case_past_300(self):
        # The excerpt keeps at most 300 names beside the last 30 hot lines, so 400 failing cases lose their first 70 names without the switch.
        r, _ = self.run_logged("for i in range(400): print(f'FAIL: test_case_{i:03d} (m.T.test_case_{i:03d})')\nraise SystemExit(1)\n",
                               {"VERDICT_FULL_LOG": "1"})
        missing = [i for i in range(400) if f"(m.T.test_case_{i:03d})" not in r.stdout]
        self.assertEqual(missing, [], "the FAIL output with VERDICT_FULL_LOG=1 drops %d of 400 failing case names" % len(missing))

    def test_full_log_fail_prints_a_name_line_past_300_chars_unchanged(self):
        # The excerpt cuts a name line at 300 chars. This name has 35 names after it, so it is outside the 30 hot lines that stay whole.
        long_line = "FAIL: test_long_" + "x" * 400 + " LONG-END-MARK"
        code = "print(%r)\nfor i in range(35): print(f'FAIL: test_after_{i:02d}')\nraise SystemExit(1)\n" % long_line
        r, _ = self.run_logged(code, {"VERDICT_FULL_LOG": "1"})
        self.assertIn(long_line, r.stdout.splitlines(), "the FAIL output with VERDICT_FULL_LOG=1 cuts a name line past 300 chars")

    def test_full_log_fail_prints_an_early_line_from_the_first_mib_of_a_2_mib_log(self):
        # The excerpt reads only the last 1 MiB of the run (TAIL), so a line at the start of a 2 MiB log is outside it without the switch.
        code = "print('EARLY-FIRST-MIB-MARK')\nfor i in range(2200): print('x' * 1000)\nprint('FAIL boom')\nraise SystemExit(1)\n"
        r, _ = self.run_logged(code, {"VERDICT_FULL_LOG": "1"})
        self.assertIn("EARLY-FIRST-MIB-MARK", r.stdout.splitlines(), "the FAIL output with VERDICT_FULL_LOG=1 drops a line from the first MiB of a 2 MiB log")

    def test_unset_or_other_switch_values_keep_the_excerpt(self):
        # Control, green on the old code: only VERDICT_FULL_LOG=1 prints the log. Unset, empty, 0 and true keep today's excerpt.
        for value in (None, "", "0", "true"):
            with self.subTest(value=value):
                r, _ = self.run_logged(self.EARLY_PLAIN, None if value is None else {"VERDICT_FULL_LOG": value})
                self.assertNotIn("EARLY-PLAIN-MARK", r.stdout.splitlines(), "VERDICT_FULL_LOG=%r prints the whole log" % value)

    def test_fail_with_no_output_still_leads_with_the_verdict_line(self):
        # Control, green on the old code: the empty log. verdict exits 1 and its FAIL line comes first.
        r, _ = self.run_logged("raise SystemExit(1)\n", {"VERDICT_FULL_LOG": "1"})
        self.assertEqual(r.returncode, 1, r.stdout[:300])
        self.assertTrue(r.stdout.startswith("FAIL "), r.stdout[:300])

    def test_pass_and_skip_print_no_log_with_the_switch(self):
        # Control, green on the old code: PASS and SKIP print one line each, with the switch on.
        cases = (("PASS", "print('NOISY-PASS-MARK')\n"), ("SKIP", "print('NOISY-SKIP-MARK')\nprint('SKIP test_one_case')\n"))
        for word, code in cases:
            with self.subTest(verdict=word):
                r, _ = self.run_logged(code, {"VERDICT_FULL_LOG": "1"})
                self.assertEqual(r.returncode, 0, r.stdout[:300])
                self.assertTrue(r.stdout.startswith(word + " "), r.stdout[:300])
                self.assertEqual(len(r.stdout.splitlines()), 1, "%s prints more than its verdict line with VERDICT_FULL_LOG=1: %r" % (word, r.stdout[:300]))


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

class StdinPassesThrough(unittest.TestCase):
    """A piped stdin reaches the command on every OS: `printf x | verdict cmd` feeds cmd. On Windows only a console
    stdin becomes an empty one, inside hooks/_nowindow.py: a no-window child cannot use an inherited console stdin."""

    def test_a_piped_stdin_reaches_the_command(self):
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
            script = os.path.join(d, "reads.py")
            with open(script, "w") as f:
                f.write("import sys\nsys.exit(0 if sys.stdin.read() == 'piped\\n' else 3)\n")
            r = subprocess.run([sys.executable, V, sys.executable, script], input="piped\n",
                               capture_output=True, text=True, timeout=60,
                               env={k: v for k, v in os.environ.items() if k != "VERDICT_LOG"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(r.stdout.startswith("PASS "), r.stdout)


class Prune(unittest.TestCase):
    def setUp(self):
        self.sb = tempfile.TemporaryDirectory(dir=RUN_FOLDER)
        self.extra = tmp_env(self.sb.name)
        self.folder = log_folder(self.extra)
        os.makedirs(self.folder, exist_ok=True)
    def tearDown(self):
        self.sb.cleanup()
    def go(self, code="raise SystemExit(3)"):
        return run(code, None, self.extra, timeout=60)

    def test_old_log_gone_recent_and_own_stay(self):
        old = plant(self.folder, "verdict-old.log", 8)
        recent = plant(self.folder, "verdict-recent.log", 0.5)
        r = self.go()
        self.assertEqual(r.returncode, 3, r.stdout)
        own = re.search(r"log=(.+)$", r.stdout.splitlines()[0]).group(1)
        self.assertFalse(os.path.exists(old), "8-day-old verdict log must be pruned")
        self.assertTrue(os.path.exists(recent), "a 12-hour-old verdict log must stay")
        self.assertTrue(os.path.exists(own), "the run's own log must stay")
        self.assertEqual(os.path.dirname(os.path.normcase(own)), os.path.normcase(self.folder))

    def test_a_log_over_a_day_old_is_pruned(self):
        day_old = plant(self.folder, "verdict-day-old.log", 2)
        r = self.go()
        self.assertEqual(r.returncode, 3, r.stdout)
        self.assertFalse(os.path.exists(day_old), "a 2-day-old verdict log must be pruned: the limit is one day")

    def test_old_log_in_callers_verdict_log_folder_stays(self):
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as caller:
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
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as out:
            target = plant(out, "target.txt", 30)
            link = os.path.join(self.folder, "verdict-link.log")
            try: os.symlink(target, link)
            except (OSError, NotImplementedError) as e: self.skipTest(f"no symlink here: {e}")
            self.go("print('x')")
            self.assertTrue(os.path.exists(target), "a symlink must never delete what it points at")

    @unittest.skipUnless(os.name == "nt", "junctions are Windows only")
    def test_junction_named_like_a_log_leaves_target(self):
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as out:
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
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
            r = run("print('x')", os.path.join(d, "no-such-dir", "v.log"), timeout=60)
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue(any(l.startswith("FAIL ") for l in r.stdout.splitlines()), (r.stdout, r.stderr[-300:]))

# Skip counting: a run that skipped tests reads SKIP with the count (plan row S8, a skip is counted and shown; test-ci-standard plan).
CHUNK, OVERLAP = 1 << 20, 256  # bin/verdict's chunk and overlap
UT_ONE_SKIP = "Ran 1 test in 0.000s\n\nOK (skipped=1)\n"  # the tail of a real `python3 -m unittest`, one skipped test
XCT_SKIPPED = ("Executed 12 tests, with 3 tests skipped and 0 failures (0 unexpected) in 1.2 (1.3) seconds\n"
               "** TEST SUCCEEDED **\n")  # xcodebuild's summary form; no swift here, so it is not captured
PYTEST_OUT = "=" * 25 + " 2 passed, 1 skipped in 0.01s " + "=" * 25 + "\n"  # pytest's summary, captured here
# pytest's summary with --color=yes, captured here: each count sits between SGR codes, not word edges
PYTEST_COLOUR = ("\x1b[32m========================= \x1b[32m\x1b[1m1 passed\x1b[0m, \x1b[33m2 skipped\x1b[0m"
                 "\x1b[32m in 0.01s\x1b[0m\x1b[32m =========================\x1b[0m\n")
# XCTest's output for nested suites, in its own shape: one Executed line per class, per bundle, and for All tests
XCT_NESTED = (
    "Test Suite 'All tests' started at 2026-11-02 00:00:00.000.\n"
    "Test Suite 'MyTests.xctest' started at 2026-11-02 00:00:00.001.\n"
    "Test Suite 'FooTests' started at 2026-11-02 00:00:00.002.\n"
    "Test Case '-[FooTests testA]' started.\n"
    "Test Case '-[FooTests testA]' passed (0.001 seconds).\n"
    "Test Case '-[FooTests testB]' skipped (0.000 seconds).\n"
    "Test Suite 'FooTests' passed at 2026-11-02 00:00:00.004.\n"
    "\t Executed 2 tests, with 1 test skipped and 0 failures (0 unexpected) in 0.001 (0.003) seconds\n"
    "Test Suite 'BarTests' started at 2026-11-02 00:00:00.005.\n"
    "Test Case '-[BarTests testC]' skipped (0.000 seconds).\n"
    "Test Suite 'BarTests' passed at 2026-11-02 00:00:00.006.\n"
    "\t Executed 1 test, with 1 test skipped and 0 failures (0 unexpected) in 0.000 (0.001) seconds\n"
    "Test Suite 'MyTests.xctest' passed at 2026-11-02 00:00:00.007.\n"
    "\t Executed 3 tests, with 2 tests skipped and 0 failures (0 unexpected) in 0.001 (0.006) seconds\n"
    "Test Suite 'All tests' passed at 2026-11-02 00:00:00.008.\n"
    "\t Executed 3 tests, with 2 tests skipped and 0 failures (0 unexpected) in 0.001 (0.007) seconds\n")
# Real `node --test` output of one skipped test (node 22, captured here): TAP first, then the spec reporter.
NODE_TAP = ("TAP version 13\n# Subtest: shelved\nok 1 - shelved # SKIP\n  ---\n  duration_ms: 1.069052\n  type: 'test'\n  ...\n"
            "1..1\n# tests 1\n# suites 0\n# pass 0\n# fail 0\n# cancelled 0\n# skipped 1\n# todo 0\n# duration_ms 133.734624\n")
NODE_SPEC = ("﹣ shelved (1.003516ms) # SKIP\nℹ tests 1\nℹ suites 0\nℹ pass 0\nℹ fail 0\n"
             "ℹ cancelled 0\nℹ skipped 1\nℹ todo 0\nℹ duration_ms 102.939863\n")
HOOKS = os.path.join(HERE, "..", "hooks")


def skipped_count(line):
    """N from the first `N skipped` on a verdict line, or None."""
    m = re.search(r"\b(\d+) skipped\b", line)
    return int(m.group(1)) if m else None


def printing(text, rc=0, raw=False):
    """Child code that writes `text` byte for byte, then exits `rc`. `raw` writes UTF-8 bytes to the binary stdout: a text
    stream turns each \\n into \\r\\n on Windows, so only raw keeps a CRLF line end as it is on every platform."""
    if raw:
        return "import sys\nsys.stdout.buffer.write(%r)\nsys.stdout.flush()\nsys.exit(%d)\n" % (text.encode("utf-8"), rc)
    return "import sys\nsys.stdout.write(%s)\nsys.exit(%d)\n" % (ascii(text), rc)  # ascii: the script file stays ASCII on any locale


def unittest_run(skips, fails=0, oks=1, module_skip=False):
    """Child code: a real unittest run of `oks` passing, `skips` skipped and `fails` failing tests. Its output goes to stderr.
    `module_skip` skips the whole module in setUpModule, so the run counts no test and one skip."""
    body = ["import sys, unittest", "class T(unittest.TestCase):", "    pass"]
    for i in range(oks):
        body += ["    def test_ok%d(self):" % i, "        pass"]
    for i in range(skips):
        body += ["    def test_skip_%d(self):" % i, "        self.skipTest('shelved')"]
    for i in range(fails):
        body += ["    def test_fail_%d(self):" % i, "        self.fail('boom')"]
    if module_skip:
        body += ["def setUpModule():", "    raise unittest.SkipTest('shelved')"]
    body += ["r = unittest.main(argv=['x'], exit=False)", "sys.exit(0 if r.result.wasSuccessful() else 1)"]
    return "\n".join(body) + "\n"


def two_suites_run():
    """Child code: two unittest runs in one process, 3 skipped tests and then 1, so two summaries reach the log."""
    body = ["import sys, unittest", "class A(unittest.TestCase):"]
    body += ["    def test_a%d(self):\n        self.skipTest('shelved')" % i for i in range(3)]
    body += ["class B(unittest.TestCase):", "    def test_b(self):", "        self.skipTest('shelved')"]
    body += ["rs = [unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(c)) for c in (A, B)]",
             "sys.exit(0 if all(r.wasSuccessful() for r in rs) else 1)"]
    return "\n".join(body) + "\n"


def case_runner_run(kinds):
    """Child code: hooks/case_runner_test.run_cases over one case per kind, "ok" or "skip", so its own output reaches the log."""
    body = ["import sys", "sys.path.insert(0, %r)" % HOOKS, "import case_runner_test as cr"]
    for i, kind in enumerate(kinds):
        body += ["def case_%d():" % i, '    """case %d"""' % i]
        body += ["    raise cr.Skip('no display here')" if kind == "skip" else "    return []"]
    body += ["sys.exit(cr.run_cases([%s]))" % ", ".join("case_%d" % i for i in range(len(kinds)))]
    return "\n".join(body) + "\n"


class Skips(unittest.TestCase):
    """A skip is counted and shown, never read as a pass (plan row S8, test-ci-standard plan)."""

    def check(self, code, extra=None, timeout=120):
        """Run one fixture with its log in this run's folder, never the system temp dir."""
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
            return run(code, os.path.join(d, "v.log"), extra, timeout=timeout)

    def assert_skip(self, r, count):
        first = r.stdout.splitlines()[0] if r.stdout.strip() else ""
        self.assertEqual(r.returncode, 0, (r.stdout[:300], r.stderr[-300:]))
        self.assertEqual(first.split()[:1], ["SKIP"], r.stdout[:300])
        self.assertEqual(skipped_count(first), count, first)

    def assert_fail(self, r, rc, reason):
        first = r.stdout.splitlines()[0] if r.stdout.strip() else ""
        self.assertEqual(r.returncode, rc, (r.stdout[:300], r.stderr[-300:]))
        self.assertEqual(first.split()[:1], ["FAIL"], r.stdout[:300])
        self.assertIn(reason, first)

    def assert_pass(self, r):
        self.assertEqual(r.returncode, 0, (r.stdout[:300], r.stderr[-300:]))
        self.assertEqual(r.stdout.split()[:1], ["PASS"], r.stdout[:300])

    def test_every_test_skipped_reads_skip_with_its_count(self):
        self.assert_skip(self.check(unittest_run(skips=3)), 3)

    def test_summaries_sum_over_the_whole_run(self):
        self.assert_skip(self.check(two_suites_run()), 4)

    def test_xctest_skipped_tests_are_counted(self):
        self.assert_skip(self.check(printing(XCT_SKIPPED)), 3)

    def test_pytest_summary_skips_are_counted(self):
        self.assert_skip(self.check(printing(PYTEST_OUT)), 1)

    def test_case_runner_summary_skips_are_counted(self):
        self.assert_skip(self.check(case_runner_run(["ok", "skip", "skip", "ok", "ok"])), 2)

    def test_marker_lines_with_no_summary_are_counted(self):
        self.assert_skip(self.check(printing("PASS first\nSKIP second: no keychain\nSKIPPED third\nPASS fourth\n")), 2)

    def test_colon_marker_lines_with_no_summary_are_counted(self):
        """`SKIP: <case>` is a skip line, as `SKIP <case>` is. A suite that prints only colon lines reads SKIP, not PASS."""
        self.assert_skip(self.check(printing("PASS first\nSKIP: second case\nSKIP: third case\nPASS fourth\n")), 2)

    def test_colon_summary_line_is_not_counted_on_top_of_its_cases(self):
        """A summary `SKIP: N check(s)` after N colon case lines adds no skip: the run skipped N, not N + 1."""
        self.assert_skip(self.check(printing("SKIP: a: no display\nSKIP: b: no display\nSKIP: 2 check(s) not run, none failed\n")), 2)

    def test_space_marker_lines_and_colon_summary_count_once(self):
        """The shape a suite prints as one run: `SKIP <case> :: detail` lines and a `SKIP: N check(s)` summary (the
        send-message suite). Green on the old code: it pins that the summary is not counted again."""
        self.assert_skip(self.check(printing("SKIP a :: x\nSKIP b\nSKIP: 2 check(s) not run, none failed\n")), 2)

    def test_colon_skip_line_with_a_number_counts_as_one(self):
        """`SKIP: <case>` counts even when the case name starts with a digit, as `SKIP: 404 page not built` does."""
        self.assert_skip(self.check(printing("PASS first\nSKIP: 404 page not built\nPASS second\n")), 1)

    def test_colon_summary_with_a_count_adds_nothing(self):
        """A summary `SKIP: 3 checks` after three colon case lines adds no skip: the run skipped three, not four."""
        self.assert_skip(self.check(printing("SKIP: a: no display\nSKIP: b: no display\nSKIP: c: no display\nSKIP: 3 checks\n")), 3)

    def test_colon_skip_line_naming_a_checkout_count_counts_as_one(self):
        """`SKIP: 12 checkout cases not run` is one skip: a case line, not a summary, though it starts with a count."""
        self.assert_skip(self.check(printing("PASS first\nSKIP: 12 checkout cases not run\nPASS second\n")), 1)

    def test_colon_skip_line_naming_checksums_counts_as_one(self):
        """`SKIP: 7 checksums unavailable` is one skip: "checksums" starts with the word "check", and it is a case line."""
        self.assert_skip(self.check(printing("PASS first\nSKIP: 7 checksums unavailable\nPASS second\n")), 1)

    def test_a_summary_in_the_chunk_overlap_counts_once(self):
        """bin/verdict reads 1 MiB chunks that overlap by 256 bytes, so a summary in the overlap is read twice."""
        ok_at = UT_ONE_SKIP.index("OK (skipped=1)")
        for at in (CHUNK - OVERLAP - 10, CHUNK - OVERLAP - 1, CHUNK - OVERLAP, CHUNK - OVERLAP + 1,
                   CHUNK - 128, CHUNK - 16, CHUNK - 10, CHUNK - 7, CHUNK - 1):  # the last three straddle CHUNK
            with self.subTest(summary_starts_at=at):
                code = ("import sys\n"
                        "out = sys.stdout.buffer\n"
                        "out.write(b'x' * %d + b'\\n')\n" % (at - ok_at - 1)
                        + "out.write(%r.encode())\n" % UT_ONE_SKIP
                        + "row = b'y' * 1023 + b'\\n'\n"
                        + "for _ in range(1536):\n"
                        + "    out.write(row)\n"
                        + "out.flush()\n")
                self.assert_skip(self.check(code), 1)

    def test_a_summary_with_zero_skipped_stays_pass(self):
        self.assert_pass(self.check(case_runner_run(["ok", "ok"])))

    def test_a_skip_word_inside_a_line_is_no_marker(self):
        self.assert_pass(self.check(printing("checking SKIP handling\nthe SKIPPED flag is set\nSKIPS the step\n")))

    def test_a_nonzero_exit_with_skips_is_fail_not_skip(self):
        self.assert_fail(self.check(unittest_run(skips=2, fails=1)), 1, " rc=1 ")

    def test_a_runner_failure_marker_beats_skip(self):
        self.assert_fail(self.check(printing(XCT_SKIPPED + "** TEST FAILED **\n")), 1, "runner failure marker")

    def test_no_tests_ran_beats_skip(self):
        self.assert_fail(self.check(printing(T.XCT0 + "\nRan 2 tests in 0.000s\n\nOK (skipped=2)\n")), 1, "no tests ran")


    def test_pytest_colour_summary_skips_are_counted(self):
        """pytest with --color=yes puts each count between SGR codes, so no word edge sits before its number."""
        self.assert_skip(self.check(printing(PYTEST_COLOUR)), 2)

    def test_a_coloured_marker_line_is_counted(self):
        self.assert_skip(self.check(printing("\x1b[33mSKIP\x1b[0m a: no display\n")), 1)

    def test_xctest_nested_summaries_take_the_max_not_the_sum(self):
        """XCTest prints an Executed line per class, per bundle and for All tests. They nest, so the max is the count."""
        self.assert_skip(self.check(printing(XCT_NESTED)), 2)

    def test_marker_line_and_a_zero_summary_take_the_max(self):
        """The count is the max of the summary sum and the marker-line count, so a 0 summary does not hide a SKIP line."""
        self.assert_skip(self.check(printing("SKIP a: no display\n0 skipped\n")), 1)


    def test_node_tap_summary_skips_are_counted(self):
        self.assert_skip(self.check(printing(NODE_TAP)), 1)

    def test_node_spec_summary_skips_are_counted(self):
        self.assert_skip(self.check(printing(NODE_SPEC), UTF8), 1)

    def test_an_sgr_code_between_count_and_word_is_read(self):
        self.assert_skip(self.check(printing("\x1b[1m2\x1b[22m skipped\n")), 2)

    def test_a_huge_count_is_not_a_log_unreadable_fail(self):
        """A 5000-digit count is past Python's int digit limit. verdict must still read the run as SKIP, never FAIL log unreadable."""
        r = self.check(printing("9" * 5000 + " skipped\n"))
        first = r.stdout.splitlines()[0] if r.stdout.strip() else ""
        self.assertEqual(r.returncode, 0, (r.stdout[:300], r.stderr[-300:]))
        self.assertNotIn("log unreadable", first, r.stdout[:300])
        self.assertEqual(first.split()[:1], ["SKIP"], r.stdout[:300])


def shim_script(*lines):
    """A POSIX shell fake: it prints the token SHIM-RAN, then each line, and exits 0."""
    return "#!/bin/sh\necho SHIM-RAN\n" + "".join("echo '%s'\n" % s for s in lines) + "exit 0\n"

SHIM_SKIP = "the fake is a POSIX shell script; verdict names a Windows .cmd shim differently"

class NoTestCount(unittest.TestCase):
    """A run with no test count is unknown, so it is never PASS (verification-report-unknown-reads).
    FAIL for a success marker with no count, and for a test command by argv with no count. FAIL for a
    unittest run that counts zero tests (`Ran 0 tests`), with LF or CRLF line ends, run directly or through
    sim-test. SKIP for a module skipped in setUpModule, with its count. PASS for a run that is no counted test,
    for a zero count beside any other count, and for a counted run wherever its count sits."""
    BUILD_OK = "** BUILD SUCCEEDED **"
    ST_PASS = "Test run with 3 tests passed after 0.001 seconds."  # Swift Testing's summary, no XCTest line
    XCT_12 = "Executed 12 tests, with 0 failures (0 unexpected) in 1.2 (1.3) seconds"
    assert_pass = Skips.assert_pass  # one home for the PASS check
    assert_fail = Skips.assert_fail  # one home for the FAIL check
    assert_skip = Skips.assert_skip  # one home for the SKIP check

    def run_case(self, code=None, argv=None, shim=None, newline=None):
        """Run one case with its log in this run's folder. Returns the run and the log's text. `newline=""` keeps each CRLF
        as it is: the default text read folds CR LF to LF, so a CRLF case must pass it to see its own line ends."""
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
            log = os.path.join(d, "v.log")
            r = run(code, log, argv=argv, shim=shim, timeout=120)
            with open(log, encoding="utf-8", errors="replace", newline=newline) as f: full = f.read()
        return r, full

    def assert_no_count_fail(self, r):
        first = r.stdout.splitlines()[0] if r.stdout.strip() else ""
        self.assertEqual(r.returncode, 1, (r.stdout[:300], r.stderr[-300:]))
        self.assertTrue(first.startswith("FAIL "), r.stdout[:300])
        self.assertIn("no test count", first, first)

    def test_success_marker_with_no_count_is_fail(self):
        """Case 1: exit 0, a success marker, and no Executed line or Swift Testing line."""
        for marker in ("** TEST SUCCEEDED **", "** TEST EXECUTE SUCCEEDED **"):
            with self.subTest(marker=marker):
                r, full = self.run_case(code=printing("Test Suite All tests started\n%s\n" % marker))
                self.assert_no_count_fail(r)

    def test_success_marker_in_full_size_output_with_no_count_is_fail(self):
        """The marker is early in 2 MiB of output with no count: the whole run is read, and still no count."""
        code = ("import sys\n"
                "sys.stdout.write('** TEST SUCCEEDED **\\n')\n"
                "line = 'x' * 1023 + '\\n'\n"
                "for _ in range(2048):\n"
                "    sys.stdout.write(line)\n")
        r, full = self.run_case(code=code)
        self.assert_no_count_fail(r)

    @unittest.skipIf(os.name == "nt", SHIM_SKIP)
    def test_xcodebuild_test_by_argv_with_no_count_is_fail(self):
        """Case 2: argv[0] is xcodebuild or xcodebuild.exe, and test or test-without-building is an argument."""
        commands = (
            ["xcodebuild", "test", "-scheme", "App"],
            ["xcodebuild", "test-without-building", "-scheme", "App"],
            ["xcodebuild", "-scheme", "App", "test"],
            ["xcodebuild.exe", "test", "-scheme", "App"],
        )
        for argv in commands:
            with self.subTest(argv=" ".join(argv)):
                r, full = self.run_case(argv=argv, shim=(argv[0], shim_script("Running tests")))
                self.assertIn("SHIM-RAN", full, "the fake never ran, so this run proves nothing")
                self.assert_no_count_fail(r)

    @unittest.skipIf(os.name == "nt", SHIM_SKIP)
    def test_swift_test_by_argv_with_no_count_is_fail(self):
        """Case 2: argv[0] is swift and argv[1] is test."""
        r, full = self.run_case(argv=["swift", "test"], shim=("swift", shim_script("Running tests")))
        self.assertIn("SHIM-RAN", full, "the fake never ran, so this run proves nothing")
        self.assert_no_count_fail(r)

    def test_build_marker_and_plain_runs_stay_pass(self):
        """Case 3: a build-for-testing marker, a Swift Testing pass line and a command with no output are PASS."""
        cases = {
            "TEST BUILD SUCCEEDED, no tests expected": printing("** TEST BUILD SUCCEEDED **\n"),
            "Swift Testing pass line alone": printing(self.ST_PASS + "\n"),
            "plain command, no output": "pass\n",
        }
        for name, code in cases.items():
            with self.subTest(name):
                r, full = self.run_case(code=code)
                self.assert_pass(r)

    @unittest.skipIf(os.name == "nt", SHIM_SKIP)
    def test_xcodebuild_build_and_swift_build_by_argv_stay_pass(self):
        """Case 3: a build is not a test run, so it needs no count. Each fake prints its own success line."""
        for name, body in (("xcodebuild", shim_script(self.BUILD_OK)), ("swift", shim_script("Build complete!"))):
            with self.subTest(name):
                r, full = self.run_case(argv=[name, "build"], shim=(name, body))
                self.assertIn("SHIM-RAN", full, "the fake never ran, so this run proves nothing")
                self.assert_pass(r)

    @unittest.skipIf(os.name == "nt", SHIM_SKIP)
    def test_xcodebuild_test_by_argv_with_count_stays_pass(self):
        """Case 3: the argv route alone never fails a run; a count that is read passes it."""
        r, full = self.run_case(argv=["xcodebuild", "test", "-scheme", "App"],
                                shim=("xcodebuild", shim_script(self.XCT_12, "** TEST SUCCEEDED **")))
        self.assertIn("SHIM-RAN", full, "the fake never ran, so this run proves nothing")
        self.assert_pass(r)

    def test_count_more_than_1_mib_before_the_marker_stays_pass(self):
        """Case 3: the count may sit anywhere in the run. Here it is 2 MiB before the marker, past any tail read."""
        code = ("import sys\n"
                "sys.stdout.write(%s + '\\n')\n"
                "line = 'x' * 1023 + '\\n'\n"
                "for _ in range(2048):\n"
                "    sys.stdout.write(line)\n"
                "sys.stdout.write('** TEST SUCCEEDED **\\n')\n") % ascii(self.XCT_12)
        r, full = self.run_case(code=code)
        self.assert_pass(r)

    def test_echoed_marker_inside_a_line_with_no_count_is_pass(self):
        """Case 1, echoed marker: a grep hit or a source line that holds the marker mid-line is not the runner's
        marker, so the run is no test run and needs no count."""
        for line in ("bin/verdict:114:    if b\"** TEST SUCCEEDED **\" in buf",
                     "foo: ** TEST SUCCEEDED **",
                     "log.txt:3:** TEST EXECUTE SUCCEEDED **"):
            with self.subTest(line=line):
                r, full = self.run_case(code=printing(line + "\n"))
                self.assertIn(line, full, "the echoed line never reached the log")
                self.assert_pass(r)

    def test_marker_at_line_start_after_space_or_colour_with_no_count_is_fail(self):
        """Case 1 keeps its FAIL: a marker that starts a line, after spaces, a tab or a colour code, is the runner's marker."""
        for line in ("  ** TEST SUCCEEDED **", "\t** TEST EXECUTE SUCCEEDED **", "\x1b[1m** TEST SUCCEEDED **\x1b[0m"):
            with self.subTest(line=ascii(line)):
                r, full = self.run_case(code=printing(line + "\n"))
                self.assert_no_count_fail(r)

    @unittest.skipIf(os.name == "nt", SHIM_SKIP)
    def test_swift_test_info_flags_by_argv_with_no_count_are_pass(self):
        """Case 2: swift test with an info flag runs no tests, so it needs no count and reads PASS."""
        for flag in ("--list-tests", "-l", "--help", "-h", "--show-codecov-path", "--show-bin-path"):
            with self.subTest(flag=flag):
                r, full = self.run_case(argv=["swift", "test", flag], shim=("swift", shim_script("AppTests.testFoo")))
                self.assertIn("SHIM-RAN", full, "the fake never ran, so this run proves nothing")
                self.assert_pass(r)

    def test_unittest_zero_count_on_exit0_is_fail_no_tests_ran(self):
        """A real unittest run of no tests prints `Ran 0 tests` and exits 0. The count is read, so the run is no pass."""
        r, full = self.run_case(code=unittest_run(skips=0, oks=0))
        self.assertIn("Ran 0 tests", full, "the unittest run never printed its count, so this run proves nothing")
        self.assert_fail(r, 1, "no tests ran")

    @unittest.skipIf(os.name == "nt", SHIM_SKIP)
    def test_unittest_zero_count_through_sim_test_is_fail_no_tests_ran(self):
        """sim-test --hold -- CMD passes its child's output on, so a zero count reads FAIL under argv sim-test too."""
        shim = ("sim-test", shim_script("Ran 0 tests in 0.000s", "", "NO TESTS RAN"))
        r, full = self.run_case(argv=["sim-test", "--hold", "--", "python3", "-m", "unittest"], shim=shim)
        self.assertIn("SHIM-RAN", full, "the fake never ran, so this run proves nothing")
        self.assert_fail(r, 1, "no tests ran")

    def test_unittest_zero_count_after_one_mib_of_output_is_fail_no_tests_ran(self):
        """Full size: the zero count sits past the first 1 MiB chunk, so the whole run is read for it."""
        code = ("import sys\n"
                "line = 'x' * 1023 + '\\n'\n"
                "for _ in range(1100):\n"
                "    sys.stdout.write(line)\n"
                "sys.stdout.write('Ran 0 tests in 0.000s\\n\\nNO TESTS RAN\\n')\n")
        r, full = self.run_case(code=code)
        self.assertIn("Ran 0 tests", full, "the zero count never reached the log, so this run proves nothing")
        self.assert_fail(r, 1, "no tests ran")

    def test_unittest_five_tests_ok_stays_pass(self):
        """Control: a real unittest run of five passing tests counts them and reads PASS."""
        r, full = self.run_case(code=unittest_run(skips=0, oks=5))
        self.assertIn("Ran 5 tests", full, "the unittest run never printed its count, so this run proves nothing")
        self.assert_pass(r)

    @unittest.skipIf(os.name == "nt", SHIM_SKIP)
    def test_unittest_five_tests_ok_through_sim_test_stays_pass(self):
        """Control: the same five-test output through sim-test reads PASS."""
        shim = ("sim-test", shim_script("Ran 5 tests in 0.000s", "", "OK"))
        r, full = self.run_case(argv=["sim-test", "--hold", "--", "python3", "-m", "unittest"], shim=shim)
        self.assertIn("SHIM-RAN", full, "the fake never ran, so this run proves nothing")
        self.assert_pass(r)

    def test_zero_count_quoted_inside_a_line_stays_pass(self):
        """Control: `Ran 0 tests` quoted inside a line of other text is no count, as an echoed success marker is no marker."""
        r, full = self.run_case(code=printing("checked the old log: Ran 0 tests in 0.000s\n"))
        self.assertIn("Ran 0 tests", full, "the quoted text never reached the log, so this run proves nothing")
        self.assert_pass(r)

    def test_module_skipped_in_setup_reads_skip_with_its_count(self):
        """A module whose setUpModule skips runs no test and counts one skip. It reads SKIP 1, not FAIL no tests ran."""
        r, full = self.run_case(code=unittest_run(skips=0, oks=1, module_skip=True))
        self.assertRegex(full, r"(?m)^Ran 0 tests in\b", "the unittest run never printed its zero count, so this run proves nothing")
        self.assertIn("OK (skipped=1)", full, "the module skip never reached the log, so this run proves nothing")
        self.assert_skip(r, 1)

    def test_pytest_log_with_a_line_start_ran_zero_is_pass(self):
        """A passing pytest log that holds a line-start `Ran 0 tests in` and no unittest OK or FAILED line is no unittest run: PASS."""
        lines = ["=" * 25 + " test session starts " + "=" * 25, "collected 3 items",
                 "Ran 0 tests in 0.000s", "=" * 25 + " 3 passed in 0.01s " + "=" * 25]
        r, full = self.run_case(code=printing("\n".join(lines) + "\n"))
        self.assertRegex(full, r"(?m)^Ran 0 tests in\b", "the line-start zero count never reached the log, so this run proves nothing")
        self.assertNotRegex(full, r"(?m)^(OK|FAILED)\b", "a unittest verdict line would make this a unittest run, so the case proves nothing")
        self.assert_pass(r)

    def test_zero_count_beside_an_xctest_count_stays_pass(self):
        """Control: `Ran 0 tests` beside an XCTest `Executed 12 tests` line reads PASS, since any other count beats a unittest zero."""
        r, full = self.run_case(code=printing(self.XCT_12 + "\nRan 0 tests in 0.000s\n\nNO TESTS RAN\n"))
        self.assertRegex(full, r"(?m)^Ran 0 tests in\b", "the unittest zero count never reached the log, so this run proves nothing")
        self.assertIn("Executed 12 tests", full, "the XCTest count never reached the log, so this run proves nothing")
        self.assert_pass(r)

    def test_zero_count_beside_a_unittest_count_of_five_stays_pass(self):
        """Control: a unittest run of no tests beside one of five reads PASS, since a zero count loses to any other count."""
        r, full = self.run_case(code=printing("Ran 0 tests in 0.000s\n\nNO TESTS RAN\n" + "Ran 5 tests in 0.001s\n\nOK\n"))
        self.assertRegex(full, r"(?m)^Ran 0 tests in\b", "the zero count never reached the log, so this run proves nothing")
        self.assertRegex(full, r"(?m)^Ran 5 tests in\b", "the count of five never reached the log, so this run proves nothing")
        self.assert_pass(r)

    def test_crlf_unittest_zero_count_is_fail_no_tests_ran(self):
        """A zero count whose lines end in CRLF, as a Windows log holds it. The result line sits behind a CRLF blank
        line, which the summary match did not take, so the run read PASS."""
        log_text = "Ran 0 tests in 0.000s\r\n\r\nNO TESTS RAN\r\n"
        r, full = self.run_case(code=printing(log_text, raw=True), newline="")
        self.assertIn(log_text, full, "the CRLF zero count never reached the log, so this run proves nothing")
        self.assert_fail(r, 1, "no tests ran")

    def test_crlf_module_skip_reads_skip_with_its_count(self):
        """Control: a CRLF module skipped in setUpModule (`Ran 0 tests`, then `OK (skipped=1)`) reads SKIP 1, so the CRLF
        fix keeps a skip a skip and never reads it as a zero count."""
        log_text = "Ran 0 tests in 0.000s\r\n\r\nOK (skipped=1)\r\n"
        r, full = self.run_case(code=printing(log_text, raw=True), newline="")
        self.assertIn(log_text, full, "the CRLF module skip never reached the log, so this run proves nothing")
        self.assert_skip(r, 1)


# A cut run: pytest output that stops before its summary. The rule is in CutStream's docstring.
PYTEST_START = "=" * 29 + " test session starts " + "=" * 30 + "\n"  # pytest's session header, captured here
COLOURED_START = "\x1b[32m" + "=" * 29 + " \x1b[1mtest session starts\x1b[0m " + "\x1b[32m" + "=" * 30 + "\x1b[0m\n"  # the same header with --color=yes
PYTEST_ALL_PASS = "=" * 30 + " 3 passed in 0.02s " + "=" * 30 + "\n"  # a summary with no skip; PYTEST_OUT reads SKIP
PROGRESS = "tests/test_big.py " + "." * 1000 + "\n"  # one progress line, 1,019 bytes
CUT_LINE = r"^FAIL .* rc=1[^(]*\bcut\b"  # the note sits between rc=1 and the timing
QUIET_SUMMARY = "3 passed in 0.1s\n"  # the summary `pytest -q` prints: no bars
COLLECT_ITEMS = "collected 3 items\n\n<Module tests/test_big.py>\n  <Function test_one>\n"  # what --collect-only prints after its header
COLLECT_IDS = "tests/test_big.py::test_one\ntests/test_big.py::test_two\ntests/test_big.py::test_three\n"  # -q --collect-only lists node ids
COLLECT_BARS = "=" * 30 + " 3 tests collected in 0.01s " + "=" * 30 + "\n"  # --collect-only's summary, in bars
COLLECT_QUIET = "3 tests collected in 0.01s\n"  # the same summary with -q: no bars
NO_TESTS_BARS = "=" * 30 + " no tests ran in 0.01s " + "=" * 30 + "\n"  # the summary of a run that collected nothing, in bars
NO_TESTS_QUIET = "no tests ran in 0.01s\n"  # the same summary with -q: no bars
FILTERED_BARS = "=" * 30 + " 3/103 tests collected (100 deselected) in 0.09s " + "=" * 30 + "\n"  # --collect-only under -k: a filtered count, in bars
FILTERED_QUIET = "3/103 tests collected (100 deselected) in 0.09s\n"  # the same summary with -q: no bars
QQ_LINE = "..." + " " * 70 + "[100%]\n"  # pytest 9.2's -qq output for three passing tests: progress and the percent, no summary line (80 bytes)
QQ_FULL = ("." * 70 + " [ 50%]\n") * 14000 + QQ_LINE  # over one chunk of progress lines, ending in the same [100%] line
QQ_CUT = "..." + " " * 70 + "[ 30%]\n"  # a -qq run cut at 30 percent: progress with no [100%] line
SGR_DOT = "\x1b[32m.\x1b[0m"  # one green progress char, as --color=yes writes it (pytest 9.2)
QQ_COLOUR = SGR_DOT * 3 + "\x1b[32m" + " " * 70 + "[100%]\x1b[0m\n"  # pytest 9.2's -qq --color=yes for three passing tests, captured: SGR between the chars
QQ_COLOUR_FULL = ("\x1b[32m" + "." * 70 + "\x1b[0m [ 50%]\n") * 13000 + QQ_COLOUR  # over one chunk; one SGR pair per line, not per char
QQ_COLOUR_CUT = "\x1b[32m..\x1b[0m\x1b[32m" + " " * 70 + "[ 30%]\x1b[0m\n"  # the coloured run cut at 30 percent, no [100%] line
QQ_WIDE = "..." + " " * 190 + "[100%]\n"  # pytest 9.2's -qq at COLUMNS=200 for three passing tests, captured: 199 characters, 190 spaces before [100%]
QQ_WIDE_FULL = ("." * 70 + " [ 50%]\n") * 14000 + QQ_WIDE  # over one chunk
QQ_WIDE_CUT = "..." + " " * 190 + "[ 30%]\n"  # the padded line cut at 30 percent
QQ_SUB = "..u" + " " * 70 + "[100%]\n"  # a subtest char u (subtests.py: the SUBPASSED and SUBFAILED progress char) in the last line; synthetic, no captured pytest 9.2 run holds a u on an rc-0 run
QQ_SUB_FULL = ("." * 70 + " [ 50%]\n") * 14000 + QQ_SUB  # over one chunk, ending in the u line
QQ_SUB_CUT = "..u" + " " * 70 + "[ 30%]\n"  # the subtest line cut at 30 percent
QQ_CO = "test_plain.py: 3\n\n"  # pytest 9.2's -qq --co for a three-test module, captured: per-file counts, no progress, no summary line
QQ_CO_FULL = "".join("test_%05d.py: 1\n" % i for i in range(65000))  # over one chunk, one count line per file
HANG_GUARD = 20  # seconds before a verdict counts as hung; a linear scan of one 1 MiB line finishes far below it


def straddling_body():
    """A complete run whose summary starts 40 bytes before the chunk edge, so the summary crosses that edge. Returns (body, offset)."""
    offset = CHUNK - 40
    n = (offset - len(PYTEST_START) - 1) // len(PROGRESS)
    pad = offset - len(PYTEST_START) - n * len(PROGRESS)  # 1 to len(PROGRESS) bytes: the dots that end the filler
    return PYTEST_START + PROGRESS * n + "." * (pad - 1) + "\n" + PYTEST_ALL_PASS, offset


class CutStream(unittest.TestCase):
    """A pytest run that exits 0 and stops before its summary reads FAIL, with `cut` in the note.
    Rule: the argv is pytest's, as typed: `pytest`, `py.test`, `python -m pytest`, `python -mpytest`, `env pytest`,
    `uv run pytest`, or `bash -c "python -m pytest ..."`. The argv has `-q` (not `-qq`) or the output has pytest's header
    (`=` bars around `test session starts` at a line start), and no line starts with pytest's summary: `=` bars around
    ` in <N>s`, or the bare `<counts> in <N>s` that `-q` prints. A `--collect-only` run ends `N tests collected in <N>s`,
    an empty run ends `no tests ran in <N>s`, and a filtered one ends `N/M tests collected (K deselected) in <N>s`. All
    of these count as summaries. A `-qq` run prints no summary: it reads PASS when its last progress line ends `[100%]`,
    and is cut otherwise. A subtest char `u` in that line and any padding before `[100%]` do not change that. A
    `-qq --collect-only` run prints per-file counts and no summary: it reads PASS when it prints some, and is cut when it
    prints none. Where the header sits does not matter. Colour codes are ignored. A `bash -c` line runs pytest when a
    newline or `do` starts its command, and a `#` that does not start a word is no comment. A quote in heredoc text is
    text. A pytest run with neither `-q` nor a header is never cut. A run that is not pytest is never cut, even
    when it prints pytest's header or progress lines, so `print('noisy')` reads PASS. A header quoted mid-line is no
    header. Other runners are not covered."""
    check = Skips.check  # one home for a fixture's run and its timeout
    assert_pass = Skips.assert_pass
    assert_skip = Skips.assert_skip
    assert_fail = Skips.assert_fail

    def pytest_case(self, text, args=(), form="module", timeout=120, hard=False, env=None, bash_line=None):
        """Run `text` as the output of a pytest run, and return the run. The fake pytest writes `text`, exits 0 and
        leaves a sentinel file, so a case knows the fake ran before it reads the verdict. `hard` ends the fake with
        os._exit(0) after a flush, as a test that exits mid-run does. Each form is the argv as verdict receives it:
        "module" runs `python -m pytest` and "glued" runs `python -mpytest`, through a fake package on PYTHONPATH;
        "bash" runs `bash -c "python -m pytest <args>"` through the same package; "bare" runs `pytest` and "env" runs
        `env pytest` through a fake on PATH; "uv" runs `uv run pytest` through a fake in a throwaway venv's bin.
        `bash_line` runs that line as `bash -c`, with the fake on PATH, so the line's own words decide what runs; the
        line names pytest and its args as a user types them. `env` adds variables to the run's environment."""
        if form in ("bare", "env", "uv") and os.name == "nt": raise unittest.SkipTest(SHIM_SKIP)
        if (form == "bash" or bash_line is not None) and os.name == "nt": raise unittest.SkipTest(POSIX_SKIP)
        if form == "uv" and shutil.which("uv") is None: raise unittest.SkipTest("uv is not installed")
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
            ran, log = os.path.join(d, "ran"), os.path.join(d, "v.log")
            end = "import os, sys\nsys.stdout.write(%s)\nsys.stdout.flush()\nos._exit(0)\n" % ascii(text) if hard else printing(text)
            fake = "open(%r, 'w').close()\n" % ran + end
            script = "#!%s\n" % sys.executable + fake
            if bash_line is not None:
                os.mkdir(os.path.join(d, "d"))  # a line may `cd d` before it runs pytest
                r = run(log=log, extra=env, shim=("pytest", script), argv=["bash", "-c", bash_line], timeout=timeout, cwd=d)
            elif form in ("bare", "env"):
                argv = {"bare": ["pytest"], "env": ["env", "pytest"]}[form] + list(args)
                r = run(log=log, extra=env, shim=("pytest", script), argv=argv, timeout=timeout, cwd=d)
            elif form == "uv":
                # uv finds pytest in the environment's bin before PATH (a shim on PATH loses), so the fake goes in a throwaway venv
                venv = os.path.join(d, "venv")
                subprocess.run([sys.executable, "-m", "venv", "--without-pip", venv], check=True, capture_output=True)
                with open(os.path.join(venv, "bin", "pytest"), "w") as g: g.write(script)
                os.chmod(os.path.join(venv, "bin", "pytest"), 0o755)
                r = run(log=log, extra=dict(env or {}, VIRTUAL_ENV=venv), argv=["uv", "run", "pytest"] + list(args), timeout=timeout, cwd=d)
            else:
                pkg = os.path.join(d, "pytest")
                os.mkdir(pkg)
                open(os.path.join(pkg, "__init__.py"), "w").close()
                with open(os.path.join(pkg, "__main__.py"), "w") as g: g.write(fake)
                path = os.pathsep.join(p for p in (d, os.environ.get("PYTHONPATH")) if p)
                if form == "glued": argv = [sys.executable, "-mpytest"] + list(args)
                elif form == "bash": argv = ["bash", "-c", " ".join(shlex.quote(p) for p in [sys.executable, "-m", "pytest"] + list(args))]
                else: argv = [sys.executable, "-m", "pytest"] + list(args)
                r = run(log=log, extra=dict(env or {}, PYTHONPATH=path), argv=argv, timeout=timeout, cwd=d)
            self.assertTrue(os.path.exists(ran), "the fake pytest never ran, so this case proves nothing")
        return r

    def run_logged(self, code=None, argv=None, timeout=120):
        """Run one fixture as `check` does, and return the run with its log text, so a case reads its output first."""
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
            log = os.path.join(d, "v.log")
            r = run(code, log, argv=argv, timeout=timeout)
            with open(log, encoding="utf-8", errors="replace") as f: full = f.read()
        return r, full

    def assert_cut(self, r):
        first = r.stdout.splitlines()[0] if r.stdout.strip() else ""
        self.assertRegex(first, CUT_LINE, f"a run cut before its summary must read FAIL with cut, got: {first!r}")
        self.assertEqual(r.returncode, 1, r.stdout[:300])

    def test_header_only_run_that_exits_0_is_cut(self):
        self.assert_cut(self.pytest_case(PYTEST_START))

    def test_run_cut_after_progress_lines_is_cut(self):
        self.assert_cut(self.pytest_case(PYTEST_START + PROGRESS * 3))

    def test_coloured_run_cut_after_progress_lines_is_cut(self):
        self.assert_cut(self.pytest_case(COLOURED_START + PROGRESS * 3))

    def test_full_size_run_cut_after_2mib_is_cut(self):
        body = PYTEST_START + PROGRESS * 2048
        self.assertGreater(len(body), CHUNK, "the fixture must hold more than one chunk")
        self.assert_cut(self.pytest_case(body))

    def test_quiet_run_cut_before_its_summary_is_fail(self):
        """`-q` prints no header, so a cut quiet run is progress lines with no summary. Its argv is pytest's, so it is cut."""
        for form in ("module", "bare"):
            with self.subTest(form=form):
                self.assert_cut(self.pytest_case(PROGRESS * 3, args=("-q",), form=form))
        with self.subTest(size="full"):
            body = PROGRESS * 2048
            self.assertGreater(len(body), CHUNK, "the fixture must hold more than one chunk")
            self.assert_cut(self.pytest_case(body, args=("-q",)))

    def test_quiet_complete_run_is_pass(self):
        """The control for the quiet cut: the same progress lines, ending in the summary `-q` prints, read as complete."""
        for form in ("module", "bare"):
            with self.subTest(form=form):
                self.assert_pass(self.pytest_case(PROGRESS * 3 + QUIET_SUMMARY, args=("-q",), form=form))
        with self.subTest(size="full"):
            self.assert_pass(self.pytest_case(PROGRESS * 2048 + QUIET_SUMMARY, args=("-q",)))

    def test_collect_only_summary_with_bars_is_pass(self):
        """`--collect-only` ends with `N tests collected in Ns`. In bars, that is a complete run."""
        for form in ("module", "bare"):
            with self.subTest(form=form):
                self.assert_pass(self.pytest_case(PYTEST_START + COLLECT_ITEMS + COLLECT_BARS, args=("--collect-only",), form=form))

    def test_collect_only_quiet_summary_is_pass(self):
        """With `-q`, `--collect-only` prints node ids and the same count with no bars. That is a complete run."""
        for form in ("module", "bare"):
            with self.subTest(form=form):
                self.assert_pass(self.pytest_case(COLLECT_IDS + COLLECT_QUIET, args=("--collect-only", "-q"), form=form))

    def test_no_tests_ran_summary_is_pass(self):
        """A run that collects nothing ends with `no tests ran in Ns`: in bars by default, bare with `-q`."""
        with self.subTest(verbosity="default"):
            self.assert_pass(self.pytest_case(PYTEST_START + "collected 0 items\n" + NO_TESTS_BARS))
        with self.subTest(verbosity="quiet"):
            self.assert_pass(self.pytest_case(NO_TESTS_QUIET, args=("-q",)))

    def test_filtered_collect_summary_is_pass(self):
        """A filtered `--collect-only` ends `N/M tests collected (K deselected) in Ns`. That is a complete run, in bars or with `-q`."""
        for form in ("module", "bare"):
            with self.subTest(form=form, verbosity="default"):
                self.assert_pass(self.pytest_case(PYTEST_START + COLLECT_ITEMS + FILTERED_BARS, args=("--collect-only",), form=form))
            with self.subTest(form=form, verbosity="quiet"):
                self.assert_pass(self.pytest_case(COLLECT_IDS + FILTERED_QUIET, args=("--collect-only", "-q"), form=form))

    def test_header_first_in_a_later_chunk_still_cuts(self):
        body = PROGRESS * 1100 + PYTEST_START + PROGRESS * 3  # 1,100 progress lines first, so the header is past the first chunk
        self.assertGreater(body.index(PYTEST_START), CHUNK, "the fixture must put the header past the first chunk")
        self.assert_cut(self.pytest_case(body))

    def test_run_with_a_summary_is_not_cut(self):
        self.assert_pass(self.pytest_case(PYTEST_START + PROGRESS * 3 + PYTEST_ALL_PASS))

    def test_coloured_complete_run_is_not_cut(self):
        self.assert_skip(self.pytest_case(COLOURED_START + PROGRESS + PYTEST_COLOUR), 2)

    def test_full_size_complete_run_is_not_cut(self):
        body = PYTEST_START + PROGRESS * 2048 + PYTEST_ALL_PASS
        self.assertGreater(len(body), CHUNK, "the fixture must hold more than one chunk")
        self.assert_pass(self.pytest_case(body))

    def test_summary_straddling_the_chunk_edge_is_not_cut(self):
        body, offset = straddling_body()
        self.assertEqual(body.index(PYTEST_ALL_PASS), offset, "the fixture must start the summary at its offset")
        self.assertGreater(offset + len(PYTEST_ALL_PASS), CHUNK, "the fixture must run the summary past the edge")
        self.assert_pass(self.pytest_case(body))

    def test_non_pytest_run_with_a_pytest_header_is_pass(self):
        """A command that is not pytest reads PASS, though its output is the output of a cut pytest run."""
        body = PYTEST_START + PROGRESS * 3
        commands = {"script": {"code": printing(body)},
                    "c": {"argv": [sys.executable, "-c", "import sys; sys.stdout.write(%s)" % ascii(body)]}}
        for name, kwargs in commands.items():
            with self.subTest(command=name):
                r, full = self.run_logged(**kwargs)
                self.assertIn(PYTEST_START.strip(), full, "the header must reach the log, or this case proves nothing")
                self.assert_pass(r)

    def test_non_pytest_progress_run_with_no_summary_is_pass(self):
        """A command that is not pytest is never cut, even with progress lines and no summary."""
        self.assert_pass(self.check(printing(PROGRESS * 3)))

    def test_one_mib_equals_line_finishes_under_the_guard(self):
        """One 1 MiB line of `=` finishes, as a plain command and as a pytest run. The scan of such a line must be
        linear, so a run still going at HANG_GUARD seconds is hung, and that is the failure."""
        line = "=" * CHUNK + "\n"
        runs = {"plain": lambda: self.check(printing(line), timeout=HANG_GUARD),
                "pytest": lambda: self.pytest_case(line, timeout=HANG_GUARD)}
        for name, go in runs.items():
            with self.subTest(run=name):
                try:
                    r = go()
                except subprocess.TimeoutExpired:
                    self.fail(f"verdict hung: still running after {HANG_GUARD} s on one 1 MiB '=' line")
                self.assertIn(r.stdout.split()[:1], (["PASS"], ["FAIL"]), r.stdout[:300])

    def test_header_quoted_mid_line_is_no_header(self):
        """A pytest run with no `-q` and a quoted header is not cut: the quoted text is no header."""
        body = "note: the pytest header is '=== test session starts ===' here\n" + PROGRESS * 3
        self.assert_pass(self.pytest_case(body))

    def test_silent_run_is_not_cut(self):
        """A pytest run with no output, no `-q` and no header is not cut. `pytest --version` has neither, so it reads PASS."""
        self.assert_pass(self.pytest_case(""))

    def test_header_then_log_truncated_under_verdict_keeps_log_unreadable(self):
        code = ("import os\n"
                f"print({PYTEST_START!r}, end='', flush=True)\n"
                "open(os.environ['VERDICT_LOG'], 'w').close()\n")
        self.assert_fail(self.check(code), 1, "log unreadable")

    def assert_argv_cut(self, form, sizes=("empty", "three")):
        """F2, a bypass: a pytest run that exits 0 mid-run reads FAIL with cut through `form`. The control for it is
        test_quiet_run_cut_before_its_summary_is_fail, which reads the same cut through `python -m pytest -q`."""
        bodies = {"empty": "", "three": PROGRESS * 3, "full": PROGRESS * 2048}
        for size in sizes:
            with self.subTest(form=form, size=size):
                body = bodies[size]
                if size == "full": self.assertGreater(len(body), CHUNK, "the full fixture must hold more than one chunk")
                self.assert_cut(self.pytest_case(body, args=("-q",), form=form, hard=True))

    def test_argv_glued_cut_run_is_fail(self):
        """F2: `python -mpytest -q` is pytest's argv, so a run it cuts reads FAIL with cut."""
        self.assert_argv_cut("glued", sizes=("empty", "three", "full"))

    def test_argv_env_cut_run_is_fail(self):
        """F2: `env pytest -q` is pytest's argv, so a run it cuts reads FAIL with cut."""
        self.assert_argv_cut("env")

    def test_argv_uv_run_cut_run_is_fail(self):
        """F2: `uv run pytest -q` is pytest's argv, so a run it cuts reads FAIL with cut. Skipped when uv is missing."""
        self.assert_argv_cut("uv")

    def test_argv_bash_c_cut_run_is_fail(self):
        """F2: `bash -c "python -m pytest -q"` is pytest's argv, so a run it cuts reads FAIL with cut."""
        self.assert_argv_cut("bash")

    def test_argv_forms_summary_run_is_pass(self):
        """Control, green on the old code: a complete `-q` run through each new form reads PASS. A fix that cuts every
        wrapped run fails here."""
        for form in ("glued", "env", "uv", "bash"):
            with self.subTest(form=form):
                self.assert_pass(self.pytest_case(PROGRESS * 3 + QUIET_SUMMARY, args=("-q",), form=form))

    def test_argv_bash_quoted_pytest_text_is_pass(self):
        """Control, green on the old code: pytest's words inside a quoted `bash -c` string run no pytest, so the run reads PASS."""
        if os.name == "nt": raise unittest.SkipTest(POSIX_SKIP)
        with tempfile.TemporaryDirectory(dir=RUN_FOLDER) as d:
            r = run(log=os.path.join(d, "v.log"), argv=["bash", "-c", "echo 'python3 -m pytest -q'"], cwd=d)
        self.assert_pass(r)

    def test_argv_qq_complete_run_without_summary_is_pass(self):
        """F1, a false alarm: a complete `-qq` run of passing tests prints no summary line in pytest 9.x, only progress
        that ends `[100%]`, so it reads PASS. Today it reads FAIL, cut before the pytest summary. No empty state is
        built: pytest 9.x exits 5 when `-qq` collects no test, so an rc-0 empty run is not a complete one."""
        for form in ("module", "bare"):
            with self.subTest(form=form, size="three"):
                self.assert_pass(self.pytest_case(QQ_LINE, args=("-qq",), form=form))
        with self.subTest(form="module", size="full"):
            self.assertGreater(len(QQ_FULL), CHUNK, "the full fixture must hold more than one chunk")
            self.assert_pass(self.pytest_case(QQ_FULL, args=("-qq",)))

    def test_argv_qq_cut_run_is_fail(self):
        """Control, green on the old code: a `-qq` run cut at 30 percent, with no `[100%]` line, reads FAIL with cut. A fix
        that stops counting `-qq` as quiet would pass it, so this pins that a complete `-qq` run is the one ending `[100%]`."""
        self.assert_cut(self.pytest_case(QQ_CUT, args=("-qq",), hard=True))

    def assert_complete_qq(self, three, full, args, env=None):
        """A complete run whose output is `three`, or `full` (over one chunk), reads PASS through the module and bare
        forms. Each form and size is one subtest."""
        for form in ("module", "bare"):
            with self.subTest(form=form, size="three"):
                self.assert_pass(self.pytest_case(three, args=args, form=form, env=env))
            with self.subTest(form=form, size="full"):
                self.assertGreater(len(full), CHUNK, "the full fixture must hold more than one chunk")
                self.assert_pass(self.pytest_case(full, args=args, form=form, env=env))

    def test_argv_qq_subtest_char_run_is_pass(self):
        """A complete `-qq` run whose last progress line holds the subtest char `u` reads FAIL with cut. It must read PASS."""
        self.assertRegex(QQ_SUB, r"\.\.u +\[100%\]\n\Z", "the fixture must hold u in its last progress line, or this case proves nothing")
        self.assert_complete_qq(QQ_SUB, QQ_SUB_FULL, ("-qq",))

    def test_argv_qq_coloured_run_is_pass(self):
        """With `--color=yes`, SGR codes sit between the progress chars and around `[100%]`. A complete `-qq` run like that
        reads FAIL with cut. It must read PASS."""
        self.assertIn("\x1b[0m\x1b[32m.", QQ_COLOUR, "the fixture must hold SGR codes between the progress chars, or this case proves nothing")
        self.assert_complete_qq(QQ_COLOUR, QQ_COLOUR_FULL, ("-qq", "--color=yes"))

    def test_argv_qq_padding_over_120_run_is_pass(self):
        """At COLUMNS=200 pytest pads the last progress line with more than 120 spaces before `[100%]`. The padding is no
        limit: a complete `-qq` run like that must read PASS."""
        self.assertGreater(QQ_WIDE.index("[100%]"), 3 + 120, "the fixture must pad past 120 spaces, or this case proves nothing")
        self.assert_complete_qq(QQ_WIDE, QQ_WIDE_FULL, ("-qq",), env={"COLUMNS": "200"})

    def test_argv_qq_collect_only_run_is_pass(self):
        """`pytest -qq --co` prints per-file counts, with no progress line and no summary line. A complete collect-only run
        must read PASS."""
        self.assert_complete_qq(QQ_CO, QQ_CO_FULL, ("-qq", "--co"))

    def test_argv_qq_cut_runs_of_those_shapes_stay_fail(self):
        """Control: a `-qq` run cut at 30 percent, with no `[100%]` line, reads FAIL with cut in each shape the complete-run
        cases above use: a subtest char, colour, and padding past 120. A `-qq --co` run that exits 0 before it prints
        anything reads FAIL too."""
        shapes = {"subtest char": (QQ_SUB_CUT, ("-qq",), None),
                  "colour": (QQ_COLOUR_CUT, ("-qq", "--color=yes"), None),
                  "padding": (QQ_WIDE_CUT, ("-qq",), {"COLUMNS": "200"})}
        for shape, (body, args, env) in shapes.items():
            with self.subTest(shape=shape):
                self.assert_cut(self.pytest_case(body, args=args, hard=True, env=env))
        with self.subTest(shape="collect only, no output"):
            self.assert_cut(self.pytest_case("", args=("-qq", "--co"), hard=True))

    def assert_line_cut(self, line, sizes=("empty", "three", "full")):
        """A pytest run that exits 0 mid-run, started by the bash line `line`, reads FAIL with cut. The fake pytest is first
        on PATH, so the sentinel proves the line ran it. A line with a newline in it prints its command name on more than
        one line, so the note may sit on a later line than `FAIL`."""
        bodies = {"empty": "", "three": PROGRESS * 3, "full": PROGRESS * 2048}
        for size in sizes:
            with self.subTest(line=line, size=size):
                if size == "full": self.assertGreater(len(bodies[size]), CHUNK, "the full fixture must hold more than one chunk")
                r = self.pytest_case(bodies[size], bash_line=line, hard=True)
                self.assertTrue(r.stdout.startswith("FAIL "), f"a cut run must read FAIL, got: {r.stdout[:200]!r}")
                self.assertRegex(r.stdout, r"rc=1[^(\n]*\bcut\b", "a cut run must carry rc=1 and the cut note")
                self.assertEqual(r.returncode, 1, r.stdout[:300])

    def test_bash_newline_before_pytest_cut_run_is_fail(self):
        """In `bash -c`, a newline ends a command, so `pytest -q` on the line after `cd d` runs pytest. A scanner that reads
        the two lines as one command, `cd d pytest -q`, finds no pytest and reads the cut run as PASS."""
        self.assert_line_cut("cd d\npytest -q")

    def test_bash_for_loop_pytest_cut_run_is_fail(self):
        """`do` starts a command, so `pytest -q $f` in a `for` loop runs pytest. A scanner that reads the command as `do`
        finds no pytest and reads the cut run as PASS."""
        self.assert_line_cut("for f in a; do pytest -q $f; done")

    def test_bash_newline_and_for_loop_summary_runs_are_pass(self):
        """Control: a complete `-q` run through the newline line and the `for` line reads PASS, in three and full size. A fix
        that cuts every run a shell wrapper starts fails here."""
        for line in ("cd d\npytest -q", "for f in a; do pytest -q $f; done"):
            for size, body in (("three", PROGRESS * 3 + QUIET_SUMMARY), ("full", PROGRESS * 2048 + QUIET_SUMMARY)):
                with self.subTest(line=line, size=size):
                    if size == "full": self.assertGreater(len(body), CHUNK, "the full fixture must hold more than one chunk")
                    self.assert_pass(self.pytest_case(body, bash_line=line))

    def test_scanner_hash_after_a_quoted_hash_is_cut(self):
        """A `#` inside quotes is text, and so is a `#` that follows the quote in the same word, so `pytest -q` after
        `echo 'a#b'#c;` runs pytest. A scanner that reads that second `#` as a comment drops the rest of the line."""
        self.assert_line_cut("echo 'a#b'#c; pytest -q")

    def test_scanner_apostrophe_in_heredoc_text_is_cut(self):
        """An apostrophe in heredoc text (`Don't`) is text, not an open quote, so the `pytest -q` after the heredoc runs
        pytest. A scanner that reads the apostrophe as an open quote never finds its close and reads no pytest. The heredoc
        also holds newlines, which end commands in bash, so the newline fix is needed for this case too."""
        self.assert_line_cut("cat <<EOF\nDon't\nEOF\npytest -q")

    def test_scanner_hash_in_quotes_and_apostrophe_in_comment_are_cut(self):
        """Control: a `#` inside quotes opens no comment, so `echo '#'; pytest -q` runs pytest. An apostrophe in a comment
        after pytest is text, so `pytest -q # don't` runs it too. A fix that cuts a line at its first `#` before it reads
        quotes fails the first line."""
        for line in ("echo '#'; pytest -q", "pytest -q # don't"):
            self.assert_line_cut(line)

    def test_scanner_newline_inside_quotes_is_text_pass(self):
        """Control: a newline inside single quotes is text, so the `pytest -q` in the quoted string runs no pytest, and the
        run reads PASS. A fix that splits lines before it reads quotes cuts this run."""
        if os.name == "nt": raise unittest.SkipTest(POSIX_SKIP)
        line = "echo 'x\npytest -q'"
        r, full = self.run_logged(argv=["bash", "-c", line])
        self.assertIn("x\npytest -q\n", full, "the quoted text must reach the log, or this case proves nothing")
        self.assert_pass(r)


class HangLineOneHome(unittest.TestCase):
    """The HANG line's fixed words have one home, hooks/_nowindow.py. bin/verdict, bin/ci-job and merge/merge.py read the line from
    there and copy none of it (rule building-allow-list-is-the-constant; decision hang-stop). The scan reads each file's string
    constants with ast, so a comment that names the words does not count, and a string that holds them does."""

    WORDS = "no output or CPU for"  # the fixed words after the name in verdict's hang line
    HOME = os.path.join(HERE, "..", "hooks", "_nowindow.py")
    USERS = [os.path.join(HERE, "..", *parts) for parts in (("bin", "verdict"), ("bin", "ci-job"), ("merge", "merge.py"))]

    @staticmethod
    def constants_with(text, words):
        """The string constants of the Python source `text` that hold `words`, read with the language's own parser."""
        return [node.value for node in ast.walk(ast.parse(text)) if isinstance(node, ast.Constant) and isinstance(node.value, str) and words in node.value]

    @staticmethod
    def read(path):
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_the_hang_words_are_copied_nowhere_outside_the_home(self):
        for path in self.USERS:
            with self.subTest(path=os.path.relpath(path, HERE)):
                found = self.constants_with(self.read(path), self.WORDS)
                self.assertEqual(found, [], "%s copies the HANG line's words %r; it must read them from the one home, hooks/_nowindow.py"
                                 % (os.path.relpath(path, os.path.join(HERE, "..")), self.WORDS))

    def test_the_one_home_holds_the_words(self):
        self.assertTrue(self.constants_with(self.read(self.HOME), self.WORDS),
                        "hooks/_nowindow.py holds no HANG line words: the one home of the hang line is not built")

    def test_the_scan_reads_strings_and_not_comments(self):  # the scanner's control: a string holding the words counts, a comment does not
        text = ('# no output or CPU for, in a comment\n'
                'one = "# no output or CPU for"\n'
                'two = """\nno output or CPU for\n"""\n'
                "# don't count this: no output or CPU for\n")
        self.assertEqual(len(self.constants_with(text, self.WORDS)), 2, "the scan does not read string constants alone")


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder

if __name__ == "__main__":
    unittest.main()
