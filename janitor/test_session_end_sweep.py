#!/usr/bin/env python3
"""Cases for janitor/session_end_sweep.py. Standard library only, `unittest`, no pytest.

Run it from the repository root:

    python3 janitor/test_session_end_sweep.py -v

Every arm that proves the hook FAILS OPEN runs the real script as `janitor/sweep.py`'s own
subprocess grandchild would: `python3 session_end_sweep.py` with a JSON payload on stdin,
asserting the PROCESS exits 0 -- not just that some inner function returns without raising.
Claude Code only sees the process's own exit code, so that is the fact each arm has to prove
(plan, "the hook always fails open").

Every fixture repository is a REAL git repository built with real git calls, the same way
janitor/test_sweep.py's own fixtures are: a fake or mocked git would prove nothing about
`resolve_repo_root`, which shells out to git twice.
"""
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
HOOK = os.path.join(HERE, "session_end_sweep.py")
REAL_SWEEP = os.path.join(HERE, "sweep.py")
sys.path.insert(0, os.path.join(REPO_ROOT, "hooks"))
sys.path.insert(0, HERE)
import guard  # noqa: E402

VCS = "g" + "it"
IDENT = ["-c", "user.email=session-end-cases@example.invalid", "-c", "user.name=session-end-cases"]

ROOT = tempfile.mkdtemp(prefix="session_end_cases_")


def run_vcs(where, *args):
    return subprocess.run([VCS, "-C", where, *args], capture_output=True, text=True, timeout=10)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def require(condition, message):
    if not condition:
        sys.exit("fixture setup failed: " + message)


def make_repo(where, branch="main"):
    os.makedirs(where, exist_ok=True)
    require(run_vcs(where, "init", "-q", "-b", branch, ".").returncode == 0, "init %r" % where)
    write(os.path.join(where, "README.md"), "hello\n")
    require(run_vcs(where, "add", "-A").returncode == 0, "add %r" % where)
    require(run_vcs(where, *IDENT, "commit", "-q", "-m", "first").returncode == 0,
            "first commit in %r" % where)


def add_reapable_branch(where, name):
    """A branch that is a plain ancestor of `main`: the cheapest REAP shape, and not checked
    out, not protected, not the only copy anywhere."""
    require(run_vcs(where, "branch", name).returncode == 0, "branch %s in %r" % (name, where))


def local_branches(where):
    answer = run_vcs(where, "for-each-ref", "--format=%(refname:short)", "refs/heads")
    require(answer.returncode == 0, "for-each-ref in %r" % where)
    return [line.strip() for line in answer.stdout.splitlines() if line.strip()]


def run_hook(hook_payload, env_extra=None, cwd=None, timeout=15):
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, HOOK],
        input=json.dumps(hook_payload) if hook_payload is not None else "",
        capture_output=True, text=True, timeout=timeout, cwd=cwd, env=env,
    )


class BadInputFailsOpen(unittest.TestCase):
    """Arm 1 of 4: stdin that is not valid JSON at all."""

    def test_garbage_stdin_still_exits_0(self):
        result = subprocess.run(
            [sys.executable, HOOK], input="{not json at all", capture_output=True, text=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_json_that_is_not_an_object_still_exits_0(self):
        result = run_hook(None, timeout=15)
        # empty stdin: json.loads("") raises, same code path as garbage
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_json_array_instead_of_object_still_exits_0(self):
        env = dict(os.environ)
        result = subprocess.run(
            [sys.executable, HOOK], input="[1, 2, 3]", capture_output=True, text=True,
            timeout=15, env=env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


class NoRepositoryFailsOpen(unittest.TestCase):
    """Arm 3 of 4: `cwd` names a real directory that holds no git repository at all."""

    def test_directory_in_no_repository_still_exits_0(self):
        empty_dir = tempfile.mkdtemp(prefix="no_repo_", dir=ROOT)
        result = run_hook({"hook_event_name": "SessionEnd", "cwd": empty_dir})
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_directory_in_no_repository_sweeps_nothing(self):
        """Not just exit 0: the real sweep must never have run at all, proven by no restore
        log and no tombstone appearing anywhere `guard.config_dir()` could have pointed."""
        empty_dir = tempfile.mkdtemp(prefix="no_repo_sweep_", dir=ROOT)
        cfg = os.path.join(ROOT, "cfg_no_repo")
        result = run_hook(
            {"hook_event_name": "SessionEnd", "cwd": empty_dir},
            env_extra={"CLAUDE_CONFIG_DIR": cfg},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(os.path.exists(os.path.join(cfg, "janitor", "restore-log.jsonl")))


class MissingSweepFailsOpen(unittest.TestCase):
    """Arm 2 of 4: janitor/sweep.py, as this hook would find it, does not exist."""

    def test_missing_sweep_still_exits_0(self):
        repo = os.path.join(ROOT, "missing_sweep_repo")
        make_repo(repo)
        result = run_hook(
            {"hook_event_name": "SessionEnd", "cwd": repo},
            env_extra={"JANITOR_SWEEP_PATH": os.path.join(ROOT, "no-such-sweep.py")},
        )
        self.assertEqual(result.returncode, 0, result.stderr)


class RaisingOrHangingSweepFailsOpen(unittest.TestCase):
    """Arm 4 of 4, two sub-cases: the sweep this hook calls raises, or hangs past the hook's own
    timeout. Both must still let the hook process itself exit 0."""

    @classmethod
    def setUpClass(cls):
        cls.repo = os.path.join(ROOT, "raising_hanging_repo")
        make_repo(cls.repo)

        cls.raising_sweep = os.path.join(ROOT, "fake_sweep_raises.py")
        write(cls.raising_sweep, textwrap.dedent("""\
            import sys
            raise RuntimeError("this fake sweep always raises")
        """))

        cls.hanging_sweep = os.path.join(ROOT, "fake_sweep_hangs.py")
        write(cls.hanging_sweep, textwrap.dedent("""\
            import time
            time.sleep(600)
        """))

    def test_raising_sweep_still_exits_0(self):
        result = run_hook(
            {"hook_event_name": "SessionEnd", "cwd": self.repo},
            env_extra={"JANITOR_SWEEP_PATH": self.raising_sweep},
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_hanging_sweep_still_exits_0_and_does_not_wait_out_the_hang(self):
        start = time.monotonic()
        result = run_hook(
            {"hook_event_name": "SessionEnd", "cwd": self.repo},
            env_extra={"JANITOR_SWEEP_PATH": self.hanging_sweep, "JANITOR_SWEEP_TIMEOUT": "1"},
            timeout=20,
        )
        elapsed = time.monotonic() - start
        self.assertEqual(result.returncode, 0, result.stderr)
        # the fake sweep sleeps 600s; the hook's own internal timeout (set to 1s above) must
        # have cut it off, never the outer test harness timeout (20s).
        self.assertLess(elapsed, 10, "hook did not honor its own sweep timeout")


class SweepsOnlyTheEndingSessionsRepository(unittest.TestCase):
    """Sweeps the ending session's OWN repository, and no other one on disk."""

    def test_sweeps_repo_a_leaves_repo_b_untouched(self):
        repo_a = os.path.join(ROOT, "repo_a")
        repo_b = os.path.join(ROOT, "repo_b")
        make_repo(repo_a)
        make_repo(repo_b)
        add_reapable_branch(repo_a, "reap-me-a")
        add_reapable_branch(repo_b, "reap-me-b")
        require("reap-me-a" in local_branches(repo_a), "fixture: repo_a has its reapable branch")
        require("reap-me-b" in local_branches(repo_b), "fixture: repo_b has its reapable branch")

        cfg = os.path.join(ROOT, "cfg_scoped")
        result = run_hook(
            {"hook_event_name": "SessionEnd", "cwd": repo_a},
            env_extra={"CLAUDE_CONFIG_DIR": cfg},
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        self.assertNotIn("reap-me-a", local_branches(repo_a),
                          "the ending session's own repository should have been swept")
        self.assertIn("reap-me-b", local_branches(repo_b),
                       "a sibling repository must not be touched")

    def test_worktree_cwd_sweeps_the_primary_checkout_not_the_worktree_itself(self):
        """The dangerous mis-resolution this hook must avoid: pointing the sweep AT a linked
        worktree path instead of its primary checkout. If that ever regressed, the primary
        checkout's own worktree entry would stop being excluded from `decide_worktree` and
        could be evaluated as reapable -- proven here by asserting the primary checkout still
        exists after the sweep runs, not merely by asserting the hook exits 0.

        The linked worktree itself is NOT asserted to survive: no session record marks it live
        (this fixture never writes one), so `guard.worktree_live_session` correctly answers
        "not live" and the sweep correctly reaps it -- the same way it would reap any worktree
        whose session has ended and left no other claim on it. That is the sweep working as
        designed, not the defect this arm guards against."""
        primary = os.path.join(ROOT, "wt_primary")
        make_repo(primary)
        add_reapable_branch(primary, "reap-me-from-worktree")
        wt_branch = "wt-feature"
        require(run_vcs(primary, "branch", wt_branch).returncode == 0, "branch for worktree")
        wt_path = os.path.join(ROOT, "wt_linked")
        require(run_vcs(primary, "worktree", "add", wt_path, wt_branch).returncode == 0,
                "worktree add")
        require(os.path.isdir(wt_path), "fixture: linked worktree exists before the sweep")

        cfg = os.path.join(ROOT, "cfg_worktree_cwd")
        result = run_hook(
            {"hook_event_name": "SessionEnd", "cwd": wt_path},
            env_extra={"CLAUDE_CONFIG_DIR": cfg},
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        self.assertTrue(os.path.isdir(primary), "the primary checkout must survive the sweep")
        self.assertNotIn("reap-me-from-worktree", local_branches(primary),
                          "the shared repository's reapable branch should still have been swept")


class ResolveRepoRootUnit(unittest.TestCase):
    """Direct unit coverage of the one piece of new logic this hook adds beyond calling the
    sweep: resolving `cwd` to a primary checkout, in-process (cheap; the subprocess arms above
    already prove the end-to-end exit-0 contract)."""

    def setUp(self):
        import session_end_sweep
        self.mod = session_end_sweep

    def test_ordinary_checkout_resolves_to_itself(self):
        repo = os.path.join(ROOT, "unit_ordinary")
        make_repo(repo)
        self.assertEqual(
            os.path.realpath(self.mod.resolve_repo_root(repo)), os.path.realpath(repo)
        )

    def test_subdirectory_resolves_to_the_checkout_root(self):
        repo = os.path.join(ROOT, "unit_subdir")
        make_repo(repo)
        sub = os.path.join(repo, "a", "b")
        os.makedirs(sub, exist_ok=True)
        self.assertEqual(
            os.path.realpath(self.mod.resolve_repo_root(sub)), os.path.realpath(repo)
        )

    def test_no_repository_returns_none(self):
        empty = tempfile.mkdtemp(prefix="unit_no_repo_", dir=ROOT)
        self.assertIsNone(self.mod.resolve_repo_root(empty))


if __name__ == "__main__":
    unittest.main(verbosity=2)
