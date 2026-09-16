#!/usr/bin/env python3
"""Fixture tests for ste_gate.py (Stop) and report_gate.py (Stop).

Each test writes a fake transcript JSONL to a temp dir, builds the hook JSON, and runs the
gate as a subprocess, the way Claude Code's Stop hook does. Run with:

    python lint/test_gates.py -v
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
STE_GATE = os.path.join(HERE, "ste_gate.py")
REPORT_GATE = os.path.join(HERE, "report_gate.py")

GOOD_REPORT = "> **Done** BUILT abc123\n> **Next** ship it"


def human(text):
    return {"type": "user", "isSidechain": False, "message": {"role": "user", "content": text}}


def tool_use_msg(name, input_=None):
    block = {"type": "tool_use", "name": name, "input": input_ or {}}
    return {"type": "assistant", "isSidechain": False, "message": {"role": "assistant", "content": [block]}}


def tool_result_msg(tool_use_id="tu_1"):
    block = {"type": "tool_result", "tool_use_id": tool_use_id, "content": "ok"}
    return {"type": "user", "isSidechain": False, "message": {"role": "user", "content": [block]}}


def assistant_text(text):
    return {"type": "assistant", "isSidechain": False,
            "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}


def write_transcript(records, tmpdir, name="transcript.jsonl"):
    path = os.path.join(tmpdir, name)
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")
    return path


def run_gate(gate, hook, raw_stdin=None):
    stdin_text = raw_stdin if raw_stdin is not None else json.dumps(hook)
    run = subprocess.run(
        [sys.executable, gate],
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=15,
    )
    return run


class ReportGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def hook_for(self, path, stop_hook_active=False):
        return {
            "hook_event_name": "Stop",
            "transcript_path": path,
            "stop_hook_active": stop_hook_active,
        }

    def test_01_landed_git_commit_good_report_passes(self):
        records = [
            human("do the task"),
            tool_use_msg("Bash", {"command": "git commit -m x"}),
            tool_result_msg(),
            assistant_text(GOOD_REPORT),
        ]
        path = write_transcript(records, self.tmp.name)
        run = run_gate(REPORT_GATE, self.hook_for(path))
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stdout.strip(), "")

    def test_02_landed_no_blockquote_blocks(self):
        records = [
            human("do the task"),
            tool_use_msg("Bash", {"command": "git commit -m x"}),
            tool_result_msg(),
            assistant_text("Done BUILT abc123"),
        ]
        path = write_transcript(records, self.tmp.name)
        run = run_gate(REPORT_GATE, self.hook_for(path))
        self.assertEqual(run.returncode, 0)
        out = json.loads(run.stdout)
        self.assertEqual(out.get("decision"), "block")

    def test_03_landed_code_fence_in_blockquote_blocks(self):
        records = [
            human("do the task"),
            tool_use_msg("Bash", {"command": "git commit -m x"}),
            tool_result_msg(),
            assistant_text("> **Done** BUILT\n> ```\n> code\n> ```"),
        ]
        path = write_transcript(records, self.tmp.name)
        run = run_gate(REPORT_GATE, self.hook_for(path))
        out = json.loads(run.stdout)
        self.assertEqual(out.get("decision"), "block")

    def test_04_landed_labels_out_of_order_blocks(self):
        records = [
            human("do the task"),
            tool_use_msg("Bash", {"command": "git commit -m x"}),
            tool_result_msg(),
            assistant_text("> **Done** BUILT\n> **Next** ship\n> **Deviations** none"),
        ]
        path = write_transcript(records, self.tmp.name)
        run = run_gate(REPORT_GATE, self.hook_for(path))
        out = json.loads(run.stdout)
        self.assertEqual(out.get("decision"), "block")

    def test_05_landed_unknown_label_first_blocks(self):
        records = [
            human("do the task"),
            tool_use_msg("Bash", {"command": "git commit -m x"}),
            tool_result_msg(),
            assistant_text("> **Summary** something"),
        ]
        path = write_transcript(records, self.tmp.name)
        run = run_gate(REPORT_GATE, self.hook_for(path))
        out = json.loads(run.stdout)
        self.assertEqual(out.get("decision"), "block")

    def test_06_landed_via_github_mcp_good_report_passes(self):
        records = [
            human("open a PR"),
            tool_use_msg("mcp__github__create_pull_request", {"title": "x"}),
            tool_result_msg(),
            assistant_text(GOOD_REPORT),
        ]
        path = write_transcript(records, self.tmp.name)
        run = run_gate(REPORT_GATE, self.hook_for(path))
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stdout.strip(), "")

    def test_07_nothing_landed_prose_reply_passes(self):
        records = [
            human("look around"),
            tool_use_msg("Bash", {"command": "ls"}),
            tool_result_msg(),
            assistant_text("Here is what I found, no report needed."),
        ]
        path = write_transcript(records, self.tmp.name)
        run = run_gate(REPORT_GATE, self.hook_for(path))
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stdout.strip(), "")

    def test_08_landed_but_stop_hook_active_passes(self):
        records = [
            human("do the task"),
            tool_use_msg("Bash", {"command": "git commit -m x"}),
            tool_result_msg(),
            assistant_text("Done BUILT abc123"),
        ]
        path = write_transcript(records, self.tmp.name)
        run = run_gate(REPORT_GATE, self.hook_for(path, stop_hook_active=True))
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stdout.strip(), "")

    def test_09_landing_before_last_human_message_passes(self):
        records = [
            human("start"),
            tool_use_msg("Bash", {"command": "git commit -m first"}),
            tool_result_msg("tu_1"),
            human("do more"),
            tool_use_msg("Bash", {"command": "ls"}),
            tool_result_msg("tu_2"),
            assistant_text("no report here"),
        ]
        path = write_transcript(records, self.tmp.name)
        run = run_gate(REPORT_GATE, self.hook_for(path))
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stdout.strip(), "")

    def test_10_garbage_stdin_no_output(self):
        run = run_gate(REPORT_GATE, None, raw_stdin="not json")
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stdout.strip(), "")


class SteGateStopTests(unittest.TestCase):
    def test_11_contraction_warns_no_block(self):
        hook = {
            "hook_event_name": "Stop",
            "stop_hook_active": False,
            "last_assistant_message": "I don't think this needs a rewrite.",
        }
        run = run_gate(STE_GATE, hook)
        self.assertEqual(run.returncode, 0)
        out = json.loads(run.stdout)
        self.assertIn("systemMessage", out)
        self.assertTrue(out["systemMessage"].startswith("STE: "))
        self.assertNotIn("decision", out)

    def test_12_stop_hook_active_no_output(self):
        hook = {
            "hook_event_name": "Stop",
            "stop_hook_active": True,
            "last_assistant_message": "I don't think this needs a rewrite.",
        }
        run = run_gate(STE_GATE, hook)
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
