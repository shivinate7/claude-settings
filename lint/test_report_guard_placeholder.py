#!/usr/bin/env python3
"""Cases for the placeholder check on a reply's fenced shell block (lint/report_guard.py, run as the Stop hook).

A reply hands the owner a command to run. A shell block (bash, sh, zsh, powershell, and the tags pwsh, ps1 and shell)
that still holds a token the owner must fill is refused. The tokens: `/dev/sdX` with an optional digit, an
angle-bracket word such as `<branch>` or `<your-path>`, a word that starts `YOUR_` or `your-`, `REPLACE_ME`,
`CHANGEME`, and a standalone `xxx` or `XXX`. The waiting-page item's `command` field has its own cases in
hooks/test_question_form_placeholder.py, and both read one detector.

Each reply is the same frame: a prose line, one fenced block, then the report. Only the line in the block changes.
Refuse cases run once unlanded and once landed (a git commit in the turn). Allow cases run the same two ways, so a
look-alike line that is a real shell form must pass in both branches of the guard. A fence inside the report
blockquote, and a placeholder in a blockquote line, are not a hand-off, so they pass.

The fixture, the transcript records and the guard runner come from lint/test_report_guard.py, the one home. Run it
from the repository root:

    python3 lint/test_report_guard_placeholder.py -v
"""
import json
import os
import sys
import unittest
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_report_guard as trg  # noqa: E402  the fixture, records, guard runner and run folder (one home)

REPORT = trg.GOOD_REPORT
SHELL_LANGS = ("bash", "sh", "zsh", "powershell", "pwsh", "ps1", "shell")
LANDING = "git commit -m x"

# Each line sits alone in the block. A person must fill the token before the line runs.
REFUSE_LINES = (
    "sudo e2fsck -f -D /dev/sdX1",
    "sudo e2fsck -f -D /dev/sdX",
    "git checkout <branch>",
    "cd <your-path>",
    "export TOKEN=YOUR_TOKEN",
    "cd your-repo",
    "echo REPLACE_ME",
    "echo CHANGEME",
    "git commit -m xxx",
    "echo XXX",
    "Get-Item <path>",
)

# Each block holds one of these shell forms. Each one passes, unlanded and landed. The tag-shaped words sit in a
# heredoc body or in a quoted string, where the shell reads them as text.
ALLOW_BLOCKS = (
    "cat > f <<'EOF'\nline one\nEOF",
    "sort < in.txt",
    "sudo e2fsck -f -D /dev/sda1 2>&1",
    "cd $HOME/repo",
    "echo ${VAR}",
    "GH_TOKEN=$(...) make test",
    "sudo e2fsck -f -D /dev/sda1",
    "grep -E 'a|b' notes.txt",
    "curl -s 'https://example.com/api?x=1'",
    "git log a..b",
    "instance-type xxxlarge",
    "cat > ~/Library/LaunchAgents/x.plist <<'EOF'\n<dict>\nEOF",
    "cat > /tmp/x.html <<'EOF'\n<html>\nEOF",
    "sed 's/<br>//g' page.html",
    "grep -o '<title>.*</title>' f",
)

# A report's blockquote is the report, not a hand-off: a placeholder in one of its lines, or a fence inside it, passes.
BLOCKQUOTE_PROSE = "> **Done** BUILT abc123\n> **Next** check the device /dev/sdX1 by hand"
BLOCKQUOTE_FENCE = "> **Done** BUILT abc123\n>\n> ```bash\n> sudo e2fsck -f -D /dev/sdX1\n> ```\n>\n> **Next** ship it"


def setUpModule():
    trg.setUpModule()  # the run folder, CLAUDE_CONFIG_DIR and the model stub, set as test_report_guard sets them


def tearDownModule():
    trg.tearDownModule()


def reply_text(lang, block):
    return "Run this on your computer:\n\n```%s\n%s\n```\n\n%s" % (lang, block, REPORT)


def stop_text(text, landed):
    records = [trg.human("do the task")]
    if landed:
        records += [trg.tool_use_msg("Bash", {"command": LANDING}), trg.tool_result_msg()]
    records.append(trg.assistant_text(text))
    name = "placeholder-%s.jsonl" % uuid.uuid4().hex
    path = trg.write_transcript(records, trg.RUN_FOLDER, name=name)
    hook = {"hook_event_name": "Stop", "transcript_path": path, "stop_hook_active": False}
    return trg.run_guard(trg.REPORT_GUARD, hook)


def stop_run(block_text, lang, landed):
    return stop_text(reply_text(lang, block_text), landed)


def decision_of(run):
    """The Stop hook's decision: "" when it prints nothing, "unparsed" when its output is not JSON."""
    text = run.stdout.strip()
    if not text:
        return ""
    try:
        return str(json.loads(text).get("decision") or "")
    except (ValueError, AttributeError):
        return "unparsed"


class PlaceholderFenceTests(unittest.TestCase):
    def assert_refused(self, block_text, lang, landed):
        run = stop_run(block_text, lang, landed)
        self.assertEqual(run.returncode, 0, "the guard exited %d: %s" % (run.returncode, run.stderr[-300:]))
        self.assertEqual(decision_of(run), "block",
                         "a placeholder in a %s block was not refused (landed=%s): %r" % (lang, landed, block_text))

    def assert_passes(self, block_text, lang, landed):
        run = stop_run(block_text, lang, landed)
        self.assertEqual(run.returncode, 0, "the guard exited %d: %s" % (run.returncode, run.stderr[-300:]))
        self.assertNotEqual(decision_of(run), "block",
                            "a real shell form in a %s block was refused (landed=%s): %r" % (lang, landed, block_text))

    def test_unlanded_placeholder_in_each_shell_block_is_refused(self):
        for lang in SHELL_LANGS:
            for line in REFUSE_LINES:
                with self.subTest(lang=lang, line=line):
                    self.assert_refused(line, lang, landed=False)

    def test_landed_placeholder_in_a_bash_block_is_refused(self):
        for line in REFUSE_LINES:
            with self.subTest(line=line):
                self.assert_refused(line, "bash", landed=True)

    def test_unlanded_real_shell_form_in_a_bash_block_passes(self):
        for block in ALLOW_BLOCKS:
            with self.subTest(block=block):
                self.assert_passes(block, "bash", landed=False)

    def test_landed_real_shell_form_in_a_bash_block_passes(self):
        for block in ALLOW_BLOCKS:
            with self.subTest(block=block):
                self.assert_passes(block, "bash", landed=True)

    def test_placeholder_in_the_report_blockquote_passes(self):
        cases = ((BLOCKQUOTE_PROSE, False), (BLOCKQUOTE_PROSE, True), (BLOCKQUOTE_FENCE, False))
        for text, landed in cases:
            with self.subTest(text=text, landed=landed):
                run = stop_text(text, landed)
                self.assertEqual(run.returncode, 0, "the guard exited %d: %s" % (run.returncode, run.stderr[-300:]))
                self.assertNotEqual(decision_of(run), "block",
                                    "a placeholder in the report blockquote was refused (landed=%s): %r"
                                    % (landed, text))


if __name__ == "__main__":
    unittest.main()
