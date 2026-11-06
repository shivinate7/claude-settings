#!/usr/bin/env python3
"""The ruling-skip check: a Done item that says it acted under a ruling must cite that ruling.

A Done item claims a ruling skip when it reads "under ruling" or "under the owner's ruling". Its cite is
`under ruling <ref> (<stamp>)`. The ref is `item <N> <key>`, an answer on the owner's waiting page, read from the
roadmap branch, or a decision id, read from docs/decisions/<id>.md. The stamp is `YYYY-MM-DD HH:MM CST|CDT` or
`HH:MM CST|CDT`.

A claim with no ref or no stamp, or a ref that does not resolve, refuses with no model call. A resolved cite costs
one model call. The call sees only the ruling texts and the Done acts, and the claims pass only when the model says
every ruling names its act. A model error or an odd answer refuses. A reply with no such Done item makes no model
call and no git read. The refusing rule is `ruling-skip-check`.

The fixture, the transcript helpers, the run folder and the model stub come from lint/test_report_guard.py and
hooks/test_call_judge.py, the one homes. Run with:

    python3 lint/test_report_guard_ruling_skip.py -v
"""
import json
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_report_guard as trg  # noqa: E402  the fixture, helpers, run folder and model stub (one home)
import report_guard  # noqa: E402  RULING_REFUTER_MODEL, the one model setting

tcj = trg.tcj  # hooks/test_call_judge.py: the claude stub's answers and the repo builder with a roadmap branch

RULE = "ruling-skip-check"
ACT = "skipped the owner pick on the apps' access"
NEXT_MARK = "NEXTMARK-4d1a"  # in the Next line, which the blind prompt must not carry
STAMP = "2026-11-06 13:08 CST"
ITEM_REF = "item 284 b"
DECISION_SLUG = "apps-keep-their-access"
OPTIONS = [
    {"key": "a", "label": "Remove the apps' access"},
    {"key": "b", "label": "Keep the apps' access as is, because calling into a repo is straightforward"},
    {"key": "c", "label": "Keep the apps' access and revisit in Q1"},
    {"key": "d", "label": "Keep the apps' access for one quarter"},
    {"key": "e", "label": "Move the apps to a second repo"},
    {"key": "f", "label": "Ask the vendor first"},
]
PICKED_LABEL = "calling into a repo is straightforward"
UNPICKED_LABEL = "revisit in Q1"
ANSWER_NOTE = "Keep as is; revisit if it gets bloated."
DECISION_RULING = ("Ruling (owner, 2026-10-28): keep the apps' access to claude-settings as is, because calling into a "
                   "repo is straightforward.")
LONG_SLUG = "long-record"
LONG_HEAD = "Ruling (owner, 2026-10-28): the record runs long. "
LONG_TAIL = "TAILMARK-9c1e"
LONG_RULING = LONG_HEAD + "Filler about the ruling. " * 700 + LONG_TAIL  # about 17,500 characters

CONFIRM = json.dumps({"ok": True, "reason": "item 284 b keeps the apps' access, which the Done item says it skipped"})
REJECT = json.dumps({"ok": False, "reason": "the ruling keeps the apps' access; the Done item names a different pick"})
ODD_ANSWERS = ("maybe", json.dumps({"ok": "true", "reason": "yes"}), json.dumps({"verdict": True}), json.dumps([True]))

ITEMS = {
    "w": {"id": "w", "n": 283, "question": "Keep the caps?", "options": OPTIONS},
    "x": {"id": "x", "n": 284, "question": "Keep the apps' access to claude-settings?", "options": OPTIONS},
    "y": {"id": "y", "n": 285, "question": "Keep the apps' access for a quarter?", "options": OPTIONS},
}
ANSWERS = {"x": {"choice": "b", "note": ANSWER_NOTE}}  # w and y have no answer: the empty state
RULING_REPO = tcj.make_repo("ruling", decisions={DECISION_SLUG: DECISION_RULING, LONG_SLUG: LONG_RULING},
                            waiting={"items": ITEMS, "answers": ANSWERS})
NO_ROADMAP_REPO = tcj.make_repo("ruling-no-roadmap", decisions={DECISION_SLUG: DECISION_RULING})

TRIGGER_RE = re.compile(r"\bunder (?:the )?(?:owner'?s? )?ruling\b", re.I)
STAMP_RE = re.compile(r"\b\d{1,2}:\d{2} (?:CST|CDT)\b")
REMEDY_RE = re.compile(r"owner|waiting page|Input Needed|cite a ruling", re.I)


def cite(ref=ITEM_REF, stamp=STAMP):
    """A ruling cite. A None ref or stamp leaves that part out."""
    return " ".join(["under ruling"] + ([ref] if ref else []) + (["(%s)" % stamp] if stamp else []))


def done(text, act=ACT):
    return "> **Done** OTHER %s %s" % (act, text)


def reply(*done_lines):
    return "\n".join([*done_lines, "> **Next** wait %s" % NEXT_MARK])


def refused_by_rule(out):
    return out.get("decision") == "block" and RULE in out.get("reason", "")


def setUpModule():
    trg.setUpModule()  # the run folder, CLAUDE_CONFIG_DIR and the model stub, set as test_report_guard sets them


def tearDownModule():
    trg.tearDownModule()


class RulingSkipFixture(unittest.TestCase):
    """Stop runs on a reply. The stub answers with CJ_ANSWER, fails with CJ_MODEL_FAIL, and records each model call
    and each git process the guard starts. The stub's recording and reading are borrowed from PastRulingRelay."""

    model_calls = trg.PastRulingRelay.model_calls
    git_starts = trg.PastRulingRelay.git_starts
    reset_calls = trg.PastRulingRelay.reset_calls

    def setUp(self):
        self.run_dir = tempfile.mkdtemp(dir=trg.RUN_FOLDER)  # the run folder, never the system temp dir
        self.record = os.path.join(trg._ISOLATION["stub"], "calls.jsonl")

    def stop(self, reply_text, answer=tcj.ALLOW, model_fail=False, repo=None):
        self.reset_calls()
        path = trg.write_transcript([trg.human("decide"), trg.assistant_text(reply_text)], self.run_dir)
        hook = {"hook_event_name": "Stop", "transcript_path": path, "stop_hook_active": False,
                "cwd": repo or RULING_REPO}
        overrides = {"CJ_ANSWER": answer}
        if model_fail:
            overrides["CJ_MODEL_FAIL"] = "1"
        with mock.patch.dict(os.environ, overrides):
            run = trg.run_guard(trg.REPORT_GUARD, hook)
        self.assertEqual(run.returncode, 0, run.stderr)
        return json.loads(run.stdout) if run.stdout.strip() else {}

    def assert_refused(self, out, cause):
        self.assertEqual(out.get("decision"), "block", cause)
        self.assertIn(RULE, out.get("reason", ""), cause + ": refused, but not by " + RULE)


class RulingSkipTests(RulingSkipFixture):

    def test_1_claim_with_no_ref_or_no_stamp_is_refused_with_no_model_call(self):
        for label, text in (
                ("no ref", done(cite(ref=None))),
                ("no stamp", done(cite(stamp=None))),
                ("neither, the owner's ruling", done("under the owner's ruling")),
                ("capitalised, no ref", done("Under Ruling (%s)" % STAMP))):
            with self.subTest(claim=label):
                out = self.stop(reply(text))
                self.assert_refused(out, "%s: a claim with no ref or no stamp passed" % label)
                self.assertEqual(self.model_calls(), [], "%s: the model ran before the cite was checked" % label)

    def test_2_good_cite_the_model_rejects_is_refused(self):
        for label, ref, named in (("item", ITEM_REF, "284"), ("decision", DECISION_SLUG, DECISION_SLUG)):
            with self.subTest(cite=label):
                out = self.stop(reply(done(cite(ref=ref))), answer=REJECT)
                self.assert_refused(out, "%s: a cite the model rejects passed" % label)
                self.assertEqual(len(self.model_calls()), 1, "%s: the model was not asked about the cite" % label)
                self.assertIn(named, out["reason"], "%s: the refusal does not name the record it cites" % label)

    def test_3_good_cite_the_model_confirms_passes(self):
        for label, text, needles in (
                ("item, full stamp", done(cite(ITEM_REF)), [PICKED_LABEL, ANSWER_NOTE]),
                ("item, short stamp", done(cite(ITEM_REF, "13:08 CDT")), [PICKED_LABEL, ANSWER_NOTE]),
                ("decision, full stamp", done(cite(DECISION_SLUG)), ["keep the apps' access to claude-settings as is"])):
            with self.subTest(cite=label):
                out = self.stop(reply(text), answer=CONFIRM)
                self.assertNotEqual(out.get("decision"), "block", "%s: a confirmed cite was refused" % label)
                calls = self.model_calls()
                self.assertEqual(len(calls), 1, "%s: the check made %d model calls, not one" % (label, len(calls)))
                self.assertEqual(tcj.model_of(calls[0]["argv"]), report_guard.RULING_REFUTER_MODEL,
                                 "%s: the check did not call the named refuter model" % label)
                prompt = calls[0]["prompt"]
                for needle in [*needles, ACT]:
                    self.assertIn(needle, prompt, "%s: the prompt lacks the ruling text or the Done act" % label)
                self.assertNotIn(UNPICKED_LABEL, prompt, "%s: the prompt carries an option the owner did not pick" % label)
                self.assertNotIn(NEXT_MARK, prompt, "%s: the prompt carries the reply outside the Done acts" % label)
                self.assertLessEqual(self.git_starts(), 2, "%s: more than two git reads for one cite" % label)

    def test_3_two_claims_share_one_model_call(self):
        out = self.stop(reply(done(cite(ITEM_REF)), done(cite(DECISION_SLUG))), answer=CONFIRM)
        self.assertNotEqual(out.get("decision"), "block", "two confirmed cites were refused")
        calls = self.model_calls()
        self.assertEqual(len(calls), 1, "two claims made %d model calls, not one" % len(calls))
        self.assertIn(PICKED_LABEL, calls[0]["prompt"], "the item ruling is missing from the one prompt")
        self.assertIn("claude-settings as is", calls[0]["prompt"], "the decision ruling is missing from the one prompt")

    def test_3_full_size_record_is_capped_in_the_prompt(self):
        out = self.stop(reply(done(cite(LONG_SLUG))), answer=CONFIRM)
        self.assertNotEqual(out.get("decision"), "block", "a confirmed full-size record was refused")
        calls = self.model_calls()
        self.assertEqual(len(calls), 1, "the full-size record was not judged: %d calls" % len(calls))
        self.assertIn(LONG_HEAD, calls[0]["prompt"], "the record's head is missing from the prompt")
        self.assertNotIn(LONG_TAIL, calls[0]["prompt"], "the whole decision record went into the prompt, not its capped head")

    def test_4_model_error_or_odd_answer_is_refused(self):
        cases = [("model error", None, True)] + [("odd answer %r" % a[:20], a, False) for a in ODD_ANSWERS]
        for label, answer, fail in cases:
            with self.subTest(model=label):
                out = self.stop(reply(done(cite(ITEM_REF))), answer=answer or CONFIRM, model_fail=fail)
                self.assert_refused(out, "%s: a model failure or an odd answer passed" % label)
                self.assertEqual(len(self.model_calls()), 1, "%s: the model was not asked once" % label)

    def test_5_unresolved_ref_is_refused_with_no_model_call(self):
        for label, ref, repo in (
                ("no item with that n", "item 999 a", None),
                ("key not in the answer's choice", "item 284 c", None),
                ("key not an option", "item 284 z", None),
                ("item with no answer", "item 285 a", None),
                ("decision with no record", "no-such-record", None),
                ("no roadmap branch", ITEM_REF, NO_ROADMAP_REPO)):
            with self.subTest(ref=label):
                out = self.stop(reply(done(cite(ref=ref))), repo=repo)
                self.assert_refused(out, "%s: a ref that does not resolve passed" % label)
                self.assertEqual(self.model_calls(), [], "%s: the model ran on a ref that does not resolve" % label)

    def test_6_reply_without_a_ruling_claim_makes_no_call_and_no_git_read(self):
        for label, text in (
                ("plain Done", "> **Done** BUILT abc123\n> **Next** wait %s" % NEXT_MARK),
                ("cite only in Next", "> **Done** BUILT abc123\n> **Next** check under ruling %s (%s)" % (ITEM_REF, STAMP)),
                ("under review", reply(done("read the apps' access under review"))),
                ("per the ruling", reply(done(cite(ITEM_REF).replace("under ruling", "per the ruling")))),
                ("rulings elsewhere", reply(done("read the rulings log")))):
            with self.subTest(claim=label):
                done_lines = "\n".join(line for line in text.splitlines() if line.startswith("> **Done**"))
                self.assertIsNone(TRIGGER_RE.search(done_lines), "%s: the scope is not a ruling-free Done item" % label)
                out = self.stop(text)
                self.assertFalse(refused_by_rule(out), "%s: a reply with no ruling claim was refused by the check" % label)
                self.assertEqual(self.model_calls(), [], "%s: the model ran with no ruling claim" % label)
                self.assertEqual(self.git_starts(), 0, "%s: git was read with no ruling claim" % label)

    def test_7_refusal_text_names_no_marker_or_passing_line(self):
        scenarios = (
            ("no ref", lambda: self.stop(reply(done(cite(ref=None))))),
            ("rejected cite", lambda: self.stop(reply(done(cite(ITEM_REF))), answer=REJECT)),
            ("unresolved ref", lambda: self.stop(reply(done(cite("item 999 a"))))),
            ("model error", lambda: self.stop(reply(done(cite(ITEM_REF))), model_fail=True)),
        )
        for label, run in scenarios:
            with self.subTest(refusal=label):
                out = run()
                self.assert_refused(out, "%s: no refusal to read the text of" % label)
                reason = out["reason"]
                self.assertIsNone(TRIGGER_RE.search(reason), "%s: the refusal names the trigger phrase" % label)
                self.assertIsNone(STAMP_RE.search(reason), "%s: the refusal names a stamp, which would pass a cite" % label)
                self.assertRegex(reason, REMEDY_RE, "%s: the refusal names no remedy" % label)


if __name__ == "__main__":
    unittest.main()
