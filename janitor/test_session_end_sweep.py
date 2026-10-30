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
`guard.primary_checkout`, which shells out to git twice.
"""
import atexit
import contextlib
import io
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
import uuid
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
HOOK = os.path.join(HERE, "session_end_sweep.py")
REAL_SWEEP = os.path.join(HERE, "sweep.py")
sys.path.insert(0, os.path.join(REPO_ROOT, "hooks"))
sys.path.insert(0, HERE)
import guard  # noqa: E402

VCS = "g" + "it"
IDENT = ["-c", "user.email=session-end-cases@example.invalid", "-c", "user.name=session-end-cases"]

# test-temp-standard (decisions/test-temp-standard.md): this run's folder is `<pid>-<UUID>` under the
# one temp root this repo shares with hooks/test_guard.py. The first request of a run sweeps the
# sibling run folders older than one day, and the run removes its own folder at exit.
TEMP_ROOT = os.path.join(tempfile.gettempdir(), "claude-settings-test-temp")
RUN_FOLDER_RE = re.compile(r"[0-9]+-[0-9a-f]{32}")
RUN_FOLDER_MAX_AGE = 24 * 60 * 60


def sweep_run_folders(temp_root, own, now=None):
    """Remove each sibling run folder under `temp_root` whose mtime is over a day old. `own` stays."""
    now = time.time() if now is None else now
    try:
        names = os.listdir(temp_root)
    except OSError:
        return
    for name in names:
        path = os.path.join(temp_root, name)
        if (path != own and RUN_FOLDER_RE.fullmatch(name) and os.path.isdir(path)
                and now - os.path.getmtime(path) > RUN_FOLDER_MAX_AGE):
            shutil.rmtree(path, ignore_errors=True)


os.makedirs(TEMP_ROOT, exist_ok=True)
ROOT = os.path.join(TEMP_ROOT, "%d-%s" % (os.getpid(), uuid.uuid4().hex))
os.makedirs(ROOT)
sweep_run_folders(TEMP_ROOT, ROOT)
atexit.register(shutil.rmtree, ROOT, True)


START_CAP_SECONDS = 120


def run_capped(argv, timeout, input_text="", cwd=None, env=None, start_after=None):
    """Run `argv`; return a CompletedProcess with its text output. Its output goes to files in ROOT,
    never to pipes, and the wait has a cap that fails by name.

    Why: on Windows, subprocess.run reads its pipes with no cap after a timeout kill. A grandchild that
    inherited a pipe keeps that read open for as long as the grandchild lives, so the call waits. A
    file has no such read. A process still running at `timeout` is killed, and the run raises
    AssertionError naming it, so a hang reads as a FAIL and never as a skip.

    With `start_after`, the `timeout` cap starts only when that file exists, so a slow host cannot spend
    the cap before the process reaches the point the case judges. The wait for the file has its own cap,
    START_CAP_SECONDS, and fails as a start guard, never as a hang guard.
    """
    stem = os.path.join(ROOT, uuid.uuid4().hex)
    stdin_path, out_path, err_path = stem + ".in", stem + ".out", stem + ".err"
    write(stdin_path, input_text)
    with open(stdin_path, encoding="utf-8") as stdin, \
            open(out_path, "w+", encoding="utf-8", errors="replace") as out, \
            open(err_path, "w+", encoding="utf-8", errors="replace") as err:
        proc = subprocess.Popen(argv, stdin=stdin, stdout=out, stderr=err, cwd=cwd, env=env)
        start_by = time.time() + START_CAP_SECONDS
        while start_after is not None and not os.path.exists(start_after) and proc.poll() is None:
            if time.time() > start_by:
                proc.kill()
                proc.wait(timeout=30)
                raise AssertionError("%s did not write %s in %s s, so it was killed (a start guard)"
                                     % (argv[0], start_after, START_CAP_SECONDS))
            time.sleep(0.05)
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=30)
            raise AssertionError("%s did not finish in %s s, so it was killed (a hang guard)"
                                 % (argv[0], timeout))
        out.seek(0)
        err.seek(0)
        return subprocess.CompletedProcess(argv, code, out.read(), err.read())


def run_vcs(where, *args):
    return run_capped([VCS, "-C", where, *args], timeout=120)


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


def run_hook(hook_payload, env_extra=None, cwd=None, timeout=120, start_after=None):
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    return run_capped(
        [sys.executable, HOOK],
        input_text=json.dumps(hook_payload) if hook_payload is not None else "",
        timeout=timeout, cwd=cwd, env=env, start_after=start_after,
    )


class BadInputFailsOpen(unittest.TestCase):
    """Arm 1 of 4: stdin that is not a usable JSON object. Each row is one input; each must exit 0."""

    def test_garbage_stdin_still_exits_0(self):
        # Rows: not JSON at all; empty stdin (json.loads("") raises); a JSON array, not an object.
        for stdin in ("{not json at all", "", "[1, 2, 3]"):
            with self.subTest(stdin=stdin):
                result = run_capped([sys.executable, HOOK], input_text=stdin, timeout=15)
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

    def test_subdirectory_cwd_sweeps_its_own_repository_and_not_the_sibling(self):
        """A cwd inside a checkout (not its root) must resolve to that checkout's root, and the
        sibling checkout must be left alone."""
        repo_a = os.path.join(ROOT, "repo_a_sub")
        repo_b = os.path.join(ROOT, "repo_b_sub")
        make_repo(repo_a)
        make_repo(repo_b)
        add_reapable_branch(repo_a, "reap-me-a-sub")
        add_reapable_branch(repo_b, "reap-me-b-sub")
        subdir = os.path.join(repo_a, "src", "deep")
        os.makedirs(subdir, exist_ok=True)

        cfg = os.path.join(ROOT, "cfg_subdir_cwd")
        result = run_hook(
            {"hook_event_name": "SessionEnd", "cwd": subdir},
            env_extra={"CLAUDE_CONFIG_DIR": cfg},
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        self.assertNotIn("reap-me-a-sub", local_branches(repo_a),
                         "a cwd inside the checkout should sweep that checkout")
        self.assertIn("reap-me-b-sub", local_branches(repo_b),
                      "a sibling repository must not be touched")


class HookBudgetFitsUnderItsHostCeiling(unittest.TestCase):
    """The hook's own worst-case run time (`session_end_sweep.HOOK_WORST_CASE_SECONDS`) must be
    STRICTLY SMALLER than the timeout settings.json actually gives this hook -- proven against
    the real settings.json in this checkout, not a copy of the number typed into this file."""

    SETTINGS_PATH = os.path.join(REPO_ROOT, "settings.json")

    @staticmethod
    def _session_end_timeout(settings):
        for entry in settings.get("hooks", {}).get("SessionEnd", []):
            for h in entry.get("hooks", []):
                if "session_end_sweep.py" in (h.get("command") or ""):
                    return h.get("timeout")
        return None

    def _wired_timeout(self):
        """Return the timeout settings.json gives this hook, or skip when the hook is disarmed.

        Two different states reach this point, and folding them together would hide one of
        them. An ABSENT `SessionEnd` key is the disarm recorded in
        decisions/session-end-sweep-is-disarmed-until-liveness-is-proven.md. There is no
        ceiling to check, so the three arms below have nothing to say, and they skip. The skip
        reads the config itself, so these arms come back on their own the day the hook returns.
        Nobody has to remember to remove a marker.

        A `SessionEnd` key that IS present but names no entry for this hook is the other state.
        That is a real defect, never the disarm, so it fails the way it always did.
        """
        timeout = self._session_end_timeout(self.settings)
        if timeout is None and "SessionEnd" not in self.settings.get("hooks", {}):
            raise unittest.SkipTest(
                "the SessionEnd hook is disarmed, see "
                "decisions/session-end-sweep-is-disarmed-until-liveness-is-proven.md"
            )
        self.assertIsNotNone(timeout, "no SessionEnd entry in settings.json calls this hook")
        return timeout

    def setUp(self):
        import session_end_sweep
        self.mod = session_end_sweep
        with open(self.SETTINGS_PATH, encoding="utf-8") as handle:
            self.settings = json.load(handle)

    def test_guard_git_call_timeout_constant_matches_the_real_guard_git(self):
        """session_end_sweep.GUARD_GIT_CALL_TIMEOUT_SECONDS is a plain, hand-typed constant, so
        nothing else stops `git_reads._git`'s real subprocess timeout drifting away from it. THIS
        TEST reads the real number back out of `git_reads._git`'s own source and pins it against the
        module's constant. The three arithmetic/settings.json arms around it never re-read
        git_reads.py, so a bump of `git_reads._git`'s `timeout=` turns only this arm red."""
        import importlib
        import inspect
        import re
        source = inspect.getsource(importlib.import_module("git_reads")._git)
        match = re.search(r"timeout\s*=\s*(\d+)", source)
        self.assertIsNotNone(match, "could not find git_reads._git's own timeout= in its source")
        real_timeout = float(match.group(1))
        self.assertEqual(
            real_timeout, self.mod.GUARD_GIT_CALL_TIMEOUT_SECONDS,
            "git_reads._git's real subprocess timeout (%r) no longer matches "
            "session_end_sweep.GUARD_GIT_CALL_TIMEOUT_SECONDS (%r); update the hand-typed "
            "constant (and RESOLVE_ROOT_WORST_CASE_SECONDS / HOOK_WORST_CASE_SECONDS follow it)"
            % (real_timeout, self.mod.GUARD_GIT_CALL_TIMEOUT_SECONDS),
        )

    def test_settings_json_gives_this_hook_a_timeout_strictly_above_its_worst_case(self):
        timeout = self._wired_timeout()
        self.assertGreater(
            timeout, self.mod.HOOK_WORST_CASE_SECONDS,
            "settings.json's SessionEnd timeout (%r) must exceed this hook's own worst-case "
            "run time (%r), or Claude Code's own ceiling could cut the hook off before it "
            "reaches its own fail-open exit" % (timeout, self.mod.HOOK_WORST_CASE_SECONDS),
        )

    def test_settings_json_timeout_leaves_a_real_margin_not_a_sliver(self):
        """Strictly-greater alone would let a 45.01s ceiling "pass" for a 45s worst case, which
        leaves no room for process-start and interpreter-import overhead neither number above
        counts. Require at least SESSION_END_TIMEOUT_MIN_HEADROOM_SECONDS of headroom -- the real
        constant the module states beside its arithmetic, never a copy of the number."""
        timeout = self._wired_timeout()
        self.assertGreaterEqual(
            timeout - self.mod.HOOK_WORST_CASE_SECONDS,
            self.mod.SESSION_END_TIMEOUT_MIN_HEADROOM_SECONDS,
        )

class PermissionsDenyCarriesTheStateFreeGuardRules(unittest.TestCase):
    """The second permissions.deny layer must keep every entry it shipped with, so a missing
    interpreter still blocks .env* and the frozen config paths (see settings.json, "permissions.deny").
    pkill and killall are no deny entries: such an entry refuses before the hook runs, so an owner override
    could not lift it. The guard refuses them (machine-wide-kill), and the guard launcher blocks when
    python or guard.py is missing; the two cases below pin those two halves."""

    EXPECTED = (
        "Read(.env)", "Edit(.env)", "Read(.env.*)",
        "Edit(.env.*)", "Read(!.env.example)", "Edit(!.env.example)",
        "Edit(~/.claude/settings.json)", "Edit(~/.claude/CLAUDE.md)",
        "Edit(~/.claude/hooks/**)", "Edit(~/.claude/lint/**)", "Edit(~/.claude/agents/**)",
        "Edit(~/.claude/janitor/**)", "Edit(~/.claude/state/**)",
    )

    def test_deny_list_has_every_state_free_rule(self):
        with open(os.path.join(REPO_ROOT, "settings.json"), encoding="utf-8") as handle:
            deny = json.load(handle)["permissions"]["deny"]
        missing = [e for e in self.EXPECTED if e not in deny]
        self.assertFalse(missing, "settings.json permissions.deny is missing: %r" % missing)

    def test_deny_list_holds_no_pkill_or_killall_entry(self):
        with open(os.path.join(REPO_ROOT, "settings.json"), encoding="utf-8") as handle:
            deny = json.load(handle)["permissions"]["deny"]
        held = [e for e in deny if e.startswith(("Bash(pkill", "Bash(killall"))]
        self.assertEqual(held, [], "an owner override cannot lift a deny entry")

    def guard_launcher(self):
        with open(os.path.join(REPO_ROOT, "settings.json"), encoding="utf-8") as handle:
            pre = json.load(handle)["hooks"]["PreToolUse"]
        rows = [h["command"] for e in pre for h in e["hooks"]
                if h.get("type") == "command" and "guard.py" in h.get("command", "")
                and "stall_watch" not in h["command"]]
        self.assertEqual(len(rows), 1, "want one guard.py launcher, found %d" % len(rows))
        return rows[0]

    def run_launcher(self, with_guard, path):
        import shutil, tempfile
        shell = shutil.which("sh")
        if not shell:
            self.skipTest("no sh on this host")
        with tempfile.TemporaryDirectory(dir=ROOT) as cfg, tempfile.TemporaryDirectory(dir=ROOT) as empty:
            if with_guard:
                os.makedirs(os.path.join(cfg, "hooks"))
                open(os.path.join(cfg, "hooks", "guard.py"), "w").close()
            env = dict(os.environ, CLAUDE_CONFIG_DIR=cfg, PATH=empty if path is None else path)
            return run_capped([shell, "-c", self.guard_launcher()], input_text="{}", env=env, timeout=60)

    def test_the_guard_launcher_blocks_when_guard_py_is_missing(self):
        r = self.run_launcher(False, None)
        self.assertEqual(r.returncode, 2, r.stderr)

    def test_the_guard_launcher_blocks_when_python_is_missing(self):
        r = self.run_launcher(True, None)
        self.assertEqual(r.returncode, 2, r.stderr)

    def test_the_guard_denies_pkill_and_killall_as_machine_wide_kill(self):
        import tempfile
        guard = os.environ.get("GUARD_UNDER_TEST") or os.path.join(REPO_ROOT, "hooks", "guard.py")
        for command in ("pkill -f node", "pkill node", "killall node"):
            with self.subTest(command=command), tempfile.TemporaryDirectory() as cfg, \
                    tempfile.TemporaryDirectory() as work:
                env = dict(os.environ, CLAUDE_CONFIG_DIR=cfg, CLAUDE_GUARD_ROOT_PID=str(os.getpid()))
                env.pop("PYTHONPATH", None)
                env.pop("CLAUDE_CODE_SESSION_ID", None)
                payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": work})
                r = run_capped([sys.executable, guard], input_text=payload, env=env, timeout=120)
                self.assertEqual(r.returncode, 0, r.stderr)
                out = json.loads(r.stdout)["hookSpecificOutput"]
                self.assertEqual(out["permissionDecision"], "deny", r.stdout)
                self.assertIn("machine-wide-kill", out["permissionDecisionReason"])


class SweepReceivesTheRemainingBudgetNotAFixedNumber(unittest.TestCase):
    """Arm: HookSpendsWhatRemains. `remaining_sweep_timeout_seconds` is the exact function
    `handle` calls to compute the `timeout=` it hands `subprocess.run` -- proving facts about
    IT proves facts about the value the hook actually passes, with no sleep involved (CLAUDE.md,
    "never write a waiter loop")."""

    def setUp(self):
        import session_end_sweep
        self.mod = session_end_sweep

    def test_plenty_of_budget_left_gets_the_fixed_cap(self):
        # elapsed=1s of a 55s ceiling, 3s margin reserved -> 51s left, capped at the fixed 25s.
        self.assertEqual(
            self.mod.remaining_sweep_timeout_seconds(1.0), self.mod.SWEEP_TIMEOUT_SECONDS
        )

    def test_much_of_the_budget_already_spent_shrinks_the_timeout_to_match(self):
        """The hook starts with much of its budget already spent (45s of a 55s ceiling): the
        timeout the sweep receives must have shrunk to match what is actually left, not stayed
        pinned at the fixed SWEEP_TIMEOUT_SECONDS guess."""
        elapsed = 45.0
        got = self.mod.remaining_sweep_timeout_seconds(elapsed)
        self.assertIsNotNone(got)
        self.assertLess(got, self.mod.SWEEP_TIMEOUT_SECONDS)
        self.assertAlmostEqual(
            got,
            self.mod.SESSION_END_CEILING_SECONDS - elapsed - self.mod.EXIT_MARGIN_SECONDS,
        )

    def test_too_little_budget_left_returns_none(self):
        """When nothing usable remains, the function must say so (None), not a near-zero or
        negative timeout that `subprocess.run` would reject or that could not run anything
        useful. Rows: the whole ceiling spent; an untrustworthy elapsed (negative, which must not
        add time back; nan and inf, which `except ValueError` never catches); an elapsed past the
        whole ceiling. Each row is one input to the same refusal."""
        ceiling = self.mod.SESSION_END_CEILING_SECONDS
        for elapsed in (ceiling, -1000.0, float("nan"), float("inf"), ceiling + 1000.0):
            with self.subTest(elapsed=elapsed):
                self.assertIsNone(self.mod.remaining_sweep_timeout_seconds(elapsed))


class HookSweepsNothingWhenTooLittleBudgetRemains(unittest.TestCase):
    """Arm: HookSkipsTheSweepWhenBudgetIsSpent. In-process: `elapsed_seconds` reaches `handle`
    only as an explicit argument, so this arm
    calls `handle` directly, the way a caller who genuinely has an elapsed reading would, with a
    real repository and a real reapable branch.

    `subprocess.run` is monkeypatched to RECORD each call, never to raise inside the callback:
    `handle` wraps that call in `except Exception`, on purpose, because the hook must fail open,
    so a raise inside the patched function is swallowed before it ever reaches this test runner
    (a test that signals failure through the code under test is at the mercy of that code).
    The recorded list is asserted on AFTER `handle` returns, the one point
    where no exception handler of `handle`'s own stands between the fact and the check."""

    def setUp(self):
        import session_end_sweep
        self.mod = session_end_sweep

    def test_too_little_budget_left_exits_cleanly_and_sweeps_nothing(self):
        repo = os.path.join(ROOT, "budget_too_little_repo")
        make_repo(repo)
        add_reapable_branch(repo, "reap-me-budget")
        require("reap-me-budget" in local_branches(repo), "fixture: reapable branch present")

        calls = []
        real_run = self.mod.subprocess.run

        def record_call(*args, **kwargs):
            # `session_end_sweep.subprocess` is the SAME module object `guard.py` imports too --
            # patching its `.run` patches it everywhere, including the real git calls
            # `guard.primary_checkout` still needs to make. Record, and short-circuit, only the one
            # shape `handle` uses for the sweep subprocess itself; let every other call (git)
            # through to the real `subprocess.run` untouched.
            argv = args[0] if args else kwargs.get("args")
            if isinstance(argv, list) and self.mod.SWEEP_PATH in argv:
                calls.append((args, kwargs))
                return subprocess.CompletedProcess(args=argv, returncode=0, stdout="", stderr="")
            return real_run(*args, **kwargs)

        self.mod.subprocess.run = record_call
        try:
            self.mod.handle(
                {"hook_event_name": "SessionEnd", "cwd": repo},
                elapsed_seconds=self.mod.SESSION_END_CEILING_SECONDS,
            )
        finally:
            self.mod.subprocess.run = real_run

        self.assertEqual(
            calls, [], "subprocess.run must never be called when too little budget remains"
        )
        self.assertIn("reap-me-budget", local_branches(repo),
                       "nothing was swept, so the reapable branch must still be there")


    def test_the_sweep_is_not_passed_the_attended_flag(self):
        repo = os.path.join(ROOT, "budget_strict_repo")
        make_repo(repo)
        calls = []
        real_run = self.mod.subprocess.run

        def record_call(*args, **kwargs):
            argv = args[0] if args else kwargs.get("args")
            if isinstance(argv, list) and self.mod.SWEEP_PATH in argv:
                calls.append(argv)
                return subprocess.CompletedProcess(args=argv, returncode=0, stdout="", stderr="")
            return real_run(*args, **kwargs)

        self.mod.subprocess.run = record_call
        try:
            self.mod.handle({"hook_event_name": "SessionEnd", "cwd": repo}, elapsed_seconds=0)
        finally:
            self.mod.subprocess.run = real_run
        self.assertEqual(len(calls), 1)
        self.assertIn("--confirm", calls[0])
        self.assertNotIn("--attended", calls[0])  # strict is the default


def deadline_value(argv):
    """The number after `--deadline-seconds` (as two arguments or as `=N`), or None when absent."""
    for i, arg in enumerate(argv):
        if arg == "--deadline-seconds" and i + 1 < len(argv):
            return float(argv[i + 1])
        if arg.startswith("--deadline-seconds="):
            return float(arg.split("=", 1)[1])
    return None


class SweepIsToldItsTimeLeftAsADeadline(unittest.TestCase):
    """Arm: HookPassesItsTimeLeft. The SessionEnd run is the only run with a deadline, so
    `handle` must hand the sweep its time left as an explicit `--deadline-seconds N`. N is
    `remaining_sweep_timeout_seconds(elapsed)`, the same number the hook uses as its own
    subprocess timeout. Recorded as in the arm above, never a real sweep."""

    def setUp(self):
        import session_end_sweep
        self.mod = session_end_sweep

    def sweep_argv_for(self, repo, elapsed):
        calls = []
        real_run = self.mod.subprocess.run

        def record_call(*args, **kwargs):
            argv = args[0] if args else kwargs.get("args")
            if isinstance(argv, list) and self.mod.SWEEP_PATH in argv:
                calls.append(argv)
                return subprocess.CompletedProcess(args=argv, returncode=0, stdout="", stderr="")
            return real_run(*args, **kwargs)

        self.mod.subprocess.run = record_call
        try:
            self.mod.handle({"hook_event_name": "SessionEnd", "cwd": repo}, elapsed_seconds=elapsed)
        finally:
            self.mod.subprocess.run = real_run
        return calls

    def test_the_sweep_is_passed_the_time_left_as_a_deadline_flag(self):
        repo = os.path.join(ROOT, "deadline_flag_repo")
        make_repo(repo)
        # elapsed 0 leaves the fixed 25 s cap; elapsed 45 leaves 55 - 45 - 3 = 7 s.
        for elapsed in (0.0, 45.0):
            with self.subTest(elapsed=elapsed):
                calls = self.sweep_argv_for(repo, elapsed)
                self.assertEqual(len(calls), 1, "the hook ran the sweep %d times" % len(calls))
                value = deadline_value(calls[0])
                self.assertIsNotNone(value, "the sweep got no --deadline-seconds: %r" % (calls[0],))
                self.assertAlmostEqual(value, self.mod.remaining_sweep_timeout_seconds(elapsed))


from sweep import FETCH_THROTTLE_SECONDS  # noqa: E402  the window, read from its one home


def make_repo_with_remote(where):
    """A repo with an `origin` it has pushed to, so `ls-remote` has a remote to list."""
    make_repo(where)
    remote = where + "_remote.git"
    require(run_vcs(ROOT, "init", "-q", "--bare", remote).returncode == 0, "bare %r" % remote)
    require(run_vcs(where, "remote", "add", "origin", remote).returncode == 0, "remote add")
    require(run_vcs(where, "push", "-q", "-u", "origin", "main").returncode == 0, "push")
    run_vcs(where, "remote", "set-head", "origin", "main")


class SessionEndFetchThrottle(unittest.TestCase):
    """The SessionEnd sweep fetches and ls-remotes a repository at most once per 10 minutes.

    The tests fix this CONTRACT for the builder: the last fetch of each repository is one file in
    `<config dir>/state/sweep-fetch/`, named by the repository's common git dir, holding the
    decimal Unix time (seconds, wall clock) of that fetch. The common git dir is the key because
    every worktree of one clone shares its remote. The tests never read a file name; they list
    the folder, and rewrite or delete what they find.

    The hook is driven through `session_end_sweep.handle`, as a SessionEnd does. Its sweep child
    runs in-process (`sweep.main` on the hook's own argv), and `_nowindow.run`, the one home of
    every child start, is wrapped to count each `git fetch` and `git ls-remote` before running the
    real git."""

    RECORD_DIR = ("state", "sweep-fetch")

    def setUp(self):
        import _nowindow
        import session_end_sweep
        import sweep
        self.hook, self.sweep, self.nowindow = session_end_sweep, sweep, _nowindow
        self.cfg = tempfile.mkdtemp(prefix="throttle_cfg_", dir=ROOT)
        self.calls = []  # (kind, realpath of the -C folder)
        self.real_run = _nowindow.run
        self.saved_cfg = os.environ.get("CLAUDE_CONFIG_DIR")
        os.environ["CLAUDE_CONFIG_DIR"] = self.cfg
        _nowindow.run = self._counting_run
        # A slow machine must not end a pass at "not judged: deadline" and fake a keep.
        self.saved_budget = sweep.JUDGE_BUDGET_SECONDS
        sweep.JUDGE_BUDGET_SECONDS = 600
        self.saved_timeout = session_end_sweep.SWEEP_TIMEOUT_SECONDS
        session_end_sweep.SWEEP_TIMEOUT_SECONDS = 600  # the budget is then the ceiling less its tails

    def tearDown(self):
        self.sweep.JUDGE_BUDGET_SECONDS = self.saved_budget
        self.hook.SWEEP_TIMEOUT_SECONDS = self.saved_timeout
        self.nowindow.run = self.real_run
        if self.saved_cfg is None:
            os.environ.pop("CLAUDE_CONFIG_DIR", None)
        else:
            os.environ["CLAUDE_CONFIG_DIR"] = self.saved_cfg

    def _counting_run(self, argv, *args, **kwargs):
        if isinstance(argv, list) and self.hook.SWEEP_PATH in argv:
            with contextlib.redirect_stdout(io.StringIO()):
                code = self.sweep.main(argv[2:])
            return subprocess.CompletedProcess(argv, code or 0, "", "")
        if isinstance(argv, list) and "-C" in argv:
            at = argv.index("-C")
            sub = argv[at + 2:at + 3]
            if sub and sub[0] in ("fetch", "ls-remote"):
                self.calls.append((sub[0], os.path.normcase(os.path.realpath(argv[at + 1]))))
        return self.real_run(argv, *args, **kwargs)

    def session_end(self, cwd):
        self.hook.handle({"hook_event_name": "SessionEnd", "cwd": cwd}, elapsed_seconds=0.0)

    def counts(self, repo):
        where = os.path.normcase(os.path.realpath(repo))
        mine = [kind for kind, path in self.calls if path == where]
        return mine.count("fetch"), mine.count("ls-remote")

    def records(self):
        folder = os.path.join(self.cfg, *self.RECORD_DIR)
        if not os.path.isdir(folder):
            return []
        return [os.path.join(folder, n) for n in sorted(os.listdir(folder))]

    def set_records(self, text):
        for path in self.records():
            write(path, text)

    def repo(self, name):
        where = os.path.join(ROOT, name)
        make_repo_with_remote(where)
        return where

    def test_first_session_end_fetches_and_records_the_time(self):
        repo = self.repo("throttle_first")
        before = time.time()
        self.session_end(repo)
        fetches, listings = self.counts(repo)
        self.assertEqual(fetches, 1, "the first SessionEnd must fetch once")
        self.assertGreaterEqual(listings, 1, "the first SessionEnd must run ls-remote (counter check)")
        self.assertEqual(len(self.records()), 1, "one record per repository in the state folder")
        with open(self.records()[0], encoding="utf-8") as handle:
            self.assertGreaterEqual(float(handle.read().strip()), before - 1)

    def test_second_session_end_within_10_minutes_runs_no_fetch_and_no_ls_remote(self):
        repo = self.repo("throttle_second")
        self.session_end(repo)
        first = self.counts(repo)
        self.session_end(repo)
        self.assertEqual(self.counts(repo), first,
                         "the second SessionEnd inside 10 minutes ran git fetch or ls-remote")

    def test_a_record_just_inside_the_window_still_throttles(self):
        repo = self.repo("throttle_inside")
        self.session_end(repo)
        first = self.counts(repo)
        self.set_records(repr(time.time() - (FETCH_THROTTLE_SECONDS - 60)))
        self.session_end(repo)
        self.assertEqual(self.counts(repo), first)

    def test_after_10_minutes_it_fetches_again(self):
        repo = self.repo("throttle_after")
        self.session_end(repo)
        self.set_records(repr(time.time() - (FETCH_THROTTLE_SECONDS + 60)))
        self.session_end(repo)
        fetches, listings = self.counts(repo)
        self.assertEqual(fetches, 2, "a record older than 10 minutes must allow a new fetch")
        self.assertGreaterEqual(listings, 2)

    def test_the_fetch_after_the_window_renews_the_record(self):
        repo = self.repo("throttle_renew")
        self.session_end(repo)
        self.set_records(repr(time.time() - (FETCH_THROTTLE_SECONDS + 60)))
        self.session_end(repo)
        self.session_end(repo)
        self.assertEqual(self.counts(repo)[0], 2, "the renewed record must throttle the third call")

    def test_two_repositories_each_get_their_own_fetch(self):
        repo_a, repo_b = self.repo("throttle_a"), self.repo("throttle_b")
        self.session_end(repo_a)
        self.session_end(repo_b)
        self.assertEqual(self.counts(repo_a)[0], 1)
        self.assertEqual(self.counts(repo_b)[0], 1, "repo B must not borrow repo A's record")
        self.assertEqual(len(self.records()), 2, "one record per repository")
        self.session_end(repo_a)
        self.session_end(repo_b)
        self.assertEqual(self.counts(repo_a)[0], 1)
        self.assertEqual(self.counts(repo_b)[0], 1)

    def test_a_missing_corrupt_or_future_record_means_fetch_now(self):
        # Each row damages the record after a first fetch; the next SessionEnd must fetch again.
        rows = (
            ("missing", None),
            ("empty", ""),
            ("garbage", "not a time"),
            ("nan", "nan"),
            ("inf", "inf"),
            ("future", repr(time.time() + 3600)),
        )
        for label, text in rows:
            with self.subTest(record=label):
                repo = self.repo("throttle_damaged_" + label)
                self.session_end(repo)
                self.assertEqual(len(self.records()), 1, "fixture: the first fetch left a record")
                if text is None:
                    for path in self.records():
                        os.remove(path)
                else:
                    self.set_records(text)
                before = self.counts(repo)[0]
                self.session_end(repo)
                self.assertEqual(self.counts(repo)[0], before + 1,
                                 "a %s record must fail toward fetching" % label)
                for path in self.records():
                    os.remove(path)

    def test_an_unwritable_record_folder_still_fetches_and_still_exits(self):
        repo = self.repo("throttle_unwritable")
        write(os.path.join(self.cfg, "state"), "a file where the state folder should be\n")
        self.session_end(repo)
        self.session_end(repo)
        self.assertEqual(self.counts(repo)[0], 2,
                         "with no record that can be kept, every SessionEnd fetches")

    def test_two_worktrees_of_one_clone_share_one_record(self):
        repo = self.repo("throttle_wt_primary")
        linked = os.path.join(ROOT, "throttle_wt_linked")
        require(run_vcs(repo, "worktree", "add", "-q", "-b", "wt-throttle", linked).returncode == 0,
                "worktree add")
        self.session_end(repo)
        self.session_end(linked)
        self.assertEqual(self.counts(repo)[0], 1, "the linked worktree's SessionEnd must not fetch again")
        self.assertEqual(len(self.records()), 1, "the clone's common git dir is the one key")

    def test_the_rest_of_the_sweep_still_runs_on_a_throttled_call(self):
        repo = self.repo("throttle_rest")
        self.session_end(repo)
        first = self.counts(repo)
        add_reapable_branch(repo, "reap-me-throttled")
        gone = os.path.join(ROOT, "throttle_rest_gone")
        require(run_vcs(repo, "worktree", "add", "-q", "-b", "gone-branch", gone).returncode == 0,
                "worktree add")
        shutil.rmtree(gone)  # a stale registration: `git worktree prune` is the sweep's own work
        self.session_end(repo)
        self.assertEqual(self.counts(repo), first, "fixture: the second call was throttled")
        self.assertNotIn("reap-me-throttled", local_branches(repo),
                         "a throttled call must still reap a merged branch")
        listed = run_vcs(repo, "worktree", "list", "--porcelain").stdout
        self.assertNotIn(os.path.basename(gone), listed,
                         "a throttled call must still prune a stale worktree registration")


    def pushed_branch(self, repo, name):
        """A branch with one commit no other branch holds, pushed to origin, `main` checked out."""
        require(run_vcs(repo, "checkout", "-q", "-b", name).returncode == 0, "checkout %s" % name)
        write(os.path.join(repo, name + ".txt"), name + chr(10))
        require(run_vcs(repo, "add", "-A").returncode == 0, "add %s" % name)
        require(run_vcs(repo, *IDENT, "commit", "-q", "-m", name).returncode == 0, "commit %s" % name)
        require(run_vcs(repo, "push", "-q", "origin", name).returncode == 0, "push %s" % name)
        require(run_vcs(repo, "checkout", "-q", "main").returncode == 0, "back to main")

    def test_a_throttled_call_reaps_no_branch_on_a_stale_on_remote_read(self):
        # The remote lost `gone-upstream` after our last fetch, so the local remote-tracking ref
        # is stale and the branch holds the only copy of its commit. A throttled run must keep
        # it, as a fetching run on the same state does. `still-pushed` is on the remote now, but
        # a throttled run cannot know that from a ref up to 10 minutes old: it is kept too.
        repo = self.repo("throttle_stale_remote")
        remote = repo + "_remote.git"
        self.session_end(repo)  # fetches, records the time
        self.pushed_branch(repo, "gone-upstream")
        self.pushed_branch(repo, "still-pushed")
        require(run_vcs(remote, "branch", "-D", "gone-upstream").returncode == 0, "delete on remote")
        first = self.counts(repo)
        self.session_end(repo)
        self.assertEqual(self.counts(repo), first, "fixture: the second call was throttled")
        self.assertIn("gone-upstream", local_branches(repo),
                      "a throttled call reaped a branch holding the only copy, on a stale ref")
        self.assertIn("still-pushed", local_branches(repo),
                      "a throttled call reaped a branch on the strength of an on-remote read")
        self.set_records(repr(time.time() - (FETCH_THROTTLE_SECONDS + 60)))
        self.session_end(repo)
        self.assertEqual(self.counts(repo)[0], first[0] + 1, "fixture: the third call fetched")
        self.assertIn("gone-upstream", local_branches(repo),
                      "a fetching run must keep the only copy once the stale ref is pruned")
        self.assertNotIn("still-pushed", local_branches(repo),
                         "a fetching run must still reap a branch the fresh remote holds")


class HookLoadsNoGuardModule(unittest.TestCase):
    """c16, janitor sweep fast on big repos. The hook starts at the end of every session, so its
    start-up cost is paid at every session's end. Neither importing it nor one whole run may load a
    module of the guard family. A fresh interpreter answers, because this file imported `guard`
    itself. The family comes from guard's own list, not a copy of it."""

    def modules_after(self, steps, env_extra=None):
        family = sorted({"guard", "guard_core", *guard._FAMILY_MODULES})
        code = ("import json, sys\nsys.path.insert(0, %r)\n%s\n"
                "print(json.dumps(sorted(set(sys.modules) & set(%r))))" % (HERE, steps, family))
        env = dict(os.environ)
        env.update(env_extra or {})
        done = run_capped([sys.executable, "-I", "-c", code], timeout=60, env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout.strip().splitlines()[-1])

    def test_importing_the_hook_loads_no_guard_module(self):
        self.assertEqual(self.modules_after("import session_end_sweep"), [],
                         "importing the hook loaded these guard modules")

    def test_one_whole_hook_run_loads_no_guard_module(self):
        repo = os.path.join(ROOT, "no_guard_repo")
        make_repo(repo)
        marker = os.path.join(ROOT, "no_guard_sweep_ran")
        stub = os.path.join(ROOT, "no_guard_sweep.py")
        write(stub, "open(%r, 'w').close()\n" % marker)
        steps = ("import session_end_sweep\nsession_end_sweep.handle("
                 "{'hook_event_name': 'SessionEnd', 'cwd': %r}, elapsed_seconds=0)" % repo)
        loaded = self.modules_after(steps, {"JANITOR_SWEEP_PATH": stub})
        self.assertTrue(os.path.isfile(marker), "the hook never ran the sweep, so this run proved "
                        "nothing: it must find the repository without the guard")
        self.assertEqual(loaded, [], "one hook run loaded these guard modules")


# THE SCRATCHPAD REAP (decision agent-end-reap-stops-what-a-finished-agent-left).
# At SessionEnd the hook also stops each process whose PPID is 1,
# whose environment holds exactly `CLAUDE_CODE_SESSION_ID=<payload session_id>`, and whose cwd sits
# in the payload's `scratchpad_dir`. Both paths are realpath'd: macOS shows /var as /private/var, so
# the payload names the /var form while the holder's cwd reads back as /private/var. Each holder is
# a python process whose shell exits first, so init adopts it. A holder writes a heartbeat file every
# 0.1 s, so a case reads its liveness with no pid, ps or kill, and it ends when its stop file appears.
TAG = "CLAUDE_CODE_SESSION_ID"
# The holder runs from a script file, so the shell passes the native Python only paths, never code.
HOLDER_SCRIPT = os.path.join(ROOT, "holder.py")
HOLDER = textwrap.dedent("""\
    import os, sys, time
    beat = sys.argv[1]
    end = time.time() + 300
    while time.time() < end and not os.path.exists(beat + ".stop"):
        with open(beat, "w", encoding="utf-8") as handle:
            handle.write(repr(time.time()))
        time.sleep(0.1)
""")
HOLDERS = []  # (pid, heartbeat path) of each holder this suite started, in start order


def read_beat(path):
    """The heartbeat text at `path`, or None when nothing wrote it yet."""
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return None


def assert_heartbeat_stops(case, path, what):
    """Passes once the heartbeat at `path` holds still for 1 s, within 10 s. It reads no pid and runs no
    ps or kill, so a stop that failed cannot read as a pass. A heartbeat that never started fails: then
    the case proved nothing."""
    last = read_beat(path)
    case.assertIsNotNone(last, "%s never wrote a heartbeat, so this case proved nothing" % what)
    deadline = time.time() + 10
    while True:
        time.sleep(1.0)
        now = read_beat(path)
        if now == last:
            return
        if time.time() > deadline:
            case.fail("%s still runs: its heartbeat still moves" % what)
        last = now


def kill_holder(pid):
    """Stop one holder this suite started, two ways, and need no ps. Its stop file ends its loop with no
    pid, so the stop works where the shell's pid space and this Python's differ (Windows). The `kill`
    runs in the shell's own pid space, because the pid is the shell's `$!`: os.kill from this Python
    would read it as a Windows pid and could stop an unrelated process. A `kill` that finds no process
    does nothing, so a holder that already ended is fine."""
    for held, beat in HOLDERS:
        if held == pid:
            write(beat + ".stop", "")
    run_capped(["sh", "-c", 'kill "$1" 2>/dev/null; true', "sh", str(pid)], timeout=10)


def spawn_orphan(cwd, env_entries=()):
    """A holder in `cwd` with `env_entries` (NAME=value) in its environment, the inherited tag
    removed first. Returns its pid, or None when it is not a PPID-1 orphan on this host. A holder
    that is not an orphan is stopped before this returns. Each holder started goes in HOLDERS."""
    env = {key: value for key, value in os.environ.items() if key != TAG}
    env.update(entry.split("=", 1) for entry in env_entries)
    os.makedirs(cwd, exist_ok=True)
    stem = os.path.join(ROOT, uuid.uuid4().hex)
    pidfile, beat = stem + ".pid", stem + ".beat"
    try:
        # The shell's stdio is files and the holder's is /dev/null, so no pipe reaches the holder. Its
        # pid comes back in a file.
        run_capped(["sh", "-c", '"$@" </dev/null >/dev/null 2>&1 & echo $! > "$0"', pidfile,
                    sys.executable, "-c", HOLDER, beat], cwd=cwd, env=env, timeout=20)
        with open(pidfile, encoding="utf-8") as handle:
            pid = int(handle.read().strip())
    except (OSError, ValueError):
        return None
    HOLDERS.append((pid, beat))  # before the ppid check, so the holder is stopped even when the case skips
    start_by = time.time() + 30  # each read below judges a holder that runs, not one still starting
    while read_beat(beat) is None and time.time() < start_by:
        time.sleep(0.05)
    try:
        parent = run_capped(["ps", "-o", "ppid=", "-p", str(pid)], timeout=5).stdout.strip()
    except OSError:
        parent = ""
    if parent == "1":
        return pid
    kill_holder(pid)  # this case skips, so its holder must not outlive it
    return None


def still_running(pid):
    """True while `pid` is alive and not a zombie. A reaped process has no `ps` line at all."""
    state = run_capped(["ps", "-o", "stat=", "-p", str(pid)], timeout=5).stdout.strip()
    return bool(state) and not state.startswith("Z")


def stop_holders():
    """At exit, stop each holder. Never raises, but a failed stop is printed, not hidden."""
    for pid, _beat in HOLDERS:
        try:
            kill_holder(pid)
        except Exception as exc:
            print("stop_holders: could not stop holder %d: %r" % (pid, exc), file=sys.stderr)


atexit.register(stop_holders)


class ScratchpadReap(unittest.TestCase):
    """The hook stops a PPID-1 process that holds this session's tag and sits in the scratchpad.
    Every case must exit 0. Each holder is skipped when this host gives no PPID-1 orphan."""

    def make_dir(self, name):
        path = os.path.join(ROOT, name)
        os.makedirs(path, exist_ok=True)
        return path

    def hold(self, cwd, env_entries=()):
        pid = spawn_orphan(cwd, env_entries)
        if pid is None:
            self.skipTest("needs a PPID-1 orphan from ps, which this host does not give")
        self.addCleanup(kill_holder, pid)  # the holder ends with its own case
        return pid

    def session_end(self, session, cwd, scratchpad):
        payload = {"hook_event_name": "SessionEnd", "cwd": cwd, "session_id": session}
        if scratchpad is not None:
            payload["scratchpad_dir"] = scratchpad
        return run_hook(payload, env_extra={"CLAUDE_CONFIG_DIR": self.make_dir("cfg_reap")})

    def assert_stopped(self, pid):
        deadline = time.time() + 5
        while still_running(pid) and time.time() < deadline:
            time.sleep(0.1)
        self.assertFalse(still_running(pid), "the hook left pid %d running" % pid)

    def test_tagged_orphan_in_scratchpad_is_stopped(self):
        repo = self.make_dir("reap_repo")
        make_repo(repo)
        scratch = self.make_dir("scratch_stop")
        pid = self.hold(scratch, [TAG + "=sess-reap-a"])
        result = self.session_end("sess-reap-a", repo, scratch)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_stopped(pid)

    def test_tagged_orphan_is_stopped_when_cwd_is_no_repository(self):
        """No repo sweep runs here, so the scratchpad reap must run on its own."""
        plain = self.make_dir("plain_cwd")
        scratch = self.make_dir("scratch_stop_plain")
        pid = self.hold(scratch, [TAG + "=sess-reap-b"])
        result = self.session_end("sess-reap-b", plain, scratch)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_stopped(pid)

    def test_another_sessions_tag_is_kept(self):
        scratch = self.make_dir("scratch_other")
        pid = self.hold(scratch, [TAG + "=sess-other-id"])
        result = self.session_end("sess-reap-c", self.make_dir("plain_c"), scratch)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(still_running(pid), "the hook stopped a process of another session")

    def test_no_tag_is_kept(self):
        scratch = self.make_dir("scratch_untagged")
        pid = self.hold(scratch)
        result = self.session_end("sess-reap-d", self.make_dir("plain_d"), scratch)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(still_running(pid), "the hook stopped an untagged process")

    def test_tagged_orphan_outside_the_scratchpad_is_kept(self):
        outside = self.make_dir("outside_scratch")
        pid = self.hold(outside, [TAG + "=sess-reap-e"])
        result = self.session_end("sess-reap-e", self.make_dir("plain_e"),
                                  self.make_dir("scratch_empty_e"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(still_running(pid), "the hook stopped a process outside the scratchpad")

    def test_payload_without_scratchpad_keeps_the_tagged_orphan(self):
        scratch = self.make_dir("scratch_no_field")
        pid = self.hold(scratch, [TAG + "=sess-reap-f"])
        result = self.session_end("sess-reap-f", self.make_dir("plain_f"), None)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(still_running(pid), "the hook stopped a process with no scratchpad named")


class SkippedCaseLeavesNoHolder(unittest.TestCase):
    """A holder whose case skips is stopped before spawn_orphan returns: when ps names another parent,
    and on a host without ps. Before, it ran until the suite exited, and on Windows the exit-time stop
    could not reach it, so it outlived the job."""

    def assert_skips_and_leaves_no_holder(self, name, ps):
        """The shared step: run spawn_orphan with each `ps` call answered by `ps(argv)`, then prove it
        gave the skip, started one holder, and stopped it. Only ps is replaced; sh and kill are real."""
        real = run_capped

        def fake(argv, timeout, **kwargs):
            if list(argv[:1]) == ["ps"]:
                return ps(argv)
            return real(argv, timeout, **kwargs)

        before = len(HOLDERS)
        with mock.patch.object(sys.modules[__name__], "run_capped", fake):
            result = spawn_orphan(os.path.join(ROOT, "scratch_" + name), [TAG + "=" + name])
        started = HOLDERS[before:]
        for pid, _beat in started:
            self.addCleanup(kill_holder, pid)
        self.assertEqual(len(started), 1, "spawn_orphan started no holder, so this case proved nothing")
        self.assertIsNone(result, "a case that skips must get None, not a pid")
        pid, beat = started[0]
        assert_heartbeat_stops(self, beat, "the holder of a skipped case (pid %d)" % pid)

    def test_the_holder_is_stopped_when_the_ppid_check_fails(self):
        self.assert_skips_and_leaves_no_holder(
            "sess-not-an-orphan", lambda argv: subprocess.CompletedProcess(argv, 0, "4242\n", ""))

    def test_a_host_without_ps_skips_and_leaves_no_holder(self):
        """On a host without ps, Popen raises FileNotFoundError, as CreateProcess does on Windows."""
        def no_ps(argv):
            raise FileNotFoundError(2, "No such file or directory", argv[0])
        self.assert_skips_and_leaves_no_holder("sess-no-ps", no_ps)


class SweepGetsNoPipes(unittest.TestCase):
    """handle() hands the sweep no pipe: stdin, stdout and stderr are DEVNULL, and nothing is captured. A
    pipe a grandchild inherits is what held the session open on Windows after a timeout kill."""

    def setUp(self):
        import session_end_sweep
        self.mod = session_end_sweep

    def test_the_sweep_gets_devnull_streams_and_no_capture(self):
        repo = os.path.join(ROOT, "no_pipes_repo")
        make_repo(repo)
        calls = []
        real_run = self.mod.subprocess.run

        def record_call(*args, **kwargs):
            argv = args[0] if args else kwargs.get("args")
            if isinstance(argv, list) and self.mod.SWEEP_PATH in argv:
                calls.append(kwargs)
                return subprocess.CompletedProcess(args=argv, returncode=0, stdout="", stderr="")
            return real_run(*args, **kwargs)

        self.mod.subprocess.run = record_call
        try:
            self.mod.handle({"hook_event_name": "SessionEnd", "cwd": repo}, elapsed_seconds=0)
        finally:
            self.mod.subprocess.run = real_run
        self.assertEqual(len(calls), 1, "handle must start the sweep once")
        for name in ("stdin", "stdout", "stderr"):
            self.assertEqual(calls[0].get(name), subprocess.DEVNULL,
                             "the sweep's %s must be DEVNULL, not a pipe" % name)
        self.assertFalse(calls[0].get("capture_output"), "the sweep's output must not be captured")


def kill_sweep(pid_path):
    """Stop the fake sweep named in `pid_path`, by the pid it wrote there. A missing or stale file is no sweep."""
    try:
        with open(pid_path, encoding="utf-8") as handle:
            pid = int(handle.read().strip())
        os.kill(pid, signal.SIGTERM)
    except (OSError, ValueError):
        pass


class HookRunIsCapped(unittest.TestCase):
    """A hook run past its cap fails by name. Before, the call raised TimeoutExpired, which reads as a
    crash of the harness. On Windows the same call also waited on the pipes after the kill. The cap
    starts at the sweep's first heartbeat, so a slow host cannot spend it before the hook reaches the
    sweep."""

    def test_a_hook_run_past_its_cap_is_a_named_fail(self):
        repo = os.path.join(ROOT, "capped_repo")
        make_repo(repo)
        # The sweep writes its pid and a heartbeat, and does not watch its parent: on Windows the dead
        # hook's pid stays in getppid(), so a parent check would run the full 600 s.
        pid_path = os.path.join(ROOT, "capped_sweep.pid")
        patient = os.path.join(ROOT, "fake_sweep_outlives_its_hook.py")
        write(patient, textwrap.dedent("""\
            import os
            import time
            with open(os.environ["FAKE_SWEEP_PID"], "w", encoding="utf-8") as handle:
                handle.write(str(os.getpid()))
            end = time.time() + 600
            while time.time() < end:
                with open(os.environ["FAKE_SWEEP_PID"] + ".beat", "w", encoding="utf-8") as handle:
                    handle.write(repr(time.time()))
                time.sleep(0.1)
        """))
        beat = pid_path + ".beat"
        self.addCleanup(assert_heartbeat_stops, self, beat, "the sweep the hook started")  # runs last
        self.addCleanup(kill_sweep, pid_path)  # runs first: the sweep this case started, by its own pid
        with self.assertRaises(AssertionError) as caught:
            run_hook({"hook_event_name": "SessionEnd", "cwd": repo},
                     env_extra={"JANITOR_SWEEP_PATH": patient, "JANITOR_SWEEP_TIMEOUT": "60",
                                "FAKE_SWEEP_PID": pid_path}, timeout=2, start_after=beat)
        self.assertIn("hang guard", str(caught.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
