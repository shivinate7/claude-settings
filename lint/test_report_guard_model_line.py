#!/usr/bin/env python3
"""The turn-end model line, and the one home of the model list.

While the owner's model word is on, the session's reply must carry one line that names the model and the owner's clause.
lint/report_guard.py refuses a turn end without it. A reply that is the report which ends the word carries no line, and
neither does a turn after `no <model>`. A stop_hook_active rewrite is never blocked again for the line (no loop).

The model list has one home, hooks/shared_names.py (MODEL_FAMILIES). lint/report_guard.py, hooks/override.py (the owner's
model word reader) and hooks/guard.py read that same object, and no other file writes the list out.

The fixture, the transcript helpers and the run folder come from lint/test_report_guard.py, the one home. Run with:

    python3 lint/test_report_guard_model_line.py -v
"""
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS = os.path.join(HERE, "..", "hooks")
sys.path.insert(0, HERE)
sys.path.insert(0, HOOKS)
import test_report_guard as trg  # noqa: E402  the fixture, helpers and run folder (one home)

human = trg.human
assistant_text = trg.assistant_text
REPORT_GUARD = trg.REPORT_GUARD
GOOD_REPORT = trg.GOOD_REPORT

OWNER_HAIKU = "Run the model audit on haiku."
# The line the reply carries while the haiku word is on: `Model <name> is on for <the owner's clause>; say "no <name>" to end it.`
LINE_OK = 'Model haiku is on for Run the model audit on haiku; say "no haiku" to end it.'
LINE_RE = re.compile(r'^Model haiku is on for .+; say "no haiku" to end it\.$', re.M)
LISTS = re.compile(r"^MODEL_FAMILIES\s*=\s*[(\[]", re.M)  # a literal copy of the model list, a second home
MODEL_LIST = ("haiku", "sonnet", "opus", "fable")


def setUpModule():
    trg.setUpModule()  # the run folder, CLAUDE_CONFIG_DIR and the model stub, set as test_report_guard sets them


def tearDownModule():
    trg.tearDownModule()


class ModelLineFixture(unittest.TestCase):
    """One Stop run of report_guard.py on a transcript this test writes into the run folder."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(dir=trg.RUN_FOLDER)  # the run folder's child, never the system temp dir
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def stop(self, records, active=False):
        path = trg.write_transcript(records, self.tmp)
        hook = {"hook_event_name": "Stop", "transcript_path": path, "stop_hook_active": active}
        run = trg.run_guard(REPORT_GUARD, hook)
        self.assertEqual(run.returncode, 0, "report_guard.py exits %d: %s" % (run.returncode, run.stderr))
        return json.loads(run.stdout) if run.stdout.strip() else {}


class TurnEndLineTests(ModelLineFixture):

    def test_a_word_on_and_no_line_refuses_the_turn_end(self):
        out = self.stop([human(OWNER_HAIKU), assistant_text("Running it.")])
        self.assertEqual(out.get("decision"), "block",
                         "the haiku word is on and the reply carries no model line, so the turn end is refused: %r" % out)
        self.assertIn("Model haiku is on for", out.get("reason", ""),
                      "the refusal names the line the reply must carry: %r" % out)

    def test_a_word_on_and_the_line_in_the_reply_passes(self):
        out = self.stop([human(OWNER_HAIKU), assistant_text(LINE_OK + "\nRunning it.")])
        self.assertNotEqual(out.get("decision"), "block",
                            "the reply carries the model line, so the turn end passes: %r" % out)
        self.assertRegex(LINE_OK, LINE_RE, "the control's own line matches the form the reader names")

    def test_no_word_on_asks_for_no_line(self):
        out = self.stop([human("Run the model audit."), assistant_text("Running it.")])
        self.assertNotEqual(out.get("decision"), "block",
                            "no model word is on, so no line is asked and the turn end passes: %r" % out)

    def test_the_report_that_ends_the_word_asks_for_no_line(self):
        out = self.stop([human(OWNER_HAIKU), assistant_text(GOOD_REPORT)])
        self.assertNotEqual(out.get("decision"), "block",
                            "the reply is the report that ends the word, so no line is asked: %r" % out)

    def test_after_no_opus_asks_for_no_line(self):
        out = self.stop([human("Use opus for it."), assistant_text("Ok."), human("no opus"), assistant_text("Stopped.")])
        self.assertNotEqual(out.get("decision"), "block",
                            "the owner said no opus, so the opus word is off and no line is asked: %r" % out)

    def test_a_stop_hook_rewrite_is_not_blocked_again_for_the_line(self):
        out = self.stop([human(OWNER_HAIKU), assistant_text("Running it.")], active=True)
        self.assertNotEqual(out.get("decision"), "block",
                            "a stop_hook_active rewrite never blocks for the line again, so it cannot loop: %r" % out)


class ModelListHomeTests(unittest.TestCase):
    """The model list is written once, in hooks/shared_names.py. The three readers name that same object."""

    def test_the_model_list_is_held_in_shared_names(self):
        import shared_names
        self.assertTrue(hasattr(shared_names, "MODEL_FAMILIES"),
                        "hooks/shared_names.py holds no MODEL_FAMILIES, the one home of the model list")
        self.assertEqual(tuple(shared_names.MODEL_FAMILIES), MODEL_LIST,
                         "the one home of the model list holds the four model words, in order")

    def test_report_guard_override_and_guard_read_the_same_object(self):
        import shared_names
        home = getattr(shared_names, "MODEL_FAMILIES", None)
        self.assertIsNotNone(home, "hooks/shared_names.py holds no MODEL_FAMILIES, so no reader can read it from there")
        import override
        import guard
        self.assertIs(trg.RG.MODEL_FAMILIES, home,
                      "lint/report_guard.py holds its own copy of the model list, not the one in hooks/shared_names.py")
        self.assertIs(override.MODEL_FAMILIES, home,
                      "hooks/override.py holds its own copy of the model list, not the one in hooks/shared_names.py")
        self.assertIs(guard.MODEL_FAMILIES, home,
                      "hooks/guard.py holds its own copy of the model list, not the one in hooks/shared_names.py")
        self.assertIn(guard.FLOOR_WORD, home, "guard.FLOOR_WORD is not one of the model list's words")

    def test_no_file_writes_the_model_list_out_again(self):
        # A literal list in any other reader is a second home. The one assignment to read is in shared_names.py.
        copies = []
        for folder in (HOOKS, HERE):
            for name in sorted(os.listdir(folder)):
                if not name.endswith(".py") or name == "shared_names.py" or name == os.path.basename(__file__):
                    continue
                with open(os.path.join(folder, name), encoding="utf-8") as handle:
                    if LISTS.search(handle.read()):
                        copies.append(name)
        self.assertEqual(copies, [], "these files write the model list out as a literal, not from hooks/shared_names.py")


if __name__ == "__main__":
    unittest.main()
