#!/usr/bin/env python3
"""Claude Code hook: stop the processes a finished subagent left in its own worktree.

Design: decisions/agent-end-reap-stops-what-a-finished-agent-left.md.

MEASURED 2026-09-26 on Windows (decisions/which-start-shapes-outlive-the-agent-on-windows.md,
PR #144): `cmd &` then another line, in one foreground Bash call, outlives the agent. Its
parent is a live MSYS bash stub, and the tool shell above the stub is dead. `sweep.is_orphan`
reads the live stub and keeps the server forever.

Reads one hook payload on stdin. SubagentStop names the agent by `agent_id`. The harness names
that agent's worktree `.claude/worktrees/agent-<agent_id>` under the primary checkout.
Only SubagentStop names a target. The target must have the `.claude/worktrees/<name>` shape and
must not be a primary checkout.

A process is stopped only when all of these answer a confirmed yes:
- its cwd sits inside the target worktree
- no live session has a cwd inside the target (`guard.worktree_live_session`)
- the root of its in-worktree process tree is orphaned: climb from the process through each
  live parent whose cwd is also inside the target, then `sweep.is_orphan` on the last one.
  A live parent outside the target (a harness, a terminal) means keep, except the host claude
  process (`host_pid`): the agent's own shells are stopped (owner ruling 2026-10-15 19:43 CDT).
- it is owned by the current user (`sweep.is_current_user_process`)

Any read that cannot tell means keep. One signal, by pid, through `sweep.send_signal`.

Build folders (decisions/build-dirs-reaped-at-agent-end.md): when the gates above hold for the whole
worktree, the reap also renames each build folder (`sweep.DEFAULT_BUILD_DIRS` plus `buildDirs`) to
a sibling trash name, then starts a detached child that deletes the trash. The hook never waits for
the child. A folder with a process cwd inside, a link, or any unreadable read stays. A later reap
deletes trash names a child left.

Worktrees (owner ruling 2026-10-15): when the gates above hold for the whole worktree, the hook then
removes the ending agent's OWN worktree, and every other `.claude/worktrees/agent-*` worktree idle
30 minutes or more. `sweep.decide_agent_end_worktree` decides each one: clean (no dirty or untracked
file), no process inside, no live lock (the own tree's lock goes when it names the hook's host pid), HEAD on a remote-tracking ref. A tree it cannot prove keeps.
A pid whose cwd cannot be read keeps the own tree only when it descends from the host.
The own tree goes first, and the stage stops at WORKTREE_SECONDS or the hook's own budget, so the
hook stays inside its 60 s timeout. A removed own tree has no build folders left to reap.

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
import guard  # noqa: E402
import sweep  # noqa: E402

AGENT_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_LOG_LINES = 200  # the payload log keeps the last 200 runs
REPLACE_TRIES = 5  # tries at the log replace, 50 ms apart
MAX_CLIMB = 64  # ponytail: fixed depth bound against a pid cycle, never a real tree this deep


def log_path() -> str:
    return os.path.join(guard.config_dir(), "state", "agent-end-payloads.jsonl")


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
    fields the docs leave open (decisions/agent-end-reap-stops-what-a-finished-agent-left.md), and
    it grew to thousands of raw payloads nobody reads. Parallel runs take turns on a lock file,
    because MEASURED on b0c87cb (PR 322 review): 13 of 120 rows were lost at 3 writers with a
    shared temp name and no lock. The temp name carries the pid. On Windows the replace can
    raise PermissionError while the destination is held for a moment, so it retries a few times.
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
                except PermissionError:  # MEASURED 2026-10-08 on Windows: the destination is held a moment
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
        primary = guard.primary_checkout(cwd)
        if not primary:
            return None
        path = os.path.join(primary, ".claude", "worktrees", "agent-" + agent_id)
    else:
        return None
    if not isinstance(path, str) or not is_agent_worktree_shape(path) or not os.path.isdir(path):
        return None
    return path


def parent_pid(pid: int):
    if sys.platform.startswith("win"):
        return sweep._parent_pid_windows(pid)
    try:
        answer = subprocess.run(["ps", "-o", "ppid=", "-p", str(pid)],
                                capture_output=True, text=True, timeout=5)
        return int(answer.stdout.strip()) if answer.returncode == 0 else None
    except Exception:
        return None


BATCH_TIMEOUT = 30  # seconds for the one cwd batch read; the hook's own limit is 60


def tree_root_orphaned(pid: int, target: str, cwd_of=None, host=None):
    """True when the root of PID's in-TARGET process tree is orphaned, or when its live parent outside
    TARGET is HOST (owner ruling 2026-10-15 19:43 CDT, point 1: the ending agent's host started it).
    False when any other live parent outside TARGET holds the tree. None when a read could not tell."""
    cwd_of = cwd_of or sweep.process_cwd
    current = pid
    for _ in range(MAX_CLIMB):
        orphan = sweep.is_orphan(current)
        if orphan is not False:
            return orphan
        parent = parent_pid(current)
        if host is not None and parent == host:
            return True
        cwd = cwd_of(parent) if parent else None
        if cwd is None:
            return None
        if not sweep._cwd_under_checkout(cwd, target):
            return False
        current = parent
    return None


def decide(target: str, host=None):
    """Return (reason, decisions). REASON is set when nothing in TARGET may be touched."""
    reason, decisions, _, _ = _decide(target, host)
    return reason, decisions


def _decide(target: str, host=None):
    """`decide` plus the cwd of every process read, for the build-folder gate, and the pids whose cwd
    could not be read, for the host-descendant gate. HOST: see `tree_root_orphaned`."""
    primary = sweep._is_primary_checkout(target)
    if primary is None:
        return "unreadable-subject", [], [], []
    if primary:
        return "primary-checkout", [], [], []
    live = guard.worktree_live_session(target)
    if live is None:
        return "unreadable-subject", [], [], []
    if live:
        return "live-session", [], [], []
    pids = sweep.list_all_pids()
    if pids is None:
        return "unreadable-subject", [], [], []
    cwd_of = sweep.process_cwd
    if sys.platform == "darwin":
        # One `lsof` for every pid: 1,300 per-pid reads at 27 ms overran the 60 s hook limit.
        # A failed batch keeps everything; it never falls back to per-pid reads.
        table = sweep._read_all_cwds_macos(BATCH_TIMEOUT)
        if table is None:
            return "unreadable-subject", [], [], []
        cwd_of = sweep._first_cwd_by_pid(table).get
    decisions, cwds, unreadable = [], [], []
    for pid in pids:
        if pid == os.getpid():
            continue
        cwd = cwd_of(pid)
        if cwd is None:
            unreadable.append(pid)
            continue
        cwds.append(cwd)
        if not sweep._cwd_under_checkout(cwd, target):
            continue
        base = {"pid": pid, "cwd": cwd, "command": sweep.process_command(pid)}
        orphan = tree_root_orphaned(pid, target, cwd_of, host)
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
    return None, decisions, cwds, unreadable


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
            subprocess.Popen([sys.executable, "-c", DELETE_CHILD, *doomed], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
        except OSError:
            pass  # the trash stays; a later reap or the janitor deletes it
    return renamed


def host_pids():
    """The pids of the host claude process this hook runs under. MEASURED 2026-10-15: the tool shell's
    CLAUDE_PID names the nearest claude.exe ancestor (shell -> cmd -> claude.exe), the pid the agent
    lock names. Not measured for a SubagentStop hook's env, so the ancestors of this process count
    too: a lock pid that is an ancestor is the process running the hook."""
    pids = set()
    if os.environ.get("CLAUDE_PID", "").isdigit():
        pids.add(int(os.environ["CLAUDE_PID"]))
    current = os.getpid()
    for _ in range(MAX_CLIMB):
        current = parent_pid(current)
        if not current or current in pids:
            break
        pids.add(current)
    return pids


def host_pid():
    """The host claude process for the stop and the descent gate: CLAUDE_PID, else the process that
    ran this hook. MEASURED 2026-10-15: the tool shell's CLAUDE_PID names its claude.exe. Not
    measured for a SubagentStop hook's env, so each run logs CLAUDE_PID. Narrower than `host_pids`
    on purpose: that set climbs to init or explorer when CLAUDE_PID is unset, and every process
    descends from those. LIMIT: with CLAUDE_PID unset and a shell between the host and the hook,
    the host's other children are not seen as host-started."""
    if os.environ.get("CLAUDE_PID", "").isdigit():
        return int(os.environ["CLAUDE_PID"])
    return parent_pid(os.getpid())


def parent_table():
    """{pid: ppid} for every process, from one read, or None when it could not be read."""
    if sys.platform.startswith("win"):
        return dict(sweep._toolhelp_process_entries()) or None
    try:
        answer = subprocess.run(["ps", "-A", "-o", "pid=,ppid="], capture_output=True, text=True, timeout=10)
    except Exception:
        return None
    rows = [line.split() for line in answer.stdout.splitlines()] if answer.returncode == 0 else []
    table = {int(r[0]): int(r[1]) for r in rows if len(r) == 2 and r[0].isdigit() and r[1].isdigit()}
    return table or None


def host_descendants(pids, host):
    """The PIDS (cwd unreadable) that descend from HOST, or None when that cannot be told. Owner call,
    2026-10-15: such a pid may sit inside the own tree, so it keeps the tree. A pid not in the table
    has exited. The hook's own chain up to HOST is not a reason to keep."""
    if not pids:
        return []
    table = parent_table() if host is not None else None
    if table is None:
        return None
    chain, current = {host}, os.getpid()
    for _ in range(MAX_CLIMB):
        if current is None or current in chain:
            break
        chain.add(current)
        current = table.get(current)
    found = []
    for pid in pids:
        if pid in chain or pid not in table:
            continue
        current, seen = table[pid], set()
        while current is not None and current not in seen and len(seen) < MAX_CLIMB:
            if current == host:
                found.append(pid)
                break
            seen.add(current)
            current = table.get(current)
    return found


STOP_WAIT_SECONDS = 5  # the stopped pids get this long to leave the tree before the worktree stage


def wait_gone(pids, target: str):
    """Wait, at most STOP_WAIT_SECONDS, until no pid in PIDS reads a cwd inside TARGET. A stopped
    process can still be listed for a moment, and the worktree stage would keep the tree for it.
    ponytail: a fixed bound; a pid still inside after it keeps the tree through the stage's own
    process check."""
    end = time.monotonic() + STOP_WAIT_SECONDS
    while pids and time.monotonic() < end:
        pids = [p for p in pids if sweep._cwd_under_checkout(sweep.process_cwd(p) or "", target)]
        if pids:
            time.sleep(0.05)


WORKTREE_SECONDS = 15  # budget for the worktree stage; a tree not reached waits for the next agent end
HOOK_BUDGET = 45  # the stage never runs past this many seconds after the hook started; the hook's own limit is 60


def reap_worktrees(target: str, deadline: float, own_keep=None):
    """Remove TARGET (the ending agent's own worktree, first) and every other finished
    `.claude/worktrees/agent-*` worktree of its repository that `sweep.decide_agent_end_worktree`
    clears. The caller has proven the process gates for TARGET. Returns one decision per tree
    decided, plus one row when DEADLINE (a `time.monotonic` time) cut the stage short. OWN_KEEP,
    when set, is the caller's reason to keep TARGET."""
    root = os.path.dirname(os.path.dirname(os.path.dirname(target)))
    entries = sweep.parse_worktree_list(root)
    if entries is None:
        return [{"path": target, "action": "keep", "reason": "unreadable-subject"}]
    own = os.path.normcase(os.path.realpath(target))
    queue = []
    for entry in entries:
        if os.path.normcase(os.path.realpath(entry["path"])) == own:
            queue.insert(0, (entry, None))  # the own tree needs no idle time
        elif sweep._is_agent_worktree(root, entry["path"]):
            queue.append((entry, sweep.AGENT_END_IDLE_SECONDS))
    rows = []
    sweep._LIVE_HEADS = {}  # one remote listing per remote for the whole stage
    # The own tree's host lock goes (its agent-<id> equals the payload agent_id); every other lock stays.
    sweep._OWN_AGENT = {"id": os.path.basename(target)[len("agent-"):], "hosts": host_pids()}
    try:
        for done, (entry, min_idle) in enumerate(queue):
            if time.monotonic() > deadline:
                rows.append({"action": "keep", "reason": "budget: %d trees not reached" % (len(queue) - done)})
                break
            if min_idle is None and own_keep:
                decision = {"path": entry["path"], "action": "keep", "reason": own_keep}
            else:
                decision = sweep.decide_agent_end_worktree(root, entry, min_idle)
            if decision["action"] == "reap":
                sweep.remove_worktree(root, entry["path"], decision)
            rows.append(decision)
    finally:
        sweep._LIVE_HEADS = None
        sweep._OWN_AGENT = None
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
    host = host_pid()
    reason, decisions, cwds, unreadable = _decide(target, host)
    stopped = []
    for decision in decisions:
        if decision["action"] == "reap":
            decision["signalled"] = sweep.send_signal(decision["pid"])
            stopped.append(decision["pid"])
    record.update(reason=reason, decisions=decisions, claudePid=os.environ.get("CLAUDE_PID"), host=host)
    if reason is None:
        wait_gone(stopped, target)
        # A stopped pid can read as unreadable while it exits (a zombie), so it is not counted.
        held = host_descendants([p for p in unreadable if p not in stopped], host)
        if held is None:
            own_keep = "unreadable-subject: the host's descendants could not be read"
        elif held:
            own_keep = "unreadable-subject: pid %s descends from the host" % ", ".join(map(str, held))
        else:
            own_keep = None
        now = time.monotonic()
        deadline = min(now + WORKTREE_SECONDS, (now if started is None else started) + HOOK_BUDGET)
        record["worktrees"] = reap_worktrees(target, deadline, own_keep)
        if os.path.isdir(target):  # a removed own tree has no build folders left
            record["buildDirs"] = reap_build_dirs(target, cwds)
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
