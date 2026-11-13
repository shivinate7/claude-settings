#!/usr/bin/env python3
"""The pick guard finds this repo's page writer in the repo's own layout extras (roadmap step pick-guard-cloud-writer).

A cloud session that asks a question has no meta/page read in its transcript. question_problem then takes the page
writer from the repo's extras key `page-writer` (layout.page_writer_key). Without that key, every question this repo's
sessions send to the page writer is refused as "the page writer is not known to this session", though the send was
delivered in the same turn.

These cases read this repo's real .claude/layout-extras.json, at the root the guard finds from lint/ (report_guard's
repo_root). No fixture stands in for it. The run folder, the send and transcript helpers come from
lint/test_report_guard.py, the one home. Run with:

    python3 lint/test_report_guard_repo_writer.py -v
"""
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_report_guard as trg  # noqa: E402  the run folder, the send and transcript helpers, the guard (one home)
import test_report_guard_stalled as trs  # noqa: E402  the triage session's own record and remote id (one home)

layout = trg.RG.layout  # the module the guard reads the writer key from, so this file reads the same key
SESSION_ID = re.compile(r"session_[A-Za-z0-9]+")
OTHER_ID = "session_notthewriter"  # a delivered send's target that is not this repo's page writer
PARENT_ID = "session_parent1"  # the parent id a triage session's own record names
REMOTE_ENV = "CLAUDE_CODE_REMOTE_SESSION_ID"  # set only in a lane; unset here, so the check reads an owner-facing session


def setUpModule():
    trg.setUpModule()  # the run folder, CLAUDE_CONFIG_DIR and the model stub, set as test_report_guard sets them


def tearDownModule():
    trg.tearDownModule()


class RepoWriterTests(trg.SameTurnWriter, unittest.TestCase):
    """This repo's extras file names a page writer that the pick check can match a same-turn send against. The send
    is SameTurnWriter.send, and the check is question_problem, the function the Stop hook calls."""

    PICK = trg.QuestionReachesPageTests.PICK
    reply = trg.QuestionReachesPageTests.reply

    def setUp(self):
        self.run_dir = tempfile.mkdtemp(dir=trg._ISOLATION["dir"])
        self.addCleanup(shutil.rmtree, self.run_dir, ignore_errors=True)
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop(REMOTE_ENV, None)

    def repo_and_writer(self):
        """This repo's root and the page writer its extras file names. The scope is checked first: the root must
        hold the extras file, else a writer read says nothing about this repo."""
        root = trg.RG.repo_root(HERE)
        self.assertIsNotNone(root, "scope: no git entry above lint/, so the guard finds no repo root")
        self.assertTrue(os.path.isfile(os.path.join(root, ".claude", "layout-extras.json")),
                        "scope: this repo has no .claude/layout-extras.json")
        return root, layout.page_writer_key(root)

    def items_write(self, url):
        """An ArtifactData set to the items collection of the page at `url`: the write a question makes on the page."""
        return self.call("ArtifactData", {"action": "set", "collection": "items", "url": url, "doc_id": "q1", "data": {}})

    def question_refusal(self, root, acts):
        """The refusal question_problem gives a pick asked after `acts` in the same turn, judged from `root`."""
        records = [trg.human("decide"), *acts, trg.assistant_text(self.reply(self.PICK))]
        hook = {"hook_event_name": "Stop", "transcript_path": trg.write_transcript(records, self.run_dir),
                "stop_hook_active": False, "cwd": root}
        refusal, _note = trg.RG.question_problem(records, records[1:], self.reply(self.PICK), hook)
        return refusal

    def test_rw_key_names_a_session_id_for_this_repo(self):
        # Catches: this repo's layout-extras.json with no page-writer key, or with a blank, parent-alias or non-session
        # value, so the pick check has no writer to match a same-turn send against.
        _root, writer = self.repo_and_writer()
        self.assertIsNotNone(writer, "this repo's layout-extras.json names no usable page-writer key")
        self.assertNotIn(writer, layout.PARENT_TARGETS, "the page-writer key names a parent alias, which reaches no one")
        self.assertIsNotNone(SESSION_ID.fullmatch(writer), "the page-writer key is not a session id: %r" % writer)

    def test_rw_green_send_to_the_key_writer_is_not_refused(self):
        # Catches: a delivered send to this repo's page writer refused as "the page writer is not known to this
        # session" when the repo's extras file names that writer, the cloud false alarm.
        root, writer = self.repo_and_writer()
        self.assertIsNotNone(writer, "this repo's layout-extras.json names no page writer, so there is no id to send to")
        refusal = self.question_refusal(root, self.send(session_id=writer, result=self.DELIVERED))
        self.assertEqual(refusal, "", "a delivered send to this repo's page writer was refused: %s" % refusal)

    def test_rw_red_send_to_another_id_still_blocks(self):
        # Catches: the writer key passing any delivered send, so a question sent to a session that is not the page
        # writer counts as one that reached the page.
        root, writer = self.repo_and_writer()
        self.assertNotEqual(OTHER_ID, writer, "scope: the other id is this repo's page writer, so the case proves nothing")
        refusal = self.question_refusal(root, self.send(session_id=OTHER_ID, result=self.DELIVERED))
        self.assertNotEqual(refusal, "", "a delivered send to a session that is not the page writer passed the pick check")

    def test_rw_green_triage_items_write_to_the_page_is_not_refused(self):
        # Catches: the page writer's own question, an items write to this repo's waiting page, refused as a lane's
        # question sent to no parent, because its own record names a parent id. The record tags the session as triage.
        root, _writer = self.repo_and_writer()
        page = layout.waiting_page(root)
        self.assertTrue(str(page).startswith("https://"), "scope: this repo's extras file names no waiting page url: %r" % page)
        os.environ[REMOTE_ENV] = trs.TRIAGE_ENV  # the session is the triage session: its own record is read from the transcript
        acts = [*trs.own_record(trs.TRIAGE_ID, ["cs-build:triage"], parent=PARENT_ID), *self.items_write(page)]
        refusal = self.question_refusal(root, acts)
        self.assertEqual(refusal, "", "the page writer's items write to the waiting page was refused: %s" % refusal)


if __name__ == "__main__":
    unittest.main()
