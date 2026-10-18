#!/usr/bin/env python3
"""At SessionEnd, runs janitor/sweep.py on the ending session's repository, to remove finished branches and worktrees. Always exits 0, so it never delays the end of the session.

Reads one JSON object on stdin (the SessionEnd hook payload: `cwd` is the ending session's own
working directory). Resolves the git repository that `cwd` sits in -- the PRIMARY checkout, not
a linked worktree's own path, see `guard.primary_checkout`'s own docstring for why that
distinction matters -- and runs `janitor/sweep.py <that root> --confirm` there. Nothing else is
swept. Always exits 0.

FAILS OPEN, ON PURPOSE. This script's own job is to let the session end; it is never the thing
that decides whether a branch or a worktree is reapable. Every way this script itself can go
wrong -- unreadable stdin, a payload that is not the SessionEnd shape, a `cwd` that names no
directory or no repository, a missing janitor/sweep.py, a sweep call that raises or hangs -- is
caught here and answered by doing nothing and exiting 0. A hook that can refuse the end of a
session is worse than the leak it guards against.

FAILS OPEN IS NOT FAILS PERMISSIVE ON THE REAP DECISION ITSELF. This script never lowers the
bar `janitor/sweep.py` and `hooks/guard.py` already hold for what counts as reapable -- an
unreadable branch, worktree, or opt-out file still means KEEP, inside the sweep, exactly as it
does when the sweep runs by hand. "Fails open" here is about THIS SCRIPT's own exit code, never
about the sweep's keep-or-reap answer. The two directions are opposite on purpose: a hook that
cannot finish must let the session go; a sweep that cannot read its subject must leave it alone.

The sweep itself decides `--confirm`, because the owner chose an automatic sweep with a
per-repository opt-out (`.claude/janitor.json`). This hook adds no new judgment call: it locates
the one repository the ending session touched, and calls the same program a person would call
by hand.
"""
import json
import math
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO_ROOT, "hooks"))
import guard  # noqa: E402

# Both overridable by environment, so a test fixture can point at a fake sweep or a short fuse
# without editing this file.
SWEEP_PATH = os.environ.get("JANITOR_SWEEP_PATH") or os.path.join(HERE, "sweep.py")
try:
    SWEEP_TIMEOUT_SECONDS = float(os.environ.get("JANITOR_SWEEP_TIMEOUT") or 25)
except (TypeError, ValueError):
    SWEEP_TIMEOUT_SECONDS = 25.0

# NO environment seam for elapsed time, on purpose. A hook that deletes branches unattended must
# never let an inherited shell variable change its own timing: `elapsed_seconds` reaches `handle`
# only as an explicit argument (see `handle` and `main` below), which a test can pass directly by
# calling the function in-process. There is no name here for an environment to carry.


# `hooks/guard.py._git`'s own per-call subprocess timeout, and settings.json's own SessionEnd
# entry timeout for THIS hook, end to end. Plain constants, not a read of either real file:
# THEY MUST STAY IN SYNC BY HAND with `guard._git`'s `timeout=` and with settings.json's
# `hooks.SessionEnd[].hooks[].timeout` for `session_end_sweep.py`.
# WHAT PINS EACH NUMBER:
#   GUARD_GIT_CALL_TIMEOUT_SECONDS is pinned live. HookBudgetFitsUnderItsHostCeiling reads
#   `guard._git`'s own source and goes red when the two drift apart.
#   SESSION_END_CEILING_SECONDS is pinned while settings.json carries the SessionEnd entry
#   (timeout 55): HookBudgetFitsUnderItsHostCeiling reads that timeout. The hook is armed. If the
#   entry is ever absent, those arms skip and this number rests on the hand-sync comment alone.
#   See decisions/session-end-sweep-is-disarmed-until-liveness-is-proven.md.
GUARD_GIT_CALL_TIMEOUT_SECONDS = 10.0
SESSION_END_CEILING_SECONDS = 55.0


# THE BUDGET ARITHMETIC (checked against the real settings.json by
# test_session_end_sweep.py's HookBudgetFitsUnderItsHostCeiling arm):
#
#   guard.primary_checkout makes exactly two guard._git calls (--show-toplevel, then
#   --git-common-dir), each bounded by guard._git's own subprocess timeout. Worst case, both
#   hang out their full timeout before guard._git gives up and returns None:
RESOLVE_ROOT_GIT_CALLS = 2
RESOLVE_ROOT_WORST_CASE_SECONDS = GUARD_GIT_CALL_TIMEOUT_SECONDS * RESOLVE_ROOT_GIT_CALLS
#
#   Then, worst case, the sweep subprocess itself runs the full SWEEP_TIMEOUT_SECONDS before
#   this hook's own timeout cuts it off:
HOOK_WORST_CASE_SECONDS = RESOLVE_ROOT_WORST_CASE_SECONDS + SWEEP_TIMEOUT_SECONDS
#
#   With the defaults above (10 * 2 + 25), that is 45 seconds. settings.json's SessionEnd entry
# for this hook must set a timeout STRICTLY GREATER than HOOK_WORST_CASE_SECONDS, with margin for
# process-start and interpreter-import overhead neither number above counts; it sets 55, a
# 10-second margin over the 45-second worst case. Changing SWEEP_TIMEOUT_SECONDS (or a future
# change to guard._git's own timeout) without also widening that settings.json entry is exactly
# the drift HookBudgetFitsUnderItsHostCeiling exists to catch.

# THE LOWER EDGE. The settings.json SessionEnd timeout must leave at least this much over
# HOOK_WORST_CASE_SECONDS, for process-start and import overhead. A test reads the constant.
SESSION_END_TIMEOUT_MIN_HEADROOM_SECONDS = 5.0


# SPENDING WHAT REMAINS, NOT WHAT WAS GUESSED. HOOK_WORST_CASE_SECONDS above is a STATIC bound,
# checked once against settings.json by HookBudgetFitsUnderItsHostCeiling; it says nothing about
# how long guard.primary_checkout actually took on THIS run. Most runs resolve the repository
# root in milliseconds, not GUARD_GIT_CALL_TIMEOUT_SECONDS * RESOLVE_ROOT_GIT_CALLS -- handing
# the sweep a fixed SWEEP_TIMEOUT_SECONDS regardless spends a number that was guessed at design
# time, not the time this run actually has left. SESSION_END_CEILING_SECONDS (above) is the real
# ceiling this run is held to; EXIT_MARGIN_SECONDS is reserved, after the sweep subprocess
# returns, for this hook's own interpreter teardown; MIN_USEFUL_SWEEP_SECONDS is the floor below
# which a sweep is more likely to be killed mid-write than to finish, so the hook skips it
# instead of starting one the harness will cut off partway (module docstring above: "a sweep the
# harness kills part way is worse than a sweep that never started").
EXIT_MARGIN_SECONDS = 3.0
MIN_USEFUL_SWEEP_SECONDS = 2.0


def remaining_sweep_timeout_seconds(elapsed_seconds):
    """How much of the sweep's own subprocess.run timeout to give it, given `elapsed_seconds`
    already spent since this hook started. Never more than SWEEP_TIMEOUT_SECONDS -- that cap is
    what HOOK_WORST_CASE_SECONDS and the ceiling arms above assume, so this function must never
    hand the sweep more than the static worst-case arithmetic already accounts for. Returns None
    when what is left, after EXIT_MARGIN_SECONDS, does not clear MIN_USEFUL_SWEEP_SECONDS: the
    caller must not run the sweep at all in that case.

    AN ELAPSED READING THIS FUNCTION CANNOT TRUST IS ALSO "TOO LITTLE TIME LEFT" (PR #84 review).
    Negative, non-finite (`nan`/`inf`), or otherwise non-numeric `elapsed_seconds` is refused the
    same way an elapsed_seconds so large it eats the whole ceiling is refused: this function
    hands out real time only when it can actually measure how much is left, never when handed a
    number it cannot make sense of. A caller that cannot supply a trustworthy elapsed reading
    gets the same answer as a caller that ran out of budget: None, sweep nothing."""
    if (
        not isinstance(elapsed_seconds, (int, float))
        or isinstance(elapsed_seconds, bool)
        or not math.isfinite(elapsed_seconds)
        or elapsed_seconds < 0
    ):
        return None
    remaining = SESSION_END_CEILING_SECONDS - elapsed_seconds - EXIT_MARGIN_SECONDS
    sweep_timeout = min(SWEEP_TIMEOUT_SECONDS, remaining)
    if sweep_timeout < MIN_USEFUL_SWEEP_SECONDS:
        return None
    return sweep_timeout


def handle(hook, start=None, elapsed_seconds=None) -> None:
    """Run the sweep for the repository `hook` names, or do nothing. Never raises.

    `start` is the `time.monotonic()` reading this hook's own process began at; `main` passes
    the real one, taken before stdin is even read, so the elapsed time computed below counts the
    whole run, not just the part inside this function. A caller that omits it (direct unit-
    testing of this function, for example) gets one taken right here instead.

    `elapsed_seconds`, when given, is used INSTEAD of measuring `start`: an explicit argument a
    test can pass by calling this function in-process, never an environment variable a hook that
    is live on this machine would otherwise have to trust (PR #84 review: a test seam that
    production reads from the environment is a control surface, not a seam). `main` never passes
    it; only tests do."""
    if start is None:
        start = time.monotonic()
    if not isinstance(hook, dict):
        return
    if hook.get("hook_event_name") != "SessionEnd":
        return
    cwd = hook.get("cwd")
    if not isinstance(cwd, str) or not cwd or not os.path.isdir(cwd):
        return

    # `guard.primary_checkout` resolves `cwd` to the PRIMARY checkout, never a linked worktree's
    # own path. Sweeping a linked worktree path directly would be wrong two ways at once: the
    # linked worktree's `.claude/janitor.json` may not be the one the repository's owner set,
    # and `janitor/sweep.py`'s own "never touch the primary checkout" exclusion compares against
    # the root IT was given -- pass it a worktree path and the primary checkout stops being
    # excluded, and could itself be evaluated as a removable worktree entry. See
    # `janitor/sweep.py`'s discovery docstring for the same reasoning applied to `--discover`.
    try:
        root = guard.primary_checkout(cwd)
    except Exception:
        root = None
    if not root:
        return  # unreadable, or cwd names no repository at all: nothing to sweep

    if not os.path.isfile(SWEEP_PATH):
        return  # the sweep this checkout ships is missing; nothing runs, nothing is denied

    if elapsed_seconds is None:
        elapsed_seconds = time.monotonic() - start
    sweep_timeout = remaining_sweep_timeout_seconds(elapsed_seconds)
    if sweep_timeout is None:
        # too little of this hook's own budget is left: a sweep the harness kills part way
        # through is worse than a sweep that never started (module docstring above)
        return

    try:
        subprocess.run(
            [sys.executable, SWEEP_PATH, root, "--confirm",
             "--deadline-seconds", str(sweep_timeout)],  # the only run with a deadline
            capture_output=True, text=True, timeout=sweep_timeout,
        )
    except Exception:
        # Covers subprocess.TimeoutExpired (the sweep hung) and every other way the call could
        # fail (the interpreter vanished, the sweep raised past its own top level, ...). A
        # nonzero return code from a sweep that ran and finished is ALSO ignored here on
        # purpose: this hook reports nothing back to the transcript either way, the same as
        # every other silent Stop/SessionStart hook in settings.json.
        pass


def main() -> None:
    start = time.monotonic()
    try:
        raw = sys.stdin.read()
    except Exception:
        return
    try:
        hook = json.loads(raw)
    except Exception:
        return
    try:
        handle(hook, start)
    except Exception:
        return


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
