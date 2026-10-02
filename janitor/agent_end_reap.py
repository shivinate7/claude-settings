#!/usr/bin/env python3
"""Claude Code hook: stop the processes a finished subagent left in its own worktree.

Design: decisions/agent-end-reap-stops-what-a-finished-agent-left.md.

MEASURED 2026-09-26 on Windows (decisions/which-start-shapes-outlive-the-agent-on-windows.md,
PR #144): `cmd &` then another line, in one foreground Bash call, outlives the agent. Its
parent is a live MSYS bash stub, and the tool shell above the stub is dead. `sweep.is_orphan`
reads the live stub and keeps the server forever.

Reads one hook payload on stdin. SubagentStop names the agent by `agent_id`. The harness names
that agent's worktree `.claude/worktrees/agent-<agent_id>` under the primary checkout.
Only SubagentStop names a target (owner ruling 1, 2026-09-27: WorktreeRemove stays
unwired). The target must have the `.claude/worktrees/<name>` shape and must not be a primary checkout.

A process is stopped only when all of these answer a confirmed yes:
- its cwd sits inside the target worktree
- no live session has a cwd inside the target (`guard.worktree_live_session`)
- the root of its in-worktree process tree is orphaned: climb from the process through each
  live parent whose cwd is also inside the target, then `sweep.is_orphan` on the last one.
  A live parent outside the target (a harness, a terminal) means keep.
- it is owned by the current user (`sweep.is_current_user_process`)

Any read that cannot tell means keep. One signal, by pid, through `sweep.send_signal`.

Every run appends the raw payload and the decisions to
`${CLAUDE_CONFIG_DIR:-~/.claude}/state/agent-end-payloads.jsonl`, so the payload fields the docs
leave unmeasured get measured. The file keeps the last 200 lines. Always exits 0: exit 2 on SubagentStop keeps the agent running.
"""
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
MAX_CLIMB = 64  # ponytail: fixed depth bound against a pid cycle, never a real tree this deep


def log_path() -> str:
    return os.path.join(guard.config_dir(), "state", "agent-end-payloads.jsonl")


def log(record: dict):
    """Append one line and keep only the last MAX_LOG_LINES. The log is the evidence for the hook
    fields the docs leave open (decisions/agent-end-reap-stops-what-a-finished-agent-left.md), and
    it grew to thousands of raw payloads nobody reads. Two agents ending at once can lose a line:
    ponytail: no lock, add one only if a measured field goes missing."""
    path = log_path()
    line = json.dumps(dict(record, at=time.strftime("%Y-%m-%dT%H:%M:%S%z"))) + "\n"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(path, encoding="utf-8") as handle:
                kept = handle.readlines()[-(MAX_LOG_LINES - 1):]
        except OSError:
            kept = []
        with open(path, "w", encoding="utf-8") as handle:
            handle.writelines(kept + [line])
    except Exception:
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


def tree_root_orphaned(pid: int, target: str):
    """True when the root of PID's in-TARGET process tree is orphaned. False when a live parent
    outside TARGET holds the tree. None when a read could not tell."""
    current = pid
    for _ in range(MAX_CLIMB):
        orphan = sweep.is_orphan(current)
        if orphan is not False:
            return orphan
        parent = parent_pid(current)
        cwd = sweep.process_cwd(parent) if parent else None
        if cwd is None:
            return None
        if not sweep._cwd_under_checkout(cwd, target):
            return False
        current = parent
    return None


def decide(target: str):
    """Return (reason, decisions). REASON is set when nothing in TARGET may be touched."""
    primary = sweep._is_primary_checkout(target)
    if primary is None:
        return "unreadable-subject", []
    if primary:
        return "primary-checkout", []
    live = guard.worktree_live_session(target)
    if live is None:
        return "unreadable-subject", []
    if live:
        return "live-session", []
    pids = sweep.list_all_pids()
    if pids is None:
        return "unreadable-subject", []
    decisions = []
    for pid in pids:
        if pid == os.getpid():
            continue
        cwd = sweep.process_cwd(pid)
        if cwd is None or not sweep._cwd_under_checkout(cwd, target):
            continue
        base = {"pid": pid, "cwd": cwd, "command": sweep.process_command(pid)}
        orphan = tree_root_orphaned(pid, target)
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


def handle(raw: str):
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
    reason, decisions = decide(target)
    for decision in decisions:
        if decision["action"] == "reap":
            decision["signalled"] = sweep.send_signal(decision["pid"])
    record.update(reason=reason, decisions=decisions)
    return record


def main() -> int:
    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""
    try:
        record = handle(raw)
    except Exception as exc:
        record = {"raw": raw, "error": repr(exc)}
    log(record)
    return 0


if __name__ == "__main__":
    sys.exit(main())
