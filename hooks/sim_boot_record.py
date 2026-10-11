#!/usr/bin/env python3
"""Record each simulator a session call booted (decisions/sweep-shuts-down-idle-simulators.md, ruling 1).

PreToolUse saves every device's state. PostToolUse of the same call appends each device that went
Shutdown -> Booted to <config>/state/sim-boots.jsonl. It never blocks: stdout stays empty, exit 0.
No snapshot, an unreadable snapshot or an unreadable list records nothing.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time

# A Bash call that cannot touch a simulator skips the ~0.3 s `simctl list`. ponytail: a boot hidden
# behind a script that never names these words goes unrecorded, and an unrecorded device is kept.
BASH_GATE = re.compile(r"\b(?:simctl|xcodebuild|xcrun|xctest|fastlane|flutter|react-native|tuist|Simulator)\b|\bexpo\s+run:ios\b")


def devices():
    """{udid: (state, record)} from `simctl list`, or None when it could not be read."""
    try:
        answer = subprocess.run(["xcrun", "simctl", "list", "devices", "--json"],
                                capture_output=True, text=True, timeout=60)
        if answer.returncode != 0:
            return None
        return {d["udid"]: (d["state"], {"udid": d["udid"], "name": d["name"],
                                         "deviceTypeIdentifier": d.get("deviceTypeIdentifier", ""),
                                         "runtime": runtime})
                for runtime, rows in json.loads(answer.stdout)["devices"].items() for d in rows}
    except Exception:
        return None


def launchd(udid):
    """(pid, ps lstart text) of UDID's launchd_sim, or (None, None). The sweep reads the same pair
    (`sweep._sim_live_launchd`); this hook stays standalone because a cloud copy has no janitor/."""
    try:
        table = subprocess.run(["ps", "-axo", "pid=,ppid=,uid=,command="],
                               capture_output=True, text=True, timeout=30).stdout
        pid = next(p[0] for p in (l.split(None, 3) for l in table.splitlines())
                   if len(p) == 4 and "launchd_sim" in p[3] and udid in p[3])
        out = subprocess.run(["ps", "-o", "pid=,lstart=", "-p", pid],
                             capture_output=True, text=True, timeout=30).stdout
        for line in out.splitlines():
            parts = line.strip().split(None, 1)
            if len(parts) == 2 and parts[0] == pid:
                return int(pid), parts[1].strip()
        return int(pid), None
    except Exception:
        return None, None


def main():
    try:
        payload = json.load(sys.stdin)
        tool_input = payload.get("tool_input") or {}
        if payload.get("tool_name") == "Bash":
            if not BASH_GATE.search(str(tool_input.get("command", ""))):
                return
        elif tool_input.get("action") != "launch":  # the MCP tool boots only on `launch`
            return
        if not shutil.which("xcrun"):
            return
        state = os.path.join(os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude"), "state")
        key = re.sub(r"[^A-Za-z0-9_-]", "_", str(payload.get("tool_use_id") or payload["session_id"]))
        snap = os.path.join(state, "sim-snapshot-" + key + ".json")
        now = devices()
        if payload["hook_event_name"] == "PreToolUse":
            if os.path.exists(snap):
                os.remove(snap)
            if now is not None:
                os.makedirs(state, exist_ok=True)
                with open(snap, "w", encoding="utf-8") as f:
                    json.dump({u: s for u, (s, _) in now.items()}, f)
        elif payload["hook_event_name"] == "PostToolUse":
            with open(snap, encoding="utf-8") as f:
                before = json.load(f)
            os.remove(snap)
            if now is None:
                return
            at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            lines = []
            for u, (s, rec) in now.items():
                if s == "Booted" and before.get(u) == "Shutdown":
                    pid, start = launchd(u)
                    lines.append(json.dumps({**rec, "at": at, "launchd_pid": pid,
                                             "launchd_start": start}) + "\n")
            if lines:
                with open(os.path.join(state, "sim-boots.jsonl"), "a", encoding="utf-8") as f:
                    f.writelines(lines)
    except Exception:
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
