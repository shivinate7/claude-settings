#!/usr/bin/env python3
"""Generates the daily launchd agent that sweeps every repository.

Writes a `.plist` into `~/Library/LaunchAgents`. NOBODY COMMITS THAT FILE: it names an absolute
path on one machine, and this repository never holds a tracked absolute path (plan, "the
installer writes the launchd plist into ~/Library. Nobody commits it").

REFUSES TO RUN FROM A LINKED WORKTREE. A committed plist would already be wrong -- it would
name one machine -- but a plist GENERATED from a linked worktree is wrong a second way: its
`ProgramArguments` would point `python3 .../janitor/sweep.py` at a worktree, and a worktree is
removable (by this very sweep, among other things). The day it is removed, launchd is left
retrying a directory that no longer exists, silently, with no session there to notice. So this
installer reads its own checkout's worktree-ness with `hooks/guard.py`'s own tested primitive
(`is_worktree`, the same read `janitor/sweep.py`'s discovery uses to skip worktrees) and refuses
outright rather than generate a plist that would work today and rot on its own. An UNREADABLE
worktree-ness answer refuses too, the same conservative direction the sweep itself takes on a
subject it cannot read (see `session_end_sweep.py`'s module docstring for why that direction is
never weakened): installing wrong is exactly the kind of mistake that direction exists to avoid,
and "install from the main checkout" costs nothing to ask for twice.

The LABEL is a fixed, generic string. It never names a worktree, a branch, or any path: launchd
identifies the agent by this label alone, and a label built from a path would make the same
mistake the refusal above exists to prevent.

This installer only WRITES the plist and prints how to load it. It never calls `launchctl`
itself: loading a machine-wide daily job is a separate, later act, on the owner's own word.

THE GENERATED PLIST CARRIES NO `--discover` ROOT. `janitor/sweep.py`, called with no ROOT and no
`--discover`, already resolves its own roots at run time: `janitor.roots` from settings.json,
falling back to `default_discover_roots()`. An installer-side root would be a second, stale copy
of that same list (this file once hard-coded `~/Developer`, a path that does not exist on every
machine and is not where this repository's own clones live). Reading roots at run time means the
loaded agent never needs re-installing when `janitor.roots` changes. See
`janitor/install_schtasks.py`, which carries the identical fix for the same reason.

Usage:
    python3 janitor/install_launchd.py                 # write ~/Library/LaunchAgents/<label>.plist
    python3 janitor/install_launchd.py --hour 3 --minute 17

Testing overrides (never used by a real install): --repo-root, --library-dir.
"""
import argparse
import os
import plistlib
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO_ROOT, "hooks"))
import guard  # noqa: E402

LABEL = "com.claude-settings.janitor.daily-sweep"


def resolve_primary_checkout(where: str):
    """Same read `session_end_sweep.py.resolve_repo_root` does: the parent of the one `.git`
    directory every worktree of a clone shares. Used only to NAME the remedy when refusing."""
    top = guard._git(where, "rev-parse", "--show-toplevel")
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
        return os.path.dirname(os.path.realpath(os.path.join(toplevel, common_dir)))
    except Exception:
        return None


def build_plist(repo_root: str, hour: int, minute: int, log_dir: str):
    # No --discover root here: see the module docstring above.
    sweep_py = os.path.join(repo_root, "janitor", "sweep.py")
    return {
        "Label": LABEL,
        "ProgramArguments": [sys.executable, sweep_py, "--confirm"],
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "RunAtLoad": False,
        "StandardOutPath": os.path.join(log_dir, "launchd-sweep.log"),
        "StandardErrorPath": os.path.join(log_dir, "launchd-sweep.err.log"),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--hour", type=int, default=3, help="local hour, 0-23 (default 3)")
    parser.add_argument("--minute", type=int, default=17, help="local minute, 0-59 (default 17)")
    parser.add_argument("--repo-root", default=None,
                         help="testing only: the checkout to treat as this installer's own")
    parser.add_argument("--library-dir", default=None,
                         help="testing only: overrides ~/Library")
    args = parser.parse_args(argv)

    repo_root = os.path.abspath(args.repo_root) if args.repo_root else REPO_ROOT
    library_dir = os.path.abspath(args.library_dir) if args.library_dir \
        else os.path.expanduser("~/Library")

    worktree = guard.is_worktree(repo_root)
    if worktree is not False:
        primary = resolve_primary_checkout(repo_root)
        if worktree is True:
            head = "janitor: refusing to install from a linked worktree (%s)." % repo_root
        else:
            head = ("janitor: could not tell whether %s is a linked worktree; refusing rather "
                     "than guess." % repo_root)
        remedy = ("Install from the main checkout instead%s." %
                  ((": " + primary) if primary else " (its main checkout)"))
        print(head + " " + remedy, file=sys.stderr)
        return 1

    log_dir = os.path.join(guard.config_dir(), "janitor")
    os.makedirs(log_dir, exist_ok=True)

    data = build_plist(repo_root, args.hour, args.minute, log_dir)
    launch_agents_dir = os.path.join(library_dir, "LaunchAgents")
    os.makedirs(launch_agents_dir, exist_ok=True)
    plist_path = os.path.join(launch_agents_dir, LABEL + ".plist")
    with open(plist_path, "wb") as handle:
        plistlib.dump(data, handle)

    print("Wrote %s" % plist_path)
    print("Load it with:   launchctl load -w %s" % plist_path)
    print("Unload it with: launchctl unload %s" % plist_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
