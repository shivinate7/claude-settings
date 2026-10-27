#!/usr/bin/env python3
"""Record each simulator a session call booted (docs/decisions/sweep-shuts-down-idle-simulators.md, ruling 1).

Modes:
- PreToolUse: Before a Bash call that names simulator tooling (simctl, xcodebuild) and a device,
  or a simulator MCP launch, saves the state of each simulator.
- PostToolUse: After such a call, appends each simulator that the call took from Shutdown to
  Booted to the boot record. After a `simctl boot` or an MCP `launch`, first checks each such
  device. A device that fails the check is stopped and booted once more.

PreToolUse saves every device's state. PostToolUse of the same call appends each device that went
Shutdown -> Booted to <config>/state/sim-boots.jsonl. The boot check runs first, so the record
holds the retry boot's pid. Stdout stays empty unless a check failed: a retry that passed writes an
additionalContext note, a retry that failed writes a `block` decision (the device stays booted and
is still recorded). Exit 0 always.
No snapshot, an unreadable snapshot or an unreadable list records nothing.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import _nowindow  # the one home of a no-window child start (hooks/_nowindow.py)
except ImportError:  # a hook never dies for a missing helper (it lands a moment after the hook in an install)
    _nowindow = subprocess

# A Bash call that cannot touch a simulator skips the ~0.3 s `simctl list`. ponytail: a boot hidden
# behind a script that never names these words goes unrecorded, and an unrecorded device is kept.
BASH_GUARD = re.compile(r"\b(?:simctl|xcodebuild|xcrun|xctest|fastlane|flutter|react-native|tuist|Simulator)\b|\bexpo\s+run:ios\b")


def devices():
    """{udid: (state, record)} from `simctl list`, or None when it could not be read."""
    try:
        answer = _nowindow.run(["xcrun", "simctl", "list", "devices", "--json"],
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
        table = _nowindow.run(["ps", "-axo", "pid=,ppid=,uid=,command="],
                               capture_output=True, text=True, timeout=30, env=env).stdout
        pids = [p[0] for p in (l.split(None, 3) for l in table.splitlines())
                if len(p) == 4 and "launchd_sim" in p[3] and udid in p[3]]
        if len(pids) != 1:  # none, or two: unclear
            return None, None
        out = _nowindow.run(["ps", "-o", "pid=,lstart=", "-p", pids[0]],
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


def sim_ok(udid):
    """True when bootstatus and a screenshot both exit 0. A timeout or error is a fail."""
    shot, ok = None, True  # a failed bootstatus still runs the screenshot; a bootstatus timeout skips it
    try:
        for argv, wait in ((["bootstatus", udid], 90), (["io", udid, "screenshot", None], 15)):
            if argv[-1] is None:
                fd, shot = tempfile.mkstemp(suffix=".png")
                os.close(fd)
                argv[-1] = shot
            ok = not _nowindow.run(["xcrun", "simctl"] + argv, capture_output=True,
                                    timeout=wait).returncode and ok
        return ok
    except Exception:
        return False
    finally:
        if shot:
            try:
                os.remove(shot)
            except OSError:
                pass


def retry(udid):
    """Shut down and boot UDID once, then check again."""
    for step, wait in (("shutdown", 30), ("boot", 60)):  # boot runs even when shutdown failed
        try:
            _nowindow.run(["xcrun", "simctl", step, udid], capture_output=True, timeout=wait)
        except Exception:
            pass
    return sim_ok(udid)


def main():
    try:
        payload = json.load(sys.stdin)
        tool_input = payload.get("tool_input") or {}
        if payload.get("tool_name") == "Bash":
            if not BASH_GUARD.search(str(tool_input.get("command", ""))):
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
            hits = [(u, rec) for u, (s, rec) in now.items()
                    if s == "Booted" and before.get(u) == "Shutdown" and (
                        u.upper() in names or (rec["name"] in names and by_name_ok(rec, now, payload)))]
            if payload.get("tool_name") == "Bash":  # check only the devices a `simctl boot` names
                booted = {m.strip("'\"").upper() for m in BOOT_ARG_RE.findall(str(tool_input.get("command", "")))}
                booted |= {m.strip("'\"") for m in BOOT_ARG_RE.findall(str(tool_input.get("command", "")))}
                to_check = {u for u, rec in hits if u.upper() in booted or rec["name"] in booted}
            else:
                to_check = {u for u, _ in hits}

            def record(u, rec):
                pid, start = launchd(u)
                if pid is None or start is None:
                    return  # unclear: no record, so the sweep keeps the device
                with open(os.path.join(state, "sim-boots.jsonl"), "a", encoding="utf-8") as f:
                    f.write(json.dumps({**rec, "at": at, "launchd_pid": pid, "launchd_start": start}) + "\n")
            notes, broken = [], []
            for u, rec in hits:
                record(u, rec)  # before the check: a hook killed mid-check still leaves a record
                if u in to_check and not sim_ok(u):
                    (notes if retry(u) else broken).append(u)
                    record(u, rec)  # the newest line holds the retry boot's pid
            msg = ("Simulator %s failed the boot check and was booted again. Launch again any app "
                   "this call launched." % ", ".join(notes)) if notes else ""
            if broken:
                print(json.dumps({"decision": "block", "reason": "Simulator %s is broken: it failed "
                                  "the boot check twice. Stop using it. %s"
                                  % (", ".join(broken), msg)}))
            elif notes:
                print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                                         "additionalContext": msg}}))
    except Exception:
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
