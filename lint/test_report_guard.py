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
import re
import runpy
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT_GUARD = os.path.join(HERE, "report_guard.py")
HOOKS = os.path.join(HERE, "..", "hooks")
GUARD_PY = os.path.join(HOOKS, "guard.py")

sys.path.insert(0, HERE)
sys.path.insert(0, HOOKS)  # guard_core, loaded by path below, imports its sibling modules
import ste_lint  # noqa: E402
import report_guard as RG  # noqa: E402  session_wording, the one detector for an order to the session (lint/report_guard.py)
import test_call_judge as tcj  # noqa: E402  the model stub and git fixtures (one home)
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per test run (lint/_test_temp.py)
import test_refusal_note as hook_base  # noqa: E402  the route-rows seam name and fixture (one home, hooks/test_refusal_note.py)

GOOD_REPORT = "> **Done** BUILT abc123\n> **Next** ship it"
# The correction step's words (decision guard-remedy-not-to-owner, shared tails). A refusal holds none of them; the
# record holds both. Lower case, to match a lowered reason or record.
CORRECTION_STEP = ("post only the corrected lines", "never send the report again")
RUN_FOLDER = _test_temp.run_folder()  # the new cases take their temp folders from it, never from the system temp dir

# Isolation. Every spawned guard inherits this process's environment (env=None, or a copy
# of os.environ). Point CLAUDE_CONFIG_DIR at this run's folder for the whole module, so no test
# appends to the user's guard.log. tearDownModule restores the value it found and removes the folder.
# A test that sets its own folder (the config report) still wins.
_ISOLATION = {}


def setUpModule():
    _ISOLATION["dir"] = RUN_FOLDER  # the run's one folder, made at import (test-temp-standard); teardown removes it
    _ISOLATION["prev"] = os.environ.get("CLAUDE_CONFIG_DIR")  # None means unset
    os.environ["CLAUDE_CONFIG_DIR"] = _ISOLATION["dir"]
    stub = os.path.join(_ISOLATION["dir"], "stub")  # the stub lives in this run's folder
    os.makedirs(stub)
    _ISOLATION["stub"] = stub
    with open(os.path.join(stub, "sitecustomize.py"), "w", encoding="utf-8") as f:
        f.write(tcj.STUB_SITE)
    _ISOLATION["env"] = {k: os.environ.get(k) for k in MODEL_ENV}
    os.environ["PYTHONPATH"] = os.pathsep.join(p for p in (stub, os.environ.get("PYTHONPATH")) if p)
    os.environ.update(CJ_LOADED_DIR=stub, CJ_RECORD=os.path.join(stub, "calls.jsonl"),
                      CJ_ANSWER=tcj.ALLOW)
    os.environ.pop("CJ_MODEL_FAIL", None)
    # The route-rows seam points at a missing file, so no old case reads a real rows file.
    _ISOLATION["rows"] = os.environ.get(hook_base.ROUTE_ROWS_ENV)
    os.environ[hook_base.ROUTE_ROWS_ENV] = os.path.join(_ISOLATION["dir"], "no-route-rows.json")


def tearDownModule():
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
    rows = _ISOLATION.pop("rows")
    if rows is None:
        os.environ.pop(hook_base.ROUTE_ROWS_ENV, None)
    else:
        os.environ[hook_base.ROUTE_ROWS_ENV] = rows
    shutil.rmtree(_ISOLATION.pop("dir"), ignore_errors=True)
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)
    shutil.rmtree(hook_base.RUN, ignore_errors=True)  # the hook harness's run folder, made at its import


def human(text):
    return {"type": "user", "isSidechain": False, "message": {"role": "user", "content": text}}


def peer_msg(body, stamp=None, from_session="local_fixture"):
    """A cross-session reply in the shape a real transcript stores: type user, origin.kind peer,
    isMeta true. It lands mid-turn, so it is never the owner's last message. `from_session` is the
    id of the session that sent it."""
    rec = {"type": "user", "isSidechain": False, "isMeta": True,
           "origin": {"kind": "peer", "from": "uds:fixture-pipe", "msg_id": "m-" + body[:8],
                      "name": "peer-cf", "fromSession": from_session, "fromMode": "bypass",
                      "body": body},
           "message": {"role": "user", "content": "Another Claude session sent a message:\n"
                       '<cross-session-message from="uds:fixture-pipe" from-session="%s" '
                       'from-name="peer-cf" from-mode="bypass">%s</cross-session-message>' % (from_session, body)}}
    if stamp:
        rec["timestamp"] = stamp
    return rec


def tool_use_msg(name, input_=None, id_=None):
    block = {"type": "tool_use", "name": name, "input": input_ or {}}
    if id_ is not None:  # a result pairs to its call by this id
        block["id"] = id_
    return {"type": "assistant", "isSidechain": False, "message": {"role": "assistant", "content": [block]}}


def tool_result_msg(tool_use_id="tu_1", content="ok", is_error=False):
    block = {"type": "tool_result", "tool_use_id": tool_use_id, "content": content}
    if is_error:
        block["is_error"] = True
    return {"type": "user", "isSidechain": False, "message": {"role": "user", "content": [block]}}


def assistant_text(text):
    return {"type": "assistant", "isSidechain": False,
            "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}


def background_agent_launch(spawn, n=0):
    """A background spawn's launch: its Agent tool_use with run_in_background, then the async-launch result
    that names the agent. Its completion, when it has one, arrives later as a notice (background_agent_done).
    A launch with no notice after it is still running. The shape is the one hooks/stall_watch.py reads:
    isAsync, status async_launched, agentId."""
    cid = "toolu_bg%d" % n
    aid = "a%016x" % (0x51a7e0000 + n)
    use = {"type": "assistant", "isSidechain": False, "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": cid, "name": "Agent", "input": dict(spawn, run_in_background=True)}]}}
    result = {"type": "user", "isSidechain": False, "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": cid,
         "content": "Async agent launched successfully. agentId: %s." % aid}]},
        "toolUseResult": {"isAsync": True, "status": "async_launched", "agentId": aid}}
    return [use, result]


def background_agent_done(n, status="completed"):
    """The completion notice of background spawn n: a queued_command attachment whose prompt is a task
    notification. Its tool-use-id is the spawn's own id, and its status is terminal."""
    cid = "toolu_bg%d" % n
    aid = "a%016x" % (0x51a7e0000 + n)
    prompt = ("<task-notification>\n<task-id>%s</task-id>\n<tool-use-id>%s</tool-use-id>\n"
              "<status>%s</status>\n<summary>Agent \"review\" %s</summary>\n</task-notification>"
              % (aid, cid, status, status))
    return {"type": "attachment", "isSidechain": False,
            "attachment": {"type": "queued_command", "prompt": prompt}}


def keyed_spawn(spawn, n=0):
    """A finished foreground spawn that carries its tool_use id, answered by a real result."""
    use = tool_use_msg("Agent", spawn)
    use["message"]["content"][0]["id"] = "toolu_fg%d" % n
    return [use, tool_result_msg("toolu_fg%d" % n)]


def compact_boundary():
    """The system record Claude Code writes when a compaction finishes. Its token fields are as the
    hook-inputs-carry-token-counts decision measured them, top level; their nesting is unmeasured."""
    return {"type": "system", "subtype": "compact_boundary", "isSidechain": False,
            "preTokens": 37179, "postTokens": 6250, "cumulativeDroppedTokens": 30929}


def compact_summary():
    """The user record Claude Code writes after a boundary. Its string content makes is_last_human read
    it as a human message."""
    return {"type": "user", "isSidechain": False, "isCompactSummary": True,
            "message": {"role": "user", "content": "This session is being continued from a previous conversation."}}


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


# The same run with subprocess.Popen refused, so a process start inside the hook fails the run instead of
# passing silently. The cost case reads it (refuse_process).
NO_PROCESS_CODE = (
    "import runpy, subprocess, sys\n"
    "def _refuse(*args, **kwargs):\n"
    "    raise RuntimeError('the hook tried to start a process: %r' % (args,))\n"
    "subprocess.Popen = _refuse\n"
    "sys.argv = sys.argv[1:2]\n"
    "runpy.run_path(sys.argv[0], run_name='__main__')\n"
)


def run_guard(guard, hook, raw_stdin=None, env=None, block=(), refuse_process=False):
    stdin_text = raw_stdin if raw_stdin is not None else json.dumps(hook)
    argv = [sys.executable, guard]
    if block:
        argv = [sys.executable, "-c", BLOCK_IMPORTS_CODE, guard, json.dumps(list(block))]
    if refuse_process:
        argv = [sys.executable, "-c", NO_PROCESS_CODE, guard]
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


# The one home of the landing-turn drive: one human message, one Bash call (a git write unless the
# caller names another command), then the reply, run through main() as the Stop hook.
def landed_run(folder, reply, command="git commit -m x"):
    records = [human("do the task"), tool_use_msg("Bash", {"command": command}), tool_result_msg(),
               assistant_text(reply)]
    path = write_transcript(records, folder)
    hook = {"hook_event_name": "Stop", "transcript_path": path, "stop_hook_active": False}
    return run_guard(REPORT_GUARD, hook)


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
            # Pin: a peer record before the commit never hides the commit.
            ("peer before commit", [human("go"), peer_msg("Answer: ok."),
                                    tool_use_msg("Bash", {"command": "git commit -m x"}),
                                    tool_result_msg(), assistant_text("done")], "block"),
            # Pin: a commit from an earlier turn never counts because a peer
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
        run = landed_run(self.tmp.name, reply)
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
        self.assert_blocked("> **Done** fixed it in abc123\n> **Next** none", "BUILT, RECORDED or OTHER")

    def test_df_red_done_without_ref_blocks(self):
        self.assert_blocked("> **Done** BUILT the guard\n> **Next** none", "BUILT, RECORDED or OTHER")

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
        self.assertIn("BUILT, RECORDED or OTHER", out["reason"])
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
        self.tmp = tempfile.TemporaryDirectory(dir=RUN_FOLDER)
        self.addCleanup(self.tmp.cleanup)

    def stop(self, records, reply, agent_model="sonnet"):
        """Run the Stop hook over the turn's records, with the reply as its last text. Return its verdict or None."""
        records = records + [tool_use_msg("Bash", {"command": "git commit -m x"}), tool_result_msg(),
                             assistant_text(reply)]
        path = write_transcript(records, self.tmp.name)
        hook = {"hook_event_name": "Stop", "transcript_path": path, "stop_hook_active": False}
        env = dict(os.environ)
        env.pop("CLAUDE_CODE_SUBAGENT_MODEL", None)  # an unset spawn reads the agent file's pin, not this
        if agent_model:
            env["CLAUDE_CODE_SUBAGENT_MODEL"] = agent_model
        run = run_guard(REPORT_GUARD, hook, env=env)
        self.assertEqual(run.returncode, 0)
        return json.loads(run.stdout) if run.stdout.strip() else None

    def verdict(self, reply, spawns, denied=(), running=(), agent_model="sonnet"):
        records = [human("do the task")]
        for spawn in spawns:
            records += [tool_use_msg("Agent", spawn), tool_result_msg()]
        for n, spawn in enumerate(running):  # a background spawn with no completion notice: still running
            records += background_agent_launch(spawn, n)
        for spawn in denied:
            use = tool_use_msg("Agent", spawn)
            use["message"]["content"][0]["id"] = "tu_denied"
            result = tool_result_msg("tu_denied")
            result["message"]["content"][0]["is_error"] = True
            records += [use, result]
        return self.stop(records, reply, agent_model)

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

    REVIEWER = {"subagent_type": "reviewer", "prompt": "Round 1 of 3"}
    TEST_AUTHOR = {"subagent_type": "test-author", "model": "haiku", "prompt": "write the cases"}
    RUNNING_NEXT = "> **Next** reviewer round 1 running; Unstarted: none"

    @staticmethod
    def file_pin(role):
        """The model: key of agents/<role>.md's frontmatter, read from the file the way the guard reads it."""
        with open(os.path.join(HERE, "..", "agents", role + ".md"), encoding="utf-8") as f:
            front = f.read().split("---")[1].splitlines()
        for line in front:
            key, _, value = line.partition(":")
            if key.strip() == "model":
                return value.strip()
        return ""

    def check_unset_spawn_takes_file_pin(self, role):
        import report_guard  # noqa: E402  MODEL_FAMILIES, the names a Done item may give (one home)
        pin = self.file_pin(role)
        self.assertEqual(pin, "haiku", "agents/%s.md pins %r, not the haiku this case expects" % (role, pin))
        wrong = next(f for f in report_guard.MODEL_FAMILIES if f != pin)
        spawn = {"subagent_type": role, "prompt": "Round 1 of 3"}

        def reply(model):
            return "> **Done** BUILT the cases, PR #5 (%s %s)\n> **Next** Unstarted: none" % (role, model)

        out = self.verdict(reply(pin), [spawn], agent_model=None)
        self.assertIsNone(out, out and out["reason"])
        out = self.verdict(reply(wrong), [spawn], agent_model=None)
        self.assertIsNotNone(out, "a %s spawn with no model field ran %s, yet Done naming %s passed"
                             % (role, pin, wrong))
        self.assertIn("'%s %s' matches no %s spawn, which ran %s" % (role, wrong, role, pin), out["reason"])

    def test_dm_green_unset_reviewer_takes_file_pin(self):
        self.check_unset_spawn_takes_file_pin("reviewer")

    def test_dm_green_unset_test_author_takes_file_pin(self):
        self.check_unset_spawn_takes_file_pin("test-author")

    def test_dm_false_alarm_running_reviewer_absent_from_done_passes(self):
        # A reviewer still running is not a finished claim: Done names the test-author and the builder only.
        reply = "> **Done** BUILT the cases, PR #5 (test-author haiku, builder sonnet)\n" + self.RUNNING_NEXT
        out = self.verdict(reply, [self.TEST_AUTHOR, self.BUILDER], running=[self.REVIEWER])
        self.assertIsNone(out, out and out["reason"])

    def test_dm_green_running_reviewer_named_at_pin_passes(self):
        # Control for the case above: the same running fixture, with Done naming the reviewer at its pin.
        reply = ("> **Done** BUILT the cases, PR #5 (test-author haiku, builder sonnet, reviewer haiku)\n"
                 + self.RUNNING_NEXT)
        out = self.verdict(reply, [self.TEST_AUTHOR, self.BUILDER], running=[self.REVIEWER])
        self.assertIsNone(out, out and out["reason"])

    def test_dm_red_unnamed_reviewer_in_done_blocks(self):
        out = self.verdict("> **Done** BUILT the guard, PR #5 (builder sonnet, reviewer)\n> **Next** Unstarted: none",
                           [self.BUILDER, self.REVIEWER])
        self.assertIsNotNone(out, "a reviewer that Done names with no model passed")
        self.assertIn("no model named for reviewer", out["reason"])

    def test_dm_green_both_roles_named_match_passes(self):
        self.assertIsNone(self.verdict(
            "> **Done** BUILT the guard, PR #5 (builder sonnet, reviewer haiku)\n> **Next** Unstarted: none",
            [self.BUILDER, {"subagent_type": "reviewer", "model": "haiku", "prompt": "Round 1 of 3"}]))

    TEST_AUTHOR_HAIKU = {"subagent_type": "test-author", "model": "haiku", "prompt": "write the cases"}
    TEST_AUTHOR_DONE = "> **Done** BUILT the cases, PR #5 (test-author haiku)\n> **Next** Unstarted: none"

    def background_builder_turn(self, status):
        """A finished test-author, then a background builder whose completion notice has `status`.
        `status` None leaves the builder with no notice: still running."""
        records = [human("do the task")] + keyed_spawn(self.TEST_AUTHOR_HAIKU, 0)
        records += background_agent_launch(self.BUILDER, 0)
        if status:
            records.append(background_agent_done(0, status))
        return records

    def test_dm_red_completed_background_builder_omitted_blocks(self):
        out = self.stop(self.background_builder_turn("completed"), self.TEST_AUTHOR_DONE)
        self.assertIsNotNone(out, "a completed background builder that Done omits passed")
        self.assertIn("no model named for builder", out["reason"])

    def test_dm_red_failed_background_builder_omitted_blocks(self):
        out = self.stop(self.background_builder_turn("failed"), self.TEST_AUTHOR_DONE)
        self.assertIsNotNone(out, "a failed background builder that Done omits passed")
        self.assertIn("no model named for builder", out["reason"])

    def test_dm_false_alarm_running_background_builder_omitted_passes(self):
        out = self.stop(self.background_builder_turn(None), self.TEST_AUTHOR_DONE)
        self.assertIsNone(out, out and out["reason"])

    def test_dm_red_finished_keyed_spawn_omitted_blocks(self):
        # A finished spawn that carries its tool_use id and a real result is required in Done like any other.
        records = [human("do the task")] + keyed_spawn(self.TEST_AUTHOR_HAIKU, 0) + keyed_spawn(self.BUILDER, 1)
        out = self.stop(records, self.TEST_AUTHOR_DONE)
        self.assertIsNotNone(out, "a finished keyed builder that Done omits passed")
        self.assertIn("no model named for builder", out["reason"])

    def test_dm_red_running_reviewer_named_bare_blocks(self):
        # A Done item that names a role with no model blocks, whether or not that role is still running.
        out = self.verdict("> **Done** BUILT the guard, PR #5 (builder sonnet, reviewer)\n"
                           "> **Next** reviewer round 1 running; Unstarted: none",
                           [self.BUILDER], running=[self.REVIEWER])
        self.assertIsNotNone(out, "a running reviewer named bare in Done passed")
        self.assertIn("no model named for reviewer", out["reason"])

    def test_dm_red_running_reviewer_named_wrong_model_blocks(self):
        out = self.verdict("> **Done** BUILT the guard, PR #5 (builder sonnet, reviewer sonnet)\n"
                           "> **Next** reviewer round 1 running; Unstarted: none",
                           [self.BUILDER], running=[self.REVIEWER])
        self.assertIsNotNone(out, "a running reviewer named with a wrong model passed")
        self.assertIn("'reviewer sonnet' matches no reviewer spawn, which ran haiku", out["reason"])

    REVIEWER_R3 = {"subagent_type": "reviewer", "model": "sonnet", "prompt": "Round 3 of 3"}
    ROUND1_NO_MODEL = {"subagent_type": "reviewer", "prompt": "Round 1 of 3"}  # runs its file pin, haiku

    def turn_records(self, earlier=(), window=()):
        """The turn's records: `earlier` spawns from before the owner's second message, then `window` spawns
        after it. Each spawn carries its tool_use id and a real result, as a finished spawn does. With no
        earlier spawn there is no second message: the window is the whole transcript."""
        records = [human("do the task")]
        n = 0
        for spawn in earlier:
            records += keyed_spawn(spawn, n)
            n += 1
        if earlier:
            records.append(human("the owner's next message"))
        for spawn in window:
            records += keyed_spawn(spawn, n)
            n += 1
        return records

    ROUNDS_DONE = ("> **Done** BUILT the guard, PR #5 (builder sonnet, reviewer haiku round 1, "
                   "reviewer sonnet rounds 2 and 3)\n> **Next** Unstarted: none")

    def test_dm_false_alarm_earlier_round_pin_named_passes(self):
        # The earlier reviewer runs before the owner's second message, on its file pin, haiku. The later
        # reviewers run after it, on sonnet, and each is named at its own model.
        records = self.turn_records(earlier=[self.ROUND1_NO_MODEL],
                                    window=[self.BUILDER, self.REVIEWER_R2, self.REVIEWER_R3])
        out = self.stop(records, self.ROUNDS_DONE)
        self.assertIsNone(out, out and out["reason"])

    def test_dm_red_earlier_round_named_with_unspawned_model_blocks(self):
        # Control: no spawn of any turn ran opus, so naming reviewer opus blocks.
        records = self.turn_records(earlier=[self.ROUND1_NO_MODEL],
                                    window=[self.BUILDER, self.REVIEWER_R2, self.REVIEWER_R3])
        out = self.stop(records, "> **Done** BUILT the guard, PR #5 (builder sonnet, reviewer opus)\n"
                                 "> **Next** Unstarted: none")
        self.assertIsNotNone(out, "Done named reviewer opus, which no spawn ran, and passed")
        self.assertIn("'reviewer opus' matches no reviewer spawn", out["reason"])

    def test_dm_false_alarm_earlier_unnamed_builder_passes(self):
        # Control: the missing-role check stays window-only. An earlier builder Done does not name is no refusal.
        records = self.turn_records(earlier=[self.BUILDER], window=[self.REVIEWER_R2])
        out = self.stop(records, "> **Done** BUILT the guard, PR #5 (reviewer sonnet)\n> **Next** Unstarted: none")
        self.assertIsNone(out, out and out["reason"])

    def test_dm_red_same_window_mismatch_blocks(self):
        # Control: a mismatch inside the window still blocks, with no earlier spawn.
        records = self.turn_records(window=[self.REVIEWER_R2])
        out = self.stop(records, "> **Done** BUILT the guard, PR #5 (reviewer haiku)\n> **Next** Unstarted: none")
        self.assertIsNotNone(out, "Done named reviewer haiku against a window reviewer that ran sonnet, and passed")
        self.assertIn("'reviewer haiku' matches no reviewer spawn, which ran sonnet", out["reason"])

    BUILDER_NO_MODEL = {"subagent_type": "builder", "prompt": "build it"}  # no model field, no file pin
    BUILDER_SONNET = {"subagent_type": "builder", "model": "sonnet", "prompt": "Round 2 of 3"}
    BUILDER_OPUS = {"subagent_type": "builder", "model": "opus", "prompt": "Round 3 of 3"}
    REVIEWER_HAIKU = {"subagent_type": "reviewer", "model": "haiku", "prompt": "Round 2 of 3"}
    REVIEWER_SONNET_EARLY = {"subagent_type": "reviewer", "model": "sonnet", "prompt": "Round 1 of 3"}

    def test_dm_red_earlier_unresolved_spawn_hides_window_mismatch_blocks(self):
        # An earlier builder with no resolvable model is '' in the transcript's map. That must not switch off
        # the builder check for the window's builder, which ran opus.
        self.assertEqual(self.file_pin("builder"), "", "agents/builder.md pins a model, so no spawn is unresolved")
        records = self.turn_records(earlier=[self.BUILDER_NO_MODEL], window=[self.BUILDER_OPUS])
        out = self.stop(records, "> **Done** BUILT the guard, PR #5 (builder sonnet)\n> **Next** Unstarted: none",
                        agent_model=None)
        self.assertIsNotNone(out, "Done named builder sonnet against a window builder that ran opus, and passed")
        self.assertIn("'builder sonnet' matches no builder spawn, which ran opus", out["reason"])

    def test_dm_red_earlier_unresolved_spawn_hides_window_wrong_model_blocks(self):
        # The mirror: the window's builder ran sonnet, and Done names opus. The earlier unresolved spawn must
        # not let that wrong name pass.
        self.assertEqual(self.file_pin("builder"), "", "agents/builder.md pins a model, so no spawn is unresolved")
        records = self.turn_records(earlier=[self.BUILDER_NO_MODEL], window=[self.BUILDER_SONNET])
        out = self.stop(records, "> **Done** BUILT the guard, PR #5 (builder opus)\n> **Next** Unstarted: none",
                        agent_model=None)
        self.assertIsNotNone(out, "Done named builder opus against a window builder that ran sonnet, and passed")
        self.assertIn("'builder opus' matches no builder spawn, which ran sonnet", out["reason"])

    def test_dm_limit_earlier_spawn_model_passes(self):
        # Accepted limit: a Done model name is judged against every spawn in the transcript, not the turn's
        # window alone. The earlier sonnet reviewer lets "reviewer sonnet" pass, though the window's reviewer ran haiku.
        records = self.turn_records(earlier=[self.REVIEWER_SONNET_EARLY], window=[self.REVIEWER_HAIKU])
        out = self.stop(records, "> **Done** BUILT the guard, PR #5 (reviewer sonnet)\n> **Next** Unstarted: none")
        self.assertIsNone(out, out and out["reason"])

    def test_dm_limit_earlier_builder_spawn_model_passes(self):
        # Accepted limit, as above: the earlier sonnet builder lets "builder sonnet" pass, though the
        # window's builder ran opus.
        records = self.turn_records(earlier=[self.BUILDER_SONNET], window=[self.BUILDER_OPUS])
        out = self.stop(records, "> **Done** BUILT the guard, PR #5 (builder sonnet)\n> **Next** Unstarted: none")
        self.assertIsNone(out, out and out["reason"])


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

    def test_nr_red_each_refusal_holds_no_correction_tail(self):
        rows = [
            # Catches: the label-word refusal carries the correction tail.
            ("label words", "> **Done** fixed it in abc123\n> **Next** none", ()),
            # Catches: the model-name refusal carries the correction tail.
            ("model names", "> **Done** BUILT the guard, PR #5\n> **Next** Unstarted: none",
             (self.BUILDER,)),
            # Catches: the Unstarted refusal carries the correction tail.
            ("Unstarted line", "> **Done** BUILT the guard, PR #5 (builder sonnet)\n> **Next** merge",
             (self.BUILDER,)),
            # Catches: the cite-gloss refusal carries the correction tail.
            ("cite gloss", "Per D12.\n\n> **Done** BUILT guard, PR #5\n> **Next** none", ()),
            # Catches: a joined refusal carries the correction tail.
            ("label words and cite gloss", "Per D12.\n\n> **Done** fixed it\n> **Next** none", ()),
        ]
        for name, reply, spawns in rows:
            with self.subTest(refusal=name):
                out = self.verdict(reply, spawns)
                self.assertEqual(out["decision"], "block")
                reason = out["reason"].lower()
                self.assertIn("decision guard-remedy-not-to-owner", reason)
                self.assertNotIn("send the report now", reason)
                for phrase in CORRECTION_STEP:
                    self.assertNotIn(phrase, reason, "the refusal carries the correction tail: %r" % phrase)
                self.assertEqual(reason.count("rule reports-order-of-labels"), 1)
                self.assertIn("rule reports-order-of-labels", reason)

    def test_nr_missing_report_block_keeps_the_reply(self):
        out = self.verdict("All done.")
        self.assertIn("does not end with the report", out["reason"])
        self.assertNotIn("post only the corrected lines", out["reason"].lower())

    def test_nr_missing_report_with_bare_cite_never_forbids_the_report(self):
        # Catches: the block asks for the report and also says never send it.
        out = self.verdict("Per D12.\n\nAll done.")
        self.assertIn("'D12'", out["reason"])
        self.assertIn("does not end with the report", out["reason"])
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
        self.assertIn("does not end with the report", out["reason"])

    def test_rw_red_rewrite_without_unstarted_blocks(self):
        self.missing_report_block()
        out = self.stop("> **Done** BUILT the guard, PR #5 (builder sonnet)\n> **Next** merge", True)
        self.assertEqual(out["decision"], "block")
        self.assertIn("Unstarted guard", out["reason"])
        self.assertIn("decision guard-remedy-not-to-owner", out["reason"])
        self.assertIn("rule reports-order-of-labels", out["reason"])

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

    def earlier_round_records(self, reply):
        """A turn whose reviewer ran before the owner's second message, on its file pin (haiku), and whose
        second reviewer ran after it, on sonnet. `reply` is the turn's last text."""
        round1 = {"subagent_type": "reviewer", "prompt": "Round 1 of 3"}  # no model field: its file pin, haiku
        round2 = {"subagent_type": "reviewer", "model": "sonnet", "prompt": "Round 2 of 3"}
        records = [human("do the task")] + keyed_spawn(round1, 0) + [human("the owner's next message")]
        records += keyed_spawn(round2, 1)
        records += [tool_use_msg("Bash", {"command": "git commit -m x"}), tool_result_msg(), assistant_text(reply)]
        return records

    def test_rw_earlier_round_pin_named_passes(self):
        # The rewrite is judged against every spawn in the transcript, as the stop path is: Done names the earlier
        # reviewer at its pin, haiku, which ran before the window, and the later one at sonnet, which ran in it.
        block = self.run_hook(self.earlier_round_records("All done."), False)
        self.assertIn("does not end with the report", block["reason"])
        reply = ("> **Done** BUILT the guard, PR #5 (reviewer haiku round 1, reviewer sonnet round 2)\n"
                 "> **Next** Unstarted: none")
        out = self.run_hook(self.earlier_round_records(reply), True)
        self.assertIsNone(out, out and out["reason"])

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


REPORT_NO_LINE = "> **Done** BUILT abc123\n> **Deviations** none\n> **Next** ship it"


def report_lines(*deviations):
    """A report whose Deviations bullets are the given lines, for the compaction-carry cases."""
    bullets = "".join("\n> - %s" % line for line in deviations)
    return "> **Done** BUILT abc123\n> **Deviations**%s\n> **Next** ship it" % bullets


REPORT_BOTH_NONE = report_lines("Recovered: none", "Handoff gave: none")
REPORT_BOTH_SOURCED = report_lines("Recovered: ruling X from PR 978 (git); fact Y (page)", "Handoff gave: none")


class CompactionCarryTests(unittest.TestCase):
    """After a compaction, each report holds a `Recovered:` line and a `Handoff gave:` line (report_guard.py, Stop)."""

    def setUp(self):
        self.folder = tempfile.mkdtemp(dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.sid = "cc-" + uuid.uuid4().hex

    def stop(self, records, active=False):
        path = write_transcript(records, self.folder)
        hook = {"hook_event_name": "Stop", "transcript_path": path, "stop_hook_active": active,
                "session_id": self.sid}
        run = run_guard(REPORT_GUARD, hook, env=dict(os.environ, CLAUDE_CODE_SUBAGENT_MODEL="sonnet"))
        self.assertEqual(run.returncode, 0, run.stderr[-300:])
        return json.loads(run.stdout) if run.stdout.strip() else None

    @staticmethod
    def compacted_turn(reply):
        """A turn that compacts mid-turn, then commits and replies. The summary record sits after the
        boundary and before the commit, so the commit lands after the last human message."""
        return [human("do the task"), compact_boundary(), compact_summary(),
                tool_use_msg("Bash", {"command": "git commit -m x"}), tool_result_msg(),
                assistant_text(reply)]

    def assertBlocksForRecovered(self, out):
        self.assertIsNotNone(out, "no block: the first report after a compaction has no Recovered line")
        self.assertEqual(out["decision"], "block")
        self.assertIn("Recovered guard", out["reason"])

    def assertBlocksNaming(self, out, *names):
        """A block whose reason starts "Recovered guard:" and names each of `names`."""
        self.assertIsNotNone(out, "no block; the reason should name %r" % (names,))
        self.assertEqual(out["decision"], "block")
        self.assertTrue(out["reason"].startswith("Recovered guard:"), out["reason"][:200])
        for name in names:
            self.assertIn(name, out["reason"])

    def test_cc_red_landed_turn_after_compaction_without_line_blocks(self):
        # Catches: a landed turn after a compaction passes with no Recovered line.
        self.assertBlocksForRecovered(self.stop(self.compacted_turn(REPORT_NO_LINE)))

    def test_cc_red_recovered_line_in_the_wrong_place_blocks(self):
        rows = [
            # Catches: a line above the report blockquote counts, when only the blockquote may hold it.
            "Recovered: none\n\n" + REPORT_NO_LINE,
            # Catches: a word that ends in "recovered:" is read as the line.
            "> **Done** BUILT abc123\n> **Deviations** Unrecovered: P3 ruling\n> **Next** ship it",
        ]
        for reply in rows:
            with self.subTest(reply=reply):
                self.assertBlocksForRecovered(self.stop(self.compacted_turn(reply)))

    def test_cc_green_recovered_line_forms_pass(self):
        rows = [
            # Catches: the bullet line under Deviations is refused.
            REPORT_BOTH_NONE,
            # Catches: the line written inline after the Deviations label is refused.
            "> **Done** BUILT abc123\n> **Deviations** Recovered: none\n> Handoff gave: none\n> **Next** ship it",
            # Catches: an upper-case label is refused (the label is any case).
            "> **Done** BUILT abc123\n> **Deviations** RECOVERED: none\n> Handoff gave: none\n> **Next** ship it",
            # Catches: the line after a semicolon in Next is refused.
            "> **Done** BUILT abc123\n> **Deviations** Handoff gave: none\n> **Next** ship it; Recovered: none",
            # Catches: a ruling with a source named in the line is refused.
            report_lines("Recovered: P3 ruling from PR #978 (git)", "Handoff gave: none"),
            # Catches: a bold bullet line is refused. Bold passes, as it does at line start.
            "> **Done** BUILT abc123\n> **Deviations**\n> - **Recovered:** none\n> - Handoff gave: none\n> **Next** ship it",
        ]
        for reply in rows:
            with self.subTest(reply=reply):
                self.assertIsNone(self.stop(self.compacted_turn(reply)), reply)

    def test_cc_green_earlier_report_with_both_lines_satisfies_the_demand(self):
        # Catches: lines given earlier since the boundary still demand them again, in a report or in prose.
        for earlier in (REPORT_BOTH_NONE, "Recovered: none\nHandoff gave: none"):
            with self.subTest(earlier=earlier):
                records = [human("do the task"), compact_boundary(), compact_summary(),
                           assistant_text(earlier),
                           human("next task"),
                           tool_use_msg("Bash", {"command": "git commit -m x"}), tool_result_msg(),
                           assistant_text(REPORT_NO_LINE)]
                self.assertIsNone(self.stop(records))

    def test_cc_red_earlier_report_without_the_line_does_not_satisfy(self):
        # Catches: an earlier report with no Recovered line since the boundary satisfies the demand.
        records = [human("do the task"), compact_boundary(), compact_summary(),
                   assistant_text(REPORT_NO_LINE),
                   human("next task"),
                   tool_use_msg("Bash", {"command": "git commit -m x"}), tool_result_msg(),
                   assistant_text(REPORT_NO_LINE)]
        self.assertBlocksForRecovered(self.stop(records))

    def test_cc_red_same_turn_earlier_report_without_line_does_not_satisfy(self):
        # Catches: a report given earlier in the same turn, with no line, satisfies the final report's demand.
        records = [human("do the task"), compact_boundary(), compact_summary(),
                   assistant_text(REPORT_NO_LINE),
                   tool_use_msg("Bash", {"command": "ls"}), tool_result_msg(),
                   tool_use_msg("Bash", {"command": "git commit -m x"}), tool_result_msg(),
                   assistant_text(REPORT_NO_LINE)]
        self.assertBlocksForRecovered(self.stop(records))

    def test_cc_green_bold_recovered_line_keeps_the_report_shape(self):
        # Catches: "**Recovered:**" read as an unknown report label fails the shape and sends the
        # missing-report block. Like "Departs from", it is not a report label.
        reply = "> **Done** BUILT abc123\n> **Deviations** none\n> **Recovered:** none\n> Handoff gave: none\n> **Next** ship it"
        self.assertIsNone(self.stop(self.compacted_turn(reply)))

    def test_cc_green_rewrite_without_report_shape_has_no_demand(self):
        # Catches: the rewrite after a missing-report block demands the line on a reply that is no report.
        first = self.stop(self.compacted_turn("All done."))
        self.assertIsNotNone(first, "no missing-report block on the first Stop")
        self.assertIn("does not end with the report", first["reason"])
        self.assertIsNone(self.stop(self.compacted_turn("Correction: the Done line needs a PR ref."), active=True))

    def test_cc_green_correction_line_satisfies_a_later_report(self):
        # Catches: a correction line posted after a block is not read as a Recovered line, so a later report
        # demands it again.
        records = [human("do the task"), compact_boundary(), compact_summary(),
                   tool_use_msg("Bash", {"command": "git commit -m x"}), tool_result_msg(),
                   assistant_text("All done."),
                   assistant_text("Recovered: none\nHandoff gave: none"),
                   human("next task"),
                   tool_use_msg("Bash", {"command": "git commit -m y"}), tool_result_msg(),
                   assistant_text(REPORT_NO_LINE)]
        self.assertIsNone(self.stop(records))

    def test_cc_red_two_text_blocks_report_in_the_second_blocks(self):
        # Catches: a final message split into two text blocks is read from the first block only.
        final = {"type": "assistant", "isSidechain": False,
                 "message": {"role": "assistant", "content": [
                     {"type": "text", "text": "Committed the guard."},
                     {"type": "text", "text": REPORT_NO_LINE}]}}
        records = [human("do the task"), compact_boundary(), compact_summary(),
                   tool_use_msg("Bash", {"command": "git commit -m x"}), tool_result_msg(), final]
        self.assertBlocksForRecovered(self.stop(records))

    def test_cc_red_boundary_in_an_earlier_turn_demands_the_line_on_the_next_report(self):
        # Catches: a boundary from an earlier turn, with no report since, is ignored.
        records = [human("do the task"), compact_boundary(), compact_summary(),
                   assistant_text("Working on it."),
                   human("next task"),
                   tool_use_msg("Bash", {"command": "git commit -m x"}), tool_result_msg(),
                   assistant_text(REPORT_NO_LINE)]
        self.assertBlocksForRecovered(self.stop(records))

    def test_cc_green_no_boundary_no_demand(self):
        # Catches: the line is demanded on a turn that never compacted.
        records = [human("do the task"), tool_use_msg("Bash", {"command": "git commit -m x"}),
                   tool_result_msg(), assistant_text(REPORT_NO_LINE)]
        self.assertIsNone(self.stop(records))

    def test_cc_red_mid_turn_compaction_landed_without_line_blocks(self):
        rows = [
            # Catches: a check that needs the summary record after the boundary misses a boundary with none.
            [human("do the task"), tool_use_msg("Bash", {"command": "ls"}), tool_result_msg(),
             compact_boundary(), tool_use_msg("Bash", {"command": "git commit -m x"}), tool_result_msg(),
             assistant_text(REPORT_NO_LINE)],
            # Catches: a scan that starts at the last human message misses a boundary that sits before the
            # summary record, which reads as a human message.
            self.compacted_turn(REPORT_NO_LINE),
        ]
        for records in rows:
            with self.subTest(records=len(records)):
                self.assertBlocksForRecovered(self.stop(records))

    def test_cc_red_newest_boundary_governs(self):
        # Catches: the oldest boundary is used, so its satisfied first report hides the newer boundary.
        records = [human("do the task"), compact_boundary(), compact_summary(),
                   tool_use_msg("Bash", {"command": "git commit -m x"}), tool_result_msg(),
                   assistant_text(REPORT_BOTH_NONE),
                   human("next task"), compact_boundary(), compact_summary(),
                   tool_use_msg("Bash", {"command": "git commit -m y"}), tool_result_msg(),
                   assistant_text(REPORT_NO_LINE)]
        self.assertBlocksForRecovered(self.stop(records))

    def test_cc_red_unlanded_report_after_compaction_blocks(self):
        # Catches: an unlanded turn whose reply has the report shape passes with no Recovered line.
        records = [human("what is the status?"), compact_boundary(), compact_summary(),
                   assistant_text(REPORT_NO_LINE)]
        self.assertBlocksForRecovered(self.stop(records))

    def test_cc_green_unlanded_prose_after_compaction_passes(self):
        # Catches: the line is demanded on a reply with no report shape.
        records = [human("what is the status?"), compact_boundary(), compact_summary(),
                   assistant_text("Here is what I found.")]
        self.assertIsNone(self.stop(records))

    def test_cc_red_rewrite_after_missing_report_block_names_the_line(self):
        first = self.stop(self.compacted_turn("All done."))
        self.assertIsNotNone(first, "no missing-report block on the first Stop")
        self.assertIn("does not end with the report", first["reason"])
        # The rewrite reads the marker the missing-report block left, and checks the Recovered line once.
        self.assertBlocksForRecovered(self.stop(self.compacted_turn(REPORT_NO_LINE), active=True))

    def test_cc_correction_block_leaves_no_marker(self):
        # Catches: a Recovered correction leaves a marker, so its rewrite is checked again and loops.
        self.assertBlocksForRecovered(self.stop(self.compacted_turn(REPORT_NO_LINE)))
        self.assertIsNone(self.stop(self.compacted_turn(REPORT_NO_LINE), active=True))

    def test_cc_red_handoff_gave_missing_blocks(self):
        # Catches: a Recovered line with no Handoff gave line passes.
        self.assertBlocksNaming(self.stop(self.compacted_turn(report_lines("Recovered: none"))), "Handoff gave")

    def test_cc_red_recovered_missing_with_handoff_present_blocks(self):
        # Catches: a Handoff gave line with no Recovered line passes.
        self.assertBlocksNaming(self.stop(self.compacted_turn(report_lines("Handoff gave: none"))))

    def test_cc_red_handoff_line_outside_the_blockquote_blocks(self):
        # Catches: a Handoff gave line above the report blockquote counts for the current reply.
        reply = "Handoff gave: none\n\n" + report_lines("Recovered: none")
        self.assertBlocksNaming(self.stop(self.compacted_turn(reply)), "Handoff gave")

    def test_cc_green_both_lines_with_sources_pass(self):
        rows = [
            # Catches: a sourced Recovered line with a Handoff gave line is refused.
            REPORT_BOTH_SOURCED,
            # Catches: the source words are read without regard to case.
            report_lines("Recovered: fact Z (GIT); fact W (Digest)", "Handoff gave: none"),
            # Catches: a Handoff gave item is judged for a source. Only the Recovered items need one.
            report_lines("Recovered: none", "Handoff gave: ruling Q from PR 12"),
        ]
        for reply in rows:
            with self.subTest(reply=reply):
                self.assertIsNone(self.stop(self.compacted_turn(reply)), reply)

    def test_cc_red_recovered_item_without_a_source_blocks(self):
        # Catches: a Recovered item that names no git, page or digest source passes.
        rows = [
            (report_lines("Recovered: ruling X", "Handoff gave: none"), "ruling X"),
            (report_lines("Recovered: rule A (git); fact B", "Handoff gave: none"), "fact B"),
            (report_lines("Recovered: a (git); b", "Handoff gave: none"), None),
        ]
        for reply, name in rows:
            with self.subTest(reply=reply):
                self.assertBlocksNaming(self.stop(self.compacted_turn(reply)), *([name] if name else []))

    def test_cc_red_source_word_must_match_a_whole_word(self):
        # Catches: "git" inside "gitlab", or "page" inside "pages", counts as a source.
        for item in ("fact Z (gitlab)", "fact Z (pages)"):
            with self.subTest(item=item):
                reply = report_lines("Recovered: " + item, "Handoff gave: none")
                self.assertBlocksNaming(self.stop(self.compacted_turn(reply)), item)

    def test_cc_green_bold_handoff_line_keeps_the_report_shape(self):
        # Catches: "**Handoff gave:**" read as an unknown report label fails the shape.
        reply = "> **Done** BUILT abc123\n> **Deviations** Recovered: none\n> **Handoff gave:** none\n> **Next** ship it"
        self.assertIsNone(self.stop(self.compacted_turn(reply)))

    def test_cc_green_no_boundary_no_demand_for_either_line(self):
        # Catches: either line, or its sources, demanded on a turn that never compacted.
        records = [human("do the task"), tool_use_msg("Bash", {"command": "git commit -m x"}),
                   tool_result_msg(), assistant_text(report_lines("Recovered: ruling X"))]
        self.assertIsNone(self.stop(records))

    def test_cc_green_earlier_recovered_line_and_current_handoff_line_pass(self):
        # Catches: a Handoff gave line in the current report is refused when an earlier report holds the Recovered line.
        records = [human("do the task"), compact_boundary(), compact_summary(),
                   assistant_text(report_lines("Recovered: none")),
                   human("next task"),
                   tool_use_msg("Bash", {"command": "git commit -m x"}), tool_result_msg(),
                   assistant_text(report_lines("Handoff gave: none"))]
        self.assertIsNone(self.stop(records))

    def test_cc_green_earlier_satisfying_line_is_not_judged_again(self):
        # Catches: an earlier report that already satisfied the demand is judged again for its sources.
        records = [human("do the task"), compact_boundary(), compact_summary(),
                   assistant_text(report_lines("Recovered: ruling X", "Handoff gave: none")),
                   human("next task"),
                   tool_use_msg("Bash", {"command": "git commit -m x"}), tool_result_msg(),
                   assistant_text(REPORT_NO_LINE)]
        self.assertIsNone(self.stop(records))

    def test_cc_red_rewrite_with_recovered_but_no_handoff_blocks(self):
        # Catches: the rewrite after a missing-report block checks the Recovered line but not the Handoff gave line.
        first = self.stop(self.compacted_turn("All done."))
        self.assertIsNotNone(first, "no missing-report block on the first Stop")
        self.assertIn("does not end with the report", first["reason"])
        self.assertBlocksNaming(self.stop(self.compacted_turn(report_lines("Recovered: none")), active=True),
                                "Handoff gave")

    def test_cc_green_none_forms_pass_the_source_check(self):
        # Catches: a none with a trailing mark, a backtick, or a word after it is read as a sourceless item.
        rows = [
            "Recovered: none needed",
            "Recovered: none - summary complete",
            "Recovered: none (the summary held all)",
            "Recovered: none;",
            "Recovered: _none_",
            "Recovered: nothing was lost",
            "`Recovered: none`",
            "Recovered: X (page); nothing else.",
        ]
        for line in rows:
            with self.subTest(line=line):
                self.assertIsNone(self.stop(self.compacted_turn(report_lines(line, "Handoff gave: none"))), line)

    def test_cc_green_semicolon_inside_parentheses_does_not_split(self):
        # Catches: a ";" inside parentheses splits one sourced item into an unsourced item.
        reply = report_lines("Recovered: X from page (commit abc; merged 3 days ago)", "Handoff gave: none")
        self.assertIsNone(self.stop(self.compacted_turn(reply)))

    def test_cc_green_recovered_line_starts_after_a_mark_or_a_separator(self):
        # Catches: a line after a report label, a quote mark, or ". " is not read as a Recovered line.
        rows = [
            "> **Done** BUILT abc123\n> **Deviations:** Recovered: none\n> Handoff gave: none\n> **Next** ship it",
            '> **Done** BUILT abc123\n> **Deviations**\n> "Recovered: none"\n> Handoff gave: none\n> **Next** ship it',
            "> **Done** BUILT abc123\n> **Deviations** Handoff gave: none\n> **Next** ship it. Recovered: none",
        ]
        for reply in rows:
            with self.subTest(reply=reply):
                self.assertIsNone(self.stop(self.compacted_turn(reply)), reply)

    def test_cc_green_mid_sentence_recovered_after_demand_met_passes(self):
        # Catches: a mid-sentence or backticked "recovered:" is read as a Recovered line, and its item is
        # judged for a source, after the demand is already met.
        earlier = report_lines("Recovered: none", "Handoff gave: none")
        later = [
            "> **Done** BUILT the `Recovered:` guard, PR #5\n> **Deviations** none\n> **Next** ship it",
            "> **Done** BUILT abc123\n> **Deviations** none\n> **Next** the janitor recovered: 3 files",
        ]
        for reply in later:
            with self.subTest(reply=reply):
                records = [human("do the task"), compact_boundary(), compact_summary(),
                           assistant_text(earlier),
                           human("next task"),
                           tool_use_msg("Bash", {"command": "git commit -m x"}), tool_result_msg(),
                           assistant_text(reply)]
                self.assertIsNone(self.stop(records), reply)

    def test_cc_red_mid_sentence_recovered_does_not_satisfy_the_pending_demand(self):
        # Catches: a mid-sentence or backticked "recovered:" satisfies the demand for the Recovered line.
        rows = [
            "> **Done** BUILT abc123\n> **Deviations** the janitor recovered: 3 files from git\n"
            "> Handoff gave: none\n> **Next** ship it",
            "> **Done** BUILT the `Recovered:` guard, PR #5\n> **Deviations** none\n"
            "> Handoff gave: none\n> **Next** ship it",
        ]
        for reply in rows:
            with self.subTest(reply=reply):
                out = self.stop(self.compacted_turn(reply))
                self.assertBlocksNaming(out)
                self.assertIn("Recovered line", out["reason"])

    def test_cc_green_unsourced_recovered_line_after_demand_met_passes(self):
        # Catches: the source check judges a Recovered item after an earlier report already met the demand.
        records = [human("do the task"), compact_boundary(), compact_summary(),
                   assistant_text(report_lines("Recovered: ruling X from PR 978 (git)", "Handoff gave: none")),
                   human("next task"),
                   tool_use_msg("Bash", {"command": "git commit -m x"}), tool_result_msg(),
                   assistant_text(report_lines("Recovered: ruling X", "Handoff gave: none"))]
        self.assertIsNone(self.stop(records))

    def test_cc_green_bare_recovered_line_with_a_sourced_bullet_passes(self):
        # Catches: a bare "Recovered:" with its items below is read as having no items.
        reply = ("> **Done** BUILT abc123\n> **Deviations**\n> Handoff gave: none\n"
                 "> Recovered:\n> - ruling X (git)\n> **Next** ship it")
        self.assertIsNone(self.stop(self.compacted_turn(reply)))

    def test_cc_red_bare_recovered_line_with_an_unsourced_bullet_blocks(self):
        # Catches: a bullet under a bare "Recovered:" passes with no source.
        reply = ("> **Done** BUILT abc123\n> **Deviations**\n> Handoff gave: none\n"
                 "> Recovered:\n> - ruling X\n> **Next** ship it")
        self.assertBlocksNaming(self.stop(self.compacted_turn(reply)), "ruling X")

    def test_cc_red_bare_recovered_line_with_nothing_below_blocks(self):
        # Catches: a bare "Recovered:" with nothing below it passes as a present line.
        reply = "> **Done** BUILT abc123\n> **Deviations**\n> Handoff gave: none\n> Recovered:\n> **Next** ship it"
        out = self.stop(self.compacted_turn(reply))
        self.assertBlocksNaming(out)
        self.assertIn("Recovered line", out["reason"])


class CompactionCarryCostTests(unittest.TestCase):
    """The compaction-carry check reads the transcript it already opens: no process, and no file
    except the marker a missing-report block already writes."""

    def setUp(self):
        self.folder = tempfile.mkdtemp(dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.sid = "cc-" + uuid.uuid4().hex
        self.home = os.path.join(self.folder, "home")
        self.config = os.path.join(self.home, ".claude")
        os.makedirs(self.config)

    def files(self):
        found = set()
        for root, _dirs, names in os.walk(self.folder):
            found.update(os.path.join(root, name) for name in names)
        return found

    def run_hook(self, records):
        write_transcript(records, self.folder)
        hook = {"hook_event_name": "Stop", "transcript_path": os.path.join(self.folder, "transcript.jsonl"),
                "stop_hook_active": False, "session_id": self.sid}
        env = dict(os.environ, HOME=self.home, CLAUDE_CONFIG_DIR=self.config,
                   CLAUDE_CODE_SUBAGENT_MODEL="sonnet")
        before = self.files()
        run = run_guard(REPORT_GUARD, hook, env=env, refuse_process=True)
        self.assertEqual(run.returncode, 0, run.stderr[-300:])
        self.assertNotIn("tried to start a process", run.stderr)
        out = json.loads(run.stdout) if run.stdout.strip() else None
        return out, sorted(self.files() - before)

    def test_cc_cost_recovered_block_starts_no_process_and_writes_no_file(self):
        records = [human("do the task"), compact_boundary(), compact_summary(),
                   tool_use_msg("Bash", {"command": "git commit -m x"}), tool_result_msg(),
                   assistant_text(REPORT_NO_LINE)]
        out, new = self.run_hook(records)
        # The block shows the check ran, so the cost below is the check's own.
        self.assertIsNotNone(out, "no block: the check did not run on the compacted turn")
        self.assertIn("Recovered guard", out["reason"])
        self.assertEqual(new, [], "the check wrote files: %r" % new)

    def test_cc_cost_missing_report_writes_only_the_marker(self):
        records = [human("do the task"), compact_boundary(), compact_summary(),
                   tool_use_msg("Bash", {"command": "git commit -m x"}), tool_result_msg(),
                   assistant_text("All done.")]
        out, new = self.run_hook(records)
        self.assertIsNotNone(out, "no missing-report block")
        self.assertIn("does not end with the report", out["reason"])
        self.assertEqual([os.path.basename(path) for path in new], [self.sid + ".report-block"])

    def test_cc_cost_both_lines_pass_starts_no_process_and_writes_no_file(self):
        records = [human("do the task"), compact_boundary(), compact_summary(),
                   tool_use_msg("Bash", {"command": "git commit -m x"}), tool_result_msg(),
                   assistant_text(REPORT_BOTH_SOURCED)]
        out, new = self.run_hook(records)
        self.assertIsNone(out, "a block on a report that carries both lines: %r" % out)
        self.assertEqual(new, [], "the check wrote files: %r" % new)


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
        # Catches: the refusal offering the question box in a repo with a waiting page. The writer is the route.
        for landed in (False, True):
            with self.subTest(landed=landed):
                out = self.verdict(self.PICK, landed=landed)
                self.assertEqual(out["decision"], "block")
                self.assertIn("Pick guard", out["reason"])
                self.assertIn("writer", out["reason"])
                self.assertNotRegex(out["reason"], r"\bbox\b")

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

    def test_pk_green_page_write_without_link_passes(self):
        # The writer's items write is the send. It reaches the page without a link in the reply, so no link is needed.
        self.assertIsNone(self.verdict(self.PICK, [self.page_set()]))

    def test_pk_red_agent_calls_do_not_count(self):
        # An agent's box and write do not count. With no link in the reply, the pick still blocks
        # (decisions-reach-a-clickable-pick).
        calls = [("AskUserQuestion", {}, True), ("ArtifactData", self.page_set()[1], True)]
        self.assertIsNotNone(self.verdict(self.PICK, calls))

    def test_pk_red_pick_with_no_link_blocks_whatever_the_calls(self):
        # Catches: another collection or a get passing as the send. An items update passes (the green test below).
        for call in (self.page_set(collection="notes"), self.page_set(action="get")):
            with self.subTest(call=call):
                self.assertIsNotNone(self.verdict(self.PICK, [call]))

    def test_pk_red_page_link_alone_blocks_whatever_the_calls(self):
        # A page link alone is not a send. A link only shows the page; nothing reaches the writer, so the question still blocks.
        reply = self.PICK + "\n" + self.PAGE
        for calls in ([], [self.page_set(collection="notes")], [self.page_set(action="get")]):
            with self.subTest(calls=calls):
                self.assertIsNotNone(self.verdict(reply, calls))

    def no_page_repo(self):
        """A repo with no waiting page. The question box counts there, and nowhere else."""
        bare = os.path.join(self.tmp.name, "bare")
        if not os.path.isdir(bare):
            os.makedirs(os.path.join(bare, ".git"))
        return bare

    def test_pk_green_unknown_page_box_and_write_pass(self):
        # With no waiting page, the box or the writer's items write still passes (spec v2, "No page").
        bare = self.no_page_repo()
        self.assertIsNone(self.verdict(self.PICK + "\n" + self.PAGE, [self.page_set()], repo=bare))
        self.assertIsNone(self.verdict(self.PICK, [("AskUserQuestion", {}, False)], repo=bare))

    def test_pk_green_update_and_batch_writes_pass(self):
        batch = ("ArtifactData", {"action": "batch", "url": self.PAGE, "writes": [
            {"op": "set", "collection": "items", "doc_id": "q1", "data": {}}]}, False)
        other = ("ArtifactData", {"action": "batch", "url": self.PAGE, "writes": [
            {"op": "set", "collection": "notes", "doc_id": "q1", "data": {}}]}, False)
        reply = self.PICK + "\n" + self.PAGE
        self.assertIsNone(self.verdict(reply, [self.page_set(action="update")]))
        self.assertIsNone(self.verdict(reply, [batch]))
        self.assertIsNotNone(self.verdict(reply, [other]))
        self.assertIsNotNone(self.verdict(self.PICK, [other]))

    def test_pk_green_controls_pass(self):
        # The box passes only in a repo with no waiting page; in a page repo the writer's write is the route.
        self.assertIsNone(self.verdict(self.PICK, [("AskUserQuestion", {}, False)], repo=self.no_page_repo()))
        self.assertIsNone(self.verdict(self.PICK + "\n\nSee " + self.PAGE, [self.page_set()]))

    def assert_pick_blocked(self, reply, repo=None):
        out = self.verdict(reply, repo=repo)
        self.assertIsNotNone(out, "the pick passed")
        self.assertEqual(out["decision"], "block")
        self.assertIn("Pick guard", out["reason"])

    def test_pk_red_reply_links_page_with_no_write_blocks(self):
        # A link to the page with no write does not reach the writer, so a pick with only that link still blocks.
        self.assertIsNotNone(self.verdict(self.PICK + "\n\nSee " + self.PAGE))

    def test_pk_red_five_minute_promise_blocks(self):
        # A promise to send after 5 minutes passes nothing. The question must reach the page writer in its
        # own turn, so a wait does not count as a send.
        for phrase in ("5 min", "5 minutes", "5-minute", "five minutes"):
            with self.subTest(phrase=phrase):
                reply = ("> **Done** OTHER read the code\n"
                         "> **Input Needed** Two ways. Ask in chat; after %s unanswered it goes to the "
                         "waiting page.\n> A (my pick): fold the guard\n> B: add a second hook\n> "
                         + self.DEPARTS_LINE + "\n> **Next** wait") % phrase
                self.assert_pick_blocked(reply)

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

    def test_pk_green_wait_without_a_waiting_page_is_not_blocked(self):
        # Catches: a repo with no waiting page (no extras file, or one with no waiting-page key) blocked on
        # the wait. Such a pick is not blocked; the hook says it was not sent (spec v2, "No page").
        reply = ("> **Done** OTHER read the code\n"
                 "> **Input Needed** Two ways. After 5 minutes unanswered it goes to the waiting page.\n"
                 "> A (my pick): fold the guard\n> B: add a second hook\n> " + self.DEPARTS_LINE + "\n"
                 "> **Next** wait")
        bare = os.path.join(self.tmp.name, "bare")
        os.makedirs(os.path.join(bare, ".git"))
        nokey = os.path.join(self.tmp.name, "nokey")
        os.makedirs(os.path.join(nokey, ".git"))
        os.makedirs(os.path.join(nokey, ".claude"))
        with open(os.path.join(nokey, ".claude", "layout-extras.json"), "w") as f:
            json.dump({"kinds": {}}, f)
        for repo in (bare, nokey):
            with self.subTest(repo=repo):
                out = self.verdict(reply, repo=repo)
                self.assertIsNotNone(out, "the unsent pick was not reported")
                self.assertNotEqual(out.get("decision"), "block", out)
                self.assertIn("no waiting page", out.get("systemMessage", ""))

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
            # Catches: a quoted earlier answer read as a pick.
            "> **Done** OTHER read it\n> **Input Needed** You picked A on Oct 26; I went with it.\n> **Next** wait",
            "> **Done** OTHER read it\n> **Input Needed** A decision is open. B was the old plan.",
            # Catches: options outside Input Needed read as a pick.
            "> **Done** OTHER two ways: A (my pick) or B\n> **Next**\n> 1. one\n> 2. two",
            # Catches: "X or Y" in a plain ask read as a pick. No question mark, so no question either (spec v2.1).
            "> **Done** OTHER read it\n> **Input Needed** Does Q or A mode apply.",
            "> **Done** OTHER read it\n> **Input Needed** Rename I or U in the code.",
            "> **Done** OTHER read it\n> **Input Needed** Is X or Y the field.",
            "> **Done** OTHER read it\n> **Input Needed** Is A or B the field.",
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
        # The Departs from check is judged on its own; the box is the route only where no page exists.
        bare = self.no_page_repo()
        box = ("AskUserQuestion", {}, False)
        for landed in (False, True):
            with self.subTest(landed=landed):
                self.assertIsNone(self.verdict(self.PICK, [box], landed=landed, repo=bare))
                self.assertIsNone(self.verdict(self.PICK_LINKED, [self.page_set()], landed=landed))
        self.assertIsNone(self.verdict(hyphen, [box], repo=bare))

    def test_dp_green_no_pick_needs_no_line(self):
        # Catches: an Input Needed item with no pick refused for its missing line (out of scope).
        bare = self.no_page_repo()
        rows = ("> **Done** OTHER read it\n> **Input Needed** Should the guard also cover Codex? I wait.\n> **Next** wait",
                "> **Done** OTHER read it\n> **Input Needed** You picked A on Oct 26; I went with it.\n> **Next** wait")
        for row in rows:
            for landed in (False, True):
                with self.subTest(row=row, landed=landed):
                    # The "?" row is a question under spec v2.1. With no waiting page, the box passes it.
                    self.assertIsNone(self.verdict(row, [("AskUserQuestion", {}, False)], landed=landed, repo=bare))

    def test_dp_one_predicate_for_the_report_and_the_chat_box(self):
        # Catches: a report copy of the rule that judges a line the chat box does not. Both read question_form.
        # The line is judged in a repo with no waiting page, where the box is the route, so the Departs from
        # check is what refuses it.
        import question_form  # the one home of the rule (hooks/ is on sys.path)
        bare = self.no_page_repo()
        bad = ["> Departs from:", "> Departs from: agent-model-cap — Opus above the row stays the existing ask"]
        for line in bad:
            with self.subTest(line=line):
                reply = self.PICK_BARE.replace("> **Next** wait", line + "\n> **Next** wait")
                out = self.verdict(reply, [("AskUserQuestion", {}, False)], repo=bare)
                box = {"questions": [{"question": "\n".join(self.FORM_LINES + [line[2:]]), "header": "Ship",
                                      "multiSelect": False,
                                      "options": [{"label": "Keep it", "description": "Gain: a. Lose: b."},
                                                  {"label": "Drop it", "description": "Gain: c. Lose: d."}]}]}
                self.assertEqual(question_form.chat_hit(box)[0], "question-departs")
                self.assertIsNotNone(out, "the report passed a line the chat box refuses")
                self.assertRegex(out["reason"], r"(?i)departs from")
        good = "> " + self.DEPARTS_LINE
        self.assertIsNone(self.verdict(self.PICK_BARE.replace("> **Next** wait", good + "\n> **Next** wait"),
                                       [("AskUserQuestion", {}, False)], repo=bare))

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
        bare = self.no_page_repo()  # the box is the route here: the question has no waiting page to reach
        for line in ("> - Departs from: " + text, "> **Departs from:** " + text, "> * Departs from: " + text):
            for landed in (False, True):
                with self.subTest(line=line, landed=landed):
                    reply = self.PICK_BARE.replace("> **Next** wait", line + "\n> **Next** wait")
                    self.assertIsNone(self.verdict(reply, [("AskUserQuestion", {}, False)], landed=landed, repo=bare))


import itertools
_CALL_IDS = itertools.count(1)


class SameTurnWriter:
    """The same-turn send a question needs: an ArtifactData get of the page's meta, whose result names the
    writer, then a send to that writer id. A TestCase mixes it in and sets PAGE to the waiting page its repo
    names."""

    WRITER = "session_writer1"

    DELIVERED = '{"status":"delivered"}'  # a cloud send_message result whose send reached its session
    NOT_DELIVERED = '{"status":"queued"}'  # a result that reads as not delivered

    def call(self, name, input_, result=None, side=False, is_error=False, tool_use_result=None):
        """The records one tool call leaves: the call, and its result when one is given. is_error sets the
        result's is_error flag (a failed cloud send); tool_use_result is the record's toolUseResult (a failed
        local SendMessage says success false there, with no is_error)."""
        use_id = "toolu_%d" % next(_CALL_IDS)
        recs = [{"type": "assistant", "isSidechain": side, "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": use_id, "name": name, "input": input_}]}}]
        if result is not None:
            block = {"type": "tool_result", "tool_use_id": use_id, "content": result}
            if is_error:
                block["is_error"] = True
            rec = {"type": "user", "isSidechain": side, "message": {"role": "user", "content": [block]}}
            if tool_use_result is not None:
                rec["toolUseResult"] = tool_use_result
            recs.append(rec)
        return recs

    def send(self, session_id=None, to=None, result=None, is_error=False, tool_use_result=None):
        """A send: send_message names its target by session_id, SendMessage by to. `result` is the send's tool
        result text, None when the transcript holds none. is_error and tool_use_result go to call as given."""
        out = {"result": result, "is_error": is_error, "tool_use_result": tool_use_result}
        if to is None:
            return self.call("mcp__claude-code-remote__send_message",
                             {"session_id": session_id, "message": "pick"}, **out)
        return self.call("SendMessage", {"to": to, "message": "pick"}, **out)

    def writer_read(self, writer, collection="meta", doc_id="page"):
        """An ArtifactData get whose result carries the writer id."""
        return self.call("ArtifactData", {"action": "get", "collection": collection, "doc_id": doc_id,
                                          "url": self.PAGE},
                         result=json.dumps({"writer": writer, "url": self.PAGE}))


class QuestionReachesPageTests(SameTurnWriter, unittest.TestCase):
    """Every question for the owner reaches the page writer in the turn it is asked. A question is an
    offered pick, or an Input Needed sentence ending in "?" outside quotes. The Stop check reads the turn
    alone: no clock, no state file.
    Owner-facing turn: the question box (main session), a send to the writer id, or an ArtifactData set,
    update or batch under collection items. Lane turn: a send to @parent or the parent id, or to the writer
    id. A promise, a page link, a box or an items write passes nothing in a lane."""

    PAGE = "https://claude.ai/artifact/waitpage2"
    OLDER_WRITER = "session_writer0"
    PARENT = "session_parent1"
    LANE_ENV = "cse_lane1"  # override.remote_session_id() reads this as LANE_ID
    LANE_ID = "session_lane1"
    DEPARTS = "Departs from: lint/report_guard.py pick check — it also needs a Departs from line"
    PICK = ["Two ways:", "A (my pick): fold the guard", "B: add a second hook", DEPARTS]
    PROMISE = ["Ask in chat; after 5 minutes unanswered it goes to the waiting page.",
               "A (my pick): fold the guard", "B: add a second hook", DEPARTS]
    LINKED = PICK + [PAGE]
    QUESTION = ["Close q_max #969 as replaced by #1010?"]
    NO_KEY = object()  # make_repo's writer default: the extras file holds no "page-writer" key

    def setUp(self):
        self.run_dir = tempfile.mkdtemp(dir=_ISOLATION["dir"])
        self.addCleanup(shutil.rmtree, self.run_dir, ignore_errors=True)
        self.cfg = os.path.join(self.run_dir, "cfg")
        self.home = os.path.join(self.run_dir, "home")
        os.makedirs(self.cfg)
        os.makedirs(self.home)
        self.repo = self.make_repo("repo")

    def make_repo(self, name, page=True, writer=NO_KEY):
        """A repo whose extras file names the waiting page (when page is true). `writer` sets its
        "page-writer" key to that JSON value (None, "" or a non-string included); NO_KEY leaves it out."""
        repo = os.path.join(self.run_dir, name)
        os.makedirs(os.path.join(repo, ".git"))
        if page:
            os.makedirs(os.path.join(repo, ".claude"))
            keys = {"kinds": {}, "waiting-page": self.PAGE}
            if writer is not self.NO_KEY:
                keys["page-writer"] = writer
            with open(os.path.join(repo, ".claude", "layout-extras.json"), "w") as f:
                json.dump(keys, f)
        return repo

    def extras_key(self, repo):
        """The "page-writer" value on disk in `repo`, or NO_KEY when the file holds no such key."""
        with open(os.path.join(repo, ".claude", "layout-extras.json")) as f:
            keys = json.load(f)
        return keys["page-writer"] if "page-writer" in keys else self.NO_KEY

    def reply(self, body):
        """A report whose Input Needed item holds the lines of `body`. Its Done line names a commit, so a
        landed turn passes the report's shape."""
        lines = ["> **Done** BUILT abc123", "> **Input Needed** " + body[0]]
        lines += ["> " + line for line in body[1:]]
        return "\n".join(lines + ["> **Next** wait"])

    def items_write(self, action="set", collection="items"):
        return self.call("ArtifactData", {"action": action, "collection": collection, "url": self.PAGE,
                                          "doc_id": "q1", "data": {}})

    def items_batch(self):
        return self.call("ArtifactData", {"action": "batch", "url": self.PAGE, "writes": [
            {"op": "set", "collection": "items", "doc_id": "q1", "data": {}}]})

    def box(self, side=False):
        return self.call("AskUserQuestion", {}, side=side)

    def lane_record(self, tags=("cs-build:lane",), parent=PARENT):
        """This session's own get_session result. A lane tag or a parent id marks a lane."""
        ccr = {"id": self.LANE_ID, "tags": list(tags), "parent_session_id": parent}
        return self.call("mcp__claude-code-remote__get_session", {"session_id": self.LANE_ID},
                         result=json.dumps({"ccr": ccr}))

    def stop(self, records, env_id=None, repo=None, stop_active=False, session_id=None):
        """Run the Stop hook on `records`. env_id is this session's remote id (a lane sets it); None is owner-facing.
        session_id, when given, is the hook's own session id: an override file is named by it."""
        path = write_transcript(records, self.run_dir)
        hook = {"hook_event_name": "Stop", "transcript_path": path, "stop_hook_active": stop_active,
                "cwd": repo or self.repo}
        if session_id:
            hook["session_id"] = session_id
        env = dict(os.environ, CLAUDE_CONFIG_DIR=self.cfg, HOME=self.home)
        env.pop("CLAUDE_CODE_REMOTE_SESSION_ID", None)
        if env_id:
            env["CLAUDE_CODE_REMOTE_SESSION_ID"] = env_id
        run = run_guard(REPORT_GUARD, hook, env=env)
        self.assertEqual(run.returncode, 0, run.stderr)
        return json.loads(run.stdout) if run.stdout.strip() else None

    def lane(self, *records, repo=None):
        """Stop on a lane: its own record first, then `records`. A lane's input is peer messages."""
        return self.stop([*self.lane_record(), *records], env_id=self.LANE_ENV, repo=repo)

    def assert_blocked(self, out, *phrases):
        self.assertIsNotNone(out, "the question passed; expected a block")
        self.assertEqual(out.get("decision"), "block", out)
        for phrase in phrases:
            self.assertIn(phrase, out.get("reason", ""), out)

    def written_files(self):
        return [os.path.join(d, name) for top in (self.cfg, self.home)
                for d, _, names in os.walk(top) for name in names]

    # Owner-facing turn.

    def test_qm_red_question_mark_sentence_blocks_with_no_send(self):
        # Catches: an Input Needed sentence ending in "?" read as no question, so it never reaches the page.
        out = self.stop([human("decide"), assistant_text(self.reply(self.QUESTION))])
        self.assert_blocked(out, "Pick guard")

    def test_qm_red_question_mark_rows_block(self):
        # Catches: a plain "X or Y?" ask with no box or send passing as a non-pick (spec v2.1).
        rows = ("Should the guard also cover Codex? I wait.", "Does Q or A mode apply?",
                "Rename I or U in the code?", "Is X or Y the field?", "Is A or B the field?")
        for row in rows:
            with self.subTest(row=row):
                self.assert_blocked(self.stop([human("decide"), assistant_text(self.reply([row]))]), "Pick guard")

    def test_qm_green_question_mark_in_a_quoted_past_question_is_no_question(self):
        # Catches: a "?" inside a quoted past question read as a question asked now (false alarm).
        out = self.stop([human("decide"), assistant_text(self.reply(['You asked "merge it?" and I picked A.']))])
        self.assertIsNone(out)

    def test_qm_green_turn_with_no_question_has_no_output_and_no_file(self):
        # Catches: a turn with no question writing a file, or printing a block.
        out = self.stop([human("status?"), assistant_text(self.reply(["None."]))])
        self.assertIsNone(out)
        self.assertEqual(self.written_files(), [])

    def test_qm_green_box_in_the_turn_passes(self):
        # Catches: a box in the turn refused in a repo with no waiting page, where the box is the route.
        bare = self.make_repo("bare", page=False)
        out = self.stop([human("decide"), *self.box(), assistant_text(self.reply(self.PICK))], repo=bare)
        self.assertIsNone(out)

    def test_qm_red_sidechain_box_does_not_count(self):
        # Catches: an agent's box read as the owner's question box.
        out = self.stop([human("decide"), *self.box(side=True), assistant_text(self.reply(self.PICK))])
        self.assert_blocked(out, "Pick guard")

    def test_qm_green_send_to_the_writer_passes(self):
        # Catches: a send to the writer id not read as the send, in either field.
        for label, send in (("session_id", self.send(session_id=self.WRITER)),
                            ("to", self.send(to=self.WRITER))):
            with self.subTest(field=label):
                out = self.stop([human("decide"), *self.writer_read(self.WRITER), *send,
                                 assistant_text(self.reply(self.PICK))])
                self.assertIsNone(out)

    def test_qm_red_send_to_another_session_blocks(self):
        # Catches: a send to a session that is not the writer passing as the question's send.
        out = self.stop([human("decide"), *self.writer_read(self.WRITER),
                         *self.send(session_id="session_other9"), assistant_text(self.reply(self.PICK))])
        self.assert_blocked(out, "Pick guard", self.WRITER)

    def test_qm_red_unknown_writer_blocks_and_names_the_page_read(self):
        # Catches: a send to an id that no meta/page read named passing; the block says how to find the writer.
        out = self.stop([human("decide"), *self.send(session_id=self.WRITER), assistant_text(self.reply(self.PICK))])
        self.assert_blocked(out, "Pick guard", "the page writer is not known to this session", self.PAGE)

    def test_qm_red_writer_from_another_item_does_not_count(self):
        # Catches: a writer id read from a get of another item taken as the page writer.
        out = self.stop([human("decide"), *self.writer_read(self.WRITER, collection="items", doc_id="q1"),
                         *self.send(session_id=self.WRITER), assistant_text(self.reply(self.PICK))])
        self.assert_blocked(out, "Pick guard", "the page writer is not known to this session")

    def test_qm_green_newest_writer_read_names_the_writer(self):
        # Catches: the oldest meta/page read taken as the writer when a newer one names another id.
        reads = [*self.writer_read(self.OLDER_WRITER), *self.writer_read(self.WRITER)]
        self.assertIsNone(self.stop([human("decide"), *reads, *self.send(session_id=self.WRITER),
                                     assistant_text(self.reply(self.PICK))]))
        out = self.stop([human("decide"), *reads, *self.send(session_id=self.OLDER_WRITER),
                         assistant_text(self.reply(self.PICK))])
        self.assert_blocked(out, "Pick guard", self.WRITER)

    def test_qm_green_items_write_in_the_turn_passes(self):
        # Catches: the writer's own items write (set, update, batch) not read as the send.
        for label, write in (("set", self.items_write("set")), ("update", self.items_write("update")),
                             ("batch", self.items_batch())):
            with self.subTest(write=label):
                out = self.stop([human("decide"), *write, assistant_text(self.reply(self.PICK))])
                self.assertIsNone(out)

    def test_qm_red_items_read_or_other_collection_does_not_count(self):
        # Catches: a read, or a write to another collection, passing as the send.
        for label, write in (("get", self.items_write("get")), ("notes", self.items_write("set", "notes"))):
            with self.subTest(write=label):
                out = self.stop([human("decide"), *write, assistant_text(self.reply(self.PICK))])
                self.assert_blocked(out, "Pick guard")

    def test_qm_red_act_in_an_earlier_turn_does_not_count(self):
        # Catches: a send, a box or an items write from an earlier turn passing for this turn's question.
        earlier = (("send", [*self.writer_read(self.WRITER), *self.send(session_id=self.WRITER)]),
                   ("box", self.box()),
                   ("items", self.items_write("set")))
        for label, act in earlier:
            with self.subTest(act=label):
                out = self.stop([human("first"), *act, assistant_text("Sent earlier."), human("decide"),
                                 assistant_text(self.reply(self.PICK))])
                self.assert_blocked(out, "Pick guard")

    def test_qm_red_send_before_a_peer_message_does_not_count(self):
        # Catches: a send before the last incoming message (a peer's) read as this turn's send.
        out = self.stop([human("decide"), *self.writer_read(self.WRITER), *self.send(session_id=self.WRITER),
                         peer_msg("status?"), assistant_text(self.reply(self.PICK))])
        self.assert_blocked(out, "Pick guard")

    def test_qm_green_ack_from_the_writer_after_a_send_keeps_the_turn(self):
        # Catches: the writer's ack of this turn's send starting a new turn, which hides the send and blocks
        # a question that send already covers. The ack is a peer message from the session the send went to.
        ack = peer_msg("got it", from_session=self.WRITER)
        for label, send in (("session_id", self.send(session_id=self.WRITER)), ("to", self.send(to=self.WRITER))):
            with self.subTest(field=label):
                out = self.stop([human("decide"), *self.writer_read(self.WRITER), *send, ack,
                                 assistant_text(self.reply(["Close q_max #969?"]))])
                self.assertIsNone(out)

    def test_qm_red_peer_from_the_writer_with_no_send_starts_a_turn(self):
        # Catches: an ack taken by its sender alone. With no send in the turn the peer message is new work,
        # so the reply that follows it has no send and blocks.
        out = self.stop([human("decide"), *self.writer_read(self.WRITER),
                         peer_msg("status?", from_session=self.WRITER),
                         assistant_text(self.reply(["Close q_max #969?"]))])
        self.assert_blocked(out, "Pick guard")

    def test_qm_red_promise_words_or_page_link_alone_block(self):
        # Catches: the 5-minute promise, or a page link, passing a question with no send (both clauses retired).
        for body in (self.PROMISE, self.LINKED):
            with self.subTest(body=body[0]):
                out = self.stop([human("decide"), assistant_text(self.reply(body))])
                self.assert_blocked(out, "Pick guard")

    def test_qm_green_no_page_is_not_blocked_and_says_so(self):
        # Catches: a repo with no waiting page (or no repo) blocked, or the pick left unreported.
        bare = self.make_repo("bare", page=False)
        loose = os.path.join(self.run_dir, "loose")
        os.makedirs(loose)
        for label, body, repo in (("pick", self.PICK, bare), ("promise", self.PROMISE, bare),
                                  ("no repo", self.PICK, loose)):
            with self.subTest(case=label):
                out = self.stop([human("decide"), assistant_text(self.reply(body))], repo=repo)
                self.assertIsNotNone(out, "the unsent pick was not reported")
                self.assertNotEqual(out.get("decision"), "block", out)
                self.assertIn("pick not sent", out.get("systemMessage", ""))
                self.assertIn("no waiting page", out.get("systemMessage", ""))

    def test_qm_green_stop_hook_active_never_blocks(self):
        # Catches: a rewrite blocked again for a question the first Stop already judged.
        for body in (self.PICK, self.QUESTION):
            with self.subTest(body=body[0]):
                out = self.stop([human("decide"), assistant_text(self.reply(body))], stop_active=True)
                self.assertIsNone(out)

    def test_qm_landed_turn_follows_the_same_rule(self):
        commit = self.call("Bash", {"command": "git commit -m x"})
        self.assert_blocked(self.stop([human("decide"), *commit, assistant_text(self.reply(self.PICK))]),
                            "Pick guard")
        self.assertIsNone(self.stop([human("decide"), *commit, *self.writer_read(self.WRITER),
                                     *self.send(session_id=self.WRITER), assistant_text(self.reply(self.PICK))]))

    def test_qm_green_own_record_without_a_lane_tag_is_owner_facing(self):
        # Catches: a session record with no lane tag and no parent read as a lane. A lane refuses the box, so a
        # pass in a repo with no waiting page shows the record reads as owner-facing.
        bare = self.make_repo("bare", page=False)
        out = self.stop([human("decide"), *self.lane_record(tags=("coordinator",), parent=None), *self.box(),
                         assistant_text(self.reply(self.PICK))], env_id=self.LANE_ENV, repo=bare)
        self.assertIsNone(out)

    def test_qm_red_peer_only_session_with_no_lane_record_gets_the_owner_rule(self):
        # Catches: the early return when no human record exists, which skips the pick check.
        out = self.stop([peer_msg("status?"), assistant_text(self.reply(self.PICK))])
        self.assert_blocked(out, "Pick guard")

    def test_qm_red_question_mark_before_markup_blocks(self):
        # Catches: a "?" followed by bold, a closing bracket, a dash or a closing curly quote read as no question.
        for body in ("**Merge #5 now?**", "(merge it now?)", "Merge it now?—", "Merge it now?”"):
            with self.subTest(body=body):
                out = self.stop([human("decide"), assistant_text(self.reply([body]))])
                self.assert_blocked(out, "Pick guard")

    def test_qm_green_url_query_alone_is_no_question(self):
        # Catches: a "?" inside a URL read as a question. A "?" counts only before whitespace or the end.
        out = self.stop([human("decide"), assistant_text(self.reply(["https://x.y/a?b=1"]))])
        self.assertIsNone(out)

    def test_qm_red_lone_quote_does_not_hide_a_question(self):
        # Catches: a lone double quote paired with a later one, which hides the "?" that falls between them.
        out = self.stop([human("decide"), assistant_text(self.reply(['Set 5" rack, merge it? Pick "main".']))])
        self.assert_blocked(out, "Pick guard")

    def test_qm_green_single_quoted_past_question_is_no_question(self):
        # Catches: a "?" inside a single-quoted past question read as a question asked now (false alarm).
        out = self.stop([human("decide"), assistant_text(self.reply(["You asked 'merge it?' and I picked A"]))])
        self.assertIsNone(out)

    def test_qm_red_question_mark_before_a_word_or_link_markup_blocks(self):
        # Catches: a "?" followed by a dash and a word, or by the closing bracket of link markup,
        # read as no question.
        for body in ("Merge it now?—yes", "[Merge #5?](https://x.y/5)"):
            with self.subTest(body=body):
                out = self.stop([human("decide"), assistant_text(self.reply([body]))])
                self.assert_blocked(out, "Pick guard")

    def test_qm_red_lone_single_quote_does_not_hide_a_question(self):
        # Catches: a lone apostrophe paired with a later single quote, which hides the "?" that falls between them.
        out = self.stop([human("decide"), assistant_text(self.reply(["Don't merge it? Pick 'main'."]))])
        self.assert_blocked(out, "Pick guard")

    def test_qm_red_owner_session_with_no_record_sends_to_parent_blocks(self):
        # Catches: an owner-facing session (no own record, so no lane evidence) whose question goes to @parent
        # passing as if @parent were a route. An owner-facing session has no parent, so the question still blocks.
        for label, send in (("@parent", self.send(session_id="@parent")), ("to parent", self.send(to="parent"))):
            with self.subTest(form=label):
                out = self.stop([human("decide"), *send, assistant_text(self.reply(self.PICK))])
                self.assert_blocked(out, "Pick guard")

    # Owner-facing turn with no meta/page read: the layout's "page-writer" key is the writer.

    def test_qm_layout_writer_green_send_to_the_key_id_passes(self):
        # Catches: a send to the layout key's writer refused when the transcript holds no meta/page read, so a
        # cloud session that never reads meta/page is blocked for a question it sent to the real writer. The send
        # carries a delivered result, so only the key's writer id decides.
        bare = self.make_repo("bare_key")
        keyed = self.make_repo("keyed_key", writer=self.WRITER)
        self.assertEqual(self.extras_key(keyed), self.WRITER, "scope: the keyed repo's extras file lacks the writer key")
        for label, send in (("session_id", self.send(session_id=self.WRITER, result=self.DELIVERED)),
                            ("to", self.send(to=self.WRITER, result=self.DELIVERED))):
            with self.subTest(field=label):
                records = [human("decide"), *send, assistant_text(self.reply(self.PICK))]
                self.assert_blocked(self.stop(records, repo=bare), "Pick guard", "the page writer is not known to this session")
                self.assertIsNone(self.stop(records, repo=keyed), "a send to the layout key's writer id was refused")

    def test_qm_layout_writer_green_ack_from_the_key_writer_keeps_the_turn(self):
        # Catches: the layout writer's ack after a send starting a new turn, which hides the send and blocks the question.
        bare = self.make_repo("bare_key")
        keyed = self.make_repo("keyed_key", writer=self.WRITER)
        self.assertEqual(self.extras_key(keyed), self.WRITER, "scope: the keyed repo's extras file lacks the writer key")
        ack = peer_msg("got it", from_session=self.WRITER)
        for label, send in (("session_id", self.send(session_id=self.WRITER, result=self.DELIVERED)),
                            ("to", self.send(to=self.WRITER, result=self.DELIVERED))):
            with self.subTest(field=label):
                records = [human("decide"), *send, ack, assistant_text(self.reply(["Close q_max #969?"]))]
                self.assert_blocked(self.stop(records, repo=bare), "Pick guard", "the page writer is not known to this session")
                self.assertIsNone(self.stop(records, repo=keyed), "the layout writer's ack after a send started a new turn")

    def test_qm_layout_writer_red_send_to_another_id_blocks(self):
        # Catches: a send to a session that is not the layout key's writer passing because the key is set.
        keyed = self.make_repo("keyed_key", writer=self.WRITER)
        self.assertEqual(self.extras_key(keyed), self.WRITER, "scope: the keyed repo's extras file lacks the writer key")
        sends = (("session_id", self.send(session_id="session_other9")), ("to", self.send(to="session_other9")),
                 ("no id", self.call("mcp__claude-code-remote__send_message", {"message": "pick"})))
        for label, send in sends:
            with self.subTest(form=label):
                out = self.stop([human("decide"), *send, assistant_text(self.reply(self.PICK))], repo=keyed)
                self.assert_blocked(out, "Pick guard")

    def test_qm_layout_writer_red_no_send_this_turn_blocks(self):
        # Catches: the layout key alone passing a question, or an earlier turn's send to the key id counting as this turn's.
        keyed = self.make_repo("keyed_key", writer=self.WRITER)
        self.assertEqual(self.extras_key(keyed), self.WRITER, "scope: the keyed repo's extras file lacks the writer key")
        earlier = (("no send", []),
                   ("send in an earlier turn", [human("first"), *self.send(session_id=self.WRITER),
                                                assistant_text("Sent earlier.")]))
        for label, before in earlier:
            with self.subTest(case=label):
                out = self.stop([*before, human("decide"), assistant_text(self.reply(self.PICK))], repo=keyed)
                self.assert_blocked(out, "Pick guard")

    def test_qm_layout_writer_red_no_usable_key_still_says_not_known(self):
        # Catches: a missing, null, empty or non-string key read as a writer id, so a send to any id passes.
        for label, value in (("no key", self.NO_KEY), ("null", None), ("empty", ""), ("number", 5),
                             ("list", [self.WRITER])):
            with self.subTest(key=label):
                repo = self.make_repo("key_" + label.replace(" ", "_"), writer=value)
                self.assertEqual(self.extras_key(repo), value, "scope: the repo's extras file does not hold the key as set")
                out = self.stop([human("decide"), *self.send(session_id=self.WRITER), assistant_text(self.reply(self.PICK))],
                                repo=repo)
                self.assert_blocked(out, "Pick guard", "the page writer is not known to this session")

    def test_qm_layout_writer_transcript_read_wins_over_the_key(self):
        # Catches: the layout key taking the place of a meta/page read that names another writer.
        keyed = self.make_repo("keyed_key", writer=self.OLDER_WRITER)
        self.assertEqual(self.extras_key(keyed), self.OLDER_WRITER, "scope: the keyed repo's extras file lacks the writer key")
        reads = self.writer_read(self.WRITER)
        out = self.stop([human("decide"), *reads, *self.send(session_id=self.OLDER_WRITER),
                         assistant_text(self.reply(self.PICK))], repo=keyed)
        self.assert_blocked(out, "Pick guard", self.WRITER)
        self.assertIsNone(self.stop([human("decide"), *reads, *self.send(session_id=self.WRITER),
                                     assistant_text(self.reply(self.PICK))], repo=keyed),
                          "a send to the transcript's writer was refused when the layout key names another id")

    def test_qm_layout_writer_red_meta_read_naming_no_writer_blocks(self):
        # Catches: a meta/page read that names no writer read as no read, so the layout key stands in for it and a
        # same-turn send to the key id passes. Any meta/page get in the transcript keeps the layout key out.
        keyed = self.make_repo("keyed_key", writer=self.WRITER)
        self.assertEqual(self.extras_key(keyed), self.WRITER, "scope: the keyed repo's extras file lacks the writer key")
        page_json = json.dumps({"url": self.PAGE, "title": "Waiting page"})
        reads = (("collection", self.call("ArtifactData", {"action": "get", "collection": "meta", "doc_id": "page",
                                                           "url": self.PAGE}, result=page_json)),
                 ("path", self.call("ArtifactData", {"action": "get", "path": "meta/page", "url": self.PAGE},
                                    result=page_json)))
        for label, read in reads:
            for field, send in (("session_id", self.send(session_id=self.WRITER)), ("to", self.send(to=self.WRITER))):
                with self.subTest(read=label, field=field):
                    out = self.stop([human("decide"), *read, *send, assistant_text(self.reply(self.PICK))], repo=keyed)
                    self.assert_blocked(out, "Pick guard", "the page writer is not known to this session")

    def test_qm_layout_writer_lane_send_to_the_key_id_is_refused(self):
        # Catches: a lane reading the layout key, so a send to the key's writer passes where a lane's own chat never reaches the owner.
        keyed = self.make_repo("keyed_key", writer=self.WRITER)
        self.assertEqual(self.extras_key(keyed), self.WRITER, "scope: the keyed repo's extras file lacks the writer key")
        out = self.lane(peer_msg("pick?"), *self.send(session_id=self.WRITER), assistant_text(self.reply(self.PICK)),
                        repo=keyed)
        self.assert_blocked(out, "Lane pick guard")

    def test_qm_layout_writer_red_key_send_errored_by_is_error_blocks(self):
        # Catches: a send to the layout key's writer whose result has is_error counted as the send, so the question
        # reached no one and the guard passed. The result text reads delivered, so only the error flag decides.
        keyed = self.make_repo("keyed_key", writer=self.WRITER)
        self.assertEqual(self.extras_key(keyed), self.WRITER, "scope: the keyed repo's extras file lacks the writer key")
        for label, send in (("session_id", self.send(session_id=self.WRITER, result=self.DELIVERED, is_error=True)),
                            ("to", self.send(to=self.WRITER, result=self.DELIVERED, is_error=True))):
            with self.subTest(field=label):
                out = self.stop([human("decide"), *send, assistant_text(self.reply(self.PICK))], repo=keyed)
                self.assert_blocked(out, "Pick guard", "the page writer is session " + self.WRITER)

    def test_qm_layout_writer_red_key_send_errored_by_success_false_blocks(self):
        # Catches: a send to the layout key's writer whose record says toolUseResult success false (a failed local
        # SendMessage, with no is_error flag) counted as the send. The result text reads delivered, so only the
        # success flag decides.
        keyed = self.make_repo("keyed_key", writer=self.WRITER)
        self.assertEqual(self.extras_key(keyed), self.WRITER, "scope: the keyed repo's extras file lacks the writer key")
        failed = {"success": False, "message": "fixture: the send did not reach its session"}
        for label, send in (("session_id", self.send(session_id=self.WRITER, result=self.DELIVERED,
                                                     tool_use_result=failed)),
                            ("to", self.send(to=self.WRITER, result=self.DELIVERED, tool_use_result=failed))):
            with self.subTest(field=label):
                out = self.stop([human("decide"), *send, assistant_text(self.reply(self.PICK))], repo=keyed)
                self.assert_blocked(out, "Pick guard", "the page writer is session " + self.WRITER)

    def test_qm_layout_writer_red_key_send_without_a_result_blocks(self):
        # Catches: a send to the layout key's writer with no result record in the transcript counted as delivered.
        keyed = self.make_repo("keyed_key", writer=self.WRITER)
        self.assertEqual(self.extras_key(keyed), self.WRITER, "scope: the keyed repo's extras file lacks the writer key")
        for label, send in (("session_id", self.send(session_id=self.WRITER)), ("to", self.send(to=self.WRITER))):
            with self.subTest(field=label):
                out = self.stop([human("decide"), *send, assistant_text(self.reply(self.PICK))], repo=keyed)
                self.assert_blocked(out, "Pick guard", "the page writer is session " + self.WRITER)

    def test_qm_layout_writer_red_key_send_not_delivered_blocks(self):
        # Catches: a send to the layout key's writer whose result reads as not delivered counted as the send when no
        # error flag is set. Only the result text decides here.
        keyed = self.make_repo("keyed_key", writer=self.WRITER)
        self.assertEqual(self.extras_key(keyed), self.WRITER, "scope: the keyed repo's extras file lacks the writer key")
        for label, send in (("session_id", self.send(session_id=self.WRITER, result=self.NOT_DELIVERED)),
                            ("to", self.send(to=self.WRITER, result=self.NOT_DELIVERED))):
            with self.subTest(field=label):
                out = self.stop([human("decide"), *send, assistant_text(self.reply(self.PICK))], repo=keyed)
                self.assert_blocked(out, "Pick guard", "the page writer is session " + self.WRITER)

    def test_qm_layout_writer_green_succeeded_send_counts_past_a_later_errored_resend(self):
        # Catches: a failed resend to the layout key's writer later in the turn hiding a delivered send to it. The
        # sends pair by tool_use id, so the delivered one counts, and the writer's ack after them keeps the turn.
        keyed = self.make_repo("keyed_key", writer=self.WRITER)
        self.assertEqual(self.extras_key(keyed), self.WRITER, "scope: the keyed repo's extras file lacks the writer key")
        ack = peer_msg("got it", from_session=self.WRITER)
        for label, target in (("session_id", {"session_id": self.WRITER}), ("to", {"to": self.WRITER})):
            with self.subTest(field=label):
                records = [human("decide"), *self.send(result=self.DELIVERED, **target),
                           *self.send(result=self.DELIVERED, is_error=True, **target), ack,
                           assistant_text(self.reply(["Close q_max #969?"]))]
                self.assertIsNone(self.stop(records, repo=keyed),
                                  "a delivered send to the layout key's writer was not counted past a later failed resend")

    def test_qm_layout_writer_green_transcript_path_failed_send_keeps_main_verdict(self):
        # Catches: the failed-send rule leaking into the transcript path. A meta/page read names the writer, so a send
        # to it passes whatever its result, as on main. That verdict must not change.
        keyed = self.make_repo("keyed_key", writer=self.WRITER)
        self.assertEqual(self.extras_key(keyed), self.WRITER, "scope: the keyed repo's extras file lacks the writer key")
        reads = self.writer_read(self.WRITER)
        failed = (("is_error", self.send(session_id=self.WRITER, result=self.DELIVERED, is_error=True)),
                  ("success false", self.send(to=self.WRITER, result=self.DELIVERED,
                                              tool_use_result={"success": False})))
        for label, send in failed:
            with self.subTest(failure=label):
                out = self.stop([human("decide"), *reads, *send, assistant_text(self.reply(self.PICK))], repo=keyed)
                self.assertIsNone(out, "a failed send on the transcript path was refused; that path keeps main's verdict")

    FRESH_QUESTION_CODE = (
        "import json, sys; sys.path.insert(0, %r); import report_guard; data = json.load(sys.stdin); "
        "print(json.dumps(list(report_guard.question_problem(data['records'], data['records'], data['text'], "
        "data['hook']))))" % HERE)

    def test_qm_question_problem_works_on_a_fresh_import(self):
        # Catches: question_problem reaching for hooks/ modules that only pending_refusals puts on sys.path, so a
        # caller that imports report_guard and asks straight away fails with ImportError.
        records = [human("decide"), assistant_text(self.reply(self.QUESTION))]
        hook = {"hook_event_name": "Stop", "transcript_path": write_transcript(records, self.run_dir),
                "stop_hook_active": False, "cwd": self.repo}
        payload = json.dumps({"records": records, "text": self.reply(self.QUESTION), "hook": hook})
        env = dict(os.environ, CLAUDE_CONFIG_DIR=self.cfg, HOME=self.home)
        env.pop("CLAUDE_CODE_REMOTE_SESSION_ID", None)
        run = subprocess.run([sys.executable, "-c", self.FRESH_QUESTION_CODE], input=payload, capture_output=True,
                             text=True, timeout=15, cwd=self.run_dir, env=env)
        self.assertEqual(run.returncode, 0, "question_problem raised on a fresh import: %s" % run.stderr[-400:])
        refusal, _note = json.loads(run.stdout)
        self.assertIn("Pick guard", refusal)

    # Lane turn.

    def test_ln_green_send_to_parent_in_the_turn_passes(self):
        # Catches: a lane's question sent to its parent in its turn not read as sent, in any of the three forms.
        # The human-first shape pins the send after a human message. A peers-only lane is skipped before it.
        shapes = (("peers only", [peer_msg("pick?")]), ("human first", [human("decide"), peer_msg("pick?")]))
        forms = (("@parent", self.send(session_id="@parent")), ("parent id", self.send(session_id=self.PARENT)),
                 ("to parent", self.send(to="parent")))
        for shape, incoming in shapes:
            for label, send in forms:
                with self.subTest(shape=shape, form=label):
                    self.assertIsNone(self.lane(*incoming, *send, assistant_text(self.reply(self.PICK))))

    def test_ln_red_promise_or_page_link_alone_blocks(self):
        # Catches: a lane's promise or page link passing; a lane's chat never reaches the owner.
        for body in (self.PROMISE, self.LINKED):
            with self.subTest(body=body[0]):
                out = self.lane(peer_msg("pick?"), assistant_text(self.reply(body)))
                self.assert_blocked(out, "Lane pick guard", "its parent")

    def test_ln_red_box_or_items_write_blocks(self):
        # Catches: a lane's box or items write read as its send. Neither passes a lane.
        for label, act in (("box", self.box()), ("items", self.items_write("set"))):
            with self.subTest(act=label):
                out = self.lane(peer_msg("pick?"), *act, assistant_text(self.reply(self.PICK)))
                self.assert_blocked(out, "Lane pick guard")

    def test_ln_green_send_to_writer_passes(self):
        # Catches: a lane's send to the writer id not read as its send, in either field and either shape.
        shapes = (("peers only", [peer_msg("pick?")]), ("human first", [human("decide"), peer_msg("pick?")]))
        forms = (("session_id", self.send(session_id=self.WRITER)), ("to", self.send(to=self.WRITER)))
        for shape, incoming in shapes:
            for label, send in forms:
                with self.subTest(shape=shape, field=label):
                    out = self.lane(*self.writer_read(self.WRITER), *incoming, *send,
                                    assistant_text(self.reply(self.PICK)))
                    self.assertIsNone(out)

    def test_ln_red_send_to_another_session_blocks(self):
        # Catches: a lane's send to a session that is neither its parent nor the writer.
        out = self.lane(peer_msg("pick?"), *self.send(session_id="session_other9"),
                        assistant_text(self.reply(self.PICK)))
        self.assert_blocked(out, "Lane pick guard", "its parent")

    def test_ln_red_send_in_an_earlier_turn_blocks(self):
        # Catches: a send before the lane's last incoming message passing as this turn's send.
        out = self.lane(peer_msg("first"), *self.send(session_id="@parent"), peer_msg("second"),
                        assistant_text(self.reply(self.PICK)))
        self.assert_blocked(out, "Lane pick guard")

    def test_ln_green_ack_from_the_parent_after_a_send_keeps_the_turn(self):
        # Catches: the parent's ack of a lane's send starting a new turn, which hides the send and blocks the question.
        # The ack is a peer message from the session the send went to.
        ack = peer_msg("got it", from_session=self.PARENT)
        forms = (("@parent", self.send(session_id="@parent")), ("parent id", self.send(session_id=self.PARENT)),
                 ("to parent", self.send(to="parent")))
        for label, send in forms:
            with self.subTest(form=label):
                self.assertIsNone(self.lane(*send, ack, assistant_text(self.reply(["Close q_max #969?"]))))

    def test_ln_red_peer_from_the_parent_with_no_send_starts_a_turn(self):
        # Catches: an ack taken by its sender alone. With no send in the turn the peer message is new work,
        # and the reply that follows it blocks.
        self.assert_blocked(self.lane(peer_msg("pick?", from_session=self.PARENT),
                                      assistant_text(self.reply(["Close q_max #969?"]))), "Lane pick guard")

    def test_ln_landed_turn_follows_the_lane_rule(self):
        commit = self.call("Bash", {"command": "git commit -m x"})
        self.assert_blocked(self.lane(peer_msg("pick?"), *commit, assistant_text(self.reply(self.PICK))),
                            "Lane pick guard")
        self.assertIsNone(self.lane(peer_msg("pick?"), *commit, *self.send(session_id="@parent"),
                                    assistant_text(self.reply(self.PICK))))

    def test_ln_red_lane_marked_by_tag_or_by_parent_blocks(self):
        # Catches: a lane recognised by one of its two marks only.
        for label, record in (("tag only", self.lane_record(tags=("cs-build:lane",), parent=None)),
                              ("parent only", self.lane_record(tags=(), parent=self.PARENT))):
            with self.subTest(mark=label):
                out = self.stop([*record, peer_msg("pick?"), assistant_text(self.reply(self.PROMISE))],
                                env_id=self.LANE_ENV)
                self.assert_blocked(out, "Lane pick guard")

    def test_ln_red_lane_with_no_page_still_blocks(self):
        # Catches: a lane failed open because its repo has no waiting page.
        bare = self.make_repo("bare", page=False)
        self.assert_blocked(self.lane(peer_msg("pick?"), assistant_text(self.reply(self.PICK)), repo=bare),
                            "Lane pick guard")

    def test_ln_red_question_mark_sentence_blocks(self):
        # Catches: a lane's "?" sentence with no send read as no question (spec v2.1).
        self.assert_blocked(self.lane(peer_msg("pick?"), assistant_text(self.reply(self.QUESTION))),
                            "Lane pick guard")

    def test_ln_green_stop_hook_active_never_blocks(self):
        # Catches: a lane's rewrite blocked again for a question the first Stop already judged.
        out = self.stop([*self.lane_record(), peer_msg("pick?"), assistant_text(self.reply(self.PICK))],
                        env_id=self.LANE_ENV, stop_active=True)
        self.assertIsNone(out)


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


class DoubleBacktickMaskTests(unittest.TestCase):
    """A two-backtick code span is one span (MASK_PATTERNS in lint/ste_lint.py).

    The tests guard that a double-backtick span is masked as code, so its text is not linted and a
    backtick inside it does not hide the prose after it. They also guard that an unclosed
    double-backtick run is literal text: it opens no span, so the prose before a later code span
    is still linted, and that code span is still masked.
    """

    LONG_TAIL = ("The reviewer reads every changed line of the test file before the branch is pushed, "
                 "then checks each new case against the old commit and records the failing run in the trailer")

    def codes(self, text):
        linter = ste_lint.Linter(dict(ste_lint.DEFAULT_CONFIG))
        return [f.code for f in linter.check_text("t.md", text)]

    def test_backtick_inside_double_backtick_span_does_not_hide_the_next_sentence(self):
        single = "Write the span as `a b` in the note. " + self.LONG_TAIL + " with `code` at the end.\n"
        self.assertIn("STE001", self.codes(single), "fixture sentence is not over budget")
        double = "Write the span as ``a ` b`` in the note. " + self.LONG_TAIL + " with `code` at the end.\n"
        self.assertIn("STE001", self.codes(double),
                      "a backtick inside a double-backtick span hides the sentence after it")

    def test_double_backtick_span_content_is_not_linted(self):
        words = " ".join(["word"] * 31)
        self.assertIn("STE001", self.codes("Run " + words + " now.\n"), "fixture sentence is not over budget")
        self.assertNotIn("STE001", self.codes("Run ``" + words + "`` now.\n"),
                         "text inside a double-backtick span is linted as prose")

    def test_double_backtick_span_without_inner_backtick_adds_no_finding(self):
        self.assertNotIn("STE001", self.codes("Set the flag ``a b`` and then stop the pump now.\n"),
                         "a double-backtick span with no backtick inside adds a finding")

    def test_unclosed_double_backtick_run_does_not_hide_prose_before_a_code_span(self):
        # The `` run has no closing run of two, so it is literal text and opens no span.
        words = " ".join(["word"] * 31)
        self.assertIn("STE001", self.codes("Run status and " + words + ", then `file`.\n"),
                      "fixture sentence is not over budget")
        self.assertIn("STE001", self.codes("Run ``status and " + words + ", then `file`.\n"),
                      "an unclosed double-backtick run hides the words before a later code span")

    def test_unclosed_double_backtick_run_does_not_lint_a_later_code_span_as_prose(self):
        # The run is literal, so the single-backtick span after it is valid and its words stay masked.
        words = " ".join(["word"] * 31)
        self.assertIn("STE001", self.codes("Run status then " + words + " now.\n"),
                      "fixture sentence is not over budget")
        self.assertNotIn("STE001", self.codes("Run ``status then `" + words + "` now.\n"),
                         "an unclosed double-backtick run makes a later code span read as prose")

    def test_lone_backtick_before_a_double_span_does_not_hide_the_words_before_it(self):
        # The lone backtick is an unclosed run, so it is literal and opens no span. The `` span after
        # it is masked, and the 31 words before it stay prose.
        words = " ".join(["word"] * 31)
        self.assertIn("STE001", self.codes("Use " + words + " ``x`` now.\n"), "fixture sentence is not over budget")
        self.assertIn("STE001", self.codes("Use ` then " + words + " ``x`` now.\n"),
                      "a lone backtick before a double-backtick span hides the words before it")

    def test_two_backtick_run_inside_a_three_backtick_run_does_not_close_the_span(self):
        # The ``` run is not a closing run of two, so the span runs on to the `` after the words and
        # the words stay inside it.
        words = " ".join(["word"] * 31)
        self.assertIn("STE001", self.codes("Use " + words + " now.\n"), "fixture sentence is not over budget")
        self.assertNotIn("STE001", self.codes("Use ``x ``` " + words + " `` now.\n"),
                         "a two-backtick run inside a three-backtick run closes the span early")

    def test_single_backtick_span_content_is_not_linted(self):
        words = " ".join(["word"] * 31)
        self.assertIn("STE001", self.codes("Run " + words + " now.\n"), "fixture sentence is not over budget")
        self.assertNotIn("STE001", self.codes("Run `" + words + "` now.\n"),
                         "text inside a single-backtick span is linted as prose")

    def test_single_backtick_span_budget_is_thirty_words(self):
        base = ("Set the flag `a b` and then the reviewer checks every changed line in the test file "
                "before the branch is pushed to the shared remote today for the crew now")
        self.assertIn("STE001", self.codes(base + " again.\n"), "fixture: a 31-word sentence is not over budget")
        self.assertNotIn("STE001", self.codes(base + ".\n"), "a 30-word sentence with one span is over budget")


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


# rewrite-cite-predates-ruling (the rewrite-stamp check in report_guard.py, Stop, landed turns): a reply
# that says decision D was rewritten for a ruling blocks when D's record was last committed before that
# ruling, on any branch or on HEAD. Each case builds its own git repo. Every commit takes its
# date from GIT_COMMITTER_DATE, so the check reads real history. Each case states the result the check
# must give; a case that fails names a gap in the check, not in the fixture.
RULING = "2026-11-01 18:44 CST"
RULING_SENTENCE = "RECORDED: rewrote decision `ci-job-caps` in place, for the owner ruling of %s (PR #1001)" % RULING
D_LAST_COMMIT = "2026-10-28T22:30:00-05:00"  # late in the Central evening, so the UTC day is the next one
NOW = "2026-11-01T14:00:00-06:00"  # LOCAL_TIME_NOW: the hook's clock, on the ruling's own date


def done_reply(done):
    return "> **Done** %s\n> **Next** none" % done


def write_file(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


class DecisionRepo:
    """A git repo whose default branch is `main`. Records sit where the layout puts the decisions kind:
    docs/decisions in a rolled-out repo (its extras file says so), else the legacy decisions/ folder."""

    def __init__(self, folder, rolled_out=True):
        self.path = folder
        self.records = "docs/decisions" if rolled_out else "decisions"
        self._git("init", "-q", "-b", "main")
        self._git("config", "user.email", "t@example.com")
        self._git("config", "user.name", "t")
        if rolled_out:
            write_file(os.path.join(folder, ".claude", "layout-extras.json"),
                       json.dumps({"kinds": {}, "rolled-out": True}))
        self.touch("2026-10-01T10:00:00Z")

    def _git(self, *args, when=None):
        env = dict(os.environ)
        if when:
            env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = when
        subprocess.run(["git", "-C", self.path, *args], check=True, capture_output=True, text=True, env=env)

    def commit(self, when, *records):
        """One commit, dated `when`, that writes one file for each record id in `records`."""
        for rec in records:
            write_file(os.path.join(self.path, self.records, rec + ".md"),
                       "# %s\n\nRevision of %s.\n" % (rec, when))
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "fixture " + when, when=when)

    def touch(self, when):
        """One commit, dated `when`, that moves the tip and touches no record."""
        write_file(os.path.join(self.path, "README.md"), "Revision of %s.\n" % when)
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "fixture " + when, when=when)

    def branch(self, name):
        self._git("branch", name)

    def switch(self, name):
        self._git("switch", "-q", name)

    def remote_commit(self, name, when, *records):
        """One commit, dated `when`, that only the remote-tracking ref origin/<name> holds. HEAD and the
        local branches never reach it."""
        temp = "tmp-" + name
        self._git("switch", "-q", "-c", temp)
        self.commit(when, *records)
        self._git("update-ref", "refs/remotes/origin/" + name, "HEAD")
        self._git("switch", "-q", "main")
        self._git("branch", "-D", temp)


GIT_TRACE_LINE = "trace: built-in: git "


def git_process_count(trace_path):
    """How many git processes wrote to a GIT_TRACE file. Git writes one `built-in: git` line per process."""
    try:
        with open(trace_path, encoding="utf-8", errors="replace") as f:
            return sum(1 for line in f if GIT_TRACE_LINE in line)
    except FileNotFoundError:
        return 0


class RewriteStampTests(unittest.TestCase):
    """rewrite-cite-predates-ruling, in report_guard.py's Stop hook. The case numbers are the brief's."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(dir=_ISOLATION["dir"])
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def repo(self, rolled_out=True):
        return DecisionRepo(tempfile.mkdtemp(dir=self.tmp), rolled_out)

    def red_repo(self):
        """D's last commit is late in the Central evening, before the ruling. A commit after the ruling
        moves the tip, so the tip is never D's last commit."""
        repo = self.repo()
        repo.commit(D_LAST_COMMIT, "ci-job-caps")
        repo.touch("2026-11-02T09:00:00Z")
        return repo

    def run_stop(self, repo, reply, landed=True, human_at=None, env_extra=None):
        first = human("do the task")
        if human_at:
            first["timestamp"] = human_at
        records = [first]
        if landed:
            records += [tool_use_msg("Bash", {"command": "git commit -m x"}), tool_result_msg()]
        records.append(assistant_text(reply))
        path = write_transcript(records, tempfile.mkdtemp(dir=self.tmp))
        hook = {"hook_event_name": "Stop", "transcript_path": path, "stop_hook_active": False,
                "cwd": repo.path}
        env = dict(os.environ, LOCAL_TIME_NOW=NOW)
        env.update(env_extra or {})
        return run_guard(REPORT_GUARD, hook, env=env)

    def assertBlocks(self, run, *parts):
        """The guard blocks, and the block's reason names each of `parts`. Stdout is checked before
        it is parsed, so a missing block fails here and never as a JSON error."""
        self.assertTrue(run.stdout.strip(), "no rewrite-stamp block. stderr: " + run.stderr[-300:])
        out = json.loads(run.stdout)
        self.assertEqual(out.get("decision"), "block", out)
        for part in parts:
            self.assertIn(part, out.get("reason", ""))

    def assertPasses(self, run):
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout.strip(), "")

    def test_f119_replay_reconstructed_blocks(self):
        """Case 1. The reply uses the wording the PR body holds. The incident's own chat text is lost, so
        this is a reconstruction. The variants change only the rewrite wording and the text around the stamp."""
        repo = self.red_repo()
        variants = {
            "reconstructed": RULING_SENTENCE,
            "rewritten": "RECORDED: decision `ci-job-caps` rewritten for the owner ruling of 2026-11-01 18:44 CST (PR #1001)",
            "rewrites": "RECORDED: rewrites decision `ci-job-caps` for the owner ruling of 2026-11-01 18:44 CST (PR #1001)",
            "rewrite of": "RECORDED: a rewrite of decision `ci-job-caps`, for the owner ruling of 2026-11-01 18:44 CST (PR #1001)",
            # Catches: a lone quote, a `//` and a `#` in one sentence hide the rewrite or the id.
            "lone quote and URL": "RECORDED: rewrote decision `ci-job-caps` in place, for the owner's ruling of 2026-11-01 18:44 CST (PR #1001, https://github.com/shivinate7/claude-settings/pull/1001#issuecomment-2)",
        }
        for name, done in variants.items():
            with self.subTest(variant=name):
                run = self.run_stop(repo, done_reply(done))
                self.assertBlocks(run, "ci-job-caps", "2026-10-28", "18:44")
                self.assertNotIn("2026-10-29", run.stdout)  # the date is Central, not UTC

    def test_ruling_stamp_zone_is_read_as_central(self):
        """Case 1, zone. D's last commit is 14:00 CST on the ruling's own date, so it predates the 18:44 CST
        ruling. Read as UTC, the ruling falls before D and the check stays quiet."""
        repo = self.repo()
        repo.commit("2026-11-01T14:00:00-06:00", "ci-job-caps")
        repo.touch("2026-11-02T09:00:00Z")
        self.assertBlocks(self.run_stop(repo, done_reply(RULING_SENTENCE)), "ci-job-caps", "2026-11-01", "18:44")

    def test_decisions_folder_comes_from_layout(self):
        """Case 1, folder. The record sits where layout.path() puts the decisions kind: docs/decisions in a
        rolled-out repo, the legacy decisions/ folder in one that has not rolled out."""
        for rolled_out in (True, False):
            with self.subTest(rolled_out=rolled_out):
                repo = self.repo(rolled_out)
                repo.commit(D_LAST_COMMIT, "ci-job-caps")
                repo.touch("2026-11-02T09:00:00Z")
                self.assertBlocks(self.run_stop(repo, done_reply(RULING_SENTENCE)),
                                  "ci-job-caps", "2026-10-28", "18:44")

    def test_under_or_by_R_without_a_stamp_passes(self):
        """Case 3, flipped to green. With no stamp there is no ruling time. R's later commit is no fallback:
        a typo fix on R would make the check cry wolf. R is committed after D, as before."""
        repo = self.repo()
        repo.commit(D_LAST_COMMIT, "ci-job-caps")
        repo.commit("2026-10-30T16:00:00Z", "test-strategy-reset")
        repo.touch("2026-11-02T09:00:00Z")
        variants = {
            "under R": "RECORDED: decision `ci-job-caps` rewritten under test-strategy-reset (PR #1002)",
            "under decision R": "RECORDED: decision `ci-job-caps` rewritten under decision `test-strategy-reset` (PR #1002)",
            "by R": "RECORDED: decision `ci-job-caps` rewritten by test-strategy-reset (PR #1002)",
        }
        for name, done in variants.items():
            with self.subTest(variant=name):
                self.assertPasses(self.run_stop(repo, done_reply(done)))

    def test_r_and_d_in_one_commit_passes(self):
        """Case 3, green. D's last commit is R's own commit, so D does not predate the ruling."""
        repo = self.repo()
        repo.commit("2026-10-30T16:00:00Z", "ci-job-caps", "test-strategy-reset")
        repo.touch("2026-11-02T09:00:00Z")
        self.assertPasses(self.run_stop(repo, done_reply(
            "RECORDED: decision `ci-job-caps` rewritten under test-strategy-reset (PR #1002)")))

    def test_bare_clock_stamp_reads_on_the_turn_date(self):
        """The `HH:MM <zone>` form, read on the turn's local date. The turn's human record and LOCAL_TIME_NOW
        name the same Central day. A clock time later than the turn time reads as the day before. The record
        predates both readings, so the block holds either way."""
        repo = self.red_repo()
        reply = done_reply("RECORDED: rewrote decision `ci-job-caps` in place, for the owner ruling at 18:44 CST (PR #1001)")
        self.assertBlocks(self.run_stop(repo, reply, human_at="2026-11-01T20:00:00Z"),
                          "ci-job-caps", "2026-10-28", "18:44")

    def test_lane_commit_after_ruling_passes(self):
        """Case 2, green. HEAD is a lane whose own commit to D is after the ruling. Main's last commit
        to D predates the ruling, and the lane's commit is the reason the check stays quiet."""
        repo = self.red_repo()
        repo.branch("lane")
        repo.switch("lane")
        repo.commit("2026-11-02T12:00:00Z", "ci-job-caps")
        self.assertPasses(self.run_stop(repo, done_reply(RULING_SENTENCE)))

    def test_record_committed_after_ruling_on_main_passes_when_head_predates_it(self):
        """Case 4, green. The record's last commit on main is after the ruling. HEAD is a lane forked before
        that commit. A block needs the record's last commit, on any branch or on HEAD, to predate the ruling,
        so the check stays quiet on either HEAD."""
        repo = self.repo()
        repo.commit(D_LAST_COMMIT, "ci-job-caps")
        repo.branch("lane")
        repo.commit("2026-11-01T18:50:00-06:00", "ci-job-caps")
        repo.touch("2026-11-02T09:00:00Z")
        for head in ("main", "lane"):
            with self.subTest(head=head):
                repo.switch(head)
                self.assertPasses(self.run_stop(repo, done_reply(RULING_SENTENCE)))

    def test_sentence_without_a_rewrite_word_passes(self):
        """Case 4, green. The same record and ruling, with no rewrite word in the sentence."""
        repo = self.red_repo()
        self.assertPasses(self.run_stop(repo, done_reply(
            "RECORDED: decision `ci-job-caps` recorded for the owner ruling of 2026-11-01 18:44 CST (PR #1001)")))

    def test_unknown_ids_and_no_time_pass(self):
        """Case 4, green. An unknown D, an unknown R, and a rewrite that gives no time at all."""
        repo = self.red_repo()
        replies = {
            "unknown D": "RECORDED: rewrote decision `no-such-decision` in place, for the owner ruling of 2026-11-01 18:44 CST (PR #1001)",
            "unknown R": "RECORDED: decision `ci-job-caps` rewritten under no-such-decision (PR #1002)",
            "no time found": "RECORDED: rewrote decision `ci-job-caps` (PR #1001)",
        }
        for name, done in replies.items():
            with self.subTest(variant=name):
                self.assertPasses(self.run_stop(repo, done_reply(done)))

    def test_git_missing_passes(self):
        """Case 4, green. The red fixture, with no git on PATH. test_f119 runs the same fixture with git
        and blocks."""
        empty = tempfile.mkdtemp(dir=self.tmp)
        self.assertPasses(self.run_stop(self.red_repo(), done_reply(RULING_SENTENCE), env_extra={"PATH": empty}))

    def test_git_failing_passes(self):
        """Case 4, green. Git runs and fails: GIT_DIR names no repository."""
        no_repo = os.path.join(self.tmp, "no-such-git-dir")
        self.assertPasses(self.run_stop(self.red_repo(), done_reply(RULING_SENTENCE), env_extra={"GIT_DIR": no_repo}))

    def test_unlanded_turn_passes(self):
        """Case 5, green. The red fixture and the same reply, on a turn with no git write."""
        self.assertPasses(self.run_stop(self.red_repo(), done_reply(RULING_SENTENCE), landed=False))

    def test_bare_id_without_a_decision_word_blocks(self):
        """Red. The id is named bare, with no word "decision", and its record file exists."""
        run = self.run_stop(self.red_repo(), done_reply(
            "RECORDED: ci-job-caps was rewritten for the owner ruling of 2026-11-01 18:44 CST (PR #1001)"))
        self.assertBlocks(run, "ci-job-caps", "2026-10-28", "18:44")

    def test_only_the_stale_id_of_two_blocks(self):
        """Red. Two ids share one ruling. test-strategy-reset is committed after the ruling, so only
        ci-job-caps is stale, and the block may name only it."""
        repo = self.red_repo()
        repo.commit("2026-11-02T10:00:00-06:00", "test-strategy-reset")
        run = self.run_stop(repo, done_reply(
            "RECORDED: Decisions test-strategy-reset and ci-job-caps were rewritten for the owner ruling "
            "of 2026-11-01 18:44 CST (PR #1001)"))
        self.assertBlocks(run, "ci-job-caps", "2026-10-28", "18:44")
        self.assertNotIn("test-strategy-reset", run.stdout)

    def test_not_rewritten_yet_or_will_be_passes(self):
        """Green. The id is stale, but the sentence says it is not rewritten yet, was not rewritten, or
        will be rewritten. None of these says a rewrite has happened."""
        repo = self.red_repo()
        replies = {
            "is not rewritten yet": "OTHER: Decision ci-job-caps is not rewritten yet for the owner ruling of 2026-11-01 18:44 CST.",
            "was not rewritten": "OTHER: Decision ci-job-caps was not rewritten for the owner ruling of 2026-11-01 18:44 CST.",
            "will be rewritten": "OTHER: Decision ci-job-caps will be rewritten for the owner ruling of 2026-11-01 18:44 CST.",
        }
        for name, done in replies.items():
            with self.subTest(variant=name):
                self.assertPasses(self.run_stop(repo, done_reply(done)))

    def test_stamp_tied_to_the_ruling_wins_over_a_later_merge_stamp(self):
        """Green. The sentence holds two stamps. The one tied to "ruling" is the ruling time. The merge
        stamp is later than the record's commit, so reading it as the ruling time would block."""
        repo = self.repo()
        repo.commit("2026-11-02T08:50:00-06:00", "ci-job-caps")
        repo.touch("2026-11-02T12:00:00-06:00")
        self.assertPasses(self.run_stop(repo, done_reply(
            "RECORDED: decision ci-job-caps was rewritten in PR 1001 (merged 2026-11-02 09:00 CST) "
            "for the owner ruling of 2026-11-01 18:44 CST")))

    def test_reply_with_no_recorded_id_runs_no_git(self):
        """Cost. A rewrite word with no id that has a record runs no git process."""
        repo = self.red_repo()
        replies = {
            "no id": "RECORDED: rewrote a record in place for the owner ruling of 2026-11-01 18:44 CST (PR #1001)",
            "unknown id": "RECORDED: rewrote decision `no-such-decision` for the owner ruling of 2026-11-01 18:44 CST (PR #1001)",
        }
        for name, done in replies.items():
            with self.subTest(variant=name):
                trace = os.path.join(tempfile.mkdtemp(dir=self.tmp), "trace.txt")
                self.run_stop(repo, done_reply(done), env_extra={"GIT_TRACE": trace})
                self.assertEqual(git_process_count(trace), 0)

    def test_matching_reply_runs_at_most_one_git_process_per_cited_id(self):
        """Cost. A reply that cites ids with records runs at most one git process per cited id."""
        repo = self.red_repo()
        repo.commit("2026-11-02T10:00:00-06:00", "test-strategy-reset")
        replies = (
            ("one id", 1, "RECORDED: decision ci-job-caps was rewritten for the owner ruling of 2026-11-01 18:44 CST (PR #1001)"),
            ("two ids", 2, "RECORDED: Decisions test-strategy-reset and ci-job-caps were rewritten for the owner ruling "
                           "of 2026-11-01 18:44 CST (PR #1001)"),
        )
        for name, cited, done in replies:
            with self.subTest(variant=name):
                trace = os.path.join(tempfile.mkdtemp(dir=self.tmp), "trace.txt")
                self.run_stop(repo, done_reply(done), env_extra={"GIT_TRACE": trace})
                self.assertLessEqual(git_process_count(trace), cited)

    def test_trace_counter_sees_each_git_process(self):
        """The counter behind the cost cases. A zero count means the guard ran no git, not that the counter is
        blind: one plain git process must count as one."""
        repo = self.red_repo()
        trace = os.path.join(tempfile.mkdtemp(dir=self.tmp), "trace.txt")
        subprocess.run(["git", "-C", repo.path, "rev-parse", "HEAD"], check=True, capture_output=True,
                       env=dict(os.environ, GIT_TRACE=trace))
        self.assertEqual(git_process_count(trace), 1)

    def test_adjacent_stamp_wins_over_a_later_merge_stamp(self):
        """Green. The stamp next to "ruling" is the ruling time. A later stamp in the same sentence is not,
        and read as the ruling time it would make a fresh record look stale."""
        repo = self.repo()
        repo.commit("2026-11-01T19:00:00-06:00", "ci-job-caps")
        repo.touch("2026-11-02T12:00:00-06:00")
        self.assertPasses(self.run_stop(repo, done_reply(
            "OTHER: Rewrote `ci-job-caps` for the 2026-11-01 18:44 CST ruling, PR #1001 (merged 2026-11-02 08:00 CST).")))

    def test_queued_negated_or_future_rewrite_sentences_pass(self):
        """Green. A queued rewrite, a rewrite not needed, one that should or must happen, one that is needed,
        and one that is pending each say no rewrite has happened. None is blocked."""
        repo = self.red_repo()
        sentences = {
            "queued": "rewrite of `ci-job-caps` for the ruling at 2026-11-01 18:44 CST (lane queued).",
            "not needed": "no rewrite of `ci-job-caps` is needed for the ruling at 2026-11-01 18:44 CST.",
            "should be rewritten": "`ci-job-caps` should be rewritten for the ruling at 2026-11-01 18:44 CST.",
            "must be rewritten": "`ci-job-caps` must be rewritten for the ruling at 2026-11-01 18:44 CST.",
            "needs a rewrite": "needs a rewrite of `ci-job-caps` for the ruling at 2026-11-01 18:44 CST.",
            "pending": "the rewrite of `ci-job-caps` for the ruling at 2026-11-01 18:44 CST is pending.",
        }
        for name, sentence in sentences.items():
            with self.subTest(variant=name):
                self.assertPasses(self.run_stop(repo, "> **Done** OTHER: read the rulings.\n> **Next:** " + sentence))

    def test_only_the_id_next_to_the_rewrite_word_is_checked(self):
        """Green. other-rec is stale, but it follows "per" and is not the id next to the rewrite word, so the
        check reads ci-job-caps alone. ci-job-caps is fresh, so the reply passes."""
        repo = self.repo()
        repo.commit(D_LAST_COMMIT, "other-rec")
        repo.commit("2026-11-01T19:00:00-06:00", "ci-job-caps")
        repo.touch("2026-11-02T12:00:00-06:00")
        self.assertPasses(self.run_stop(repo, done_reply(
            "RECORDED: Rewrote `ci-job-caps` per `other-rec` for the ruling at 2026-11-01 18:44 CST (PR #1001)")))

    def test_clock_time_later_than_the_turn_means_the_day_before(self):
        """Green. The turn is 00:20 CST on the day after the ruling. A clock time later than the turn's clock
        names the day before, so "23:50 CST" is the earlier evening, and the record was rewritten after it."""
        repo = self.repo()
        repo.commit("2026-11-01T23:55:00-06:00", "ci-job-caps")
        repo.touch("2026-11-02T12:00:00-06:00")
        self.assertPasses(self.run_stop(
            repo, done_reply("RECORDED: rewrote decision `ci-job-caps` for the 23:50 CST ruling (PR #1001)"),
            human_at="2026-11-02T06:20:00Z", env_extra={"LOCAL_TIME_NOW": "2026-11-02T00:20:00-06:00"}))

    def test_rewrite_on_a_remote_branch_only_counts(self):
        """Green. The rewrite is on origin/lane-x only, after the ruling. main and HEAD hold only the stale
        commit. A rewrite pushed anywhere counts, so the record is not stale."""
        repo = self.repo()
        repo.commit(D_LAST_COMMIT, "ci-job-caps")
        repo.touch("2026-11-02T09:00:00Z")
        repo.remote_commit("lane-x", "2026-11-01T19:00:00-06:00", "ci-job-caps")
        replies = {
            "bare id": "OTHER: lane rewrote `ci-job-caps` for the 2026-11-01 18:44 CST ruling (PR draft).",
            "decision word": "OTHER: lane rewrote decision `ci-job-caps` for the 2026-11-01 18:44 CST ruling (PR draft).",
        }
        for name, done in replies.items():
            with self.subTest(variant=name):
                self.assertPasses(self.run_stop(repo, done_reply(done)))

    def test_f119_replay_still_blocks_when_no_branch_holds_a_later_commit(self):
        """Block expectation. Every local and remote branch holds only commits that predate the ruling, so the
        F119 replay still blocks. This passes on the current head as well."""
        repo = self.red_repo()
        repo.branch("lane")
        repo.remote_commit("lane-y", "2026-10-27T10:00:00-05:00", "other-rec")
        self.assertBlocks(self.run_stop(repo, done_reply(RULING_SENTENCE)), "ci-job-caps", "2026-10-28", "18:44")

    def test_same_id_in_three_sentences_runs_one_git_process(self):
        """Cost. The same id cited in three sentences of one reply runs one git process."""
        repo = self.red_repo()
        trace = os.path.join(tempfile.mkdtemp(dir=self.tmp), "trace.txt")
        self.run_stop(repo, done_reply(
            "RECORDED: Rewrote `ci-job-caps` for the 2026-11-01 18:44 CST ruling. "
            "Rewrote `ci-job-caps` for the 2026-11-01 18:44 CST ruling again. "
            "The rewrite of `ci-job-caps` for the 2026-11-01 18:44 CST ruling is on main (PR #1001)."),
            env_extra={"GIT_TRACE": trace})
        self.assertEqual(git_process_count(trace), 1)

    def test_ids_with_no_or_queued_before_a_hyphen_do_not_skip_the_sentence(self):
        """Green. "no" and "queued" are skip words in the check. Inside a hyphenated id they are part of the id,
        so the sentence is still checked, and a stale record still blocks."""
        repo = self.repo()
        repo.commit(D_LAST_COMMIT, "no-x", "queued-x")
        repo.touch("2026-11-02T12:00:00-06:00")
        replies = (
            ("no-x", "RECORDED: Rewrote `no-x` for the 2026-11-01 18:44 CST ruling (PR #1001)."),
            ("queued-x", "RECORDED: `queued-x` was rewritten for the ruling at 2026-11-01 18:44 CST (PR #1001)."),
        )
        for name, done in replies:
            with self.subTest(variant=name):
                self.assertBlocks(self.run_stop(repo, done_reply(done)), name, "2026-10-28", "18:44")


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


class PastRulingRelay(SameTurnWriter, unittest.TestCase):
    PAGE = tcj.PAGE_URL  # the waiting page tcj.make_repo names, which the writer read cites

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.record = os.path.join(_ISOLATION["stub"], "calls.jsonl")
        self.reset_calls()
        self.decided = tcj.make_repo("relay-decided", decisions={tcj.APPS_SLUG: tcj.APPS_RULING})
        self.bare = tcj.make_repo("relay-bare")
        self.ci = tcj.CI_REPO  # a roadmap ref, so the one git process is the roadmap read

    def reset_calls(self):
        for name in ("calls.jsonl", "git.log"):
            path = os.path.join(_ISOLATION["stub"], name)
            if os.path.exists(path):
                os.remove(path)

    def git_starts(self):
        # The git processes the guard spawned, counted by the stub's Popen (hooks/test_call_judge.py).
        path = os.path.join(_ISOLATION["stub"], "git.log")
        if not os.path.exists(path):
            return 0
        with open(path, encoding="utf-8") as f:
            return len(f.read().split())

    def model_calls(self):
        if not os.path.exists(self.record):
            return []
        with open(self.record, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def stop(self, repo, reply=None, answer=None, model_fail=False, records=None, to_writer=False):
        if records is None:
            # A question reaches the page writer in its own turn, so `to_writer` adds that send before the reply.
            sent = [*self.writer_read(self.WRITER), *self.send(session_id=self.WRITER)] if to_writer else []
            records = [human("decide"), *sent, assistant_text(reply)]
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
        # The send to the writer keeps the question check quiet, so this case tests only the relay's unknown notice.
        out, err = self.stop(self.bare, RELAY, answer=tcj.ALLOW, to_writer=True)
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
        # Each turn sends to the writer, so the question check stays quiet and only the relay's model error is tested.
        out, _ = self.stop(self.decided, RELAY, model_fail=True, to_writer=True)
        self.assertIn("Unvetted guard", self.reason(out), out)
        self.assertEqual(len(self.model_calls()), 1)
        self.reset_calls()
        out, _ = self.stop(self.decided, RELAY + "\n> " + UNVETTED, model_fail=True, to_writer=True)
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
        self.assertIn("Unvetted guard", self.reason(out), out)

    def test_a_relayed_question_costs_two_git_processes_and_one_model_call(self):
        # The roadmap read plus one origin/main blob read: the intended added cost (step guards-read-origin-main-config).
        self.stop(self.ci, RELAY, answer=tcj.ALLOW)
        self.assertEqual(len(self.model_calls()), 1)
        self.assertEqual(self.git_starts(), 2)

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
        self.assertIn("Unvetted guard", self.reason(out), out)
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
        # A prose question with no Input Needed item. The Unvetted line beside the question passes it, whether it sits
        # on its own line, in a blockquote, or on the question line.
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
    whole word "answered" must cite a source, outside code spans and fences. Incident F188 (decision
    answered-needs-source)."""

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
        # Synthetic replay, not a copy. The real F188 line (docs/plans/owner-feedback-audit.md, decision
        # answered-needs-source) never used the word. This line stands in for a reply that did.
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

    def test_an_red_refusal_names_the_inline_code_span_route(self):
        # Ruling (coordinator, 15:57 CST): the refusal text names the inline code span route. The verdict does not
        # change. Control first: the same line with the word in backticks is no claim, so it returns ''.
        # Catches: the reason names only "say what is meant in other words", so a session never learns the route.
        import report_guard  # noqa: E402  answered_problem, the refusal text (lint/report_guard.py)

        self.assertEqual(report_guard.answered_problem("The `answered` check blocks this line."), "",
                         "the inline code span control is refused: the existing exemption broke")
        refusal = report_guard.answered_problem("The answered check blocks this line.")
        self.assertTrue(refusal, "the verdict changed: a bare answered line is no longer refused")
        self.assertIn("inline code span", refusal,
                      "the refusal text does not name the inline code span route: %r" % refusal)

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

    # Cost: regex only, plus one read of hooks/guard.py. report_guard reads its stamp id there once per run, at
    # load (hooks_dirs), so no other file opens. The probe is builtins.open, the pattern
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

    def test_an_cost_no_word_opens_only_transcript_and_guard_py(self):
        # Catches: the check reads a file, such as a glossary or a record, even when the reply has no "answered".
        for reply in ("Lane 4 is still running.", "The owner answers in chat.", "The lane is answering now."):
            with self.subTest(reply=reply):
                out, opened, transcript = self.guard_opens(reply)
                self.assertEqual(out, "")
                self.assertEqual(set(opened), {transcript, GUARD_PY})

    def test_an_cost_offending_line_still_opens_only_transcript_and_guard_py(self):
        # The block is the red part. The read is the cost: the verdict reads the reply, and nothing else opens.
        out, opened, transcript = self.guard_opens("Answered: no permission rule can lift it.")
        self.assertEqual((json.loads(out) if out else {}).get("decision"), "block", out)
        self.assertEqual(set(opened), {transcript, GUARD_PY})


class PendingRefusalTests(unittest.TestCase):
    """refusal-note, the Stop half: a refused tool stays pending until the reply names it under
    Input Needed or says the refusal was right. A reply that raises a refusal also records it as raised,
    so the same tool refused again for the same reason passes silently. The refusals file is written here
    by hand, so these cases do not depend on hooks/refusal_note.py. Each case works in its own folder under
    this run's folder (test-temp-standard)."""

    SID = "pd-sid-1"
    ARCHIVE = "mcp__claude-code-remote__archive_session"
    ADD_REPO = "mcp__claude-code-remote__add_repo"
    BASH = "Bash"
    REASON = "auto mode refused the call: it archives a session the owner did not name"
    OTHER_REASON = "auto mode refused the call: it adds a repo outside the allowed list"
    PAGE = "https://claude.ai/artifact/waitpage3"
    PROSE = "Nothing landed. The state is unchanged."
    LANDED_OTHER_ASK = ("> **Done** BUILT abc123\n> **Deviations** none\n"
                        "> **Input Needed** allow `mcp__github__update_pull_request`?\n> **Next** wait")
    LANDED_CLEAN = ("> **Done** BUILT abc123\n> **Deviations** none\n"
                    "> **Input Needed** none\n> **Next** ship it")

    def setUp(self):
        self.scratch = tempfile.mkdtemp(dir=_ISOLATION["dir"])
        self.addCleanup(shutil.rmtree, self.scratch, True)
        self.cfg = os.path.join(self.scratch, "cfg")
        os.makedirs(self.cfg)
        # A repo with a waiting page: an owner question in it is judged, not handed the no-page note.
        self.repo = os.path.join(self.scratch, "repo")
        os.makedirs(os.path.join(self.repo, ".git"))
        os.makedirs(os.path.join(self.repo, ".claude"))
        with open(os.path.join(self.repo, ".claude", "layout-extras.json"), "w") as handle:
            json.dump({"kinds": {}, "waiting-page": self.PAGE}, handle)

    def refusals_file(self, sid=SID):
        return os.path.join(self.cfg, "state", "refusals", sid + ".jsonl")

    def write_rows(self, rows, sid=SID, agent_id=None):
        """The refusals file with one row per (tool_name, reason) pair, in the shape hooks/refusal_note.py writes.
        With `agent_id`, each row is an agent's refused call, as the hook writes it."""
        os.makedirs(os.path.dirname(self.refusals_file(sid)), exist_ok=True)
        with open(self.refusals_file(sid), "w", encoding="utf-8") as handle:
            for tool, reason in rows:
                row = {"ts": "2026-11-01T10:00:00-05:00", "tool_name": tool, "reason": reason}
                if agent_id:
                    row["agent_id"] = agent_id
                handle.write(json.dumps(row) + "\n")

    def write_refusals(self, tools, sid=SID):
        self.write_rows([(tool, "refused") for tool in tools], sid)

    def pending_tools(self, sid=SID):
        """The tool_name of each line still in the refusals file, [] when the file is gone."""
        try:
            with open(self.refusals_file(sid), encoding="utf-8") as handle:
                return [json.loads(line)["tool_name"] for line in handle if line.strip()]
        except FileNotFoundError:
            return []

    def stop(self, reply, landed=False, active=False, sid=SID, cwd=None):
        records = [human("do the task")]
        if landed:
            records += [tool_use_msg("Bash", {"command": "git commit -m x"}), tool_result_msg()]
        records += [tool_use_msg(self.ARCHIVE), tool_result_msg(), assistant_text(reply)]
        path = write_transcript(records, self.scratch)
        hook = {"hook_event_name": "Stop", "transcript_path": path, "stop_hook_active": active,
                "session_id": sid, "cwd": cwd or self.scratch}
        run = run_guard(REPORT_GUARD, hook, env=dict(os.environ, CLAUDE_CONFIG_DIR=self.cfg))
        self.assertEqual(run.returncode, 0, run.stderr)
        return run

    @staticmethod
    def blocked(run):
        """The block decision the guard printed, or None when the Stop passed."""
        return json.loads(run.stdout) if run.stdout.strip() else None

    def use_fresh_config(self):
        """A config folder of its own, so one subtest's raised refusals never settle the next subtest's."""
        self.cfg = tempfile.mkdtemp(dir=self.scratch)

    @staticmethod
    def raising_reply(rows):
        """A reply that raises each (tool, reason) row: its tool's name, then "refusal was right"."""
        return "\n".join("`%s` refusal was right." % tool for tool, _ in rows) + "\nNothing landed."

    @staticmethod
    def input_needed_reply(rows):
        """A reply that raises each row by naming its tool under Input Needed, with no question for the owner."""
        names = ", ".join("`%s`" % tool for tool, _ in rows)
        return ("> **Done** OTHER read the state\n> **Deviations** none\n"
                "> **Input Needed** %s was refused; nothing for the owner to decide.\n> **Next** wait" % names)

    def raise_refusal(self, rows, reply, active=False, sid=SID):
        """Raise `rows` with `reply`. Scope first: the rows are in the file. Then the reply passes and clears them."""
        self.write_rows(rows, sid)
        self.assertEqual(self.pending_tools(sid), [tool for tool, _ in rows],
                         "scope: the fixture file does not hold the rows")
        run = self.stop(reply, active=active, sid=sid)
        self.assertEqual(run.stdout.strip(), "", "the reply that raises the refusal blocked: %s" % run.stdout)
        self.assertEqual(self.pending_tools(sid), [], "the reply that raises the refusal left its row in the file")

    def config_files(self):
        """Every file under this test's config folder, as {relative path: bytes}."""
        found = {}
        for root, _, names in os.walk(self.cfg):
            for name in names:
                path = os.path.join(root, name)
                with open(path, "rb") as handle:
                    found[os.path.relpath(path, self.cfg)] = handle.read()
        return found

    def test_d_pending_refusal_not_named_under_input_needed_blocks(self):
        rows = (("unlanded prose reply", False, self.PROSE),
                ("landed report that asks about another tool", True, self.LANDED_OTHER_ASK))
        for label, landed, reply in rows:
            with self.subTest(label):
                self.write_refusals([self.ARCHIVE])
                out = self.blocked(self.stop(reply, landed=landed))
                self.assertIsNotNone(out, "the Stop passed with a pending refusal")
                self.assertEqual(out.get("decision"), "block")
                self.assertIn(self.ARCHIVE, out["reason"])
                self.assertIn("decision refusals-reach-the-owner", out["reason"], "the joined refusal lost its owner cite")
                self.assertIn("does not raise it with the owner", out["reason"])
                self.assertEqual(self.pending_tools(), [self.ARCHIVE], "a blocked Stop cleared the entry")

    def test_e_allow_line_with_no_send_blocks_as_a_question(self):
        # An "allow <tool>?" line is a question for the owner (spec v2.1), so it blocks until the question is
        # sent. Naming the refused tool still clears its entry: the owner was asked about that refusal.
        styles = (("backticks", "Bash", "> **Input Needed** allow `Bash`?"),
                  ("should I", "Bash", "> **Input Needed** Should I allow `Bash`?"),
                  ("plain MCP name", self.ARCHIVE, "> **Input Needed** allow %s?" % self.ARCHIVE))
        for label, tool, line in styles:
            with self.subTest(label):
                self.write_refusals([tool])
                reply = "> **Done** OTHER read the state\n> **Deviations** none\n%s\n> **Next** wait" % line
                out = self.blocked(self.stop(reply, cwd=self.repo))
                self.assertIsNotNone(out, "an allow line with no send passed as the answer")
                self.assertEqual(out.get("decision"), "block")
                self.assertIn("Pick guard", out["reason"])
                self.assertNotIn("Refusal guard", out["reason"], "the named refusal was raised again")
                self.assertNotIn(tool, self.pending_tools(), "the reply did not clear the entry")

    def test_e2_every_pending_tool_named_clears_all_and_the_question_still_blocks(self):
        self.write_refusals([self.ARCHIVE, self.ADD_REPO])
        reply = ("> **Done** OTHER read the state\n> **Deviations** none\n"
                 "> **Input Needed** allow `%s` and `%s`?\n> **Next** wait" % (self.ARCHIVE, self.ADD_REPO))
        out = self.blocked(self.stop(reply, cwd=self.repo))
        self.assertIsNotNone(out, "a reply that asks about two refusals with no send passed")
        self.assertEqual(out.get("decision"), "block")
        self.assertIn("Pick guard", out["reason"])
        self.assertEqual(self.pending_tools(), [], "the reply left an entry in the file")

    def test_e3_a_name_outside_input_needed_is_no_answer(self):
        self.write_refusals([self.ARCHIVE])
        reply = ("> **Done** OTHER read `%s` in the refusal list\n> **Deviations** none\n"
                 "> **Input Needed** none\n> **Next** wait" % self.ARCHIVE)
        out = self.blocked(self.stop(reply))
        self.assertIsNotNone(out, "a name in Done passed as the answer to the refusal")
        self.assertEqual(out.get("decision"), "block")
        self.assertIn(self.ARCHIVE, out["reason"])
        self.assertIn("decision refusals-reach-the-owner", out["reason"], "the joined refusal lost its owner cite")
        self.assertEqual(self.pending_tools(), [self.ARCHIVE])

    def test_k_a_plain_word_in_input_needed_does_not_clear_a_built_in_tool(self):
        # Edit and Bash are English words, so a bare mention of either does not name the tool.
        rows = (("Edit", "Edit the record first?"), ("Bash", "Bash output was empty"))
        for tool, text in rows:
            with self.subTest(tool):
                self.write_refusals([tool])
                reply = ("> **Done** OTHER read the state\n> **Deviations** none\n"
                         "> **Input Needed** %s\n> **Next** wait" % text)
                out = self.blocked(self.stop(reply))
                self.assertIsNotNone(out, "a plain mention of %s cleared it" % tool)
                self.assertEqual(out.get("decision"), "block")
                self.assertIn("`%s`" % tool, out["reason"])
                self.assertEqual(self.pending_tools(), [tool], "a plain mention cleared the entry")

    def test_k2_a_backticked_built_in_tool_name_clears_it(self):
        # The named refusal clears and is not raised again. The allow line is a question (spec v2.1), so the
        # reply still blocks until the question is sent.
        for tool in ("Edit", "Bash"):
            with self.subTest(tool):
                self.write_refusals([tool])
                reply = ("> **Done** OTHER read the state\n> **Deviations** none\n"
                         "> **Input Needed** allow `%s`?\n> **Next** wait" % tool)
                out = self.blocked(self.stop(reply, cwd=self.repo))
                self.assertIsNotNone(out, "a backticked %s allow line with no send passed" % tool)
                self.assertEqual(out.get("decision"), "block")
                self.assertNotIn("Refusal guard", out["reason"], "a backticked %s was raised again" % tool)
                self.assertEqual(self.pending_tools(), [], "the reply left %s in the file" % tool)

    def test_k3_a_short_mcp_name_does_not_clear_the_full_name(self):
        self.write_refusals([self.ARCHIVE])
        reply = ("> **Done** OTHER read the state\n> **Deviations** none\n"
                 "> **Input Needed** allow `archive_session`?\n> **Next** wait")
        out = self.blocked(self.stop(reply))
        self.assertIsNotNone(out, "the short name cleared the full MCP name")
        self.assertEqual(out.get("decision"), "block")
        self.assertIn("`%s`" % self.ARCHIVE, out["reason"], "the block reason does not quote the full name")
        self.assertIn("decision refusals-reach-the-owner", out["reason"], "the joined refusal lost its owner cite")
        self.assertEqual(self.pending_tools(), [self.ARCHIVE])
        # The reason quotes the full name, so one rewrite that names it clears the entry.
        reply = ("> **Done** OTHER read the state\n> **Deviations** none\n"
                 "> **Input Needed** allow `%s`?\n> **Next** wait" % self.ARCHIVE)
        run = self.stop(reply, active=True)
        self.assertEqual(run.stdout.strip(), "", "the rewrite that names the full name blocked: %s" % run.stdout)
        self.assertEqual(self.pending_tools(), [], "the rewrite left the entry in the file")

    def test_k_pending_refusal_with_no_transcript_refuses_and_cites_the_owner_rule(self):
        # The refusal alone blocks when the transcript is missing, and its reason cites the owner rule.
        self.write_refusals([self.ARCHIVE])
        hook = {"hook_event_name": "Stop", "stop_hook_active": False, "session_id": self.SID, "cwd": self.scratch}
        run = run_guard(REPORT_GUARD, hook, env=dict(os.environ, CLAUDE_CONFIG_DIR=self.cfg))
        self.assertEqual(run.returncode, 0, run.stderr)
        out = self.blocked(run)
        self.assertIsNotNone(out, "the Stop passed with a pending refusal and no transcript")
        self.assertEqual(out.get("decision"), "block")
        self.assertIn(self.ARCHIVE, out["reason"])
        self.assertEqual(out["reason"].count("decision refusals-reach-the-owner"), 1, out["reason"])
        self.assertEqual(self.pending_tools(), [self.ARCHIVE], "a blocked Stop cleared the entry")

    def test_f_stop_hook_active_does_not_block_on_a_refusal(self):
        rows = (("unlanded", False, self.PROSE), ("landed", True, self.LANDED_OTHER_ASK))
        for label, landed, reply in rows:
            with self.subTest(label):
                self.write_refusals([self.ARCHIVE])
                run = self.stop(reply, landed=landed, active=True)
                self.assertEqual(run.stdout.strip(), "", "a stop_hook_active Stop blocked on a refusal: %s" % run.stdout)

    def test_g_no_refusals_file_is_a_no_op(self):
        rows = (("unlanded", False, self.PROSE), ("landed clean report", True, self.LANDED_CLEAN))
        for label, landed, reply in rows:
            with self.subTest(label):
                run = self.stop(reply, landed=landed)
                self.assertEqual(run.stdout.strip(), "", run.stdout)
                self.assertFalse(os.path.exists(self.refusals_file()), "the Stop wrote a refusals file")

    def test_i_another_sessions_refusals_do_not_block(self):
        self.write_refusals([self.ARCHIVE], sid="pd-other-sid")
        run = self.stop(self.PROSE)
        self.assertEqual(run.stdout.strip(), "", "another session's refusal blocked this Stop: %s" % run.stdout)
        self.assertEqual(self.pending_tools("pd-other-sid"), [self.ARCHIVE])

    def test_j_unreadable_refusals_file_fails_open(self):
        os.makedirs(os.path.dirname(self.refusals_file()), exist_ok=True)
        with open(self.refusals_file(), "w", encoding="utf-8") as handle:
            handle.write("not json\n")
        run = self.stop(self.PROSE)
        self.assertEqual(run.stdout.strip(), "", "an unreadable refusals file blocked the Stop: %s" % run.stdout)

    def test_l_a_raised_refusal_does_not_block_again_for_the_same_tool_and_reason(self):
        # Catches: a refusal the owner was already told of blocks again, when the classifier refuses the same tool
        # for the same reason and a later reply does not name it.
        one = [(self.ARCHIVE, self.REASON)]
        two = [(self.ARCHIVE, self.REASON), (self.ADD_REPO, self.REASON)]
        raises = (("refusal was right, one row", self.raising_reply, one),
                  ("Input Needed, one row", self.input_needed_reply, one),
                  ("refusal was right, two rows", self.raising_reply, two))
        followers = (("unlanded prose", False, self.PROSE), ("landed clean report", True, self.LANDED_CLEAN))
        for raise_label, make_reply, rows in raises:
            for next_label, landed, reply in followers:
                with self.subTest(raised=raise_label, next_reply=next_label):
                    self.use_fresh_config()
                    self.raise_refusal(rows, make_reply(rows))
                    self.write_rows(rows)
                    out = self.blocked(self.stop(reply, landed=landed))
                    self.assertIsNone(out, "a refusal already raised with the owner blocked again: %s" % out)
                    self.assertEqual(self.pending_tools(), [], "the Stop left the repeated refusal in the file")

    def test_m_a_new_refusal_still_blocks_after_a_raise(self):
        # Catches: a raise settles a different refusal of the same tool, or of another tool with the same reason.
        cases = (("same tool, new reason", [(self.BASH, self.REASON)], [(self.BASH, self.OTHER_REASON)], self.BASH),
                 ("new tool, same reason", [(self.ARCHIVE, self.REASON)], [(self.ADD_REPO, self.REASON)], self.ADD_REPO))
        for label, raised, new, tool in cases:
            with self.subTest(label):
                self.use_fresh_config()
                self.raise_refusal(raised, self.raising_reply(raised))
                self.write_rows(new)
                out = self.blocked(self.stop(self.PROSE))
                self.assertIsNotNone(out, "a new refusal passed on the strength of an earlier raise")
                self.assertEqual(out.get("decision"), "block")
                self.assertIn("`%s`" % tool, out["reason"], "the block does not name the new refusal")
                self.assertEqual(self.pending_tools(), [tool], "the new refusal left the file")

    def test_n_an_empty_reason_is_never_matched(self):
        # Catches: refusals with no reason read as one refusal, so a second one with no reason passes unraised.
        cases = (("empty, then empty", [(self.BASH, "")], [(self.BASH, "")]),
                 ("a reason, then empty", [(self.BASH, self.REASON)], [(self.BASH, "")]))
        for label, raised, new in cases:
            with self.subTest(label):
                self.use_fresh_config()
                self.raise_refusal(raised, self.raising_reply(raised))
                self.write_rows(new)
                out = self.blocked(self.stop(self.PROSE))
                self.assertIsNotNone(out, "a refusal with no reason passed on the strength of an earlier raise")
                self.assertEqual(out.get("decision"), "block")
                self.assertIn("`%s`" % self.BASH, out["reason"])
                self.assertEqual(self.pending_tools(), [self.BASH], "the empty-reason refusal left the file")

    def test_o_a_stop_hook_active_raise_is_recorded_and_never_blocks(self):
        # Catches: a rewrite Stop clears a refusal without recording it, so the next reply blocks on it again.
        rows = [(self.ARCHIVE, self.REASON)]
        raises = (("refusal was right", self.raising_reply), ("Input Needed", self.input_needed_reply))
        for raise_label, make_reply in raises:
            with self.subTest(raised=raise_label):
                self.use_fresh_config()
                self.raise_refusal(rows, make_reply(rows), active=True)  # the rewrite never blocks, and clears the row
                self.write_rows(rows)
                out = self.blocked(self.stop(self.PROSE))
                self.assertIsNone(out, "a refusal raised by a stop_hook_active rewrite blocked again: %s" % out)
                self.assertEqual(self.pending_tools(), [], "the Stop left the repeated refusal in the file")

    def test_p_a_raise_in_one_session_does_not_settle_another(self):
        # Catches: the raised record is shared across sessions, so one session's raise settles another's refusal.
        other = "pd-other-sid-raised"
        rows = [(self.ARCHIVE, self.REASON)]
        self.raise_refusal(rows, self.raising_reply(rows))
        self.write_rows(rows, sid=other)
        self.assertEqual(self.pending_tools(other), [self.ARCHIVE],
                         "scope: the other session's file does not hold the row")
        out = self.blocked(self.stop(self.PROSE, sid=other))
        self.assertIsNotNone(out, "another session's raise settled this session's refusal")
        self.assertEqual(out.get("decision"), "block")
        self.assertIn(self.ARCHIVE, out["reason"])
        self.assertEqual(self.pending_tools(other), [self.ARCHIVE], "a blocked Stop cleared the other session's row")

    def test_q_a_stop_with_no_refusals_file_writes_nothing(self):
        # Catches: a Stop writes state under the config folder when no refusal is pending. The cost is one stat.
        for label, landed, reply in (("unlanded", False, self.PROSE), ("landed clean report", True, self.LANDED_CLEAN)):
            with self.subTest(label):
                self.use_fresh_config()
                self.assertFalse(os.path.exists(self.refusals_file()), "scope: a refusals file exists")
                before = self.config_files()
                run = self.stop(reply, landed=landed)
                self.assertEqual(run.stdout.strip(), "", run.stdout)
                self.assertEqual(self.config_files(), before, "the Stop wrote a file with no refusal pending")

    def test_s_a_blank_reason_is_never_matched(self):
        # Catches: a reason of spaces only counts as a reason, so a second refusal with that blank reason passes
        # on the strength of an earlier raise. A blank reason identifies nothing, as an empty one does.
        raises = (("refusal was right", self.raising_reply), ("Input Needed", self.input_needed_reply))
        for raise_label, make_reply in raises:
            with self.subTest(raised=raise_label):
                self.use_fresh_config()
                rows = [(self.BASH, "   ")]
                self.raise_refusal(rows, make_reply(rows))
                self.write_rows(rows)
                out = self.blocked(self.stop(self.PROSE))
                self.assertIsNotNone(out, "a refusal with a blank reason passed on the strength of an earlier raise")
                self.assertEqual(out.get("decision"), "block")
                self.assertIn("`%s`" % self.BASH, out["reason"], "the block does not name the blank-reason refusal")
                self.assertEqual(self.pending_tools(), [self.BASH], "the blank-reason refusal left the file")

    def test_r_an_agent_row_is_never_recorded_as_raised(self):
        # Catches: an agent's refused call is recorded as raised, so the same tool and reason refused to the
        # orchestrator later passes unseen. The agent row clears by the agent rule; the orchestrator row must block.
        agent = [(self.BASH, self.REASON)]
        followers = (("unlanded prose", False, self.PROSE), ("landed clean report", True, self.LANDED_CLEAN))
        for label, landed, reply in followers:
            with self.subTest(next_reply=label):
                self.use_fresh_config()
                self.write_rows(agent, agent_id="agent-r1")
                self.assertEqual(self.pending_tools(), [self.BASH], "scope: the fixture file does not hold the agent row")
                run = self.stop(self.input_needed_reply(agent))
                self.assertEqual(run.stdout.strip(), "", "the reply that names the agent row blocked: %s" % run.stdout)
                self.assertEqual(self.pending_tools(), [], "the reply left the agent row in the file")
                self.write_rows(agent)
                out = self.blocked(self.stop(reply, landed=landed))
                self.assertIsNotNone(out, "an orchestrator row passed on the strength of an agent row that was named")
                self.assertEqual(out.get("decision"), "block")
                self.assertIn(self.BASH, out["reason"], "the block does not name the orchestrator refusal")
                self.assertEqual(self.pending_tools(), [self.BASH], "a blocked Stop cleared the orchestrator row")

    def test_t_block_reason_names_both_clearing_forms_as_facts(self):
        # Catches: the block reason says a refused tool is unanswered but not how it clears, so the session cannot
        # tell that naming the tool under Input Needed, or writing the phrase after its name, clears it. The phrase
        # is quoted with the placeholder <tool_name>, as the decision says (refusals-reach-the-owner): quoting it
        # with the real tool name would clear the row. The reason is facts only: no order to the session. It says
        # "clears when", never "clears only when": an MCP tool also clears by its full name, and "refusal is right"
        # also clears, so "only" would be false.
        for label, tools in (("one tool", [self.BASH]), ("two tools", [self.BASH, self.ARCHIVE])):
            with self.subTest(refused=label):
                self.use_fresh_config()
                self.write_refusals(tools)
                out = self.blocked(self.stop(self.PROSE))
                self.assertIsNotNone(out, "the Stop passed with a pending refusal")
                reason = out["reason"]
                for tool in tools:  # scope first: the reason names each refused tool in backticks
                    self.assertIn("`%s`" % tool, reason, "scope: the block does not name refused tool %s" % tool)
                order = RG.session_wording(reason)
                checks = (
                    ("the block does not say when a refused tool clears", "clears when" in reason),
                    ("the block says 'only' about clearing, which is false: other forms clear a tool too",
                     not re.search(r"\bonly\b", reason, re.I)),
                    ("the block does not give the Input Needed clearing form", "under Input Needed" in reason),
                    ("the block does not give the phrase clearing form `<tool_name>`: refusal was right",
                     "`<tool_name>`: refusal was right" in reason),
                    ("the block quotes the phrase with a real tool name, so quoting it would clear the row",
                     not any("`%s`: refusal was right" % tool in reason for tool in tools)),
                    ("the block holds an order to the session: %r" % order, not order),
                )
                for cause, passed in checks:
                    with self.subTest(cause=cause):
                        self.assertTrue(passed, cause)

    def test_t_block_reason_says_an_mcp_tool_counts_by_full_name(self):
        # Catches: the block reason gives the clearing forms but not that an MCP tool counts by its full name, so a
        # session that refused an MCP call cannot tell that naming its full name, in backticks or not, clears the row.
        # The reason is facts only: no order to the session.
        self.write_refusals([self.ARCHIVE])
        out = self.blocked(self.stop(self.PROSE))
        self.assertIsNotNone(out, "the Stop passed with a pending refusal")
        reason = out["reason"]
        self.assertIn("`%s`" % self.ARCHIVE, reason, "scope: the block does not name the refused MCP tool")
        flat = " ".join(reason.split()).lower()  # a line break in the reason does not hide the wording
        order = RG.session_wording(reason)
        checks = (
            ("the block does not say an MCP tool counts by its full name",
             "mcp tool counts by its full name" in flat),
            ("the block does not say the full name counts with or without backticks",
             "with or without backticks" in flat),
            ("the block holds an order to the session: %r" % order, not order),
        )
        for cause, passed in checks:
            with self.subTest(cause=cause):
                self.assertTrue(passed, cause)


# building-mistake-names-its-guard (decision mistake-means-missing-guard): a Deviations admission of a
# mistake the agent made names the guard for it. Every case is one landing turn read through main().
MG_RULE = "building-mistake-names-its-guard"
MG_DONE = "> **Done** OTHER read the audit"
MG_INBOX = "I broke my feedback inbox: a sed -i deleted its closing fence, not its last item."


def mg_report(deviations, done=MG_DONE, nxt="> **Next** none"):
    return "%s\n> **Deviations** %s\n%s" % (done, deviations, nxt)


class MistakeNamesGuardTests(unittest.TestCase):
    """building-mistake-names-its-guard, in report_guard.py's Stop hook: an admission in Deviations names its guard."""

    def setUp(self):
        self.folder = tempfile.mkdtemp(dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, self.folder, True)

    def verdict(self, reply, landed=True):
        run = landed_run(self.folder, reply, "git commit -m x" if landed else "git status")
        self.assertEqual(run.returncode, 0, run.stderr[-300:])
        return json.loads(run.stdout) if run.stdout.strip() else None

    def assert_blocked(self, reply):
        out = self.verdict(reply)
        self.assertIsNotNone(out, "no block: a Deviations admission with no guard named passed: " + reply)
        self.assertEqual(out.get("decision"), "block", out)
        self.assertIn(MG_RULE, out.get("reason", ""), "the block does not name the rule: %s" % out)

    def assert_allowed(self, reply, landed=True):
        out = self.verdict(reply, landed)
        self.assertIsNone(out, "a control blocked, but must pass: %s" % out)

    # Red: an admission that names no guard blocks.
    def test_mg_red_inbox_admission_blocks(self):
        self.assert_blocked(mg_report(MG_INBOX))

    def test_mg_red_stale_decision_blocks(self):
        self.assert_blocked(mg_report("I trusted a stale decision line and called a lane idle while its PR was open."))

    def test_mg_red_wrong_short_sha_blocks(self):
        self.assert_blocked(mg_report("My first message to the batch runner gave a wrong short sha."))

    def test_mg_red_clobbered_notes_blocks(self):
        self.assert_blocked(mg_report("I clobbered the lane's notes file by mistake."))

    def test_mg_red_outdated_record_blocks(self):
        self.assert_blocked(mg_report("I trusted an outdated record and skipped the check."))

    # Red twins: each one fails if a green control's clearing rule is read too loosely.
    def test_mg_red_guard_word_without_ref_blocks(self):
        self.assert_blocked(mg_report("I broke the inbox; a guard would catch it."))

    def test_mg_red_split_ref_and_guard_word_blocks(self):
        self.assert_blocked(mg_report("I wrongly sent commit 3c2d1d97f; the CI check passed on it."))

    def test_mg_red_negator_in_another_clause_blocks(self):
        self.assert_blocked(mg_report("I did not test it, and I broke the build."))

    # A negator clears only within 3 words before the fault word: four words between them still block.
    def test_mg_red_negator_four_words_before_fault_blocks(self):
        self.assert_blocked(mg_report("I did not run the check and broke the build."))

    def test_mg_red_never_four_words_before_fault_blocks(self):
        self.assert_blocked(mg_report("I never read the diff and clobbered the notes."))

    def test_mg_red_admission_in_second_bullet_blocks(self):
        self.assert_blocked(
            "%s\n> **Deviations**\n> - the audit ran twice\n> - %s\n> **Next** none" % (MG_DONE, MG_INBOX))

    def test_mg_red_apostrophes_do_not_hide_admission_blocks(self):
        self.assert_blocked(mg_report("I didn't check; I clobbered the lane's notes."))

    def test_mg_red_lone_apostrophe_does_not_hide_admission_blocks(self):
        # A lone apostrophe with a space before it reads as an opening quote. The admission after it still counts.
        for text in ("I waited 'til the lane ended, and I broke the batch.' Nothing else.",
                     "I ran it 'cause the lane was slow, and I clobbered the notes.' Nothing else."):
            with self.subTest(text=text):
                self.assert_blocked(mg_report(text))

    def test_mg_red_elided_opener_does_not_hide_admission_blocks(self):
        # An elided word after an apostrophe ('em, 'round, 'tis, 'kay) is no opening quote, so the admission after it
        # still counts. Each text holds one lone elision and a later apostrophe that could close a span.
        for text in ("I told 'em to wait, then I broke the lanes' notes.",
                     "I waited 'round the lanes, then I clobbered the notes.' Nothing else.",
                     "The lane said 'tis fine, and I broke the batch.' Nothing else.",
                     "I called it 'kay, then I overwrote the notes.' Nothing else."):
            with self.subTest(text=text):
                self.assert_blocked(mg_report(text))

    def test_mg_red_capitalised_elision_does_not_hide_admission_blocks(self):
        # A capitalised elision ('Cause, 'Til) opens no quote either: the admission after it still counts.
        for text in ("I ran it 'Cause the lane was slow, and I clobbered the notes.' Nothing else.",
                     "I waited 'Til the lanes ended, and I broke the batch.' Nothing else."):
            with self.subTest(text=text):
                self.assert_blocked(mg_report(text))

    def test_mg_red_year_elision_does_not_hide_admission_blocks(self):
        # A year elision ('25) opens no quote either: the admission after it still counts.
        self.assert_blocked(mg_report("Back in '25 I broke the lanes' notes."))

    def test_mg_pin_listed_elisions_do_not_hide_admission_blocks(self):
        # Green now: 'cos, 'twas and 'nuff are listed elisions. Each text holds one and a later apostrophe.
        for text in ("I waited 'cos the lane was slow, and I clobbered the notes.' Nothing else.",
                     "The lane said 'twas fine, and I broke the batch.' Nothing else.",
                     "I told them 'nuff, then I overwrote the notes.' Nothing else."):
            with self.subTest(text=text):
                self.assert_blocked(mg_report(text))

    # Green: each of these must pass.
    def test_mg_green_inbox_admission_with_fence_step_passes(self):
        self.assert_allowed(mg_report(MG_INBOX + " Queued as step:inbox-fence-check."))

    def test_mg_green_inbox_admission_with_debt_passes(self):
        self.assert_allowed(mg_report(MG_INBOX + " A debt records it."))

    def test_mg_green_inbox_admission_with_guard_ref_passes(self):
        self.assert_allowed(mg_report(MG_INBOX + " The guard is built in #1300."))

    def test_mg_green_did_not_break_anything_passes(self):
        self.assert_allowed(mg_report("I never broke anything."))

    def test_mg_green_nothing_i_did_passes(self):
        self.assert_allowed(mg_report("Nothing I did broke the build."))

    def test_mg_green_repointed_test_passes(self):
        self.assert_allowed(mg_report("The test was wrong; I re-pointed it."))

    def test_mg_green_worktree_refusal_passes(self):
        self.assert_allowed(mg_report("I routed around the refusal because the guard was wrong about the worktree."))

    def test_mg_green_quoted_owner_phrase_passes(self):
        self.assert_allowed(mg_report('Owner said "I broke it, own up to a mistake".'))

    def test_mg_green_single_quoted_owner_phrase_passes(self):
        self.assert_allowed(mg_report("Owner said 'I broke it, own up to a mistake'."))

    def test_mg_green_elision_closed_at_once_stays_quoted_passes(self):
        # 'em' closed at once is quoted text, so the quote after it pairs as usual and 'I broke it' stays quoted.
        self.assert_allowed(mg_report("Owner said 'em' and 'I broke it'."))

    def test_mg_green_admission_in_done_passes(self):
        self.assert_allowed(mg_report("none", done="> **Done** OTHER I broke my feedback inbox and restored it."))

    def test_mg_green_admission_in_next_passes(self):
        self.assert_allowed(mg_report("none", nxt="> **Next** I trusted a stale decision line and will re-check it."))

    def test_mg_green_admission_on_unlanded_turn_passes(self):
        self.assert_allowed(mg_report(MG_INBOX), landed=False)

    def test_mg_green_empty_deviations_passes(self):
        self.assert_allowed(mg_report("none"))

    def test_mg_green_lost_race_passes(self):
        self.assert_allowed(mg_report("I lost the race to another lane."))

    def test_mg_green_wiped_cache_passes(self):
        self.assert_allowed(mg_report("I wiped the cache to reproduce the failure."))

    def test_mg_green_trusted_verdict_passes(self):
        self.assert_allowed(mg_report("I trusted the reviewer's verdict; it was correct."))

    # A first-person word after the fault word in its clause is not the admission's subject.
    def test_mg_green_i_after_fault_word_in_clause_passes(self):
        self.assert_allowed(mg_report("The test was wrong so I re-pointed it."))

    def test_mg_green_wrong_file_then_i_used_passes(self):
        self.assert_allowed(mg_report("The brief named the wrong file and I used foo.py."))

    # "corrupted" is not a fault word, so a regenerated corrupted fixture is not an admission.
    def test_mg_green_regenerated_corrupted_fixture_passes(self):
        self.assert_allowed(mg_report("I regenerated the corrupted fixture."))

    # A guard, check or debt named in a later sentence of the same Deviations item clears the admission.
    def test_mg_green_guard_built_in_pr_sentence_passes(self):
        self.assert_allowed(mg_report("I broke the inbox. Guard built in PR #1300."))

    def test_mg_green_check_added_in_sentence_passes(self):
        self.assert_allowed(mg_report("I broke the inbox. Check added in #1300."))

    def test_mg_green_debt_filed_sentence_passes(self):
        self.assert_allowed(mg_report("I broke the inbox. Debt filed: inbox-fence."))

    # "broke" that means split admits nothing, so it passes. Each fault word after it still admits a mistake, even
    # with a relative clause ("that was wrong"), a when clause or a parenthesis after the writer's verb: a regex
    # cannot tell that description from an admission, so no such clause clears it.
    def test_mg_green_broke_the_batch_into_lanes_passes(self):
        self.assert_allowed(mg_report("I broke the batch into three lanes."))

    # "into" after "broke" does not clear an admission that names a state the writer put the thing in.
    def test_mg_red_broke_the_build_into_a_red_state_blocks(self):
        self.assert_blocked(mg_report("I broke the build into a red state."))

    def test_mg_red_changed_the_test_that_was_wrong_blocks(self):
        self.assert_blocked(mg_report("I changed the test that was wrong."))

    def test_mg_red_repointed_test_in_parentheses_blocks(self):
        self.assert_blocked(mg_report("I re-pointed the test (the one that was wrong)."))

    def test_mg_red_repointed_test_when_check_was_wrong_blocks(self):
        self.assert_blocked(mg_report("I re-pointed the test when the check was wrong."))

    def test_mg_red_wrote_the_test_that_was_wrong_blocks(self):
        self.assert_blocked(mg_report("I wrote the test that was wrong."))

    def test_mg_red_merged_the_pr_when_check_was_wrong_blocks(self):
        self.assert_blocked(mg_report("I merged the PR when the check was wrong."))

    def test_mg_red_merged_the_pr_and_that_was_wrong_blocks(self):
        self.assert_blocked(mg_report("I merged the PR and that was wrong."))

    # The twins: an admission keeps its block when a parenthesis, a that clause or a when clause follows it.
    # A clause split must cut only after the admission, never drop it.
    def test_mg_red_broke_the_batch_by_merging_a_red_lane_blocks(self):
        self.assert_blocked(mg_report("I broke the batch by merging a red lane."))

    def test_mg_red_changed_the_test_wrongly_blocks(self):
        self.assert_blocked(mg_report("I changed the test wrongly."))

    def test_mg_red_forgot_the_check_in_parentheses_blocks(self):
        self.assert_blocked(mg_report("I forgot the check (the one for the batch)."))

    def test_mg_red_trusted_stale_record_before_that_clause_blocks(self):
        self.assert_blocked(mg_report("I trusted a stale record that the lane had cited."))

    def test_mg_red_forgot_the_check_before_when_clause_blocks(self):
        self.assert_blocked(mg_report("I forgot the check when the lane was open."))


if __name__ == "__main__":
    unittest.main()
