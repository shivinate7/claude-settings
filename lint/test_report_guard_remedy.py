#!/usr/bin/env python3
"""Owner-safe block reasons for report_guard.py (decision guard-remedy-not-to-owner).

A Stop block reason reaches the owner in chat. So each reason opens with one plain line that names its
check, cites the record guard-remedy-not-to-owner, and holds no session instruction. Each block path is
one fixture, run through report_guard as a Stop hook. The transcript records and the guard runner come
from lint/test_report_guard.py. The repo fixtures and the model stub come from hooks/test_call_judge.py.

Case 1 checks three properties of each block reason: 1a holds no session phrase, 1b cites the record, and
1c opens with a sentence that names the check. Case 2 checks that each path still blocks, and that a clean
report is not blocked. Run it as:

    python3 lint/test_report_guard_remedy.py -v
"""
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS = os.path.join(HERE, "..", "hooks")
sys.path.insert(0, HERE)
sys.path.insert(0, HOOKS)
import test_report_guard as trg  # noqa: E402  the transcript records, the guard runner and the run folder
import test_call_judge as tcj  # noqa: E402  the repo fixtures, the waiting-page url and the ruling

CITE = "guard-remedy-not-to-owner"
# The session instructions a block reason must not carry to the owner. Matched case-insensitively.
SESSION_PHRASES = (
    "send it again", "send the report", "post only", "never send", "add the line", "remedy:",
    "do not write it again", "keep the reply", "would reach the owner", "as the next thing you write",
)
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
FIXTURES = ("missing_report", "correction_tail", "done_format", "models", "unstarted", "unvetted",
            "past_ruling", "keys", "pick")


def setUpModule():
    trg.setUpModule()  # the config isolation, the model stub and the run folder, as test_report_guard sets them


def tearDownModule():
    trg.tearDownModule()
    shutil.rmtree(tcj.ROOT, ignore_errors=True)  # the repo fixtures' run folder, which trg does not remove


def landed(reply):
    """A turn that lands a commit, then the reply."""
    return [trg.human("do the task"), trg.tool_use_msg("Bash", {"command": "git commit -m x"}),
            trg.tool_result_msg(), trg.assistant_text(reply)]


def builder_turn(model, reply):
    """A turn that runs a builder on `model`, lands a commit, then the reply."""
    spawn = trg.tool_use_msg("Agent", {"subagent_type": "builder", "model": model, "prompt": "build it"})
    return [trg.human("do the task"), spawn, trg.tool_result_msg(),
            trg.tool_use_msg("Bash", {"command": "git commit -m x"}), trg.tool_result_msg(),
            trg.assistant_text(reply)]


class RemedyReasons(trg.SameTurnWriter, unittest.TestCase):
    PAGE = tcj.PAGE_URL  # the waiting page tcj.make_repo names; the same-turn writer read cites it

    def sent_to_writer(self):
        """The same-turn send to the page writer, so a question's own check stays quiet."""
        return [*self.writer_read(self.WRITER), *self.send(session_id=self.WRITER)]

    def fixture(self, name):
        """(records, env, cwd, word the first sentence must hold) for one block path. Every hook names a cwd
        that tcj.make_repo built, so no check reads this worktree's own records."""
        clean = tcj.make_repo("remedy-clean")
        bare = tcj.make_repo("remedy-bare")
        decided = tcj.make_repo("remedy-decided", decisions={tcj.APPS_SLUG: tcj.APPS_RULING})
        shaped_relay = "> **Done** OTHER read the audit\n" + trg.RELAY + "\n> **Next** wait"
        table = {
            "missing_report": (landed("Committed the change."), {}, clean, "report"),
            "correction_tail": (landed("> **Done** BUILT abc123\n> **Next** ship it, see D12."), {}, clean, "gloss"),
            "done_format": (landed("> **Done** BUILT\n> **Next** ship it"), {}, clean, "done"),
            "models": (builder_turn("sonnet", "> **Done** BUILT abc123 (builder)\n> **Next** Unstarted: none"),
                       {}, clean, "model"),
            "unstarted": (builder_turn("sonnet", "> **Done** BUILT abc123 (builder sonnet)\n> **Next** ship it"),
                          {}, clean, "unstarted"),
            "unvetted": ([trg.human("decide"), *self.sent_to_writer(), trg.assistant_text(shaped_relay)],
                         {"CJ_MODEL_FAIL": "1"}, bare, "unvetted"),
            "past_ruling": ([trg.human("decide"), *self.sent_to_writer(), trg.assistant_text(trg.RELAY)],
                            {"CJ_ANSWER": trg.REFUSE_APPS}, decided, "past-ruling"),
            "keys": ([trg.human("decide"), *self.sent_to_writer(), trg.assistant_text(trg.KEYS_SAME)],
                     {}, bare, "key"),
            "pick": ([trg.human("decide"), trg.assistant_text(trg.RELAY)], {}, bare, "pick"),
        }
        return table[name]

    def run_stop(self, records, env, cwd):
        """Run report_guard as the Stop hook over `records`, and return what it printed (or {})."""
        path = trg.write_transcript(records, tempfile.mkdtemp(dir=trg.RUN_FOLDER))
        hook = {"hook_event_name": "Stop", "transcript_path": path, "stop_hook_active": False, "cwd": cwd}
        with mock.patch.dict(os.environ, env):
            run = trg.run_guard(trg.REPORT_GUARD, hook)
        self.assertEqual(run.returncode, 0, "the guard exited with an error: %s" % run.stderr[-300:])
        return json.loads(run.stdout) if run.stdout.strip() else {}

    def block_reason(self, name):
        records, env, cwd, _ = self.fixture(name)
        out = self.run_stop(records, env, cwd)
        self.assertEqual(out.get("decision"), "block", "%s: the path does not block: %r" % (name, out))
        return out["reason"]

    def check_no_session_phrase(self, name, reason):
        for phrase in SESSION_PHRASES:
            self.assertNotIn(phrase, reason.lower(),
                             "%s: 1a the reason holds the session phrase %r" % (name, phrase))

    def check_cites_record(self, name, reason):
        self.assertIn(CITE, reason, "%s: 1b the reason does not cite %s" % (name, CITE))

    def check_first_sentence(self, name, reason, word):
        first = SENTENCE_END.split(reason, maxsplit=1)[0].lower()
        self.assertIn(word, first,
                      "%s: 1c the first sentence does not name the check (%r): %r" % (name, word, first))
        for phrase in SESSION_PHRASES:
            self.assertNotIn(phrase, first,
                             "%s: 1c the first sentence holds the session phrase %r" % (name, phrase))

    def test_2_clean_report_is_not_blocked(self):
        out = self.run_stop(landed(trg.GOOD_REPORT), {}, tcj.make_repo("remedy-clean"))
        self.assertNotEqual(out.get("decision"), "block", "2 a clean report is blocked: %r" % out)


def _case_1a(name):
    def test(self):
        self.check_no_session_phrase(name, self.block_reason(name))
    return test


def _case_1b(name):
    def test(self):
        self.check_cites_record(name, self.block_reason(name))
    return test


def _case_1c(name):
    def test(self):
        self.check_first_sentence(name, self.block_reason(name), self.fixture(name)[3])
    return test


def _case_2(name):
    def test(self):
        records, env, cwd, _ = self.fixture(name)
        out = self.run_stop(records, env, cwd)
        self.assertEqual(out.get("decision"), "block", "%s: 2 the verdict is no longer block: %r" % (name, out))
    return test


for _name in FIXTURES:
    setattr(RemedyReasons, "test_1a_%s_no_session_phrase" % _name, _case_1a(_name))
    setattr(RemedyReasons, "test_1b_%s_cites_record" % _name, _case_1b(_name))
    setattr(RemedyReasons, "test_1c_%s_first_sentence_names_check" % _name, _case_1c(_name))
    setattr(RemedyReasons, "test_2_%s_still_blocks" % _name, _case_2(_name))


if __name__ == "__main__":
    unittest.main()
