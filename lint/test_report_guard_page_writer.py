#!/usr/bin/env python3
"""The pick guard finds this repo's page writer in the repo's own layout extras (roadmap step pick-guard-cloud-writer).

A cloud session that asks a question has no meta/page read in its transcript. question_problem then takes the page
writer from the repo's extras key `page-writer` (layout.page_writer_key). Without that key, every question this repo's
sessions send to the page writer is refused as "the page writer is not known to this session", though the send was
delivered in the same turn.

The same-turn cases run on a fixture repo whose extras file names FIXTURE_WRITER, so they hold whatever this repo's own
extras file names. The one case that reads this repo's real .claude/layout-extras.json reads only its key. The run
folder, the send and transcript helpers come from lint/test_report_guard.py, the one home. Run with:

    python3 lint/test_report_guard_page_writer.py -v
"""
import json
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

layout = trg.RG.layout  # the module the guard reads the writer key from, so this file reads the same key
FIXTURE_WRITER = "session_pagewriter1"  # the fixture repo's page writer: no live session holds this id
OTHER_ID = "session_notthewriter"  # a delivered send's target that is not the page writer
PARENT_ID = "session_parent1"  # the parent id a triage session's own record names
REMOTE_ENV = "CLAUDE_CODE_REMOTE_SESSION_ID"  # set only in a lane; unset here, so the check reads an owner-facing session


def setUpModule():
    trg.setUpModule()  # the run folder, CLAUDE_CONFIG_DIR and the model stub, set as test_report_guard sets them


def tearDownModule():
    trg.tearDownModule()


class PageWriterTests(trg.SameTurnWriter, unittest.TestCase):
    """A fixture repo whose extras file names FIXTURE_WRITER, checked against a same-turn send. The send is
    SameTurnWriter.send, and the check is question_problem, the function the Stop hook calls."""

    PICK = trg.QuestionReachesPageTests.PICK
    reply = trg.QuestionReachesPageTests.reply

    def setUp(self):
        self.run_dir = tempfile.mkdtemp(dir=trg._ISOLATION["dir"])
        self.addCleanup(shutil.rmtree, self.run_dir, ignore_errors=True)
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop(REMOTE_ENV, None)
        self.root = self.fixture_repo()

    def fixture_repo(self):
        """A repo folder with a git entry, whose extras file names FIXTURE_WRITER and the waiting page of these tests."""
        root = os.path.join(self.run_dir, "repo")
        os.makedirs(os.path.join(root, ".git"))
        os.makedirs(os.path.join(root, ".claude"))
        keys = {"kinds": {}, "page-writer": FIXTURE_WRITER, "waiting-page": trg.QuestionReachesPageTests.PAGE}
        with open(os.path.join(root, ".claude", "layout-extras.json"), "w", encoding="utf-8") as handle:
            json.dump(keys, handle)
        return root

    def real_root(self):
        """This repo's root, the folder above lint/. Its extras file is read as it stands, and only its key is read."""
        root = os.path.dirname(HERE)
        self.assertTrue(os.path.isfile(os.path.join(root, ".claude", "layout-extras.json")),
                        "scope: this repo has no .claude/layout-extras.json")
        return root

    def repo_and_writer(self):
        """The fixture repo's root and the page writer its extras file names. The key is read back first, so a
        writer read says nothing about another file."""
        writer = layout.page_writer_key(self.root)
        self.assertEqual(writer, FIXTURE_WRITER, "scope: the fixture's extras file does not name its page writer")
        return self.root, writer

    def items_write(self, url):
        """An ArtifactData set to the items collection of the page at `url`: the write a question makes on the page."""
        return self.call("ArtifactData", {"action": "set", "collection": "items", "url": url, "doc_id": "q1", "data": {}})

    def claude_artifacts_items(self, name, url):
        """A claude-artifacts db call on the items collection of the page at `url`. Its input's action says update, so
        only the tool name's verb tells a read from a write."""
        return self.call(name, {"action": "update", "collection": "items", "url": url, "doc_id": "q1", "data": {}})

    def question_refusal(self, root, acts):
        """The refusal question_problem gives a pick asked after `acts` in the same turn, judged from `root`."""
        records = [trg.human("decide"), *acts, trg.assistant_text(self.reply(self.PICK))]
        hook = {"hook_event_name": "Stop", "transcript_path": trg.write_transcript(records, self.run_dir),
                "stop_hook_active": False, "cwd": root}
        refusal, _note = trg.RG.question_problem(records, records[1:], self.reply(self.PICK), hook)
        return refusal

    def test_rw_key_is_none_for_this_repo(self):
        # Catches: this repo's layout-extras.json naming a page-writer session, which has gone stale. A question sent
        # to it comes back undelivered, and the Stop check blocks on that. The owner ruled the page writer N/A
        # (2026-11-25 20:32 CST, "page writer should be N/A atm"), so the key names no writer.
        writer = layout.page_writer_key(self.real_root())
        self.assertIsNone(writer, "this repo's layout-extras.json names a page writer, but the page writer is N/A: %r" % writer)

    def test_rw_green_send_to_the_key_writer_is_not_refused(self):
        # Catches: a delivered send to the page writer refused as "the page writer is not known to this session" when
        # the extras file names that writer, the cloud false alarm.
        root, writer = self.repo_and_writer()
        refusal = self.question_refusal(root, self.send(session_id=writer, result=self.DELIVERED))
        self.assertEqual(refusal, "", "a delivered send to the page writer was refused: %s" % refusal)

    def test_rw_red_send_to_another_id_still_blocks(self):
        # Catches: the writer key passing any delivered send, so a question sent to a session that is not the page
        # writer counts as one that reached the page.
        root, writer = self.repo_and_writer()
        self.assertNotEqual(OTHER_ID, writer, "scope: the other id is the page writer, so the case proves nothing")
        refusal = self.question_refusal(root, self.send(session_id=OTHER_ID, result=self.DELIVERED))
        self.assertNotEqual(refusal, "", "a delivered send to a session that is not the page writer passed the pick check")

    def test_rw_green_triage_items_write_to_the_page_is_not_refused(self):
        # Catches: the page writer's own question, an items write to the waiting page, refused as a lane's question
        # sent to no parent, because its own record names a parent id. The record tags the session as triage.
        root, _writer = self.repo_and_writer()
        page = layout.waiting_page(root)
        self.assertTrue(str(page).startswith("https://"), "scope: the fixture's extras file names no waiting page url: %r" % page)
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

    def test_rw_red_claude_artifacts_db_get_is_no_items_write(self):
        # Catches: the tool name's verb dropped at items_write, so a claude-artifacts db_get whose input says update
        # counts as the page writer's write of an item. The control is the same input under db_write, which must pass
        # first: it shows the call reaches the items check at all.
        root, _writer = self.repo_and_writer()
        page = layout.waiting_page(root)
        self.assertTrue(str(page).startswith("https://"), "scope: the fixture's extras file names no waiting page url: %r" % page)
        control = self.question_refusal(root, self.claude_artifacts_items("mcp__claude-artifacts__db_write", page))
        self.assertEqual(control, "", "scope: a claude-artifacts db_write of items was refused, so the read case proves nothing: %s" % control)
        refusal = self.question_refusal(root, self.claude_artifacts_items("mcp__claude-artifacts__db_get", page))
        self.assertNotEqual(refusal, "", "a claude-artifacts db_get of items counted as the page writer's items write")


if __name__ == "__main__":
    unittest.main()
