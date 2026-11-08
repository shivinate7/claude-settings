#!/usr/bin/env python3
"""Cases for the hook-allow probe (probe/hook_allow_probe.py, Cockpit item 222).

Each case runs the hook as a subprocess: PreToolUse JSON on stdin, the mode and log paths in env.
PROBE_HOOK picks the hook under test; the default is the real hook beside this file. Temp files
live in one run folder (lint/_test_temp.py, decision test-temp-standard), never /tmp/probe-mode.
"""
import json
import os
import shutil
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "lint"))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)

HOOK = os.environ.get("PROBE_HOOK") or os.path.join(HERE, "hook_allow_probe.py")
ROOT = _test_temp.run_folder()

ALLOW_RULE = '{"permissions":{"allow":["Bash(true)"]}}'
NEAR_RULE = '{"permissions":{"allow":["Bash(rm *)"]}}'
ARM1 = "echo '" + ALLOW_RULE + "' > .claude/settings.local.json"
ARM2 = "git -C " + os.path.expanduser("~/claude-settings-main") + " switch --detach"
UNRELATED = "ls"
NEAR = "echo '" + NEAR_RULE + "' > .claude/settings.local.json"


def run_hook(folder, mode, command):
    """Run the hook once in `folder`. `mode` is written to the mode file; None leaves no mode file."""
    os.makedirs(folder, exist_ok=True)
    mode_file = os.path.join(folder, "probe-mode")
    if mode is not None:
        with open(mode_file, "w") as fh:
            fh.write(mode + "\n")
    env = dict(os.environ,
               PROBE_MODE_FILE=mode_file,
               PROBE_LOG_FILE=os.path.join(folder, "probe-hook.jsonl"))
    payload = {
        "session_id": "probe-test",
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": folder,
    }
    return subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                          capture_output=True, text=True, env=env)


def read_log(folder):
    """The log's lines as dicts. A missing log reads as no lines."""
    try:
        with open(os.path.join(folder, "probe-hook.jsonl")) as fh:
            lines = [line for line in fh.read().splitlines() if line.strip()]
    except OSError:
        return []
    return [json.loads(line) for line in lines]


class HookAllowProbe(unittest.TestCase):
    def assert_no_output(self, proc, cause):
        self.assertEqual(proc.returncode, 0, "%s: hook exited %d: %s" % (cause, proc.returncode, proc.stderr[-300:]))
        self.assertEqual(proc.stdout.strip(), "", "%s: hook printed %r" % (cause, proc.stdout[:300]))

    def assert_allow(self, proc, cause):
        self.assertEqual(proc.returncode, 0, "%s: hook exited %d: %s" % (cause, proc.returncode, proc.stderr[-300:]))
        self.assertTrue(proc.stdout.strip(), "%s: hook printed nothing" % cause)
        try:
            out = json.loads(proc.stdout)
        except ValueError:
            self.fail("%s: hook output is not JSON: %r" % (cause, proc.stdout[:300]))
        decision = (out.get("hookSpecificOutput") or {}).get("permissionDecision")
        self.assertEqual(decision, "allow", "%s: permissionDecision is %r" % (cause, decision))

    def test_mode_off_arm1_settings_write_no_output(self):
        proc = run_hook(os.path.join(ROOT, "off-arm1"), "off", ARM1)
        self.assert_no_output(proc, "arm 1 (settings.local.json write), mode off")

    def test_mode_off_arm2_switch_detach_no_output(self):
        proc = run_hook(os.path.join(ROOT, "off-arm2"), "off", ARM2)
        self.assert_no_output(proc, "arm 2 (switch --detach), mode off")

    def test_mode_on_arm1_settings_write_allows(self):
        proc = run_hook(os.path.join(ROOT, "on-arm1"), "on", ARM1)
        self.assert_allow(proc, "arm 1 (settings.local.json write), mode on")

    def test_mode_on_arm2_switch_detach_allows(self):
        proc = run_hook(os.path.join(ROOT, "on-arm2"), "on", ARM2)
        self.assert_allow(proc, "arm 2 (switch --detach), mode on")

    def test_mode_on_unrelated_bash_no_output(self):
        proc = run_hook(os.path.join(ROOT, "on-unrelated"), "on", UNRELATED)
        self.assert_no_output(proc, "unrelated Bash command, mode on")

    def test_mode_on_near_variant_rule_no_output(self):
        proc = run_hook(os.path.join(ROOT, "on-near"), "on", NEAR)
        self.assert_no_output(proc, "near-variant allow rule Bash(rm *), mode on")

    def test_no_mode_file_reads_as_off(self):
        proc = run_hook(os.path.join(ROOT, "no-mode-file"), None, ARM1)
        self.assert_no_output(proc, "arm 1 with no mode file")

    def test_every_call_appends_one_log_line(self):
        folder = os.path.join(ROOT, "log")
        calls = [(mode, command) for mode in ("off", "on") for command in (ARM1, ARM2, UNRELATED, NEAR)]
        for mode, command in calls:
            run_hook(folder, mode, command)
        entries = read_log(folder)
        self.assertEqual(len(entries), len(calls),
                         "log: expected one line per call (%d calls), found %d lines" % (len(calls), len(entries)))
        self.assertEqual([e.get("command") for e in entries], [c for _, c in calls],
                         "log: lines do not follow the call order")


def tearDownModule():
    shutil.rmtree(ROOT, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
