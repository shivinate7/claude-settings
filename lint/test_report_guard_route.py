#!/usr/bin/env python3
"""The question route the pick check judges.

A question for the owner must reach the page writer in the turn it is asked, because a waiting page is the
only place the owner answers it. Only a repo with no waiting page takes the question box instead. The rule is
the page-writer ruling of the questions decision, stamped 23:31 CST on 1 November.

These cases pin three gaps the check had:

- an ack that carries a later message from the same sender into the turn (the lane-ack debt);
- an owner-facing session, with its own record, whose question goes to @parent, which reaches no one there;
- a question box alone in a repo that has a waiting page, with or without a remote id.

OnThePageFormTests pins item 3 of step page-wakes-and-relays, one home per answer. Once the owner-facing turn sends
its question to the page writer, or writes the page's items, the page holds the question, so the chat reply holds
only `on the page, item N`. It carries no options and no question text.

The fixture, the transcript helpers and the run folder come from lint/test_report_guard.py, the one home.
They are borrowed by name here, so this file adds only its cases. Run with:

    python3 lint/test_report_guard_route.py -v
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_report_guard as trg  # noqa: E402  the fixture, helpers and run folder (one home)

human = trg.human
peer_msg = trg.peer_msg
assistant_text = trg.assistant_text


def setUpModule():
    trg.setUpModule()  # the run folder, CLAUDE_CONFIG_DIR and the model stub, set as test_report_guard sets them


def tearDownModule():
    trg.tearDownModule()


ON_PAGE = "on the page, item"  # the form a reply names once its question is on the page (item 3, page-wakes-and-relays)
NOT_SENT = "was not sent to the page writer"  # the Pick guard's reason, which a counted send keeps out


def assert_on_the_page(test, out):
    """The send counted, and the block is the on-the-page form. Scope first: no Pick guard reason, so the send
    counted. Then the subject: the reason names the page item. A copy of test_report_guard's assert_on_the_page;
    the red run here imports main's test_report_guard, which has no such helper, so this file defines its own."""
    test.assertIsNotNone(out, "the question passed; expected a block")
    test.assertEqual(out.get("decision"), "block", out)
    reason = out.get("reason", "")
    test.assertNotIn(NOT_SENT, reason, "the Pick guard refused it, so its send did not count: %r" % reason)
    test.assertIn(ON_PAGE, reason, "the block does not name the on-the-page form: %r" % reason)


class RouteFixture(trg.SameTurnWriter):
    """test_report_guard's QuestionReachesPageTests fixture, borrowed name by name. A case here reuses it and
    does not copy it, so a change to the shared fixture reaches both files."""

    PAGE = trg.QuestionReachesPageTests.PAGE
    PARENT = trg.QuestionReachesPageTests.PARENT
    LANE_ENV = trg.QuestionReachesPageTests.LANE_ENV
    LANE_ID = trg.QuestionReachesPageTests.LANE_ID
    PICK = trg.QuestionReachesPageTests.PICK
    QUESTION = trg.QuestionReachesPageTests.QUESTION
    NO_KEY = trg.QuestionReachesPageTests.NO_KEY  # make_repo's writer default; the same object, so the identity test holds

    setUp = trg.QuestionReachesPageTests.setUp
    make_repo = trg.QuestionReachesPageTests.make_repo
    reply = trg.QuestionReachesPageTests.reply
    box = trg.QuestionReachesPageTests.box
    lane_record = trg.QuestionReachesPageTests.lane_record
    stop = trg.QuestionReachesPageTests.stop
    lane = trg.QuestionReachesPageTests.lane
    assert_blocked = trg.QuestionReachesPageTests.assert_blocked
    items_write = trg.QuestionReachesPageTests.items_write
    items_batch = trg.QuestionReachesPageTests.items_batch


class RouteTests(RouteFixture, unittest.TestCase):

    # The ack. The first message from a send's target is the ack of that send and keeps the turn. A later
    # message from the same target is a message of its own and starts a turn.

    def test_rt_red_lane_message_after_the_ack_starts_a_turn(self):
        # Catches: the parent's second message skipped as a second ack, so a question with no send rides on the
        # first send. The ack skip never clears the sender's targets (the lane-ack debt).
        out = self.lane(peer_msg("pick?"), *self.send(session_id="@parent"),
                        peer_msg("got it", from_session=self.PARENT),
                        peer_msg("one more pick?", from_session=self.PARENT),
                        assistant_text(self.reply(self.QUESTION)))
        self.assert_blocked(out, "Lane pick guard", "its parent")

    def test_rt_red_owner_message_after_the_writer_ack_starts_a_turn(self):
        # Catches: the same skip on the page writer's ack. Its second message is skipped as an ack too.
        out = self.stop([human("decide"), *self.writer_read(self.WRITER), *self.send(session_id=self.WRITER),
                         peer_msg("got it", from_session=self.WRITER),
                         peer_msg("one more", from_session=self.WRITER),
                         assistant_text(self.reply(self.QUESTION))])
        self.assert_blocked(out, "Pick guard", self.WRITER)

    def test_rt_green_first_ack_then_a_question_keeps_the_turn(self):
        # Catches: the first ack starting a turn of its own, which hides the send the question rides on.
        # Two shapes: the lane's input alone, and a human message before it.
        for label, incoming in (("peers only", [peer_msg("pick?")]),
                                ("human first", [human("decide"), peer_msg("pick?")])):
            with self.subTest(shape=label):
                out = self.lane(*incoming, *self.send(session_id="@parent"),
                                peer_msg("got it", from_session=self.PARENT),
                                assistant_text(self.reply(self.QUESTION)))
                self.assertIsNone(out, "the first ack ended the turn that sent the question")

    def test_rt_green_parent_second_message_with_no_question_passes(self):
        # Catches: the second message starting a turn that then blocks a reply which asks nothing.
        out = self.lane(peer_msg("pick?"), *self.send(session_id="@parent"),
                        peer_msg("got it", from_session=self.PARENT),
                        peer_msg("status?", from_session=self.PARENT),
                        assistant_text(self.reply(["None."])))
        self.assertIsNone(out, "a reply that asks nothing was blocked")

    def test_rt_green_question_sent_after_the_second_message_passes(self):
        # Catches: a fix that blocks the send made in the second message's own turn.
        out = self.lane(peer_msg("pick?"), *self.send(session_id="@parent"),
                        peer_msg("got it", from_session=self.PARENT),
                        peer_msg("status?", from_session=self.PARENT),
                        *self.send(session_id="@parent"),
                        assistant_text(self.reply(self.QUESTION)))
        self.assertIsNone(out, "a question sent in its own turn was blocked")

    # The owner-facing session. Its own record, with no lane tag and no parent, makes it owner-facing: a send to
    # @parent reaches no one there, so the question needs the page writer.

    def test_rt_red_owner_record_sends_to_parent_only_blocks(self):
        # Catches: an owner-facing session passing a question because its send went to @parent.
        for label, send in (("@parent", self.send(session_id="@parent")), ("to parent", self.send(to="parent"))):
            with self.subTest(form=label):
                out = self.stop([human("decide"), *self.lane_record(tags=("coordinator",), parent=None), *send,
                                 assistant_text(self.reply(self.PICK))], env_id=self.LANE_ENV)
                self.assertNotIn("Lane pick guard", (out or {}).get("reason", ""), "read as a lane, not an owner")
                self.assert_blocked(out, "Pick guard")

    def test_rt_green_owner_record_sends_to_the_writer_reaches_the_page(self):
        # Catches: an owner-facing record's send to the writer not counted. The send counts, so the reply names only
        # the page item and holds no options (item 3 of page-wakes-and-relays).
        out = self.stop([human("decide"), *self.lane_record(tags=("coordinator",), parent=None),
                         *self.writer_read(self.WRITER), *self.send(session_id=self.WRITER),
                         assistant_text(self.reply(self.PICK))], env_id=self.LANE_ENV)
        assert_on_the_page(self, out)

    # The question box. In a repo with a waiting page the box is no route: the question goes to the writer.

    def test_rt_red_box_alone_in_a_page_repo_with_a_remote_id_blocks(self):
        # Catches: a box alone passing a question in a repo that has a waiting page.
        out = self.stop([human("decide"), *self.lane_record(tags=("coordinator",), parent=None), *self.box(),
                         assistant_text(self.reply(self.PICK))], env_id=self.LANE_ENV)
        self.assertNotIn("Lane pick guard", (out or {}).get("reason", ""), "read as a lane, not an owner")
        self.assert_blocked(out, "Pick guard")

    def test_rt_red_box_alone_in_a_page_repo_with_no_remote_id_blocks(self):
        # Catches: the no-remote-id path passing a box alone in a repo that has a waiting page.
        out = self.stop([human("decide"), *self.box(), assistant_text(self.reply(self.PICK))])
        self.assert_blocked(out, "Pick guard")

    def test_rt_green_box_with_a_send_to_the_writer_reaches_the_page(self):
        # Catches: a box in the turn stopping the writer's send from counting, with or without a remote id. The send
        # counts, so the reply names only the page item (item 3 of page-wakes-and-relays).
        writer_turn = [*self.writer_read(self.WRITER), *self.box(), *self.send(session_id=self.WRITER)]
        assert_on_the_page(self, self.stop([human("decide"), *writer_turn, assistant_text(self.reply(self.PICK))]))
        assert_on_the_page(self, self.stop([human("decide"), *self.lane_record(tags=("coordinator",), parent=None),
                                            *writer_turn, assistant_text(self.reply(self.PICK))],
                                           env_id=self.LANE_ENV))

    def test_rt_green_box_alone_in_a_repo_with_no_page_passes(self):
        # Catches: a box alone refused in a repo with no waiting page. That repo asks in the reply or the box.
        bare = self.make_repo("bare", page=False)
        self.assertIsNone(self.stop([human("decide"), *self.box(), assistant_text(self.reply(self.PICK))], repo=bare),
                          "the box alone was blocked with no remote id")
        self.assertIsNone(self.stop([human("decide"), *self.lane_record(tags=("coordinator",), parent=None),
                                     *self.box(), assistant_text(self.reply(self.PICK))],
                                    env_id=self.LANE_ENV, repo=bare),
                          "the box alone was blocked with a remote id")

    # The lane. Its send to its parent is its route in its own turn.

    def test_rt_green_lane_send_to_parent_in_the_turn_passes(self):
        # Catches: the lane's send to its parent, in its own turn, refused.
        out = self.lane(peer_msg("pick?"), *self.send(session_id="@parent"), assistant_text(self.reply(self.PICK)))
        self.assertIsNone(out, "the lane's send to its parent was blocked")


class OnThePageFormTests(RouteFixture, unittest.TestCase):
    """Item 3 of step page-wakes-and-relays: one home per answer, the page. Once the question is on the page, the chat
    reply holds only `on the page, item N`. The red cases run each owner-facing pass site: the writer's send, the layout
    key writer's delivered send, and the items write. Each runs a pick and a sentence question."""

    def test_op_red_writer_send_restating_the_question_blocks_on_the_page(self):
        # Catches: a reply that restates its pick or question after the writer send passing, so the owner reads the
        # question twice and chat holds what the page holds.
        for label, body in (("pick", self.PICK), ("question", self.QUESTION)):
            with self.subTest(body=label):
                out = self.stop([human("decide"), *self.writer_read(self.WRITER), *self.send(session_id=self.WRITER),
                                 assistant_text(self.reply(body))])
                assert_on_the_page(self, out)

    def test_op_red_delivered_key_send_restating_the_question_blocks_on_the_page(self):
        # Catches: the same restated question passing on the layout-key route. No meta/page read names the writer
        # there, so only the delivered send counts.
        keyed = self.make_repo("keyed_op", writer=self.WRITER)
        for label, body in (("pick", self.PICK), ("question", self.QUESTION)):
            with self.subTest(body=label):
                out = self.stop([human("decide"), *self.send(session_id=self.WRITER, result=self.DELIVERED),
                                 assistant_text(self.reply(body))], repo=keyed)
                assert_on_the_page(self, out)

    def test_op_red_items_write_restating_the_question_blocks_on_the_page(self):
        # Catches: the writer's own items write (set, batch) passing a restated question instead of the page form.
        for label, write in (("set", self.items_write("set")), ("batch", self.items_batch())):
            for body_label, body in (("pick", self.PICK), ("question", self.QUESTION)):
                with self.subTest(write=label, body=body_label):
                    out = self.stop([human("decide"), *write, assistant_text(self.reply(body))])
                    assert_on_the_page(self, out)

    def test_op_red_pointer_with_the_options_left_in_chat_blocks(self):
        # Catches: the pointer added while the options stay in chat, so chat still holds the question.
        body = ["on the page, item 12", *self.PICK[1:]]
        out = self.stop([human("decide"), *self.writer_read(self.WRITER), *self.send(session_id=self.WRITER),
                         assistant_text(self.reply(body))])
        assert_on_the_page(self, out)

    def test_op_green_pointer_alone_after_the_writer_send_passes(self):
        # Catches: the form itself refused. Chat holding only the pointer has no options and no question, so it passes.
        out = self.stop([human("decide"), *self.writer_read(self.WRITER), *self.send(session_id=self.WRITER),
                         assistant_text(self.reply(["on the page, item 12"]))])
        self.assertIsNone(out, "the pointer alone was refused")

    def test_op_green_no_send_keeps_the_pick_guard_without_the_page_form(self):
        # Catches: the page form named for a question that no send or items write put on the page.
        out = self.stop([human("decide"), assistant_text(self.reply(self.PICK))])
        self.assert_blocked(out, "Pick guard")
        self.assertNotIn(ON_PAGE, out.get("reason", ""), "the page form named a page item that holds no question")

    def test_op_green_send_to_another_session_keeps_the_pick_guard_without_the_page_form(self):
        # Catches: the page form named for a send that missed the writer.
        out = self.stop([human("decide"), *self.writer_read(self.WRITER), *self.send(session_id="session_other9"),
                         assistant_text(self.reply(self.PICK))])
        self.assert_blocked(out, "Pick guard", self.WRITER)
        self.assertNotIn(ON_PAGE, out.get("reason", ""), "the page form named a page item for a send that missed the writer")

    def test_op_green_lane_send_to_the_writer_with_options_still_passes(self):
        # Catches: the page form applied to a lane. A lane's chat goes to its parent, so the lane keeps its own route.
        out = self.lane(*self.writer_read(self.WRITER), peer_msg("pick?"), *self.send(session_id=self.WRITER),
                        assistant_text(self.reply(self.PICK)))
        self.assertIsNone(out, "the lane's send to the writer, with its options, was refused")


if __name__ == "__main__":
    unittest.main()
