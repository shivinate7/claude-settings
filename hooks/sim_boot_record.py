#!/usr/bin/env python3
"""Record each simulator a session call booted (decisions/sweep-shuts-down-idle-simulators.md, ruling 1).

Modes:
- PreToolUse: Before a Bash or simulator call, saves the state of each simulator.
- PostToolUse: After a Bash or simulator call, appends each simulator that the call took
  from Shutdown to Booted to the boot record. Never blocks.

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
        env = {**os.environ, "LC_ALL": "C"}  # lstart text must not depend on the caller's locale
        table = subprocess.run(["ps", "-axo", "pid=,ppid=,uid=,command="],
                               capture_output=True, text=True, timeout=30, env=env).stdout
        pids = [p[0] for p in (l.split(None, 3) for l in table.splitlines())
                if len(p) == 4 and "launchd_sim" in p[3] and udid in p[3]]
        if len(pids) != 1:  # none, or two: unclear
            return None, None
        out = subprocess.run(["ps", "-o", "pid=,lstart=", "-p", pids[0]],
                             capture_output=True, text=True, timeout=30, env=env).stdout
        for line in out.splitlines():
            parts = line.strip().split(None, 1)
            if len(parts) == 2 and parts[0] == pids[0]:
                return int(pids[0]), parts[1].strip()
        return None, None
    except Exception:
        return None, None


UDID_RE = re.compile(r"\b[0-9A-Fa-f]{8}-(?:[0-9A-Fa-f]{4}-){3}[0-9A-Fa-f]{12}\b")
BOOT_ARG_RE = re.compile(r"\bsimctl\s+boot\s+(\"[^\"]+\"|'[^']+'|\S+)")
DEST_RE = re.compile(r"-destination[= ]\s*('[^']*'|\"[^\"]*\"|\S+)")
OS_RE = re.compile(r"\bOS=([0-9][0-9.]*)")
DEST_NAME_RE = re.compile(r"\bname=([^,'\"]+)")


def by_name_ok(rec, now, payload):
    """True when REC's name picks one device: the name sits on one runtime, or `OS=` picks one."""
    runtimes = {r["runtime"] for _, r in now.values() if r["name"] == rec["name"]}
    if len(runtimes) > 1:
        command = str((payload.get("tool_input") or {}).get("command", ""))
        wanted = []  # OS= counts only inside a -destination value that holds this name
        for value in DEST_RE.findall(command):
            value = value.strip("'\"")
            if rec["name"] in DEST_NAME_RE.findall(value):
                wanted += OS_RE.findall(value)
        def version(runtime):
            return runtime.split("SimRuntime.")[-1].split("-", 1)[-1].replace("-", ".")
        runtimes = {r for r in runtimes if any(version(r) == w or version(r).startswith(w + ".")
                                               for w in wanted)}
    return len(runtimes) == 1 and rec["runtime"] in runtimes


def named(payload):
    """The UDIDs (upper case) and device names that the call names. Empty when it names none."""
    tool_input = payload.get("tool_input") or {}
    if payload.get("tool_name") == "Bash":
        text = str(tool_input.get("command", ""))
        found = set(UDID_RE.findall(text)) | set(DEST_NAME_RE.findall(text)) \
            | {m.strip("'\"") for m in BOOT_ARG_RE.findall(text)}
    else:
        found = {v for v in map(tool_input.get, ("device", "udid")) if isinstance(v, str)}
    return {x.upper() if UDID_RE.fullmatch(x) else x for x in found if x}


def main():
    try:
        payload = json.load(sys.stdin)
        tool_input = payload.get("tool_input") or {}
        if payload.get("tool_name") == "Bash":
            if not BASH_GATE.search(str(tool_input.get("command", ""))):
                return
        elif tool_input.get("action") != "launch":  # the MCP tool boots only on `launch`
            return
        names = named(payload)
        if not names or not shutil.which("xcrun"):  # a call that names no device records nothing
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
                if s == "Booted" and before.get(u) == "Shutdown" and (
                        u.upper() in names or (rec["name"] in names and by_name_ok(rec, now, payload))):
                    pid, start = launchd(u)
                    if pid is None or start is None:
                        continue  # unclear: no record, so the sweep keeps the device
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
