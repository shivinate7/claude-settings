#!/usr/bin/env python3
"""Fixture test for bin/wait-pid. Run: python3 lint/test_wait_pid.py -v

`wait-pid PID [--timeout SECS]` waits for one pid that this session owns, and never signals it.
Exit 0: the pid ended, or was not running at the start. Exit 124: still running at --timeout.
Exit 2: a bad argument, or a pid that is not this session's (it returns at once, with no wait).

A pid is this session's when it descends from the session root (`CLAUDE_GUARD_ROOT_PID` is the seam,
as in hooks/test_guard.py), or when its ancestor walk reaches init and the pid itself, or any
ancestor below init, holds `CLAUDE_CODE_SESSION_ID=<id>` from wait-pid's own environment. The
measured stranded shape on Linux: after a stall the forked stub shell (PPID 1) holds no tag, and
the exec'd job under it does.

Each case that waits ends its target with SIGKILL at a set time and checks that the helper returned
after that time, so an early return fails without a timing guess. No case here writes a file.
"""
import ast
import os
import signal
import subprocess
import sys
import threading
import time
import unittest
import uuid
from collections import namedtuple

HERE = os.path.dirname(os.path.abspath(__file__))
WP = os.environ.get("WAIT_PID_UNDER_TEST") or os.path.join(HERE, "..", "bin", "wait-pid")
TAG = "CLAUDE_CODE_SESSION_ID"
SESSION = "wait-pid-test-" + uuid.uuid4().hex
OTHER_SESSION = "wait-pid-other-" + uuid.uuid4().hex
LIFE = "60"   # a target outlives every case; each case ends it, and cleanup is the backstop
HEARTBEAT_LINE = "wait-pid: still waiting"
Result = namedtuple("Result", "rc out end elapsed")


def run_helper(args, session=SESSION, root=None, heartbeat=None, timeout=20):
    """Run bin/wait-pid itself (so its executable bit and shebang count). stdout and stderr are
    one stream. rc is None when it did not return in `timeout` seconds."""
    if not os.path.exists(WP):
        raise AssertionError("bin/wait-pid does not exist: %s" % WP)
    env = {k: v for k, v in os.environ.items()
           if k not in (TAG, "CLAUDE_GUARD_ROOT_PID", "WAIT_PID_HEARTBEAT")}
    env["CLAUDE_GUARD_ROOT_PID"] = str(os.getpid() if root is None else root)
    if session:
        env[TAG] = session
    if heartbeat:
        env["WAIT_PID_HEARTBEAT"] = str(heartbeat)
    start = time.monotonic()
    try:
        done = subprocess.run([WP] + [str(a) for a in args], stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                              env=env, timeout=timeout)
        rc, out = done.returncode, done.stdout
    except subprocess.TimeoutExpired as e:
        rc, out = None, (e.stdout.decode() if isinstance(e.stdout, bytes) else e.stdout) or ""
    end = time.monotonic()
    return Result(rc, out, end, end - start)


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def stop(pid):
    try:
        os.kill(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


class Killer:
    """Sends SIGKILL to `pid` after `delay` seconds and records the time just before it does."""
    def __init__(self, pid, delay):
        self.at = None
        self._pid = pid
        self._timer = threading.Timer(delay, self._fire)
        self._timer.daemon = True
        self._timer.start()

    def _fire(self):
        self.at = time.monotonic()
        stop(self._pid)

    def join(self):
        self._timer.join()


def ps_parents():
    out = subprocess.run(["ps", "-axo", "pid=,ppid="], capture_output=True, text=True, timeout=10).stdout
    return {int(a): int(b) for a, b in (line.split() for line in out.splitlines() if line.strip())}


def detach(argv, env):
    """Start `argv` detached, so init adopts it (PPID 1). Return its pid, or None when this host
    does not reparent to 1."""
    script = '"$@" </dev/null >/dev/null 2>&1 & echo $!'
    try:
        answer = subprocess.run(["sh", "-c", script, "sh"] + argv, env=env, capture_output=True,
                                text=True, timeout=20)
        pid = int(answer.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    if ps_parents().get(pid) != 1:
        stop(pid)
        return None
    return pid


def tag_words(tag):
    """`env` words that give the job exactly this tag, or none at all when `tag` is None."""
    return ["env", "-u", TAG] if tag is None else ["env", "%s=%s" % (TAG, tag)]


def strand(stub_tag, job_tag, with_stub=True):
    """A stranded job. With a stub: a detached stub shell (PPID 1) and its one child `sleep`,
    which holds `job_tag`; the stub holds `stub_tag`. Without: the job alone is the PPID-1 pid.
    A tag of None means the process holds no session tag. Returns the job's pid, or None."""
    env = {k: v for k, v in os.environ.items() if k != TAG}
    if stub_tag:
        env[TAG] = stub_tag
    job = tag_words(job_tag) + ["sleep", LIFE]
    if not with_stub:
        return detach(job, env)
    stub = detach(["sh", "-c", '"$@" & wait', "sh"] + job, env)
    if stub is None:
        return None
    for _ in range(100):   # the stub forks the job a moment after it starts
        found = [p for p, parent in ps_parents().items() if parent == stub]
        if found:
            return found[0]
        time.sleep(0.05)
    stop(stub)
    return None



class T(unittest.TestCase):
    def own_child(self):
        """A live `sleep` that is a child of this test, reaped by a thread the moment it ends."""
        proc = subprocess.Popen(["sleep", LIFE])
        threading.Thread(target=proc.wait, daemon=True).start()
        self.addCleanup(stop, proc.pid)
        return proc.pid

    def stranded(self, stub_tag, job_tag, with_stub=True):
        pid = strand(stub_tag, job_tag, with_stub)
        if pid is None:
            self.skipTest("no PPID-1 orphan with a child on this host")
        self.addCleanup(stop, pid)
        return pid

    def assertWaitsUntilKilled(self, pid, delay=2.0, **kw):
        killer = Killer(pid, delay)
        r = run_helper([pid], **kw)
        killer.join()
        self.assertEqual(r.rc, 0, r.out)
        self.assertIsNotNone(killer.at, "the target was never killed")
        self.assertGreaterEqual(r.end, killer.at, "returned before the pid ended: " + r.out)
        return r

    def assertRefusedAtOnce(self, pid, **kw):
        r = run_helper([pid], timeout=15, **kw)
        self.assertEqual(r.rc, 2, "waited, or exit was not 2: %r" % (r.out,))
        self.assertRegex(r.out, r"(?i)not this session")
        self.assertLess(r.elapsed, 5, "did not return at once")
        self.assertTrue(alive(pid), "the helper signalled a pid it does not own")

    # The file itself.
    def test_helper_is_an_executable_python_script(self):
        self.assertTrue(os.path.isfile(WP), WP)
        self.assertTrue(os.access(WP, os.X_OK), "bin/wait-pid is not executable")
        with open(WP, encoding="utf-8") as handle:
            first = handle.readline()
        self.assertTrue(first.startswith("#!") and "python" in first, first)

    def test_ownership_lives_in_guard_kill_and_the_helper_reads_no_tag(self):
        """One home for ownership (hooks/guard_kill.py, beside pid_is_owned). The helper imports it
        and never reads the tag itself: no proc_env import, and no use of holds_session_tag in any
        form. A liveness poll may still use guard_kill's own helpers."""
        self.assertTrue(os.path.isfile(WP), WP)
        with open(WP, encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        imported, names = set(), set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
            if isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.Attribute):
                names.add(node.attr)
            elif isinstance(node, ast.alias):
                names.update(n for n in (node.name, node.asname) if n)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                names.add(node.value)   # a name given to importlib or getattr
        self.assertIn("guard_kill", imported)
        self.assertNotIn("proc_env", imported | names)
        self.assertNotIn("holds_session_tag", names)

    # Owned pids.
    def test_owned_child_exits_after_two_seconds(self):
        self.assertWaitsUntilKilled(self.own_child())

    def test_stranded_job_under_an_untagged_stub_is_owned_by_its_tag(self):
        """The measured shape: untagged PPID-1 stub, tagged job under it."""
        self.assertWaitsUntilKilled(self.stranded(None, SESSION))

    def test_stranded_job_under_a_tagged_stub_is_owned(self):
        """Any ancestor below init that holds the tag owns the pid: here the stub, not the job."""
        self.assertWaitsUntilKilled(self.stranded(SESSION, None))

    def test_tagged_ppid_1_pid_itself_is_owned(self):
        self.assertWaitsUntilKilled(self.stranded(None, SESSION, with_stub=False))

    # Foreign pids: exit 2, a message, no wait, no signal.
    def test_foreign_pid_is_refused_at_once(self):
        other = subprocess.Popen(["sleep", LIFE])   # a live pid that is nobody's ancestor
        self.addCleanup(lambda: (stop(other.pid), other.wait()))
        self.assertRefusedAtOnce(self.own_child(), root=other.pid)

    def test_stranded_job_with_no_tag_anywhere_is_refused(self):
        self.assertRefusedAtOnce(self.stranded(None, None))

    def test_stranded_job_with_another_sessions_tag_is_refused(self):
        self.assertRefusedAtOnce(self.stranded(OTHER_SESSION, OTHER_SESSION))

    def test_tag_is_not_read_when_the_helper_has_no_session_id(self):
        """With no id of its own the helper must not match an empty id against a tagged job."""
        self.assertRefusedAtOnce(self.stranded(None, SESSION), session=None)

    # Pids that are not running.
    def test_pid_not_running_at_start_exits_0_and_says_so(self):
        proc = subprocess.Popen(["sleep", "0"])
        proc.wait()
        r = run_helper([proc.pid])
        self.assertEqual(r.rc, 0, r.out)
        self.assertRegex(r.out, r"(?i)\bnot running\b")
        self.assertIn(str(proc.pid), r.out)
        self.assertLess(r.elapsed, 5)

    # Timeout.
    def test_still_running_at_timeout_exits_124_and_leaves_the_pid_alone(self):
        pid = self.own_child()
        r = run_helper([pid, "--timeout", "1"])
        self.assertEqual(r.rc, 124, r.out)
        self.assertGreaterEqual(r.elapsed, 0.9)
        self.assertLess(r.elapsed, 10)
        self.assertTrue(alive(pid), "wait-pid must not stop the pid it waits on")

    # Arguments.
    def test_bad_arguments_exit_2_at_once(self):
        for args in (["0"], ["1"], ["-1"], ["abc"], ["12x"], []):
            with self.subTest(args=args):
                r = run_helper(args, timeout=15)
                self.assertEqual(r.rc, 2, "args %r: %r" % (args, r.out))
                self.assertLess(r.elapsed, 5)

    # Heartbeat: a long, quiet wait must not draw a false stall alarm (decision stall-watch), so
    # check for at least one beat, never an exact count.
    def test_heartbeat_while_waiting(self):
        r = self.assertWaitsUntilKilled(self.own_child(), delay=3.2, heartbeat="1")
        beats = [l for l in r.out.splitlines() if l.startswith(HEARTBEAT_LINE)]
        self.assertGreaterEqual(len(beats), 1, r.out)


if __name__ == "__main__":
    if os.name == "nt":
        print("SKIP wait-pid: a POSIX helper (ps, pids and signals)")
        sys.exit(0)
    unittest.main()
