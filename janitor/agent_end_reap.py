#!/usr/bin/env python3
"""At SubagentStop, stops processes the finished agent left running in its worktree, and removes other idle agent worktrees. When a check cannot tell, it keeps.

Design: docs/decisions/agent-end-reap-stops-what-a-finished-agent-left.md.

Reads one hook payload on stdin. SubagentStop names the agent by `agent_id`. The harness names
that agent's worktree `.claude/worktrees/agent-<agent_id>` under the primary checkout.
Only SubagentStop names a target (WorktreeRemove stays
unwired). The target must have the `.claude/worktrees/<name>` shape and must not be a primary checkout.

A process is stopped only when all of these answer a confirmed yes:
- its cwd sits inside the target worktree
- no live session has a cwd inside the target (`git_reads.worktree_live_session`)
- the root of its in-worktree process tree is orphaned: climb from the process through each
  live parent whose cwd is also inside the target, then `sweep.is_orphan` on the last one.
  A live parent outside the target (a harness, a terminal) means keep.
- it is owned by the current user (`sweep.is_current_user_process`)

Any read that cannot tell means keep. One signal, by pid, through `sweep.send_signal`.

Build folders (docs/decisions/build-dirs-reaped-at-agent-end.md): the ending agent's own tree keeps
its build folders, since a finished agent is often resumed there. A later agent end reaps them once the
tree is idle 30 minutes. The worktree stage gives each other `.claude/worktrees/agent-*` tree it keeps a
build pass when that tree and its newest uncommitted change are idle AGENT_END_IDLE_SECONDS or more,
it holds no lock other than a Claude agent lock, has no live session, and no process has a cwd anywhere in it (`build_keep`). A build runs from the worktree root,
so a cwd check on the folder alone is not enough. The pass renames each build folder
(`sweep.DEFAULT_BUILD_DIRS` plus `buildDirs`) to a sibling trash name, then starts a detached child that
deletes the trash, and leftover trash names go with it. The hook never waits for the child. A folder
with a process cwd inside, a link, or any unreadable read stays. A tree the stage deadline does not
reach keeps its folders. A tree the stage removes whole needs no pass.

Worktrees (docs/decisions/when-a-worktree-may-be-removed.md): when the checks above hold for the whole worktree,
the hook KEEPS the ending agent's own worktree, with the row reason OWN_TREE_REASON; a later agent end
removes it once idle 30 minutes. It removes every other `.claude/worktrees/agent-*`
worktree idle 30 minutes or more that `sweep.decide_agent_end_worktree` clears: clean (no dirty or
untracked file), no process inside, no live lock, HEAD on a remote-tracking ref. A tree it cannot
prove keeps. The stage stops at WORKTREE_SECONDS or HOOK_BUDGET, so the hook stays inside its 60 s
timeout.

Every run appends the raw payload and the decisions to
`${CLAUDE_CONFIG_DIR:-~/.claude}/state/agent-end-payloads.jsonl`, so the payload fields the docs
leave unmeasured get measured. The file keeps the last 200 lines. Always exits 0: exit 2 on SubagentStop keeps the agent running.
"""
import contextlib
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "hooks"))
sys.path.insert(0, HERE)
import git_reads  # noqa: E402
import sweep  # noqa: E402
try:
    import _nowindow  # the one home of a no-window child start (hooks/_nowindow.py)
except ImportError:  # a hook never dies for a missing helper (it lands a moment after the hook in an install)
    _nowindow = subprocess

AGENT_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_LOG_LINES = 200  # the payload log keeps the last 200 runs
LOG_WAIT_SECONDS = 30  # one log() call waits this long, in all, for the lock and the replace; the hook's own limit is 60
LOG_RETRY_SECONDS = 0.02  # pause between two tries at the lock or the replace


class LogWaitTimeout(OSError):
    """A log() call waited past LOG_WAIT_SECONDS for the lock or the replace."""


def log_path() -> str:
    return os.path.join(git_reads.config_dir(), "state", "agent-end-payloads.jsonl")


@contextlib.contextmanager
def _log_lock(path: str, deadline: float):
    """Hold an exclusive lock on `<log>.lock` so parallel hook runs take turns. `fcntl.flock`
    on POSIX. On Windows `msvcrt.locking` with LK_NBLCK, tried every LOG_RETRY_SECONDS until
    DEADLINE (a `time.monotonic` time), then LogWaitTimeout: LK_LOCK gives up after about 10 s, and
    the body never runs without the lock."""
    with open(path + ".lock", "a+") as handle:
        if sys.platform.startswith("win"):
            import msvcrt
            while True:
                handle.seek(0)
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:  # held by another run
                    if time.monotonic() >= deadline:
                        raise LogWaitTimeout("payload log lock not taken in %d s" % LOG_WAIT_SECONDS)
                    time.sleep(LOG_RETRY_SECONDS)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)


def log(record: dict, replace_run=None):
    """Append one line and keep only the last MAX_LOG_LINES. The log is the evidence for the hook
    fields the docs leave open (docs/decisions/agent-end-reap-stops-what-a-finished-agent-left.md).
    Parallel runs take turns on a lock file, because writers lost rows without it. The temp name
    carries the pid. On Windows the replace can raise PermissionError while the destination is
    held, so it retries until LOG_WAIT_SECONDS (the lock wait counts toward the same limit).
    REPLACE_RUN names a start row written earlier by this run; the last line is replaced only
    when it carries that run id, so another agent's row is never dropped.
    A write that cannot finish in LOG_WAIT_SECONDS raises LogWaitTimeout, the only way a row is
    dropped for waiting. A failed write never fails the hook (exit stays 0); it prints one line to stderr."""
    deadline = time.monotonic() + LOG_WAIT_SECONDS
    path = log_path()
    line = json.dumps(dict(record, at=time.strftime("%Y-%m-%dT%H:%M:%S%z"))) + "\n"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with _log_lock(path, deadline):
            try:
                with open(path, encoding="utf-8") as handle:
                    kept = handle.readlines()[-(MAX_LOG_LINES - 1):]
            except OSError:
                kept = []
            if replace_run and kept and ('"run": "%s"' % replace_run) in kept[-1]:
                kept = kept[:-1]  # our own start row: the finished row takes its place
            temp = "%s.%d.tmp" % (path, os.getpid())
            with open(temp, "w", encoding="utf-8") as handle:
                handle.writelines(kept + [line])
            while True:
                try:
                    os.replace(temp, path)  # a reader never sees an empty or half-written file
                    break
                except PermissionError as exc:  # Windows: the destination is held a moment
                    if time.monotonic() >= deadline:
                        raise LogWaitTimeout("payload log replace refused for %d s: %r" % (LOG_WAIT_SECONDS, exc))
                    time.sleep(LOG_RETRY_SECONDS)
    except Exception as exc:
        print("agent_end_reap: payload log write failed: %r" % exc, file=sys.stderr)


def is_agent_worktree_shape(path: str) -> bool:
    """True when PATH is `<something>/.claude/worktrees/<name>`."""
    parts = os.path.normpath(path).replace("\\", "/").rstrip("/").split("/")
    return len(parts) >= 3 and parts[-3] == ".claude" and parts[-2] == "worktrees" and bool(parts[-1])


def target_worktree(payload: dict):
    """The agent worktree this payload names, or None."""
    event = payload.get("hook_event_name")
    if event == "SubagentStop":
        agent_id, cwd = payload.get("agent_id"), payload.get("cwd")
        if not isinstance(agent_id, str) or not AGENT_ID.match(agent_id) or not isinstance(cwd, str):
            return None
        primary = git_reads.primary_checkout(cwd)
        if not primary:
            return None
        path = os.path.join(primary, ".claude", "worktrees", "agent-" + agent_id)
    else:
        return None
    if not isinstance(path, str) or not is_agent_worktree_shape(path) or not os.path.isdir(path):
        return None
    return path


BATCH_TIMEOUT = 30  # seconds for the one cwd batch read; the hook's own limit is 60


def tree_root_orphaned(pid: int, target: str, cwd_of=None):
    """True when the root of PID's in-TARGET process tree is orphaned. False when a live parent
    outside TARGET holds the tree. None when a read could not tell."""
    cwd_of = cwd_of or sweep.process_cwd
    current = pid
    for _ in range(sweep.MAX_CLIMB):
        orphan = sweep.is_orphan(current)
        if orphan is not False:
            return orphan
        parent = sweep._parent_pid(current)
        cwd = cwd_of(parent) if parent else None
        if cwd is None:
            return None
        if not sweep._cwd_under_checkout(cwd, target):
            return False
        current = parent
    return None


def decide(target: str):
    """Return (reason, decisions). REASON is set when nothing in TARGET may be touched."""
    return _decide(target)


def cwd_reader(timeout=BATCH_TIMEOUT):
    """`(pids, cwd_of)` for every process but this one, or None when the enumeration failed.
    CWD_OF(pid) is that pid's cwd, or None when its own read failed."""
    pids = sweep.list_all_pids()
    if pids is None:
        return None
    cwd_of = sweep.process_cwd
    if sys.platform == "darwin":
        # One `lsof` for every pid: 1,300 per-pid reads at 27 ms overran the 60 s hook limit.
        # A failed batch keeps everything; it never falls back to per-pid reads.
        table = sweep._read_all_cwds_macos(timeout)
        if table is None:
            return None
        cwd_of = sweep._first_cwd_by_pid(table).get
    return [pid for pid in pids if pid != os.getpid()], cwd_of


def all_cwds(timeout=BATCH_TIMEOUT):
    """Every readable process cwd, or None when the enumeration failed."""
    read = cwd_reader(timeout)
    if read is None:
        return None
    pids, cwd_of = read
    return [cwd for cwd in map(cwd_of, pids) if cwd is not None]


def _decide(target: str):
    primary = sweep._is_primary_checkout(target)
    if primary is None:
        return "unreadable-subject", []
    if primary:
        return "primary-checkout", []
    live = git_reads.worktree_live_session(target)
    if live is None:
        return "unreadable-subject", []
    if live:
        return "live-session", []
    read = cwd_reader()
    if read is None:
        return "unreadable-subject", []
    pids, cwd_of = read
    decisions = []
    for pid in pids:
        cwd = cwd_of(pid)
        if cwd is None or not sweep._cwd_under_checkout(cwd, target):
            continue
        base = {"pid": pid, "cwd": cwd, "command": sweep.process_command(pid)}
        orphan = tree_root_orphaned(pid, target, cwd_of)
        if orphan is None:
            decisions.append(dict(base, action="keep", reason="unreadable-subject"))
            continue
        if not orphan:
            decisions.append(dict(base, action="keep", reason="not-orphaned"))
            continue
        owner = sweep.is_current_user_process(pid)
        if owner is None:
            decisions.append(dict(base, action="keep", reason="unreadable-subject"))
            continue
        if not owner:
            decisions.append(dict(base, action="keep", reason="not-current-user"))
            continue
        decisions.append(dict(base, action="reap", reason="agent-ended"))
    return None, decisions


BUILD_SCAN_SECONDS = 20  # the scan stops here and keeps the rest; the hook's own limit is 60
# The check is inlined on purpose: the child runs after the rename, and `rmtree` refusing a
# top-level junction is a stdlib promise, not ours. The child cannot import sweep.
DELETE_CHILD = ("import os, shutil, stat, sys\n"
                "def link(p):\n"
                "    try: st = os.lstat(p)\n"
                "    except OSError: return True\n"
                "    return os.path.islink(p) or bool(getattr(st, 'st_file_attributes', 0)"
                " & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0))\n"
                "for p in sys.argv[1:]:\n"
                "    if not link(p): shutil.rmtree(p, ignore_errors=True)\n")

trash_name, is_trash_name = sweep.trash_name, sweep.is_trash_name  # one home: sweep.py


def reap_build_dirs(target: str, cwds, stop_at=None):
    """Rename each proven build folder in TARGET to a trash name, then start one detached child
    that deletes those and every leftover trash name. Returns the folders renamed. The caller has
    proven the worktree checks; this proves the folder checks: no link, no process cwd inside. The
    scan stops at BUILD_SCAN_SECONDS or at STOP_AT (a `time.monotonic` time), whichever is first."""
    root = os.path.dirname(os.path.dirname(os.path.dirname(target)))
    names = sweep.build_dir_names(sweep.read_optout(root))
    if names is None:  # bad file: nothing, defaults included
        return []
    if sweep.is_link(target):  # a link as the worktree would send the rename and delete elsewhere
        return []
    stop = time.monotonic() + BUILD_SCAN_SECONDS
    builds, trash = sweep.scan_worktree(target, names, stop if stop_at is None else min(stop, stop_at))

    def busy(folder):
        return any(sweep._cwd_under_checkout(c, folder) for c in cwds)

    doomed = [t for t in trash if not busy(t)]
    renamed = []
    for folder in builds:
        if busy(folder):
            continue
        new = trash_name(folder)
        try:
            os.rename(folder, new)
        except OSError:
            continue  # a failed rename keeps the folder
        renamed.append(folder)
        doomed.append(new)
    if doomed:
        try:
            _nowindow.Popen([sys.executable, "-c", DELETE_CHILD, *doomed], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
        except OSError:
            pass  # the trash stays; a later reap or the janitor deletes it
    return renamed


WORKTREE_SECONDS = 15  # budget for the worktree stage; a tree not reached waits for the next agent end
HOOK_BUDGET = 45  # the stage never runs past this many seconds after the hook started; the hook's own limit is 60


OWN_TREE_REASON = "own tree: kept for 30 idle min"  # decision when-a-worktree-may-be-removed (own tree waits 30 idle min); a later agent end removes it


def _skipped(rel: str, names) -> bool:
    """True when REL (a path under the tree, `/`-separated) is inside a build folder or trash name."""
    parts = rel.strip("/").split("/")
    return any(p in names or sweep.is_trash_name(p) for p in parts) or any(
        rel.strip("/") == n or rel.startswith(n + "/") for n in names if "/" in n)


def _newest_under(folder: str, path: str, names, deadline: float):
    """Newest mtime of the files under FOLDER (None when it holds none), links not followed, build
    folders and trash names skipped. Folder mtimes do not count: creating a build folder moves its
    parent's. Raises OSError when a read failed or DEADLINE (a `time.monotonic` time) cut the walk."""
    failed, newest = [], None
    for dirpath, dirnames, filenames in os.walk(folder, onerror=failed.append):
        if time.monotonic() > deadline:
            raise OSError("walk cut short by the deadline")
        rel = os.path.relpath(dirpath, path).replace(os.sep, "/")
        dirnames[:] = [d for d in dirnames if d != ".git" and not _skipped(rel + "/" + d, names)]
        for name in filenames:
            found = os.lstat(os.path.join(dirpath, name)).st_mtime
            newest = found if newest is None else max(newest, found)
    if failed:
        raise failed[0]
    return newest


def changed_paths(path: str):
    """The paths `git status` lists as changed or untracked in PATH, relative and `/`-separated, or
    None when it cannot be read. `-z` gives each path exactly, with no quoting. `--untracked-files=normal`
    overrides the repository's `status.showUntrackedFiles`, so untracked files always show; a
    folder of only untracked files shows as the folder."""
    answer = git_reads._git(path, "status", "--porcelain", "-z", "--untracked-files=normal")
    if answer is None or answer.returncode != 0:
        return None
    fields, paths = answer.stdout.split("\0"), []
    rename_source = False
    for field in fields:
        if rename_source:  # `-z` puts a rename's source path in the next field
            rename_source = False
            continue
        if len(field) < 4:
            continue
        paths.append(field[3:])
        rename_source = field[0] in "RC"
    return paths


def _lstat_or_missing(full: str):
    """`os.lstat(FULL)`, or None when FULL does not exist. Any other failure raises: an unreadable
    path is never read as deleted."""
    try:
        return os.lstat(full)
    except FileNotFoundError:
        return None


def edit_idle(path: str, deadline: float):
    """Seconds since the newest change among the changed and untracked paths of PATH, or None when
    a read failed or DEADLINE (a `time.monotonic` time) cut a walk short. The admin-file idle clock
    misses edits that are not committed or staged. A file counts by its own mtime, an untracked
    folder by the newest file under it. A deleted path counts by the own mtime of its nearest
    existing parent folder, since the delete moved it. Build folders and trash names are skipped.
    `git status` touches no working-tree mtime, so this read may follow it. No such path: infinity."""
    rels = changed_paths(path)
    if rels is None:
        return None
    names = sweep.build_dir_names(sweep.read_optout(
        os.path.dirname(os.path.dirname(os.path.dirname(path))))) or set(sweep.DEFAULT_BUILD_DIRS)
    newest = None
    try:
        for rel in rels:
            if _skipped(rel, names):
                continue
            full = os.path.join(path, rel.rstrip("/"))
            info = _lstat_or_missing(full)
            if info is None:  # a deleted path: the own mtime of its nearest existing parent
                while info is None and os.path.dirname(full) != full:
                    full = os.path.dirname(full)
                    info = _lstat_or_missing(full)
                if info is None:
                    return None
                found = info.st_mtime
            elif os.path.isdir(full) and not sweep.is_link(full):
                found = _newest_under(full, path, names, deadline)
            else:
                found = info.st_mtime
            if found is not None:
                newest = found if newest is None else max(newest, found)
    except OSError:
        return None
    return float("inf") if newest is None else time.time() - newest


def build_keep(entry: dict, idle, deadline: float):
    """`(reason, cwds)`: why the other agent tree ENTRY keeps its build folders (None when every
    check gives a confirmed yes), and every process cwd read for the pass. IDLE is the tree's
    admin-file idle read, taken before any `git status`. The cwds are read last, after the edit
    walk, so a build started during the hook keeps. The reap stops no process in this tree, so any
    process with a cwd anywhere in it keeps every folder: a build runs from the worktree root."""
    path = entry["path"]
    if idle is None:
        return "unreadable-subject: idle", None
    if idle < sweep.AGENT_END_IDLE_SECONDS:
        return "recently-active: git activity %d minutes ago" % (idle // 60), None
    # The live host holds an agent lock on every agent tree all session, so that lock says nothing
    # about activity. Any other lock (a person's, empty or unknown text) keeps.
    holder = entry.get("locked_reason")
    if holder is not None and not sweep.AGENT_LOCK_RE.match(holder):
        return "locked: %s" % (holder or "locked"), None
    live = git_reads.worktree_live_session(path)
    if live is None:
        return "unreadable-subject: session", None
    if live:
        return "live-session", None
    edited = edit_idle(path, deadline)
    if edited is None:
        return "unreadable-subject: edits", None
    if edited < sweep.AGENT_END_IDLE_SECONDS:
        return "recently-edited: newest uncommitted change %d minutes ago" % (edited // 60), None
    cwds = all_cwds(max(1, min(BATCH_TIMEOUT, deadline - time.monotonic())))
    if cwds is None:
        return "unreadable-subject: processes", None
    if any(sweep._cwd_under_checkout(c, path) for c in cwds):
        return "process-in-worktree", cwds
    return None, cwds


def reap_worktrees(target: str, deadline: float):
    """Keep TARGET (the ending agent's own worktree and its build folders; a later agent end removes
    them once idle) and remove every other finished `.claude/worktrees/agent-*` worktree of its
    repository, idle 30 minutes or more, that `sweep.decide_agent_end_worktree` clears. Each other
    tree it keeps gets a build pass when `build_keep` clears it. Returns one row for TARGET, one per
    other tree decided, plus one row when DEADLINE (a `time.monotonic` time) cut the stage short. A tree's row carries `buildDirs` (folders renamed)
    or `buildDirsKept` (why not)."""
    rows = [{"path": target, "action": "keep", "reason": OWN_TREE_REASON,
             "buildDirsKept": OWN_TREE_REASON}]
    root = os.path.dirname(os.path.dirname(os.path.dirname(target)))
    entries = sweep.parse_worktree_list(root)
    if entries is None:
        return rows + [{"action": "keep", "reason": "unreadable-subject: the worktree list"}]
    own = os.path.normcase(os.path.realpath(target))
    queue = [e for e in entries if os.path.normcase(os.path.realpath(e["path"])) != own
             and sweep._is_agent_worktree(root, e["path"])]
    sweep._LIVE_HEADS = {}  # one remote listing per remote for the whole stage
    try:
        for done, entry in enumerate(queue):
            if time.monotonic() > deadline:
                rows.append({"action": "keep", "reason": "budget: %d trees not reached" % (len(queue) - done)})
                break
            # Idle is read once, before `git status` in the decision can rewrite the index.
            entry = dict(entry, idle=sweep.worktree_idle_seconds(entry["path"]))
            decision = sweep.decide_agent_end_worktree(root, entry, sweep.AGENT_END_IDLE_SECONDS)
            if decision["action"] == "reap":
                sweep.remove_worktree(root, entry["path"], decision)
            elif time.monotonic() > deadline:
                decision["buildDirsKept"] = "budget"
            else:
                kept, cwds = build_keep(entry, entry["idle"], deadline)
                if kept:
                    decision["buildDirsKept"] = kept
                else:
                    decision["buildDirs"] = reap_build_dirs(entry["path"], cwds, deadline)
            rows.append(decision)
    finally:
        sweep._LIVE_HEADS = None
    return rows


def handle(raw: str, started=None):
    try:
        payload = json.loads(raw)
    except Exception:
        return {"raw": raw, "target": None}
    if not isinstance(payload, dict):
        return {"raw": raw, "target": None}
    target = target_worktree(payload)
    record = {"raw": raw, "target": target}
    if not target:
        return record
    reason, decisions = _decide(target)
    for decision in decisions:
        if decision["action"] == "reap":
            decision["signalled"] = sweep.send_signal(decision["pid"])
    # claudePid: whether the harness sets CLAUDE_PID in a SubagentStop hook's env is not measured.
    record.update(reason=reason, decisions=decisions, claudePid=os.environ.get("CLAUDE_PID"))
    if reason is None:
        now = time.monotonic()
        deadline = min(now + WORKTREE_SECONDS, (now if started is None else started) + HOOK_BUDGET)
        record["worktrees"] = reap_worktrees(target, deadline)
    return record


def main() -> int:
    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""
    started = time.monotonic()
    run = "%d-%d" % (os.getpid(), time.time_ns())
    log({"raw": raw, "run": run, "state": "started"})  # a run the hook timeout kills leaves this row
    try:
        record = handle(raw, started)
    except Exception as exc:
        record = {"raw": raw, "error": repr(exc)}
    log(dict(record, run=run, state="done"), replace_run=run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
