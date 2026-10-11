#!/usr/bin/env python3
"""Cases for hooks/sim_boot_record.py, the boot-record hook. Standard library only, `unittest`.

Run it from the repository root:

    python3 hooks/test_sim_boot_record.py -v

Owner ruling 2026-10-10: a hook on Bash and on the simulator MCP control tool records each device
that went shut-down -> booted during the call, in <config>/state/sim-boots.jsonl. The hook runs
for BOTH events of one call: a PreToolUse run snapshots every simulator's state, and the matching
PostToolUse run records the shut-down -> booted changes against that snapshot. A PostToolUse run
with no snapshot records nothing, so a device booted before the call is never recorded.

The contract pinned here (hooks/sim_boot_record.py must match it):
  - the event is read from `hook_event_name`; the hook never blocks: stdout is empty, exit 0.
  - a record line is {"udid", "name", "deviceTypeIdentifier", "runtime", "at", "launchd_pid",
    "launchd_start"}. `at` is ISO-8601 UTC. launchd_pid and launchd_start are the pid and the start
    time of the device's launchd_sim, as `ps` prints them, read when the device is booted.
  - the hook reads `simctl list devices` (a simctl read) only for a Bash call whose command names a
    simulator tool as a whole word (simctl, xcodebuild, xcrun, ...), and for a simulator MCP call
    whose action is `launch`. `export FOO=1`, `swift build` and `expo start` name no simulator tool.
    The fake xcrun counts each run in a log, so the cases count the simctl reads.
  - the snapshot lives under <config>/state/. The cases find it by name-agnostic means: they only
    remove or corrupt files in that folder, never read the snapshot's own name.

Each case runs the hook as Claude Code does: one JSON object on stdin. A fake `xcrun` stands first on
PATH and answers `simctl list devices` from a file the case rewrites between the two events. A fake
`ps` stands there too, with a launchd_sim row for each UDID. Its argv naming `lstart` answers
"PID START" lines when the -o list names pid=, else "START" lines.
No environment seam reaches the hook except CLAUDE_CONFIG_DIR and PATH, which Claude Code sets too.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "sim_boot_record.py")

MCP = "mcp__Claude_Code_iOS_Simulator__control"
RT = "com.apple.CoreSimulator.SimRuntime.iOS-26-0"
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
    """rows: (udid, name, state, deviceTypeIdentifier)."""
    grouped = {RT: [{"udid": u, "name": n, "state": s, "deviceTypeIdentifier": t,
                     "isAvailable": True} for u, n, s, t in rows]}
    return json.dumps({"devices": grouped})


def fake_ps_script(rows, log):
    """A POSIX `ps` for ROWS, (pid, ppid, uid, command), all strings. Each call appends its
    LC_ALL to LOG, so a case can see the locale the hook ran the read under."""
    table = "".join("%s %s %s %s\n" % row for row in rows)
    starts = [(pid, cmd) for pid, _, _, cmd in rows if "launchd_sim" in cmd]
    pid_lines = "".join("%s %s\n" % (pid, LSTART) for pid, _ in starts)
    start_lines = "".join(LSTART + "\n" for _ in starts)
    for text in (table, pid_lines, start_lines):
        assert "'" not in text, "the printf body is single-quoted"
    return ("#!/bin/sh\n"
            "echo \"${LC_ALL-unset}\" >> '" + log + "'\n"
            "case \"$*\" in\n"
            "  *lstart*) case \"$*\" in *pid=*) printf '%s' '" + pid_lines + "' ;;"
            " *) printf '%s' '" + start_lines + "' ;; esac ;;\n"
            "  *) printf '%s' '" + table + "' ;;\n"
            "esac\n")


@unittest.skipIf(not POSIX, "the fake xcrun is a POSIX shell script")
class SimBootRecordTests(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="sim_boot_record_")
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
        # A default `ps` with a launchd_sim row for each UDID, so a boot's record can name one.
        self.write_ps([(str(LAUNCHD_PIDS[u]), "1", "0", LAUNCHD_CMD + " " + u)
                       for u in (U1, U2, U3)])

    # ------------------------------------------------------------------ helpers

    def write_ps(self, rows):
        """Make the fake `ps` answer the process table ROWS, (pid, ppid, uid, command)."""
        path = os.path.join(self.bin, "ps")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(fake_ps_script([("1", "0", "0", "/sbin/launchd")] + list(rows),
                                        self.ps_log))
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
        with open(self.fake, "w", encoding="utf-8") as handle:
            handle.write("#!/bin/sh\necho read >> '" + self.reads + "'\n" + body)
        os.chmod(self.fake, 0o755)

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
