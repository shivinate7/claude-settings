#!/usr/bin/env python3
"""The question route the pick check judges.

A question for the owner must reach the page writer in the turn it is asked, because a waiting page is the
only place the owner answers it. Only a repo with no waiting page takes the question box instead. The rule is
the page-writer ruling of the questions decision, stamped 23:31 CST on 1 November.

These cases pin four gaps the check had:

- an ack that carries a later message from the same sender into the turn;
- an owner-facing session, with its own record, whose question goes to @parent, which reaches no one there;
- a question box alone in a repo that has a waiting page, with or without a remote id;
- a target's first reply with a "?" outside quotes, code, fences and blockquotes, read as its ack (the lane-ack
  debt). Such a reply is an answer: it starts a turn.

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


class RouteTests(RouteFixture, unittest.TestCase):

    # The ack. The first message from a send's target is the ack of that send and keeps the turn, unless it is an
    # answer (see below). A later message from the same target is a message of its own and starts a turn.

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

    # The answer. A target's first reply that holds a "?" outside quotes, code spans, fenced blocks and blockquotes
    # is an answer, not an ack: it starts a turn, so a question after it needs a send of its own. A reply with no
    # such "?" is an ack, as before. The controls pin both sides, so a fix that reads every reply as an answer fails.

    def assert_blocks(self, out, cause, *phrases):
        """assert_blocked, with the cause named first, so a failure says which gap it is."""
        self.assertIsNotNone(out, cause)
        self.assert_blocked(out, *phrases)

    def test_rt_red_parent_reply_with_a_question_mark_is_an_answer_not_an_ack(self):
        # Catches: the lane-ack debt. A send to @parent, the parent's one reply asking a new question with a plain
        # "?", and the lane's reply asking it with no send. The parent's reply was taken as the ack, so it passed.
        out = self.lane(peer_msg("pick?"), *self.send(session_id="@parent"),
                        peer_msg("Is the pick still open?", from_session=self.PARENT),
                        assistant_text(self.reply(self.QUESTION)))
        self.assert_blocks(out, "the parent's plain ? was read as its ack, so the question passed",
                           "Lane pick guard", "its parent")

    def test_rt_red_writer_reply_with_a_question_mark_is_an_answer_not_an_ack(self):
        # Catches: the same ack on the page writer's one reply. Its "?" starts a turn, so the owner question after it
        # has no send in its turn and blocks. Both send forms, session_id and to, reach the writer.
        for label, send in (("session_id", self.send(session_id=self.WRITER)), ("to", self.send(to=self.WRITER))):
            with self.subTest(field=label):
                out = self.stop([human("decide"), *self.writer_read(self.WRITER), *send,
                                 peer_msg("Is the pick still open?", from_session=self.WRITER),
                                 assistant_text(self.reply(self.QUESTION))])
                self.assert_blocks(out, "the writer's plain ? was read as its ack, so the question passed",
                                   "Pick guard", self.WRITER)

    def test_rt_red_plain_question_mark_beside_a_scanner_trap_is_an_answer(self):
        # Catches: a scan that reads a lone apostrophe, a lone opening quote, a comment opener in prose, or a quoted
        # "?" on the same reply as a plain one, and so hides the plain "?". Each body holds one plain "?".
        bodies = (("a lone apostrophe", "Don't ship yet?"),
                  ("a lone opening quote", 'The lead wrote "ship it? Is it ready?'),
                  ("comment openers in prose", "#12 // or #13?"),
                  ("a quoted ? and a plain one", 'The lead wrote "is it ready?"\nIs the pick still open?'))
        for label, body in bodies:
            with self.subTest(trap=label):
                out = self.lane(peer_msg("pick?"), *self.send(session_id="@parent"),
                                peer_msg(body, from_session=self.PARENT), assistant_text(self.reply(self.QUESTION)))
                self.assert_blocks(out, "the plain ? in a reply with %s was read as an ack, so the question passed"
                                   % label, "Lane pick guard", "its parent")

    def test_rt_green_a_question_mark_only_in_a_quote_or_block_is_still_an_ack(self):
        # Catches: a fix that reads every "?" as an answer. Each form holds its only "?" inside a quote, a code span,
        # a fenced block or a blockquote line, so the reply is an ack and the send keeps the turn.
        forms = (("double quotes", 'Lead: "is it ready?"'),
                 ("single quotes", "Lead: 'is it ready?'"),
                 ("curly quotes", "Lead: “is it ready?”"),
                 ("code span", "Lead: `is it ready?`"),
                 ("fenced block", "See:\n```\nis it ready?\n```"),
                 ("blockquote", "See:\n> is it ready?"))
        # Each form is one control.
        for label, body in forms:
            with self.subTest(form=label):
                self.assertIn("?", body, "scope: the body holds no question mark, so the control proves nothing")
                # Scope first: with no send in the turn, the reply's question blocks, so the pass below is the send's.
                self.assert_blocks(self.lane(peer_msg("pick?"), assistant_text(self.reply(self.QUESTION))),
                                   "scope: with no send, the reply's question did not block", "Lane pick guard")
                out = self.lane(peer_msg("pick?"), *self.send(session_id="@parent"),
                                peer_msg(body, from_session=self.PARENT), assistant_text(self.reply(self.QUESTION)))
                self.assertIsNone(out, "a question mark inside a %s was read as an answer, so the ack started a turn"
                                  % label)

    def test_rt_green_a_reply_with_no_question_mark_is_an_ack(self):
        # Catches: an ack with no "?" read as an answer, which starts a turn and blocks the question its send covers.
        # Shapes: an empty reply (the empty state), a bare ack, and a two-line status.
        for label, body in (("empty", ""), ("got it", "got it"), ("two lines", "Noted.\nStatus: green.")):
            with self.subTest(shape=label):
                self.assertNotIn("?", body, "scope: the body holds a question mark, so it is not the ack this tests")
                self.assert_blocks(self.lane(peer_msg("pick?"), assistant_text(self.reply(self.QUESTION))),
                                   "scope: with no send, the reply's question did not block", "Lane pick guard")
                out = self.lane(peer_msg("pick?"), *self.send(session_id="@parent"),
                                peer_msg(body, from_session=self.PARENT), assistant_text(self.reply(self.QUESTION)))
                self.assertIsNone(out, "an ack with no question mark (%s) started a turn and hid its send" % label)

    def test_rt_green_answer_then_a_fresh_send_covers_the_question(self):
        # Catches: a fix that blocks everything after a "?" reply, so a send made after the answer goes unseen.
        out = self.lane(peer_msg("pick?"), *self.send(session_id="@parent"),
                        peer_msg("Is the pick still open?", from_session=self.PARENT),
                        *self.send(session_id="@parent"), assistant_text(self.reply(self.QUESTION)))
        self.assertIsNone(out, "a question sent in the answer's own turn was blocked")

    def test_rt_green_answer_then_a_send_and_an_ack_keeps_the_later_send(self):
        # Catches: a fix that spends the parent's ack slot on the answer, so the next reply ("got it", the ack of the
        # later send) starts a turn of its own and hides that send.
        out = self.lane(peer_msg("pick?"), *self.send(session_id="@parent"),
                        peer_msg("Is the pick still open?", from_session=self.PARENT),
                        *self.send(session_id="@parent"), peer_msg("got it", from_session=self.PARENT),
                        assistant_text(self.reply(self.QUESTION)))
        self.assertIsNone(out, "the ack of the later send started a turn and hid that send")

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

    def test_rt_green_owner_record_sends_to_the_writer_passes(self):
        # Catches: an owner-facing record's send to the writer refused. This is the route the ruling names.
        out = self.stop([human("decide"), *self.lane_record(tags=("coordinator",), parent=None),
                         *self.writer_read(self.WRITER), *self.send(session_id=self.WRITER),
                         assistant_text(self.reply(self.PICK))], env_id=self.LANE_ENV)
        self.assertIsNone(out, "the owner's send to the writer was blocked")

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

    def test_rt_green_box_with_a_send_to_the_writer_passes(self):
        # Catches: a box in the turn stopping the writer's send from counting, with or without a remote id.
        writer_turn = [*self.writer_read(self.WRITER), *self.box(), *self.send(session_id=self.WRITER)]
        self.assertIsNone(self.stop([human("decide"), *writer_turn, assistant_text(self.reply(self.PICK))]),
                          "the box and the writer send were blocked with no remote id")
        self.assertIsNone(self.stop([human("decide"), *self.lane_record(tags=("coordinator",), parent=None),
                                     *writer_turn, assistant_text(self.reply(self.PICK))], env_id=self.LANE_ENV),
                          "the box and the writer send were blocked with a remote id")

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


if __name__ == "__main__":
    unittest.main()
