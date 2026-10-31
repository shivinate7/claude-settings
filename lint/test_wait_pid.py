#!/usr/bin/env python3
"""Fixture test for bin/wait-pid. Run: python3 lint/test_wait_pid.py -v

`wait-pid PID [--timeout SECS]` waits for one pid that this session owns, and never signals it.
Exit 0: the pid ended, or was not running at the start. Exit 124: still running at --timeout.
Exit 2: a bad argument, or a pid that is not this session's (it returns at once, with no wait).
Exit 3: unknown. `ps` failed or timed out, so the helper cannot tell whether the pid lives; a failed
read is never taken as "ended".

A pid is this session's when it descends from the session root (`CLAUDE_GUARD_ROOT_PID` is the seam,
as in hooks/test_guard.py), or when its ancestor walk reaches init and the pid itself, or any
ancestor below init, holds `CLAUDE_CODE_SESSION_ID=<id>` from wait-pid's own environment. The
measured stranded shape on Linux: after a stall the forked stub shell (PPID 1) holds no tag, and
the exec'd job under it does. The stall report names that stub first in `pid=`, so the stub itself,
with a tagged descendant, is also this session's.

Each case that waits ends its target with SIGKILL at a set time and checks that the helper returned
after that time, so an early return fails without a timing guess. Only the fake-`ps` cases write a
file, and only in this run's folder (test-temp-standard, lint/_test_temp.py).

The macOS path (`ps`, not /proc) has no product seam, so those cases run the helper through
`runpy` with `sys.platform` set to "darwin", as hooks/test_stall_watch.py sets `os.name`, and put
a fake `ps` first on PATH. The fake sends the ownership reads (`ppid=`, `comm=`) to the real `ps`.
"""
import ast
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
from collections import namedtuple

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_temp  # noqa: E402  test-temp-standard: every temp path comes from this run's folder
RUN_FOLDER = _test_temp.run_folder()  # one run folder per test run; its sweep is proved in test_find_copies.py
HOOKS = os.path.join(HERE, "..", "hooks")
WP = os.environ.get("WAIT_PID_UNDER_TEST") or os.path.join(HERE, "..", "bin", "wait-pid")
TAG = "CLAUDE_CODE_SESSION_ID"
SESSION = "wait-pid-test-" + uuid.uuid4().hex
OTHER_SESSION = "wait-pid-other-" + uuid.uuid4().hex
LIFE = "60"   # a target outlives every case; each case ends it, and cleanup is the backstop
HEARTBEAT_LINE = "wait-pid: still waiting"
Result = namedtuple("Result", "rc out end elapsed")
Strand = namedtuple("Strand", "job stub")   # stub is None when the job is itself the PPID-1 pid
# Runs bin/wait-pid as the macOS would: `ps` answers liveness, since sys.platform is not "linux".
DARWIN_DRIVER = ("import runpy, sys\nsys.platform = 'darwin'\nsys.argv = sys.argv[1:]\n"
                 "runpy.run_path(sys.argv[0], run_name='__main__')\n")


def run_helper(args, session=SESSION, root=None, heartbeat=None, timeout=20, darwin=False, path_first=None):
    """Run bin/wait-pid itself (so its executable bit and shebang count). stdout and stderr are
    one stream. rc is None when it did not return in `timeout` seconds. `darwin` runs it through
    DARWIN_DRIVER (the ps path); `path_first` is a folder put first on PATH."""
    if not os.path.exists(WP):
        raise AssertionError("bin/wait-pid does not exist: %s" % WP)
    env = {k: v for k, v in os.environ.items()
           if k not in (TAG, "CLAUDE_GUARD_ROOT_PID", "WAIT_PID_HEARTBEAT")}
    env["CLAUDE_GUARD_ROOT_PID"] = str(os.getpid() if root is None else root)
    if session:
        env[TAG] = session
    if heartbeat:
        env["WAIT_PID_HEARTBEAT"] = str(heartbeat)
    if path_first:
        env["PATH"] = path_first + os.pathsep + env.get("PATH", os.defpath)
    command = [sys.executable, "-c", DARWIN_DRIVER, WP] if darwin else [WP]
    start = time.monotonic()
    try:
        done = subprocess.run(command + [str(a) for a in args], stdin=subprocess.DEVNULL,
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
    A tag of None means the process holds no session tag. Returns Strand(job pid, stub pid), or
    None when this host cannot build the shape."""
    env = {k: v for k, v in os.environ.items() if k != TAG}
    if stub_tag:
        env[TAG] = stub_tag
    job = tag_words(job_tag) + ["sleep", LIFE]
    if not with_stub:
        pid = detach(job, env)
        return None if pid is None else Strand(pid, None)
    stub = detach(["sh", "-c", '"$@" & wait', "sh"] + job, env)
    if stub is None:
        return None
    for _ in range(100):   # the stub forks the job a moment after it starts
        found = [p for p, parent in ps_parents().items() if parent == stub]
        if found:
            return Strand(found[0], stub)
        time.sleep(0.05)
    stop(stub)
    return None


def fake_ps(folder, mode):
    """Write a fake `ps` into `folder` and return the folder. Each liveness read (anything but the
    ownership reads `ppid=` and `comm=`, which go to the real ps) is counted in `folder/calls`, then:
    "fail" exits 1 with a message on stderr; "hang" sleeps past the helper's timeout;
    "fail_after_first" answers the first liveness read for real and fails every later one."""
    real, calls = shlex.quote(shutil.which("ps")), shlex.quote(os.path.join(folder, "calls"))
    fail = 'echo "ps: simulated failure" >&2; exit 1'
    body = {"fail": fail, "hang": "exec sleep 30",
            "fail_after_first": 'n=$(wc -l < %s); [ $n -le 1 ] && exec %s "$@"; %s' % (calls, real, fail)}[mode]
    path = os.path.join(folder, "ps")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write('#!/bin/sh\ncase "$*" in *ppid=*|*comm=*) exec %s "$@";; esac\necho x >> %s\n%s\n' % (real, calls, body))
    os.chmod(path, 0o755)
    return folder


def load_stall_watch_tests():
    """hooks/test_stall_watch.py, the one home of the stall-watch hook runner. The import makes its
    own scratch folder, removed when this process exits."""
    sys.path.insert(0, HOOKS)
    try:
        import test_stall_watch
    finally:
        sys.path.remove(HOOKS)
    return test_stall_watch


def hooks_proc_env():
    """hooks/proc_env.py, the one home of the exec-environment read, for a case's precondition."""
    sys.path.insert(0, HOOKS)
    try:
        import proc_env
    finally:
        sys.path.remove(HOOKS)
    return proc_env



class T(unittest.TestCase):
    def own_child(self):
        """A live `sleep` that is a child of this test, reaped by a thread the moment it ends."""
        proc = subprocess.Popen(["sleep", LIFE])
        threading.Thread(target=proc.wait, daemon=True).start()
        self.addCleanup(stop, proc.pid)
        return proc.pid

    def stranded_pair(self, stub_tag, job_tag, with_stub=True):
        """Strand(job, stub) of a stranded job; both are stopped at cleanup."""
        found = strand(stub_tag, job_tag, with_stub)
        if found is None:
            self.skipTest("no PPID-1 orphan with a child on this host")
        for pid in found:
            if pid:
                self.addCleanup(stop, pid)
        return found

    def stranded(self, stub_tag, job_tag, with_stub=True):
        return self.stranded_pair(stub_tag, job_tag, with_stub).job

    def assertWaitsUntilKilled(self, pid, delay=2.0, kill=None, **kw):
        """Wait on `pid`; end `kill` (default: `pid`) after `delay` seconds."""
        killer = Killer(pid if kill is None else kill, delay)
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

    def test_untagged_stub_with_a_tagged_child_is_owned_and_waits_for_the_job(self):
        """The pid a stall report names first is the stub, not the job. Waiting on the stub is owned
        when a descendant holds the tag, and it returns when the whole job ends, not before."""
        found = self.stranded_pair(None, SESSION)
        self.assertWaitsUntilKilled(found.stub, kill=found.job)

    def test_stall_report_names_a_pid_that_wait_pid_waits_on(self):
        """End to end: the real stall-watch wrapper on a quiet job. The wrapper shell holds no tag
        and only the job's exec holds it (the measured shape), so the first pid of `pid=` is an
        untagged PPID-1 stub. `wait-pid <that pid>` must wait for the job and exit 0."""
        stall = load_stall_watch_tests()
        env = {k: v for k, v in os.environ.items() if k != TAG}
        job = "env %s=%s sleep %s; echo done" % (TAG, SESSION, LIFE)   # `; echo` keeps a stub shell above the job
        rc, text, _secs, _cmd = stall.run_rewritten(job, shell="/bin/sh", env=env)
        self.assertEqual(rc, 3, text)
        line = next((l for l in text.splitlines() if l.startswith("STALL:")), "")
        named = re.search(r"\bpid=(\d+(?:,\d+)*)", line)
        self.assertIsNotNone(named, "no pid= on the STALL line: " + text)
        pids = [int(p) for p in named.group(1).split(",")]
        for pid in pids:
            self.addCleanup(stop, pid)
        stub, rest = pids[0], pids[1:]
        holds = hooks_proc_env().holds_session_tag
        if not rest:
            self.skipTest("the job shell ran the job in place, so there is no stub shell to wait on")
        if ps_parents().get(stub) != 1:
            self.skipTest("the stub was not reparented to init, so it is not a stranded stub")
        if holds(stub, SESSION) or not any(holds(p, SESSION) for p in rest):
            self.skipTest("cannot build an untagged stub over a tagged job here (the exec-environment read found none)")
        self.assertWaitsUntilKilled(stub, kill=next(p for p in rest if holds(p, SESSION)))

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

    def test_untagged_stub_with_an_untagged_child_is_refused(self):
        """A PPID-1 stub is not this session's just for having a child: that child must hold the tag."""
        self.assertRefusedAtOnce(self.stranded_pair(None, None).stub)

    def test_untagged_stub_with_another_sessions_child_is_refused(self):
        self.assertRefusedAtOnce(self.stranded_pair(None, OTHER_SESSION).stub)

    # Pids that are not running.
    def test_pid_not_running_at_start_exits_0_and_says_so(self):
        proc = subprocess.Popen(["sleep", "0"])
        proc.wait()
        r = run_helper([proc.pid])
        self.assertEqual(r.rc, 0, r.out)
        self.assertRegex(r.out, r"(?i)\bnot running\b")
        self.assertIn(str(proc.pid), r.out)
        self.assertLess(r.elapsed, 5)

    # A failed or timed-out ps is unknown, never "ended". The pid lives through each case.
    def assertPsFailureIsUnknown(self, mode, pid=None, timeout=20, **kw):
        folder = tempfile.mkdtemp(dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, folder, True)
        pid = pid or self.own_child()
        r = run_helper([pid], timeout=timeout, darwin=True, path_first=fake_ps(folder, mode), **kw)
        self.assertTrue(alive(pid), "the target ended, so this case proves nothing")
        self.assertNotEqual(r.rc, 0, "ps failed, yet the helper read it as ended: %r" % (r.out,))
        self.assertEqual(r.rc, 3, r.out)
        self.assertRegex(r.out, r"(?i)\bunknown\b")
        return r

    def test_failed_ps_at_the_start_is_unknown_not_not_running(self):
        self.assertPsFailureIsUnknown("fail")

    def test_failed_ps_while_waiting_is_unknown_not_ended(self):
        self.assertPsFailureIsUnknown("fail_after_first")

    def test_timed_out_ps_is_unknown_not_not_running(self):
        """The helper gives `ps` 10 seconds, so this case takes about that long."""
        self.assertPsFailureIsUnknown("hang", timeout=40)

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


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)   # test-temp-standard: teardown removes the run folder


if __name__ == "__main__":
    if os.name == "nt":
        print("SKIP wait-pid: a POSIX helper (ps, pids and signals)")
        sys.exit(0)
    unittest.main()
