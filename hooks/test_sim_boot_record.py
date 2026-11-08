#!/usr/bin/env python3
"""Cases for hooks/sim_boot_record.py, the boot-record hook. Standard library only, `unittest`.

Run it from the repository root:

    python3 hooks/test_sim_boot_record.py -v

A hook on Bash and on the simulator MCP control tool records each device
that went shut-down -> booted during the call, in <config>/state/sim-boots.jsonl. The hook runs
for BOTH events of one call: a PreToolUse run snapshots every simulator's state, and the matching
PostToolUse run records the shut-down -> booted changes against that snapshot. A PostToolUse run
with no snapshot records nothing, so a device booted before the call is never recorded.

The contract pinned here (hooks/sim_boot_record.py must match it):
  - the event is read from `hook_event_name`. Exit is 0 in every case. Stdout is empty unless the
    boot check failed (see below).
  - boot check (decision sim-boot-is-verified): after a Bash `simctl boot` or an MCP `launch`, each device that went
    shut-down -> booted is checked: `xcrun simctl bootstatus <UDID>` exits 0 AND `xcrun simctl io
    <UDID> screenshot <file>` exits 0, AND `frame_uniform(<file>)` is not True (a frame of one colour,
    black or blank, fails the check). A fail runs `simctl shutdown <UDID>` then `simctl boot
    <UDID>` once, then checks again. A healthy boot writes nothing to stdout. A retry that passes
    writes {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": ...}}
    (booted again, launch the app again). A retry that fails writes {"decision": "block",
    "reason": ...} (names the UDID, broken, stop using it) and runs no second shutdown. The record
    line is written in both cases, and carries the launchd_sim pid read AFTER the retry. An
    `xcodebuild -destination` boot is not checked. The hung-bootstatus timeout (90 s) is not
    pinned: it needs an environment seam, and the suite must not wait.
  - frame_uniform(path) (decision sim-boot-is-verified): True when every pixel of the PNG is one colour, False when
    not, None when the file cannot be judged (not a PNG, 16-bit, palette, interlaced, truncated, empty, missing).
    `sim_ok` fails only on True. The frame cases build their PNGs with the encoder below. The judged
    8-bit cases cover all five filters; the undecodable and plain uniform cases use filter 0.
  - a record line is {"udid", "name", "deviceTypeIdentifier", "runtime", "at", "launchd_pid",
    "launchd_start"}. `at` is ISO-8601 UTC. launchd_pid and launchd_start are the pid and the start
    time of the device's launchd_sim, as `ps` prints them, read when the device is booted.
  - the hook reads `simctl list devices` (a simctl read) only for a Bash call whose command names a
    simulator tool as a whole word (simctl, xcodebuild, xcrun, ...), and for a simulator MCP call
    whose action is `launch`. `export FOO=1`, `swift build` and `expo start` name no simulator tool.
    The fake xcrun counts each run in a log, so the cases count the simctl reads.
  - the snapshot lives under <config>/state/. The cases find it by name-agnostic means: they only
    remove or corrupt files in that folder, never read the snapshot's own name.
  - record mode: `--record <UDID>` appends one record line for that device, from the same device list
    and launchd_sim read as the hook mode. bin/sim-test calls it after its own boot. It prints nothing
    and exits 0. It writes no line when the device is not listed or its launchd_sim is unclear.

Each case runs the hook as Claude Code does: one JSON object on stdin. A fake `xcrun` stands first on
PATH and answers `simctl list devices` from a file the case rewrites between the two events. A fake
`ps` stands there too, with a launchd_sim row for each UDID. Its argv naming `lstart` answers
"PID START" lines when the -o list names pid=, else "START" lines.
No environment seam reaches the hook except CLAUDE_CONFIG_DIR and PATH, which Claude Code sets too.
"""

import importlib.util
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import unittest
import zlib
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "sim_boot_record.py")
sys.path.insert(0, os.path.join(HERE, "..", "lint"))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)

RUN_FOLDER = _test_temp.run_folder()  # every temp path of this run lives under here
unittest.addModuleCleanup(shutil.rmtree, RUN_FOLDER, True)

MCP = "mcp__Claude_Code_iOS_Simulator__control"
RT = "com.apple.CoreSimulator.SimRuntime.iOS-26-0"
RT_OLD = "com.apple.CoreSimulator.SimRuntime.iOS-25-0"
TYPE_PRO = "com.apple.CoreSimulator.SimDeviceType.iPhone-17-Pro"
TYPE_AIR = "com.apple.CoreSimulator.SimDeviceType.iPad-Air"
U1 = "1A2B3C4D-0000-4000-8000-000000000101"
U2 = "1A2B3C4D-0000-4000-8000-000000000102"
U3 = "1A2B3C4D-0000-4000-8000-000000000103"
LAUNCHD_PIDS = {U1: 2001, U2: 2002, U3: 2003}  # the launchd_sim pid the fake `ps` gives each UDID
LSTART = "Sat Oct 10 07:00:00 2026"            # the start time the fake `ps` gives every launchd_sim
LAUNCHD_CMD = ("/Library/Developer/PrivateFrameworks/CoreSimulator.framework/Versions/A/"
               "Resources/launchd_sim")
POSIX = not sys.platform.startswith("win")


def devices_json(rows):
    """rows: (udid, name, state, deviceTypeIdentifier[, runtime]). The runtime defaults to RT."""
    grouped = {}
    for row in rows:
        udid, name, state, dtype = row[:4]
        runtime = row[4] if len(row) > 4 else RT
        grouped.setdefault(runtime, []).append({
            "udid": udid, "name": name, "state": state, "deviceTypeIdentifier": dtype,
            "isAvailable": True})
    return json.dumps({"devices": grouped})


# ------------------------------------------------------------------ PNG fixtures (stdlib only)
# A small PNG encoder for the frame cases. It writes 8-bit RGB (colour type 2) and RGBA (6),
# non-interlaced, with a chosen filter per row, so every unfilter path runs. The undecodable cases
# reuse it with a 16-bit depth, a palette (3), the interlace flag, or a cut stream.

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
BLACK_RGBA = b"\x00\x00\x00\xff"
WHITE_RGB = b"\xff\xff\xff"
COLOUR_RGB = bytes([200, 100, 50])
# The fake xcrun runs this to copy a fixture to the screenshot path, then to log the fixture's name.
# It sits in shell double quotes, so it holds no $ and no backtick.
FRAME_COPY = ("import shutil,sys; shutil.copyfile(sys.argv[1],sys.argv[2]); "
              "open(sys.argv[3],'a').write(sys.argv[4]+'\\n')")


def chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def filter_row(kind, raw, prev, bpp):
    """One scanline with its filter type byte. PREV is the unfiltered row above (zeros for the first)."""
    left = bytes(bpp) + raw[:-bpp]
    upleft = bytes(bpp) + prev[:-bpp]
    if kind == 0:
        pred = bytes(len(raw))
    elif kind == 1:
        pred = left
    elif kind == 2:
        pred = prev
    elif kind == 3:
        pred = bytes((a + b) >> 1 for a, b in zip(left, prev))
    elif kind == 4:
        pred = bytes(paeth(a, b, c) for a, b, c in zip(left, prev, upleft))
    else:
        raise ValueError("filter type %r is not 0-4" % kind)
    return bytes([kind]) + bytes((x - p) & 0xFF for x, p in zip(raw, pred))


def make_png(rows, width, colour_type=6, depth=8, filters=0, idat_size=None, interlace=0, palette=None):
    """A PNG of ROWS, each one scanline of raw sample bytes. FILTERS is one filter for every row, or a list
    cycled over the rows. IDAT_SIZE splits the zlib stream into IDAT chunks of that many bytes."""
    kinds = [filters] if isinstance(filters, int) else list(filters)
    bpp = max(1, CHANNELS[colour_type] * depth // 8)
    filtered, prev = bytearray(), bytes(len(rows[0]))
    for y, raw in enumerate(rows):
        filtered += filter_row(kinds[y % len(kinds)], raw, prev, bpp)
        prev = raw
    stream = zlib.compress(bytes(filtered))
    size = idat_size or len(stream)
    pieces = [stream[i:i + size] for i in range(0, len(stream), size)]
    header = struct.pack(">IIBBBBB", width, len(rows), depth, colour_type, 0, 0, interlace)
    out = PNG_SIGNATURE + chunk(b"IHDR", header)
    if palette is not None:
        out += chunk(b"PLTE", palette)
    out += b"".join(chunk(b"IDAT", piece) for piece in pieces)
    return out + chunk(b"IEND", b"")


def rows_of(width, height, pixel):
    """Every row one colour. PIXEL is the bytes of one pixel."""
    return [pixel * width] * height


def live_rows(width, height, channels):
    """Varied pixels: the frame is not one colour."""
    return [bytes((x * 7 + y * 13 + c * 31) % 256 for x in range(width) for c in range(channels))
            for y in range(height)]


def sub_ramp_rows(width, height, step, channels):
    """Pixel x holds (x + 1) * step on every channel. Sub filtering turns each row into bytes of STEP alone."""
    row = b"".join(bytes([(x + 1) * step] * channels) for x in range(width))
    return [row] * height


def up_ramp_rows(width, height, step, channels):
    """Row y holds (y + 1) * step. Up filtering turns every row into bytes of STEP alone."""
    return [bytes([(y + 1) * step] * (width * channels)) for y in range(height)]


def with_byte(rows, y, index, value):
    """ROWS with byte INDEX of row Y set to VALUE."""
    changed = list(rows)
    row = bytearray(changed[y])
    row[index] = value
    changed[y] = bytes(row)
    return changed


def cut_inside_idat(data):
    """DATA cut three bytes into the first IDAT chunk's data: no IEND, and the chunk is short."""
    return data[:data.index(b"IDAT") + 4 + 3]


def integration_frames():
    """The fixtures the fake xcrun copies to a screenshot path, by name."""
    return {
        "live": make_png(live_rows(32, 64, 4), 32, colour_type=6, filters=[0, 1, 2, 3, 4]),
        "black": make_png(rows_of(32, 64, BLACK_RGBA), 32, colour_type=6, filters=[0, 1, 2, 3, 4]),
        "blank": make_png(rows_of(32, 64, WHITE_RGB), 32, colour_type=2, filters=[0, 1, 2, 3, 4]),
        "undecodable": make_png(rows_of(32, 64, b"\x00" * 6), 32, colour_type=2, depth=16),
    }


def fake_ps_script(rows, log, flag=None, rows_after=None):
    """A POSIX `ps` for ROWS, (pid, ppid, uid, command), all strings. Each call appends its
    LC_ALL to LOG, so a case can see the locale the hook ran the read under. When the file FLAG
    exists (the fake `xcrun` makes it on `simctl boot`), the table is ROWS_AFTER instead."""
    def block(rows):
        table = "".join("%s %s %s %s\n" % row for row in rows)
        starts = [(pid, cmd) for pid, _, _, cmd in rows if "launchd_sim" in cmd]
        pid_lines = "".join("%s %s\n" % (pid, LSTART) for pid, _ in starts)
        start_lines = "".join(LSTART + "\n" for _ in starts)
        for text in (table, pid_lines, start_lines):
            assert "'" not in text, "the printf body is single-quoted"
        return ("case \"$*\" in\n"
                "  *lstart*) case \"$*\" in *pid=*) printf '%s' '" + pid_lines + "' ;;"
                " *) printf '%s' '" + start_lines + "' ;; esac ;;\n"
                "  *) printf '%s' '" + table + "' ;;\n"
                "esac\n")
    head = "#!/bin/sh\necho \"${LC_ALL-unset}\" >> '" + log + "'\n"
    if flag and rows_after is not None:
        return (head + "if [ -e '" + flag + "' ]; then\n" + block(rows_after) + "else\n"
                + block(rows) + "fi\n")
    return head + block(rows)


@unittest.skipIf(not POSIX, "the fake xcrun is a POSIX shell script")
class SimBootRecordTests(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="sim_boot_record_", dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, self.root, True)
        self.cfg = os.path.join(self.root, "cfg")
        self.state = os.path.join(self.cfg, "state")
        self.bin = os.path.join(self.root, "bin")
        self.empty = os.path.join(self.root, "empty")
        os.makedirs(self.bin)
        os.makedirs(self.empty)
        self.fake = os.path.join(self.bin, "xcrun")
        self.reads = os.path.join(self.root, "simctl-reads.log")
        self.records = os.path.join(self.state, "sim-boots.jsonl")
        self.ps_log = os.path.join(self.root, "ps-locale.log")
        self.calls = os.path.join(self.root, "boot-check-calls.log")  # one "name UDID" per call
        self.plans = os.path.join(self.root, "plans")                 # <name>: one exit code per call
        self.booted_flag = os.path.join(self.root, "fake-boot-ran")
        self.frame_dir = os.path.join(self.root, "frames")              # the scripted screenshot fixtures
        self.frame_plan_path = os.path.join(self.root, "frame-plan")    # one fixture name per screenshot call
        self.frame_log = os.path.join(self.root, "frames-written.log")  # one name per frame the fake wrote
        os.makedirs(self.plans)
        os.makedirs(self.frame_dir)
        for name, data in integration_frames().items():
            with open(os.path.join(self.frame_dir, name + ".png"), "wb") as handle:
                handle.write(data)
        # A default `ps` with a launchd_sim row for each UDID, so a boot's record can name one.
        self.write_ps([(str(LAUNCHD_PIDS[u]), "1", "0", LAUNCHD_CMD + " " + u)
                       for u in (U1, U2, U3)])

    # ------------------------------------------------------------------ helpers

    def write_ps(self, rows, rows_after=None):
        """Make the fake `ps` answer the process table ROWS, (pid, ppid, uid, command). With
        ROWS_AFTER, it answers that table once the fake `simctl boot` has run."""
        path = os.path.join(self.bin, "ps")
        init = [("1", "0", "0", "/sbin/launchd")]
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(fake_ps_script(
                init + list(rows), self.ps_log, self.booted_flag,
                None if rows_after is None else init + list(rows_after)))
        os.chmod(path, 0o755)

    def simctl_reads(self):
        """How many times the fake xcrun ran `simctl list devices` since the last reset_reads."""
        if not os.path.exists(self.reads):
            return 0
        with open(self.reads, encoding="utf-8") as handle:
            return len(handle.read().splitlines())

    def reset_reads(self):
        if os.path.exists(self.reads):
            os.remove(self.reads)

    def set_devices(self, rows, rc=0):
        """Make the fake xcrun answer the device list ROWS, or fail with RC. Each run is logged."""
        if rc:
            body = "exit %d\n" % rc
        else:
            text = devices_json(rows)
            assert "'" not in text, "the printf body is single-quoted"
            body = "printf '%s' '" + text + "'\n"
        # `simctl list` answers BODY. bootstatus, io screenshot, shutdown and boot log "name UDID"
        # and exit with line N of plans/<name> for their Nth call (0 when the plan has no line N).
        # Shell builtins only: the hook's PATH holds no grep or sed. A boot also makes the flag file the fake `ps` reads.
        # A screenshot copies its scripted frame fixture to its file, with FRAME_COPY, and logs the fixture's name.
        script = (
            "#!/bin/sh\n"
            "case \"$*\" in\n"
            "  \"simctl list devices\"*) echo read >> '" + self.reads + "'\n" + body + "  ;;\n"
            "  \"simctl bootstatus \"*|\"simctl io \"*|\"simctl shutdown \"*|\"simctl boot \"*)\n"
            "    case \"$2\" in io) name=$4; udid=$3 ;; *) name=$2; udid=$3 ;; esac\n"
            "    echo \"$name $udid\" >> '" + self.calls + "'\n"
            "    n=0; while read -r l _; do [ \"$l\" = \"$name\" ] && n=$((n+1)); done < '" + self.calls + "'\n"
            "    [ \"$name\" = boot ] && : > '" + self.booted_flag + "'\n"
            "    i=0; rc=0; [ -f '" + self.plans + "'/\"$name\" ] && while read -r v; do"
            " i=$((i+1)); [ $i -eq $n ] && rc=$v; done < '" + self.plans + "'/\"$name\"\n"
            "    if [ \"$name\" = screenshot ]; then f=live; i=0; [ -f '" + self.frame_plan_path + "' ] && while read -r v; do"
            " i=$((i+1)); [ $i -eq $n ] && f=$v; done < '" + self.frame_plan_path + "'\n"
            "      '" + sys.executable + "' -I -c \"" + FRAME_COPY + "\" '" + self.frame_dir + "'/\"$f\".png \"$5\""
            " '" + self.frame_log + "' \"$f\"; fi\n"
            "    exit \"${rc:-0}\" ;;\n"
            "esac\n")
        with open(self.fake, "w", encoding="utf-8") as handle:
            handle.write(script)
        os.chmod(self.fake, 0o755)

    def plan(self, name, *rcs):
        """Script the exit codes of the fake xcrun's NAME calls (bootstatus, screenshot, shutdown,
        boot), one per call in order. A call past the list exits 0."""
        with open(os.path.join(self.plans, name), "w", encoding="utf-8") as handle:
            handle.write("".join("%d\n" % rc for rc in rcs))

    def script_frames(self, *names):
        """Script the fixture the fake xcrun copies to the path of each screenshot call, in order. A call past
        the list gets a live frame."""
        for name in names:
            self.assertTrue(os.path.exists(os.path.join(self.frame_dir, name + ".png")),
                            "no fixture named %s" % name)
        with open(self.frame_plan_path, "w", encoding="utf-8") as handle:
            handle.write("".join(name + "\n" for name in names))

    def frames_written(self):
        """The fixture names the fake xcrun copied to a screenshot path, in order."""
        if not os.path.exists(self.frame_log):
            return []
        with open(self.frame_log, encoding="utf-8") as handle:
            return handle.read().splitlines()

    def check_calls(self):
        """The "name UDID" lines the fake xcrun logged for the check and the retry, in order."""
        if not os.path.exists(self.calls):
            return []
        with open(self.calls, encoding="utf-8") as handle:
            return handle.read().splitlines()

    def post_raw(self, rows, tool=None, tool_input=None):
        """Like post, but returns the result and asserts only exit 0."""
        self.set_devices(rows)
        result = self.run_hook("PostToolUse", tool=tool, tool_input=tool_input)
        self.assertEqual(result.returncode, 0, "PostToolUse failed: %s" % result.stderr[:300])
        return result

    def run_hook(self, event, tool=None, tool_input=None, path=None):
        payload = {"hook_event_name": event, "session_id": "sim-boot-record-cases",
                   "tool_name": tool or "Bash",
                   "tool_input": tool_input or {"command": "xcrun simctl boot " + U1}}
        if event == "PostToolUse":
            payload["tool_response"] = {"stdout": "", "stderr": "", "interrupted": False}
        env = dict(os.environ)
        env["CLAUDE_CONFIG_DIR"] = self.cfg
        env["PATH"] = self.bin + os.pathsep + os.path.dirname(sys.executable) \
            if path is None else path
        result = subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                                capture_output=True, text=True, env=env, timeout=60)
        return result

    def pre(self, rows, tool=None, tool_input=None):
        self.set_devices(rows)
        result = self.run_hook("PreToolUse", tool=tool, tool_input=tool_input)
        self.assertEqual(result.returncode, 0, "PreToolUse failed: %s" % result.stderr[:300])
        self.assertEqual(result.stdout, "", "PreToolUse wrote to stdout: %r" % result.stdout[:200])

    def post(self, rows, tool=None, tool_input=None):
        self.set_devices(rows)
        result = self.run_hook("PostToolUse", tool=tool, tool_input=tool_input)
        self.assertEqual(result.returncode, 0, "PostToolUse failed: %s" % result.stderr[:300])
        self.assertEqual(result.stdout, "", "PostToolUse wrote to stdout: %r" % result.stdout[:200])

    def read_records(self):
        if not os.path.exists(self.records):
            return []
        with open(self.records, encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    # ------------------------------------------------------------------ cases

    def test_a_shut_down_device_booted_during_a_bash_call_is_recorded(self):
        self.pre([(U1, "Idle Pro", "Shutdown", TYPE_PRO)])
        self.post([(U1, "Idle Pro", "Booted", TYPE_PRO)])
        records = self.read_records()
        self.assertEqual(len(records), 1, "the shut-down -> booted device was not recorded")
        record = records[0]
        self.assertEqual(record["udid"], U1)
        self.assertEqual(record["name"], "Idle Pro")
        self.assertEqual(record["deviceTypeIdentifier"], TYPE_PRO)
        self.assertEqual(record["runtime"], RT)
        time.strptime(record["at"], "%Y-%m-%dT%H:%M:%SZ")  # raises if `at` is not ISO-8601 UTC

    def test_the_simulator_mcp_control_tool_is_recorded_the_same_way(self):
        mcp_input = {"action": "launch", "device": U1}
        self.pre([(U1, "Idle Pro", "Shutdown", TYPE_PRO)], tool=MCP, tool_input=mcp_input)
        self.post([(U1, "Idle Pro", "Booted", TYPE_PRO)], tool=MCP, tool_input=mcp_input)
        self.assertEqual([r["udid"] for r in self.read_records()], [U1],
                         "the MCP control tool's boot was not recorded")

    def test_only_the_devices_that_changed_are_recorded(self):
        # The call names U1 and U2 and not U3, so U3 (already booted) is out whatever it does.
        ti = {"command": "xcrun simctl boot " + U1 + " " + U2}
        self.pre([(U1, "Idle Pro", "Shutdown", TYPE_PRO), (U2, "Idle Air", "Shutdown", TYPE_AIR),
                  (U3, "Already Up", "Booted", TYPE_PRO)], tool_input=ti)
        self.post([(U1, "Idle Pro", "Booted", TYPE_PRO), (U2, "Idle Air", "Booted", TYPE_AIR),
                   (U3, "Already Up", "Booted", TYPE_PRO)], tool_input=ti)
        self.assertEqual(sorted(r["udid"] for r in self.read_records()), sorted([U1, U2]),
                         "the two shut-down -> booted devices were not both recorded")

    def test_a_device_booted_before_the_call_is_not_recorded(self):
        self.pre([(U1, "Owner Pro", "Booted", TYPE_PRO)])
        self.post([(U1, "Owner Pro", "Booted", TYPE_PRO)])
        self.assertEqual(self.read_records(), [], "an owner-booted device was recorded")

    def test_a_device_shut_down_during_the_call_is_not_recorded(self):
        self.pre([(U1, "Idle Pro", "Booted", TYPE_PRO)])
        self.post([(U1, "Idle Pro", "Shutdown", TYPE_PRO)])
        self.assertEqual(self.read_records(), [], "a shutdown was recorded as a boot")

    def test_a_post_with_no_snapshot_records_nothing(self):
        self.set_devices([(U1, "Idle Pro", "Booted", TYPE_PRO)])
        result = self.run_hook("PostToolUse")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.read_records(), [], "a boot with no before-state was recorded")

    def test_a_failed_pre_read_records_nothing(self):
        self.set_devices([], rc=1)
        self.assertEqual(self.run_hook("PreToolUse").returncode, 0)
        self.post([(U1, "Idle Pro", "Booted", TYPE_PRO)])
        self.assertEqual(self.read_records(), [], "a boot was recorded from an unreadable before")

    def test_a_corrupt_snapshot_records_nothing(self):
        self.pre([(U1, "Idle Pro", "Shutdown", TYPE_PRO)])
        self.assertTrue(os.path.isdir(self.state), "the pre-run wrote no state folder")
        for name in os.listdir(self.state):
            if name != "sim-boots.jsonl":
                with open(os.path.join(self.state, name), "w", encoding="utf-8") as handle:
                    handle.write("{ this is not the snapshot")
        self.post([(U1, "Idle Pro", "Booted", TYPE_PRO)])
        self.assertEqual(self.read_records(), [], "a corrupt snapshot still recorded a boot")

    def test_a_repeated_boot_is_recorded_once(self):
        self.pre([(U1, "Idle Pro", "Shutdown", TYPE_PRO)])
        self.post([(U1, "Idle Pro", "Booted", TYPE_PRO)])
        self.pre([(U1, "Idle Pro", "Booted", TYPE_PRO)])
        self.post([(U1, "Idle Pro", "Booted", TYPE_PRO)])
        self.assertEqual(len(self.read_records()), 1, "a device already booted was recorded again")

    def test_the_record_carries_the_launchd_sim_pid_and_start_time(self):
        self.pre([(U1, "Idle Pro", "Shutdown", TYPE_PRO)])
        self.post([(U1, "Idle Pro", "Booted", TYPE_PRO)])
        records = self.read_records()
        self.assertEqual(len(records), 1, "the shut-down -> booted device was not recorded")
        self.assertEqual(str(records[0].get("launchd_pid")), str(LAUNCHD_PIDS[U1]),
                         "the record does not name the launchd_sim pid of this boot")
        self.assertEqual(records[0].get("launchd_start"), LSTART,
                         "the record does not name the launchd_sim start time of this boot")

    def test_bash_commands_naming_no_simulator_tool_never_read_simctl(self):
        rows = [(U1, "Idle Pro", "Shutdown", TYPE_PRO)]
        for command in ("export FOO=1", "swift build", "expo start"):
            with self.subTest(command=command):
                self.reset_reads()
                tool_input = {"command": command}
                self.pre(rows, tool_input=tool_input)
                self.post([(U1, "Idle Pro", "Booted", TYPE_PRO)], tool_input=tool_input)
                self.assertEqual(self.simctl_reads(), 0,
                                 "the Bash command %r read simctl" % command)

    def test_simulator_mcp_calls_other_than_launch_never_read_simctl(self):
        rows = [(U1, "Idle Pro", "Shutdown", TYPE_PRO)]
        for action in ("screenshot", "tap"):
            with self.subTest(action=action):
                self.reset_reads()
                tool_input = {"action": action, "device": U1}
                self.pre(rows, tool=MCP, tool_input=tool_input)
                self.post(rows, tool=MCP, tool_input=tool_input)
                self.assertEqual(self.simctl_reads(), 0,
                                 "the simulator MCP action %r read simctl" % action)

    def test_a_simctl_boot_and_an_mcp_launch_do_read_simctl(self):
        # Controls for the read counter: the two shapes that must read.
        rows = [(U1, "Idle Pro", "Shutdown", TYPE_PRO)]
        self.reset_reads()
        self.pre(rows)
        self.assertGreaterEqual(self.simctl_reads(), 1, "a Bash simctl boot did not read simctl")
        self.reset_reads()
        self.pre(rows, tool=MCP, tool_input={"action": "launch", "device": U1})
        self.assertGreaterEqual(self.simctl_reads(), 1, "an MCP launch did not read simctl")

    def test_a_device_booted_by_hand_during_a_call_naming_another_is_not_recorded(self):
        ti = {"command": "xcodebuild test -scheme App -destination id=" + U1}
        rows = [(U1, "Named Pro", "Shutdown", TYPE_PRO), (U2, "Hand Air", "Shutdown", TYPE_AIR)]
        self.pre(rows, tool_input=ti)
        self.post([(U1, "Named Pro", "Booted", TYPE_PRO), (U2, "Hand Air", "Booted", TYPE_AIR)],
                  tool_input=ti)
        self.assertEqual([r["udid"] for r in self.read_records()], [U1],
                         "a device the call did not name was recorded as its boot")

    def test_an_os_pin_in_another_destination_does_not_pin_this_name(self):
        # OS=26.0 sits in the destination that names iPad Air. iPhone 17 has two runtimes, so the
        # name is ambiguous for its own destination and nothing is recorded.
        ti = {"command": "xcodebuild test -scheme App "
                         "-destination 'name=iPad Air,OS=26.0' -destination 'name=iPhone 17'"}
        rows = [(U1, "iPhone 17", "Shutdown", TYPE_PRO, RT),
                (U2, "iPhone 17", "Shutdown", TYPE_PRO, RT_OLD),
                (U3, "iPad Air", "Shutdown", TYPE_AIR, RT)]
        self.pre(rows, tool_input=ti)
        self.post([(U1, "iPhone 17", "Booted", TYPE_PRO, RT),
                   (U2, "iPhone 17", "Shutdown", TYPE_PRO, RT_OLD),
                   (U3, "iPad Air", "Shutdown", TYPE_AIR, RT)], tool_input=ti)
        self.assertEqual(self.read_records(), [],
                         "an OS pin in another destination picked the iPhone 17 on iOS 26")

    def test_an_os_pin_in_the_naming_destination_records_that_device(self):
        # Control: the OS pin sits in the destination that names iPhone 17.
        ti = {"command": "xcodebuild test -scheme App "
                         "-destination 'name=iPad Air' -destination 'name=iPhone 17,OS=26.0'"}
        rows = [(U1, "iPhone 17", "Shutdown", TYPE_PRO, RT),
                (U2, "iPhone 17", "Shutdown", TYPE_PRO, RT_OLD),
                (U3, "iPad Air", "Shutdown", TYPE_AIR, RT)]
        self.pre(rows, tool_input=ti)
        self.post([(U1, "iPhone 17", "Booted", TYPE_PRO, RT),
                   (U2, "iPhone 17", "Shutdown", TYPE_PRO, RT_OLD),
                   (U3, "iPad Air", "Shutdown", TYPE_AIR, RT)], tool_input=ti)
        self.assertEqual([r["udid"] for r in self.read_records()], [U1],
                         "an OS pin in the naming destination did not pick iPhone 17 on iOS 26")

    def test_a_call_naming_a_device_by_name_records_only_that_name(self):
        ti = {"command": "xcodebuild test -scheme App -destination "
                         "'platform=iOS Simulator,name=iPhone 17'"}
        rows = [(U1, "iPhone 17", "Shutdown", TYPE_PRO), (U2, "iPhone 17 Pro", "Shutdown", TYPE_PRO)]
        self.pre(rows, tool_input=ti)
        self.post([(U1, "iPhone 17", "Booted", TYPE_PRO), (U2, "iPhone 17 Pro", "Booted", TYPE_PRO)],
                  tool_input=ti)
        self.assertEqual([r["udid"] for r in self.read_records()], [U1],
                         "a device with another name was recorded for a call that names iPhone 17")

    def test_an_mcp_launch_by_name_records_only_that_name(self):
        ti = {"action": "launch", "device": "iPhone 17"}
        rows = [(U1, "iPhone 17", "Shutdown", TYPE_PRO), (U2, "iPhone 17 Pro", "Shutdown", TYPE_PRO)]
        self.pre(rows, tool=MCP, tool_input=ti)
        self.post([(U1, "iPhone 17", "Booted", TYPE_PRO), (U2, "iPhone 17 Pro", "Booted", TYPE_PRO)],
                  tool=MCP, tool_input=ti)
        self.assertEqual([r["udid"] for r in self.read_records()], [U1],
                         "a device with another name was recorded for an MCP launch by name")

    def test_an_mcp_launch_by_udid_records_only_that_udid(self):
        ti = {"action": "launch", "device": U1}
        rows = [(U1, "Named Pro", "Shutdown", TYPE_PRO), (U2, "Hand Air", "Shutdown", TYPE_AIR)]
        self.pre(rows, tool=MCP, tool_input=ti)
        self.post([(U1, "Named Pro", "Booted", TYPE_PRO), (U2, "Hand Air", "Booted", TYPE_AIR)],
                  tool=MCP, tool_input=ti)
        self.assertEqual([r["udid"] for r in self.read_records()], [U1],
                         "a device the MCP launch did not name was recorded")

    def test_a_call_naming_no_device_records_nothing(self):
        ti = {"command": "xcodebuild build -scheme App"}
        self.pre([(U1, "Hand Pro", "Shutdown", TYPE_PRO)], tool_input=ti)
        self.post([(U1, "Hand Pro", "Booted", TYPE_PRO)], tool_input=ti)
        self.assertEqual(self.read_records(), [],
                         "a call that names no device recorded a device booted during it")

    def test_an_mcp_launch_by_the_udid_alias_records_that_udid(self):
        ti = {"action": "launch", "udid": U1}
        rows = [(U1, "Named Pro", "Shutdown", TYPE_PRO), (U2, "Hand Air", "Shutdown", TYPE_AIR)]
        self.pre(rows, tool=MCP, tool_input=ti)
        self.post([(U1, "Named Pro", "Booted", TYPE_PRO), (U2, "Hand Air", "Booted", TYPE_AIR)],
                  tool=MCP, tool_input=ti)
        self.assertEqual([r["udid"] for r in self.read_records()], [U1],
                         "an MCP launch that names its device by the udid key recorded nothing")

    def test_an_mcp_launch_naming_device_and_udid_records_both(self):
        # guard.py judges every non-empty name in device and udid. The record must do the same:
        # the udid is dropped when device is set, so U2 (booted by the call) is not recorded.
        ti = {"action": "launch", "device": U1, "udid": U2}
        rows = [(U1, "Named Pro", "Shutdown", TYPE_PRO), (U2, "Hand Air", "Shutdown", TYPE_AIR)]
        self.pre(rows, tool=MCP, tool_input=ti)
        self.post([(U1, "Named Pro", "Booted", TYPE_PRO), (U2, "Hand Air", "Booted", TYPE_AIR)],
                  tool=MCP, tool_input=ti)
        self.assertEqual(sorted(r["udid"] for r in self.read_records()), sorted([U1, U2]),
                         "an MCP launch naming device and udid did not record both devices")

    def test_a_name_shared_by_two_runtimes_records_neither_when_both_boot(self):
        ti = {"command": "xcodebuild test -scheme App -destination "
                         "'platform=iOS Simulator,name=iPhone 17'"}
        rows = [(U1, "iPhone 17", "Shutdown", TYPE_PRO, RT),
                (U2, "iPhone 17", "Shutdown", TYPE_PRO, RT_OLD)]
        self.pre(rows, tool_input=ti)
        self.post([(U1, "iPhone 17", "Booted", TYPE_PRO, RT),
                   (U2, "iPhone 17", "Booted", TYPE_PRO, RT_OLD)], tool_input=ti)
        self.assertEqual(self.read_records(), [],
                         "an ambiguous name shared by two runtimes recorded a device")

    def test_a_name_pinned_to_an_os_records_only_the_device_on_that_runtime(self):
        ti = {"command": "xcodebuild test -scheme App -destination "
                         "'platform=iOS Simulator,name=iPhone 17,OS=26.0'"}
        rows = [(U1, "iPhone 17", "Shutdown", TYPE_PRO, RT),
                (U2, "iPhone 17", "Shutdown", TYPE_PRO, RT_OLD)]
        self.pre(rows, tool_input=ti)
        self.post([(U1, "iPhone 17", "Booted", TYPE_PRO, RT),
                   (U2, "iPhone 17", "Booted", TYPE_PRO, RT_OLD)], tool_input=ti)
        self.assertEqual([r["udid"] for r in self.read_records()], [U1],
                         "OS=26.0 did not pick the device on the iOS 26 runtime")

    def test_two_launchd_sims_for_one_udid_record_nothing_for_it(self):
        self.write_ps([("90", "1", "0", LAUNCHD_CMD + " " + U1),
                       ("200", "1", "0", LAUNCHD_CMD + " " + U1)])
        self.pre([(U1, "Idle Pro", "Shutdown", TYPE_PRO)])
        self.post([(U1, "Idle Pro", "Booted", TYPE_PRO)])
        self.assertEqual(self.read_records(), [],
                         "a UDID with two live launchd_sim processes was recorded with one pid")

    def test_both_ps_reads_run_under_lc_all_c(self):
        # The table read and the lstart read force the C locale, whatever the parent's locale is.
        rows = [(U1, "Idle Pro", "Shutdown", TYPE_PRO)]
        with mock.patch.dict(os.environ, {"LC_ALL": "de_DE.UTF-8"}):
            self.pre(rows)
            self.post([(U1, "Idle Pro", "Booted", TYPE_PRO)])
        with open(self.ps_log, encoding="utf-8") as handle:
            seen = handle.read().splitlines()
        self.assertGreaterEqual(len(seen), 2, "the hook made no ps read for the boot")
        self.assertEqual(set(seen), {"C"}, "a ps read ran under a locale other than C: %r" % seen)

    def test_malformed_stdin_exits_zero_and_records_nothing(self):
        self.set_devices([(U1, "Idle Pro", "Booted", TYPE_PRO)])
        env = dict(os.environ, CLAUDE_CONFIG_DIR=self.cfg, PATH=self.bin)
        result = subprocess.run([sys.executable, HOOK], input="{not json",
                                capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(result.returncode, 0, "a malformed payload crashed the hook")
        self.assertEqual(result.stdout, "")
        self.assertEqual(self.read_records(), [])

    def test_no_xcrun_on_the_path_records_nothing_and_never_blocks(self):
        result = self.run_hook("PreToolUse", path=self.empty)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        result = self.run_hook("PostToolUse", path=self.empty)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(self.read_records(), [])


    # ------------------------------------------------------------------ boot check (sim-boot-is-verified)

    OFF = [(U1, "Idle Pro", "Shutdown", TYPE_PRO)]
    ON = [(U1, "Idle Pro", "Booted", TYPE_PRO)]

    def ps_with_retry_pid(self):
        """The launchd_sim pid of U1 is 2001 until the fake boot runs, 3001 after it."""
        row = lambda pid: [(pid, "1", "0", LAUNCHD_CMD + " " + U1)]
        self.write_ps(row("2001"), rows_after=row("3001"))

    def boot_and_check(self, tool=None, tool_input=None):
        self.pre(self.OFF, tool=tool, tool_input=tool_input)
        return self.post_raw(self.ON, tool=tool, tool_input=tool_input)

    def test_a_healthy_boot_runs_the_check_and_writes_nothing(self):
        result = self.boot_and_check()
        self.assertEqual(result.stdout, "", "a healthy boot wrote to stdout")
        self.assertEqual(self.check_calls(), ["bootstatus " + U1, "screenshot " + U1],
                         "the check did not run bootstatus then io screenshot, or ran more")
        self.assertEqual([r["udid"] for r in self.read_records()], [U1],
                         "a healthy boot must leave exactly one record line")

    def test_a_healthy_mcp_launch_runs_the_check_and_writes_nothing(self):
        ti = {"action": "launch", "device": U1}
        result = self.boot_and_check(tool=MCP, tool_input=ti)
        self.assertEqual(result.stdout, "", "a healthy MCP launch wrote to stdout")
        self.assertEqual(self.check_calls(), ["bootstatus " + U1, "screenshot " + U1],
                         "an MCP launch was not checked")

    def test_a_failed_check_is_retried_once_and_a_pass_tells_the_session(self):
        cases = {"bootstatus fails": ("bootstatus", [1]), "screenshot fails": ("screenshot", [1])}
        for label, (name, rcs) in cases.items():
            with self.subTest(label):
                self.tearDown_state()
                self.ps_with_retry_pid()
                self.plan(name, *rcs)
                result = self.boot_and_check()
                names = [c.split()[0] for c in self.check_calls()]
                self.assertEqual([n for n in names if n in ("shutdown", "boot")],
                                 ["shutdown", "boot"], "no single shutdown then boot after a fail")
                self.assertLess(names.index("shutdown"), names.index("boot"))
                self.assertEqual(names[-1], "screenshot", "no second check after the retry")
                self.assertIn("bootstatus", names[names.index("boot"):],
                              "the check did not run again after the boot")
                self.assertIn(U1, [c.split()[1] for c in self.check_calls() if c.startswith("shutdown")])
                out = json.loads(result.stdout)
                self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "PostToolUse")
                note = out["hookSpecificOutput"]["additionalContext"].lower()
                self.assertIn("again", note, "the note does not say the device was booted again")
                self.assertNotIn("decision", out)
                # sim-boot-is-verified: the record goes in before the check, and a retry adds a second line.
                records = self.read_records()
                self.assertEqual([r["udid"] for r in records], [U1, U1])
                self.assertEqual([str(r["launchd_pid"]) for r in records], ["2001", "3001"],
                                 "want the old pid first and the retry boot's pid newest")

    def test_a_failed_check_after_the_retry_blocks_and_names_the_device(self):
        cases = {"bootstatus": ("bootstatus", [1, 1]), "screenshot": ("screenshot", [1, 1]),
                 "bootstatus then screenshot": None}
        for label, spec in cases.items():
            with self.subTest(label):
                self.tearDown_state()
                self.ps_with_retry_pid()
                if spec:
                    self.plan(*spec[:1], *spec[1])
                else:
                    self.plan("bootstatus", 1)
                    self.plan("screenshot", 0, 1)
                result = self.boot_and_check()
                out = json.loads(result.stdout)
                self.assertEqual(out["decision"], "block")
                reason = out["reason"]
                self.assertIn(U1, reason, "the reason does not name the UDID")
                self.assertIn("broken", reason.lower())
                self.assertIn("stop", reason.lower(), "the reason does not say to stop using it")
                self.assertIn("decision sim-boot-is-verified", reason, "the reason does not cite its decision")
                names = [c.split()[0] for c in self.check_calls()]
                self.assertEqual(names.count("shutdown"), 1, "more or fewer than one shutdown")
                self.assertEqual(names.count("boot"), 1, "more or fewer than one boot")
                self.assertNotEqual(names[-1], "shutdown", "the hook shut the device after the fail")
                records = self.read_records()
                self.assertEqual([r["udid"] for r in records], [U1, U1],
                                 "a broken device needs a record line before and after the retry")
                self.assertEqual([str(r["launchd_pid"]) for r in records], ["2001", "3001"],
                                 "want the old pid first and the retry boot's pid newest")

    def test_an_mcp_launch_that_fails_the_check_is_retried(self):
        ti = {"action": "launch", "device": U1}
        self.ps_with_retry_pid()
        self.plan("bootstatus", 1)
        result = self.boot_and_check(tool=MCP, tool_input=ti)
        self.assertIn("additionalContext", json.loads(result.stdout)["hookSpecificOutput"])
        self.assertEqual(self.check_calls().count("shutdown " + U1), 1)

    def test_an_xcodebuild_destination_boot_is_not_checked(self):
        ti = {"command": "xcodebuild test -scheme App -destination id=" + U1}
        self.plan("bootstatus", 1, 1)
        self.plan("screenshot", 1, 1)
        result = self.boot_and_check(tool_input=ti)
        self.assertEqual(result.stdout, "", "an xcodebuild boot was checked and blocked")
        self.assertEqual(self.check_calls(), [], "an xcodebuild boot ran the check")
        self.assertEqual([r["udid"] for r in self.read_records()], [U1])

    def test_a_device_booted_before_the_call_is_not_checked(self):
        self.plan("bootstatus", 1, 1)
        self.pre(self.ON)
        result = self.post_raw(self.ON)
        self.assertEqual(result.stdout, "")
        self.assertEqual(self.check_calls(), [], "an owner-booted device was checked")

    def test_a_mixed_call_checks_only_the_device_simctl_boot_names(self):
        U2_ON = (U2, "Idle Air", "Booted", TYPE_AIR)
        U2_OFF = (U2, "Idle Air", "Shutdown", TYPE_AIR)
        ti = {"command": "xcrun simctl boot %s && xcodebuild test -scheme App -destination id=%s"
                         % (U1, U2)}
        self.plan("bootstatus", 1, 1)  # a check of U2 would fail and retry
        self.pre(self.OFF + [U2_OFF], tool_input=ti)
        self.post_raw(self.ON + [U2_ON], tool_input=ti)
        self.assertEqual([c for c in self.check_calls() if U2 in c], [],
                         "the xcodebuild-booted device was checked or retried")
        self.assertEqual(sorted({r["udid"] for r in self.read_records()}), sorted([U1, U2]),
                         "both booted devices must still be recorded")

    def test_the_boot_runs_even_when_the_retry_shutdown_fails(self):
        self.ps_with_retry_pid()
        self.plan("bootstatus", 1)
        self.plan("shutdown", 1)
        result = self.boot_and_check()
        names = [c.split()[0] for c in self.check_calls()]
        self.assertEqual([n for n in names if n in ("shutdown", "boot")], ["shutdown", "boot"],
                         "boot did not run after a failed shutdown")
        self.assertIn("again", json.loads(result.stdout)["hookSpecificOutput"]
                      ["additionalContext"].lower())

    # ------------------------------------------------------------------ frame judge in the check (sim-boot-is-verified)
    # A screenshot that exits 0 still fails the check when its frame is one colour. The fake xcrun copies
    # the fixture named by the frame plan (line N for the Nth screenshot call, live after the list) to the
    # screenshot's file, and logs its name.

    def test_a_black_frame_with_exit_0_is_retried_once(self):
        self.ps_with_retry_pid()
        self.script_frames("black", "live")
        self.boot_and_check()
        self.assertEqual(self.frames_written()[:1], ["black"], "the black frame did not reach the screenshot path")
        names = [c.split()[0] for c in self.check_calls()]
        self.assertEqual(names, ["bootstatus", "screenshot", "shutdown", "boot", "bootstatus", "screenshot"],
                         "a uniform black frame that exited 0 was not retried once")

    def test_a_live_frame_on_the_retry_gives_the_pass_note(self):
        self.ps_with_retry_pid()
        self.script_frames("black", "live")
        result = self.boot_and_check()
        self.assertTrue(result.stdout, "the black frame was not followed by a pass note")
        out = json.loads(result.stdout)
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "PostToolUse")
        self.assertIn("again", out["hookSpecificOutput"]["additionalContext"].lower(),
                      "the pass note does not say the device was booted again")
        self.assertNotIn("decision", out, "a retry with a live frame was blocked")

    def test_a_blank_white_frame_with_exit_0_is_retried_once(self):
        self.ps_with_retry_pid()
        self.script_frames("blank", "live")
        self.boot_and_check()
        self.assertEqual(self.frames_written()[:1], ["blank"], "the white frame did not reach the screenshot path")
        names = [c.split()[0] for c in self.check_calls()]
        self.assertEqual(names, ["bootstatus", "screenshot", "shutdown", "boot", "bootstatus", "screenshot"],
                         "a uniform white frame that exited 0 was not retried once")

    def test_a_black_frame_on_the_retry_too_blocks_the_device(self):
        self.ps_with_retry_pid()
        self.script_frames("black", "black")
        result = self.boot_and_check()
        self.assertTrue(result.stdout, "two black frames wrote no block decision")
        out = json.loads(result.stdout)
        self.assertEqual(out.get("decision"), "block", "two black frames did not block the device")
        self.assertIn(U1, out["reason"], "the block reason does not name the UDID")
        self.assertIn("broken", out["reason"].lower(), "the block reason does not call the device broken")
        names = [c.split()[0] for c in self.check_calls()]
        self.assertEqual(names.count("shutdown"), 1, "the retry did not shut the device down exactly once")

    def test_an_undecodable_frame_is_a_pass_and_is_not_retried(self):
        self.script_frames("undecodable")
        result = self.boot_and_check()
        self.assertEqual(self.frames_written()[:1], ["undecodable"],
                         "the undecodable frame did not reach the screenshot path")
        self.assertEqual(result.stdout, "", "an undecodable frame wrote to stdout")
        self.assertEqual(self.check_calls(), ["bootstatus " + U1, "screenshot " + U1],
                         "an undecodable frame was retried")

    # ------------------------------------------------------------------ record mode (`--record <UDID>`)
    # bin/sim-test calls the hook as `sim_boot_record.py --record <UDID>` after its own boot. The mode
    # appends one record line for that device, read with the same devices() and launchd() as the hook
    # mode. It prints nothing and exits 0 in every case.

    def run_record(self, udid):
        """The hook in record mode for UDID, with an empty stdin, as bin/sim-test runs it."""
        env = dict(os.environ)
        env["CLAUDE_CONFIG_DIR"] = self.cfg
        env["PATH"] = self.bin + os.pathsep + os.path.dirname(sys.executable)
        return subprocess.run([sys.executable, HOOK, "--record", udid], input="",
                              capture_output=True, text=True, env=env, timeout=60)

    def test_record_mode_appends_one_line_for_the_named_device(self):
        self.set_devices([(U1, "Idle Pro", "Booted", TYPE_PRO)])
        result = self.run_record(U1)
        self.assertEqual(result.returncode, 0, "--record exited non-zero: %s" % result.stderr[:300])
        self.assertEqual(result.stdout, "", "--record wrote to stdout: %r" % result.stdout[:200])
        records = self.read_records()
        self.assertEqual(len(records), 1, "--record appended %d lines, want one" % len(records))
        record = records[0]
        self.assertEqual(sorted(record), sorted(["udid", "name", "deviceTypeIdentifier", "runtime",
                                                 "at", "launchd_pid", "launchd_start"]),
                         "the --record line has other fields than the hook's record line")
        self.assertEqual(record["udid"], U1)
        self.assertEqual(record["name"], "Idle Pro")
        self.assertEqual(record["deviceTypeIdentifier"], TYPE_PRO)
        self.assertEqual(record["runtime"], RT)
        self.assertEqual(record["launchd_pid"], LAUNCHD_PIDS[U1])
        self.assertEqual(record["launchd_start"], LSTART)
        time.strptime(record["at"], "%Y-%m-%dT%H:%M:%SZ")  # raises if `at` is not ISO-8601 UTC

    def test_record_mode_names_only_the_device_it_is_given(self):
        self.set_devices([(U1, "Idle Pro", "Booted", TYPE_PRO), (U2, "Idle Air", "Booted", TYPE_AIR)])
        self.assertEqual(self.run_record(U1).returncode, 0)
        self.assertEqual([r["udid"] for r in self.read_records()], [U1],
                         "--record wrote a line for a device it was not given")

    def test_record_mode_writes_nothing_when_no_launchd_sim_names_the_device(self):
        self.write_ps([(str(LAUNCHD_PIDS[U2]), "1", "0", LAUNCHD_CMD + " " + U2)])
        self.set_devices([(U1, "Idle Pro", "Booted", TYPE_PRO)])
        result = self.run_record(U1)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(self.read_records(), [], "a device with no launchd_sim was recorded")

    def test_record_mode_writes_nothing_when_two_launchd_sims_name_the_device(self):
        self.write_ps([(str(LAUNCHD_PIDS[U1]), "1", "0", LAUNCHD_CMD + " " + U1),
                       ("2999", "1", "0", LAUNCHD_CMD + " " + U1)])
        self.set_devices([(U1, "Idle Pro", "Booted", TYPE_PRO)])
        result = self.run_record(U1)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(self.read_records(), [], "an unclear launchd_sim was recorded")

    def test_record_mode_exits_zero_and_writes_nothing_when_the_device_list_is_unreadable(self):
        self.set_devices([], rc=1)
        result = self.run_record(U1)
        self.assertEqual(result.returncode, 0, "--record exited non-zero on an unreadable list")
        self.assertEqual(result.stdout, "")
        self.assertEqual(self.read_records(), [], "a device was recorded from an unreadable list")

    def tearDown_state(self):
        """Reset the fake's logs, plans, flag and records between sub-cases of one test."""
        for path in (self.calls, self.booted_flag, self.records, self.frame_plan_path, self.frame_log):
            if os.path.exists(path):
                os.remove(path)
        for name in os.listdir(self.plans):
            os.remove(os.path.join(self.plans, name))
        shutil.rmtree(self.state, ignore_errors=True)


def load_hook():
    """The hook module, loaded by path and per call, so a missing name fails one case rather than the file."""
    spec = importlib.util.spec_from_file_location("sim_boot_record_under_test", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FrameUniformTests(unittest.TestCase):
    """frame_uniform(path) in hooks/sim_boot_record.py (decision sim-boot-is-verified): True when every pixel is
    one colour, False when not, None when the file cannot be judged. Each case writes its own PNG."""

    def setUp(self):
        self.folder = tempfile.mkdtemp(dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, self.folder, True)

    def judge(self, data):
        """frame_uniform on a file that holds DATA. DATA None: no file at the path."""
        path = os.path.join(self.folder, "frame.png")
        if data is not None:
            with open(path, "wb") as handle:
                handle.write(data)
        judge = getattr(load_hook(), "frame_uniform", None)
        self.assertIsNotNone(judge, "sim_boot_record has no frame_uniform: the frame judge is not built")
        return judge(path)

    def test_uniform_black_rgba_is_uniform(self):
        data = make_png(rows_of(16, 8, BLACK_RGBA), 16, colour_type=6)
        self.assertIs(self.judge(data), True, "a uniform black RGBA frame was not judged uniform")

    def test_uniform_white_rgb_is_uniform(self):
        data = make_png(rows_of(16, 8, WHITE_RGB), 16, colour_type=2)
        self.assertIs(self.judge(data), True, "a uniform white RGB frame was not judged uniform")

    def test_uniform_black_is_uniform_under_each_filter(self):
        for kind in range(5):
            with self.subTest(filter=kind):
                data = make_png(rows_of(16, 8, BLACK_RGBA), 16, colour_type=6, filters=kind)
                self.assertIs(self.judge(data), True, "a uniform black frame was not judged uniform")

    def test_uniform_colour_is_uniform_under_each_filter(self):
        for kind in range(5):
            with self.subTest(filter=kind):
                data = make_png(rows_of(16, 8, COLOUR_RGB), 16, colour_type=2, filters=kind)
                self.assertIs(self.judge(data), True, "a uniform colour frame was not judged uniform")

    def test_uniform_frame_whose_rows_mix_filters_is_uniform(self):
        for pixel, colour_type in ((BLACK_RGBA, 6), (COLOUR_RGB, 2)):
            with self.subTest(colour_type=colour_type):
                data = make_png(rows_of(16, 10, pixel), 16, colour_type=colour_type, filters=[0, 1, 2, 3, 4])
                self.assertIs(self.judge(data), True, "a uniform frame whose rows mix filters was not judged uniform")

    def test_live_frame_is_not_uniform_under_each_filter(self):
        for kind in range(5):
            with self.subTest(filter=kind):
                data = make_png(live_rows(16, 8, 4), 16, colour_type=6, filters=kind)
                self.assertIs(self.judge(data), False, "a live frame with varied pixels was judged uniform")

    def test_a_sub_ramp_with_flat_filtered_bytes_is_not_uniform(self):
        data = make_png(sub_ramp_rows(40, 40, 3, 3), 40, colour_type=2, filters=1)
        self.assertIs(self.judge(data), False,
                      "a Sub-filtered ramp, flat in its filtered bytes but varied in pixels, was judged uniform")

    def test_an_up_ramp_with_flat_filtered_bytes_is_not_uniform(self):
        data = make_png(up_ramp_rows(40, 40, 3, 3), 40, colour_type=2, filters=2)
        self.assertIs(self.judge(data), False,
                      "an Up-filtered ramp, flat in its filtered bytes but varied in pixels, was judged uniform")

    def test_one_pixel_off_by_one_in_the_last_row_is_not_uniform(self):
        rows = with_byte(rows_of(16, 8, WHITE_RGB), 7, 47, 254)  # last row, last byte: 254 among 255s
        data = make_png(rows, 16, colour_type=2, filters=[0, 1, 2, 3, 4])
        self.assertIs(self.judge(data), False, "one pixel off by 1 in the last row was judged uniform")

    def test_one_pixel_off_by_one_in_the_first_row_is_not_uniform(self):
        rows = with_byte(rows_of(16, 8, WHITE_RGB), 0, 0, 254)  # first row, first byte: 254 among 255s
        data = make_png(rows, 16, colour_type=2, filters=[0, 1, 2, 3, 4])
        self.assertIs(self.judge(data), False, "one pixel off by 1 in the first row was judged uniform")

    def test_several_idat_chunks_of_a_uniform_frame_are_joined_and_judged_uniform(self):
        data = make_png(rows_of(16, 8, BLACK_RGBA), 16, colour_type=6, filters=[0, 1, 2, 3, 4], idat_size=3)
        self.assertIs(self.judge(data), True, "a uniform frame split into several IDAT chunks was not judged uniform")

    def test_several_idat_chunks_of_a_live_frame_are_judged_not_uniform(self):
        data = make_png(live_rows(16, 8, 4), 16, colour_type=6, filters=[0, 1, 2, 3, 4], idat_size=3)
        self.assertIs(self.judge(data), False, "a live frame split into several IDAT chunks was judged uniform")

    def test_a_full_size_uniform_frame_is_uniform(self):
        data = make_png(rows_of(390, 844, WHITE_RGB), 390, colour_type=2, filters=[0, 1, 2, 3, 4])
        self.assertIs(self.judge(data), True, "a full-size uniform frame was not judged uniform")

    def test_a_16_bit_frame_is_none(self):
        data = make_png(rows_of(16, 8, b"\x00" * 6), 16, colour_type=2, depth=16)
        self.assertIsNone(self.judge(data), "a 16-bit frame was not left undecided (None)")

    def test_a_palette_frame_is_none(self):
        data = make_png(rows_of(16, 8, b"\x00"), 16, colour_type=3, palette=b"\x00\x00\x00")
        self.assertIsNone(self.judge(data), "a palette frame was not left undecided (None)")

    def test_an_interlaced_frame_is_none(self):
        data = make_png(rows_of(16, 8, BLACK_RGBA), 16, colour_type=6, interlace=1)
        self.assertIsNone(self.judge(data), "an interlaced frame was not left undecided (None)")

    def test_a_truncated_frame_is_none(self):
        data = cut_inside_idat(make_png(rows_of(16, 8, BLACK_RGBA), 16, colour_type=6))
        self.assertIsNone(self.judge(data), "a truncated frame was not left undecided (None)")

    def test_a_file_that_is_not_a_png_is_none(self):
        self.assertIsNone(self.judge(b"this is a text file, not a PNG\n"),
                          "a file that is not a PNG was not left undecided (None)")

    def test_an_empty_file_is_none(self):
        self.assertIsNone(self.judge(b""), "an empty file was not left undecided (None)")

    def test_a_missing_file_is_none(self):
        self.assertIsNone(self.judge(None), "a missing file was not left undecided (None)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
