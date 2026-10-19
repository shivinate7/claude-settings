#!/usr/bin/env python3
"""Fixture tests for ste_gate.py (Stop) and report_gate.py (Stop).

Each test writes a fake transcript JSONL to a temp dir, builds the hook JSON, and runs the
gate as a subprocess, the way Claude Code's Stop hook does. Run with:

    python lint/test_gates.py -v
"""
import errno
import glob
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
STE_GATE = os.path.join(HERE, "ste_gate.py")
REPORT_GATE = os.path.join(HERE, "report_gate.py")
HOOKS = os.path.join(HERE, "..", "hooks")
MD_SWEEP = os.environ.get("MD_SWEEP_UNDER_TEST") or os.path.join(HERE, "md_sweep.py")

sys.path.insert(0, HERE)
import ste_lint  # noqa: E402
from _transcript import format_finding, landed_work  # noqa: E402

GOOD_REPORT = "> **Done** BUILT abc123\n> **Next** ship it"

# Isolation. Every spawned gate and sweep inherits this process's environment (env=None, or a copy
# of os.environ). Point CLAUDE_CONFIG_DIR at a temporary folder for the whole module, so no test
# appends to the user's guard.log. tearDownModule restores the value it found. A test that sets its
# own folder (gl_env, the config report) still wins. Also imported by lint/test_ste_autofix.py.
_ISOLATION = {}


def setUpModule():
    _ISOLATION["dir"] = tempfile.TemporaryDirectory()
    _ISOLATION["prev"] = os.environ.get("CLAUDE_CONFIG_DIR")  # None means unset
    os.environ["CLAUDE_CONFIG_DIR"] = _ISOLATION["dir"].name


def tearDownModule():
    prev = _ISOLATION.pop("prev")
    if prev is None:
        os.environ.pop("CLAUDE_CONFIG_DIR", None)
    else:
        os.environ["CLAUDE_CONFIG_DIR"] = prev
    _ISOLATION.pop("dir").cleanup()


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


# The config report is a section of hooks/decision_watch.py.
# This runs just that section, in a fresh process like the hook, so a case never reaches the git
# status and model judgment `decision_watch.run` makes. It prints what `main` would print for it.
CONFIG_REPORT_CODE = (
    "import json, sys; sys.path.insert(0, %r); import decision_watch; "
    "message = decision_watch.config_report(json.load(sys.stdin)); "
    "print(json.dumps({'systemMessage': message}) if message else '')" % HOOKS
)


def run_config_report(hook, env=None):
    return subprocess.run([sys.executable, "-c", CONFIG_REPORT_CODE], input=json.dumps(hook),
                          capture_output=True, text=True, timeout=15, env=env)


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
        rows = [
            # Catches: a landed turn with a good report is blocked.
            GOOD_REPORT,
            # Catches: a colon inside a bold label is read as a bad label.
            "> **Done:** BUILT abc123\n> **Next:** ship it",
        ]
        for text in rows:
            with self.subTest(text=text), tempfile.TemporaryDirectory() as tmp:
                records = [
                    human("do the task"),
                    tool_use_msg("Bash", {"command": "git commit -m x"}),
                    tool_result_msg(),
                    assistant_text(text),
                ]
                path = write_transcript(records, tmp)
                run = run_gate(REPORT_GATE, self.hook_for(path))
                self.assertEqual(run.returncode, 0)
                self.assertEqual(run.stdout.strip(), "")

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
        rows = [
            # Catches: labels out of order in a landing turn pass as a report.
            "> **Done** BUILT\n> **Next** ship\n> **Deviations** none",
            # Catches: the same order check misses colon labels.
            "> **Done:** BUILT\n> **Next:** ship\n> **Deviations:** none",
        ]
        for text in rows:
            with self.subTest(text=text), tempfile.TemporaryDirectory() as tmp:
                records = [
                    human("do the task"),
                    tool_use_msg("Bash", {"command": "git commit -m x"}),
                    tool_result_msg(),
                    assistant_text(text),
                ]
                path = write_transcript(records, tmp)
                run = run_gate(REPORT_GATE, self.hook_for(path))
                out = json.loads(run.stdout)
                self.assertEqual(out.get("decision"), "block")

    def test_05_landed_unknown_label_first_blocks(self):
        rows = [
            # Catches: an unknown label first in a landing turn passes as a report.
            "> **Summary** something",
            # Catches: the same check misses an unknown colon label.
            "> **Summary:** something",
        ]
        for text in rows:
            with self.subTest(text=text), tempfile.TemporaryDirectory() as tmp:
                records = [
                    human("do the task"),
                    tool_use_msg("Bash", {"command": "git commit -m x"}),
                    tool_result_msg(),
                    assistant_text(text),
                ]
                path = write_transcript(records, tmp)
                run = run_gate(REPORT_GATE, self.hook_for(path))
                out = json.loads(run.stdout)
                self.assertEqual(out.get("decision"), "block")

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

    def test_10_garbage_stdin_no_output(self):
        rows = [
            # Catches: unparseable stdin crashes the gate.
            "not json",
            # Catches: valid JSON that is not an object crashes the gate.
            "[1,2,3]",
        ]
        for raw in rows:
            with self.subTest(raw=raw):
                run = run_gate(REPORT_GATE, None, raw_stdin=raw)
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
        rows = [
            # Catches: prose above a good report after a question blocks it.
            ("why does it only fire sometimes?",
             "The gate fires on a landing turn only.\n\n" + GOOD_REPORT),
            # Catches: prose above a good report with no question blocks it.
            ("do the task", "Here is some prose.\n\n" + GOOD_REPORT),
        ]
        for prompt, text in rows:
            with self.subTest(prompt=prompt), tempfile.TemporaryDirectory() as tmp:
                records = [
                    human(prompt),
                    tool_use_msg("Bash", {"command": "git commit -m x"}),
                    tool_result_msg(),
                    assistant_text(text),
                ]
                path = write_transcript(records, tmp)
                run = run_gate(REPORT_GATE, self.hook_for(path))
                self.assertEqual(run.returncode, 0)
                self.assertEqual(run.stdout.strip(), "")

    def test_58_quoted_git_commit_in_probe_list_passes(self):
        # A read-only Bash call quoting a probe list, 'git commit -q -m x' 'git push --quiet',
        # landed nothing, so the gate must not demand a report. The words sit inside single
        # quotes, never run as a command.
        rows = [
            # Catches: a quoted probe list is read as a landing command.
            (
                "check the guard against a probe list",
                "grep -n \"'git commit -q -m x' 'git push --quiet'\" hooks/guard.py",
                "Found the probe list in the test fixtures, no report needed.",
            ),
            # Catches: git merge-base is read as a landing command.
            (
                "check ancestry",
                "git merge-base --is-ancestor a b",
                "a is an ancestor of b, no report needed.",
            ),
            # Catches: a quoted git -C commit inside echo is read as a landing command.
            (
                "show the reproduction command",
                "echo 'git -C /path commit'",
                "That command is only printed, no report needed.",
            ),
        ]
        for prompt, command, text in rows:
            with self.subTest(command=command), tempfile.TemporaryDirectory() as tmp:
                records = [
                    human(prompt),
                    tool_use_msg("Bash", {"command": command}),
                    tool_result_msg(),
                    assistant_text(text),
                ]
                path = write_transcript(records, tmp)
                run = run_gate(REPORT_GATE, self.hook_for(path))
                self.assertEqual(run.returncode, 0)
                self.assertEqual(run.stdout.strip(), "")

    def test_59_heredoc_body_naming_git_merge_passes(self):
        records = [
            human("write a note about merging"),
            tool_use_msg("Bash", {
                "command": "cat <<'EOF' > notes.txt\nremember to git merge later\nEOF",
            }),
            tool_result_msg(),
            assistant_text("Wrote the note, no report needed."),
        ]
        path = write_transcript(records, self.tmp.name)
        run = run_gate(REPORT_GATE, self.hook_for(path))
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stdout.strip(), "")

    def test_60_real_git_commit_blocks(self):
        rows = [
            # Catches: a real git commit with no report is not blocked.
            "Committed.",
            # Catches: a report line with no blockquote is not blocked.
            "Done BUILT abc123",
        ]
        for text in rows:
            with self.subTest(text=text), tempfile.TemporaryDirectory() as tmp:
                records = [
                    human("land the fix"),
                    tool_use_msg("Bash", {"command": "git commit -m x"}),
                    tool_result_msg(),
                    assistant_text(text),
                ]
                path = write_transcript(records, tmp)
                run = run_gate(REPORT_GATE, self.hook_for(path))
                self.assertEqual(run.returncode, 0)
                out = json.loads(run.stdout)
                self.assertEqual(out.get("decision"), "block")

    def test_61_sudo_git_push_blocks(self):
        records = [
            human("push the branch"),
            tool_use_msg("Bash", {"command": "sudo git push"}),
            tool_result_msg(),
            assistant_text("Pushed."),
        ]
        path = write_transcript(records, self.tmp.name)
        run = run_gate(REPORT_GATE, self.hook_for(path))
        out = json.loads(run.stdout)
        self.assertEqual(out.get("decision"), "block")

    def test_62_git_commit_in_an_earlier_turn_passes(self):
        # Pin: already correct before this fix. A landing in an earlier turn must not
        # demand a report on a later turn that did nothing itself.
        rows = [
            # Catches: a landing in an earlier turn blocks a later turn that only reads.
            [
                human("land it"),
                tool_use_msg("Bash", {"command": "git commit -m first"}),
                tool_result_msg("tu_1"),
                human("what does the log show now"),
                tool_use_msg("Bash", {"command": "git log -1"}),
                tool_result_msg("tu_2"),
                assistant_text("The last commit is `first`, no report needed."),
            ],
            # Catches: a landing before the last human message blocks the later turn.
            [
                human("start"),
                tool_use_msg("Bash", {"command": "git commit -m first"}),
                tool_result_msg("tu_1"),
                human("do more"),
                tool_use_msg("Bash", {"command": "ls"}),
                tool_result_msg("tu_2"),
                assistant_text("no report here"),
            ],
        ]
        for i, records in enumerate(rows):
            with self.subTest(row=i), tempfile.TemporaryDirectory() as tmp:
                path = write_transcript(records, tmp)
                run = run_gate(REPORT_GATE, self.hook_for(path))
                self.assertEqual(run.returncode, 0)
                self.assertEqual(run.stdout.strip(), "")

    def test_63_git_dash_c_commit_blocks(self):
        # Regression: `-C <dir>` is a pre-subcommand option that takes a value. A predicate
        # that requires the subcommand to be `git`'s own literal next token misses this and
        # lets a real landing through unreported, a false negative worse than the false
        # positive this fix set out to remove.
        records = [
            human("commit from another checkout"),
            tool_use_msg("Bash", {"command": "git -C /some/path commit -m x"}),
            tool_result_msg(),
            assistant_text("Committed."),
        ]
        path = write_transcript(records, self.tmp.name)
        run = run_gate(REPORT_GATE, self.hook_for(path))
        out = json.loads(run.stdout)
        self.assertEqual(out.get("decision"), "block")

    def test_64_git_dash_c_push_blocks(self):
        records = [
            human("push from another checkout"),
            tool_use_msg("Bash", {"command": "git -C /some/path push"}),
            tool_result_msg(),
            assistant_text("Pushed."),
        ]
        path = write_transcript(records, self.tmp.name)
        run = run_gate(REPORT_GATE, self.hook_for(path))
        out = json.loads(run.stdout)
        self.assertEqual(out.get("decision"), "block")

    def test_65_git_dash_dash_git_dir_commit_blocks(self):
        records = [
            human("commit against an explicit git dir"),
            tool_use_msg("Bash", {"command": "git --git-dir=/x/.git commit -m y"}),
            tool_result_msg(),
            assistant_text("Committed."),
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

    def test_67_every_github_landing_tool_with_no_report_blocks(self):
        # Pinned by hand, not read from report_gate.LANDING_TOOLS: an emptied set must fail here.
        # Catches: a GitHub landing tool with no report is not blocked.
        for tool in ("mcp__github__merge_pull_request", "mcp__github__create_pull_request",
                     "mcp__github__push_files", "mcp__github__create_or_update_file"):
            with self.subTest(tool=tool), tempfile.TemporaryDirectory() as tmp:
                records = [
                    human("land it"),
                    tool_use_msg(tool, {"title": "x"}),
                    tool_result_msg(),
                    assistant_text("Landed it."),
                ]
                path = write_transcript(records, tmp)
                run = run_gate(REPORT_GATE, self.hook_for(path))
                self.assertEqual(run.returncode, 0)
                self.assertEqual(json.loads(run.stdout).get("decision"), "block")
        # Catches: a GitHub landing with a good report is blocked.
        with self.subTest(tool="good report"), tempfile.TemporaryDirectory() as tmp:
            records = [
                human("open a PR"),
                tool_use_msg("mcp__github__create_pull_request", {"title": "x"}),
                tool_result_msg(),
                assistant_text(GOOD_REPORT),
            ]
            path = write_transcript(records, tmp)
            run = run_gate(REPORT_GATE, self.hook_for(path))
            self.assertEqual(run.returncode, 0)
            self.assertEqual(run.stdout.strip(), "")

    def test_68_first_label_not_done_blocks(self):
        records = [
            human("do the task"),
            tool_use_msg("Bash", {"command": "git commit -m x"}),
            tool_result_msg(),
            assistant_text("> **Deviations** none\n> **Next** ship it"),
        ]
        path = write_transcript(records, self.tmp.name)
        run = run_gate(REPORT_GATE, self.hook_for(path))
        self.assertEqual(json.loads(run.stdout).get("decision"), "block")

    def test_69_event_other_than_stop_never_blocks(self):
        records = [
            human("do the task"),
            tool_use_msg("Bash", {"command": "git commit -m x"}),
            tool_result_msg(),
            assistant_text("Done BUILT abc123"),
        ]
        path = write_transcript(records, self.tmp.name)
        for event in ("SubagentStop", "PreToolUse", "SessionEnd"):
            hook = self.hook_for(path)
            hook["hook_event_name"] = event
            run = run_gate(REPORT_GATE, hook)
            self.assertEqual(run.returncode, 0, event)
            self.assertEqual(run.stdout.strip(), "", event)


class DoneFormatAndCiteTests(unittest.TestCase):
    """reports-done-format and speak-cite-id-plus-gloss, both in report_gate.py's Stop hook."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def verdict(self, reply):
        records = [
            human("do the task"),
            tool_use_msg("Bash", {"command": "git commit -m x"}),
            tool_result_msg(),
            assistant_text(reply),
        ]
        path = write_transcript(records, self.tmp.name)
        hook = {"hook_event_name": "Stop", "transcript_path": path, "stop_hook_active": False}
        run = run_gate(REPORT_GATE, hook)
        self.assertEqual(run.returncode, 0)
        return json.loads(run.stdout) if run.stdout.strip() else None

    def assert_blocked(self, reply, needle):
        out = self.verdict(reply)
        self.assertIsNotNone(out, reply)
        self.assertEqual(out.get("decision"), "block")
        self.assertIn(needle, out["reason"])

    def assert_allowed(self, reply):
        self.assertIsNone(self.verdict(reply), reply)

    # reports-done-format
    def test_df_red_done_without_kind_blocks(self):
        self.assert_blocked("> **Done** fixed it in abc123\n> **Next** none", "BUILT, RECORDED, or OTHER")

    def test_df_red_done_without_ref_blocks(self):
        self.assert_blocked("> **Done** BUILT the gate\n> **Next** none", "BUILT, RECORDED, or OTHER")

    def test_df_red_one_bullet_lacks_ref_blocks(self):
        rows = [
            # Catches: a RECORDED bullet with no ref passes.
            ("> **Done**\n> - BUILT gate, PR #5\n> - RECORDED the ruling\n> **Next** none",
             "RECORDED the ruling"),
            # Catches: a bullet with no kind word passes.
            ("> **Done**\n> - swept the stale branches\n> **Next** none", "swept the stale"),
            # Catches: a top bullet after sub-bullets is not checked.
            ("> **Done**\n> - BUILT gate, PR #5\n>   - detail\n> - RECORDED ruling\n> **Next** none",
             "RECORDED ruling"),
            # Catches: a lead-in line with a kind word hides a bullet with no ref.
            ("> **Done** BUILT it:\n> - BUILT gate, PR #5\n> **Next** none", "BUILT it"),
        ]
        for reply, needle in rows:
            with self.subTest(reply=reply):
                self.assert_blocked(reply, needle)

    def test_df_allowed_other_needs_no_ref(self):
        self.assert_allowed("> **Done**\n> - BUILT gate, PR #5\n> - OTHER swept the stale branches\n> **Next** none")

    def test_df_allowed_inline_with_pr(self):
        self.assert_allowed("> **Done** BUILT the gate, PR #226\n> **Next** none")

    def test_df_allowed_bullets_with_sha_and_pr_url(self):
        self.assert_allowed(
            "> **Done**\n> - BUILT gate, abc1234\n"
            "> - RECORDED ruling, https://github.com/o/r/pull/12\n> **Next** none")

    def test_df_false_alarm_ref_on_wrapped_line_passes(self):
        self.assert_allowed("> **Done**\n> - BUILT the gate and\n>   its tests, commit abc1234\n> **Next** none")

    def test_df_false_alarm_deviations_text_not_read_as_done(self):
        self.assert_allowed("> **Done** BUILT gate, PR #226\n> **Deviations** none of the kind words here")

    # speak-cite-id-plus-gloss
    def test_cite_red_bare_d_id_blocks(self):
        rows = [
            # Catches: a bare D-id in prose after "Per" passes.
            ("Per D12 this is fine.\n\n> **Done** BUILT gate, PR #226\n> **Next** none", "'D12'"),
            # Catches: a bare D-id inside the report body passes.
            ("> **Done** BUILT gate, PR #226\n> **Next** follow D258 next", "'D258'"),
            # Catches: a gloss-like phrase after a bare D-id hides the id.
            ("Per D12 and more.\n\n> **Done** BUILT gate, PR #226\n> **Next** none", "'D12'"),
        ]
        for reply, needle in rows:
            with self.subTest(reply=reply):
                self.assert_blocked(reply, needle)

    def test_cite_red_bare_decision_number_blocks(self):
        self.assert_blocked("See decision 136.\n\n> **Done** BUILT gate, PR #226\n> **Next** none", "decision 136")

    def test_cite_allowed_id_plus_gloss(self):
        rows = [
            # Catches: false alarm on an id followed by its gloss.
            "Per D12, short titles for records, this holds.\n\n> **Done** BUILT gate, PR #226\n> **Next** none",
            # Catches: false alarm on a gloss in parentheses before the id.
            "Short titles for records (D12) hold.\n\n> **Done** BUILT gate, PR #226\n> **Next** none",
        ]
        for reply in rows:
            with self.subTest(reply=reply):
                self.assert_allowed(reply)

    def test_cite_false_alarm_pr_link_sha_and_version(self):
        self.assert_allowed(
            "Merged https://github.com/o/r/pull/218 and [D12](https://x/y), sha d1234567890abcdef, "
            "version v1.2.3, decision 1.2 notes, and PR #218.\n\n"
            "> **Done** BUILT gate, PR #218\n> **Next** none")

    def test_cite_false_alarm_code_span_and_path(self):
        self.assert_allowed(
            "The heading `## D012` is refused, see decisions/D258-slug.md.\n\n"
            "> **Done** BUILT gate, PR #226\n> **Next** none")

    def test_cite_false_alarm_not_a_report_turn(self):
        records = [human("what is D12?"), assistant_text("D12 is a record.")]
        path = write_transcript(records, self.tmp.name)
        hook = {"hook_event_name": "Stop", "transcript_path": path, "stop_hook_active": False}
        self.assertEqual(run_gate(REPORT_GATE, hook).stdout.strip(), "")

    # review fixes
    def test_df_red_facade_is_not_a_sha(self):
        self.assert_blocked("> **Done** BUILT facade\n> **Next** none", "BUILT facade")

    def test_df_allowed_sub_bullets_are_details(self):
        self.assert_allowed(
            "> **Done**\n> - BUILT gate, PR #5\n>   - touched the parser\n>   - no ref here\n> **Next** none")

    def test_df_allowed_lead_in_text_with_bullets_is_not_an_item(self):
        self.assert_allowed("> **Done** two items:\n> - BUILT gate, PR #5\n> - OTHER swept, abc1234\n> **Next** none")

    def test_cite_allowed_more_gloss_shapes(self):
        for lead in ("D12 = short titles for records", "D12 -- short titles for records",
                     "D12 says short titles win", "Short titles ruling, D12"):
            self.assert_allowed("Per " + lead + " here.\n\n> **Done** BUILT gate, PR #226\n> **Next** none")

    def test_cite_false_alarm_cell_range_and_vitamin(self):
        self.assert_allowed("Sum A1:D12 and take vitamin D3 daily, or D12:F20.\n\n"
                            "> **Done** BUILT gate, PR #226\n> **Next** none")

    def test_cite_and_done_block_once_with_both_reasons(self):
        out = self.verdict("Per D12.\n\n> **Done** BUILT gate\n> **Next** none")
        self.assertIn("BUILT, RECORDED, or OTHER", out["reason"])
        self.assertIn("'D12'", out["reason"])

    def test_df_cite_quiet_on_rewrite(self):
        records = [human("x"), tool_use_msg("Bash", {"command": "git commit -m x"}), tool_result_msg(),
                   assistant_text("Per D12.\n\n> **Done** BUILT gate\n> **Next** none")]
        path = write_transcript(records, self.tmp.name)
        hook = {"hook_event_name": "Stop", "transcript_path": path, "stop_hook_active": True}
        self.assertEqual(run_gate(REPORT_GATE, hook).stdout.strip(), "")


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
        run = run_config_report(self.hook_for(path))
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
        run = run_config_report(self.hook_for(path))
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
        run = run_config_report(self.hook_for(path), env=env)
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
        run = run_config_report(self.hook_for(path), env=env)
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stdout.strip(), "")

    def test_22_a_refusal_line_is_not_an_unread_subject(self):
        path, env = self._turn([self._log_line("shared-tree", "deny",
                                               "git reset --hard HEAD")])
        run = run_config_report(self.hook_for(path), env=env)
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stdout.strip(), "")

    def test_19_merge_into_main_after_last_human_names_it_by_pr_number(self):
        # The report gate is a CHECK now: when
        # the reply's own report block does not already name the merge, it fires, by PR
        # number, never by the raw command line.
        rows = [
            # Catches: a merge the report does not name is not named by PR number.
            ("gh pr merge 7 --squash", "> **Done** shipped it", "#7"),
            # Catches: a merge with no report block is not named.
            ("gh pr merge 7 --squash", "done", "#7"),
        ]
        for command, text, number in rows:
            with self.subTest(command=command, text=text):
                records = [
                    human("merge it"),
                    tool_use_msg("Bash", {"command": command}),
                    tool_result_msg(),
                    assistant_text(text),
                ]
                path = write_transcript(records, self.tmp.name)
                run = run_config_report(self.hook_for(path))
                self.assertEqual(run.returncode, 0)
                out = json.loads(run.stdout)
                self.assertIn("Merges into main this turn: " + number + ".", out["systemMessage"])
                self.assertNotIn("--squash", out["systemMessage"])
                self.assertIn("Name them in the report.", out["systemMessage"])

    def test_19a_merge_named_in_the_report_stays_silent(self):
        records = [
            human("merge it"),
            tool_use_msg("Bash", {"command": "gh pr merge 75 --squash"}),
            tool_result_msg(),
            assistant_text("> **Done** BUILT, merged #75\n> **Next** none"),
        ]
        path = write_transcript(records, self.tmp.name)
        run = run_config_report(self.hook_for(path))
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stdout.strip(), "")

    def test_19b_merge_omitted_from_the_report_still_fires(self):
        records = [
            human("merge it"),
            tool_use_msg("Bash", {"command": "gh pr merge 75 --squash"}),
            tool_result_msg(),
            assistant_text("> **Done** BUILT the fix\n> **Next** none"),
        ]
        path = write_transcript(records, self.tmp.name)
        run = run_config_report(self.hook_for(path))
        self.assertEqual(run.returncode, 0)
        out = json.loads(run.stdout)
        self.assertIn("Merges into main this turn: #75.", out["systemMessage"])

    def test_19c_chained_gh_pr_view_does_not_ride_along(self):
        records = [
            human("merge it"),
            tool_use_msg("Bash", {
                "command": "gh pr merge 75 --squash ; gh pr view 75 --json state,mergedAt",
            }),
            tool_result_msg(),
            assistant_text("no report yet"),
        ]
        path = write_transcript(records, self.tmp.name)
        run = run_config_report(self.hook_for(path))
        self.assertEqual(run.returncode, 0)
        out = json.loads(run.stdout)
        self.assertIn("Merges into main this turn: #75.", out["systemMessage"])
        self.assertNotIn("gh pr view", out["systemMessage"])
        self.assertNotIn("--json", out["systemMessage"])

    def test_19d_several_merges_in_one_turn_are_all_named(self):
        records = [
            human("merge both"),
            tool_use_msg("Bash", {"command": "gh pr merge 75 --squash"}),
            tool_result_msg(),
            tool_use_msg("Bash", {"command": "gh pr merge 76 --squash"}),
            tool_result_msg(),
            assistant_text("> **Done** merged #75\n> **Next** none"),
        ]
        path = write_transcript(records, self.tmp.name)
        run = run_config_report(self.hook_for(path))
        self.assertEqual(run.returncode, 0)
        out = json.loads(run.stdout)
        # #75 is already named in the report; #76 is not, so only #76 fires.
        self.assertIn("Merges into main this turn: #76.", out["systemMessage"])
        self.assertNotIn("#75", out["systemMessage"])

    def test_19e_unreadable_pr_number_falls_back(self):
        records = [
            human("merge it"),
            tool_use_msg("Bash", {"command": "gh pr merge --auto --squash"}),
            tool_result_msg(),
            assistant_text("no report yet"),
        ]
        path = write_transcript(records, self.tmp.name)
        run = run_config_report(self.hook_for(path))
        self.assertEqual(run.returncode, 0)
        out = json.loads(run.stdout)
        self.assertIn("Merges into main this turn: an unnumbered merge.", out["systemMessage"])

    def test_18_stop_hook_active_no_output(self):
        target = os.path.join(self.tmp.name, ".claude", "hooks", "x.py")
        records = [
            human("edit the project hook"),
            tool_use_msg("Edit", {"file_path": target}),
            tool_result_msg(),
            assistant_text("done"),
        ]
        path = write_transcript(records, self.tmp.name)
        run = run_config_report(self.hook_for(path, stop_hook_active=True))
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stdout.strip(), "")


class RemovedBudgetKeysTests(unittest.TestCase):
    """load_config says so when a config still sets a removed word-budget key (plain-prose-lint)."""

    def load(self, data):
        import contextlib
        import io
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        with open(os.path.join(tmp.name, ".ste.json"), "w", encoding="utf-8") as f:
            json.dump(data, f)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            cfg = ste_lint.load_config(tmp.name)
        return cfg, err.getvalue()

    def test_removed_budget_keys_print_a_notice_each(self):
        for key in ("max_words_procedural", "max_words_descriptive"):
            with self.subTest(key=key):
                _cfg, err = self.load({key: 20})
                self.assertIn(key, err)

    def test_a_current_key_prints_no_notice(self):
        cfg, err = self.load({"max_words": 20})
        self.assertEqual(cfg["max_words"], 20)
        self.assertEqual(err, "")


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
            "words here for every reader who checks the count today.\n"
        )
        # Each sentence alone is under the 30-word budget. Joined as
        # one sentence (the pre-patch behavior), the word count would exceed it.
        findings = self.lint(text)
        codes = [f.code for f in findings]
        self.assertNotIn("STE001", codes)

    def test_20_plain_thirty_one_word_sentence_still_ste001(self):
        words = ["word"] * 31
        text = " ".join(words).capitalize() + ".\n"
        findings = self.lint(text)
        codes = [f.code for f in findings]
        self.assertIn("STE001", codes)


class DecisionGlossCollapseTests(unittest.TestCase):
    """STE001 must not count the words a gloss tool inserts after a citation
    (lint/ste_lint.py build_gloss_pattern). A hermetic fixture folder stands
    in for a real `docs/decisions/`, so this needs no other repository.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.decisions_dir = os.path.join(self.tmp.name, "decisions")
        os.makedirs(self.decisions_dir)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(ste_lint.set_gloss_pattern, None)

    def write_entry(self, filename, id_, title, body="Some prose.\n"):
        with open(os.path.join(self.decisions_dir, filename), "w", encoding="utf-8") as fh:
            fh.write(
                "---\nid: %s\nslug: %s\ntitle: %s\ndate: 2026-01-01\n---\n\n%s"
                % (id_, os.path.splitext(filename)[0], title, body))

    def lint(self, text, use_gloss):
        pattern = ste_lint.build_gloss_pattern(self.decisions_dir) if use_gloss else None
        ste_lint.set_gloss_pattern(pattern)
        linter = ste_lint.Linter(dict(ste_lint.DEFAULT_CONFIG))
        return linter.check_text("t.md", text)

    def test_genuinely_long_sentence_without_citation_still_ste001(self):
        self.write_entry("d-001.md", "D-001", "A short title")
        words = ["word"] * 31
        text = " ".join(words).capitalize() + ".\n"
        codes = [f.code for f in self.lint(text, use_gloss=True)]
        self.assertIn("STE001", codes)

    def test_gloss_only_overflow_is_not_ste001_once_collapsed(self):
        self.write_entry("d-001.md", "D-001", "A title of exactly six whole words")
        text = (
            "The team agreed today that this long sentence about D-001, A title "
            "of exactly six whole words still carries plenty of authored words "
            "for the sentence count today at the main site now.\n")
        uncollapsed = [f.code for f in self.lint(text, use_gloss=False)]
        self.assertIn("STE001", uncollapsed, "fixture sentence was not actually over budget")
        collapsed = [f.code for f in self.lint(text, use_gloss=True)]
        self.assertNotIn("STE001", collapsed)

    def test_wrong_gloss_for_a_real_id_is_not_collapsed(self):
        self.write_entry("d-001.md", "D-001", "A title of exactly six whole words")
        text = (
            "The team agreed today that this long sentence about D-001, some "
            "text that is not entry one real title still carries plenty of "
            "authored words for the count today at the main site now.\n")
        codes = [f.code for f in self.lint(text, use_gloss=True)]
        self.assertIn("STE001", codes)

    def test_reversed_entry_gloss_suffix_also_collapses(self):
        self.write_entry("d-001.md", "D-001", "A title of exactly six whole words")
        self.write_entry("d-002.md", "D-002", "The newer rule", body="reverses: D-001\n")
        text = (
            "The team agreed that this sentence about D-001, A title of exactly six "
            "whole words (reversed by D-002, The newer rule) still carries plenty of "
            "words for the whole crew today and for the late shift too.\n")
        uncollapsed = [f.code for f in self.lint(text, use_gloss=False)]
        self.assertIn("STE001", uncollapsed, "fixture sentence was not actually over budget")
        codes = [f.code for f in self.lint(text, use_gloss=True)]
        self.assertNotIn("STE001", codes)

    def test_heading_gloss_trigger_word_does_not_force_procedural_mode(self):
        # D-448's real title in q_max, "The operator tiers run themselves", carries
        # `run`, a `PROCEDURAL_HEADINGS` trigger word. The sentence limit is one number now, so
        # the mode shows through STE015, a rule that reads procedural text only. The body holds a
        # condition after its instruction: STE015 fires in procedural mode, never in descriptive.
        self.write_entry("d-001.md", "D-001", "The operator tiers run themselves")
        body = (
            "The server brings Postgres up on the machine own loopback interface, "
            "and restarts it when the health check fails here.\n")
        rows = [
            # Catches: a trigger word in the gloss forces procedural mode on a cited heading.
            "## A loopback server is the first target here (D-001, The operator "
            "tiers run themselves)\n\n" + body,
            # Catches: a cited heading with no gloss forces procedural mode.
            "## A loopback server is the first target, and Neon is the second (D-001)\n\n" + body,
            # Catches: a gloss with no trigger word forces procedural mode.
            "## A loopback server is the first target, and Neon is the second "
            "(D-001, The operator tiers manage themselves)\n\n" + body,
        ]
        for text in rows:
            with self.subTest(heading=text.split("\n")[0]):
                codes = [f.code for f in self.lint(text, use_gloss=True)]
                self.assertNotIn("STE015", codes)

    def test_authored_procedural_heading_still_selects_procedural_mode(self):
        # Check 5: the fix must not blind the heuristic to a real procedural heading.
        self.write_entry("d-001.md", "D-001", "The operator tiers run themselves")
        text = (
            "## Running the probes\n\n"
            "The server brings Postgres up on the machine own loopback interface, "
            "and restarts it when the health check fails here.\n")
        codes = [f.code for f in self.lint(text, use_gloss=True)]
        self.assertIn("STE015", codes)

    def test_heading_with_no_citation_is_unaffected(self):
        # Check 7: a heading naming no id behaves exactly as it did before this fix.
        self.write_entry("d-001.md", "D-001", "The operator tiers run themselves")
        text = (
            "## A loopback server is the first target here today\n\n"
            "The server brings Postgres up on the machine own loopback interface, "
            "and restarts it when the health check fails here.\n")
        with_dir = [f.code for f in self.lint(text, use_gloss=True)]
        without_feature = [f.code for f in self.lint(text, use_gloss=False)]
        self.assertEqual(with_dir, without_feature)

    def test_list_item_opening_with_a_citation_stays_descriptive(self):
        # The list-item path reads its first word through `IMPERATIVE_STARTERS`,
        # through `re.match(r"([A-Za-z]+)", body)`. An id such as "D-001" stops that
        # match at its own hyphen. The gloss's words are never reached. No fix was
        # needed here, and this proves it. The body holds a condition after its
        # instruction: STE015 fires in procedural mode only, so a wrong
        # classification would fail this test.
        self.write_entry("d-001.md", "D-001", "The operator tiers run themselves")
        text = (
            "- D-001, The operator tiers run themselves, so nothing else here "
            "needs a restart when the check fails today.\n")
        codes = [f.code for f in self.lint(text, use_gloss=True)]
        self.assertNotIn("STE015", codes)

    def test_pending_entry_has_no_id_to_collapse(self):
        self.write_entry("d-003.md", "pending", "Not stamped yet")
        pattern = ste_lint.build_gloss_pattern(self.decisions_dir)
        self.assertIsNone(pattern)

    def test_absent_decisions_dir_gives_no_pattern(self):
        pattern = ste_lint.build_gloss_pattern(os.path.join(self.tmp.name, "no-such-dir"))
        self.assertIsNone(pattern)


class PromotedRuleTests(unittest.TestCase):
    """Plain-prose lint (decisions/plain-prose-lint.md): a rule either blocks or does not exist,
    and six advisory codes are the one exception. Five rules block: STE001, STE011, STE013,
    STE020, STE021. Six are advisory: STE003, STE007, STE008, STE009, STE015, STE017 are
    warnings that the linter reports and no gate ever blocks on. Each case here proves a rule
    fires at its severity, the thing a table-row edit alone cannot prove. STE006 and STE018 are
    deleted, so they get their own no-finding cases instead, since a deleted rule has no
    severity left to assert.
    """

    def lint(self, text, mode=None):
        config = dict(ste_lint.DEFAULT_CONFIG)
        if mode:
            config["mode"] = mode
        linter = ste_lint.Linter(config)
        return linter.check_text("t.md", text)

    def assert_blocks(self, text, code, mode=None):
        findings = self.lint(text, mode=mode)
        hit = [f for f in findings if f.code == code]
        self.assertTrue(hit, "%s did not fire on %r" % (code, text))
        self.assertEqual(hit[0].severity, "error")

    def assert_advisory(self, text, code, mode=None):
        findings = self.lint(text, mode=mode)
        hit = [f for f in findings if f.code == code]
        self.assertTrue(hit, "%s did not fire on %r" % (code, text))
        self.assertEqual(hit[0].severity, "warning")

    def test_ste003_nominalization_is_advisory(self):
        self.assert_advisory(
            "The team performs a validation of the payload before it saves the record.\n",
            "STE003")

    def test_ste009_phrasal_verb_is_advisory(self):
        self.assert_advisory(
            "Do not set up the server unless you read the runbook first.\n",
            "STE009")

    def test_ste011_bloat_blocks(self):
        self.assert_blocks(
            "In order to fix the bug, read the log file first.\n",
            "STE011")

    def test_ste013_double_negative_blocks(self):
        self.assert_blocks(
            "The setting is not unavailable after the restart finishes.\n",
            "STE013")

    def test_ste015_condition_order_is_advisory(self):
        self.assert_advisory(
            "Restart the service if the health check fails.\n",
            "STE015", mode="procedural")

    def test_ste017_omitted_that_is_advisory(self):
        self.assert_advisory(
            "The linter ensures the file is valid before it runs.\n",
            "STE017")

    def test_ste007_latin_abbreviation_is_advisory(self):
        self.assert_advisory("Send the report via email.\n", "STE007")

    def test_ste008_contraction_is_advisory(self):
        self.assert_advisory("They'd finished the work.\n", "STE008")

    def test_gendered_pronoun_produces_no_finding(self):
        # STE018 is deleted outright, not merely downgraded. A gendered pronoun must raise
        # nothing at all.
        findings = self.lint("When a user signs in, he sees the dashboard.\n")
        self.assertEqual(findings, [])

    def test_semicolon_produces_no_finding(self):
        # STE006 is prose-only, with no mechanism.
        # A semicolon must raise nothing at all.
        findings = self.lint("This sentence uses a semicolon; and continues here.\n")
        self.assertEqual(findings, [])

    def test_semicolon_joined_pair_over_budget_still_trips_ste001(self):
        # split_sentences only splits at . ! ?, never at ;. A semicolon-joined pair
        # that together cross the word budget is one sentence to the counter, and
        # must still trip STE001.
        text = ("w1 w2 w3 w4 w5 w6 w7 w8 w9 w10 w11 w12 w13; "
                "w14 w15 w16 w17 w18 w19 w20 w21 w22 w23 w24 w25 w26 w27 w28 w29 w30 w31 w32.\n")
        findings = self.lint(text)
        self.assertIn("STE001", [f.code for f in findings])

    def test_errors_are_exactly_the_five_blocking_codes_and_warnings_the_six_advisory_ones(self):
        severities = {code: rule.severity for code, rule in ste_lint.RULES.items()}
        self.assertEqual({c for c, s in severities.items() if s == "error"}, set(ERROR_CODES))
        self.assertEqual({c for c, s in severities.items() if s == "warning"}, set(ADVISORY_CODES))
        self.assertEqual(set(severities), set(ERROR_CODES) | set(ADVISORY_CODES), "a rule has no ruling")


# These errors block (plain-prose-lint):
ERROR_CODES = ("STE001", "STE011", "STE013", "STE020", "STE021")
# These six are advisory: reported as warnings, never a deny, a rewrite or a failed run.
ADVISORY_CODES = ("STE003", "STE007", "STE008", "STE009", "STE015", "STE017")
# One input per advisory code. Each holds that code's finding and no error finding, and none is
# text a fixer rewrites, so a failing run comes from the severity alone.
ADVISORY_SAMPLES = {
    "STE003": "The team performs a validation of the payload before it saves the record.\n",
    "STE007": "Send the report via email.\n",
    "STE008": "They'd finished the work.\n",
    "STE009": "Do not set up the server unless you read the runbook first.\n",
    "STE015": "<!-- ste: procedural -->\n\nRestart the service if the health check fails.\n",
    "STE017": "The linter ensures the file is valid before it runs.\n",
}


def plain_words(n):
    """A sentence of exactly n words, one per `word`."""
    return " ".join(["word"] * n).capitalize() + ".\n"


# One input per kept error code: (file suffix, text). None is text the fixer rewrites.
KEPT_SAMPLES = {
    "STE001": (".md", plain_words(31)),
    "STE011": (".md", "In conclusion, the plan works.\n"),
    "STE013": (".md", "This step is not unsafe.\n"),
    "STE020": (".tsx", "const x = <button>Save the file right now</button>;\n"),
    "STE021": (".tsx", "const x = (\n  // ste-disable-next-line STE020\n  <p>Hello.</p>\n);\n"),
}


def run_lint_cli(text, suffix=".md"):
    """ste_lint.py at its defaults on a file holding text: (exit code, parsed JSON)."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "t" + suffix)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        run = subprocess.run([sys.executable, os.path.join(HERE, "ste_lint.py"), "--no-color",
                              "--format", "json", path], capture_output=True, text=True, timeout=15)
    return run.returncode, json.loads(run.stdout)


def run_write_gate(text, name="t.md"):
    """The STE gate on a Write of text to a new file: (process, hookSpecificOutput)."""
    with tempfile.TemporaryDirectory() as d:
        run = run_gate(STE_GATE, {"hook_event_name": "PreToolUse", "tool_name": "Write",
                                  "tool_input": {"file_path": os.path.join(d, name), "content": text}})
    out = json.loads(run.stdout).get("hookSpecificOutput", {}) if run.stdout.strip() else {}
    return run, out


def note_text(run):
    """The note a hook printed, as one string: systemMessage and additionalContext. "" when it
    printed none. Either field shows the note to the reader, so a case does not pick one."""
    if not run.stdout.strip():
        return ""
    out = json.loads(run.stdout)
    parts = (out.get("systemMessage"), (out.get("hookSpecificOutput") or {}).get("additionalContext"))
    return "\n".join(p for p in parts if isinstance(p, str))


class OneSentenceBudgetTests(unittest.TestCase):
    """One sentence budget of 30 words, procedural or descriptive. No separate procedural limit
    of 20 or descriptive limit of 25 exists."""

    def lint(self, text, mode):
        config = dict(ste_lint.DEFAULT_CONFIG)
        config["mode"] = mode
        return ste_lint.Linter(config).check_text("t.md", text)

    def test_b01_26_to_30_words_pass_in_both_modes(self):
        for mode in ("descriptive", "procedural"):
            for n in (26, 30):
                with self.subTest(mode=mode, words=n):
                    self.assertNotIn("STE001", [f.code for f in self.lint(plain_words(n), mode)])

    def test_b02_31_words_error_in_both_modes_and_name_the_limit(self):
        # The message states the one limit.
        for mode in ("descriptive", "procedural"):
            with self.subTest(mode=mode):
                hit = [f for f in self.lint(plain_words(31), mode) if f.code == "STE001"]
                self.assertTrue(hit)
                self.assertEqual(hit[0].severity, "error")
                self.assertRegex(hit[0].message, r"\b30\b")

    def test_b03_the_cli_passes_26_words_in_a_procedural_file_and_a_descriptive_file(self):
        for label, text in (("descriptive", plain_words(26)),
                            ("procedural", "<!-- ste: procedural -->\n\n" + plain_words(26))):
            with self.subTest(file=label):
                rc, data = run_lint_cli(text)
                self.assertEqual(data["findings"], [])
                self.assertEqual(rc, 0)

    def test_b04_the_cli_fails_31_words_in_a_procedural_file_and_a_descriptive_file(self):
        for label, text in (("descriptive", plain_words(31)),
                            ("procedural", "<!-- ste: procedural -->\n\n" + plain_words(31))):
            with self.subTest(file=label):
                rc, data = run_lint_cli(text)
                self.assertEqual([f["code"] for f in data["findings"]], ["STE001"])
                self.assertEqual(rc, 1)

    def test_b05_the_gate_allows_26_words_in_both_modes(self):
        for label, text in (("descriptive", plain_words(26)),
                            ("procedural", "<!-- ste: procedural -->\n\n" + plain_words(26))):
            with self.subTest(file=label):
                run, out = run_write_gate(text)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertNotEqual(out.get("permissionDecision"), "deny", out)

    def test_b06_the_gate_denies_31_words_in_both_modes_and_names_the_limit(self):
        for label, text in (("descriptive", plain_words(31)),
                            ("procedural", "<!-- ste: procedural -->\n\n" + plain_words(31))):
            with self.subTest(file=label):
                run, out = run_write_gate(text)
                self.assertEqual(out.get("permissionDecision"), "deny")
                reason = out["permissionDecisionReason"]
                self.assertIn("31", reason)
                self.assertRegex(reason, r"\b30\b")
                self.assertIn("split", reason.lower())

    def test_b06b_the_deny_note_does_not_call_an_advisory_rule_an_error(self):
        # The deny text ends in a note that lists the rules that block. It names none of the six
        # advisory rules, or the writer is told to fix what no gate checks.
        run, out = run_write_gate(plain_words(31))
        self.assertEqual(out.get("permissionDecision"), "deny")
        note = out["permissionDecisionReason"].lower()
        for phrase in ("nominalization", "latin abbreviation", "contraction", "phrasal verb",
                       "condition order", "omitted 'that'"):
            with self.subTest(phrase=phrase):
                self.assertNotIn(phrase, note)

    # building-scanner-respects-strings: text a scanner can misread must not move the boundary.
    # (label, template, filler words that make the sentence exactly 30 words)
    TRAPS = [
        ("comment openers inside inline code",
         'Run `x = "/* a */"` then `y = "// b"` and `z = "# c"` before you read %s.', 21),
        ("a lone double quote and a JSX-style apostrophe",
         'The 5" pipe and <p>Don\'t</p> stay in the line so please read %s.', 18),
    ]

    def test_b07_scanner_traps_do_not_move_the_boundary(self):
        for label, template, fit in self.TRAPS:
            for filler, flagged in ((fit, False), (fit + 1, True)):
                with self.subTest(trap=label, filler=filler):
                    text = template % " ".join(["word"] * filler)
                    codes = [f.code for f in self.lint(text, "descriptive")]
                    self.assertEqual("STE001" in codes, flagged)

    def test_b08_a_fenced_multiline_template_literal_adds_no_words(self):
        fence = ("```js\nconst s = `line one " + " ".join(["word"] * 20)
                 + "\nline two // keep /* keep */`;\n```\n\n")
        for n, flagged in ((30, False), (31, True)):
            with self.subTest(words=n):
                codes = [f.code for f in self.lint(fence + plain_words(n), "descriptive")]
                self.assertEqual("STE001" in codes, flagged)


class AdvisoryCodesTests(unittest.TestCase):
    """STE003, STE007, STE008, STE009, STE015 and STE017 are reported and never block: not the
    linter's exit code, not the gate, not the sweep, not CI."""

    def test_a01_each_advisory_code_is_reported_as_a_warning_and_the_cli_exits_zero(self):
        for code, text in ADVISORY_SAMPLES.items():
            with self.subTest(code=code):
                rc, data = run_lint_cli(text)
                hits = [f for f in data["findings"] if f["code"] == code]
                self.assertTrue(hits, "%s is not reported: %r" % (code, data["findings"]))
                self.assertEqual({f["severity"] for f in hits}, {"warning"})
                self.assertEqual(data["summary"]["error"], 0, data["findings"])
                self.assertEqual(rc, 0)

    def test_a02_the_gate_notes_an_advisory_code_and_neither_denies_nor_rewrites(self):
        # An advisory must be seen. The write goes ahead, unchanged, with a note that names the code.
        for code, text in ADVISORY_SAMPLES.items():
            with self.subTest(code=code):
                run, out = run_write_gate(text)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertNotIn(out.get("permissionDecision"), ("deny", "ask"), out)
                self.assertNotIn("updatedInput", out)
                self.assertNotIn("decision", json.loads(run.stdout) if run.stdout.strip() else {})
                self.assertIn(code, note_text(run), "no note for %s: %r" % (code, run.stdout))

    def test_a03_all_six_in_one_file_still_pass_the_cli_and_the_gate(self):
        text = "\n".join(ADVISORY_SAMPLES.values())
        rc, data = run_lint_cli(text)
        self.assertEqual({f["code"] for f in data["findings"]} & set(ERROR_CODES), set())
        self.assertEqual(rc, 0)
        run, out = run_write_gate(text)
        self.assertNotEqual(out.get("permissionDecision"), "deny", out)
        self.assertNotIn("updatedInput", out)
        for code in ADVISORY_CODES:
            with self.subTest(code=code):
                self.assertIn(code, note_text(run))

    def test_a05_a_clean_write_prints_nothing(self):
        # Guard: green before and after. A note on clean text is a guard that cries wolf.
        run, out = run_write_gate("This is a short clean sentence.\n")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout.strip(), "")

    def test_a06_a_fix_and_an_advisory_in_one_write_show_both(self):
        # "in order to" is a kept bloat fix. The advisory must not be lost when a fix lands.
        run, out = run_write_gate("Close the valve in order to stop the pump.\n\n"
                                  "They'd finished the work.\n")
        self.assertNotEqual(out.get("permissionDecision"), "deny", out)
        self.assertIn("Close the valve to stop the pump.", json.dumps(out.get("updatedInput", {})))
        self.assertIn("STE008", note_text(run))

    def test_a07_an_edit_notes_only_the_changed_block(self):
        head = "They'd finished the work.\n\nThis is a short clean sentence.\n"
        rows = [
            # Catches: an advisory in an untouched block is noted again on every edit.
            ("This is a short clean sentence.\n", "This is one more short clean sentence.\n", False),
            # Catches: an advisory the edit adds is not noted.
            ("This is a short clean sentence.\n", "Send the report via email.\n", True),
        ]
        for old, new, noted in rows:
            with self.subTest(noted=noted):
                with tempfile.TemporaryDirectory() as d:
                    target = os.path.join(d, "t.md")
                    with open(target, "w", encoding="utf-8") as f:
                        f.write(head)
                    run = run_gate(STE_GATE, {"hook_event_name": "PreToolUse", "tool_name": "Edit",
                                              "tool_input": {"file_path": target, "old_string": old,
                                                             "new_string": new}})
                self.assertEqual(run.returncode, 0, run.stderr)
                out = json.loads(run.stdout).get("hookSpecificOutput", {}) if run.stdout.strip() else {}
                self.assertNotEqual(out.get("permissionDecision"), "deny", out)
                self.assertNotIn("updatedInput", out)
                note = note_text(run)
                self.assertNotIn("STE008", note, "an advisory outside the edit was noted")
                if noted:
                    self.assertIn("STE007", note)
                else:
                    self.assertEqual(note, "")

    def test_a04_the_advisory_samples_are_what_they_say(self):
        # The samples above hold their code and no error code, so the cases are not vacuous.
        for code, text in ADVISORY_SAMPLES.items():
            with self.subTest(code=code):
                codes = [f.code for f in ste_lint.Linter(dict(ste_lint.DEFAULT_CONFIG)).check_text("t.md", text)]
                self.assertIn(code, codes)
                self.assertEqual(set(codes) & set(ERROR_CODES), set())


class KeptErrorCodesTests(unittest.TestCase):
    """STE001, STE011, STE013, STE020 and STE021 are errors."""

    def test_k01_each_kept_code_is_an_error_and_the_cli_exits_one(self):
        for code, (suffix, text) in KEPT_SAMPLES.items():
            with self.subTest(code=code):
                rc, data = run_lint_cli(text, suffix)
                hits = [f for f in data["findings"] if f["code"] == code]
                self.assertTrue(hits, "%s is not reported: %r" % (code, data["findings"]))
                self.assertEqual({f["severity"] for f in hits}, {"error"})
                self.assertEqual(rc, 1)

    def test_k02_the_gate_denies_each_kept_code(self):
        for code, (suffix, text) in KEPT_SAMPLES.items():
            with self.subTest(code=code):
                run, out = run_write_gate(text, "t" + suffix)
                self.assertEqual(out.get("permissionDecision"), "deny", out)
                self.assertIn(code, out["permissionDecisionReason"])
                self.assertNotIn("updatedInput", out)


class MdSweepTests(unittest.TestCase):
    """Fixtures for lint/md_sweep.py (Stop): the markdown sweep that judges the ACT, not the
    command shape. A file counts when its mtime is newer than the last human message and,
    in a git work tree, it is also dirty against HEAD. Most fixtures below no longer put a
    meaningful command in the transcript, because the predicate never reads one. Each
    fixture instead controls two things directly: the file's content and mtime on disk, and
    the last human record's `timestamp`.

    Fixtures test_23 through test_53 vary the FILE side: filename case, nesting, suffix, and
    git state. Fixtures test_54 onward close the command-text defect and cover the
    false-positive risks the predicate opens.
    """

    ERROR_TEXT = "This sentence is not unclean, and that trips the STE013 rule.\n"
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

    def _fresh_root(self):
        """Give the next row its own project folder, so no file from an earlier row is left."""
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        self.tmp = root

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
        rows = [
            # Catches: a new error file is not blocked.
            "notes.md",
            # Catches: a new error file under another name is not blocked.
            "guide.md",
            # Catches: a new error file with a longer name is not blocked.
            "readme_bit.md",
            # Catches: an upper-case file name hides a new error file.
            "NOTES.md",
        ]
        for name in rows:
            with self.subTest(name=name):
                self._fresh_root()
                self._write_md(name, self.ERROR_TEXT)
                run = self.run_sweep()
                self.assert_blocks(run, name)
                self.assertIn("STE013", json.loads(run.stdout).get("reason", ""))

    def test_25b_advisory_findings_never_block_the_sweep_but_are_reported(self):
        # STE003, STE007, STE008, STE009, STE015 and STE017 are warnings. A file holding only
        # these does not block, and the sweep names the code in a note, since an advisory must be seen.
        for code, text in ADVISORY_SAMPLES.items():
            with self.subTest(code=code):
                self._fresh_root()
                self._write_md("notes.md", text)
                run = self.run_sweep()
                self.assertEqual(run.returncode, 0, run.stderr)
                out = json.loads(run.stdout) if run.stdout.strip() else {}
                self.assertNotEqual(out.get("decision"), "block", out)
                self.assertIn(code, note_text(run), "no note for %s: %r" % (code, run.stdout))
                self.assertIn("notes.md", note_text(run))

    def test_25c_the_sweep_note_follows_the_changed_block_only(self):
        head = "They'd finished the work.\n\nThis is a short clean sentence.\n"
        rows = [
            # Catches: an advisory in an untouched block is noted again on every turn.
            ("This is a short clean sentence.\n", "This is one more short clean sentence.\n", False),
            # Catches: an advisory in the changed block is not noted in a git work tree.
            ("They'd finished the work.\n", "They'd finished the job.\n", True),
        ]
        for old, new, noted in rows:
            with self.subTest(noted=noted):
                self._fresh_root()
                self._init_git()
                self._write_md("notes.md", head)
                self._git_commit_all()
                self._write_md("notes.md", head.replace(old, new))
                run = self.run_sweep()
                self.assertEqual(run.returncode, 0, run.stderr)
                out = json.loads(run.stdout) if run.stdout.strip() else {}
                self.assertNotEqual(out.get("decision"), "block", out)
                if noted:
                    self.assertIn("STE008", note_text(run))
                else:
                    self.assertEqual(note_text(run), "")

    def test_26_new_clean_markdown_no_block(self):
        rows = [
            # Catches: a new clean markdown file blocks.
            ("clean.md", self.CLEAN_TEXT),
            # Catches: a project with no markdown file at all blocks.
            (None, None),
            # Catches: an upper-case clean file blocks.
            ("NOTES.md", self.CLEAN_TEXT),
            # Catches: a clean file in a nested folder blocks.
            (os.path.join("sub", "dir", "notes.md"), self.CLEAN_TEXT),
            # Catches: a clean file with the .markdown suffix blocks.
            ("guide.markdown", self.CLEAN_TEXT),
        ]
        for relpath, text in rows:
            with self.subTest(relpath=relpath):
                self._fresh_root()
                if relpath is not None:
                    self._write_md(relpath, text)
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

    def test_34_nested_directory_error_blocks(self):
        # The walk must recurse: a file several directories deep still counts.
        self._write_md(os.path.join("sub", "dir", "notes.md"), self.ERROR_TEXT)
        run = self.run_sweep()
        self.assert_blocks(run, "notes.md")

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
            try:
                os.symlink(real, link)
            except OSError:
                # Windows needs Developer Mode or admin rights to create a symlink. Skip
                # rather than fail, so the suite still runs everywhere else this holds.
                raise unittest.SkipTest(
                    "os.symlink needs elevated privilege or Developer Mode on this platform")
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

    # ---------------------------------------------------------- the defect this rewrite closes

    def test_54_python_script_not_dash_c_writes_markdown_error_blocks(self):
        # THE DEFECT: `python3 gen.py` has no `-c` string for the old hook to read. The new
        # predicate does not care what ran, only that the file changed.
        # Catches: a markdown error written by any command blocks. The predicate never reads
        # the command text, so the command string does not change the result.
        self._write_md("gen.md", self.ERROR_TEXT)
        run = self.run_sweep(command="python3 gen.py")
        self.assert_blocks(run, "gen.md")

    # ---------------------------------------------------------- false-positive risk (3)

    def test_57_human_message_without_timestamp_field_no_block_no_crash(self):
        # `human()` does not set a `timestamp` field on its own. This is exactly the shape a
        # real transcript takes when the field this predicate needs is absent.
        rows = [
            # Catches: a human message with no timestamp field blocks or crashes.
            {"include_timestamp": False},
            # Catches: a transcript with no human message blocks or crashes.
            {"include_human": False},
            # Catches: an unparseable timestamp gives a baseline and blocks.
            {"stamp": "not-a-timestamp-at-all"},
        ]
        for kwargs in rows:
            with self.subTest(**kwargs):
                self._fresh_root()
                self._write_md("notes.md", self.ERROR_TEXT)
                run = self.run_sweep(**kwargs)
                self.assert_no_block(run)

    def test_58_broken_git_dir_inside_real_work_tree_no_block(self):
        # A real work tree, `.git` present on disk, but every git subprocess call fails: a
        # broken `GIT_DIR` reproduces a stale `index.lock` or any other git-side failure. The
        # file is clean against HEAD, with a freshly touched mtime, so it must not block
        # whether git works or not.
        self._init_git()
        self._write_md("notes.md", self.ERROR_TEXT)
        self._git_commit_all()
        self._write_md("notes.md", self.ERROR_TEXT)  # mtime refreshed, content unchanged
        env = dict(os.environ)
        env["GIT_DIR"] = os.path.join(self.tmp.name, "definitely-missing", ".git")
        run = self.run_sweep(env=env)
        self.assert_no_block(run)

    # ---------------------------------------------------------- scoping to changed blocks

    THREE_ERRORS_ONE_CLEAN = (
        "This sentence is not unclean, and that trips the STE013 rule.\n"
        "\n"
        "This one is also not unclean, right here for good measure.\n"
        "\n"
        "A third sentence that is not unclean sits in its own paragraph.\n"
        "\n"
        "This is the clean block that gets edited later.\n"
    )
    THREE_ERRORS_ONE_CLEAN_EDITED = (
        "This sentence is not unclean, and that trips the STE013 rule.\n"
        "\n"
        "This one is also not unclean, right here for good measure.\n"
        "\n"
        "A third sentence that is not unclean sits in its own paragraph.\n"
        "\n"
        "This is the clean block that gets edited later today.\n"
    )

    def test_59_pre_existing_errors_elsewhere_edited_clean_block_no_block(self):
        # THE HEADLINE CASE. HEAD already holds 3 STE013 errors in 3 untouched blocks. This
        # turn edits only the last, clean block, and keeps it clean. Against the pre-scoping
        # gate this blocks and names all 3 pre-existing errors (see redgreen.py in the task
        # report). Scoped to the changed block, it must not block at all.
        self._init_git()
        self._write_md("notes.md", self.THREE_ERRORS_ONE_CLEAN)
        self._git_commit_all()
        self._write_md("notes.md", self.THREE_ERRORS_ONE_CLEAN_EDITED)
        run = self.run_sweep()
        self.assert_no_block(run)

    def test_60_error_introduced_in_the_edited_block_still_blocks(self):
        # THE INVERSE, the one that matters most: an error introduced IN the changed block
        # must still block, even while 3 other, untouched blocks also hold errors.
        edited_with_new_error = self.THREE_ERRORS_ONE_CLEAN.replace(
            "This is the clean block that gets edited later.\n",
            "This is the block that gets edited later, and now is not unclean either.\n",
        )
        self._init_git()
        self._write_md("notes.md", self.THREE_ERRORS_ONE_CLEAN)
        self._git_commit_all()
        self._write_md("notes.md", edited_with_new_error)
        run = self.run_sweep()
        out = json.loads(run.stdout)
        self.assertEqual(out.get("decision"), "block")
        # Only the edited block's own STE013 finding surfaces, at its own line 7. The 3
        # pre-existing errors, in untouched blocks, stay out of scope.
        self.assertIn("line 7: STE013", out["reason"])
        self.assertEqual(out["reason"].count("STE013"), 1)

    def test_61_multiline_sentence_crossing_a_changed_line_still_blocks(self):
        # THE TRAP. A sentence starts on the paragraph's first line (unchanged this turn) and
        # only crosses the 30-word limit because of words added on its THIRD
        # line, the only line this turn's edit touches. A naive line-only filter keeps only
        # the changed line and drops the finding, because the finding is reported at the
        # SENTENCE-START line, which is outside the diff. A block-scoped filter must not.
        head = (
            "w1 w2 w3 w4 w5 w6 w7 w8 w9 w10 w11 w12\n"
            "w13 w14 w15 w16 w17 w18 w19 w20\n"
            "w21 w22 w23.\n"
        )
        edited = (
            "w1 w2 w3 w4 w5 w6 w7 w8 w9 w10 w11 w12\n"
            "w13 w14 w15 w16 w17 w18 w19 w20\n"
            "w21 w22 w23 w24 w25 w26 w27 w28 w29 w30 w31.\n"
        )
        self._init_git()
        self._write_md("sentence.md", head)
        self._git_commit_all()
        self._write_md("sentence.md", edited)
        run = self.run_sweep()
        # A naive line filter (kept only line 3, the changed one) would drop this finding,
        # because ste_lint.py reports STE001 at line 1, where the sentence starts. Assert the
        # actual, wrong-if-naive outcome: it blocks, and names STE001.
        out = json.loads(run.stdout)
        self.assertEqual(out.get("decision"), "block", "a naive per-line filter would pass "
                          "this wrongly, dropping the sentence-start finding")
        self.assertIn("STE001", out["reason"])

    def test_62_different_file_gains_an_error_still_blocks_naming_it(self):
        # A file edited in a clean block must not suppress a genuinely new error in a
        # DIFFERENT file this same turn touched.
        self._init_git()
        self._write_md("scoped.md", self.THREE_ERRORS_ONE_CLEAN)
        self._write_md("other.md", self.CLEAN_TEXT)
        self._git_commit_all()
        self._write_md("scoped.md", self.THREE_ERRORS_ONE_CLEAN_EDITED)  # clean block, no block
        self._write_md("other.md", self.ERROR_TEXT)  # a fresh error, different file
        run = self.run_sweep()
        out = json.loads(run.stdout)
        self.assertEqual(out.get("decision"), "block")
        self.assertIn("other.md", out["reason"])
        self.assertNotIn("scoped.md", out["reason"])

    def test_63_untracked_file_blocks_on_every_pre_existing_error(self):
        # Item 5: an untracked file has no HEAD baseline to diff against, so it lints in
        # full. All 3 STE013 errors in it must surface, not only one.
        self._init_git()
        self._write_md("README.md", self.CLEAN_TEXT)
        self._git_commit_all()
        self._write_md("notes.md", self.THREE_ERRORS_ONE_CLEAN)  # untracked, this turn
        run = self.run_sweep()
        out = json.loads(run.stdout)
        self.assertEqual(out.get("decision"), "block")
        self.assertEqual(out["reason"].count("STE013"), 3)

    def test_64_staged_new_file_blocks_on_every_error(self):
        # Item 4: a brand new file, `git add`-ed but not yet committed, has no content in
        # HEAD at all. `git diff HEAD` reports it as entirely added, so every line is in
        # scope, and every error in it must block.
        self._init_git()
        self._write_md("README.md", self.CLEAN_TEXT)
        self._git_commit_all()
        target = self._write_md("notes.md", self.THREE_ERRORS_ONE_CLEAN)
        subprocess.run(["git", "add", target], cwd=self.tmp.name, check=True,
                        capture_output=True, text=True)
        run = self.run_sweep()
        out = json.loads(run.stdout)
        self.assertEqual(out.get("decision"), "block")
        self.assertEqual(out["reason"].count("STE013"), 3)


class SteGatePreToolUseTests(unittest.TestCase):
    """Fixtures for lint/ste_gate.py's PreToolUse handler: it replays the proposed edit onto
    the file on disk to get the full proposed content, then lints only the blocks that
    differ from disk. See ste_gate.py's own module docstring, "SCOPING TO CHANGED BLOCKS".
    """

    ERROR_LINE = "This sentence is not unclean, and that trips the STE013 rule.\n"
    CLEAN_LINE = "This is a short clean sentence.\n"

    THREE_ERRORS_ONE_CLEAN = (
        "This sentence is not unclean, and that trips the STE013 rule.\n"
        "\n"
        "This one is also not unclean, right here for good measure.\n"
        "\n"
        "A third sentence that is not unclean sits in its own paragraph.\n"
        "\n"
        "This is the clean block that gets edited.\n"
    )

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _write(self, name, text):
        target = os.path.join(self.tmp.name, name)
        with open(target, "w", encoding="utf-8") as f:
            f.write(text)
        return target

    def run_pretooluse(self, tool_name, tool_input):
        hook = {"hook_event_name": "PreToolUse", "tool_name": tool_name, "tool_input": tool_input}
        return run_gate(STE_GATE, hook)

    def assert_denied(self, run):
        self.assertEqual(run.returncode, 0)
        out = json.loads(run.stdout)
        self.assertEqual(out.get("hookSpecificOutput", {}).get("permissionDecision"), "deny")
        return out["hookSpecificOutput"]["permissionDecisionReason"]

    def assert_allowed(self, run):
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stdout.strip(), "")

    # ---------------------------------------------------------- the headline case (item 1)

    def test_59_pre_existing_errors_elsewhere_clean_edit_allowed(self):
        edit = {
            "old_string": "This is the clean block that gets edited.\n",
            "new_string": "This is the clean block that gets edited today.\n",
        }
        rows = [
            # Catches: a clean Edit beside old errors is denied.
            ("Edit", edit),
            # Catches: a clean MultiEdit beside old errors is denied.
            ("MultiEdit", {"edits": [edit]}),
        ]
        for tool, tool_input in rows:
            with self.subTest(tool=tool):
                target = self._write("notes.md", self.THREE_ERRORS_ONE_CLEAN)
                run = self.run_pretooluse(tool, dict(tool_input, file_path=target))
                self.assert_allowed(run)

    # ---------------------------------------------------------- the inverse (item 2)

    def test_60_error_introduced_in_the_edit_still_denied(self):
        target = self._write("notes.md", self.THREE_ERRORS_ONE_CLEAN)
        run = self.run_pretooluse("Edit", {
            "file_path": target,
            "old_string": "This is the clean block that gets edited.\n",
            "new_string": "This block is not unclean, right in the edit itself.\n",
        })
        reason = self.assert_denied(run)
        self.assertIn("STE013", reason)

    # ---------------------------------------------------------- the multi-line trap (item 3)

    def test_61_multiline_sentence_crossing_a_changed_line_still_denied(self):
        head = (
            "w1 w2 w3 w4 w5 w6 w7 w8 w9 w10 w11 w12\n"
            "w13 w14 w15 w16 w17 w18 w19 w20\n"
            "w21 w22 w23.\n"
        )
        target = self._write("sentence.md", head)
        run = self.run_pretooluse("Edit", {
            "file_path": target,
            "old_string": "w21 w22 w23.\n",
            "new_string": "w21 w22 w23 w24 w25 w26 w27 w28 w29 w30 w31.\n",
        })
        reason = self.assert_denied(run)
        self.assertIn("STE001", reason)

    # ---------------------------------------------------------- a brand new file (item 4)

    def test_62_new_file_via_write_denied_on_every_error(self):
        target = os.path.join(self.tmp.name, "new.md")  # never created: Write makes it
        # Three STE013 double negatives the fixer has no fix for, so every one is denied,
        # not rewritten.
        content = ("This first block is not unclean.\n"
                   "\n"
                   "This second block is not unclean too.\n"
                   "\n"
                   "This third block is not unclean as well.\n"
                   "\n"
                   "This is the clean block.\n")
        run = self.run_pretooluse("Write", {"file_path": target, "content": content})
        reason = self.assert_denied(run)
        self.assertEqual(reason.count("STE013"), 3)

    # ---------------------------------------------------------- MultiEdit and Write scoping

    def test_64_write_full_file_clean_change_allowed_despite_other_errors(self):
        target = self._write("notes.md", self.THREE_ERRORS_ONE_CLEAN)
        proposed = self.THREE_ERRORS_ONE_CLEAN.replace(
            "This is the clean block that gets edited.\n",
            "This is the clean block that gets edited today.\n",
        )
        run = self.run_pretooluse("Write", {"file_path": target, "content": proposed})
        self.assert_allowed(run)

    def test_65_write_over_existing_file_still_denies_a_new_error(self):
        target = self._write("notes.md", self.THREE_ERRORS_ONE_CLEAN)
        proposed = self.THREE_ERRORS_ONE_CLEAN.replace(
            "This is the clean block that gets edited.\n",
            "This block is not unclean, right in the edit itself.\n",
        )
        run = self.run_pretooluse("Write", {"file_path": target, "content": proposed})
        reason = self.assert_denied(run)
        self.assertIn("STE013", reason)

    # ---------------------------------------------------------- fail-open on an unresolved edit

    def test_66_old_string_not_found_falls_back_to_linting_the_new_text_in_full(self):
        # The edit cannot be replayed: `old_string` is not in the file on disk. Rather than
        # guess which blocks changed, the gate lints the proposed new_string in full. The
        # STE013 double negative in it must still be caught.
        bad_edit = {
            "old_string": "text that is not actually in the file",
            "new_string": "This new text is not unclean, introduced here.",
        }
        rows = [
            # Catches: an unreplayable Edit is not linted in full.
            ("Edit", bad_edit),
            # Catches: an unreplayable second MultiEdit step lints the old file, not the new text.
            ("MultiEdit", {"edits": [
                {"old_string": "This is the clean block that gets edited.\n",
                 "new_string": "This is the clean block that gets edited today.\n"},
                bad_edit,
            ]}),
        ]
        for tool, tool_input in rows:
            with self.subTest(tool=tool):
                target = self._write("notes.md", self.THREE_ERRORS_ONE_CLEAN)
                run = self.run_pretooluse(tool, dict(tool_input, file_path=target))
                reason = self.assert_denied(run)
                self.assertIn("STE013", reason)

    def test_67b_non_prose_suffix_with_an_ste_error_still_allowed(self):
        # The path guard, not the text, must be what lets this through: the content has a
        # double negative, an STE013 error if the file were linted.
        rows = [
            # Catches: a .txt file with an STE013 error is linted as prose.
            ("notes.txt", "This is not unclear prose the gate should read.\n"),
            # Catches: a .py file is linted as prose.
            ("notes.py", "print('a; b')\n"),
        ]
        for name, content in rows:
            with self.subTest(name=name):
                target = os.path.join(self.tmp.name, name)  # never created: Write makes it
                run = self.run_pretooluse("Write", {"file_path": target, "content": content})
                self.assert_allowed(run)

    def test_67d_ambiguous_edit_is_not_replayed_at_the_first_match(self):
        # old_string sits in two paragraphs, no replace_all. Edit itself refuses that, and
        # the gate lints only new_string (short, clean). Replaying at the first match would
        # join it to the 20 words above and wrongly report a 31-word sentence.
        head = ("w1 w2 w3 w4 w5 w6 w7 w8 w9 w10 w11 w12\n"
                "w13 w14 w15 w16 w17 w18 w19 w20\n"
                "w21 w22 w23.\n\n"
                "Another paragraph.\n\n"
                "w21 w22 w23.\n")
        target = self._write("twice.md", head)
        run = self.run_pretooluse("Edit", {
            "file_path": target,
            "old_string": "w21 w22 w23.\n",
            "new_string": "w21 w22 w23 w24 w25 w26 w27 w28 w29 w30 w31.\n",
        })
        self.assert_allowed(run)


class SourceProseLintTests(unittest.TestCase):
    """Fixtures for ste_lint.py's source-prose mode: `Linter.check_source` lints only
    the comments and docstrings of a .py or .sh file, never its code. The mode is off
    by default; nothing here touches `check_text` or the Markdown path.

    `check_source` picks its extractor from the `path` extension and never reads the
    disk, so these fixtures pass inline text under a plain file name.
    """

    def check(self, path, text):
        config = dict(ste_lint.DEFAULT_CONFIG)
        linter = ste_lint.Linter(config)
        return linter.check_source(path, text)

    def test_68_contraction_in_python_string_literal_not_reported(self):
        text = "CMD = \"can't fix this\"  # no problem on this line\n"
        findings = self.check("sample.py", text)
        self.assertNotIn("STE008", [f.code for f in findings])

    def test_69_contraction_in_python_comment_reported(self):
        text = "# this comment isn't clean and that trips the rule\n"
        findings = self.check("sample.py", text)
        self.assertIn("STE008", [f.code for f in findings])

    def test_71_long_code_line_not_reported(self):
        text = "x = " + " + ".join(["1"] * 40) + "  # ok\n"
        findings = self.check("sample.py", text)
        self.assertEqual([f.code for f in findings], [])

    def test_72_reported_line_numbers_match_source(self):
        rows = [
            # Catches: a long sentence across comment lines is not reported.
            ("\n".join("# " + w for w in ["word"] * 31) + "\n", None),
            # Catches: a reported line number points at the wrong source line.
            ("x = 1\n"
             "# a short first comment line\n"
             "# and this comment run keeps going to make the sentence long enough "
             "that it holds more than thirty words in total across these comment lines "
             "of the sample file for the test\n",
             {2, 3}),
        ]
        for text, allowed_lines in rows:
            with self.subTest(allowed_lines=allowed_lines):
                findings = self.check("sample.py", text)
                self.assertIn("STE001", [f.code for f in findings])
                if allowed_lines is not None:
                    lines = {f.line for f in findings}
                    self.assertNotIn(1, lines)
                    self.assertTrue(lines and lines.issubset(allowed_lines))

    def test_73_hash_inside_shell_quotes_is_not_a_comment(self):
        # No unquoted '#' exists on this line. A scanner that finds '#' without
        # tracking quote state would treat "b; c" as a comment body and report the
        # semicolon. The quote-aware scanner must find no comment at all here.
        text = 'VAR="a # b; c"\n'
        findings = self.check("sample.sh", text)
        self.assertEqual(findings, [])

    def test_74_contraction_in_shell_comment_reported(self):
        text = "# this comment isn't clean and that trips the rule\n"
        findings = self.check("sample.sh", text)
        self.assertIn("STE008", [f.code for f in findings])

    def test_75_unknown_extension_falls_back_to_check_text(self):
        text = "This sentence isn't clean and that trips the rule.\n"
        findings = self.check("notes.md", text)
        self.assertIn("STE008", [f.code for f in findings])

    def test_76_docstring_contraction_reported_at_its_own_line(self):
        text = (
            "def f():\n"
            '    """Summary line.\n'
            "\n"
            "    This body line isn't clean and should be reported here.\n"
            '    """\n'
            "    return 1\n"
        )
        findings = self.check("sample.py", text)
        matches = [f for f in findings if f.code == "STE008"]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].line, 4)


class FindingEchoSanitizationTests(unittest.TestCase):
    """lint/_transcript.py's format_finding is the one place lint/md_sweep.py and
    lint/ste_gate.py turn an ste_lint.py finding into text for a hook's reason: ste_gate.py's
    permissionDecisionReason, live on every Write, Edit and MultiEdit, and md_sweep.py's Stop
    block reason. A finding's `message` is attacker-reachable: ste_lint.py's STE003, STE007,
    STE008, STE009, STE011, STE013, STE015 and STE017 rules build it with %r around a substring
    matched out of the linted file (see ste_lint.py's check_words). format_finding must not
    trust that text.

    Handed a crafted finding directly (not routed back through ste_lint.py's own %r, which
    already escapes a raw control byte before it would reach here), format_finding must still
    come out clean: this is the same belt this module gives every finding, not a claim that
    today's %r-wrapped rules leak an unescaped byte.
    """

    def test_77_control_character_in_message_is_not_echoed_raw(self):
        finding = {"line": 3, "code": "STE002", "message": "'is\x1fadded' is passive."}
        self.assertNotIn("\x1f", format_finding(finding))


class ValeBloatPairTests(unittest.TestCase):
    """STE011 pairs copied from the Vale style packs (decisions/fewest-words-mandate.md)."""

    def codes(self, text):
        return [f.code for f in ste_lint.Linter(dict(ste_lint.DEFAULT_CONFIG)).check_text("t.md", text)]

    def test_80_acronym_pair_is_case_sensitive(self):
        rows = [
            # Catches: an upper-case PIN pair is not blocked.
            ("Type the PIN number again.\n", True),
            # Catches: a lower-case pin pair is a false alarm.
            ("Read the pin number on the board.\n", False),
            # Catches: the bloat pair "in addition to" is a false alarm.
            ("It reads the log in addition to the file.\n", False),
        ]
        for text, present in rows:
            with self.subTest(text=text):
                if present:
                    self.assertIn("STE011", self.codes(text))
                else:
                    self.assertNotIn("STE011", self.codes(text))


class UICopyLintTests(unittest.TestCase):
    """Front-end copy: ste_lint reads only the text a user sees in .tsx, .jsx, .html and
    .vue files, and caps a button, label or aria-label at 4 words (STE020)."""

    def check(self, path, text):
        return ste_lint.Linter(dict(ste_lint.DEFAULT_CONFIG)).check_ui(path, text)

    def codes(self, path, text):
        return [f.code for f in self.check(path, text)]

    def test_82_five_word_button_blocks(self):
        rows = [
            # Catches: a five-word button is not blocked at the 4-word cap.
            ("const x = <button>Save the file right now</button>;\n", True),
            # Catches: a five-word label is not blocked at the 4-word cap.
            ("const x = <label>Your primary email address here</label>;\n", True),
            # Catches: a four-word button at the cap is a false alarm.
            ("const x = <button>Save the file now</button>;\n", False),
        ]
        for text, blocked in rows:
            with self.subTest(text=text):
                findings = self.check("a.tsx", text)
                if blocked:
                    self.assertEqual([f.code for f in findings], ["STE020"])
                    hit = [f for f in findings if f.code == "STE020"]
                    self.assertTrue(hit)
                    self.assertIn("5 words", hit[0].message)
                    self.assertIn("limit is 4", hit[0].message)
                else:
                    self.assertEqual([f.code for f in findings], [])

    def test_84_expression_only_label_is_skipped(self):
        self.assertEqual(self.codes("a.jsx", "const x = <label>{props.longLabelText}</label>;\n"), [])

    def test_85_expression_is_not_counted(self):
        self.assertEqual(self.codes("a.jsx", "const x = <button>Delete {count} old files</button>;\n"), [])

    def test_86_aria_label_cap(self):
        self.assertIn("STE020", self.codes(
            "a.tsx", 'const x = <input aria-label="Close this dialog window now" />;\n'))
        self.assertEqual(self.codes("a.tsx", 'const x = <input aria-label="Close dialog" />;\n'), [])

    def test_87_class_name_with_long_text_passes(self):
        text = ('const x = <div className="in order to make the layout wide and prior to the '
                'grid move it">Hi</div>;\n')
        self.assertEqual(self.codes("a.tsx", text), [])

    def test_88_bloat_in_jsx_text_blocks(self):
        findings = self.check("a.tsx", "const x = (\n  <p>In order to save, press the key.</p>\n);\n")
        hit = [f for f in findings if f.code == "STE011"]
        self.assertTrue(hit)
        self.assertEqual((hit[0].line, hit[0].col), (2, 6))

    def test_89_bloat_in_js_string_passes(self):
        text = ('// in order to load it\nconst msg = "in order to save";\n'
                "const re = /in order to/;\nconst t = `in order to ${a}`;\n")
        self.assertEqual(self.codes("a.tsx", text), [])

    def test_90_generic_and_comparison_are_not_jsx(self):
        text = ("function f<T>(a: Array<T>) { return a.length < 3 && b > 1; }\n"
                "const g = <T,>(x: T) => x;\n"
                "const y = <p>In order to go.</p>;\n")
        self.assertEqual(self.codes("a.tsx", text), ["STE011"])

    def test_91_vue_template_is_read(self):
        text = ("<template>\n  <div :title=\"dynamicTitle\">\n"
                "    <p>In order to go, press {{ key }}.</p>\n"
                "    <button>Delete all of the files</button>\n  </div>\n</template>\n"
                "<script setup>\nconst s = \"in order to\";\n</script>\n")
        findings = self.check("a.vue", text)
        self.assertEqual(sorted((f.code, f.line) for f in findings), [("STE011", 3), ("STE020", 4)])

    def test_92_html_file_is_read(self):
        text = ('<html><head><script>var a = "in order to";</script></head><body>\n'
                '<h1 class="prior-to">Welcome</h1>\n'
                '<img src="x.png" alt="A picture taken prior to the launch">\n'
                "<code>in order to</code>\n</body></html>\n")
        findings = self.check("a.html", text)
        self.assertEqual([(f.code, f.line, f.col) for f in findings], [("STE011", 3, 39)])

    def test_93_contraction_is_skipped_for_ui(self):
        self.assertEqual(self.codes("a.tsx", "const x = <p>You can't undo it.</p>;\n"), [])

    def test_94_disable_comment_is_honored(self):
        text = ("const x = (\n  // ste-disable-next-line STE020: brand name\n"
                "  <button>Save the file right now</button>\n);\n")
        self.assertEqual(self.codes("a.tsx", text), [])

    def test_95_cli_reads_ui_file_as_ui(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "a.tsx")
            with open(path, "w", encoding="utf-8") as f:
                f.write('const msg = "in order to save";\n')
            run = subprocess.run([sys.executable, os.path.join(HERE, "ste_lint.py"),
                                  "--no-color", path], capture_output=True, text=True, timeout=15)
        self.assertEqual(run.returncode, 0, run.stdout)


class SteGateUICopyTests(unittest.TestCase):
    """lint/ste_gate.py blocks a Write, Edit or MultiEdit to a UI file on its copy, the
    same way it blocks a *.md write."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def pretooluse(self, tool, tool_input):
        return run_gate(STE_GATE, {"hook_event_name": "PreToolUse", "tool_name": tool,
                                   "tool_input": tool_input})

    def target(self, name, text=None):
        path = os.path.join(self.tmp.name, name)
        if text is not None:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        return path

    def test_96_tsx_write_with_five_word_button_denied(self):
        rows = [
            # Catches: a five-word button written to a .tsx file is allowed.
            ("export const A = () => <button>Save the file right now</button>;\n", True),
            # Catches: a four-word button at the cap is wrongly denied.
            ("export const A = () => <button>Save the file now</button>;\n", False),
        ]
        for content, denied in rows:
            with self.subTest(content=content):
                run = self.pretooluse("Write", {"file_path": self.target("App.tsx"),
                                               "content": content})
                if denied:
                    reason = json.loads(run.stdout)["hookSpecificOutput"]["permissionDecisionReason"]
                    self.assertIn("STE020", reason)
                else:
                    self.assertEqual(run.stdout.strip(), "")

    def test_98_jsx_edit_with_bloat_denied(self):
        path = self.target("App.jsx", "export const A = () => (\n  <p>Save it.</p>\n);\n")
        run = self.pretooluse("Edit", {"file_path": path, "old_string": "<p>Save it.</p>",
                                       "new_string": "<p>In order to save, press it.</p>"})
        self.assertIn("STE011", run.stdout)

    def test_99_vue_multiedit_js_string_allowed(self):
        path = self.target("A.vue", "<template><p>Hi</p></template>\n<script>\nconst s = 1;\n</script>\n")
        run = self.pretooluse("MultiEdit", {"file_path": path, "edits": [
            {"old_string": "const s = 1;", "new_string": 'const s = "in order to";'}]})
        self.assertEqual(run.stdout.strip(), "")

    def test_100_html_write_with_bloat_denied(self):
        run = self.pretooluse("Write", {"file_path": self.target("index.html"),
                                        "content": "<p>Wait prior to the launch.</p>\n"})
        self.assertIn("STE011", run.stdout)


class UICopyRoundTwoTests(unittest.TestCase):
    """Front-end copy lint: label tags come from a per-repo config key, and a UI escape is
    line-level and names a rule and a reason."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def check(self, path, text, **config):
        return [f.code for f in ste_lint.Linter(dict(ste_lint.DEFAULT_CONFIG, **config))
                .check_ui(path, text)]

    def md(self, text):
        return [f.code for f in ste_lint.Linter(dict(ste_lint.DEFAULT_CONFIG)).check_text("t.md", text)]

    def cli(self, name, text, config=None):
        sub = os.path.join(self.tmp.name, "src")
        os.makedirs(sub, exist_ok=True)
        if config is not None:
            with open(os.path.join(self.tmp.name, ".ste.json"), "w", encoding="utf-8") as f:
                json.dump(config, f)
        path = os.path.join(sub, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        run = subprocess.run([sys.executable, os.path.join(HERE, "ste_lint.py"), "--format",
                              "json", "--fail-on", "never", path],
                             capture_output=True, text=True, timeout=15)
        return [f["code"] for f in json.loads(run.stdout)["findings"]]

    # R1 -------------------------------------------------------------------------

    def test_101_label_tags_come_from_repo_config(self):
        text = "const x = <Button>Save the file right now</Button>;\n"
        self.assertEqual(self.cli("a.tsx", text), [])
        self.assertEqual(self.cli("a.tsx", text, {"label_tags": ["Button"]}), ["STE020"])

    def test_102_jsx_tag_compare_is_exact(self):
        text = "const x = <button>Save the file right now</button>;\n"
        self.assertEqual(self.check("a.tsx", text, label_tags=["Button"]), [])

    def test_103_html_tag_compare_ignores_case(self):
        text = "<button>Save the file right now</button>\n"
        self.assertEqual(self.check("a.html", text, label_tags=["Button"]), ["STE020"])

    # R2 -------------------------------------------------------------------------

    def test_104_escape_without_reason_is_an_error(self):
        rows = [
            # Catches: a UI escape with no reason goes unreported.
            ("a.tsx", "const x = (\n  // ste-disable-next-line STE020\n"
                      "  <button>Save the file right now</button>\n);\n"),
            # Catches: a UI escape with no rule name goes unreported.
            ("a.html", "<!-- ste-disable-next-line: brand name -->\n"
                       "<button>Save the file right now</button>\n"),
        ]
        for path, text in rows:
            with self.subTest(path=path):
                self.assertEqual(sorted(self.check(path, text)), ["STE020", "STE021"])

    def test_106_file_escape_is_an_error_for_ui(self):
        text = "// ste-disable-file STE020: all\nconst x = <button>Save the file right now</button>;\n"
        self.assertEqual(sorted(self.check("a.tsx", text)), ["STE020", "STE021"])

    def test_107_escape_in_visible_copy_does_not_count(self):
        text = "const x = <button>ste-disable-line STE020: why not here</button>;\n"
        self.assertIn("STE020", self.check("a.tsx", text))

    def test_108_valid_same_line_escape_in_jsx_comment(self):
        text = "const x = <button>Save the file right now</button>; {/* ste-disable-line STE020: brand */}\n"
        self.assertEqual(self.check("a.tsx", text), [])

    # Finding 1 and item 10 -------------------------------------------------------

    def test_109_adverb_and_ui_pairs_are_gone(self):
        for text in ("Completely separate the two cables.\n",
                     "The job did not successfully complete.\n",
                     "The cause is readily apparent from the log.\n",
                     "Put the parts in some cases on the shelf.\n",
                     "In most cases the rack holds two units.\n",
                     "Place an order for the parts.\n",
                     "Take action on the alert.\n"):
            self.assertNotIn("STE011", self.md(text), text)

    # Finding 3 ------------------------------------------------------------------

    def test_110_jsx_code_tags_are_skipped(self):
        text = ("const x = (<div>\n<code>in order to</code>\n<pre>prior to</pre>\n"
                "<kbd>in order to</kbd>\n<samp>prior to</samp>\n<p>Go now.</p>\n</div>);\n")
        self.assertEqual(self.check("a.tsx", text), [])

    # Finding 5 ------------------------------------------------------------------

    def test_112_vue_reads_only_the_template(self):
        text = ('<template><p>Hi</p></template>\n<i18n>\n{"en": {"a": "In order to go prior to it"}}\n'
                "</i18n>\n")
        self.assertEqual(self.check("a.vue", text), [])

    # Finding 8 ------------------------------------------------------------------

    def test_113_label_does_not_count_select_options(self):
        text = ("const x = <label>Size <select><option>Small size box</option>"
                "<option>Large size box</option></select></label>;\n")
        self.assertEqual(self.check("a.tsx", text), [])

    # Finding 9 ------------------------------------------------------------------

    def test_120_paren_copy_is_read(self):
        self.assertEqual(self.check("a.tsx", "const x = <small>(optional) Click on the link in order "
                                             "to go.</small>;\n"), ["STE011", "STE011"])
        self.assertEqual(self.check("a.tsx", "const x = <button>(1) Save all of your changes "
                                             "now</button>;\n"), ["STE020"])

    def test_114_many_generics_lint_in_linear_time(self):
        import time
        lines = []
        for i in range(600):
            lines.append("const f%d = <T extends X>(a: T): T => a;" % i)
            lines.extend(["const v%d_%d = %d;" % (i, j, j) for j in range(7)])
        lines.append("const y = <p>In order to go.</p>;")
        text = "\n".join(lines) + "\n"
        self.assertGreaterEqual(len(lines), 4800)
        started = time.monotonic()
        codes = self.check("a.tsx", text)
        self.assertLess(time.monotonic() - started, 2.0)
        self.assertEqual(codes, ["STE011"])


class SteGateUIScopeTests(unittest.TestCase):
    """Finding 2: a UI edit is scoped to the copy it changed, never to a blank-line block."""

    COMPONENT = ("export function A() {\n  const count = 1;\n  const other = 2;\n"
                 "  return (\n    <button>Save all the open files now</button>\n  );\n}\n")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "A.tsx")
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(self.COMPONENT)

    def edit(self, old, new):
        return run_gate(STE_GATE, {"hook_event_name": "PreToolUse", "tool_name": "Edit",
                                   "tool_input": {"file_path": self.path, "old_string": old,
                                                  "new_string": new}})

    def test_115_code_edit_near_old_long_button_allowed(self):
        run = self.edit("const count = 1;", "const count = 2;")
        self.assertEqual(run.stdout.strip(), "")

    def test_116_button_text_edit_to_six_words_denied(self):
        run = self.edit("Save all the open files now", "Save all of the open files now")
        self.assertIn("STE020", run.stdout)

    def test_118_copy_of_old_long_button_is_in_scope(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(self.COMPONENT.replace("    <button>", "    <p>Bye</p>\n    <button>"))
        run = self.edit("<p>Bye</p>", "<button>Save all the open files now</button>")
        self.assertIn("STE020", run.stdout)

    def test_119_gate_reads_repo_label_tags(self):
        with open(os.path.join(self.tmp.name, ".ste.json"), "w", encoding="utf-8") as f:
            json.dump({"label_tags": ["button", "Button"]}, f)
        run = run_gate(STE_GATE, {"hook_event_name": "PreToolUse", "tool_name": "Write",
                                  "tool_input": {"file_path": os.path.join(self.tmp.name, "B.tsx"),
                                                 "content": "export const B = () => "
                                                            "<Button>Save all the open files now</Button>;\n"}})
        self.assertIn("STE020", run.stdout)

    def test_117_lint_that_cannot_run_is_reported_unknown(self):
        # A copy of the gate next to a linter that prints no JSON: the gate must say the
        # result is unknown, for .md and for UI files, never pass in silence.
        d = os.path.join(self.tmp.name, "gate")
        os.makedirs(d)
        for name in ("ste_gate.py", "_transcript.py"):
            with open(os.path.join(HERE, name), encoding="utf-8") as src, \
                    open(os.path.join(d, name), "w", encoding="utf-8") as dst:
                dst.write(src.read())
        with open(os.path.join(d, "ste_lint.py"), "w", encoding="utf-8") as f:
            f.write("UI_SUFFIXES = {'.tsx'}\nif __name__ == '__main__':\n    print('not json')\n")
        for name in ("n.md", "n.tsx"):
            run = run_gate(os.path.join(d, "ste_gate.py"), {
                "hook_event_name": "PreToolUse", "tool_name": "Write",
                "tool_input": {"file_path": os.path.join(self.tmp.name, name), "content": "x\n"}})
            self.assertIn("unknown", json.loads(run.stdout)["systemMessage"], name)


class TurnEndEarlyExitTests(unittest.TestCase):
    """lint/_transcript.py's `landed_work` is the one early exit for a Stop hook: False only
    when nothing is dirty in the work tree since the last human message. The repo below is
    quiet (every file backdated), so each test changes ONE thing and the answer must follow it. `read_turn` is the tail reader the idle hooks use."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = os.path.join(self.tmp.name, "repo")
        os.makedirs(self.repo)
        self.vcs("init", "-q")
        for name in ("a.md", "n.txt"):
            with open(os.path.join(self.repo, name), "w", encoding="utf-8") as f:
                f.write("one\n")
        self.vcs("add", "-A")
        self.vcs("commit", "-q", "-m", "init")
        old = datetime.now(timezone.utc).timestamp() - 1000
        for name in ("a.md", "n.txt"):  # the work tree only: the repo's own files churn under us
            os.utime(os.path.join(self.repo, name), (old, old))

    def vcs(self, *args):
        subprocess.run(["git", "-c", "user.email=t@example.com", "-c", "user.name=T",
                        "-C", self.repo] + list(args), check=True, capture_output=True, text=True)

    def transcript(self, stamp="auto"):
        record = human("go")
        if stamp == "auto":
            stamp = (datetime.now(timezone.utc) - timedelta(seconds=100)).isoformat().replace("+00:00", "Z")
        if stamp:
            record["timestamp"] = stamp
        return write_transcript([record, assistant_text("hi")], self.tmp.name)

    def landed(self, **kw):
        return landed_work(self.transcript(kw.pop("stamp", "auto")), kw.pop("cwd", self.repo), **kw)

    def test_idle_turn_exits(self):
        self.assertFalse(self.landed())

    def test_uncommitted_edit_does_not_exit(self):
        with open(os.path.join(self.repo, "n.txt"), "w", encoding="utf-8") as f:
            f.write("two\n")
        self.assertTrue(self.landed())

    def test_untracked_file_does_not_exit(self):
        with open(os.path.join(self.repo, "new.txt"), "w", encoding="utf-8") as f:
            f.write("x\n")
        self.assertTrue(self.landed())

    def test_deleted_file_does_not_exit(self):
        os.remove(os.path.join(self.repo, "n.txt"))
        self.assertTrue(self.landed())

    def test_dirt_older_than_the_message_exits(self):
        target = os.path.join(self.repo, "n.txt")
        with open(target, "w", encoding="utf-8") as f:
            f.write("two\n")
        old = datetime.now(timezone.utc).timestamp() - 1000
        os.utime(target, (old, old))
        self.assertFalse(self.landed())

    def test_unknown_reads_keep_the_hook_running(self):
        self.assertTrue(self.landed(stamp=""))  # no timestamp on the human record
        self.assertTrue(self.landed(cwd=self.tmp.name))  # not a work tree

    def test_read_turn_matches_the_full_read(self):
        sidechain = dict(human("sub"), isSidechain=True)
        records = [human("q1"), tool_use_msg("Bash", {"command": "ls"}), tool_result_msg(),
                   human("q2"), sidechain, tool_use_msg("Edit", {"file_path": "x"}),
                   tool_result_msg(), assistant_text("done")]
        path = write_transcript(records, self.tmp.name)
        from _transcript import read_transcript, records_after_last_human, read_turn
        full = read_transcript(path)
        last, after = read_turn(path)
        self.assertEqual(after, records_after_last_human(full))
        self.assertEqual(last, records[3])
        self.assertEqual(read_turn(write_transcript([assistant_text("x")], self.tmp.name)), (None, []))

    def test_read_turn_crosses_a_chunk_boundary(self):
        import _transcript
        big = [human("q")] + [assistant_text("y" * 400) for _ in range(40)]
        path = write_transcript(big, self.tmp.name)
        whole = list(_transcript._lines_backwards(path))
        small = list(_transcript._lines_backwards(path, chunk=300))
        self.assertEqual(whole, small)

    def _main_inproc(self, module_path, name, payload, patches):
        import contextlib
        import importlib.util
        import io
        spec = importlib.util.spec_from_file_location(name, module_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        calls = {}
        for attr in patches:
            real = getattr(mod, attr)

            def counted(*a, _real=real, _attr=attr, **k):
                calls[_attr] = calls.get(_attr, 0) + 1
                return _real(*a, **k)
            setattr(mod, attr, counted)
        out, stdin = io.StringIO(), sys.stdin
        sys.stdin = io.StringIO(json.dumps(payload))
        try:
            with contextlib.redirect_stdout(out):
                mod.main()
        finally:
            sys.stdin = stdin
        return out.getvalue(), calls

    def test_md_sweep_idle_turn_stops_before_it_reads_the_baseline(self):
        hook = {"hook_event_name": "Stop", "transcript_path": self.transcript(), "cwd": self.repo}
        out, calls = self._main_inproc(MD_SWEEP, "md_sweep_idle", hook, ["last_human_epoch"])
        self.assertEqual((out.strip(), calls.get("last_human_epoch", 0)), ("", 0))

    def test_md_sweep_landed_turn_still_blocks(self):
        with open(os.path.join(self.repo, "a.md"), "w", encoding="utf-8") as f:
            f.write(MdSweepTests.ERROR_TEXT)
        hook = {"hook_event_name": "Stop", "transcript_path": self.transcript(), "cwd": self.repo}
        out, calls = self._main_inproc(MD_SWEEP, "md_sweep_landed", hook, ["last_human_epoch"])
        self.assertEqual(calls.get("last_human_epoch"), 1)
        self.assertEqual(json.loads(out).get("decision"), "block")

    def test_config_report_reads_only_this_turn(self):
        target = os.path.join(self.repo, ".claude", "hooks", "x.py")
        records = [human("old turn"), tool_use_msg("Edit", {"file_path": target}), tool_result_msg(),
                   human("new turn"), assistant_text("done")]
        path = write_transcript(records, self.tmp.name)
        run = run_config_report({"hook_event_name": "Stop", "transcript_path": path, "cwd": self.repo})
        self.assertEqual(run.stdout.strip(), "")
        records.append(tool_use_msg("Edit", {"file_path": target}))
        path = write_transcript(records, self.tmp.name)
        run = run_config_report({"hook_event_name": "Stop", "transcript_path": path, "cwd": self.repo})
        self.assertIn("Config files changed", json.loads(run.stdout)["systemMessage"])


# ---------------------------------------------------------------- guard.log lines from the gates
#
# The STE gate and md_sweep append one guard.log line per outcome, through guard_core.record, so
# the columns match every other guard line. The matched field is the file's basename and a count:
# never a path, never file text. Decisions: `fixed` (a rewrite landed), `deny` (refused, with the
# remaining codes), and `noted` with rule STE-fallback (a fixer crash, timeout or oversize). md_sweep
# writes `deny` with tool `Stop`. Pinned call site: guard_core.set_log_session(the hook's session_id)
# once, then guard_core.record(...) once per outcome. Ruling: ste-gate-fixes-not-nags (the STE gate
# fixes what it can and denies the rest).

GL_SESSION = "9f2c4e1a-7b3d-4c8e-9a10-5d6e7f8a9b0c"
GL_ENV_SESSION = "1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d"
GL_RULE_CAP = 40  # pinned: the rule field holds at most this many characters
GL_LONG = ("The operators on each shift must record every valve position, every pressure reading, "
           "every alarm, and every handover note in the shared log before they leave the site today "
           "and then sign the page for the next crew.")  # 38 words: over the one budget of 30
GL_FIXED_DOC = "We close the valve in order to stop the pump, prior to the shift.\n"  # fixed: STE011 x2
GL_DENY_DOC = "The pump is not unsafe.\n"  # denied: STE013 has no fix
GL_CLEAN_DOC = "This is a short clean sentence.\n"
GL_MIXED_DOC = GL_FIXED_DOC + "\n" + GL_LONG + "\n"  # fixed, then STE001 stays: a deny
GL_MANY_FINDINGS_DOC = (  # seven error findings, three codes: STE001, STE011, STE013
    "In conclusion, the seals are sound.\n\nNeedless to say, the valve is shut.\n\n"
    "This is not uncommon.\n\nThis is not unusual.\n\nThis is not unsafe.\n\n"
    + GL_LONG + "\n\n" + GL_LONG + "\n")
GL_STRIPPED = ("STE_FIXER_LIMIT_S", "STE_FIXER_MAX_BYTES", "CLAUDE_CODE_SESSION_ID",
               "MD_SWEEP_DISABLE", "MD_SWEEP_EXCLUDE")
# Characters a guard.log field must never hold: C0 and C1 controls, line and paragraph separators,
# the bidi overrides and isolates, and a lone surrogate.
GL_HOSTILE = re.compile("[\x00-\x1f\x7f-\x9f  ‪-‮⁦-⁩\ud800-\udfff]")
def gl_env(cfg, extra=None):
    """One gate run's environment. CLAUDE_CONFIG_DIR is the test's own folder, never ~/.claude."""
    env = dict(os.environ)
    for key in GL_STRIPPED:
        env.pop(key, None)
    env["CLAUDE_CONFIG_DIR"] = cfg
    env.update(extra or {})
    return env


def gl_text(cfg):
    """guard.log in cfg as text (universal newlines), or None when there is no file."""
    path = os.path.join(cfg, "guard.log")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def gl_lines(cfg):
    """The lines of guard.log in cfg, or None when there is no file."""
    text = gl_text(cfg)
    if text is None:
        return None
    rows = text.split("\n")
    if rows[-1] == "":
        rows.pop()
    return rows


def gl_fields(row):
    """The six tab fields of one guard.log line. Any other count is a failure."""
    fields = row.split("\t")
    if len(fields) != 6:
        raise AssertionError("expected six tab fields, found %d: %r" % (len(fields), row))
    return fields


def gl_out(run):
    return json.loads(run.stdout) if run.stdout.strip() else {}


def gl_decision(run):
    return gl_out(run).get("hookSpecificOutput", {}).get("permissionDecision")


def gl_gate(cfg, tool, tool_input, session=GL_SESSION, extra=None, gate=STE_GATE):
    """Run the STE gate once on a PreToolUse call. session=None leaves the session_id key out."""
    hook = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input}
    if session is not None:
        hook["session_id"] = session
    return run_gate(gate, hook, env=gl_env(cfg, extra))


def gl_blocked_cfg(tmp):
    """A CLAUDE_CONFIG_DIR that cannot be created, because its parent is a plain file."""
    blocker = os.path.join(tmp, "blocker")
    with open(blocker, "w", encoding="utf-8") as handle:
        handle.write("not a folder")
    return os.path.join(blocker, "cfg")


def gl_copy_tree(root, old_transcript=False):
    """Copy lint/*.py (no tests) to <root>/lint and hooks/guard_core.py to <root>/hooks. With
    old_transcript, the copy's _transcript.py stops before guard_logger: the module of an older
    install, beside the new scripts. Returns the copied lint folder."""
    lint_copy = os.path.join(root, "lint")
    os.makedirs(lint_copy)
    for src in glob.glob(os.path.join(HERE, "*.py")):
        if not os.path.basename(src).startswith("test_"):
            shutil.copy(src, lint_copy)
    os.makedirs(os.path.join(root, "hooks"))
    shutil.copy(os.path.join(HOOKS, "guard_core.py"), os.path.join(root, "hooks"))
    if old_transcript:
        path = os.path.join(lint_copy, "_transcript.py")
        with open(path, encoding="utf-8") as handle:
            old = handle.read().split("\ndef guard_logger(")[0]
        if "def guard_logger" in old:
            raise AssertionError("the cut did not remove guard_logger")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(old)
    return lint_copy


def gl_set_linter(lint_copy, entry):
    """Make the linter in `lint_copy` run `entry` where its main() runs: a fresh copy of lint/ste_lint.py
    with that entry. Calling it again swaps the entry and leaves the folder, and so every path a gate
    prints, the same."""
    with open(os.path.join(HERE, "ste_lint.py"), encoding="utf-8") as handle:
        text = handle.read()
    entry_main = 'if __name__ == "__main__":\n    sys.exit(main())'
    if text.count(entry_main) != 1:
        raise AssertionError("the linter entry point moved")
    with open(os.path.join(lint_copy, "ste_lint.py"), "w", encoding="utf-8") as handle:
        handle.write(text.replace(entry_main, 'if __name__ == "__main__":\n    ' + entry))


def gl_linter_tree(root, entry):
    """A gate tree whose linter, run as a script, does `entry` where its main() runs, so the gate
    gets no findings from the child: a crash, or silence. Returns the copied ste_gate.py."""
    lint_copy = gl_copy_tree(root)
    gl_set_linter(lint_copy, entry)
    return os.path.join(lint_copy, "ste_gate.py")


def gl_sleepy_tree(root, seconds):
    """A gate tree whose guard_core.record sleeps first, so a log write takes `seconds`. Returns the
    copied lint folder."""
    lint_copy = gl_copy_tree(root)
    with open(os.path.join(root, "hooks", "guard_core.py"), "a", encoding="utf-8") as handle:
        handle.write("\n\nimport time as _slow_time\n_slow_record = record\n\n"
                     "def record(tool, decision, rule, matched):\n"
                     "    _slow_time.sleep(%r)\n"
                     "    _slow_record(tool, decision, rule, matched)\n" % (seconds,))
    return lint_copy


def gl_timed(script, hook, env):
    """Run a hook script. Return (seconds until its first stdout line, rc, all stdout, stderr)."""
    proc = subprocess.Popen([sys.executable, script], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    start = time.monotonic()
    proc.stdin.write(json.dumps(hook).encode("utf-8"))
    proc.stdin.close()
    first = proc.stdout.readline()
    seconds = time.monotonic() - start
    rest = proc.stdout.read()
    err = proc.stderr.read()
    proc.stdout.close()
    proc.stderr.close()
    proc.wait()
    return seconds, proc.returncode, (first + rest).decode("utf-8"), err.decode("utf-8", "replace")


def gl_guard_core():
    """guard_core, imported the way the gates import it: from hooks/ beside lint/."""
    if HOOKS not in sys.path:
        sys.path.insert(0, HOOKS)
    import guard_core
    return guard_core


class SteGateLogTests(unittest.TestCase):
    """The STE gate's guard.log line, one per outcome. Each test names the pin it holds."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cfg = os.path.join(self.tmp.name, "cfg")  # CLAUDE_CONFIG_DIR: a test folder
        os.makedirs(self.cfg)
        self.docs = os.path.join(self.tmp.name, "privdir-4481")  # the folder of the written file
        os.makedirs(self.docs)

    def _fresh_row(self):
        """Give the next row its own config folder and file folder, so no line from an earlier row is left."""
        root = tempfile.mkdtemp(dir=self.tmp.name)
        self.cfg = os.path.join(root, "cfg")
        os.makedirs(self.cfg)
        self.docs = os.path.join(root, "privdir-4481")  # the folder of the written file
        os.makedirs(self.docs)

    def _path(self, name="notes.md"):
        return os.path.join(self.docs, name)

    def _disk(self, name, text):
        with open(self._path(name), "w", encoding="utf-8") as handle:
            handle.write(text)
        return self._path(name)

    def _rows(self, what):
        rows = gl_lines(self.cfg)
        self.assertIsNotNone(rows, "no guard.log line for %s" % what)
        return rows

    def _gate_copy(self, name, with_guard_core):
        """A copy of lint/*.py (no tests) under <tmp>/<name>/lint, beside <tmp>/<name>/hooks when
        `with_guard_core` is true, holding the real guard_core.py. Returns the copied ste_gate.py."""
        root = os.path.join(self.tmp.name, name)
        lint_copy = os.path.join(root, "lint")
        os.makedirs(lint_copy)
        for src in glob.glob(os.path.join(HERE, "*.py")):
            if not os.path.basename(src).startswith("test_"):
                shutil.copy(src, lint_copy)
        if with_guard_core:
            os.makedirs(os.path.join(root, "hooks"))
            shutil.copy(os.path.join(HOOKS, "guard_core.py"), os.path.join(root, "hooks"))
        return os.path.join(lint_copy, "ste_gate.py")

    def _crash_gate(self):
        """A gate copy whose fixer raises. The plain lint in the copy is unchanged."""
        gate = self._gate_copy("crash", True)
        with open(os.path.join(os.path.dirname(gate), "ste_lint.py"), "a", encoding="utf-8") as handle:
            handle.write("\n\ndef apply_fixes(text):\n    raise RuntimeError('fixer crash')\n")
        return gate

    def _assert_fallback(self, reason):
        """A fallback over a denied write: one noted line for the fallback, one deny for the codes."""
        rows = self._rows("the %s fallback" % reason)
        by = {gl_fields(row)[2]: gl_fields(row) for row in rows}
        self.assertEqual(sorted(by), ["deny", "noted"], rows)
        self.assertEqual(by["noted"][1:5],
                         ["Write", "noted", "STE-fallback", "notes.md fallback=%s" % reason])
        self.assertEqual(by["deny"][1:5], ["Write", "deny", "STE011", "notes.md denied=2"])
        self.assertEqual({fields[5] for fields in by.values()}, {GL_SESSION})

    # (1) a fixed write: one `fixed` line. The rule holds the fixed codes and matched the basename.
    def test_01_fixed_write_appends_one_line_with_codes_and_counts(self):
        run = gl_gate(self.cfg, "Write", {"file_path": self._path(), "content": GL_FIXED_DOC})
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("updatedInput", gl_out(run).get("hookSpecificOutput", {}))  # precondition
        rows = self._rows("a fixed write")
        self.assertEqual(len(rows), 1)
        when, *rest = gl_fields(rows[0])
        datetime.fromisoformat(when)
        self.assertEqual(rest, ["Write", "fixed", "STE011", "notes.md fixed=2", GL_SESSION])

    # (1) Edit and MultiEdit log their own tool name. The codes and count match the rewrite note.
    def test_02_fixed_edit_and_multiedit_log_their_tool_name_and_note_codes(self):
        self._disk("notes.md", "Intro.\n")
        calls = [
            ("Edit", {"file_path": self._path(), "old_string": "Intro.\n", "new_string": GL_FIXED_DOC}),
            ("MultiEdit", {"file_path": self._path(),
                           "edits": [{"old_string": "Intro.\n", "new_string": GL_FIXED_DOC}]}),
        ]
        for count, (tool, tool_input) in enumerate(calls, 1):
            run = gl_gate(self.cfg, tool, tool_input)
            pairs = re.findall(r"(STE\d{3}) x(\d+)", gl_out(run).get("systemMessage", ""))
            self.assertTrue(pairs, "precondition: %s was not fixed" % tool)
            rows = self._rows("a fixed %s" % tool)
            self.assertEqual(len(rows), count)
            want = [tool, "fixed", ",".join(sorted({code for code, _ in pairs})),
                    "notes.md fixed=%d" % sum(int(n) for _, n in pairs), GL_SESSION]
            self.assertEqual(gl_fields(rows[-1])[1:], want)

    # (2) a denied write: one `deny` line, the remaining codes, and the count of findings.
    def test_03_deny_appends_the_remaining_codes_and_the_denied_count(self):
        rows = [
            # Catches: a plain deny logs the wrong code or count.
            (GL_DENY_DOC, "STE013"),
            # Catches: a mixed write logs the fixed code as well as the code that remains.
            (GL_MIXED_DOC, "STE001"),
        ]
        for content, rule in rows:
            with self.subTest(rule=rule):
                self._fresh_row()
                run = gl_gate(self.cfg, "Write", {"file_path": self._path(), "content": content})
                self.assertEqual(gl_decision(run), "deny")  # precondition
                log = self._rows("a denied write")
                self.assertEqual(len(log), 1)
                self.assertEqual(gl_fields(log[0])[1:],
                                 ["Write", "deny", rule, "notes.md denied=1", GL_SESSION])

    # (2) the rule field stays under its cap, and the count still counts every finding, not the
    # five shown. Only three codes can deny a Markdown write now (STE001, STE011, STE013), so the
    # cap itself is out of reach of this input.
    def test_05_many_findings_deny_keeps_the_rule_under_the_cap_and_counts_every_finding(self):
        run = gl_gate(self.cfg, "Write", {"file_path": self._path(), "content": GL_MANY_FINDINGS_DOC})
        self.assertEqual(gl_decision(run), "deny")  # precondition
        rows = self._rows("a many-findings deny")
        self.assertEqual(len(rows), 1)
        _, tool, decision, rule, matched, session = gl_fields(rows[0])
        self.assertEqual((tool, decision), ("Write", "deny"))
        self.assertLessEqual(len(rule), GL_RULE_CAP, rule)
        self.assertEqual(rule, "STE001,STE011,STE013")
        self.assertEqual(matched, "notes.md denied=7")
        self.assertEqual(session, GL_SESSION)

    # (3) a clean write adds no line. The fixed write first proves the line would be seen.
    def test_06_clean_write_adds_no_line_after_a_fixed_write(self):
        gl_gate(self.cfg, "Write", {"file_path": self._path(), "content": GL_FIXED_DOC})
        before = len(self._rows("the fixed write"))
        clean = gl_gate(self.cfg, "Write", {"file_path": self._path(), "content": GL_CLEAN_DOC})
        self.assertEqual(clean.stdout.strip(), "")
        self.assertEqual(len(gl_lines(self.cfg)), before, "a clean write added a guard.log line")

    # (4) a timeout: one noted STE-fallback line, the deny from plain lint, and the same output
    # as a run whose log cannot be written.
    def test_07_timeout_fallback_logs_noted_and_keeps_the_output(self):
        extra = {"STE_FIXER_LIMIT_S": "0.001"}
        run = gl_gate(self.cfg, "Write", {"file_path": self._path(), "content": GL_FIXED_DOC},
                      extra=extra)
        bare = gl_gate(gl_blocked_cfg(self.tmp.name), "Write",
                       {"file_path": self._path(), "content": GL_FIXED_DOC}, extra=extra)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(gl_decision(run), "deny")  # precondition: plain lint decides
        self.assertEqual(run.stdout, bare.stdout)
        self._assert_fallback("timeout")

    # (4) an oversize input: the same pins as the timeout.
    def test_08_oversize_fallback_logs_noted_and_keeps_the_output(self):
        extra = {"STE_FIXER_MAX_BYTES": "5"}
        run = gl_gate(self.cfg, "Write", {"file_path": self._path(), "content": GL_FIXED_DOC},
                      extra=extra)
        bare = gl_gate(gl_blocked_cfg(self.tmp.name), "Write",
                       {"file_path": self._path(), "content": GL_FIXED_DOC}, extra=extra)
        self.assertEqual(gl_decision(run), "deny")  # precondition: plain lint decides
        self.assertEqual(run.stdout, bare.stdout)
        self._assert_fallback("oversize")

    # (4) a fixer crash: one noted STE-fallback line, the deny from plain lint, no traceback.
    def test_09_crash_fallback_logs_noted_then_the_plain_deny(self):
        run = gl_gate(self.cfg, "Write", {"file_path": self._path(), "content": GL_FIXED_DOC},
                      gate=self._crash_gate())
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertNotIn("Traceback", run.stderr)
        self.assertEqual(gl_decision(run), "deny")  # precondition
        self._assert_fallback("crash")

    # (4) a fixer crash on clean text: the write is allowed, and the fallback still counts once.
    def test_09b_crash_on_clean_text_logs_one_noted_line(self):
        run = gl_gate(self.cfg, "Write", {"file_path": self._path(), "content": GL_CLEAN_DOC},
                      gate=self._crash_gate())
        self.assertEqual(run.stdout.strip(), "")  # precondition: the write is allowed
        rows = self._rows("a fallback on clean text")
        self.assertEqual(len(rows), 1)
        self.assertEqual(gl_fields(rows[0])[1:],
                         ["Write", "noted", "STE-fallback", "notes.md fallback=crash", GL_SESSION])

    # (4) a log that cannot be written never changes the output or the exit code.
    def test_11_unwritable_log_never_changes_output_or_exit_code(self):
        run = gl_gate(self.cfg, "Write", {"file_path": self._path(), "content": GL_FIXED_DOC})
        bare = gl_gate(gl_blocked_cfg(self.tmp.name), "Write",
                       {"file_path": self._path(), "content": GL_FIXED_DOC})
        self.assertEqual(bare.returncode, 0, bare.stderr)
        self.assertNotIn("Traceback", bare.stderr)
        self.assertEqual((run.returncode, run.stdout), (bare.returncode, bare.stdout))

    # (4) a read-only log: nothing is appended, nothing is raised, the output is the fixed text.
    def test_12_read_only_log_never_changes_output_or_exit_code(self):
        log = os.path.join(self.cfg, "guard.log")
        with open(log, "w", encoding="utf-8") as handle:
            handle.write("")
        os.chmod(log, stat.S_IREAD)
        self.addCleanup(os.chmod, log, stat.S_IREAD | stat.S_IWRITE)  # restore before the tmp cleanup
        run = gl_gate(self.cfg, "Write", {"file_path": self._path(), "content": GL_FIXED_DOC})
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertNotIn("Traceback", run.stderr)
        self.assertIn("updatedInput", gl_out(run).get("hookSpecificOutput", {}))
        with open(log, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "", "a line was appended to a read-only log")

    # (4) a missing guard_core (the hooks folder is absent) keeps the output and the exit code.
    def test_13_missing_guard_core_keeps_the_output_and_exit_code(self):
        bare = gl_gate(self.cfg, "Write", {"file_path": self._path(), "content": GL_FIXED_DOC},
                       gate=self._gate_copy("nohooks", False))
        full = gl_gate(self.cfg, "Write", {"file_path": self._path(), "content": GL_FIXED_DOC})
        self.assertEqual(bare.returncode, 0, bare.stderr)
        self.assertNotIn("Traceback", bare.stderr)
        self.assertEqual(bare.stdout, full.stdout)

    # (10) the line holds no file text and no folder: a marker in the body and in an Edit is absent.
    def test_14_line_holds_no_file_text_and_no_folder(self):
        marker = "ZQXMARK-7731"
        self._disk("edit.md", "Intro %s here.\n" % marker)
        gl_gate(self.cfg, "Write", {"file_path": self._path(),
                                    "content": "We close the valve in order to stop %s, prior to the shift.\n" % marker})
        gl_gate(self.cfg, "Write", {"file_path": self._path("deny.md"),
                                    "content": "The pump is not unsafe, %s.\n" % marker})
        gl_gate(self.cfg, "Edit", {"file_path": self._path("edit.md"),
                                   "old_string": "Intro %s here.\n" % marker,
                                   "new_string": "We close it in order to stop, prior to here.\n"})
        rows = self._rows("the privacy writes")
        self.assertGreaterEqual(len(rows), 2)
        text = gl_text(self.cfg)
        self.assertNotIn(marker, text)
        self.assertNotIn("privdir-4481", text)
        self.assertNotIn(self.docs, text)

    # (8) the session column is the hook's session_id, never the environment, and `-` when absent.
    def test_15_session_column_is_the_hook_id_and_never_the_environment(self):
        core = gl_guard_core()
        extra = {"CLAUDE_CODE_SESSION_ID": GL_ENV_SESSION}
        gl_gate(self.cfg, "Write", {"file_path": self._path(), "content": GL_FIXED_DOC}, extra=extra)
        gl_gate(self.cfg, "Write", {"file_path": self._path("deny.md"), "content": GL_DENY_DOC},
                session=None, extra=extra)
        rows = self._rows("two writes")
        self.assertEqual(len(rows), 2)
        self.assertEqual(gl_fields(rows[0])[5], core.session_log_field(GL_SESSION))
        self.assertEqual(gl_fields(rows[1])[5], "-")

    # (9) the line ends as guard_core.record ends its lines on this platform (CRLF on Windows).
    def test_18_line_end_matches_guard_core_record_on_this_platform(self):
        base = os.path.join(self.tmp.name, "base")
        os.makedirs(base)
        subprocess.run([sys.executable, "-c",
                        "import sys; sys.path.insert(0, %r); import guard_core; "
                        "guard_core.record('Write', 'deny', 'X', 'm')" % HOOKS],
                       env=gl_env(base), check=True, capture_output=True, text=True)
        with open(os.path.join(base, "guard.log"), "rb") as handle:
            recorded = handle.read()
        end = recorded[len(recorded.rstrip(b"\r\n")):]
        if os.name == "nt":
            self.assertEqual(end, b"\r\n", "guard_core.record no longer writes CRLF on Windows")
        gl_gate(self.cfg, "Write", {"file_path": self._path(), "content": GL_FIXED_DOC})
        self._rows("the fixed write")
        with open(os.path.join(self.cfg, "guard.log"), "rb") as handle:
            raw = handle.read()
        self.assertTrue(raw.endswith(end), "line end differs from guard_core.record: %r" % raw[-4:])
        body = raw[:-len(end)]
        self.assertNotIn(b"\n", body)
        self.assertNotIn(b"\r", body)

    def _run_parallel_gates(self):
        """Start twenty gates at once on one config folder, each under its own session id. Each
        must exit 0. The caller reads guard.log."""
        procs = []
        for i in range(20):
            hook = {"hook_event_name": "PreToolUse", "tool_name": "Write",
                    "session_id": "gl-par-%02d" % i,
                    "tool_input": {"file_path": self._path(), "content": GL_FIXED_DOC}}
            proc = subprocess.Popen([sys.executable, STE_GATE], stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    env=gl_env(self.cfg))
            proc.stdin.write(json.dumps(hook).encode("utf-8"))
            proc.stdin.close()
            procs.append(proc)
        for proc in procs:
            proc.stdout.read()
            err = proc.stderr.read()
            proc.stdout.close()
            proc.stderr.close()
            proc.wait()
            self.assertEqual(proc.returncode, 0, err.decode("utf-8", "replace"))

    # (7) each gate writes exactly one whole line: no line is corrupted, doubled or joined, no process
    # crashes, and all twenty land.
    def test_19b_parallel_gates_write_exactly_one_whole_line_each(self):
        # Catches: a lost, joined, doubled or corrupted line under twenty parallel gates. Each
        # session appears once. Runs on every platform, as the lock covers Windows too.
        self._run_parallel_gates()
        rows = gl_lines(self.cfg) or []
        self.assertEqual(len(rows), 20, "lines lost: kept %d of 20" % len(rows))
        sessions = []
        for row in rows:
            when, tool, decision, rule, matched, session = gl_fields(row)
            datetime.fromisoformat(when)
            self.assertEqual((tool, decision, rule, matched),
                             ("Write", "fixed", "STE011", "notes.md fixed=2"), row)
            sessions.append(session)
        self.assertEqual(len(sessions), len(set(sessions)), "a session wrote two lines")
        self.assertLessEqual(set(sessions), {"gl-par-%02d" % i for i in range(20)})

    # (2) import skew: the new gate beside an old _transcript.py that has no guard_logger. The gate
    # prints what it prints with logging, exits as it does, and writes no line. No ImportError.
    def test_21_old_transcript_without_guard_logger_keeps_the_gate_output(self):
        gate = os.path.join(gl_copy_tree(os.path.join(self.tmp.name, "skew"), old_transcript=True),
                            "ste_gate.py")
        skew_cfg = os.path.join(self.tmp.name, "skew-cfg")
        content = {"file_path": self._path(), "content": GL_FIXED_DOC}
        skewed = gl_gate(skew_cfg, "Write", content, gate=gate)
        full = gl_gate(self.cfg, "Write", content)
        self.assertIn("updatedInput", gl_out(full).get("hookSpecificOutput", {}))  # precondition
        self.assertNotIn("Traceback", skewed.stderr)
        self.assertEqual(skewed.returncode, full.returncode, skewed.stderr)
        self.assertEqual(skewed.returncode, 0)
        self.assertEqual(skewed.stdout, full.stdout)
        self.assertIsNone(gl_lines(skew_cfg), "an old _transcript wrote a line")

    # (4) the linter returns nothing (a crash, or silence): findings are None, the write is unknown.
    # One line names the unchecked write. The output and the exit code do not change.
    def _unchecked(self, name, entry):
        gate = gl_linter_tree(os.path.join(self.tmp.name, name), entry)
        clean = {"file_path": self._path(), "content": GL_CLEAN_DOC}
        run = gl_gate(self.cfg, "Write", clean, gate=gate)
        bare = gl_gate(gl_blocked_cfg(self.tmp.name), "Write", clean, gate=gate)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertNotIn("Traceback", run.stderr)
        self.assertIn("was not checked", run.stdout)  # precondition: the unknown path
        self.assertEqual((run.returncode, run.stdout), (bare.returncode, bare.stdout))
        rows = self._rows("an unchecked write")
        self.assertEqual(len(rows), 1)
        self.assertEqual(gl_fields(rows[0])[1:],
                         ["Write", "noted", "STE-unchecked", "notes.md unchecked", GL_SESSION])

    def test_22_linter_crash_logs_unchecked_and_keeps_the_output(self):
        # Catches: a crashing linter, or a silent one, does not log the write as unchecked.
        rows = [
            ("crashlint", 'raise RuntimeError("linter crash")'),
            ("silentlint", "pass"),
        ]
        for name, entry in rows:
            with self.subTest(name=name):
                self._fresh_row()
                self._unchecked(name, entry)

    # (6) name hygiene: tab, NUL, controls, U+2028 and U+202E, and a name over 80 characters. The
    # line is one whole line, the name is cleaned, and the matched field is at most 80 characters.
    def test_25_control_characters_in_the_name_are_cleaned_and_the_field_is_capped(self):
        core = gl_guard_core()
        rows = [
            # Catches: a tab, a newline or U+2028 in a name splits the log line.
            ("a\tb\nc d ñé日本.md", "fixed", "ñé日本.md fixed=2", " fixed=2", core.LOG_MAX_MATCHED),
            # Catches: a 5000-character name loses its count or breaks the cap.
            ("n" * 5000 + ".md", "fixed", None, ".md fixed=2", core.LOG_MAX_MATCHED),
            # Catches: a lone surrogate in a name breaks the log line.
            ("notes\ud800.md", None, None, None, 80),
            # Catches: bidi isolates reach the log.
            ("a⁦b⁧c⁨d⁩e.md", "fixed", ".md", None, 80),
            # Catches: control bytes, a bidi override and a long name are not cleaned and capped.
            ("p\tq\x00r\x01s\x1bt‮u v" + "x" * 90 + ".md", None, None, None, 80),
        ]
        for name, decision, contains, ends, cap in rows:
            with self.subTest(name=ascii(name)):
                self._fresh_row()
                run = gl_gate(self.cfg, "Write",
                              {"file_path": self._path(name), "content": GL_FIXED_DOC})
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertNotIn("Traceback", run.stderr)
                log = self._rows("a write named with hostile characters")
                self.assertEqual(len(gl_text(self.cfg).splitlines()), 1, "a name split the log line")
                when, tool, got, rule, matched, session = gl_fields(log[0])
                datetime.fromisoformat(when)
                self.assertEqual((tool, session), ("Write", GL_SESSION))
                if decision is None:
                    self.assertIn(got, ("fixed", "noted", "deny"))
                else:
                    self.assertEqual(got, decision)
                    self.assertEqual(rule, "STE011")
                if contains is not None:
                    self.assertIn(contains, matched)
                if ends is not None:
                    self.assertTrue(matched.endswith(ends), matched)
                self.assertLessEqual(len(matched), cap, matched)
                self.assertIsNone(GL_HOSTILE.search(matched), repr(matched))


    # (H3) the answer leaves before the log write. The log write sleeps 4 s; the first stdout line
    # arrives in under 2 s, for a fix and for a deny.
    def _answer_first(self, name, content):
        script = os.path.join(gl_sleepy_tree(os.path.join(self.tmp.name, name), 4), "ste_gate.py")
        hook = {"hook_event_name": "PreToolUse", "tool_name": "Write", "session_id": GL_SESSION,
                "tool_input": {"file_path": self._path(), "content": content}}
        seconds, rc, out, err = gl_timed(script, hook, gl_env(self.cfg))
        self.assertNotIn("Traceback", err)
        self.assertEqual(rc, 0, err)
        self.assertLess(seconds, 2.0, "the answer waited for the log write")
        return out

    def test_27_a_fix_answers_before_the_slow_log_write(self):
        self.assertIn("updatedInput", self._answer_first("slow-fix", GL_FIXED_DOC))

    def test_28_a_deny_answers_before_the_slow_log_write(self):
        self.assertIn('"permissionDecision": "deny"', self._answer_first("slow-deny", GL_DENY_DOC))


class MdSweepLogTests(unittest.TestCase):
    """md_sweep (Stop) writes one guard.log line per run that blocks. A clean run writes none."""

    ERROR_TEXT = "This sentence is not unclean, and that trips the STE013 rule.\n"
    CLEAN_TEXT = "This is a short clean sentence.\nHere is one more short clean sentence.\n"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.proj = os.path.join(self.tmp.name, "proj")  # the swept folder: a git work tree
        self.cfg = os.path.join(self.tmp.name, "cfg")  # CLAUDE_CONFIG_DIR, outside the swept folder
        os.makedirs(self.proj)
        os.makedirs(self.cfg)
        subprocess.run(["git", "init", "-q"], cwd=self.proj, check=True, capture_output=True,
                       text=True)

    def _fresh_row(self):
        """A new swept folder (a git work tree) and a new config folder: no file or line from an
        earlier row is left."""
        self.proj = tempfile.mkdtemp(dir=self.tmp.name)
        self.cfg = tempfile.mkdtemp(dir=self.tmp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.proj, check=True, capture_output=True,
                       text=True)

    def _md(self, name, text):
        with open(os.path.join(self.proj, name), "w", encoding="utf-8") as handle:
            handle.write(text)

    def _stop_hook(self):
        """The Stop hook md_sweep reads. The last human message is 5 s old, so each file written
        here is newer than it and dirty in the work tree."""
        first = human("write the doc")
        first["timestamp"] = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat(
            timespec="milliseconds").replace("+00:00", "Z")
        records = [first, tool_use_msg("Bash", {"command": "true"}), tool_result_msg(),
                   assistant_text("done")]
        transcript = write_transcript(records, self.tmp.name)
        return {"hook_event_name": "Stop", "transcript_path": transcript, "cwd": self.proj,
                "stop_hook_active": False, "session_id": GL_SESSION}

    def _sweep(self, cfg=None, extra=None, script=None):
        """Run md_sweep as a Stop hook."""
        return run_gate(script or MD_SWEEP, self._stop_hook(), env=gl_env(cfg or self.cfg, extra))

    def _rows(self, what):
        rows = gl_lines(self.cfg)
        self.assertIsNotNone(rows, "no guard.log line for %s" % what)
        return rows

    # (5) a blocking run: one Stop line. The rule holds the STE codes; matched holds one basename.
    def test_01_a_blocking_run_appends_one_stop_line(self):
        rows = [
            # Catches: a blocking Stop run logs the wrong file count or the wrong basename.
            (["notes.md"], r"^notes\.md files=1$"),
            # Catches: two blocking files log two lines, or a count without one basename.
            (["a.md", "b.md"], r"^(a\.md|b\.md) files=2$"),
        ]
        for names, matched_pattern in rows:
            with self.subTest(files=names):
                self._fresh_row()
                for name in names:
                    self._md(name, self.ERROR_TEXT)
                run = self._sweep()
                self.assertEqual(json.loads(run.stdout).get("decision"), "block")  # precondition
                log = self._rows("a blocking Stop")
                self.assertEqual(len(log), 1)
                _, tool, decision, rule, matched, session = gl_fields(log[0])
                self.assertEqual((tool, decision, rule, session),
                                 ("Stop", "deny", "STE013", GL_SESSION))
                self.assertRegex(matched, matched_pattern)

    # (5) a clean run adds no line after a blocking run.
    def test_03_clean_run_after_a_blocking_run_adds_no_line(self):
        self._md("notes.md", self.ERROR_TEXT)
        self._sweep()
        before = len(self._rows("the blocking run"))
        self._md("notes.md", self.CLEAN_TEXT)
        run = self._sweep()
        self.assertEqual(run.stdout.strip(), "")
        self.assertEqual(len(gl_lines(self.cfg)), before, "a clean run added a guard.log line")

    # (10) the line holds no file text and no folder.
    def test_04_the_line_holds_no_file_text_and_no_folder(self):
        marker = "ZQXMARK-7731"
        self._md("notes.md", "This sentence is not unclean, %s, and that trips STE013.\n" % marker)
        self._sweep()
        self._rows("the blocking run")
        text = gl_text(self.cfg)
        self.assertIn("notes.md files=1", text)
        self.assertNotIn(marker, text)
        self.assertNotIn(self.proj, text)

    # (4) a log that cannot be written never changes md_sweep's output.
    def test_05_unwritable_log_keeps_the_block_output(self):
        self._md("notes.md", self.ERROR_TEXT)
        run = self._sweep()
        bare = self._sweep(cfg=gl_blocked_cfg(self.tmp.name))
        self.assertEqual(bare.returncode, 0, bare.stderr)
        self.assertNotIn("Traceback", bare.stderr)
        self.assertEqual(run.stdout, bare.stdout)

    # (5) the disabled sweep does nothing, so it writes nothing.
    def test_06_disabled_sweep_writes_no_line(self):
        self._md("notes.md", self.ERROR_TEXT)
        run = self._sweep(extra={"MD_SWEEP_DISABLE": "1"})
        self.assertEqual(run.stdout.strip(), "")
        self.assertIsNone(gl_lines(self.cfg))

    # (2) import skew, on the sweep side: the new md_sweep beside an old _transcript.py that has no
    # guard_logger. The sweep blocks as it does with logging, exits 0, and writes no line.
    def test_07_old_transcript_without_guard_logger_keeps_the_sweep_output(self):
        self._md("notes.md", self.ERROR_TEXT)
        real = self._sweep()
        self.assertEqual(json.loads(real.stdout).get("decision"), "block")  # precondition
        lint_copy = gl_copy_tree(os.path.join(self.tmp.name, "skew"), old_transcript=True)
        skew_cfg = os.path.join(self.tmp.name, "skew-cfg")
        skewed = self._sweep(cfg=skew_cfg, script=os.path.join(lint_copy, "md_sweep.py"))
        self.assertNotIn("Traceback", skewed.stderr)
        self.assertEqual(skewed.returncode, 0, skewed.stderr)
        self.assertEqual(skewed.stdout, real.stdout)
        self.assertIsNone(gl_lines(skew_cfg), "an old _transcript wrote a line")

    # (H3) the sweep prints its block before the log write. The log write sleeps 4 s; the first stdout
    # line arrives in under 2 s.
    def test_09_sweep_answers_before_the_slow_log_write(self):
        self._md("notes.md", self.ERROR_TEXT)
        script = os.path.join(gl_sleepy_tree(os.path.join(self.tmp.name, "slow"), 4), "md_sweep.py")
        seconds, rc, out, err = gl_timed(script, self._stop_hook(), gl_env(self.cfg))
        self.assertNotIn("Traceback", err)
        self.assertEqual(rc, 0, err)
        self.assertEqual(json.loads(out).get("decision"), "block")
        self.assertLess(seconds, 2.0, "the sweep waited for the log write")


# ---------------------------------------------------------------- two writers, one guard.log
#
# Guards: two processes appending to one guard.log at the same time keep every line, each exactly
# once. Each writes APPEND_N lines, so 2 x APPEND_N must land. record() takes a lock around each
# write, so a Windows append cannot overwrite another writer's line. Linux does not lose these
# lines, so a green on Linux proves nothing about the Windows path.
# Two writers are cased: guard_core.record, and the STE gate's logger (lint/_transcript.guard_logger),
# which reaches record through the same locked append. The one-writer case is the control: it must stay green.
APPEND_N = 2000
APPEND_WRITER_RECORD = r'''
import sys
sys.path.insert(0, sys.argv[1])  # the hooks/ folder
import guard_core
tag, n, session = sys.argv[2], int(sys.argv[3]), sys.argv[4]
guard_core.set_log_session(session)
for i in range(n):
    guard_core.record("Bash", "deny", "append-race", "{}-{:05d}".format(tag, i))
'''
APPEND_WRITER_STE = r'''
import sys
sys.path.insert(0, sys.argv[1])  # the lint/ folder: the STE gate's own logger
from _transcript import guard_logger
tag, n, session = sys.argv[2], int(sys.argv[3]), sys.argv[4]
log = guard_logger({"session_id": session})
for i in range(n):
    log("Write", "fixed", "STE007,STE013", "{}-{:05d}.md".format(tag, i), "fixed=2")
'''


class GuardLogAppendRaceTests(unittest.TestCase):
    """Concurrent appends to one guard.log: every line written is kept, once, whole."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = os.path.join(self.tmp.name, "cfg")
        os.makedirs(self.cfg)

    def tearDown(self):
        self.tmp.cleanup()

    def _run_writers(self, source, lib, tags):
        """Start one writer process per tag at the same time. Each writes APPEND_N lines to self.cfg."""
        writer = os.path.join(self.tmp.name, "writer.py")
        with open(writer, "w", encoding="utf-8") as handle:
            handle.write(source)
        env = dict(os.environ, CLAUDE_CONFIG_DIR=self.cfg)
        procs, outs = [], []
        for tag in tags:
            out = open(os.path.join(self.tmp.name, "out-%s.txt" % tag), "w", encoding="utf-8")
            outs.append(out)
            procs.append(subprocess.Popen([sys.executable, writer, lib, tag, str(APPEND_N), GL_SESSION],
                                          env=env, stdout=out, stderr=subprocess.STDOUT))
        codes = []
        for proc in procs:
            try:
                codes.append(proc.wait(timeout=120))
            except subprocess.TimeoutExpired:
                proc.kill()
                codes.append(None)
        for out in outs:
            out.close()
        self.writer_text = ""
        for tag in tags:
            with open(os.path.join(self.tmp.name, "out-%s.txt" % tag), encoding="utf-8") as handle:
                self.writer_text += handle.read()[:300]
        return codes

    def _assert_kept_each_once(self, codes, tags, want):
        """`want` is the matched field of every line that must land, in any order."""
        self.assertEqual(codes, [0] * len(tags), "a writer failed: " + self.writer_text)
        rows = gl_lines(self.cfg) or []
        self.assertEqual(len(rows), len(want), "kept %d of %d written" % (len(rows), len(want)))
        got = sorted(gl_fields(row)[4] for row in rows)  # six fields each, or this names the row
        self.assertEqual(len(set(got)), len(got), "a line was doubled")
        self.assertTrue(got == sorted(want), "missing %d line(s)" % len(set(want) - set(got)))

    def test_two_record_writers_keep_every_line(self):
        # Rows: one writer is the control, so a red elsewhere is the race. Two
        # guard_core.record writers are the one append every guard, gate and sweep line goes
        # through. Two STE gate loggers reach record through the same locked append.
        rows = [
            # Catches: a lone writer loses or doubles a line (control).
            (APPEND_WRITER_RECORD, HOOKS, ("a",), ""),
            # Catches: two guard_core.record writers lose or double a line.
            (APPEND_WRITER_RECORD, HOOKS, ("a", "b"), ""),
            # Catches: two STE gate loggers lose or double a line.
            (APPEND_WRITER_STE, HERE, ("a", "b"), ".md fixed=2"),
        ]
        for source, lib, tags, suffix in rows:
            with self.subTest(tags=tags, suffix=suffix):
                self.cfg = tempfile.mkdtemp(dir=self.tmp.name)  # a fresh log per row
                codes = self._run_writers(source, lib, tags)
                want = ["%s-%05d%s" % (tag, i, suffix) for tag in tags for i in range(APPEND_N)]
                self._assert_kept_each_once(codes, tags, want)

    def _record_with_lock_error(self, errno_value):
        """Run guard_core.record() in this process while every lock call raises OSError(errno_value).
        Return (guard_core module, seconds record() took, the guard.log lines). No process stalls."""
        spec = importlib.util.spec_from_file_location("guard_core_probe",
                                                      os.path.join(HOOKS, "guard_core.py"))
        core = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(core)
        lock_call = "msvcrt.locking" if os.name == "nt" else "fcntl.flock"
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": self.cfg}), \
                mock.patch(lock_call, side_effect=OSError(errno_value, "lock refused")):
            started = time.monotonic()
            core.record("Bash", "deny", "lock-probe", "errno-%d" % errno_value)
            seconds = time.monotonic() - started
        return core, seconds, gl_lines(self.cfg) or []

    def test_lock_error_that_is_not_contention_returns_at_once(self):
        # Guards: a lock error that is not contention (EINVAL, errno 22, here) returns at once and keeps
        # the line. Waiting out LOG_LOCK_WAIT buys nothing when no other writer holds the lock.
        _core, seconds, rows = self._record_with_lock_error(errno.EINVAL)
        self.assertLess(seconds, 0.5, "record() waited %.2f s on errno 22" % seconds)
        self.assertEqual(len(rows), 1, "the line was not kept: %r" % rows)
        self.assertEqual(rows[0].split("\t")[4], "errno-22", rows[0])

    def test_contention_lock_error_waits_then_writes(self):
        # Green pin: a lock held by another writer still gets the full wait, then the line lands.
        contention = errno.EACCES if os.name == "nt" else errno.EAGAIN
        core, seconds, rows = self._record_with_lock_error(contention)
        self.assertGreaterEqual(seconds, core.LOG_LOCK_WAIT * 0.9,
                                "record() did not wait out a contended lock: %.2f s" % seconds)
        self.assertEqual(len(rows), 1, "the line was not kept: %r" % rows)
        self.assertEqual(rows[0].split("\t")[4], "errno-%d" % contention, rows[0])


if __name__ == "__main__":
    unittest.main()
