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
from datetime import datetime, timedelta, timezone

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

    def test_52_prose_above_report_after_a_question_passes(self):
        records = [
            human("why does it only fire sometimes?"),
            tool_use_msg("Bash", {"command": "git commit -m x"}),
            tool_result_msg(),
            assistant_text("The gate fires on a landing turn only.\n\n" + GOOD_REPORT),
        ]
        path = write_transcript(records, self.tmp.name)
        run = run_gate(REPORT_GATE, self.hook_for(path))
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stdout.strip(), "")

    def test_53_prose_above_report_without_a_question_blocks(self):
        records = [
            human("do the task"),
            tool_use_msg("Bash", {"command": "git commit -m x"}),
            tool_result_msg(),
            assistant_text("Here is some prose.\n\n" + GOOD_REPORT),
        ]
        path = write_transcript(records, self.tmp.name)
        run = run_gate(REPORT_GATE, self.hook_for(path))
        out = json.loads(run.stdout)
        self.assertEqual(out.get("decision"), "block")

    def test_55_colon_inside_the_bold_label_passes(self):
        records = [
            human("do the task"),
            tool_use_msg("Bash", {"command": "git commit -m x"}),
            tool_result_msg(),
            assistant_text("> **Done:** BUILT abc123\n> **Next:** ship it"),
        ]
        path = write_transcript(records, self.tmp.name)
        run = run_gate(REPORT_GATE, self.hook_for(path))
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stdout.strip(), "")

    def test_56_colon_label_out_of_order_still_blocks(self):
        records = [
            human("do the task"),
            tool_use_msg("Bash", {"command": "git commit -m x"}),
            tool_result_msg(),
            assistant_text("> **Done:** BUILT\n> **Next:** ship\n> **Deviations:** none"),
        ]
        path = write_transcript(records, self.tmp.name)
        run = run_gate(REPORT_GATE, self.hook_for(path))
        out = json.loads(run.stdout)
        self.assertEqual(out.get("decision"), "block")

    def test_57_unknown_colon_label_still_blocks(self):
        records = [
            human("do the task"),
            tool_use_msg("Bash", {"command": "git commit -m x"}),
            tool_result_msg(),
            assistant_text("> **Summary:** something"),
        ]
        path = write_transcript(records, self.tmp.name)
        run = run_gate(REPORT_GATE, self.hook_for(path))
        out = json.loads(run.stdout)
        self.assertEqual(out.get("decision"), "block")

    def test_54_prose_below_report_after_a_question_blocks(self):
        records = [
            human("why does it only fire sometimes?"),
            tool_use_msg("Bash", {"command": "git commit -m x"}),
            tool_result_msg(),
            assistant_text(GOOD_REPORT + "\n\nOne more thought."),
        ]
        path = write_transcript(records, self.tmp.name)
        run = run_gate(REPORT_GATE, self.hook_for(path))
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

    # THE UNREADABLE SUBJECT REPORT. The guard allows a discarding git call whose subject it
    # could not read, and logs one `noted`/`subject-unread` line. This hook is where a person
    # still sees it. The log holds LOCAL times and the transcript holds UTC times, so each test
    # builds both stamps for real rather than assuming one zone.
    def _turn(self, log_lines, human_offset_seconds=0):
        """Write a transcript whose last human message carries a UTC stamp, plus a guard.log
        holding `log_lines`, and return (transcript path, environment).
        """
        when = datetime.now(timezone.utc) - timedelta(seconds=human_offset_seconds)
        record = human("do the task")
        record["timestamp"] = when.isoformat().replace("+00:00", "Z")
        records = [record, tool_use_msg("Bash", {"command": "ls"}), tool_result_msg(),
                   assistant_text("done")]
        path = write_transcript(records, self.tmp.name)
        config = os.path.join(self.tmp.name, "cfg")
        os.makedirs(config, exist_ok=True)
        with open(os.path.join(config, "guard.log"), "w", encoding="utf-8") as handle:
            handle.write("".join(line + "\n" for line in log_lines))
        env = dict(os.environ)
        env["CLAUDE_CONFIG_DIR"] = config
        return path, env

    @staticmethod
    def _log_line(rule, decision, matched, age_seconds=0):
        stamp = (datetime.now() - timedelta(seconds=age_seconds)).isoformat(timespec="seconds")
        return "\t".join([stamp, "Bash", decision, rule, matched])

    def test_20_unread_subject_this_turn_is_named(self):
        path, env = self._turn([self._log_line("subject-unread", "noted",
                                               "git reset --hard HEAD")])
        run = run_gate(CONFIG_REPORT, self.hook_for(path), env=env)
        self.assertEqual(run.returncode, 0)
        out = json.loads(run.stdout)
        self.assertIn("could not read the subject", out["systemMessage"])
        self.assertIn("git reset --hard HEAD", out["systemMessage"])
        self.assertIn("Name them in the report.", out["systemMessage"])

    def test_21_unread_subject_from_an_older_turn_is_not_named(self):
        path, env = self._turn(
            [self._log_line("subject-unread", "noted", "git reset --hard HEAD",
                            age_seconds=600)],
            human_offset_seconds=60,
        )
        run = run_gate(CONFIG_REPORT, self.hook_for(path), env=env)
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stdout.strip(), "")

    def test_22_a_refusal_line_is_not_an_unread_subject(self):
        path, env = self._turn([self._log_line("shared-tree", "deny",
                                               "git reset --hard HEAD")])
        run = run_gate(CONFIG_REPORT, self.hook_for(path), env=env)
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
    """Fixtures for lint/md_sweep.py (Stop): the markdown sweep that judges the ACT, not the
    command shape. A file counts when its mtime is newer than the last human message and,
    in a git work tree, it is also dirty against HEAD. Most fixtures below no longer put a
    meaningful command in the transcript, because the new predicate never reads one. Each
    fixture instead controls two things directly: the file's content and mtime on disk, and
    the last human record's `timestamp`.

    Fixtures test_23 through test_53 are the 31 fixtures this class held before the rewrite.
    None were deleted. Each is reworked to exercise the new predicate. Several of the old
    command-shape fixtures collapse onto the same new behavior, so they now vary the FILE
    side instead: filename case, nesting, suffix, and git state. Fixtures test_54 onward are
    new: they close the defect this rewrite targets, and they cover the false-positive risks
    the new predicate opens.
    """

    ERROR_TEXT = "This sentence holds a semicolon; and that trips the STE006 rule.\n"
    CLEAN_TEXT = "This is a short clean sentence.\nHere is one more short clean sentence.\n"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    # ---------------------------------------------------------- shared fixture plumbing

    def hook_for(self, path, stop_hook_active=False):
        return {
            "hook_event_name": "Stop",
            "transcript_path": path,
            "cwd": self.tmp.name,
            "stop_hook_active": stop_hook_active,
        }

    def _iso(self, epoch, use_z=True):
        dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
        text = dt.isoformat(timespec="milliseconds")
        return text.replace("+00:00", "Z") if use_z else text

    def _stamp(self, offset_seconds=5.0, use_z=True):
        """An ISO timestamp `offset_seconds` before now. The default, 5 seconds, gives every
        fixture that writes its file first, then calls run_sweep, a wide safety margin over
        real test execution time.
        """
        return self._iso(datetime.now(timezone.utc).timestamp() - offset_seconds, use_z=use_z)

    def _write_md(self, relpath, text, age_seconds=None):
        """Write a file under the fixture directory. `age_seconds`, when given, backdates its
        mtime that many seconds before now, for an "old file" fixture.
        """
        target = os.path.join(self.tmp.name, relpath)
        parent = os.path.dirname(target)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(text)
        if age_seconds is not None:
            when = datetime.now(timezone.utc).timestamp() - age_seconds
            os.utime(target, (when, when))
        return target

    def _init_git(self):
        subprocess.run(["git", "init", "-q"], cwd=self.tmp.name, check=True,
                        capture_output=True, text=True)

    def _git_commit_all(self, message="init"):
        subprocess.run(["git", "add", "-A"], cwd=self.tmp.name, check=True,
                        capture_output=True, text=True)
        subprocess.run(
            ["git", "-c", "user.email=t@example.com", "-c", "user.name=Test",
             "commit", "-q", "-m", message],
            cwd=self.tmp.name, check=True, capture_output=True, text=True,
        )

    def run_sweep(self, offset_seconds=5.0, include_timestamp=True, include_human=True,
                  stamp=None, stop_hook_active=False, env=None, command="true"):
        records = []
        if include_human:
            record = human("write the doc")
            if include_timestamp:
                record["timestamp"] = stamp if stamp is not None else self._stamp(offset_seconds)
            records.append(record)
        records += [
            tool_use_msg("Bash", {"command": command}),
            tool_result_msg(),
            assistant_text("done"),
        ]
        path = write_transcript(records, self.tmp.name)
        hook = self.hook_for(path, stop_hook_active=stop_hook_active)
        return run_gate(MD_SWEEP, hook, env=env)

    def assert_blocks(self, run, *basenames):
        self.assertEqual(run.returncode, 0)
        out = json.loads(run.stdout)
        self.assertEqual(out.get("decision"), "block")
        for name in basenames:
            self.assertIn(name, out.get("reason", ""))

    def assert_no_block(self, run):
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stdout.strip(), "")

    # ---------------------------------------------------------- basic block / no-block, no git

    def test_23_new_error_file_blocks_and_names_it(self):
        self._write_md("notes.md", self.ERROR_TEXT)
        run = self.run_sweep()
        self.assert_blocks(run, "notes.md")
        self.assertIn("STE006", json.loads(run.stdout).get("reason", ""))

    def test_24_second_new_error_file_blocks_and_names_it(self):
        self._write_md("guide.md", self.ERROR_TEXT)
        run = self.run_sweep()
        self.assert_blocks(run, "guide.md")

    def test_25_third_new_error_file_blocks_and_names_it(self):
        self._write_md("readme_bit.md", self.ERROR_TEXT)
        run = self.run_sweep()
        self.assert_blocks(run, "readme_bit.md")

    def test_26_new_clean_markdown_no_block(self):
        self._write_md("clean.md", self.CLEAN_TEXT)
        run = self.run_sweep()
        self.assert_no_block(run)

    def test_27_non_markdown_file_no_block(self):
        # Extension filter still applies: a .py file, however new and however full of
        # semicolons, is never a markdown target.
        self._write_md("script.py", "print('a; b')\n")
        run = self.run_sweep()
        self.assert_no_block(run)

    def test_28_stop_hook_active_no_block(self):
        self._write_md("notes.md", self.ERROR_TEXT)
        run = self.run_sweep(stop_hook_active=True)
        self.assert_no_block(run)

    def test_29_no_markdown_files_at_all_no_block(self):
        # An empty project: the walk finds nothing, so there is nothing to lint.
        run = self.run_sweep()
        self.assert_no_block(run)

    def test_30_exclude_env_stops_the_block(self):
        self._write_md("notes.md", self.ERROR_TEXT)
        env = dict(os.environ)
        env["MD_SWEEP_EXCLUDE"] = "notes.md"
        run = self.run_sweep(env=env)
        self.assert_no_block(run)

    def test_31_disable_env_stops_the_block(self):
        self._write_md("notes.md", self.ERROR_TEXT)
        env = dict(os.environ)
        env["MD_SWEEP_DISABLE"] = "1"
        run = self.run_sweep(env=env)
        self.assert_no_block(run)

    # ---------------------------------------------------------- filename and path shapes

    def test_32_uppercase_filename_error_blocks(self):
        self._write_md("NOTES.md", self.ERROR_TEXT)
        run = self.run_sweep()
        self.assert_blocks(run, "NOTES.md")

    def test_33_uppercase_filename_clean_no_block(self):
        self._write_md("NOTES.md", self.CLEAN_TEXT)
        run = self.run_sweep()
        self.assert_no_block(run)

    def test_34_nested_directory_error_blocks(self):
        # The walk must recurse: a file several directories deep still counts.
        self._write_md(os.path.join("sub", "dir", "notes.md"), self.ERROR_TEXT)
        run = self.run_sweep()
        self.assert_blocks(run, "notes.md")

    def test_35_nested_directory_clean_no_block(self):
        self._write_md(os.path.join("sub", "dir", "notes.md"), self.CLEAN_TEXT)
        run = self.run_sweep()
        self.assert_no_block(run)

    def test_36_old_file_with_error_no_block(self):
        # False-positive risk (1): an error that predates this turn must not block. The file's
        # mtime is set an hour before the human message's own timestamp.
        self._write_md("old.md", self.ERROR_TEXT, age_seconds=3600)
        run = self.run_sweep(offset_seconds=0)
        self.assert_no_block(run)

    def test_37_markdown_suffix_variant_error_blocks(self):
        self._write_md("guide.markdown", self.ERROR_TEXT)
        run = self.run_sweep()
        self.assert_blocks(run, "guide.markdown")

    def test_38_markdown_suffix_variant_clean_no_block(self):
        self._write_md("guide.markdown", self.CLEAN_TEXT)
        run = self.run_sweep()
        self.assert_no_block(run)

    def test_39_mtime_exactly_at_baseline_no_block(self):
        # Boundary: the predicate requires STRICTLY newer. A file stamped to the exact same
        # instant as the human message does not count as this turn's write. The ISO stamp
        # only holds millisecond precision, so the epoch used for the file's own mtime is
        # round-tripped through the same string first, or the two would differ by a
        # sub-millisecond fraction and the file would read as newer.
        stamp = self._stamp(0.0)
        epoch = datetime.fromisoformat(stamp[:-1] + "+00:00").timestamp()
        target = self._write_md("boundary.md", self.ERROR_TEXT)
        os.utime(target, (epoch, epoch))
        run = self.run_sweep(stamp=stamp)
        self.assert_no_block(run)

    def test_40_no_human_message_in_transcript_no_block_no_crash(self):
        self._write_md("notes.md", self.ERROR_TEXT)
        run = self.run_sweep(include_human=False)
        self.assert_no_block(run)

    # ---------------------------------------------------------- git dirty filter

    def test_41_git_untracked_new_file_error_blocks(self):
        self._init_git()
        self._write_md("README.md", self.CLEAN_TEXT)
        self._git_commit_all()
        self._write_md("notes.md", self.ERROR_TEXT)  # untracked, this turn
        run = self.run_sweep()
        self.assert_blocks(run, "notes.md")

    def test_42_git_untracked_new_file_clean_no_block(self):
        self._init_git()
        self._write_md("README.md", self.CLEAN_TEXT)
        self._git_commit_all()
        self._write_md("more.md", self.CLEAN_TEXT)
        run = self.run_sweep()
        self.assert_no_block(run)

    def test_43_git_mtime_new_but_clean_against_head_no_block(self):
        # False-positive risk (2), a real git init fixture. HEAD already holds the error. The
        # file is rewritten to the SAME content, as a `git pull` would leave a file's mtime
        # touched with no content change. It must not block: it is not dirty.
        self._init_git()
        self._write_md("notes.md", self.ERROR_TEXT)
        self._git_commit_all()
        self._write_md("notes.md", self.ERROR_TEXT)  # mtime refreshed, content unchanged
        run = self.run_sweep()
        self.assert_no_block(run)

    def test_44_git_tracked_file_modified_this_turn_blocks(self):
        self._init_git()
        self._write_md("notes.md", self.CLEAN_TEXT)
        self._git_commit_all()
        self._write_md("notes.md", self.ERROR_TEXT)  # edited this turn, now dirty
        run = self.run_sweep()
        self.assert_blocks(run, "notes.md")

    def test_45_symlink_outside_project_is_not_linted(self):
        with tempfile.TemporaryDirectory() as outside:
            real = os.path.join(outside, "external.md")
            with open(real, "w", encoding="utf-8") as f:
                f.write(self.ERROR_TEXT)
            link = os.path.join(self.tmp.name, "outside.md")
            os.symlink(real, link)
            run = self.run_sweep()
            self.assert_no_block(run)

    def test_46_rewritten_back_to_head_content_no_block(self):
        # Documented hole: HEAD already holds the error. This turn edits the file away and
        # then back to the exact original text. The final content matches HEAD, so the git
        # filter drops it, even though the file WAS touched this turn.
        self._init_git()
        self._write_md("notes.md", self.ERROR_TEXT)
        self._git_commit_all()
        self._write_md("notes.md", self.CLEAN_TEXT)  # mid-turn edit
        self._write_md("notes.md", self.ERROR_TEXT)  # undone, back to HEAD's own text
        run = self.run_sweep()
        self.assert_no_block(run)

    def test_47_tracked_file_deleted_this_turn_no_block_no_crash(self):
        # git ls-files --cached still names a tracked path after it is deleted from disk. The
        # walk must not crash reading its mtime.
        self._init_git()
        target = self._write_md("notes.md", self.CLEAN_TEXT)
        self._git_commit_all()
        os.remove(target)
        run = self.run_sweep()
        self.assert_no_block(run)

    # ---------------------------------------------------------- multi-file, case, and parsing

    def test_48_multiple_files_names_only_the_erroring_one(self):
        self._write_md("bad.md", self.ERROR_TEXT)
        self._write_md("good.md", self.CLEAN_TEXT)
        run = self.run_sweep()
        out = json.loads(run.stdout)
        self.assertEqual(out.get("decision"), "block")
        self.assertIn("bad.md", out["reason"])
        self.assertNotIn("good.md", out["reason"])

    def test_49_uppercase_extension_error_blocks(self):
        self._write_md("notes.MD", self.ERROR_TEXT)
        run = self.run_sweep()
        self.assert_blocks(run, "notes.MD")

    def test_50_unreadable_file_no_block_no_crash(self):
        target = self._write_md("locked.md", self.ERROR_TEXT)
        os.chmod(target, 0o000)
        try:
            if os.access(target, os.R_OK):
                self.skipTest("running with a privilege that ignores file permissions")
            run = self.run_sweep()
            self.assert_no_block(run)
        finally:
            os.chmod(target, 0o644)

    def test_51_timestamp_with_utc_offset_instead_of_z_still_parses(self):
        self._write_md("notes.md", self.ERROR_TEXT)
        run = self.run_sweep(stamp=self._stamp(5.0, use_z=False))
        self.assert_blocks(run, "notes.md")

    def test_52_unparseable_timestamp_no_block_no_crash(self):
        # False-positive risk (3), the garbage-string sibling of the missing-field case:
        # a value that fails to parse gives no baseline either.
        self._write_md("notes.md", self.ERROR_TEXT)
        run = self.run_sweep(stamp="not-a-timestamp-at-all")
        self.assert_no_block(run)

    def test_53_shell_command_text_is_irrelevant_to_the_predicate(self):
        # This used to be "a variable-held path stays out of scope," the one documented hole
        # of the OLD, shape-matching predicate. The new predicate never reads command text at
        # all, so an unparseable, made-up, or blank command string changes nothing: the file
        # on disk still blocks.
        self._write_md("notes.md", self.ERROR_TEXT)
        run = self.run_sweep(command="$( totally not shell syntax << )")
        self.assert_blocks(run, "notes.md")

    # ---------------------------------------------------------- the defect this rewrite closes

    def test_54_python_script_not_dash_c_writes_markdown_error_blocks(self):
        # THE DEFECT: `python3 gen.py` has no `-c` string for the old hook to read. The new
        # predicate does not care what ran, only that the file changed.
        self._write_md("gen.md", self.ERROR_TEXT)
        run = self.run_sweep(command="python3 gen.py")
        self.assert_blocks(run, "gen.md")

    def test_55_bash_script_writes_markdown_error_blocks(self):
        self._write_md("sh.md", self.ERROR_TEXT)
        run = self.run_sweep(command="bash gen.sh")
        self.assert_blocks(run, "sh.md")

    def test_56_arbitrary_unlisted_program_writes_markdown_error_blocks(self):
        # `make` was never on any shape list the old hook could have matched.
        self._write_md(os.path.join("docs", "OUTPUT.md"), self.ERROR_TEXT)
        run = self.run_sweep(command="make docs")
        self.assert_blocks(run, "OUTPUT.md")

    # ---------------------------------------------------------- false-positive risk (3)

    def test_57_human_message_without_timestamp_field_no_block_no_crash(self):
        # `human()` does not set a `timestamp` field on its own. This is exactly the shape a
        # real transcript takes when the field this predicate needs is absent.
        self._write_md("notes.md", self.ERROR_TEXT)
        run = self.run_sweep(include_timestamp=False)
        self.assert_no_block(run)

    def test_58_broken_git_dir_inside_real_work_tree_no_block(self):
        # A real work tree, `.git` present on disk, but every git subprocess call fails: a
        # broken `GIT_DIR` reproduces a stale `index.lock` or any other git-side failure. The
        # file is clean against HEAD, with a freshly touched mtime, so it must not block
        # whether git works or not. Before the fix this branch widened to a plain mtime-only
        # walk on git failure, and a clean-but-new file wrongly blocked.
        self._init_git()
        self._write_md("notes.md", self.ERROR_TEXT)
        self._git_commit_all()
        self._write_md("notes.md", self.ERROR_TEXT)  # mtime refreshed, content unchanged
        env = dict(os.environ)
        env["GIT_DIR"] = os.path.join(self.tmp.name, "definitely-missing", ".git")
        run = self.run_sweep(env=env)
        self.assert_no_block(run)


if __name__ == "__main__":
    unittest.main()
