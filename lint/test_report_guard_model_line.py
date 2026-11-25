#!/usr/bin/env python3
"""The turn-end model line, and the one home of the model list.

While the owner's model hold is on, the session's reply must carry one line that names the model. The hold is the judged yes
for a model: the session's Opus pass file (state/override/opus/<session>.json) with its `model` field. lint/report_guard.py
reads that same file through the same reader as the guard, so the two cannot disagree. It refuses a turn end without the line.
A reply that is the report which ends the hold carries no line, and so does a turn with no hold. A stop_hook_active rewrite is
never blocked again for the line (no loop).

The model list has one home, hooks/shared_names.py (MODEL_FAMILIES). The three other holders name that object: ROLE_MODEL_RANK
in hooks/guard.py, the alternation of ROLE_MODEL_RE in lint/report_guard.py, and MODEL_NAME in lint/check_agent_models.py.
No other file writes the list out as a literal.

The fixture, the transcript helpers and the run folder come from lint/test_report_guard.py, the one home. The pass file is
written here as the judge's yes writes it, because this suite runs in its own process and cannot import the guard's section
of the Opus pass (one object-free JSON write, named here as the reason for the copy). Run with:

    python3 lint/test_report_guard_model_line.py -v
"""
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

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
# The line the reply carries while the haiku hold is on: `Model <name> is on for <the owner's clause>; say "no <name>" to end it.`
LINE_OK = 'Model haiku is on for Run the model audit on haiku; say "no haiku" to end it.'
LINE_RE = re.compile(r'^Model haiku is on for .+; say "no haiku" to end it\.$', re.M)
LISTS = re.compile(r"^MODEL_FAMILIES\s*=\s*[(\[]", re.M)  # a literal copy of the model list, a second home
MODEL_LIST = ("haiku", "sonnet", "opus", "fable")
WORD = re.compile(r"haiku|sonnet|opus|fable")
OWNER_TZ = timezone(timedelta(hours=-6))  # the owner's Central clock in these fixtures, a fixed offset
HOLD_AT = datetime(2026, 11, 25, 10, 0, tzinfo=OWNER_TZ)  # the instant the owner's model ask was judged: the hold's `at`


def instant(minutes):
    """The transcript timestamp `minutes` after HOLD_AT. Arithmetic on a fixed instant: no clock is read."""
    return (HOLD_AT + timedelta(minutes=minutes)).isoformat()


def timed(record, minutes):
    """The record with its transcript timestamp, the instant the reader compares with a hold's `at`."""
    record["timestamp"] = instant(minutes)
    return record


def setUpModule():
    trg.setUpModule()  # the run folder, CLAUDE_CONFIG_DIR and the model stub, set as test_report_guard sets them


def tearDownModule():
    trg.tearDownModule()


class ModelLineFixture(unittest.TestCase):
    """One Stop run of report_guard.py on a transcript this test writes into the run folder, with its own config folder
    so the hold files of one case never reach another."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(dir=trg.RUN_FOLDER)  # the run folder's child, never the system temp dir
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.cfg = os.path.join(self.tmp, "config")
        os.makedirs(self.cfg)

    def hold(self, session, model, end="report"):
        """The judged yes for `model`, written to the session's Opus pass file as the judge's yes writes it: `model`, `at`,
        and `end` "report" for a plain ask. `until` is far ahead, so only the report can end the hold in these cases."""
        body = {"kind": "opus", "until": "2099-01-01T00:00:00+00:00", "role": None, "model": model, "at": instant(0)}
        if end:
            body["end"] = end
        path = os.path.join(self.cfg, "state", "override", "opus", session + ".json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(body, handle)

    def stop(self, records, active=False, session="s-model-line"):
        path = trg.write_transcript(records, self.tmp)
        hook = {"hook_event_name": "Stop", "transcript_path": path, "stop_hook_active": active, "session_id": session}
        run = trg.run_guard(REPORT_GUARD, hook, env=dict(os.environ, CLAUDE_CONFIG_DIR=self.cfg))
        self.assertEqual(run.returncode, 0, "report_guard.py exits %d: %s" % (run.returncode, run.stderr))
        return json.loads(run.stdout) if run.stdout.strip() else {}


class TurnEndLineTests(ModelLineFixture):

    def test_a_haiku_hold_and_no_line_refuses_the_turn_end(self):
        self.hold("s-model-line", "haiku")
        out = self.stop([timed(human(OWNER_HAIKU), 0), timed(assistant_text("Running it."), 1)])
        self.assertEqual(out.get("decision"), "block",
                         "the haiku hold is on and the reply carries no model line, so the turn end is refused: %r" % out)
        self.assertIn("Model haiku is on for", out.get("reason", ""),
                      "the refusal names the line the reply must carry: %r" % out)

    def test_a_sonnet_hold_names_sonnet_in_the_refused_line(self):
        self.hold("s-model-line", "sonnet")
        out = self.stop([timed(human("Use sonnet for the audit."), 0), timed(assistant_text("Running it."), 1)])
        self.assertEqual(out.get("decision"), "block",
                         "the sonnet hold is on and the reply carries no model line, so the turn end is refused: %r" % out)
        self.assertIn("Model sonnet is on for", out.get("reason", ""),
                      "the refusal names the sonnet line the reply must carry: %r" % out)

    def test_a_hold_and_the_line_in_the_reply_passes(self):
        self.hold("s-model-line", "haiku")
        out = self.stop([timed(human(OWNER_HAIKU), 0), timed(assistant_text(LINE_OK + "\nRunning it."), 1)])
        self.assertNotEqual(out.get("decision"), "block",
                            "the reply carries the model line, so the turn end passes: %r" % out)
        self.assertRegex(LINE_OK, LINE_RE, "the control's own line matches the form the reader names")

    def test_no_hold_asks_for_no_line(self):
        out = self.stop([timed(human("Run the model audit."), 0), timed(assistant_text("Running it."), 1)])
        self.assertNotEqual(out.get("decision"), "block",
                            "no model hold is on, so no line is asked and the turn end passes: %r" % out)

    def test_the_report_that_ends_the_hold_asks_for_no_line(self):
        self.hold("s-model-line", "haiku")
        out = self.stop([timed(human(OWNER_HAIKU), 0), timed(assistant_text(GOOD_REPORT), 5)])
        self.assertNotEqual(out.get("decision"), "block",
                            "the reply is the report that ends the hold, so no line is asked: %r" % out)

    def test_after_no_opus_asks_for_no_line(self):
        out = self.stop([human("Use opus for it."), assistant_text("Ok."), human("no opus"), assistant_text("Stopped.")])
        self.assertNotEqual(out.get("decision"), "block",
                            "the owner said no opus, so no hold is on and no line is asked: %r" % out)

    def test_a_stop_hook_rewrite_is_not_blocked_again_for_the_line(self):
        self.hold("s-model-line", "haiku")
        out = self.stop([timed(human(OWNER_HAIKU), 0), timed(assistant_text("Running it."), 1)], active=True)
        self.assertNotEqual(out.get("decision"), "block",
                            "a stop_hook_active rewrite never blocks for the line again, so it cannot loop: %r" % out)


class ModelListHomeTests(unittest.TestCase):
    """The model list is written once, in hooks/shared_names.py. The other holders name that same object, or hold the
    same words where a regex needs a literal."""

    def home(self):
        import shared_names
        home = getattr(shared_names, "MODEL_FAMILIES", None)
        self.assertIsNotNone(home, "hooks/shared_names.py holds no MODEL_FAMILIES, the one home of the model list")
        return shared_names, home

    def test_the_model_list_is_held_in_shared_names(self):
        _, home = self.home()
        self.assertEqual(tuple(home), MODEL_LIST, "the one home of the model list holds the four model words, in order")

    def test_report_guard_reads_the_same_object(self):
        _, home = self.home()
        self.assertIs(trg.RG.MODEL_FAMILIES, home,
                      "lint/report_guard.py holds its own copy of the model list, not the one in hooks/shared_names.py")

    def test_the_role_model_regex_holds_the_same_words(self):
        _, home = self.home()
        self.assertEqual(set(WORD.findall(trg.RG.ROLE_MODEL_RE.pattern)), set(home),
                         "lint/report_guard.py ROLE_MODEL_RE names other model words than hooks/shared_names.py holds")

    def test_the_guard_role_rank_names_come_from_the_list(self):
        _, home = self.home()
        import guard
        self.assertTrue(set(guard.ROLE_MODEL_RANK) <= set(home),
                        "hooks/guard.py ROLE_MODEL_RANK names a word that hooks/shared_names.py does not hold: %r"
                        % (guard.ROLE_MODEL_RANK,))

    def test_the_agent_model_check_holds_the_same_words(self):
        _, home = self.home()
        import check_agent_models
        self.assertEqual(set(WORD.findall(check_agent_models.MODEL_NAME.pattern)), set(home),
                         "lint/check_agent_models.py MODEL_NAME names other model words than hooks/shared_names.py holds")

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
