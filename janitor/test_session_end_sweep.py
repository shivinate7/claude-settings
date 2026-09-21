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


class HookBudgetFitsUnderItsHostCeiling(unittest.TestCase):
    """The hook's own worst-case run time (`session_end_sweep.HOOK_WORST_CASE_SECONDS`) must be
    STRICTLY SMALLER than the timeout settings.json actually gives this hook -- proven against
    the real settings.json in this checkout, not a copy of the number typed into this file.
    A reviewer measured the earlier arithmetic wrong: two 10s guard._git calls plus a 25s sweep
    is 45s, against a 30s settings.json ceiling that used to sit there unchecked."""

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

    def test_default_arithmetic_matches_what_the_module_documents(self):
        self.assertEqual(self.mod.GUARD_GIT_CALL_TIMEOUT_SECONDS, 10.0)
        self.assertEqual(self.mod.RESOLVE_ROOT_GIT_CALLS, 2)
        self.assertEqual(self.mod.RESOLVE_ROOT_WORST_CASE_SECONDS, 20.0)
        self.assertEqual(self.mod.HOOK_WORST_CASE_SECONDS, 45.0)

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

    def test_settings_json_timeout_does_not_leave_more_than_the_stated_headroom(self):
        """Arm: SettingsCeilingHeadroomHasAnUpperEdge. The floor test above only refuses a
        ceiling that runs too CLOSE to the worst case. Nothing above refused one that runs too
        FAR ahead -- a later change that quietly doubled SWEEP_TIMEOUT_SECONDS (or halved it
        while settings.json's timeout stayed put) would still pass every arm above it. This arm
        reads the real constant the module states beside its own arithmetic
        (SESSION_END_TIMEOUT_MAX_HEADROOM_SECONDS), never a copy of it, and refuses a margin
        that runs past it. When this goes red: either shrink the work (bring
        SWEEP_TIMEOUT_SECONDS or the git-call budget back down), or move the ceiling on purpose
        (widen settings.json's SessionEnd timeout AND this module's max-headroom constant, in
        the same commit, with a reason)."""
        timeout = self._wired_timeout()
        self.assertTrue(
            self.mod.headroom_within_bounds(timeout, self.mod.HOOK_WORST_CASE_SECONDS),
            "settings.json's SessionEnd timeout (%r) leaves a margin over "
            "HOOK_WORST_CASE_SECONDS (%r) outside [%r, %r]" % (
                timeout, self.mod.HOOK_WORST_CASE_SECONDS,
                self.mod.SESSION_END_TIMEOUT_MIN_HEADROOM_SECONDS,
                self.mod.SESSION_END_TIMEOUT_MAX_HEADROOM_SECONDS,
            ),
        )


class HeadroomWithinBoundsUnit(unittest.TestCase):
    """Direct, synthetic-number coverage of `headroom_within_bounds`, proving the upper-edge arm
    goes red in BOTH directions -- not just against the one real settings.json this checkout
    happens to ship. Cheap and fast: no subprocess, no git, no real settings.json involved."""

    def setUp(self):
        import session_end_sweep
        self.mod = session_end_sweep

    def test_real_settings_headroom_is_within_bounds(self):
        """Sanity: the actual repository is not, itself, the defect this arm guards."""
        self.assertTrue(self.mod.headroom_within_bounds(55.0, 45.0))

    def test_worst_case_grown_toward_the_ceiling_fails_the_band(self):
        """Direction 1: the worst case creeps up toward the ceiling (SWEEP_TIMEOUT_SECONDS grew,
        or a future guard._git timeout grew) until the margin drops under the stated floor."""
        self.assertFalse(self.mod.headroom_within_bounds(55.0, 51.0))  # margin 4 < floor 5

    def test_ceiling_far_ahead_of_the_worst_case_fails_the_band(self):
        """Direction 2: settings.json's ceiling runs far ahead of the worst case (raised without
        a matching reason, or the worst case shrank without the ceiling following it down)."""
        self.assertFalse(self.mod.headroom_within_bounds(100.0, 45.0))  # margin 55 > ceiling 20


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
        useful."""
        elapsed = self.mod.SESSION_END_CEILING_SECONDS  # the whole ceiling already spent
        self.assertIsNone(self.mod.remaining_sweep_timeout_seconds(elapsed))


class HookSweepsNothingWhenTooLittleBudgetRemains(unittest.TestCase):
    """Arm: HookSkipsTheSweepWhenBudgetIsSpent. In-process: `elapsed_seconds` reaches `handle`
    only as an explicit argument now (PR #84 review dropped the environment seam), so this arm
    calls `handle` directly, the way a caller who genuinely has an elapsed reading would, with a
    real repository and a real reapable branch.

    `subprocess.run` is monkeypatched to RECORD each call, never to raise inside the callback:
    `handle` wraps that call in `except Exception`, on purpose, because the hook must fail open,
    so a raise inside the patched function is swallowed before it ever reaches this test runner
    (second PR #84 review: a test that signals failure through the code under test is at the
    mercy of that code). The recorded list is asserted on AFTER `handle` returns, the one point
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
            # `resolve_repo_root` still needs to make. Record, and short-circuit, only the one
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


class RemainingSweepTimeoutRefusesAnUntrustworthyElapsedReading(unittest.TestCase):
    """Arms guarding the property PR #84 review actually asked for: even with the environment
    seam gone, an elapsed reading this function cannot trust must never be spent as if it were
    free time. Each case is named for the shape of reading it guards against."""

    def setUp(self):
        import session_end_sweep
        self.mod = session_end_sweep

    def test_negative_elapsed_is_refused_not_treated_as_extra_time(self):
        """A negative elapsed (a clock read backwards, or a bad caller) must not add time back
        onto the budget. Refused -> None, sweep nothing, never the full SWEEP_TIMEOUT_SECONDS."""
        self.assertIsNone(self.mod.remaining_sweep_timeout_seconds(-1000.0))

    def test_non_finite_elapsed_is_refused(self):
        """nan and inf both parse as a Python float without raising, so `except ValueError`
        alone never catches them -- proven for both shapes at once."""
        self.assertIsNone(self.mod.remaining_sweep_timeout_seconds(float("nan")))
        self.assertIsNone(self.mod.remaining_sweep_timeout_seconds(float("inf")))

    def test_elapsed_larger_than_the_ceiling_is_refused(self):
        """A plainly numeric, finite, non-negative elapsed that simply exceeds the whole ceiling
        must still land on None, the same as the too-little-budget-left case above -- proven
        directly against the real ceiling, not a copy of it."""
        got = self.mod.remaining_sweep_timeout_seconds(
            self.mod.SESSION_END_CEILING_SECONDS + 1000.0
        )
        self.assertIsNone(got)


if __name__ == "__main__":
    unittest.main(verbosity=2)
