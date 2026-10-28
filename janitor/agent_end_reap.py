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

Build folders (docs/decisions/build-dirs-reaped-at-agent-end.md): when the gates above hold for the whole
worktree, the reap also renames each build folder (`sweep.DEFAULT_BUILD_DIRS` plus `buildDirs`) to
a sibling trash name, then starts a detached child that deletes the trash. The hook never waits for
the child. Every build folder stays while the reap keeps any process in the worktree. A folder with
a process cwd inside, a link, or any unreadable read stays. A later reap
deletes trash names a child left.

Worktrees (docs/decisions/when-a-worktree-may-be-removed.md): when the gates above hold for the whole worktree,
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
REPLACE_TRIES = 5  # tries at the log replace, 50 ms apart


def log_path() -> str:
    return os.path.join(git_reads.config_dir(), "state", "agent-end-payloads.jsonl")


@contextlib.contextmanager
def _log_lock(path: str):
    """Hold an exclusive lock on `<log>.lock` so parallel hook runs take turns. `fcntl.flock`
    on POSIX, `msvcrt.locking` on Windows (blocks up to about 10 s, then raises)."""
    with open(path + ".lock", "a+") as handle:
        if sys.platform.startswith("win"):
            import msvcrt
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
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
    held for a moment, so it retries a few times.
    REPLACE_RUN names a start row written earlier by this run; the last line is replaced only
    when it carries that run id, so another agent's row is never dropped.
    A failed write never fails the hook (exit stays 0); it prints one line to stderr."""
    path = log_path()
    line = json.dumps(dict(record, at=time.strftime("%Y-%m-%dT%H:%M:%S%z"))) + "\n"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with _log_lock(path):
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
            for attempt in range(REPLACE_TRIES):
                try:
                    os.replace(temp, path)  # a reader never sees an empty or half-written file
                    break
                except PermissionError:  # Windows: the destination is held a moment
                    if attempt == REPLACE_TRIES - 1:
                        raise
                    time.sleep(0.05)
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
    reason, decisions, _ = _decide(target)
    return reason, decisions


def _decide(target: str):
    """`decide` plus the cwd of every process read, for the build-folder gate."""
    primary = sweep._is_primary_checkout(target)
    if primary is None:
        return "unreadable-subject", [], []
    if primary:
        return "primary-checkout", [], []
    live = git_reads.worktree_live_session(target)
    if live is None:
        return "unreadable-subject", [], []
    if live:
        return "live-session", [], []
    pids = sweep.list_all_pids()
    if pids is None:
        return "unreadable-subject", [], []
    cwd_of = sweep.process_cwd
    if sys.platform == "darwin":
        # One `lsof` for every pid: 1,300 per-pid reads at 27 ms overran the 60 s hook limit.
        # A failed batch keeps everything; it never falls back to per-pid reads.
        table = sweep._read_all_cwds_macos(BATCH_TIMEOUT)
        if table is None:
            return "unreadable-subject", [], []
        cwd_of = sweep._first_cwd_by_pid(table).get
    decisions, cwds = [], []
    for pid in pids:
        if pid == os.getpid():
            continue
        cwd = cwd_of(pid)
        if cwd is not None:
            cwds.append(cwd)
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
    return None, decisions, cwds


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


def reap_build_dirs(target: str, cwds):
    """Rename each proven build folder in TARGET to a trash name, then start one detached child
    that deletes those and every leftover trash name. Returns the folders renamed. The caller has
    proven the worktree gates; this proves the folder gates: no link, no process cwd inside."""
    root = os.path.dirname(os.path.dirname(os.path.dirname(target)))
    names = sweep.build_dir_names(sweep.read_optout(root))
    if names is None:  # bad file: nothing, defaults included
        return []
    if sweep.is_link(target):  # a link as the worktree would send the rename and delete elsewhere
        return []
    builds, trash = sweep.scan_worktree(target, names, time.monotonic() + BUILD_SCAN_SECONDS)

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


def reap_worktrees(target: str, deadline: float):
    """Keep TARGET (the ending agent's own worktree; a later agent end removes it once idle) and remove
    every other finished `.claude/worktrees/agent-*` worktree of its repository, idle 30 minutes or
    more, that `sweep.decide_agent_end_worktree` clears. Returns one row for TARGET, one per other
    tree decided, plus one row when DEADLINE (a `time.monotonic` time) cut the stage short."""
    rows = [{"path": target, "action": "keep", "reason": OWN_TREE_REASON}]
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
            decision = sweep.decide_agent_end_worktree(root, entry, sweep.AGENT_END_IDLE_SECONDS)
            if decision["action"] == "reap":
                sweep.remove_worktree(root, entry["path"], decision)
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
    reason, decisions, cwds = _decide(target)
    for decision in decisions:
        if decision["action"] == "reap":
            decision["signalled"] = sweep.send_signal(decision["pid"])
    # claudePid: whether the harness sets CLAUDE_PID in a SubagentStop hook's env is not measured.
    record.update(reason=reason, decisions=decisions, claudePid=os.environ.get("CLAUDE_PID"))
    if reason is None:
        # A build runs from the worktree root (xcodebuild, swift build), not from inside the folder
        # it writes. Any process the reap keeps in the worktree means a build may be writing.
        if any(d["action"] != "reap" for d in decisions):
            record["buildDirs"], record["buildDirsKept"] = [], "process-in-worktree"
        else:
            record["buildDirs"] = reap_build_dirs(target, cwds)
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
