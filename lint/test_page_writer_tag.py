#!/usr/bin/env python3
"""The page writer is the session its triage tag names (roadmap step page-writer-key-follows-tag).

The writer is the `writer` of the newest meta/page get. With no such get, it is the one session whose newest get_session
or list_sessions record carries cs-build:triage and cs-repo:<repo>, the repo compared lowercase. Zero or two such
sessions name no writer, and a send to no one passes. The pick check (lint/report_guard.py question_problem) and the
owner-feedback page check (hooks/feedback_guard.py Pages.is_writer) both read that one home, so they agree.

Every case runs on this repo's real .claude/layout-extras.json root. Its fixed `page-writer` key is a stale id for these
cases: no case may pass a send to it. The run folder, the send, transcript and listing helpers come from
lint/test_report_guard.py, the one home. Run with:

    python3 lint/test_page_writer_tag.py -v
"""
import inspect
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "hooks"))
import test_report_guard as trg  # noqa: E402  the run folder, the send, transcript and listing helpers, the guard (one home)
import test_report_guard_stalled as trs  # noqa: E402  the lane's own record and remote id (one home)
import feedback_guard  # noqa: E402  Pages.is_writer, the owner-feedback page check

layout = trg.RG.layout  # the module the guard reads the extras key from, so this file reads the same key
REMOTE_ENV = "CLAUDE_CODE_REMOTE_SESSION_ID"  # set only in a lane; unset here, so the check reads an owner-facing session
NEW = "session_pwtnew1"  # a triage session whose id is not the extras key
OTHER = "session_pwtother"  # a second triage session, or one whose newest record is no longer triage
LANE = "session_pwtlane"  # a session tagged as a lane, never a writer
META = "session_pwtmeta"  # the writer a meta/page get names
PARENT_ID = "session_parent1"  # the parent id a lane's own record names


def setUpModule():
    trg.setUpModule()  # the run folder, CLAUDE_CONFIG_DIR and the model stub, set as test_report_guard sets them


def tearDownModule():
    trg.tearDownModule()


class PageWriterTagTests(trg.SameTurnWriter, unittest.TestCase):
    """The pick check and the owner-feedback check name the writer from the triage tag. Each case is an owner-facing
    turn: the main session, with no lane id in its environment."""

    PAGE = trg.QuestionReachesPageTests.PAGE  # the waiting page a meta/page get names (SameTurnWriter.writer_read)
    PICK = trg.QuestionReachesPageTests.PICK
    reply = trg.QuestionReachesPageTests.reply
    OTHER_REPO = "example-owner/other-repo"

    def setUp(self):
        self.run_dir = tempfile.mkdtemp(dir=trg._ISOLATION["dir"])
        self.addCleanup(shutil.rmtree, self.run_dir, ignore_errors=True)
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop(REMOTE_ENV, None)

    def scope(self):
        """This repo's root, its repo name and its extras key. Checked first: a case that reads the name or the key
        proves nothing without them."""
        root = trg.RG.repo_root(HERE)
        self.assertIsNotNone(root, "scope: no git entry above lint/, so the guard finds no repo root")
        repo = layout.repo_name(root)
        self.assertIsNotNone(repo, "scope: this checkout has no GitHub origin, so no cs-repo tag can name it")
        key = layout.page_writer_key(root)
        self.assertIsNotNone(key, "scope: this repo's extras file names no page-writer key, the stale id these cases refuse")
        self.assertNotIn(key, (NEW, OTHER, LANE, META), "scope: the extras key is one of this test's session ids")
        return root, repo, key

    def refusal(self, root, acts):
        """The refusal question_problem gives a pick asked after `acts` in the same turn; "" when it passes."""
        return self.refusal_after(root, [], acts)

    def refusal_after(self, root, before, turn):
        """The refusal for a pick asked in `turn`, after the records `before` of the same transcript; "" when it passes."""
        records = [*before, trg.human("decide"), *turn, trg.assistant_text(self.reply(self.PICK))]
        hook = {"hook_event_name": "Stop", "transcript_path": trg.write_transcript(records, self.run_dir),
                "stop_hook_active": False, "cwd": root}
        refusal, _note = trg.RG.question_problem(records, records[len(before) + 1:], self.reply(self.PICK), hook)
        return refusal

    def is_writer(self, acts, session_id, repo):
        """Pages.is_writer on a transcript whose one owner message holds `acts`."""
        return self.is_writer_of([trg.human("decide"), *acts], session_id, repo)

    def is_writer_of(self, records, session_id, repo):
        """Pages.is_writer on the transcript `records`, asked with the repo. The signature is checked first, so a build
        without the repo argument fails on that, named."""
        params = inspect.signature(feedback_guard.Pages.is_writer).parameters
        self.assertIn("repo", params, "Pages.is_writer takes no repo, so it cannot read the triage tag")
        path = trg.write_transcript(records, self.run_dir)
        return feedback_guard.Pages(path).is_writer(session_id, repo=repo)

    def test_tag_new_triage_session_passes_a_delivered_send(self):
        # Catches: the pick check fixed to the extras key, so a delivered send to the new triage session is refused as
        # "the page writer is session <key>". Two listings: a short one, and a full one of 51 sessions, triage last.
        root, repo, key = self.scope()
        self.assertNotEqual(NEW, key, "scope: the new triage id is the extras key, so the case proves nothing")
        short = [(LANE, self.session_tags("lane", repo)), (NEW, self.session_tags("triage", repo))]
        full = [("session_pwtlane%02d" % n, self.session_tags("lane", repo)) for n in range(50)] + [
            (NEW, self.session_tags("triage", repo))]
        for label, sessions in (("short listing", short), ("full listing", full)):
            with self.subTest(listing=label):
                acts = [*self.listing(sessions), *self.send(session_id=NEW, result=self.DELIVERED)]
                refusal = self.refusal(root, acts)
                self.assertEqual(refusal, "", "a delivered send to the triage session %s was refused: %s" % (NEW, refusal))

    def test_tag_is_writer_and_pick_check_name_the_same_writer(self):
        # Catches: the owner-feedback check and the pick check naming different writers. Each row fixes its writer by
        # its spec. The pick check must pass a delivered send to that id only, and is_writer must say the same.
        root, repo, key = self.scope()
        rows = [
            ("one triage session", self.listing([(NEW, self.session_tags("triage", repo)),
                                                 (LANE, self.session_tags("lane", repo))]), NEW),
            ("two triage sessions", self.listing([(NEW, self.session_tags("triage", repo)),
                                                  (OTHER, self.session_tags("triage", repo))]), None),
            ("no triage session", self.listing([(LANE, self.session_tags("lane", repo))]), None),
            ("meta/page writer", self.writer_read(META), META),
            ("empty transcript", [], None),
        ]
        for label, acts, writer in rows:
            for sid in (NEW, OTHER, META, key):
                with self.subTest(transcript=label, session=sid):
                    sent = [*acts, *self.send(session_id=sid, result=self.DELIVERED)]
                    want = sid == writer
                    passed = self.refusal(root, sent) == ""
                    self.assertEqual(passed, want, "the pick check %s a delivered send to %s; the writer here is %s" % (
                        "passed" if passed else "refused", sid, writer))
                    self.assertEqual(self.is_writer(sent, sid, repo), want,
                                     "is_writer names another writer than the spec does for %s" % sid)

    def test_tag_stale_key_is_refused_once_a_listing_names_another_triage_session(self):
        # Catches: the pick check still passing a delivered send to the extras key id after a listing names another
        # triage session for this repo. That stale id refuses the real writer.
        root, repo, key = self.scope()
        acts = [*self.listing([(NEW, self.session_tags("triage", repo))]),
                *self.send(session_id=key, result=self.DELIVERED)]
        refusal = self.refusal(root, acts)
        self.assertNotEqual(refusal, "", "a delivered send to the stale key %s passed while %s is the triage session"
                            % (key, NEW))

    def test_tag_no_triage_session_refuses_a_send_to_the_key(self):
        # Catches: the key id passing as the writer when no session is tagged triage for this repo. Zero matches name
        # no writer, so the send is refused.
        root, repo, key = self.scope()
        cases = (("no session record", []),
                 ("listing with no triage session", self.listing([(LANE, self.session_tags("lane", repo))])))
        for label, acts in cases:
            with self.subTest(records=label):
                refusal = self.refusal(root, [*acts, *self.send(session_id=key, result=self.DELIVERED)])
                self.assertNotEqual(refusal, "", "a delivered send to the key %s passed with no triage session named (%s)"
                                    % (key, label))

    def test_tag_two_triage_sessions_refuse_a_send_to_either(self):
        # Catches: one of two triage sessions for this repo taken as the writer. The key id is one of the two, so the
        # stale key passes unless the two count as no writer.
        root, repo, key = self.scope()
        acts = self.listing([(key, self.session_tags("triage", repo)), (NEW, self.session_tags("triage", repo))])
        for sid in (key, NEW):
            with self.subTest(session=sid):
                refusal = self.refusal(root, [*acts, *self.send(session_id=sid, result=self.DELIVERED)])
                self.assertNotEqual(refusal, "", "a send to %s passed with two triage sessions named for this repo" % sid)

    def test_tag_triage_of_another_repo_is_ignored(self):
        # Catches: a triage session of another repo counted as this repo's writer. That makes two matches and refuses
        # the real writer.
        root, repo, key = self.scope()
        self.assertNotEqual("cs-repo:" + self.OTHER_REPO, "cs-repo:" + repo, "scope: the other repo is this repo")
        acts = self.listing([(NEW, self.session_tags("triage", repo)),
                             (OTHER, self.session_tags("triage", self.OTHER_REPO))])
        with self.subTest(session=NEW):
            refusal = self.refusal(root, [*acts, *self.send(session_id=NEW, result=self.DELIVERED)])
            self.assertEqual(refusal, "", "this repo's triage session %s was refused: %s" % (NEW, refusal))
        with self.subTest(session=OTHER):
            refusal = self.refusal(root, [*acts, *self.send(session_id=OTHER, result=self.DELIVERED)])
            self.assertNotEqual(refusal, "", "the triage session of another repo passed the pick check")

    def test_tag_undelivered_send_to_the_triage_writer_does_not_pass(self):
        # Catches: an undelivered send passing as the writer's pick, or the refusal naming the stale key rather than
        # the triage session the tag names.
        root, repo, key = self.scope()
        acts = [*self.listing([(NEW, self.session_tags("triage", repo))]),
                *self.send(session_id=NEW, result=self.NOT_DELIVERED)]
        refusal = self.refusal(root, acts)
        with self.subTest(part="passes"):
            self.assertNotEqual(refusal, "", "an undelivered send to the triage session %s passed the pick check" % NEW)
        with self.subTest(part="names the writer"):
            self.assertIn(NEW, refusal, "the refusal names another writer, not the triage session %s: %r" % (NEW, refusal))

    def test_tag_get_session_record_counts_as_the_triage_read(self):
        # Catches: a get_session record of the triage session ignored, so only a list_sessions listing names a writer.
        # The wrapped form is how the harness returns another session's record.
        root, repo, key = self.scope()
        for label, wrapped in (("bare record", False), ("wrapped record", True)):
            with self.subTest(form=label):
                acts = [*self.session_record(NEW, self.session_tags("triage", repo), wrapped=wrapped),
                        *self.send(session_id=NEW, result=self.DELIVERED)]
                refusal = self.refusal(root, acts)
                self.assertEqual(refusal, "", "a delivered send to the triage session %s, named by its %s, was refused: %s"
                                 % (NEW, label, refusal))

    def test_tag_repo_tag_compares_lowercase(self):
        # Catches: the cs-repo tag compared with its case, so a tag written in capitals never names this repo.
        root, repo, key = self.scope()
        upper = "cs-repo:" + repo.upper()
        self.assertNotEqual(upper, "cs-repo:" + repo, "scope: the tag is already lowercase, so the case proves nothing")
        acts = [*self.listing([(NEW, ["cs-build:triage", upper])]), *self.send(session_id=NEW, result=self.DELIVERED)]
        refusal = self.refusal(root, acts)
        self.assertEqual(refusal, "", "a triage session tagged %r was refused for this repo: %s" % (upper, refusal))

    def test_tag_newest_record_decides_whether_a_session_is_triage(self):
        # Catches: a session whose newest record no longer carries cs-build:triage still counted. Then two sessions
        # match and the real triage session is refused.
        root, repo, key = self.scope()
        acts = [*self.session_record(OTHER, self.session_tags("triage", repo)),
                *self.session_record(OTHER, self.session_tags("lane", repo)),
                *self.session_record(NEW, self.session_tags("triage", repo))]
        with self.subTest(session=NEW):
            refusal = self.refusal(root, [*acts, *self.send(session_id=NEW, result=self.DELIVERED)])
            self.assertEqual(refusal, "", "the triage session %s was refused; %s's newest record is a lane: %s"
                             % (NEW, OTHER, refusal))
        with self.subTest(session=OTHER):
            refusal = self.refusal(root, [*acts, *self.send(session_id=OTHER, result=self.DELIVERED)])
            self.assertNotEqual(refusal, "", "a session whose newest record is a lane passed the pick check")

    def test_tag_has_more_listing_names_no_writer(self):
        # Catches: a list_sessions page marked has_more naming a triage session as the writer. The page may miss the
        # real triage session, so no writer is named from it. The same session in a complete listing still names it.
        root, repo, key = self.scope()
        with self.subTest(listing="has_more true"):
            acts = [*self.listing([(NEW, self.session_tags("triage", repo))], has_more=True),
                    *self.send(session_id=NEW, result=self.DELIVERED)]
            refusal = self.refusal(root, acts)
            self.assertNotEqual(refusal, "", "a delivered send to a triage session named by a has_more page passed")
        with self.subTest(listing="complete"):
            acts = [*self.listing([(NEW, self.session_tags("triage", repo))]),
                    *self.send(session_id=NEW, result=self.DELIVERED)]
            refusal = self.refusal(root, acts)
            self.assertEqual(refusal, "", "a delivered send to a triage session in a complete listing was refused: %s" % refusal)

    def test_tag_listing_from_an_earlier_turn_names_no_writer(self):
        # Catches: a triage session read in an earlier turn named as this turn's writer. Triage restarts and gets new ids,
        # so a tag read before the last owner message may be stale. The same listing in this turn still names it.
        root, repo, key = self.scope()
        listing = self.listing([(NEW, self.session_tags("triage", repo))])
        send = self.send(session_id=NEW, result=self.DELIVERED)
        with self.subTest(turn="earlier"):
            before = [trg.human("first"), *listing, trg.assistant_text("Listed.")]
            refusal = self.refusal_after(root, before, send)
            self.assertNotEqual(refusal, "", "a delivered send to a triage session listed in an earlier turn passed")
        with self.subTest(turn="this"):
            before = [trg.human("first"), trg.assistant_text("Done.")]
            refusal = self.refusal_after(root, before, [*listing, *send])
            self.assertEqual(refusal, "", "a delivered send to a triage session listed in this turn was refused: %s" % refusal)

    def test_tag_lane_send_to_the_tagged_writer(self):
        # Catches: a lane's send to the triage session its tag read names refused, because the lane branch counts only a
        # meta/page writer. An undelivered send to that writer still does not pass.
        root, repo, key = self.scope()
        os.environ[REMOTE_ENV] = trs.LANE_ENV  # the session is the lane: its own record is read from the transcript
        own = trs.own_record(trs.LANE_ID, ["cs-build:lane"], parent=PARENT_ID)
        listing = self.listing([(NEW, self.session_tags("triage", repo))])
        with self.subTest(send="delivered"):
            acts = [*own, *listing, *self.send(session_id=NEW, result=self.DELIVERED)]
            refusal = self.refusal(root, acts)
            self.assertEqual(refusal, "", "a delivered lane send to the tag writer %s was refused: %s" % (NEW, refusal))
        with self.subTest(send="undelivered"):
            acts = [*own, *listing, *self.send(session_id=NEW, result=self.NOT_DELIVERED)]
            refusal = self.refusal(root, acts)
            self.assertNotEqual(refusal, "", "an undelivered lane send to the tag writer %s passed the pick check" % NEW)

    def test_tag_is_writer_and_pick_check_agree_on_the_turn_rules(self):
        # Catches: is_writer and the pick check reading the turn or the page differently. Each transcript names no
        # writer by spec, and both checks must say so for a delivered send to either session.
        root, repo, key = self.scope()
        rows = [
            ("has_more page", [], self.listing([(NEW, self.session_tags("triage", repo))], has_more=True)),
            ("earlier turn", [trg.human("first"), *self.listing([(NEW, self.session_tags("triage", repo))]),
                              trg.assistant_text("Listed.")], []),
        ]
        for label, before, now in rows:
            for sid in (NEW, key):
                with self.subTest(transcript=label, session=sid):
                    turn = [*now, *self.send(session_id=sid, result=self.DELIVERED)]
                    passed = self.refusal_after(root, before, turn) == ""
                    written = self.is_writer_of([*before, trg.human("decide"), *turn], sid, repo)
                    self.assertEqual(passed, written, "the pick check and is_writer disagree on %s" % sid)
                    self.assertFalse(written, "the writer read names %s, which the spec does not name" % sid)

    def test_tag_control_meta_page_writer_passes(self):
        # Control, green on the old code: the meta/page writer's delivered send passes, so the harness does pass a real send.
        root, repo, key = self.scope()
        acts = [*self.writer_read(META), *self.send(session_id=META, result=self.DELIVERED)]
        refusal = self.refusal(root, acts)
        self.assertEqual(refusal, "", "a delivered send to the meta/page writer %s was refused: %s" % (META, refusal))


if __name__ == "__main__":
    unittest.main()
