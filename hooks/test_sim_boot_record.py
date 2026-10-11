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
  - a record line is {"udid", "name", "deviceTypeIdentifier", "runtime", "at"}, `at` ISO-8601 UTC.
  - the snapshot lives under <config>/state/. The cases find it by name-agnostic means: they only
    remove or corrupt files in that folder, never read the snapshot's own name.

Each case runs the hook as Claude Code does: one JSON object on stdin. A fake `xcrun` stands first on
PATH and answers `simctl list devices` from a file the case rewrites between the two events.
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

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "sim_boot_record.py")

MCP = "mcp__Claude_Code_iOS_Simulator__control"
RT = "com.apple.CoreSimulator.SimRuntime.iOS-26-0"
TYPE_PRO = "com.apple.CoreSimulator.SimDeviceType.iPhone-17-Pro"
TYPE_AIR = "com.apple.CoreSimulator.SimDeviceType.iPad-Air"
U1 = "1A2B3C4D-0000-4000-8000-000000000101"
U2 = "1A2B3C4D-0000-4000-8000-000000000102"
U3 = "1A2B3C4D-0000-4000-8000-000000000103"
POSIX = not sys.platform.startswith("win")


def devices_json(rows):
    """rows: (udid, name, state, deviceTypeIdentifier)."""
    grouped = {RT: [{"udid": u, "name": n, "state": s, "deviceTypeIdentifier": t,
                     "isAvailable": True} for u, n, s, t in rows]}
    return json.dumps({"devices": grouped})


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
        self.records = os.path.join(self.state, "sim-boots.jsonl")

    # ------------------------------------------------------------------ helpers

    def set_devices(self, rows, rc=0):
        """Make the fake xcrun answer the device list ROWS, or fail with RC."""
        if rc:
            body = "exit %d\n" % rc
        else:
            text = devices_json(rows)
            assert "'" not in text, "the printf body is single-quoted"
            body = "printf '%s' '" + text + "'\n"
        with open(self.fake, "w", encoding="utf-8") as handle:
            handle.write("#!/bin/sh\n" + body)
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
        self.pre([(U1, "Idle Pro", "Shutdown", TYPE_PRO), (U2, "Idle Air", "Shutdown", TYPE_AIR),
                  (U3, "Already Up", "Booted", TYPE_PRO)])
        self.post([(U1, "Idle Pro", "Booted", TYPE_PRO), (U2, "Idle Air", "Booted", TYPE_AIR),
                   (U3, "Already Up", "Booted", TYPE_PRO)])
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
