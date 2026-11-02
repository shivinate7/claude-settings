#!/usr/bin/env python3
"""Fixture tests for report_guard.py (Stop) and the STE linter, lint/ste_lint.py.

Each test writes a fake transcript JSONL to a temp dir, builds the hook JSON, and runs the
guard as a subprocess, the way Claude Code's Stop hook does. Run with:

    python lint/test_report_guard.py -v
"""
import contextlib
import errno
import importlib.util
import io
import json
import os
import runpy
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT_GUARD = os.path.join(HERE, "report_guard.py")
HOOKS = os.path.join(HERE, "..", "hooks")

sys.path.insert(0, HERE)
sys.path.insert(0, HOOKS)  # guard_core, loaded by path below, imports its sibling modules
import ste_lint  # noqa: E402
import test_call_judge as tcj  # noqa: E402  the model stub and git fixtures (one home)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)

GOOD_REPORT = "> **Done** BUILT abc123\n> **Next** ship it"
RUN_FOLDER = None  # made in setUpModule, so an import leaks no folder

# Isolation. Every spawned guard inherits this process's environment (env=None, or a copy
# of os.environ). Point CLAUDE_CONFIG_DIR at a temporary folder for the whole module, so no test
# appends to the user's guard.log. tearDownModule restores the value it found. A test that sets its
# own folder (the config report) still wins.
_ISOLATION = {}


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()  # test-temp-standard: one run folder per run
    _ISOLATION["dir"] = tempfile.TemporaryDirectory()
    _ISOLATION["prev"] = os.environ.get("CLAUDE_CONFIG_DIR")  # None means unset
    os.environ["CLAUDE_CONFIG_DIR"] = _ISOLATION["dir"].name
    stub = tempfile.TemporaryDirectory()
    _ISOLATION["stub"] = stub
    with open(os.path.join(stub.name, "sitecustomize.py"), "w", encoding="utf-8") as f:
        f.write(tcj.STUB_SITE)
    _ISOLATION["env"] = {k: os.environ.get(k) for k in MODEL_ENV}
    os.environ["PYTHONPATH"] = os.pathsep.join(p for p in (stub.name, os.environ.get("PYTHONPATH")) if p)
    os.environ.update(CJ_LOADED_DIR=stub.name, CJ_RECORD=os.path.join(stub.name, "calls.jsonl"),
                      CJ_ANSWER=tcj.ALLOW)
    os.environ.pop("CJ_MODEL_FAIL", None)


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder
    prev = _ISOLATION.pop("prev")
    if prev is None:
        os.environ.pop("CLAUDE_CONFIG_DIR", None)
    else:
        os.environ["CLAUDE_CONFIG_DIR"] = prev
    for key, value in _ISOLATION.pop("env").items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    _ISOLATION.pop("stub").cleanup()
    _ISOLATION.pop("dir").cleanup()


def human(text):
    return {"type": "user", "isSidechain": False, "message": {"role": "user", "content": text}}


def peer_msg(body, stamp=None):
    """A cross-session reply in the shape a real transcript stores: type user, origin.kind peer,
    isMeta true. It lands mid-turn, so it is never the owner's last message."""
    rec = {"type": "user", "isSidechain": False, "isMeta": True,
           "origin": {"kind": "peer", "from": "uds:fixture-pipe", "msg_id": "m-" + body[:8],
                      "name": "peer-cf", "fromSession": "local_fixture", "fromMode": "bypass",
                      "body": body},
           "message": {"role": "user", "content": "Another Claude session sent a message:\n"
                       '<cross-session-message from="uds:fixture-pipe" from-session="local_fixture" '
                       'from-name="peer-cf" from-mode="bypass">%s</cross-session-message>' % body}}
    if stamp:
        rec["timestamp"] = stamp
    return rec


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


# A guard run with the modules named in `block` set to None in sys.modules, so `import <name>` raises
# ImportError in that process. The guard's folder leads sys.path, as it does when run as a script.
BLOCK_IMPORTS_CODE = (
    "import json, os, runpy, sys\n"
    "sys.path.insert(0, os.path.dirname(sys.argv[1]))\n"
    "for name in json.loads(sys.argv[2]):\n"
    "    sys.modules[name] = None\n"
    "sys.argv = sys.argv[1:2]\n"
    "runpy.run_path(sys.argv[0], run_name='__main__')\n"
)


def run_guard(guard, hook, raw_stdin=None, env=None, block=()):
    stdin_text = raw_stdin if raw_stdin is not None else json.dumps(hook)
    argv = [sys.executable, guard]
    if block:
        argv = [sys.executable, "-c", BLOCK_IMPORTS_CODE, guard, json.dumps(list(block))]
    run = subprocess.run(
        argv,
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=15,
        env=env,
    )
    return run


# A hook that has nothing to do for its input must not pay to import the modules that do the
# work: the shell parser (guard), the model caller (decision_watch) and the linter (ste_lint).
# This runs a hook file as __main__ in a fresh process, then reports which of them that process
# imported. The hook's own output comes first, and the PROBE line last.
GUARD_FAMILY = ("guard", "decision_watch", "ste_lint")
IMPORT_PROBE = (
    "import json, runpy, sys\n"
    "try:\n"
    "    runpy.run_path(sys.argv[1], run_name='__main__')\n"
    "except SystemExit:\n"
    "    pass\n"
    "print('PROBE ' + json.dumps([m for m in %r if m in sys.modules]))\n" % (GUARD_FAMILY,)
)


def run_import_probe(script, hook):
    """Return (the hook's stdout, the GUARD_FAMILY modules its process imported)."""
    run = subprocess.run([sys.executable, "-c", IMPORT_PROBE, script], input=json.dumps(hook),
                         capture_output=True, text=True, timeout=15)
    out, mark, tail = run.stdout.rpartition("PROBE ")
    if not mark:
        raise AssertionError("the probe did not finish: %s" % run.stderr[-300:])
    return out, json.loads(tail)


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


class ReportGuardTests(unittest.TestCase):
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
                run = run_guard(REPORT_GUARD, self.hook_for(path))
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
        run = run_guard(REPORT_GUARD, self.hook_for(path))
        out = json.loads(run.stdout)
        self.assertEqual(out.get("decision"), "block")

    def test_04_landed_labels_out_of_order_blocks(self):
        rows = [
            # Catches: labels out of order in a landing turn pass as a report.
            "> **Done** BUILT\n> **Next** ship\n> **Deviations** none",
            # Catches: the same order check misses colon labels.
            "> **Done:** BUILT\n> **Next:** ship\n> **Deviations:** none",
            # Catches: the retired label "Decided by the advisor" (questions-go-to-owner) still passes.
            "> **Done** BUILT abc123\n> **Deviations** none\n> **Decided by the advisor** test names\n> **Next** ship",
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
                run = run_guard(REPORT_GUARD, self.hook_for(path))
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
                run = run_guard(REPORT_GUARD, self.hook_for(path))
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
        run = run_guard(REPORT_GUARD, self.hook_for(path))
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
        run = run_guard(REPORT_GUARD, self.hook_for(path, stop_hook_active=True))
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stdout.strip(), "")

    def test_10_garbage_stdin_no_output(self):
        rows = [
            # Catches: unparseable stdin crashes the guard.
            "not json",
            # Catches: valid JSON that is not an object crashes the guard.
            "[1,2,3]",
        ]
        for raw in rows:
            with self.subTest(raw=raw):
                run = run_guard(REPORT_GUARD, None, raw_stdin=raw)
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
        run = run_guard(REPORT_GUARD, self.hook_for(path))
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
        run = run_guard(REPORT_GUARD, self.hook_for(path))
        self.assertEqual(run.returncode, 0)
        out = json.loads(run.stdout)
        self.assertEqual(out.get("decision"), "block")

    def test_52_prose_above_report_after_a_question_passes(self):
        rows = [
            # Catches: prose above a good report after a question blocks it.
            ("why does it only fire sometimes?",
             "The guard fires on a landing turn only.\n\n" + GOOD_REPORT),
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
                run = run_guard(REPORT_GUARD, self.hook_for(path))
                self.assertEqual(run.returncode, 0)
                self.assertEqual(run.stdout.strip(), "")

    def test_58_quoted_git_commit_in_probe_list_passes(self):
        # A read-only Bash call quoting a probe list, 'git commit -q -m x' 'git push --quiet',
        # landed nothing, so the guard must not demand a report. The words sit inside single
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
                run = run_guard(REPORT_GUARD, self.hook_for(path))
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
        run = run_guard(REPORT_GUARD, self.hook_for(path))
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
                run = run_guard(REPORT_GUARD, self.hook_for(path))
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
        run = run_guard(REPORT_GUARD, self.hook_for(path))
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
                run = run_guard(REPORT_GUARD, self.hook_for(path))
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
        run = run_guard(REPORT_GUARD, self.hook_for(path))
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
        run = run_guard(REPORT_GUARD, self.hook_for(path))
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
        run = run_guard(REPORT_GUARD, self.hook_for(path))
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
        run = run_guard(REPORT_GUARD, self.hook_for(path))
        out = json.loads(run.stdout)
        self.assertEqual(out.get("decision"), "block")

    def test_67_every_github_landing_tool_with_no_report_blocks(self):
        # Pinned by hand, not read from report_guard.LANDING_TOOLS: an emptied set must fail here.
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
                run = run_guard(REPORT_GUARD, self.hook_for(path))
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
            run = run_guard(REPORT_GUARD, self.hook_for(path))
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
        run = run_guard(REPORT_GUARD, self.hook_for(path))
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
            run = run_guard(REPORT_GUARD, hook)
            self.assertEqual(run.returncode, 0, event)
            self.assertEqual(run.stdout.strip(), "", event)

    def test_70_ignored_input_imports_no_guard_family_module(self):
        idle = write_transcript([human("look"), tool_use_msg("Read", {"file_path": "x"}),
                                 tool_result_msg(), assistant_text("done")], self.tmp.name)
        rows = [
            # Catches: a hook registered on another event imports the shell parser and the linter.
            ("event other than Stop", {"hook_event_name": "PreToolUse", "transcript_path": idle}),
            # Catches: a rewrite turn, which the guard never judges, imports them.
            ("stop_hook_active", {"hook_event_name": "Stop", "transcript_path": idle,
                                  "stop_hook_active": True}),
            # Catches: a Stop with no transcript to read imports them.
            ("no transcript", {"hook_event_name": "Stop"}),
            # Catches: an idle turn with no shell tool use imports a shell parser it never calls.
            ("idle turn", {"hook_event_name": "Stop", "transcript_path": idle}),
        ]
        for label, hook in rows:
            with self.subTest(label):
                out, imported = run_import_probe(REPORT_GUARD, hook)
                self.assertEqual(out.strip(), "", "the input was not ignored")
                self.assertEqual(imported, [], "imported before it had work to do")

    def test_71_commit_then_peer_reply_then_stop_with_no_report_blocks(self):
        # Catches: a peer reply that lands mid-turn is read as the owner's last message, so the
        # commit before it falls outside the turn and the missing report goes unflagged.
        records = [
            human("do the task"),
            tool_use_msg("Bash", {"command": "git commit -m x"}),
            tool_result_msg(),
            peer_msg("Answer: yes, rename it."),
            assistant_text("Renamed it and committed."),
        ]
        path = write_transcript(records, self.tmp.name)
        run = run_guard(REPORT_GUARD, self.hook_for(path))
        self.assertNotEqual(run.stdout.strip(), "", "the guard stayed silent on a landed turn")
        self.assertEqual(json.loads(run.stdout).get("decision"), "block")

    def test_72_commit_then_peer_reply_then_stop_with_good_report_passes(self):
        # Catches: counting the commit once the peer reply is skipped also blocks a good report.
        records = [
            human("do the task"),
            tool_use_msg("Bash", {"command": "git commit -m x"}),
            tool_result_msg(),
            peer_msg("Answer: yes, rename it."),
            assistant_text(GOOD_REPORT),
        ]
        path = write_transcript(records, self.tmp.name)
        run = run_guard(REPORT_GUARD, self.hook_for(path))
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stdout.strip(), "")

    def test_73_peer_reply_does_not_move_the_turn_start_in_either_direction(self):
        rows = [
            # Pin (green before the fix): a peer record before the commit never hides the commit.
            ("peer before commit", [human("go"), peer_msg("Answer: ok."),
                                    tool_use_msg("Bash", {"command": "git commit -m x"}),
                                    tool_result_msg(), assistant_text("done")], "block"),
            # Pin (green before the fix): a commit from an earlier turn never counts because a peer
            # reply came after the new human message.
            ("earlier turn commit", [human("land it"), tool_use_msg("Bash", {"command": "git commit -m a"}),
                                     tool_result_msg(), human("what is the log"),
                                     peer_msg("Answer: ok."), tool_use_msg("Bash", {"command": "git log -1"}),
                                     tool_result_msg(), assistant_text("no report needed")], "pass"),
        ]
        for label, records, want in rows:
            with self.subTest(label), tempfile.TemporaryDirectory() as tmp:
                path = write_transcript(records, tmp)
                run = run_guard(REPORT_GUARD, self.hook_for(path))
                self.assertEqual(run.returncode, 0)
                if want == "block":
                    self.assertNotEqual(run.stdout.strip(), "", "the guard stayed silent on a landed turn")
                    self.assertEqual(json.loads(run.stdout).get("decision"), "block")
                else:
                    self.assertEqual(run.stdout.strip(), "")


class DoneFormatAndCiteTests(unittest.TestCase):
    """reports-done-format and speak-cite-id-plus-gloss, both in report_guard.py's Stop hook."""

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
        run = run_guard(REPORT_GUARD, hook)
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
        self.assert_blocked("> **Done** BUILT the guard\n> **Next** none", "BUILT, RECORDED, or OTHER")

    def test_df_red_one_bullet_lacks_ref_blocks(self):
        rows = [
            # Catches: a RECORDED bullet with no ref passes.
            ("> **Done**\n> - BUILT guard, PR #5\n> - RECORDED the ruling\n> **Next** none",
             "RECORDED the ruling"),
            # Catches: a bullet with no kind word passes.
            ("> **Done**\n> - swept the stale branches\n> **Next** none", "swept the stale"),
            # Catches: a top bullet after sub-bullets is not checked.
            ("> **Done**\n> - BUILT guard, PR #5\n>   - detail\n> - RECORDED ruling\n> **Next** none",
             "RECORDED ruling"),
            # Catches: a lead-in line with a kind word hides a bullet with no ref.
            ("> **Done** BUILT it:\n> - BUILT guard, PR #5\n> **Next** none", "BUILT it"),
        ]
        for reply, needle in rows:
            with self.subTest(reply=reply):
                self.assert_blocked(reply, needle)

    def test_df_allowed_other_needs_no_ref(self):
        self.assert_allowed("> **Done**\n> - BUILT guard, PR #5\n> - OTHER swept the stale branches\n> **Next** none")

    def test_df_allowed_inline_with_pr(self):
        self.assert_allowed("> **Done** BUILT the guard, PR #226\n> **Next** none")

    def test_df_allowed_bullets_with_sha_and_pr_url(self):
        self.assert_allowed(
            "> **Done**\n> - BUILT guard, abc1234\n"
            "> - RECORDED ruling, https://github.com/o/r/pull/12\n> **Next** none")

    def test_df_false_alarm_ref_on_wrapped_line_passes(self):
        self.assert_allowed("> **Done**\n> - BUILT the guard and\n>   its tests, commit abc1234\n> **Next** none")

    def test_df_false_alarm_deviations_text_not_read_as_done(self):
        self.assert_allowed("> **Done** BUILT guard, PR #226\n> **Deviations** none of the kind words here")

    # speak-cite-id-plus-gloss
    def test_cite_red_bare_d_id_blocks(self):
        rows = [
            # Catches: a bare D-id in prose after "Per" passes.
            ("Per D12 this is fine.\n\n> **Done** BUILT guard, PR #226\n> **Next** none", "'D12'"),
            # Catches: a bare D-id inside the report body passes.
            ("> **Done** BUILT guard, PR #226\n> **Next** follow D258 next", "'D258'"),
            # Catches: a gloss-like phrase after a bare D-id hides the id.
            ("Per D12 and more.\n\n> **Done** BUILT guard, PR #226\n> **Next** none", "'D12'"),
        ]
        for reply, needle in rows:
            with self.subTest(reply=reply):
                self.assert_blocked(reply, needle)

    def test_cite_red_bare_decision_number_blocks(self):
        self.assert_blocked("See decision 136.\n\n> **Done** BUILT guard, PR #226\n> **Next** none", "decision 136")

    def test_cite_allowed_id_plus_gloss(self):
        rows = [
            # Catches: false alarm on an id followed by its gloss.
            "Per D12, short titles for records, this holds.\n\n> **Done** BUILT guard, PR #226\n> **Next** none",
            # Catches: false alarm on a gloss in parentheses before the id.
            "Short titles for records (D12) hold.\n\n> **Done** BUILT guard, PR #226\n> **Next** none",
        ]
        for reply in rows:
            with self.subTest(reply=reply):
                self.assert_allowed(reply)

    def test_cite_false_alarm_pr_link_sha_and_version(self):
        self.assert_allowed(
            "Merged https://github.com/o/r/pull/218 and [D12](https://x/y), sha d1234567890abcdef, "
            "version v1.2.3, decision 1.2 notes, and PR #218.\n\n"
            "> **Done** BUILT guard, PR #218\n> **Next** none")

    def test_cite_false_alarm_code_span_and_path(self):
        self.assert_allowed(
            "The heading `## D012` is refused, see decisions/D258-slug.md.\n\n"
            "> **Done** BUILT guard, PR #226\n> **Next** none")

    def test_cite_false_alarm_not_a_report_turn(self):
        records = [human("what is D12?"), assistant_text("D12 is a record.")]
        path = write_transcript(records, self.tmp.name)
        hook = {"hook_event_name": "Stop", "transcript_path": path, "stop_hook_active": False}
        self.assertEqual(run_guard(REPORT_GUARD, hook).stdout.strip(), "")

    # review fixes
    def test_df_red_facade_is_not_a_sha(self):
        self.assert_blocked("> **Done** BUILT facade\n> **Next** none", "BUILT facade")

    def test_df_allowed_sub_bullets_are_details(self):
        self.assert_allowed(
            "> **Done**\n> - BUILT guard, PR #5\n>   - touched the parser\n>   - no ref here\n> **Next** none")

    def test_df_allowed_lead_in_text_with_bullets_is_not_an_item(self):
        self.assert_allowed("> **Done** two items:\n> - BUILT guard, PR #5\n> - OTHER swept, abc1234\n> **Next** none")

    def test_cite_allowed_more_gloss_shapes(self):
        for lead in ("D12 = short titles for records", "D12 -- short titles for records",
                     "D12 says short titles win", "Short titles ruling, D12"):
            self.assert_allowed("Per " + lead + " here.\n\n> **Done** BUILT guard, PR #226\n> **Next** none")

    def test_cite_false_alarm_cell_range_and_vitamin(self):
        self.assert_allowed("Sum A1:D12 and take vitamin D3 daily, or D12:F20.\n\n"
                            "> **Done** BUILT guard, PR #226\n> **Next** none")

    def test_cite_and_done_block_once_with_both_reasons(self):
        out = self.verdict("Per D12.\n\n> **Done** BUILT guard\n> **Next** none")
        self.assertIn("BUILT, RECORDED, or OTHER", out["reason"])
        self.assertIn("'D12'", out["reason"])

    def test_df_cite_quiet_on_rewrite(self):
        records = [human("x"), tool_use_msg("Bash", {"command": "git commit -m x"}), tool_result_msg(),
                   assistant_text("Per D12.\n\n> **Done** BUILT guard\n> **Next** none")]
        path = write_transcript(records, self.tmp.name)
        hook = {"hook_event_name": "Stop", "transcript_path": path, "stop_hook_active": True}
        self.assertEqual(run_guard(REPORT_GUARD, hook).stdout.strip(), "")


class DoneNamesModelsTests(unittest.TestCase):
    """reports-done-names-models, in report_guard.py's Stop hook."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def verdict(self, reply, spawns, denied=()):
        records = [human("do the task")]
        for spawn in spawns:
            records += [tool_use_msg("Agent", spawn), tool_result_msg()]
        for spawn in denied:
            use = tool_use_msg("Agent", spawn)
            use["message"]["content"][0]["id"] = "tu_denied"
            result = tool_result_msg("tu_denied")
            result["message"]["content"][0]["is_error"] = True
            records += [use, result]
        records += [tool_use_msg("Bash", {"command": "git commit -m x"}), tool_result_msg(),
                    assistant_text(reply)]
        path = write_transcript(records, self.tmp.name)
        hook = {"hook_event_name": "Stop", "transcript_path": path, "stop_hook_active": False}
        env = dict(os.environ, CLAUDE_CODE_SUBAGENT_MODEL="sonnet")
        run = run_guard(REPORT_GUARD, hook, env=env)
        self.assertEqual(run.returncode, 0)
        return json.loads(run.stdout) if run.stdout.strip() else None

    BUILDER = {"subagent_type": "builder", "prompt": "build it"}
    REVIEWER_R2 = {"subagent_type": "reviewer", "model": "sonnet", "prompt": "Round 2 of 3"}

    def test_dm_red_builder_unnamed_blocks(self):
        out = self.verdict("> **Done** BUILT the guard, PR #5\n> **Next** Unstarted: none", [self.BUILDER])
        self.assertEqual(out["decision"], "block")
        self.assertIn("no model named for builder", out["reason"])

    def test_dm_red_one_of_two_roles_unnamed_blocks(self):
        out = self.verdict("> **Done** BUILT the guard, PR #5 (builder sonnet)\n> **Next** Unstarted: none",
                           [self.BUILDER, self.REVIEWER_R2])
        self.assertIn("no model named for reviewer", out["reason"])

    def test_dm_red_builder_named_opus_ran_sonnet_blocks(self):
        # The builder file has no pin, so the spawn reads CLAUDE_CODE_SUBAGENT_MODEL, sonnet.
        out = self.verdict("> **Done** BUILT the guard, PR #5 (builder opus)\n> **Next** Unstarted: none",
                           [self.BUILDER])
        self.assertIn("'builder opus' matches no builder spawn, which ran sonnet", out["reason"])

    def test_dm_red_reviewer_named_sonnet_ran_file_pin_blocks(self):
        # No model field: the reviewer runs its agents/reviewer.md pin, haiku.
        out = self.verdict("> **Done** BUILT the guard, PR #5 (reviewer sonnet)\n> **Next** Unstarted: none",
                           [{"subagent_type": "reviewer", "prompt": "Round 1 of 3"}])
        self.assertIn("ran haiku", out["reason"])

    def test_dm_green_names_match_spawns(self):
        self.assertIsNone(self.verdict(
            "> **Done** BUILT the guard, PR #5 (builder sonnet, reviewer sonnet)\n> **Next** Unstarted: none",
            [self.BUILDER, self.REVIEWER_R2]))

    def test_dm_green_round3_builder_opus(self):
        self.assertIsNone(self.verdict(
            "> **Done** BUILT the guard, PR #5 (builder opus)\n> **Next** Unstarted: none",
            [{"subagent_type": "builder", "model": "opus", "prompt": "Round 3 of 3"}]))

    def test_dm_red_denied_opus_builder_does_not_back_opus_name(self):
        out = self.verdict("> **Done** BUILT the guard, PR #5 (builder opus)\n> **Next** Unstarted: none",
                           [self.BUILDER], denied=[{"subagent_type": "builder", "model": "opus"}])
        self.assertIn("'builder opus' matches no builder spawn, which ran sonnet", out["reason"])

    def test_dm_false_alarm_denied_spawn_then_solo_passes(self):
        self.assertIsNone(self.verdict("> **Done** BUILT the guard, PR #5\n> **Next** Unstarted: none", [],
                                       denied=[{"subagent_type": "builder", "model": "opus"}]))

    def test_dm_false_alarm_other_name_forms_pass(self):
        for done in ("(builder and reviewer sonnet)", "(builder: sonnet, reviewer (sonnet))",
                     "(builder, reviewer sonnet)"):
            self.assertIsNone(self.verdict(
                "> **Done** BUILT the guard, PR #5 " + done + "\n> **Next** Unstarted: none",
                [self.BUILDER, self.REVIEWER_R2]), done)

    def test_dm_false_alarm_no_agent_passes(self):
        self.assertIsNone(self.verdict("> **Done** BUILT the guard, PR #5\n> **Next** Unstarted: none", []))

    def test_dm_false_alarm_search_only_spawns_pass(self):
        # An Explore search or a Plan spawn builds and reviews nothing, so Done names no model.
        self.assertIsNone(self.verdict(
            "> **Done** BUILT the guard, PR #5\n> **Next** Unstarted: none",
            [{"subagent_type": "Explore", "prompt": "find x"}, {"subagent_type": "Plan", "prompt": "plan"}]))


class UnstartedItemsTests(unittest.TestCase):
    """reports-name-unstarted-items, in report_guard.py's Stop hook."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def verdict(self, reply, spawns):
        records = [human("do the task")]
        for spawn in spawns:
            records += [tool_use_msg("Agent", spawn), tool_result_msg()]
        records += [tool_use_msg("Bash", {"command": "git commit -m x"}), tool_result_msg(),
                    assistant_text(reply)]
        path = write_transcript(records, self.tmp.name)
        hook = {"hook_event_name": "Stop", "transcript_path": path, "stop_hook_active": False}
        env = dict(os.environ, CLAUDE_CODE_SUBAGENT_MODEL="sonnet")
        run = run_guard(REPORT_GUARD, hook, env=env)
        self.assertEqual(run.returncode, 0)
        return json.loads(run.stdout) if run.stdout.strip() else None

    BUILDER = {"subagent_type": "builder", "prompt": "build it"}
    DONE = "> **Done** BUILT the guard, PR #5 (builder sonnet)\n"

    def test_un_red_builder_turn_without_line_blocks(self):
        rows = [
            # Catches: a builder turn whose Next names no unstarted items passes.
            self.DONE + "> **Next** merge the batch",
            # Catches: the word alone, with no colon, is read as the line.
            self.DONE + "> **Next** Unstarted items wait on the batch",
            # Catches: the line outside the report blockquote counts.
            "Unstarted: none\n\n" + self.DONE + "> **Next** merge the batch",
        ]
        for reply in rows:
            with self.subTest(reply=reply):
                out = self.verdict(reply, [self.BUILDER])
                self.assertEqual(out["decision"], "block")
                self.assertIn("Unstarted guard", out["reason"])

    def test_un_green_line_forms_pass(self):
        rows = [
            self.DONE + "> **Next** Unstarted: none",
            self.DONE + "> **Next**\n> - merge the batch\n> - Unstarted: c41, the lint lane, waits on the brake",
            self.DONE + "> **Next** merge the batch\n> Unstarted: none",
            self.DONE + "> **Next:** Unstarted: none",
            self.DONE + "> **Next** merge the batch; Unstarted: none",
            self.DONE + "> **Next** unstarted: none",
        ]
        for reply in rows:
            with self.subTest(reply=reply):
                self.assertIsNone(self.verdict(reply, [self.BUILDER]))

    def test_un_false_alarm_no_builder_passes(self):
        rows = [
            # Catches: a solo turn, or one that spawned only a reviewer, must name unstarted items.
            ([], "> **Done** BUILT the guard, PR #5\n> **Next** none"),
            ([{"subagent_type": "reviewer", "model": "sonnet", "prompt": "Round 2 of 3"}],
             "> **Done** BUILT the guard, PR #5 (reviewer sonnet)\n> **Next** none"),
        ]
        for spawns, reply in rows:
            with self.subTest(reply=reply):
                self.assertIsNone(self.verdict(reply, spawns))


class NoResendTests(unittest.TestCase):
    """A report guard never makes a session send its whole report twice (roadmap c101)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    BUILDER = {"subagent_type": "builder", "prompt": "build it"}

    def verdict(self, reply, spawns=(), stop_hook_active=False):
        records = [human("do the task")]
        for spawn in spawns:
            records += [tool_use_msg("Agent", spawn), tool_result_msg()]
        records += [tool_use_msg("Bash", {"command": "git commit -m x"}), tool_result_msg(),
                    assistant_text(reply)]
        path = write_transcript(records, self.tmp.name)
        hook = {"hook_event_name": "Stop", "transcript_path": path,
                "stop_hook_active": stop_hook_active}
        env = dict(os.environ, CLAUDE_CODE_SUBAGENT_MODEL="sonnet")
        run = run_guard(REPORT_GUARD, hook, env=env)
        self.assertEqual(run.returncode, 0)
        return json.loads(run.stdout) if run.stdout.strip() else None

    def test_nr_red_each_report_block_asks_for_the_corrected_lines_only(self):
        rows = [
            # Catches: the label-word block asks for the report again.
            ("label words", "> **Done** fixed it in abc123\n> **Next** none", ()),
            # Catches: the model-name block asks for the report again.
            ("model names", "> **Done** BUILT the guard, PR #5\n> **Next** Unstarted: none",
             (self.BUILDER,)),
            # Catches: the Unstarted block asks for the report again.
            ("Unstarted line", "> **Done** BUILT the guard, PR #5 (builder sonnet)\n> **Next** merge",
             (self.BUILDER,)),
            # Catches: the cite-gloss block asks for the report again.
            ("cite gloss", "Per D12.\n\n> **Done** BUILT guard, PR #5\n> **Next** none", ()),
            # Catches: two joined reasons each carry the tail.
            ("label words and cite gloss", "Per D12.\n\n> **Done** fixed it\n> **Next** none", ()),
        ]
        for name, reply, spawns in rows:
            with self.subTest(block=name):
                out = self.verdict(reply, spawns)
                self.assertEqual(out["decision"], "block")
                reason = out["reason"].lower()
                self.assertIn("post only the corrected lines", reason)
                self.assertIn("never send the report again", reason)
                self.assertNotIn("send the report now", reason)
                self.assertEqual(reason.count("post only the corrected lines"), 1)

    def test_nr_missing_report_block_keeps_the_reply(self):
        out = self.verdict("All done.")
        self.assertIn("Do not write it again.", out["reason"])
        self.assertNotIn("post only the corrected lines", out["reason"].lower())

    def test_nr_missing_report_with_bare_cite_never_forbids_the_report(self):
        # Catches: the block asks for the report and also says never send it.
        out = self.verdict("Per D12.\n\nAll done.")
        self.assertIn("'D12'", out["reason"])
        self.assertIn("Send the report now", out["reason"])
        self.assertNotIn("never send the report again", out["reason"].lower())

    def test_nr_correction_only_follow_up_passes(self):
        # The follow-up holds only the corrected lines, with no report. It runs as a rewrite.
        for reply in ("Correction: the first Done line is OTHER, and the builder ran sonnet.",
                      "> **Done** OTHER fixed it in abc123 (builder sonnet)"):
            with self.subTest(reply=reply):
                self.assertIsNone(self.verdict(reply, (self.BUILDER,), stop_hook_active=True))


class RewriteAfterMissingReportTests(unittest.TestCase):
    """The rewrite after a missing-report block is checked once for model names and the Unstarted line."""

    BUILDER = {"subagent_type": "builder", "prompt": "build it"}
    GOOD = "> **Done** BUILT the guard, PR #5 (builder sonnet)\n> **Next** Unstarted: none"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.sid = "rw-%d" % id(self)

    def run_hook(self, records, active):
        path = write_transcript(records, self.tmp.name)
        hook = {"hook_event_name": "Stop", "transcript_path": path, "stop_hook_active": active,
                "session_id": self.sid}
        run = run_guard(REPORT_GUARD, hook, env=dict(os.environ, CLAUDE_CODE_SUBAGENT_MODEL="sonnet"))
        self.assertEqual(run.returncode, 0)
        return json.loads(run.stdout) if run.stdout.strip() else None

    def stop(self, reply, active):
        records = [human("do the task"), tool_use_msg("Agent", self.BUILDER), tool_result_msg(),
                   tool_use_msg("Bash", {"command": "git commit -m x"}), tool_result_msg(),
                   assistant_text(reply)]
        return self.run_hook(records, active)

    def missing_report_block(self):
        out = self.stop("All done.", False)
        self.assertIn("Send the report now", out["reason"])

    def test_rw_red_rewrite_without_unstarted_blocks(self):
        self.missing_report_block()
        out = self.stop("> **Done** BUILT the guard, PR #5 (builder sonnet)\n> **Next** merge", True)
        self.assertEqual(out["decision"], "block")
        self.assertIn("Unstarted guard", out["reason"])
        self.assertIn("post only the corrected lines", out["reason"].lower())

    def test_rw_red_rewrite_with_wrong_model_blocks(self):
        for reply in ("> **Done** BUILT the guard, PR #5 (builder opus)\n> **Next** Unstarted: none",
                      "> **Done** BUILT the guard, PR #5\n> **Next** Unstarted: none"):
            with self.subTest(reply=reply):
                self.missing_report_block()
                out = self.stop(reply, True)
                self.assertEqual(out["decision"], "block")
                self.assertIn("Model-name guard", out["reason"])

    def test_rw_second_rewrite_stays_quiet(self):
        self.missing_report_block()
        bad = "> **Done** BUILT the guard, PR #5 (builder sonnet)\n> **Next** merge"
        self.assertEqual(self.stop(bad, True)["decision"], "block")
        self.assertIsNone(self.stop(bad, True))

    def test_rw_correct_rewrite_passes(self):
        self.missing_report_block()
        self.assertIsNone(self.stop(self.GOOD, True))
        self.assertIsNone(self.stop(self.GOOD, True))

    def test_rw_red_rewrite_keeps_an_unsourced_answered_line_is_refused_again(self):
        # Red then pass. With the report marker set, the rewrite is judged again, so a line that says
        # "answered" with no source is refused again. Without the marker the same line stays quiet
        # (test_an_green_stop_hook_active_stays_quiet). A sourced line in the same rewrite passes.
        self.missing_report_block()
        reply = "Answered: no permission rule can lift it.\n\n" + self.GOOD
        out = self.stop(reply, True)
        self.assertIsNotNone(out, reply)
        self.assertEqual(out.get("decision"), "block")
        self.assertIn("Answered: no permission rule can lift it.", out["reason"])
        self.missing_report_block()
        self.assertIsNone(self.stop("Item 143 answered in chat at 17:25 CST.\n\n" + self.GOOD, True))

    def test_rw_no_prior_missing_report_block_stays_quiet(self):
        bad = "> **Done** BUILT the guard, PR #5\n> **Next** merge"
        self.assertIsNone(self.stop(bad, True))

    def test_rw_correction_block_leaves_no_marker(self):
        # A correction block (report present) must not arm a check on the next rewrite.
        bad = "> **Done** BUILT the guard, PR #5\n> **Next** merge"
        self.assertEqual(self.stop(bad, False)["decision"], "block")
        self.assertIsNone(self.stop(bad, True))

    def test_rw_stale_marker_is_cleared_by_a_later_turn(self):
        # The rewrite never ran, so the marker is stale. A new turn's Stop must clear it.
        self.missing_report_block()
        self.assertIsNone(self.stop(self.GOOD, False))
        bad = "> **Done** BUILT the guard, PR #5\n> **Next** merge"
        self.assertIsNone(self.stop(bad, True))

    def test_rw_feedback_record_counted_as_human_keeps_spawns(self):
        # Assumed shape of the hook's feedback record: a plain user text record after the block.
        self.missing_report_block()
        records = [human("do the task"), tool_use_msg("Agent", self.BUILDER), tool_result_msg(),
                   tool_use_msg("Bash", {"command": "git commit -m x"}), tool_result_msg(),
                   assistant_text("All done."), human("Stop hook feedback: send the report"),
                   assistant_text("> **Done** BUILT the guard, PR #5\n> **Next** merge")]
        out = self.run_hook(records, True)
        self.assertIn("Unstarted guard", out["reason"])


class PickGuardTests(unittest.TestCase):
    """decisions-reach-a-clickable-pick: an Input Needed pick needs the question box or a linked waiting-page item."""

    PAGE = "https://claude.ai/artifact/waitpage1"
    OTHER = "https://claude.ai/artifact/otherrepo9"
    # The line a pick carries in its Input Needed item (rule question-departs): what is on main, and what changes.
    DEPARTS_LINE = "Departs from: lint/report_guard.py pick check — it also needs a Departs from line"
    PICK_BARE = ("> **Done** OTHER read the code\n"
                 "> **Input Needed** Two ways:\n> A (my pick): fold the guard\n> B: add a second hook\n"
                 "> **Next** wait")
    PICK = PICK_BARE.replace("> **Next** wait", "> " + DEPARTS_LINE + "\n> **Next** wait")
    # The page link sits inside the report, on the Next line: a landed turn's report ends the reply.
    PICK_LINKED = PICK.replace("> **Next** wait", "> **Next** wait " + PAGE)
    PICK_BARE_LINKED = PICK_BARE.replace("> **Next** wait", "> **Next** wait " + PAGE)
    FORM_LINES = ["Goal: the stamp check runs in the lint job",
                  "Problem (risk): the pick needs your word",
                  "Based on (read): the report guard reads the Input Needed item"]

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = os.path.join(self.tmp.name, "repo")
        os.makedirs(os.path.join(self.repo, ".git"))
        os.makedirs(os.path.join(self.repo, ".claude"))
        with open(os.path.join(self.repo, ".claude", "layout-extras.json"), "w") as f:
            json.dump({"kinds": {}, "waiting-page": self.PAGE}, f)

    def verdict(self, reply, calls=(), landed=False, repo=None, block=()):
        records = [human("decide")]
        if landed:
            records.append(tool_use_msg("Bash", {"command": "git commit -m x"}))
        for name, inp, side in calls:
            rec = tool_use_msg(name, inp)
            rec["isSidechain"] = side
            records.append(rec)
        records.append(assistant_text(reply))
        path = write_transcript(records, self.tmp.name)
        hook = {"hook_event_name": "Stop", "transcript_path": path, "stop_hook_active": False,
                "cwd": repo or self.repo}
        run = run_guard(REPORT_GUARD, hook, block=block)
        self.assertEqual(run.returncode, 0)
        return json.loads(run.stdout) if run.stdout.strip() else None

    def page_set(self, url=None, collection="items", action="set"):
        return ("ArtifactData", {"action": action, "collection": collection, "url": url or self.PAGE,
                                 "doc_id": "q1"}, False)

    def test_pk_red_pick_with_no_control_blocks(self):
        # Catches: the Oct 27 incident, a pick as report text only, on an unlanded and a landed turn.
        for landed in (False, True):
            with self.subTest(landed=landed):
                out = self.verdict(self.PICK, landed=landed)
                self.assertEqual(out["decision"], "block")
                self.assertIn("Pick guard", out["reason"])
                self.assertIn("question box", out["reason"])
                # Catches: the refusal naming the box as allowed only with nothing running.
                self.assertRegex(out["reason"], r"question box[^.]*only with nothing running|"
                                                r"only with nothing running[^.]*question box")

    def test_pk_red_option_forms_block(self):
        rows = [
            "> **Input Needed** A or B: fold it or add a hook?",
            "> **Input Needed** Two ways:\n> 1. fold the guard\n> 2. add a hook",
            "> **Input Needed** Two ways: 1. stack them (my pick). 2. one per file.",
            "> **Input Needed** Is it A or B? A (my pick) keeps the hook.",
            "> **Input Needed**\n> A) fold it\n> B) add a hook",
            "> **Input Needed** Two ways: A (my pick) fold it. B add a hook.",
        ]
        for row in rows:
            with self.subTest(row=row):
                out = self.verdict("> **Done** OTHER read it\n" + row)
                self.assertEqual(out["decision"], "block")

    def test_pk_red_page_write_to_another_repo_blocks(self):
        out = self.verdict(self.PICK + "\n\n" + self.OTHER, [self.page_set(self.OTHER)])
        self.assertIsNotNone(out)

    def test_pk_red_page_write_without_link_in_reply_blocks(self):
        self.assertIsNotNone(self.verdict(self.PICK, [self.page_set()]))

    def test_pk_red_agent_calls_do_not_count(self):
        # An agent's box and write do not count. With no link in the reply, the pick still blocks
        # (decisions-reach-a-clickable-pick).
        calls = [("AskUserQuestion", {}, True), ("ArtifactData", self.page_set()[1], True)]
        self.assertIsNotNone(self.verdict(self.PICK, calls))

    def test_pk_red_pick_with_no_link_blocks_whatever_the_calls(self):
        # With no link in the reply, the pick blocks whatever the calls: another collection, a get, or
        # an items update (decisions-reach-a-clickable-pick).
        for call in (self.page_set(collection="notes"), self.page_set(action="get"),
                     self.page_set(action="update")):
            with self.subTest(call=call):
                self.assertIsNotNone(self.verdict(self.PICK, [call]))

    def test_pk_green_link_passes_whatever_the_calls(self):
        # A reply that holds this repo's waiting page URL passes, whatever ArtifactData calls the
        # turn made (decisions-reach-a-clickable-pick).
        reply = self.PICK + "\n" + self.PAGE
        for calls in ([], [self.page_set(collection="notes")], [self.page_set(action="get")]):
            with self.subTest(calls=calls):
                self.assertIsNone(self.verdict(reply, calls))

    def test_pk_red_unknown_page_only_the_box_passes(self):
        bare = os.path.join(self.tmp.name, "bare")
        os.makedirs(os.path.join(bare, ".git"))
        self.assertIsNotNone(self.verdict(self.PICK + "\n" + self.PAGE, [self.page_set()], repo=bare))
        self.assertIsNone(self.verdict(self.PICK, [("AskUserQuestion", {}, False)], repo=bare))

    def test_pk_green_update_and_batch_writes_pass(self):
        batch = ("ArtifactData", {"action": "batch", "url": self.PAGE, "writes": [
            {"op": "set", "collection": "items", "doc_id": "q1", "data": {}}]}, False)
        other = ("ArtifactData", {"action": "batch", "url": self.PAGE, "writes": [
            {"op": "set", "collection": "notes", "doc_id": "q1", "data": {}}]}, False)
        reply = self.PICK + "\n" + self.PAGE
        self.assertIsNone(self.verdict(reply, [self.page_set(action="update")]))
        self.assertIsNone(self.verdict(reply, [batch]))
        self.assertIsNone(self.verdict(reply, [other]))
        self.assertIsNotNone(self.verdict(self.PICK, [other]))

    def test_pk_green_controls_pass(self):
        self.assertIsNone(self.verdict(self.PICK, [("AskUserQuestion", {}, False)]))
        self.assertIsNone(self.verdict(self.PICK + "\n\nSee " + self.PAGE, [self.page_set()]))

    def assert_pick_blocked(self, reply, repo=None):
        out = self.verdict(reply, repo=repo)
        self.assertIsNotNone(out, "the pick passed")
        self.assertEqual(out["decision"], "block")
        self.assertIn("Pick guard", out["reason"])

    def test_pk_green_reply_links_this_repos_page_with_no_write_passes(self):
        # Chat first, then the page (questions-go-to-owner): the session sends the question to the
        # page's writer, so its reply links the page and it writes nothing itself.
        self.assertIsNone(self.verdict(self.PICK + "\n\nSee " + self.PAGE))

    def test_pk_green_five_minute_wait_names_the_page_with_no_box_passes(self):
        # Chat first, then the page (questions-go-to-owner): after 5 minutes unanswered in chat, the
        # question goes to the page.
        for phrase in ("5 min", "5 minutes", "5-minute", "five minutes"):
            with self.subTest(phrase=phrase):
                reply = ("> **Done** OTHER read the code\n"
                         "> **Input Needed** Two ways. Ask in chat; after %s unanswered it goes to the "
                         "waiting page.\n> A (my pick): fold the guard\n> B: add a second hook\n> "
                         + self.DEPARTS_LINE + "\n> **Next** wait") % phrase
                self.assertIsNone(self.verdict(reply))

    def test_pk_red_wait_needs_both_words_blocks(self):
        # Catches: a 5-minute wait with no page word, and a page word with no 5-minute wait.
        only_wait = ("> **Done** OTHER read the code\n"
                     "> **Input Needed** Two ways. After 5 minutes unanswered I send it on.\n"
                     "> A (my pick): fold the guard\n> B: add a second hook\n> **Next** wait")
        only_page = ("> **Done** OTHER read the code\n"
                     "> **Input Needed** Two ways. I put it on the waiting page.\n"
                     "> A (my pick): fold the guard\n> B: add a second hook\n> **Next** wait")
        for reply in (only_wait, only_page):
            with self.subTest(reply=reply):
                self.assert_pick_blocked(reply)

    def test_pk_red_wait_outside_input_needed_blocks(self):
        # Catches: the 5-minute wait and the page named in Done or Next, not in the Input Needed item.
        in_done = ("> **Done** OTHER read the code; after 5 minutes unanswered it goes to the waiting page.\n"
                   "> **Input Needed** Two ways:\n> A (my pick): fold the guard\n> B: add a second hook\n"
                   "> **Next** wait")
        in_next = ("> **Done** OTHER read the code\n"
                   "> **Input Needed** Two ways:\n> A (my pick): fold the guard\n> B: add a second hook\n"
                   "> **Next** after 5 minutes unanswered, the waiting page.")
        for reply in (in_done, in_next):
            with self.subTest(reply=reply):
                self.assert_pick_blocked(reply)

    def test_pk_red_wait_without_a_waiting_page_blocks(self):
        # Catches: the 5-minute wait and the page words in a repo whose layout gives no waiting page,
        # with no extras file and with an extras file that has no waiting-page key.
        reply = ("> **Done** OTHER read the code\n"
                 "> **Input Needed** Two ways. After 5 minutes unanswered it goes to the waiting page.\n"
                 "> A (my pick): fold the guard\n> B: add a second hook\n> **Next** wait")
        bare = os.path.join(self.tmp.name, "bare")
        os.makedirs(os.path.join(bare, ".git"))
        self.assert_pick_blocked(reply, repo=bare)
        nokey = os.path.join(self.tmp.name, "nokey")
        os.makedirs(os.path.join(nokey, ".git"))
        os.makedirs(os.path.join(nokey, ".claude"))
        with open(os.path.join(nokey, ".claude", "layout-extras.json"), "w") as f:
            json.dump({"kinds": {}}, f)
        self.assert_pick_blocked(reply, repo=nokey)

    def test_pk_red_other_minute_counts_block(self):
        # Catches: the five-minute wait read inside a longer number, such as 15, 25 or 35, or a
        # spelled-out twenty-five or fifty-five.
        for n in ("15 minutes", "25 minutes", "35 minutes", "twenty-five minutes",
                  "twenty five minutes", "fifty-five minutes"):
            with self.subTest(n=n):
                self.assert_pick_blocked(
                    "> **Done** OTHER read the code\n"
                    "> **Input Needed** Two ways. After %s unanswered it goes to the waiting page.\n"
                    "> A (my pick): fold the guard\n> B: add a second hook\n> **Next** wait" % n)

    def test_pk_red_another_repos_link_in_reply_blocks(self):
        # Catches: another repo's waiting page link, with no write, read as this repo's page.
        self.assert_pick_blocked(self.PICK + "\n\nSee " + self.OTHER)

    def test_pk_green_no_false_alarm(self):
        rows = [
            # Catches: a plain ask with no options refused.
            "> **Done** OTHER read it\n> **Input Needed** Should the guard also cover Codex? I wait.\n> **Next** wait",
            # Catches: a quoted earlier answer read as a pick.
            "> **Done** OTHER read it\n> **Input Needed** You picked A on Oct 26; I went with it.\n> **Next** wait",
            "> **Done** OTHER read it\n> **Input Needed** A decision is open. B was the old plan.",
            # Catches: options outside Input Needed read as a pick.
            "> **Done** OTHER two ways: A (my pick) or B\n> **Next**\n> 1. one\n> 2. two",
            # Catches: "X or Y" in a plain ask read as a pick.
            "> **Done** OTHER read it\n> **Input Needed** Does Q or A mode apply?",
            "> **Done** OTHER read it\n> **Input Needed** Rename I or U in the code?",
            "> **Done** OTHER read it\n> **Input Needed** Is X or Y the field?",
            "> **Done** OTHER read it\n> **Input Needed** Is A or B the field?",
            # Catches: numbered separate asks read as options.
            "> **Done** OTHER read it\n> **Input Needed**\n> 1. Approve the cap raise.\n> 2. Confirm the date.",
            # No Input Needed label.
            "> **Done** OTHER read it\n> **Next** wait",
            "plain prose with A or B in it",
        ]
        for row in rows:
            with self.subTest(row=row):
                self.assertIsNone(self.verdict(row))


    # question-departs: a pick in Input Needed says how it departs from main, on the landed and the unlanded turn.
    # The line is judged by question_form, the one home of the rule, whatever the calls and the link.

    def test_dp_red_pick_with_no_departs_line_blocks(self):
        # Catches: a pick with a box or a link and no Departs from line, which the form never judges.
        for landed in (False, True):
            for calls, reply in (([("AskUserQuestion", {}, False)], self.PICK_BARE),
                                 ([], self.PICK_BARE_LINKED)):
                with self.subTest(landed=landed, control=calls or "link"):
                    out = self.verdict(reply, calls, landed=landed)
                    self.assertIsNotNone(out, "the pick passed with no Departs from line")
                    self.assertEqual(out["decision"], "block")
                    self.assertRegex(out["reason"], r"(?i)departs from")

    def test_dp_red_bad_line_blocks(self):
        # Catches: an empty line, a side left empty, no separator, and a line that restates main.
        rows = ("> Departs from:",
                "> Departs from: lint/report_guard.py pick check —",
                "> Departs from: — the check reads the box",
                "> Departs from: lint/report_guard.py pick check",
                "> Departs from: agent-model-cap — Opus above the row stays the existing ask")
        for line in rows:
            for landed in (False, True):
                with self.subTest(line=line, landed=landed):
                    reply = self.PICK_BARE.replace("> **Next** wait", line + "\n> **Next** wait")
                    out = self.verdict(reply, [("AskUserQuestion", {}, False)], landed=landed)
                    self.assertIsNotNone(out, "the pick passed with a line that is not a departure")
                    self.assertEqual(out["decision"], "block")
                    self.assertRegex(out["reason"], r"(?i)departs from")

    def test_dp_red_line_outside_input_needed_blocks(self):
        # Catches: a Departs from line in Done or Next, not in the Input Needed item the pick sits in.
        in_done = self.PICK_BARE.replace("> **Input Needed**", "> " + self.DEPARTS_LINE + "\n> **Input Needed**")
        in_next = self.PICK_BARE + "\n> " + self.DEPARTS_LINE
        for reply in (in_done, in_next):
            with self.subTest(reply=reply):
                out = self.verdict(reply, [("AskUserQuestion", {}, False)])
                self.assertIsNotNone(out, "the pick passed with its line outside Input Needed")
                self.assertEqual(out["decision"], "block")

    def test_dp_green_valid_line_passes(self):
        # Catches: a valid line refused, on either turn, with the box or the link, and with a hyphen separator.
        hyphen = self.PICK_BARE.replace("> **Next** wait",
                                        "> Departs from: lint/report_guard.py pick check - it also needs a line\n"
                                        "> **Next** wait")
        for landed in (False, True):
            with self.subTest(landed=landed):
                self.assertIsNone(self.verdict(self.PICK, [("AskUserQuestion", {}, False)], landed=landed))
                self.assertIsNone(self.verdict(self.PICK_LINKED, [self.page_set()], landed=landed))
        self.assertIsNone(self.verdict(hyphen, [("AskUserQuestion", {}, False)]))

    def test_dp_green_no_pick_needs_no_line(self):
        # Catches: an Input Needed item with no pick refused for its missing line (out of scope).
        rows = ("> **Done** OTHER read it\n> **Input Needed** Should the guard also cover Codex? I wait.\n> **Next** wait",
                "> **Done** OTHER read it\n> **Input Needed** You picked A on Oct 26; I went with it.\n> **Next** wait")
        for row in rows:
            for landed in (False, True):
                with self.subTest(row=row, landed=landed):
                    self.assertIsNone(self.verdict(row, landed=landed))

    def test_dp_one_predicate_for_the_report_and_the_chat_box(self):
        # Catches: a report copy of the rule that judges a line the chat box does not. Both read question_form.
        import question_form  # the one home of the rule (hooks/ is on sys.path)
        bad = ["> Departs from:", "> Departs from: agent-model-cap — Opus above the row stays the existing ask"]
        for line in bad:
            with self.subTest(line=line):
                reply = self.PICK_BARE.replace("> **Next** wait", line + "\n> **Next** wait")
                out = self.verdict(reply, [("AskUserQuestion", {}, False)])
                box = {"questions": [{"question": "\n".join(self.FORM_LINES + [line[2:]]), "header": "Ship",
                                      "multiSelect": False,
                                      "options": [{"label": "Keep it", "description": "Gain: a. Lose: b."},
                                                  {"label": "Drop it", "description": "Gain: c. Lose: d."}]}]}
                self.assertEqual(question_form.chat_hit(box)[0], "question-departs")
                self.assertIsNotNone(out, "the report passed a line the chat box refuses")
        good = "> " + self.DEPARTS_LINE
        self.assertIsNone(self.verdict(self.PICK_BARE.replace("> **Next** wait", good + "\n> **Next** wait"),
                                       [("AskUserQuestion", {}, False)]))

    def test_dp_no_copy_the_report_imports_question_form(self):
        # A presence check only: the verdict cases above pin the behaviour. The report reads the form's
        # predicate by import, so one edit to question_form moves both routes.
        with open(REPORT_GUARD, encoding="utf-8") as f:
            source = f.read()
        self.assertRegex(source, r"(?m)^\s*(?:import question_form|from question_form import)")

    def test_dp_import_failure_keeps_the_pick_refusal(self):
        # Catches: question_form cannot import, so the Departs from check raises. On the unlanded turn the
        # pick refusal and that check share one try, so the error drops the pick refusal too. The Departs
        # from check fails open: no Departs-from reason prints, and the pick refusal still does.
        for label, reply in (("valid line", self.PICK), ("no line", self.PICK_BARE)):
            for landed in (False, True):
                with self.subTest(line=label, landed=landed):
                    out = self.verdict(reply, landed=landed, block=("question_form",))
                    self.assertIsNotNone(out, "the pick passed with question_form unable to import")
                    self.assertEqual(out["decision"], "block")
                    self.assertIn("Pick guard", out["reason"])
                    self.assertNotIn("Departs-from guard", out["reason"])

    def test_dp_green_line_forms_in_input_needed_pass(self):
        # Catches: a Departs from line written as a bullet or a bold label refused as missing. A bold label
        # reads as a new report label, which ends the Input Needed item at that line.
        text = "lint/report_guard.py pick check — it also needs a Departs from line"
        for line in ("> - Departs from: " + text, "> **Departs from:** " + text, "> * Departs from: " + text):
            for landed in (False, True):
                with self.subTest(line=line, landed=landed):
                    reply = self.PICK_BARE.replace("> **Next** wait", line + "\n> **Next** wait")
                    self.assertIsNone(self.verdict(reply, [("AskUserQuestion", {}, False)], landed=landed))


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
        # The report guard checks this now: when
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
    and six advisory codes are the one exception. Three rules block: STE001, STE011, STE013.
    Six are advisory: STE003, STE007, STE008, STE009, STE015, STE017 are
    warnings that the linter reports and no guard ever blocks on. Each case here proves a rule
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

    def test_errors_are_exactly_the_three_blocking_codes_and_warnings_the_six_advisory_ones(self):
        severities = {code: rule.severity for code, rule in ste_lint.RULES.items()}
        self.assertEqual({c for c, s in severities.items() if s == "error"}, set(ERROR_CODES))
        self.assertEqual({c for c, s in severities.items() if s == "warning"}, set(ADVISORY_CODES))
        self.assertEqual(set(severities), set(ERROR_CODES) | set(ADVISORY_CODES), "a rule has no ruling")


# These errors fail CI's STE lint on changed lines (plain-prose-lint):
ERROR_CODES = ("STE001", "STE011", "STE013")
# These six are advisory: reported as warnings, never a failed run.
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


# One input per kept error code: (file suffix, text).
KEPT_SAMPLES = {
    "STE001": (".md", plain_words(31)),
    "STE011": (".md", "In conclusion, the plan works.\n"),
    "STE013": (".md", "This step is not unsafe.\n"),
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
    linter's exit code, not CI."""

    def test_a01_each_advisory_code_is_reported_as_a_warning_and_the_cli_exits_zero(self):
        for code, text in ADVISORY_SAMPLES.items():
            with self.subTest(code=code):
                rc, data = run_lint_cli(text)
                hits = [f for f in data["findings"] if f["code"] == code]
                self.assertTrue(hits, "%s is not reported: %r" % (code, data["findings"]))
                self.assertEqual({f["severity"] for f in hits}, {"warning"})
                self.assertEqual(data["summary"]["error"], 0, data["findings"])
                self.assertEqual(rc, 0)


    def test_a03_all_six_in_one_file_still_pass_the_cli(self):
        text = "\n".join(ADVISORY_SAMPLES.values())
        rc, data = run_lint_cli(text)
        self.assertEqual({f["code"] for f in data["findings"]} & set(ERROR_CODES), set())
        self.assertEqual(rc, 0)
        for code in ADVISORY_CODES:
            with self.subTest(code=code):
                self.assertIn(code, {f["code"] for f in data["findings"]})


    def test_a04_the_advisory_samples_are_what_they_say(self):
        # The samples above hold their code and no error code, so the cases are not vacuous.
        for code, text in ADVISORY_SAMPLES.items():
            with self.subTest(code=code):
                codes = [f.code for f in ste_lint.Linter(dict(ste_lint.DEFAULT_CONFIG)).check_text("t.md", text)]
                self.assertIn(code, codes)
                self.assertEqual(set(codes) & set(ERROR_CODES), set())


class KeptErrorCodesTests(unittest.TestCase):
    """STE001, STE011 and STE013 are errors."""

    def test_k01_each_kept_code_is_an_error_and_the_cli_exits_one(self):
        for code, (suffix, text) in KEPT_SAMPLES.items():
            with self.subTest(code=code):
                rc, data = run_lint_cli(text, suffix)
                hits = [f for f in data["findings"] if f["code"] == code]
                self.assertTrue(hits, "%s is not reported: %r" % (code, data["findings"]))
                self.assertEqual({f["severity"] for f in hits}, {"error"})
                self.assertEqual(rc, 1)


class RemovedUiCodesTests(unittest.TestCase):
    """No label-length cap (STE020) and no UI-escape check (STE021). The icon-and-label rule and
    design review carry label length. CI's STE lint carries the three kept codes."""

    def check(self, path, text):
        return [f.code for f in ste_lint.Linter(dict(ste_lint.DEFAULT_CONFIG)).check_ui(path, text)]

    def test_the_rules_table_has_neither_code(self):
        for code in ("STE020", "STE021"):
            with self.subTest(code=code):
                self.assertNotIn(code, ste_lint.RULES)

    def test_a_long_button_label_or_aria_label_is_clean(self):
        for text in ("const x = <button>Save the file right now</button>;\n",
                     "const x = <label>Your primary email address here</label>;\n",
                     'const x = <input aria-label="Close this dialog window now" />;\n'):
            with self.subTest(text=text):
                self.assertEqual(self.check("a.tsx", text), [])

    def test_an_escape_comment_with_no_reason_is_clean(self):
        for path, text in (("a.tsx", "const x = (\n  // ste-disable-next-line STE011\n  <p>Hello.</p>\n);\n"),
                           ("a.html", "<!-- ste-disable-next-line: brand name -->\n<p>Hello.</p>\n")):
            with self.subTest(path=path):
                self.assertEqual(self.check(path, text), [])

    def test_the_cli_exits_zero_on_a_long_button_label(self):
        rc, data = run_lint_cli("const x = <button>Save the file right now</button>;\n", ".tsx")
        self.assertEqual((rc, data["findings"]), (0, []))


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
    .vue files. A button, label or aria-label has no word cap."""

    def check(self, path, text):
        return ste_lint.Linter(dict(ste_lint.DEFAULT_CONFIG)).check_ui(path, text)

    def codes(self, path, text):
        return [f.code for f in self.check(path, text)]


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
        self.assertEqual(sorted((f.code, f.line) for f in findings), [("STE011", 3)])

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
        text = ("const x = (\n  // ste-disable-next-line STE011: quoted label\n"
                "  <p>In order to save.</p>\n);\n")
        self.assertEqual(self.codes("a.tsx", text), [])

    def test_95_cli_reads_ui_file_as_ui(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "a.tsx")
            with open(path, "w", encoding="utf-8") as f:
                f.write('const msg = "in order to save";\n')
            run = subprocess.run([sys.executable, os.path.join(HERE, "ste_lint.py"),
                                  "--no-color", path], capture_output=True, text=True, timeout=15)
        self.assertEqual(run.returncode, 0, run.stdout)


class UICopyRoundTwoTests(unittest.TestCase):
    """Front-end copy lint: the adverb pairs, code tags, the Vue template scope and parenthesis copy."""

    def check(self, path, text):
        return [f.code for f in ste_lint.Linter(dict(ste_lint.DEFAULT_CONFIG)).check_ui(path, text)]

    def md(self, text):
        return [f.code for f in ste_lint.Linter(dict(ste_lint.DEFAULT_CONFIG)).check_text("t.md", text)]


    # R1 -------------------------------------------------------------------------


    # R2 -------------------------------------------------------------------------


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


    # Finding 9 ------------------------------------------------------------------

    def test_120_paren_copy_is_read(self):
        self.assertEqual(self.check("a.tsx", "const x = <small>(optional) Click on the link in order "
                                             "to go.</small>;\n"), ["STE011", "STE011"])
        self.assertEqual(self.check("a.tsx", "const x = <button>(1) Save it prior to "
                                             "launch</button>;\n"), ["STE011"])

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


class TurnReaderTests(unittest.TestCase):
    """`read_turn` is the tail reader the idle hooks use; the config report reads only this turn."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = os.path.join(self.tmp.name, "repo")
        os.makedirs(self.repo)

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

    def test_the_shared_readers_skip_a_peer_record_as_the_last_human(self):
        # Catches: a peer reply (type user, origin.kind peer, isMeta) taken as the owner's last
        # message, so every Stop hook reads a turn that starts after it.
        import _transcript
        records = [human("q1"), tool_use_msg("Bash", {"command": "git commit -m x"}), tool_result_msg(),
                   peer_msg("Answer: ok.", "2026-10-22T18:00:05.000Z"), assistant_text("done")]
        records[0]["timestamp"] = "2026-10-22T18:00:00.000Z"
        path = write_transcript(records, self.tmp.name)
        self.assertFalse(_transcript.is_last_human(records[3]))
        self.assertTrue(_transcript.is_last_human(records[0]))
        self.assertEqual(_transcript.records_after_last_human(records), records[1:])
        self.assertEqual(_transcript.read_turn(path), (records[0], records[1:]))
        self.assertEqual(_transcript.last_human_epoch(path),
                         _transcript.parse_utc_timestamp("2026-10-22T18:00:00.000Z"))

    def test_read_turn_crosses_a_chunk_boundary(self):
        import _transcript
        big = [human("q")] + [assistant_text("y" * 400) for _ in range(40)]
        path = write_transcript(big, self.tmp.name)
        whole = list(_transcript._lines_backwards(path))
        small = list(_transcript._lines_backwards(path, chunk=300))
        self.assertEqual(whole, small)


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


# ---------------------------------------------------------------- guard.log readers
#
# Used by the append-race cases at the end of this file.

GL_SESSION = "9f2c4e1a-7b3d-4c8e-9a10-5d6e7f8a9b0c"


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


# ---------------------------------------------------------------- two writers, one guard.log
#
# Guards: two processes appending to one guard.log at the same time keep every line, each exactly
# once. Each writes APPEND_N lines, so 2 x APPEND_N must land. record() takes a lock around each
# write, so a Windows append cannot overwrite another writer's line. Linux does not lose these
# lines, so a green on Linux proves nothing about the Windows path.
# The one-writer case is the control: it must stay green.
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
        # guard_core.record writers are the one append every guard line goes through.
        rows = [
            # Catches: a lone writer loses or doubles a line (control).
            (APPEND_WRITER_RECORD, HOOKS, ("a",), ""),
            # Catches: two guard_core.record writers lose or double a line.
            (APPEND_WRITER_RECORD, HOOKS, ("a", "b"), ""),
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


# ------------------------------------------------------------------ relayed questions and option keys
#
# A Stop whose reply holds Input Needed, or a prose line ending in `?` outside code fences, gets one past-ruling model
# call (spec past-rulings, relayed questions). The model is the stub in hooks/test_call_judge.py, set up in setUpModule:
# CJ_ANSWER is its answer, CJ_MODEL_FAIL makes it fail, and every call is recorded. A model error refuses once with the
# Unvetted: remedy; an absent source allows with the stderr notice; question-keys refuses two questions on one key.
MODEL_ENV = ("PYTHONPATH", "CJ_LOADED_DIR", "CJ_RECORD", "CJ_ANSWER", "CJ_MODEL_FAIL")
RELAY = "> **Input Needed** Should the GitHub apps keep their access to claude-settings?"
PROSE_Q = "Should the GitHub apps keep their access to claude-settings?"
DONE_ONLY = "> **Done** OTHER read the audit\n> **Next** wait"
FENCED_Q = "```\nkeep the apps?\n```\n> **Done** OTHER read the audit\n> **Next** wait"
UNVETTED = "Unvetted: the model review could not run, so the owner reads this question unchecked."
REFUSE_APPS = json.dumps({"ok": False, "reason": "past-ruling: %s, 2026-10-28, already decides this." % tcj.APPS_SLUG})
KEYS_SAME = "> **Input Needed** Two questions.\n> a) keep the apps\n> b) remove the apps\n> a) about 2x\n> b) under 80%"
KEYS_DISTINCT = ("> **Input Needed** Two questions.\n> 1a) keep the apps\n> 1b) remove the apps\n"
                 "> 2a) about 2x\n> 2b) under 80%")
KEYS_NOW = "> **Input Needed** Keep the caps?\n> a) about 2x\n> b) under 80%"
KEYS_EARLIER = "> **Input Needed** Keep the apps?\n> a) keep\n> b) remove"


C153_MARK = "c153-5e7a"
C153_SENTENCE = ("Ruling (owner, Oct 28): keep the apps' access to claude-settings as is, because calling into a repo "
                 "is straightforward; revisit if it gets bloated. Marker " + C153_MARK + ".")


class PastRulingRelay(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.record = os.path.join(_ISOLATION["stub"].name, "calls.jsonl")
        self.reset_calls()
        self.decided = tcj.make_repo("relay-decided", decisions={tcj.APPS_SLUG: tcj.APPS_RULING})
        self.bare = tcj.make_repo("relay-bare")
        self.ci = tcj.CI_REPO  # a roadmap ref, so the one git process is the roadmap read

    def reset_calls(self):
        for name in ("calls.jsonl", "git.log"):
            path = os.path.join(_ISOLATION["stub"].name, name)
            if os.path.exists(path):
                os.remove(path)

    def git_starts(self):
        # The git processes the guard spawned, counted by the stub's Popen (hooks/test_call_judge.py).
        path = os.path.join(_ISOLATION["stub"].name, "git.log")
        if not os.path.exists(path):
            return 0
        with open(path, encoding="utf-8") as f:
            return len(f.read().split())

    def model_calls(self):
        if not os.path.exists(self.record):
            return []
        with open(self.record, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def stop(self, repo, reply=None, answer=None, model_fail=False, records=None):
        if records is None:
            records = [human("decide"), assistant_text(reply)]
        path = write_transcript(records, self.tmp.name)
        hook = {"hook_event_name": "Stop", "transcript_path": path, "stop_hook_active": False, "cwd": repo}
        overrides = {"CJ_ANSWER": answer or tcj.ALLOW}
        if model_fail:
            overrides["CJ_MODEL_FAIL"] = "1"
        with mock.patch.dict(os.environ, overrides):
            run = run_guard(REPORT_GUARD, hook)
        self.assertEqual(run.returncode, 0, run.stderr)
        out = json.loads(run.stdout) if run.stdout.strip() else {}
        return out, run.stderr

    @staticmethod
    def reason(out):
        return out.get("reason", "") if out.get("decision") == "block" else ""

    def test_relayed_ruling_refuses_with_the_rule_and_the_ruling(self):
        out, _ = self.stop(self.decided, RELAY, answer=REFUSE_APPS)
        calls = self.model_calls()
        self.assertTrue("past-ruling" in self.reason(out) and tcj.APPS_SLUG in self.reason(out), out)
        self.assertEqual(len(calls), 1)
        self.assertIn(tcj.APPS_RULING, calls[0]["prompt"])

    def test_absent_sources_allow_with_the_unknown_notice(self):
        out, err = self.stop(self.bare, RELAY, answer=tcj.ALLOW)
        self.assertEqual(out, {}, out)
        self.assertIn("past-ruling search unknown:", err)
        self.assertEqual(len(self.model_calls()), 1)

    def test_reply_with_neither_input_needed_nor_a_question_makes_no_call(self):
        out, _ = self.stop(self.ci, DONE_ONLY)
        self.assertEqual(self.model_calls(), [])
        self.assertEqual(self.git_starts(), 0)
        self.assertNotIn("past-ruling", self.reason(out))

    def test_prose_question_triggers_the_check(self):
        self.stop(self.decided, PROSE_Q, answer=tcj.ALLOW)
        calls = self.model_calls()
        self.assertEqual(len(calls), 1)
        self.assertIn(tcj.APPS_RULING, calls[0]["prompt"])

    def test_question_inside_a_code_fence_does_not_trigger(self):
        self.stop(self.decided, FENCED_Q)
        self.assertEqual(self.model_calls(), [])

    def test_model_error_refuses_once_and_an_unvetted_line_passes_without_a_call(self):
        out, _ = self.stop(self.decided, RELAY, model_fail=True)
        self.assertIn("Unvetted:", self.reason(out), out)
        self.assertEqual(len(self.model_calls()), 1)
        self.reset_calls()
        out, _ = self.stop(self.decided, RELAY + "\n> " + UNVETTED, model_fail=True)
        self.assertEqual(out, {}, out)
        self.assertEqual(len(self.model_calls()), 1)

    def test_question_keys_refuse_two_questions_with_the_same_keys(self):
        out, _ = self.stop(self.decided, KEYS_SAME, answer=tcj.ALLOW)
        self.assertIn("question-keys", self.reason(out), out)

    def test_distinct_keys_do_not_trigger_question_keys(self):
        out, _ = self.stop(self.decided, KEYS_DISTINCT, answer=tcj.ALLOW)
        self.assertNotIn("question-keys", self.reason(out), out)

    def test_question_keys_see_an_earlier_reply_since_the_last_human(self):
        records = [human("decide"), assistant_text(KEYS_EARLIER), assistant_text(KEYS_NOW)]
        out, _ = self.stop(self.decided, records=records)
        self.assertIn("question-keys", self.reason(out), out)

    def test_unshown_id_cite_takes_the_unvetted_path(self):
        # Index shape (spec, Nov 1 18:58 CST): a reason citing an id the index did not show is a model error.
        bogus = json.dumps({"ok": False, "reason": "decisions/no-such-record: already decided."})
        out, _ = self.stop(self.decided, RELAY, answer=bogus)
        self.assertIn("Unvetted:", self.reason(out), out)

    def test_a_relayed_question_costs_one_git_process_and_one_model_call(self):
        self.stop(self.ci, RELAY, answer=tcj.ALLOW)
        self.assertEqual(len(self.model_calls()), 1)
        self.assertEqual(self.git_starts(), 1)

    def test_a_prose_question_costs_one_git_process_and_one_model_call(self):
        self.stop(self.ci, PROSE_Q, answer=tcj.ALLOW)
        self.assertEqual(len(self.model_calls()), 1)
        self.assertEqual(self.git_starts(), 1)

    def test_an_unvetted_line_elsewhere_in_the_reply_does_not_skip_the_check(self):
        out, _ = self.stop(self.decided, UNVETTED + "\n" + RELAY, answer=REFUSE_APPS)
        self.assertTrue("past-ruling" in self.reason(out), out)
        self.assertEqual(len(self.model_calls()), 1)

    def test_a_relay_exception_refuses_unvetted_with_a_stderr_line(self):
        # relay_reasons catches an exception and fails open. A hook cwd that is not a path raises inside the relay
        # check, and that must refuse with the Unvetted remedy and a stderr line (owner rulings, Nov 1 19:30 CST).
        path = write_transcript([human("decide"), assistant_text(RELAY)], self.tmp.name)
        hook = {"hook_event_name": "Stop", "transcript_path": path, "stop_hook_active": False, "cwd": 12345}
        with mock.patch.dict(os.environ, {"CJ_ANSWER": tcj.ALLOW}):
            run = run_guard(REPORT_GUARD, hook)
        out = json.loads(run.stdout) if run.stdout.strip() else {}
        self.assertIn("Unvetted:", self.reason(out), out)
        self.assertIn("past-ruling", run.stderr)

    def test_a_stop_hook_active_rewrite_that_keeps_the_ruled_question_is_refused_again(self):
        path = write_transcript([human("decide"), assistant_text(RELAY)], self.tmp.name)
        hook = {"hook_event_name": "Stop", "transcript_path": path, "stop_hook_active": True, "cwd": self.decided}
        with mock.patch.dict(os.environ, {"CJ_ANSWER": REFUSE_APPS}):
            run = run_guard(REPORT_GUARD, hook)
        out = json.loads(run.stdout) if run.stdout.strip() else {}
        self.assertTrue("past-ruling" in self.reason(out), out)
        self.assertEqual(len(self.model_calls()), 1)

    def test_an_earlier_blockquote_question_does_not_hide_the_input_needed_item(self):
        # The c153 replay: an earlier blockquote line ends in "?", then the real Input Needed item asks the ruled question.
        repo = tcj.make_repo("relay-c153", steps={"c153": C153_SENTENCE})
        reply = "> Did the last audit finish?\n> **Input Needed** Should the GitHub apps keep their access to claude-settings?"
        self.stop(repo, reply, answer=tcj.ALLOW)
        calls = self.model_calls()
        self.assertEqual(len(calls), 1)
        self.assertIn(C153_MARK, calls[0]["prompt"])

    def test_a_question_mark_inside_a_prose_line_triggers_the_check(self):
        self.stop(self.decided, "Ship the fix? Say go and I merge.", answer=tcj.ALLOW)
        self.assertEqual(len(self.model_calls()), 1)

    def test_a_question_in_an_earlier_assistant_text_block_triggers_the_check(self):
        records = [human("decide"), assistant_text("Ship the fix?"), assistant_text(DONE_ONLY)]
        self.stop(self.decided, records=records, answer=tcj.ALLOW)
        self.assertEqual(len(self.model_calls()), 1)

    def test_an_unvetted_line_beside_a_prose_question_passes_when_the_model_fails(self):
        # Review round 2: a prose question with no Input Needed item. The Unvetted line beside the question passes it,
        # whether it sits on its own line, in a blockquote, or on the question line.
        beside = ("Should the GitHub apps keep their access to claude-settings?\n" + UNVETTED,
                  "> Should the GitHub apps keep their access to claude-settings?\n> " + UNVETTED,
                  "Should the GitHub apps keep their access to claude-settings? " + UNVETTED)
        for reply in beside:
            self.reset_calls()
            out, _ = self.stop(self.decided, reply, model_fail=True)
            self.assertEqual(out, {}, reply)

    def test_a_second_stop_after_a_peer_message_makes_no_call_for_an_old_question(self):
        # The question was asked on the first Stop. A plain reply after a peer message must not ask it again.
        first = [human("decide"), assistant_text(PROSE_Q)]
        self.stop(self.ci, records=first, answer=tcj.ALLOW)
        self.assertEqual(len(self.model_calls()), 1)
        self.reset_calls()
        second = first + [peer_msg("status: the lane ended"), assistant_text(DONE_ONLY)]
        self.stop(self.ci, records=second, answer=tcj.ALLOW)
        self.assertEqual(self.model_calls(), [])
        self.assertEqual(self.git_starts(), 0)

    def test_question_keys_keep_their_window_across_a_peer_message(self):
        records = [human("decide"), assistant_text(KEYS_EARLIER), peer_msg("status: the lane ended"),
                   assistant_text(KEYS_NOW)]
        out, _ = self.stop(self.decided, records=records, answer=tcj.ALLOW)
        self.assertIn("question-keys", self.reason(out), out)

    def test_a_question_mark_only_inside_a_code_span_makes_no_call(self):
        self.stop(self.decided, "Use `keep the apps?` as the probe.", answer=tcj.ALLOW)
        self.assertEqual(self.model_calls(), [])

    def test_question_keys_pass_an_earlier_reply_before_the_last_human(self):
        records = [assistant_text(KEYS_EARLIER), human("second"), assistant_text(KEYS_NOW)]
        out, _ = self.stop(self.decided, records=records)
        self.assertNotIn("question-keys", self.reason(out), out)



class AnsweredNeedsSourceTests(unittest.TestCase):
    """The answered verdict, in report_guard.py's Stop hook. On any turn, each reply line that holds the
    whole word "answered" must cite a source, outside code spans and fences. Incident F188 (claude-settings
    draft PR #1008)."""

    def hook(self, reply, landed=False, stop_hook_active=False):
        records = [human("ask the owner")]
        if landed:
            records += [tool_use_msg("Bash", {"command": "git commit -m x"}), tool_result_msg()]
        records.append(assistant_text(reply))
        path = write_transcript(records, tempfile.mkdtemp(dir=RUN_FOLDER))
        return {"hook_event_name": "Stop", "transcript_path": path, "stop_hook_active": stop_hook_active}

    def verdict(self, reply, **kw):
        run = run_guard(REPORT_GUARD, self.hook(reply, **kw))
        self.assertEqual(run.returncode, 0, run.stderr)
        return json.loads(run.stdout) if run.stdout.strip() else None

    def assert_blocked(self, reply, *needles, **kw):
        out = self.verdict(reply, **kw)
        self.assertIsNotNone(out, reply)
        self.assertEqual(out.get("decision"), "block", reply)
        for needle in needles:
            self.assertIn(needle, out["reason"])
        return out

    def assert_allowed(self, reply, **kw):
        out = self.verdict(reply, **kw)
        self.assertIsNone(out, "%r was blocked: %s" % (reply, out and out.get("reason")))

    # Red: each case below fails until the verdict exists.

    def test_an_red_synthetic_f188_replay_blocks(self):
        # Synthetic replay, not a copy. The real F188 line (docs/plans/owner-feedback-audit.md, claude-settings
        # draft PR #1008) never used the word. This line stands in for a reply that did.
        # Catches: a line that says "Answered" with no source passes.
        self.assert_blocked("Answered: no permission rule can lift it.", "Answered: no permission rule can lift it.")

    def test_an_red_any_case_and_any_position_blocks(self):
        rows = [
            # Catches: an upper-case ANSWERED passes, so the match is case-sensitive.
            "The owner ANSWERED it.",
            # Catches: the word at the end of a line passes.
            "The owner said yes and answered",
            # Catches: a word for a number is read as item <n>.
            "Item one answered in chat.",
            # Catches: a lane number is read as a source.
            "Lane 4 answered.",
        ]
        for line in rows:
            with self.subTest(line=line):
                self.assert_blocked(line, line)

    def test_an_red_each_offending_line_is_listed_in_one_block(self):
        # Catches: only the first offending line is listed, or a cited line is listed with the red ones.
        cited = "Item 143 answered in chat at 17:25 CST."
        reply = "\n".join(["Answered: no permission rule can lift it.", cited, "The owner answered it."])
        out = self.assert_blocked(reply, "Answered: no permission rule can lift it.", "The owner answered it.")
        self.assertNotIn(cited, out["reason"])

    def test_an_red_lone_quote_opens_no_quoted_phrase(self):
        # Catches: a lone double quote counts as a quoted owner phrase, so a line with no pair passes.
        self.assert_blocked('Answered 9" after the call.', 'Answered 9" after the call.')

    def test_an_red_quotes_do_not_pair_across_lines(self):
        # Catches: a quote on one line pairs with a quote on the next line, so the first line passes.
        first = 'Answered, the owner wrote "no.'
        self.assert_blocked(first + '\nHe then said "yes" later.', first)

    def test_an_red_fence_marker_mid_line_opens_no_fence(self):
        # Catches: a ``` inside a line, and not at its start, opens a fence that hides the lines after it.
        self.assert_blocked("Typed ``` in the middle, then answered.\nThe next line answered too.",
                            "Typed ``` in the middle, then answered.", "The next line answered too.")

    def test_an_red_text_after_a_closed_fence_is_judged(self):
        # Catches: a fence that never closes in the scan hides the lines after it.
        self.assert_blocked("```\nkeep the apps\n```\nAnswered: no permission rule can lift it.",
                            "Answered: no permission rule can lift it.")

    def test_an_red_landed_turn_blocks_above_a_good_report(self):
        # Catches: the check runs only on unlanded turns, or misses a line above the report.
        reply = "Answered: no permission rule can lift it.\n\n> **Done** BUILT abc123\n> **Next** ship it"
        self.assert_blocked(reply, "Answered: no permission rule can lift it.", landed=True)

    def test_an_red_joins_a_missing_report_in_one_block(self):
        # Catches: the answered line is dropped when the report is missing, or sent as a second block.
        reply = "Answered: no permission rule can lift it.\n\nAll done."
        self.assert_blocked(reply, "Report-shape guard", "Answered: no permission rule can lift it.", landed=True)

    def test_an_red_and_or_is_not_a_repo_path_blocks(self):
        # Ruling (lane orchestrator, process-only): "and/or" is not a repo path, so the slash in it cites nothing.
        self.assert_blocked("Answered: use a and/or b.", "Answered: use a and/or b.")

    def test_an_red_double_quoted_phrase_is_no_source(self):
        # Lane choice (process-only): a double-quoted phrase is no longer a source. This re-points the
        # quoted-phrase row that the green list held.
        rows = [
            # Catches: an owner phrase in double quotes still cites the line.
            'Answered "no, keep the apps" in chat.',
            # Catches: a quoted label in a Q-line still cites the line.
            'Q1 ("Departs from" line) was answered.',
        ]
        for line in rows:
            with self.subTest(line=line):
                self.assert_blocked(line, line)

    # Green: these pass before the verdict exists too. Each guards against a false alarm.

    def test_an_green_each_source_cites_the_word(self):
        rows = [
            # Catches: a URL is not read as a source.
            "Answered at https://github.com/shivinate7/claude-settings/pull/1008 today.",
            # Catches: a PR ref #<n> is not read as a source.
            "Answered on PR #1008.",
            # Catches: a commit hash is not read as a source.
            "Answered in commit 1a2b3c4d.",
            # Catches: a repo path with a slash is not read as a source.
            "Answered in lint/report_guard today.",
            # Catches: a repo path ending in a file extension is not read as a source.
            "Answered in report_guard.py and its tests.",
            # Catches: item <n> is not read as a source.
            "Answered in item 143.",
            # Catches: page:<n> is not read as a source.
            "Answered on page:12.",
            # Catches: an fb- inbox id is not read as a source.
            "fb-1042 answered in chat.",
            # Catches: a session_ id is not read as a source.
            "Answered by session_0a1b2c3d4e5f.",
            # Catches: a Central time HH:MM is not read as a source.
            "Answered at 17:25 CST.",
        ]
        for line in rows:
            with self.subTest(line=line):
                self.assert_allowed(line)

    def test_an_green_docs_path_after_the_word_passes(self):
        # Brief (b): the synthetic F188 line with a docs path.
        self.assert_allowed("Answered: no permission rule can lift it. (docs: code.claude.com/docs/en/permissions)")

    def test_an_green_item_and_central_time_pass(self):
        # Brief (c): the item number and the Central time both cite.
        self.assert_allowed("Item 143 answered in chat at 17:25 CST.")

    def test_an_green_negations_and_inbox_home_word_pass(self):
        rows = [
            # Catches: unanswered is read as the word.
            "Q2 is unanswered.",
            # Catches: not answered is read as the word.
            "The owner has not answered.",
            # Catches: a line that opens with Not answered is read as the word.
            "Not answered.",
            # Catches: never answered is read as the word.
            "The owner never answered.",
            # Catches: hasn't answered is read as the word.
            "The lane hasn't answered yet.",
            # Catches: the upper-case form of a negation is read as the word.
            "The owner has NOT ANSWERED.",
            # Catches: the inbox home word in [question] -> answered is read as a claim.
            "[question] -> answered",
        ]
        for line in rows:
            with self.subTest(line=line):
                self.assert_allowed(line)

    def test_an_green_code_span_and_fence_pass(self):
        rows = [
            # Catches: the word inside a one-tick code span is read as a claim.
            "Use `answered` as the probe.",
            # Catches: the word inside a two-tick code span is read as a claim.
            "Use ``answered`` as the probe.",
            # Catches: the words inside a multi-line fence are read as claims.
            "```\nAnswered: no permission rule can lift it.\nThe owner answered it.\n```",
            # Catches: a fence with an info string is read as text.
            "```text\nanswered\n```",
        ]
        for reply in rows:
            with self.subTest(reply=reply):
                self.assert_allowed(reply)

    def test_an_green_not_yet_answered_passes(self):
        # Ruling (lane orchestrator, process-only): "not yet answered" is exempt, like "not answered".
        for line in ("The owner has not yet answered.", "Not yet answered."):
            with self.subTest(line=line):
                self.assert_allowed(line)

    def test_an_green_source_inside_a_code_span_counts(self):
        # Ruling (lane orchestrator, process-only): a source in an inline code span counts.
        for line in ("Answered in `report_guard.py`.", "Answered at `https://github.com/o/r/pull/1`."):
            with self.subTest(line=line):
                self.assert_allowed(line)

    def test_an_green_sources_match_in_any_case(self):
        # Catches: item <n> and fb- ids match only in lower case, so a capitalised source reads as no source.
        for line in ("Item 143 answered in chat.", "FB-1042 answered in chat."):
            with self.subTest(line=line):
                self.assert_allowed(line)

    def test_an_green_negated_forms_beyond_the_list_pass(self):
        # Catches: a negated "answered" outside the exempt list (wasn't, has not been, could not be, haven't,
        # has yet to be, No one) is read as a claim.
        rows = [
            "The ask wasn't answered.",
            "The ask has not been answered.",
            "No one answered.",
            "The ask could not be answered.",
            "We haven't answered.",
            "The ask has yet to be answered.",
        ]
        for line in rows:
            with self.subTest(line=line):
                self.assert_allowed(line)

    def test_an_green_hyphen_joined_word_is_not_the_word(self):
        # Catches: the word inside a hyphen-joined name (answered-needs-source) is read as the word.
        self.assert_allowed("The rule answered-needs-source holds.")

    def test_an_green_no_and_nothing_forms_pass(self):
        # Catches: "No question", "None", "Nothing", and "Cannot tell whether" with "answered" are read as a claim.
        rows = [
            "No question was answered.",
            "None were answered.",
            "Nothing was answered.",
            "Cannot tell whether it was answered.",
        ]
        for line in rows:
            with self.subTest(line=line):
                self.assert_allowed(line)

    def test_an_green_tilde_fence_passes(self):
        # Catches: a line inside a ~~~ fence is read as text, since only ``` fences are skipped.
        rows = [
            "~~~\nThe owner answered it.\n~~~",
            "~~~text\nanswered\n~~~",
        ]
        for reply in rows:
            with self.subTest(reply=reply):
                self.assert_allowed(reply)

    def test_an_green_question_line_passes(self):
        # Catches: a question that asks whether the word happened is read as a claim.
        self.assert_allowed("Has the owner answered?")

    def test_an_green_word_forms_that_are_not_the_word_pass(self):
        # Catches: answers, answering, or answer is read as answered.
        self.assert_allowed("The owner answers in chat. Answering takes a minute, and the answer is pending.")

    def test_an_green_landed_turn_with_a_cited_line_passes(self):
        reply = "Item 143 answered in chat at 17:25 CST.\n\n> **Done** BUILT abc123\n> **Next** ship it"
        self.assert_allowed(reply, landed=True)

    def test_an_green_stop_hook_active_stays_quiet(self):
        # Catches: the check blocks a rewrite, which this guard leaves quiet today.
        self.assert_allowed("Answered: no permission rule can lift it.", stop_hook_active=True)

    # Cost: regex only, no file read beyond the transcript. The probe is builtins.open, the pattern
    # test_repo_colour.py uses. The guard runs in this process, so the watch can see its opens.

    def guard_opens(self, reply):
        """Run report_guard.py's main here and return (its stdout, every path it opened, the transcript path)."""
        import _transcript  # noqa: F401  imported before the watch, so its own load is not counted
        import layout  # noqa: F401
        import local_time  # noqa: F401
        hook = self.hook(reply)
        opened, real_open = [], open

        def watch(path, mode="r", *args, **kwargs):
            opened.append(str(path))
            return real_open(path, mode, *args, **kwargs)
        out = io.StringIO()
        with mock.patch("builtins.open", watch), mock.patch("sys.stdin", io.StringIO(json.dumps(hook))), \
                contextlib.redirect_stdout(out):
            runpy.run_path(REPORT_GUARD, run_name="__main__")
        return out.getvalue().strip(), opened, hook["transcript_path"]

    def test_an_cost_no_word_opens_only_the_transcript(self):
        # Catches: the check reads a file, such as a glossary or a record, even when the reply has no "answered".
        for reply in ("Lane 4 is still running.", "The owner answers in chat.", "The lane is answering now."):
            with self.subTest(reply=reply):
                out, opened, transcript = self.guard_opens(reply)
                self.assertEqual(out, "")
                self.assertEqual(set(opened), {transcript})

    def test_an_cost_offending_line_still_opens_only_the_transcript(self):
        # The block is the red part. The read is the cost: the verdict reads the reply, and nothing else opens.
        out, opened, transcript = self.guard_opens("Answered: no permission rule can lift it.")
        self.assertEqual((json.loads(out) if out else {}).get("decision"), "block", out)
        self.assertEqual(set(opened), {transcript})


if __name__ == "__main__":
    unittest.main()
