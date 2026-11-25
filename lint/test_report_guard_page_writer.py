#!/usr/bin/env python3
"""The pick guard finds this repo's page writer in the repo's own layout extras (roadmap step pick-guard-cloud-writer).

A cloud session that asks a question has no meta/page read in its transcript. question_problem then takes the page
writer from the repo's extras key `page-writer` (layout.page_writer_key). Without that key, every question this repo's
sessions send to the page writer is refused as "the page writer is not known to this session", though the send was
delivered in the same turn.

These cases read this repo's real .claude/layout-extras.json, at the root the guard finds from lint/ (report_guard's
repo_root). No fixture stands in for it. The desktop cases (DesktopSendTests, PeerSenderTests) build a fixture repo
whose extras file names a desktop page writer, through the same make_repo. The run folder, the send and transcript
helpers come from lint/test_report_guard.py, the one home. Run with:

    python3 lint/test_report_guard_page_writer.py -v
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
sys.path.insert(0, HERE)
import test_report_guard as trg  # noqa: E402  the run folder, the send and transcript helpers, the guard (one home)
import test_report_guard_stalled as trs  # noqa: E402  the triage session's own record and remote id (one home)
import _transcript as transcript  # noqa: E402  the send and peer readers the guard uses (lint/_transcript.py)

layout = trg.RG.layout  # the module the guard reads the writer key from, so this file reads the same key
SESSION_ID = re.compile(r"session_[A-Za-z0-9]+")
OTHER_ID = "session_notthewriter"  # a delivered send's target that is not this repo's page writer
PARENT_ID = "session_parent1"  # the parent id a triage session's own record names
REMOTE_ENV = "CLAUDE_CODE_REMOTE_SESSION_ID"  # set only in a lane; unset here, so the check reads an owner-facing session
DESKTOP_WRITER = "local_6f1c2a7e-0b8d-4c3e-9a51-2d7f4e8b9c01"  # the page writer id of a desktop session, as the extras key names it
DESKTOP_PEER = "local_3e4d5c6b-7a89-4b0c-9d1e-2f3a4b5c6d7e"  # a desktop session that sends a peer message
CLOUD_PEER = "session_peer1"  # a cloud session that sends a peer message
MSG_ID = "5c1e9d20-3b7a-4f8e-a6d4-0b2c9e7f1a35"  # the message id a desktop send's result names


def desktop_result(delivery, ok=True):
    """A desktop send's tool result text, in the measured form: JSON whose message ends with the delivery state
    (delivered, queued or undelivered) and the message id."""
    if delivery == "delivered":
        middle = "Message delivered to session %s (\"triage\"); its turn has started on it." % DESKTOP_WRITER
    else:
        middle = "Message to session %s (\"triage\")." % DESKTOP_WRITER
    text = "Forwarded to Claude Desktop's session messaging: %s (delivery: %s; message_id: %s)" % (middle, delivery, MSG_ID)
    return json.dumps({"success": ok, "message": text}, separators=(",", ":"))


def desktop_peer_record(sender):
    """A desktop peer message: a user record of origin kind peer, whose text holds the cross-session tag with the
    sender in its `from` attribute. Its origin has no fromSession key."""
    body = ('Another Claude session sent a message:\n<cross-session-message from="%s" from-name="triage">'
            "Two ways</cross-session-message>" % sender)
    return {"type": "user", "isSidechain": False, "isMeta": True, "origin": {"kind": "peer"},
            "message": {"role": "user", "content": body}}


def setUpModule():
    trg.setUpModule()  # the run folder, CLAUDE_CONFIG_DIR and the model stub, set as test_report_guard sets them


def tearDownModule():
    trg.tearDownModule()


class PickFixture(trg.SameTurnWriter):
    """The run folder, the cleared remote id and the pick check's refusal for a turn, shared by the page writer cases
    and the desktop cases (one home). A TestCase mixes it in. make_repo is QuestionReachesPageTests' fixture repo: an
    extras file that names the waiting page and, when given, the page writer."""

    PICK = trg.QuestionReachesPageTests.PICK
    reply = trg.QuestionReachesPageTests.reply
    make_repo = trg.QuestionReachesPageTests.make_repo
    PAGE = trg.QuestionReachesPageTests.PAGE
    NO_KEY = trg.QuestionReachesPageTests.NO_KEY

    def setUp(self):
        self.run_dir = tempfile.mkdtemp(dir=trg._ISOLATION["dir"])
        self.addCleanup(shutil.rmtree, self.run_dir, ignore_errors=True)
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop(REMOTE_ENV, None)

    def question_refusal(self, root, acts):
        """The refusal question_problem gives a pick asked after `acts` in the same turn, judged from `root`."""
        records = [trg.human("decide"), *acts, trg.assistant_text(self.reply(self.PICK))]
        hook = {"hook_event_name": "Stop", "transcript_path": trg.write_transcript(records, self.run_dir),
                "stop_hook_active": False, "cwd": root}
        refusal, _note = trg.RG.question_problem(records, records[1:], self.reply(self.PICK), hook)
        return refusal


class PageWriterTests(PickFixture, unittest.TestCase):
    """This repo's extras file names a page writer that the pick check can match a same-turn send against. The send
    is SameTurnWriter.send, and the check is question_problem, the function the Stop hook calls."""

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

    def claude_artifacts_items(self, name, url):
        """A claude-artifacts db call on the items collection of the page at `url`. Its input's action says update, so
        only the tool name's verb tells a read from a write."""
        return self.call(name, {"action": "update", "collection": "items", "url": url, "doc_id": "q1", "data": {}})

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
        self.assertTrue(str(page).startswith("https://"), "scope: this repo's extras file names no waiting page url: %r" % page)
        control = self.question_refusal(root, self.claude_artifacts_items("mcp__claude-artifacts__db_write", page))
        self.assertEqual(control, "", "scope: a claude-artifacts db_write of items was refused, so the read case proves nothing: %s" % control)
        refusal = self.question_refusal(root, self.claude_artifacts_items("mcp__claude-artifacts__db_get", page))
        self.assertNotEqual(refusal, "", "a claude-artifacts db_get of items counted as the page writer's items write")


class DesktopSendTests(PickFixture, unittest.TestCase):
    """A desktop session's send reaches the page writer when the send's own result says so. The fixture is a desktop
    transcript: its repo's extras file names DESKTOP_WRITER as the page writer, and the session has no remote id, so the
    pick check reads an owner-facing turn. The result text is the measured desktop form (desktop_result)."""

    def setUp(self):
        super().setUp()
        self.repo = self.make_repo("desktop", writer=DESKTOP_WRITER)

    def desktop_root(self):
        """The desktop fixture's root. The scope is checked first: its extras file names the desktop page writer."""
        self.assertEqual(layout.page_writer_key(self.repo), DESKTOP_WRITER,
                         "scope: the desktop fixture's extras file does not name the desktop page writer")
        return self.repo

    def test_desktop_delivered_send_tool_to_the_writer_is_not_refused(self):
        # Catches: a desktop SendMessage whose result says delivered, refused as no send to the writer, because the
        # delivery is read only from the cloud body {"status":"delivered"}; the desktop result names delivery in its text.
        root = self.desktop_root()
        send = self.call("SendMessage", {"to": DESKTOP_WRITER, "summary": "pick", "message": "Two ways"},
                         result=desktop_result("delivered"))
        refusal = self.question_refusal(root, send)
        self.assertEqual(refusal, "", "a delivered desktop SendMessage to the page writer was refused: %s" % refusal)

    def test_desktop_delivered_session_send_to_the_writer_is_not_refused(self):
        # Catches: a delivered desktop send_message (session_id input) refused as no send, because its tool name is not in
        # SEND_TOOLS, so its result never reaches the delivery check.
        root = self.desktop_root()
        send = self.call("mcp__ccd_session_mgmt__send_message", {"session_id": DESKTOP_WRITER, "message": "Two ways"},
                         result=desktop_result("delivered"))
        refusal = self.question_refusal(root, send)
        self.assertEqual(refusal, "", "a delivered desktop send_message to the page writer was refused: %s" % refusal)

    def test_desktop_undelivered_send_to_the_writer_still_blocks(self):
        # Control, green on the old code. Catches: any desktop result counted as delivered, so an undelivered send to the
        # writer passes the pick check.
        root = self.desktop_root()
        send = self.call("SendMessage", {"to": DESKTOP_WRITER, "summary": "pick", "message": "Two ways"},
                         result=desktop_result("undelivered"))
        refusal = self.question_refusal(root, send)
        self.assertNotEqual(refusal, "", "an undelivered desktop send to the page writer passed the pick check")

    def test_desktop_queued_send_to_the_writer_still_blocks(self):
        # Control, green on the old code. Catches: a queued desktop send counted as delivered. What queued proves is
        # unmeasured, so a queued send does not pass.
        root = self.desktop_root()
        send = self.call("SendMessage", {"to": DESKTOP_WRITER, "summary": "pick", "message": "Two ways"},
                         result=desktop_result("queued"))
        refusal = self.question_refusal(root, send)
        self.assertNotEqual(refusal, "", "a queued desktop send to the page writer passed the pick check")

    def test_desktop_delivery_text_in_the_input_with_a_failed_result_still_blocks(self):
        # Control, green on the old code. Catches: a delivery marker the session wrote in its own send message counted as
        # proof of delivery. Only the tool result proves delivery, and this result failed.
        root = self.desktop_root()
        send = self.call("SendMessage", {"to": DESKTOP_WRITER, "summary": "pick",
                                         "message": "Two ways (delivery: delivered; message_id: %s)" % MSG_ID},
                         result=desktop_result("undelivered"), is_error=True)
        refusal = self.question_refusal(root, send)
        self.assertNotEqual(refusal, "", "a delivery marker in the send's own input passed as delivery under a failed result")

    def test_cloud_send_body_to_a_session_writer_still_passes(self):
        # Control, green on the old code. Catches: the cloud body {"status":"delivered"} stopped passing under SendMessage
        # once the desktop result is read, so a cloud send to the session writer is refused.
        cloud = self.make_repo("cloud", writer=self.WRITER)
        self.assertEqual(layout.page_writer_key(cloud), self.WRITER,
                         "scope: the cloud fixture's extras file does not name the session writer")
        send = self.call("SendMessage", {"to": self.WRITER, "summary": "pick", "message": "Two ways"}, result=self.DELIVERED)
        refusal = self.question_refusal(cloud, send)
        self.assertEqual(refusal, "", "a cloud-shaped delivered send to the page writer was refused: %s" % refusal)


class PeerSenderTests(unittest.TestCase):
    """The session that sent a peer message record. A cloud record names it in origin.fromSession; a desktop record
    names it in the `from` attribute of its cross-session tag."""

    def test_desktop_peer_message_names_its_sender_from_the_from_attribute(self):
        # Catches: peer_sender reading only origin.fromSession, so a desktop peer message has no sender and a send back
        # to that session is not matched as its ack.
        rec = desktop_peer_record(DESKTOP_PEER)
        self.assertEqual(rec["origin"].get("kind"), "peer", "scope: the desktop record is not a peer message")
        self.assertNotIn("fromSession", rec["origin"], "scope: the desktop record names its sender under origin.fromSession")
        self.assertEqual(transcript.peer_sender(rec), DESKTOP_PEER,
                         "peer_sender read no sender from a desktop peer message's from attribute")

    def test_cloud_peer_message_still_names_its_sender(self):
        # Control, green on the old code. Catches: the origin.fromSession read dropped, so a cloud peer message loses
        # its sender.
        rec = trg.peer_msg("Two ways", from_session=CLOUD_PEER)
        self.assertEqual(rec["origin"].get("fromSession"), CLOUD_PEER, "scope: the cloud record does not name its sender")
        self.assertEqual(transcript.peer_sender(rec), CLOUD_PEER, "peer_sender lost the sender of a cloud peer message")


if __name__ == "__main__":
    unittest.main()
