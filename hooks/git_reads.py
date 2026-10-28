"""The git and session reads the guard and the janitor share: one `git` call, the primary
checkout, a tree's status, the default branch, a branch's proof of survival, a worktree's lock
and whether a live session stands in it.

The janitor (janitor/sweep.py, janitor/session_end_sweep.py) imports this file and no guard module,
so its start-up never loads the guard. guard_core.py imports it by name, and a test or the janitor
that patches one of these names patches it here, on the one object every reader calls. Standard
library only, plus `_nowindow` and `shared_names`, and it imports no guard module.
"""
import json
import os
import subprocess
import sys
import time
try:
    import _nowindow  # the one home of a no-window child start; a flat hooks/ file, not a guard-set member
except ImportError:  # install-hooks-whole: the guard set lands whole, the helper beside it a moment later; the guard still judges
    _nowindow = subprocess

from shared_names import config_dir  # noqa: E402  the one home, shared with the config watch


def _git(where: str, *args):
    try:
        return _nowindow.run(
            ["git", "-C", where, *args], capture_output=True, encoding="utf-8", errors="replace", timeout=10
        )
    except Exception:
        return None


def is_worktree(where: str):
    """True in a linked worktree, False in an ordinary checkout, None when unknown.

    A worktree is the tree whose git directory differs from the repository's common git directory.
    On this machine an ordinary checkout answers `.git` to both questions, while a linked
    worktree answers `<repo>/.git/worktrees/<name>` and `<repo>/.git`.
    """
    if not where or not os.path.isdir(where):
        return None
    top = _git(where, "rev-parse", "--show-toplevel")
    if top is None or top.returncode != 0 or not top.stdout.strip():
        return None
    root = top.stdout.strip()
    answer = _git(root, "rev-parse", "--git-dir", "--git-common-dir")
    if answer is None or answer.returncode != 0:
        return None
    lines = answer.stdout.splitlines()
    if len(lines) < 2:
        return None
    own = os.path.normcase(os.path.realpath(os.path.join(root, lines[0].strip())))
    common = os.path.normcase(os.path.realpath(os.path.join(root, lines[1].strip())))
    return own != common


def _common_dir(where: str):
    """Return the absolute, realpath'd git COMMON directory for `where`, or None when it could
    not be read. `git rev-parse --show-toplevel` answers `where` itself when `where` sits inside
    an ordinary checkout, but it answers the WORKTREE's own path when `where` sits inside a
    linked worktree. `git rev-parse --git-common-dir` names the ONE `.git` directory every
    worktree of a clone shares. Two `_git` calls, on purpose: the toplevel, then
    `--git-common-dir` run FROM that toplevel.

    The one read `primary_checkout` and `git_common_dir` both build on, so the two never drift
    apart (CLAUDE.md, "building-allow-list-is-the-constant").
    """
    top = _git(where, "rev-parse", "--show-toplevel")
    if top is None or top.returncode != 0:
        return None
    toplevel = top.stdout.strip()
    if not toplevel:
        return None
    common = _git(toplevel, "rev-parse", "--git-common-dir")
    if common is None or common.returncode != 0:
        return None
    common_dir = common.stdout.strip()
    if not common_dir:
        return None
    try:
        return os.path.realpath(os.path.join(toplevel, common_dir))
    except Exception:
        return None


def primary_checkout(where: str):
    """Return the PRIMARY checkout that `where` belongs to, or None when it could not be read.

    The common directory's parent (`dirname`) is always the primary checkout, ordinary checkout
    or linked worktree alike.

    Callers that need this to name a remedy (`janitor/install_launchd.py`) or to sweep the right
    repository (`janitor/session_end_sweep.py`) both used to carry their own copy of this same
    read; this is the one constant they now both point at (CLAUDE.md,
    "building-allow-list-is-the-constant").
    """
    common_dir = _common_dir(where)
    if not common_dir:
        return None
    primary = os.path.dirname(common_dir)
    if not primary or not os.path.isdir(primary):
        return None
    return primary


def git_common_dir(where: str):
    """Return the absolute git common directory for `where`, or None when it could not be read.

    This is the directory every worktree of the clone shares, so a record written here survives
    the removal of any one worktree. See `agent_home_record_path`.
    """
    return _common_dir(where)


def _inside_work_tree(where: str):
    """True inside a git working tree, False when git says this is no git tree, None when git
    gives no answer at all (git missing, a timeout, a crash).
    """
    if not where:
        return False
    answer = _git(where, "rev-parse", "--is-inside-work-tree")
    if answer is None:
        return None
    if answer.returncode == 0:
        return answer.stdout.strip() == "true"
    return False


def porcelain(where: str, pathspecs=(), ignored: bool = False):
    """Return the lines of `git status --porcelain`, or None when it cannot be read."""
    args = ["status", "--porcelain"]
    if ignored:
        args.append("--ignored")
    if pathspecs:
        args.append("--")
        args.extend(pathspecs)
    answer = _git(where, *args)
    if answer is None or answer.returncode != 0:
        return None
    return [line for line in answer.stdout.splitlines() if line.strip()]


def stash_stack(where: str):
    """Return the lines of `git stash list`, or None when it cannot be read."""
    answer = _git(where, "stash", "list")
    if answer is None or answer.returncode != 0:
        return None
    return [line for line in answer.stdout.splitlines() if line.strip()]


# ------------------------------------------------------------------ a branch's only copy
#
# `git branch -d/-D <name>` throws away a branch pointer. The FILES never move, so this is not a
# working-tree read at all: the subject is the WORK the branch names, and the question is whether
# that work exists anywhere else.
#
# Resolve the base in this order: `origin/HEAD` when it resolves, then `origin/main`, `origin/master`,
# local `main`, local `master`. None answering is UNREADABLE, never a silent pass and never a silent deny:
# a repository with no default branch this rule can find is one this rule cannot judge.
#
# THREE TESTS, ANY ONE PASSING PROVES THE WORK SURVIVES the branch:
#   ancestor       `git merge-base --is-ancestor <branch> <base>`. The branch's tip is already
#                  reachable from the base, commit id for commit id.
#   cherry-empty   `git cherry <base> <branch>` prints a `+` for every commit NOT already on the
#                  base by PATCH id, so no `+` line means every commit's content is already
#                  there, even after a rebase changed every commit id.
#   remote-contains a remote-tracking ref's history already contains the branch's tip, so a
#                  clone elsewhere holds the same commit.
# Any one of the three failing to ANSWER (not "false", but "git could not tell") makes the whole
# read unreadable, because a read that skipped a test it could not run is a guess, not a proof.
def read_default_base(where: str, remote: str = "origin"):
    """Return (short ref name, `<remote>/HEAD`'s short name), each None when git does not answer.

    The order is `<remote>/HEAD` when it resolves, then `<remote>/main`, then
    `<remote>/master`, then local `main`, then local `master`. The first that resolves wins; the
    rest are never tried. A dangling `<remote>/HEAD` falls through. The second value is the name
    the symbolic ref holds, even when that branch does not verify or a later read failed; it is ""
    when the ref is unset. A name is None when git could not run: unreadable, never "does not
    exist". The push guard reads the PUSHED remote here; the branch-delete rule and the sweep
    read `origin`.
    """
    candidates = [remote + "/main", remote + "/master", "main", "master"]
    # No --short: a local branch or tag named `<remote>/<default>` makes git print the ambiguous
    # `remotes/<remote>/<default>`. The full ref strips to the name with no such ambiguity.
    named = _git(where, "symbolic-ref", "-q", "refs/remotes/" + remote + "/HEAD")
    if named is None:  # git could not run: unreadable
        return None, None
    full_head = named.stdout.strip() if named.returncode == 0 else ""
    head = full_head.removeprefix("refs/remotes/")
    if head == full_head or not head.startswith(remote + "/"):
        head = ""
    if head:
        candidates.insert(0, head)
    for name in candidates:
        full = ("refs/remotes/" if name.startswith(remote + "/") else "refs/heads/") + name
        live = _git(where, "rev-parse", "--verify", "--quiet", full + "^{commit}")
        if live is None:  # git could not run: unreadable, never "does not exist"
            return None, head
        if live.returncode == 0:
            return name, head
    return None, head


def resolve_default_base(where: str, remote: str = "origin"):
    """The short ref name of the default branch, or None when none answers (`read_default_base`)."""
    return read_default_base(where, remote)[0]


def branch_is_ancestor(where: str, base: str, branch: str):
    """True when `branch`'s tip is already reachable from `base`, False when it plainly is not,
    None when the question could not be answered (an unresolvable revision, a git that would not
    run)."""
    answer = _git(where, "merge-base", "--is-ancestor", branch, base)
    if answer is None:
        return None
    if answer.returncode == 0:
        return True
    if answer.returncode == 1:
        return False
    return None


def branch_cherry_empty(where: str, base: str, branch: str):
    """True when `git cherry <base> <branch>` prints no `+` line: every commit's PATCH already
    sits on the base, even one a rebase or a cherry-pick gave a new commit id. None when the
    read failed."""
    answer = _git(where, "cherry", base, branch)
    if answer is None or answer.returncode != 0:
        return None
    return not any(line.startswith("+") for line in answer.stdout.splitlines())


def branch_on_remote(where: str, branch: str):
    """True when some remote-tracking ref's history already contains `branch`'s tip, False when
    none does, None when the read failed."""
    answer = _git(
        where, "for-each-ref", "--contains", branch, "--format=%(refname)", "refs/remotes"
    )
    if answer is None or answer.returncode != 0:
        return None
    return bool(answer.stdout.strip())


def branch_proof(where: str, base: str, branch: str, ancestor=None):
    """The first of the three tests that proves `branch`'s work survives it: "ancestor",
    "cherry-empty" or "on-remote", in that order. False when none does (the branch holds the only
    copy). None when any one test could not be read. ANCESTOR is the answer a caller already holds
    for the first test (one batched read for many branches): True or False; None reads it here."""
    if ancestor is None:
        ancestor = branch_is_ancestor(where, base, branch)
    if ancestor is None:
        return None
    if ancestor:
        return "ancestor"
    cherry_empty = branch_cherry_empty(where, base, branch)
    if cherry_empty is None:
        return None
    if cherry_empty:
        return "cherry-empty"
    on_remote = branch_on_remote(where, branch)
    if on_remote is None:
        return None
    return "on-remote" if on_remote else False


def branch_is_empty(where: str, base: str, branch: str):
    """True when `branch` holds no work absent elsewhere, False when it holds the only copy,
    None when any one of the three tests could not be read."""
    proof = branch_proof(where, base, branch)
    return None if proof is None else bool(proof)


def worktree_locked(where: str, target: str):
    """True when TARGET is registered as a locked worktree, False when it is registered and
    unlocked, None when the registration cannot be read, or TARGET is not a registered worktree
    of this clone at all (an unreadable state: nothing here says the removal is safe)."""
    answer = _git(where, "worktree", "list", "--porcelain")
    if answer is None or answer.returncode != 0:
        return None
    try:
        target_real = os.path.normcase(os.path.realpath(target))
    except Exception:
        return None
    for block in answer.stdout.split("\n\n"):
        lines = block.splitlines()
        if not lines or not lines[0].startswith("worktree "):
            continue
        path = lines[0][len("worktree "):].strip()
        if os.path.normcase(os.path.realpath(path)) != target_real:
            continue
        return any(line == "locked" or line.startswith("locked ") for line in lines[1:])
    return None


# Liveness reads `~/.claude/sessions/*.json` (or `${CLAUDE_CONFIG_DIR}/sessions`, the same
# override `config_dir` already answers for the frozen-path rule). A missing directory is a real,
# readable answer: zero sessions have ever recorded liveness here, so nothing stands in any tree.
# A directory that exists but cannot be LISTED is unreadable, and a bad individual record is
# skipped rather than treated as a read failure, so one corrupt file cannot make an otherwise
# readable directory look unreadable.
#
# On Windows a session record's `startedAt` is written 1.7 to 3.2 seconds after the
# kernel's own process-creation time. A correct read can fall outside a 5-second window under
# load, so the tolerance widens to 60 seconds on every platform.
SESSION_LIVE_TOLERANCE_MS = 60000

# `_process_start_ms` returns this sentinel, never `None`, when the read itself could not tell
# whether the process is alive or dead. `None` stays reserved for a CONFIRMED dead pid, so a
# caller can never coerce "I could not tell" into "it is dead."
PROCESS_START_UNREADABLE = object()


def session_records():
    """Return this machine's session records, or None when the session directory exists but
    cannot be listed at all."""
    folder = os.path.join(config_dir(), "sessions")
    if not os.path.isdir(folder):
        return []
    try:
        names = os.listdir(folder)
    except Exception:
        return None
    records = []
    for name in names:
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(folder, name), encoding="utf-8") as handle:
                records.append(json.load(handle))
        except Exception:
            continue  # one bad record does not make the whole directory unreadable
    return records


def _process_start_ms_windows(pid: int):
    """Windows arm of `_process_start_ms`. Only called when `sys.platform` says Windows, so the
    Windows-only `ctypes` import stays out of every Linux check run.

    `OpenProcess` with `PROCESS_QUERY_LIMITED_INFORMATION` (0x1000) asks for the least a read
    needs. A NULL handle is read through `GetLastError`. Code 87 (`ERROR_INVALID_PARAMETER`)
    means no process at all exists at this pid, the CONFIRMED dead case, matched to
    `_process_start_ms`'s existing `None` contract. Code 5 (`ERROR_ACCESS_DENIED`) means the
    process exists but this read cannot see into it. Any other code is also unreadable: this
    function never guesses a code it has not measured into a definite dead or alive answer.

    A valid handle's `GetProcessTimes` creation FILETIME is UTC-anchored by definition. `ps
    -o lstart=` below prints local time with no zone marker at all. FILETIME carries no such
    trap: no zone is assumed, because none is ever ambiguous.

    Cost on the reference machine: 0.137 ms per call.
    """
    import ctypes
    import ctypes.wintypes

    kernel32 = ctypes.windll.kernel32
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        error = ctypes.GetLastError()
        if error == 87:  # ERROR_INVALID_PARAMETER: no such process
            return None
        return PROCESS_START_UNREADABLE  # 5 (ERROR_ACCESS_DENIED) or any other code
    try:
        creation = ctypes.wintypes.FILETIME()
        exit_time = ctypes.wintypes.FILETIME()
        kernel_time = ctypes.wintypes.FILETIME()
        user_time = ctypes.wintypes.FILETIME()
        ok = kernel32.GetProcessTimes(
            handle, ctypes.byref(creation), ctypes.byref(exit_time),
            ctypes.byref(kernel_time), ctypes.byref(user_time),
        )
        if not ok:
            return PROCESS_START_UNREADABLE
        value = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
        return value // 10000 - 11644473600000
    finally:
        kernel32.CloseHandle(handle)


def _process_start_ms(pid: int):
    """Return a live process's start time in epoch milliseconds. Return `None` when the pid is
    CONFIRMED not running (dead). Return `PROCESS_START_UNREADABLE` when the read could not
    tell either way. A caller must never fold the third state into the second: an unreadable
    read is not proof of death.

    POSIX: `ps -o lstart=` prints the start time in THIS machine's own local clock, with no
    timezone marker at all. Read it with `time.mktime`. That call turns a naive `struct_time`
    into an epoch by treating it as LOCAL time on THIS SAME machine. The number it returns then
    lines up with the epoch millisecond a session record already carries, written by
    `Date.now()` on the same local machine.
    The trap: parsing the identical string as UTC
    introduced a five-hour offset and made a live session look expired. `calendar.timegm` and
    `datetime.fromisoformat(...).timestamp()` after tagging the string UTC both carry that trap.
    `mktime` does not, because it never assumes a zone the string never named.

    Windows has no such trap: see `_process_start_ms_windows`, called below when `sys.platform`
    says Windows.
    """
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return None
    if sys.platform.startswith("win"):
        return _process_start_ms_windows(pid)
    try:
        answer = _nowindow.run(
            ["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True, timeout=5,
        )
    except Exception:
        return PROCESS_START_UNREADABLE  # exec failed or timed out, not a dead-pid answer
    if answer.returncode != 0:
        # `ps` answers exit code 1 with empty stdout for "no such pid": CONFIRMED dead. Any
        # other nonzero code is a read failure, not a death, and stays unreadable.
        if answer.returncode == 1 and not answer.stdout.strip():
            return None
        return PROCESS_START_UNREADABLE
    text = answer.stdout.strip()
    if not text:
        return None
    try:
        parsed = time.strptime(text, "%a %b %d %H:%M:%S %Y")
        return int(time.mktime(parsed) * 1000)
    except Exception:
        return PROCESS_START_UNREADABLE  # output that does not parse is not a death either


def session_is_live(record):
    """True when the record's process id is alive AND its recorded start time still matches
    that live process's own start time, within a tolerance for the read's own granularity.
    False when the pid is CONFIRMED dead, or the record itself is malformed. None when the
    liveness read could not tell either way (`_process_start_ms` returned
    `PROCESS_START_UNREADABLE`), which a caller must treat as "cannot tell," never as False.

    A recycled pid then cannot inherit a dead session's claim. The process at that pid today
    started at a different moment than the one the record names.

    The tolerance is one-sided. `actual` (read now, fixed forever once the kernel records a
    process's creation FILETIME) more than the tolerance AHEAD of `started` (written 1.7-3.2s
    later by `Date.now()`) is the recycled-pid signature -- but a clock stepping
    BACKWARDS between those two original measurements produces the exact same shape for a
    process that never died: `started` reads too small because it was captured after the step.
    The two are indistinguishable from this reading alone, so that direction answers None
    (cannot tell), never a confident False. The other direction (`started` far AHEAD of
    `actual`) has no such legitimate reading -- `started` is always written strictly after
    `actual` -- so it stays a confident False, unchanged."""
    if not isinstance(record, dict):
        return False
    pid = record.get("pid")
    started = record.get("startedAt")
    if not isinstance(started, (int, float)) or isinstance(started, bool):
        return False
    actual = _process_start_ms(pid)
    if actual is PROCESS_START_UNREADABLE:
        return None
    if actual is None:
        return False
    diff = actual - started
    if diff > SESSION_LIVE_TOLERANCE_MS:
        return None
    return diff >= -SESSION_LIVE_TOLERANCE_MS


def _path_identity(path: str):
    """A key identifying PATH's underlying file, stable across different path spellings of one
    physical location (a Windows `subst` drive or a mapped network drive against its UNC or
    local equivalent). `None` when the identity itself could not be read.

    `os.path.realpath` does not reliably canonicalise such a spelling to the same
    string as its equivalent -- mapping drive `T:` to a UNC share left `realpath` naming
    the UNC path for one spelling and the local path for the other, so they never compared
    equal as strings. `os.stat`'s `(st_dev, st_ino)` agreed for both. That pair, not the path
    string, is the identity this function reports."""
    try:
        info = os.stat(path)
        return (info.st_dev, info.st_ino)
    except Exception:
        return None


def _under_by_identity(cwd_resolved: str, target_identity):
    """True when some ancestor of CWD_RESOLVED (itself included) is the same underlying file as
    TARGET_IDENTITY. False when every ancestor's own identity resolves and none matches. None
    when TARGET_IDENTITY itself is unreadable, or some ancestor's identity could not be read
    without another ancestor already matching -- that leaves the question open, never "no"."""
    if target_identity is None:
        return None
    ancestor = cwd_resolved
    unresolved = False
    while True:
        identity = _path_identity(ancestor)
        if identity is None:
            unresolved = True
        elif identity == target_identity:
            return True
        parent = os.path.dirname(ancestor)
        if parent == ancestor:
            break
        ancestor = parent
    return None if unresolved else False


def worktree_live_session(target: str):
    """True when a live session's cwd sits at or under TARGET. False when every session under
    TARGET is confirmed not live, or none has a cwd under TARGET at all. None when the session
    directory itself could not be read. None also when some session's cwd sits under TARGET,
    but its own liveness read came back unreadable rather than confirmed dead. None also when a
    record's cwd cannot be MATCHED against TARGET at all: neither the string compare nor the
    file-identity fallback (`_under_by_identity`) could tell, so it might be an unmatched
    spelling of a live session's own worktree.

    A record with an unreadable liveness read is never dropped by `continue` as though it were
    confirmed dead. Doing so would fold "could not tell" back into "not live," the exact defect
    this read exists to avoid."""
    records = session_records()
    if records is None:
        return None
    try:
        target_resolved = os.path.realpath(target)
    except Exception:
        return None
    target_real = os.path.normcase(target_resolved) + os.sep
    target_identity = _path_identity(target_resolved)
    saw_unreadable = False
    for record in records:
        if not isinstance(record, dict):
            continue
        cwd = record.get("cwd")
        if not isinstance(cwd, str) or not cwd:
            continue
        try:
            cwd_resolved = os.path.realpath(cwd)
        except Exception:
            continue
        cwd_real = os.path.normcase(cwd_resolved) + os.sep
        under = cwd_real.startswith(target_real)
        if not under:
            # The string spellings differ. Before concluding "not under," check whether they
            # are two spellings of the one physical location (see `_path_identity`).
            under = _under_by_identity(cwd_resolved, target_identity)
        if under is None:
            saw_unreadable = True
            continue
        if not under:
            continue
        live = session_is_live(record)
        if live is True:
            return True
        if live is None:
            saw_unreadable = True
    return None if saw_unreadable else False
