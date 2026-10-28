#!/usr/bin/env python3
"""The machine-wide janitor sweep.

Governed by the-janitor-is-one-machine-wide-sweep. Reaps local branches that hold no unique work
and removes git worktrees that no session still uses, across every repository the sweep is
pointed at, or discovers. Removal limits: when-a-worktree-may-be-removed. The orphan stop:
unattended-sweep-stops-proven-orphans.

Every keep-or-reap boolean comes from hooks/git_reads.py's own primitives (`resolve_default_base`,
`session_is_live`, the `branch_*` tests, `worktree_locked`, `porcelain`): dirty, locked, live,
ancestor, cherry, remote-contains. Never
re-derive one here; a second copy of that logic is the outcome to avoid. This module keeps only
orchestration: which repositories, which branches, which order, the preview report, the
tombstone, and the 90-day purge.

Preview is the default. The run fetches and prunes remote-tracking refs; no branch or worktree is
deleted until `--confirm` is passed. The sweep never pushes to a remote. The one program it can
stop is an orphaned TCP listener inside a repository this sweep already covers, once every read on it is a confirmed "yes, reap": it is orphaned (a per-OS read);
no live Claude session has a cwd in the same checkout (git_reads.py's own oracle); the current user
owns it. An unreadable answer to any one of the three means KEEP. `--confirm` signals a reapable
pid by NUMBER alone, never by a name or a command-line pattern, and never escalates past that
one signal.

Before a worktree is removed, the sweep also checks for ANY process (not only a listener) whose
cwd sits inside it, and keeps the worktree, naming the pids, when one is found. On Windows,
`git worktree remove` against a directory a live process holds open does a PARTIAL delete
(files gone, an empty directory left, the worktree still registered). Refusing to call it at all
keeps that state from happening.

Usage:
    python3 janitor/sweep.py [ROOT ...]                 # preview a sweep of the named roots
    python3 janitor/sweep.py --discover DIR              # preview a sweep of DIR's own checkouts
    python3 janitor/sweep.py ROOT --confirm              # actually reap, no deadline
    python3 janitor/sweep.py ROOT --confirm --deadline-seconds N
                                                         # the SessionEnd run: judge no tree later
                                                         # than min(12 s, N minus 7.5 s) from the
                                                         # start of the pass. Only a run with this
                                                         # flag has a budget
    python3 janitor/sweep.py --purge                     # preview which tombstones are past 90 days
    python3 janitor/sweep.py --purge --confirm           # actually drop tombstones past 90 days

With no ROOT and no `--discover`, the sweep reads `janitor.roots` from this repository's own
settings.json. Absent, it discovers under every one of `~/Developer`, `~/Clones`, `~/src`,
`~/code`, and `~/repos` that exists on this machine, combined into one list. Present but
malformed, not a list of strings, the sweep refuses to discover
anything and says why. It never guesses at a wish it cannot read. `--discover DIR` bypasses
`janitor.roots` and the default list entirely. Discovery lists a directory's immediate children
whose `.git` is a DIRECTORY (an ordinary checkout), never a FILE (a linked worktree of some other
checkout): a linked worktree's branches already belong to its primary checkout's sweep, and
sweeping it a second time as its own "repository" would apply the keep rule against the wrong
tree entirely.
"""
import argparse
import calendar
import concurrent.futures
import hashlib
import json
import math
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import threading
import time
import uuid
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO_ROOT, "hooks"))
import git_reads  # noqa: E402  (the preview cache patches the reads where they live; no guard module loads)
try:
    import _nowindow  # the one home of a no-window child start (hooks/_nowindow.py)
except ImportError:  # a hook never dies for a missing helper (it lands a moment after the hook in an install)
    _nowindow = subprocess
try:
    import temp_sweep  # the Windows temp-folder step (janitor/temp_sweep.py)
except ImportError:  # guard.py imports this file for its sim-boot refusal; a missing step must not break it
    temp_sweep = None

OPTOUT_FILENAME = os.path.join(".claude", "janitor.json")
DEFAULT_PROTECTED_PREFIXES = ("backup/",)
TOMBSTONE_REF_PREFIX = "refs/janitor/reaped/"
TOMBSTONE_TTL_MS = 90 * 24 * 60 * 60 * 1000  # git's own reflog-retention number


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
    """Claude Desktop's scratch-workspace root, one per platform. macOS:
    `~/Library/Application Support/Claude/scratch-workspaces`. Windows:
    `%APPDATA%\\Claude\\scratch-workspaces`, with APPDATA read from the environment, never a
    hardcoded user. Linux: none, because that layout is unmeasured and no path is guessed (the
    direction `load_janitor_roots_setting` takes for any wish it cannot read).

    Those leaves hold scratch files, not checkouts, so `discover_repos` (an immediate child whose
    `.git` is a directory) finds nothing there today. The root is still added: a linked worktree
    left behind there is then covered the day it appears, at no cost while it is empty."""
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
    order. Clones can be split across several of these directories, so it does not stop at the
    first hit.

    `os.path.normpath` is applied to each candidate. Each is written POSIX-style, like
    `~/Developer`, and `os.path.expanduser` replaces only the leading `~`. On Windows the result
    then mixes both separators in one path, which plain string equality sees as a different path
    from the same directory built with `os.path.join`. `discover_repos_multi` de-duplicates with
    a `set()`, a plain string match, so `normpath` fixes every candidate once, where they all
    pass.
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
    return _optout_fields(read_optout(root))


def _optout_fields(data):
    """(sweep_enabled, protected_prefixes, ok) from `read_optout`'s dict (None means unreadable)."""
    if data is None:
        return False, (), False
    sweep_enabled = data.get("sweep", True)
    prefixes = list(DEFAULT_PROTECTED_PREFIXES)
    for item in data.get("protectedPrefixes", []):
        if item:
            prefixes.append(item)
    return sweep_enabled, tuple(prefixes), True


def read_optout(root: str):
    """The one reader of `.claude/janitor.json`: its keys as a dict ({} when the file is absent),
    or None when the file is unreadable or a key it holds is mis-shaped (`sweep` not a boolean,
    `protectedPrefixes`, `huskNames` or `buildDirs` not a list of strings). `load_optout` and `find_husks`
    both read through this."""
    path = os.path.join(root, OPTOUT_FILENAME)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    if "sweep" in data and not isinstance(data["sweep"], bool):
        return None
    for key in ("protectedPrefixes", "huskNames", "buildDirs"):
        if key in data and (not isinstance(data[key], list)
                            or not all(isinstance(item, str) for item in data[key])):
            return None
    return data


# ------------------------------------------------------------------ reading a repository's state


def list_local_branches(where: str):
    """Return every local branch's short name, or None when the read failed."""
    answer = git_reads._git(where, "for-each-ref", "--format=%(refname:short)", "refs/heads")
    if answer is None or answer.returncode != 0:
        return None
    return [line.strip() for line in answer.stdout.splitlines() if line.strip()]


def merged_batch(where: str, base: str):
    """The local branches already in BASE, from ONE `for-each-ref --merged`: {"base": BASE,
    "names": the branch names, "tips": their commit ids}. None when the read failed. A branch is in
    the batch exactly when `merge-base --is-ancestor <branch> BASE` would say yes. It proves "in
    main" for every branch and every worktree HEAD at once. What it does not hold is asked of the
    repository one by one (`cherry`), and a read that fails keeps."""
    answer = git_reads._git(where, "for-each-ref", "--merged=" + base,
                        "--format=%(objectname) %(refname:short)", "refs/heads")
    if answer is None or answer.returncode != 0:
        return None
    names, tips = set(), set()
    for line in answer.stdout.splitlines():
        sha, _, name = line.strip().partition(" ")
        if sha and name:
            names.add(name)
            tips.add(sha)
    return {"base": base, "names": names, "tips": tips}


def _short_branch_ref(ref: str) -> str:
    prefix = "refs/heads/"
    return ref[len(prefix):] if ref.startswith(prefix) else ref


def parse_worktree_list(where: str):
    """Return every registered worktree of `where`'s clone as a dict, or None when unreadable.

    Same block shape git_reads.worktree_locked already parses (`--porcelain`, blocks separated by a
    blank line); this reads the whole listing instead of one target, because the sweep needs the
    full set: which branch each worktree holds (for the checked-out refusal) and which path to
    decide on next.
    """
    answer = git_reads._git(where, "worktree", "list", "--porcelain")
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
            "prunable": False,
            "head": None,
        }
        for line in lines[1:]:
            if line.startswith("branch "):
                entry["branch"] = _short_branch_ref(line[len("branch "):].strip())
            elif line.startswith("HEAD "):
                entry["head"] = line[len("HEAD "):].strip()
            elif line == "bare":
                entry["bare"] = True
            elif line == "detached":
                entry["detached"] = True
            elif line == "prunable" or line.startswith("prunable "):
                entry["prunable"] = True
            elif line == "locked" or line.startswith("locked "):
                entry["locked_reason"] = line[len("locked"):].strip() or "locked"
        entries.append(entry)
    return entries


# ------------------------------------------------------------------ the branch keep rule
#
# The REAP-OR-KEEP answer is git_reads.branch_proof(where, base, branch) alone, the same three tests
# git_reads.branch_is_empty runs: ancestor, then cherry-empty, then remote-contains, any one passing
# proves the work survives the branch, None (any test could not be read) means keep. Its answer
# is also the label of the test that passed. The refusals ahead of it (default branch, protected
# prefix, checked out) are the only things added here, and they can only turn a reap into a keep.


def decide_branch(where: str, base: str, branch: str, protected_prefixes, checked_out_branches,
                  batch=None):
    """Return one decision dict: {"name", "action": "reap"|"keep", "reason"}. BATCH
    (`merged_batch`) answers the ancestor test for every branch at once; None reads it per branch."""
    if branch in ("main", "master"):
        return {"name": branch, "action": "keep", "reason": "default-branch"}
    for prefix in protected_prefixes:
        if branch.startswith(prefix):
            return {"name": branch, "action": "keep", "reason": "protected-prefix:" + prefix}
    if branch in checked_out_branches:
        return {"name": branch, "action": "keep", "reason": "checked-out"}
    label = git_reads.branch_proof(where, base, branch,
                               None if batch is None else branch in batch["names"])
    if label is None:
        return {"name": branch, "action": "keep", "reason": "unreadable-subject"}
    if label is False:
        return {"name": branch, "action": "keep", "reason": "only-copy"}
    if label == "on-remote" and _fetch_throttled(where):
        # A throttled run skipped the fetch, so the remote-tracking refs may be 10 minutes old and
        # an on-remote read could name a head the remote has since lost. A branch merged into the
        # base (ancestor, cherry-empty) needs no remote read and still goes.
        return {"name": branch, "action": "keep", "reason": "unreadable-subject: fetch throttled"}
    return {"name": branch, "action": "reap", "reason": label}


# ------------------------------------------------------------------ the worktree keep rule
#
# Every boolean (dirty, locked, live) is git_reads' own primitive (git_reads.porcelain,
# git_reads.worktree_locked, git_reads.worktree_live_session), read in the order
# guard_core.worktree_remove_subject uses. This function adds only the "which one refused" label.
# The "never touch the primary checkout" exclusion is decided in `sweep_repo`, before
# `decide_worktree` is called, by `_is_primary_checkout` below.


def _is_primary_checkout(entry_path: str):
    """True when `entry_path` IS the repository's one primary checkout, False for a linked
    worktree, None when the read failed.

    Ask git which path is primary; never compare against the `root` argument. `sweep_repo` can be
    called with a linked worktree's own path, and the real primary checkout would then stop
    matching `root`, stop being excluded, and be judged like any worktree. Git's own refusal to
    remove a main working tree is not a guard this program may lean on
    (verification-recovery-independent-of-state).

    Every worktree of one clone shares one git directory (`--git-common-dir`). The primary
    checkout is the one worktree whose OWN git directory (`--git-dir`) equals it. A linked
    worktree's own git directory is `<common>/worktrees/<name>`, so the two never match. This is
    the read `hooks/git_reads.py.is_worktree` makes, run here per entry.
    """
    answer = git_reads._git(entry_path, "rev-parse", "--git-dir", "--git-common-dir")
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


AGENT_LOCK_RE = re.compile(r"^claude agent agent-[\w-]+ \(pid (\d+)(?: start (.+))?\)$")


def stale_agent_lock_verdict(reason: str):
    """True when REASON is a claude agent lock that may go. Two forms: the Agent tool's own
    lock `claude agent agent-<id> (pid N start <date>)`, and `claude agent agent-<id> (pid N)`
    with no start time. N is the HOST claude process, not the agent.
    A lock goes when N is dead; with a start time, also when N is alive with another start time (pid
    reuse). LIMIT: with no start time there is no pid-reuse check, so a dead host whose pid a live
    process now holds keeps its lock. False when the holder still runs, or the reason is any other
    lock. None when the start time or the process read could not tell. Only True lets a lock go."""
    found = AGENT_LOCK_RE.match(reason or "")
    if not found:
        return False
    pid, start = int(found.group(1)), found.group(2)
    locked_ms = None
    if start is not None:
        try:
            # The lock's date is UTC, so it is read with timegm, never mktime.
            locked_ms = calendar.timegm(time.strptime(start, "%a %b %d %H:%M:%S %Y")) * 1000
        except Exception:
            return None
    actual = git_reads._process_start_ms(pid)
    if actual is git_reads.PROCESS_START_UNREADABLE:
        return None
    if actual is None:
        return True
    if locked_ms is None:
        return False
    return abs(actual - locked_ms) > git_reads.SESSION_LIVE_TOLERANCE_MS


MAX_CLIMB = 64  # fixed depth bound against a pid cycle, never a real tree this deep


def _parent_pid(pid: int):
    """The parent pid of PID, or None when it cannot be read."""
    if sys.platform.startswith("win"):
        return _parent_pid_windows(pid)
    try:
        answer = _nowindow.run(["ps", "-o", "ppid=", "-p", str(pid)],
                               capture_output=True, text=True, timeout=5)
        return int(answer.stdout.strip()) if answer.returncode == 0 else None
    except Exception:
        return None


def own_agent_lock_verdict(reason: str):
    """True when REASON is an Agent-tool lock whose live holder is this process or one of its
    ancestors (the calling session's own Claude process). False for any other reason, or a holder
    outside the ancestry. None when a pid read could not tell. The caller still owns the clean,
    merged, idle, session and process checks: this reads the holder only."""
    found = AGENT_LOCK_RE.match(reason or "")
    if not found:
        return False
    alive = stale_agent_lock_verdict(reason)
    if alive is not False:
        return None if alive is None else False
    holder = int(found.group(1))
    current = os.getpid()
    for _ in range(MAX_CLIMB):
        if current == holder:
            return True
        if current <= 1:
            return False
        current = _parent_pid(current)
        if current is None:
            return None
    return None


def _own_lock_ready(where: str, path: str, batch, idle):
    """True when a tree held by the caller's own agent lock may go: merged into the default
    branch, and idle AGENT_END_IDLE_SECONDS even under --attended. IDLE is the read taken before
    any `git status`, which can rewrite the index. An unreadable fact is False."""
    if idle is None or idle < AGENT_END_IDLE_SECONDS:
        return False
    return _merged_read(where, path, batch) is True


_FETCH_FAILED = None  # a set of roots while `main` runs: those whose `fetch --prune` failed
_LIVE_HEADS = None  # a dict while `main` runs: one ls-remote per remote per repository per run


def _common_dir_key(path: str):
    common = git_reads._git(path, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if common is None or common.returncode != 0 or not common.stdout.strip():
        return None
    return os.path.normcase(common.stdout.strip())


def _live_remote_heads(path: str):
    """The SHAs of every head the repository's remotes list NOW (`git ls-remote --heads`, which
    moves no ref; the run's own `fetch --prune` is `_fetch_prune`), or None when any read failed.
    A head whose commit this clone lacks is dropped, because `rev-list` fails on an unknown SHA.
    A dropped head can sit above a commit the clone has, so dropping it can only make a tree read
    unpushed, and an unpushed tree is kept unless it is merged. Local refs/remotes/* are not used: they lag the remote."""
    key = _common_dir_key(path)
    if key is None:
        return None
    if _LIVE_HEADS is not None and _LIVE_HEADS.get((key, "throttled")):
        return None  # a fetch within the window: no ls-remote either; every tree then reads unsettled and is kept
    if _LIVE_HEADS is not None and key in _LIVE_HEADS:
        return _LIVE_HEADS[key]
    shas = set()
    remotes = git_reads._git(path, "remote")
    if remotes is None or remotes.returncode != 0:
        shas = None
    else:
        for remote in remotes.stdout.split():
            try:  # prompts off: an unattended run never waits on a login window
                listed = _nowindow.run(
                    ["git", "-C", path, "ls-remote", "--heads", remote], capture_output=True,
                    text=True, encoding="utf-8", errors="replace", timeout=10,
                    env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"})
            except Exception:
                listed = None
            if listed is None or listed.returncode != 0:
                shas = None
                break
            shas.update(line.split("\t", 1)[0] for line in listed.stdout.splitlines() if "\t" in line)
    if shas:
        try:
            held = _nowindow.run(
                ["git", "-C", path, "cat-file", "--batch-check"],
                input="".join(sha + "\n" for sha in sorted(shas)),
                capture_output=True, text=True, timeout=10)
        except Exception:
            held = None
        if held is None or held.returncode != 0:
            shas = None
        else:
            shas -= {line.split()[0] for line in held.stdout.splitlines() if line.endswith(" missing")}
    if _LIVE_HEADS is not None:
        _LIVE_HEADS[key] = shas
    return shas


def _unpushed_among(path: str, heads, live):
    """The subset of HEADS (commit SHAs) with a commit no head in LIVE reaches, or None when git
    could not tell: ONE `rev-list --stdin` for all of HEADS. rev-list names every commit
    reachable from HEADS and not from LIVE; a head is pushed exactly when it is not named."""
    heads = sorted(set(heads))
    if not heads:
        return set()
    if not live:  # no remote head at all: nothing is pushed, and no walk is needed to say so
        return set(heads)
    try:
        answer = _nowindow.run(
            ["git", "-C", path, "rev-list", "--stdin"],
            input="".join(h + "\n" for h in heads) + "--not\n" + "".join(
                sha + "\n" for sha in sorted(live)),
            capture_output=True, text=True, timeout=30)
    except Exception:
        return None
    if answer.returncode != 0:
        return None
    named = set(answer.stdout.split())
    return {h for h in heads if h in named}


def _pushed_cache(path: str):
    """This run's {commit SHA: pushed?} for the repository PATH is in, or None with no run."""
    if _LIVE_HEADS is None:
        return None
    key = _common_dir_key(path)
    return None if key is None else _LIVE_HEADS.setdefault((key, "pushed"), {})


def prime_pushed(root: str, entries):
    """Settle every worktree HEAD of ROOT's repository in one rev-list, so `fully_pushed` does
    not run one per tree (measured: the per-tree reads are why a sweep outran its 25 s). Only
    inside a `main` run. A failed read caches nothing: each tree then asks for itself."""
    cache = _pushed_cache(root)
    live = _live_remote_heads(root) if cache is not None else None
    if live is None:
        return
    heads = {e["head"] for e in entries
             if not e.get("bare") and e.get("head") and set(e["head"]) != {"0"}}
    unpushed = _unpushed_among(root, heads - set(cache), live)
    if unpushed is not None:
        cache.update({h: h not in unpushed for h in heads if h not in cache})


def fully_pushed(path: str):
    """True when every commit on HEAD is reachable from a head the remote lists now (a detached
    HEAD counts too), False when one is not, None when git could not tell: ls-remote failed
    or rev-list failed. A live SHA missing locally is dropped, not unreadable. Every reap needs it, not only a
    stale agent lock: a lane always commits, and a detached HEAD has no branch to tombstone.
    HEAD is read now; `prime_pushed` may already have settled that commit this run."""
    live = _live_remote_heads(path)
    if live is None:
        return None
    head = git_reads._git(path, "rev-parse", "HEAD")
    if head is None or head.returncode != 0 or not head.stdout.strip():
        return None
    head = head.stdout.strip()
    cache = _pushed_cache(path)
    if cache is not None and head in cache:
        return cache[head]
    unpushed = _unpushed_among(path, [head], live)
    if unpushed is None:
        return None
    if cache is not None:
        cache[head] = head not in unpushed
    return head not in unpushed


STRICT_IDLE_SECONDS = 60 * 60  # a tree needs 1 hour of git quiet
# A pushed, clean, NOT merged tree is removable once it is idle this long
# (when-a-worktree-may-be-removed).
STRICT_UNMERGED_IDLE_SECONDS = 24 * 60 * 60


def worktree_idle_seconds(path: str, now=None):
    """Seconds since the newest git activity in worktree PATH, or None when it cannot be read.
    Activity is the newest mtime of the worktree's own admin files: index, HEAD, logs/HEAD under
    `.git/worktrees/<name>`. HEAD must exist; a missing index or log is skipped."""
    answer = git_reads._git(path, "rev-parse", "--absolute-git-dir")
    if answer is None or answer.returncode != 0 or not answer.stdout.strip():
        return None
    admin = answer.stdout.strip()
    try:
        newest = os.stat(os.path.join(admin, "HEAD")).st_mtime
    except OSError:
        return None
    for name in ("index", os.path.join("logs", "HEAD")):
        try:
            newest = max(newest, os.stat(os.path.join(admin, name)).st_mtime)
        except OSError:
            pass
    return (time.time() if now is None else now) - newest


def _merged_read(where: str, path: str, batch=None):
    """True when HEAD in PATH holds no commit the default branch lacks, by ancestry or by patch
    (docs/decisions/a-branch-is-redundant-by-patch-not-by-ancestry.md). False when it holds one. None
    when git could not tell. HEAD is read in the worktree itself, never in WHERE. One home: the
    strict keep and the unpushed keep both ask it. BATCH (`merged_batch`) holds the commits that
    are in the default branch: a HEAD in it is merged with no further read. Any other HEAD is
    asked of git as before (ancestry, then patch), and the default branch is read once."""
    if batch is not None:
        head = git_reads._git(path, "rev-parse", "HEAD")
        if head is None or head.returncode != 0 or not head.stdout.strip():
            return None
        if head.stdout.strip() in batch["tips"]:
            return True
        base = batch["base"]
    else:
        base = git_reads.resolve_default_base(where)
    if base is None:
        return None
    merged = git_reads.branch_is_ancestor(path, base, "HEAD")
    if merged is False:
        merged = git_reads.branch_cherry_empty(path, base, "HEAD")
    return merged


def _strict_keep(where: str, path: str, idle, batch=None, fast=False):
    """The keep decision a run adds unless a person passed --attended, or None when the tree is merged and idle.
    Merged: HEAD holds no commit the default branch lacks, by ancestry or by patch
    (docs/decisions/a-branch-is-redundant-by-patch-not-by-ancestry.md). Pushed alone is not merged,
    except after STRICT_UNMERGED_IDLE_SECONDS: the caller already kept an unpushed tree, so an
    unmerged tree here is pushed. FAST: no push was read, so an unmerged tree is always kept."""
    merged = _merged_read(where, path, batch)
    if merged is None:
        return {"path": path, "action": "keep", "reason": "unreadable-subject"}
    if not merged:
        if fast:
            return {"path": path, "action": "keep",
                    "reason": "unmerged: HEAD has a commit the default branch lacks"}
        if idle is None:
            return {"path": path, "action": "keep", "reason": "unreadable-subject"}
        if idle >= STRICT_UNMERGED_IDLE_SECONDS:
            return None
        return {"path": path, "action": "keep",
                "reason": "unmerged: HEAD has a commit the default branch lacks"}
    if idle is None:
        return {"path": path, "action": "keep", "reason": "unreadable-subject"}
    if idle < STRICT_IDLE_SECONDS:
        return {"path": path, "action": "keep",
                "reason": "recently-active: git activity %d minutes ago" % (idle // 60)}
    return None


AGENT_IDLE_SECONDS = 4 * 60 * 60  # a finished agent's tree needs 4 hours of quiet


def _is_agent_worktree(where: str, path: str) -> bool:
    """True when PATH is `<WHERE>/.claude/worktrees/agent-*`, directly under that folder."""
    def norm(p):
        return os.path.normcase(os.path.realpath(p))
    parent, name = os.path.split(norm(path))
    return parent == norm(os.path.join(where, ".claude", "worktrees")) and name.startswith("agent-")


def _agent_rule_keep(kept: dict, idle):
    """The agent rule (when-a-worktree-may-be-removed). It ADDS removals to the older unattended
    rulings and never narrows them. The caller runs it for a tree under `.claude/worktrees/agent-*`
    that those rulings keep (KEPT is their decision), after the clean, lock, session and
    live-ls-remote reads passed. Returns a keep decision, or None when the tree may go: idle 4
    hours, and HEAD on a remote-tracking ref (`git branch -r --contains`). A keep that came from
    a failed read (`unreadable-subject`, an unreadable idle time included) stays, and so does a
    failed read here."""
    path = kept["path"]
    if kept["reason"] == "unreadable-subject":
        return kept
    if idle < AGENT_IDLE_SECONDS:
        return {"path": path, "action": "keep",
                "reason": "recently-active: git activity %d minutes ago" % (idle // 60)}
    return _remote_tracking_keep(path)


def _remote_tracking_keep(path: str):
    """A keep decision unless HEAD of PATH is on a remote-tracking ref (`git branch -r --contains`),
    else None. A failed read keeps. One home: the agent rule and the agent-end rule both ask it."""
    contains = git_reads._git(path, "branch", "-r", "--contains", "HEAD")
    if contains is None or contains.returncode != 0:
        return {"path": path, "action": "keep", "reason": "unreadable-subject"}
    if not contains.stdout.strip():
        return {"path": path, "action": "keep",
                "reason": "unpushed: HEAD is on no remote-tracking ref"}
    return None


def _idle_then_dirty(entry: dict, attended: bool):
    """(idle, path, dirty) for ENTRY. Idle is read first: `git status` can rewrite the index and
    make every tree look active."""
    idle = worktree_idle_seconds(entry["path"]) if not attended else None
    path = entry["path"]
    dirty = git_reads.porcelain(path)
    return idle, path, dirty


def decide_worktree(where: str, entry: dict, attended: bool = False, agent_rule: bool = True,
                    batch=None, fast: bool = False, own_lock_rule: bool = True):
    """Return one decision dict: {"path", "action": "reap"|"keep", "reason"}. Strict by default: a
    worktree also needs to be merged and idle 1 hour, so a stale installed job fails safe.
    ATTENDED (a person's run) skips those two keeps. AGENT_RULE (on by default) lets a clean,
    fully pushed tree under `.claude/worktrees/agent-*` go after 4 idle hours even when those two
    keeps hold it. A repo's own `reap:worktrees` script turns it off. BATCH (`merged_batch`) is
    the one read that says which commits are in the default branch. FAST reads no remote and no
    push state: the tree goes only when its HEAD is in the default branch (and idle 1 hour,
    unless attended), and with no BATCH nothing is proven, so it stays. OWN_LOCK_RULE (on by
    default) frees the calling session's own agent lock once the tree is clean, merged, idle 30
    minutes and unused; the agent-end reap turns it off."""
    lock_idle = None  # an agent lock's idle is read even when attended, and before any status
    if AGENT_LOCK_RE.match(entry.get("locked_reason") or ""):
        lock_idle = entry["idle"] if "idle" in entry else worktree_idle_seconds(entry["path"])
    if "idle" in entry:  # a pass's sort read it before any status ran: one read per tree
        idle, path = (None if attended else entry["idle"]), entry["path"]
        dirty = git_reads.porcelain(path)
    else:
        idle, path, dirty = _idle_then_dirty(entry, attended)
    if dirty is None:
        return {"path": path, "action": "keep", "reason": "unreadable-subject"}
    if dirty:
        return {"path": path, "action": "keep", "reason": "dirty"}
    # The lock comes from the entry `parse_worktree_list` read once for the pass, not a fresh
    # `worktree list` per tree (measured: one of the reads that made a sweep outrun its 25 s).
    # `remove_worktree` still has git refuse a locked tree.
    stale_agent_lock = False
    own_lock = False
    if entry.get("locked_reason") is not None:
        holder = entry.get("locked_reason") or "locked"
        stale_agent_lock = stale_agent_lock_verdict(holder)
        if stale_agent_lock is not True:
            own_lock = (own_lock_rule and own_agent_lock_verdict(holder) is True
                        and (not fast or batch is not None)
                        and _own_lock_ready(where, path, batch, lock_idle))
            if not own_lock:
                return {"path": path, "action": "keep", "reason": "locked: %s" % holder}
    live = git_reads.worktree_live_session(path)
    if live is None:
        return {"path": path, "action": "keep", "reason": "unreadable-subject"}
    if live:
        return {"path": path, "action": "keep", "reason": "live-session"}
    pushed = True if fast else fully_pushed(path)
    if pushed is None:
        return {"path": path, "action": "keep", "reason": "unreadable-subject"}
    if not pushed:
        # Unpushed is only a loss when the default branch lacks the work. A squash merge leaves
        # a lane's own commit on no remote branch, though its patch is on main. Only when the
        # repository has a remote: with none, nothing is pushed, so every worktree is kept.
        remotes = git_reads._git(where, "remote")
        has_remote = remotes is not None and remotes.returncode == 0 and remotes.stdout.strip()
        merged = _merged_read(where, path, batch) if has_remote else False
        if merged is None:
            return {"path": path, "action": "keep", "reason": "unreadable-subject"}
        if not merged:
            return {"path": path, "action": "keep",
                    "reason": "unpushed: HEAD has a commit on no remote branch"}
    if fast:
        if batch is None:
            return {"path": path, "action": "keep", "reason": "unreadable-subject"}
        kept = _strict_keep(where, path, float("inf") if attended else idle, batch, fast=True)
        if kept:
            return kept
    elif not attended:
        kept = _strict_keep(where, path, idle, batch)
        if kept and agent_rule and _is_agent_worktree(where, path):
            kept = _agent_rule_keep(kept, idle)
        if kept:
            return kept
    # The pre-removal process check. ANY process at all, not only a listener -- a plain shell
    # sitting in this worktree is just as much a reason `git worktree remove` must not run as a
    # live Claude session is.
    #
    # A single PID whose own cwd read fails is OUT OF SCOPE, not a keep
    # (unattended-sweep-stops-proven-orphans): keeping on it would refuse to reap anything on a
    # machine where many processes belong to another account. Same on POSIX and Windows: both
    # dispatch through `process_cwd`. Only the WHOLE enumeration failing (`processes_in`
    # returning `(None, None)`) means keep-everything.
    inside, _unreadable = processes_in(path)
    if inside is None:
        return {"path": path, "action": "keep", "reason": "unreadable-subject"}
    if inside:
        return {"path": path, "action": "keep",
                "reason": "process-inside: pid %s" % ", ".join(str(p) for p in sorted(inside))}
    if stale_agent_lock or own_lock:
        return {"path": path, "action": "reap",
                "reason": "removable: " + ("stale agent lock" if stale_agent_lock else "own agent lock"),
                "unlock": True, "lock_reason": holder}
    return {"path": path, "action": "reap", "reason": "removable"}


# At agent end, ANOTHER finished agent's tree needs 30 minutes of quiet
# (when-a-worktree-may-be-removed). AGENT_IDLE_SECONDS (4 hours) stays the janitor's floor.
AGENT_END_IDLE_SECONDS = 30 * 60


def decide_agent_end_worktree(where: str, entry: dict, min_idle=None):
    """The keep-or-reap decision for one `.claude/worktrees/agent-*` tree at agent end. MIN_IDLE is
    the seconds of git quiet the tree needs (None: none). Idle is read first: `git status` can
    rewrite the index and make every tree look active. The rest is
    `decide_worktree` with the person's run flag, which skips its merged and idle keeps and keeps
    the clean, lock, session, live-ls-remote and process checks. Then HEAD must be on a
    remote-tracking ref. Any failed read keeps. A tree an earlier remove left half done
    (`_restore_cut_short`) gets its deleted tracked files back first, when no lock, session or
    process holds it, so it can be decided again."""
    path = entry["path"]
    if min_idle is not None:
        idle = worktree_idle_seconds(path)
        if idle is None:
            return {"path": path, "action": "keep", "reason": "unreadable-subject"}
        if idle < min_idle:
            return {"path": path, "action": "keep",
                    "reason": "recently-active: git activity %d minutes ago" % (idle // 60)}
    _restore_cut_short(where, entry)
    decision = decide_worktree(where, entry, attended=True, own_lock_rule=False)
    if decision["action"] != "reap":
        return decision
    return _remote_tracking_keep(path) or decision


# ------------------------------------------------------------------ orphaned TCP listeners
#
# See the module docstring for the shape of the rule.
# Every function below is read-only until `send_signal` and `reap_listener`, at the very end of
# this section: everything before that point only LOOKS, on this one machine, and touches
# nothing.
#
# Every OS-specific read below answers three things, never two, the same shape guard.py's own
# `_process_start_ms` already established: a confirmed answer (True/False), or `None` when the
# read itself could not tell. `None` is never coerced into a confident answer by this file. A
# caller that receives `None` from any of these always keeps, never reaps -- see
# CLAUDE.md's "report a read that could not run as unknown, never as clear or broken", which
# states it for every read.


def list_listeners():
    """Return every `[{"pid", "port"}]` this machine currently has a process LISTENing on a TCP
    port for, or `None` when the enumeration itself failed (no per-OS tool answered at all).
    Stdlib subprocess calls and, on Windows, `ctypes` only -- no psutil."""
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
        answer = _nowindow.run(
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
    the pid is pulled out with a regex, not a full parse. `None` when `ss` itself is missing or
    refuses to run, so the caller falls back to lsof."""
    try:
        answer = _nowindow.run(["ss", "-ltnp"], capture_output=True, text=True, timeout=10)
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
    layouts (`MIB_TCPROW_OWNER_PID` vs `MIB_TCP6ROW_OWNER_PID`); skipping IPv6 would miss a
    listener bound to `[::]`. `None` when the API itself refuses (the first, sizing call answers
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
    fd (pid gone, or this read is not allowed to see it) -- unreadable, not a path.
    In a preview the one cwd table answers it (the first cwd line of PID, as lsof would print)."""
    if _RUN is not None:
        table = _all_cwds_macos()
        if table is not None:
            return _memo("cwd-by-pid", lambda: _first_cwd_by_pid(table)).get(pid)
    try:
        answer = _nowindow.run(
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
    unlinked reads back with a literal ` (deleted)` suffix, stripped here so the path still
    matches the worktree it names: the process is still THERE, the directory entry is just
    gone."""
    try:
        raw = os.readlink("/proc/%d/cwd" % pid)
    except Exception:
        return None
    suffix = " (deleted)"
    if raw.endswith(suffix):
        raw = raw[: -len(suffix)]
    return raw or None


def _process_cwd_windows(pid: int):
    """ponytail: the PEB offsets below are UNDOCUMENTED and 64-bit-process-only
    (github.com/giampaolo/psutil/issues/51, github.com/raskrebs/sonar/pull/57). Any failure at
    any step answers `None`, never a guess. Upgrade path: `psutil.Process(pid).cwd()` the day
    this repository allows a third-party dependency; this function exists because the sweep is
    stdlib+ctypes only.

    `OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ)` -> `NtQueryInformationProcess`
    for the PEB address -> `ReadProcessMemory` of `PEB.ProcessParameters` (offset 0x20 on
    64-bit) -> `ReadProcessMemory` of that struct's `CurrentDirectory.DosPath`, a
    `UNICODE_STRING` (offset 0x38), whose `Buffer` is read once more for the actual text."""
    import ctypes

    PROCESS_QUERY_INFORMATION = 0x0400
    PROCESS_VM_READ = 0x0010
    kernel32 = ctypes.windll.kernel32
    ntdll = ctypes.windll.ntdll

    # Type every handle and pointer explicitly: ctypes assumes a 32-bit `c_int` for any argument
    # or return value it is not told the type of, which truncates (going IN) or raises
    # `OverflowError` (coming OUT) on a 64-bit PEB address or heap pointer.
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
    """Best-effort, display-only. Never used to decide reap-or-keep
    (verification-never-dry-run-refusal-list) -- the preview shows it so a human can recognise the
    program, and a signal is still sent by pid number alone."""
    if sys.platform == "darwin":
        return _process_command_posix(pid)
    if sys.platform.startswith("linux"):
        return _process_command_linux(pid) or _process_command_posix(pid)
    if sys.platform.startswith("win"):
        return _process_command_windows(pid)
    return None


def _process_command_posix(pid: int):
    row = _ps_row(pid)
    if row is not _NO_TABLE:
        return (row[2].strip() or None) if row else None
    try:
        answer = _nowindow.run(
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
    every caller in this file, never coerced into a confident answer either way.

    POSIX: PID's own PPid is 1 (`/proc/PID/status` on Linux, `ps -o ppid=` on macOS). A
    subreaper (`PR_SET_CHILD_SUBREAPER`) adopts with ITS OWN pid, never 1, so this stays
    stricter than "parent is dead" on purpose: a subreaper is not treated as orphaned.

    Windows never re-parents an orphan: the recorded ParentProcessId either names a dead
    process, or names a LIVE one that was created AFTER this pid (the pid was reused once the
    real parent exited). Either shape means orphaned. A live parent created BEFORE this pid,
    the ordinary shape, means not."""
    if sys.platform == "darwin":
        row = _ps_row(pid)
        if row is not _NO_TABLE:
            return _ppid_is_init(row[0] if row else "")
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
        answer = _nowindow.run(argv, capture_output=True, text=True, timeout=5)
    except Exception:
        return None
    if answer.returncode != 0:
        return None
    return _ppid_is_init(answer.stdout)


def _ppid_is_init(text: str):
    text = text.strip()
    if not text:
        return None
    try:
        return int(text) == 1
    except ValueError:
        return None


def _is_orphan_windows(pid: int):
    """`OpenProcess` success alone (git_reads' own oracle, built for a different question) cannot
    tell "parent is dead" from "parent is running" here. `git_reads._process_start_ms_windows`
    answers a real creation time for a pid that has ALREADY EXITED while anything still holds a
    handle open to it (a `subprocess.Popen` not yet garbage-collected is enough), because
    Windows keeps the process object alive as a zombie until every handle closes.
    `_process_running_windows` below checks `GetExitCodeProcess` for `STILL_ACTIVE`, which a
    zombie never answers, before anything is trusted as alive."""
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
    child_start = git_reads._process_start_ms_windows(pid)
    if child_start is None or child_start is git_reads.PROCESS_START_UNREADABLE:
        return None  # can't confirm the child's OWN start either, so no comparison is possible
    parent_start = git_reads._process_start_ms_windows(parent_pid)
    if parent_start is None or parent_start is git_reads.PROCESS_START_UNREADABLE:
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
    failed. Used only by `processes_in`'s pre-removal check: if the enumeration fails, KEEP
    everything and remove no worktree."""
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
    if sys.platform == "darwin" and _RUN is not None:
        table = _ps_table()
        if table is not None:
            return list(table)
    try:
        answer = _nowindow.run(["ps", "-axo", "pid="], capture_output=True, text=True, timeout=10)
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
        row = _ps_row(pid)
        if row is not _NO_TABLE:
            return _uid_is_mine(row[1] if row else "")
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
        answer = _nowindow.run(argv, capture_output=True, text=True, timeout=5)
    except Exception:
        return None
    if answer.returncode != 0:
        return None
    return _uid_is_mine(answer.stdout)


def _uid_is_mine(text: str):
    text = text.strip()
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
    itself the signal that a process is not ours. `is_current_user_process` treats `None` as
    unreadable, not as a guessed "yes"."""
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

    `os.path.realpath` first, never `git_reads._path_identity`'s `os.stat`-based fallback: a worktree
    that has ALREADY been removed has nothing left to `os.stat`, and `realpath` degrades to a
    plain normalised string for the part that is gone. `normpath` alone is not enough while the
    checkout DOES exist: on Windows a path can arrive through a SHORT (8.3) component
    (`SHIVAM~1`) while `git worktree list` reports the LONG form for the same directory, and
    `normpath` never expands an 8.3 name. `realpath` resolves both to one spelling."""
    try:
        cwd_norm = os.path.normcase(os.path.realpath(cwd)) + os.sep
        target_norm = os.path.normcase(os.path.realpath(checkout_path)) + os.sep
    except Exception:
        return False
    return cwd_norm.startswith(target_norm)


def _matching_checkout(cwd: str, checkout_paths):
    """The DEEPEST entry of CHECKOUT_PATHS that CWD sits under, or `None` when it sits under
    none of them. Agent worktrees sit under `.claude/worktrees/` INSIDE the primary checkout,
    and `parse_worktree_list` names the primary first, so taking the first match would judge a
    listener in an agent worktree against the primary checkout and its live session."""
    matches = [path for path in checkout_paths if _cwd_under_checkout(cwd, path)]
    if not matches:
        return None
    return max(matches, key=lambda path: len(os.path.normcase(os.path.realpath(path))))


def _under_agent_worktree(cwd: str) -> bool:
    """True when CWD sits under a `.claude/worktrees/<name>` checkout. No session record names a
    agent, so the sweep cannot tell a running agent's worktree from an ended one. It leaves
    those folders to janitor/agent_end_reap.py (agent-end-reap-stops-what-a-finished-agent-left),
    which runs when the harness says the agent ended."""
    parts = os.path.normcase(os.path.realpath(cwd)).replace("\\", "/").split("/")
    claude, worktrees = os.path.normcase(".claude"), os.path.normcase("worktrees")
    return any(parts[i] == claude and parts[i + 1] == worktrees and parts[i + 2]
               for i in range(len(parts) - 2))


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
        if cwd is None or _under_agent_worktree(cwd):
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
    live Claude session has a cwd in the same checkout (git_reads.py's own tested oracle, reused
    verbatim, never re-derived here); owned by the current user. Any `None` along the way
    means keep, reported as `unreadable-subject`."""
    pid = entry["pid"]
    base = dict(entry, command=process_command(pid))

    orphan = is_orphan(pid)
    if orphan is None:
        return {**base, "action": "keep", "reason": "unreadable-subject"}
    if not orphan:
        return {**base, "action": "keep", "reason": "not-orphaned"}

    live = git_reads.worktree_live_session(entry["checkout"])
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


DEAD_ROOTED_EXTENSIONS = (".py", ".sh", ".js", ".mjs", ".ts")
_ARGV_PATH_RE = re.compile(r"(?:[A-Za-z]:)?[\\/][^\s'\"]+")


def _project_ancestor(path: str):
    """The nearest EXISTING ancestor of PATH that carries `.git` or `.claude`, looking at most
    12 levels up, or `None`. `None` too when PATH's own parent directory still exists: a
    script missing from a live directory is not a deleted tree. A deleted checkout leaves no
    `.git` of its own, so the test asks whether the ground it stood on is still a project."""
    probe = os.path.dirname(path)
    if os.path.isdir(probe):
        return None
    levels = 0
    while True:
        if os.path.isdir(probe):
            if os.path.exists(os.path.join(probe, ".git")) or \
                    os.path.isdir(os.path.join(probe, ".claude")):
                return probe
            levels += 1
            if levels > 12:
                return None
        parent = os.path.dirname(probe)
        if parent == probe:
            return None
        probe = parent


def find_dead_rooted():
    """Return one decision dict per process whose argv names a script file
    (`DEAD_ROOTED_EXTENSIONS`) that no longer exists, whose parent directory is also
    missing, and whose nearest existing ancestor carries `.git` or `.claude` (a deleted
    checkout or worktree). `None` when the machine pid enumeration failed.
    Decision: {"pid", "command", "missing", "home", "action": "reap"|"keep", "reason"}.
    Reap only when `is_orphan` and `is_current_user_process` both answer a confirmed yes;
    `None` from either is `unreadable-subject`, keep.

    The argv is the subject here, so `process_command` decides WHICH processes qualify. It never
    decides reap-or-keep: that stays with the two reads and a pid-only signal."""
    pids = list_all_pids()
    if pids is None:
        return None
    found = []
    for pid in pids:
        if pid == os.getpid():
            continue
        command = process_command(pid)
        if not command:
            continue
        hit = None
        for raw in _ARGV_PATH_RE.findall(command):
            if raw.lower().endswith(DEAD_ROOTED_EXTENSIONS) and not os.path.exists(raw):
                home = _project_ancestor(raw)
                if home:
                    hit = (raw, home)
                    break
        if hit is None:
            continue
        base = {"pid": pid, "command": command, "missing": hit[0], "home": hit[1]}
        orphan = is_orphan(pid)
        owner = is_current_user_process(pid) if orphan else None
        if orphan is None or (orphan and owner is None):
            found.append({**base, "action": "keep", "reason": "unreadable-subject"})
        elif not orphan:
            found.append({**base, "action": "keep", "reason": "not-orphaned"})
        elif not owner:
            found.append({**base, "action": "keep", "reason": "not-current-user"})
        else:
            found.append({**base, "action": "reap", "reason": "dead-rooted-server"})
    return found


def print_dead_rooted_report(decisions, out=sys.stdout):
    print("", file=out)
    print("== dead-rooted servers ==", file=out)
    if decisions is None:
        print("  UNREADABLE -- the machine pid enumeration failed; none examined", file=out)
        return
    for d in decisions:
        print("  server    %-4s pid=%-8s %-50s %s" % (
            "REAP" if d["action"] == "reap" else "KEEP", d["pid"], d["missing"], d["reason"]),
            file=out)
    print("  dead-rooted servers examined: %d" % len(decisions), file=out)


# ------------------------------------------------------------------ the simulator tier
#
# docs/decisions/sweep-shuts-down-idle-simulators.md. One home for "idle": `sim_keep_code` is the
# test; the guard's reuse rule (hooks/guard.py) imports it from here.
SIM_IDLE_SECONDS = 3600
SIM_SHUTDOWN_CAP = 4  # per run; the rest wait for the next run
_SIM_APP_RE = re.compile(r"^\S*/Simulator\.app/Contents/MacOS/Simulator(?:\s|$)")
_XCODE_APP_RE = re.compile(r"^\S*/Xcode[^/]*\.app/Contents/MacOS/Xcode(?:\s|$)")


def sim_available():
    return not sys.platform.startswith("win") and shutil.which("xcrun") is not None


def sim_read_devices():
    """Every simulator as {udid, name, state, deviceTypeIdentifier, runtime}; None if unreadable."""
    try:
        answer = _nowindow.run(["xcrun", "simctl", "list", "devices", "--json"],
                                capture_output=True, text=True, timeout=60)
        if answer.returncode != 0:
            return None
        groups = json.loads(answer.stdout)["devices"]
        return [{**d, "runtime": runtime} for runtime, rows in groups.items() for d in rows]
    except Exception:
        return None


def sim_read_boots(record_path):
    """{udid: {"at": epoch seconds or None when unreadable, "pid", "start"}} from the NEWEST line
    per UDID. "pid" and "start" name the boot's launchd_sim; either is None when the line has none."""
    boots = {}
    try:
        with open(record_path, encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                    udid = row["udid"]
                except Exception:
                    continue
                try:
                    at = calendar.timegm(time.strptime(row["at"], "%Y-%m-%dT%H:%M:%SZ"))
                except Exception:
                    at = None
                boots[udid] = {"at": at, "pid": row.get("launchd_pid"),
                               "start": row.get("launchd_start")}
    except OSError:
        pass
    return boots


def _sim_live_launchd(table, udid):
    """(pid, ps lstart text) of UDID's live launchd_sim; (None, None) when not found or unreadable."""
    pids = sorted(pid for pid, (_, _, cmd) in table.items() if "launchd_sim" in cmd and udid in cmd)
    if len(pids) != 1:  # none, or two: no single launchd_sim is this boot, so unclear
        return None, None
    try:
        answer = _nowindow.run(["ps", "-o", "pid=,lstart=", "-p", str(pids[0])],
                                capture_output=True, text=True, timeout=30, env=_ps_env())
        if answer.returncode == 0:
            for line in answer.stdout.splitlines():
                parts = line.strip().split(None, 1)
                if len(parts) == 2 and parts[0] == str(pids[0]):
                    return pids[0], parts[1].strip()
    except Exception:
        pass
    return pids[0], None


def _sim_device_tree(table, udid):
    """The pids of UDID's launchd_sim and every descendant."""
    tree = {pid for pid, (_, _, cmd) in table.items() if "launchd_sim" in cmd and udid in cmd}
    grew = True
    while grew:
        grew = False
        for pid, (ppid, _, _) in table.items():
            if pid not in tree and ppid.isdigit() and int(ppid) in tree:
                tree.add(pid)
                grew = True
    return tree


def sim_keep_code(device, boots, table, now):
    """None when DEVICE is idle (ruling 2, all four tests), else the code naming why it is not.
    DEVICE must have a line in BOOTS. TABLE is the `_read_ps_table` answer, or None when unreadable."""
    if table is None:
        return "process-table-unreadable"
    commands = [cmd for _, _, cmd in table.values()]
    if any(_SIM_APP_RE.match(c) for c in commands):
        return "simulator-app-running"
    if any(_XCODE_APP_RE.match(c) for c in commands):
        return "xcode-running"
    record = boots[device["udid"]]
    if record["at"] is None:
        return "start-time-unreadable"
    if now - record["at"] < SIM_IDLE_SECONDS:
        return "booted-recently"
    # The newest record must be THIS boot: a device booted again by hand has a new launchd_sim.
    if _sim_live_launchd(table, device["udid"]) != (record["pid"], record["start"]) \
            or record["start"] is None:
        return "boot-record-mismatch"
    own = _sim_device_tree(table, device["udid"])
    needles = (device["udid"], device["name"], "booted")
    for pid, (_, _, cmd) in table.items():
        if pid not in own and any(n in cmd for n in needles):
            return "held-by-process"
    return None


def sim_tier(confirm, record_path=None):
    """One decision per recorded UDID that is booted: {"udid", "name", "action": "shutdown"|"keep",
    "reason"}. A shutdown is one `xcrun simctl shutdown <UDID>`, run only under CONFIRM. Any read
    that failed keeps. [] when there is no xcrun or the platform is Windows."""
    if not sim_available():
        return []
    record_path = record_path or os.path.join(git_reads.config_dir(), "state", "sim-boots.jsonl")
    boots = sim_read_boots(record_path)
    if not boots:
        return []
    devices = sim_read_devices()
    table = _read_ps_table()
    now = time.time()
    out, planned = [], 0
    for udid in boots:
        dev = next((d for d in devices or () if d["udid"] == udid), None)
        if devices is not None and (dev is None or dev["state"] != "Booted"):
            continue
        code = "simctl-unreadable" if devices is None else sim_keep_code(dev, boots, table, now)
        if code is None and planned >= SIM_SHUTDOWN_CAP:
            code = "run-cap-reached"
        decision = {"udid": udid, "name": dev["name"] if dev else "", "action": "keep",
                    "reason": code or "idle"}
        if code is None:
            planned += 1
            decision["action"] = "shutdown"
            if confirm:
                try:
                    run = _nowindow.run(["xcrun", "simctl", "shutdown", udid],
                                         capture_output=True, text=True, timeout=60)
                    if run.returncode != 0:
                        decision["error"] = "exit %d" % run.returncode
                except Exception as exc:
                    decision["error"] = type(exc).__name__
        out.append(decision)
    return out


def print_sim_report(decisions, confirm, out=sys.stdout):
    if not decisions:
        return
    print("", file=out)
    print("== simulators ==", file=out)
    for d in decisions:
        verb = ("STOP" if confirm else "WOULD STOP") if d["action"] == "shutdown" else "KEEP"
        print("  simulator %-10s %s %-24s %s%s" % (
            verb, d["udid"], d["name"], d["reason"],
            " FAILED " + d["error"] if d.get("error") else ""), file=out)


def _on_windows():
    return sys.platform.startswith("win")


def temp_tier(confirm):
    """The Windows temp-folder step: removes the temp folder of a session idle over 24 hours (preview
    without CONFIRM). Windows only. It stops at the sweep deadline. Returns the number of
    failures: folders it could not remove or folders it could not read."""
    if temp_sweep is None or not _on_windows():
        return 0
    print("")
    print("== session temp folders ==")
    temp_sweep.past_deadline = _past_deadline
    return temp_sweep.run(confirm)


# A Claude Code Bash call starts every command as `zsh -c 'source ~/.claude/shell-snapshots/...
# && <command>'`, so that path sits in the argv of the process and stays there after the
# session is gone. Measured on this machine: 10 live processes carry it, read in 0.03 s.
SESSION_MARK = os.path.join(".claude", "shell-snapshots")


def find_loose_processes():
    """Return one dict per ORPHANED process whose argv contains a shell-snapshots path, or `None`
    when the pid enumeration failed. REPORT ONLY: nothing here, and nothing in `main`, signals
    one. Dict: {"pid", "command", "orphan", "owner"}; `orphan` and `owner` are True or None
    (unreadable). A process that is not an orphan (a live session's shell wrapper) is left
    out, and so is a process of another user. An unreadable owner or orphan read is listed."""
    pids = list_all_pids()
    if pids is None:
        return None
    found = []
    for pid in pids:
        command = process_command(pid)
        if not command or SESSION_MARK not in command or pid == os.getpid():
            continue
        owner = is_current_user_process(pid)
        if owner is False:
            continue
        orphan = is_orphan(pid)
        if orphan is False:
            continue
        found.append({"pid": pid, "command": command, "owner": owner, "orphan": orphan})
    return found


def print_loose_processes_report(found, out=sys.stdout):
    print("", file=out)
    print("== loose processes (report only, never stopped) ==", file=out)
    if found is None:
        print("  UNREADABLE -- the machine pid enumeration failed; none examined", file=out)
        return
    for d in found:
        print("  process   pid=%-8s orphan=%-7s owner=%-7s %.70s" % (
            d["pid"], {True: "yes", False: "no"}.get(d["orphan"], "unknown"),
            "me" if d["owner"] else "unknown", d["command"]), file=out)
    print("  loose processes listed: %d (%d with an unreadable owner)" % (
        len(found), sum(1 for d in found if d["owner"] is None)), file=out)


# ------------------------------------------------------------------ the per-run read cache
#
# A preview reads the same machine facts again and again: one `lsof` table per worktree judged,
# one `ps` call per pid, one `git worktree list` per worktree, one session-record read per
# worktree. Measured on a real machine: 67 of 70 s. `_RUN` is a dict only while a PREVIEW runs
# (`main` sets it, without --confirm and outside --tier1); every read below then happens once.
# A run that acts is never cached: the re-check right before a delete must see the machine as it
# is NOW. Direct callers (the tests, other scripts) see `_RUN is None` and read fresh.
_RUN = None
_NO_TABLE = object()  # `_ps_row`: no table to read, so the caller runs its own per-pid read
_WORKTREE_LIST_ARGS = ("worktree", "list", "--porcelain")


_RUN_LOCK = threading.RLock()  # `_pmap` workers share the cache: each read still happens once
_POOL = None  # the per-branch and per-worktree reads of ONE repository
_ROOT_POOL = None  # whole repositories; a separate pool, so a repository never waits on itself
PREVIEW_WORKERS = 8
# Windows stays serial: its ctypes reads set argtypes on the shared `kernel32` object (and rebuild
# a Structure class) on every call, so two threads in them break each other. Measured on CI.
PREVIEW_THREADS = not sys.platform.startswith("win")
PREVIEW_ROOT_WORKERS = 4


def _memo(key, compute):
    if _RUN is None:
        return compute()
    with _RUN_LOCK:
        if key not in _RUN:
            _RUN[key] = compute()
        return _RUN[key]


def _pmap(fn, items, acts, pool=None):
    """`map(fn, items)` in order. In a preview the calls run on a few threads, because the
    per-branch and per-worktree reads are many separate `git` runs that nothing can share. ACTS
    is True when the caller acts on each result (confirm): that always gets the lazy `map`,
    whatever the pool state, so each decision still comes before the act that follows it."""
    items = list(items)
    pool = pool or _POOL
    if acts or pool is None or len(items) < 2:
        return map(fn, items)
    return pool.map(fn, items)


def _ps_env():
    return {**os.environ, "LC_ALL": "C"}  # lstart text must not depend on the caller's locale


def _read_ps_table():
    """`{pid: (ppid, uid, command)}` (strings) from ONE `ps`, or None when it could not answer."""
    try:
        answer = _nowindow.run(["ps", "-axo", "pid=,ppid=,uid=,command="],
                                capture_output=True, text=True, timeout=30, env=_ps_env())
    except Exception:
        return None
    if answer.returncode != 0:
        return None
    table = {}
    for line in answer.stdout.splitlines():
        parts = line.split(None, 3)
        if len(parts) >= 3 and parts[0].isdigit():
            table[int(parts[0])] = (parts[1], parts[2], parts[3] if len(parts) > 3 else "")
    return table if table else None  # an empty table is a failed read, never "no process"


def _ps_table():
    return _memo("ps", _read_ps_table)


def _ps_row(pid: int):
    """PID's (ppid, uid, command) row; None when PID is not in the table (what a failed per-pid
    `ps -p` answers); `_NO_TABLE` when this run has no table (cache off, or `ps` failed)."""
    if _RUN is None or sys.platform != "darwin":
        return _NO_TABLE  # Linux and Windows keep their own reads
    table = _ps_table()
    return _NO_TABLE if table is None else table.get(pid)


def _begin_preview_cache():
    """Start the per-run cache and wrap the two reads that repeat per worktree. Returns the
    undo function."""
    global _RUN, _POOL, _ROOT_POOL
    _RUN = {}
    if PREVIEW_THREADS:
        _POOL = concurrent.futures.ThreadPoolExecutor(max_workers=PREVIEW_WORKERS)
        _ROOT_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=PREVIEW_ROOT_WORKERS)
    real_git, real_records = git_reads._git, git_reads.session_records

    def run_git(where, *args):
        if args == _WORKTREE_LIST_ARGS:
            return _memo(("git", where), lambda: real_git(where, *args))
        return real_git(where, *args)

    git_reads._git = run_git
    git_reads.session_records = lambda: _memo("sessions", real_records)

    def undo():
        global _RUN, _POOL, _ROOT_POOL
        for pool in (_POOL, _ROOT_POOL):
            if pool is not None:
                pool.shutdown()
        _POOL = _ROOT_POOL = None
        _RUN = None
        git_reads._git, git_reads.session_records = real_git, real_records
    return undo


def _first_cwd_by_pid(table):
    found = {}
    for pid, cwd in table:
        found.setdefault(pid, cwd)
    return found


def _all_cwds_macos():
    return _memo("cwds", _read_all_cwds_macos)


def _read_all_cwds_macos(timeout=60):
    """Every process's cwd as [(pid, cwd)], from ONE `lsof -d cwd -Fpn` (the per-pid read cost
    about 25 s per call on a real machine). `None` when lsof could not answer: any exit code
    but 0 or 1 (1 means some process was not readable, the same out-of-scope case as a
    per-pid `None`). An EMPTY table is also `None`: lsof printed nothing, which cannot be
    "no process anywhere"."""
    try:
        answer = _nowindow.run(["lsof", "-d", "cwd", "-Fpn"], capture_output=True, text=True,
                                timeout=timeout)
    except Exception:
        return None
    if answer.returncode not in (0, 1):
        return None
    table = []
    pid = None
    for line in answer.stdout.splitlines():
        if line.startswith("p"):
            pid = int(line[1:]) if line[1:].isdigit() else None
        elif line.startswith("n") and pid is not None:
            table.append((pid, line[1:]))
    # A running machine always has processes; an empty table is a failed read, not "nobody".
    return table or None


def processes_in(path: str):
    """Return `(inside_pids, unreadable_pids)`, both lists (possibly empty), for the pre-removal
    check in `decide_worktree`. `inside_pids` is `None` (with `unreadable_pids` also `None`)
    when the pid ENUMERATION itself failed: keep everything and remove no worktree.

    A single pid whose OWN cwd cannot be read is OUT OF SCOPE, never a reason to keep
    (unattended-sweep-stops-proven-orphans). `unreadable_pids` is still returned, so a caller
    MAY report how many were skipped, but `decide_worktree` does not let it block a removal.
    Identical on POSIX and Windows: both dispatch through this same `process_cwd`."""
    if sys.platform == "darwin":
        table = _all_cwds_macos()
        if table is None:
            return None, None
        return [pid for pid, cwd in table if _cwd_under_checkout(cwd, path)], []
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
# Reached only from `sweep_repo`'s own `if confirm and decision["action"] == "reap":` check,
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
    return os.path.join(git_reads.config_dir(), "janitor", "restore-log.jsonl")


def default_run_log_path() -> str:
    return os.environ.get("JANITOR_RUN_LOG") or os.path.join(
        git_reads.config_dir(), "state", "janitor-runs.jsonl")


def _removed_count(decisions):
    return sum(1 for d in decisions if d["action"] == "reap" and not d.get("error"))


def append_run_log(path: str, results):
    """One JSON line per repository, so a run's yield is readable later. Never fails the sweep:
    the reaping is done by now, and a log that cannot be written is only a missing line."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        lines = []
        for result in results:
            try:
                free = shutil.disk_usage(result["root"]).free
            except OSError:
                free = None  # unknown, never a made-up number
            lines.append(json.dumps({
                "root": result["root"], "free_bytes": free,
                "worktrees_removed": _removed_count(result["worktrees"]),
                "branches_reaped": _removed_count(result["branches"]),
                "time_ms": int(time.time() * 1000),
            }))
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    except (OSError, ValueError) as exc:
        print("janitor: run log not written (%s)" % exc)


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
    tip = git_reads._git(root, "rev-parse", "refs/heads/" + branch)
    if tip is None or tip.returncode != 0:
        decision["error"] = "could not resolve the branch tip; branch left alone"
        return
    commit = tip.stdout.strip()
    tomb = git_reads._git(root, "update-ref", TOMBSTONE_REF_PREFIX + branch, commit)
    if tomb is None or tomb.returncode != 0:
        decision["error"] = "tombstone write failed; branch NOT deleted"
        return
    append_restore_log(restore_log_path, root, branch, commit)
    delete = git_reads._git(root, "branch", "-D", branch)
    if delete is None or delete.returncode != 0:
        decision["error"] = "delete failed after the tombstone landed: %s" % (
            delete.stderr.strip() if delete is not None else "git gave no answer"
        )


REMOVAL_MARKER = "claude-removal-started"  # in the tree's admin dir; a finished remove deletes that dir


def _admin_dir(path: str):
    """The absolute git admin dir of worktree PATH (`.git/worktrees/<name>`), or None. The same read
    as `worktree_idle_seconds`, kept apart so the sweep-fast lane's edits there do not collide."""
    answer = git_reads._git(path, "rev-parse", "--absolute-git-dir")
    if answer is None or answer.returncode != 0 or not answer.stdout.strip():
        return None
    return answer.stdout.strip()


def _restore_cut_short(where: str, entry: dict):
    """`git_reads._git` stops `git worktree remove` at 10 s, which
    can leave a tree half deleted. `remove_worktree` writes REMOVAL_MARKER before each remove. When
    the marker is there and every dirty line is a deleted tracked file, this writes the missing
    files back from the index (`checkout-index` without -f never overwrites a file that exists), so
    `decide_worktree` sees a clean tree and the next remove finishes the job. No --force anywhere.
    LIMIT: when the cut-short remove already deleted the tree's `.git` file, git cannot read the
    tree, so it is kept as unreadable and needs a person.
    A failed remove can leave the marker on an intact tree, where a deletion may be
    a person's own. So the write-back runs only when the lock, session and process checks that
    `decide_worktree` runs after its clean check would pass. Any failed read writes nothing."""
    path = entry["path"]
    admin = _admin_dir(path)
    if not admin or not os.path.isfile(os.path.join(admin, REMOVAL_MARKER)):
        return
    dirty = git_reads.porcelain(path)
    if not dirty or not all(line.startswith(" D ") for line in dirty):
        return
    locked = git_reads.worktree_locked(where, path)
    if locked is None or (locked and stale_agent_lock_verdict(entry.get("locked_reason") or "") is not True):
        return
    if git_reads.worktree_live_session(path) is not False:
        return
    inside, _unreadable = processes_in(path)
    if inside != []:
        return
    git_reads._git(path, "checkout-index", "--all", "--quiet")  # the decide below reads the result


_LOCK_UNREADABLE = object()


def _lock_unlockable(root: str, path: str, decision: dict):
    """Re-read the lock of this one tree just before `git worktree unlock`: an agent may have
    taken a live lock since the pass listed it. True when the lock is gone, or is still the very
    lock that was judged stale, so the removal goes ahead; otherwise False, and DECISION becomes a
    keep. A lock that changed since the read is kept, even a stale one.
    LIMIT: git has no compare-and-unlock, so a lock taken between this read and the unlock is still
    cleared."""
    named = os.path.normcase(os.path.realpath(path))
    found = [e for e in parse_worktree_list(root) or []
             if os.path.normcase(os.path.realpath(e["path"])) == named]
    reason = found[0]["locked_reason"] if found else _LOCK_UNREADABLE
    if reason is None:
        decision.pop("unlock", None)  # nobody holds a lock now: nothing to take off
        return True
    if (reason is not _LOCK_UNREADABLE and reason == decision.get("lock_reason")
            and (stale_agent_lock_verdict(reason) is True
                 or own_agent_lock_verdict(reason) is True)):
        return True
    decision.pop("unlock", None)
    decision["action"] = "keep"
    decision["reason"] = ("unreadable-subject" if reason is _LOCK_UNREADABLE
                          else "locked: %s" % reason)
    return False


def remove_worktree(root: str, path: str, decision: dict):
    if decision.get("unlock") and not _lock_unlockable(root, path, decision):
        return
    if decision.get("unlock"):  # a stale agent lock; never --force
        unlocked = git_reads._git(root, "worktree", "unlock", path)
        if unlocked is None or unlocked.returncode != 0:
            decision["error"] = "unlock failed: %s" % (
                unlocked.stderr.strip() if unlocked is not None else "git gave no answer")
            return
    admin = _admin_dir(path)
    if admin:
        try:
            with open(os.path.join(admin, REMOVAL_MARKER), "w", encoding="utf-8") as handle:
                handle.write("%d\n" % int(time.time()))
        except OSError:
            pass  # no marker: a cut-short remove is kept as dirty, as before
    answer = git_reads._git(root, "worktree", "remove", path)
    if answer is None or answer.returncode != 0:
        decision["error"] = "remove failed: %s" % (
            answer.stderr.strip() if answer is not None else
            "git gave no answer (cut short at its time limit, or git did not start); a later "
            "agent end finishes a cut-short remove"
        )
        if decision.get("unlock"):
            # The lock came off for this removal only. Put it back, so the worktree is no
            # less guarded than before, and say which way it went.
            relock = git_reads._git(root, "worktree", "lock", "--reason",
                                decision.get("lock_reason") or "locked", path)
            decision["error"] += "; lock %s" % (
                "restored" if relock is not None and relock.returncode == 0 else "NOT restored")


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
    entries = read_restore_log(restore_log_path)

    def row_key(e):
        # The same repository can be spelled many ways in the log (slashes, case, 8.3 names).
        repo = e.get("repo")
        if not isinstance(repo, str) or not repo:
            return None
        branch = e.get("branch")
        return (os.path.normcase(os.path.realpath(repo)), branch.lower() if isinstance(branch, str) else branch, e.get("commit"))

    unexpired = {row_key(e) for e in entries
                 if isinstance(e.get("time_ms"), (int, float)) and not isinstance(e.get("time_ms"), bool)
                 and now_ms - e["time_ms"] < TOMBSTONE_TTL_MS}
    for entry in entries:
        repo = entry.get("repo")
        branch = entry.get("branch")
        when = entry.get("time_ms")
        commit = entry.get("commit")
        if not isinstance(repo, str) or not repo or not isinstance(branch, str) or not branch \
                or not isinstance(commit, str) or not commit \
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
            # The ref is keyed by branch name, so a later reap of the same name overwrites it.
            # Drop it only while it still holds THIS entry's commit; the old-value argument
            # makes git refuse on a mismatch. A mismatch keeps the ref and is not an error.
            ref = TOMBSTONE_REF_PREFIX + branch
            # One commit can have two log rows (a branch reaped twice at one tip). The ref stays
            # while any unexpired row for the same repo, branch and commit still needs it.
            if row_key(entry) in unexpired:
                decision["reason"] += "; ref kept: an unexpired entry names the same commit"
                continue
            held = git_reads._git(repo, "rev-parse", "-q", "--verify", ref)
            if held is None or held.returncode not in (0, 1) or (
                    held.returncode == 1 and held.stderr.strip()):
                # Exit 1 with empty stderr means the ref is gone. Any other failure, exit 1 with a
                # message included (a broken ref), is not an answer: keep the ref.
                decision["error"] = "ref read failed: %s" % (
                    held.stderr.strip() if held is not None else "git gave no answer")
                continue
            if held.returncode == 1 or held.stdout.strip() != commit:
                if held.returncode == 0:
                    decision["reason"] += "; ref kept: it holds a younger restore point"
                continue
            dropped = git_reads._git(repo, "update-ref", "-d", ref, commit)
            if dropped is None or dropped.returncode != 0:
                decision["error"] = "drop failed: %s" % (
                    dropped.stderr.strip() if dropped is not None else "git gave no answer"
                )
    return decisions


# ------------------------------------------------------------------ sweeping one repository


def prune_registrations(root: str, confirm: bool):
    """Stale worktree registrations, named by `git worktree prune -n -v`. Under `confirm`, runs
    `git worktree prune` and nothing else. Returns {"names": [...], "error": str|None}; `names`
    is None when git could not answer, and then nothing is pruned."""
    preview = git_reads._git(root, "worktree", "prune", "-n", "-v")
    if preview is None or preview.returncode != 0:
        return {"names": None, "error": "git worktree prune -n gave no answer"}
    names = [line.strip() for line in (preview.stdout + preview.stderr).splitlines()
             if line.strip()]
    result = {"names": names, "error": None}
    if confirm and names:
        done = git_reads._git(root, "worktree", "prune")
        if done is None or done.returncode != 0:
            result["error"] = "prune failed: %s" % (
                done.stderr.strip() if done is not None else "git gave no answer")
    return result


def is_link(path) -> bool:
    """True for a symlink or a Windows reparse point (a junction, which `os.path.islink`
    never reports). True when the path cannot be read: it is not ours to delete."""
    try:
        st = os.lstat(path)
    except OSError:
        return True
    if os.path.islink(path):
        return True
    return bool(hasattr(st, "st_file_attributes")
                and st.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def husk_verdict(root: str, path: str, entries, names):
    """One folder's verdict, or None when it is not a husk candidate. A husk is a real folder
    directly under `<root>/.claude/worktrees/` that git does not list as a worktree, is not
    empty, and holds only entries named in `huskNames`. Returns {"path", "action":
    "husk"|"keep", "reason"}. A live session or any process inside is "keep": a supervisor
    there would only recreate it. An unreadable folder or check is "keep" too. The folder's
    parent must be the repository's own `.claude/worktrees`, not a link out of it. The check
    sees a process by its cwd only: a process outside the folder that holds a file inside is
    not seen."""
    own_base = os.path.join(os.path.realpath(root), ".claude", "worktrees")
    if os.path.normcase(os.path.realpath(os.path.dirname(path))) != os.path.normcase(own_base):
        return None
    if is_link(path) or not os.path.isdir(path):
        return None
    registered = {os.path.normcase(os.path.realpath(e["path"])) for e in entries}
    if os.path.normcase(os.path.realpath(path)) in registered:
        return None
    keep = {"path": path, "action": "keep", "reason": "unreadable-subject"}
    try:
        contents = os.listdir(path)
    except OSError:
        return keep
    if not contents or not set(contents) <= set(names):
        return None
    live = git_reads.worktree_live_session(path)
    inside, _ = processes_in(path)
    if live is None or inside is None:
        return keep
    if live:
        return {"path": path, "action": "keep", "reason": "live-session"}
    if inside:
        return {"path": path, "action": "keep", "reason": "process-inside: pid %s"
                % ", ".join(str(p) for p in sorted(inside))}
    return {"path": path, "action": "husk", "reason": "only " + ", ".join(sorted(contents))}


def find_husks(root: str, entries, names):
    """Every husk verdict under `<root>/.claude/worktrees/` (none when `names` is empty).
    None when the folder cannot be read: the scan is unknown, never zero."""
    base = os.path.join(root, ".claude", "worktrees")
    if not names or not os.path.isdir(base):
        return []
    try:
        listing = sorted(os.listdir(base))
    except OSError:  # unreadable folder: unknown, the run goes on
        return None
    verdicts = (husk_verdict(root, os.path.join(base, n), entries, names) for n in listing)
    return [v for v in verdicts if v]


def find_strays(root: str, entries):
    """Absolute paths of the entries directly under `<root>/.claude/worktrees/` that git does
    not register as a worktree: a leftover folder, a stray file, a backup. LISTED, never
    deleted. A husk (a folder of only `huskNames`) is one of them until it is reaped."""
    base = os.path.join(root, ".claude", "worktrees")
    if not os.path.isdir(base):
        return []
    try:
        names = sorted(os.listdir(base))
    except OSError as exc:  # unreadable folder: no strays listed, the sweep goes on
        print("janitor: worktrees folder unreadable (%s)" % exc)
        return None
    registered = {os.path.normcase(os.path.realpath(e["path"])) for e in entries}
    return [p for p in (os.path.join(base, n) for n in names)
            if os.path.normcase(os.path.realpath(p)) not in registered]


def reap_husk(root: str, decision: dict, names):
    """Delete one proven husk. The proof is run again right before the delete, because the
    folder may have changed since the preview. `shutil.rmtree` never follows a link inside, and
    a folder that is itself a link is refused. Any error keeps the folder and is reported."""
    path = decision["path"]
    entries = parse_worktree_list(root)
    if entries is None:
        decision["error"] = "worktree list unreadable"
        return
    again = husk_verdict(root, path, entries, names)
    if again is None or again["action"] != "husk":
        decision["action"] = "keep"
        decision["reason"] = "changed before delete: " + (again["reason"] if again else "no longer a husk")
        return
    try:
        shutil.rmtree(path)
    except OSError as exc:
        decision["error"] = "delete failed: %s" % exc


# ------------------------------------------------------------------ build folders and their trash
#
# docs/decisions/build-dirs-reaped-at-agent-end.md. The agent-end reap renames a proven build folder to a
# trash name, and a detached child deletes it. The pattern and the scan live here, one home: the reap
# (agent_end_reap.py) and the sweep below both call them.

DEFAULT_BUILD_DIRS = ("native/build", ".build", "DerivedData")
TRASH_RE = re.compile(r"^.+\.reap-trash-[0-9a-f]{12}$")


def trash_name(folder: str) -> str:
    """The sibling path a reap renames FOLDER to."""
    return "%s.reap-trash-%s" % (folder, uuid.uuid4().hex[:12])


def is_trash_name(basename: str) -> bool:
    return bool(TRASH_RE.match(basename))


def build_dir_names(optout):
    """The folder names a reap deletes: the defaults plus `buildDirs`. None (delete nothing) when
    the opt-out file is unreadable or mis-shaped."""
    return None if optout is None else set(DEFAULT_BUILD_DIRS) | set(optout.get("buildDirs", []))


def scan_worktree(wt: str, names, stop_at=None):
    """`(builds, trash)`: the real folders under WT named in NAMES, and the trash names. A name with
    `/` matches one path under WT. A bare name matches at any depth. A link is never listed and
    never walked. A folder the walk could not read, or the time STOP_AT cut off, is not listed:
    unlisted means keep."""
    builds, trash = [], []
    for dirpath, dirnames, _ in os.walk(wt):
        if stop_at is not None and time.monotonic() > stop_at:
            break
        walk = []
        for d in dirnames:
            full = os.path.join(dirpath, d)
            if d == ".git" or is_link(full):
                continue
            if is_trash_name(d):
                trash.append(full)
            elif d in names or os.path.relpath(full, wt).replace(os.sep, "/") in names:
                builds.append(full)
            else:
                walk.append(d)
        dirnames[:] = walk
    return builds, trash


def trash_verdict(path: str):
    """`(delete, reason)` for one trash folder. Keep on a live session, a process inside, or any
    read that cannot tell."""
    if is_link(path) or not os.path.isdir(path):
        return False, "not a real folder"
    live = git_reads.worktree_live_session(path)
    inside, _ = processes_in(path)
    if live is None or inside is None:
        return False, "unreadable-subject"
    if live:
        return False, "live-session"
    if inside:
        return False, "process-inside: pid %s" % ", ".join(str(p) for p in sorted(inside))
    return True, "leftover trash"


def find_trash(root: str, entries):
    """Every trash folder in a registered, non-primary worktree directly under
    `<root>/.claude/worktrees/`, as {"path", "action": "trash"|"keep", "reason"}."""
    base = os.path.normcase(os.path.join(os.path.realpath(root), ".claude", "worktrees"))
    found = []
    for entry in entries:
        path = entry["path"]
        if (entry.get("bare") or os.path.normcase(os.path.dirname(os.path.realpath(path))) != base
                or _is_primary_checkout(path) is not False or is_link(path)):
            continue
        for folder in scan_worktree(path, set())[1]:
            delete, reason = trash_verdict(folder)
            found.append({"path": folder, "action": "trash" if delete else "keep", "reason": reason})
    return found


def reap_trash(decision: dict):
    """Delete one trash folder, proven again right before. `rmtree` never follows a link inside."""
    delete, reason = trash_verdict(decision["path"])
    if not delete:
        decision["action"], decision["reason"] = "keep", "changed before delete: " + reason
        return
    try:
        shutil.rmtree(decision["path"])
    except OSError as exc:
        decision["error"] = "delete failed: %s" % exc


def _is_toplevel(path: str) -> bool:
    """True when the VCS says PATH is its own repository's top level."""
    answer = git_reads._git(path, "rev-parse", "--show-toplevel")
    return (answer is not None and answer.returncode == 0 and os.path.normcase(
        os.path.realpath(answer.stdout.strip())) == os.path.normcase(os.path.realpath(path)))


MODES = ("full", "tier1", "branches")


REAPER_SCRIPT = "reap:worktrees"
# session_end_sweep.py kills this sweep at 25 s (SWEEP_TIMEOUT_SECONDS). The repo's own script has
# to end well inside that, or the kill orphans its npm child, so it gets 15 s. After a timeout the
# older rules alone judge the trees.
REAPER_TIMEOUT_SECONDS = 15


def repo_reaper(root: str):
    """The repo's own agent-worktree remover: ("none", None) when `<root>/package.json` is absent
    or defines no `reap:worktrees` script, ("script", None) when it does, ("unreadable", why) when
    package.json cannot be read or parsed. The agent rule needs "none"."""
    package = os.path.join(root, "package.json")
    if not os.path.isfile(package):
        return "none", None
    try:
        with open(package, encoding="utf-8") as handle:
            scripts = json.load(handle).get("scripts") or {}
        return ("script" if REAPER_SCRIPT in scripts else "none"), None
    except Exception as exc:
        return "unreadable", "package.json unreadable: %s" % exc


def run_repo_reaper(root: str):
    """Run `npm run reap:worktrees -- --remove` in ROOT. Returns None on success, else why it
    failed. npm is resolved with shutil.which (npm.cmd on Windows); prompts are off."""
    npm = shutil.which("npm")
    if npm is None:
        return "npm not found"
    try:
        done = _nowindow.run(
            [npm, "run", REAPER_SCRIPT, "--", "--remove"], cwd=root, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=REAPER_TIMEOUT_SECONDS,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"})
    except Exception as exc:
        return "npm run %s failed: %s" % (REAPER_SCRIPT, exc)
    if done.returncode != 0:
        return "npm run %s exited %d: %s" % (REAPER_SCRIPT, done.returncode,
                                             (done.stderr or done.stdout).strip()[-200:])
    return None


# Only the SessionEnd run has a deadline. session_end_sweep.py kills its sweep after min(25 s,
# the time its hook has left) and passes that number as `--deadline-seconds N`. The budget counts
# from the start of the pass: the pass judges trees until min(JUDGE_BUDGET_SECONDS, N minus
# DEADLINE_TAIL_SECONDS) seconds after it started. A tree judged at the last moment still costs
# about 7.5 s, then the branch, leftover-folder and listener work follows, so the tail is that
# 7.5 s. The scheduled job and a person's run have no budget. A tree the pass did not reach is
# kept ("not judged: deadline") and the next run judges it.
JUDGE_BUDGET_SECONDS = 12
DEADLINE_TAIL_SECONDS = 7.5
_now = time.monotonic  # `main` reads it at a pass's start; the cases replace it with their own clock
_DEADLINE = None  # a `_now()` time while `main` runs; None means no deadline


def _past_deadline() -> bool:
    return _DEADLINE is not None and _now() >= _DEADLINE


def _same_folder(a: str, b: str) -> bool:
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def _oldest_idle_first(entries):
    """ENTRIES with the longest-idle tree first: the likeliest removals come before the deadline.
    A tree whose idle time cannot be read goes last; it is kept either way. Each entry keeps its
    read as "idle", and `decide_worktree` uses it: one idle read per tree per pass."""
    idle = {}
    for e in entries:  # a read past the deadline never starts; that tree is "not judged"
        idle[e["path"]] = (None if e.get("bare") or _past_deadline()
                           else worktree_idle_seconds(e["path"]))
    return sorted((dict(e, idle=idle[e["path"]]) for e in entries), key=lambda e: (idle[e["path"]] is None, -(idle[e["path"]] or 0)))


FETCH_THROTTLE_SECONDS = 600  # one fetch and one ls-remote per repository per 10 minutes


def _fetch_record_path(key: str) -> str:
    return os.path.join(git_reads.config_dir(), "state", "sweep-fetch",
                        hashlib.sha256(key.encode("utf-8")).hexdigest()[:32])


def _fetch_throttled(root: str) -> bool:
    """True when the SessionEnd run (the only one with a deadline) fetched this clone less than
    FETCH_THROTTLE_SECONDS ago. The record is one file per clone, keyed by its common git dir,
    holding wall-clock Unix seconds. A missing, corrupt, non-finite or future record reads as
    "fetch now". The scheduled job and a person's run are never throttled. Decided once per
    clone per run, so `_live_remote_heads` agrees with `_fetch_prune`."""
    if _DEADLINE is None or _LIVE_HEADS is None:
        return False
    key = _common_dir_key(root)
    if key is None:
        return False
    if (key, "throttled") not in _LIVE_HEADS:
        try:
            with open(_fetch_record_path(key), encoding="utf-8") as handle:
                age = time.time() - float(handle.read().strip())
            _LIVE_HEADS[(key, "throttled")] = math.isfinite(age) and 0 <= age < FETCH_THROTTLE_SECONDS
        except (OSError, ValueError):
            _LIVE_HEADS[(key, "throttled")] = False
    return _LIVE_HEADS[(key, "throttled")]


def _record_fetch(root: str) -> None:
    """Keep the time of a fetch that succeeded; a failed fetch is retried next run. An
    unwritable state folder only loses the throttle."""
    key = _common_dir_key(root)
    if key is None:
        return
    try:
        path = _fetch_record_path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(repr(time.time()))
    except OSError:
        pass


def _fetch_prune(root: str) -> bool:
    """`git fetch --prune --no-tags` in ROOT, so the pushed and merged reads see the remote as it
    is now: its current default branch, and no tracking ref for a head deleted there. It moves
    only remote-tracking refs, so a preview runs it too. True when it succeeded. A failed fetch
    does not stop the run: the reads that follow keep each tree they cannot settle. The timeout is
    10 s, or the time left to the run's deadline when that is less."""
    if _fetch_throttled(root):
        return True  # fetched within the window: the remote-tracking refs are fresh enough
    left = 10 if _DEADLINE is None else min(10, _DEADLINE - _now())
    if left <= 0:
        return False
    try:  # prompts off: an unattended run never waits on a login window
        done = _nowindow.run(
            ["git", "-C", root, "fetch", "--prune", "--no-tags"], capture_output=True, timeout=left,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"})
    except Exception:
        return False
    if done.returncode == 0:
        _record_fetch(root)
    return done.returncode == 0


def sweep_repo(root: str, confirm: bool, restore_log_path: str, mode: str = "full",
               attended: bool = False):
    """One repository. `mode` "full" is the whole sweep. "tier1" acts for real, with no
    --confirm, and only on stale registrations and husks: no worktree, branch or process work.
    "branches" reaps branches only (preview without --confirm), removes no worktree, and holds
    every branch any worktree has checked out. "fast" judges worktrees only, with no fetch, no
    remote read and no branch work: a tree goes only when its HEAD is already in the default
    branch, and the default branch must be a remote-tracking ref."""
    if mode == "tier1":
        confirm = True
    result = {"root": root, "refused": None, "branches": [], "worktrees": [], "listeners": [],
              "pruned": None, "husks": [], "strays": [], "trash": []}

    optout = read_optout(root)  # once: protected prefixes and huskNames both come from it
    sweep_enabled, protected_prefixes, optout_ok = _optout_fields(optout)
    if not optout_ok:
        result["refused"] = "unreadable-optout"
        return result
    if not sweep_enabled:
        result["refused"] = "opted-out"
        return result

    if mode not in ("tier1", "fast") and not _past_deadline():
        if not _fetch_prune(root) and _FETCH_FAILED is not None:
            _FETCH_FAILED.add(root)
    base = git_reads.resolve_default_base(root)
    if base is None and mode != "tier1":
        result["refused"] = "no-default-base"
        return result
    if mode == "fast" and not base.startswith("origin/"):
        # A local default branch may hold work no remote has: "in main" is no proof of a copy.
        result["refused"] = "no-remote-default-base"
        return result
    # One read for every "is it in main?" below. None (tier1, or a read that failed) leaves each
    # decision to ask git for itself, except in "fast", which keeps what it cannot prove.
    batch = None if mode == "tier1" else merged_batch(root, base)

    # Before the worktree list is read, so a pruned registration is not judged as a worktree.
    # "branches" and "fast" prune nothing: a stale registration then keeps its branch held.
    if mode not in ("branches", "fast"):
        result["pruned"] = prune_registrations(root, confirm)

    # The agent rule (when-a-worktree-may-be-removed) is the default remover of finished agent
    # trees. A repo with its own `reap:worktrees` script gets that script instead, run before the
    # list is read so the trees it removes are not judged; an unreadable package.json turns the
    # rule off.
    agent_rule = mode == "full" and not attended
    if agent_rule:
        reaper, why = repo_reaper(root)
        if reaper != "none":
            agent_rule = False
            if reaper == "unreadable":
                result["reaper"] = why
            elif confirm and _past_deadline():
                result["reaper"] = "not run: deadline"
            elif confirm:
                result["reaper"] = run_repo_reaper(root) or "ran"
            else:
                result["reaper"] = "would run"

    entries = parse_worktree_list(root)
    if entries is None:
        result["refused"] = "unreadable-worktree-list"
        return result

    if mode == "branches" and not entries:
        # No worktree list means no branch is held; refuse rather than reap on that.
        result["refused"] = "unreadable-worktree-list"
        return result

    if result["pruned"] and result["pruned"]["names"] and not result["pruned"]["error"]:
        # Confirm prunes these before anything else is judged; a preview must predict that run.
        # A failed real prune leaves them registered, so they stay.
        entries = [e for e in entries if not e["prunable"]]

    branches = [] if mode in ("tier1", "fast") else list_local_branches(root)
    if branches is None:
        result["refused"] = "unreadable-branch-list"
        return result

    # Worktrees go first: a branch stays held while ANY entry that is not removed holds it. An
    # entry is removed in THIS run (confirm), or would be (preview: action reap). A removal
    # that failed (decision["error"]) keeps its entry. A primary checkout is never removed.
    removed = set()

    def judge(entry):
        """The decision for one entry, or None when none is ever recorded against it."""
        if entry.get("bare"):
            return None
        # Past the deadline no git read starts in a tree's folder, the primary-checkout read
        # included. ROOT is the primary checkout in a SessionEnd run: it gets no decision.
        if _past_deadline() and _same_folder(entry["path"], root):
            return None
        if _past_deadline():
            return {"path": entry["path"], "action": "keep", "reason": "not judged: deadline"}
        is_primary = _is_primary_checkout(entry["path"])
        if is_primary is True:
            return None  # the clone's one primary checkout: no decision is ever recorded
        if is_primary is None:
            # Could not tell whether this IS the primary checkout. Rule 7's direction: an
            # unreadable subject means keep, never a guess that it is safe to evaluate.
            return {"path": entry["path"], "action": "keep", "reason": "unreadable-subject"}
        return decide_worktree(root, entry, attended, agent_rule, batch, mode == "fast")

    judged = _oldest_idle_first(entries) if mode in ("full", "fast") else []
    if judged and mode == "full" and not _past_deadline():
        prime_pushed(root, judged)
    for entry, decision in zip(judged, _pmap(judge, judged, confirm)):
        if decision is None:
            continue
        if (decision["action"] == "keep" and decision["reason"] == "unreadable-subject"
                and _FETCH_FAILED is not None and root in _FETCH_FAILED):
            decision["reason"] += ": fetch failed"  # the likely cause of an unsettled read
        elif (decision["action"] == "keep" and decision["reason"] == "unreadable-subject"
                and _fetch_throttled(root)):
            decision["reason"] += ": fetch throttled"  # no fetch and no ls-remote ran this window
        result["worktrees"].append(decision)
        if confirm and decision["action"] == "reap":
            if _past_deadline():
                decision.update(action="keep", reason="not removed: deadline")
            else:
                remove_worktree(root, entry["path"], decision)
        gone = decision["action"] == "reap"
        gone = gone and not decision.get("error")
        if gone:
            removed.add(entry["path"])

    checked_out_branches = {e["branch"] for e in entries
                            if e.get("branch") and e["path"] not in removed}

    def judge_branch(b):
        # The clock is read before the decision starts and again after it: a reap follows at
        # once, so a decision that ended past the deadline is not reaped.
        late = {"name": b, "action": "keep", "reason": "not judged: deadline"}
        if _past_deadline():
            return late
        decision = decide_branch(root, base, b, protected_prefixes, checked_out_branches, batch)
        return late if decision["action"] == "reap" and _past_deadline() else decision

    for branch, decision in zip(branches, _pmap(
            judge_branch,
            branches, confirm)):
        result["branches"].append(decision)
        if confirm and decision["action"] == "reap":
            reap_branch(root, branch, decision, restore_log_path)

    if mode in ("branches", "fast"):
        return result

    # Past the deadline the folder scans and their reaps wait for the next run. An unscanned
    # folder is unknown (None), never zero.
    husk_names = optout.get("huskNames", [])
    result["husks"] = None if _past_deadline() else find_husks(root, entries, husk_names)
    if confirm:
        for decision in result["husks"] or []:
            if decision["action"] == "husk":
                if _past_deadline():
                    decision.update(action="keep", reason="not reaped: deadline")
                else:
                    reap_husk(root, decision, husk_names)

    result["trash"] = None if _past_deadline() else find_trash(root, entries)
    if confirm:
        for decision in result["trash"] or []:
            if decision["action"] == "trash":
                if _past_deadline():
                    decision.update(action="keep", reason="not reaped: deadline")
                else:
                    reap_trash(decision)

    result["strays"] = find_strays(root, entries)  # after the husk reap: a deleted husk is gone

    if mode == "tier1":
        return result

    checkout_paths = [root] + [e["path"] for e in entries if not e.get("bare")]
    if _past_deadline():
        result["listeners"] = None  # not read; the report says UNREADABLE, the next run reads
        return result
    listener_entries = find_swept_listeners(checkout_paths)
    if listener_entries is None:
        result["listeners"] = None  # the machine-wide listener enumeration itself failed
    else:
        for entry in listener_entries:
            decision = decide_listener(entry)
            result["listeners"].append(decision)
            if confirm and decision["action"] == "reap":
                if _past_deadline():
                    decision.update(action="keep", reason="not reaped: deadline")
                else:
                    reap_listener(decision)

    return result


# ------------------------------------------------------------------ reporting


def print_sweep_report(results, confirm: bool, out=sys.stdout):
    mode = "CONFIRM: reaping for real" if confirm else "PREVIEW: no branch or worktree is deleted"
    print("janitor sweep -- %s" % mode, file=out)

    branch_counts = Counter()
    worktree_counts = Counter()
    listener_counts = Counter()
    husk_counts = Counter()
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
        pruned = result.get("pruned")
        has_prune = pruned and (pruned["names"] is None or pruned["names"])
        if not result["branches"] and not result["worktrees"] and not result["listeners"] \
                and not has_prune and result.get("husks", []) == [] and result.get("strays", []) == []:  # None is unknown
            print("  nothing to examine", file=out)
        if result.get("reaper"):
            print("  reaper    %s: %s" % (REAPER_SCRIPT, result["reaper"]), file=out)
        if pruned and pruned["names"] is None:
            print("  prune     UNREADABLE -- %s; nothing pruned" % pruned["error"], file=out)
        elif pruned:
            for name in pruned["names"]:
                line = "  prune     %-5s %s" % ("PRUNE" if confirm else "WOULD", name)
                if pruned["error"]:
                    line += "  [ERROR: %s]" % pruned["error"]
                print(line, file=out)
        if result.get("husks") is None:
            print("  husk      UNKNOWN -- the husk scan could not read the worktrees folder, or "
                  "the deadline came first", file=out)
        if result.get("trash", []) is None:
            print("  trash     UNKNOWN -- not scanned: deadline", file=out)
        for h in result.get("husks") or []:
            husk_counts[h["action"]] += 1
            tag = "KEEP" if h.get("error") else {"husk": "REAP" if confirm else "WOULD"}.get(
                h["action"], "KEEP")
            line = "  husk      %-5s %-60s %s" % (tag, h["path"], h["reason"])
            if h.get("error"):
                line += "  [ERROR: %s]" % h["error"]
            print(line, file=out)
        for t in result.get("trash") or []:
            tag = "KEEP" if t["action"] == "keep" or t.get("error") else ("REAP" if confirm else "WOULD")
            print("  trash     %-5s %-60s %s%s" % (tag, t["path"], t["reason"],
                                                   "  [ERROR: %s]" % t["error"] if t.get("error") else ""),
                  file=out)
        if result.get("strays") is None:
            print("  stray     UNKNOWN -- the stray scan could not read the worktrees folder",
                  file=out)
        for stray in result.get("strays") or []:
            print("  stray     KEEP  %-60s not a registered worktree; never deleted"
                  % os.path.basename(stray), file=out)
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
    if any(r.get("husks") is None and not r.get("refused") for r in results):
        print("  leftover folders: unknown (folder unreadable, or the deadline came first)",
              file=out)
    else:
        print("  leftover folders: %d, kept: %d"
              % (husk_counts["husk"], husk_counts["keep"]), file=out)
    if any(r.get("strays") is None and not r.get("refused") for r in results):
        print("  strays under .claude/worktrees (kept): unknown (folder unreadable)", file=out)
    else:
        print("  strays under .claude/worktrees (kept): %d"
              % sum(len(r.get("strays") or []) for r in results), file=out)
    print("  stale worktree registrations: %d" % sum(
        len(r["pruned"]["names"] or []) for r in results if r.get("pruned")), file=out)
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
            print("    pid=%s port=%s %s" % (d["pid"], d.get("port", "-"),
                                            d.get("cwd") or d.get("missing") or "?"), file=out)
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
                         help="actually delete branches, worktrees and leftover folders (husks), or drop tombstones")
    parser.add_argument("--attended", action="store_true",
                         help="a person's run: skip the merged and idle-1-hour keeps. Without "
                              "it, --confirm removes a worktree only when it is both")
    parser.add_argument("--deadline-seconds", type=float, metavar="N",
                         help="the SessionEnd run only: N is the time left before the caller kills "
                              "this sweep. The budget counts from the start of the pass: it "
                              "judges no tree later than min(%d s, N minus %s s) from then. Only a "
                              "run with this flag has a budget (session_end_sweep.py passes it). "
                              "Without it there is none: the scheduled job and a person's run, "
                              "with or without --confirm, judge every tree"
                              % (JUDGE_BUDGET_SECONDS, DEADLINE_TAIL_SECONDS))
    parser.add_argument("--purge", action="store_true",
                         help="purge tombstones past 90 days instead of sweeping")
    parser.add_argument("--restore-log", metavar="PATH",
                         help="override the restore log path (default: under the config dir)")
    parser.add_argument("--root", metavar="PATH",
                         help="sweep the one repository PATH belongs to (PATH may be a linked "
                              "worktree or a folder inside it); adds to any ROOT given")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--tier1", action="store_true",
                       help="only stale registrations and husks. The one mode that acts "
                            "without --confirm: it removes only proven junk, and a hook "
                            "runs it. No worktree, branch or process work")
    modes.add_argument("--branches", action="store_true",
                       help="only branches: reap those with no unique work, removing no "
                            "worktree; a preview without --confirm")
    modes.add_argument("--fast", action="store_true",
                       help="only worktrees whose branch is already in the default branch, "
                            "judged with no fetch, no remote read and no branch work; "
                            "a preview without --confirm")
    parser.add_argument("--settings-path", metavar="PATH",
                         help="testing only: overrides the settings.json read for janitor.roots")
    args = parser.parse_args(argv)

    restore_log_path = args.restore_log or default_restore_log_path()

    if args.purge:
        decisions = purge_tombstones(restore_log_path, args.confirm)
        print_purge_report(decisions, args.confirm)
        return 0

    roots = [os.path.abspath(r) for r in args.roots]
    if args.root:
        primary = git_reads.primary_checkout(os.path.abspath(args.root))
        if primary is not None and not (
                _is_toplevel(primary) and os.path.normcase(os.path.realpath(
                    git_reads.git_common_dir(primary) or "")) == os.path.normcase(os.path.realpath(
                        git_reads.git_common_dir(os.path.abspath(args.root)) or "-"))):
            primary = None  # a submodule or a separate git dir: dirname(common dir) is wrong
        if primary is None:
            print("janitor: %s is not inside a repository" % args.root, file=sys.stderr)
            return 1
        roots.append(primary)
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

    mode = ("tier1" if args.tier1 else "branches" if args.branches
            else "fast" if args.fast else "full")
    global _LIVE_HEADS, _DEADLINE, _FETCH_FAILED
    undo = _begin_preview_cache() if not args.confirm and mode != "tier1" else (lambda: None)
    _LIVE_HEADS = {}
    _FETCH_FAILED = set()
    # Only a run given `--deadline-seconds N` has a deadline: the SessionEnd run. The scheduled
    # job and a person's run judge everything. A NaN is no
    # time left, never no deadline: it compares false against every clock reading.
    n = args.deadline_seconds
    _DEADLINE = None if n is None else _now() + (
        0 if n != n else min(JUDGE_BUDGET_SECONDS, n - DEADLINE_TAIL_SECONDS))
    try:
        return _sweep_roots(args, roots, restore_log_path, mode)
    finally:
        _LIVE_HEADS = _DEADLINE = _FETCH_FAILED = None
        undo()


def _sweep_roots(args, roots, restore_log_path, mode):
    def one(root):
        result = sweep_repo(root, args.confirm, restore_log_path, mode, args.attended)
        if args.confirm:  # one line per repository, as each finishes
            append_run_log(default_run_log_path(), [result])
        return result

    results = list(_pmap(
        one,
        roots, args.confirm or mode == "tier1", _ROOT_POOL))
    print_sweep_report(results, args.confirm or mode == "tier1")
    if args.confirm:
        if any(_removed_count(r["worktrees"]) + _removed_count(r["branches"]) for r in results):
            try:
                free = min(shutil.disk_usage(r["root"]).free for r in results)
                print("  free disk: %.1f GB" % (free / 1e9))
            except (OSError, ValueError):
                print("  free disk: unknown")
    if mode != "full":
        return 0
    if _past_deadline():
        print("\njanitor: past the time budget; dead-rooted, loose-process and simulator "
              "reads not run (the next run does them)")
        return 0
    dead = find_dead_rooted()
    print_dead_rooted_report(dead)
    if not _past_deadline():
        print_loose_processes_report(find_loose_processes())
    if args.confirm:
        reaped = reaped_listener_decisions(results)
        for d in dead or []:
            if d["action"] == "reap" and d["pid"] not in {r["pid"] for r in reaped}:
                if _past_deadline():
                    break  # the next run reaps it
                reap_listener(d)
                reaped.append(d)
        print_grace_period_report(reaped)
    if not _past_deadline():
        print_sim_report(sim_tier(args.confirm), args.confirm)
    if not _past_deadline():
        return 1 if temp_tier(args.confirm) else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
