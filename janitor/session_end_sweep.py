#!/usr/bin/env python3
"""Claude Code hook: SessionEnd trigger for janitor/sweep.py.

Reads one JSON object on stdin (the SessionEnd hook payload: `cwd` is the ending session's own
working directory). Resolves the git repository that `cwd` sits in -- the PRIMARY checkout, not
a linked worktree's own path, see `resolve_repo_root` below for why that distinction matters --
and runs `janitor/sweep.py <that root> --confirm` there. Nothing else is swept. Always exits 0.

FAILS OPEN, ON PURPOSE (plan: "Two triggers", CLAUDE.md rule:verification-recovery-not-gated-on-
own-state's sibling posture for a hook rather than a recovery control). This script's own job is
to let the session end; it is never the thing that decides whether a branch or a worktree is
reapable. Every way this script itself can go wrong -- unreadable stdin, a payload that is not
the SessionEnd shape, a `cwd` that names no directory or no repository, a missing
janitor/sweep.py, a sweep call that raises or hangs -- is caught here and answered by doing
nothing and exiting 0. A hook that can refuse the end of a session is worse than the leak it
guards against (plan, "the hook always fails open").

FAILS OPEN IS NOT FAILS PERMISSIVE ON THE REAP DECISION ITSELF. This script never lowers the
bar `janitor/sweep.py` and `hooks/guard.py` already hold for what counts as reapable -- an
unreadable branch, worktree, or opt-out file still means KEEP, inside the sweep, exactly as it
does when the sweep runs by hand. "Fails open" here is about THIS SCRIPT's own exit code, never
about the sweep's keep-or-reap answer. The two directions are opposite on purpose: a hook that
cannot finish must let the session go; a sweep that cannot read its subject must leave it alone.

The sweep itself decides `--confirm`, because the owner chose an automatic sweep with a
per-repository opt-out (`.claude/janitor.json`, plan: "the sweep is automatic, and a repository
opts out"). This hook adds no new judgment call: it locates the one repository the ending
session touched, and calls the same program a person would call by hand.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO_ROOT, "hooks"))
import guard  # noqa: E402

# Both overridable by environment, so a test fixture can point at a fake sweep or a short fuse
# without editing this file. Unset, they are this checkout's own sweep and a timeout comfortably
# under the 30s the SessionEnd entry in settings.json gives this hook end to end.
SWEEP_PATH = os.environ.get("JANITOR_SWEEP_PATH") or os.path.join(HERE, "sweep.py")
try:
    SWEEP_TIMEOUT_SECONDS = float(os.environ.get("JANITOR_SWEEP_TIMEOUT") or 25)
except (TypeError, ValueError):
    SWEEP_TIMEOUT_SECONDS = 25.0


def resolve_repo_root(cwd: str):
    """Return the PRIMARY checkout that `cwd` belongs to, or None when it could not be read.

    `git rev-parse --show-toplevel` answers "cwd" itself when `cwd` sits inside an ordinary
    checkout, but it answers the WORKTREE's own path when `cwd` sits inside a linked worktree.
    Sweeping a linked worktree path directly would be wrong two ways at once: the linked
    worktree's `.claude/janitor.json` may not be the one the repository's owner set, and
    `janitor/sweep.py`'s own "never touch the primary checkout" exclusion compares against
    the root IT was given -- pass it a worktree path and the primary checkout stops being
    excluded, and could itself be evaluated as a removable worktree entry. See
    `janitor/sweep.py`'s discovery docstring for the same reasoning applied to `--discover`.

    `git rev-parse --git-common-dir` names the ONE `.git` directory every worktree of a clone
    shares; its parent is always the primary checkout, ordinary checkout or linked worktree
    alike, so resolving through it answers the same repository root either way.
    """
    top = guard._git(cwd, "rev-parse", "--show-toplevel")
    if top is None or top.returncode != 0:
        return None
    toplevel = top.stdout.strip()
    if not toplevel:
        return None
    common = guard._git(toplevel, "rev-parse", "--git-common-dir")
    if common is None or common.returncode != 0:
        return None
    common_dir = common.stdout.strip()
    if not common_dir:
        return None
    try:
        common_abs = os.path.realpath(os.path.join(toplevel, common_dir))
        primary = os.path.dirname(common_abs)
    except Exception:
        return None
    if not primary or not os.path.isdir(primary):
        return None
    return primary


def handle(hook) -> None:
    """Run the sweep for the repository `hook` names, or do nothing. Never raises."""
    if not isinstance(hook, dict):
        return
    if hook.get("hook_event_name") != "SessionEnd":
        return
    cwd = hook.get("cwd")
    if not isinstance(cwd, str) or not cwd or not os.path.isdir(cwd):
        return

    try:
        root = resolve_repo_root(cwd)
    except Exception:
        root = None
    if not root:
        return  # unreadable, or cwd names no repository at all: nothing to sweep

    if not os.path.isfile(SWEEP_PATH):
        return  # the sweep this checkout ships is missing; nothing runs, nothing is denied

    try:
        subprocess.run(
            [sys.executable, SWEEP_PATH, root, "--confirm"],
            capture_output=True, text=True, timeout=SWEEP_TIMEOUT_SECONDS,
        )
    except Exception:
        # Covers subprocess.TimeoutExpired (the sweep hung) and every other way the call could
        # fail (the interpreter vanished, the sweep raised past its own top level, ...). A
        # nonzero return code from a sweep that ran and finished is ALSO ignored here on
        # purpose: this hook reports nothing back to the transcript either way, the same as
        # every other silent Stop/SessionStart hook in settings.json.
        pass


def main() -> None:
    try:
        raw = sys.stdin.read()
    except Exception:
        return
    try:
        hook = json.loads(raw)
    except Exception:
        return
    try:
        handle(hook)
    except Exception:
        return


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
