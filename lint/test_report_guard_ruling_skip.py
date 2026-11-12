#!/usr/bin/env python3
"""The ruling-skip check: a Done item that says it picked under a ruling must cite that ruling.

A Done item makes a pick claim when report_guard's RULING_PICK_RE (a pick word) and RULING_CUE_RE (a ruling cue)
both match it. The cases import both from report_guard, the one home, and copy neither. Its cite is
`under ruling <ref> (<stamp>)`. The ref is
`item <N> <key>`, an answer on the owner's waiting page, read from the roadmap branch, or a decision id, read from
docs/decisions/<id>.md. The stamp is `YYYY-MM-DD HH:MM CST|CDT` or `HH:MM CST|CDT`.

A claim with no ref or no stamp, or a ref that does not resolve, refuses with no model call. A resolved cite costs
one model call. The call sees only the ruling texts and the Done acts, and the claims pass only when the model says
every ruling names its act. A model error, a timeout or an odd answer refuses. The two model calls of one Stop share
the Stop hook's time. A reply with no pick claim makes no model call and no git read. The refusing rule is
`ruling-skip-check`.

The fixture, the transcript helpers, the run folder and the model stub come from lint/test_report_guard.py and
hooks/test_call_judge.py, the one homes. Run with:

    python3 lint/test_report_guard_ruling_skip.py -v
"""
import json
import os
import re
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_report_guard as trg  # noqa: E402  the fixture, helpers, run folder and model stub (one home)
import report_guard  # noqa: E402  RULING_REFUTER_MODEL, the one model setting, and the Stop deadline
import decision_watch  # noqa: E402  the one model call, patched in the in-process cases
import question_form  # noqa: E402  the roadmap reader, spied on in the in-process cases

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
# A record whose ruling bullet sits past byte 6000 but within 6000 characters: the cap is in bytes.
LONG_MB_SLUG = "long-multibyte"
LONG_MB_MARK = "BYTEMARK-2b8c"
LONG_MB_RULING = "Ruling (owner, 2026-10-28): the bullets follow.\n" + "é" * 3500 + "\n- " + LONG_MB_MARK + ": keep the apps' access as is.\n"
# An ASCII record whose bullet sits past byte 6000 and past 6000 characters: the head cap already leaves it out.
LONG_ASCII_SLUG = "long-ascii"
LONG_ASCII_MARK = "ASCIIMARK-5e9d"
LONG_ASCII_RULING = "Ruling (owner, 2026-10-28): the bullets follow.\n" + "x" * 6100 + "\n- " + LONG_ASCII_MARK + ": keep the apps' access as is.\n"

CONFIRM = json.dumps({"ok": True, "reason": "item 284 b keeps the apps' access, which the Done item says it skipped"})
REJECT = json.dumps({"ok": False, "reason": "the ruling keeps the apps' access; the Done item names a different pick"})
ODD_ANSWERS = ("maybe", json.dumps({"ok": "true", "reason": "yes"}), json.dumps({"verdict": True}), json.dumps([True]))

ITEM_TITLE = "Keep the apps' access to claude-settings?"  # a real waiting item keeps its question in `title`
ITEMS = {
    "w": {"id": "w", "n": 283, "title": "Keep the caps?", "options": OPTIONS},
    "x": {"id": "x", "n": 284, "title": ITEM_TITLE, "options": OPTIONS},
    "y": {"id": "y", "n": 285, "title": "Keep the apps' access for a quarter?", "options": OPTIONS},
}
ANSWERS = {"x": {"choice": "b", "note": ANSWER_NOTE}}  # w and y have no answer: the empty state
RULING_REPO = tcj.make_repo("ruling", decisions={
    DECISION_SLUG: DECISION_RULING, LONG_SLUG: LONG_RULING, LONG_MB_SLUG: LONG_MB_RULING,
    LONG_ASCII_SLUG: LONG_ASCII_RULING, tcj.APPS_SLUG: tcj.APPS_RULING}, waiting={"items": ITEMS, "answers": ANSWERS})
NO_ROADMAP_REPO = tcj.make_repo("ruling-no-roadmap", decisions={DECISION_SLUG: DECISION_RULING})
# The page closed item x: its answer file is gone, and the item keeps lastAnswer. Item s still has its answer file,
# so the answers folder exists on the branch.
FILED_ITEMS = {
    "s": {"id": "s", "n": 280, "title": "Keep the caps?", "options": OPTIONS},
    "x": {"id": "x", "n": 284, "title": ITEM_TITLE, "options": OPTIONS,
          "lastAnswer": {"choice": "b", "note": ANSWER_NOTE}},
}
FILED_ANSWERS = {"s": {"choice": "a", "note": "Remove the caps."}}
FILED_REPO = tcj.make_repo("ruling-filed", waiting={"items": FILED_ITEMS, "answers": FILED_ANSWERS})

TRIGGER_RE = re.compile(r"\bunder (?:the )?(?:owner'?s? )?ruling\b", re.I)
STAMP_RE = re.compile(r"\b\d{1,2}:\d{2} (?:CST|CDT)\b")
REMEDY_RE = re.compile(r"owner|waiting page|Input Needed|cite a ruling", re.I)


def stop_timeout():
    """The Stop hook's timeout for report_guard, read from settings.json: the time all of the guard's work shares."""
    with open(os.path.join(HERE, "..", "settings.json"), encoding="utf-8") as handle:
        settings = json.load(handle)
    for entry in settings["hooks"]["Stop"]:
        for hook in entry.get("hooks", []):
            if "report_guard.py" in hook.get("command", ""):
                return hook["timeout"]
    raise ValueError("settings.json has no Stop hook that runs report_guard.py")


STOP_TIMEOUT = stop_timeout()
PRINT_ROOM = 5  # seconds the Stop hook keeps after its shared model budget, to print its reply
STOP_BUDGET_CEILING = STOP_TIMEOUT - PRINT_ROOM  # the most model time one Stop may spend: 75 s under the 80 s timeout


def is_pick_claim(text):
    return bool(report_guard.RULING_PICK_RE.search(text) and report_guard.RULING_CUE_RE.search(text))


def cite(ref=ITEM_REF, stamp=STAMP):
    """A ruling cite. A None ref or stamp leaves that part out."""
    return " ".join(["under ruling"] + ([ref] if ref else []) + (["(%s)" % stamp] if stamp else []))


def done(text, act=ACT):
    return "> **Done** OTHER %s %s" % (act, text)


def reply(*done_lines):
    return "\n".join([*done_lines, "> **Next** wait %s" % NEXT_MARK])


def pick_and_question():
    """A pick claim with a cite, and an Input Needed question the past-ruling check reads: two model calls in one Stop."""
    return "\n".join([done(cite(ITEM_REF)), trg.RELAY, "> **Next** wait %s" % NEXT_MARK])


def refused_by_rule(out):
    return out.get("decision") == "block" and RULE in out.get("reason", "")


def setUpModule():
    trg.setUpModule()  # the run folder, CLAUDE_CONFIG_DIR and the model stub, set as test_report_guard sets them


def tearDownModule():
    trg.tearDownModule()


class RulingSkipFixture(unittest.TestCase):
    """Stop runs on a reply. The stub answers with CJ_ANSWER, fails with CJ_MODEL_FAIL, raises a timeout with
    CJ_TIMEOUT_HIT, and records each model call (its prompt and timeout) and each git process the guard starts. The
    stub's recording and reading are borrowed from PastRulingRelay."""

    model_calls = trg.PastRulingRelay.model_calls
    git_starts = trg.PastRulingRelay.git_starts
    reset_calls = trg.PastRulingRelay.reset_calls

    def setUp(self):
        self.run_dir = tempfile.mkdtemp(dir=trg.RUN_FOLDER)  # the run folder, never the system temp dir
        self.record = os.path.join(trg._ISOLATION["stub"], "calls.jsonl")

    def stop(self, reply_text, answer=tcj.ALLOW, model_fail=False, repo=None, timeout_hit=False, active=False,
             session_id=None):
        self.reset_calls()
        path = trg.write_transcript([trg.human("decide"), trg.assistant_text(reply_text)], self.run_dir)
        hook = {"hook_event_name": "Stop", "transcript_path": path, "stop_hook_active": active,
                "cwd": repo or RULING_REPO}
        if session_id:
            hook["session_id"] = session_id
        overrides = {"CJ_ANSWER": answer}
        if model_fail:
            overrides["CJ_MODEL_FAIL"] = "1"
        if timeout_hit:
            overrides["CJ_TIMEOUT_HIT"] = "1"
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

    def test_6_reply_without_a_pick_claim_makes_no_call_and_no_git_read(self):
        for label, text in (
                ("plain Done", "> **Done** BUILT abc123\n> **Next** wait %s" % NEXT_MARK),
                ("cite only in Next", "> **Done** BUILT abc123\n> **Next** check under ruling %s (%s)" % (ITEM_REF, STAMP)),
                ("under review", "> **Done** OTHER read the apps' access under review\n> **Next** wait %s" % NEXT_MARK),
                ("per the ruling, no pick", "> **Done** OTHER read the apps' access per the ruling item 284 b (%s)\n"
                                            "> **Next** wait %s" % (STAMP, NEXT_MARK)),
                ("rulings elsewhere", "> **Done** OTHER read the rulings log\n> **Next** wait %s" % NEXT_MARK)):
            with self.subTest(claim=label):
                done_lines = "\n".join(line for line in text.splitlines() if line.startswith("> **Done**"))
                self.assertFalse(is_pick_claim(done_lines), "%s: the scope is a pick claim" % label)
                out = self.stop(text)
                self.assertFalse(refused_by_rule(out), "%s: a reply with no pick claim was refused by the check" % label)
                self.assertEqual(self.model_calls(), [], "%s: the model ran with no pick claim" % label)
                self.assertEqual(self.git_starts(), 0, "%s: git was read with no pick claim" % label)

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

    # A filed ruling resolves from its last answer. A pick claim with no cite is refused; a Done item with no pick is not.
    # Model calls share one Stop deadline, and a long record is cut at 6000 bytes so the prompt stays bounded.

    def test_r1_filed_ruling_resolves_from_its_last_answer(self):
        # The page's Route-and-close deletes the answer file and keeps lastAnswer on the item.
        out = self.stop(reply(done(cite(ITEM_REF))), answer=CONFIRM, repo=FILED_REPO)
        self.assertNotEqual(out.get("decision"), "block", "a filed ruling with its lastAnswer was refused")
        calls = self.model_calls()
        self.assertEqual(len(calls), 1, "the filed ruling never reached the model: %d calls" % len(calls))
        self.assertIn(PICKED_LABEL, calls[0]["prompt"], "the filed ruling's picked label is missing from the prompt")
        self.assertIn(ANSWER_NOTE, calls[0]["prompt"], "the filed ruling's note is missing from the prompt")

    def test_r1_key_outside_the_last_answer_is_refused_with_no_model_call(self):
        out = self.stop(reply(done(cite("item 284 c"))), answer=CONFIRM, repo=FILED_REPO)
        self.assert_refused(out, "a key not in the filed lastAnswer passed")
        self.assertEqual(self.model_calls(), [], "the model ran on a key the filed answer does not name")

    def test_r2_done_items_with_no_pick_make_no_call(self):
        for label, line in (
                ("a rewrite under the owner's ruling", "> **Done** RECORDED: rewrote X under the owner's ruling (PR #611)"),
                ("a lane named for the rule", "> **Done** BUILT: under ruling-skip-check lane (PR #9)")):
            with self.subTest(claim=label):
                self.assertFalse(is_pick_claim(line), "%s: the scope is a pick claim" % label)
                out = self.stop(reply(line))
                self.assertFalse(refused_by_rule(out), "%s: a Done item with no pick was refused by the check" % label)
                self.assertEqual(self.model_calls(), [], "%s: the model ran on a Done item with no pick" % label)

    def test_r3_pick_claims_with_no_cite_are_refused_with_no_model_call(self):
        for act in ("took pick a per the owner's ruling", "picked b under a ruling", "chose c per ruling",
                    "took a under the owner's rulings", "skipped asking: the owner's ruling covers it"):
            with self.subTest(claim=act):
                self.assertTrue(is_pick_claim(act), "%s: the scope is not a pick claim" % act)
                out = self.stop(reply("> **Done** OTHER " + act))
                self.assert_refused(out, "%r: a pick claim with no cite passed" % act)
                self.assertEqual(self.model_calls(), [], "%r: the model ran on a pick claim with no cite" % act)

    def test_r4_one_deadline_caps_both_model_calls(self):
        # The past-ruling check and the refuter share the Stop hook's time, which the guard's own work also spends.
        self.stop(pick_and_question(), answer=tcj.ALLOW, repo=RULING_REPO)
        calls = self.model_calls()
        self.assertEqual(len(calls), 2, "the past-ruling check and the refuter made %d model calls, not two" % len(calls))
        timeouts = [call.get("timeout") for call in calls]
        self.assertTrue(all(isinstance(t, (int, float)) for t in timeouts), "a model call had no timeout: %r" % timeouts)
        self.assertLess(sum(timeouts), STOP_TIMEOUT,
                        "the two model calls may spend %s s, but the Stop hook has %s s for all its work"
                        % (sum(timeouts), STOP_TIMEOUT))
        # The timeout is not the limit that keeps the print room: the shared budget is, so both must stay under it.
        self.assertLessEqual(sum(timeouts), STOP_BUDGET_CEILING,
                             "the two model calls may spend %s s, past the %s s that leave the Stop hook room to print"
                             % (sum(timeouts), STOP_BUDGET_CEILING))
        self.assertLessEqual(report_guard.STOP_BUDGET, STOP_BUDGET_CEILING,
                             "report_guard.STOP_BUDGET is %s s, past the %s s that leave the Stop hook room to print"
                             % (report_guard.STOP_BUDGET, STOP_BUDGET_CEILING))

    def test_r4_a_deadline_hit_refuses_and_does_not_pass(self):
        out = self.stop(pick_and_question(), answer=tcj.ALLOW, repo=RULING_REPO, timeout_hit=True)
        self.assert_refused(out, "a model call that hit its deadline let the claim pass")

    def test_r5_long_decision_record_is_capped_in_bytes(self):
        for label, slug, record, mark in (
                ("multibyte, mark past byte 6000", LONG_MB_SLUG, LONG_MB_RULING, LONG_MB_MARK),
                ("ascii, mark past byte 6000", LONG_ASCII_SLUG, LONG_ASCII_RULING, LONG_ASCII_MARK)):
            with self.subTest(record=label):
                self.assertGreater(len(record.encode("utf-8")), 6000, "%s: the record is not over 6000 bytes" % label)
                self.assertGreater(record.encode("utf-8").index(mark.encode("utf-8")), 6000,
                                   "%s: the mark is not past byte 6000" % label)
                self.stop(reply(done(cite(slug))), answer=CONFIRM, repo=RULING_REPO)
                calls = self.model_calls()
                self.assertEqual(len(calls), 1, "%s: the record was not judged: %d calls" % (label, len(calls)))
                self.assertNotIn(mark, calls[0]["prompt"], "%s: the bullet past byte 6000 went into the prompt" % label)

    # The refuter judges a cite against the item's title, so the title must reach its prompt.
    # A Done item that uses a ruling word without a pick claims nothing.

    def test_r6_item_title_reaches_the_refuter_prompt(self):
        self.stop(reply(done(cite(ITEM_REF))), answer=CONFIRM, repo=RULING_REPO)
        calls = self.model_calls()
        self.assertEqual(len(calls), 1, "the cited item did not reach the model: %d calls" % len(calls))
        self.assertIn(ITEM_TITLE, calls[0]["prompt"], "the item's title is missing from the refuter prompt")

    def test_r7_done_items_that_name_a_word_but_make_no_pick_claim_pass(self):
        for label, line in (
                ("pick-route compound", "> **Done** BUILT: re-pointed three pick-route cases to the owner's ruling (PR #9)"),
                ("cherry-pick", "> **Done** OTHER: cherry-pick of the ruling census fix"),
                ("took minutes", "> **Done** OTHER: round 2 took 4 min; the ruling table is regenerated")):
            with self.subTest(claim=label):
                self.assertTrue(report_guard.RULING_CUE_RE.search(line), "%s: the scope has no ruling cue" % label)
                out = self.stop(reply(line))
                self.assertFalse(refused_by_rule(out), "%s: a Done item with no pick was refused by the check" % label)
                self.assertEqual(self.model_calls(), [], "%s: the model ran on a Done item with no pick" % label)

    # A pick word and a ruling word that do not govern each other make no pick under a ruling.
    # A cite names a ruling, an item and a time, and may put "on" before the item. A valid cite must not be refused.

    def test_r8_pick_words_that_name_no_pick_under_a_ruling_pass(self):
        for label, line in (
                ("a pick list, the ruling is its object", "> **Done** OTHER the pick list shows each ruling"),
                ("took a look, the ruling is its object", "> **Done** OTHER took a look at the owner's ruling"),
                ("the key ruling, not a key pick", "> **Done** OTHER took the key ruling into the check"),
                ("chose, and a ruling in another clause", "> **Done** BUILT chose the simpler test; the ruling table is "
                                                          "regenerated")):
            with self.subTest(claim=label):
                self.assertTrue(is_pick_claim(line), "%s: the line has no pick word and ruling cue, so it probes nothing"
                                % label)
                out = self.stop(reply(line))
                self.assertFalse(refused_by_rule(out), "%s: a Done item with no pick under a ruling was refused" % label)
                self.assertEqual(self.model_calls(), [], "%s: the model ran on a Done item with no pick under a ruling"
                                 % label)

    def test_r9_a_cite_with_on_before_its_item_is_accepted(self):
        line = "> **Done** OTHER picked b under the owner's ruling on item 284 b (13:08 CST)"
        self.assertTrue(is_pick_claim(line), "the cited line is not a pick claim, so it does not probe the cite")
        out = self.stop(reply(line), answer=CONFIRM)
        self.assertNotEqual(out.get("decision"), "block", "a valid cite with 'on' before its item was refused")
        calls = self.model_calls()
        self.assertEqual(len(calls), 1, "the cite never reached the model: %d calls" % len(calls))
        self.assertIn(PICKED_LABEL, calls[0]["prompt"], "the cited item's ruling is missing from the prompt")

    # With the refuter down, a rewrite must not be refused on every Stop: the first Stop refuses, and the rewrites pass.

    def test_r10_refuter_down_refuses_the_first_stop_and_not_the_rewrites_after_it(self):
        sid = "ruling-skip-outage"
        line = done(cite(ITEM_REF))
        self.assertTrue(is_pick_claim(line), "the cited line is not a pick claim, so the outage is not on the check")
        first = self.stop(reply(line), model_fail=True, session_id=sid)
        self.assert_refused(first, "the first Stop with the refuter down passed the claim")
        for attempt in (2, 3):
            with self.subTest(rewrite=attempt):
                out = self.stop(reply(line), model_fail=True, session_id=sid, active=True)
                self.assertFalse(refused_by_rule(out), "rewrite %d under the same refuter outage was refused again"
                                 % attempt)


class SpentDeadlineTests(unittest.TestCase):
    """The shared Stop deadline, checked in this process. report_guard's start time (`_STARTED`) is the seam: setting it
    far back spends the deadline with no wait. The model call is patched here, because the check runs in this process.
    `spend()` runs right after the chosen roadmap read, so one case can spend the deadline between its reads and its
    refuter."""

    def setUp(self):
        for patch in (mock.patch.object(report_guard, "_STARTED", report_guard._STARTED),
                      mock.patch.object(report_guard, "_granted", 0.0),
                      mock.patch.object(decision_watch, "invoke_model", return_value=(json.loads(CONFIRM), ""))):
            self.addCleanup(patch.stop)
            patch.start()
        self.invoke = decision_watch.invoke_model

    def check(self, text, spent_at_start=False, spend_after=None):
        """(refusal, reads) of ruling_skip_problem on `text`. `reads` names each roadmap folder read, in order."""
        reads = []
        real_read = question_form.read_json_folder

        def spend():
            report_guard._STARTED = time.monotonic() - report_guard.STOP_BUDGET - 1

        def read(root, folder, refs, *rest):
            reads.append(folder)
            result = real_read(root, folder, refs, *rest)
            if folder == spend_after:
                spend()
            return result

        with mock.patch.object(question_form, "read_json_folder", read):
            if spent_at_start:
                spend()
            refusal = report_guard.ruling_skip_problem(text, RULING_REPO)
        return refusal, reads

    def test_s0_unspent_deadline_passes_a_confirmed_item_cite(self):
        refusal, _ = self.check(reply(done(cite(ITEM_REF))))
        self.assertEqual(refusal, "", "an unspent deadline refused a confirmed cite: %s" % refusal)
        self.assertEqual(self.invoke.call_count, 1, "the confirmed cite did not reach the model")

    def test_s1_spent_deadline_refuses_the_item_read_with_no_read_and_no_model_call(self):
        refusal, reads = self.check(reply(done(cite(ITEM_REF))), spent_at_start=True)
        self.assertEqual(reads, [], "the roadmap was read after the Stop deadline was spent")
        self.assertIn(RULE, refusal, "a spent deadline let the item cite pass")
        self.assertEqual(self.invoke.call_count, 0, "the model ran after the Stop deadline was spent")

    def test_s2_spent_deadline_after_the_reads_refuses_the_refuter_with_no_model_call(self):
        refusal, reads = self.check(reply(done(cite(ITEM_REF))), spend_after="waiting/answers")
        self.assertEqual(reads, ["waiting/items", "waiting/answers"], "the two roadmap reads did not both run")
        self.assertIn(RULE, refusal, "a spent deadline before the refuter let the item cite pass")
        self.assertEqual(self.invoke.call_count, 0, "the refuter ran after the Stop deadline was spent")

    def test_s3_spent_deadline_refuses_a_decision_cite_with_no_model_call(self):
        refusal, _ = self.check(reply(done(cite(DECISION_SLUG))), spent_at_start=True)
        self.assertIn(RULE, refusal, "a spent deadline let the decision cite pass")
        self.assertEqual(self.invoke.call_count, 0, "the refuter ran on a decision cite after the Stop deadline was spent")

    def test_s4_a_review_check_that_spends_its_budget_leaves_the_refuter_its_full_limit(self):
        # The review check runs first in the same Stop, on REVIEW_CHECK_BUDGET, and the refuter takes what is left of
        # STOP_BUDGET. Once the review has spent its whole budget, the refuter must still get its full limit.
        clock = 1000.0
        with mock.patch.object(report_guard.time, "monotonic", return_value=clock):
            report_guard._STARTED = clock - report_guard.REVIEW_CHECK_BUDGET
            timeout = report_guard.call_timeout(report_guard.RULING_REFUTER_TIMEOUT, model=True)
        self.assertIsNotNone(timeout, "no time was left for the refuter after the review check's whole budget")
        self.assertGreaterEqual(timeout, report_guard.RULING_REFUTER_TIMEOUT,
                                "after the review check's %s s, the refuter got %s s, under its %s s limit"
                                % (report_guard.REVIEW_CHECK_BUDGET, timeout, report_guard.RULING_REFUTER_TIMEOUT))


if __name__ == "__main__":
    unittest.main()
