#!/usr/bin/env python3
"""The pick guard finds this repo's page writer by its triage tag, not by a fixed session id (the roadmap step
page-writer-key-follows-tag; its cases are in lint/test_page_writer_tag.py).

A cloud session that asks a question has no meta/page read in its transcript. question_problem then takes the page
writer from the one session tagged cs-build:triage for this repo, read from the transcript's get_session and
list_sessions records. The extras key `page-writer` is not the writer.

These cases read this repo's real .claude/layout-extras.json, at the root the guard finds from lint/ (report_guard's
repo_root). No fixture stands in for it. The run folder, the send and transcript helpers come from
lint/test_report_guard.py, the one home, listing included. Run with:

    python3 lint/test_report_guard_page_writer.py -v
"""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_report_guard as trg  # noqa: E402  the run folder, the send and transcript helpers, the guard (one home)
import test_report_guard_stalled as trs  # noqa: E402  the triage session's own record and remote id (one home)

layout = trg.RG.layout  # the module the guard reads the extras key from, so this file reads the same key
OTHER_ID = "session_notthewriter"  # a delivered send's target that is not this repo's page writer
PARENT_ID = "session_parent1"  # the parent id a triage session's own record names
REMOTE_ENV = "CLAUDE_CODE_REMOTE_SESSION_ID"  # set only in a lane; unset here, so the check reads an owner-facing session


def setUpModule():
    trg.setUpModule()  # the run folder, CLAUDE_CONFIG_DIR and the model stub, set as test_report_guard sets them


def tearDownModule():
    trg.tearDownModule()


class PageWriterTests(trg.SameTurnWriter, unittest.TestCase):
    """This repo's triage tag names a page writer that the pick check can match a same-turn send against. The send
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

    def triage_listing(self, root, session_id):
        """A list_sessions result that names `session_id` as this repo's triage session. The repo name is checked first."""
        repo = layout.repo_name(root)
        self.assertIsNotNone(repo, "scope: this checkout has no GitHub origin, so no cs-repo tag can name it")
        return self.listing([(session_id, self.session_tags("triage", repo))])

    def test_rw_pick_check_does_not_read_the_fixed_key(self):
        # Catches: the pick check taking the writer from this repo's extras key, the fixed id that goes stale when
        # triage gets a new session. The triage listing alone must carry the writer, so the key is not read.
        root, _writer = self.repo_and_writer()
        acts = [*self.triage_listing(root, self.WRITER), *self.send(session_id=self.WRITER, result=self.DELIVERED)]
        with mock.patch.object(layout, "page_writer_key", return_value=None) as key_read:
            refusal = self.question_refusal(root, acts)
        self.assertEqual(key_read.call_count, 0,
                         "the pick check read the fixed page-writer key %d time(s)" % key_read.call_count)
        self.assertEqual(refusal, "", "a delivered send to the triage session was refused with the key unread: %s" % refusal)

    def test_rw_green_send_to_the_tagged_writer_is_not_refused(self):
        # Catches: a delivered send to this repo's triage session refused as "the page writer is not known to this
        # session", the cloud false alarm, when no meta/page read names the writer.
        root, _writer = self.repo_and_writer()
        acts = [*self.triage_listing(root, self.WRITER), *self.send(session_id=self.WRITER, result=self.DELIVERED)]
        refusal = self.question_refusal(root, acts)
        self.assertEqual(refusal, "", "a delivered send to this repo's triage session was refused: %s" % refusal)

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

    def test_rw_green_triage_send_to_its_parent_is_not_refused(self):
        # Catches: the page writer's question sent to its parent refused, so a fix that makes triage owner-facing
        # drops the parent send the lane rule counted.
        root, _writer = self.repo_and_writer()
        os.environ[REMOTE_ENV] = trs.TRIAGE_ENV
        acts = [*trs.own_record(trs.TRIAGE_ID, ["cs-build:triage"], parent=PARENT_ID),
                *self.send(session_id=PARENT_ID, result=self.DELIVERED)]
        refusal = self.question_refusal(root, acts)
        self.assertEqual(refusal, "", "the page writer's send to its parent was refused: %s" % refusal)

    def test_rw_red_lane_items_write_to_the_page_still_blocks(self):
        # Catches: any lane passing on an items write, so the parent-send rule goes dead for a session that is
        # not the page writer.
        root, _writer = self.repo_and_writer()
        page = layout.waiting_page(root)
        os.environ[REMOTE_ENV] = trs.TRIAGE_ENV
        acts = [*trs.own_record(trs.TRIAGE_ID, ["cs-build:lane"], parent=PARENT_ID), *self.items_write(page)]
        refusal = self.question_refusal(root, acts)
        self.assertNotEqual(refusal, "", "a plain lane's items write passed the pick check")


if __name__ == "__main__":
    unittest.main()
