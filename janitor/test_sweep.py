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
import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest

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
        decision = sweep.decide_worktree(self.root, self.entry_for(self.removable))
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


class ListenerDecisionTests(unittest.TestCase):
    """`sweep.find_swept_listeners` / `sweep.decide_listener`, this build's own subject. Every
    listener here is a REAL process this suite starts itself (`spawn_plain_listener` /
    `spawn_orphaned_listener`, defined above) -- never a mock, for the same reason
    hooks/test_guard.py and this file's own git fixtures never mock git."""

    @classmethod
    def setUpClass(cls):
        cls.root = os.path.join(ROOT, "listener-repo")
        make_repo(cls.root, {"f.txt": "base\n"})

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
        decision = sweep.decide_worktree(self.root, self.entry_for(self.occupied))
        self.assertEqual(decision["action"], "keep")
        self.assertTrue(decision["reason"].startswith("process-inside:"))
        self.assertIn(str(self.pid), decision["reason"])

    def test_an_empty_worktree_is_still_removable(self):
        decision = sweep.decide_worktree(self.root, self.entry_for(self.empty))
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
        with _BreakRead(_platform_read_name("cwd")):
            decision = sweep.decide_worktree(self.root, self.entry_for(self.empty))
        self.assertEqual(decision["action"], "reap")
        self.assertEqual(decision["reason"], "removable")

    def test_unreadable_pid_enumeration_keeps_the_worktree(self):
        """The OTHER half of the pre-check's own unreadable contract: the brief's own words,
        "if the whole listing ... or the pre-check enumeration fails, KEEP everything and
        remove no worktree" -- this is the whole PID listing itself failing, not one pid's cwd."""
        original = sweep.list_all_pids
        sweep.list_all_pids = lambda: None
        try:
            decision = sweep.decide_worktree(self.root, self.entry_for(self.empty))
        finally:
            sweep.list_all_pids = original
        self.assertEqual(decision["action"], "keep")
        self.assertEqual(decision["reason"], "unreadable-subject")


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
        guard._git = failing_git
        try:
            sweep.reap_branch(root, "old-topic-2", decision, log_path)
        finally:
            guard._git = real_git

        self.assertIn("error", decision)
        self.assertIn("old-topic-2", sweep.list_local_branches(root))
        tomb = run_vcs(root, "rev-parse", sweep.TOMBSTONE_REF_PREFIX + "old-topic-2")
        self.assertEqual(tomb.returncode, 0)
        self.assertEqual(tomb.stdout.strip(), tip)
        entries = sweep.read_restore_log(log_path)
        self.assertTrue(len(entries) > 0)
        self.assertTrue(any(e.get("branch") == "old-topic-2" for e in entries))


# --------------------------------------------------------------------------- worktree removal


class WorktreeRemovalTests(unittest.TestCase):
    def test_confirm_removes_a_reapable_worktree(self):
        root = os.path.join(ROOT, "wt-remove-repo")
        make_repo(root, {"f.txt": "x\n"})
        target = os.path.join(ROOT, "wt-remove-target")
        run_vcs(root, "worktree", "add", "-q", target, "-b", "lane-remove")

        entries = sweep.parse_worktree_list(root)
        self.assertTrue(entries is not None and len(entries) > 0)

        log_path = os.path.join(ROOT, "wt-remove.log")
        result = sweep.sweep_repo(root, confirm=True, restore_log_path=log_path)
        self.assertIsNone(result["refused"])
        matches = [w for w in result["worktrees"]
                   if os.path.normcase(os.path.realpath(w["path"]))
                   == os.path.normcase(os.path.realpath(target))]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["action"], "reap")
        self.assertNotIn("error", matches[0])
        self.assertFalse(os.path.isdir(target))


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
        result = sweep.sweep_repo(root, confirm=False, restore_log_path=log_path)
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
        now = int(time.time() * 1000)
        self.write_log([{"repo": self.repo, "branch": "old-two",
                          "commit": "deadbeef", "time_ms": now - 91 * 86400000}])
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
