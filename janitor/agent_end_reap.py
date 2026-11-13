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
prove keeps. One lock and its processes are the exception (decision `when-a-worktree-may-be-removed`): a
tree locked by this session's host is unlocked and removed only when the agent is
proven finished (`agent_finished`: its own SubagentStop row is in the payload log and newer than its
agent transcript, it is not listed as running in `background_tasks`, and the transcript is idle 30
minutes or more) and the tree is clean and pushed. A process inside keeps the tree unless
`sweep.host_child_stops` proves each one the agent's own: it holds the agent marker, the exec-time
`CLAUDE_AGENT_ID` equal to the 17-hex id in the tree's basename (`sweep.agent_mark`), or it holds none
and a marked process in the tree descends from it (a background job's `( )` subshell is a fork, so
unmarked). Another agent's marker, or an unmarked process no marked one descends from, keeps the tree.
The unlock comes first (`sweep.unlock_for_removal`); a failed one stops nothing. Pids are signalled
deepest first, the process table is read again until empty (`stop_and_settle`), and a pid still alive,
or a failed read, puts the lock back (the row's `relocked` says whether it took) and keeps the tree,
with the cause as the reason. A tree kept for another reason never has a process stopped. The stage stops at
WORKTREE_SECONDS or HOOK_BUDGET, so the hook stays inside its 60 s timeout.

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
    import agent_procs  # the one home of the per-agent process record (hooks/agent_procs.py)
except ImportError:  # a hook never dies for a missing helper; with no record, no process is ended
    agent_procs = None
try:
    import _nowindow  # the one home of a no-window child start (hooks/_nowindow.py)
except ImportError:  # a hook never dies for a missing helper (it lands a moment after the hook in an install)
    _nowindow = subprocess

AGENT_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_LOG_LINES = 200  # the payload log keeps the last 200 runs
LOG_WAIT_SECONDS = 30  # one log() call waits at most this long for the lock, the read and the replace together
LOG_RETRY_SECONDS = 0.02  # pause between two tries at the lock, the read or the replace
LOG_DONE_BY = 58  # seconds after the hook started by which the done row stops waiting; the hook's own limit is 60


class LogWaitTimeout(OSError):
    """A log() call waited past its deadline for the lock, the read or the replace."""


def log_path() -> str:
    return os.path.join(git_reads.config_dir(), "state", "agent-end-payloads.jsonl")


@contextlib.contextmanager
def _log_lock(path: str, deadline: float):
    """Hold an exclusive lock on `<log>.lock` so parallel hook runs take turns. `fcntl.flock` on
    POSIX, `msvcrt.locking` on Windows, both non-blocking and tried every LOG_RETRY_SECONDS until
    DEADLINE (a `time.monotonic` time), then LogWaitTimeout. The body never runs without the lock.
    (`msvcrt.LK_LOCK` gives up after about 10 s on its own, so it is not used.)"""
    with open(path + ".lock", "a+") as handle:
        win = sys.platform.startswith("win")
        if win:
            import msvcrt
        else:
            import fcntl
        while True:
            try:
                if win:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:  # held by another run
                if time.monotonic() >= deadline:
                    raise LogWaitTimeout("payload log lock not taken before the deadline")
                time.sleep(LOG_RETRY_SECONDS)
        try:
            yield
        finally:
            if win:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


DROPS_MAX_BYTES = 256 * 1024  # the drops file moves to `<drops>.old` at this size


def drops_path() -> str:
    return os.path.join(git_reads.config_dir(), "state", "agent-end-drops.jsonl")


def log(record: dict, replace_run=None, give_up_at=None):
    """Append one line and keep only the last MAX_LOG_LINES. The log is the evidence for the hook
    fields the docs leave open (docs/decisions/agent-end-reap-stops-what-a-finished-agent-left.md).
    Parallel runs take turns on a lock file, because writers lost rows without it. The temp name
    carries the pid. The replace can raise PermissionError while the destination is held (seen on
    Windows), so it retries on every platform; a permanent refusal costs the whole wait.
    The lock wait and the replace share one deadline: LOG_WAIT_SECONDS from now, or GIVE_UP_AT
    (a `time.monotonic` time, the hook's own clock) when that is sooner.
    REPLACE_RUN names a start row written earlier by this run; the last line is replaced only
    when it carries that run id, so another agent's row is never dropped.
    Only the new row can drop, never a row the log holds. It drops when:
    - the lock or the replace waits past the deadline (LogWaitTimeout)
    - a read of the log is refused with PermissionError until the deadline (LogWaitTimeout)
    - a read of the log fails with any other OSError but a missing file; the row drops at once
    - the folder, the lock file or the temp file cannot be written
    - the replace is refused with an OSError other than PermissionError
    A read refused with PermissionError is retried every LOG_RETRY_SECONDS until that deadline, as the
    replace is, so a refusal that passes lets the row land.
    A drop does not raise out of log(), so the hook's exit stays 0. A record that cannot be serialised
    raises before any write, and no drop row is written for it. A drop goes as one JSON line (`at`, `run`,
    `error`) to the drops file, drops_path(), and then to stderr. The append comes first, so a closed
    stderr (OSError or ValueError) cannot stop it. The append is best effort: if it fails too, nothing
    more is written. It shares the `state/` folder with the log, so a folder that cannot be written, or a
    full disk, fails both and leaves stderr as the only report.
    Cost: one append, only on a failed write, plus one rename when the drops file is DROPS_MAX_BYTES
    (256 KiB) or more; a write that lands writes nothing extra.
    Bound: that rename moves the drops file to `<drops>.old`, replacing any old one, so the two files
    hold at most about 512 KiB. A failed rename is swallowed and the file keeps growing until it works.
    A read that stays refused leaves the log as it is: the row is not written. A drop shows in the daily
    note's drops line, which reads the current drops file only, unless the `state/` folder cannot be
    written, or the row moved to `.old` before the note read the file."""
    deadline = time.monotonic() + LOG_WAIT_SECONDS
    if give_up_at is not None:
        deadline = min(deadline, give_up_at)
    path = log_path()
    at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    line = json.dumps(dict(record, at=at)) + "\n"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with _log_lock(path, deadline):
            while True:
                try:
                    with open(path, encoding="utf-8") as handle:
                        kept = handle.readlines()[-(MAX_LOG_LINES - 1):]
                    break
                except FileNotFoundError:
                    kept = []  # no log yet
                    break
                except PermissionError as exc:  # held a moment: retried like the replace
                    if time.monotonic() >= deadline:
                        raise LogWaitTimeout("payload log read refused until the deadline: %r" % exc)
                    time.sleep(LOG_RETRY_SECONDS)
                # any other OSError propagates, so the log is never rewritten short
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
                        raise LogWaitTimeout("payload log replace refused until the deadline: %r" % exc)
                    time.sleep(LOG_RETRY_SECONDS)
    except Exception as exc:
        try:
            run = record.get("run")
            drop = json.dumps({"at": at, "run": run if isinstance(run, str) else None, "error": repr(exc)})
            drops = drops_path()
            os.makedirs(os.path.dirname(drops), exist_ok=True)
            try:
                if os.path.getsize(drops) >= DROPS_MAX_BYTES:
                    os.replace(drops, drops + ".old")  # the one rotation: the next append starts a fresh file
            except OSError:  # best effort: no file yet, or the rename is refused; the append still runs
                pass
            with open(drops, "a", encoding="utf-8") as handle:
                handle.write(drop + "\n")
        except Exception:  # best effort: the stderr line below stays
            pass
        try:
            print("agent_end_reap: payload log write failed: %r" % exc, file=sys.stderr)
        except (OSError, ValueError):  # a closed stderr must not raise out of log(); the drop row is already written
            pass


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


def stopped_agents():
    """`{agent id: POSIX time of its newest SubagentStop row}` from the payload log, or None when the
    log cannot be read. A row counts when its `raw` payload parses to a SubagentStop for that
    `agent_id` and its `at` (as `log()` stamps it) parses; a row with no readable time never counts.
    The log keeps the last 200 runs, so an agent whose row the cap cut reads as not stopped."""
    try:
        with open(log_path(), encoding="utf-8") as handle:
            lines = handle.readlines()
    except OSError:
        return None
    found = {}
    for line in lines:
        try:
            row = json.loads(line)
            raw = row.get("raw")
            payload = json.loads(raw) if isinstance(raw, str) else None
            when = _row_time(row.get("at"))
        except (ValueError, AttributeError, TypeError, OverflowError):
            continue
        if (isinstance(payload, dict) and payload.get("hook_event_name") == "SubagentStop"
                and isinstance(payload.get("agent_id"), str)):
            agent = payload["agent_id"]
            found[agent] = max(found.get(agent, when), when)
    return found


def _row_time(stamp):
    """POSIX time of a payload-log `at` stamp (`%Y-%m-%dT%H:%M:%S%z`). Raises ValueError or TypeError
    for a stamp that is missing or malformed."""
    from datetime import datetime
    return datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S%z").timestamp()


def agent_finished(payload, path: str, stopped) -> bool:
    """True when the agent that owns the tree at PATH is proven finished, by all of: STOPPED (from
    `stopped_agents`) holds a SubagentStop row of its own that is not older than its agent
    transcript (an older row is from before the agent was resumed); the payload's `background_tasks`
    is a list of dicts and none lists this agent (`id` is the agent id) as running; `transcript_path`
    names a `.jsonl`; and `<transcript minus .jsonl>/subagents/agent-<id>.jsonl` exists and has been
    idle AGENT_END_IDLE_SECONDS. A missing or malformed field, or an unreadable file, is False.
    Why the stop row: `background_tasks` omits a running agent in a quiet gap (decision
    when-a-worktree-may-be-removed, "A finished agent's tree"). The row's `at` has whole seconds, so
    the transcript time is cut to whole seconds before the compare."""
    if not isinstance(payload, dict) or not stopped:
        return False
    name = os.path.basename(os.path.normpath(path))
    if not name.startswith("agent-") or name[len("agent-"):] not in stopped:
        return False
    agent = name[len("agent-"):]
    tasks = payload.get("background_tasks")
    if not isinstance(tasks, list) or not all(isinstance(t, dict) for t in tasks):
        return False
    if any(t.get("id") == agent and t.get("status") == "running" for t in tasks):
        return False
    transcript = payload.get("transcript_path")
    if not isinstance(transcript, str) or not transcript.endswith(".jsonl"):
        return False
    record = os.path.join(transcript[:-len(".jsonl")], "subagents", "agent-%s.jsonl" % agent)
    try:
        if not os.path.isfile(record):
            return False
        written = os.path.getmtime(record)
    except OSError:
        return False
    return time.time() - written >= sweep.AGENT_END_IDLE_SECONDS and stopped[agent] >= int(written)


def host_is_session_root(decision: dict) -> bool:
    """True when the host a host-lock decision names is this session's own `claude` process or
    descends from it (`guard_kill.session_root_pid`, `pid_is_owned`). The decision already proved
    the host an ancestor of this hook (`sweep.own_agent_lock_verdict`); this is the second read, so a
    root it can find must agree. It vetoes only a root it finds: with none (0), the ancestry proof
    stands alone. Any failed read, or a missing helper, is False."""
    found = sweep.AGENT_LOCK_RE.match(decision.get("lock_reason") or "")
    if not found:
        return False
    host = int(found.group(1))
    try:
        import guard_kill
        root = guard_kill.session_root_pid()
        if not root or host == root:
            return True
        return guard_kill.pid_is_owned(host, root) is True
    except Exception:
        return False


SETTLE_POLL_SECONDS = 0.1  # pause between two reads of the process table while a stopped process exits


def stop_and_settle(path: str, decision: dict, deadline: float):
    """Called only after the unlock succeeded (`sweep.unlock_for_removal`). Signal each pid in
    DECISION["stop_pids"], deepest first, then re-read `sweep.processes_in` until it is empty or
    DEADLINE (a `time.monotonic` time). Returns None when it came back empty, else the keep reason
    that names the cause: a process still alive at the deadline, or a failed read of the process
    table. The tree stays either way. Settling reads the process table, never `pid_alive`: a
    stopped child nobody has waited on is a zombie, which `pid_alive` still reads as alive and
    `processes_in` does not list."""
    decision["signalled"] = [sweep.send_signal(pid) for pid in decision["stop_pids"]]
    while True:
        inside, _unreadable = sweep.processes_in(path)
        if inside is not None and not inside:
            return None
        if inside is None:
            return "unreadable-subject: the process table after the stop"
        if time.monotonic() >= deadline:
            return "process-inside: pid %s still alive at the deadline" % ", ".join(
                str(pid) for pid in sorted(inside))
        time.sleep(SETTLE_POLL_SECONDS)


def reap_worktrees(target: str, deadline: float, payload=None):
    """Keep TARGET (the ending agent's own worktree and its build folders; a later agent end removes
    them once idle) and remove every other finished `.claude/worktrees/agent-*` worktree of its
    repository, idle 30 minutes or more, that `sweep.decide_agent_end_worktree` clears. Each other
    tree it keeps gets a build pass when `build_keep` clears it. PAYLOAD is the SubagentStop
    payload: a tree whose agent it proves finished (`agent_finished`) may lose its host lock, and the
    processes it holds that carry the agent's marker are stopped (`stop_and_settle`) before the
    removal; any pid left alive keeps the tree. Returns one row for TARGET, one per
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
    stopped = stopped_agents()  # one read of the payload log for the stage
    try:
        for done, entry in enumerate(queue):
            if time.monotonic() > deadline:
                rows.append({"action": "keep", "reason": "budget: %d trees not reached" % (len(queue) - done)})
                break
            # Idle is read once, before `git status` in the decision can rewrite the index.
            entry = dict(entry, finished=entry.get("locked_reason") is not None
                         and agent_finished(payload, entry["path"], stopped))  # file reads: no index
            entry = dict(entry, idle=sweep.worktree_idle_seconds(entry["path"]))
            decision = sweep.decide_agent_end_worktree(root, entry, sweep.AGENT_END_IDLE_SECONDS)
            if decision["action"] == "reap" and decision.get("host_lock") and not host_is_session_root(decision):
                decision.update(action="keep", reason="unreadable-subject: the session's host")
                for field in ("stop_pids", "unlock"):
                    decision.pop(field, None)
            if decision["action"] == "reap" and decision.get("stop_pids"):
                # The unlock and its lock re-read come first: a failed one stops nothing.
                if not sweep.unlock_for_removal(root, entry["path"], decision):
                    decision.pop("stop_pids", None)
                    if decision["action"] == "reap":
                        decision.update(action="keep", reason="unreadable-subject: the unlock failed")
                else:
                    why = stop_and_settle(entry["path"], decision, deadline)
                    if why is not None:
                        decision["relocked"] = sweep.relock_worktree(root, entry["path"], decision)
                        decision.update(action="keep", reason=why)
                        decision.pop("unlock", None)
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


AGENT_END_SETTLE_SECONDS = 3  # how long the stop waits for a signalled process to leave


def marked_processes(agent: str):
    """The pids that hold AGENT's marker (`sweep.agent_mark`), never this process or its ancestors, or None when the
    process list could not be read."""
    pids = sweep.list_all_pids()
    if pids is None:
        return None
    own = sweep._own_chain_pids()
    return [pid for pid in pids if pid > 1 and pid not in own and sweep.agent_mark(pid) == agent]


def end_agent_processes(payload: dict):
    """The ending agent's process record (step agent-owned-processes). Writes the processes that hold the agent's
    marker to its `agent_procs` record, and ends only those `agent_procs.plan_ends` clears: the marker is the agent's,
    the account running the hook owns the pid, its start ticks match the record (or no record held it), and no other
    agent's record lists it. A pid whose start differs, or whose start cannot be read (macOS, Windows), is recorded
    as kind "unclear" and kept. Windows adds the Office diff. Returns {"ended", "reported"} pid lists for the
    payload log, or None when the payload names no agent."""
    agent = payload.get("agent_id")
    if agent_procs is None or payload.get("hook_event_name") != "SubagentStop" or not isinstance(agent, str) \
            or not AGENT_ID.match(agent):
        return None
    record = agent_procs.read_record(agent) or {"procs": []}
    entries = {e["pid"]: e for e in record["procs"]}
    pids = marked_processes(agent)
    if pids is None:
        return {"ended": [], "reported": [], "error": "unreadable-subject: the process table"}
    candidates = []
    for pid in pids:
        current, prior = agent_procs.start_ticks(pid), entries.get(pid)
        start_ok = current is not None and (prior is None or prior.get("start") == current)
        kind = prior.get("kind", "background") if prior and start_ok else "background" if start_ok else "unclear"
        owner = agent if sweep.is_current_user_process(pid) is True else None
        entries[pid] = {"pid": pid, "start": current if start_ok or prior is None else prior.get("start"),
                        "owner": agent, "kind": kind}
        candidates.append({"pid": pid, "owner": owner, "kind": kind, "visible": False, "start_ok": start_ok,
                           "shared": bool(agent_procs.held_by_others(pid, agent))})
    for candidate in agent_procs.office_candidates(agent):
        entries[candidate["pid"]] = {"pid": candidate["pid"], "start": None, "owner": agent, "kind": "office"}
        candidates.append(candidate)
    ends = []
    for pid in agent_procs.plan_ends(candidates, agent):
        # Read again just before the signal: a pid reused since the scan is not the agent's.
        if entries[pid]["kind"] == "office" or agent_procs.start_ticks(pid) == entries[pid]["start"]:
            if sweep.send_signal(pid):
                ends.append(pid)
    settle_by = time.monotonic() + AGENT_END_SETTLE_SECONDS
    while any(agent_procs.is_running(pid) for pid in ends) and time.monotonic() < settle_by:
        time.sleep(SETTLE_POLL_SECONDS)
    gone = [pid for pid in ends if not agent_procs.is_running(pid)]
    for pid, entry in entries.items():
        entry["ended"] = pid in gone
    had_office = record.pop("office_before", None) is not None  # a later agent's stop no longer waits on this one
    record["procs"] = sorted(entries.values(), key=lambda e: e["pid"])
    if entries or had_office:
        agent_procs.write_record(agent, record)
    return {"ended": gone, "reported": [c["pid"] for c in candidates if c["pid"] not in gone]}


def handle(raw: str, started=None):
    try:
        payload = json.loads(raw)
    except Exception:
        return {"raw": raw, "target": None}
    if not isinstance(payload, dict):
        return {"raw": raw, "target": None}
    target = target_worktree(payload)
    record = {"raw": raw, "target": target}
    try:
        record["agentProcs"] = end_agent_processes(payload)
    except Exception as exc:  # the process record never stops the worktree stage
        record["agentProcs"] = {"error": repr(exc)}
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
        record["worktrees"] = reap_worktrees(target, deadline, payload)
    return record


def main() -> int:
    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""
    started = time.monotonic()
    run = "%d-%d" % (os.getpid(), time.time_ns())
    # One hook clock: the start row stops waiting where the worktree stage stops, the done row
    # LOG_DONE_BY seconds in, so the hook ends inside its 60 s limit even when the log stays held.
    log({"raw": raw, "run": run, "state": "started"},  # a run the hook timeout kills leaves this row
        give_up_at=started + HOOK_BUDGET)
    try:
        record = handle(raw, started)
    except Exception as exc:
        record = {"raw": raw, "error": repr(exc)}
    log(dict(record, run=run, state="done"), replace_run=run, give_up_at=started + LOG_DONE_BY)
    return 0


if __name__ == "__main__":
    sys.exit(main())
