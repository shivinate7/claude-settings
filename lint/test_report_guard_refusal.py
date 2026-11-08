#!/usr/bin/env python3
"""Cases for the Stop-side settle of refusals, lint/report_guard.py pending_refusals (roadmap step
report-guard-refusal-right; decision refusals-reach-the-owner).

Two rules:
- A reply that names a refused tool, with "refusal was right" or "refusal is right" directly after the
  name (an optional colon may sit between), clears that tool's row, in any part of the reply. A phrase
  that does not follow its name, a hedged phrase, or a quoted block reason clears nothing. A tool named
  under Input Needed clears as before.
- A row for an agent's call is dropped when its tool_use_id is a tool_use only in agent records: the
  sidechain records of the transcript, or the files under <session>/subagents/. A row whose tool_use_id is
  in an orchestrator record stays, even when it carries agent_id. A tool_use_id found in no transcript keeps
  the row, so an unflushed refusal is never lost (lane ruling, 17:38 CST). A row with no tool_use_id (an old
  file) stays. A transcript that cannot be read keeps the row.

Calls pending_refusals directly. Each case works in its own folder under this run's folder (test-temp-standard).
Run it from the repository root:

    python3 lint/test_report_guard_refusal.py

Standard library only. The file helpers are restated from lint/test_report_guard.py PendingRefusalTests:
that file is shared with other lanes, so its helpers are not imported.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per test run (lint/_test_temp.py)
import report_guard  # noqa: E402  pending_refusals, the Stop-side settle of the refusals file

RUN_FOLDER = _test_temp.run_folder()
SID = "rg-sid-1"
CREATE = "mcp__claude-code-remote__create_session"
INTERRUPT = "mcp__claude-code-remote__interrupt_session"
BASH = "Bash"
AGENT_ID = "a1b2c3d4e5f6a7b8c"
PHRASES = ("refusal was right", "refusal is right")
AFTER = "after the block"
OUTSIDE = ("Done", "Deviations", "Next", AFTER)  # every part but Input Needed
ALL_PARTS = ("Done", "Deviations", "Input Needed", "Next", AFTER)
HUMAN = {"type": "user", "isSidechain": False, "message": {"role": "user", "content": "do the task"}}


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)


def restore_config_dir(prev):
    if prev is None:
        os.environ.pop("CLAUDE_CONFIG_DIR", None)
    else:
        os.environ["CLAUDE_CONFIG_DIR"] = prev


def reply(part, line):
    """A report block with `line` in `part`. For AFTER, the block is followed by `line` as a paragraph."""
    labels = [("Done", "OTHER read the state"), ("Deviations", "none"),
              ("Input Needed", "none"), ("Next", "wait")]
    block = "\n".join("> **%s** %s" % (name, line if name == part else text) for name, text in labels)
    if part == AFTER:
        return block + "\n\n" + line + "\n"
    return block + "\n"


NEUTRAL = reply("Done", "OTHER read the state")


def tool_use(tool_use_id, name, sidechain=False):
    return {"type": "assistant", "isSidechain": sidechain,
            "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": tool_use_id, "name": name, "input": {}}]}}


class SettleTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.mkdtemp(dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, self.scratch, True)
        self.cfg = os.path.join(self.scratch, "cfg")
        os.makedirs(self.cfg)
        prev = os.environ.get("CLAUDE_CONFIG_DIR")
        os.environ["CLAUDE_CONFIG_DIR"] = self.cfg
        self.addCleanup(restore_config_dir, prev)

    def fresh_config(self):
        """A config folder of its own for the next subtest. The raised-refusals file lives in the config folder, so
        an earlier subtest's raised row would drop this subtest's identical row."""
        self.cfg = tempfile.mkdtemp(dir=self.scratch)
        os.environ["CLAUDE_CONFIG_DIR"] = self.cfg

    def refusals_file(self):
        return os.path.join(self.cfg, "state", "refusals", SID + ".jsonl")

    def write_rows(self, rows):
        os.makedirs(os.path.dirname(self.refusals_file()), exist_ok=True)
        with open(self.refusals_file(), "w", encoding="utf-8") as handle:
            for row in rows:
                out = {"ts": "2026-11-03T10:00:00-06:00", "reason": "refused"}
                out.update(row)
                handle.write(json.dumps(out) + "\n")

    def write_refusals(self, tools):
        self.write_rows([{"tool_name": tool} for tool in tools])

    def pending_tools(self):
        """The tool_name of each row still in the refusals file, [] when the file is gone."""
        try:
            with open(self.refusals_file(), encoding="utf-8") as handle:
                return [json.loads(line)["tool_name"] for line in handle if line.strip()]
        except FileNotFoundError:
            return []

    def check_scope(self, tools):
        """Scope first (P7): the rows are in the file before the reply is judged."""
        self.write_refusals(tools)
        self.assertEqual(self.pending_tools(), tools, "scope: the fixture file does not hold the rows")

    def write_jsonl(self, path, records):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            for rec in records:
                handle.write(json.dumps(rec) + "\n")
        return path

    def transcript(self, records):
        return self.write_jsonl(os.path.join(self.scratch, "transcript.jsonl"), records)

    def agent_file(self, transcript, name, records):
        """The agent file beside the transcript, where Claude Code writes an agent's records: <session>/subagents/."""
        folder = os.path.join(os.path.splitext(transcript)[0], "subagents")
        return self.write_jsonl(os.path.join(folder, name + ".jsonl"), records)

    def settle(self, text, transcript=None):
        hook = {"session_id": SID}
        if transcript is not None:
            hook["transcript_path"] = transcript
        return report_guard.pending_refusals(hook, text)

    # ---- the phrase: a line naming the tool with "refusal was right" or "refusal is right"

    def test_b1_phrase_and_full_name_outside_input_needed_clear_that_row(self):
        for tool in (CREATE, INTERRUPT):
            for part in OUTSIDE:
                for phrase in PHRASES:
                    with self.subTest(tool=tool, part=part, phrase=phrase):
                        self.check_scope([tool])
                        line = "`%s` %s; the call stays refused." % (tool, phrase)
                        left = self.settle(reply(part, line))
                        self.assertEqual(left, [], "the reply said the refusal was right for %s in %s, "
                                                   "and the row stayed" % (tool, part))
                        self.assertFalse(os.path.exists(self.refusals_file()),
                                         "the row was cleared but the file stayed")

    def test_b2_full_name_under_input_needed_clears_with_or_without_the_phrase(self):
        for tool in (CREATE, INTERRUPT):
            lines = ("`%s` %s; the call stays refused." % (tool, PHRASES[0]), "allow `%s`?" % tool)
            for line in lines:
                with self.subTest(tool=tool, line=line):
                    self.check_scope([tool])
                    left = self.settle(reply("Input Needed", line))
                    self.assertEqual(left, [], "a name under Input Needed did not clear the row for %s" % tool)
                    self.assertFalse(os.path.exists(self.refusals_file()),
                                     "the row was cleared but the file stayed")

    def test_b3_one_tool_named_with_the_phrase_leaves_the_other(self):
        with self.subTest("one of two"):
            self.check_scope([CREATE, INTERRUPT])
            left = self.settle(reply("Done", "`%s` refusal was right; the call stays refused." % CREATE))
            self.assertEqual(left, [INTERRUPT], "the reply cleared a tool it did not name with the phrase")
            self.assertEqual(self.pending_tools(), [INTERRUPT], "the cleared row stayed in the file")
        with self.subTest("both"):
            self.check_scope([CREATE, INTERRUPT])
            line = "`%s` refusal was right and `%s` refusal was right." % (CREATE, INTERRUPT)
            left = self.settle(reply("Done", line))
            self.assertEqual(left, [], "a reply naming both tools with the phrase left a row")
            self.assertFalse(os.path.exists(self.refusals_file()), "both rows were cleared but the file stayed")

    def test_b4_phrase_without_the_tool_name_clears_nothing(self):
        for part in ALL_PARTS:
            with self.subTest(part=part):
                self.check_scope([CREATE])
                left = self.settle(reply(part, "the refusal was right; keep it refused."))
                self.assertEqual(left, [CREATE], "a phrase with no tool name cleared the row in %s" % part)
                self.assertEqual(self.pending_tools(), [CREATE], "a phrase with no tool name changed the file")

    def test_b5_tool_name_without_the_phrase_outside_input_needed_clears_nothing(self):
        lines = ("`%s` was refused by auto mode; the handoff holds the note." % CREATE,
                 "`%s` refusal was wrong." % CREATE)
        for part in OUTSIDE:
            for line in lines:
                with self.subTest(part=part, line=line):
                    self.check_scope([CREATE])
                    left = self.settle(reply(part, line))
                    self.assertEqual(left, [CREATE],
                                     "a tool name without the phrase cleared the row outside Input Needed, in %s"
                                     % part)

    def test_b6_the_name_and_the_phrase_on_different_lines_clear_nothing(self):
        self.check_scope([CREATE])
        text = reply("Done", "`%s` was refused by auto mode." % CREATE) + "\nThe refusal was right.\n"
        left = self.settle(text)
        self.assertEqual(left, [CREATE], "a name and the phrase on different lines cleared the row")

    def test_b7_a_built_in_tool_needs_its_backticked_name(self):
        with self.subTest("backticked"):
            self.fresh_config()
            self.check_scope([BASH])
            left = self.settle(reply("Done", "`Bash` refusal was right; the call stays refused."))
            self.assertEqual(left, [], "the backticked name of Bash with the phrase, outside Input Needed, "
                                       "did not clear the row")
        with self.subTest("bare word"):
            self.fresh_config()
            self.check_scope([BASH])
            left = self.settle(reply("Done", "Bash output was empty; the refusal was right."))
            self.assertEqual(left, [BASH], "a bare Bash, an English word, cleared the row")

    def test_b8_the_phrase_must_follow_its_name_directly(self):
        # Each reply names a tool with the phrase, but not in the one form the rule allows: the phrase directly
        # after the name, with an optional colon between them.
        cases = (
            ("the phrase follows the first name only", [CREATE, INTERRUPT],
             "`%s` refusal was right; `%s` stays refused." % (CREATE, INTERRUPT), [INTERRUPT]),
            ("a word sits between the name and the phrase", [CREATE],
             "`%s`: not sure the refusal was right" % CREATE, [CREATE]),
            ("the phrase is hedged after the name", [CREATE],
             "`%s`: the refusal is right or wrong" % CREATE, [CREATE]),
            ("the reply quotes the guard's own block reason", [CREATE],
             "OTHER the guard said: " + report_guard.refusal_reason([CREATE]), [CREATE]),
        )
        for label, tools, line, expect in cases:
            with self.subTest(label):
                self.fresh_config()
                self.check_scope(tools)
                left = self.settle(reply("Done", line))
                self.assertEqual(left, expect, "%s cleared a row the direct form does not clear" % label)

    def test_b9_the_phrase_directly_after_the_name_clears(self):
        for line in ("`%s`: refusal was right" % CREATE, "`%s` refusal is right" % CREATE):
            with self.subTest(line=line):
                self.check_scope([CREATE])
                left = self.settle(reply("Done", line))
                self.assertEqual(left, [], "the phrase directly after the name did not clear the row: %r" % line)
                self.assertFalse(os.path.exists(self.refusals_file()), "the row was cleared but the file stayed")

    def test_b10_a_hedge_in_the_clause_keeps_the_row(self):
        # A hedge in the clause, after the phrase or before the name, is no verdict that the refusal was right.
        cases = (
            ("or wrong after the phrase", "`%s`: refusal was right or wrong" % CREATE),
            ("a question after the phrase", "`%s`: refusal was right?" % CREATE),
            ("unsure before the name, in the clause", "If unsure, `%s`: refusal was right" % CREATE),
        )
        for label, line in cases:
            with self.subTest(label):
                self.check_scope([CREATE])
                left = self.settle(reply("Done", line))
                self.assertEqual(left, [CREATE], "a hedged line cleared the row: %s" % label)

    def test_b11_a_hedge_in_an_earlier_sentence_does_not_keep_the_row(self):
        self.check_scope([CREATE])
        left = self.settle(reply("Done", "Unsure. `%s`: refusal was right" % CREATE))
        self.assertEqual(left, [], "a hedge in an earlier sentence kept the row")
        self.assertFalse(os.path.exists(self.refusals_file()), "the row was cleared but the file stayed")

    # ---- an agent's row: an agent record's tool_use_id, or an agent_id that an orchestrator record does not share

    def test_r1_an_agent_id_row_stays_when_its_tool_use_is_in_the_orchestrator_transcript(self):
        transcript = self.transcript([HUMAN, tool_use("toolu_orch_r1", CREATE), tool_use("toolu_orch_ctl", INTERRUPT)])
        self.write_rows([{"tool_name": CREATE, "tool_use_id": "toolu_orch_r1", "agent_id": AGENT_ID},
                         {"tool_name": INTERRUPT, "tool_use_id": "toolu_orch_ctl"}])
        self.assertEqual(self.pending_tools(), [CREATE, INTERRUPT], "scope: the fixture file does not hold the rows")
        left = self.settle(NEUTRAL, transcript)
        self.assertEqual(left, [CREATE, INTERRUPT],
                         "a row with agent_id was dropped though its tool_use is in the orchestrator transcript")

    def test_r2_a_row_whose_tool_use_is_only_in_a_sidechain_is_dropped(self):
        transcript = self.transcript([HUMAN, tool_use("toolu_orch_ctl", INTERRUPT),
                                      tool_use("toolu_side_r2", CREATE, sidechain=True)])
        self.write_rows([{"tool_name": CREATE, "tool_use_id": "toolu_side_r2"},
                         {"tool_name": INTERRUPT, "tool_use_id": "toolu_orch_ctl"}])
        self.assertEqual(self.pending_tools(), [CREATE, INTERRUPT], "scope: the fixture file does not hold the rows")
        left = self.settle(NEUTRAL, transcript)
        self.assertEqual(left, [INTERRUPT], "a refusal whose tool_use is only in a sidechain still blocked the Stop")

    def test_r3_a_row_whose_tool_use_is_in_the_orchestrator_transcript_still_blocks(self):
        transcript = self.transcript([HUMAN, tool_use("toolu_orch_r3", CREATE)])
        self.write_rows([{"tool_name": CREATE, "tool_use_id": "toolu_orch_r3"}])
        self.assertEqual(self.pending_tools(), [CREATE], "scope: the fixture file does not hold the row")
        left = self.settle(NEUTRAL, transcript)
        self.assertEqual(left, [CREATE], "an orchestrator refusal whose tool_use is in the transcript was dropped")

    def test_r4_a_row_with_no_tool_use_id_still_blocks(self):
        self.write_refusals([CREATE])
        self.assertEqual(self.pending_tools(), [CREATE], "scope: the fixture file does not hold the row")
        left = self.settle(NEUTRAL)
        self.assertEqual(left, [CREATE], "an old row with no tool_use_id was dropped")

    def test_r5_a_tool_use_id_found_in_no_transcript_keeps_the_row(self):
        # Lane ruling, 17:38 CST: a tool_use_id found in no transcript keeps its row.
        transcript = self.transcript([HUMAN, tool_use("toolu_orch_ctl", INTERRUPT)])
        self.write_rows([{"tool_name": CREATE, "tool_use_id": "toolu_gone_r5"},
                         {"tool_name": INTERRUPT, "tool_use_id": "toolu_orch_ctl"}])
        self.assertEqual(self.pending_tools(), [CREATE, INTERRUPT], "scope: the fixture file does not hold the rows")
        left = self.settle(NEUTRAL, transcript)
        self.assertEqual(left, [CREATE, INTERRUPT],
                         "a row whose tool_use_id is in no transcript was dropped, so an unflushed refusal is lost")

    def test_r6_an_unreadable_transcript_keeps_the_block(self):
        self.write_rows([{"tool_name": CREATE, "tool_use_id": "toolu_orch_r6"}])
        self.assertEqual(self.pending_tools(), [CREATE], "scope: the fixture file does not hold the row")
        missing = os.path.join(self.scratch, "no-such-transcript.jsonl")
        left = self.settle(NEUTRAL, missing)
        self.assertEqual(left, [CREATE], "an unreadable transcript dropped a refusal row")

    def test_r7_a_row_whose_tool_use_id_is_only_in_an_agent_file_is_dropped(self):
        transcript = self.transcript([HUMAN, tool_use("toolu_orch_r7", INTERRUPT)])
        agent = self.agent_file(transcript, "agent-x", [tool_use("toolu_agent_r7", CREATE, sidechain=True)])
        self.write_rows([{"tool_name": CREATE, "tool_use_id": "toolu_agent_r7"},
                         {"tool_name": INTERRUPT, "tool_use_id": "toolu_orch_r7"}])
        self.assertTrue(os.path.isfile(agent), "scope: the agent file was not written beside the transcript")
        self.assertEqual(self.pending_tools(), [CREATE, INTERRUPT], "scope: the fixture file does not hold the rows")
        left = self.settle(NEUTRAL, transcript)
        self.assertEqual(left, [INTERRUPT],
                         "a row whose tool_use_id is only in an agent file still blocked the Stop")

    def test_r8_an_id_in_both_an_orchestrator_record_and_a_sidechain_record_stays(self):
        transcript = self.transcript([HUMAN, tool_use("toolu_both_r8", CREATE),
                                      tool_use("toolu_both_r8", CREATE, sidechain=True)])
        self.write_rows([{"tool_name": CREATE, "tool_use_id": "toolu_both_r8"}])
        self.assertEqual(self.pending_tools(), [CREATE], "scope: the fixture file does not hold the row")
        left = self.settle(NEUTRAL, transcript)
        self.assertEqual(left, [CREATE], "a row whose tool_use_id is also an orchestrator record was dropped")

    def test_r9_an_agent_id_row_whose_id_is_in_no_transcript_is_dropped(self):
        transcript = self.transcript([HUMAN, tool_use("toolu_orch_r9", INTERRUPT)])
        self.write_rows([{"tool_name": CREATE, "tool_use_id": "toolu_gone_r9", "agent_id": AGENT_ID},
                         {"tool_name": INTERRUPT}])
        self.assertEqual(self.pending_tools(), [CREATE, INTERRUPT], "scope: the fixture file does not hold the rows")
        left = self.settle(NEUTRAL, transcript)
        self.assertEqual(left, [INTERRUPT],
                         "an agent_id row whose tool_use_id is in no transcript still blocked the Stop")

    def test_r10_an_agent_id_row_with_no_tool_use_id_is_dropped(self):
        transcript = self.transcript([HUMAN, tool_use("toolu_orch_r10", INTERRUPT)])
        self.write_rows([{"tool_name": CREATE, "agent_id": AGENT_ID}, {"tool_name": INTERRUPT}])
        self.assertEqual(self.pending_tools(), [CREATE, INTERRUPT], "scope: the fixture file does not hold the rows")
        left = self.settle(NEUTRAL, transcript)
        self.assertEqual(left, [INTERRUPT], "an agent_id row with no tool_use_id still blocked the Stop")

    def test_r11_an_agent_id_row_with_an_unreadable_transcript_is_dropped(self):
        self.write_rows([{"tool_name": CREATE, "tool_use_id": "toolu_orch_r11", "agent_id": AGENT_ID},
                         {"tool_name": INTERRUPT}])
        self.assertEqual(self.pending_tools(), [CREATE, INTERRUPT], "scope: the fixture file does not hold the rows")
        missing = os.path.join(self.scratch, "no-such-transcript.jsonl")
        left = self.settle(NEUTRAL, missing)
        self.assertEqual(left, [INTERRUPT], "an agent_id row with an unreadable transcript still blocked the Stop")


if __name__ == "__main__":
    unittest.main()
