#!/usr/bin/env python3
"""Cases for hooks/state_parse_check.py (decision state-file-parse-check). Standard library only.

Run it from the repository root:

    python3 hooks/test_state_parse_check.py

WHAT IT PROVES. A PostToolUse hook names a state file that a call left unreadable: a *.json that
json.loads rejects, an inbox or handoff .md with a fence left open, an Edit that drops an inbox block
header, or a handoff with no `## Working premises` heading. It never blocks and never changes the file.
It stays silent for a file that was already broken before an Edit, for a deleted file, for a .md outside
the handoff folder, and for the scanner traps (fences inside JSON strings, mid-line backticks, indented
fences, tilde blocks, a lone apostrophe). A shell pre-filter in settings.json starts no Python for a
call that names no state file.

THE SEAM. Each case runs hooks/state_parse_check.py as a subprocess, with a Claude Code payload on
stdin and CLAUDE_CONFIG_DIR at a temp folder. A Bash command runs for real in sh first, so the hook
reads the file the command left. STATE_PARSE_CHECK_UNDER_TEST names another file to test, as
LOCAL_TIME_UNDER_TEST does in hooks/test_local_time.py.

A SILENT CASE HAS A TWIN. Empty output also comes from a hook that is absent or never prints. So each
silent expectation sits in the same test as a named expectation for the same file made broken.

WORDING. The spec fixes no message text. The cases look for the file's basename, for `line N` and
`column N` where a JSON or fence line is claimed, and for `Working premises` on the handoff check.
Run-folder paths are removed before any number is searched for.

TEMP FILES. One run folder per run (lint/_test_temp.py, the one home of the standard). Every case's
folders sit under it, and it is removed at exit.
"""
import atexit
import json
import os
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

HOOK = os.environ.get("STATE_PARSE_CHECK_UNDER_TEST") or os.path.join(HERE, "state_parse_check.py")
SETTINGS = os.path.join(REPO, "settings.json")
RUN = _test_temp.run_folder()
atexit.register(shutil.rmtree, RUN, True)

SID = "s-test"
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
    """The (line, column) that json.loads reports for `text`. The expected position comes from the
    stdlib of the Python that runs this file, so it holds on any version. A hand-counted position
    breaks when a Python release changes the message or where it points."""
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


def payload(cwd, tool, tool_input, response=None):
    """A PostToolUse payload. tool_input comes before tool_response, as the hook's shell filter expects."""
    return json.dumps({
        "session_id": SID,
        "hook_event_name": "PostToolUse",
        "cwd": cwd,
        "tool_name": tool,
        "tool_input": tool_input,
        "tool_response": response if response is not None else {"stdout": "", "stderr": ""},
    })


def context_of(stdout):
    """The PostToolUse additionalContext, or "" when the hook printed nothing. Anything else is text
    that no silent or named assertion can match."""
    if not stdout.strip():
        return ""
    try:
        special = json.loads(stdout)["hookSpecificOutput"]
        if special.get("hookEventName") != "PostToolUse":
            return "(hookEventName is %r, not PostToolUse)" % special.get("hookEventName")
        return special.get("additionalContext", "")
    except Exception:
        return "(stdout is not a PostToolUse context: %r)" % stdout[:100]


def assert_silent(t, ctx, why):
    t.assertEqual(ctx, "", "%s: the hook spoke about a file that is fine: %r" % (why, ctx[:160]))


def assert_named(t, rc, ctx, why, name, line=None, column=None, words=(), home=None):
    t.assertTrue(ctx, "%s: the hook named no break (exit %s)" % (why, rc))
    t.assertIn(name, ctx, "%s: the message does not name %s: %r" % (why, name, ctx[:160]))
    bare = ctx.replace(RUN, " ")
    if home is not None:
        bare = bare.replace(home.root, " ")
    if line is not None:
        t.assertRegex(bare, r"\bline\D{0,4}%d\b" % line,
                      "%s: no `line %d` in the message: %r" % (why, line, ctx[:160]))
    if column is not None:
        t.assertRegex(bare, r"\bcol(?:umn)?\D{0,4}%d\b" % column,
                      "%s: no `column %d` in the message: %r" % (why, column, ctx[:160]))
    for word in words:
        t.assertIn(word, ctx, "%s: the message does not say %r" % (why, word))
    t.assertEqual(rc, 0, "%s: the hook exited %s, and it must never block" % (why, rc))


def hook_entry():
    """(command, matcher) of the settings.json PostToolUse entry that runs this hook, or (None, None)."""
    with open(SETTINGS, "r", encoding="utf-8") as handle:
        settings = json.load(handle)
    for entry in settings.get("hooks", {}).get("PostToolUse", []):
        for hook in entry.get("hooks", []):
            command = hook.get("command", "")
            if "state_parse_check.py" in command:
                return command, entry.get("matcher", "")
    return None, None


class Home:
    """One config folder and one work folder for a case, both under the run folder."""

    def __init__(self):
        self.root = tempfile.mkdtemp(prefix="case-", dir=RUN)
        self.cfg = os.path.join(self.root, "config")
        self.handoffs = os.path.join(self.cfg, "handoffs")
        self.work = os.path.join(self.root, "work")
        os.makedirs(self.handoffs)
        os.makedirs(self.work)

    @property
    def inbox(self):
        return os.path.join(self.handoffs, SID + ".inbox.md")

    @property
    def handoff(self):
        return os.path.join(self.handoffs, SID + ".md")

    def hook(self, tool, tool_input):
        """Run the hook once, as Claude Code does. Return (exit code, PostToolUse context)."""
        env = dict(os.environ, CLAUDE_CONFIG_DIR=self.cfg, HOME=self.root)
        done = subprocess.run([sys.executable, HOOK], input=payload(self.work, tool, tool_input),
                              capture_output=True, text=True, env=env, cwd=self.work)
        return done.returncode, context_of(done.stdout)

    def write_hook(self, path, text):
        """A Write call: the file is written, then the hook runs on the call."""
        write(path, text)
        return self.hook("Write", {"file_path": path, "content": text})

    def sh(self, command):
        return subprocess.run(["sh", "-c", command], cwd=self.work, capture_output=True, text=True).returncode


class IncidentReplay(unittest.TestCase):
    """Case 1: the coordinator's inbox, and the sed that deleted its closing fence."""

    @GNU_SED_ONLY
    def test_sed_that_deletes_the_closing_fence_is_named_at_the_open_fence(self):
        home = Home()
        intact = HEAD_1 + "\n````\nowner: keep the closing fence\n````\n"
        self.assertEqual(intact.splitlines()[-1], "````", "scope: the closer must be the last line")
        rc, ctx = home.write_hook(home.inbox, intact)
        assert_silent(self, ctx, "the intact inbox")
        shell_rc = home.sh("sed -i '$d' " + shlex.quote(home.inbox))
        self.assertEqual(shell_rc, 0, "scope: the sed must run on the temp inbox")
        self.assertNotEqual(read_text(home.inbox).splitlines()[-1], "````",
                            "scope: the sed must delete the closing fence")
        after = read_bytes(home.inbox)
        rc, ctx = home.hook("Bash", {"command": "sed -i '$d' " + shlex.quote(home.inbox)})
        assert_named(self, rc, ctx, "the sed that deleted the closer", SID + ".inbox.md",
                     line=2, home=home)
        self.assertEqual(read_bytes(home.inbox), after, "the hook changed the inbox; it must never revert")


class EditJson(unittest.TestCase):
    """Case 2: an Edit or MultiEdit on a *.json, judged on the state the call left."""

    def test_edit_that_breaks_json_names_the_line_and_column(self):
        home = Home()
        path = os.path.join(home.work, "state.json")
        write(path, OK_JSON)
        json.loads(read_text(path))
        old, new = '"b": 2', '"b": 2,'
        edit_on_disk(self, path, old, new)
        line, column = json_error(self, read_text(path))
        rc, ctx = home.hook("Edit", {"file_path": path, "old_string": old, "new_string": new})
        assert_named(self, rc, ctx, "an Edit that adds a trailing comma", "state.json",
                     line=line, column=column, home=home)

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
        rc, ctx = home.hook("Edit", {"file_path": path, "old_string": old, "new_string": new})
        assert_silent(self, ctx, "an Edit on a file that was broken before the call")
        line, column = json_error(self, read_text(path))
        rc, ctx = home.write_hook(path, read_text(path))
        assert_named(self, rc, ctx, "the same break written in a Write", "state.json",
                     line=line, column=column, home=home)

    def test_multiedit_that_breaks_json_names_the_line_and_column(self):
        home = Home()
        path = os.path.join(home.work, "state.json")
        write(path, OK_JSON)
        edits = [{"old_string": '"a": 1', "new_string": '"a": 10'},
                 {"old_string": '"b": 2', "new_string": '"b": 2,'}]
        for edit in edits:
            edit_on_disk(self, path, edit["old_string"], edit["new_string"])
        line, column = json_error(self, read_text(path))
        rc, ctx = home.hook("MultiEdit", {"file_path": path, "edits": edits})
        assert_named(self, rc, ctx, "a MultiEdit that adds a trailing comma", "state.json",
                     line=line, column=column, home=home)


class EmptyNewString(unittest.TestCase):
    """Case 2, an Edit that only removes text. Its before-state cannot be rebuilt by putting
    new_string back, because an empty new_string matches everywhere. The check reads the removal from
    the file the call leaves."""

    def test_edit_removing_the_closing_fence_of_an_inbox_block_is_named(self):
        home = Home()
        before = HEAD_1 + "\n````\nowner: keep the closing fence\n````\n- fb-1138-1 [note] -> noted\n"
        write(home.inbox, before)
        # A block has two fence lines, so the closer alone is not a unique old_string. The item line
        # under it makes the old_string unique, as an Edit call needs.
        old = "````\n- fb-1138-1 [note] -> noted\n"
        self.assertEqual(before.count(old), 1, "scope: old_string must occur once in the inbox")
        edit_on_disk(self, home.inbox, old, "")
        self.assertEqual(read_text(home.inbox).count("````"), 1, "scope: the closer is gone")
        rc, ctx = home.hook("Edit", {"file_path": home.inbox, "old_string": old, "new_string": ""})
        assert_named(self, rc, ctx, "an empty-new_string Edit that removes the closing fence",
                     SID + ".inbox.md", line=2, home=home)

    def test_edit_removing_a_plain_line_from_a_broken_file_is_silent(self):
        home = Home()
        path = os.path.join(home.work, "state.json")
        write(path, '{\n  "a": 1,,\n  "note": "drop me",\n  "b": 2\n}\n')
        old = '  "note": "drop me",\n'
        edit_on_disk(self, path, old, "")
        json_error(self, read_text(path))  # scope: still broken, the removal did not fix it
        rc, ctx = home.hook("Edit", {"file_path": path, "old_string": old, "new_string": ""})
        assert_silent(self, ctx, "an empty-new_string Edit that removes a plain line from a file already broken")
        line, column = json_error(self, read_text(path))
        rc, ctx = home.write_hook(path, read_text(path))
        assert_named(self, rc, ctx, "the same broken file written in a Write", "state.json",
                     line=line, column=column, home=home)

    def test_edit_removing_a_line_that_breaks_valid_json_is_named(self):
        home = Home()
        path = os.path.join(home.work, "state.json")
        write(path, OK_JSON)
        old = '  "b": 2\n'
        edit_on_disk(self, path, old, "")
        line, column = json_error(self, read_text(path))
        rc, ctx = home.hook("Edit", {"file_path": path, "old_string": old, "new_string": ""})
        assert_named(self, rc, ctx, "an empty-new_string Edit that leaves a trailing comma", "state.json",
                     line=line, column=column, home=home)


class WriteAndDeleted(unittest.TestCase):
    """Case 3: a Write judged as written, and a state file that was deleted."""

    def test_write_of_valid_json_is_silent_and_broken_json_is_named(self):
        home = Home()
        path = os.path.join(home.work, "state.json")
        rc, ctx = home.write_hook(path, OK_JSON)
        assert_silent(self, ctx, "a Write of valid JSON")
        line, column = json_error(self, '{"a": 1,}')
        rc, ctx = home.write_hook(path, '{"a": 1,}')
        assert_named(self, rc, ctx, "a Write of broken JSON", "state.json",
                     line=line, column=column, home=home)

    @SHELL_ONLY
    def test_deleted_state_file_is_silent_and_a_broken_write_is_named(self):
        home = Home()
        settings = os.path.join(home.cfg, "settings.json")
        write(settings, '{"a": 1,}')
        shell_rc = home.sh("rm -f " + shlex.quote(settings))
        self.assertEqual(shell_rc, 0, "scope: the rm must run")
        self.assertFalse(os.path.exists(settings), "scope: the rm must delete the file")
        rc, ctx = home.hook("Bash", {"command": "rm -f " + shlex.quote(settings)})
        assert_silent(self, ctx, "a Bash rm of a state file that was already broken")
        line, column = json_error(self, '{"a": 1,}')
        rc, ctx = home.write_hook(os.path.join(home.work, "other.json"), '{"a": 1,}')
        assert_named(self, rc, ctx, "a broken Write to another file", "other.json",
                     line=line, column=column, home=home)


class BashWrites(unittest.TestCase):
    """Case 4: a Bash command judged by the file it writes, not the file it reads."""

    @SHELL_ONLY
    def test_cat_of_an_invalid_json_is_silent_and_an_append_to_it_is_named(self):
        home = Home()
        path = os.path.join(home.work, "bad.json")
        write(path, '{"a": 1,}\n')
        with self.assertRaises(json.JSONDecodeError):
            json.loads(read_text(path))
        self.assertEqual(home.sh("cat bad.json"), 0, "scope: the cat must run")
        rc, ctx = home.hook("Bash", {"command": "cat bad.json"})
        assert_silent(self, ctx, "a read of an invalid bad.json")
        self.assertEqual(home.sh("printf 'x' >> bad.json"), 0, "scope: the append must run")
        rc, ctx = home.hook("Bash", {"command": "printf 'x' >> bad.json"})
        assert_named(self, rc, ctx, "an append in a write position on the same file", "bad.json", home=home)

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
                rc, ctx = home.hook("Bash", {"command": command})
                assert_named(self, rc, ctx, command, "bad.json", home=home)

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
        rc, ctx = home.hook("Bash", {"command": command})
        assert_named(self, rc, ctx, "sed -i in a write position", "bad.json", home=home)

    @SHELL_ONLY
    def test_read_of_a_broken_state_file_is_named(self):
        # Spec reading: a state-file path counts in any position, so a cat of settings.json counts.
        home = Home()
        settings = os.path.join(home.cfg, "settings.json")
        write(settings, '{"a": 1,}\n')
        self.assertEqual(home.sh("cat " + shlex.quote(settings)), 0, "scope: the cat must run")
        rc, ctx = home.hook("Bash", {"command": "cat " + shlex.quote(settings)})
        assert_named(self, rc, ctx, "a cat of a broken settings.json", "settings.json", home=home)


class ScannerTraps(unittest.TestCase):
    """Case 5: handoff text and JSON text that a fence scan must not misread."""

    def test_handoff_traps_are_silent_and_an_open_fence_is_named(self):
        for label, trap in TRAPS:
            with self.subTest(trap=label):
                home = Home()
                text = handoff_text(trap)
                rc, ctx = home.write_hook(home.handoff, text)
                assert_silent(self, ctx, "the handoff with %s" % label)
                broken = text + "```\nopen at the end\n"
                rc, ctx = home.write_hook(home.handoff, broken)
                assert_named(self, rc, ctx, "the same handoff with a fence left open", SID + ".md",
                             line=text.count("\n") + 1, home=home)

    def test_a_handoff_outside_the_handoff_folder_is_not_judged(self):
        home = Home()
        text = handoff_text("```\nopen\n")
        fence_line = handoff_text().count("\n") + 1
        rc, ctx = home.write_hook(os.path.join(home.work, "notes.md"), text)
        assert_silent(self, ctx, "a .md outside the handoff folder with a fence left open")
        rc, ctx = home.write_hook(home.handoff, text)
        assert_named(self, rc, ctx, "the same .md in the handoff folder", SID + ".md",
                     line=fence_line, home=home)

    def test_json_string_holding_a_fence_is_silent_and_a_trailing_comma_is_named(self):
        home = Home()
        path = os.path.join(home.work, "body.json")
        rc, ctx = home.write_hook(path, JSON_TRAP_OK)
        assert_silent(self, ctx, "valid JSON that holds a fence and a comment-like string")
        line, column = json_error(self, JSON_TRAP_BAD)
        rc, ctx = home.write_hook(path, JSON_TRAP_BAD)
        assert_named(self, rc, ctx, "the same JSON with a trailing comma", "body.json",
                     line=line, column=column, home=home)


class LostSection(unittest.TestCase):
    """Case 6: an Edit that drops an inbox block header, and a handoff with no premises heading."""

    def test_edit_that_keeps_every_header_is_silent_and_dropping_one_is_named(self):
        home = Home()
        rc, ctx = home.write_hook(home.inbox, INBOX_TWO)
        assert_silent(self, ctx, "the intact two-block inbox")
        edit_on_disk(self, home.inbox, "first owner message", "first owner message, edited")
        rc, ctx = home.hook("Edit", {"file_path": home.inbox, "old_string": "first owner message",
                                     "new_string": "first owner message, edited"})
        assert_silent(self, ctx, "an Edit that changes text and keeps both headers")
        edit_on_disk(self, home.inbox, HEAD_2, "### Notes")
        rc, ctx = home.hook("Edit", {"file_path": home.inbox, "old_string": HEAD_2,
                                     "new_string": "### Notes"})
        assert_named(self, rc, ctx, "an Edit that turns the second block header into plain text",
                     SID + ".inbox.md", words=("11:40",), home=home)

    def test_multiedit_that_drops_an_inbox_header_is_named(self):
        home = Home()
        write(home.inbox, INBOX_TWO)
        edits = [{"old_string": HEAD_2, "new_string": "### Notes"}]
        edit_on_disk(self, home.inbox, HEAD_2, "### Notes")
        rc, ctx = home.hook("MultiEdit", {"file_path": home.inbox, "edits": edits})
        assert_named(self, rc, ctx, "a MultiEdit that drops the second block header",
                     SID + ".inbox.md", words=("11:40",), home=home)

    def test_handoff_without_working_premises_is_named(self):
        home = Home()
        rc, ctx = home.write_hook(home.handoff, handoff_text("## Next\n\n- one step\n"))
        assert_silent(self, ctx, "a handoff with its Working premises heading")
        without = GOAL + "## Next\n\n- one step\n"
        rc, ctx = home.write_hook(home.handoff, without)
        assert_named(self, rc, ctx, "a handoff with no Working premises heading", SID + ".md",
                     words=("Working premises",), home=home)


class EmptyAndFullStates(unittest.TestCase):
    """Case 8: the empty and the full-size states of each kind of file."""

    def test_empty_inbox_is_silent_and_an_open_fence_in_it_is_named(self):
        home = Home()
        rc, ctx = home.write_hook(home.inbox, "")
        assert_silent(self, ctx, "an empty inbox")
        rc, ctx = home.write_hook(home.inbox, HEAD_1 + "\n````\nopen\n")
        assert_named(self, rc, ctx, "an inbox whose only fence is left open", SID + ".inbox.md",
                     line=2, home=home)

    def test_full_size_inbox_is_silent_and_a_lost_closer_at_the_end_is_named(self):
        home = Home()
        intact, _ = build_inbox(300)
        rc, ctx = home.write_hook(home.inbox, intact)
        assert_silent(self, ctx, "a 300-block inbox with every fence closed")
        broken, opener = build_inbox(300, drop_last_closer=True)
        rc, ctx = home.write_hook(home.inbox, broken)
        assert_named(self, rc, ctx, "a 300-block inbox whose last closer is lost", SID + ".inbox.md",
                     line=opener, home=home)

    def test_empty_json_is_named_at_line_1_column_1(self):
        home = Home()
        line, column = json_error(self, "")
        rc, ctx = home.write_hook(os.path.join(home.work, "empty.json"), "")
        assert_named(self, rc, ctx, "an empty *.json", "empty.json", line=line, column=column, home=home)


class PreFilter(unittest.TestCase):
    """Case 7: the settings.json entry for this hook, and the shell filter that starts no Python."""

    def test_settings_json_runs_the_hook_on_the_five_tools(self):
        command, matcher = hook_entry()
        self.assertIsNotNone(command, "settings.json has no PostToolUse entry that runs state_parse_check.py")
        self.assertEqual(set(matcher.split("|")), {"Bash", "PowerShell", "Write", "Edit", "MultiEdit"},
                         "the entry's matcher is %r" % matcher)

    @SHELL_ONLY
    def test_prefilter_starts_no_python_for_a_call_that_names_no_state_file(self):
        command, _ = hook_entry()
        self.assertIsNotNone(command, "settings.json has no PostToolUse entry that runs state_parse_check.py")
        home = Home()
        # A stand-in file, so the entry's own file test passes. The shim below answers for python.
        write(os.path.join(home.cfg, "hooks", "state_parse_check.py"), "# stand-in\n")
        bin_dir = os.path.join(home.root, "shim-bin")
        log = os.path.join(home.root, "python-starts.log")
        for name in ("python3", "python"):
            shim = os.path.join(bin_dir, name)
            write(shim, '#!/bin/sh\necho started >> "$SHIM_LOG"\ncat > /dev/null\nexit 0\n')
            os.chmod(shim, 0o755)

        def python_starts(tool_input, response=None):
            if os.path.exists(log):
                os.remove(log)
            env = dict(os.environ, CLAUDE_CONFIG_DIR=home.cfg, HOME=home.root, SHIM_LOG=log,
                       PATH=bin_dir + os.pathsep + os.environ.get("PATH", ""))
            subprocess.run(["sh", "-c", command], input=payload(home.work, "Bash", tool_input, response),
                           capture_output=True, text=True, env=env, cwd=home.work)
            return os.path.exists(log) and os.path.getsize(log) > 0

        self.assertFalse(python_starts({"command": "git status"},
                                       {"stdout": "wrote notes.json and handoffs/s-test.md"}),
                         "a call that names no state file started Python")
        self.assertTrue(python_starts({"command": "sed -i 's/a/b/' bad.json"}),
                        "a call that writes a *.json started no Python: the filter is not reached")
        self.assertTrue(python_starts({"command": "cat " + shlex.quote(home.handoff)}),
                        "a call that names the handoff folder started no Python")


class RunFolderSweep(unittest.TestCase):
    """The run-folder standard: the first request of a run removes a day-old sibling, keeps a fresh one."""

    def test_sweep_removes_a_day_old_sibling_and_keeps_a_fresh_one(self):
        now = 1800000000  # a fixed clock: sweep takes `now`, so no real time is read
        root = tempfile.mkdtemp(prefix="sweep-", dir=RUN)
        own = os.path.join(root, "1-%s" % uuid.uuid4().hex)
        old = os.path.join(root, "2-%s" % uuid.uuid4().hex)
        fresh = os.path.join(root, "3-%s" % uuid.uuid4().hex)
        for path, age in ((own, 0), (old, 2 * 86400), (fresh, 3600)):
            os.makedirs(path)
            os.utime(path, (now - age, now - age))
        _test_temp.sweep(root, own, now=now)
        self.assertFalse(os.path.exists(old), "the sweep kept a sibling run folder over a day old")
        self.assertTrue(os.path.isdir(fresh), "the sweep removed a sibling run folder under a day old")
        self.assertTrue(os.path.isdir(own), "the sweep removed the run's own folder")


if __name__ == "__main__":
    unittest.main(verbosity=2)
