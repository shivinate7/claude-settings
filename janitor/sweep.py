#!/usr/bin/env python3
"""The machine-wide janitor sweep.

Governed by plans/janitor-build-plan.md. Reaps local branches that hold no unique work and
removes git worktrees that no session still uses, across every repository the sweep is pointed
at, or discovers.

WHY THIS IMPORTS hooks/guard.py INSTEAD OF WRITING ITS OWN COPY: hooks/guard.py's PreToolUse
rule 1 (`branch_delete_subject`, `worktree_remove_subject`, `resolve_default_base`,
`session_is_live`, the three `branch_*` tests, `worktree_locked`, `porcelain`) already answers
almost every question this sweep asks, is already exercised by hooks/test_guard.py, and a
second copy of that logic is the one outcome this build must avoid (plan, "the one outcome to
avoid"). This module therefore calls guard's own primitives directly for every decision that
holds a safety property (dirty/locked/live/ancestor/cherry/remote-contains), and keeps its own
code only for orchestration (which repositories, which branches, which order, the preview
report, the tombstone, and the 90-day purge) that guard has no reason to know about. Nothing
here re-derives a keep-or-reap boolean by a path of its own; every boolean comes from guard.

Preview is the default. Nothing is deleted until `--confirm` is passed. The sweep never touches
a remote. It never stops a program a live session still needs: the one program it can stop is an
orphaned TCP listener, left behind inside a repository this sweep already covers, once every
liveness and ownership read on it comes back a confirmed "yes, reap." See "ORPHANED LISTENERS"
below for the incident this answers and the reasons behind each read.

ORPHANED LISTENERS (2026-09-24, macOS). A subagent started `python3 -m http.server 8000` inside
`( ... & )`. Its own shell exited; pid 1 adopted the server. Its checkout was a linked worktree
under Claude's own scratch-workspaces directory. The parent later ran `git worktree remove` on
that worktree while two servers still ran inside it -- deleting files out from under a running
program. The server bound `[::]:8000`, shadowed the owner's own server on `localhost:8000`, and
was still running a day later.

This sweep now finds a TCP listener whose cwd sits inside a repository (or worktree) it already
covers, and reaps it ONLY when every one of these reads answers a confirmed yes:
it is orphaned (a per-OS read, never a guess); no live Claude session has a cwd in that same
checkout (guard.py's own tested oracle, never a second copy of it); and it is owned by the
current user. An unreadable answer to any one of those three means KEEP, the same fail-closed
shape guard.py's own liveness oracle already uses (decisions/liveness-read-is-platform-specific-
and-unreadable-is-not-death.md). `--confirm` signals a reapable pid by NUMBER alone, never by a
name or a command-line pattern (CLAUDE.md: "Never kill a process you did not start. Treat
`pkill -f` and `lsof -t` as machine-wide."), and this sweep never escalates past that one signal
on its own.

Before a worktree is removed, this sweep also checks for ANY process at all (not only a
listener) whose cwd sits inside it, and keeps the worktree, naming the pids, when one is found.
On Windows this pre-check is the actual fix for the incident above, not a nicety: `git worktree
remove` against a directory Windows refuses to delete (because a live process still holds it
open) does a PARTIAL delete there -- files gone, an empty directory left behind, and git still
lists the worktree as registered. Refusing to call `git worktree remove` at all when a process
still sits inside is what keeps that partial state from ever happening.

Usage:
    python3 janitor/sweep.py [ROOT ...]                 # preview a sweep of the named roots
    python3 janitor/sweep.py --discover DIR              # preview a sweep of DIR's own checkouts
    python3 janitor/sweep.py ROOT --confirm              # actually reap
    python3 janitor/sweep.py --purge                     # preview which tombstones are past 90 days
    python3 janitor/sweep.py --purge --confirm           # actually drop tombstones past 90 days

With no ROOT and no `--discover`, the sweep reads `janitor.roots` from this repository's own
settings.json. Absent, it discovers under every one of `~/Developer`, `~/Clones`, `~/src`,
`~/code`, and `~/repos` that exists on this machine, combined into one list. A measured default
run once printed "no repositories found" while five real clones sat in `~/Clones`, not
`~/Developer`. Present but malformed, not a list of strings, the sweep refuses to discover
anything and says why. It never guesses at a wish it cannot read. `--discover DIR` bypasses
`janitor.roots` and the default list entirely. Discovery lists a directory's immediate children
whose `.git` is a DIRECTORY (an ordinary checkout), never a FILE (a linked worktree of some other
checkout): a linked worktree's branches already belong to its primary checkout's sweep, and
sweeping it a second time as its own "repository" would apply the keep rule against the wrong
tree entirely.
"""
import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO_ROOT, "hooks"))
import guard  # noqa: E402

OPTOUT_FILENAME = os.path.join(".claude", "janitor.json")
DEFAULT_PROTECTED_PREFIXES = ("backup/",)
TOMBSTONE_REF_PREFIX = "refs/janitor/reaped/"
TOMBSTONE_TTL_MS = 90 * 24 * 60 * 60 * 1000  # git's own reflog-retention number; see the plan


# ------------------------------------------------------------------ discovery


def discover_repos(root: str):
    """Return ROOT's immediate children that are ordinary checkouts (`.git` a directory).

    A linked worktree's `.git` is a FILE naming its own admin directory, so it never matches
    here; only a primary checkout does. Sorted for a stable, readable report.
    """
    if not root or not os.path.isdir(root):
        return []
    found = []
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        if os.path.isdir(os.path.join(path, ".git")):
            found.append(path)
    return found


def discover_repos_multi(roots):
    """Combine `discover_repos` across every root in ROOTS into one de-duplicated, sorted list.
    A default or configured root LIST then behaves like one search, instead of stopping at the
    first root that happens to exist."""
    found = set()
    for root in roots:
        found.update(discover_repos(root))
    return sorted(found)


# ------------------------------------------------------------------ `janitor.roots` (settings.json)
#
# `janitor.roots`, inside THIS repository's own settings.json, read as DATA (json.load) and
# never executed. ABSENT (no settings.json, no `janitor` object, or no `roots` key inside it)
# states nothing. The caller then falls back to `default_discover_roots()`.
#
# PRESENT but malformed states a wish this function cannot read. "Malformed" means not a list,
# or a list holding a non-string. This is the same direction `load_optout` above already takes
# for `.claude/janitor.json`. Guessing wrong costs branches or checkouts that never get swept,
# and nobody notices. Refusing costs one rerun after the owner fixes the file.

def _scratch_workspace_root_candidates():
    """Claude Desktop's own scratch-workspace root, one per platform, MEASURED rather than
    guessed. macOS: `~/Library/Application Support/Claude/scratch-workspaces` (named in this
    build's brief, from the 2026-09-23 incident). Windows: `%APPDATA%\\Claude\\scratch-
    workspaces`, with APPDATA read from the environment, never a hardcoded user, so this
    answers for whoever runs the sweep. Linux: UNKNOWN. Nobody has measured this machine's own
    layout there, so this adds NOTHING for Linux rather than guess a path that may not exist --
    the same direction `load_janitor_roots_setting` already takes for any wish it cannot read.

    MEASURED on a real Windows machine, 2026-09-24, read-only (no code below acts on this):
    `%APPDATA%\\Claude\\scratch-workspaces` holds `<uuid>\\<uuid>\\scratch-YYYY-MM-DD-xxxxxx`
    leaf directories. None of six such leaves on this machine held a `.git` file OR directory
    -- they held ordinary scratch files (templates, scripts), never a checkout. A sibling
    `%APPDATA%\\Claude\\git-shadow\\<hash>\\shadow-of` file names the REAL external repo a
    hashed git directory shadows, but that mechanism has no path back to a scratch-workspaces
    leaf: it runs in the other direction, and nothing under scratch-workspaces referenced it.
    So `discover_repos`'s existing rule (an immediate child whose `.git` is a directory) finds
    nothing here, exactly as this build's brief predicted it would, and there is no further
    checkout-mapping this sweep can act on beneath this root without inventing one. The root is
    still added: a future scratch-workspaces layout that DOES leave a real linked worktree
    behind (the incident this build answers was exactly that shape, on macOS) is then covered
    the day it appears, at no cost today, since an empty root discovers nothing either way."""
    if sys.platform == "darwin":
        return ("~/Library/Application Support/Claude/scratch-workspaces",)
    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA")
        if not appdata:
            return ()
        return (os.path.join(appdata, "Claude", "scratch-workspaces"),)
    return ()


DEFAULT_DISCOVER_ROOT_CANDIDATES = (
    ("~/Developer", "~/Clones", "~/src", "~/code", "~/repos") + _scratch_workspace_root_candidates()
)


def default_discover_roots():
    """Every one of DEFAULT_DISCOVER_ROOT_CANDIDATES that exists on this machine, in that fixed
    order. Replaces the old single-root guess. This module's docstring names the measured
    problem. A real machine can have clones split across more than one of these directories.
    Stopping at the first hit missed the rest.

    `os.path.normpath` fixes a real defect, measured on Windows. Each candidate is written
    POSIX-style, like `~/Developer`. `os.path.expanduser` only replaces the leading `~`. It
    never touches the rest of the string.

    On Windows, the `~` becomes a backslash path. The literal `/Developer` suffix stays a
    forward slash. The result mixes both separators in one path. The same directory, built
    through `os.path.join` anywhere else in this codebase, uses backslash throughout. Plain
    string equality then sees two different paths for the same directory.

    `discover_repos_multi` removes duplicates with a `set()`. That is the same plain string
    match. `normpath` fixes every candidate once, at the one place they all pass through.
    """
    return [os.path.normpath(path)
            for path in (os.path.expanduser(c) for c in DEFAULT_DISCOVER_ROOT_CANDIDATES)
            if os.path.isdir(path)]


def default_settings_path() -> str:
    return os.path.join(REPO_ROOT, "settings.json")


def load_janitor_roots_setting(settings_path=None):
    """Return (roots, ok).

    `roots` is None when the `janitor.roots` key is ABSENT: the caller then falls back to
    `default_discover_roots()`. `roots` is the configured list, each entry `os.path.expanduser`
    -ed, when the key is present and well shaped.

    `ok` is False when settings.json exists but cannot be parsed as one JSON object. It is also
    False when the top-level `janitor` value is present but is not an object. It is False too
    when `janitor.roots` IS present but is not a list of strings. In every one of those cases
    the caller refuses to discover anything rather than trust a default it was not asked for.
    """
    path = settings_path or default_settings_path()
    if not os.path.isfile(path):
        return None, True
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return None, False
    if not isinstance(data, dict):
        return None, False
    janitor_cfg = data.get("janitor")
    if janitor_cfg is None:
        return None, True
    if not isinstance(janitor_cfg, dict):
        return None, False
    if "roots" not in janitor_cfg:
        return None, True
    roots = janitor_cfg["roots"]
    if not isinstance(roots, list) or not all(isinstance(item, str) for item in roots):
        return None, False
    return [os.path.expanduser(item) for item in roots], True


# ------------------------------------------------------------------ the opt-out file
#
# `.claude/janitor.json`, inside the repository, read as DATA (json.load) and never executed.
# Absent means swept, with the default protected prefix `backup/` alone. `"sweep": false` opts
# the whole repository out. `"protectedPrefixes"` adds more prefixes beside `backup/`.
#
# A present file that cannot be parsed is an UNREADABLE subject, same direction as refusal 7: the
# sweep does not know what this repository asked for, so it reaps nothing here rather than guess
# that an unreadable "no" meant "yes".


def load_optout(root: str):
    """Return (sweep_enabled, protected_prefixes, ok).

    ok is False when the file exists but could not be read as one JSON object, or when a key it
    DOES hold is not shaped the way that key means: a `sweep` value that is not a boolean, or a
    `protectedPrefixes` value that is not a list of strings. In every one of those cases the
    caller refuses the whole repository rather than trust a default.

    A key that is ABSENT is different: an absent key states nothing, and the owner's choice was
    auto-on, so the default still applies. But a key that IS present and malformed states a
    wish the sweep cannot read. Guessing at that wish is the one error that costs work: guess
    wrong on `sweep` and a repository that opted out gets swept and loses branches; guess wrong
    on `protectedPrefixes` and a repository silently protects nothing. Refusing the repository
    costs one rerun after the owner fixes the file. Guessing costs branches that do not come
    back.
    """
    path = os.path.join(root, OPTOUT_FILENAME)
    if not os.path.isfile(path):
        return True, DEFAULT_PROTECTED_PREFIXES, True
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return False, (), False
    if not isinstance(data, dict):
        return False, (), False
    if "sweep" in data and not isinstance(data["sweep"], bool):
        return False, (), False
    sweep_enabled = data.get("sweep", True)
    if "protectedPrefixes" in data:
        extra = data["protectedPrefixes"]
        if not isinstance(extra, list) or not all(isinstance(item, str) for item in extra):
            return False, (), False
    else:
        extra = []
    prefixes = list(DEFAULT_PROTECTED_PREFIXES)
    for item in extra:
        if item:
            prefixes.append(item)
    return sweep_enabled, tuple(prefixes), True


# ------------------------------------------------------------------ reading a repository's state


def list_local_branches(where: str):
    """Return every local branch's short name, or None when the read failed."""
    answer = guard._git(where, "for-each-ref", "--format=%(refname:short)", "refs/heads")
    if answer is None or answer.returncode != 0:
        return None
    return [line.strip() for line in answer.stdout.splitlines() if line.strip()]


def _short_branch_ref(ref: str) -> str:
    prefix = "refs/heads/"
    return ref[len(prefix):] if ref.startswith(prefix) else ref


def parse_worktree_list(where: str):
    """Return every registered worktree of `where`'s clone as a dict, or None when unreadable.

    Same block shape guard.worktree_locked already parses (`--porcelain`, blocks separated by a
    blank line); this reads the whole listing instead of one target, because the sweep needs the
    full set: which branch each worktree holds (for the checked-out refusal) and which path to
    decide on next.
    """
    answer = guard._git(where, "worktree", "list", "--porcelain")
    if answer is None or answer.returncode != 0:
        return None
    entries = []
    for block in answer.stdout.split("\n\n"):
        lines = block.splitlines()
        if not lines or not lines[0].startswith("worktree "):
            continue
        entry = {
            "path": lines[0][len("worktree "):].strip(),
            "branch": None,
            "bare": False,
            "detached": False,
            "locked_reason": None,
        }
        for line in lines[1:]:
            if line.startswith("branch "):
                entry["branch"] = _short_branch_ref(line[len("branch "):].strip())
            elif line == "bare":
                entry["bare"] = True
            elif line == "detached":
                entry["detached"] = True
            elif line == "locked" or line.startswith("locked "):
                entry["locked_reason"] = line[len("locked"):].strip() or "locked"
        entries.append(entry)
    return entries


# ------------------------------------------------------------------ the branch keep rule
#
# The REAP-OR-KEEP boolean is guard.branch_is_empty(where, base, branch) alone, unchanged:
# ancestor, then cherry-empty, then remote-contains, any one passing proves the work survives the
# branch, None (any test could not be read) means keep. This function decides nothing that
# function did not already decide; the refusals ahead of it (default branch, protected prefix,
# checked out) and the label after it (which of the three tests passed) are the only things added
# here, and neither can turn a keep into a reap or a reap into a keep.


def decide_branch(where: str, base: str, branch: str, protected_prefixes, checked_out_branches):
    """Return one decision dict: {"name", "action": "reap"|"keep", "reason"}."""
    if branch in ("main", "master"):
        return {"name": branch, "action": "keep", "reason": "default-branch"}
    for prefix in protected_prefixes:
        if branch.startswith(prefix):
            return {"name": branch, "action": "keep", "reason": "protected-prefix:" + prefix}
    if branch in checked_out_branches:
        return {"name": branch, "action": "keep", "reason": "checked-out"}
    empty = guard.branch_is_empty(where, base, branch)
    if empty is None:
        return {"name": branch, "action": "keep", "reason": "unreadable-subject"}
    if empty is False:
        return {"name": branch, "action": "keep", "reason": "only-copy"}
    return {"name": branch, "action": "reap", "reason": _branch_reap_label(where, base, branch)}


def _branch_reap_label(where: str, base: str, branch: str) -> str:
    """Cosmetic only: guard.branch_is_empty above already decided REAP. This re-reads the same
    three tests, in the same order, purely to name which one passed in the preview line. A bug
    here can only mislabel a reap; it cannot turn a keep into a reap, because the boolean already
    came from guard.branch_is_empty and this function's return value never feeds back into it."""
    if guard.branch_is_ancestor(where, base, branch):
        return "ancestor"
    if guard.branch_cherry_empty(where, base, branch):
        return "cherry-empty"
    return "on-remote"


# ------------------------------------------------------------------ the worktree keep rule
#
# Same shape: every boolean (dirty, locked, live) is guard's own primitive
# (guard.porcelain, guard.worktree_locked, guard.worktree_live_session), read in the same order
# guard.worktree_remove_subject already uses. This function adds only the "which one refused"
# label. The "never touch the primary checkout" exclusion is NOT here: it is decided in
# `sweep_repo`, before `decide_worktree` is ever called, by `_is_primary_checkout` below. See
# that function's docstring for why comparing against the ROOT argument (an earlier version of
# this file did that, and only that) is not enough.


def _is_primary_checkout(entry_path: str):
    """True when `entry_path` IS the repository's one primary checkout, False for a linked
    worktree, None when the read failed.

    THE DEFECT THIS REPLACES: an earlier version of this file compared each worktree entry's
    real path against the `root` argument `sweep_repo` was called with, and skipped only that
    one match. That is correct ONLY when `root` already names the primary checkout. Call
    `sweep_repo` with a LINKED WORKTREE's own path instead (`session_end_sweep.py`'s whole job
    is to prevent that, by resolving to the primary checkout first, but `sweep.py` itself must
    not depend on every caller doing that correctly) and the actual primary checkout stops
    matching `root`, stops being excluded, and gets evaluated by `decide_worktree` like any
    other worktree -- `REAP removable` when it happens to be clean, unlocked, and not live. A
    reviewer measured exactly that against a real fixture: `git worktree remove` on the primary
    tree then failed only because GIT ITSELF refuses to remove a main working tree that way --
    a refusal this program does not control and must not lean on (CLAUDE.md,
    "verification-recovery-not-gated-on-own-state"; a guard that depends on someone else's
    refusal fails the day that refusal changes).

    THE FIX: ask git which path is primary, independent of what `root` was. Every worktree of
    one clone shares exactly one git directory (`--git-common-dir`); the primary checkout is
    the one worktree whose OWN git directory (`--git-dir`) equals that shared one. A linked
    worktree's own git directory is instead a subdirectory of the shared one
    (`<common>/worktrees/<name>`), so the two never match there. This is the same read
    `hooks/guard.py.is_worktree` already makes and `hooks/test_guard.py` already exercises, run
    here per-entry so it answers correctly no matter which worktree `sweep_repo` was pointed at.
    """
    answer = guard._git(entry_path, "rev-parse", "--git-dir", "--git-common-dir")
    if answer is None or answer.returncode != 0:
        return None
    lines = answer.stdout.splitlines()
    if len(lines) < 2:
        return None
    try:
        own = os.path.normcase(os.path.realpath(os.path.join(entry_path, lines[0].strip())))
        common = os.path.normcase(os.path.realpath(os.path.join(entry_path, lines[1].strip())))
    except Exception:
        return None
    return own == common


def decide_worktree(where: str, entry: dict):
    """Return one decision dict: {"path", "action": "reap"|"keep", "reason"}."""
    path = entry["path"]
    dirty = guard.porcelain(path)
    if dirty is None:
        return {"path": path, "action": "keep", "reason": "unreadable-subject"}
    if dirty:
        return {"path": path, "action": "keep", "reason": "dirty"}
    locked = guard.worktree_locked(where, path)
    if locked is None:
        return {"path": path, "action": "keep", "reason": "unreadable-subject"}
    if locked:
        holder = entry.get("locked_reason") or "locked"
        return {"path": path, "action": "keep", "reason": "locked: %s" % holder}
    live = guard.worktree_live_session(path)
    if live is None:
        return {"path": path, "action": "keep", "reason": "unreadable-subject"}
    if live:
        return {"path": path, "action": "keep", "reason": "live-session"}
    # The pre-removal process check (brief point 4). ANY process at all, not only a listener --
    # a plain shell sitting in this worktree is just as much a reason `git worktree remove`
    # must not run as a live Claude session is.
    #
    # A single PID whose own cwd read fails is OUT OF SCOPE, not a keep -- MEASURED, not the
    # first guess: on this real Windows machine, 272 of 580 running processes answer `None` to
    # `process_cwd` (most of them belong to another account, or are otherwise access-
    # protected). Keeping every worktree on a machine that shape is normal on would make this
    # pre-check refuse to ever reap anything, on any real machine, which is a worse outcome
    # than the leak it exists to prevent. This is the SAME direction the original brief already
    # named for a different read: "A single process of another user, or one that refuses
    # access, is out of scope. Count it in the report, never act on it" -- extended here from
    # the owner check to this one too, for the reason just measured, and kept identical on
    # POSIX and Windows (both dispatch through the same `process_cwd`, with no OS branch here
    # at all). Only the WHOLE enumeration failing (`processes_in` returning `(None, None)`)
    # still means keep-everything: that is a different failure, the brief's own words, "if the
    # whole listing ... or the pre-check enumeration fails."
    inside, _unreadable = processes_in(path)
    if inside is None:
        return {"path": path, "action": "keep", "reason": "unreadable-subject"}
    if inside:
        return {"path": path, "action": "keep",
                "reason": "process-inside: pid %s" % ", ".join(str(p) for p in sorted(inside))}
    return {"path": path, "action": "reap", "reason": "removable"}


# ------------------------------------------------------------------ orphaned TCP listeners
#
# See the module docstring, "ORPHANED LISTENERS", for the incident and the shape of the rule.
# Every function below is read-only until `send_signal` and `reap_listener`, at the very end of
# this section: everything before that point only LOOKS, on this one machine, and touches
# nothing.
#
# Every OS-specific read below answers three things, never two, the same shape guard.py's own
# `_process_start_ms` already established: a confirmed answer (True/False), or `None` when the
# read itself could not tell. `None` is never coerced into a confident answer by this file. A
# caller that receives `None` from any of these always keeps, never reaps -- see
# decisions/liveness-read-is-platform-specific-and-unreadable-is-not-death.md, which states this
# rule for a different read, and CLAUDE.md's "report a read that could not run as unknown, never
# as clear or broken", which states it for every read.


def list_listeners():
    """Return every `[{"pid", "port"}]` this machine currently has a process LISTENing on a TCP
    port for, or `None` when the enumeration itself failed (no per-OS tool answered at all).
    Stdlib subprocess calls and, on Windows, `ctypes` only -- no psutil, per this build's brief."""
    if sys.platform == "darwin":
        return _list_listeners_lsof()
    if sys.platform.startswith("linux"):
        listeners = _list_listeners_ss()
        return listeners if listeners is not None else _list_listeners_lsof()
    if sys.platform.startswith("win"):
        return _list_listeners_windows()
    return None


def _port_from_address(address: str):
    """Parse the port out of an lsof/ss-style "host:port" address, including a bracketed IPv6
    host (`[::]:8000`) and a trailing state annotation ss sometimes appends. `None` when the
    text does not end in a parseable port."""
    if not address or ":" not in address:
        return None
    port_text = address.rsplit(":", 1)[-1].split()[0]
    try:
        return int(port_text)
    except ValueError:
        return None


def _list_listeners_lsof():
    """macOS (and Linux's own fallback): `lsof -nP -iTCP -sTCP:LISTEN -F pn`. `-F pn` prints one
    `p<pid>` line per process, followed by one `n<name>` line per matching socket of that same
    process -- so the last `p` line seen names the owner of every `n` line that follows it,
    until the next `p`. lsof's own exit code is 1, with empty output, when nothing at all
    matches; that is a confirmed empty answer, not a read failure."""
    try:
        answer = subprocess.run(
            ["lsof", "-nP", "-iTCP", "-sTCP:LISTEN", "-F", "pn"],
            capture_output=True, text=True, timeout=10,
        )
    except Exception:
        return None
    if answer.returncode not in (0, 1):
        return None
    listeners = []
    pid = None
    for line in answer.stdout.splitlines():
        if not line:
            continue
        tag, value = line[0], line[1:]
        if tag == "p":
            try:
                pid = int(value)
            except ValueError:
                pid = None
        elif tag == "n" and pid is not None:
            port = _port_from_address(value)
            if port is not None:
                listeners.append({"pid": pid, "port": port})
    return listeners


_SS_PID_RE = re.compile(r"pid=(\d+)")


def _list_listeners_ss():
    """Linux: `ss -ltnp`. Its "Process" column reads like `users:(("python3",pid=1234,fd=6))`;
    the pid is pulled out with a regex rather than a full parse of that column, the same
    lightness `_process_owner_sid_windows` elsewhere in this file uses for a Windows structure
    it only needs one field from. `None` when `ss` itself is missing or refuses to run, so the
    caller falls back to lsof (Linux ships both, per this build's brief)."""
    try:
        answer = subprocess.run(["ss", "-ltnp"], capture_output=True, text=True, timeout=10)
    except Exception:
        return None
    if answer.returncode != 0:
        return None
    listeners = []
    for line in answer.stdout.splitlines():
        if not line.startswith("LISTEN"):
            continue
        columns = line.split()
        if len(columns) < 4:
            continue
        port = _port_from_address(columns[3])
        match = _SS_PID_RE.search(line)
        if port is None or not match:
            continue
        listeners.append({"pid": int(match.group(1)), "port": port})
    return listeners


def _tcp_table_windows(address_family: int):
    """One call to `GetExtendedTcpTable(TCP_TABLE_OWNER_PID_LISTENER)`, for AF_INET or
    AF_INET6, returning every LISTENing row's (pid, port). Two calls (this function, called
    once per family by `_list_listeners_windows`) because IPv4 and IPv6 use two different row
    layouts (`MIB_TCPROW_OWNER_PID` vs `MIB_TCP6ROW_OWNER_PID`) -- and the real incident this
    build answers bound `[::]:8000`, IPv6, so skipping this family would miss the exact shape
    that was measured. `None` when the API itself refuses (the first, sizing call answers
    neither 0 nor `ERROR_INSUFFICIENT_BUFFER`, or the second, real call does not answer 0)."""
    import ctypes

    MIB_TCP_STATE_LISTEN = 2
    ERROR_INSUFFICIENT_BUFFER = 122
    iphlpapi = ctypes.windll.iphlpapi

    size = ctypes.c_ulong(0)
    ret = iphlpapi.GetExtendedTcpTable(None, ctypes.byref(size), False, address_family, 3, 0)
    if ret not in (0, ERROR_INSUFFICIENT_BUFFER):
        return None
    buf = ctypes.create_string_buffer(size.value)
    ret = iphlpapi.GetExtendedTcpTable(buf, ctypes.byref(size), False, address_family, 3, 0)
    if ret != 0:
        return None

    num_entries = ctypes.cast(buf, ctypes.POINTER(ctypes.c_ulong))[0]
    row_offset = ctypes.sizeof(ctypes.c_ulong)
    listeners = []
    if address_family == 2:  # AF_INET
        class Row(ctypes.Structure):
            _fields_ = [("dwState", ctypes.c_ulong), ("dwLocalAddr", ctypes.c_ulong),
                        ("dwLocalPort", ctypes.c_ulong), ("dwRemoteAddr", ctypes.c_ulong),
                        ("dwRemotePort", ctypes.c_ulong), ("dwOwningPid", ctypes.c_ulong)]
    else:  # AF_INET6 == 23
        class Row(ctypes.Structure):
            _fields_ = [("ucLocalAddr", ctypes.c_ubyte * 16), ("dwLocalScopeId", ctypes.c_ulong),
                        ("dwLocalPort", ctypes.c_ulong), ("ucRemoteAddr", ctypes.c_ubyte * 16),
                        ("dwRemoteScopeId", ctypes.c_ulong), ("dwRemotePort", ctypes.c_ulong),
                        ("dwState", ctypes.c_ulong), ("dwOwningPid", ctypes.c_ulong)]
    rows = ctypes.cast(
        ctypes.byref(buf, row_offset), ctypes.POINTER(Row * num_entries)
    )[0] if num_entries else []
    for row in rows:
        if row.dwState != MIB_TCP_STATE_LISTEN:
            continue
        port_be = row.dwLocalPort & 0xFFFF
        port = ((port_be & 0xFF) << 8) | (port_be >> 8)
        listeners.append({"pid": row.dwOwningPid, "port": port})
    return listeners


def _list_listeners_windows():
    """ctypes `GetExtendedTcpTable`, IPv4 then IPv6. `None` only when BOTH families fail to
    answer at all (a partial answer, one family real and the other refused, still reports the
    family that worked rather than throw it away -- an enumeration failure on one family is not
    proof the other's answer is wrong)."""
    ipv4 = _tcp_table_windows(2)
    ipv6 = _tcp_table_windows(23)
    if ipv4 is None and ipv6 is None:
        return None
    return (ipv4 or []) + (ipv6 or [])


def process_cwd(pid: int):
    """Return PID's current working directory, or `None` when it could not be read (pid gone,
    access denied, or -- Windows -- the undocumented PEB read below refused). Never raises."""
    if sys.platform == "darwin":
        return _process_cwd_macos(pid)
    if sys.platform.startswith("linux"):
        return _process_cwd_linux(pid)
    if sys.platform.startswith("win"):
        return _process_cwd_windows(pid)
    return None


def _process_cwd_macos(pid: int):
    """`lsof -a -p PID -d cwd -Fn`: one `n<path>` line for the cwd file descriptor alone (`-d
    cwd`), `-a` ANDs that with `-p PID`. Exit code 1 with empty output means lsof found no such
    fd (pid gone, or this read is not allowed to see it) -- unreadable, not a path."""
    try:
        answer = subprocess.run(
            ["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
            capture_output=True, text=True, timeout=10,
        )
    except Exception:
        return None
    if answer.returncode not in (0, 1):
        return None
    for line in answer.stdout.splitlines():
        if line.startswith("n"):
            return line[1:]
    return None


def _process_cwd_linux(pid: int):
    """`/proc/PID/cwd` is a symlink to the process's cwd. A cwd whose directory has since been
    unlinked (exactly the "worktree already removed, process still inside it" case this build
    exists for) reads back with a literal ` (deleted)` suffix, which is stripped here so the
    path still matches the worktree it names -- the process is still THERE, the directory
    entry is just gone."""
    try:
        raw = os.readlink("/proc/%d/cwd" % pid)
    except Exception:
        return None
    suffix = " (deleted)"
    if raw.endswith(suffix):
        raw = raw[: -len(suffix)]
    return raw or None


def _process_cwd_windows(pid: int):
    """ponytail: the PEB offsets below are UNDOCUMENTED and 64-bit-process-only (per this
    build's own brief: github.com/giampaolo/psutil/issues/51,
    github.com/raskrebs/sonar/pull/57). Any failure at any step answers `None`, never a guess.
    Upgrade path: `psutil.Process(pid).cwd()` the day this repository allows a third-party
    dependency for it -- this function exists only because the brief asks for stdlib+ctypes
    alone.

    `OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ)` -> `NtQueryInformationProcess`
    for the PEB address -> `ReadProcessMemory` of `PEB.ProcessParameters` (offset 0x20 on
    64-bit) -> `ReadProcessMemory` of that struct's `CurrentDirectory.DosPath`, a
    `UNICODE_STRING` (offset 0x38), whose `Buffer` is read once more for the actual text."""
    import ctypes

    PROCESS_QUERY_INFORMATION = 0x0400
    PROCESS_VM_READ = 0x0010
    kernel32 = ctypes.windll.kernel32
    ntdll = ctypes.windll.ntdll

    # MEASURED bug, fixed here: ctypes guesses a plain 32-bit `c_int` for any argument or
    # return value it is not told the type of. A real PEB address or heap pointer on a 64-bit
    # process routinely exceeds that range (MEASURED: 0x4cd39e000, this file's own process) --
    # silently truncated going IN, or raising `OverflowError` coming OUT. Every handle and
    # pointer this function touches is typed explicitly so the addresses below are never
    # mangled by that default.
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    ntdll.NtQueryInformationProcess.restype = ctypes.c_long
    ntdll.NtQueryInformationProcess.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p,
    ]
    kernel32.ReadProcessMemory.restype = ctypes.c_int
    kernel32.ReadProcessMemory.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]

    handle = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not handle:
        return None
    try:
        class ProcessBasicInformation(ctypes.Structure):
            _fields_ = [("Reserved1", ctypes.c_void_p), ("PebBaseAddress", ctypes.c_void_p),
                        ("Reserved2", ctypes.c_void_p * 2), ("UniqueProcessId", ctypes.c_void_p),
                        ("Reserved3", ctypes.c_void_p)]

        pbi = ProcessBasicInformation()
        status = ntdll.NtQueryInformationProcess(
            handle, 0, ctypes.byref(pbi), ctypes.sizeof(pbi), None
        )
        if status != 0 or not pbi.PebBaseAddress:
            return None

        params_addr = ctypes.c_void_p()
        ok = kernel32.ReadProcessMemory(
            handle, ctypes.c_void_p(pbi.PebBaseAddress + 0x20), ctypes.byref(params_addr),
            ctypes.sizeof(params_addr), None,
        )
        if not ok or not params_addr.value:
            return None

        class UnicodeString(ctypes.Structure):
            _fields_ = [("Length", ctypes.c_ushort), ("MaximumLength", ctypes.c_ushort),
                        ("Buffer", ctypes.c_void_p)]

        current_directory = UnicodeString()
        ok = kernel32.ReadProcessMemory(
            handle, ctypes.c_void_p(params_addr.value + 0x38), ctypes.byref(current_directory),
            ctypes.sizeof(current_directory), None,
        )
        if not ok or not current_directory.Buffer or current_directory.Length <= 0:
            return None

        text_buf = ctypes.create_unicode_buffer(current_directory.Length // 2)
        ok = kernel32.ReadProcessMemory(
            handle, ctypes.c_void_p(current_directory.Buffer), text_buf,
            current_directory.Length, None,
        )
        if not ok:
            return None
        return text_buf.value or None
    except Exception:
        return None
    finally:
        kernel32.CloseHandle(handle)


def process_command(pid: int):
    """Best-effort, display-only. Never used to decide reap-or-keep (CLAUDE.md: never dry-run a
    block-list) -- the preview shows it so a human can recognise the program, and a signal is
    still sent by pid number alone."""
    if sys.platform == "darwin":
        return _process_command_posix(pid)
    if sys.platform.startswith("linux"):
        return _process_command_linux(pid) or _process_command_posix(pid)
    if sys.platform.startswith("win"):
        return _process_command_windows(pid)
    return None


def _process_command_posix(pid: int):
    try:
        answer = subprocess.run(
            ["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True, timeout=5,
        )
    except Exception:
        return None
    if answer.returncode != 0:
        return None
    text = answer.stdout.strip()
    return text or None


def _process_command_linux(pid: int):
    try:
        with open("/proc/%d/cmdline" % pid, "rb") as handle:
            raw = handle.read()
    except Exception:
        return None
    parts = [part.decode("utf-8", "replace") for part in raw.split(b"\x00") if part]
    return " ".join(parts) or None


def _process_command_windows(pid: int):
    """`QueryFullProcessImageNameW`, a DOCUMENTED API (unlike the cwd read above): this reports
    the executable's own path, not its argv, because getting a full command line reliably needs
    the same undocumented PEB reach this file already limits to one read (cwd). The image path
    is enough for a human reading the preview to recognise the program."""
    import ctypes
    import ctypes.wintypes as wintypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.QueryFullProcessImageNameW.argtypes = [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.c_wchar_p, ctypes.POINTER(wintypes.DWORD),
    ]
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        size = wintypes.DWORD(32768)
        buf = ctypes.create_unicode_buffer(size.value)
        ok = kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size))
        if not ok:
            return None
        return buf.value or None
    finally:
        kernel32.CloseHandle(handle)


def is_orphan(pid: int):
    """True when PID is confirmed orphaned. False when it is confirmed NOT orphaned (a real
    parent pid was read, and that parent is alive with no later creation time than PID's own).
    None when some read along the way could not tell -- reported as `unreadable-subject` by
    every caller in this file, never coerced into a confident answer either way (decisions/
    liveness-read-is-platform-specific-and-unreadable-is-not-death.md).

    POSIX: PID's own PPid is 1 (`/proc/PID/status` on Linux, `ps -o ppid=` on macOS). A
    subreaper (`PR_SET_CHILD_SUBREAPER`) adopts with ITS OWN pid, never 1, so this stays
    stricter than "parent is dead" on purpose -- the brief: "Do not treat a subreaper as
    orphaned (stricter is safe)."

    Windows never re-parents an orphan at all (Raymond Chen, devblogs "Old New Thing",
    2015-04-03): the recorded ParentProcessId either names a dead process, or names a LIVE one
    that was created AFTER this pid -- the pid got reused by an unrelated process once the real
    parent exited, and Windows never updates the child's own stale record of it. Either shape
    means orphaned. A live parent created BEFORE this pid, the ordinary shape, means not."""
    if sys.platform == "darwin":
        return _is_orphan_posix_ppid(["ps", "-o", "ppid=", "-p", str(pid)])
    if sys.platform.startswith("linux"):
        return _is_orphan_linux(pid)
    if sys.platform.startswith("win"):
        return _is_orphan_windows(pid)
    return None


def _is_orphan_linux(pid: int):
    try:
        with open("/proc/%d/status" % pid, encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("PPid:"):
                    try:
                        return int(line.split(":", 1)[1].strip()) == 1
                    except ValueError:
                        return None
    except Exception:
        return None
    return None  # no `PPid:` line at all: the format did not match what this read expects


def _is_orphan_posix_ppid(argv):
    try:
        answer = subprocess.run(argv, capture_output=True, text=True, timeout=5)
    except Exception:
        return None
    if answer.returncode != 0:
        return None
    text = answer.stdout.strip()
    if not text:
        return None
    try:
        return int(text) == 1
    except ValueError:
        return None


def _is_orphan_windows(pid: int):
    """MEASURED gap this closes: `guard._process_start_ms_windows` answers a real creation
    time for a pid that has ALREADY EXITED, as long as anything on the machine still holds one
    handle open to it (a `subprocess.Popen` object that has not been garbage-collected yet is
    enough) -- Windows keeps that pid's process object alive as a zombie, exactly like a POSIX
    zombie, until every handle closes. `OpenProcess` success alone (guard's own oracle, built
    for a DIFFERENT question -- whether a session's OWN recorded pid is still that same
    process) is therefore not enough here to tell "parent is dead" from "parent is running":
    `_process_running_windows` below checks `GetExitCodeProcess` for `STILL_ACTIVE`, which a
    zombie never answers, before anything is trusted as "the parent is alive."."""
    parent_pid = _parent_pid_windows(pid)
    if parent_pid is None:
        return None
    running = _process_running_windows(parent_pid)
    if running is None:
        return None
    if not running:
        return True  # parent CONFIRMED not running (dead, or a zombie no one can act through)
    # The parent IS genuinely running -- but it could be an UNRELATED process that received
    # this same pid after the real parent exited and was fully reaped (Windows never blocks
    # pid reuse the way a zombie blocks it). Creation-time order is what tells the two apart.
    child_start = guard._process_start_ms_windows(pid)
    if child_start is None or child_start is guard.PROCESS_START_UNREADABLE:
        return None  # can't confirm the child's OWN start either, so no comparison is possible
    parent_start = guard._process_start_ms_windows(parent_pid)
    if parent_start is None or parent_start is guard.PROCESS_START_UNREADABLE:
        return None  # already confirmed running, above -- an unreadable start here is a race
    return parent_start > child_start  # parent created AFTER this pid: a recycled, unrelated pid


def _process_running_windows(pid: int):
    """True when PID answers `GetExitCodeProcess` with `STILL_ACTIVE` (259): genuinely
    running right now, not a zombie. False when `OpenProcess` fails with error 87 (no such
    process at all) or `GetExitCodeProcess` answers a real exit code (a zombie: it exited, but
    something still holds a handle open, so its pid has not been recycled yet). None when the
    read could not tell (access denied, or any other unexpected error)."""
    import ctypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False if ctypes.GetLastError() == 87 else None
    try:
        code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return None
        return code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def _parent_pid_windows(pid: int):
    """One `Process32First`/`Process32Next` walk of a `CreateToolhelp32Snapshot(
    TH32CS_SNAPPROCESS)` table, the same table `_list_all_pids_windows` below walks for every
    pid at once. `None` when the pid is not found in the table at all (it exited between being
    listed and being asked about here) or the snapshot itself could not be taken."""
    for entry_pid, entry_ppid in _toolhelp_process_entries():
        if entry_pid == pid:
            return entry_ppid
    return None


def _toolhelp_process_entries():
    """Every (pid, ppid) pair on this machine right now, via one `CreateToolhelp32Snapshot`.
    Empty (never `None`) when the snapshot itself could not be taken -- callers that need to
    distinguish "empty" from "unreadable" wrap this, this generator itself just stops."""
    import ctypes

    class ProcessEntry32(ctypes.Structure):
        _fields_ = [
            ("dwSize", ctypes.c_ulong), ("cntUsage", ctypes.c_ulong),
            ("th32ProcessID", ctypes.c_ulong), ("th32DefaultHeapID", ctypes.c_void_p),
            ("th32ModuleID", ctypes.c_ulong), ("cntThreads", ctypes.c_ulong),
            ("th32ParentProcessID", ctypes.c_ulong), ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", ctypes.c_ulong), ("szExeFile", ctypes.c_char * 260),
        ]

    TH32CS_SNAPPROCESS = 0x00000002
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    kernel32.CreateToolhelp32Snapshot.argtypes = [ctypes.c_ulong, ctypes.c_ulong]
    kernel32.Process32First.argtypes = [ctypes.c_void_p, ctypes.POINTER(ProcessEntry32)]
    kernel32.Process32Next.argtypes = [ctypes.c_void_p, ctypes.POINTER(ProcessEntry32)]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    invalid_handle = (1 << (8 * ctypes.sizeof(ctypes.c_void_p))) - 1  # INVALID_HANDLE_VALUE
    if not snapshot or snapshot == invalid_handle:
        return
    try:
        entry = ProcessEntry32()
        entry.dwSize = ctypes.sizeof(ProcessEntry32)
        if not kernel32.Process32First(snapshot, ctypes.byref(entry)):
            return
        while True:
            yield entry.th32ProcessID, entry.th32ParentProcessID
            if not kernel32.Process32Next(snapshot, ctypes.byref(entry)):
                return
    finally:
        kernel32.CloseHandle(snapshot)


def list_all_pids():
    """Return EVERY pid on this machine right now, or `None` when the enumeration itself
    failed. Used only by `processes_in`'s pre-removal check: "if the whole listing or the
    pre-check enumeration fails, KEEP everything and remove no worktree" (this build's brief)."""
    if sys.platform == "darwin" or sys.platform.startswith("linux"):
        return _list_all_pids_posix()
    if sys.platform.startswith("win"):
        return _list_all_pids_windows()
    return None


def _list_all_pids_posix():
    if sys.platform.startswith("linux"):
        try:
            return [int(name) for name in os.listdir("/proc") if name.isdigit()]
        except Exception:
            return None
    try:
        answer = subprocess.run(["ps", "-axo", "pid="], capture_output=True, text=True, timeout=10)
    except Exception:
        return None
    if answer.returncode != 0:
        return None
    pids = []
    for line in answer.stdout.splitlines():
        line = line.strip()
        if line.isdigit():
            pids.append(int(line))
    return pids


def _list_all_pids_windows():
    pids = [pid for pid, _ppid in _toolhelp_process_entries()]
    return pids or None  # an empty snapshot on a real machine means the snapshot call failed


def is_current_user_process(pid: int):
    """True when PID is owned by the account running this sweep. False when it is confirmed
    owned by someone else. None when the read could not tell -- reported as
    `unreadable-subject`, same as every other tri-state read in this file."""
    if sys.platform == "darwin":
        return _is_current_user_posix_uid(["ps", "-o", "uid=", "-p", str(pid)])
    if sys.platform.startswith("linux"):
        return _is_current_user_linux(pid)
    if sys.platform.startswith("win"):
        return _is_current_user_windows(pid)
    return None


def _is_current_user_linux(pid: int):
    try:
        uid = os.stat("/proc/%d" % pid).st_uid
    except Exception:
        return None
    try:
        return uid == os.getuid()
    except AttributeError:
        return None  # no os.getuid at all: not this platform's real shape


def _is_current_user_posix_uid(argv):
    try:
        answer = subprocess.run(argv, capture_output=True, text=True, timeout=5)
    except Exception:
        return None
    if answer.returncode != 0:
        return None
    text = answer.stdout.strip()
    if not text:
        return None
    try:
        uid = int(text)
    except ValueError:
        return None
    try:
        return uid == os.getuid()
    except AttributeError:
        return None


def _is_current_user_windows(pid: int):
    """`OpenProcessToken` + `GetTokenInformation(TokenUser)` on PID, compared to the same read
    on this sweep's own process. Both sides are converted to a `ConvertSidToStringSidW` string
    rather than compared as raw SIDs, so the comparison is a plain string equality, not a
    binary-buffer one."""
    mine = _token_user_sid_windows(None)
    theirs = _token_user_sid_windows(pid)
    if mine is None or theirs is None:
        return None
    return mine == theirs


def _token_user_sid_windows(pid):
    """PID's own TokenUser SID string, or -- PID `None` -- this sweep's OWN process's SID
    string. `None` on any failure: PEB-adjacent reads on someone else's process routinely
    refuse for the same access-control reason `_process_cwd_windows` does, and that refusal is
    itself the signal that a process is not ours (brief: "or treat 'PEB read refused' as not
    ours" -- honoured here by this function answering `None`, which `is_current_user_process`
    already treats as unreadable rather than a guessed "yes")."""
    import ctypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    TOKEN_QUERY = 0x0008
    TOKEN_USER = 1
    kernel32 = ctypes.windll.kernel32
    advapi32 = ctypes.windll.advapi32

    # Same measured overflow this file's own `_process_cwd_windows` comment names: a real SID
    # pointer, read out of the TOKEN_USER buffer below, is a full heap address and routinely
    # exceeds ctypes' untyped default of `c_int`. Every handle/pointer here is typed explicitly.
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    advapi32.OpenProcessToken.argtypes = [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi32.GetTokenInformation.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_ulong),
    ]
    advapi32.ConvertSidToStringSidW.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
    ]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]

    if pid is None:
        process_handle = kernel32.GetCurrentProcess()
        owns_handle = False
    else:
        process_handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        owns_handle = True
        if not process_handle:
            return None
    try:
        token = ctypes.c_void_p()
        if not advapi32.OpenProcessToken(process_handle, TOKEN_QUERY, ctypes.byref(token)):
            return None
        try:
            size = ctypes.c_ulong(0)
            advapi32.GetTokenInformation(token, TOKEN_USER, None, 0, ctypes.byref(size))
            if size.value == 0:
                return None
            buf = ctypes.create_string_buffer(size.value)
            if not advapi32.GetTokenInformation(token, TOKEN_USER, buf, size.value,
                                                 ctypes.byref(size)):
                return None
            sid_ptr = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0]  # TOKEN_USER.Sid
            if not sid_ptr:
                return None
            sid_string_ptr = ctypes.c_void_p()
            if not advapi32.ConvertSidToStringSidW(sid_ptr, ctypes.byref(sid_string_ptr)):
                return None
            try:
                return ctypes.wstring_at(sid_string_ptr)
            finally:
                kernel32.LocalFree(sid_string_ptr)
        finally:
            kernel32.CloseHandle(token)
    finally:
        if owns_handle:
            kernel32.CloseHandle(process_handle)


def _cwd_under_checkout(cwd: str, checkout_path: str) -> bool:
    """True when CWD sits at or under CHECKOUT_PATH, matched as a normalised path PREFIX.

    `os.path.realpath` first, never `guard._path_identity`'s `os.stat`-based fallback: a git
    worktree that has ALREADY been removed (brief point 1: "including a worktree path that is
    already removed") can have nothing left to `os.stat`, and `realpath` never raises for a
    path that does not exist -- it degrades gracefully to a plain normalised string for the
    part that is gone, which is exactly `os.path.normpath`'s own behaviour for that case.

    MEASURED why plain `normpath` alone (an earlier version of this function) is not enough
    while the checkout DOES still exist: on this Windows machine, `tempfile.mkdtemp()`
    sometimes returns a path through a SHORT (8.3) component (`SHIVAM~1`), while `git
    worktree list` always reports the LONG form (`ShivamSemwal`) for the identical directory.
    `normpath` normalises slashes and case but never expands an 8.3 name, so the two never
    shared a prefix as plain strings -- a real listener's own cwd, read back from the OS, then
    matched NEITHER form reliably. `realpath` resolves the short form to the long one (or vice
    versa) whenever the directory still exists, so both sides land on the same spelling."""
    try:
        cwd_norm = os.path.normcase(os.path.realpath(cwd)) + os.sep
        target_norm = os.path.normcase(os.path.realpath(checkout_path)) + os.sep
    except Exception:
        return False
    return cwd_norm.startswith(target_norm)


def _matching_checkout(cwd: str, checkout_paths):
    """The first entry of CHECKOUT_PATHS that CWD sits under, or `None` when it sits under
    none of them."""
    for path in checkout_paths:
        if _cwd_under_checkout(cwd, path):
            return path
    return None


def find_swept_listeners(checkout_paths):
    """Return `[{"pid", "port", "cwd", "checkout"}]` for every TCP listener whose cwd sits
    under one of CHECKOUT_PATHS (this repository's primary checkout plus every worktree
    `parse_worktree_list` named, including an already-removed one). A listener outside every
    one of them is left out entirely -- it is never even reported, let alone acted on, because
    this sweep has no standing to decide anything about a program outside the repositories it
    covers. `None` only when the machine-wide listener enumeration itself failed; a listener
    whose OWN cwd could not be read is instead left out silently, the same as one outside every
    checkout, because a cwd this sweep cannot read cannot be matched to a checkout it covers
    either -- it is not evidence of anything, in either direction."""
    listeners = list_listeners()
    if listeners is None:
        return None
    found = []
    for entry in listeners:
        cwd = process_cwd(entry["pid"])
        if cwd is None:
            continue
        checkout = _matching_checkout(cwd, checkout_paths)
        if checkout is None:
            continue
        found.append({"pid": entry["pid"], "port": entry["port"], "cwd": cwd,
                      "checkout": checkout})
    return found


def decide_listener(entry: dict):
    """Return one decision dict: {"pid", "port", "cwd", "checkout", "command", "action":
    "reap"|"keep", "reason"}. ENTRY is one of `find_swept_listeners`'s own results, already
    matched to a checkout this sweep covers.

    Reapable only when ALL three of these answer a confirmed yes, in this order: orphaned; no
    live Claude session has a cwd in the same checkout (guard.py's own tested oracle, reused
    verbatim, never re-derived here); owned by the current user. Any `None` along the way
    means keep, reported as `unreadable-subject` -- this build's brief, "An unreadable fact
    means KEEP." """
    pid = entry["pid"]
    base = dict(entry, command=process_command(pid))

    orphan = is_orphan(pid)
    if orphan is None:
        return {**base, "action": "keep", "reason": "unreadable-subject"}
    if not orphan:
        return {**base, "action": "keep", "reason": "not-orphaned"}

    live = guard.worktree_live_session(entry["checkout"])
    if live is None:
        return {**base, "action": "keep", "reason": "unreadable-subject"}
    if live:
        return {**base, "action": "keep", "reason": "live-session"}

    owner = is_current_user_process(pid)
    if owner is None:
        return {**base, "action": "keep", "reason": "unreadable-subject"}
    if not owner:
        return {**base, "action": "keep", "reason": "not-current-user"}

    return {**base, "action": "reap", "reason": "orphaned-listener"}


def processes_in(path: str):
    """Return `(inside_pids, unreadable_pids)`, both lists (possibly empty), for the pre-removal
    check in `decide_worktree`. `inside_pids` is `None` (with `unreadable_pids` also `None`)
    when the pid ENUMERATION itself failed -- the brief's own rule: "if the whole listing ... or
    the pre-check enumeration fails, KEEP everything and remove no worktree."

    A single pid whose OWN cwd cannot be read is OUT OF SCOPE, never a reason to keep --
    MEASURED, not the first guess: on a real Windows machine, 272 of 580 running processes
    answered `None` to `process_cwd` here, almost all of them owned by another account or
    otherwise access-protected. Naming those as a reason to keep would make this pre-check
    refuse to ever reap anything, on any real machine, which is a worse outcome than the leak
    it exists to prevent. `unreadable_pids` is still returned, so a caller MAY report how many
    were skipped this way, but `decide_worktree` does not let it block a removal -- the same
    direction the original brief already named for a different read ("A single process of
    another user, or one that refuses access, is out of scope. Count it in the report, never
    act on it"), extended here from the owner check to this one, for the measured reason
    above, and identical on POSIX and Windows: both dispatch through this same `process_cwd`,
    with no OS branch anywhere in this function."""
    pids = list_all_pids()
    if pids is None:
        return None, None
    inside = []
    unreadable = []
    for pid in pids:
        cwd = process_cwd(pid)
        if cwd is None:
            unreadable.append(pid)
            continue
        if _cwd_under_checkout(cwd, path):
            inside.append(pid)
    return inside, unreadable


# ------------------------------------------------------------------ acting on a reapable listener
#
# Reached only from `sweep_repo`'s own `if confirm and decision["action"] == "reap":` gate,
# exactly the shape branches and worktrees already use. A signal is sent by PID NUMBER alone,
# never by a name or a command-line pattern (CLAUDE.md: "Never kill a process you did not
# start. Treat `pkill -f` and `lsof -t` as machine-wide.") -- every pid reaching `send_signal`
# already passed `decide_listener`'s full keep-or-reap rule; this function does no matching of
# its own, and escalates nothing on its own past this one signal.


def send_signal(pid: int) -> bool:
    """POSIX: SIGTERM. Windows: `TerminateProcess` by pid (never `taskkill /IM`, which matches
    by NAME). Return True only when the signal was actually delivered -- not proof of death,
    only of delivery; the grace-period check after it is the read that answers death."""
    if sys.platform.startswith("win"):
        return _terminate_windows(pid)
    try:
        os.kill(pid, signal.SIGTERM)
        return True
    except Exception:
        return False


def _terminate_windows(pid: int) -> bool:
    import ctypes

    PROCESS_TERMINATE = 0x0001
    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel32.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
    if not handle:
        return False
    try:
        return bool(kernel32.TerminateProcess(handle, 1))
    finally:
        kernel32.CloseHandle(handle)


def pid_alive(pid: int) -> bool:
    """Observational only, run AFTER a signal has already been sent, to REPORT whether it took
    -- never consulted beforehand to decide reap-or-keep (CLAUDE.md: "a recovery control must
    not depend on the state it recovers"). POSIX: `os.kill(pid, 0)` -- `ProcessLookupError`
    means gone, `PermissionError` means alive but not ours. Windows: reuses
    `_process_running_windows` (a zombie -- an already-exited pid some other handle still
    holds open -- must read as gone here too, the same as everywhere else in this file)."""
    if sys.platform.startswith("win"):
        return _process_running_windows(pid) is True
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return False


def reap_listener(decision: dict):
    if not send_signal(decision["pid"]):
        decision["error"] = "signal could not be sent"


LISTENER_GRACE_PERIOD_SECONDS = 3  # ponytail: fixed, not a flag. Add --grace-period the day a
                                    # real server needs longer than 3s to flush and exit on SIGTERM.


# ------------------------------------------------------------------ the tombstone


def default_restore_log_path() -> str:
    return os.path.join(guard.config_dir(), "janitor", "restore-log.jsonl")


def append_restore_log(path: str, repo: str, branch: str, commit: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    line = json.dumps({
        "repo": repo, "branch": branch, "commit": commit,
        "time_ms": int(time.time() * 1000),
    })
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def reap_branch(root: str, branch: str, decision: dict, restore_log_path: str):
    """Write the tombstone, log it, THEN delete. In that order: a delete that ran before its
    tombstone landed could lose the branch's only pointer to work the log has not recorded yet."""
    tip = guard._git(root, "rev-parse", "refs/heads/" + branch)
    if tip is None or tip.returncode != 0:
        decision["error"] = "could not resolve the branch tip; branch left alone"
        return
    commit = tip.stdout.strip()
    tomb = guard._git(root, "update-ref", TOMBSTONE_REF_PREFIX + branch, commit)
    if tomb is None or tomb.returncode != 0:
        decision["error"] = "tombstone write failed; branch NOT deleted"
        return
    append_restore_log(restore_log_path, root, branch, commit)
    delete = guard._git(root, "branch", "-D", branch)
    if delete is None or delete.returncode != 0:
        decision["error"] = "delete failed after the tombstone landed: %s" % (
            delete.stderr.strip() if delete is not None else "git gave no answer"
        )


def remove_worktree(root: str, path: str, decision: dict):
    answer = guard._git(root, "worktree", "remove", path)
    if answer is None or answer.returncode != 0:
        decision["error"] = "remove failed: %s" % (
            answer.stderr.strip() if answer is not None else "git gave no answer"
        )


# ------------------------------------------------------------------ the purge
#
# Age comes from the restore log's OWN time_ms field, never from the tombstone ref's mtime (an
# mtime changes for reasons unrelated to the reap: a repack, a filesystem touch, a clone).


def read_restore_log(path: str):
    if not os.path.isfile(path):
        return []
    entries = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except Exception:
                continue  # one bad line does not make the rest of the log unreadable
    return entries


def purge_tombstones(restore_log_path: str, confirm: bool, now_ms=None):
    """Return one decision dict per log entry: {"repo", "branch", "action": "purge"|"keep",
    "reason"}. With confirm, a "purge" decision also drops that repository's tombstone ref."""
    now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    decisions = []
    for entry in read_restore_log(restore_log_path):
        repo = entry.get("repo")
        branch = entry.get("branch")
        when = entry.get("time_ms")
        if not isinstance(repo, str) or not repo or not isinstance(branch, str) or not branch \
                or not isinstance(when, (int, float)) or isinstance(when, bool):
            decisions.append({"repo": repo, "branch": branch, "action": "keep",
                               "reason": "unreadable-entry"})
            continue
        age_ms = now_ms - when
        if age_ms < TOMBSTONE_TTL_MS:
            decisions.append({"repo": repo, "branch": branch, "action": "keep",
                               "reason": "not yet 90 days (%d days old)" % (age_ms // 86400000)})
            continue
        decision = {"repo": repo, "branch": branch, "action": "purge",
                     "reason": "past 90 days (%d days old)" % (age_ms // 86400000)}
        decisions.append(decision)
        if confirm:
            dropped = guard._git(repo, "update-ref", "-d", TOMBSTONE_REF_PREFIX + branch)
            if dropped is None or dropped.returncode != 0:
                decision["error"] = "drop failed: %s" % (
                    dropped.stderr.strip() if dropped is not None else "git gave no answer"
                )
    return decisions


# ------------------------------------------------------------------ sweeping one repository


def sweep_repo(root: str, confirm: bool, restore_log_path: str):
    result = {"root": root, "refused": None, "branches": [], "worktrees": [], "listeners": []}

    sweep_enabled, protected_prefixes, optout_ok = load_optout(root)
    if not optout_ok:
        result["refused"] = "unreadable-optout"
        return result
    if not sweep_enabled:
        result["refused"] = "opted-out"
        return result

    base = guard.resolve_default_base(root)
    if base is None:
        result["refused"] = "no-default-base"
        return result

    entries = parse_worktree_list(root)
    if entries is None:
        result["refused"] = "unreadable-worktree-list"
        return result

    checked_out_branches = {e["branch"] for e in entries if e.get("branch")}

    branches = list_local_branches(root)
    if branches is None:
        result["refused"] = "unreadable-branch-list"
        return result

    for branch in branches:
        decision = decide_branch(root, base, branch, protected_prefixes, checked_out_branches)
        result["branches"].append(decision)
        if confirm and decision["action"] == "reap":
            reap_branch(root, branch, decision, restore_log_path)

    for entry in entries:
        if entry.get("bare"):
            continue
        is_primary = _is_primary_checkout(entry["path"])
        if is_primary is True:
            continue  # the clone's one primary checkout: no decision is ever recorded against it
        if is_primary is None:
            # Could not tell whether this IS the primary checkout. Rule 7's direction: an
            # unreadable subject means keep, never a guess that it is safe to evaluate.
            result["worktrees"].append(
                {"path": entry["path"], "action": "keep", "reason": "unreadable-subject"}
            )
            continue
        decision = decide_worktree(root, entry)
        result["worktrees"].append(decision)
        if confirm and decision["action"] == "reap":
            remove_worktree(root, entry["path"], decision)

    checkout_paths = [root] + [e["path"] for e in entries if not e.get("bare")]
    listener_entries = find_swept_listeners(checkout_paths)
    if listener_entries is None:
        result["listeners"] = None  # the machine-wide listener enumeration itself failed
    else:
        for entry in listener_entries:
            decision = decide_listener(entry)
            result["listeners"].append(decision)
            if confirm and decision["action"] == "reap":
                reap_listener(decision)

    return result


# ------------------------------------------------------------------ reporting


def print_sweep_report(results, confirm: bool, out=sys.stdout):
    mode = "CONFIRM: reaping for real" if confirm else "PREVIEW: nothing is deleted"
    print("janitor sweep -- %s" % mode, file=out)

    branch_counts = Counter()
    worktree_counts = Counter()
    listener_counts = Counter()
    refused_repos = []
    unreadable_listener_repos = []

    for result in results:
        print("", file=out)
        print("== %s ==" % result["root"], file=out)
        if result["refused"]:
            refused_repos.append((result["root"], result["refused"]))
            print("  REFUSED: %s -- reaps nothing in this repository" % result["refused"],
                  file=out)
            continue
        if not result["branches"] and not result["worktrees"] and not result["listeners"]:
            print("  nothing to examine", file=out)
        for b in result["branches"]:
            branch_counts[(b["action"], b["reason"].split(":", 1)[0])] += 1
            tag = "REAP" if b["action"] == "reap" else "KEEP"
            line = "  branch    %-4s %-40s %s" % (tag, b["name"], b["reason"])
            if b.get("error"):
                line += "  [ERROR: %s]" % b["error"]
            print(line, file=out)
        for w in result["worktrees"]:
            worktree_counts[(w["action"], w["reason"].split(":", 1)[0])] += 1
            tag = "REAP" if w["action"] == "reap" else "KEEP"
            line = "  worktree  %-4s %-60s %s" % (tag, w["path"], w["reason"])
            if w.get("error"):
                line += "  [ERROR: %s]" % w["error"]
            print(line, file=out)
        if result["listeners"] is None:
            unreadable_listener_repos.append(result["root"])
            print("  listener  UNREADABLE -- the machine-wide listener enumeration failed; "
                  "no listener in this repository was examined", file=out)
        else:
            for entry in result["listeners"]:
                listener_counts[(entry["action"], entry["reason"].split(":", 1)[0])] += 1
                tag = "REAP" if entry["action"] == "reap" else "KEEP"
                line = "  listener  %-4s pid=%-8s port=%-6s %-50s %s" % (
                    tag, entry["pid"], entry["port"], entry.get("cwd") or "?", entry["reason"],
                )
                if entry.get("command"):
                    line += "  [%s]" % entry["command"]
                if entry.get("error"):
                    line += "  [ERROR: %s]" % entry["error"]
                print(line, file=out)

    print("", file=out)
    print("== summary ==", file=out)
    if refused_repos:
        for repo, reason in refused_repos:
            print("  repository refused: %s (%s)" % (repo, reason), file=out)
    else:
        print("  repositories refused: 0", file=out)
    total_branches = sum(branch_counts.values())
    print("  local branches examined: %d" % total_branches, file=out)
    for (action, reason), n in sorted(branch_counts.items()):
        print("    %-5s %-20s %d" % (action, reason, n), file=out)
    total_worktrees = sum(worktree_counts.values())
    print("  worktrees examined: %d" % total_worktrees, file=out)
    for (action, reason), n in sorted(worktree_counts.items()):
        print("    %-5s %-20s %d" % (action, reason, n), file=out)
    total_listeners = sum(listener_counts.values())
    print("  TCP listeners examined: %d" % total_listeners, file=out)
    for (action, reason), n in sorted(listener_counts.items()):
        print("    %-5s %-20s %d" % (action, reason, n), file=out)
    if unreadable_listener_repos:
        print("  repositories with an unreadable listener enumeration: %d"
              % len(unreadable_listener_repos), file=out)


def reaped_listener_decisions(results):
    """Every listener decision, across RESULTS, that was signalled for real (action "reap",
    and its repository's listener enumeration was readable in the first place). Used by `main`
    to run the grace-period check exactly once, after every repository's signal has already
    been sent -- not once per repository, which would multiply the wait."""
    found = []
    for result in results:
        if result["refused"] or result["listeners"] is None:
            continue
        for entry in result["listeners"]:
            if entry["action"] == "reap":
                found.append(entry)
    return found


def print_grace_period_report(reaped, out=sys.stdout):
    """Wait `LISTENER_GRACE_PERIOD_SECONDS`, once, then report which signalled pids are still
    alive. This sweep never escalates past the one signal it already sent -- it only reports."""
    if not reaped:
        return
    print("", file=out)
    print("waiting %.0fs, then checking every signalled listener ..."
          % LISTENER_GRACE_PERIOD_SECONDS, file=out)
    time.sleep(LISTENER_GRACE_PERIOD_SECONDS)
    still_alive = [d for d in reaped if pid_alive(d["pid"])]
    if still_alive:
        print("  STILL ALIVE after the grace period (never escalated further):", file=out)
        for d in still_alive:
            print("    pid=%s port=%s %s" % (d["pid"], d["port"], d.get("cwd") or "?"), file=out)
    else:
        print("  every signalled listener is gone.", file=out)


def print_purge_report(decisions, confirm: bool, out=sys.stdout):
    mode = "CONFIRM: dropping tombstones for real" if confirm else "PREVIEW: nothing is dropped"
    print("janitor purge -- %s" % mode, file=out)
    counts = Counter()
    for d in decisions:
        counts[d["action"]] += 1
        tag = "PURGE" if d["action"] == "purge" else "KEEP "
        line = "  %s %-30s %-40s %s" % (tag, d.get("repo"), d.get("branch"), d["reason"])
        if d.get("error"):
            line += "  [ERROR: %s]" % d["error"]
        print(line, file=out)
    print("", file=out)
    print("tombstones examined: %d, purge: %d, keep: %d"
          % (len(decisions), counts.get("purge", 0), counts.get("keep", 0)), file=out)


# ------------------------------------------------------------------ CLI


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="The machine-wide janitor sweep. Preview by default; --confirm to reap."
    )
    parser.add_argument("roots", nargs="*", help="repository roots to sweep")
    parser.add_argument("--discover", metavar="DIR",
                         help="sweep DIR's own checkouts, used only when no ROOT is given")
    parser.add_argument("--confirm", action="store_true",
                         help="actually delete branches/worktrees or drop tombstones")
    parser.add_argument("--purge", action="store_true",
                         help="purge tombstones past 90 days instead of sweeping")
    parser.add_argument("--restore-log", metavar="PATH",
                         help="override the restore log path (default: under the config dir)")
    parser.add_argument("--settings-path", metavar="PATH",
                         help="testing only: overrides the settings.json read for janitor.roots")
    args = parser.parse_args(argv)

    restore_log_path = args.restore_log or default_restore_log_path()

    if args.purge:
        decisions = purge_tombstones(restore_log_path, args.confirm)
        print_purge_report(decisions, args.confirm)
        return 0

    roots = [os.path.abspath(r) for r in args.roots]
    if not roots:
        if args.discover:
            discover_root = os.path.abspath(args.discover)
            roots = discover_repos(discover_root)
            if not roots:
                print("janitor: no repositories found under %s" % discover_root, file=sys.stderr)
                return 1
        else:
            configured, ok = load_janitor_roots_setting(args.settings_path)
            if not ok:
                print(
                    "janitor: refusing to discover -- settings.json's janitor.roots is "
                    "malformed. Fix it, or pass ROOT/--discover explicitly", file=sys.stderr,
                )
                return 1
            search_roots = configured if configured is not None else default_discover_roots()
            roots = discover_repos_multi(search_roots)
            if not roots:
                where = ", ".join(search_roots) if search_roots else \
                    "any default root (~/Developer, ~/Clones, ~/src, ~/code, ~/repos)"
                print("janitor: no repositories found under %s" % where, file=sys.stderr)
                return 1

    results = [sweep_repo(root, args.confirm, restore_log_path) for root in roots]
    print_sweep_report(results, args.confirm)
    if args.confirm:
        print_grace_period_report(reaped_listener_decisions(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
