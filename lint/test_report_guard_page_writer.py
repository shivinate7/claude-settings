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
# The two measured wordings of a queued desktop send, each the sentence the app puts after "Message queued for session".
QUEUED_HOLDING = "that session is holding it (a turn is in progress there, or its host or process is away) and runs it when that clears."
QUEUED_BEHIND = "that session accepted it behind other work and runs it when that finishes."
QUEUED_WORDINGS = (("holding", QUEUED_HOLDING), ("behind other work", QUEUED_BEHIND))


def desktop_result(delivery, ok=True, wording=QUEUED_HOLDING):
    """A desktop send's tool result text, in the measured form: JSON whose message ends with the delivery state
    (delivered, queued or undelivered) and the message id. A queued result carries `wording`, one of QUEUED_WORDINGS."""
    if delivery == "delivered":
        middle = "Message delivered to session %s (\"triage\"); its turn has started on it." % DESKTOP_WRITER
    elif delivery == "queued":
        middle = ("Message queued for session %s (\"triage\"): %s Don't wait on it; check back with list_events if the "
                  "outcome matters." % (DESKTOP_WRITER, wording))
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

    def question_refusal(self, root, acts, before=()):
        """The refusal question_problem gives a pick asked after `acts` in the same turn, judged from `root`. `before`
        holds the records of earlier turns, ahead of the turn's own owner message, so the turn starts after them."""
        records = [*before, trg.human("decide"), *acts, trg.assistant_text(self.reply(self.PICK))]
        hook = {"hook_event_name": "Stop", "transcript_path": trg.write_transcript(records, self.run_dir),
                "stop_hook_active": False, "cwd": root}
        refusal, _note = trg.RG.question_problem(records, records[len(before) + 1:], self.reply(self.PICK), hook)
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

    def page_read_repo(self):
        """A desktop fixture with no layout key, so the page read is the only writer a send can match. The scope is
        checked first: the extras file names no page-writer key."""
        repo = self.make_repo("desktop_read")
        self.assertIsNone(layout.page_writer_key(repo), "scope: the page-read fixture's extras file names a page-writer key")
        return repo

    def page_read_sends(self, result):
        """The two desktop send shapes, each with `result` as its tool result, as (label, records): SendMessage names the
        writer by `to`, send_message by session_id."""
        return (("SendMessage", self.call("SendMessage", {"to": DESKTOP_WRITER, "summary": "pick", "message": "Two ways"},
                                          result=result)),
                ("send_message", self.call("mcp__ccd_session_mgmt__send_message",
                                           {"session_id": DESKTOP_WRITER, "message": "Two ways"}, result=result)))

    def page_read_refusal(self, root, send):
        """The refusal a pick gets when the turn's page read names the desktop writer and `send` follows it. The scope is
        checked first: the page read names the desktop writer."""
        acts = [*self.writer_read(DESKTOP_WRITER), *send]
        self.assertEqual(transcript.page_writer_id([trg.human("decide"), *acts]), DESKTOP_WRITER,
                         "scope: the page read does not name the desktop writer")
        return self.question_refusal(root, acts)

    def test_desktop_delivered_send_to_the_page_read_writer_is_not_refused(self):
        # Control, green on the old code. Catches: a delivered desktop send refused on the page-read path, where a send to
        # the writer the page read names is matched on the send alone.
        root = self.page_read_repo()
        for label, send in self.page_read_sends(desktop_result("delivered")):
            with self.subTest(shape=label):
                refusal = self.page_read_refusal(root, send)
                self.assertEqual(refusal, "", "a delivered desktop %s to the writer the page read names was refused: %s"
                                 % (label, refusal))

    def test_desktop_undelivered_send_to_the_page_read_writer_is_refused(self):
        # Catches: the page-read writer path counting any send to the writer on the send alone, so a desktop send whose
        # result says undelivered passes the pick check. The key-writer path already needs delivery.
        root = self.page_read_repo()
        for label, send in self.page_read_sends(desktop_result("undelivered")):
            with self.subTest(shape=label):
                refusal = self.page_read_refusal(root, send)
                self.assertNotEqual(refusal, "", "an undelivered desktop %s to the writer the page read names passed the pick check"
                                    % label)

    def test_desktop_queued_send_to_the_page_read_writer_is_refused(self):
        # Catches: the page-read writer path counting a queued desktop send as delivered. What queued proves is unmeasured,
        # so a queued send to the writer the page read names does not pass.
        root = self.page_read_repo()
        for label, send in self.page_read_sends(desktop_result("queued")):
            with self.subTest(shape=label):
                refusal = self.page_read_refusal(root, send)
                self.assertNotEqual(refusal, "", "a queued desktop %s to the writer the page read names passed the pick check"
                                    % label)

    def test_desktop_input_marker_with_an_undelivered_unmarked_result_is_refused_on_the_key_path(self):
        # Catches: a delivered marker typed in a send's own input counted as delivery when the result says undelivered and
        # is not marked failed. The key-writer path reads the result alone; the failed-result case above is its sibling.
        root = self.desktop_root()
        send = self.call("SendMessage", {"to": DESKTOP_WRITER, "summary": "pick",
                                         "message": "Two ways (delivery: delivered; message_id: %s)" % MSG_ID},
                         result=desktop_result("undelivered"))
        refusal = self.question_refusal(root, send)
        self.assertNotEqual(refusal, "", "a delivery marker in the send's input passed as delivery under an undelivered result")

    def test_desktop_input_marker_with_an_undelivered_unmarked_result_is_refused_on_the_page_read_path(self):
        # Catches: a delivery marker typed in a send's own input passing on the page-read path under an undelivered result
        # that is not marked failed. That path counts a send on the send alone, so this case is red until it reads delivery.
        root = self.page_read_repo()
        send = self.call("SendMessage", {"to": DESKTOP_WRITER, "summary": "pick",
                                         "message": "Two ways (delivery: delivered; message_id: %s)" % MSG_ID},
                         result=desktop_result("undelivered"))
        refusal = self.page_read_refusal(root, send)
        self.assertNotEqual(refusal, "", "a delivery marker in the send's input passed as delivery on the page-read path")

    def checkin(self, recurring=False):
        """The scheduling call that sets a check-in: CronCreate, whose `recurring` input says whether it repeats. A
        one-time check-in has recurring false."""
        return self.call("CronCreate", {"cron": "17 9 25 11 *", "prompt": "Read the target session and verify the send.",
                                        "recurring": recurring}, result="Scheduled.")

    def queued_send(self, marker, is_error=False):
        """A SendMessage to the desktop writer whose result is the queued form, with `marker`, one of QUEUED_WORDINGS."""
        return self.send(to=DESKTOP_WRITER, result=desktop_result("queued", wording=marker), is_error=is_error)

    def test_desktop_queued_send_with_a_same_turn_checkin_counts(self):
        # Catches:a queued desktop send refused although the same turn set a one-time check-in for it
        # (CronCreate with recurring false), so a send the rule counts still reads as not sent.
        root = self.desktop_root()
        for label, marker in QUEUED_WORDINGS:
            with self.subTest(wording=label):
                refusal = self.question_refusal(root, [*self.queued_send(marker), *self.checkin()])
                self.assertEqual(refusal, "", "a queued desktop send with a same-turn one-time check-in was refused: %s" % refusal)

    def test_desktop_queued_send_refusal_tells_the_session_to_checkin_and_verify(self):
        # Catches:the refusal for a queued send with no same-turn check-in saying only that the send
        # was not sent to the page writer, so the session is not told to set a one-time check-in or to read the target
        # session to verify that the send left queued.
        root = self.desktop_root()
        for label, marker in QUEUED_WORDINGS:
            with self.subTest(wording=label):
                refusal = self.question_refusal(root, self.queued_send(marker))
                self.assertNotEqual(refusal, "", "scope: a queued send with no check-in passed, so its refusal text is not read")
                self.assertIn("check-in", refusal, "the refusal for a queued send does not tell the session to set a one-time check-in")
                self.assertIn("verify", refusal, "the refusal for a queued send does not tell the session to verify the send")

    def test_desktop_queued_send_without_a_checkin_is_refused(self):
        # Control, green on the old code. Catches: a queued send counted as sent on its wording alone, with no check-in
        # and no reply from the target.
        root = self.desktop_root()
        for label, marker in QUEUED_WORDINGS:
            with self.subTest(wording=label):
                refusal = self.question_refusal(root, self.queued_send(marker))
                self.assertNotEqual(refusal, "", "a queued desktop send with no check-in passed the pick check")

    def test_desktop_queued_send_with_a_recurring_checkin_is_refused(self):
        # Control, green on the old code. Catches: a recurring schedule call counted as the one-time check-in, so a send
        # whose check-in repeats is taken as a set check-in.
        root = self.desktop_root()
        for label, marker in QUEUED_WORDINGS:
            with self.subTest(wording=label):
                refusal = self.question_refusal(root, [*self.queued_send(marker), *self.checkin(recurring=True)])
                self.assertNotEqual(refusal, "", "a queued desktop send with a recurring schedule call passed the pick check")

    def test_desktop_queued_send_with_a_checkin_from_an_earlier_turn_is_refused(self):
        # Control, green on the old code. Catches: a check-in set in an earlier turn counted for this turn's queued send.
        root = self.desktop_root()
        for label, marker in QUEUED_WORDINGS:
            with self.subTest(wording=label):
                before = [trg.human("earlier"), *self.checkin(), trg.assistant_text("Done.")]
                refusal = self.question_refusal(root, self.queued_send(marker), before=before)
                self.assertNotEqual(refusal, "", "a check-in from an earlier turn counted for a queued send in this turn")

    def test_desktop_queued_send_then_a_reply_from_the_target_counts(self):
        # Catches:a queued desktop send refused although its target later sent a message back, which
        # shows the send reached it. Both peer shapes name the target: the desktop tag's from attribute and the cloud origin.
        root = self.desktop_root()
        replies = (("desktop peer", desktop_peer_record(DESKTOP_WRITER)),
                   ("cloud peer", trg.peer_msg("Two ways", from_session=DESKTOP_WRITER)))
        for label, marker in QUEUED_WORDINGS:
            for shape, reply in replies:
                with self.subTest(wording=label, reply=shape):
                    self.assertEqual(transcript.peer_sender(reply), DESKTOP_WRITER,
                                     "scope: the reply does not name the target as its sender")
                    refusal = self.question_refusal(root, [*self.queued_send(marker), reply])
                    self.assertEqual(refusal, "", "a queued desktop send, then a reply from its target, was refused: %s" % refusal)

    def test_desktop_queued_send_then_a_reply_from_another_session_is_refused(self):
        # Control, green on the old code. Catches: any peer message counted as the target's reply, so a reply from a
        # different session passes for a queued send.
        root = self.desktop_root()
        for label, marker in QUEUED_WORDINGS:
            with self.subTest(wording=label):
                reply = desktop_peer_record(OTHER_ID)
                self.assertEqual(transcript.peer_sender(reply), OTHER_ID, "scope: the reply does not name the other session")
                refusal = self.question_refusal(root, [*self.queued_send(marker), reply])
                self.assertNotEqual(refusal, "", "a reply from another session counted as the target's reply for a queued send")

    def test_desktop_queued_send_with_a_same_turn_checkin_counts_on_the_page_read_path(self):
        # Catches:the page-read writer path refusing a queued send that the same turn's one-time
        # check-in covers, as it refuses the send alone.
        root = self.page_read_repo()
        for label, marker in QUEUED_WORDINGS:
            for shape, send in self.page_read_sends(desktop_result("queued", wording=marker)):
                with self.subTest(wording=label, shape=shape):
                    refusal = self.page_read_refusal(root, [*send, *self.checkin()])
                    self.assertEqual(refusal, "", "a queued desktop %s with a same-turn one-time check-in to the writer the page "
                                     "read names was refused: %s" % (shape, refusal))

    def test_desktop_queued_send_then_a_reply_from_the_target_counts_on_the_page_read_path(self):
        # Catches:the page-read writer path refusing a queued send whose target later sent a message back.
        root = self.page_read_repo()
        for label, marker in QUEUED_WORDINGS:
            with self.subTest(wording=label):
                refusal = self.page_read_refusal(root, [*self.queued_send(marker), desktop_peer_record(DESKTOP_WRITER)])
                self.assertEqual(refusal, "", "a queued desktop send, then a reply from the writer the page read names, was refused: %s"
                                 % refusal)

    def test_failed_or_refused_queued_send_with_a_checkin_still_does_not_count(self):
        # Control, green on the old code. Catches: a one-time check-in rescuing a send whose result is an error or a refusal.
        root = self.desktop_root()
        refused = "Refused: the send guard blocked this message; no session was reached."
        shapes = (("error", self.queued_send(QUEUED_HOLDING, is_error=True)),
                  ("refusal", self.send(to=DESKTOP_WRITER, result=refused, is_error=True)))
        for label, send in shapes:
            with self.subTest(shape=label):
                refusal = self.question_refusal(root, [*send, *self.checkin()])
                self.assertNotEqual(refusal, "", "a %s on a queued desktop send, with a same-turn check-in, passed the pick check" % label)

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

    def assert_real_peer_names_its_sender(self):
        """The control every negative below rests on: a real desktop peer record still names its sender."""
        self.assertEqual(transcript.peer_sender(desktop_peer_record(DESKTOP_PEER)), DESKTOP_PEER,
                         "scope: a real desktop peer record names no sender, so the negative case proves nothing")

    def test_tool_result_quoting_a_cross_session_block_names_no_sender(self):
        # Catches: peer_sender naming a sender from a tool result whose text quotes a cross-session-message block, so a
        # quoted id reads as a peer's sender. A tool result is no peer record, whatever its text quotes.
        self.assert_real_peer_names_its_sender()
        quoted = '<cross-session-message from="%s" from-name="triage">Two ways</cross-session-message>' % DESKTOP_PEER
        rec = {"type": "user", "isSidechain": False, "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "toolu_quoted1", "content": quoted}]}}
        self.assertNotIn("origin", rec, "scope: the tool result record names an origin")
        self.assertIsNotNone(transcript.CROSS_SESSION_FROM.search(quoted), "scope: the quoted text holds no cross-session-message tag")
        self.assertIsNone(transcript.peer_sender(rec),
                          "peer_sender named a sender for a tool result that quotes a cross-session-message block")

    def test_owner_typed_text_quoting_a_cross_session_block_names_no_sender(self):
        # Catches: peer_sender naming a sender from words the owner typed that quote a cross-session-message tag. The
        # owner's record is no peer record: it carries no origin, so it names no sender.
        self.assert_real_peer_names_its_sender()
        quoted = ('Look at this: <cross-session-message from="%s" from-name="triage">Two ways</cross-session-message>'
                  % DESKTOP_PEER)
        rec = {"type": "user", "isSidechain": False, "message": {"role": "user", "content": quoted}}
        self.assertNotIn("origin", rec, "scope: the owner record names an origin")
        self.assertIsNotNone(transcript.CROSS_SESSION_FROM.search(quoted), "scope: the quoted text holds no cross-session-message tag")
        self.assertIsNone(transcript.peer_sender(rec),
                          "peer_sender named a sender for owner-typed text that quotes a cross-session-message block")


if __name__ == "__main__":
    unittest.main()
