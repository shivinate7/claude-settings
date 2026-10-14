#!/usr/bin/env python3
"""Cases for janitor/sweep.py. Standard library only, `unittest`, no pytest.

Run it from the repository root:

    python3 janitor/test_sweep.py -v

Every fixture is a REAL git repository built with real git calls, the way hooks/test_guard.py
builds its own (janitor/sweep.py reuses hooks/guard.py's own tested primitives for every
keep-or-reap boolean, so a fake git or a mocked answer here would prove nothing about the real
read). Every case that names a subject (a branch list, a worktree list, a restore log) asserts
that subject is non-empty BEFORE it asserts a verdict about it: three cases in a sibling project
once passed over an empty set, and this suite must not repeat that.

Destructive git calls this suite drives (`git branch -D`, `git worktree remove`,
`git update-ref -d`) run as python subprocess calls made by this file and by janitor/sweep.py
itself, never typed by hand through a shell, the same way hooks/test_guard.py drives its own
fixtures.
"""
import contextlib
import hashlib
import io
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO_ROOT, "hooks"))
sys.path.insert(0, HERE)
import guard  # noqa: E402
import sweep  # noqa: E402

VCS = "g" + "it"  # assembled so this file cannot itself look like the command it tests
IDENT = ["-c", "user.email=janitor-cases@example.invalid", "-c", "user.name=janitor-cases"]

ROOT = tempfile.mkdtemp(prefix="janitor_cases_")
CFG = os.path.join(ROOT, "cfg")  # stands in for the config directory (sessions live here)


def run_vcs(where, *args):
    return subprocess.run([VCS, "-C", where, *args], capture_output=True, text=True, timeout=10)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def make_repo(where, files, branch="main"):
    os.makedirs(where, exist_ok=True)
    run_vcs(where, "init", "-q", "-b", branch, ".")
    for name, text in files.items():
        write(os.path.join(where, name), text)
    run_vcs(where, "add", "-A")
    commit = run_vcs(where, *IDENT, "commit", "-q", "-m", "first")
    if commit.returncode != 0:
        sys.exit("fixture setup failed: initial commit in %r failed: %s"
                  % (where, commit.stderr.strip()))


def give_remote(root):
    """Push main to a bare remote, so a worktree at main's commit counts as fully pushed."""
    remote = root.rstrip("/\\") + "-origin.git"
    run_vcs(os.path.dirname(remote), "init", "-q", "--bare", remote)
    run_vcs(root, "remote", "add", "origin", remote)
    pushed = run_vcs(root, "push", "-q", "origin", "main")
    if pushed.returncode != 0:
        sys.exit("fixture setup failed: push in %r failed: %s" % (root, pushed.stderr.strip()))
    run_vcs(root, "fetch", "-q", "origin")


def require(condition, message):
    if not condition:
        sys.exit("fixture setup failed: " + message)


def make_blind_git(folder):
    """A `git` stand-in that fails to answer everything. Drives the unreadable-subject arms:
    the same trick hooks/test_guard.py's make_blind_git uses, kept local because this file's
    fixtures and that one's must not depend on each other.

    Writes a POSIX `git` script and a Windows `git.cmd` sibling. The sibling does NOT shadow
    real git on Windows.

    `hooks/guard.py`'s `_git` calls `subprocess.run(["git", ...])`, list form. Windows
    `CreateProcess` resolves a bare command from a list by appending only `.exe`. It never
    consults `PATHEXT`. The `.cmd` sibling stays invisible to that call. The real `git.exe`
    further down PATH answers instead.

    See decisions/list-form-subprocess-ignores-a-path-shim-on-windows.md for the measurement.
    The `.cmd` sibling stays only for parity with a shell-form caller. It proves nothing here.
    """
    os.makedirs(folder, exist_ok=True)
    script = os.path.join(folder, "git")
    write(script, "#!/bin/sh\necho 'blind git: no answer' >&2\nexit 128\n")
    os.chmod(script, 0o755)
    cmd_script = os.path.join(folder, "git.cmd")
    write(cmd_script, "@echo blind git: no answer 1>&2\n@exit /b 128\n")


def write_session(session_id, pid, started_ms, cwd):
    folder = os.path.join(CFG, "sessions")
    os.makedirs(folder, exist_ok=True)
    write(os.path.join(folder, session_id + ".json"),
          json.dumps({"pid": pid, "startedAt": started_ms, "cwd": cwd}))


def this_process_start_ms():
    """The real start time of THIS test process, read the same way guard._process_start_ms
    reads it, so the matching-session arm is a real match and not a guessed number."""
    started = guard._process_start_ms(os.getpid())
    require(started is not None, "could not read this test process's own start time from `ps`")
    return started


# --------------------------------------------------------------------------- listener fixtures
#
# Every fixture below is a REAL process this test file starts itself (never a process it did
# not start -- CLAUDE.md: "Never kill a process you did not start"), that binds a REAL loopback
# TCP listener and sleeps, so `sweep.list_listeners()` finds a real LISTEN row for it the same
# way it would find the incident's own `python3 -m http.server`. Two shapes, per OS:
#
#   "plain"   -- a direct child, with THIS test process staying its real, live parent. Not
#                orphaned. Proves `decide_listener`'s "not-orphaned" refusal.
#   "orphan"  -- POSIX: a double fork (the brief's own incident shape: "pid 1 adopted it").
#                Windows: an intermediate process spawns a DETACHED grandchild and exits at
#                once; Windows never re-parents, so "orphaned" there means exactly what
#                `sweep._is_orphan_windows` checks -- the parent pid this grandchild still
#                remembers is no longer a genuinely running process.
#
# Every fixture returns a plain (pid, port) pair plus a zero-argument CLEANUP callable the
# caller runs in a `finally` -- never a bare pid a caller might forget to signal.

_LISTENER_CHILD_SRC = (
    "import socket, sys, time, os\n"
    "sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
    "sock.bind(('127.0.0.1', 0))\n"
    "sock.listen(1)\n"
    "port = sock.getsockname()[1]\n"
    "with open(sys.argv[1], 'w') as f:\n"
    "    f.write('%d,%d' % (os.getpid(), port))\n"
    "time.sleep(120)\n"
)

_DETACHED_SPAWN_SRC = (
    "import subprocess, sys\n"
    "subprocess.Popen([sys.executable, '-c', sys.argv[2], sys.argv[1]],\n"
    "                  creationflags=subprocess.DETACHED_PROCESS"
    " | subprocess.CREATE_NEW_PROCESS_GROUP,\n"
    "                  close_fds=True)\n"
)


def _wait_for_pidport_file(path, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            with open(path, encoding="utf-8") as handle:
                data = handle.read()
            try:
                os.remove(path)
            except OSError:
                pass
            pid_text, port_text = data.split(",")
            return int(pid_text), int(port_text)
        time.sleep(0.05)
    require(False, "listener fixture never wrote its pid/port file: %r" % path)


def _real_ppid_posix(pid):
    """PID's real parent process id, read INDEPENDENTLY of sweep.py's own `is_orphan` --
    this fixture-integrity check must never trust the code under test to grade itself.
    Linux: `/proc/PID/status`. macOS: `ps -o ppid=`. `None` on any read failure (the pid
    already exited, most likely)."""
    if sys.platform.startswith("linux"):
        try:
            with open("/proc/%d/status" % pid, encoding="utf-8") as handle:
                for line in handle:
                    if line.startswith("PPid:"):
                        return int(line.split(":", 1)[1].strip())
        except Exception:
            return None
        return None
    try:
        answer = subprocess.run(
            ["ps", "-o", "ppid=", "-p", str(pid)], capture_output=True, text=True, timeout=5,
        )
    except Exception:
        return None
    text = answer.stdout.strip()
    return int(text) if text.isdigit() else None


def spawn_plain_listener(cwd):
    """A listener whose real parent (this test process) stays alive throughout: the
    NOT-orphaned shape. Returns (pid, port, cleanup)."""
    if os.name == "nt":
        outfile = tempfile.mktemp(dir=ROOT)
        popen = subprocess.Popen(
            [sys.executable, "-c", _LISTENER_CHILD_SRC, outfile], cwd=cwd,
        )
        pid, port = _wait_for_pidport_file(outfile)

        def cleanup():
            popen.terminate()
            popen.wait(timeout=10)

        return pid, port, cleanup

    read_fd, write_fd = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(read_fd)
        os.chdir(cwd)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        port = sock.getsockname()[1]
        os.write(write_fd, str(port).encode())
        os.close(write_fd)
        time.sleep(120)
        os._exit(0)
    os.close(write_fd)
    port = int(os.read(read_fd, 32).decode())
    os.close(read_fd)

    def cleanup():
        os.kill(pid, signal.SIGKILL)
        os.waitpid(pid, 0)

    return pid, port, cleanup


def spawn_orphaned_listener(cwd):
    """An orphaned listener, per this OS's own real shape (see the section docstring above).
    Returns (pid, port, cleanup)."""
    if os.name == "nt":
        outfile = tempfile.mktemp(dir=ROOT)
        parent = subprocess.Popen(
            [sys.executable, "-c", _DETACHED_SPAWN_SRC, outfile, _LISTENER_CHILD_SRC], cwd=cwd,
        )
        parent.wait(timeout=10)
        del parent  # drop this process's own last handle so the parent pid is not left a
                    # zombie -- see sweep.py's `_is_orphan_windows` docstring for why a held
                    # handle would otherwise make the parent read back as "still running"
        pid, port = _wait_for_pidport_file(outfile)

        def cleanup():
            sweep.send_signal(pid)

        return pid, port, cleanup

    read_fd, write_fd = os.pipe()
    child = os.fork()
    if child == 0:
        os.close(read_fd)
        os.chdir(cwd)
        grandchild = os.fork()
        if grandchild == 0:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(("127.0.0.1", 0))
            sock.listen(1)
            port = sock.getsockname()[1]
            os.write(write_fd, ("%d,%d" % (os.getpid(), port)).encode())
            os.close(write_fd)
            time.sleep(120)
            os._exit(0)
        os.close(write_fd)
        os._exit(0)  # the immediate child exits now; pid 1 adopts the grandchild
    os.close(write_fd)
    data = os.read(read_fd, 64).decode()
    os.close(read_fd)
    os.waitpid(child, 0)  # reap the immediate child so it never lingers as a zombie
    pid_text, port_text = data.split(",")
    pid = int(pid_text)
    port = int(port_text)

    # MEASURED, 2026-09-24, under `wsl -e python3 ...` invoked from Windows: WSL2's own
    # "Relay" process sits between this fixture and real init, and it adopts the orphan
    # itself (a genuine subreaper -- PR_SET_CHILD_SUBREAPER -- not a defect). The brief's own
    # rule ("Do not treat a subreaper as orphaned, stricter is safe") means
    # `sweep.is_orphan_linux` is RIGHT to answer "not orphaned" for that shape. This fixture
    # cannot exercise the true-orphan path on an invocation like that, so it checks its own
    # result independently of sweep.py (never trusting the code under test to grade itself)
    # and skips with a named reason instead of asserting a false failure.
    real_ppid = _real_ppid_posix(pid)
    if real_ppid not in (1, None):
        os.kill(pid, signal.SIGKILL)
        raise unittest.SkipTest(
            "the fork-orphan fixture was adopted by pid %d, not init (pid 1) -- a subreaper "
            "sits between this process and init on this invocation (see this function's own "
            "comment). sweep.is_orphan is correct to answer 'not orphaned' here, so this "
            "fixture cannot prove the true-orphan path this way, on this platform right now."
            % real_ppid
        )

    def cleanup():
        os.kill(pid, signal.SIGKILL)

    return pid, port, cleanup


def _platform_read_name(kind: str) -> str:
    """The module-level `sweep.<name>` this platform's dispatcher (`process_cwd` / `is_orphan`
    / `is_current_user_process`) actually calls for its real per-OS read, so a test can
    monkeypatch THAT read alone -- the lsof/proc read on POSIX, the PEB read on Windows --
    while the dispatcher itself keeps running for real."""
    if kind == "cwd":
        if sys.platform == "darwin":
            return "_process_cwd_macos"
        if sys.platform.startswith("linux"):
            return "_process_cwd_linux"
        return "_process_cwd_windows"
    if kind == "orphan":
        if sys.platform == "darwin":
            return "_is_orphan_posix_ppid"
        if sys.platform.startswith("linux"):
            return "_is_orphan_linux"
        return "_is_orphan_windows"
    if kind == "owner":
        if sys.platform == "darwin":
            return "_is_current_user_posix_uid"
        if sys.platform.startswith("linux"):
            return "_is_current_user_linux"
        return "_is_current_user_windows"
    raise ValueError(kind)


class _BreakRead:
    """Context manager: monkeypatches `sweep.<name>` (a real per-OS read primitive) to always
    answer `None` -- "could not tell", never a guessed confident answer -- restoring the
    original afterward even if the body raises."""

    def __init__(self, name: str):
        self.name = name

    def __enter__(self):
        self.original = getattr(sweep, self.name)
        setattr(sweep, self.name, lambda *a, **k: None)
        return self

    def __exit__(self, *exc_info):
        setattr(sweep, self.name, self.original)
        return False


class _Stub:
    """Context manager: replaces `sweep.<name>` with FN, restoring it afterward."""

    def __init__(self, name, fn):
        self.name, self.fn = name, fn

    def __enter__(self):
        self.original = getattr(sweep, self.name)
        setattr(sweep, self.name, self.fn)

    def __exit__(self, *exc_info):
        setattr(sweep, self.name, self.original)
        return False


class _FakeLsof:
    """Context manager: `sweep.subprocess.run` answers CODE and OUT, or raises EXC."""

    def __init__(self, code=0, out="", exc=None):
        self.code, self.out, self.exc = code, out, exc

    def __enter__(self):
        self.original = sweep.subprocess.run

        def fake(*a, **k):
            if self.exc:
                raise self.exc
            return subprocess.CompletedProcess(a, self.code, self.out, "")
        sweep.subprocess.run = fake

    def __exit__(self, *exc_info):
        sweep.subprocess.run = self.original
        return False


# --------------------------------------------------------------------------- shared fixtures
#
# MAIN carries the branch shapes every branch-decision arm needs, off one shared history, pushed
# to a real bare remote so `git cherry` and `git for-each-ref --contains` both read real history:
#
#   main               the base itself
#   ancestor-work      never moved past main: the ancestor test alone proves it safe
#   rebased-work       a commit whose PATCH main also carries, under a DIFFERENT commit id (a
#                      real rebase). THE ANCHOR ARM: only `git cherry` sees through this.
#   unmerged-work      one commit found nowhere else at all: the true only-copy case
#   pushed-work        a commit as unique as unmerged-work's, but pushed to the remote: only the
#                      remote-contains test proves it safe
#   backup/experiment  under the default protected prefix, unique and unpushed, to prove the
#                      prefix refusal fires before the (otherwise reapable) emptiness test
#   wip-current        checked out as MAIN's own HEAD, to prove the checked-out refusal
BASEREMOTE = os.path.join(ROOT, "base-remote.git")
MAIN = os.path.join(ROOT, "main-repo")


def build_main_fixture():
    os.makedirs(BASEREMOTE, exist_ok=True)
    run_vcs(BASEREMOTE, "init", "-q", "--bare")
    make_repo(MAIN, {"base.txt": "base\n"})
    run_vcs(MAIN, "remote", "add", "origin", BASEREMOTE)
    push = run_vcs(MAIN, "push", "-q", "origin", "main")
    require(push.returncode == 0, "pushing MAIN's main failed: %s" % push.stderr.strip())
    run_vcs(MAIN, "remote", "set-head", "origin", "main")

    run_vcs(MAIN, "checkout", "-q", "-b", "ancestor-work")
    run_vcs(MAIN, "checkout", "-q", "main")

    run_vcs(MAIN, "checkout", "-q", "-b", "rebased-work")
    write(os.path.join(MAIN, "r.txt"), "same patch\n")
    run_vcs(MAIN, "add", "r.txt")
    run_vcs(MAIN, *IDENT, "commit", "-q", "-m", "add r.txt on rebased-work")
    run_vcs(MAIN, "checkout", "-q", "main")
    write(os.path.join(MAIN, "r.txt"), "same patch\n")  # identical content, its own commit
    run_vcs(MAIN, "add", "r.txt")
    run_vcs(MAIN, *IDENT, "commit", "-q", "-m", "add r.txt directly on main")

    run_vcs(MAIN, "checkout", "-q", "-b", "unmerged-work")
    write(os.path.join(MAIN, "u.txt"), "found nowhere else\n")
    run_vcs(MAIN, "add", "u.txt")
    run_vcs(MAIN, *IDENT, "commit", "-q", "-m", "unmerged-work's only copy")
    run_vcs(MAIN, "checkout", "-q", "main")

    run_vcs(MAIN, "checkout", "-q", "-b", "pushed-work")
    write(os.path.join(MAIN, "p.txt"), "pushed to the remote\n")
    run_vcs(MAIN, "add", "p.txt")
    run_vcs(MAIN, *IDENT, "commit", "-q", "-m", "pushed-work's commit")
    pushb = run_vcs(MAIN, "push", "-q", "origin", "pushed-work")
    require(pushb.returncode == 0, "pushing pushed-work failed: %s" % pushb.stderr.strip())
    run_vcs(MAIN, "checkout", "-q", "main")

    run_vcs(MAIN, "checkout", "-q", "-b", "backup/experiment")
    write(os.path.join(MAIN, "b.txt"), "protected by prefix, not by content\n")
    run_vcs(MAIN, "add", "b.txt")
    run_vcs(MAIN, *IDENT, "commit", "-q", "-m", "backup/experiment's own commit")
    run_vcs(MAIN, "checkout", "-q", "main")

    run_vcs(MAIN, "checkout", "-q", "-b", "wip-current")  # left checked out on purpose

    pushm = run_vcs(MAIN, "push", "-q", "origin", "main")
    require(pushm.returncode == 0, "re-pushing main failed: %s" % pushm.stderr.strip())
    fetch = run_vcs(MAIN, "fetch", "-q", "origin")
    require(fetch.returncode == 0, "fetching origin failed: %s" % fetch.stderr.strip())

    head = run_vcs(MAIN, "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD")
    require(head.returncode == 0 and head.stdout.strip() == "origin/main",
            "origin/HEAD in MAIN does not resolve to origin/main: %r" % head.stdout.strip())
    cherry = run_vcs(MAIN, "cherry", "origin/main", "rebased-work")
    require(not any(line.startswith("+") for line in cherry.stdout.splitlines()),
            "rebased-work still carries a `+` against origin/main: %r" % cherry.stdout)


def setUpModule():
    os.environ["CLAUDE_CONFIG_DIR"] = CFG
    build_main_fixture()


def tearDownModule():
    shutil.rmtree(ROOT, ignore_errors=True)


# --------------------------------------------------------------------------- the anchor arm


class AnchorArmTests(unittest.TestCase):
    """The rebase-ghost fixture. Plan: 'The anchor arm is the rebase ghost. It must go red
    against a keep rule that tests ancestry alone.'"""

    def test_ancestry_alone_is_blind_to_the_rebase(self):
        branches = sweep.list_local_branches(MAIN)
        self.assertTrue(len(branches) > 0, "branch list must not be empty before any verdict")
        self.assertIn("rebased-work", branches)

        base = guard.resolve_default_base(MAIN)
        self.assertIsNotNone(base)

        # A keep rule that tests ancestry ALONE (Banchi's rule this build replaces) says KEEP,
        # because a rebase gave the commit a new id: ancestry cannot see the patch it carries.
        ancestor = guard.branch_is_ancestor(MAIN, base, "rebased-work")
        self.assertFalse(
            ancestor, "an ancestry-only rule must fail to see the rebase, or this arm proves "
                      "nothing this build exists for"
        )

    def test_the_patch_test_sees_through_the_rebase_and_reaps(self):
        branches = sweep.list_local_branches(MAIN)
        self.assertTrue(len(branches) > 0)
        self.assertIn("rebased-work", branches)

        base = guard.resolve_default_base(MAIN)
        self.assertIsNotNone(base)
        decision = sweep.decide_branch(MAIN, base, "rebased-work",
                                        sweep.DEFAULT_PROTECTED_PREFIXES, set())
        self.assertEqual(decision["action"], "reap")
        self.assertEqual(decision["reason"], "cherry-empty")


# --------------------------------------------------------------------------- branch decisions


class BranchDecisionTests(unittest.TestCase):
    def setUp(self):
        self.branches = sweep.list_local_branches(MAIN)
        self.assertTrue(len(self.branches) > 0, "branch list must not be empty")
        self.base = guard.resolve_default_base(MAIN)
        self.assertIsNotNone(self.base)

    def decide(self, branch, checked_out=frozenset(), prefixes=sweep.DEFAULT_PROTECTED_PREFIXES):
        self.assertIn(branch, self.branches, "the branch under test must be a real fixture branch")
        return sweep.decide_branch(MAIN, self.base, branch, prefixes, checked_out)

    def test_ancestor_reaps(self):
        decision = self.decide("ancestor-work")
        self.assertEqual(decision["action"], "reap")
        self.assertEqual(decision["reason"], "ancestor")

    def test_on_remote_reaps(self):
        decision = self.decide("pushed-work")
        self.assertEqual(decision["action"], "reap")
        self.assertEqual(decision["reason"], "on-remote")

    def test_unmerged_and_on_no_remote_is_the_only_copy_and_is_kept(self):
        decision = self.decide("unmerged-work")
        self.assertEqual(decision["action"], "keep")
        self.assertEqual(decision["reason"], "only-copy")

    # ------------------------------------------------------------- refusal 1: protected prefix
    def test_refusal_protected_prefix(self):
        # backup/experiment is unique and unpushed, so the emptiness test alone would REAP it.
        # The prefix refusal must still win and keep it.
        decision = self.decide("backup/experiment")
        self.assertEqual(decision["action"], "keep")
        self.assertTrue(decision["reason"].startswith("protected-prefix:"))

    def test_refusal_protected_prefix_from_the_opt_out_file(self):
        decision = self.decide("unmerged-work", prefixes=("backup/", "unmerged-"))
        self.assertEqual(decision["action"], "keep")
        self.assertEqual(decision["reason"], "protected-prefix:unmerged-")

    # ------------------------------------------------------------- refusal 2: checked out
    def test_refusal_checked_out_branch(self):
        decision = self.decide("wip-current", checked_out={"wip-current"})
        self.assertEqual(decision["action"], "keep")
        self.assertEqual(decision["reason"], "checked-out")

    # ------------------------------------------------------------- refusal 6: main/master/HEAD
    def test_refusal_default_branch_itself(self):
        decision = self.decide("main")
        self.assertEqual(decision["action"], "keep")
        self.assertEqual(decision["reason"], "default-branch")

    # ------------------------------------------------------------- refusal 7: unreadable subject
    @unittest.skipIf(
        os.name == "nt",
        "Windows CreateProcess resolves a list-form subprocess call by appending only .exe, so "
        "this PATH-shadowing git.cmd stand-in is never reached, and the real git answers "
        "instead of blind git. See "
        "decisions/list-form-subprocess-ignores-a-path-shim-on-windows.md.",
    )
    def test_refusal_unreadable_subject_is_kept(self):
        blind = os.path.join(ROOT, "blind-branch")
        make_blind_git(blind)
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = blind + os.pathsep + old_path
        try:
            decision = self.decide("unmerged-work")
        finally:
            os.environ["PATH"] = old_path
        self.assertEqual(decision["action"], "keep")
        self.assertEqual(decision["reason"], "unreadable-subject")


class BaseResolutionRefusalTests(unittest.TestCase):
    """Refusal: no default branch answers (no origin/HEAD, no local main, no local master), so
    the whole repository is refused and reaps nothing, rather than guessed at."""

    def test_no_default_base_refuses_the_whole_repository(self):
        root = os.path.join(ROOT, "no-base-repo")
        make_repo(root, {"f.txt": "x\n"}, branch="trunk")
        run_vcs(root, "checkout", "-q", "-b", "topic")
        write(os.path.join(root, "t.txt"), "unique\n")
        run_vcs(root, "add", "t.txt")
        run_vcs(root, *IDENT, "commit", "-q", "-m", "topic's only copy")
        run_vcs(root, "checkout", "-q", "trunk")

        branches = sweep.list_local_branches(root)
        self.assertTrue(len(branches) > 0, "branch list must not be empty")
        self.assertIsNone(guard.resolve_default_base(root))

        result = sweep.sweep_repo(root, confirm=False, restore_log_path=os.path.join(ROOT, "x.log"))
        self.assertEqual(result["refused"], "no-default-base")
        self.assertEqual(result["branches"], [])


# --------------------------------------------------------------------------- worktree decisions


class WorktreeDecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = os.path.join(ROOT, "wt-repo")
        make_repo(cls.root, {"f.txt": "base\n"})
        give_remote(cls.root)

        cls.dirty = os.path.join(ROOT, "wt-dirty")
        run_vcs(cls.root, "worktree", "add", "-q", cls.dirty, "-b", "lane-dirty")
        write(os.path.join(cls.dirty, "new.txt"), "uncommitted\n")

        cls.locked = os.path.join(ROOT, "wt-locked")
        run_vcs(cls.root, "worktree", "add", "-q", cls.locked, "-b", "lane-locked")
        lock = run_vcs(cls.root, "worktree", "lock", cls.locked, "--reason", "held by lane-x")
        require(lock.returncode == 0, "locking wt-locked failed: %s" % lock.stderr.strip())

        cls.live = os.path.join(ROOT, "wt-live")
        run_vcs(cls.root, "worktree", "add", "-q", cls.live, "-b", "lane-live")
        started = this_process_start_ms()
        write_session("live-session-case", os.getpid(), started, cls.live)

        cls.dead = os.path.join(ROOT, "wt-dead")
        run_vcs(cls.root, "worktree", "add", "-q", cls.dead, "-b", "lane-dead")
        # A record naming THIS SAME live pid, but a startedAt far BEHIND the real creation time:
        # the recycled-pid shape (a new process, created well after some old record's claimed
        # start). A backwards clock step between a session's own two original measurements
        # produces the exact same shape for a process that never died -- the two are
        # indistinguishable from this reading alone (decisions/liveness-read-is-platform-
        # specific-and-unreadable-is-not-death.md). So this arm must read as UNREADABLE, not a
        # confident dead, and the sweep must keep it rather than reap it.
        write_session("mismatched-start-case", os.getpid(), started - 10_000_000, cls.dead)

        cls.removable = os.path.join(ROOT, "wt-removable")
        run_vcs(cls.root, "worktree", "add", "-q", cls.removable, "-b", "lane-removable")

        entries = sweep.parse_worktree_list(cls.root)
        require(entries is not None and len(entries) >= 6, "worktree list did not build as expected")
        cls.entries = {e["path"]: e for e in entries}

    def entry_for(self, path):
        self.assertTrue(len(self.entries) > 0, "worktree list must not be empty")
        # git worktree list can realpath differently on macOS (/tmp vs /private/tmp); resolve
        # both sides the same way the sweep itself does before comparing.
        target = os.path.normcase(os.path.realpath(path))
        for p, e in self.entries.items():
            if os.path.normcase(os.path.realpath(p)) == target:
                return e
        self.fail("no worktree-list entry found for %r among %r" % (path, list(self.entries)))

    # ------------------------------------------------------------- refusal 3: dirty
    def test_refusal_dirty_worktree(self):
        decision = sweep.decide_worktree(self.root, self.entry_for(self.dirty))
        self.assertEqual(decision["action"], "keep")
        self.assertEqual(decision["reason"], "dirty")

    # ------------------------------------------------------------- refusal 5: locked
    def test_refusal_locked_worktree_names_its_holder(self):
        decision = sweep.decide_worktree(self.root, self.entry_for(self.locked))
        self.assertEqual(decision["action"], "keep")
        self.assertTrue(decision["reason"].startswith("locked:"))
        self.assertIn("held by lane-x", decision["reason"])

    # ------------------------------------------------------------- refusal 4: live session
    def test_refusal_live_session_worktree(self):
        decision = sweep.decide_worktree(self.root, self.entry_for(self.live))
        self.assertEqual(decision["action"], "keep")
        self.assertEqual(decision["reason"], "live-session")

    def test_mismatched_start_time_reads_as_unreadable_not_dead(self):
        """A record whose stored start time reads far BEHIND the live process's own start time
        is the recycled-pid shape -- but a backwards clock step between a session's own two
        original measurements produces that exact same shape for a process that never died.
        The two are indistinguishable from this one reading, so the sweep must keep the
        worktree as unreadable, never confidently reap it. This test's NAME is also what
        janitor/mutate_sweep.py's liveness mutant requires as its kill proof: the mutant
        (matching pid alone, ignoring the recorded start time) answers "live-session" here
        instead of "unreadable-subject", so this case still catches it."""
        decision = sweep.decide_worktree(self.root, self.entry_for(self.dead))
        self.assertEqual(decision["action"], "keep")
        self.assertEqual(decision["reason"], "unreadable-subject")

    def test_clean_unlocked_no_session_worktree_is_removable(self):
        decision = sweep.decide_worktree(self.root, self.entry_for(self.removable), attended=True)
        self.assertEqual(decision["action"], "reap")
        self.assertEqual(decision["reason"], "removable")

    # ------------------------------------------------------------- refusal 7: unreadable subject
    @unittest.skipIf(
        os.name == "nt",
        "Windows CreateProcess resolves a list-form subprocess call by appending only .exe, so "
        "this PATH-shadowing git.cmd stand-in is never reached, and the real git answers "
        "instead of blind git. See "
        "decisions/list-form-subprocess-ignores-a-path-shim-on-windows.md.",
    )
    def test_refusal_unreadable_subject_worktree(self):
        blind = os.path.join(ROOT, "blind-worktree")
        make_blind_git(blind)
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = blind + os.pathsep + old_path
        try:
            decision = sweep.decide_worktree(self.root, self.entry_for(self.removable))
        finally:
            os.environ["PATH"] = old_path
        self.assertEqual(decision["action"], "keep")
        self.assertEqual(decision["reason"], "unreadable-subject")


class StaleAgentLockTests(unittest.TestCase):
    """A claude agent lock (`claude agent agent-<id> (pid N start <UTC date>)`) is stale when its
    pid is dead, or alive with another start time. A stale lock no longer keeps the worktree; the
    worktree must then be clean and fully pushed. Any other lock reason keeps."""

    @classmethod
    def setUpClass(cls):
        cls.root = os.path.join(ROOT, "stale-lock-repo")
        make_repo(cls.root, {"f.txt": "base\n"})
        give_remote(cls.root)

        gone = subprocess.Popen([sys.executable, "-c", "pass"])
        gone.wait()
        cls.dead_pid = gone.pid
        own = time.strftime("%a %b %e %H:%M:%S %Y",
                            time.gmtime(this_process_start_ms() / 1000))
        cls.reasons = {
            "dead": "claude agent agent-dead (pid %d start %s)" % (cls.dead_pid, own),
            "running": "claude agent agent-run (pid %d start %s)" % (os.getpid(), own),
            "reused": "claude agent agent-reuse (pid %d start Thu Jan  1 00:00:00 2015)"
                      % os.getpid(),
            "garbled": "claude agent agent-bad (pid %d start no-date)" % cls.dead_pid,
        }
        cls.wt = {}
        for name, reason in cls.reasons.items():
            cls.wt[name] = cls.add(name, reason)
        cls.wt["unpushed"] = cls.add("unpushed", cls.reasons["dead"])
        write(os.path.join(cls.wt["unpushed"], "g.txt"), "only here\n")
        run_vcs(cls.wt["unpushed"], "add", "-A")
        run_vcs(cls.wt["unpushed"], *IDENT, "commit", "-q", "-m", "unpushed work")
        cls.wt["detached"] = cls.add("detached", cls.reasons["dead"], detach=True)
        # Pushed to a remote branch, NOT merged into main: the pushed check must count it alone.
        write(os.path.join(cls.wt["detached"], "d.txt"), "pushed, not merged\n")
        run_vcs(cls.wt["detached"], "add", "-A")
        run_vcs(cls.wt["detached"], *IDENT, "commit", "-q", "-m", "detached pushed work")
        pushed = run_vcs(cls.wt["detached"], "push", "-q", "origin", "HEAD:refs/heads/remote-only")
        require(pushed.returncode == 0, "push of the detached commit failed: %s" % pushed.stderr.strip())
        # No lock at all: the pushed check covers every reap, not only a stale agent lock.
        cls.wt["free_unpushed"] = os.path.join(ROOT, "stale-lock-free-unpushed")
        run_vcs(cls.root, "worktree", "add", "-q", "--detach", cls.wt["free_unpushed"], "main")
        write(os.path.join(cls.wt["free_unpushed"], "h.txt"), "only here\n")
        run_vcs(cls.wt["free_unpushed"], "add", "-A")
        run_vcs(cls.wt["free_unpushed"], *IDENT, "commit", "-q", "-m", "unpushed detached")
        cls.wt["other"] = cls.add("other", "held by lane-x")
        entries = sweep.parse_worktree_list(cls.root)
        cls.entries = {os.path.normcase(os.path.realpath(e["path"])): e for e in entries}

    @classmethod
    def add(cls, name, reason, detach=False):
        path = os.path.join(ROOT, "stale-lock-" + name)
        args = ["worktree", "add", "-q", path]
        args += ["--detach", "main"] if detach else ["-b", "lane-stale-" + name]
        require(run_vcs(cls.root, *args).returncode == 0, "worktree add %s failed" % name)
        require(run_vcs(cls.root, "worktree", "lock", path, "--reason", reason).returncode == 0,
                "lock %s failed" % name)
        return path

    def decide(self, name):
        entry = self.entries[os.path.normcase(os.path.realpath(self.wt[name]))]
        return sweep.decide_worktree(self.root, entry, attended=True)

    def test_dead_pid_lock_is_stale_and_pushed_worktree_is_removable(self):
        decision = self.decide("dead")
        self.assertEqual(decision["action"], "reap")
        self.assertTrue(decision.get("unlock"))

    def test_detached_head_on_a_pushed_commit_counts_as_pushed(self):
        path = self.wt["detached"]
        # The fixture's point: the commit is not an ancestor of main (exit 1), yet it is pushed.
        self.assertEqual(run_vcs(path, "merge-base", "--is-ancestor", "HEAD", "main").returncode, 1)
        self.assertIs(sweep.fully_pushed(path), True)
        self.assertEqual(self.decide("detached")["action"], "reap")

    def test_reused_pid_with_other_start_time_is_stale(self):
        self.assertEqual(self.decide("reused")["action"], "reap")

    def test_running_agent_lock_keeps(self):
        decision = self.decide("running")
        self.assertEqual(decision["action"], "keep")
        self.assertTrue(decision["reason"].startswith("locked:"))

    def test_unreadable_lock_start_keeps(self):
        decision = self.decide("garbled")
        self.assertEqual(decision["action"], "keep")
        self.assertTrue(decision["reason"].startswith("locked:"))

    def test_other_lock_reason_keeps(self):
        self.assertEqual(self.decide("other")["action"], "keep")

    def test_unlocked_clean_detached_worktree_with_an_unpushed_commit_keeps(self):
        decision = self.decide("free_unpushed")
        self.assertEqual(decision["action"], "keep")
        self.assertTrue(decision["reason"].startswith("unpushed:"))

    def test_stale_lock_with_unpushed_commit_keeps(self):
        decision = self.decide("unpushed")
        self.assertEqual(decision["action"], "keep")
        self.assertTrue(decision["reason"].startswith("unpushed:"))

    def test_remove_unlocks_then_removes_without_force(self):
        path = self.add("removal", self.reasons["dead"])
        decision = sweep.decide_worktree(
            self.root, {"path": path, "locked_reason": self.reasons["dead"]},
            attended=True)
        self.assertEqual(decision["action"], "reap")
        sweep.remove_worktree(self.root, path, decision)
        self.assertNotIn("error", decision)
        self.assertFalse(os.path.exists(path))

    def test_failed_remove_restores_the_lock(self):
        path = self.add("failremove", self.reasons["dead"])
        write(os.path.join(path, "dirty.txt"), "git refuses to remove this without --force\n")
        decision = {"path": path, "action": "reap", "unlock": True,
                    "lock_reason": self.reasons["dead"]}
        sweep.remove_worktree(self.root, path, decision)
        self.assertIn("remove failed", decision["error"])
        self.assertIn("lock restored", decision["error"])
        self.assertTrue(os.path.isdir(path))
        self.assertTrue(guard.worktree_locked(self.root, path))
        entry = [e for e in sweep.parse_worktree_list(self.root)
                 if os.path.realpath(e["path"]) == os.path.realpath(path)][0]
        self.assertEqual(entry["locked_reason"], self.reasons["dead"])

    @unittest.skipIf(not hasattr(time, "tzset"), "no time.tzset on this platform")
    def test_lock_date_is_read_as_utc_in_a_non_utc_zone(self):
        old = os.environ.get("TZ")
        os.environ["TZ"] = "America/Chicago"
        time.tzset()
        try:
            self.assertIs(sweep.stale_agent_lock_verdict(self.reasons["running"]), False)
        finally:
            if old is None:
                del os.environ["TZ"]
            else:
                os.environ["TZ"] = old
            time.tzset()

    def test_unreadable_process_start_is_unknown_not_stale(self):
        real = guard._process_start_ms
        sys.modules["guard_core"]._process_start_ms = lambda pid: guard.PROCESS_START_UNREADABLE
        try:
            self.assertIsNone(sweep.stale_agent_lock_verdict(self.reasons["dead"]))
        finally:
            sys.modules["guard_core"]._process_start_ms = real

    def test_unreadable_pushed_check_keeps(self):
        real = sweep.fully_pushed
        sweep.fully_pushed = lambda path: None
        try:
            decision = self.decide("detached")
        finally:
            sweep.fully_pushed = real
        self.assertEqual(decision["action"], "keep")
        self.assertEqual(decision["reason"], "unreadable-subject")

    def test_a_repository_with_no_remote_keeps_every_worktree(self):
        root = os.path.join(ROOT, "no-remote-repo")
        make_repo(root, {"f.txt": "base\n"})
        path = os.path.join(ROOT, "no-remote-wt")
        run_vcs(root, "worktree", "add", "-q", "--detach", path, "main")
        decision = sweep.decide_worktree(root, {"path": path}, attended=True)
        self.assertEqual(decision["action"], "keep")
        self.assertTrue(decision["reason"].startswith("unpushed:"))

    def test_preview_never_unlocks(self):
        sweep.sweep_repo(self.root, confirm=False, restore_log_path=os.path.join(ROOT, "p.log"))
        self.assertTrue(guard.worktree_locked(self.root, self.wt["dead"]))


class ListenerDecisionTests(unittest.TestCase):
    """`sweep.find_swept_listeners` / `sweep.decide_listener`, this build's own subject. Every
    listener here is a REAL process this suite starts itself (`spawn_plain_listener` /
    `spawn_orphaned_listener`, defined above) -- never a mock, for the same reason
    hooks/test_guard.py and this file's own git fixtures never mock git."""

    @classmethod
    def setUpClass(cls):
        cls.root = os.path.join(ROOT, "listener-repo")
        make_repo(cls.root, {"f.txt": "base\n"})
        give_remote(cls.root)

        cls.reap_wt = os.path.join(ROOT, "wt-listener-reap")
        run_vcs(cls.root, "worktree", "add", "-q", cls.reap_wt, "-b", "lane-listener-reap")
        cls.live_wt = os.path.join(ROOT, "wt-listener-live")
        run_vcs(cls.root, "worktree", "add", "-q", cls.live_wt, "-b", "lane-listener-live")
        cls.plain_wt = os.path.join(ROOT, "wt-listener-plain")
        run_vcs(cls.root, "worktree", "add", "-q", cls.plain_wt, "-b", "lane-listener-plain")

        cls.cleanups = []
        cls.reap_pid, cls.reap_port, reap_cleanup = spawn_orphaned_listener(cls.reap_wt)
        cls.cleanups.append(reap_cleanup)
        # Also orphaned: the ONLY difference from reap_wt is the live-session record below.
        # Without that, this fixture would reach the same "orphaned-listener" verdict, and
        # would prove nothing about the live-session refusal specifically.
        cls.live_pid, cls.live_port, live_cleanup = spawn_orphaned_listener(cls.live_wt)
        cls.cleanups.append(live_cleanup)
        cls.plain_pid, cls.plain_port, plain_cleanup = spawn_plain_listener(cls.plain_wt)
        cls.cleanups.append(plain_cleanup)

        started = this_process_start_ms()
        write_session("listener-live-session-case", os.getpid(), started, cls.live_wt)

        cls.checkout_paths = [cls.root, cls.reap_wt, cls.live_wt, cls.plain_wt]

        cls.outside_root = os.path.join(ROOT, "listener-outside-repo")
        make_repo(cls.outside_root, {"f.txt": "base\n"})

    @classmethod
    def tearDownClass(cls):
        for cleanup in reversed(cls.cleanups):
            try:
                cleanup()
            except Exception:
                pass

    def _entry_for(self, pid):
        found = sweep.find_swept_listeners(self.checkout_paths)
        self.assertIsNotNone(found, "listener enumeration must not fail on a real machine")
        self.assertTrue(len(found) > 0, "listener list must not be empty before any verdict")
        for entry in found:
            if entry["pid"] == pid:
                return entry
        self.fail("pid %r not found among swept listeners: %r"
                  % (pid, [e["pid"] for e in found]))

    def test_orphaned_listener_no_live_session_is_reaped(self):
        decision = sweep.decide_listener(self._entry_for(self.reap_pid))
        self.assertEqual(decision["action"], "reap")
        self.assertEqual(decision["reason"], "orphaned-listener")

    def test_orphaned_listener_with_live_session_is_kept(self):
        decision = sweep.decide_listener(self._entry_for(self.live_pid))
        self.assertEqual(decision["action"], "keep")
        self.assertEqual(decision["reason"], "live-session")

    def test_non_orphaned_listener_is_kept(self):
        decision = sweep.decide_listener(self._entry_for(self.plain_pid))
        self.assertEqual(decision["action"], "keep")
        self.assertEqual(decision["reason"], "not-orphaned")

    def test_owner_mismatch_is_kept(self):
        """No account switch is available to this suite (no admin privilege to run a fixture
        process as a genuinely different user), so this stubs `sweep.is_current_user_process`
        itself -- the same seam `hooks/test_guard.py` already stubs `ctypes.windll` at, for a
        Windows arm no fixture can drive for real either (decisions/liveness-read-is-platform-
        specific-and-unreadable-is-not-death.md, "Holes, named"). `self.reap_pid`'s entry is
        otherwise the exact reap shape (orphaned, no live session), so a confirmed "not ours"
        answer is the ONLY thing standing between it and a reap here."""
        original = sweep.is_current_user_process
        sweep.is_current_user_process = lambda pid: False
        try:
            decision = sweep.decide_listener(self._entry_for(self.reap_pid))
        finally:
            sweep.is_current_user_process = original
        self.assertEqual(decision["action"], "keep")
        self.assertEqual(decision["reason"], "not-current-user")

    def test_listener_outside_every_swept_repo_is_never_listed(self):
        # self.outside_root is a real, swept-shaped repository, but it is not in
        # self.checkout_paths -- the same shape a repository the CURRENT sweep run was not
        # pointed at would have. None of this suite's own fixture listeners live under it.
        found = sweep.find_swept_listeners([self.outside_root])
        self.assertIsNotNone(found)
        self.assertEqual(found, [],
                          "a listener whose cwd sits outside every checkout must never be "
                          "listed, not merely kept")

    def test_sweep_repo_lists_and_reaps_the_orphan_but_keeps_the_others(self):
        """End-to-end through `sweep_repo` itself, confirm=True, against a REAL machine --
        proves the wiring in `sweep_repo` (checkout_paths, `find_swept_listeners`,
        `decide_listener`, `reap_listener`), not only the two functions above in isolation."""
        result = sweep.sweep_repo(self.root, confirm=True, restore_log_path=os.path.join(
            ROOT, "listener-restore.log"))
        self.assertIsNone(result["refused"])
        self.assertIsNotNone(result["listeners"])
        self.assertTrue(len(result["listeners"]) > 0)
        by_pid = {entry["pid"]: entry for entry in result["listeners"]}
        self.assertIn(self.reap_pid, by_pid)
        self.assertEqual(by_pid[self.reap_pid]["action"], "reap")
        self.assertIn(self.live_pid, by_pid)
        self.assertEqual(by_pid[self.live_pid]["action"], "keep")
        self.assertIn(self.plain_pid, by_pid)
        self.assertEqual(by_pid[self.plain_pid]["action"], "keep")
        # The reap really happened: give it a moment, the same grace period `main` itself
        # gives, then check the real OS-level pid.
        deadline = time.time() + 5
        while time.time() < deadline and sweep.pid_alive(self.reap_pid):
            time.sleep(0.2)
        self.assertFalse(sweep.pid_alive(self.reap_pid),
                          "sweep_repo(confirm=True) must have actually signalled the orphan")
        # Respawn it under the SAME worktree so tearDownClass's cleanup still has something
        # real to clean up, and so a second run of this same test class (unlikely, but cheap
        # to guard) is not left holding a dead pid.
        self.reap_pid, self.reap_port, new_cleanup = spawn_orphaned_listener(self.reap_wt)
        self.cleanups[0] = new_cleanup


class UnreadableListenerReadTests(unittest.TestCase):
    """Coordinator parity note, 2026-09-24: a listener's cwd/orphan/owner read, refused on
    THIS platform's OWN read path (`_platform_read_name`, above), must be kept and never
    reaped -- the same outcome on POSIX and on Windows. One real, genuinely orphaned listener
    with no live session is reused for every injection: unmodified, it reaps (see
    `test_baseline_is_reaped`), so any one of these three injected failures is exactly what
    must flip that outcome away from "reap"."""

    @classmethod
    def setUpClass(cls):
        cls.root = os.path.join(ROOT, "listener-unreadable-repo")
        make_repo(cls.root, {"f.txt": "base\n"})
        cls.wt = os.path.join(ROOT, "wt-listener-unreadable")
        run_vcs(cls.root, "worktree", "add", "-q", cls.wt, "-b", "lane-listener-unreadable")
        cls.pid, cls.port, cls.cleanup = spawn_orphaned_listener(cls.wt)
        cls.checkout_paths = [cls.root, cls.wt]

    @classmethod
    def tearDownClass(cls):
        try:
            cls.cleanup()
        except Exception:
            pass

    def _entry(self):
        found = sweep.find_swept_listeners(self.checkout_paths)
        self.assertIsNotNone(found)
        self.assertTrue(len(found) > 0, "listener list must not be empty")
        for entry in found:
            if entry["pid"] == self.pid:
                return entry
        self.fail("fixture pid not found among swept listeners")

    def test_baseline_is_reaped(self):
        decision = sweep.decide_listener(self._entry())
        self.assertEqual(decision["action"], "reap")
        self.assertEqual(decision["reason"], "orphaned-listener")

    def test_unreadable_cwd_read_means_never_matched_never_reaped(self):
        """`find_swept_listeners` reads cwd BEFORE a listener can be matched to any checkout
        at all -- a cwd this sweep cannot read cannot be told apart from a listener outside
        every checkout, and this build's own docstring (`find_swept_listeners`) chooses the
        same silent-drop direction for both, rather than name every unreadable system process
        on the machine against every repository being swept. Either way, the outcome this
        test pins is the one that matters: NEVER reaped."""
        with _BreakRead(_platform_read_name("cwd")):
            found = sweep.find_swept_listeners(self.checkout_paths)
        self.assertIsNotNone(found)
        self.assertFalse(any(entry["pid"] == self.pid for entry in found),
                          "a listener whose cwd could not be read must never be matched, "
                          "and therefore never reaped")

    def test_unreadable_orphan_read_is_kept(self):
        entry = self._entry()
        with _BreakRead(_platform_read_name("orphan")):
            decision = sweep.decide_listener(entry)
        self.assertEqual(decision["action"], "keep")
        self.assertEqual(decision["reason"], "unreadable-subject")

    def test_unreadable_owner_read_is_kept(self):
        entry = self._entry()
        with _BreakRead(_platform_read_name("owner")):
            decision = sweep.decide_listener(entry)
        self.assertEqual(decision["action"], "keep")
        self.assertEqual(decision["reason"], "unreadable-subject")


class WorktreeProcessPreCheckTests(unittest.TestCase):
    """`decide_worktree`'s pre-removal check (this build's brief, point 4): ANY process at
    all, not only a listener, sitting inside a worktree must keep it, naming the pids. Reuses
    `spawn_plain_listener` purely as a convenient real, long-lived process with a known cwd --
    what it listens on is irrelevant to this check."""

    @classmethod
    def setUpClass(cls):
        cls.root = os.path.join(ROOT, "precheck-repo")
        make_repo(cls.root, {"f.txt": "base\n"})
        give_remote(cls.root)
        cls.occupied = os.path.join(ROOT, "wt-precheck-occupied")
        run_vcs(cls.root, "worktree", "add", "-q", cls.occupied, "-b", "lane-precheck-occupied")
        cls.empty = os.path.join(ROOT, "wt-precheck-empty")
        run_vcs(cls.root, "worktree", "add", "-q", cls.empty, "-b", "lane-precheck-empty")
        cls.pid, cls.port, cls.cleanup = spawn_plain_listener(cls.occupied)
        entries = sweep.parse_worktree_list(cls.root)
        require(entries is not None and len(entries) >= 2, "worktree list did not build")
        cls.entries = {e["path"]: e for e in entries}

    @classmethod
    def tearDownClass(cls):
        try:
            cls.cleanup()
        except Exception:
            pass

    def entry_for(self, path):
        target = os.path.normcase(os.path.realpath(path))
        for p, e in self.entries.items():
            if os.path.normcase(os.path.realpath(p)) == target:
                return e
        self.fail("no worktree-list entry found for %r" % path)

    def test_a_process_inside_the_worktree_keeps_it_and_names_the_pid(self):
        decision = sweep.decide_worktree(self.root, self.entry_for(self.occupied), attended=True)
        self.assertEqual(decision["action"], "keep")
        self.assertTrue(decision["reason"].startswith("process-inside:"))
        self.assertIn(str(self.pid), decision["reason"])

    def test_an_empty_worktree_is_still_removable(self):
        decision = sweep.decide_worktree(self.root, self.entry_for(self.empty), attended=True)
        self.assertEqual(decision["action"], "reap")
        self.assertEqual(decision["reason"], "removable")

    def test_unreadable_pre_check_cwd_read_is_out_of_scope_not_a_keep(self):
        """Coordinator parity note, 2026-09-24, resolved by measurement: a refused cwd read
        for ONE pid during this pre-check does NOT keep the worktree, on POSIX or on Windows
        (`decide_worktree` has no OS branch here at all -- both dispatch through the same
        `process_cwd`). MEASURED, not the first guess: with EVERY pid's cwd read broken (this
        test's own injection), a real Windows machine still has ~580 running processes, and
        NONE of them can be told apart from "the one process actually inside this worktree"
        -- so treating a single unreadable pid as a keep reason would make this pre-check
        refuse to ever reap anything, on any real machine. That is a worse outcome than the
        leak it exists to prevent, and the same direction the ORIGINAL brief already named
        for a different read: "A single process ... that refuses access is out of scope.
        Count it in the report, never act on it." Only the WHOLE enumeration failing (the
        next test below) still means keep-everything."""
        if sys.platform == "darwin":
            # macOS reads every cwd in ONE lsof call: no per-pid read left to break. The analog
            # is a table that holds other processes only (lsof skipped the unreadable ones).
            with _Stub("_all_cwds_macos", lambda: [(os.getpid(), "/elsewhere")]):
                decision = sweep.decide_worktree(self.root, self.entry_for(self.empty), attended=True)
        else:
            with _BreakRead(_platform_read_name("cwd")):
                decision = sweep.decide_worktree(self.root, self.entry_for(self.empty), attended=True)
        self.assertEqual(decision["action"], "reap")
        self.assertEqual(decision["reason"], "removable")

    def test_unreadable_pid_enumeration_keeps_the_worktree(self):
        """The OTHER half of the pre-check's own unreadable contract: the brief's own words,
        "if the whole listing ... or the pre-check enumeration fails, KEEP everything and
        remove no worktree" -- this is the whole PID listing itself failing, not one pid's cwd."""
        name = "_all_cwds_macos" if sys.platform == "darwin" else "list_all_pids"
        with _Stub(name, lambda: None):
            decision = sweep.decide_worktree(self.root, self.entry_for(self.empty), attended=True)
        self.assertEqual(decision["action"], "keep")
        self.assertEqual(decision["reason"], "unreadable-subject")


def _read_when_ready(path, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            with open(path, encoding="utf-8") as handle:
                return handle.read().strip()
        time.sleep(0.05)
    require(False, "fixture never wrote its pid file: %r" % path)


_LOOP = 'echo $$ > "$2"; i=0; while [ $i -lt 120 ]; do sleep 1; i=$((i+1)); done'


@unittest.skipIf(os.name == "nt", "the sh-loop fixture is POSIX only")
class DeadRootedServerTests(unittest.TestCase):
    """`sweep.find_dead_rooted`. Every process is a REAL `sh` loop this suite starts. The
    scratch checkout is a temp dir with `.git` whose `wt` folder never exists, so the
    script path in argv is gone but its ground is still a project."""

    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.mkdtemp(dir=ROOT)
        os.mkdir(os.path.join(cls.home, ".git"))
        os.mkdir(os.path.join(cls.home, "wt"))
        cls.dead_script = os.path.join(cls.home, "wt", "serve.sh")
        write(cls.dead_script, "true\n")
        cls.live_script = os.path.join(cls.home, "live.sh")
        write(cls.live_script, "true\n")
        shutil.rmtree(os.path.join(cls.home, "wt"))  # the checkout is gone
        cls.cleanups = []
        cls.orphan = cls._orphan(cls.dead_script)
        cls.live = cls._orphan(cls.live_script)
        cls.dead_parent = cls._orphan(os.path.join(cls.home, "gone.sh"))  # parent dir exists
        cls.child_pidfile = os.path.join(ROOT, "dr-child.pid")
        cls.child = subprocess.Popen(["sh", "-c", _LOOP, "sh", cls.dead_script, cls.child_pidfile])
        cls.cleanups.append(cls.child.kill)
        cls.child_pid = cls.child.pid

    @classmethod
    def _orphan(cls, script):
        """Double fork: the outer sh exits, pid 1 adopts the loop. Returns the loop's pid."""
        pidfile = tempfile.mktemp(dir=ROOT, suffix=".pid")
        subprocess.run(["sh", "-c", '( sh -c "$1" sh "$2" "$3" & ) ; exit 0', "sh", _LOOP,
                        script, pidfile], check=True)
        pid = int(_read_when_ready(pidfile))
        cls.cleanups.append(lambda: os.kill(pid, signal.SIGKILL))
        if _real_ppid_posix(pid) not in (1, None):
            raise unittest.SkipTest("a subreaper adopted the fixture, not init")
        return pid

    @classmethod
    def tearDownClass(cls):
        for cleanup in cls.cleanups:
            try:
                cleanup()
            except Exception:
                pass
        shutil.rmtree(cls.home, ignore_errors=True)

    def _mine(self):
        found = sweep.find_dead_rooted()
        self.assertIsNotNone(found)
        return {d["pid"]: d for d in found}

    def test_orphan_with_dead_script_is_found_and_reaped(self):
        d = self._mine()[self.orphan]
        self.assertEqual((d["action"], d["reason"]), ("reap", "dead-rooted-server"))
        self.assertEqual(d["missing"], self.dead_script)

    def test_live_script_is_ignored(self):
        self.assertNotIn(self.live, self._mine())

    def test_non_orphan_is_kept(self):
        d = self._mine()[self.child_pid]
        self.assertEqual((d["action"], d["reason"]), ("keep", "not-orphaned"))

    def test_missing_script_in_a_live_directory_is_kept(self):
        self.assertNotIn(self.dead_parent, self._mine())

    def test_script_outside_any_project_is_ignored(self):
        self.assertIsNone(sweep._project_ancestor("/nonexistent-root-xyz/a/b.sh"))


@unittest.skipIf(os.name == "nt", "the sh-loop fixture is POSIX only")
class LooseProcessTests(unittest.TestCase):
    """`sweep.find_loose_processes`. Real `sh` loops, one with a fake shell-snapshots path in
    argv and one without. The report stops nothing, `--confirm` included."""

    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.mkdtemp(dir=ROOT)
        snap = os.path.join(cls.home, ".claude", "shell-snapshots", "snapshot-zsh-1-fake.sh")
        cls.procs = []
        cls.marked = cls._start(snap)  # an orphan and a plain one: is_orphan is stubbed True for both
        cls.live = cls._start(snap + ".live")  # a live session's wrapper: parent alive
        cls.plain = cls._start(os.path.join(cls.home, "plain.sh"))
        cls.real_is_orphan = staticmethod(sweep.is_orphan)
        sweep.is_orphan = lambda pid: True if pid in (cls.marked, cls.plain) else cls.real_is_orphan(pid)

    @classmethod
    def _start(cls, arg):
        pidfile = tempfile.mktemp(dir=ROOT, suffix=".pid")
        proc = subprocess.Popen(["sh", "-c", _LOOP, "sh", arg, pidfile])
        cls.procs.append(proc)
        _read_when_ready(pidfile)
        return proc.pid

    @classmethod
    def tearDownClass(cls):
        sweep.is_orphan = cls.real_is_orphan
        for proc in cls.procs:
            proc.kill()
            proc.wait()
        shutil.rmtree(cls.home, ignore_errors=True)

    def test_marked_orphan_is_listed_and_unmarked_is_not(self):
        pids = {d["pid"] for d in sweep.find_loose_processes()}
        self.assertIn(self.marked, pids)
        self.assertNotIn(self.plain, pids)

    def test_a_live_sessions_wrapper_is_not_listed(self):
        self.assertFalse(sweep.is_orphan(self.live))
        self.assertNotIn(self.live, {d["pid"] for d in sweep.find_loose_processes()})

    def test_an_unreadable_orphan_read_is_listed_as_unknown(self):
        sweep.is_orphan = lambda pid: None if pid == self.live else True if pid in (self.marked, self.plain) \
            else self.real_is_orphan(pid)
        try:
            found = sweep.find_loose_processes()
        finally:
            sweep.is_orphan = lambda pid: True if pid in (self.marked, self.plain) else self.real_is_orphan(pid)
        entry = [d for d in found if d["pid"] == self.live]
        self.assertEqual(len(entry), 1)
        out = io.StringIO()
        sweep.print_loose_processes_report(entry, out=out)
        self.assertIn("orphan=unknown", out.getvalue())

    def test_report_lists_the_marked_process(self):
        out = io.StringIO()
        sweep.print_loose_processes_report(sweep.find_loose_processes(), out=out)
        self.assertIn("loose processes", out.getvalue())
        self.assertIn("pid=%-8s" % self.marked, out.getvalue())

    def test_unreadable_owner_is_listed_as_unknown(self):
        """An owner read that fails (`None`) lists the process; it is not left out. The stub
        answers `None` for the marked pid only, the real read for every other pid."""
        real = sweep.is_current_user_process
        sweep.is_current_user_process = lambda pid: None if pid == self.marked else real(pid)
        try:
            found = sweep.find_loose_processes()
        finally:
            sweep.is_current_user_process = real
        entry = [d for d in found if d["pid"] == self.marked]
        self.assertEqual(len(entry), 1)
        self.assertIsNone(entry[0]["owner"])
        out = io.StringIO()
        sweep.print_loose_processes_report(entry, out=out)
        self.assertIn("owner=unknown", out.getvalue())

    def test_confirm_sends_the_marked_process_no_signal(self):
        """Runs real `main --confirm` on an empty scratch repo. `find_dead_rooted` is stubbed
        so the real machine's dead-rooted tier cannot act; every signal path is recorded."""
        sent = []
        stubs = {
            (os, "kill"): lambda pid, sig: sent.append(pid),
            (sweep, "reap_listener"): lambda d: sent.append(d["pid"]),
            (sweep, "find_dead_rooted"): lambda: [],
        }
        real = {key: getattr(*key) for key in stubs}
        repo = os.path.join(self.home, "repo")
        subprocess.run(["git", "init", repo], check=True, capture_output=True)
        for key, fn in stubs.items():
            setattr(key[0], key[1], fn)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                sweep.main(["--confirm", "--restore-log", os.path.join(self.home, "log"), repo])
        finally:
            for key, fn in real.items():
                setattr(key[0], key[1], fn)
        self.assertNotIn(self.marked, sent)
        self.assertIsNone(self.procs[0].poll())


class PrimaryCheckoutExclusionTests(unittest.TestCase):
    """`sweep_repo` must never record a decision against the clone's one primary checkout, NO
    MATTER WHICH WORKTREE PATH IT WAS CALLED WITH. An earlier version of this file compared
    each worktree entry against the `root` argument alone, which is correct only when `root`
    already names the primary checkout; called with a LINKED worktree's own path instead, the
    real primary checkout used to fall through to `decide_worktree` like any other worktree and
    could be labeled `REAP removable`. `git worktree remove` on it then failed only because git
    itself refuses to remove a main working tree that way -- a refusal this suite must not lean
    on (CLAUDE.md, "a recovery control must not depend on the state it recovers"). This class
    calls `sweep_repo` with the LINKED worktree as `root`, the exact shape that exposed the
    defect, and asserts no decision was ever RECORDED for the primary checkout's path -- not
    that the directory still exists on disk, which git's own refusal could make true even with
    the defect back in place."""

    # A FRESH fixture per test method, not shared via setUpClass: a `confirm=True` case in this
    # class really does remove the linked worktree it is pointed at (it is not the primary
    # checkout, and this fixture leaves it clean/unlocked/session-free on purpose, so it is a
    # genuinely reapable worktree). Sharing one fixture across methods let an earlier `confirm`
    # case consume it before a later `preview` case ran, and that case's "at least one decision"
    # assertion failed for a reason that had nothing to do with the exclusion this class exists
    # to prove -- an empty-subject case exactly like the ones CLAUDE.md and this suite's own
    # module docstring warn against, just introduced from the test side this time.
    def setUp(self):
        # A SHORT tag, not the full test method name. An earlier version used
        # `self.id().rsplit(".", 1)[-1]` directly. This suite's method names are full
        # sentences.

        # MEASURED on a real Windows machine: git names its worktree admin directory after
        # the worktree's own basename. Here that basename is
        # `primary-checkout-linked-<full test name>`. The combined path tripped Windows' own
        # path-length ceiling: "fatal: could not create directory of
        # '.git/worktrees/...': Filename too long". The identical fixture shape works on
        # POSIX, whose path limits are far looser.

        # No production code builds a worktree name from a test's own description. This is a
        # fixture-only defect. The fix hashes the id down to something short instead.

        tag = hashlib.md5(self.id().encode("utf-8")).hexdigest()[:12]
        self.tag = tag
        self.primary = os.path.join(ROOT, "primary-checkout-%s" % tag)
        make_repo(self.primary, {"f.txt": "base\n"})
        give_remote(self.primary)

        self.linked = os.path.join(ROOT, "primary-checkout-linked-%s" % tag)
        result = run_vcs(self.primary, "worktree", "add", "-q", self.linked, "-b", "lane-x")
        require(result.returncode == 0,
                "worktree add for the exclusion fixture: %s" % result.stderr.strip())
        require(os.path.isdir(self.linked), "fixture: linked worktree exists")

    def _decisions(self, root, confirm):
        log_path = os.path.join(ROOT, "primary-exclusion-%s.log" % self.tag)
        return sweep.sweep_repo(root, confirm=confirm, restore_log_path=log_path)

    def _primary_recorded(self, result):
        primary_real = os.path.normcase(os.path.realpath(self.primary))
        for w in result["worktrees"]:
            if os.path.normcase(os.path.realpath(w["path"])) == primary_real:
                return w
        return None

    def test_no_decision_is_recorded_against_the_primary_checkout_when_swept_via_a_linked_worktree(self):
        result = self._decisions(self.linked, confirm=False)
        self.assertTrue(len(result["worktrees"]) > 0,
                         "fixture must produce at least one worktree decision to mean anything")
        recorded = self._primary_recorded(result)
        self.assertIsNone(
            recorded,
            "the primary checkout must never appear in the worktree decisions at all, got: %r"
            % (recorded,),
        )

    def test_confirm_via_a_linked_worktree_never_attempts_to_remove_the_primary_checkout(self):
        result = self._decisions(self.linked, confirm=True)
        self.assertTrue(len(result["worktrees"]) > 0,
                         "fixture must produce at least one worktree decision to mean anything")
        self.assertIsNone(self._primary_recorded(result))
        self.assertTrue(os.path.isdir(self.primary),
                         "the primary checkout must survive even a --confirm sweep")

    def test_swept_via_its_own_root_the_primary_checkout_is_still_excluded(self):
        """Same exclusion, the ordinary call shape (root IS the primary checkout), so the fix
        does not regress the case the old root-comparison already handled."""
        result = self._decisions(self.primary, confirm=False)
        self.assertTrue(len(result["worktrees"]) > 0, "fixture must produce a decision")
        self.assertIsNone(self._primary_recorded(result))


# --------------------------------------------------------------------------- discovery


class DiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = os.path.join(ROOT, "discover-root")
        os.makedirs(cls.dir, exist_ok=True)
        cls.repo = os.path.join(cls.dir, "repoA")
        make_repo(cls.repo, {"f.txt": "x\n"})
        cls.linked = os.path.join(cls.dir, "repoA-worktree")
        run_vcs(cls.repo, "worktree", "add", "-q", cls.linked, "-b", "lane")
        os.makedirs(os.path.join(cls.dir, "not-a-repo"), exist_ok=True)

    def test_discovers_ordinary_checkouts_only(self):
        found = sweep.discover_repos(self.dir)
        self.assertTrue(len(found) > 0, "discovery must not come back empty")
        self.assertIn(self.repo, found)

    def test_never_discovers_a_linked_worktree_as_its_own_repository(self):
        found = sweep.discover_repos(self.dir)
        self.assertTrue(len(found) > 0)
        self.assertNotIn(self.linked, found)

    def test_never_discovers_a_plain_directory(self):
        found = sweep.discover_repos(self.dir)
        self.assertTrue(len(found) > 0)
        self.assertNotIn(os.path.join(self.dir, "not-a-repo"), found)


# --------------------------------------------------------------------------- janitor.roots


class DefaultDiscoverRootsTests(unittest.TestCase):
    """`sweep.default_discover_roots()` reads `~/...` candidates, expanded by
    `os.path.expanduser`. This drives a fake home directory holding two of the five candidate
    directories, each with a real checkout. It restores the real environment afterward, no
    matter what.

    BOTH `HOME` AND `USERPROFILE` ARE PATCHED, not `HOME` alone. This is measured, not
    assumed. `ntpath.expanduser` is the code `os.path.expanduser` runs on Windows. It reads
    `USERPROFILE` first. It never reads `HOME` at all.

    A fixture that patches only `HOME` expands `~` against the real machine's profile
    directory on Windows. It finds fewer than two roots there. It fails with "must find both
    roots just created". That is a fixture gap. It is not a defect in
    `default_discover_roots()`, which calls the correct stdlib primitive for the platform it
    runs on.

    A SEPARATE, REAL DEFECT surfaced once that fixture gap closed. This case's own
    `os.path.join(home, "Developer")` is backslash-joined on Windows. It did not equal what
    `default_discover_roots()` returned for the same directory. That function substitutes `~`
    with a backslash path, then glues on the literal `/Developer` suffix unchanged. The two
    separators mixed. `default_discover_roots()` now runs each candidate through
    `os.path.normpath`. That is the fix, not this assertion. See that function's own
    docstring.
    """

    def test_every_existing_default_root_is_combined_not_just_the_first(self):
        home = os.path.join(ROOT, "fake-home-multi")
        developer = os.path.join(home, "Developer")
        clones = os.path.join(home, "Clones")
        os.makedirs(developer, exist_ok=True)
        os.makedirs(clones, exist_ok=True)
        repo_a = os.path.join(developer, "repoA")
        repo_b = os.path.join(clones, "repoB")
        make_repo(repo_a, {"f.txt": "x\n"})
        make_repo(repo_b, {"f.txt": "x\n"})
        old_home = os.environ.get("HOME")
        old_userprofile = os.environ.get("USERPROFILE")
        os.environ["HOME"] = home
        os.environ["USERPROFILE"] = home
        try:
            roots = sweep.default_discover_roots()
            self.assertTrue(len(roots) >= 2, "must find both roots just created")
            self.assertIn(developer, roots)
            self.assertIn(clones, roots)
            found = sweep.discover_repos_multi(roots)
        finally:
            if old_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old_home
            if old_userprofile is None:
                os.environ.pop("USERPROFILE", None)
            else:
                os.environ["USERPROFILE"] = old_userprofile
        self.assertTrue(len(found) > 0, "combined discovery must not come back empty")
        self.assertIn(repo_a, found)
        self.assertIn(repo_b, found)


class JanitorRootsSettingTests(unittest.TestCase):
    """`sweep.load_janitor_roots_setting` reads `janitor.roots` from a settings.json passed by
    path, never the real repository one. This class must not touch the checkout's own
    settings.json, which real hooks also depend on."""

    def test_missing_settings_file_reads_as_no_configured_roots(self):
        roots, ok = sweep.load_janitor_roots_setting(os.path.join(ROOT, "no-such-settings.json"))
        self.assertTrue(ok)
        self.assertIsNone(roots)

    def test_absent_janitor_key_reads_as_no_configured_roots(self):
        path = os.path.join(ROOT, "settings-roots-absent.json")
        write(path, json.dumps({"hooks": {}}))
        roots, ok = sweep.load_janitor_roots_setting(path)
        self.assertTrue(ok)
        self.assertIsNone(roots)

    def test_explicit_roots_list_is_honored_and_discoverable(self):
        explicit_dir = os.path.join(ROOT, "explicit-roots-dir")
        os.makedirs(explicit_dir, exist_ok=True)
        repo = os.path.join(explicit_dir, "repoC")
        make_repo(repo, {"f.txt": "x\n"})
        path = os.path.join(ROOT, "settings-roots-explicit.json")
        write(path, json.dumps({"janitor": {"roots": [explicit_dir]}}))
        roots, ok = sweep.load_janitor_roots_setting(path)
        self.assertTrue(ok)
        self.assertEqual(roots, [explicit_dir])
        found = sweep.discover_repos_multi(roots)
        self.assertTrue(len(found) > 0, "discovery from the explicit root must not be empty")
        self.assertIn(repo, found)

    def test_malformed_roots_not_a_list_refuses(self):
        path = os.path.join(ROOT, "settings-roots-not-list.json")
        write(path, json.dumps({"janitor": {"roots": "~/Developer"}}))
        roots, ok = sweep.load_janitor_roots_setting(path)
        self.assertFalse(ok, "a bare string is not a list of strings: it must refuse")
        self.assertIsNone(roots)

    def test_malformed_roots_non_string_item_refuses(self):
        path = os.path.join(ROOT, "settings-roots-bad-item.json")
        write(path, json.dumps({"janitor": {"roots": ["~/Developer", 7]}}))
        roots, ok = sweep.load_janitor_roots_setting(path)
        self.assertFalse(ok, "a non-string item must refuse, not be silently dropped")

    def test_malformed_janitor_key_not_an_object_refuses(self):
        path = os.path.join(ROOT, "settings-janitor-not-object.json")
        write(path, json.dumps({"janitor": "nope"}))
        roots, ok = sweep.load_janitor_roots_setting(path)
        self.assertFalse(ok)

    def test_unparseable_settings_file_refuses(self):
        path = os.path.join(ROOT, "settings-roots-broken.json")
        write(path, "{ not json at all")
        roots, ok = sweep.load_janitor_roots_setting(path)
        self.assertFalse(ok)

    def test_cli_refuses_to_discover_when_roots_is_malformed_and_no_root_given(self):
        """Traces the caller path the brief names: no explicit ROOT, no --discover, and a
        malformed janitor.roots. main() must refuse and say why. It never falls back to a
        default. Uses --settings-path so the real repository settings.json is never touched."""
        path = os.path.join(ROOT, "settings-roots-cli-malformed.json")
        write(path, json.dumps({"janitor": {"roots": [1, 2]}}))
        result = subprocess.run(
            [sys.executable, os.path.join(HERE, "sweep.py"), "--settings-path", path],
            capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("malformed", result.stderr.lower())

    def test_cli_uses_the_explicit_roots_list_when_no_root_or_discover_given(self):
        explicit_dir = os.path.join(ROOT, "cli-explicit-roots-dir")
        os.makedirs(explicit_dir, exist_ok=True)
        repo = os.path.join(explicit_dir, "repoD")
        make_repo(repo, {"f.txt": "x\n"})
        settings_path = os.path.join(ROOT, "settings-roots-cli-explicit.json")
        write(settings_path, json.dumps({"janitor": {"roots": [explicit_dir]}}))
        result = subprocess.run(
            [sys.executable, os.path.join(HERE, "sweep.py"), "--settings-path", settings_path,
             "--restore-log", os.path.join(ROOT, "cli-explicit.log")],
            capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(repo, result.stdout)


# --------------------------------------------------------------------------- the opt-out file


def make_optout_repo(name, optout_json=None):
    """A repository with one reapable branch ("feature", an ancestor of main): the subject a
    sweep would touch if it were not refused. Real git, no mocking."""
    root = os.path.join(ROOT, name)
    make_repo(root, {"f.txt": "x\n"})
    run_vcs(root, "checkout", "-q", "-b", "feature")
    run_vcs(root, "checkout", "-q", "main")
    if optout_json is not None:
        write(os.path.join(root, ".claude", "janitor.json"), optout_json)
    return root


class OptOutTests(unittest.TestCase):
    def test_absent_file_means_swept_with_the_default_prefix(self):
        root = os.path.join(ROOT, "optout-absent")
        make_repo(root, {"f.txt": "x\n"})
        enabled, prefixes, ok = sweep.load_optout(root)
        self.assertTrue(ok)
        self.assertTrue(enabled)
        self.assertEqual(prefixes, ("backup/",))

    def test_sweep_false_opts_the_whole_repository_out(self):
        root = os.path.join(ROOT, "optout-false")
        make_repo(root, {"f.txt": "x\n"})
        write(os.path.join(root, ".claude", "janitor.json"), json.dumps({"sweep": False}))
        result = sweep.sweep_repo(root, confirm=False, restore_log_path=os.path.join(ROOT, "x2.log"))
        self.assertEqual(result["refused"], "opted-out")

    def test_sweep_true_explicitly_still_sweeps(self):
        root = make_optout_repo("optout-sweep-true", json.dumps({"sweep": True}))
        branches = sweep.list_local_branches(root)
        self.assertTrue(len(branches) > 0, "branch list must not be empty before any verdict")
        self.assertIn("feature", branches)
        enabled, prefixes, ok = sweep.load_optout(root)
        self.assertTrue(ok)
        self.assertTrue(enabled)
        result = sweep.sweep_repo(root, confirm=False,
                                   restore_log_path=os.path.join(ROOT, "x-true.log"))
        self.assertIsNone(result["refused"])
        reaped = [b for b in result["branches"] if b["action"] == "reap"]
        self.assertTrue(len(reaped) > 0, "a real reapable branch must show up as reaped")

    def test_protected_prefixes_extend_the_default(self):
        root = os.path.join(ROOT, "optout-prefixes")
        make_repo(root, {"f.txt": "x\n"})
        write(os.path.join(root, ".claude", "janitor.json"),
              json.dumps({"protectedPrefixes": ["experimental/"]}))
        enabled, prefixes, ok = sweep.load_optout(root)
        self.assertTrue(ok)
        self.assertTrue(enabled)
        self.assertIn("backup/", prefixes)
        self.assertIn("experimental/", prefixes)

    def test_unparseable_file_refuses_the_whole_repository(self):
        root = os.path.join(ROOT, "optout-broken")
        make_repo(root, {"f.txt": "x\n"})
        write(os.path.join(root, ".claude", "janitor.json"), "{ not json at all")
        result = sweep.sweep_repo(root, confirm=False, restore_log_path=os.path.join(ROOT, "x3.log"))
        self.assertEqual(result["refused"], "unreadable-optout")

    # --------------------- a present key whose value is malformed refuses, not defaults ---------

    def test_sweep_string_false_refuses_the_whole_repository(self):
        # The exact regression this build guards: `"sweep": "false"`, the STRING, must never be
        # treated as truthy-and-swept. It must refuse the repository the way an unreadable file
        # does, not fall through to the permissive default.
        root = make_optout_repo("optout-sweep-string-false", json.dumps({"sweep": "false"}))
        branches = sweep.list_local_branches(root)
        self.assertTrue(len(branches) > 0, "branch list must not be empty before any verdict")
        self.assertIn("feature", branches)
        enabled, prefixes, ok = sweep.load_optout(root)
        self.assertFalse(ok, "a non-boolean sweep value must not read as ok")
        result = sweep.sweep_repo(root, confirm=False,
                                   restore_log_path=os.path.join(ROOT, "x-str.log"))
        self.assertEqual(result["refused"], "unreadable-optout")
        self.assertEqual(result["branches"], [], "a refused repository must decide on nothing")

    def test_sweep_zero_refuses_the_whole_repository(self):
        root = make_optout_repo("optout-sweep-zero", json.dumps({"sweep": 0}))
        branches = sweep.list_local_branches(root)
        self.assertTrue(len(branches) > 0, "branch list must not be empty before any verdict")
        self.assertIn("feature", branches)
        enabled, prefixes, ok = sweep.load_optout(root)
        self.assertFalse(ok, "0 is not a bool in Python's own sense here: it must refuse")
        result = sweep.sweep_repo(root, confirm=False,
                                   restore_log_path=os.path.join(ROOT, "x-zero.log"))
        self.assertEqual(result["refused"], "unreadable-optout")
        self.assertEqual(result["branches"], [])

    def test_sweep_null_refuses_the_whole_repository(self):
        root = make_optout_repo("optout-sweep-null", json.dumps({"sweep": None}))
        branches = sweep.list_local_branches(root)
        self.assertTrue(len(branches) > 0, "branch list must not be empty before any verdict")
        self.assertIn("feature", branches)
        enabled, prefixes, ok = sweep.load_optout(root)
        self.assertFalse(ok, "null is present and is not a boolean: it must refuse")
        result = sweep.sweep_repo(root, confirm=False,
                                   restore_log_path=os.path.join(ROOT, "x-null.log"))
        self.assertEqual(result["refused"], "unreadable-optout")
        self.assertEqual(result["branches"], [])

    def test_protected_prefixes_bare_string_refuses_the_whole_repository(self):
        # "archive/" the bare string is not a list, so the intended protection can be neither
        # read nor safely ignored: refuse the repository rather than silently protect nothing.
        root = make_optout_repo("optout-prefixes-bare-string",
                                 json.dumps({"protectedPrefixes": "archive/"}))
        branches = sweep.list_local_branches(root)
        self.assertTrue(len(branches) > 0, "branch list must not be empty before any verdict")
        self.assertIn("feature", branches)
        enabled, prefixes, ok = sweep.load_optout(root)
        self.assertFalse(ok, "a bare string is not a list of strings: it must refuse")
        result = sweep.sweep_repo(root, confirm=False,
                                   restore_log_path=os.path.join(ROOT, "x-prefstr.log"))
        self.assertEqual(result["refused"], "unreadable-optout")
        self.assertEqual(result["branches"], [])


# --------------------------------------------------------------------------- the tombstone


class TombstoneTests(unittest.TestCase):
    def test_reap_writes_a_tombstone_and_a_restore_log_line_before_deleting(self):
        root = os.path.join(ROOT, "tomb-repo")
        make_repo(root, {"f.txt": "x\n"})
        run_vcs(root, "checkout", "-q", "-b", "old-topic")
        run_vcs(root, "checkout", "-q", "main")  # old-topic == main's tip: an ancestor, reapable

        branches = sweep.list_local_branches(root)
        self.assertTrue(len(branches) > 0)
        self.assertIn("old-topic", branches)
        tip = run_vcs(root, "rev-parse", "old-topic").stdout.strip()
        self.assertTrue(tip)

        log_path = os.path.join(ROOT, "tomb-restore.jsonl")
        result = sweep.sweep_repo(root, confirm=True, restore_log_path=log_path)
        self.assertIsNone(result["refused"])
        decision = next(b for b in result["branches"] if b["name"] == "old-topic")
        self.assertEqual(decision["action"], "reap")
        self.assertNotIn("error", decision)

        self.assertNotIn("old-topic", sweep.list_local_branches(root))
        tomb = run_vcs(root, "rev-parse", sweep.TOMBSTONE_REF_PREFIX + "old-topic")
        self.assertEqual(tomb.returncode, 0)
        self.assertEqual(tomb.stdout.strip(), tip)

        entries = sweep.read_restore_log(log_path)
        self.assertTrue(len(entries) > 0, "restore log must not be empty")
        matches = [e for e in entries if e.get("branch") == "old-topic" and e.get("repo") == root]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["commit"], tip)
        self.assertIsInstance(matches[0]["time_ms"], int)
        self.assertLessEqual(abs(int(time.time() * 1000) - matches[0]["time_ms"]), 60_000)

    def test_a_failed_delete_still_leaves_the_tombstone_and_the_branch(self):
        """The tombstone and the log line land BEFORE the delete. If the delete then fails, the
        branch is still there (nothing lost) and the tombstone still names its tip (nothing
        unrecorded)."""
        root = os.path.join(ROOT, "tomb-repo-fail")
        make_repo(root, {"f.txt": "x\n"})
        run_vcs(root, "checkout", "-q", "-b", "old-topic-2")
        run_vcs(root, "checkout", "-q", "main")

        branches = sweep.list_local_branches(root)
        self.assertTrue(len(branches) > 0)
        self.assertIn("old-topic-2", branches)
        tip = run_vcs(root, "rev-parse", "old-topic-2").stdout.strip()

        real_git = guard._git

        def failing_git(where, *args):
            if args[:2] == ("branch", "-D"):
                return subprocess.CompletedProcess(args, 1, "", "simulated failure")
            return real_git(where, *args)

        log_path = os.path.join(ROOT, "tomb-restore-fail.jsonl")
        decision = {"name": "old-topic-2", "action": "reap", "reason": "ancestor"}
        sys.modules["guard_core"]._git = failing_git
        try:
            sweep.reap_branch(root, "old-topic-2", decision, log_path)
        finally:
            sys.modules["guard_core"]._git = real_git

        self.assertIn("error", decision)
        self.assertIn("old-topic-2", sweep.list_local_branches(root))
        tomb = run_vcs(root, "rev-parse", sweep.TOMBSTONE_REF_PREFIX + "old-topic-2")
        self.assertEqual(tomb.returncode, 0)
        self.assertEqual(tomb.stdout.strip(), tip)
        entries = sweep.read_restore_log(log_path)
        self.assertTrue(len(entries) > 0)
        self.assertTrue(any(e.get("branch") == "old-topic-2" for e in entries))

    def _reap_with_git_failing(self, name, failing_args, answer):
        """Run reap_branch on an ancestor branch while guard._git answers `answer` for the
        call whose leading args are `failing_args`. Return (decision, log_path, root)."""
        root = os.path.join(ROOT, "tomb-gitfail-" + name)
        make_repo(root, {"f.txt": "x\n"})
        run_vcs(root, "checkout", "-q", "-b", name)
        run_vcs(root, "checkout", "-q", "main")
        real_git = guard._git

        def failing_git(where, *args):
            if args[:len(failing_args)] == failing_args:
                return answer(args)
            return real_git(where, *args)

        log_path = os.path.join(ROOT, "tomb-gitfail-%s.jsonl" % name)
        decision = {"name": name, "action": "reap", "reason": "ancestor"}
        sys.modules["guard_core"]._git = failing_git
        try:
            sweep.reap_branch(root, name, decision, log_path)
        finally:
            sys.modules["guard_core"]._git = real_git
        return decision, log_path, root

    def test_a_failed_tombstone_write_stops_the_delete(self):
        for label, answer in (("rc", lambda a: subprocess.CompletedProcess(a, 1, "", "no ref")),
                              ("none", lambda a: None)):
            name = "tomb-w-" + label
            decision, log_path, root = self._reap_with_git_failing(
                name, ("update-ref",), answer)
            self.assertIn("tombstone write failed", decision.get("error", ""), label)
            self.assertIn(name, sweep.list_local_branches(root),
                          "the branch was deleted although its tombstone never landed: " + label)
            self.assertEqual(sweep.read_restore_log(log_path), [], label)

    def test_an_unresolved_branch_tip_leaves_the_branch_alone(self):
        for label, answer in (("rc", lambda a: subprocess.CompletedProcess(a, 128, "", "bad")),
                              ("none", lambda a: None)):
            name = "tomb-t-" + label
            decision, log_path, root = self._reap_with_git_failing(
                name, ("rev-parse", "refs/heads/" + name), answer)
            self.assertIn("could not resolve the branch tip", decision.get("error", ""), label)
            self.assertIn(name, sweep.list_local_branches(root), label)
            self.assertEqual(sweep.read_restore_log(log_path), [], label)


# --------------------------------------------------------------------------- worktree removal


class WorktreeRemovalTests(unittest.TestCase):
    def test_confirm_removes_a_reapable_worktree(self):
        root = os.path.join(ROOT, "wt-remove-repo")
        make_repo(root, {"f.txt": "x\n"})
        give_remote(root)
        target = os.path.join(ROOT, "wt-remove-target")
        run_vcs(root, "worktree", "add", "-q", target, "-b", "lane-remove")

        entries = sweep.parse_worktree_list(root)
        self.assertTrue(entries is not None and len(entries) > 0)

        log_path = os.path.join(ROOT, "wt-remove.log")
        result = sweep.sweep_repo(root, confirm=True, restore_log_path=log_path, attended=True)
        self.assertIsNone(result["refused"])
        matches = [w for w in result["worktrees"]
                   if os.path.normcase(os.path.realpath(w["path"]))
                   == os.path.normcase(os.path.realpath(target))]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["action"], "reap")
        self.assertNotIn("error", matches[0])
        self.assertFalse(os.path.isdir(target))


class SameRunBranchCutTests(unittest.TestCase):
    """A branch is released from "checked-out" only when the worktree holding it is removed in
    this run (confirm) or would be (preview: REAP). A kept or failed removal keeps it held."""

    def _repo(self, name, dirty=False):
        root = os.path.join(ROOT, "cut-" + name)
        make_repo(root, {"f.txt": "x\n"})
        give_remote(root)
        wt = os.path.join(ROOT, "cut-" + name + "-wt")
        run_vcs(root, "worktree", "add", "-q", wt, "-b", "lane-cut")
        if dirty:
            write(os.path.join(wt, "new.txt"), "dirty\n")
        return root, wt

    def _branch(self, result):
        found = [b for b in result["branches"] if b["name"] == "lane-cut"]
        self.assertEqual(len(found), 1)
        return found[0]

    def _sweep(self, root, confirm):
        return sweep.sweep_repo(root, confirm, os.path.join(ROOT, "cut.log"), attended=True)

    def test_preview_releases_the_branch_of_a_reap_worktree(self):
        root, _wt = self._repo("preview")
        result = self._sweep(root, False)
        self.assertEqual(self._branch(result)["action"], "reap")

    def test_confirm_removes_the_worktree_and_its_branch_in_one_run(self):
        root, wt = self._repo("confirm")
        result = self._sweep(root, True)
        self.assertEqual(self._branch(result)["action"], "reap")
        self.assertNotIn("error", self._branch(result))
        self.assertFalse(os.path.isdir(wt))
        self.assertNotIn("lane-cut", sweep.list_local_branches(root))

    def test_a_kept_worktree_keeps_its_branch_held(self):
        root, wt = self._repo("kept", dirty=True)
        result = self._sweep(root, True)
        self.assertEqual(self._branch(result)["reason"], "checked-out")
        self.assertTrue(os.path.isdir(wt))
        self.assertIn("lane-cut", sweep.list_local_branches(root))

    def test_a_second_kept_worktree_on_the_same_branch_keeps_it_held(self):
        root, wt = self._repo("twice")
        other = os.path.join(ROOT, "cut-twice-wt2")
        run_vcs(root, "worktree", "add", "-q", "--force", other, "lane-cut")
        write(os.path.join(other, "new.txt"), "dirty\n")  # this one is kept
        result = self._sweep(root, False)
        self.assertEqual(self._branch(result)["reason"], "checked-out")

    def test_a_failed_removal_keeps_the_branch_held(self):
        root, wt = self._repo("failed")
        real = sweep.remove_worktree
        sweep.remove_worktree = lambda r, p, d: d.__setitem__("error", "remove failed: stub")
        try:
            result = self._sweep(root, True)
        finally:
            sweep.remove_worktree = real
        self.assertEqual(self._branch(result)["reason"], "checked-out")
        self.assertIn("lane-cut", sweep.list_local_branches(root))


class SingleTierModeTests(unittest.TestCase):
    """`--tier1` and `--branches`, driven through `main`. Fixture per test: a stale
    registration (`gone`), a live reapable worktree (`lane-live`), a merged branch (`merged-b`)."""

    def _fixture(self, name):
        root = os.path.join(ROOT, "mode-" + name)
        make_repo(root, {"f.txt": "x\n"})
        give_remote(root)
        run_vcs(root, "branch", "merged-b")
        live = os.path.join(ROOT, "mode-" + name + "-live")
        run_vcs(root, "worktree", "add", "-q", live, "-b", "lane-live")
        gone = os.path.join(ROOT, "mode-" + name + "-gone")
        run_vcs(root, "worktree", "add", "-q", gone, "-b", "lane-gone")
        shutil.rmtree(gone)
        return root, live

    def _main(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = sweep.main(["--restore-log", os.path.join(ROOT, "mode.log")] + list(args))
        return code, out.getvalue()

    def _registered(self, root):
        return [os.path.basename(e["path"]) for e in sweep.parse_worktree_list(root)]

    def test_tier1_prunes_stale_registrations_with_no_confirm_and_touches_nothing_else(self):
        root, live = self._fixture("tier1")
        before = self._registered(root)
        self.assertTrue(any(n.endswith("-gone") for n in before))
        code, _ = self._main("--root", live, "--tier1")  # a linked worktree resolves to its clone
        self.assertEqual(code, 0)
        after = self._registered(root)
        self.assertFalse(any(n.endswith("-gone") for n in after))
        self.assertTrue(os.path.isdir(live))
        self.assertIn("merged-b", sweep.list_local_branches(root))

    def test_branches_reaps_a_merged_branch_but_removes_no_worktree_and_holds_theirs(self):
        root, live = self._fixture("branches")
        code, _ = self._main("--root", root, "--branches", "--confirm", "--attended")
        self.assertEqual(code, 0)
        left = sweep.list_local_branches(root)
        self.assertNotIn("merged-b", left)
        self.assertIn("lane-live", left)
        self.assertTrue(os.path.isdir(live))
        self.assertTrue(any(n.endswith("-gone") for n in self._registered(root)))

    def test_branches_previews_without_confirm(self):
        root, _live = self._fixture("branches-preview")
        result = sweep.sweep_repo(root, False, os.path.join(ROOT, "mode.log"), "branches")
        self.assertEqual({b["name"]: b["action"] for b in result["branches"]}["merged-b"], "reap")
        self.assertIn("merged-b", sweep.list_local_branches(root))

    def test_branches_refuses_when_the_worktree_list_is_empty(self):
        root, _live = self._fixture("branches-blind")
        real = sweep.parse_worktree_list
        sweep.parse_worktree_list = lambda where: []
        try:
            result = sweep.sweep_repo(root, True, os.path.join(ROOT, "mode.log"), "branches")
        finally:
            sweep.parse_worktree_list = real
        self.assertEqual(result["refused"], "unreadable-worktree-list")
        self.assertIn("merged-b", sweep.list_local_branches(root))

    def test_root_resolves_a_linked_worktree_to_its_primary_checkout(self):
        root, live = self._fixture("resolve")
        seen = []
        real = sweep.sweep_repo
        sweep.sweep_repo = lambda r, *a, **k: (seen.append(r), real(r, *a, **k))[1]
        try:
            self._main("--root", live, "--tier1")
        finally:
            sweep.sweep_repo = real
        self.assertEqual([os.path.realpath(r) for r in seen], [os.path.realpath(root)])

    def test_single_tier_modes_do_no_process_work(self):
        root, _live = self._fixture("noproc")
        calls = []
        stubs = {"find_dead_rooted": lambda: calls.append("dead") or [],
                 "find_loose_processes": lambda: calls.append("loose") or [],
                 "find_swept_listeners": lambda paths: calls.append("listeners") or []}
        real = {k: getattr(sweep, k) for k in stubs}
        for k, fn in stubs.items():
            setattr(sweep, k, fn)
        try:
            self._main("--root", root, "--tier1")
            self._main("--root", root, "--branches", "--confirm")
        finally:
            for k, fn in real.items():
                setattr(sweep, k, fn)
        self.assertEqual(calls, [])

    def test_root_in_a_separate_git_dir_clone_exits_1(self):
        work = os.path.join(ROOT, "mode-sepdir-work")
        gitdir = os.path.join(ROOT, "mode-sepdir-store", "g")
        os.makedirs(work)
        os.makedirs(os.path.dirname(gitdir))
        made = run_vcs(work, "init", "-q", "-b", "main", "--separate-git-dir", gitdir)
        require(made.returncode == 0, "separate git dir fixture: %s" % made.stderr.strip())
        require(guard.primary_checkout(work) is not None, "fixture: guard resolves a primary")
        code, text = self._main("--root", work, "--tier1")
        self.assertEqual(code, 1)
        self.assertIn("not inside a repository", text)

    def test_root_whose_git_dir_sits_in_another_repos_root_exits_1(self):
        parent = os.path.join(ROOT, "mode-nested-parent")
        make_repo(parent, {"f.txt": "x\n"})
        work = os.path.join(ROOT, "mode-nested-work")
        os.makedirs(work)
        made = run_vcs(work, "init", "-q", "-b", "main", "--separate-git-dir",
                       os.path.join(parent, "g"))
        require(made.returncode == 0, "nested git dir fixture: %s" % made.stderr.strip())
        require(guard.primary_checkout(work) == os.path.realpath(parent), "fixture: sees parent")
        code, text = self._main("--root", work, "--tier1")
        self.assertEqual(code, 1)
        self.assertIn("not inside a repository", text)

    def test_root_outside_any_repository_exits_1(self):
        code, text = self._main("--root", ROOT, "--tier1")
        self.assertEqual(code, 1)
        self.assertIn("not inside a repository", text)


# --------------------------------------------------------------------------- the --confirm gate
#
# Every OTHER confirm=False call in this file (BaseResolutionRefusalTests,
# OptOutTests.test_sweep_false_..., OptOutTests.test_unparseable_file_...) hits a REFUSED
# repository before either loop in sweep_repo ever runs, so none of them can prove anything about
# the gate itself: a refused repository never reaches `if confirm and decision["action"] ==
# "reap":` at all. This class is the one arm that puts a REAPABLE branch and a REMOVABLE worktree
# in front of a confirm=False sweep and checks that preview leaves both alone. Its absence is a
# MEASURED hole: janitor/mutate_sweep.py's `--confirm: reap branches for real with no --confirm
# on the line` mutant (the `confirm and` dropped from that same line) passed all 31 cases in this
# file before this class existed.
class ConfirmGateTests(unittest.TestCase):
    def test_preview_names_reapable_subjects_but_touches_neither(self):
        root = os.path.join(ROOT, "confirm-gate-repo")
        make_repo(root, {"f.txt": "x\n"})
        give_remote(root)
        # A branch identical to main's own tip: the ancestor test alone proves it empty, so it is
        # REAPABLE, not merely present.
        run_vcs(root, "checkout", "-q", "-b", "preview-should-not-touch")
        run_vcs(root, "checkout", "-q", "main")
        # A clean, unlocked worktree with no live session recorded against it: REMOVABLE, not
        # merely registered.
        target = os.path.join(ROOT, "confirm-gate-worktree")
        run_vcs(root, "worktree", "add", "-q", target, "-b", "lane-confirm-gate")

        # THE SUBJECT SET MUST NOT BE EMPTY before any verdict about it means anything (the same
        # rule every other case in this file follows; see the module docstring).
        branches_before = sweep.list_local_branches(root)
        self.assertTrue(len(branches_before) > 0, "branch list must not be empty")
        self.assertIn("preview-should-not-touch", branches_before)
        entries_before = sweep.parse_worktree_list(root)
        self.assertTrue(entries_before is not None and len(entries_before) > 0,
                         "worktree list must not be empty")
        self.assertTrue(any(
            os.path.normcase(os.path.realpath(e["path"]))
            == os.path.normcase(os.path.realpath(target)) for e in entries_before
        ))

        log_path = os.path.join(ROOT, "confirm-gate.log")
        result = sweep.sweep_repo(root, confirm=False, restore_log_path=log_path, attended=True)
        self.assertIsNone(result["refused"])

        # The preview must have NAMED both subjects as reapable. A preview that silently reported
        # nothing at all -- as empty a result as an empty subject set -- would pass a weaker
        # assertion than this one just as wrongly.
        branch_decision = next(
            (b for b in result["branches"] if b["name"] == "preview-should-not-touch"), None)
        self.assertIsNotNone(branch_decision, "the branch must appear in the preview at all")
        self.assertEqual(branch_decision["action"], "reap")

        worktree_decision = next(
            (w for w in result["worktrees"]
             if os.path.normcase(os.path.realpath(w["path"]))
             == os.path.normcase(os.path.realpath(target))), None)
        self.assertIsNotNone(worktree_decision, "the worktree must appear in the preview at all")
        self.assertEqual(worktree_decision["action"], "reap")

        # And PREVIEW MUST NOT HAVE TOUCHED EITHER ONE: this is the assertion the gate itself
        # lives or dies on.
        branches_after = sweep.list_local_branches(root)
        self.assertIn("preview-should-not-touch", branches_after,
                       "a preview run with confirm=False deleted a branch")
        entries_after = sweep.parse_worktree_list(root)
        self.assertTrue(entries_after is not None)
        self.assertTrue(any(
            os.path.normcase(os.path.realpath(e["path"]))
            == os.path.normcase(os.path.realpath(target)) for e in entries_after
        ), "a preview run with confirm=False removed a worktree")
        self.assertTrue(os.path.isdir(target),
                         "a preview run with confirm=False deleted a worktree's directory")


class WorktreePruneTests(unittest.TestCase):
    """`sweep.prune_registrations`: a registration whose directory is gone is named by
    `git worktree prune -n`, and pruned only under confirm."""

    def _stale(self, name):
        root = os.path.join(ROOT, name + "-repo")
        make_repo(root, {"f.txt": "x\n"})
        target = os.path.join(ROOT, name + "-wt")
        run_vcs(root, "worktree", "add", "-q", target, "-b", "lane-" + name)
        shutil.rmtree(target)
        registration = os.path.join(root, ".git", "worktrees", os.path.basename(target))
        self.assertTrue(os.path.isdir(registration), "fixture needs a stale registration")
        return root, registration

    def test_preview_names_the_stale_registration_and_prunes_nothing(self):
        root, registration = self._stale("prune-preview")
        result = sweep.sweep_repo(root, False, os.path.join(ROOT, "prune-preview.log"))
        self.assertEqual(len(result["pruned"]["names"]), 1)
        self.assertTrue(os.path.isdir(registration))
        out = io.StringIO()
        sweep.print_sweep_report([result], False, out=out)
        self.assertIn("prune     WOULD", out.getvalue())

    def test_confirm_prunes_the_stale_registration(self):
        root, registration = self._stale("prune-confirm")
        result = sweep.sweep_repo(root, True, os.path.join(ROOT, "prune-confirm.log"))
        self.assertEqual(len(result["pruned"]["names"]), 1)
        self.assertIsNone(result["pruned"]["error"])
        self.assertFalse(os.path.isdir(registration))

    def test_preview_and_confirm_agree_on_a_branch_held_by_a_stale_registration(self):
        root, _ = self._stale("prune-agree")
        log = os.path.join(ROOT, "prune-agree.log")
        verdicts = []
        for confirm in (False, True):
            result = sweep.sweep_repo(root, confirm, log)
            verdicts.append([(b["name"], b["action"], b["reason"]) for b in result["branches"]
                             if b["name"] == "lane-prune-agree"])
        self.assertEqual(len(verdicts[0]), 1)
        self.assertEqual(verdicts[0], verdicts[1])

    def test_a_failed_prune_leaves_the_registration_and_its_branch_kept(self):
        root, registration = self._stale("prune-fails")
        failed = subprocess.CompletedProcess([], 1, "", "fatal")
        real = guard._git
        sys.modules["guard_core"]._git = lambda where, *a: (failed if a == ("worktree", "prune")
                                        else real(where, *a))
        try:
            result = sweep.sweep_repo(root, True, os.path.join(ROOT, "prune-fails.log"))
        finally:
            sys.modules["guard_core"]._git = real
        self.assertTrue(result["pruned"]["error"])
        self.assertTrue(os.path.isdir(registration))
        verdict = [b for b in result["branches"] if b["name"] == "lane-prune-fails"]
        self.assertEqual([b["action"] for b in verdict], ["keep"])

    def test_an_unreadable_preview_prunes_nothing(self):
        """git gives no answer (None), and git answers with a failure: both prune nothing."""
        failed = subprocess.CompletedProcess([], 128, "", "fatal")
        for name, answer in (("none", None), ("failed", failed)):
            root, registration = self._stale("prune-blind-" + name)
            real = guard._git
            sys.modules["guard_core"]._git = lambda where, *a: (answer if a[:2] == ("worktree", "prune")
                                            else real(where, *a))
            try:
                found = sweep.prune_registrations(root, True)
            finally:
                sys.modules["guard_core"]._git = real
            self.assertIsNone(found["names"])
            self.assertTrue(os.path.isdir(registration))


class HuskTests(unittest.TestCase):
    """`sweep.find_husks`: a leftover folder is reported, never deleted, `--confirm` included."""

    def _repo(self, name, husk_names=("node_modules", ".serve")):
        root = os.path.join(ROOT, name + "-repo")
        make_repo(root, {"f.txt": "x\n"})
        if husk_names is not None:
            write(os.path.join(root, ".claude", "janitor.json"),
                  json.dumps({"huskNames": list(husk_names)}))
        return root

    def _husk(self, root, name, children):
        path = os.path.join(root, ".claude", "worktrees", name)
        for child in children:
            os.makedirs(os.path.join(path, child))
        return path

    def _husks(self, root):
        names = sweep.read_optout(root).get("huskNames", [])
        found = sweep.find_husks(root, sweep.parse_worktree_list(root), names)
        return {os.path.basename(h["path"]): h["action"] for h in found}

    @unittest.skipIf(os.name == "nt", "Windows never deletes husks")
    def test_preview_lists_a_husk_as_would_and_deletes_nothing(self):
        root = self._repo("husk-found")
        path = self._husk(root, "gone", ["node_modules", ".serve"])
        self.assertEqual(self._husks(root), {"gone": "husk"})
        result = sweep.sweep_repo(root, False, os.path.join(ROOT, "husk.log"))
        self.assertTrue(os.path.isdir(path), "a preview deleted a husk")
        out = io.StringIO()
        sweep.print_sweep_report([result], False, out=out)
        self.assertIn("husk      WOULD", out.getvalue())

    @unittest.skipIf(os.name == "nt", "Windows never deletes husks")
    def test_confirm_deletes_a_proven_husk(self):
        root = self._repo("husk-confirm")
        path = self._husk(root, "gone", ["node_modules", ".serve"])
        keep = self._husk(root, "has-source", ["node_modules", "src"])
        result = sweep.sweep_repo(root, True, os.path.join(ROOT, "husk.log"))
        self.assertFalse(os.path.exists(path))
        self.assertTrue(os.path.isdir(keep))
        self.assertEqual([h.get("error") for h in result["husks"]], [None])

    def test_confirm_keeps_a_folder_that_gained_a_foreign_file_after_the_find(self):
        root = self._repo("husk-changed")
        path = self._husk(root, "gone", ["node_modules"])
        names = ["node_modules"]
        found = sweep.find_husks(root, sweep.parse_worktree_list(root), names)
        write(os.path.join(path, "notes.txt"), "mine\n")
        sweep.reap_husk(root, found[0], names)
        self.assertTrue(os.path.isfile(os.path.join(path, "notes.txt")))
        self.assertEqual(found[0]["action"], "keep")

    @unittest.skipIf(os.name == "nt", "symlinks need privilege on Windows")
    def test_confirm_refuses_a_folder_that_became_a_link(self):
        root = self._repo("husk-link")
        path = self._husk(root, "gone", ["node_modules"])
        names = ["node_modules"]
        found = sweep.find_husks(root, sweep.parse_worktree_list(root), names)
        target = os.path.join(ROOT, "husk-link-target")
        os.makedirs(os.path.join(target, "node_modules"))
        shutil.rmtree(path)
        os.symlink(target, path)
        sweep.reap_husk(root, found[0], names)
        self.assertTrue(os.path.isdir(os.path.join(target, "node_modules")))
        self.assertEqual(found[0]["action"], "keep")

    def test_a_folder_holding_anything_else_is_not_a_husk(self):
        root = self._repo("husk-source")
        self._husk(root, "has-source", ["node_modules", "src"])
        self._husk(root, "empty", [])
        self.assertEqual(self._husks(root), {})

    def test_no_husk_names_means_no_husks(self):
        root = self._repo("husk-nokey", husk_names=None)
        self._husk(root, "gone", ["node_modules"])
        self.assertEqual(self._husks(root), {})

    def test_a_registered_worktree_is_not_a_husk(self):
        # `.git` is named too, so only the registration check can tell this folder from a husk.
        root = self._repo("husk-registered", husk_names=("node_modules", ".git"))
        target = os.path.join(root, ".claude", "worktrees", "live")
        run_vcs(root, "worktree", "add", "-q", target, "-b", "lane-husk-registered")
        for tracked in os.listdir(target):
            if tracked != ".git":
                os.remove(os.path.join(target, tracked))
        os.makedirs(os.path.join(target, "node_modules"))
        self.assertNotIn("live", self._husks(root))

    def test_a_malformed_husk_names_refuses_the_repository(self):
        root = self._repo("husk-bad")
        write(os.path.join(root, ".claude", "janitor.json"), '{"huskNames": "node_modules"}')
        result = sweep.sweep_repo(root, False, os.path.join(ROOT, "h.log"))
        self.assertEqual(result["refused"], "unreadable-optout")

    def test_a_symlinked_worktrees_base_is_never_walked_or_deleted(self):
        root = self._repo("husk-base-link")
        outside = os.path.join(ROOT, "husk-base-outside")
        os.makedirs(os.path.join(outside, "gone", "node_modules"))
        os.makedirs(os.path.join(root, ".claude"), exist_ok=True)
        os.symlink(outside, os.path.join(root, ".claude", "worktrees"))
        names = ["node_modules"]
        self.assertEqual(sweep.find_husks(root, sweep.parse_worktree_list(root), names), [])
        forged = {"path": os.path.join(root, ".claude", "worktrees", "gone"), "action": "husk",
                  "reason": "forged"}
        sweep.reap_husk(root, forged, names)
        self.assertTrue(os.path.isdir(os.path.join(outside, "gone", "node_modules")))
        self.assertEqual(forged["action"], "keep")

    @unittest.skipIf(os.name == "nt", "Windows never deletes husks")
    def test_a_failed_delete_prints_keep_with_the_error(self):
        root = self._repo("husk-fails")
        path = self._husk(root, "gone", ["node_modules"])

        def refuse(*a, **k):
            raise OSError("refused")
        real = shutil.rmtree
        shutil.rmtree = refuse
        try:
            result = sweep.sweep_repo(root, True, os.path.join(ROOT, "husk.log"))
        finally:
            shutil.rmtree = real
        self.assertTrue(os.path.isdir(path))
        out = io.StringIO()
        sweep.print_sweep_report([result], True, out=out)
        self.assertIn("husk      KEEP", out.getvalue())
        self.assertIn("refused", out.getvalue())

    @unittest.skipUnless(os.name == "nt", "the Windows delete; POSIX has its own cases above")
    def test_on_windows_a_proven_husk_is_deleted(self):
        root = self._repo("husk-nt")
        path = self._husk(root, "gone", ["node_modules"])
        self.assertEqual(self._husks(root), {"gone": "husk"})
        result = sweep.sweep_repo(root, True, os.path.join(ROOT, "husk.log"))
        self.assertFalse(os.path.exists(path), "a proven husk was kept on Windows")
        self.assertEqual([h.get("error") for h in result["husks"]], [None])

    @unittest.skipUnless(os.name == "nt", "a junction is a Windows folder link")
    def test_windows_husk_delete_unlinks_a_junction_inside_and_keeps_its_target(self):
        root = self._repo("husk-windows")
        path = self._husk(root, "gone", [])
        target = os.path.join(ROOT, "husk-windows-target")
        write(os.path.join(target, "keep.txt"), "not ours\n")
        make_junction(os.path.join(path, "node_modules"), target)
        self.assertEqual(self._husks(root), {"gone": "husk"})
        sweep.sweep_repo(root, True, os.path.join(ROOT, "husk.log"))
        self.assertFalse(os.path.exists(path), "a proven husk was kept on Windows")
        self.assertTrue(os.path.isfile(os.path.join(target, "keep.txt")),
                        "the delete went through the junction into its target")

    def test_an_empty_process_table_keeps_the_husk(self):
        root = self._repo("husk-blind")
        self._husk(root, "gone", ["node_modules"])
        with _Stub("processes_in", lambda path: (None, None)):
            self.assertEqual(self._husks(root), {"gone": "keep"})

    def test_darwin_processes_in_reads_one_table(self):
        inside = os.path.join(ROOT, "husk-table")
        os.makedirs(inside, exist_ok=True)
        real = sweep.sys.platform
        sweep.sys.platform = "darwin"
        try:
            with _Stub("_all_cwds_macos", lambda: [(7, inside), (8, "/elsewhere")]):
                self.assertEqual(sweep.processes_in(inside), ([7], []))
            with _Stub("_all_cwds_macos", lambda: None):
                self.assertEqual(sweep.processes_in(inside), (None, None))
        finally:
            sweep.sys.platform = real


    @unittest.skipIf(os.name == "nt", "the sleep fixture is POSIX only")
    def test_a_process_inside_keeps_the_husk(self):
        root = self._repo("husk-busy")
        path = self._husk(root, "busy", ["node_modules"])
        proc = subprocess.Popen(["sleep", "30"], cwd=path)
        try:
            self.assertEqual(self._husks(root), {"busy": "keep"})
        finally:
            proc.kill()
            proc.wait()


def make_junction(link, target):
    """A real Windows junction LINK -> TARGET (no admin needed). The test removes only the link."""
    os.makedirs(target, exist_ok=True)
    os.makedirs(os.path.dirname(link), exist_ok=True)
    done = subprocess.run(["cmd", "/c", "mklink", "/J", link, target], capture_output=True, text=True)
    require(done.returncode == 0, "mklink /J failed: " + (done.stdout + done.stderr).strip())


def junction_fixture(case, keep=True):
    """`(base, target)`: a temp dir and a real folder in it holding `node_modules/x.txt` and, with
    KEEP, `keep.txt`. A name set of `node_modules` alone makes the target a husk-shaped folder."""
    base = tempfile.mkdtemp(prefix="junction_")
    case.addCleanup(shutil.rmtree, base, True)
    target = os.path.join(base, "target")
    write(os.path.join(target, "node_modules", "x.txt"), "x\n")
    if keep:
        write(os.path.join(target, "keep.txt"), "not ours\n")
    return base, target


@unittest.skipUnless(os.name == "nt", "a junction is a Windows folder link")
class JunctionTests(unittest.TestCase):
    """A Windows junction is a link `os.path.islink` does not see. `sweep.is_link` is the one check.
    Each case builds a real junction. A reap must never delete through it."""

    def _intact(self, target):
        self.assertTrue(os.path.isfile(os.path.join(target, "node_modules", "x.txt")),
                        "the target lost node_modules/x.txt")

    def test_is_link_sees_a_junction_and_a_symlink_and_not_a_real_folder(self):
        base, target = junction_fixture(self)
        junction = os.path.join(base, "j")
        make_junction(junction, target)
        self.assertTrue(sweep.is_link(junction), "a junction is not a link")
        self.assertFalse(sweep.is_link(target), "a real folder is a link")
        symlink = os.path.join(base, "s")
        try:
            os.symlink(target, symlink, target_is_directory=True)
        except OSError:
            symlink = None  # no privilege to make a symlink: this assert is skipped
        if symlink:
            self.assertTrue(sweep.is_link(symlink), "a symlink is not a link")

    def test_a_junction_under_the_worktrees_folder_is_not_a_husk_and_its_target_is_kept(self):
        root = os.path.join(ROOT, "junction-husk-repo")
        make_repo(root, {"f.txt": "x\n"})
        names = ["node_modules", ".serve"]
        write(os.path.join(root, ".claude", "janitor.json"), json.dumps({"huskNames": names}))
        base, target = junction_fixture(self, keep=False)  # the target alone looks like a husk
        link = os.path.join(root, ".claude", "worktrees", "gone")
        make_junction(link, target)
        verdict = sweep.husk_verdict(root, link, sweep.parse_worktree_list(root), names)
        self.assertIsNone(verdict, "a junction was given a husk verdict: %s" % verdict)
        sweep.sweep_repo(root, True, os.path.join(ROOT, "junction-husk.log"))
        self._intact(target)

    def test_scan_worktree_lists_no_junction_and_walks_none(self):
        base, target = junction_fixture(self)
        os.makedirs(os.path.join(target, "build"))
        wt = os.path.join(base, "wt")
        os.makedirs(os.path.join(wt, "real"))
        make_junction(os.path.join(wt, "build"), target)
        make_junction(os.path.join(wt, "other"), target)  # a walk into it would list target/build
        builds, _ = sweep.scan_worktree(wt, {"build"})
        self.assertEqual(builds, [], "a junction was listed, or walked into: %s" % builds)
        self._intact(target)

    def test_scan_worktree_lists_a_real_build_folder_holding_a_junction(self):
        base, target = junction_fixture(self)
        wt = os.path.join(base, "wt")
        make_junction(os.path.join(wt, "build", "j"), target)
        builds, _ = sweep.scan_worktree(wt, {"build"})
        self.assertEqual(builds, [os.path.join(wt, "build")])

    def test_trash_verdict_keeps_a_junction_with_a_trash_name(self):
        base, target = junction_fixture(self)
        link = sweep.trash_name(os.path.join(base, "build"))
        make_junction(link, target)
        delete, reason = sweep.trash_verdict(link)
        self.assertFalse(delete, "a junction was proven as trash: %s" % reason)
        self._intact(target)


class AllCwdsMacosTests(unittest.TestCase):
    """`sweep._all_cwds_macos` against a faked lsof, on every platform."""

    def test_parses_pid_and_cwd_lines(self):
        with _FakeLsof(0, "p10\nn/a/b\np11\nn/c\n"):
            self.assertEqual(sweep._all_cwds_macos(), [(10, "/a/b"), (11, "/c")])

    def test_exit_1_is_readable_and_other_exits_are_not(self):
        with _FakeLsof(1, "p10\nn/a\n"):
            self.assertEqual(sweep._all_cwds_macos(), [(10, "/a")])
        with _FakeLsof(2, "p10\nn/a\n"):
            self.assertIsNone(sweep._all_cwds_macos())

    def test_a_timeout_is_unreadable(self):
        with _FakeLsof(exc=subprocess.TimeoutExpired("lsof", 60)):
            try:
                found = sweep._all_cwds_macos()
            except Exception as exc:  # a FAIL line, not an ERROR line, is what the harness reads
                self.fail("the timeout escaped: %r" % (exc,))
        self.assertIsNone(found)

    def test_an_empty_table_is_unreadable(self):
        with _FakeLsof(0, ""):
            self.assertIsNone(sweep._all_cwds_macos())
        with _FakeLsof(1, ""):
            self.assertIsNone(sweep._all_cwds_macos())


# --------------------------------------------------------------------------- the preview cache


class PreviewCacheTests(unittest.TestCase):
    """A preview reads each machine fact once; a run that acts, and any direct caller, never
    caches."""

    def setUp(self):
        self.calls = []
        self.real_run = sweep.subprocess.run
        uid = os.getuid() if hasattr(os, "getuid") else 0
        self.ps_out = ("  5     1   %d  /bin/sh -c  echo hi \n"
                       "  7     1   %d  /other\n  8     4   %d  /child\n" % (uid, uid + 1, uid))
        self.exit_code = 0

        def fake(argv, *a, **k):
            self.calls.append(list(argv))
            if argv[0] == "lsof":
                out = getattr(self, "lsof_out", "p10\nn/a\n")
            elif argv[:2] == ["ps", "-axo"] and argv[2] == "pid=":
                out = "5\n6\n"
            elif argv[:2] == ["ps", "-axo"]:
                out = self.ps_out
            else:
                out = "9\n"  # a per-pid `ps -o X= -p PID`
            return subprocess.CompletedProcess(argv, self.exit_code, out, "")
        sweep.subprocess.run = fake
        self.undo = None

    def tearDown(self):
        sweep.subprocess.run = self.real_run
        if self.undo:
            self.undo()

    def begin(self):
        self.undo = sweep._begin_preview_cache()

    def test_cwd_table_is_read_once_per_preview_and_never_outside_one(self):
        self.begin()
        sweep._all_cwds_macos()
        sweep._all_cwds_macos()
        self.assertEqual(len(self.calls), 1)
        self.undo()
        self.undo = None
        sweep._all_cwds_macos()
        sweep._all_cwds_macos()
        self.assertEqual(len(self.calls), 3)

    @unittest.skipIf(sys.platform.startswith("win"), "POSIX uid")
    def test_one_ps_table_answers_command_orphan_owner_and_pid_list_on_macos(self):
        with mock.patch.object(sys, "platform", "darwin"):
            self.begin()
            self.assertEqual(sweep.process_command(5), "/bin/sh -c  echo hi")
            self.assertIs(sweep.is_orphan(5), True)
            self.assertIs(sweep.is_current_user_process(5), True)
            self.assertIs(sweep.is_current_user_process(7), False)
            self.assertIs(sweep.is_orphan(8), False)
            self.assertEqual(sweep.list_all_pids(), [5, 7, 8])
            self.assertIsNone(sweep.process_command(6))
            self.assertIsNone(sweep.is_orphan(6))
            self.assertEqual(len(self.calls), 1)

    def test_a_failed_ps_table_falls_back_to_the_per_pid_read(self):
        self.exit_code = 1
        with mock.patch.object(sys, "platform", "darwin"):
            self.begin()
            sweep.process_command(5)
            sweep.process_command(5)
            self.assertEqual(self.calls[0][:2], ["ps", "-axo"])
            self.assertEqual(self.calls[1:], [["ps", "-o", "command=", "-p", "5"]] * 2)

    def test_an_empty_ps_table_falls_back_to_the_per_pid_read(self):
        self.ps_out = ""
        with mock.patch.object(sys, "platform", "darwin"):
            self.begin()
            self.assertEqual(sweep.process_command(5), "9")
            self.assertEqual(self.calls[-1], ["ps", "-o", "command=", "-p", "5"])

    def test_without_a_preview_every_read_is_per_pid_and_linux_never_uses_the_table(self):
        with mock.patch.object(sys, "platform", "darwin"):
            sweep.process_command(5)
            sweep.list_all_pids()
        self.assertEqual(self.calls, [["ps", "-o", "command=", "-p", "5"], ["ps", "-axo", "pid="]])
        self.begin()
        with mock.patch.object(sys, "platform", "linux"):
            self.assertIs(sweep._ps_row(5), sweep._NO_TABLE)

    def test_one_cwd_table_answers_every_process_cwd_in_a_preview_on_macos(self):
        self.lsof_out = "p10\nn/a\nn/second\np11\nn/c\n"
        with mock.patch.object(sys, "platform", "darwin"):
            self.begin()
            self.assertEqual(sweep.process_cwd(10), "/a")
            self.assertEqual(sweep.process_cwd(11), "/c")
            self.assertIsNone(sweep.process_cwd(12))
            self.assertEqual(len(self.calls), 1)
            self.undo()
            self.undo = None
            self.assertEqual(sweep.process_cwd(10), "/a")
            self.assertEqual(self.calls[-1][:3], ["lsof", "-a", "-p"])

    def test_worktree_list_is_read_once_per_repository_and_other_git_reads_are_not_cached(self):
        seen = []
        real = sweep.guard._git
        sys.modules["guard_core"]._git = lambda where, *args: seen.append((where, args))
        try:
            self.begin()
            for where in ("a", "a", "b"):
                sweep.guard._git(where, "worktree", "list", "--porcelain")
            sweep.guard._git("a", "status", "--porcelain")
            sweep.guard._git("a", "status", "--porcelain")
        finally:
            self.undo()
            self.undo = None
            sys.modules["guard_core"]._git = real
        self.assertEqual(len(seen), 4)

    def test_session_records_are_read_once_per_preview(self):
        seen = []
        real = sweep.guard.session_records
        sys.modules["guard_core"].session_records = lambda: seen.append(1) or []
        try:
            self.begin()
            sweep.guard.session_records()
            sweep.guard.session_records()
        finally:
            self.undo()
            self.undo = None
            sys.modules["guard_core"].session_records = real
        self.assertEqual(len(seen), 1)

    def test_only_a_preview_caches_and_the_guard_reads_come_back_after(self):
        repo = os.path.join(ROOT, "cache-gate-repo")
        seen = []
        real_git, real_records = sweep.guard._git, sweep.guard.session_records
        with _Stub("_sweep_roots", lambda *a: seen.append(
                (sweep._RUN is not None, sweep._POOL is not None)) or 0):
            for args in ([repo], ["--confirm", repo], ["--tier1", repo], ["--branches", repo]):
                sweep.main(args)
        on = sweep.PREVIEW_THREADS
        self.assertEqual(seen, [(True, on), (False, False), (False, False), (True, on)])
        self.assertIsNone(sweep._RUN)
        self.assertIsNone(sweep._POOL)
        self.assertIs(sweep.guard._git, real_git)
        self.assertIs(sweep.guard.session_records, real_records)


class ParallelPreviewTests(unittest.TestCase):
    """In a preview the per-branch and per-worktree reads run on threads. The report must not
    change, and a run that acts must stay one decision at a time."""

    def test_pmap_is_lazy_and_in_order_outside_a_preview(self):
        seen = []
        out = sweep._pmap(lambda i: seen.append(i) or i, [1, 2, 3], False)
        self.assertEqual(seen, [])
        self.assertEqual(next(iter(out)), 1)
        self.assertEqual(seen, [1])

    def test_a_run_that_acts_gets_one_decision_at_a_time_even_with_the_pool_open(self):
        undo = sweep._begin_preview_cache()
        try:
            seen = []
            out = sweep._pmap(lambda i: seen.append(i) or i, [1, 2, 3], True)
            self.assertEqual(seen, [])
            self.assertEqual(next(iter(out)), 1)
            self.assertEqual(seen, [1])
        finally:
            undo()

    @unittest.skipUnless(sweep.PREVIEW_THREADS, "Windows previews stay serial")
    def test_pmap_runs_a_preview_in_parallel_and_returns_input_order(self):
        undo = sweep._begin_preview_cache()
        try:
            gate = threading.Barrier(2, timeout=3)

            def both(i):
                gate.wait()  # two calls must be in flight at once, or this raises
                time.sleep((2 - i) * 0.2)
                return i
            try:
                got = list(sweep._pmap(both, [0, 1], False))
            except threading.BrokenBarrierError:
                self.fail("the two calls did not run at the same time")
            self.assertEqual(got, [0, 1])
        finally:
            undo()
        self.assertIsNone(sweep._POOL)

    def test_a_cached_read_runs_once_when_workers_ask_together(self):
        undo = sweep._begin_preview_cache()
        try:
            runs = []
            list(sweep._pmap(lambda i: sweep._memo("k", lambda: runs.append(i) or time.sleep(0.2)),
                             range(6), False))
        finally:
            undo()
        self.assertEqual(len(runs), 1)

    def test_a_parallel_preview_reports_what_a_plain_one_does(self):
        root = os.path.join(ROOT, "parallel-preview-repo")
        make_repo(root, {"f.txt": "x\n"})
        give_remote(root)
        for name in ("empty-a", "empty-b", "empty-c"):
            run_vcs(root, "branch", name)
        run_vcs(root, "checkout", "-q", "-b", "has-work")
        write(os.path.join(root, "g.txt"), "y\n")
        run_vcs(root, "add", "-A")
        run_vcs(root, *IDENT, "commit", "-q", "-m", "work")
        run_vcs(root, "checkout", "-q", "main")
        for name in ("one", "two"):
            run_vcs(root, "worktree", "add", "-q", os.path.join(ROOT, "parallel-preview-" + name),
                    "-b", "lane-" + name)
        log = os.path.join(ROOT, "parallel-preview.log")
        plain = sweep.sweep_repo(root, False, log)
        undo = sweep._begin_preview_cache()
        try:
            fast = sweep.sweep_repo(root, False, log)
        finally:
            undo()
        self.assertTrue(len(plain["branches"]) >= 5 and len(plain["worktrees"]) == 2)
        self.assertEqual(fast, plain)

        # Each loop runs its decisions side by side in a preview.
        for name in ("decide_branch", "decide_worktree") if sweep.PREVIEW_THREADS else ():
            peak = self._peak_concurrency(name, lambda: sweep.sweep_repo(root, False, log))
            self.assertTrue(peak > 1, "%s never ran twice at once" % name)

    def test_confirm_never_runs_decisions_side_by_side_even_with_the_pool_open(self):
        root = os.path.join(ROOT, "confirm-serial-repo")
        make_repo(root, {"f.txt": "x\n"})
        give_remote(root)
        for name in ("empty-a", "empty-b", "empty-c"):
            run_vcs(root, "branch", name)
        log = os.path.join(ROOT, "confirm-serial.log")
        peak = self._peak_concurrency(
            "decide_branch", lambda: sweep.sweep_repo(root, True, log))
        self.assertEqual(peak, 1)
        self.assertNotIn("empty-a", sweep.list_local_branches(root))

    def _peak_concurrency(self, name, run):
        """Highest number of calls to `sweep.<name>` in flight at once during `run()`, in a
        preview."""
        real, lock, state = getattr(sweep, name), threading.Lock(), {"now": 0, "peak": 0}

        def wrapped(*a, **k):
            with lock:
                state["now"] += 1
                state["peak"] = max(state["peak"], state["now"])
            time.sleep(0.2)
            try:
                return real(*a, **k)
            finally:
                with lock:
                    state["now"] -= 1
        undo = sweep._begin_preview_cache()
        try:
            with _Stub(name, wrapped):
                run()
        finally:
            undo()
        return state["peak"]

    @unittest.skipUnless(sweep.PREVIEW_THREADS, "Windows previews stay serial")
    def test_whole_repositories_run_side_by_side_in_a_preview(self):
        class Stop(Exception):
            pass

        def stop(*a, **k):
            raise Stop
        args = types.SimpleNamespace(confirm=False, attended=False)

        def run():
            with _Stub("print_sweep_report", stop):
                try:
                    sweep._sweep_roots(args, ["a", "b", "c"], "log", "full")
                except Stop:
                    pass
        with _Stub("sweep_repo", lambda root, *a: {"root": root}):
            peak = self._peak_concurrency("sweep_repo", run)
        self.assertTrue(peak > 1, "sweep_repo never ran twice at once")


# --------------------------------------------------------------------------- the purge


class PurgeTests(unittest.TestCase):
    def setUp(self):
        self.repo = os.path.join(ROOT, "purge-repo")
        if not os.path.isdir(self.repo):
            make_repo(self.repo, {"f.txt": "x\n"})
        self.log_path = os.path.join(ROOT, "purge-%s.jsonl" % self.id().rsplit(".", 1)[-1])

    def write_log(self, lines):
        with open(self.log_path, "w", encoding="utf-8") as handle:
            for line in lines:
                handle.write(json.dumps(line) + "\n")

    def test_an_old_tombstone_previews_as_purge_and_is_not_dropped_without_confirm(self):
        run_vcs(self.repo, "update-ref", "refs/janitor/reaped/old-one", "HEAD")
        now = int(time.time() * 1000)
        self.write_log([{"repo": self.repo, "branch": "old-one",
                          "commit": "deadbeef", "time_ms": now - 91 * 86400000}])
        entries = sweep.read_restore_log(self.log_path)
        self.assertTrue(len(entries) > 0)

        decisions = sweep.purge_tombstones(self.log_path, confirm=False, now_ms=now)
        self.assertTrue(len(decisions) > 0)
        self.assertEqual(decisions[0]["action"], "purge")
        still_there = run_vcs(self.repo, "rev-parse", "refs/janitor/reaped/old-one")
        self.assertEqual(still_there.returncode, 0, "preview must not have dropped the ref")

    def test_confirm_drops_a_tombstone_past_90_days(self):
        run_vcs(self.repo, "update-ref", "refs/janitor/reaped/old-two", "HEAD")
        held = run_vcs(self.repo, "rev-parse", "refs/janitor/reaped/old-two").stdout.strip()
        now = int(time.time() * 1000)
        self.write_log([{"repo": self.repo, "branch": "old-two",
                          "commit": held, "time_ms": now - 91 * 86400000}])
        decisions = sweep.purge_tombstones(self.log_path, confirm=True, now_ms=now)
        self.assertTrue(len(decisions) > 0)
        self.assertEqual(decisions[0]["action"], "purge")
        self.assertNotIn("error", decisions[0])
        gone = run_vcs(self.repo, "rev-parse", "refs/janitor/reaped/old-two")
        self.assertNotEqual(gone.returncode, 0, "the tombstone ref must be gone after confirm")

    def test_a_tombstone_under_90_days_is_kept(self):
        run_vcs(self.repo, "update-ref", "refs/janitor/reaped/young", "HEAD")
        now = int(time.time() * 1000)
        self.write_log([{"repo": self.repo, "branch": "young",
                          "commit": "deadbeef", "time_ms": now - 5 * 86400000}])
        decisions = sweep.purge_tombstones(self.log_path, confirm=True, now_ms=now)
        self.assertTrue(len(decisions) > 0)
        self.assertEqual(decisions[0]["action"], "keep")
        still_there = run_vcs(self.repo, "rev-parse", "refs/janitor/reaped/young")
        self.assertEqual(still_there.returncode, 0)

    def test_an_unreadable_log_entry_is_kept_not_purged(self):
        now = int(time.time() * 1000)
        self.write_log([{"repo": self.repo, "time_ms": now - 200 * 86400000}])  # no branch field
        decisions = sweep.purge_tombstones(self.log_path, confirm=True, now_ms=now)
        self.assertTrue(len(decisions) > 0)
        self.assertEqual(decisions[0]["action"], "keep")
        self.assertEqual(decisions[0]["reason"], "unreadable-entry")

    def test_a_non_numeric_time_ms_is_kept_not_purged(self):
        """A string, a bool, or a missing time must read as unreadable. A True would otherwise
        count as 1 ms since the epoch and purge a fresh tombstone."""
        run_vcs(self.repo, "update-ref", "refs/janitor/reaped/odd-time", "HEAD")
        now = int(time.time() * 1000)
        for bad_time in ("yesterday", True, None):
            self.write_log([{"repo": self.repo, "branch": "odd-time",
                              "commit": "deadbeef", "time_ms": bad_time}])
            try:
                decisions = sweep.purge_tombstones(self.log_path, confirm=True, now_ms=now)
            except TypeError as exc:
                self.fail("time_ms %r crashed the purge: %s" % (bad_time, exc))
            self.assertEqual(decisions[0]["action"], "keep", repr(bad_time))
            self.assertEqual(decisions[0]["reason"], "unreadable-entry", repr(bad_time))
        still_there = run_vcs(self.repo, "rev-parse", "refs/janitor/reaped/odd-time")
        self.assertEqual(still_there.returncode, 0)


class PurgeRefOwnershipTests(unittest.TestCase):
    """The restore ref is keyed by branch name, so one name reaped twice shares one ref. The
    purge must drop a ref only while it still holds the expired entry's own commit.

    These cases assert refs and green pins only. Line compaction (removing expired lines from
    the restore log) is a separate, unplanned change: no case here asserts that a line leaves
    the log, and none should until that change is planned."""

    DAY_MS = 86400000

    def fresh_repo(self, tag):
        repo = os.path.join(ROOT, "pown-" + tag)
        make_repo(repo, {"f.txt": "x\n"})
        return repo

    def log_path(self, tag):
        return os.path.join(ROOT, "pown-%s.jsonl" % tag)

    def rev(self, repo, rev):
        out = run_vcs(repo, "rev-parse", "-q", "--verify", rev)
        return out.stdout.strip() if out.returncode == 0 else None

    def ref(self, repo, branch):
        return self.rev(repo, sweep.TOMBSTONE_REF_PREFIX + branch)

    def younger_commit(self, repo, message):
        made = run_vcs(repo, *IDENT, "commit-tree", "HEAD^{tree}", "-p", "HEAD", "-m", message)
        self.assertEqual(made.returncode, 0, "fixture: commit-tree failed: %s" % made.stderr.strip())
        return made.stdout.strip()

    def reap(self, repo, branch, commit, log):
        made = run_vcs(repo, "branch", branch, commit)
        self.assertEqual(made.returncode, 0, "fixture: could not create branch %s" % branch)
        decision = {}
        sweep.reap_branch(repo, branch, decision, log)
        self.assertNotIn("error", decision, "fixture: reap of %s failed" % branch)

    def age_log(self, log, ages_days, now):
        entries = sweep.read_restore_log(log)
        self.assertEqual(len(entries), len(ages_days), "fixture: restore-log row count")
        with open(log, "w", encoding="utf-8") as handle:
            for entry, days in zip(entries, ages_days):
                entry["time_ms"] = now - days * self.DAY_MS
                handle.write(json.dumps(entry) + "\n")

    def test_an_expired_entry_keeps_the_ref_that_holds_the_younger_commit(self):
        repo = self.fresh_repo("twice-ref")
        log = self.log_path("twice-ref")
        now = int(time.time() * 1000)
        old = self.rev(repo, "HEAD")
        self.reap(repo, "lane-twice", old, log)
        young = self.younger_commit(repo, "younger reap of the same name")
        self.reap(repo, "lane-twice", young, log)
        self.age_log(log, [91, 5], now)
        self.assertEqual(self.ref(repo, "lane-twice"), young,
                         "fixture: the second reap of one name must overwrite the ref")

        decisions = sweep.purge_tombstones(log, confirm=True, now_ms=now)

        self.assertEqual(decisions[0]["action"], "purge")
        self.assertEqual(decisions[1]["action"], "keep")
        self.assertEqual(self.ref(repo, "lane-twice"), young,
                         "the expired entry dropped the ref that holds the younger restore "
                         "point: purge drops by branch name, not by commit")

    def test_the_purge_leaves_the_younger_log_line_in_place(self):
        repo = self.fresh_repo("twice-log")
        log = self.log_path("twice-log")
        now = int(time.time() * 1000)
        self.reap(repo, "lane-twice-log", self.rev(repo, "HEAD"), log)
        young = self.younger_commit(repo, "younger reap of the same name")
        self.reap(repo, "lane-twice-log", young, log)
        self.age_log(log, [91, 5], now)

        sweep.purge_tombstones(log, confirm=True, now_ms=now)

        self.assertIn(young, [e["commit"] for e in sweep.read_restore_log(log)],
                      "the purge must not drop the younger entry's line")

    def test_a_lone_expired_entry_whose_ref_holds_its_commit_drops_the_ref(self):
        repo = self.fresh_repo("lone-ref")
        log = self.log_path("lone-ref")
        now = int(time.time() * 1000)
        self.reap(repo, "lane-lone", self.rev(repo, "HEAD"), log)
        self.age_log(log, [91], now)

        decisions = sweep.purge_tombstones(log, confirm=True, now_ms=now)

        self.assertEqual(decisions[0]["action"], "purge")
        self.assertNotIn("error", decisions[0])
        self.assertIsNone(self.ref(repo, "lane-lone"), "the ref must be dropped")

    def test_an_expired_entry_whose_ref_was_deleted_by_hand_purges_without_error(self):
        repo = self.fresh_repo("gone-ref")
        log = self.log_path("gone-ref")
        now = int(time.time() * 1000)
        self.reap(repo, "lane-gone", self.rev(repo, "HEAD"), log)
        self.age_log(log, [91], now)
        gone = run_vcs(repo, "update-ref", "-d", sweep.TOMBSTONE_REF_PREFIX + "lane-gone")
        self.assertEqual(gone.returncode, 0, "fixture: deleting the ref by hand failed")
        self.assertIsNone(self.ref(repo, "lane-gone"))

        decisions = sweep.purge_tombstones(log, confirm=True, now_ms=now)

        self.assertEqual(decisions[0]["action"], "purge")
        self.assertNotIn("error", decisions[0],
                         "a ref already gone must not read as a failed drop")

    def test_an_expired_entry_does_not_drop_a_ref_that_holds_another_commit(self):
        """The ref holds a commit no log line records (a reap whose line was lost). It is not
        this entry's restore point, so the purge must leave it alone."""
        repo = self.fresh_repo("moved-ref")
        log = self.log_path("moved-ref")
        now = int(time.time() * 1000)
        self.reap(repo, "lane-moved", self.rev(repo, "HEAD"), log)
        self.age_log(log, [91], now)
        other = self.younger_commit(repo, "a reap whose log line was lost")
        moved = run_vcs(repo, "update-ref", sweep.TOMBSTONE_REF_PREFIX + "lane-moved", other)
        self.assertEqual(moved.returncode, 0, "fixture: moving the ref failed")

        sweep.purge_tombstones(log, confirm=True, now_ms=now)

        self.assertEqual(self.ref(repo, "lane-moved"), other,
                         "the expired entry dropped a ref that holds another commit")

    def test_a_failed_ref_delete_keeps_the_ref_and_the_log_line(self):
        repo = self.fresh_repo("failed-drop")
        log = self.log_path("failed-drop")
        now = int(time.time() * 1000)
        commit = self.rev(repo, "HEAD")
        self.reap(repo, "lane-failed", commit, log)
        self.age_log(log, [91], now)
        real = sys.modules["guard_core"]._git
        failed = subprocess.CompletedProcess([], 1, "", "simulated failure")

        def failing_delete(where, *args):
            if args[:2] == ("update-ref", "-d"):
                return failed
            return real(where, *args)

        sys.modules["guard_core"]._git = failing_delete
        try:
            decisions = sweep.purge_tombstones(log, confirm=True, now_ms=now)
        finally:
            sys.modules["guard_core"]._git = real

        self.assertIn("error", decisions[0], "a failed drop must be reported")
        self.assertEqual(self.ref(repo, "lane-failed"), commit, "a failed drop must keep the ref")
        self.assertEqual([e["commit"] for e in sweep.read_restore_log(log)], [commit],
                         "a failed drop must keep its log line: never log-without-ref")

    def write_rows(self, log, rows):
        with open(log, "w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row) + "\n")

    def test_an_expired_entry_keeps_the_ref_while_an_unexpired_entry_names_its_commit(self):
        """One branch reaped twice at one tip: two log rows name one commit. The 91-day row
        expires, but the 5-day row still needs the ref, so the purge must keep it."""
        repo = self.fresh_repo("same-commit")
        log = self.log_path("same-commit")
        now = int(time.time() * 1000)
        commit = self.rev(repo, "HEAD")
        self.reap(repo, "lane-same", commit, log)
        self.reap(repo, "lane-same", commit, log)
        self.age_log(log, [91, 5], now)
        self.assertEqual(self.ref(repo, "lane-same"), commit,
                         "fixture: two reaps at one tip must leave the ref on that commit")

        decisions = sweep.purge_tombstones(log, confirm=True, now_ms=now)

        self.assertEqual(decisions[1]["action"], "keep")
        self.assertEqual(self.ref(repo, "lane-same"), commit,
                         "the expired row dropped the ref while the 5-day row still names "
                         "its commit")

    def test_an_expired_entry_drops_the_ref_once_no_unexpired_entry_names_its_commit(self):
        repo = self.fresh_repo("same-gone")
        log = self.log_path("same-gone")
        now = int(time.time() * 1000)
        commit = self.rev(repo, "HEAD")
        self.reap(repo, "lane-same-gone", commit, log)
        self.reap(repo, "lane-same-gone", commit, log)
        self.age_log(log, [91, 92], now)

        decisions = sweep.purge_tombstones(log, confirm=True, now_ms=now)

        self.assertEqual([d["action"] for d in decisions], ["purge", "purge"])
        self.assertNotIn("error", decisions[0])
        self.assertNotIn("error", decisions[1])
        self.assertIsNone(self.ref(repo, "lane-same-gone"),
                          "both rows are expired and name the commit: the ref must be dropped")

    def test_a_missing_repo_path_is_reported_not_read_as_a_gone_ref(self):
        """git exits 128 for a missing path. Only exit 1 means the ref is gone."""
        missing = os.path.join(ROOT, "pown-no-such-repo")
        self.assertFalse(os.path.exists(missing), "fixture: the path must not exist")
        log = self.log_path("missing-path")
        now = int(time.time() * 1000)
        self.write_rows(log, [{"repo": missing, "branch": "lane-missing-path",
                               "commit": "1" * 40, "time_ms": now - 91 * self.DAY_MS}])

        decisions = sweep.purge_tombstones(log, confirm=True, now_ms=now)

        self.assertIn("error", decisions[0],
                      "a git failure (exit 128) must be reported, not read as a gone ref")

    def test_a_non_repo_directory_is_reported_not_read_as_a_gone_ref(self):
        """git exits 128 inside a directory that is not a repository."""
        plain = os.path.join(ROOT, "pown-plain-dir")
        os.makedirs(plain, exist_ok=True)
        log = self.log_path("plain-dir")
        now = int(time.time() * 1000)
        self.write_rows(log, [{"repo": plain, "branch": "lane-plain-dir",
                               "commit": "2" * 40, "time_ms": now - 91 * self.DAY_MS}])

        decisions = sweep.purge_tombstones(log, confirm=True, now_ms=now)

        self.assertIn("error", decisions[0],
                      "a git failure (exit 128) must be reported, not read as a gone ref")

    def test_a_failed_ref_read_is_reported_and_keeps_the_ref(self):
        repo = self.fresh_repo("read-fails")
        log = self.log_path("read-fails")
        now = int(time.time() * 1000)
        commit = self.rev(repo, "HEAD")
        self.reap(repo, "lane-read", commit, log)
        self.age_log(log, [91], now)
        real = sys.modules["guard_core"]._git
        failed = subprocess.CompletedProcess([], 128, "", "fatal: simulated")

        def failing_read(where, *args):
            if args[:3] == ("rev-parse", "-q", "--verify"):
                return failed
            return real(where, *args)

        sys.modules["guard_core"]._git = failing_read
        try:
            decisions = sweep.purge_tombstones(log, confirm=True, now_ms=now)
        finally:
            sys.modules["guard_core"]._git = real

        self.assertIn("error", decisions[0], "a git failure (exit 128) must be reported")
        self.assertEqual(self.ref(repo, "lane-read"), commit,
                         "a ref that could not be read must be kept")

    def spellings_of(self, repo):
        """Other strings that name the same directory on this PC (NTFS is case-insensitive,
        and tempfile hands back an 8.3 short name whose long form realpath returns)."""
        drive, tail = os.path.splitdrive(repo)
        return {
            "trailing-sep": repo + os.sep,
            "forward-slash": repo.replace("\\", "/"),
            "mixed-sep": drive + "\\" + tail[1:].replace("\\", "/"),
            "drive-case": repo[0].swapcase() + repo[1:],
            "all-upper": repo.upper(),
            "long-name": os.path.realpath(repo),
        }

    def check_spellings_keep_ref(self, tag, labels):
        """An expired row that spells the repo as one of `labels` must not drop the ref that an
        unexpired row (spelled as the fixture made it) still names. A spelling equal to the
        fixture's own string is skipped: there is no other spelling to test."""
        repo = self.fresh_repo(tag)
        now = int(time.time() * 1000)
        commit = self.rev(repo, "HEAD")
        spellings = self.spellings_of(repo)
        for label in labels:
            spelled = spellings[label]
            if spelled == repo:
                continue  # this PC gives the same string: no spelling to test
            with self.subTest(spelling=label):
                branch = "lane-spell-" + label
                log = self.log_path("spell-" + label)
                self.reap(repo, branch, commit, log)
                self.reap(repo, branch, commit, log)
                self.age_log(log, [91, 5], now)
                rows = sweep.read_restore_log(log)
                rows[0]["repo"] = spelled
                self.write_rows(log, rows)

                decisions = sweep.purge_tombstones(log, confirm=True, now_ms=now)

                self.assertNotIn("error", decisions[0])
                self.assertEqual(self.ref(repo, branch), commit,
                                 "the expired row, spelled %r, dropped the ref that the "
                                 "unexpired row still names" % label)

    def test_an_unexpired_row_protects_the_ref_across_spellings_of_its_repo(self):
        """The same-commit check must compare repositories by their real path. A trailing
        separator and the long name name the same directory on every platform, so these cases
        run on every platform."""
        self.check_spellings_keep_ref("spell", ["trailing-sep", "long-name"])

    @unittest.skipUnless(sys.platform == "win32",
                         "case and separator spellings name another path on POSIX: the file "
                         "system is case-sensitive and '/' is a literal character, so only the "
                         "Windows path compare folds them")
    def test_an_unexpired_row_protects_the_ref_across_case_and_separator_spellings(self):
        self.check_spellings_keep_ref("spell-win",
                                      ["all-upper", "drive-case", "forward-slash", "mixed-sep"])

    def test_a_broken_ref_file_is_an_error_not_a_gone_ref(self):
        """git rev-parse exits 1 for a broken ref file and says so on stderr. Only a clean
        exit 1 (no stderr) means the ref is gone."""
        repo = self.fresh_repo("broken-ref")
        log = self.log_path("broken-ref")
        now = int(time.time() * 1000)
        commit = self.rev(repo, "HEAD")
        self.reap(repo, "lane-broken", commit, log)
        self.age_log(log, [91], now)
        ref_file = os.path.join(repo, ".git", "refs", "janitor", "reaped", "lane-broken")
        self.assertTrue(os.path.isfile(ref_file), "fixture: the ref must be a loose file")
        write(ref_file, "not a sha\n")

        decisions = sweep.purge_tombstones(log, confirm=True, now_ms=now)

        self.assertIn("error", decisions[0],
                      "a broken ref (exit 1 with stderr) must be an error, not a gone ref")
        self.assertTrue(os.path.isfile(ref_file), "a broken ref must be kept")

    def test_a_reap_landing_after_the_read_keeps_the_younger_ref(self):
        """The read says the ref holds the expired commit, but a reap lands before the delete.
        The old-value argument must refuse the delete and keep the younger restore point."""
        repo = self.fresh_repo("race")
        log = self.log_path("race")
        now = int(time.time() * 1000)
        old = self.rev(repo, "HEAD")
        self.reap(repo, "lane-race", old, log)
        young = self.younger_commit(repo, "a reap that lands after the read")
        self.reap(repo, "lane-race", young, log)
        self.age_log(log, [91, 5], now)
        self.assertEqual(self.ref(repo, "lane-race"), young,
                         "fixture: the second reap must hold the ref")
        real = sys.modules["guard_core"]._git
        stale = subprocess.CompletedProcess([], 0, old + "\n", "")

        def read_says_old(where, *args):
            if args[:3] == ("rev-parse", "-q", "--verify"):
                return stale
            return real(where, *args)

        sys.modules["guard_core"]._git = read_says_old
        try:
            decisions = sweep.purge_tombstones(log, confirm=True, now_ms=now)
        finally:
            sys.modules["guard_core"]._git = real

        self.assertIn("error", decisions[0], "a refused delete must be reported")
        self.assertEqual(self.ref(repo, "lane-race"), young,
                         "the younger restore point must survive a delete that lost the race")


class AgentEndLogConcurrencyTests(unittest.TestCase):
    """janitor/agent_end_reap.py log(): parallel hook runs (one per finished agent) each append
    one row to the shared payload log. Every row must survive and every line must parse. The
    reviewer measured 13 of 120 rows lost at 3 writers on b0c87cb: one shared `.tmp` name and an
    unlocked read-modify-write. Real writer processes, real file, no fake."""

    CHILD = (
        "import sys\n"
        "sys.path.insert(0, __JANITOR__)\n"
        "import agent_end_reap\n"
        "lo, hi = int(sys.argv[1]), int(sys.argv[2])\n"
        "for i in range(lo, hi):\n"
        "    agent_end_reap.log({'raw': 'x', 'run': 'r' + str(i), 'state': 'done'})\n"
    ).replace("__JANITOR__", repr(os.path.dirname(os.path.abspath(__file__))))  # repr: Windows backslashes

    def run_writers(self, writers, rows):
        folder = tempfile.mkdtemp(prefix="reap_log_")
        self.addCleanup(shutil.rmtree, folder, True)
        env = dict(os.environ, CLAUDE_CONFIG_DIR=folder)
        step = rows // writers
        procs = [subprocess.Popen([sys.executable, "-c", self.CHILD, str(w * step), str((w + 1) * step)],
                                  env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                 for w in range(writers)]
        for proc in procs:
            _out, err = proc.communicate(timeout=120)
            self.assertEqual(proc.returncode, 0, "writer failed: %s" % err)
        path = os.path.join(folder, "state", "agent-end-payloads.jsonl")
        with open(path, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        bad = []
        runs = []
        for line in lines:
            try:
                row = json.loads(line)
            except ValueError:
                bad.append(line)
                continue
            if row.get("state") == "done":
                runs.append(row.get("run"))
        self.assertEqual(bad, [], "unparseable log lines with %d writers" % writers)
        lost = sorted(set("r" + str(i) for i in range(rows)) - set(runs))
        self.assertEqual(lost, [], "%d of %d rows lost with %d writers" % (len(lost), rows, writers))

    def test_three_parallel_writers_lose_no_row(self):
        self.run_writers(3, 120)

    def test_twenty_four_parallel_writers_lose_no_row(self):
        self.run_writers(24, 120)


class AgentEndReapBatchTests(unittest.TestCase):
    """janitor/agent_end_reap.py reads every process's cwd in ONE batch call, never one call per
    pid. Owner ruling 2026-10-10: about 1,300 pids at 27 ms each overran the 60 s hook timeout,
    12 times in one session. The fake table answers `lsof` only (macOS cwd read), and counts
    every `lsof` call. A per-pid read carries `-p PID`, a batch read does not."""

    @classmethod
    def setUpClass(cls):
        import agent_end_reap
        cls.reap = agent_end_reap
        cls.root = tempfile.mkdtemp(prefix="reap_batch_")
        cls.target = os.path.realpath(os.path.join(cls.root, ".claude", "worktrees", "agent-batch"))
        os.makedirs(os.path.join(cls.target, "sub"))
        cls.in_reap = {100, 200}   # inside the target, orphaned, owned by this user: reaped
        cls.in_foreign = 300       # inside the target, orphaned, another user's: kept
        cls.table = {pid: "/elsewhere/p%d" % pid for pid in range(2, 1302)}
        cls.table[100] = os.path.join(cls.target, "sub")
        cls.table[200] = cls.target
        cls.table[cls.in_foreign] = os.path.join(cls.target, "sub")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def setUp(self):
        self.lsof_calls = []
        self.fail_batch = False

    def fake_lsof(self, argv, *a, **k):
        if argv and argv[0] == "lsof":
            self.lsof_calls.append(list(argv))
            if "-p" in argv:   # a per-pid read
                cwd = self.table.get(int(argv[argv.index("-p") + 1]))
                if cwd is None:
                    return subprocess.CompletedProcess(argv, 1, "", "")
                return subprocess.CompletedProcess(argv, 0, "n" + cwd + "\n", "")
            if self.fail_batch:   # the batch read itself cannot answer
                return subprocess.CompletedProcess(argv, 2, "", "lsof failed")
            text = "".join("p%d\nn%s\n" % (pid, cwd) for pid, cwd in self.table.items())
            return subprocess.CompletedProcess(argv, 0, text, "")
        return subprocess.CompletedProcess(argv, 1, "", "")

    def decide_with_table(self):
        pids = list(range(2, 1302))
        patches = [
            mock.patch.object(sys, "platform", "darwin"),
            mock.patch.object(sweep.subprocess, "run", self.fake_lsof),
            mock.patch.object(sweep, "list_all_pids", lambda: list(pids)),
            mock.patch.object(sweep, "_is_primary_checkout", lambda path: False),
            mock.patch.object(sys.modules["guard_core"], "worktree_live_session", lambda path: False),
            mock.patch.object(sweep, "is_orphan", lambda pid: True),
            mock.patch.object(sweep, "is_current_user_process",
                              lambda pid: pid != self.in_foreign),
            mock.patch.object(sweep, "process_command", lambda pid: "fake %d" % pid),
        ]
        for patch in patches:
            patch.start()
        try:
            return self.reap.decide(self.target)
        finally:
            for patch in patches:
                patch.stop()

    def test_decide_reads_every_process_cwd_in_one_batch_call(self):
        reason, _decisions = self.decide_with_table()
        self.assertIsNone(reason)
        self.assertEqual(len(self.lsof_calls), 1,
                         "cwd reads for 1,300 pids: %d; want one batch read" % len(self.lsof_calls))
        self.assertTrue(all("-p" not in call for call in self.lsof_calls),
                        "the one read is per-pid, not a batch: %r" % self.lsof_calls)

    def test_decide_never_calls_the_per_pid_cwd_reader_over_1300_pids(self):
        # Counts calls, not seconds: a timing bound flakes on a loaded machine.
        calls = []

        def counting_reader(pid):
            calls.append(pid)
            return self.table.get(pid)
        with mock.patch.object(sweep, "process_cwd", counting_reader):
            self.decide_with_table()
        self.assertEqual(calls, [], "per-pid cwd reads over 1,300 pids: %d" % len(calls))

    def test_decide_still_reaps_and_keeps_the_same_pids_from_the_table(self):
        reason, decisions = self.decide_with_table()
        self.assertIsNone(reason)
        reaped = {d["pid"]: d["reason"] for d in decisions if d["action"] == "reap"}
        kept = {d["pid"]: d["reason"] for d in decisions if d["action"] == "keep"}
        self.assertEqual(reaped, {100: "agent-ended", 200: "agent-ended"})
        self.assertEqual(kept, {self.in_foreign: "not-current-user"})

    def test_a_failed_batch_read_keeps_everything_even_when_per_pid_reads_work(self):
        self.fail_batch = True   # per-pid reads still answer, so only the batch failure stops reaps
        reason, decisions = self.decide_with_table()
        self.assertNotIn("reap", [d["action"] for d in decisions],
                         "a batch read that cannot answer must keep everything")
        self.assertIn(reason, (None, "unreadable-subject"))


class AgentEndReapTests(unittest.TestCase):
    """janitor/agent_end_reap.py and the deepest-checkout match it depends on. Real repo, real
    worktrees under `.claude/worktrees/`, real listener processes this suite starts itself."""

    @classmethod
    def setUpClass(cls):
        import agent_end_reap
        cls.reap = agent_end_reap
        cls.repo = os.path.join(ROOT, "reap-primary")
        make_repo(cls.repo, {"f.txt": "base\n"})
        give_remote(cls.repo)
        cls.wts = {}
        for name in ("reapA", "reapB", "reapLive"):
            path = os.path.join(cls.repo, ".claude", "worktrees", "agent-" + name)
            run_vcs(cls.repo, "worktree", "add", "-q", path, "-b", "lane-" + name)
            require(os.path.isdir(path), "worktree %s was not created" % path)
            cls.wts[name] = path

    def same(self, a, b):
        self.assertEqual(os.path.normcase(os.path.realpath(a)), os.path.normcase(os.path.realpath(b)))

    def decision_for(self, target, pid):
        reason, decisions = self.reap.decide(target)
        self.assertIsNone(reason)
        self.assertTrue(len(decisions) > 0, "no process found inside %s" % target)
        for decision in decisions:
            if decision["pid"] == pid:
                return decision
        self.fail("pid %r not among %r" % (pid, [d["pid"] for d in decisions]))

    def test_the_deepest_checkout_wins_over_the_primary_that_contains_it(self):
        cwd = os.path.join(self.wts["reapA"], "sub")
        self.same(sweep._matching_checkout(cwd, [self.repo, self.wts["reapA"]]), self.wts["reapA"])
        self.same(sweep._matching_checkout(os.path.join(self.repo, "f"), [self.repo, self.wts["reapA"]]),
                  self.repo)

    def test_subagent_stop_names_the_agent_worktree_from_any_cwd(self):
        for cwd in (self.wts["reapA"], self.repo):
            target = self.reap.target_worktree(
                {"hook_event_name": "SubagentStop", "agent_id": "reapA", "cwd": cwd})
            self.assertIsNotNone(target)
            self.same(target, self.wts["reapA"])

    def test_an_unsafe_or_unknown_agent_id_names_nothing(self):
        # "reapA/../agent-reapB" would name agent B's worktree if the id were not checked.
        for agent_id in ("../reapA", "reapA/..", "reapA/../agent-reapB", "", "nosuchagent", None):
            self.assertIsNone(self.reap.target_worktree(
                {"hook_event_name": "SubagentStop", "agent_id": agent_id, "cwd": self.repo}))

    def test_only_subagent_stop_names_a_target(self):
        # Owner ruling 1, 2026-09-27: WorktreeRemove stays unwired and names nothing.
        self.assertIsNone(self.reap.target_worktree(
            {"hook_event_name": "WorktreeRemove", "worktree_path": self.wts["reapA"]}))
        self.assertIsNone(self.reap.target_worktree({"hook_event_name": "Stop", "cwd": self.repo}))

    def test_the_primary_checkout_is_never_a_target(self):
        self.assertEqual(self.reap.decide(self.repo)[0], "primary-checkout")

    def test_an_orphan_inside_the_ended_agent_worktree_is_reaped(self):
        pid, _port, cleanup = spawn_orphaned_listener(self.wts["reapA"])
        try:
            decision = self.decision_for(self.wts["reapA"], pid)
            self.assertEqual((decision["action"], decision["reason"]), ("reap", "agent-ended"))
        finally:
            cleanup()

    def test_a_process_whose_live_parent_sits_outside_is_kept(self):
        pid, _port, cleanup = spawn_plain_listener(self.wts["reapA"])
        try:
            decision = self.decision_for(self.wts["reapA"], pid)
            self.assertEqual((decision["action"], decision["reason"]), ("keep", "not-orphaned"))
        finally:
            cleanup()

    def test_an_orphan_in_another_worktree_is_not_even_considered(self):
        pid, _port, cleanup = spawn_orphaned_listener(self.wts["reapB"])
        try:
            _reason, decisions = self.reap.decide(self.wts["reapA"])
            self.assertNotIn(pid, [d["pid"] for d in decisions])
        finally:
            cleanup()

    def test_a_live_session_in_the_worktree_keeps_everything(self):
        pid, _port, cleanup = spawn_orphaned_listener(self.wts["reapLive"])
        record = os.path.join(CFG, "sessions", "reap-live-case.json")
        try:
            write_session("reap-live-case", os.getpid(), this_process_start_ms(), self.wts["reapLive"])
            self.assertEqual(self.reap.decide(self.wts["reapLive"]), ("live-session", []))
        finally:
            os.remove(record)
            cleanup()

    def test_the_sweep_leaves_an_orphan_in_an_agent_worktree_to_the_reaper(self):
        # Owner ruling 2, 2026-09-27: no session record names a subagent, so the sweep
        # skips every `.claude/worktrees/*` cwd, even a proven orphan.
        pid, _port, cleanup = spawn_orphaned_listener(self.wts["reapB"])
        try:
            found = sweep.find_swept_listeners([self.repo, self.wts["reapB"]])
            self.assertIsNotNone(found)
            self.assertNotIn(pid, [entry["pid"] for entry in found])
        finally:
            cleanup()

    def test_junk_on_stdin_names_no_target_and_raises_nothing(self):
        for raw in ("", "not json", "[1]", json.dumps({"hook_event_name": "SubagentStop"})):
            self.assertIsNone(self.reap.handle(raw).get("target"))

    def test_the_payload_log_keeps_only_the_last_200_lines(self):
        folder = os.path.join(ROOT, "reap-log")
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": folder}):
            for number in range(205):
                self.reap.log({"raw": "payload %d" % number})
            with open(self.reap.log_path(), encoding="utf-8") as handle:
                lines = handle.read().splitlines()
        self.assertEqual(len(lines), 200)
        self.assertEqual(json.loads(lines[0])["raw"], "payload 5")
        self.assertEqual(json.loads(lines[-1])["raw"], "payload 204")

    def test_the_payload_log_keeps_a_line_when_the_first_replace_is_denied(self):
        # Windows: os.replace raises PermissionError(13) while a scanner holds the destination.
        folder = os.path.join(ROOT, "reap-log-retry")
        real_replace = os.replace
        denied = []

        def replace_denied_once(src, dst):
            if not denied:
                denied.append(src)
                raise PermissionError(13, "Access is denied")
            return real_replace(src, dst)

        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": folder}):
            for number in range(3):
                self.reap.log({"raw": "payload %d" % number})
            with mock.patch.object(self.reap.os, "replace", new=replace_denied_once):
                self.reap.log({"raw": "payload 3"})
            with open(self.reap.log_path(), encoding="utf-8") as handle:
                raws = [json.loads(line)["raw"] for line in handle.read().splitlines()]
        self.assertEqual(len(denied), 1, "the injected PermissionError was never reached")
        self.assertIn("payload 3", raws)


BUILD_DIRS = ("native/build", "DegenKit/.build", "DerivedData")
REAP_HOOK = os.path.join(HERE, "agent_end_reap.py")
JANITOR = os.path.join(HERE, "sweep.py")


class BuildDirReapTests(unittest.TestCase):
    """Decision build-dirs-reaped-at-agent-end, Part 1. The SubagentStop reap deletes build folders
    in the finished agent's worktree: `native/build`, a bare `.build` at any depth, `DerivedData`,
    and each `buildDirs` name from `.claude/janitor.json`. Each delete is a rename to a trash name,
    then a detached child deletes the trash.

    Real git repos, real hook processes (`agent_end_reap.py` run as the harness runs it). Every
    fixture is a few small files. Each keep arm sits beside a control arm that must delete, so a
    keep arm cannot pass on a reaper that deletes nothing. The trash-name contract is two
    functions the builder exports: `trash_name(folder)` (the sibling path a reap renames to) and
    `is_trash_name(basename)`.
    """

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="bdr_cases_")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.cfg = os.path.join(self.root, "cfg")  # the config dir the hook process reads and writes
        import agent_end_reap
        self.reap = agent_end_reap

    def make_primary(self, tag, janitor=None):
        primary = os.path.join(self.root, tag)
        make_repo(primary, {"f.txt": "base\n"})
        if janitor is not None:
            write(os.path.join(primary, ".claude", "janitor.json"), janitor)
        return primary

    def add_agent(self, primary, agent):
        wt = os.path.join(primary, ".claude", "worktrees", "agent-" + agent)
        run_vcs(primary, "worktree", "add", "-q", wt, "-b", "lane-" + agent)
        require(os.path.isdir(wt), "worktree %s was not created" % wt)
        # One unmerged commit, so the janitor keeps the worktree itself and only trash is in play.
        write(os.path.join(wt, "lane.txt"), agent + "\n")
        run_vcs(wt, "add", "lane.txt")
        commit = run_vcs(wt, *IDENT, "commit", "-q", "-m", "lane work " + agent)
        require(commit.returncode == 0, "lane commit in %s failed: %s" % (wt, commit.stderr.strip()))
        return wt

    def fill(self, base, rels=BUILD_DIRS):
        for rel in rels:
            write(os.path.join(base, rel, "payload.bin"), "x" * 1024 + "\n")

    def run_hook(self, agent, wt):
        """Run the SubagentStop hook as the harness does. Return its wall time in seconds."""
        payload = json.dumps({"hook_event_name": "SubagentStop", "agent_id": agent,
                              "cwd": wt, "session_id": "bdr-cases"})
        env = dict(os.environ, CLAUDE_CONFIG_DIR=self.cfg)
        started = time.monotonic()
        result = subprocess.run([sys.executable, REAP_HOOK], input=payload, capture_output=True,
                                text=True, env=env, timeout=120)
        elapsed = time.monotonic() - started
        self.assertEqual(result.returncode, 0, "hook exited %d: %s" % (result.returncode,
                                                                       result.stderr[-300:]))
        return elapsed

    def hold_cwd(self, folder):
        """A live process whose cwd is FOLDER. The test started it, so the test stops it."""
        proc = subprocess.Popen(["sleep", "120"], cwd=folder, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self.stop_proc, proc)
        return proc

    @staticmethod
    def stop_proc(proc):
        proc.kill()
        proc.wait(timeout=10)

    def wait_gone(self, path, seconds=30):
        """Bounded wait for a detached child to delete PATH. Capped at SECONDS; never unbounded."""
        deadline = time.monotonic() + seconds
        while os.path.exists(path) and time.monotonic() < deadline:
            time.sleep(0.2)
        return not os.path.exists(path)

    def test_native_build_bare_build_at_depth_and_derived_data_are_reaped(self):
        primary = self.make_primary("reap")
        wt = self.add_agent(primary, "bdrA")
        self.fill(wt)
        self.run_hook("bdrA", wt)
        for rel in BUILD_DIRS:
            with self.subTest(folder=rel):
                self.assertFalse(os.path.exists(os.path.join(wt, rel)),
                                 "%s in the ended agent worktree was not reaped" % rel)

    def test_the_same_folders_in_the_primary_checkout_are_kept(self):
        primary = self.make_primary("kept-primary")
        wt = self.add_agent(primary, "bdrA")
        self.fill(wt)
        self.fill(primary)
        self.run_hook("bdrA", wt)
        with self.subTest(control="agent worktree"):
            for rel in BUILD_DIRS:
                self.assertFalse(os.path.exists(os.path.join(wt, rel)), "%s not reaped" % rel)
        with self.subTest(arm="primary checkout"):
            for rel in BUILD_DIRS:
                self.assertTrue(os.path.isdir(os.path.join(primary, rel)),
                                "%s in the primary checkout was removed" % rel)

    def test_a_link_named_as_a_build_folder_is_kept_and_its_target_untouched(self):
        primary = self.make_primary("link")
        wt = self.add_agent(primary, "bdrA")
        self.fill(wt, ("native/build", "DerivedData"))
        outside = os.path.join(self.root, "outside")
        write(os.path.join(outside, "keep.txt"), "not ours\n")
        os.symlink(outside, os.path.join(wt, ".build"))
        self.run_hook("bdrA", wt)
        with self.subTest(control="native/build"):
            self.assertFalse(os.path.exists(os.path.join(wt, "native", "build")))
        with self.subTest(arm="link .build"):
            self.assertTrue(os.path.islink(os.path.join(wt, ".build")), "the link was removed")
            self.assertTrue(os.path.isfile(os.path.join(outside, "keep.txt")),
                            "the link's target was touched")

    def test_a_folder_with_a_live_process_cwd_inside_is_kept(self):
        primary = self.make_primary("proc")
        wt = self.add_agent(primary, "bdrA")
        self.fill(wt)
        self.hold_cwd(os.path.join(wt, "DerivedData"))
        self.run_hook("bdrA", wt)
        with self.subTest(control="native/build and DegenKit/.build"):
            self.assertFalse(os.path.exists(os.path.join(wt, "native", "build")))
            self.assertFalse(os.path.exists(os.path.join(wt, "DegenKit", ".build")))
        with self.subTest(arm="DerivedData with a live cwd"):
            self.assertTrue(os.path.isdir(os.path.join(wt, "DerivedData")),
                            "DerivedData with a live process inside was removed")

    def test_a_live_session_inside_the_worktree_keeps_everything(self):
        primary = self.make_primary("live")
        live = self.add_agent(primary, "bdrLive")
        other = self.add_agent(primary, "bdrB")
        self.fill(live)
        self.fill(other)
        write(os.path.join(self.cfg, "sessions", "bdr-live.json"),
              json.dumps({"pid": os.getpid(), "startedAt": this_process_start_ms(), "cwd": live}))
        self.run_hook("bdrLive", live)
        self.run_hook("bdrB", other)
        with self.subTest(control="agent-bdrB with no session"):
            for rel in BUILD_DIRS:
                self.assertFalse(os.path.exists(os.path.join(other, rel)), "%s not reaped" % rel)
        with self.subTest(arm="agent-bdrLive with a live session"):
            for rel in BUILD_DIRS:
                self.assertTrue(os.path.isdir(os.path.join(live, rel)),
                                "%s removed under a live session" % rel)

    def test_a_bad_build_dirs_value_deletes_nothing(self):
        clean = self.make_primary("clean")
        clean_wt = self.add_agent(clean, "bdrOk")
        self.fill(clean_wt)
        self.run_hook("bdrOk", clean_wt)
        with self.subTest(control="checkout with no janitor.json reaps the defaults"):
            for rel in BUILD_DIRS:
                self.assertFalse(os.path.exists(os.path.join(clean_wt, rel)), "%s not reaped" % rel)
        for number, bad in enumerate(("Pods/Build", ["Pods/Build", 7])):
            with self.subTest(buildDirs=bad):
                primary = self.make_primary("bad%d" % number,
                                            janitor=json.dumps({"buildDirs": bad}))
                wt = self.add_agent(primary, "bdrBad")
                self.fill(wt)
                self.run_hook("bdrBad", wt)
                for rel in BUILD_DIRS:
                    self.assertTrue(os.path.isdir(os.path.join(wt, rel)),
                                    "%s deleted under a bad buildDirs value" % rel)

    def test_a_buildDirs_name_adds_a_folder_at_its_depth(self):
        primary = self.make_primary("names", janitor=json.dumps(
            {"buildDirs": ["Pods/Build", "scratch-out"]}))
        wt = self.add_agent(primary, "bdrA")
        self.fill(wt)
        self.fill(wt, ("Pods/Build", "Sub/scratch-out"))
        self.run_hook("bdrA", wt)
        with self.subTest(control="a default folder"):
            self.assertFalse(os.path.exists(os.path.join(wt, "native", "build")))
        with self.subTest(name="Pods/Build"):
            self.assertFalse(os.path.exists(os.path.join(wt, "Pods", "Build")))
        with self.subTest(name="scratch-out, a bare name at depth"):
            self.assertFalse(os.path.exists(os.path.join(wt, "Sub", "scratch-out")))

    def test_the_hook_renames_the_build_folder_first_and_returns_before_the_delete(self):
        primary = self.make_primary("ret")
        wt = self.add_agent(primary, "bdrR")
        self.fill(wt, ("native/build",))
        build = os.path.realpath(os.path.join(wt, "native", "build"))
        gate = threading.Event()
        renames = []
        real_rename, real_replace = os.rename, os.replace

        def recorded(real):
            def inner(src, dst, *args, **kwargs):
                renames.append((os.path.realpath(src), os.path.realpath(dst)))
                return real(src, dst, *args, **kwargs)
            return inner

        def held_delete(*args, **kwargs):
            gate.wait(30)  # a delete made in the hook's own process waits here, so the hook hangs

        payload = json.dumps({"hook_event_name": "SubagentStop", "agent_id": "bdrR",
                              "cwd": wt, "session_id": "bdr-cases"})
        worker = threading.Thread(target=self.reap.handle, args=(payload,), daemon=True)
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": self.cfg}), \
                mock.patch.object(os, "rename", recorded(real_rename)), \
                mock.patch.object(os, "replace", recorded(real_replace)), \
                mock.patch.object(shutil, "rmtree", held_delete), \
                mock.patch.object(os, "remove", held_delete):
            worker.start()
            worker.join(30)
            returned = not worker.is_alive()
            gate.set()
            worker.join(30)
        self.assertTrue(returned, "the hook did not return while the delete was held")
        moves = [(src, dst) for src, dst in renames if src == build]
        self.assertTrue(moves, "the build folder was never renamed to a trash name first")
        self.assertEqual(os.path.dirname(moves[0][1]), os.path.dirname(build),
                         "the trash name is not a sibling on the same volume")
        self.assertFalse(os.path.exists(build), "the build folder is still at its own name")

    def test_a_later_reap_deletes_a_leftover_trash_name_and_keeps_a_name_outside_the_pattern(self):
        primary = self.make_primary("later")
        wt = self.add_agent(primary, "bdrT")
        trash = self.reap.trash_name(os.path.join(wt, "native", "build"))
        self.assertTrue(self.reap.is_trash_name(os.path.basename(trash)),
                        "the trash name the reap renames to is not a trash name")
        self.assertFalse(self.reap.is_trash_name("notes-not-trash"))
        self.fill(os.path.dirname(trash), (os.path.basename(trash),))
        notes = os.path.join(wt, "notes-not-trash")
        write(os.path.join(notes, "keep.txt"), "not trash\n")
        self.run_hook("bdrT", wt)
        with self.subTest(arm="notes-not-trash"):
            self.assertTrue(os.path.isfile(os.path.join(notes, "keep.txt")),
                            "a name outside the trash pattern was deleted")
        with self.subTest(control="leftover trash name"):
            self.assertTrue(self.wait_gone(trash), "a later reap left the trash name on disk")

    def test_a_trash_name_with_a_live_process_inside_is_kept(self):
        primary = self.make_primary("trashproc")
        wt = self.add_agent(primary, "bdrT")
        free = self.reap.trash_name(os.path.join(wt, "native", "build"))
        live = self.reap.trash_name(os.path.join(wt, "DerivedData"))
        self.fill(os.path.dirname(free), (os.path.basename(free),))
        self.fill(os.path.dirname(live), (os.path.basename(live),))
        self.hold_cwd(live)
        self.run_hook("bdrT", wt)
        with self.subTest(control="leftover trash with no process"):
            self.assertTrue(self.wait_gone(free), "a leftover trash name was left on disk")
        with self.subTest(arm="leftover trash with a live cwd"):
            self.assertTrue(os.path.isdir(live), "a trash name with a live process inside was deleted")

    def test_the_janitor_deletes_a_leftover_trash_name_and_keeps_one_with_a_live_process(self):
        primary = self.make_primary("janitor")
        wt = self.add_agent(primary, "bdrJ")
        free = self.reap.trash_name(os.path.join(wt, "native", "build"))
        live = self.reap.trash_name(os.path.join(wt, "DerivedData"))
        self.fill(os.path.dirname(free), (os.path.basename(free),))
        self.fill(os.path.dirname(live), (os.path.basename(live),))
        self.hold_cwd(live)
        env = dict(os.environ, CLAUDE_CONFIG_DIR=self.cfg)
        result = subprocess.run([sys.executable, JANITOR, primary, "--confirm"], capture_output=True,
                                text=True, env=env, timeout=120)
        self.assertEqual(result.returncode, 0, "janitor exited %d: %s"
                         % (result.returncode, result.stderr[-300:]))
        with self.subTest(control="leftover trash with no process"):
            self.assertFalse(os.path.exists(free), "the janitor left a leftover trash name")
        with self.subTest(arm="leftover trash with a live cwd"):
            self.assertTrue(os.path.isdir(live), "the janitor deleted a trash name with a live process")


    @unittest.skipUnless(os.name == "nt", "a junction is a Windows folder link")
    def test_junction_as_the_worktree_path_is_never_reaped_through(self):
        primary = self.make_primary("junction-wt")
        base = os.path.join(self.root, "elsewhere")
        write(os.path.join(base, "DerivedData", "payload.bin"), "x\n")
        link = os.path.join(primary, ".claude", "worktrees", "agent-x")
        make_junction(link, base)
        self.assertEqual(self.reap.reap_build_dirs(link, []), [])
        deadline = time.monotonic() + 2  # a detached child, if one ran, would act inside this window
        while time.monotonic() < deadline:
            time.sleep(0.2)
        self.assertEqual(os.listdir(base), ["DerivedData"], "the target was renamed or gained a trash name")
        self.assertTrue(os.path.isfile(os.path.join(base, "DerivedData", "payload.bin")),
                        "the target's DerivedData lost its file")

    @unittest.skipUnless(os.name == "nt", "a junction is a Windows folder link")
    def test_junction_inside_a_build_folder_is_unlinked_and_its_target_kept(self):
        primary = self.make_primary("junction", janitor=json.dumps({"buildDirs": ["build"]}))
        wt = self.add_agent(primary, "bdrJ")
        base, target = junction_fixture(self)
        self.fill(wt, ("build",))
        make_junction(os.path.join(wt, "build", "link"), target)
        renamed = self.reap.reap_build_dirs(wt, [])
        with self.subTest(control="the build folder is reaped"):
            self.assertEqual(renamed, [os.path.join(wt, "build")])
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and any(
                    self.reap.is_trash_name(n) for n in os.listdir(wt)):
                time.sleep(0.2)
            self.assertFalse([n for n in os.listdir(wt) if self.reap.is_trash_name(n)],
                             "the trash folder was not deleted in 10 s")
        with self.subTest(arm="the junction target"):
            self.assertTrue(os.path.isfile(os.path.join(target, "keep.txt")))
            self.assertTrue(os.path.isfile(os.path.join(target, "node_modules", "x.txt")))


class StrictWorktreeTests(unittest.TestCase):
    """Owner ruling: --confirm removes a worktree only when it is merged (by patch, not
    ancestry) and idle 1 hour. A person passes --attended for the old rules."""

    @classmethod
    def setUpClass(cls):
        cls.root = os.path.join(ROOT, "unatt-repo")
        make_repo(cls.root, {"f.txt": "base\n"})
        give_remote(cls.root)
        # lane-unmerged: a commit pushed to origin, on no default branch.
        cls.unmerged = os.path.join(ROOT, "unatt-unmerged")
        run_vcs(cls.root, "worktree", "add", "-q", cls.unmerged, "-b", "lane-unmerged")
        write(os.path.join(cls.unmerged, "u.txt"), "only on the lane\n")
        run_vcs(cls.unmerged, "add", "u.txt")
        run_vcs(cls.unmerged, *IDENT, "commit", "-q", "-m", "unmerged")
        require(run_vcs(cls.unmerged, "push", "-q", "origin", "lane-unmerged").returncode == 0,
                "pushing lane-unmerged failed")
        # lane-patch: same patch as a commit on main, other commit id, pushed.
        cls.patch = os.path.join(ROOT, "unatt-patch")
        run_vcs(cls.root, "worktree", "add", "-q", cls.patch, "-b", "lane-patch")
        write(os.path.join(cls.patch, "p.txt"), "same patch\n")
        run_vcs(cls.patch, "add", "p.txt")
        run_vcs(cls.patch, *IDENT, "commit", "-q", "-m", "patch on the lane")
        require(run_vcs(cls.patch, "push", "-q", "origin", "lane-patch").returncode == 0,
                "pushing lane-patch failed")
        write(os.path.join(cls.root, "p.txt"), "same patch\n")
        run_vcs(cls.root, "add", "p.txt")
        run_vcs(cls.root, *IDENT, "commit", "-q", "-m", "patch on main")
        require(run_vcs(cls.root, "push", "-q", "origin", "main").returncode == 0,
                "pushing main failed")
        # lane-merged: at main's own tip, so an ancestor.
        cls.merged = os.path.join(ROOT, "unatt-merged")
        run_vcs(cls.root, "worktree", "add", "-q", cls.merged, "-b", "lane-merged")
        cls.entries = {os.path.normcase(os.path.realpath(e["path"])): e
                       for e in sweep.parse_worktree_list(cls.root)}

    def entry(self, path):
        return self.entries[os.path.normcase(os.path.realpath(path))]

    def age(self, path, seconds, only=None):
        """Set the worktree's admin files `seconds` old, except `only`, left fresh."""
        admin = run_vcs(path, "rev-parse", "--absolute-git-dir").stdout.strip()
        for name in ("index", "HEAD", os.path.join("logs", "HEAD")):
            target = os.path.join(admin, name)
            then = time.time() - (0 if name == only else seconds)
            if os.path.exists(target):
                os.utime(target, (then, then))

    def decide(self, path, attended=False):
        return sweep.decide_worktree(self.root, self.entry(path), attended)

    def test_strict_keeps_a_pushed_but_unmerged_tree(self):
        self.age(self.unmerged, 7200)
        decision = self.decide(self.unmerged)
        self.assertEqual(decision["action"], "keep")
        self.assertTrue(decision["reason"].startswith("unmerged"), decision["reason"])

    # Owner ruling 2026-10-09 (decisions/unattended-sweep-stops-proven-orphans.md): a pushed,
    # clean, unmerged tree idle 24 hours is removable. Under 24 hours it is still kept.
    def test_strict_removes_a_pushed_unmerged_tree_idle_25_hours(self):
        self.age(self.unmerged, 25 * 3600)
        decision = self.decide(self.unmerged)
        self.assertEqual(decision["action"], "reap", decision["reason"])
        self.assertEqual(decision["reason"], "removable")

    def test_strict_keeps_a_pushed_unmerged_tree_idle_23_hours(self):
        self.age(self.unmerged, 23 * 3600)
        decision = self.decide(self.unmerged)
        self.assertEqual(decision["action"], "keep")
        self.assertTrue(decision["reason"].startswith("unmerged"), decision["reason"])

    def test_strict_keeps_an_unpushed_tree_idle_48_hours(self):
        path = os.path.join(ROOT, "unatt-unpushed")
        run_vcs(self.root, "worktree", "add", "-q", path, "-b", "lane-unpushed")
        write(os.path.join(path, "local.txt"), "a commit on no remote\n")
        run_vcs(path, "add", "local.txt")
        run_vcs(path, *IDENT, "commit", "-q", "-m", "local only")
        self.age(path, 48 * 3600)
        entries = {os.path.normcase(os.path.realpath(e["path"])): e
                   for e in sweep.parse_worktree_list(self.root)}
        decision = sweep.decide_worktree(self.root, entries[os.path.normcase(os.path.realpath(path))])
        self.assertEqual(decision["action"], "keep")
        self.assertTrue(decision["reason"].startswith("unpushed"), decision["reason"])

    def test_strict_keeps_a_merged_tree_active_10_minutes_ago(self):
        self.age(self.merged, 600)
        decision = self.decide(self.merged)
        self.assertEqual(decision["action"], "keep")
        self.assertTrue(decision["reason"].startswith("recently-active"), decision["reason"])

    def test_strict_activity_in_any_one_admin_file_keeps_the_tree(self):
        for name in ("index", "HEAD", os.path.join("logs", "HEAD")):
            self.age(self.merged, 7200, only=name)
            decision = self.decide(self.merged)
            self.assertEqual(decision["action"], "keep", name)
            self.assertTrue(decision["reason"].startswith("recently-active"), name)

    def test_strict_removes_a_merged_tree_idle_2_hours(self):
        self.age(self.merged, 7200)
        decision = self.decide(self.merged)
        self.assertEqual(decision["action"], "reap")
        self.assertEqual(decision["reason"], "removable")

    def test_strict_removes_a_tree_merged_by_patch_idle_2_hours(self):
        self.age(self.patch, 7200)
        decision = self.decide(self.patch)
        self.assertEqual(decision["action"], "reap")
        self.assertEqual(decision["reason"], "removable")

    def test_strict_keeps_a_tree_whose_idle_time_cannot_be_read(self):
        with mock.patch.object(sweep, "worktree_idle_seconds", return_value=None):
            decision = self.decide(self.merged)
        self.assertEqual(decision["action"], "keep")
        self.assertEqual(decision["reason"], "unreadable-subject")
        self.assertIsNone(sweep.worktree_idle_seconds(os.path.join(ROOT, "no-such-tree")))

    def test_an_unmerged_tree_whose_idle_time_cannot_be_read_is_unreadable_not_unmerged(self):
        """P2 (review of 6351ac2): an unmerged tree the sweep cannot age keeps as
        unreadable-subject. The reason "unmerged" names a fact the sweep does not have yet."""
        with mock.patch.object(sweep, "worktree_idle_seconds", return_value=None):
            decision = self.decide(self.unmerged)
        self.assertEqual(decision["action"], "keep")
        self.assertEqual(decision["reason"], "unreadable-subject", decision["reason"])

    def test_a_persons_run_removes_an_unmerged_active_tree_as_before(self):
        self.age(self.unmerged, 60)
        decision = self.decide(self.unmerged, attended=True)
        self.assertEqual(decision["action"], "reap")
        self.assertEqual(decision["reason"], "removable")

    def test_the_attended_flag_reaches_the_sweep(self):
        self.age(self.unmerged, 7200)
        def mine(**kw):
            result = sweep.sweep_repo(self.root, False, os.path.join(ROOT, "unatt.log"), **kw)
            found = [d for d in result["worktrees"]
                     if os.path.normcase(os.path.realpath(d["path"]))
                     == os.path.normcase(os.path.realpath(self.unmerged))]
            self.assertEqual(len(found), 1)
            return found[0]["reason"]

        self.assertTrue(mine().startswith("unmerged"))  # strict with no flag at all
        self.age(self.unmerged, 7200)
        self.assertEqual(mine(attended=True), "removable")

    def test_strict_removes_a_detached_merged_tree_and_keeps_a_detached_unmerged_one(self):
        merged = os.path.join(ROOT, "unatt-detached-merged")
        run_vcs(self.root, "worktree", "add", "-q", "--detach", merged, "main")
        unmerged = os.path.join(ROOT, "unatt-detached-unmerged")
        run_vcs(self.root, "worktree", "add", "-q", "--detach", unmerged, "lane-unmerged")
        entries = {os.path.normcase(os.path.realpath(e["path"])): e
                   for e in sweep.parse_worktree_list(self.root)}
        for path, action, reason in ((merged, "reap", "removable"),
                                     (unmerged, "keep", "unmerged")):
            self.age(path, 7200)
            decision = sweep.decide_worktree(
                self.root, entries[os.path.normcase(os.path.realpath(path))])
            self.assertEqual(decision["action"], action, path)
            self.assertTrue(decision["reason"].startswith(reason), decision["reason"])

    def test_main_takes_the_attended_flag(self):
        seen = []

        def spy(root, confirm, log, mode="full", attended=False):
            seen.append(attended)
            return {"root": root, "refused": "opted-out", "branches": [], "worktrees": [],
                    "listeners": [], "pruned": None, "husks": []}

        with mock.patch.object(sweep, "sweep_repo", spy), \
                contextlib.redirect_stdout(io.StringIO()):
            sweep.main(["--root", self.root, "--attended",
                        "--restore-log", os.path.join(ROOT, "unatt.log")])
            sweep.main(["--root", self.root, "--restore-log", os.path.join(ROOT, "unatt.log")])
        self.assertEqual(seen, [True, False])


class RemoteLivenessTests(unittest.TestCase):
    """P1 (review of 6351ac2): "pushed" means reachable from a head the remote lists NOW, read
    with `git ls-remote` (read-only). This clone is never fetched or pruned, so a branch deleted
    on the remote leaves a local refs/remotes/origin/<branch> that still names the commit. Local
    refs alone then call the tree pushed, and an idle one gets reaped. An unreadable remote keeps."""

    @classmethod
    def setUpClass(cls):
        base = os.path.join(ROOT, "remote-live")
        os.makedirs(base, exist_ok=True)
        cls.bare = os.path.join(base, "origin.git")
        run_vcs(base, "init", "-q", "--bare", cls.bare)
        cls.root = os.path.join(base, "clone")
        make_repo(cls.root, {"f.txt": "base\n"})
        require(run_vcs(cls.root, "remote", "add", "origin", cls.bare).returncode == 0,
                "adding origin failed")
        require(run_vcs(cls.root, "push", "-q", "origin", "main").returncode == 0,
                "pushing main failed")
        cls.gone = cls._pushed_lane("lane-gone")
        cls.live = cls._pushed_lane("lane-live")
        # Delete lane-gone ON THE REMOTE only. The clone keeps its own refs/remotes/origin/lane-gone.
        require(run_vcs(cls.bare, "update-ref", "-d", "refs/heads/lane-gone").returncode == 0,
                "deleting lane-gone on the remote failed")
        require(run_vcs(cls.root, "rev-parse", "--verify", "-q",
                        "refs/remotes/origin/lane-gone").returncode == 0,
                "the clone's own tracking ref for lane-gone is missing")
        listed = run_vcs(cls.root, "ls-remote", "origin").stdout
        require("refs/heads/lane-gone" not in listed, "lane-gone is still listed on the remote")

    @classmethod
    def _pushed_lane(cls, branch):
        path = os.path.join(ROOT, "remote-live-" + branch)
        require(run_vcs(cls.root, "worktree", "add", "-q", path, "-b", branch).returncode == 0,
                "adding the worktree for %s failed" % branch)
        write(os.path.join(path, branch + ".txt"), "work on %s\n" % branch)
        run_vcs(path, "add", "-A")
        require(run_vcs(path, *IDENT, "commit", "-q", "-m", branch).returncode == 0,
                "committing on %s failed" % branch)
        require(run_vcs(path, "push", "-q", "origin", branch).returncode == 0,
                "pushing %s failed" % branch)
        return path

    def entry(self, path):
        target = _norm_path(path)
        for e in sweep.parse_worktree_list(self.root):
            if _norm_path(e["path"]) == target:
                return e
        self.fail("no worktree-list entry for %r" % path)

    def test_a_branch_deleted_on_the_remote_is_not_pushed_so_its_tree_is_kept(self):
        _age_admin_files(self.gone, 25 * 3600)
        decision = sweep.decide_worktree(self.root, self.entry(self.gone))
        self.assertEqual(decision["action"], "keep", decision)
        self.assertTrue(decision["reason"].startswith("unpushed"), decision["reason"])
        self.assertIs(sweep.fully_pushed(self.gone), False)

    def test_a_branch_still_live_on_the_remote_is_pushed_so_idle_25_hours_is_reaped(self):
        self.assertIs(sweep.fully_pushed(self.live), True)
        _age_admin_files(self.live, 25 * 3600)
        decision = sweep.decide_worktree(self.root, self.entry(self.live))
        self.assertEqual(decision["action"], "reap", decision)
        self.assertEqual(decision["reason"], "removable")

    def test_an_unreadable_remote_keeps_a_tree_that_looks_pushed(self):
        missing = os.path.join(ROOT, "remote-live-no-such-origin.git")
        require(run_vcs(self.root, "remote", "set-url", "origin", missing).returncode == 0,
                "pointing origin at a missing path failed")
        try:
            _age_admin_files(self.live, 25 * 3600)
            decision = sweep.decide_worktree(self.root, self.entry(self.live))
        finally:
            run_vcs(self.root, "remote", "set-url", "origin", self.bare)
        self.assertEqual(decision["action"], "keep", decision)
        self.assertEqual(decision["reason"], "unreadable-subject", decision["reason"])

    def test_ls_remote_runs_with_credential_prompts_off(self):
        """P3 (coordinator, r24): the `git ls-remote` that _live_remote_heads runs must carry
        GIT_TERMINAL_PROMPT=0 and GCM_INTERACTIVE=never, so an unattended run never waits on a
        credential or login window. The call is observed at subprocess.run, the runner guard._git
        uses. The real call still runs, so the answer is real."""
        real_run = subprocess.run
        seen = []

        def observe(argv, *args, **kwargs):
            if "ls-remote" in argv:
                seen.append(kwargs.get("env") or {})
            return real_run(argv, *args, **kwargs)

        with mock.patch.object(subprocess, "run", side_effect=observe):
            sweep.fully_pushed(self.live)
        self.assertGreaterEqual(len(seen), 1, "no ls-remote call was made")
        for env in seen:
            self.assertEqual(env.get("GIT_TERMINAL_PROMPT"), "0", env)
            self.assertEqual(env.get("GCM_INTERACTIVE"), "never", env)

    def test_a_failed_ls_remote_keeps_the_tree(self):
        """Pin for P3: when the ls-remote call fails, the tree is kept as unreadable-subject."""
        real_run = subprocess.run

        def failing(argv, *args, **kwargs):
            if "ls-remote" in argv:
                return subprocess.CompletedProcess(argv, 128, stdout="", stderr="fatal: no login")
            return real_run(argv, *args, **kwargs)

        _age_admin_files(self.live, 25 * 3600)
        with mock.patch.object(subprocess, "run", side_effect=failing):
            decision = sweep.decide_worktree(self.root, self.entry(self.live))
        self.assertEqual(decision["action"], "keep", decision)
        self.assertEqual(decision["reason"], "unreadable-subject", decision["reason"])


# --------------------------------------------------------------------------- owner rulings 2026-10-08


def _norm_path(path):
    return os.path.normcase(os.path.realpath(path))


def _age_admin_files(path, seconds):
    """Make a worktree's own git admin files `seconds` old, so the strict idle rule reads it quiet."""
    admin = run_vcs(path, "rev-parse", "--absolute-git-dir").stdout.strip()
    then = time.time() - seconds
    for name in ("index", "HEAD", os.path.join("logs", "HEAD")):
        target = os.path.join(admin, name)
        if os.path.exists(target):
            os.utime(target, (then, then))


def _read_run_log(path):
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


@contextlib.contextmanager
def _machine_quiet():
    """Stub the two machine-wide reapers the full sweep also runs (dead rooted servers and loose
    processes). A case here must never signal a process this suite did not start."""
    with mock.patch.object(sweep, "find_dead_rooted", return_value=[]), \
            mock.patch.object(sweep, "find_loose_processes", return_value=[]), \
            contextlib.redirect_stdout(io.StringIO()):
        yield


class RunLogTests(unittest.TestCase):
    """Owner ruling 2026-10-08: a --confirm run appends ONE JSON line per repository to the run
    log: `JANITOR_RUN_LOG`, or else `${CLAUDE_CONFIG_DIR:-~/.claude}/state/janitor-runs.jsonl`.
    Each line carries `root`, `worktrees_removed`, `branches_reaped` and `free_bytes`
    (shutil.disk_usage on the repository's drive). A preview appends nothing."""

    def setUp(self):
        self.base = tempfile.mkdtemp(prefix="runlog-", dir=ROOT)
        self.busy = os.path.join(self.base, "busy")
        make_repo(self.busy, {"f.txt": "x\n"})
        give_remote(self.busy)
        run_vcs(self.busy, "branch", "old-merged")  # at main's tip: merged, so reapable
        self.wt = os.path.join(self.base, "busy-wt")
        run_vcs(self.busy, "worktree", "add", "-q", "--detach", self.wt, "main")
        self.idle = os.path.join(self.base, "idle")
        make_repo(self.idle, {"g.txt": "y\n"})
        give_remote(self.idle)
        self.log = os.path.join(self.base, "janitor-runs.jsonl")
        self.restore = os.path.join(self.base, "restore.log")
        require("old-merged" in (sweep.list_local_branches(self.busy) or []),
                "branch old-merged was not created")
        require(os.path.isdir(self.wt), "the detached worktree was not created")

    def _main(self, argv):
        with mock.patch.dict(os.environ, {"JANITOR_RUN_LOG": self.log}), _machine_quiet(), \
                mock.patch.object(shutil, "disk_usage",
                                  return_value=types.SimpleNamespace(total=1, used=1, free=4242)), \
                contextlib.redirect_stdout(io.StringIO()):
            return sweep.main(argv + ["--restore-log", self.restore])

    def test_confirm_appends_one_line_per_repository_with_the_four_fields(self):
        _age_admin_files(self.wt, 7200)  # quiet for 2 hours: the strict idle rule allows the reap
        self._main([self.busy, self.idle, "--confirm"])
        self.assertTrue(os.path.isfile(self.log), "a --confirm run wrote no run log")
        records = _read_run_log(self.log)
        self.assertEqual(len(records), 2, records)
        by_root = {_norm_path(r.get("root", "")): r for r in records}
        busy = by_root.get(_norm_path(self.busy))
        idle = by_root.get(_norm_path(self.idle))
        self.assertIsNotNone(busy, "no run-log line names the busy repository: %r" % records)
        self.assertIsNotNone(idle, "no run-log line names the idle repository: %r" % records)
        self.assertEqual(busy["worktrees_removed"], 1, busy)
        self.assertEqual(busy["branches_reaped"], 1, busy)
        self.assertEqual(busy["free_bytes"], 4242, busy)
        self.assertEqual(idle["worktrees_removed"], 0, idle)
        self.assertEqual(idle["branches_reaped"], 0, idle)
        self.assertEqual(idle["free_bytes"], 4242, idle)
        self.assertFalse(os.path.exists(self.wt), "the subject worktree was not removed")

    def test_preview_appends_no_run_line_and_the_confirm_after_it_does(self):
        self._main([self.busy, self.idle])
        self.assertFalse(os.path.isfile(self.log) and os.path.getsize(self.log) > 0,
                         "a preview run appended to the run log")
        _age_admin_files(self.wt, 7200)
        self._main([self.busy, self.idle, "--confirm"])
        self.assertTrue(os.path.isfile(self.log), "the confirm after the preview wrote no run log")
        self.assertEqual(len(_read_run_log(self.log)), 2)

    def test_default_run_log_sits_under_the_config_dir(self):
        cfg = os.path.join(self.base, "cfg")
        _age_admin_files(self.wt, 7200)
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": cfg}):
            os.environ.pop("JANITOR_RUN_LOG", None)
            with _machine_quiet():
                sweep.main([self.busy, self.idle, "--confirm", "--restore-log", self.restore])
        default_log = os.path.join(cfg, "state", "janitor-runs.jsonl")
        self.assertTrue(os.path.isfile(default_log), "no run log at %s" % default_log)
        self.assertEqual(len(_read_run_log(default_log)), 2)

    def test_first_repository_line_survives_a_later_failure(self):
        """Finding (review): the run log was written after ALL roots, so a run cut short (the
        SessionEnd hook's 25 s kill) left no line. One line per repository, as each finishes."""
        _age_admin_files(self.wt, 7200)
        real = sweep.sweep_repo

        def fail_second(root, *args, **kwargs):
            if _norm_path(root) == _norm_path(self.idle):
                raise RuntimeError("injected failure in the second repository")
            return real(root, *args, **kwargs)

        with mock.patch.object(sweep, "sweep_repo", side_effect=fail_second):
            try:
                self._main([self.busy, self.idle, "--confirm"])
            except RuntimeError:
                pass  # the run stops here; the first repository's line must already be on disk
        self.assertTrue(os.path.isfile(self.log), "the first repository wrote no run line")
        roots = [_norm_path(r.get("root", "")) for r in _read_run_log(self.log)]
        self.assertIn(_norm_path(self.busy), roots, "no run-log line for the first repository")


@contextlib.contextmanager
def _process_table(rows):
    """Inject the machine's process table: ROWS maps pid to cwd. The real table is never read."""
    if sys.platform == "darwin":
        with _Stub("_all_cwds_macos", lambda: list(rows.items())):
            yield
    else:
        with _Stub("list_all_pids", lambda: list(rows)), _Stub("process_cwd", rows.get):
            yield


@contextlib.contextmanager
def _watch_git(calls, fail=None):
    """Append the argv of every `git` call to CALLS. A call that FAIL(argv, cwd) accepts answers
    exit 128. The rest run for real."""
    real = subprocess.run

    def run(args, *a, **k):
        if isinstance(args, (list, tuple)) and args and str(args[0]) == "git":
            argv = [str(x) for x in args]
            calls.append(argv)
            if fail and fail(argv, k.get("cwd")):
                return subprocess.CompletedProcess(args, 128, "", "fatal: injected read failure\n")
        return real(args, *a, **k)

    with mock.patch("subprocess.run", run):
        yield


def _aimed_at(path, argv, cwd):
    """True when the git call runs inside PATH (`-C PATH`, or cwd PATH)."""
    target = argv[argv.index("-C") + 1] if "-C" in argv and argv.index("-C") + 1 < len(argv) else cwd
    return bool(target) and _norm_path(target) == _norm_path(path)


class AgentWorktreeReapTests(unittest.TestCase):
    """Owner ruling 2026-10-14: the end-of-session sweep (`sweep.py --confirm`, no --attended, as
    session_end_sweep.py runs it) removes a finished agent's worktree, IN ADDITION to what the
    unattended rulings of 2026-10-01 and 2026-10-09 remove (merged and idle 1 hour, or pushed and
    idle 24 hours, on any path). Those stay: no case here forbids one of their removals. The
    agent rule removes a tree only when ALL hold: its path is `<repo>/.claude/worktrees/agent-*`
    (a branch or a detached HEAD); it is clean (no uncommitted, no untracked file); no process has
    a cwd inside it; its last change is 4 hours old or more; its HEAD commit is reachable from a
    remote-tracking ref. A repo whose package.json defines `reap:worktrees` gets that script run
    with `--remove` instead. A read that fails keeps the tree. A tree that should go below is
    pushed and not merged, which the older rulings keep before 24 hours, so its removal at 5 hours
    can only be the agent rule's, and its keep can only be that rule's refusal.

    Incident: q_max reached 798 registered worktrees. Its remover read 181 as "never pushed",
    because a lane pushes `HEAD:<lane>` from a local branch of another name.

    Seams. Clock: `time.time` runs HOURS ahead, so no file is touched and nothing sleeps.
    Process table: `sweep.list_all_pids` and `sweep.process_cwd` (darwin: `_all_cwds_macos`).
    npm: a stub `npm` first on PATH logs argv and cwd. It is a real executable, so the sweep
    may reach it by any call form. Failed git read: `subprocess.run` answers 128 for one tree.
    A kept tree must also see no `git worktree remove` call: git refuses a dirty tree on its own,
    and that refusal is not the sweep's guard. Every keep case also holds a control tree (`agent-ctl`) that must be removed in the same run,
    so a sweep that does nothing, or stops early, cannot pass a keep case."""

    def setUp(self):
        self.base = tempfile.mkdtemp(prefix="rp-", dir=ROOT)  # short: Windows path length
        self.repo = os.path.join(self.base, "r")
        make_repo(self.repo, {"f.txt": "base\n"})
        give_remote(self.repo)
        self.restore_log = os.path.join(self.base, "restore.log")
        self.run_log = os.path.join(self.base, "runs.jsonl")
        self.npm_log = os.path.join(self.base, "npm.jsonl")
        self.branch_of = {}  # tree path -> its local branch, None when detached
        self.shim = os.path.join(self.base, "shim")
        os.makedirs(self.shim)
        stub = os.path.join(self.shim, "npm_stub.py")
        write(stub, "import json, os, sys\n"
                    "with open(os.environ['NPM_STUB_LOG'], 'a', encoding='utf-8') as h:\n"
                    "    h.write(json.dumps({'argv': sys.argv[1:], 'cwd': os.getcwd()}) + '\\n')\n")
        write(os.path.join(self.shim, "npm"), '#!/bin/sh\nexec "%s" "%s" "$@"\n' % (sys.executable, stub))
        os.chmod(os.path.join(self.shim, "npm"), 0o755)
        write(os.path.join(self.shim, "npm.cmd"), '@"%s" "%s" %%*\r\n' % (sys.executable, stub))

    # ---- fixtures

    def commit(self, path, name):
        write(os.path.join(path, name), "work\n")
        run_vcs(path, "add", "-A")
        done = run_vcs(path, *IDENT, "commit", "-q", "-m", name)
        require(done.returncode == 0, "commit in %r failed: %s" % (path, done.stderr.strip()))

    def agent(self, name, state="pushed", path=None, detach=False):
        """A linked worktree, by default at `<repo>/.claude/worktrees/agent-<name>`, with one
        commit of its own that is not on main, on local branch `wt-<name>` or (DETACH) on no
        branch. STATE: "pushed" is that commit pushed with `push origin HEAD:lane-<name>`, so a
        local branch has no upstream (the incident shape); "local" is never pushed; "ahead" is
        pushed, then one more local commit."""
        path = path or os.path.join(self.repo, ".claude", "worktrees", "agent-" + name)
        branch = None if detach else "wt-" + name
        made = run_vcs(self.repo, "worktree", "add", "-q", path, *(["--detach"] if detach else ["-b", branch]))
        require(made.returncode == 0, "worktree add %r failed: %s" % (path, made.stderr.strip()))
        self.commit(path, name + ".txt")
        if state in ("pushed", "ahead"):
            lane = "lane-" + name
            pushed = run_vcs(path, "push", "-q", "origin", "HEAD:refs/heads/" + lane)
            require(pushed.returncode == 0, "push of %s failed: %s" % (lane, pushed.stderr.strip()))
            require(run_vcs(self.repo, "rev-parse", "-q", "--verify",
                            "refs/remotes/origin/" + lane).returncode == 0,
                    "no remote-tracking ref for %s after the push" % lane)
            require(lane in run_vcs(self.repo, "ls-remote", "--heads", "origin").stdout,
                    "the remote does not list %s" % lane)
            if branch:
                require(run_vcs(path, "rev-parse", "--abbrev-ref", branch + "@{upstream}").returncode != 0,
                        "%s has an upstream; the fixture must not" % branch)
        if state == "ahead":
            self.commit(path, name + "-2.txt")
        require(self.listed(path), "%r is not a registered worktree" % path)
        self.branch_of[path] = branch
        return path

    # ---- the run

    def run_sweep(self, hours, rows=None, fail=None):
        """One `sweep.py --confirm` run, HOURS in the future, over the injected process table.
        Returns the report text (stdout and stderr)."""
        out = io.StringIO()
        env = {"PATH": self.shim + os.pathsep + os.environ.get("PATH", ""),
               "NPM_STUB_LOG": self.npm_log, "JANITOR_RUN_LOG": self.run_log}
        real, report = time.time, sweep.print_sweep_report

        def tee(*args, **kwargs):  # the report's `out=sys.stdout` default is bound at import
            kwargs["out"] = out
            return report(*args[:2], **kwargs)

        self.git_calls = []
        with mock.patch.dict(os.environ, env), _machine_quiet(), \
                mock.patch("time.time", lambda: real() + hours * 3600), \
                mock.patch.object(sweep, "print_sweep_report", tee), \
                _process_table(rows or {}), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(out), _watch_git(self.git_calls, fail):
            sweep.main([self.repo, "--confirm", "--restore-log", self.restore_log])
        return out.getvalue()

    # ---- reads

    def listed(self, path):
        return any(_norm_path(e["path"]) == _norm_path(path)
                   for e in sweep.parse_worktree_list(self.repo) or [])

    def npm_calls(self):
        if not os.path.isfile(self.npm_log):
            return []
        return _read_run_log(self.npm_log)

    def lines_about(self, out, name):
        return "\n".join(line for line in out.splitlines() if name in line) or "(no report line)"

    def removal_attempts(self, path):
        """The `git worktree remove` calls the last run made on PATH. A dirty tree survives such a
        call, because git refuses it; that refusal is git's, so a kept tree must never see one."""
        return [call for call in self.git_calls if "worktree" in call and "remove" in call
                and any(_norm_path(arg) == _norm_path(path) for arg in call[call.index("remove") + 1:])]

    # ---- verdicts. The report line is the message, so a red run shows the sweep's own reason.

    def assertKept(self, path, out):
        name, branch = os.path.basename(path), self.branch_of[path]
        why = self.lines_about(out, name)
        self.assertEqual(self.removal_attempts(path), [], "%s: the sweep tried to remove it. "
                         "Report: %s" % (name, why))
        self.assertTrue(os.path.isdir(path), "%s was removed. Report: %s" % (name, why))
        self.assertTrue(self.listed(path), "%s was unregistered. Report: %s" % (name, why))
        if branch:
            self.assertIn(branch, sweep.list_local_branches(self.repo) or [], "%s lost its branch" % name)

    def assertRemoved(self, path, out):
        name, branch = os.path.basename(path), self.branch_of[path]
        why = self.lines_about(out, name)
        self.assertFalse(os.path.isdir(path), "%s was kept. Report: %s" % (name, why))
        self.assertFalse(self.listed(path), "%s is still registered. Report: %s" % (name, why))
        if branch:
            self.assertNotIn(branch, sweep.list_local_branches(self.repo) or [],
                             "%s's local branch is still there. Report: %s" % (name, why))

    # ---- (a) the incident shape

    def test_a_removes_a_clean_pushed_tree_idle_5h_with_its_local_branch(self):
        tree = self.agent("a")
        sha = run_vcs(tree, "rev-parse", "HEAD").stdout.strip()
        out = self.run_sweep(5)
        self.assertRemoved(tree, out)
        self.assertIn("lane-a", run_vcs(self.repo, "ls-remote", "--heads", "origin").stdout,
                      "the sweep touched the remote")
        self.assertEqual(run_vcs(self.repo, "cat-file", "-e", sha + "^{commit}").returncode, 0,
                         "the lane's commit is gone from the repository")
        self.assertEqual(self.npm_calls(), [], "a repo with no `reap:worktrees` script ran npm")

    # ---- (b) the 4 hour floor

    def test_b_keeps_a_pushed_unmerged_tree_idle_under_4h(self):
        """Pushed, not merged: the 1 hour and 24 hour rulings keep it too, so only the agent
        rule's 4 hour floor can be what removes it at 5 hours, and what keeps it before."""
        tree = self.agent("b")
        for hours in (3, 3.9):
            out = self.run_sweep(hours)
            self.assertKept(tree, out)
        out = self.run_sweep(5)  # the same tree, 1.1 hours later: removable, so the keeps were the floor
        self.assertRemoved(tree, out)

    # ---- (c) HEAD on no remote-tracking ref

    def test_c_keeps_a_tree_whose_head_is_on_no_remote_ref(self):
        local, ahead = self.agent("c1", "local"), self.agent("c2", "ahead")
        ctl = self.agent("ctl")
        out = self.run_sweep(5)
        self.assertKept(local, out)
        self.assertKept(ahead, out)  # its branch was pushed once; HEAD is one commit past that push
        self.assertRemoved(ctl, out)

    # ---- (d) uncommitted or untracked

    def test_d_keeps_a_dirty_tree_and_a_tree_with_an_untracked_file(self):
        dirty, untracked = self.agent("d1"), self.agent("d2")
        ctl = self.agent("ctl")
        write(os.path.join(dirty, "f.txt"), "edited, not committed\n")
        write(os.path.join(untracked, "scratch.txt"), "new, not added\n")
        out = self.run_sweep(5)
        self.assertKept(dirty, out)
        self.assertKept(untracked, out)
        self.assertRemoved(ctl, out)

    # ---- (e) a process inside

    def test_e_keeps_a_tree_with_a_process_cwd_inside_it(self):
        busy, ctl = self.agent("e"), self.agent("ctl")
        inside = os.path.join(busy, "sub")
        os.makedirs(inside)  # an empty folder: git sees no change
        out = self.run_sweep(5, rows={424242: inside})
        self.assertKept(busy, out)
        self.assertRemoved(ctl, out)

    # ---- (f) outside the agent folder, and the main checkout

    def test_f_keeps_a_tree_outside_agent_folders_and_the_main_checkout(self):
        """The agent rule adds removals; it never reaches a tree off its path. Both trees are
        clean, pushed, not merged, idle 5 hours: the older rulings (merged and idle 1 hour, or
        pushed and idle 24 hours, on any path) keep them, so only the agent rule could remove
        them, and its path keeps them."""
        outside = self.agent("f1", path=os.path.join(self.base, "agent-f1"))
        renamed = self.agent("f2", path=os.path.join(self.repo, ".claude", "worktrees", "lane-f2"))
        ctl = self.agent("ctl")
        out = self.run_sweep(5)
        self.assertTrue(os.path.isdir(outside), "a tree outside .claude/worktrees was removed. "
                        + self.lines_about(out, "agent-f1"))
        self.assertTrue(os.path.isdir(renamed), "a tree not named agent-* was removed. "
                        + self.lines_about(out, "lane-f2"))
        self.assertTrue(self.listed(outside) and self.listed(renamed))
        self.assertTrue(os.path.isdir(os.path.join(self.repo, ".git")), "the main checkout was removed")
        self.assertTrue(self.listed(self.repo))
        self.assertRemoved(ctl, out)

    # ---- (g) the repo's own remover

    def test_g_runs_the_repos_remover_with_remove_and_removes_nothing_itself(self):
        write(os.path.join(self.repo, "package.json"),
              json.dumps({"name": "x", "scripts": {"reap:worktrees": "node reap.mjs"}}))
        run_vcs(self.repo, "add", "-A")
        self.assertEqual(run_vcs(self.repo, *IDENT, "commit", "-q", "-m", "reaper").returncode, 0)
        require(run_vcs(self.repo, "push", "-q", "origin", "main").returncode == 0, "push of main failed")
        tree = self.agent("g")  # the built-in rule would remove it at 5 hours
        out = self.run_sweep(5)
        calls = self.npm_calls()
        self.assertEqual(len(calls), 1, "npm calls: %r\n%s" % (calls, out))
        argv = calls[0]["argv"]
        self.assertIn("reap:worktrees", argv)
        self.assertIn("--remove", argv)
        self.assertLess(argv.index("reap:worktrees"), argv.index("--remove"), argv)
        self.assertEqual(_norm_path(calls[0]["cwd"]), _norm_path(self.repo))
        self.assertKept(tree, out)

    # ---- (i) a detached tree: the red-proof checkout a test-author makes under .claude/worktrees

    def test_i_removes_a_detached_tree_on_a_pushed_commit_idle_5h(self):
        """No local branch holds the commit. It lives on the pushed lane, so the tree can go."""
        tree = self.agent("i1", detach=True)
        sha = run_vcs(tree, "rev-parse", "HEAD").stdout.strip()
        require(run_vcs(tree, "symbolic-ref", "-q", "HEAD").returncode != 0, "the fixture is on a branch")
        out = self.run_sweep(5)
        self.assertRemoved(tree, out)
        self.assertEqual(run_vcs(self.repo, "cat-file", "-e", sha + "^{commit}").returncode, 0,
                         "the commit is gone from the repository")
        self.assertIn(sha, run_vcs(self.repo, "ls-remote", "--heads", "origin").stdout)

    def test_i_keeps_a_detached_tree_on_an_unpushed_commit(self):
        """A detached HEAD has no branch to tombstone: removing this tree loses the commit."""
        tree, ctl = self.agent("i2", "local", detach=True), self.agent("ctl")
        out = self.run_sweep(5)
        self.assertKept(tree, out)
        self.assertRemoved(ctl, out)

    # ---- (h) a failed read

    def assertLogged(self, out, name):
        try:
            with open(self.run_log, encoding="utf-8") as handle:
                out += "\n" + handle.read()
        except OSError:
            pass
        logged = [line for line in out.splitlines() if name in line
                  and any(word in line.lower() for word in ("unreadable", "unknown", "fail"))]
        self.assertTrue(logged, "the failed read is not logged (report or run log):\n" + out)

    def kept_and_logged(self, tree, ctl, out, name):
        self.assertKept(tree, out)
        self.assertRemoved(ctl, out)
        self.assertLogged(out, name)

    def test_h_keeps_a_tree_when_any_git_read_in_it_fails_and_logs_it(self):
        tree, ctl = self.agent("h1"), self.agent("ctl")
        out = self.run_sweep(5, fail=lambda argv, cwd: _aimed_at(tree, argv, cwd))
        self.kept_and_logged(tree, ctl, out, "agent-h1")

    def test_h_keeps_a_tree_when_the_clean_read_fails_and_logs_it(self):
        """Only `git status` fails here. The case above fails every read in the tree, so a
        second read that also fails would hide a clean read that fails open."""
        tree, ctl = self.agent("h3"), self.agent("ctl")
        fired = []

        def match(argv, cwd):
            hit = "status" in argv and _aimed_at(tree, argv, cwd)
            if hit:
                fired.append(argv)
            return hit

        out = self.run_sweep(5, fail=match)
        self.assertTrue(fired, "no `git status` ran in the tree. Report: "
                        + self.lines_about(out, "agent-h3"))
        self.kept_and_logged(tree, ctl, out, "agent-h3")

    def test_h_keeps_a_tree_when_the_live_remote_read_fails_and_logs_it(self):
        """The agent rule needs the live `git ls-remote` read too, so a stale remote-tracking ref
        alone never removes a tree. ls-remote is cached for the whole run, so a failure keeps
        every tree: the same tree goes in a second run that the remote answers."""
        tree = self.agent("h4")
        out = self.run_sweep(5, fail=lambda argv, cwd: "ls-remote" in argv)
        self.assertTrue([call for call in self.git_calls if "ls-remote" in call],
                        "no `git ls-remote` ran. Report: " + self.lines_about(out, "agent-h4"))
        self.assertKept(tree, out)
        self.assertLogged(out, "agent-h4")
        out = self.run_sweep(5)
        self.assertRemoved(tree, out)

    def test_h_keeps_a_tree_when_the_remote_reach_read_fails_and_logs_it(self):
        """The read that matters here is `git branch -r --contains` (or `for-each-ref
        --contains`): is HEAD on a remote-tracking ref? The tree is pushed and not merged, so
        the older rulings keep it. The path, the idle time and the clean tree allow the agent rule
        to remove it, and only this read can keep it."""
        tree, ctl = self.agent("h2"), self.agent("ctl")
        sha = run_vcs(tree, "rev-parse", "HEAD").stdout.strip()
        fired = []

        def match(argv, cwd):
            hit = "--contains" in argv and (_aimed_at(tree, argv, cwd) or sha in argv
                                            or "wt-h2" in argv or "refs/heads/wt-h2" in argv)
            if hit:
                fired.append(argv)
            return hit

        out = self.run_sweep(5, fail=match)
        self.assertTrue(fired, "no `--contains` read was made for the tree. Report: "
                        + self.lines_about(out, "agent-h2"))
        self.kept_and_logged(tree, ctl, out, "agent-h2")

    # ---- (j) the agent rule's own two reads: idle time, and the remote-tracking ref

    def test_j_keeps_a_tree_whose_idle_time_cannot_be_read(self):
        """Only the idle read fails. The tree is clean, pushed, and not merged, so the older
        rulings keep it before 24 hours and the agent rule alone decides. An idle time the rule
        cannot read is no idle time: the same tree goes in a second run that can read it."""
        tree = self.agent("j1")
        fired = []

        def match(argv, cwd):
            hit = "--absolute-git-dir" in argv and _aimed_at(tree, argv, cwd)
            if hit:
                fired.append(argv)
            return hit

        out = self.run_sweep(5, fail=match)
        self.assertTrue(fired, "no idle read (`rev-parse --absolute-git-dir`) ran in the tree. "
                        "Report: " + self.lines_about(out, "agent-j1"))
        self.assertKept(tree, out)
        self.assertLogged(out, "agent-j1")
        out = self.run_sweep(5)
        self.assertRemoved(tree, out)

    def test_j_keeps_a_tree_the_remote_lists_when_no_tracking_ref_holds_its_head(self):
        """The live ls-remote lists the head, so a rule that read only that would remove the
        tree. `git branch -r --contains HEAD` is empty, because the tracking ref is gone. The
        tree stays until a fetch brings the ref back."""
        tree = self.agent("j2")
        sha = run_vcs(tree, "rev-parse", "HEAD").stdout.strip()
        require(run_vcs(self.repo, "update-ref", "-d", "refs/remotes/origin/lane-j2").returncode == 0,
                "could not delete the tracking ref")
        require(sha in run_vcs(self.repo, "ls-remote", "--heads", "origin").stdout,
                "the remote does not list the head")
        require(not run_vcs(tree, "branch", "-r", "--contains", "HEAD").stdout.strip(),
                "a remote-tracking ref still holds HEAD")
        out = self.run_sweep(5)
        self.assertKept(tree, out)
        require(run_vcs(self.repo, "fetch", "-q", "origin").returncode == 0, "fetch failed")
        out = self.run_sweep(5)
        self.assertRemoved(tree, out)


class MergedCountsAsSafeTests(unittest.TestCase):
    """Owner ruling 2026-10-08: a HEAD merged into the default branch, by ancestry or by patch,
    is not kept for "unpushed". The other checks still apply, and a truly unpushed commit is
    still kept."""

    @classmethod
    def setUpClass(cls):
        cls.root = os.path.join(ROOT, "merged-safe-repo")
        make_repo(cls.root, {"f.txt": "base\n"})
        give_remote(cls.root)
        # lane-squash: one commit, never pushed. Main then gets the same patch as a different
        # commit (what a squash merge does), and main is pushed.
        cls.squash = os.path.join(ROOT, "merged-safe-squash")
        run_vcs(cls.root, "worktree", "add", "-q", cls.squash, "-b", "lane-squash")
        write(os.path.join(cls.squash, "s.txt"), "squashed work\n")
        run_vcs(cls.squash, "add", "s.txt")
        require(run_vcs(cls.squash, *IDENT, "commit", "-q", "-m", "lane work").returncode == 0,
                "committing lane-squash failed")
        write(os.path.join(cls.root, "s.txt"), "squashed work\n")
        run_vcs(cls.root, "add", "s.txt")
        require(run_vcs(cls.root, *IDENT, "commit", "-q", "-m", "squash of lane-squash").returncode == 0,
                "squash commit on main failed")
        require(run_vcs(cls.root, "push", "-q", "origin", "main").returncode == 0,
                "pushing main failed")
        # lane-unique: one commit on no default branch, never pushed.
        cls.unique = os.path.join(ROOT, "merged-safe-unique")
        run_vcs(cls.root, "worktree", "add", "-q", cls.unique, "-b", "lane-unique")
        write(os.path.join(cls.unique, "u.txt"), "only on this lane\n")
        run_vcs(cls.unique, "add", "u.txt")
        require(run_vcs(cls.unique, *IDENT, "commit", "-q", "-m", "unique work").returncode == 0,
                "committing lane-unique failed")
        cls.entries = {_norm_path(e["path"]): e for e in sweep.parse_worktree_list(cls.root) or []}
        require(_norm_path(cls.squash) in cls.entries and _norm_path(cls.unique) in cls.entries,
                "the worktree list does not hold both lanes")

    def decide(self, path):
        return sweep.decide_worktree(self.root, self.entries[_norm_path(path)], attended=True)

    def test_a_squash_merged_lane_never_pushed_is_removable(self):
        decision = self.decide(self.squash)
        self.assertEqual(decision["action"], "reap", decision["reason"])
        self.assertEqual(decision["reason"], "removable")

    def test_a_truly_unpushed_unique_commit_is_still_kept(self):
        decision = self.decide(self.unique)
        self.assertEqual(decision["action"], "keep", decision["reason"])
        self.assertTrue(decision["reason"].startswith("unpushed"), decision["reason"])


class StrayFolderTests(unittest.TestCase):
    """Owner ruling 2026-10-08: an entry under <root>/.claude/worktrees/ that git does not
    register as a worktree is a STRAY. The sweep lists it (result["strays"], and the printed
    report) and never deletes it, in preview or confirm."""

    def setUp(self):
        self.base = tempfile.mkdtemp(prefix="strays-", dir=ROOT)
        self.root = os.path.join(self.base, "repo")
        make_repo(self.root, {"f.txt": "x\n"})
        wts = os.path.join(self.root, ".claude", "worktrees")
        self.registered = os.path.join(wts, "lane-reg")  # a real worktree: NOT a stray
        run_vcs(self.root, "worktree", "add", "-q", "--detach", self.registered, "main")
        self.folder = os.path.join(wts, "stray-folder")  # no .git: not registered
        write(os.path.join(self.folder, "notes.txt"), "left behind\n")
        self.file = os.path.join(wts, "x.bak")
        write(self.file, "backup\n")
        require(os.path.isdir(self.registered) and os.path.isdir(self.folder)
                and os.path.isfile(self.file), "the stray fixtures were not built")
        self.log = os.path.join(self.base, "strays.log")

    @staticmethod
    def _stray_names(result):
        return sorted(os.path.basename(p) for p in (result.get("strays") or []))

    def test_preview_lists_both_strays_in_the_result_and_the_report(self):
        result = sweep.sweep_repo(self.root, False, self.log)
        self.assertEqual(self._stray_names(result), ["stray-folder", "x.bak"], result.get("strays"))
        out = io.StringIO()
        sweep.print_sweep_report([result], False, out=out)
        self.assertIn("stray-folder", out.getvalue())
        self.assertIn("x.bak", out.getvalue())

    def test_confirm_lists_both_strays_and_deletes_neither(self):
        result = sweep.sweep_repo(self.root, True, self.log)
        self.assertEqual(self._stray_names(result), ["stray-folder", "x.bak"], result.get("strays"))
        self.assertTrue(os.path.isfile(os.path.join(self.folder, "notes.txt")),
                        "a confirm run deleted a file inside a stray folder")
        self.assertTrue(os.path.isfile(self.file), "a confirm run deleted x.bak")

    def test_unreadable_worktrees_base_does_not_abort_the_run(self):
        """Finding (review): find_strays called a bare os.listdir, so a PermissionError on
        <root>/.claude/worktrees escaped sweep_repo and aborted the run. The run must finish,
        report the strays as UNKNOWN (result["strays"] is None, not []), and still judge every
        registered worktree. Zero would read as a clean folder; None does not."""
        base = os.path.join(self.root, ".claude", "worktrees")
        real_listdir = os.listdir

        def denied(path="."):
            if _norm_path(path) == _norm_path(base):
                raise PermissionError(13, "Access is denied", path)
            return real_listdir(path)

        with mock.patch.object(sweep.os, "listdir", side_effect=denied):
            result = sweep.sweep_repo(self.root, False, self.log)
        self.assertIsNone(result["refused"])
        self.assertIsNone(result["strays"], "an unreadable folder gave a count, not unknown: %r"
                          % (result["strays"],))
        judged = [_norm_path(d["path"]) for d in result["worktrees"]]
        self.assertIn(_norm_path(self.registered), judged, "the registered worktree was not judged")

    def test_unreadable_worktrees_base_report_says_unknown_not_zero(self):
        """Batch review J2: the printed report must not say "strays ... (kept): 0" for a folder
        it could not read. It must say the count is unknown or the folder unreadable."""
        base = os.path.join(self.root, ".claude", "worktrees")
        real_listdir = os.listdir

        def denied(path="."):
            if _norm_path(path) == _norm_path(base):
                raise PermissionError(13, "Access is denied", path)
            return real_listdir(path)

        with mock.patch.object(sweep.os, "listdir", side_effect=denied):
            result = sweep.sweep_repo(self.root, False, self.log)
        out = io.StringIO()
        sweep.print_sweep_report([result], False, out=out)
        text = out.getvalue()
        lines = [ln for ln in text.splitlines() if "strays under .claude/worktrees" in ln]
        self.assertEqual(len(lines), 1, "no single strays line in the report: %r" % text)
        self.assertNotIn("(kept): 0", lines[0], "an unreadable folder reported zero strays: %r"
                         % lines[0])
        self.assertRegex(lines[0], r"(?i)unknown|unreadable", "the strays line does not say the "
                         "scan could not run: %r" % lines[0])


def _lane_entry(root, path):
    target = _norm_path(path)
    for entry in sweep.parse_worktree_list(root) or []:
        if _norm_path(entry["path"]) == target:
            return entry
    raise AssertionError("no worktree-list entry for %r" % path)


class DanglingDefaultBaseTests(unittest.TestCase):
    """Finding (review): guard.resolve_default_base returned origin/HEAD without checking that it
    resolves. A dangling origin/HEAD makes every base read unreadable, so no squash-merged lane is
    ever exempted. The base must fall back to a ref that resolves (local main, then master). An
    origin/HEAD that resolves stays the first base (owner's order)."""

    def _squash_lane(self, origin_head_target):
        base = tempfile.mkdtemp(prefix="dangling-base-", dir=ROOT)
        root = os.path.join(base, "repo")
        make_repo(root, {"f.txt": "x\n"})
        give_remote(root)  # origin/main exists and matches main's first commit
        lane = os.path.join(base, "lane")
        run_vcs(root, "worktree", "add", "-q", lane, "-b", "lane-squash")
        write(os.path.join(lane, "lane.txt"), "work\n")
        run_vcs(lane, "add", "-A")
        run_vcs(lane, *IDENT, "commit", "-q", "-m", "lane work")
        # The squash: the same patch lands on main as a new commit. The lane's own commit is on no
        # remote branch and is not an ancestor of main; only the patch matches.
        write(os.path.join(root, "lane.txt"), "work\n")
        run_vcs(root, "add", "-A")
        run_vcs(root, *IDENT, "commit", "-q", "-m", "squash of lane-squash")
        set_head = run_vcs(root, "symbolic-ref", "refs/remotes/origin/HEAD", origin_head_target)
        require(set_head.returncode == 0, "setting origin/HEAD failed: %s" % set_head.stderr.strip())
        return root, lane

    def test_dangling_origin_head_falls_back_to_a_ref_that_resolves(self):
        root, _ = self._squash_lane("refs/remotes/origin/gone")  # a remote branch that is missing
        self.assertEqual(guard.resolve_default_base(root), "main")

    def test_squash_merged_unpushed_lane_is_removable_when_origin_head_dangles(self):
        root, lane = self._squash_lane("refs/remotes/origin/gone")
        decision = sweep.decide_worktree(root, _lane_entry(root, lane), attended=True)
        self.assertEqual(decision["action"], "reap", decision)
        self.assertEqual(decision["reason"], "removable")

    def test_resolving_origin_head_keeps_a_lane_whose_squash_is_only_on_local_main(self):
        # Local main is ahead of origin/main and holds the squash. origin/HEAD resolves, so it
        # stays the base (owner's order), origin/main lacks the patch, and the lane is kept.
        root, lane = self._squash_lane("refs/remotes/origin/main")
        decision = sweep.decide_worktree(root, _lane_entry(root, lane), attended=True)
        self.assertEqual(decision["action"], "keep", decision)
        self.assertTrue(decision["reason"].startswith("unpushed:"), decision)

    def test_unreadable_origin_head_verify_returns_none_not_local_main(self):
        """Batch review J3: guard.resolve_default_base treated a verify read that could not RUN
        (guard._git returns None) as "does not exist", and fell through to local main. Only a git
        that answers "does not exist" (returncode != 0) may fall through. An unreadable verify
        returns None, so the sweep keeps the lane."""
        root, _ = self._squash_lane("refs/remotes/origin/main")
        require(guard.resolve_default_base(root) == "origin/main",
                "the unpatched base is not origin/main, so the case proves nothing")
        real_git = guard._git
        verify_calls = []

        def unreadable_verify(where, *args):
            if args and args[-1].endswith("^{commit}"):  # the origin/HEAD verify read
                verify_calls.append(args)
                return None  # guard._git could not run git
            return real_git(where, *args)

        with mock.patch.object(sys.modules["guard_core"], "_git", side_effect=unreadable_verify):
            base = guard.resolve_default_base(root)
        self.assertGreaterEqual(len(verify_calls), 1, "the verify read never ran: no proof")
        self.assertIsNone(base, "an unreadable origin/HEAD verify fell through to %r" % base)

    def test_origin_head_verify_returncode_128_falls_back_to_local_main(self):
        """Round 3 R7 (pin): git answers the origin/HEAD verify with returncode 128, a dangling
        origin/HEAD. Only a live origin/HEAD keeps origin's ref, so the base falls to local main.
        Green on the pre-round-3 code: a pin, not a red case."""
        root, _ = self._squash_lane("refs/remotes/origin/main")
        real_git = guard._git
        verify_calls = []

        def fatal_verify(where, *args):
            if args and args[-1].endswith("^{commit}"):  # the origin/HEAD verify read
                verify_calls.append(args)
                return subprocess.CompletedProcess(["git", *args], 128, "", "fatal: bad object")
            return real_git(where, *args)

        with mock.patch.object(sys.modules["guard_core"], "_git", side_effect=fatal_verify):
            base = guard.resolve_default_base(root)
        self.assertGreaterEqual(len(verify_calls), 1, "the verify read never ran: no proof")
        self.assertEqual(base, "main")

    def test_live_origin_head_resolves_to_origin_ref(self):
        """Round 3 R7 (pin): a live origin/HEAD is the base, as origin/main. Green on the
        pre-round-3 code: a pin, not a red case."""
        root, _ = self._squash_lane("refs/remotes/origin/main")
        self.assertEqual(guard.resolve_default_base(root), "origin/main")


class UnreadableHuskBaseRunTests(unittest.TestCase):
    """Batch review J1: find_husks called a bare os.listdir on <root>/.claude/worktrees. With
    huskNames set (so find_husks reaches the listdir) and that folder unreadable, the PermissionError
    escaped sweep_repo. The run aborted before the repository's run-log line was written. The run
    must finish, and the repository must still get its run-log line."""

    def setUp(self):
        self.base = tempfile.mkdtemp(prefix="husk-unreadable-", dir=ROOT)
        self.root = os.path.join(self.base, "repo")
        make_repo(self.root, {"f.txt": "x\n"})
        give_remote(self.root)
        write(os.path.join(self.root, ".claude", "janitor.json"),
              json.dumps({"huskNames": [".DS_Store"]}))
        self.wts = os.path.join(self.root, ".claude", "worktrees")
        os.makedirs(self.wts)
        self.log = os.path.join(self.base, "janitor-runs.jsonl")
        self.restore = os.path.join(self.base, "restore.log")
        require(sweep.read_optout(self.root).get("huskNames") == [".DS_Store"],
                "huskNames was not read from janitor.json")

    def test_unreadable_worktrees_folder_still_gets_the_repository_run_line(self):
        real_listdir = os.listdir
        denials = []

        def denied(path="."):
            if _norm_path(path) == _norm_path(self.wts):
                denials.append(path)
                raise PermissionError(13, "Access is denied", path)
            return real_listdir(path)

        error = None
        with mock.patch.object(sweep.os, "listdir", side_effect=denied), \
                mock.patch.dict(os.environ, {"JANITOR_RUN_LOG": self.log}), _machine_quiet(), \
                mock.patch.object(shutil, "disk_usage",
                                  return_value=types.SimpleNamespace(total=1, used=1, free=4242)), \
                contextlib.redirect_stdout(io.StringIO()):
            try:
                sweep.main([self.root, "--confirm", "--restore-log", self.restore])
            except PermissionError as exc:
                error = exc
        self.assertIsNone(error, "a PermissionError from the husk scan escaped the run: %r" % error)
        self.assertGreaterEqual(len(denials), 1, "the unreadable folder was never read: no proof")
        self.assertTrue(os.path.isfile(self.log), "no run log was written")
        roots = [_norm_path(r.get("root", "")) for r in _read_run_log(self.log)]
        self.assertIn(_norm_path(self.root), roots, "no run-log line for the repository: %r" % roots)

    def _denied_worktrees_listdir(self):
        real_listdir = os.listdir
        denials = []

        def denied(path="."):
            if _norm_path(path) == _norm_path(self.wts):
                denials.append(path)
                raise PermissionError(13, "Access is denied", path)
            return real_listdir(path)
        return denied, denials

    def test_unreadable_worktrees_folder_husk_line_says_unknown_not_zero(self):
        """Round 3 R5: find_husks returns [] for a folder it cannot read, so the report printed
        "leftover folders: 0, kept: 0". The husk scan must read as unknown on that line."""
        denied, denials = self._denied_worktrees_listdir()
        out = io.StringIO()
        with mock.patch.object(sweep.os, "listdir", side_effect=denied), _machine_quiet():
            result = sweep.sweep_repo(self.root, False, self.restore)
            sweep.print_sweep_report([result], False, out=out)
        self.assertGreaterEqual(len(denials), 1, "the unreadable folder was never read: no proof")
        text = out.getvalue()
        lines = [ln for ln in text.splitlines() if "leftover folders" in ln]
        self.assertEqual(len(lines), 1, "no single leftover-folders line: %r" % text)
        self.assertNotIn("leftover folders: 0", lines[0],
                         "an unreadable folder reported zero leftover folders: %r" % lines[0])
        self.assertRegex(lines[0], r"(?i)unknown|unreadable", "the husk line does not say the scan "
                         "could not run: %r" % lines[0])

    def test_unreadable_worktrees_folder_tier1_report_is_not_nothing_to_examine(self):
        """Round 3 R6: with the stray scan unknown, the report printed "nothing to examine" for a
        repository it had not finished examining. Tier1 runs only the husk and stray scans, so
        every other section is empty here."""
        denied, denials = self._denied_worktrees_listdir()
        out = io.StringIO()
        with mock.patch.object(sweep.os, "listdir", side_effect=denied), _machine_quiet():
            result = sweep.sweep_repo(self.root, False, self.restore, mode="tier1")
            sweep.print_sweep_report([result], True, out=out)
        self.assertGreaterEqual(len(denials), 1, "the unreadable folder was never read: no proof")
        self.assertIsNone(result["refused"], "the repository was refused: no proof of the scan")
        text = out.getvalue()
        self.assertNotIn("nothing to examine", text, "an unknown stray scan printed nothing to "
                         "examine: %r" % text)
        self.assertIn("stray     UNKNOWN", text, "the unknown stray scan is not shown: %r" % text)


# --------------------------------------------------------------------------- the simulator tier
#
# Owner ruling 2026-10-10. The contract these cases pin (janitor/sweep.py must match it):
#   sweep.sim_tier(confirm, record_path=None) returns one decision per UDID in the boot record:
#     {"udid", "name", "action": "shutdown" | "keep", "reason"}.
#   A keep reason string carries one code from SIM_KEEP_CODES. A shutdown runs ONE
#     `xcrun simctl shutdown <UDID>`. A preview (confirm False) runs none. No call ever names `all`.
#   Reads: `xcrun simctl list devices --json`, one `ps -axo pid=,ppid=,uid=,command=` table
#     (the table _read_ps_table reads), and one `ps -o pid=,lstart= -p PIDS` call for the start
#     time of each launchd_sim the table names. A `ps` call whose arguments name `lstart` answers
#     "PID START" lines when its -o list names pid=, else "START" lines. No xcrun on the PATH, or a
#     win32 platform: no tier, no decision, nothing printed.
#   record_path holds JSON lines {"udid", "name", "deviceTypeIdentifier", "runtime", "at",
#     "launchd_pid", "launchd_start"}, where "at" is ISO-8601 UTC, and launchd_pid and
#     launchd_start are the launchd_sim of that boot, as ps prints them. The NEWEST line for a UDID
#     decides its boot time. A device is idle only when its live launchd_sim has that pid AND that
#     start time; otherwise it was booted again by hand, and the tier keeps it with the code
#     "boot-record-mismatch".

SIM_RUNTIME = "com.apple.CoreSimulator.SimRuntime.iOS-26-0"
SIM_TYPE = "com.apple.CoreSimulator.SimDeviceType.iPhone-17-Pro"
SIM_U1 = "1A2B3C4D-0000-4000-8000-000000000001"
SIM_U2 = "1A2B3C4D-0000-4000-8000-000000000002"
SIM_U9 = "1A2B3C4D-0000-4000-8000-000000000009"
SIM_LAUNCHD = ("/Library/Developer/PrivateFrameworks/CoreSimulator.framework/Versions/A/"
               "Resources/launchd_sim")
SIM_LSTART = "Sat Oct 10 07:00:00 2026"  # the start time the fixtures give every launchd_sim
SIM_KEEP_CODES = ("booted-recently", "held-by-process", "simulator-app-running",
                  "xcode-running", "simctl-unreadable", "process-table-unreadable",
                  "start-time-unreadable", "boot-record-mismatch")


def sim_launchd_pid(udid):
    """The launchd_sim pid this file gives UDID: 1000 plus its last two digits."""
    return 1000 + int(udid[-2:])


def sim_launchd_row(udid, pid=None):
    """The process-table row (pid, ppid, command) of UDID's launchd_sim, a child of launchd."""
    return (sim_launchd_pid(udid) if pid is None else pid, 1, SIM_LAUNCHD + " " + udid)


def sim_iso_ago(seconds):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - seconds))


def sim_record(udid, name, at, pid=None, start=SIM_LSTART):
    """A boot-record line. The launchd_sim fields default to the ones the live table gives UDID."""
    return json.dumps({"udid": udid, "name": name, "deviceTypeIdentifier": SIM_TYPE,
                       "runtime": SIM_RUNTIME, "at": at,
                       "launchd_pid": sim_launchd_pid(udid) if pid is None else pid,
                       "launchd_start": start})


class SimWorld:
    """In-process stand-ins for `xcrun simctl` and the process table. Replaces sweep's
    subprocess.run for one case and records every call in `calls`. Any other command fails the
    case loudly: the tier must not read or run anything this file has not answered. Every Booted
    device gets its launchd_sim row in the table unless the case names one."""

    def __init__(self, devices, ps_rows):
        self.devices = devices      # [(udid, name, "Booted" | "Shutdown")]
        self.ps_rows = list(ps_rows)  # [(pid, ppid, command)]
        for udid, _, state in devices:
            if state == "Booted" and not any("launchd_sim" in cmd and udid in cmd
                                             for _, _, cmd in self.ps_rows):
                self.ps_rows.append(sim_launchd_row(udid))
        self.simctl_rc = 0
        self.simctl_out = None      # None: the device list is built from `devices`
        self.ps_rc = 0
        self.ps_out = None          # None: the table is built from `ps_rows`
        self.xcrun_missing = False
        self.calls = []
        self.ps_envs = []           # the env each ps call was given (None: inherited)
        self.uid = os.getuid() if hasattr(os, "getuid") else 0

    def simctl_text(self):
        if self.simctl_out is not None:
            return self.simctl_out
        rows = [{"udid": u, "name": n, "state": s, "deviceTypeIdentifier": SIM_TYPE,
                 "isAvailable": True} for u, n, s in self.devices]
        return json.dumps({"devices": {SIM_RUNTIME: rows}})

    def ps_text(self):
        if self.ps_out is not None:
            return self.ps_out
        if not self.ps_rows:
            # A readable table with no holder in it, as the guard fixtures build. Only ps_out ""
            # is the empty read, so the idle cases and the empty-table case do not collide.
            return "1 0 %d /sbin/launchd\n" % self.uid
        return "".join("%d %d %d %s\n" % (pid, ppid, self.uid, cmd)
                       for pid, ppid, cmd in self.ps_rows)

    def lstart_text(self, argv):
        """The start-time answer: "PID START" lines when the -o list names pid=, else "START"
        lines, one per launchd_sim row (only the -p PIDS when -p is given)."""
        wanted = argv[argv.index("-p") + 1].split(",") if "-p" in argv else None
        with_pid = any("pid=" in a for a in argv)
        lines = []
        for pid, _, cmd in self.ps_rows:
            if "launchd_sim" not in cmd or (wanted is not None and str(pid) not in wanted):
                continue
            start = SIM_LSTART
            lines.append("%d %s\n" % (pid, start) if with_pid else start + "\n")
        return "".join(lines)

    def run(self, argv, *a, **k):
        self.calls.append(list(argv))
        if argv[0] == "xcrun":
            if self.xcrun_missing:
                raise FileNotFoundError(argv[0])
            if "shutdown" in argv:
                return subprocess.CompletedProcess(argv, 0, "", "")
            return subprocess.CompletedProcess(argv, self.simctl_rc, self.simctl_text(), "")
        if argv[0] == "ps":
            self.ps_envs.append(k.get("env"))
            if any("lstart" in a for a in argv):
                return subprocess.CompletedProcess(argv, self.ps_rc, self.lstart_text(argv), "")
            return subprocess.CompletedProcess(argv, self.ps_rc, self.ps_text(), "")
        raise AssertionError("the simulator tier ran a command no case answers: %r" % (argv,))

    def shutdowns(self):
        """The UDIDs of every `simctl shutdown` call, in call order."""
        return [c[3] for c in self.calls if c[:3] == ["xcrun", "simctl", "shutdown"]]


@unittest.skipIf(sys.platform.startswith("win"), "the tier reads simctl and a POSIX ps table")
class SimulatorTierTests(unittest.TestCase):
    """Every case names its subject first (the devices, the record), then asserts a verdict."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="sim_tier_")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.record = os.path.join(self.dir, "sim-boots.jsonl")
        self.world = None
        for patch in (mock.patch.object(sys, "platform", "darwin"),
                      mock.patch("shutil.which", return_value="/usr/bin/xcrun")):
            patch.start()
            self.addCleanup(patch.stop)

    def arm(self, devices, ps_rows=(), records=()):
        self.world = SimWorld(devices, list(ps_rows))
        write(self.record, "".join(line + "\n" for line in records))
        patch = mock.patch.object(sweep.subprocess, "run", self.world.run)
        patch.start()
        self.addCleanup(patch.stop)

    def tier(self, confirm):
        return {d["udid"]: d for d in sweep.sim_tier(confirm, record_path=self.record)}

    def test_idle_recorded_device_is_shut_down_on_confirm(self):
        self.arm([(SIM_U1, "Idle Pro", "Booted")],
                 records=[sim_record(SIM_U1, "Idle Pro", sim_iso_ago(2 * 3600))])
        decisions = self.tier(confirm=True)
        self.assertIn(SIM_U1, decisions, "the recorded booted device was not judged")
        self.assertEqual(decisions[SIM_U1]["action"], "shutdown")
        self.assertEqual(self.world.shutdowns(), [SIM_U1])

    def test_preview_plans_the_shutdown_and_runs_none(self):
        self.arm([(SIM_U1, "Idle Pro", "Booted")],
                 records=[sim_record(SIM_U1, "Idle Pro", sim_iso_ago(2 * 3600))])
        decisions = self.tier(confirm=False)
        self.assertIn(SIM_U1, decisions, "the recorded booted device was not judged")
        self.assertEqual(decisions[SIM_U1]["action"], "shutdown")
        self.assertEqual(self.world.shutdowns(), [], "a preview ran a shutdown")

    def test_one_shutdown_per_device_and_never_all(self):
        self.arm([(SIM_U1, "Idle Pro", "Booted"), (SIM_U2, "Idle Two", "Booted")],
                 records=[sim_record(SIM_U1, "Idle Pro", sim_iso_ago(2 * 3600)),
                          sim_record(SIM_U2, "Idle Two", sim_iso_ago(3 * 3600))])
        decisions = self.tier(confirm=True)
        self.assertEqual(len(decisions), 2, "both recorded devices must be judged")
        self.assertEqual(sorted(self.world.shutdowns()), sorted([SIM_U1, SIM_U2]))
        self.assertFalse(any("all" in c for c in self.world.calls), "a call named `all`")

    def test_an_unrecorded_booted_device_is_never_shut_down(self):
        self.arm([(SIM_U1, "Idle Pro", "Booted"), (SIM_U9, "Owner Pro", "Booted")],
                 records=[sim_record(SIM_U1, "Idle Pro", sim_iso_ago(2 * 3600))])
        decisions = self.tier(confirm=True)
        self.assertEqual(decisions[SIM_U1]["action"], "shutdown")
        self.assertEqual(self.world.shutdowns(), [SIM_U1],
                         "an owner-booted device that no boot record names was shut down")

    def test_a_recorded_device_already_shut_down_is_left_alone(self):
        self.arm([(SIM_U1, "Old Pro", "Shutdown"), (SIM_U2, "Idle Two", "Booted")],
                 records=[sim_record(SIM_U1, "Old Pro", sim_iso_ago(2 * 3600)),
                          sim_record(SIM_U2, "Idle Two", sim_iso_ago(2 * 3600))])
        decisions = self.tier(confirm=True)
        self.assertEqual(decisions[SIM_U2]["action"], "shutdown", "the control was not judged")
        self.assertEqual(self.world.shutdowns(), [SIM_U2])

    def test_booted_under_an_hour_is_kept(self):
        self.arm([(SIM_U1, "Fresh Pro", "Booted")],
                 records=[sim_record(SIM_U1, "Fresh Pro", sim_iso_ago(59 * 60))])
        decisions = self.tier(confirm=True)
        self.assertIn(SIM_U1, decisions, "the recorded booted device was not judged")
        self.assertEqual(decisions[SIM_U1]["action"], "keep")
        self.assertIn("booted-recently", decisions[SIM_U1]["reason"])
        self.assertEqual(self.world.shutdowns(), [])

    def test_the_newest_boot_record_decides(self):
        self.arm([(SIM_U1, "Fresh Pro", "Booted")],
                 records=[sim_record(SIM_U1, "Fresh Pro", sim_iso_ago(2 * 3600)),
                          sim_record(SIM_U1, "Fresh Pro", sim_iso_ago(10 * 60))])
        decisions = self.tier(confirm=True)
        self.assertIn(SIM_U1, decisions, "the recorded booted device was not judged")
        self.assertEqual(decisions[SIM_U1]["action"], "keep")
        self.assertIn("booted-recently", decisions[SIM_U1]["reason"])
        self.assertEqual(self.world.shutdowns(), [])

    def test_a_process_outside_the_device_tree_naming_its_udid_keeps_it(self):
        # The Claude.app panel holder: `simctl spawn <UDID> log stream`, under Claude, not launchd_sim.
        self.arm([(SIM_U1, "Idle Pro", "Booted")],
                 ps_rows=[sim_launchd_row(SIM_U1),
                          (400, 1, "/Applications/Claude.app/Contents/MacOS/Claude"),
                          (500, 400, "xcrun simctl spawn %s log stream --level debug" % SIM_U1)],
                 records=[sim_record(SIM_U1, "Idle Pro", sim_iso_ago(2 * 3600))])
        decisions = self.tier(confirm=True)
        self.assertIn(SIM_U1, decisions, "the recorded booted device was not judged")
        self.assertEqual(decisions[SIM_U1]["action"], "keep")
        self.assertIn("held-by-process", decisions[SIM_U1]["reason"])
        self.assertEqual(self.world.shutdowns(), [])

    def test_a_process_naming_the_device_name_keeps_it(self):
        self.arm([(SIM_U1, "Idle Pro", "Booted")],
                 ps_rows=[sim_launchd_row(SIM_U1),
                          (500, 1, "/usr/local/bin/probe --device 'Idle Pro'")],
                 records=[sim_record(SIM_U1, "Idle Pro", sim_iso_ago(2 * 3600))])
        decisions = self.tier(confirm=True)
        self.assertIn(SIM_U1, decisions, "the recorded booted device was not judged")
        self.assertEqual(decisions[SIM_U1]["action"], "keep")
        self.assertIn("held-by-process", decisions[SIM_U1]["reason"])
        self.assertEqual(self.world.shutdowns(), [])

    def test_a_process_naming_booted_keeps_it(self):
        self.arm([(SIM_U1, "Idle Pro", "Booted")],
                 ps_rows=[sim_launchd_row(SIM_U1),
                          (500, 1, "xcrun simctl list devices booted")],
                 records=[sim_record(SIM_U1, "Idle Pro", sim_iso_ago(2 * 3600))])
        decisions = self.tier(confirm=True)
        self.assertIn(SIM_U1, decisions, "the recorded booted device was not judged")
        self.assertEqual(decisions[SIM_U1]["action"], "keep")
        self.assertIn("held-by-process", decisions[SIM_U1]["reason"])
        self.assertEqual(self.world.shutdowns(), [])

    def test_the_launchd_sim_argv_naming_its_own_udid_is_not_a_holder(self):
        self.arm([(SIM_U1, "Idle Pro", "Booted")],
                 ps_rows=[sim_launchd_row(SIM_U1)],
                 records=[sim_record(SIM_U1, "Idle Pro", sim_iso_ago(2 * 3600))])
        decisions = self.tier(confirm=True)
        self.assertEqual(decisions[SIM_U1]["action"], "shutdown",
                         "the device's own launchd_sim counted as a holder of itself")
        self.assertEqual(self.world.shutdowns(), [SIM_U1])

    def test_an_in_simulator_process_naming_its_udid_is_not_a_holder(self):
        self.arm([(SIM_U1, "Idle Pro", "Booted")],
                 ps_rows=[sim_launchd_row(SIM_U1),
                          (1002, 1001, "/Applications/Probe.app/Probe --udid " + SIM_U1)],
                 records=[sim_record(SIM_U1, "Idle Pro", sim_iso_ago(2 * 3600))])
        decisions = self.tier(confirm=True)
        self.assertEqual(decisions[SIM_U1]["action"], "shutdown",
                         "a process inside the device's own tree counted as a holder")
        self.assertEqual(self.world.shutdowns(), [SIM_U1])

    def test_simulator_app_running_keeps_every_device(self):
        self.arm([(SIM_U1, "Idle Pro", "Booted"), (SIM_U2, "Idle Two", "Booted")],
                 ps_rows=[(600, 1, "/Applications/Simulator.app/Contents/MacOS/Simulator")],
                 records=[sim_record(SIM_U1, "Idle Pro", sim_iso_ago(2 * 3600)),
                          sim_record(SIM_U2, "Idle Two", sim_iso_ago(2 * 3600))])
        decisions = self.tier(confirm=True)
        self.assertIn(SIM_U2, decisions, "the recorded booted devices were not judged")
        for udid in (SIM_U1, SIM_U2):
            self.assertEqual(decisions[udid]["action"], "keep")
            self.assertIn("simulator-app-running", decisions[udid]["reason"])
        self.assertEqual(self.world.shutdowns(), [])

    def test_xcode_running_keeps_every_device(self):
        self.arm([(SIM_U1, "Idle Pro", "Booted")],
                 ps_rows=[(600, 1, "/Applications/Xcode.app/Contents/MacOS/Xcode")],
                 records=[sim_record(SIM_U1, "Idle Pro", sim_iso_ago(2 * 3600))])
        decisions = self.tier(confirm=True)
        self.assertIn(SIM_U1, decisions, "the recorded booted device was not judged")
        self.assertEqual(decisions[SIM_U1]["action"], "keep")
        self.assertIn("xcode-running", decisions[SIM_U1]["reason"])
        self.assertEqual(self.world.shutdowns(), [])

    def test_xcode_beta_running_keeps_every_device(self):
        self.arm([(SIM_U1, "Idle Pro", "Booted"), (SIM_U2, "Idle Two", "Booted")],
                 ps_rows=[(600, 1, "/Applications/Xcode-beta.app/Contents/MacOS/Xcode")],
                 records=[sim_record(SIM_U1, "Idle Pro", sim_iso_ago(2 * 3600)),
                          sim_record(SIM_U2, "Idle Two", sim_iso_ago(2 * 3600))])
        decisions = self.tier(confirm=True)
        self.assertIn(SIM_U2, decisions, "the recorded booted devices were not judged")
        for udid in (SIM_U1, SIM_U2):
            self.assertEqual(decisions[udid]["action"], "keep")
            self.assertEqual(decisions[udid]["reason"], "xcode-running",
                             "Xcode-beta.app is not read as Xcode running")
        self.assertEqual(self.world.shutdowns(), [])

    def test_a_device_booted_again_by_hand_is_kept(self):
        # Recorded 4 hours ago with launchd_sim pid 501. Shut down, then booted by hand: the live
        # launchd_sim has pid 1001 and a start time. No record line for the hand boot.
        self.arm([(SIM_U1, "Idle Pro", "Booted")],
                 records=[sim_record(SIM_U1, "Idle Pro", sim_iso_ago(4 * 3600), pid=501,
                                     start="Sat Oct 10 00:10:00 2026")])
        decisions = self.tier(confirm=True)
        self.assertIn(SIM_U1, decisions, "the recorded booted device was not judged")
        self.assertEqual(decisions[SIM_U1]["action"], "keep")
        self.assertEqual(decisions[SIM_U1]["reason"], "boot-record-mismatch",
                         "a device booted by hand was judged on the record of an older boot")
        self.assertEqual(self.world.shutdowns(), [])

    def test_the_same_launchd_pid_with_a_new_start_time_is_kept(self):
        # A pid reused after the recorded launchd_sim died: same pid, different start time.
        self.arm([(SIM_U1, "Idle Pro", "Booted")],
                 records=[sim_record(SIM_U1, "Idle Pro", sim_iso_ago(4 * 3600),
                                     start="Fri Oct 9 09:00:00 2026")])
        decisions = self.tier(confirm=True)
        self.assertIn(SIM_U1, decisions, "the recorded booted device was not judged")
        self.assertEqual(decisions[SIM_U1]["action"], "keep")
        self.assertEqual(decisions[SIM_U1]["reason"], "boot-record-mismatch",
                         "a reused launchd_sim pid with a new start time matched the record")
        self.assertEqual(self.world.shutdowns(), [])

    def test_two_live_launchd_sims_for_one_udid_keep_it(self):
        # The record names pid 90. The table names two launchd_sim processes for the UDID, so no
        # single live launchd_sim is this boot, and the device is kept.
        self.arm([(SIM_U1, "Idle Pro", "Booted")],
                 ps_rows=[sim_launchd_row(SIM_U1, pid=90), sim_launchd_row(SIM_U1, pid=200)],
                 records=[sim_record(SIM_U1, "Idle Pro", sim_iso_ago(2 * 3600), pid=90)])
        decisions = self.tier(confirm=True)
        self.assertIn(SIM_U1, decisions, "the recorded booted device was not judged")
        self.assertEqual(decisions[SIM_U1]["action"], "keep")
        self.assertEqual(decisions[SIM_U1]["reason"], "boot-record-mismatch",
                         "two live launchd_sim processes matched the record by their first pid")
        self.assertEqual(self.world.shutdowns(), [])

    def test_both_ps_reads_run_under_lc_all_c(self):
        # The table read and the lstart read force LC_ALL=C, whatever the parent's locale is.
        self.arm([(SIM_U1, "Idle Pro", "Booted")],
                 records=[sim_record(SIM_U1, "Idle Pro", sim_iso_ago(2 * 3600))])
        with mock.patch.dict(os.environ, {"LC_ALL": "de_DE.UTF-8"}):
            self.tier(confirm=False)
        self.assertGreaterEqual(len(self.world.ps_envs), 2,
                                "the tier made fewer than two ps reads for one booted device")
        for env in self.world.ps_envs:
            self.assertEqual((env or {}).get("LC_ALL"), "C",
                             "a ps read ran under %r, not C" % ((env or {}).get("LC_ALL"),))

    def test_a_failed_simctl_read_keeps_every_device(self):
        self.arm([(SIM_U1, "Idle Pro", "Booted")],
                 records=[sim_record(SIM_U1, "Idle Pro", sim_iso_ago(2 * 3600))])
        self.world.simctl_rc = 1
        decisions = self.tier(confirm=True)
        self.assertIn(SIM_U1, decisions, "the recorded device was not judged")
        self.assertEqual(decisions[SIM_U1]["action"], "keep")
        self.assertIn("simctl-unreadable", decisions[SIM_U1]["reason"])
        self.assertEqual(self.world.shutdowns(), [])

    def test_bad_simctl_json_keeps_every_device(self):
        self.arm([(SIM_U1, "Idle Pro", "Booted")],
                 records=[sim_record(SIM_U1, "Idle Pro", sim_iso_ago(2 * 3600))])
        self.world.simctl_out = "this is not json {"
        decisions = self.tier(confirm=True)
        self.assertIn(SIM_U1, decisions, "the recorded device was not judged")
        self.assertEqual(decisions[SIM_U1]["action"], "keep")
        self.assertIn("simctl-unreadable", decisions[SIM_U1]["reason"])
        self.assertEqual(self.world.shutdowns(), [])

    def test_a_failed_process_table_keeps_every_device(self):
        self.arm([(SIM_U1, "Idle Pro", "Booted")],
                 records=[sim_record(SIM_U1, "Idle Pro", sim_iso_ago(2 * 3600))])
        self.world.ps_rc = 1
        decisions = self.tier(confirm=True)
        self.assertIn(SIM_U1, decisions, "the recorded device was not judged")
        self.assertEqual(decisions[SIM_U1]["action"], "keep")
        self.assertIn("process-table-unreadable", decisions[SIM_U1]["reason"])
        self.assertEqual(self.world.shutdowns(), [])

    def test_an_empty_process_table_keeps_every_device(self):
        self.arm([(SIM_U1, "Idle Pro", "Booted")],
                 records=[sim_record(SIM_U1, "Idle Pro", sim_iso_ago(2 * 3600))])
        self.world.ps_out = ""
        decisions = self.tier(confirm=True)
        self.assertIn(SIM_U1, decisions, "the recorded device was not judged")
        self.assertEqual(decisions[SIM_U1]["action"], "keep")
        self.assertIn("process-table-unreadable", decisions[SIM_U1]["reason"])
        self.assertEqual(self.world.shutdowns(), [])

    def test_an_unreadable_start_time_keeps_that_device(self):
        self.arm([(SIM_U1, "Idle Pro", "Booted")],
                 records=[sim_record(SIM_U1, "Idle Pro", "sometime last tuesday")])
        decisions = self.tier(confirm=True)
        self.assertIn(SIM_U1, decisions, "the recorded device was not judged")
        self.assertEqual(decisions[SIM_U1]["action"], "keep")
        self.assertIn("start-time-unreadable", decisions[SIM_U1]["reason"])
        self.assertEqual(self.world.shutdowns(), [])


    def test_the_run_cap_shuts_down_four_and_keeps_the_fifth(self):
        udids = ["1A2B3C4D-0000-4000-8000-0000000001%02d" % n for n in range(5)]
        self.arm([(u, "Idle %d" % n, "Booted") for n, u in enumerate(udids)],
                 records=[sim_record(u, "Idle %d" % n, sim_iso_ago(2 * 3600))
                          for n, u in enumerate(udids)])
        decisions = self.tier(confirm=True)
        self.assertEqual(sorted(decisions), sorted(udids), "all five recorded devices must be judged")
        shutdowns = self.world.shutdowns()
        self.assertEqual(len(shutdowns), 4, "the run cap must allow exactly four shutdowns")
        self.assertEqual(len(set(shutdowns)), 4, "a device was shut down twice")
        kept = [u for u in udids if decisions[u]["action"] == "keep"]
        self.assertEqual(kept, [u for u in udids if u not in shutdowns])
        self.assertEqual(len(kept), 1, "exactly one device must wait for the next run")
        self.assertEqual(decisions[kept[0]]["reason"], "run-cap-reached")


class SimulatorTierPlatformTests(unittest.TestCase):
    """No xcrun, or Windows: no tier. Runs on every platform, so it holds on the Windows CI too."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="sim_tier_platform_")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.record = os.path.join(self.dir, "sim-boots.jsonl")
        write(self.record, sim_record(SIM_U1, "Idle Pro", sim_iso_ago(2 * 3600)) + "\n")
        self.world = SimWorld([(SIM_U1, "Idle Pro", "Booted")], [])
        patch = mock.patch.object(sweep.subprocess, "run", self.world.run)
        patch.start()
        self.addCleanup(patch.stop)

    def test_no_xcrun_means_no_tier_and_prints_nothing(self):
        self.world.xcrun_missing = True
        out = io.StringIO()
        with mock.patch("shutil.which", return_value=None), contextlib.redirect_stdout(out):
            decisions = sweep.sim_tier(True, record_path=self.record)
        self.assertEqual(decisions, [], "the tier judged a device with no xcrun on the PATH")
        self.assertEqual(out.getvalue(), "", "the tier printed with no xcrun on the PATH")
        self.assertEqual(self.world.shutdowns(), [])

    def test_windows_has_no_tier(self):
        with mock.patch.object(sys, "platform", "win32"), \
                mock.patch("shutil.which", return_value="C:\\Tools\\xcrun.exe"):
            decisions = sweep.sim_tier(True, record_path=self.record)
        self.assertEqual(decisions, [], "the tier ran on Windows")
        self.assertEqual(self.world.shutdowns(), [])


class SimulatorTierActTests(unittest.TestCase):
    """The preview and the act are one decision: a preview and a confirm name the same devices."""

    def test_preview_and_confirm_judge_the_same_devices(self):
        dir_ = tempfile.mkdtemp(prefix="sim_tier_act_")
        self.addCleanup(shutil.rmtree, dir_, True)
        record = os.path.join(dir_, "sim-boots.jsonl")
        write(record, sim_record(SIM_U1, "Idle Pro", sim_iso_ago(2 * 3600)) + "\n"
              + sim_record(SIM_U2, "Fresh Two", sim_iso_ago(5 * 60)) + "\n")
        world = SimWorld([(SIM_U1, "Idle Pro", "Booted"), (SIM_U2, "Fresh Two", "Booted")], [])
        patches = [mock.patch.object(sweep.subprocess, "run", world.run),
                   mock.patch.object(sys, "platform", "darwin"),
                   mock.patch("shutil.which", return_value="/usr/bin/xcrun")]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        preview = sweep.sim_tier(False, record_path=record)
        self.assertEqual(sorted(d["udid"] for d in preview), sorted([SIM_U1, SIM_U2]))
        self.assertEqual(world.shutdowns(), [], "the preview ran a shutdown")
        act = sweep.sim_tier(True, record_path=record)
        self.assertEqual(sorted(d["udid"] for d in act), sorted([SIM_U1, SIM_U2]))
        self.assertEqual(sorted((d["udid"], d["action"]) for d in preview),
                         sorted((d["udid"], d["action"]) for d in act),
                         "a preview predicted a different verdict than the act")
        self.assertEqual(world.shutdowns(), [SIM_U1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
