#!/usr/bin/env python3
"""Record each simulator a session call booted (docs/decisions/sweep-shuts-down-idle-simulators.md, ruling 1).

Modes:
- PreToolUse: Before a Bash call that names simulator tooling (simctl, xcodebuild) and a device,
  or a simulator MCP launch, saves the state of each simulator.
- PostToolUse: After such a call, appends each simulator that the call took from Shutdown to
  Booted to the boot record. After a `simctl boot` or an MCP `launch`, first checks each such
  device (bootstatus exits 0, a screenshot exits 0 and is not one colour). A device that fails
  the check is stopped and booted once more.

PreToolUse saves every device's state. PostToolUse of the same call appends each device that went
Shutdown -> Booted to <config>/state/sim-boots.jsonl. The boot check runs first, so the record
holds the retry boot's pid. Stdout stays empty unless a check failed: a retry that passed writes an
additionalContext note, a retry that failed writes a `block` decision (the device stays booted and
is still recorded). Exit 0 always.
No snapshot, an unreadable snapshot or an unreadable list records nothing.

Record mode: `sim_boot_record.py --record <UDID>`, which bin/sim-test calls after its own boot, appends
one record line for that device, read with the same devices() and launchd(). It prints nothing and
exits 0. It writes no line when the device is not listed or its launchd_sim is unclear.

Check mode: `sim_boot_record.py --check <UDID>`, which bin/sim-test calls after `--record` on its own boot (owner
ruling, page item 433 pick a, 2026-11-08 12:00 CST; decision sim-boot-is-verified). It runs sim_ok(UDID) once, the
same first-frame check as the hook modes, the one home of it. A pass prints nothing and exits 0. A fail prints one
stderr line naming the UDID and exits 1. It retries, shuts down and boots nothing. With no UDID it exits 2 and
calls no simctl. Cost: one bootstatus (up to 90 s) and one screenshot.
"""
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import zlib
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


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
SAMPLES_PER_PIXEL = {2: 3, 6: 4}  # the colour types frame_uniform judges: RGB and RGBA
MAX_FRAME_BYTES = 1 << 28  # a header that claims more is not a screenshot; it is left unjudged


def _filtered(kind, raw, prev, bpp):
    """One scanline RAW as the PNG encoder filters it with filter KIND, filter byte first. PREV is the row above."""
    left = bytes(bpp) + raw[:-bpp]
    if kind == 0:
        pred = bytes(len(raw))
    elif kind == 1:
        pred = left
    elif kind == 2:
        pred = prev
    elif kind == 3:
        pred = bytes((a + b) >> 1 for a, b in zip(left, prev))
    else:
        upleft = bytes(bpp) + prev[:-bpp]
        pred = bytearray()
        for a, b, c in zip(left, prev, upleft):
            pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
            pred.append(a if pa <= pb and pa <= pc else b if pb <= pc else c)
    return bytes([kind]) + bytes((x - y) & 0xFF for x, y in zip(raw, pred))


def frame_uniform(path):
    """True when every pixel of the PNG at PATH is one colour, False when not, None when it cannot be judged
    (not 8-bit RGB or RGBA, interlaced, bad structure, truncated, empty or missing). Never raises.

    Exact and stdlib only (Mac system python3 has no PIL). Under every PNG filter, row 0's first pixel
    is stored as is, so it is the colour C if the frame is uniform. Then each row of a uniform frame has one
    known filtered form per filter type (the row above is zeros for row 0, else the uniform row), and a
    row-by-row bytes comparison at C speed replaces a byte unfilter in Python."""
    try:
        with open(path, "rb") as handle:
            data = handle.read()
        if not data.startswith(PNG_SIGNATURE):
            return None
        pos, header, idat = len(PNG_SIGNATURE), None, []
        while pos + 8 <= len(data):
            size, kind = struct.unpack(">I4s", data[pos:pos + 8])
            body = data[pos + 8:pos + 8 + size]
            if len(body) < size:
                return None
            pos += 12 + size
            if kind == b"IHDR":
                header = body
            elif kind == b"IDAT":
                idat.append(body)
            elif kind == b"IEND":
                break
        else:
            return None  # no IEND: the file ends inside a chunk or before the image ends
        if header is None or len(header) != 13 or not idat:
            return None
        width, height, depth, colour, method, filtering, interlace = struct.unpack(">IIBBBBB", header)
        if depth != 8 or colour not in SAMPLES_PER_PIXEL or method or filtering or interlace:
            return None
        bpp = SAMPLES_PER_PIXEL[colour]
        stride = width * bpp + 1
        if not width or not height or stride * height > MAX_FRAME_BYTES:
            return None
        inflater = zlib.decompressobj()
        raw = inflater.decompress(b"".join(idat), stride * height + 1)
        if not inflater.eof or len(raw) != stride * height:
            return None
        pixel = raw[1:1 + bpp]
        row = pixel * width
        first = [_filtered(kind, row, bytes(len(row)), bpp) for kind in range(5)]
        later = [_filtered(kind, row, row, bpp) for kind in range(5)]
        for y in range(height):
            kind = raw[y * stride]
            if kind > 4:
                return None
            if raw[y * stride:(y + 1) * stride] != (first if y == 0 else later)[kind]:
                return False
        return True
    except Exception:
        return None


def sim_ok(udid):
    """True when bootstatus exits 0, the screenshot exits 0, and the screenshot is not one colour
    (frame_uniform is True: a black or blank display). A frame that cannot be judged passes. A timeout or error is a fail."""
    shot, ok = None, True  # a failed bootstatus still runs the screenshot; a bootstatus timeout skips it
    try:
        for argv, wait in ((["bootstatus", udid], 90), (["io", udid, "screenshot", None], 15)):
            if argv[-1] is None:
                fd, shot = tempfile.mkstemp(suffix=".png")
                os.close(fd)
                argv[-1] = shot
            ok = not _nowindow.run(["xcrun", "simctl"] + argv, capture_output=True,
                                    timeout=wait).returncode and ok
        return ok and frame_uniform(shot) is not True
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


def state_dir():
    return os.path.join(os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude"), "state")


def write_record(state, udid, rec, at):
    """Append one record line for UDID to <state>/sim-boots.jsonl. No line when its launchd_sim is unclear:
    the sweep then keeps the device. The one writer of the record, for the hook modes and `--record`."""
    pid, start = launchd(udid)
    if pid is None or start is None:
        return
    with open(os.path.join(state, "sim-boots.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({**rec, "at": at, "launchd_pid": pid, "launchd_start": start}) + "\n")


def record_one(udid):
    """`--record UDID`: one record line for the listed device UDID. Silent."""
    try:
        now = devices()
        if now is None or udid not in now:
            return
        state = state_dir()
        os.makedirs(state, exist_ok=True)
        write_record(state, udid, now[udid][1], time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    except Exception:
        pass


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
        state = state_dir()
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
                write_record(state, u, rec, at)
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
                                  "the boot check twice. Stop using it. %s (decision sim-boot-is-verified)"
                                  % (", ".join(broken), msg)}))
            elif notes:
                print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                                         "additionalContext": msg}}))
    except Exception:
        pass


if __name__ == "__main__":
    if sys.argv[1:2] == ["--check"]:
        if len(sys.argv) < 3 or not sys.argv[2]:
            sys.exit(2)
        if not sim_ok(sys.argv[2]):
            print("sim_boot_record: first-frame check failed for %s" % sys.argv[2], file=sys.stderr)
            sys.exit(1)
    elif sys.argv[1:2] == ["--record"]:
        if len(sys.argv) > 2:
            record_one(sys.argv[2])
    else:
        main()
    sys.exit(0)
