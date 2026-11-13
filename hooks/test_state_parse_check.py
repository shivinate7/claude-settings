#!/usr/bin/env python3
"""Cases for the PostToolUse check of state files a call names (decision state-file-parse-check). Standard library only.

Run it from the repository root:

    python3 hooks/test_state_parse_check.py

WHAT IT PROVES. After a Bash, PowerShell, Write, Edit or MultiEdit call, a state file that the call left
unreadable is named in a PostToolUse additionalContext: a *.json that json.loads rejects, an inbox or handoff
.md with a code fence left open, an Edit that drops an inbox block header, or a handoff with no Working premises
heading. The check never blocks (exit 0) and never changes a file. It stays silent for a file that was already
broken before the call, for a deleted file, for a read, for a .md outside the handoff folder, for a call that
names no state file, and for the scanner traps (fences inside JSON strings, mid-line backticks, indented fences,
tilde blocks, a lone apostrophe, a quoted `>` and a quoted `#`).

THE SEAM. Each case runs the PostToolUse commands that settings.json registers for the call's tool, as Claude
Code does, with the payload on stdin and CLAUDE_CONFIG_DIR at a temp folder. No case names the check's file. So
the check's home may be a new file or an existing one, and a red on an old commit is an assert that no
registered hook names the broken file. It is never a missing import or path.

A SILENT CASE HAS A TWIN. Empty output also comes from a hook that is absent or never prints. So each silent
expectation sits in the same test as a named expectation for the same file made broken.

WORDING. The spec fixes no message text. The cases look for the file's basename, for `line N` and `column N`
where a JSON or fence line is claimed, and for `Working premises` on the handoff check.

TEMP FILES. One run folder per run (lint/_test_temp.py, the one home of the standard), removed at exit. Every
case's folders sit under it.
"""

import atexit
import collections
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "lint"))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (the one home, lint/_test_temp.py)
sys.path.insert(0, HERE)
import test_wrappers  # noqa: E402  the one home of the settings.json reader (hooks/test_wrappers.py)

RUN = _test_temp.run_folder()
atexit.register(shutil.rmtree, RUN, True)
SHELL_ONLY = unittest.skipIf(os.name == "nt", "the cases run Bash in sh, which this platform lacks")
GNU_SED_ONLY = unittest.skipIf(os.name == "nt" or sys.platform == "darwin",
                               "sed -i takes a suffix argument on BSD sed, so these cases run on Linux")

HEAD_1 = "### 2026-11-06 11:38 CST (UTC-06:00)"
HEAD_2 = "### 2026-11-06 11:40 CST (UTC-06:00)"
GOAL = "# Handoff\n\n## Goal\n\nShip the state check.\n\n"
PREMISES = "## Working premises\n\n- the owner's word settles a ruling\n"
OK_JSON = '{\n  "a": 1,\n  "b": 2\n}\n'

# An inbox with two owner blocks. Each fence closes; each block has one item line.
INBOX_TWO = (HEAD_1 + "\n````\nfirst owner message\n````\n- fb-1138-1 [note] -> noted\n"
             + HEAD_2 + "\n````\nsecond owner message\n````\n- fb-1140-1 [note] -> noted\n")

# Valid JSON that holds a fence, a URL with a comment opener, and a comment-looking string.
JSON_TRAP_OK = ('{\n  "body": "```",\n  "url": "https://example.com/*x",\n'
                '  "note": "// not a comment"\n}\n')
JSON_TRAP_BAD = ('{\n  "body": "```",\n  "url": "https://example.com/*x",\n'
                 '  "note": "// not a comment",\n}\n')

# Handoff text that a correct check must leave silent. Each one is valid markdown.
TRAPS = [
    ("three backticks mid-line", "Use ``` mid-line in a sentence, not as a fence.\n"),
    ("a longer outer fence around a shorter inner one", "````\n```\ninner text\n```\n````\n"),
    ("a tilde fence holding a balanced backtick pair", "~~~\n```\ncode\n```\n~~~\n"),
    ("a tilde fence holding one backtick line", "~~~\n```\ncode\n~~~\n"),
    ("a fence indented four spaces", "    ```\n    indented code\n"),
    ("a lone apostrophe in text", "Don't block the handoff on the dashboard.\n"),
    ("a quoted fence line", "\"```\"\n"),
    ("a bash info-string block", "```bash\nls -la\n```\n"),
]


def handoff_text(middle=""):
    return GOAL + PREMISES + "\n" + middle


def build_inbox(count, drop_last_closer=False):
    """An inbox of `count` owner blocks. Returns (text, line of the last block's opening fence)."""
    lines, opener = [], 0
    for i in range(count):
        minutes = 8 * 60 + i
        lines.append("### 2026-11-06 %02d:%02d CST (UTC-06:00)" % (minutes // 60, minutes % 60))
        opener = len(lines) + 1
        lines += ["````", "owner message %d" % i, "````", "- fb-%d-1 [note] -> noted" % i]
    if drop_last_closer:
        del lines[-2]
    return "\n".join(lines) + "\n", opener


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def read_text(path):
    with open(path, "r", encoding="utf-8", newline="") as handle:
        return handle.read()


def read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


def json_error(t, text):
    """The (line, column) that json.loads reports for `text`. The expected position comes from the stdlib
    of the Python that runs this file, so it holds on any version."""
    try:
        json.loads(text)
    except json.JSONDecodeError as error:
        return error.lineno, error.colno
    t.fail("scope: the text is valid JSON, so it has no error position")


def edit_on_disk(t, path, old, new):
    """Apply an Edit to the file, as the Edit tool would have. The old text must occur once."""
    text = read_text(path)
    t.assertEqual(text.count(old), 1, "scope: old_string must occur once in %s" % os.path.basename(path))
    write(path, text.replace(old, new, 1))


def payload(cwd, sid, tool, tool_input, response=None):
    """A PostToolUse payload. tool_input comes before tool_response, as the hook's shell filter expects."""
    return json.dumps({
        "session_id": sid,
        "hook_event_name": "PostToolUse",
        "cwd": cwd,
        "tool_name": tool,
        "tool_input": tool_input,
        "tool_response": response if response is not None else {"stdout": "", "stderr": ""},
    })


def post_context(stdout):
    """The PostToolUse additionalContext that one hook printed, or "" when it printed none of that kind."""
    try:
        special = json.loads(stdout)["hookSpecificOutput"]
    except (ValueError, KeyError, TypeError):
        return ""
    if special.get("hookEventName") != "PostToolUse":
        return ""
    return special.get("additionalContext", "") or ""


def hook_commands(tool):
    """The PostToolUse commands settings.json registers for the tool, in file order. A matcher is a regex
    on the tool name; a group with no matcher runs for every tool."""
    found = []
    for group in test_wrappers.load().get("hooks", {}).get("PostToolUse", []):
        matcher = group.get("matcher")
        if matcher is None or re.fullmatch(matcher, tool):
            found += [h["command"] for h in group.get("hooks", []) if h.get("command")]
    return found


def hooks_template():
    """One copy of hooks/ per run, without the test files. Every case's config folder links to it."""
    template = os.path.join(RUN, "hooks")
    if not os.path.isdir(template):
        shutil.copytree(os.path.join(REPO, "hooks"), template,
                        ignore=shutil.ignore_patterns("test_*.py", "__pycache__"))
    return template


def assert_silent(t, ctx, why):
    t.assertEqual(ctx, "", "%s: a registered hook spoke about a file that is fine: %r" % (why, ctx[:160]))


def assert_named(t, codes, ctx, why, name, home, line=None, column=None, words=()):
    t.assertTrue(ctx, "%s: no registered hook named the break" % why)
    t.assertIn(name, ctx, "%s: the message does not name %s: %r" % (why, name, ctx[:160]))
    bare = ctx.replace(RUN, " ").replace(home.root, " ")
    if line is not None:
        t.assertRegex(bare, r"\bline\D{0,4}%d\b" % line, "%s: no `line %d` in the message: %r" % (why, line, ctx[:160]))
    if column is not None:
        t.assertRegex(bare, r"\bcol(?:umn)?\D{0,4}%d\b" % column,
                      "%s: no `column %d` in the message: %r" % (why, column, ctx[:160]))
    for word in words:
        t.assertIn(word, ctx, "%s: the message does not say %r" % (why, word))
    t.assertTrue(all(code == 0 for code in codes), "%s: a hook exited %r, and it must never block" % (why, codes))


class Home:
    """One config folder and one work folder for a case, both under the run folder. The config folder links to
    the run's copy of hooks/, so the registered commands find their files as they do in a real session."""

    def __init__(self):
        self.sid = "s-" + uuid.uuid4().hex[:12]
        self.root = tempfile.mkdtemp(prefix="case-", dir=RUN)
        self.cfg = os.path.join(self.root, "config")
        self.handoffs = os.path.join(self.cfg, "handoffs")
        self.work = os.path.join(self.root, "work")
        os.makedirs(self.handoffs)
        os.makedirs(self.work)
        link = os.path.join(self.cfg, "hooks")
        try:
            os.symlink(hooks_template(), link, target_is_directory=True)
        except OSError:
            shutil.copytree(hooks_template(), link)

    @property
    def inbox(self):
        return os.path.join(self.handoffs, self.sid + ".inbox.md")

    @property
    def handoff(self):
        return os.path.join(self.handoffs, self.sid + ".md")

    def dispatch(self, tool, tool_input, response=None):
        """Run the registered PostToolUse commands for the tool, as Claude Code does. Return (exit codes, context)."""
        body = payload(self.work, self.sid, tool, tool_input, response)
        env = dict(os.environ, CLAUDE_CONFIG_DIR=self.cfg, HOME=self.root, PYTHONDONTWRITEBYTECODE="1")
        codes, contexts = [], []
        for command in hook_commands(tool):
            done = subprocess.run([test_wrappers.SH, "-c", command], input=body, capture_output=True,
                                  text=True, env=env, cwd=self.work, timeout=60)
            codes.append(done.returncode)
            found = post_context(done.stdout)
            if found:
                contexts.append(found)
        return codes, "\n".join(contexts)

    def write_hook(self, path, text):
        """A Write call: the file is written, then the registered hooks run on the call."""
        write(path, text)
        return self.dispatch("Write", {"file_path": path, "content": text})

    def sh(self, command):
        """Run a command for real in sh, as the Bash tool would, and return its exit code."""
        return subprocess.run(["sh", "-c", command], cwd=self.work, capture_output=True, text=True).returncode


class IncidentReplay(unittest.TestCase):
    """The coordinator's inbox, and the sed that deleted its closing fence."""

    @GNU_SED_ONLY
    def test_sed_that_deletes_the_closing_fence_is_named_at_the_open_fence(self):
        home = Home()
        intact = HEAD_1 + "\n````\nowner: keep the closing fence\n````\n"
        self.assertEqual(intact.splitlines()[-1], "````", "scope: the closer must be the last line")
        codes, ctx = home.write_hook(home.inbox, intact)
        assert_silent(self, ctx, "the intact inbox")
        command = "sed -i '$d' " + shlex.quote(home.inbox)
        self.assertEqual(home.sh(command), 0, "scope: the sed must run on the temp inbox")
        self.assertNotEqual(read_text(home.inbox).splitlines()[-1], "````", "scope: the sed must delete the closer")
        after = read_bytes(home.inbox)
        codes, ctx = home.dispatch("Bash", {"command": command})
        assert_named(self, codes, ctx, "the sed that deleted the closer", home.sid + ".inbox.md", home, line=2)
        self.assertEqual(read_bytes(home.inbox), after, "a registered hook changed the inbox; it must never revert")


class EditJson(unittest.TestCase):
    """An Edit or MultiEdit on a *.json, judged on the state the call left."""

    def test_edit_that_breaks_json_names_the_line_and_column(self):
        home = Home()
        path = os.path.join(home.work, "state.json")
        write(path, OK_JSON)
        json.loads(read_text(path))
        old, new = '"b": 2', '"b": 2,'
        edit_on_disk(self, path, old, new)
        line, column = json_error(self, read_text(path))
        codes, ctx = home.dispatch("Edit", {"file_path": path, "old_string": old, "new_string": new})
        assert_named(self, codes, ctx, "an Edit that adds a trailing comma", "state.json", home,
                     line=line, column=column)

    def test_edit_on_a_file_already_broken_is_silent(self):
        home = Home()
        path = os.path.join(home.work, "state.json")
        broken = '{\n  "a": 1,,\n  "b": 2\n}\n'
        write(path, broken)
        with self.assertRaises(json.JSONDecodeError):
            json.loads(broken)
        old, new = '"b": 2', '"b": 3'
        edit_on_disk(self, path, old, new)
        with self.assertRaises(json.JSONDecodeError):
            json.loads(read_text(path))
        codes, ctx = home.dispatch("Edit", {"file_path": path, "old_string": old, "new_string": new})
        assert_silent(self, ctx, "an Edit on a file that was broken before the call")
        line, column = json_error(self, read_text(path))
        codes, ctx = home.write_hook(path, read_text(path))
        assert_named(self, codes, ctx, "the same break written in a Write", "state.json", home,
                     line=line, column=column)

    def test_multiedit_that_breaks_json_names_the_line_and_column(self):
        home = Home()
        path = os.path.join(home.work, "state.json")
        write(path, OK_JSON)
        edits = [{"old_string": '"a": 1', "new_string": '"a": 10'},
                 {"old_string": '"b": 2', "new_string": '"b": 2,'}]
        for edit in edits:
            edit_on_disk(self, path, edit["old_string"], edit["new_string"])
        line, column = json_error(self, read_text(path))
        codes, ctx = home.dispatch("MultiEdit", {"file_path": path, "edits": edits})
        assert_named(self, codes, ctx, "a MultiEdit that adds a trailing comma", "state.json", home,
                     line=line, column=column)


class EmptyNewString(unittest.TestCase):
    """An Edit that only removes text. Its before-state cannot be rebuilt by putting new_string back, because an
    empty new_string matches everywhere. The check reads the removal from the file the call leaves."""

    def test_edit_removing_the_closing_fence_of_an_inbox_block_is_named(self):
        home = Home()
        before = HEAD_1 + "\n````\nowner: keep the closing fence\n````\n- fb-1138-1 [note] -> noted\n"
        write(home.inbox, before)
        # The closer alone is not a unique old_string; the item line under it makes it unique.
        old = "````\n- fb-1138-1 [note] -> noted\n"
        self.assertEqual(before.count(old), 1, "scope: old_string must occur once in the inbox")
        edit_on_disk(self, home.inbox, old, "")
        self.assertEqual(read_text(home.inbox).count("````"), 1, "scope: the closer is gone")
        codes, ctx = home.dispatch("Edit", {"file_path": home.inbox, "old_string": old, "new_string": ""})
        assert_named(self, codes, ctx, "an empty-new_string Edit that removes the closing fence",
                     home.sid + ".inbox.md", home, line=2)

    def test_edit_removing_a_plain_line_from_a_broken_file_is_silent(self):
        home = Home()
        path = os.path.join(home.work, "state.json")
        write(path, '{\n  "a": 1,,\n  "note": "drop me",\n  "b": 2\n}\n')
        old = '  "note": "drop me",\n'
        edit_on_disk(self, path, old, "")
        json_error(self, read_text(path))  # scope: still broken, the removal did not fix it
        codes, ctx = home.dispatch("Edit", {"file_path": path, "old_string": old, "new_string": ""})
        assert_silent(self, ctx, "an empty-new_string Edit that removes a plain line from a file already broken")
        line, column = json_error(self, read_text(path))
        codes, ctx = home.write_hook(path, read_text(path))
        assert_named(self, codes, ctx, "the same broken file written in a Write", "state.json", home,
                     line=line, column=column)

    def test_edit_removing_a_line_that_breaks_valid_json_is_named(self):
        home = Home()
        path = os.path.join(home.work, "state.json")
        write(path, OK_JSON)
        old = '  "b": 2\n'
        edit_on_disk(self, path, old, "")
        line, column = json_error(self, read_text(path))
        codes, ctx = home.dispatch("Edit", {"file_path": path, "old_string": old, "new_string": ""})
        assert_named(self, codes, ctx, "an empty-new_string Edit that leaves a trailing comma", "state.json", home,
                     line=line, column=column)


class RepeatedNewString(unittest.TestCase):
    """An Edit whose new_string occurs more than once. Each occurrence gives one candidate before-state. The
    fault is the call's only when every candidate was fine before it."""

    def test_edit_whose_new_string_repeats_is_named_when_one_place_was_valid(self):
        home = Home()
        path = os.path.join(home.work, "state.json")
        before = '{\n  "first": {"enabled": true},\n  "second": {"enabled": true}\n}\n'
        write(path, before)
        json.loads(before)
        old, new = '"enabled": true}\n}', '"enabled": true'
        self.assertEqual(before.count(new), 2, "scope: new_string must repeat in the file")
        edit_on_disk(self, path, old, new)
        line, column = json_error(self, read_text(path))
        codes, ctx = home.dispatch("Edit", {"file_path": path, "old_string": old, "new_string": new})
        assert_named(self, codes, ctx, "an Edit whose new_string repeats, where one place was valid",
                     "state.json", home, line=line, column=column)

    def test_edit_whose_new_string_repeats_is_silent_when_every_place_was_broken(self):
        home = Home()
        path = os.path.join(home.work, "state.json")
        before = '{\n  "version": 1,,\n  "first": {"enabled": true},\n  "second": {"enabled": true}\n}\n'
        write(path, before)
        json_error(self, before)  # scope: broken in a place no candidate touches
        old, new = '"enabled": true}\n}', '"enabled": true'
        self.assertEqual(before.count(new), 2, "scope: new_string must repeat in the file")
        edit_on_disk(self, path, old, new)
        after = read_text(path)
        json_error(self, after)  # scope: still broken after the edit
        codes, ctx = home.dispatch("Edit", {"file_path": path, "old_string": old, "new_string": new})
        assert_silent(self, ctx, "an Edit whose new_string repeats, on a file broken where no candidate fixes")
        line, column = json_error(self, after)
        codes, ctx = home.write_hook(path, after)
        assert_named(self, codes, ctx, "the same broken file written in a Write", "state.json", home,
                     line=line, column=column)


class EveryTool(unittest.TestCase):
    """Each of the five tools the check runs on is registered, and names a state file its call left broken."""

    def test_each_of_the_five_tools_names_a_broken_state_file(self):
        for tool in ("Bash", "PowerShell", "Write", "Edit", "MultiEdit"):
            with self.subTest(tool=tool):
                home = Home()
                path = os.path.join(home.work, "bad.json")
                command = "printf '%s' '{\"a\": 1,}' > bad.json"
                if tool == "Write":
                    codes, ctx = home.write_hook(path, '{"a": 1,}')
                elif tool == "Edit":
                    write(path, OK_JSON)
                    edit_on_disk(self, path, '"b": 2', '"b": 2,')
                    codes, ctx = home.dispatch("Edit", {"file_path": path, "old_string": '"b": 2',
                                                        "new_string": '"b": 2,'})
                elif tool == "MultiEdit":
                    write(path, OK_JSON)
                    edits = [{"old_string": '"b": 2', "new_string": '"b": 2,'}]
                    edit_on_disk(self, path, '"b": 2', '"b": 2,')
                    codes, ctx = home.dispatch("MultiEdit", {"file_path": path, "edits": edits})
                else:
                    # Bash and PowerShell name the file in a write position. The Bash call runs for real;
                    # the PowerShell call is judged on the file it left, which the test writes.
                    if tool == "Bash":
                        self.assertEqual(home.sh(command), 0, "scope: the Bash call must run")
                    else:
                        write(path, '{"a": 1,}\n')
                    codes, ctx = home.dispatch(tool, {"command": command})
                assert_named(self, codes, ctx, "a %s call that leaves bad.json broken" % tool, "bad.json", home)


class WriteAndDeleted(unittest.TestCase):
    """A Write judged as written, and a state file that was deleted."""

    def test_write_of_valid_json_is_silent_and_broken_json_is_named(self):
        home = Home()
        path = os.path.join(home.work, "state.json")
        codes, ctx = home.write_hook(path, OK_JSON)
        assert_silent(self, ctx, "a Write of valid JSON")
        line, column = json_error(self, '{"a": 1,}')
        codes, ctx = home.write_hook(path, '{"a": 1,}')
        assert_named(self, codes, ctx, "a Write of broken JSON", "state.json", home, line=line, column=column)

    @SHELL_ONLY
    def test_deleted_state_file_is_silent_and_a_broken_write_is_named(self):
        home = Home()
        settings = os.path.join(home.cfg, "settings.json")
        write(settings, '{"a": 1,}')
        command = "rm -f " + shlex.quote(settings)
        self.assertEqual(home.sh(command), 0, "scope: the rm must run")
        self.assertFalse(os.path.exists(settings), "scope: the rm must delete the file")
        codes, ctx = home.dispatch("Bash", {"command": command})
        assert_silent(self, ctx, "a Bash rm of a state file that was already broken")
        line, column = json_error(self, '{"a": 1,}')
        codes, ctx = home.write_hook(os.path.join(home.work, "other.json"), '{"a": 1,}')
        assert_named(self, codes, ctx, "a broken Write to another file", "other.json", home,
                     line=line, column=column)


class BashWrites(unittest.TestCase):
    """A Bash command judged by the file it writes, not the file it reads."""

    @SHELL_ONLY
    def test_cat_of_an_invalid_json_is_silent_and_an_append_to_it_is_named(self):
        home = Home()
        path = os.path.join(home.work, "bad.json")
        write(path, '{"a": 1,}\n')
        with self.assertRaises(json.JSONDecodeError):
            json.loads(read_text(path))
        self.assertEqual(home.sh("cat bad.json"), 0, "scope: the cat must run")
        codes, ctx = home.dispatch("Bash", {"command": "cat bad.json"})
        assert_silent(self, ctx, "a read of an invalid bad.json")
        self.assertEqual(home.sh("printf 'x' >> bad.json"), 0, "scope: the append must run")
        codes, ctx = home.dispatch("Bash", {"command": "printf 'x' >> bad.json"})
        assert_named(self, codes, ctx, "an append in a write position on the same file", "bad.json", home)

    @SHELL_ONLY
    def test_write_position_commands_name_the_file_they_leave_broken(self):
        commands = [
            "echo x > bad.json",
            "echo x >> bad.json",
            "printf 'x' | tee bad.json",
        ]
        for command in commands:
            with self.subTest(command=command):
                home = Home()
                path = os.path.join(home.work, "bad.json")
                write(path, '{"a": 1}\n')
                json.loads(read_text(path))
                self.assertEqual(home.sh(command), 0, "scope: the command must run")
                with self.assertRaises(json.JSONDecodeError):
                    json.loads(read_text(path))
                codes, ctx = home.dispatch("Bash", {"command": command})
                assert_named(self, codes, ctx, command, "bad.json", home)

    @GNU_SED_ONLY
    def test_sed_in_place_that_breaks_a_valid_json_is_named(self):
        home = Home()
        path = os.path.join(home.work, "bad.json")
        write(path, '{"a": 1}\n')
        json.loads(read_text(path))
        command = "sed -i 's/}$/,}/' bad.json"
        self.assertEqual(home.sh(command), 0, "scope: the sed must run")
        with self.assertRaises(json.JSONDecodeError):
            json.loads(read_text(path))
        codes, ctx = home.dispatch("Bash", {"command": command})
        assert_named(self, codes, ctx, "sed -i in a write position", "bad.json", home)

    @SHELL_ONLY
    def test_read_of_a_broken_state_file_is_silent_and_a_write_to_it_is_named(self):
        # A read changes nothing, so a read is not judged: an alarm on each read would repeat until the file is
        # fixed. The write twin keeps the named side for the same file.
        home = Home()
        settings = os.path.join(home.cfg, "settings.json")
        write(settings, '{"a": 1,}\n')
        json_error(self, read_text(settings))  # scope: broken
        self.assertEqual(home.sh("cat " + shlex.quote(settings)), 0, "scope: the cat must run")
        codes, ctx = home.dispatch("Bash", {"command": "cat " + shlex.quote(settings)})
        assert_silent(self, ctx, "a cat of a broken settings.json")
        command = "printf 'x' >> " + shlex.quote(settings)
        self.assertEqual(home.sh(command), 0, "scope: the append must run")
        codes, ctx = home.dispatch("Bash", {"command": command})
        assert_named(self, codes, ctx, "an append to the same settings.json", "settings.json", home)

    @SHELL_ONLY
    def test_read_of_an_inbox_with_a_fence_open_is_silent_and_a_write_to_it_is_named(self):
        home = Home()
        write(home.inbox, HEAD_1 + "\n````\nowner text, the fence is still open\n")
        self.assertEqual(home.sh("cat " + shlex.quote(home.inbox)), 0, "scope: the cat must run")
        codes, ctx = home.dispatch("Bash", {"command": "cat " + shlex.quote(home.inbox)})
        assert_silent(self, ctx, "a cat of an inbox with a fence left open")
        command = "printf 'x\\n' >> " + shlex.quote(home.inbox)
        self.assertEqual(home.sh(command), 0, "scope: the append must run")
        codes, ctx = home.dispatch("Bash", {"command": command})
        assert_named(self, codes, ctx, "an append to the same inbox", home.sid + ".inbox.md", home, line=2)

    @SHELL_ONLY
    def test_a_quoted_gt_is_not_a_redirect_and_a_quoted_hash_is_not_a_comment(self):
        home = Home()
        path = os.path.join(home.work, "bad.json")
        write(path, '{"a": 1,}\n')
        json_error(self, read_text(path))  # scope: broken
        codes, ctx = home.dispatch("Bash", {"command": "grep -c '>' bad.json"})
        assert_silent(self, ctx, "a grep whose pattern is a quoted lone >")
        command = 'echo "# note" >> bad.json'
        self.assertEqual(home.sh(command), 0, "scope: the append must run")
        codes, ctx = home.dispatch("Bash", {"command": command})
        assert_named(self, codes, ctx, "an append whose text holds a quoted #", "bad.json", home)


class NoStateFile(unittest.TestCase):
    """A call that names no state file is silent, even while a state file in the folder is broken."""

    def test_a_call_naming_no_state_file_is_silent_while_a_state_file_is_broken(self):
        home = Home()
        write(home.inbox, HEAD_1 + "\n````\nowner text, the fence is still open\n")
        code_path = os.path.join(home.work, "tool.py")
        write(code_path, "x = 1\n")
        edit = {"file_path": code_path, "old_string": "x = 1", "new_string": "x = 2"}
        edit_on_disk(self, code_path, edit["old_string"], edit["new_string"])
        codes, ctx = home.dispatch("Edit", edit)
        assert_silent(self, ctx, "an Edit of a .py file while an inbox is broken")
        codes, ctx = home.dispatch("Bash", {"command": "ls -la"})
        assert_silent(self, ctx, "a Bash ls while an inbox is broken")
        command = "printf 'x\\n' >> " + shlex.quote(home.inbox)
        self.assertEqual(home.sh(command), 0, "scope: the append must run")
        codes, ctx = home.dispatch("Bash", {"command": command})
        assert_named(self, codes, ctx, "the same call naming the broken inbox", home.sid + ".inbox.md", home, line=2)


# The hook's own opens, logged by a sitecustomize that the shim's PYTHONPATH puts first. One line per open().
OPEN_LOGGER = '''import builtins
import os

_open = builtins.open


def _logged_open(file, *args, **kwargs):
    log = os.environ.get("STATE_OPENS_LOG")
    if log and isinstance(file, (str, bytes, os.PathLike)):
        with _open(log, "a", encoding="utf-8") as handle:
            handle.write(os.fsdecode(file) + "\\n")
    return _open(file, *args, **kwargs)


builtins.open = _logged_open
'''
FilterRun = collections.namedtuple("FilterRun", "starts before after opened")


class HookRunner:
    """The one runner of the state check's registered command: a recording shim per python, and a log of each open
    the hook makes. A test class mixes it in with unittest.TestCase."""

    @staticmethod
    def state_command():
        found = [c for c in hook_commands("Bash") if "state_parse_check" in c]
        return found[0] if found else None

    def run_hook(self, home, tool, tool_input, response):
        """Run the state check's registered command with a recording shim first on PATH, and a sitecustomize that
        logs each file the hook opens. Return a FilterRun: the starts, the files before the call and after it (each
        as its path and sha256), and the paths the hook opened."""
        # On an old commit no command is registered. Running none starts no Python, so the cost asserts give the red.
        command = self.state_command() or "exit 0"
        shims = tempfile.mkdtemp(prefix="shim-", dir=RUN)
        log = os.path.join(shims, "starts.log")
        opens = os.path.join(shims, "opens.log")
        write(os.path.join(shims, "sitecustomize.py"), OPEN_LOGGER)
        for name in ("python3", "python"):
            shim = os.path.join(shims, name)
            write(shim, '#!/bin/sh\necho start >> %s\nexec %s "$@"\n' % (shlex.quote(log), shlex.quote(sys.executable)))
            os.chmod(shim, 0o755)
        # Compact JSON: the pre-filter cuts the input at the literal `"tool_input":` and `"tool_response":`.
        compact = json.dumps({"session_id": home.sid, "cwd": home.work, "tool_name": tool, "tool_input": tool_input,
                              "tool_response": response}, separators=(",", ":"))
        env = dict(os.environ, CLAUDE_CONFIG_DIR=home.cfg, HOME=home.root, PYTHONDONTWRITEBYTECODE="1",
                   PATH=shims + os.pathsep + os.environ.get("PATH", ""), STATE_OPENS_LOG=opens,
                   PYTHONPATH=os.pathsep.join(filter(None, [shims, os.environ.get("PYTHONPATH")])))

        def listing():
            return sorted((os.path.join(d, n), hashlib.sha256(read_bytes(os.path.join(d, n))).hexdigest())
                          for d, _, names in os.walk(home.root) for n in names)

        before = listing()
        done = subprocess.run([test_wrappers.SH, "-c", command], input=compact, capture_output=True, text=True,
                              env=env, cwd=home.work, timeout=60)
        self.assertEqual(done.returncode, 0, "the filter must never block: %r" % done.stderr[:160])
        starts = len(read_text(log).splitlines()) if os.path.exists(log) else 0
        opened = read_text(opens).splitlines() if os.path.exists(opens) else []
        return FilterRun(starts, before, listing(), opened)

class PreFilterCost(HookRunner, unittest.TestCase):
    """The cost the decision states (docs/decisions/state-file-parse-check.md, Cost): a call that names neither
    .json nor the handoff folder starts no Python, a call that names one starts one, and the hook writes no file."""

    def run_filter(self, home, tool, tool_input, response):
        """(starts, files before the call, files after it) from run_hook."""
        run = self.run_hook(home, tool, tool_input, response)
        return run.starts, run.before, run.after

    @SHELL_ONLY
    def test_a_call_naming_no_state_file_starts_no_python_and_a_json_call_starts_one(self):
        home = Home()
        # The response names a .json, which the filter must not read: it cuts the input at tool_response.
        starts, _, _ = self.run_filter(home, "Bash", {"command": "ls -la"}, {"stdout": "bad.json\n", "stderr": ""})
        self.assertEqual(starts, 0, "a call that names no .json and no handoffs started Python")
        path = os.path.join(home.work, "bad.json")
        write(path, '{"a": 1,}\n')
        starts, _, _ = self.run_filter(home, "Write", {"file_path": path, "content": '{"a": 1,}\n'}, {})
        self.assertEqual(starts, 1, "a call that names a .json must start one Python")
        starts, _, _ = self.run_filter(home, "Write", {"file_path": home.handoff, "content": "x"}, {})
        self.assertEqual(starts, 1, "a call that names the handoff folder must start one Python")

    @SHELL_ONLY
    def test_the_hook_writes_no_file_when_it_judges_a_broken_state_file(self):
        home = Home()
        path = os.path.join(home.work, "bad.json")
        write(path, '{"a": 1,}\n')
        write(home.inbox, HEAD_1 + "\n````\nopen\n")
        for name, target in (("bad.json", path), ("the inbox", home.inbox)):
            with self.subTest(file=name):
                starts, before, after = self.run_filter(home, "Write", {"file_path": target, "content": "x"}, {})
                self.assertEqual(starts, 1, "scope: the hook must run on %s" % name)
                self.assertEqual(before, after, "the hook wrote or changed a file while judging %s" % name)

    @SHELL_ONLY
    def test_a_call_naming_25_json_files_reads_at_most_20_and_each_once(self):
        home = Home()
        names = ["f%02d.json" % n for n in range(1, 26)]
        for name in names:
            write(os.path.join(home.work, name), '{"a": 1,}\n')
        # The command names the 25 files and is not run, so the files stay as written.
        run = self.run_hook(home, "Bash", {"command": "tee " + " ".join(names)}, {"stdout": "", "stderr": ""})
        self.assertEqual(run.starts, 1, "scope: the hook must run on the call")
        reads = collections.Counter(os.path.basename(p) for p in run.opened if os.path.basename(p) in names)
        self.assertGreater(sum(reads.values()), 0, "scope: the hook must read at least one of the 25 files")
        self.assertLessEqual(sum(reads.values()), 20,
                             "a call naming 25 .json files read %d of them" % sum(reads.values()))
        for name in names:
            self.assertLessEqual(reads[name], 1, "%s was read %d times in one call" % (name, reads[name]))


class ScannerTraps(unittest.TestCase):
    """Handoff text and JSON text that a fence scan must not misread."""

    def test_handoff_traps_are_silent_and_an_open_fence_is_named(self):
        for label, trap in TRAPS:
            with self.subTest(trap=label):
                home = Home()
                text = handoff_text(trap)
                codes, ctx = home.write_hook(home.handoff, text)
                assert_silent(self, ctx, "the handoff with %s" % label)
                broken = text + "```\nopen at the end\n"
                codes, ctx = home.write_hook(home.handoff, broken)
                assert_named(self, codes, ctx, "the same handoff with a fence left open", home.sid + ".md", home,
                             line=text.count("\n") + 1)

    def test_a_handoff_outside_the_handoff_folder_is_not_judged(self):
        home = Home()
        text = handoff_text("```\nopen\n")
        fence_line = handoff_text().count("\n") + 1
        codes, ctx = home.write_hook(os.path.join(home.work, "notes.md"), text)
        assert_silent(self, ctx, "a .md outside the handoff folder with a fence left open")
        codes, ctx = home.write_hook(home.handoff, text)
        assert_named(self, codes, ctx, "the same .md in the handoff folder", home.sid + ".md", home,
                     line=fence_line)

    def test_longer_outer_fence_left_open_around_a_shorter_inner_is_named(self):
        # The inner ``` does not close a four-backtick fence: only a run at least as long closes it.
        closed = handoff_text("````\n```\ninner text\n```\n````\n")
        home = Home()
        codes, ctx = home.write_hook(home.handoff, closed)
        assert_silent(self, ctx, "the handoff with a longer outer fence closed after a shorter inner one")
        left_open = handoff_text("````\n```\ninner text\n```\n")
        fence_line = handoff_text().count("\n") + 1
        codes, ctx = home.write_hook(home.handoff, left_open)
        assert_named(self, codes, ctx, "a four-backtick outer fence left open around a three-backtick inner one",
                     home.sid + ".md", home, line=fence_line)

    def test_json_string_holding_a_fence_is_silent_and_a_trailing_comma_is_named(self):
        home = Home()
        path = os.path.join(home.work, "body.json")
        codes, ctx = home.write_hook(path, JSON_TRAP_OK)
        assert_silent(self, ctx, "valid JSON that holds a fence and a comment-like string")
        line, column = json_error(self, JSON_TRAP_BAD)
        codes, ctx = home.write_hook(path, JSON_TRAP_BAD)
        assert_named(self, codes, ctx, "the same JSON with a trailing comma", "body.json", home,
                     line=line, column=column)


class EditHandoffFence(unittest.TestCase):
    """An Edit on a handoff .md that an open fence already broke. The Edit did not open the fence, so it stays
    silent. The same text written whole is named, so the silent case has its named twin."""

    def test_edit_on_a_handoff_already_broken_by_an_open_fence_is_silent(self):
        home = Home()
        before = handoff_text("```\nopen\n")
        write(home.handoff, before)
        old, new = "open\n", "still open\n"
        self.assertEqual(before.count(old), 1, "scope: old_string must occur once in the handoff")
        edit_on_disk(self, home.handoff, old, new)
        after = read_text(home.handoff)
        self.assertIn("```\nstill open\n", after, "scope: the fence is still open after the edit")
        codes, ctx = home.dispatch("Edit", {"file_path": home.handoff, "old_string": old, "new_string": new})
        assert_silent(self, ctx, "an Edit on a handoff that an open fence already broke")
        fence_line = handoff_text().count("\n") + 1
        codes, ctx = home.write_hook(home.handoff, after)
        assert_named(self, codes, ctx, "the same open fence written in a Write", home.sid + ".md", home,
                     line=fence_line)


class LostSection(unittest.TestCase):
    """An Edit that drops an inbox block header, and a handoff with no premises heading."""

    def test_edit_that_keeps_every_header_is_silent_and_dropping_one_is_named(self):
        home = Home()
        codes, ctx = home.write_hook(home.inbox, INBOX_TWO)
        assert_silent(self, ctx, "the intact two-block inbox")
        edit_on_disk(self, home.inbox, "first owner message", "first owner message, edited")
        codes, ctx = home.dispatch("Edit", {"file_path": home.inbox, "old_string": "first owner message",
                                            "new_string": "first owner message, edited"})
        assert_silent(self, ctx, "an Edit that changes text and keeps both headers")
        edit_on_disk(self, home.inbox, HEAD_2, "### Notes")
        codes, ctx = home.dispatch("Edit", {"file_path": home.inbox, "old_string": HEAD_2, "new_string": "### Notes"})
        assert_named(self, codes, ctx, "an Edit that turns the second block header into plain text",
                     home.sid + ".inbox.md", home, words=("11:40",))

    def test_multiedit_that_drops_an_inbox_header_is_named(self):
        home = Home()
        write(home.inbox, INBOX_TWO)
        edits = [{"old_string": HEAD_2, "new_string": "### Notes"}]
        edit_on_disk(self, home.inbox, HEAD_2, "### Notes")
        codes, ctx = home.dispatch("MultiEdit", {"file_path": home.inbox, "edits": edits})
        assert_named(self, codes, ctx, "a MultiEdit that drops the second block header",
                     home.sid + ".inbox.md", home, words=("11:40",))

    def test_handoff_without_working_premises_is_named(self):
        home = Home()
        codes, ctx = home.write_hook(home.handoff, handoff_text("## Next\n\n- one step\n"))
        assert_silent(self, ctx, "a handoff with its Working premises heading")
        codes, ctx = home.write_hook(home.handoff, GOAL + "## Next\n\n- one step\n")
        assert_named(self, codes, ctx, "a handoff with no Working premises heading", home.sid + ".md", home,
                     words=("Working premises",))


class EmptyAndFullStates(unittest.TestCase):
    """The empty and the full-size states of each kind of file."""

    def test_empty_inbox_is_silent_and_an_open_fence_in_it_is_named(self):
        home = Home()
        codes, ctx = home.write_hook(home.inbox, "")
        assert_silent(self, ctx, "an empty inbox")
        codes, ctx = home.write_hook(home.inbox, HEAD_1 + "\n````\nopen\n")
        assert_named(self, codes, ctx, "an inbox whose only fence is left open", home.sid + ".inbox.md", home,
                     line=2)

    def test_full_size_inbox_is_silent_and_a_lost_closer_at_the_end_is_named(self):
        home = Home()
        intact, _ = build_inbox(300)
        codes, ctx = home.write_hook(home.inbox, intact)
        assert_silent(self, ctx, "a 300-block inbox with every fence closed")
        broken, opener = build_inbox(300, drop_last_closer=True)
        codes, ctx = home.write_hook(home.inbox, broken)
        assert_named(self, codes, ctx, "a 300-block inbox whose last closer is lost", home.sid + ".inbox.md", home,
                     line=opener)

    def test_empty_json_is_named_at_line_1_column_1(self):
        home = Home()
        line, column = json_error(self, "")
        codes, ctx = home.write_hook(os.path.join(home.work, "empty.json"), "")
        assert_named(self, codes, ctx, "an empty *.json", "empty.json", home, line=line, column=column)


class CdAndHeredoc(unittest.TestCase):
    """A sed -i that runs after a cd, and a heredoc body whose lone apostrophe hides the append from the check."""

    @SHELL_ONLY
    def test_sed_after_cd_into_the_handoff_folder_that_deletes_the_closer_is_named(self):
        home = Home()
        write(home.inbox, HEAD_1 + "\n````\nowner: keep the closing fence\n````\n")
        command = "cd %s && sed -i '$d' %s" % (shlex.quote(home.handoffs), shlex.quote(os.path.basename(home.inbox)))
        self.assertEqual(home.sh(command), 0, "scope: the cd and the sed must run")
        self.assertNotEqual(read_text(home.inbox).splitlines()[-1], "````", "scope: the sed must delete the closer")
        codes, ctx = home.dispatch("Bash", {"command": command})
        assert_named(self, codes, ctx, "a sed -i after a cd into the handoff folder", home.sid + ".inbox.md", home,
                     line=2)

    @SHELL_ONLY
    def test_heredoc_body_with_a_lone_apostrophe_that_opens_a_fence_is_named(self):
        home = Home()
        write(home.inbox, HEAD_1 + "\n")
        command = "cat >> %s <<'EOF'\n````\nit's\nEOF\n" % shlex.quote(home.inbox)
        self.assertEqual(home.sh(command), 0, "scope: the heredoc append must run")
        self.assertEqual(read_text(home.inbox), HEAD_1 + "\n````\nit's\n", "scope: the body must land in the inbox")
        codes, ctx = home.dispatch("Bash", {"command": command})
        assert_named(self, codes, ctx, "a heredoc body with a lone apostrophe that opens a fence",
                     home.sid + ".inbox.md", home, line=2)

    @SHELL_ONLY
    def test_the_same_heredoc_without_the_apostrophe_is_named_control(self):
        home = Home()
        write(home.inbox, HEAD_1 + "\n")
        command = "cat >> %s <<'EOF'\n````\nits\nEOF\n" % shlex.quote(home.inbox)
        self.assertEqual(home.sh(command), 0, "scope: the heredoc append must run")
        self.assertEqual(read_text(home.inbox), HEAD_1 + "\n````\nits\n", "scope: the body must land in the inbox")
        codes, ctx = home.dispatch("Bash", {"command": command})
        assert_named(self, codes, ctx, "the same heredoc without the apostrophe", home.sid + ".inbox.md", home,
                     line=2)


    @SHELL_ONLY
    def test_heredoc_body_that_names_a_json_write_but_writes_nothing_is_silent(self):
        home = Home()
        path = os.path.join(home.work, "bad.json")
        write(path, '{"a": 1,}\n')
        json_error(self, read_text(path))  # scope: broken before the call
        command = "cat <<EOF\necho x > bad.json\nEOF\n"
        self.assertEqual(home.sh(command), 0, "scope: the cat must run")
        self.assertEqual(read_text(path), '{"a": 1,}\n', "scope: the call must leave bad.json as it was")
        codes, ctx = home.dispatch("Bash", {"command": command})
        assert_silent(self, ctx, "a heredoc body holding > bad.json, where no write reaches the file")
        # The twin: the same redirect as a real write is named, so the silence above is not a dead hook.
        twin = "printf 'x' >> bad.json"
        self.assertEqual(home.sh(twin), 0, "scope: the append must run")
        line, column = json_error(self, read_text(path))
        codes, ctx = home.dispatch("Bash", {"command": twin})
        assert_named(self, codes, ctx, "the same redirect as a real append", "bad.json", home, line=line, column=column)


class WriteForms(unittest.TestCase):
    """Each write form that leaves an inbox with its closing fence lost is named at the open fence, line 2. A shell
    form runs for real. Each PowerShell form is judged on the state the test leaves, as EveryTool does."""

    INTACT = HEAD_1 + "\n````\nowner: keep the closing fence\n````\n"
    LOST = HEAD_1 + "\n````\nowner: keep the closing fence\n"

    def named_when_lost(self, home, tool, command, why):
        self.assertEqual(read_text(home.inbox), self.LOST, "scope: the call must leave the closer lost")
        codes, ctx = home.dispatch(tool, {"command": command})
        assert_named(self, codes, ctx, why, home.sid + ".inbox.md", home, line=2)

    @SHELL_ONLY
    def test_head_to_a_temp_file_then_mv_that_drops_the_closer_is_named(self):
        home = Home()
        q = shlex.quote
        write(home.inbox, self.INTACT)
        tmp = home.inbox + ".tmp"
        command = "head -n -1 %s > %s && mv %s %s" % (q(home.inbox), q(tmp), q(tmp), q(home.inbox))
        self.assertEqual(home.sh(command), 0, "scope: the head and mv must run")
        self.named_when_lost(home, "Bash", command, "head -n -1 into a temp file, then mv over the inbox")

    @SHELL_ONLY
    def test_mv_of_a_copy_that_drops_the_closer_is_named(self):
        home = Home()
        q = shlex.quote
        write(home.inbox, self.INTACT)
        source = home.inbox + ".new"
        write(source, self.LOST)
        command = "mv %s %s" % (q(source), q(home.inbox))
        self.assertEqual(home.sh(command), 0, "scope: the mv must run")
        self.named_when_lost(home, "Bash", command, "mv of a copy that drops the closer, over the inbox")

    @SHELL_ONLY
    def test_cp_of_a_copy_that_drops_the_closer_is_named(self):
        home = Home()
        q = shlex.quote
        write(home.inbox, self.INTACT)
        source = os.path.join(home.work, "lost-copy.txt")
        write(source, self.LOST)
        command = "cp %s %s" % (q(source), q(home.inbox))
        self.assertEqual(home.sh(command), 0, "scope: the cp must run")
        self.named_when_lost(home, "Bash", command, "cp of a copy that drops the closer, over the inbox")

    @SHELL_ONLY
    def test_perl_in_place_that_drops_the_last_line_is_named(self):
        home = Home()
        write(home.inbox, self.INTACT)
        command = "perl -i -pe '$_ = \"\" if eof' %s" % shlex.quote(home.inbox)
        self.assertEqual(home.sh(command), 0, "scope: the perl must run")
        self.named_when_lost(home, "Bash", command, "perl -i -pe that drops the closer")

    @GNU_SED_ONLY
    def test_truncate_that_drops_the_closer_is_named(self):
        # truncate -s -N is GNU coreutils; BSD truncate has no -s, so this runs where GNU sed does.
        home = Home()
        write(home.inbox, self.INTACT)
        self.assertEqual(self.INTACT[-5:], "````\n", "scope: the last five bytes are the closer")
        command = "truncate -s -5 %s" % shlex.quote(home.inbox)
        self.assertEqual(home.sh(command), 0, "scope: the truncate must run")
        self.named_when_lost(home, "Bash", command, "truncate -s -5 that drops the closer")

    @SHELL_ONLY
    def test_powershell_set_content_that_drops_the_closer_is_named(self):
        home = Home()
        write(home.inbox, self.LOST)
        command = 'Set-Content -Path "%s" -Value "owner: keep the closing fence"' % home.inbox
        self.named_when_lost(home, "PowerShell", command, "PowerShell Set-Content that drops the closer")

    @SHELL_ONLY
    def test_powershell_out_file_that_drops_the_closer_is_named(self):
        home = Home()
        write(home.inbox, self.LOST)
        command = 'Out-File -FilePath "%s"' % home.inbox
        self.named_when_lost(home, "PowerShell", command, "PowerShell Out-File that drops the closer")


class NoFalseAlarm(unittest.TestCase):
    """Text that a strict JSON reader rejects, but the file is fine as it stands, is silent. A broken state .json
    stays named."""

    @SHELL_ONLY
    def test_tsconfig_json_with_line_comments_is_silent(self):
        home = Home()
        text = '{\n  // the compiler options\n  "compilerOptions": {}\n}\n'
        with self.assertRaises(json.JSONDecodeError):
            json.loads(text)  # scope: a strict reader rejects the text
        codes, ctx = home.write_hook(os.path.join(home.work, "tsconfig.json"), text)
        assert_silent(self, ctx, "a tsconfig.json with // comments")

    @SHELL_ONLY
    def test_json_file_with_a_utf8_bom_is_silent(self):
        home = Home()
        path = os.path.join(home.work, "bom.json")
        codes, ctx = home.write_hook(path, "﻿" + OK_JSON)
        self.assertEqual(read_bytes(path)[:3], b"\xef\xbb\xbf", "scope: the file starts with a UTF-8 BOM")
        with self.assertRaises(json.JSONDecodeError):
            json.loads(read_text(path))  # scope: a strict reader rejects the BOM
        assert_silent(self, ctx, "a valid .json with a UTF-8 byte order mark")

    @SHELL_ONLY
    def test_background_redirect_that_leaves_an_empty_json_is_silent(self):
        home = Home()
        path = os.path.join(home.work, "bg.json")
        write(path, "")
        self.assertEqual(read_text(path), "", "scope: the file is still empty when the hook runs")
        codes, ctx = home.dispatch("Bash", {"command": "slowtool > bg.json &"})
        assert_silent(self, ctx, "a background redirect whose json is still empty")

    @SHELL_ONLY
    def test_foreground_redirect_that_leaves_an_empty_json_is_named_control(self):
        home = Home()
        write(os.path.join(home.work, "bg.json"), "")
        line, column = json_error(self, "")
        codes, ctx = home.dispatch("Bash", {"command": "slowtool > bg.json"})
        assert_named(self, codes, ctx, "a foreground redirect that leaves the same empty json", "bg.json", home,
                     line=line, column=column)

    @SHELL_ONLY
    def test_a_genuinely_broken_state_json_is_still_named_control(self):
        home = Home()
        broken = '{\n  "a": 1,,\n  "b": 2\n}\n'
        line, column = json_error(self, broken)
        codes, ctx = home.write_hook(os.path.join(home.work, "state.json"), broken)
        assert_named(self, codes, ctx, "a state .json with a doubled comma", "state.json", home,
                     line=line, column=column)


class PremisesReadCost(HookRunner, unittest.TestCase):
    """An Edit whose new_string occurs 40 times in a handoff. Each place is one candidate before-state, and each is
    judged. The premises prompt must still be read at most once in the call, and the handoff once."""

    def repeated_edit(self):
        home = Home()
        write(home.handoff, handoff_text("## Next\n\n" + "- step\n" * 39 + "- old\n"))
        edit_on_disk(self, home.handoff, "- old\n", "- step\n")
        self.assertEqual(read_text(home.handoff).count("- step\n"), 40, "scope: new_string must repeat 40 times")
        run = self.run_hook(home, "Edit", {"file_path": home.handoff, "old_string": "- old\n", "new_string": "- step\n"},
                            {"stdout": "", "stderr": ""})
        return home, run

    @SHELL_ONLY
    def test_repeated_new_string_reads_the_premises_prompt_at_most_once(self):
        home, run = self.repeated_edit()
        self.assertEqual(run.starts, 1, "scope: the hook must run on the Edit")
        prompt = sum(os.path.basename(p) == "precompact_handoff_prompt.md" for p in run.opened)
        self.assertGreaterEqual(prompt, 1, "scope: the premises prompt must be read")
        self.assertLessEqual(prompt, 1, "the premises prompt was opened %d times in one Edit" % prompt)

    @SHELL_ONLY
    def test_repeated_new_string_reads_the_handoff_once(self):
        home, run = self.repeated_edit()
        self.assertEqual(run.starts, 1, "scope: the hook must run on the Edit")
        handoff = sum(os.path.basename(p) == os.path.basename(home.handoff) for p in run.opened)
        self.assertGreaterEqual(handoff, 1, "scope: the handoff must be read")
        self.assertLessEqual(handoff, 1, "the handoff was opened %d times in one Edit" % handoff)


class InPlaceForms(unittest.TestCase):
    """An in-place write that leaves a state .json broken, by the sed and perl forms with a backup suffix. The sed -i,
    sed -ni and BSD `sed -i ''` forms are controls: they already name the file."""

    BROKEN = '{"a": 1,}\n'
    REWRITTEN = '{"b": 1,}\n'  # the same break, after s/a/b/

    def assert_named_after(self, home, path, command, why):
        line, column = json_error(self, read_text(path))
        codes, ctx = home.dispatch("Bash", {"command": command})
        assert_named(self, codes, ctx, why, os.path.basename(path), home, line=line, column=column)

    @SHELL_ONLY
    def test_sed_with_a_backup_suffix_that_leaves_a_json_broken_is_named(self):
        home = Home()
        path = os.path.join(home.work, "bad.json")
        write(path, self.BROKEN)
        command = "sed -i.bak s/a/b/ bad.json"
        self.assertEqual(home.sh(command), 0, "scope: the sed must run")
        self.assertEqual(read_text(path), self.REWRITTEN, "scope: the sed must rewrite bad.json")
        self.assert_named_after(home, path, command, "sed -i.bak, the suffix form, that leaves a json broken")

    @SHELL_ONLY
    def test_sed_with_a_backup_suffix_after_cd_that_leaves_a_json_broken_is_named(self):
        home = Home()
        path = os.path.join(home.work, "sub", "bad.json")
        write(path, self.BROKEN)
        command = "cd sub && sed -i.bak s/a/b/ bad.json"
        self.assertEqual(home.sh(command), 0, "scope: the cd and the sed must run")
        self.assertEqual(read_text(path), self.REWRITTEN, "scope: the sed must rewrite sub/bad.json")
        self.assert_named_after(home, path, command, "cd sub, then sed -i.bak, that leaves a json broken")

    @SHELL_ONLY
    def test_perl_with_a_backup_suffix_that_leaves_a_json_broken_is_named(self):
        home = Home()
        path = os.path.join(home.work, "bad.json")
        write(path, self.BROKEN)
        command = "perl -pi.bak -e 's/a/b/' bad.json"
        self.assertEqual(home.sh(command), 0, "scope: the perl must run")
        self.assertEqual(read_text(path), self.REWRITTEN, "scope: the perl must rewrite bad.json")
        self.assert_named_after(home, path, command, "perl -pi.bak, the suffix form, that leaves a json broken")

    @SHELL_ONLY
    def test_sed_dash_i_that_leaves_a_json_broken_is_named_control(self):
        home = Home()
        path = os.path.join(home.work, "bad.json")
        write(path, self.BROKEN)
        command = "sed -i s/a/b/ bad.json"
        self.assertEqual(home.sh(command), 0, "scope: the sed must run")
        self.assertEqual(read_text(path), self.REWRITTEN, "scope: the sed must rewrite bad.json")
        self.assert_named_after(home, path, command, "sed -i, the form that already names the file")

    @SHELL_ONLY
    def test_sed_dash_ni_that_leaves_a_json_broken_is_named_control(self):
        home = Home()
        path = os.path.join(home.work, "bad.json")
        write(path, self.BROKEN)
        command = "sed -ni 's/a/b/p' bad.json"
        self.assertEqual(home.sh(command), 0, "scope: the sed must run")
        self.assertEqual(read_text(path), self.REWRITTEN, "scope: the sed must rewrite bad.json")
        self.assert_named_after(home, path, command, "sed -ni, the combined flags, that leaves a json broken")

    @SHELL_ONLY
    def test_bsd_sed_dash_i_with_an_empty_suffix_that_leaves_a_json_broken_is_named_control(self):
        # BSD sed reads the '' after -i as the empty suffix. GNU sed would read it as the script, so this state is
        # written as the BSD sed leaves it, and the call is judged on that state.
        home = Home()
        path = os.path.join(home.work, "bad.json")
        write(path, self.REWRITTEN)
        self.assert_named_after(home, path, "sed -i '' 's/a/b/' bad.json",
                                "sed -i '' with the BSD empty suffix, that leaves a json broken")


    @SHELL_ONLY
    def test_sed_dash_n_dash_e_with_dash_i_only_in_the_script_text_is_silent(self):
        home = Home()
        path = os.path.join(home.work, "bad.json")
        write(path, self.BROKEN)
        command = "sed -n -e 's/x/-i/' bad.json"
        self.assertEqual(home.sh(command), 0, "scope: the sed must run")
        self.assertEqual(read_text(path), self.BROKEN, "scope: the sed must write nothing to bad.json")
        codes, ctx = home.dispatch("Bash", {"command": command})
        assert_silent(self, ctx, "sed -n -e with -i only in the script text, which writes nothing")

    @SHELL_ONLY
    def test_sed_dash_e_whose_script_word_is_dash_i_is_silent(self):
        # -e takes the next word as its script, so this -i is the script and the file is bad.json. The word after -e
        # is skipped only when the skip is set, so this case is the one that tells a skipped script from a flag.
        home = Home()
        path = os.path.join(home.work, "bad.json")
        write(path, self.BROKEN)
        command = "sed -n -e -i bad.json"
        home.sh(command)  # sed rejects the script and writes nothing
        self.assertEqual(read_text(path), self.BROKEN, "scope: the sed must write nothing to bad.json")
        codes, ctx = home.dispatch("Bash", {"command": command})
        assert_silent(self, ctx, "sed -n -e -i, where -i is the script that -e takes")

    @SHELL_ONLY
    def test_sed_double_dash_then_dash_i_is_an_operand_and_silent(self):
        home = Home()
        path = os.path.join(home.work, "bad.json")
        write(path, self.BROKEN)
        command = "sed p -- -i bad.json"
        home.sh(command)  # sed reads the missing file -i, prints bad.json, and writes nothing
        self.assertEqual(read_text(path), self.BROKEN, "scope: the sed must write nothing to bad.json")
        codes, ctx = home.dispatch("Bash", {"command": command})
        assert_silent(self, ctx, "sed p -- -i, where -i after -- is an operand, not a flag")

    @SHELL_ONLY
    def test_sed_dash_i_before_bad_json_names_control(self):
        # The state the call leaves is written, not run: a sed -i with no script leaves bad.json as the script.
        home = Home()
        path = os.path.join(home.work, "bad.json")
        write(path, self.BROKEN)
        self.assert_named_after(home, path, "sed -i bad.json", "sed -i bad.json, the flag that names the file")


class FenceHelperPins(unittest.TestCase):
    """feedback_guard.unfenced() and is_grant() keep their main results. The handoff check reads the same fence
    rule through a shared loop (decision state-file-parse-check), so these pins sit beside the check's cases.
    They pass on main by design: they are the control that the shared loop must keep."""

    @staticmethod
    def fg():
        import feedback_guard  # the one home of the fence loops, loaded from hooks/
        return feedback_guard

    def test_unfenced_hides_the_text_of_a_four_space_indented_fence(self):
        text = "kept before\n    ```\nhidden grant text\n    ```\nkept after"
        self.assertEqual(self.fg().unfenced(text), "kept before\nkept after",
                         "unfenced() kept the text of a four-space-indented fence")

    def test_unfenced_hides_the_text_of_a_tab_indented_fence(self):
        text = "kept before\n\t```\nhidden grant text\n\t```\nkept after"
        self.assertEqual(self.fg().unfenced(text), "kept before\nkept after",
                         "unfenced() kept the text of a tab-indented fence")

    def test_unfenced_hides_the_text_of_a_fence_indented_three_spaces(self):
        text = "kept before\n   ```\nhidden grant text\n   ```\nkept after"
        self.assertEqual(self.fg().unfenced(text), "kept before\nkept after",
                         "unfenced() kept the text of a three-space-indented fence")

    def test_unfenced_runs_an_unclosed_fence_to_the_end(self):
        self.assertEqual(self.fg().unfenced("kept\n```\nhidden"), "kept",
                         "unfenced() kept text after an unclosed fence")

    def test_is_grant_ignores_grant_words_inside_a_four_space_fence(self):
        text = "    ```\nI approved the merge\n    ```"
        self.assertFalse(self.fg().is_grant(text), "is_grant() read a grant inside a four-space fence")

    def test_is_grant_ignores_grant_words_inside_a_tab_fence(self):
        text = "\t```\nI approved the merge\n\t```"
        self.assertFalse(self.fg().is_grant(text), "is_grant() read a grant inside a tab-indented fence")

    def test_is_grant_still_reads_a_grant_in_plain_text_and_ignores_a_fenced_one(self):
        self.assertTrue(self.fg().is_grant("I approved the merge"), "is_grant() missed a plain grant")
        self.assertFalse(self.fg().is_grant("```\nI approved the merge\n```"),
                         "is_grant() read a grant inside a plain fence")


if __name__ == "__main__":
    unittest.main()
