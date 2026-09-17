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
CONFIG_REPORT = os.path.join(HERE, "..", "hooks", "config_report.py")
MD_SWEEP = os.environ.get("MD_SWEEP_UNDER_TEST") or os.path.join(HERE, "md_sweep.py")

sys.path.insert(0, HERE)
import ste_lint  # noqa: E402

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


def run_gate(gate, hook, raw_stdin=None, env=None):
    stdin_text = raw_stdin if raw_stdin is not None else json.dumps(hook)
    run = subprocess.run(
        [sys.executable, gate],
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=15,
        env=env,
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

    def test_13_valid_json_not_object_no_output(self):
        run = run_gate(REPORT_GATE, None, raw_stdin="[1,2,3]")
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stdout.strip(), "")

    def test_21_merge_base_is_not_a_landing_command_passes(self):
        records = [
            human("check ancestry"),
            tool_use_msg("Bash", {"command": "git merge-base --is-ancestor a b"}),
            tool_result_msg(),
            assistant_text("a is an ancestor of b, no report needed."),
        ]
        path = write_transcript(records, self.tmp.name)
        run = run_gate(REPORT_GATE, self.hook_for(path))
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stdout.strip(), "")

    def test_22_git_merge_no_edit_blocks(self):
        records = [
            human("merge the branch"),
            tool_use_msg("Bash", {"command": "git merge --no-edit feature"}),
            tool_result_msg(),
            assistant_text("Merged feature in."),
        ]
        path = write_transcript(records, self.tmp.name)
        run = run_gate(REPORT_GATE, self.hook_for(path))
        self.assertEqual(run.returncode, 0)
        out = json.loads(run.stdout)
        self.assertEqual(out.get("decision"), "block")

    def test_14_stray_non_object_transcript_line_skipped_still_blocks(self):
        path = os.path.join(self.tmp.name, "transcript.jsonl")
        lines = [
            json.dumps(human("do the task")),
            "5",
            json.dumps(tool_use_msg("Bash", {"command": "git commit -m x"})),
            json.dumps(tool_result_msg()),
            json.dumps(assistant_text("Done BUILT abc123")),
        ]
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        run = run_gate(REPORT_GATE, self.hook_for(path))
        self.assertEqual(run.returncode, 0)
        out = json.loads(run.stdout)
        self.assertEqual(out.get("decision"), "block")


class ConfigReportTests(unittest.TestCase):
    """Decision 7: an allowed project config edit is still reported at turn end."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def hook_for(self, path, stop_hook_active=False):
        return {
            "hook_event_name": "Stop",
            "transcript_path": path,
            "cwd": self.tmp.name,
            "stop_hook_active": stop_hook_active,
        }

    def test_16_hook_edit_after_last_human_names_it(self):
        target = os.path.join(self.tmp.name, ".claude", "hooks", "x.py")
        records = [
            human("edit the project hook"),
            tool_use_msg("Edit", {"file_path": target}),
            tool_result_msg(),
            assistant_text("done"),
        ]
        path = write_transcript(records, self.tmp.name)
        run = run_gate(CONFIG_REPORT, self.hook_for(path))
        self.assertEqual(run.returncode, 0)
        out = json.loads(run.stdout)
        self.assertIn("systemMessage", out)
        self.assertIn(target.replace("\\", "/"), out["systemMessage"].replace("\\", "/"))
        self.assertIn("Name them in the report.", out["systemMessage"])

    def test_17_ordinary_source_edit_no_output(self):
        target = os.path.join(self.tmp.name, "src", "app.py")
        records = [
            human("edit the app"),
            tool_use_msg("Edit", {"file_path": target}),
            tool_result_msg(),
            assistant_text("done"),
        ]
        path = write_transcript(records, self.tmp.name)
        run = run_gate(CONFIG_REPORT, self.hook_for(path))
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stdout.strip(), "")

    def test_19_merge_into_main_after_last_human_names_it(self):
        records = [
            human("merge it"),
            tool_use_msg("Bash", {"command": "gh pr merge 7 --squash"}),
            tool_result_msg(),
            assistant_text("done"),
        ]
        path = write_transcript(records, self.tmp.name)
        run = run_gate(CONFIG_REPORT, self.hook_for(path))
        self.assertEqual(run.returncode, 0)
        out = json.loads(run.stdout)
        self.assertIn("systemMessage", out)
        self.assertIn("Merges into main this turn:", out["systemMessage"])
        self.assertIn("gh pr merge 7 --squash", out["systemMessage"])
        self.assertIn("Name them in the report.", out["systemMessage"])

    def test_18_stop_hook_active_no_output(self):
        target = os.path.join(self.tmp.name, ".claude", "hooks", "x.py")
        records = [
            human("edit the project hook"),
            tool_use_msg("Edit", {"file_path": target}),
            tool_result_msg(),
            assistant_text("done"),
        ]
        path = write_transcript(records, self.tmp.name)
        run = run_gate(CONFIG_REPORT, self.hook_for(path, stop_hook_active=True))
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

    def test_15_valid_json_not_object_no_output(self):
        run = run_gate(STE_GATE, None, raw_stdin="[1,2,3]")
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stdout.strip(), "")


class SentenceSplitBoldTests(unittest.TestCase):
    """A sentence end inside bold or italic markers still splits (claude-settings patch)."""

    def lint(self, text):
        config = dict(ste_lint.DEFAULT_CONFIG)
        linter = ste_lint.Linter(config)
        return linter.check_text("t.md", text)

    def test_19_bold_split_sentences_each_under_limit_no_ste001(self):
        text = (
            "**First short sentence.** Second short sentence that alone is well "
            "under the limit for this test case and it stays clear plain short "
            "words here.\n"
        )
        # Each sentence alone is under the 25-word descriptive budget. Joined as
        # one sentence (the pre-patch behavior), the word count would exceed it.
        findings = self.lint(text)
        codes = [f.code for f in findings]
        self.assertNotIn("STE001", codes)

    def test_20_plain_thirty_word_sentence_still_ste001(self):
        words = ["word"] * 30
        text = " ".join(words).capitalize() + ".\n"
        findings = self.lint(text)
        codes = [f.code for f in findings]
        self.assertIn("STE001", codes)


class MdSweepTests(unittest.TestCase):
    """Fixtures for lint/md_sweep.py (Stop): the markdown sweep that reads this turn's shell writes
    from disk, not from the tool call. Each fixture writes the FILE the shell command would have
    produced, and puts the shell command's text in the transcript, because the sweep judges the
    command text and lints the disk file, and never runs the command itself.
    """

    ERROR_TEXT = "This sentence holds a semicolon; and that trips the STE006 rule.\n"
    CLEAN_TEXT = "This is a short clean sentence.\nHere is one more short clean sentence.\n"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def hook_for(self, path, stop_hook_active=False):
        return {
            "hook_event_name": "Stop",
            "transcript_path": path,
            "cwd": self.tmp.name,
            "stop_hook_active": stop_hook_active,
        }

    def run_sweep(self, cmd, stop_hook_active=False, env=None):
        records = [
            human("write the doc"),
            tool_use_msg("Bash", {"command": cmd}),
            tool_result_msg(),
            assistant_text("done"),
        ]
        path = write_transcript(records, self.tmp.name)
        hook = self.hook_for(path, stop_hook_active=stop_hook_active)
        return run_gate(MD_SWEEP, hook, env=env)

    def test_23_bash_heredoc_error_blocks_and_names_file(self):
        target = os.path.join(self.tmp.name, "notes.md")
        with open(target, "w", encoding="utf-8") as f:
            f.write(self.ERROR_TEXT)
        cmd = "cat <<'EOF' > %s\n%sEOF" % (target, self.ERROR_TEXT)
        run = self.run_sweep(cmd)
        self.assertEqual(run.returncode, 0)
        out = json.loads(run.stdout)
        self.assertEqual(out.get("decision"), "block")
        self.assertIn("notes.md", out.get("reason", ""))
        self.assertIn("STE006", out.get("reason", ""))

    def test_24_sed_i_error_blocks_and_names_file(self):
        target = os.path.join(self.tmp.name, "guide.md")
        with open(target, "w", encoding="utf-8") as f:
            f.write(self.ERROR_TEXT)
        cmd = "sed -i 's/foo/bar/' %s" % target
        run = self.run_sweep(cmd)
        out = json.loads(run.stdout)
        self.assertEqual(out.get("decision"), "block")
        self.assertIn("guide.md", out.get("reason", ""))

    def test_25_redirect_error_blocks_and_names_file(self):
        target = os.path.join(self.tmp.name, "readme_bit.md")
        with open(target, "w", encoding="utf-8") as f:
            f.write(self.ERROR_TEXT)
        cmd = "echo 'This sentence holds a semicolon; here.' > %s" % target
        run = self.run_sweep(cmd)
        out = json.loads(run.stdout)
        self.assertEqual(out.get("decision"), "block")
        self.assertIn("readme_bit.md", out.get("reason", ""))

    def test_26_clean_markdown_via_bash_no_block(self):
        target = os.path.join(self.tmp.name, "clean.md")
        with open(target, "w", encoding="utf-8") as f:
            f.write(self.CLEAN_TEXT)
        cmd = "echo 'clean' > %s" % target
        run = self.run_sweep(cmd)
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stdout.strip(), "")

    def test_27_py_file_via_bash_no_block(self):
        target = os.path.join(self.tmp.name, "script.py")
        with open(target, "w", encoding="utf-8") as f:
            f.write("print('a; b')\n")
        cmd = "echo 'print(1)' > %s" % target
        run = self.run_sweep(cmd)
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stdout.strip(), "")

    def test_28_stop_hook_active_no_block(self):
        target = os.path.join(self.tmp.name, "notes.md")
        with open(target, "w", encoding="utf-8") as f:
            f.write(self.ERROR_TEXT)
        cmd = "cat <<'EOF' > %s\n%sEOF" % (target, self.ERROR_TEXT)
        run = self.run_sweep(cmd, stop_hook_active=True)
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stdout.strip(), "")

    def test_29_named_but_missing_from_disk_no_block(self):
        target = os.path.join(self.tmp.name, "ghost.md")
        cmd = "echo 'x' > %s" % target  # never actually created on disk for this fixture
        run = self.run_sweep(cmd)
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stdout.strip(), "")

    def test_30_exclude_env_stops_the_block(self):
        target = os.path.join(self.tmp.name, "notes.md")
        with open(target, "w", encoding="utf-8") as f:
            f.write(self.ERROR_TEXT)
        cmd = "cat <<'EOF' > %s\n%sEOF" % (target, self.ERROR_TEXT)
        env = dict(os.environ)
        env["MD_SWEEP_EXCLUDE"] = "notes.md"
        run = self.run_sweep(cmd, env=env)
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stdout.strip(), "")

    def test_31_disable_env_stops_the_block(self):
        target = os.path.join(self.tmp.name, "notes.md")
        with open(target, "w", encoding="utf-8") as f:
            f.write(self.ERROR_TEXT)
        cmd = "cat <<'EOF' > %s\n%sEOF" % (target, self.ERROR_TEXT)
        env = dict(os.environ)
        env["MD_SWEEP_DISABLE"] = "1"
        run = self.run_sweep(cmd, env=env)
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stdout.strip(), "")

    # ---------------------------------------------------------- quote-aware split (Task 1)

    def test_32_quoted_semicolon_in_sed_expression_still_blocks(self):
        target = os.path.join(self.tmp.name, "NOTES.md")
        with open(target, "w", encoding="utf-8") as f:
            f.write(self.ERROR_TEXT)
        cmd = "sed -i 's/a;b/c/' %s" % target
        run = self.run_sweep(cmd)
        out = json.loads(run.stdout)
        self.assertEqual(out.get("decision"), "block")
        self.assertIn("NOTES.md", out.get("reason", ""))

    def test_33_quoted_semicolon_in_sed_expression_clean_no_block(self):
        target = os.path.join(self.tmp.name, "NOTES.md")
        with open(target, "w", encoding="utf-8") as f:
            f.write(self.CLEAN_TEXT)
        cmd = "sed -i 's/a;b/c/' %s" % target
        run = self.run_sweep(cmd)
        self.assertEqual(run.stdout.strip(), "")

    # ---------------------------------------------------------- node -e fs writes

    def test_34_node_write_file_sync_error_blocks(self):
        target = os.path.join(self.tmp.name, "notes.md")
        with open(target, "w", encoding="utf-8") as f:
            f.write(self.ERROR_TEXT)
        script = "const fs=require('fs'); fs.writeFileSync('%s', 'x')" % target
        cmd = 'node -e "%s"' % script
        run = self.run_sweep(cmd)
        out = json.loads(run.stdout)
        self.assertEqual(out.get("decision"), "block")
        self.assertIn("notes.md", out.get("reason", ""))

    def test_35_node_write_file_sync_clean_no_block(self):
        target = os.path.join(self.tmp.name, "notes.md")
        with open(target, "w", encoding="utf-8") as f:
            f.write(self.CLEAN_TEXT)
        script = "const fs=require('fs'); fs.writeFileSync('%s', 'x')" % target
        cmd = 'node -e "%s"' % script
        run = self.run_sweep(cmd)
        self.assertEqual(run.stdout.strip(), "")

    def test_36_program_name_in_quoted_grep_arg_is_not_a_write(self):
        target = os.path.join(self.tmp.name, "notes.md")
        with open(target, "w", encoding="utf-8") as f:
            f.write(self.ERROR_TEXT)
        cmd = 'grep -n "fs.writeFileSync" %s' % target
        run = self.run_sweep(cmd)
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stdout.strip(), "")

    # ---------------------------------------------------------- perl -i / perl -e open

    def test_37_perl_inplace_error_blocks(self):
        target = os.path.join(self.tmp.name, "guide.md")
        with open(target, "w", encoding="utf-8") as f:
            f.write(self.ERROR_TEXT)
        cmd = "perl -i -pe 's/foo/bar/' %s" % target
        run = self.run_sweep(cmd)
        out = json.loads(run.stdout)
        self.assertEqual(out.get("decision"), "block")
        self.assertIn("guide.md", out.get("reason", ""))

    def test_38_perl_inplace_clean_no_block(self):
        target = os.path.join(self.tmp.name, "guide.md")
        with open(target, "w", encoding="utf-8") as f:
            f.write(self.CLEAN_TEXT)
        cmd = "perl -i -pe 's/foo/bar/' %s" % target
        run = self.run_sweep(cmd)
        self.assertEqual(run.stdout.strip(), "")

    def test_39_perl_open_for_write_error_blocks(self):
        target = os.path.join(self.tmp.name, "notes.md")
        with open(target, "w", encoding="utf-8") as f:
            f.write(self.ERROR_TEXT)
        script = 'open(FH, ">%s"); print FH "x";' % target
        cmd = "perl -e '%s'" % script
        run = self.run_sweep(cmd)
        out = json.loads(run.stdout)
        self.assertEqual(out.get("decision"), "block")
        self.assertIn("notes.md", out.get("reason", ""))

    def test_40_perl_e_without_open_write_no_block(self):
        target = os.path.join(self.tmp.name, "notes.md")
        with open(target, "w", encoding="utf-8") as f:
            f.write(self.ERROR_TEXT)
        script = 'print "%s\\n";' % target
        cmd = "perl -e '%s'" % script
        run = self.run_sweep(cmd)
        self.assertEqual(run.stdout.strip(), "")

    # ---------------------------------------------------------- ruby -i

    def test_41_ruby_inplace_error_blocks(self):
        target = os.path.join(self.tmp.name, "guide.md")
        with open(target, "w", encoding="utf-8") as f:
            f.write(self.ERROR_TEXT)
        cmd = "ruby -i -pe 's/foo/bar/' %s" % target
        run = self.run_sweep(cmd)
        out = json.loads(run.stdout)
        self.assertEqual(out.get("decision"), "block")
        self.assertIn("guide.md", out.get("reason", ""))

    def test_42_ruby_inplace_clean_no_block(self):
        target = os.path.join(self.tmp.name, "guide.md")
        with open(target, "w", encoding="utf-8") as f:
            f.write(self.CLEAN_TEXT)
        cmd = "ruby -i -pe 's/foo/bar/' %s" % target
        run = self.run_sweep(cmd)
        self.assertEqual(run.stdout.strip(), "")

    # ---------------------------------------------------------- awk / gawk output redirect

    def test_43_awk_program_redirect_error_blocks(self):
        target = os.path.join(self.tmp.name, "notes.md")
        with open(target, "w", encoding="utf-8") as f:
            f.write(self.ERROR_TEXT)
        cmd = 'awk \'{ print > "%s" }\' /dev/null' % target
        run = self.run_sweep(cmd)
        out = json.loads(run.stdout)
        self.assertEqual(out.get("decision"), "block")
        self.assertIn("notes.md", out.get("reason", ""))

    def test_44_awk_program_redirect_clean_no_block(self):
        target = os.path.join(self.tmp.name, "notes.md")
        with open(target, "w", encoding="utf-8") as f:
            f.write(self.CLEAN_TEXT)
        cmd = 'awk \'{ print > "%s" }\' /dev/null' % target
        run = self.run_sweep(cmd)
        self.assertEqual(run.stdout.strip(), "")

    def test_45_gawk_program_redirect_error_blocks(self):
        target = os.path.join(self.tmp.name, "notes.md")
        with open(target, "w", encoding="utf-8") as f:
            f.write(self.ERROR_TEXT)
        cmd = 'gawk \'{ print >> "%s" }\' /dev/null' % target
        run = self.run_sweep(cmd)
        out = json.loads(run.stdout)
        self.assertEqual(out.get("decision"), "block")
        self.assertIn("notes.md", out.get("reason", ""))

    # ---------------------------------------------------------- dd of=

    def test_46_dd_of_error_blocks(self):
        target = os.path.join(self.tmp.name, "notes.md")
        with open(target, "w", encoding="utf-8") as f:
            f.write(self.ERROR_TEXT)
        cmd = "dd if=/dev/zero of=%s bs=1 count=1" % target
        run = self.run_sweep(cmd)
        out = json.loads(run.stdout)
        self.assertEqual(out.get("decision"), "block")
        self.assertIn("notes.md", out.get("reason", ""))

    def test_47_dd_of_clean_no_block(self):
        target = os.path.join(self.tmp.name, "notes.md")
        with open(target, "w", encoding="utf-8") as f:
            f.write(self.CLEAN_TEXT)
        cmd = "dd if=/dev/zero of=%s bs=1 count=1" % target
        run = self.run_sweep(cmd)
        self.assertEqual(run.stdout.strip(), "")

    # ---------------------------------------------------------- python pathlib write

    def test_48_pathlib_write_text_error_blocks(self):
        target = os.path.join(self.tmp.name, "notes.md")
        with open(target, "w", encoding="utf-8") as f:
            f.write(self.ERROR_TEXT)
        script = "from pathlib import Path; Path('%s').write_text('x')" % target
        cmd = 'python3 -c "%s"' % script
        run = self.run_sweep(cmd)
        out = json.loads(run.stdout)
        self.assertEqual(out.get("decision"), "block")
        self.assertIn("notes.md", out.get("reason", ""))

    def test_49_pathlib_open_write_error_blocks(self):
        target = os.path.join(self.tmp.name, "notes.md")
        with open(target, "w", encoding="utf-8") as f:
            f.write(self.ERROR_TEXT)
        script = "from pathlib import Path; Path('%s').open('w').write('x')" % target
        cmd = 'python3 -c "%s"' % script
        run = self.run_sweep(cmd)
        out = json.loads(run.stdout)
        self.assertEqual(out.get("decision"), "block")
        self.assertIn("notes.md", out.get("reason", ""))

    def test_50_pathlib_write_text_clean_no_block(self):
        target = os.path.join(self.tmp.name, "notes.md")
        with open(target, "w", encoding="utf-8") as f:
            f.write(self.CLEAN_TEXT)
        script = "from pathlib import Path; Path('%s').write_text('x')" % target
        cmd = 'python3 -c "%s"' % script
        run = self.run_sweep(cmd)
        self.assertEqual(run.stdout.strip(), "")

    # ---------------------------------------------------------- printf redirect

    def test_51_printf_redirect_error_blocks(self):
        target = os.path.join(self.tmp.name, "notes.md")
        with open(target, "w", encoding="utf-8") as f:
            f.write(self.ERROR_TEXT)
        cmd = "printf 'This sentence holds a semicolon; here.\\n' > %s" % target
        run = self.run_sweep(cmd)
        out = json.loads(run.stdout)
        self.assertEqual(out.get("decision"), "block")
        self.assertIn("notes.md", out.get("reason", ""))

    def test_52_printf_redirect_clean_no_block(self):
        target = os.path.join(self.tmp.name, "notes.md")
        with open(target, "w", encoding="utf-8") as f:
            f.write(self.CLEAN_TEXT)
        cmd = "printf 'clean text\\n' > %s" % target
        run = self.run_sweep(cmd)
        self.assertEqual(run.stdout.strip(), "")

    # ---------------------------------------------------------- variable-held path (out of scope)

    def test_53_variable_held_path_stays_out_of_scope(self):
        target = os.path.join(self.tmp.name, "notes.md")
        with open(target, "w", encoding="utf-8") as f:
            f.write(self.ERROR_TEXT)
        cmd = 'f=%s; sed -i "s/foo/bar/" "$f"' % target
        run = self.run_sweep(cmd)
        # Documented hole: a path only reachable through a shell variable is never seen.
        self.assertEqual(run.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
