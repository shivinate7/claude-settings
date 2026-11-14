#!/usr/bin/env python3
"""Prose contract for the page's close: skills/waiting-page/SKILL.md, "Route and close" and "Read the answers".

    python3 -m unittest lint/test_page_close_keeps_answer.py

A close keeps the owner's answer. Only a reword (step 3 or 4) or an overturn (step 5) deletes the answer, and a lane reopen keeps
it. The park branch is the one exception: a park closes its item and deletes its answer, so a sentence about a close carries a
non-park scope. Reads prose only and runs none of the skill's code. Each case pins one claim:
  1. Step 2 (the close) has no sentence that deletes the answer, however worded.
  2. Step 2 says the close keeps the answer.
  3. No sentence outside the park sentences says a close, or step 2, deletes the answer, however worded.
  4. Steps 3 and 4, and the overturn, still delete the answer (control).
  5. No sentence says a reopen deletes the answer. "Reopen" and "open it again" both name a reopen.
  6. A sentence says a delete of the answer comes only from a reword or an overturn, and names no reopen.
  7. The lane reopen (reopen with lane and lastAnswer) says the answer is kept.
  8. The turn-start read says the owning session skips a kept answer on a closed item and does not route it again.
  9. The helper flags "Never close an item without deleting `answers/<id>`." (a mutant that a negation word let pass).
 10. The helper flags "Do not forget to delete `answers/<id>`." (a mutant).
 11. The helper flags "Never skip deleting `answers/<id>`." (a mutant).
 12. The turn-start skip names the exception for an overturn of an arbiter ruling.
 13. No sentence says step 2 skips its delete: a step that skips a delete is named by its own number, not step 2.
 14. Every close sentence that names a delete of the answer, negated or not, outside the park sentences, carries a non-park scope.
 15. Route and close, before the park branch, deletes the answer only in steps 3 and 4, the overturn and a reword sentence.
 16. The route scan flags a sub-bullet "- Then delete `answers/<id>`." under step 2 (a mutant).
 17. The route scan flags a standalone "The writer then deletes `answers/<id>` for good." (a mutant).
 18. The route scan flags "Then clear `answers/<id>`." at the end of step 2 (a mutant).
 19. The reopen check flags "Open it again with `lane` and `lastAnswer`, and delete `answers/<id>`." (a mutant).
 20. A "never" or "not" right before the delete verb reads as no delete, with or without a non-park scope.
 21. A non-park scope does not excuse a delete that no approved sentence allows.
 22. Delete, drop, remove, discard, clear, rm and unlink count only when the answer, answers/<id> or it is their object.

How the scope words and the approved sentence work:
  A negation is "never" or "not" right before the delete verb. Any other word before the verb ("without", "to", "skip") leaves
  the delete a delete.
  NON_PARK names the scope a close sentence may carry: "non-park", "except a park" or "other than a park". is_park() ignores
  those words, so a scoped close sentence is still checked.
  APPROVED_NEGATED holds the one sentence whose delete is a prohibition ("is wrong"). SCOPE_CLAUSE removes a non-park scope
  clause from a sentence before the word-for-word compare, so the approved sentence matches with or without that clause.
  The park branch starts at PARK_BRANCH. route_deletes reads the Route and close text before it. The park branch is exempt.

Ruling: triage, 15:01 CST Nov 12 (pick a: page_grant rule 4 stays, lane checks run before close, park unchanged, kept-answer
line stays without delete remedy), recorded in the roadmap record.
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(HERE, "..", "skills", "waiting-page", "SKILL.md")

ROUTE_HEADING = "## Route and close"
READ_HEADING = "## Read the answers"
CLOSE_STEP = "2. Close the item"  # the list item that closes an item
REWORD_STEP = "3. If the answer is"  # the list item for a `none` answer with no clear direction
CONTEXT_STEP = "4. If any other answer"  # the list item for any other answer that is not clear
OVERTURN_SENTENCE = "The ruling's record stands"  # the one sentence of the overturn's delete, in its own block
PARK_BRANCH = "A parked answer ("  # the first sentence of the park branch, the last part of Route and close

ROUTE_NAME = re.compile(r'"Route and close"')  # the heading's name, quoted in SKILL.md: its words name no close act
DELETE_VERB = re.compile(r"\b(?:delet\w*|drop\w*|remov\w*|discard\w*|eras\w*|purg\w*|wip\w*|clear(?:s|ed)?|rm|unlink\w*)\b", re.I)
# The object right after a delete verb: the answer as `answers/<id>`, answers/<id>, the answer or the answers, or it or them.
# A bare "answer" is no object, so "a clear answer" never reads as a delete.
ANSWER_OBJECT = re.compile(r"\s*(?:(?:the|its|their)\s+)?`?answers/|\s*(?:the|its|their)\s+answers?\b|\s*(?:it|them)\b", re.I)
NEG_BEFORE = re.compile(r"\b(?:never|not)\s*$", re.I)  # the word right before a delete verb that makes it a negation
ANSWER_WORD = re.compile(r"\banswers?\b", re.I)  # answers/<id>, the answer, the answers; never lastAnswer
CLOSE = re.compile(r"\bclos\w*", re.I)
STEP_TWO = re.compile(r"\bsteps? 2\b", re.I)
KEEP = re.compile(r"\bkeeps?\b|\bkept\b", re.I)
KEEP_OR_STAY = re.compile(r"\bkeeps?\b|\bkept\b|\bstays?\b|\bremains?\b|\bin place\b", re.I)
PARK = re.compile(r"\bpark", re.I)
NON_PARK = re.compile(r"\bnon-park\b|\bexcept (?:in )?a park\b|\bother than (?:a )?park\b", re.I)  # the scope a close may carry
# A scope clause, removed before an approved sentence is compared: "non-park ", " (except a park)", ", except a park".
SCOPE_CLAUSE = re.compile(r"non-park\s+|\s*\(\s*(?:except (?:in )?a park|other than (?:a )?park)\s*\)"
                          r"|,?\s*(?:except (?:in )?a park|other than (?:a )?park)(?=\W|$)", re.I)
LANE = re.compile(r"\blane\b", re.I)
LAST_ANSWER = re.compile(r"\blastAnswer\b")
ONLY = re.compile(r"\bonly\b", re.I)
REWORD = re.compile(r"\breword\w*", re.I)
OVERTURN = re.compile(r"\boverturn\w*", re.I)
REOPEN = re.compile(r"\bre-?open\w*|\bopen (?:it|the item|them) again\b|\bopen again\b", re.I)  # "reopen", "open it again"
TURN = re.compile(r"\bturn\b", re.I)
CLOSED = re.compile(r"\bclos\w*", re.I)
SKIP = re.compile(r"\bskip\w*|\bignor\w*", re.I)
ROUTE_AGAIN = re.compile(r"\bre-?rout\w*|\broutes? (?:it|them)\b", re.I)  # "re-route", "route it", "routes them"; not the heading
ARBITER = re.compile(r"\barbiter\w*", re.I)
SKIP_CLAIM = re.compile(r"\bskips?\b", re.I)  # "steps 2 to 4 skip their delete": a step that keeps the answer
# The approved sentence whose delete is a prohibition, not a negation: "is wrong". The negations ("never delete") need no entry:
# NEG_BEFORE reads them. A non-park scope clause is removed before the compare, so the scoped wording matches too.
APPROVED_NEGATED = ("The `kept-answer:` line is the writer-path check: a close that drops `answers/<id>` is wrong.",)


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def blocks(text):
    """Paragraphs and list items. A sentence pair never spans two of them."""
    return [b for b in re.split(r"\n[ \t]*\n|\n(?=[ \t]*(?:- |\d+\. ))", text) if b.strip()]


def sentences(block):
    flat = " ".join(block.split())
    return [s for s in re.split(r"(?<=[.!?])\s+", flat) if s]


def section(text, heading):
    """The section that starts with `heading`, up to the next "## " heading, or "" when the heading is missing."""
    start = text.find(heading)
    if start < 0:
        return ""
    end = text.find("\n## ", start + 1)
    return text[start:] if end < 0 else text[start:end]


def block_starting(text, opening):
    """The Route and close block that starts with `opening`, flattened, or "" when none does."""
    for block in blocks(section(text, ROUTE_HEADING)):
        flat = " ".join(block.split())
        if flat.startswith(opening):
            return flat
    return ""


def block_containing(text, phrase):
    """The Route and close block that holds `phrase`, flattened, or "" when none does."""
    for block in blocks(section(text, ROUTE_HEADING)):
        flat = " ".join(block.split())
        if phrase in flat:
            return flat
    return ""


def answer_deletes(sentence):
    """Each delete verb in the sentence whose object is the answer, as (verb, negated). A verb is negated when `never` or `not`
    is the word right before it. Any other word before it, such as `without`, `to` or `skip`, leaves it a delete."""
    return [(m.group(0), bool(NEG_BEFORE.search(sentence[:m.start()])))
            for m in DELETE_VERB.finditer(sentence) if ANSWER_OBJECT.match(sentence, m.end())]


def names_delete(sentence):
    """True when the sentence names a delete of the answer, negated or not."""
    return bool(answer_deletes(sentence))


def deletes_answer(sentence):
    """True when the sentence deletes the answer: a delete of it that is not negated, in a sentence that is not approved.
    An approved sentence is compared with its non-park scope clause removed."""
    if " ".join(SCOPE_CLAUSE.sub("", sentence).split()) in APPROVED_NEGATED:
        return False
    return any(not negated for _, negated in answer_deletes(sentence))


def is_park(sentence):
    """True when the sentence is about the park branch. A scope that reads non-park or except a park is no park."""
    return bool(PARK.search(NON_PARK.sub(" ", sentence)))


def close_act(sentence):
    """True when the sentence names a close as an act. The heading's own name, "Route and close", is no act."""
    return bool(CLOSE.search(ROUTE_NAME.sub("", sentence)))


def skips_step_two(sentence):
    """True when a `skip` that a delete follows has step 2 in its subject: the words from the last `,`, `;` or `:` before the skip.
    "Steps 2 to 4 skip their delete" names step 2; "so only steps 3 and 4 skip their delete" does not."""
    for m in SKIP_CLAIM.finditer(sentence):
        if not DELETE_VERB.search(sentence[m.end():]):
            continue
        before = sentence[:m.start()]
        start = max(before.rfind(","), before.rfind(";"), before.rfind(":")) + 1
        if STEP_TWO.search(sentence[start:m.start()]):
            return True
    return False


def reopen_deletes(text):
    """The sentences of the text that name a reopen and delete the answer, in the same sentence."""
    return [s for block in blocks(text) for s in sentences(block) if REOPEN.search(s) and deletes_answer(s)]


def close_deletes(text):
    """The sentences that name a close and a delete of the answer, negated or not, outside the park sentences."""
    return [s for block in blocks(text) for s in sentences(block) if not is_park(s) and close_act(s) and names_delete(s)]


def route_deletes(route):
    """The sentences of Route and close, before the park branch, that delete the answer outside the reword and overturn steps. A
    sub-bullet, a standalone paragraph and a sentence of step 2 all count. Steps 3 and 4, the overturn paragraph and a sentence
    that names a reword or an overturn do not."""
    head = route.split(PARK_BRANCH, 1)[0]
    flagged = []
    for block in blocks(head):
        flat = " ".join(block.split())
        for s in sentences(block):
            if not deletes_answer(s):
                continue
            if flat.startswith((REWORD_STEP, CONTEXT_STEP)) or OVERTURN_SENTENCE in flat or REWORD.search(s) or OVERTURN.search(s):
                continue
            flagged.append(s)
    return flagged


class CloseKeepsAnswer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill = read(SKILL)
        cls.route = section(cls.skill, ROUTE_HEADING)
        cls.read = section(cls.skill, READ_HEADING)
        cls.close = block_starting(cls.skill, CLOSE_STEP)

    def route_with(self, anchor, inserted):
        """The Route and close text with `inserted` put before `anchor`, which must hold once in that text."""
        self.assertEqual(self.route.count(anchor), 1, "scope: %r is not in Route and close once" % anchor)
        return self.route.replace(anchor, inserted + anchor, 1)

    def assert_route_flags(self, text, sentence):
        flagged = route_deletes(text)
        self.assertTrue(any(sentence in s for s in flagged), "the route scan does not flag %r; it flags: %s" % (sentence, flagged))

    def test_1_step_2_does_not_delete_the_answer(self):
        self.assertTrue(self.close, "SKILL.md's Route and close has no step 2 that starts with %r" % CLOSE_STEP)
        bad = [s for s in sentences(self.close) if deletes_answer(s)]
        detail = bad[0] if bad else ""
        self.assertFalse(bad, "step 2 (the close) deletes the answer: " + detail)

    def test_2_step_2_says_the_close_keeps_the_answer(self):
        self.assertTrue(self.close, "SKILL.md's Route and close has no step 2 that starts with %r" % CLOSE_STEP)
        keeps = [s for s in sentences(self.close) if KEEP.search(s) and ANSWER_WORD.search(s) and CLOSE.search(s)]
        self.assertTrue(keeps, "step 2 does not say that the close keeps the answer:\n" + self.close)

    def test_3_no_sentence_outside_the_park_branch_says_a_close_deletes_the_answer(self):
        self.assertTrue(self.close, "SKILL.md's Route and close has no step 2, so the close rule has no scope")
        bad = []
        for block in blocks(self.skill):
            bad += [s for s in sentences(block) if not is_park(s) and deletes_answer(s) and (close_act(s) or STEP_TWO.search(s))]
        detail = bad[0] if bad else ""
        self.assertFalse(bad, "%d sentence(s) say a close or step 2 deletes the answer; the first: %s" % (len(bad), detail))

    def test_4_steps_3_and_4_and_the_overturn_still_delete_the_answer(self):
        # The control: a reword, a context change and an overturn still delete the answer (SKILL.md steps 3, 4 and overturn).
        for label, opening in (("step 3", REWORD_STEP), ("step 4", CONTEXT_STEP)):
            block = block_starting(self.skill, opening)
            self.assertTrue(block, "SKILL.md has no %s block that starts with %r" % (label, opening))
            self.assertTrue(any(deletes_answer(s) for s in sentences(block)), "%s no longer deletes answers/<id>:\n%s" % (label, block))
        overturn = block_containing(self.skill, OVERTURN_SENTENCE)
        self.assertTrue(overturn, "SKILL.md has no overturn block that holds %r" % OVERTURN_SENTENCE)
        self.assertTrue(any(deletes_answer(s) for s in sentences(overturn)), "the overturn no longer deletes answers/<id>:\n" + overturn)

    def test_5_no_sentence_says_a_reopen_deletes_the_answer(self):
        self.assertTrue(self.route, "SKILL.md has no Route and close section, so the reopen rule has no scope")
        bad = reopen_deletes(self.skill)
        detail = bad[0] if bad else ""
        self.assertFalse(bad, "%d sentence(s) say a reopen deletes the answer; the first: %s" % (len(bad), detail))

    def test_6_a_delete_of_the_answer_comes_only_from_a_reword_or_an_overturn(self):
        self.assertTrue(self.route, "SKILL.md has no Route and close section, so the delete triggers have no scope")
        says = [s for block in blocks(self.route) for s in sentences(block)
                if names_delete(s) and ONLY.search(s) and REWORD.search(s) and OVERTURN.search(s) and not REOPEN.search(s)]
        self.assertTrue(says, "no Route and close sentence says a delete of the answer comes only from a reword or an overturn, "
                              "and names no reopen")

    def test_7_a_lane_reopen_keeps_the_answer(self):
        self.assertTrue(self.route, "SKILL.md has no Route and close section, so the lane reopen has no scope")
        reopens = [s for block in blocks(self.route) for s in sentences(block)
                   if REOPEN.search(s) and LANE.search(s) and LAST_ANSWER.search(s)]
        self.assertTrue(reopens, "scope: no Route and close sentence reopens an item with lane and lastAnswer")
        kept = [s for s in reopens if KEEP_OR_STAY.search(s) and ANSWER_WORD.search(s)]
        self.assertTrue(kept, "the lane reopen does not say it keeps answers/<id>:\n" + reopens[0])

    def test_8_the_turn_start_read_skips_a_kept_answer_on_a_closed_item(self):
        self.assertTrue(self.read, "SKILL.md has no Read the answers section, so the turn-start read has no scope")
        skips = [s for block in blocks(self.read) for s in sentences(block)
                 if TURN.search(s) and CLOSED.search(s) and SKIP.search(s) and ANSWER_WORD.search(s) and ROUTE_AGAIN.search(s)]
        self.assertTrue(skips, "the turn-start read does not say the owning session skips a kept answer on a closed item "
                               "and does not route it again")

    def test_9_the_helper_flags_a_delete_under_never_close_without(self):
        mutant = "Never close an item without deleting `answers/<id>`."
        self.assertTrue(deletes_answer(mutant), "the helper reads a delete under a negation as no delete: " + mutant)

    def test_10_the_helper_flags_a_delete_after_do_not_forget_to(self):
        mutant = "Do not forget to delete `answers/<id>`."
        self.assertTrue(deletes_answer(mutant), "the helper reads a delete under a negation as no delete: " + mutant)

    def test_11_the_helper_flags_a_delete_after_never_skip(self):
        mutant = "Never skip deleting `answers/<id>`."
        self.assertTrue(deletes_answer(mutant), "the helper reads a delete under a negation as no delete: " + mutant)

    def test_12_the_turn_start_skip_names_the_overturn_of_an_arbiter_ruling(self):
        skips = [s for block in blocks(self.read) for s in sentences(block)
                 if TURN.search(s) and CLOSED.search(s) and SKIP.search(s) and ANSWER_WORD.search(s) and ROUTE_AGAIN.search(s)]
        self.assertTrue(skips, "scope: the turn-start read has no skip sentence, so the overturn exception has no scope")
        exempt = [s for s in skips if OVERTURN.search(s) and ARBITER.search(s)]
        self.assertTrue(exempt, "the turn-start skip has no exception for an overturn of an arbiter ruling: " + skips[0])

    def test_13_no_sentence_says_step_2_skips_its_delete(self):
        skips = [s for block in blocks(self.skill) for s in sentences(block) if SKIP_CLAIM.search(s) and DELETE_VERB.search(s)]
        self.assertTrue(skips, "scope: no sentence says a step skips its delete, so the skip wording has no scope")
        bad = [s for block in blocks(self.skill) for s in sentences(block) if skips_step_two(s)]
        detail = bad[0] if bad else ""
        self.assertFalse(bad, "%d sentence(s) say step 2 skips its delete; the first: %s" % (len(bad), detail))

    def test_14_every_close_sentence_that_names_a_delete_of_the_answer_carries_a_non_park_scope(self):
        targets = close_deletes(self.skill)
        self.assertTrue(targets, "scope: no close sentence names a delete of the answer, so the non-park scope has nothing to check")
        bare = [s for s in targets if not NON_PARK.search(s)]
        self.assertFalse(bare, "%d close sentence(s) name a delete of the answer with no non-park scope; the first: %s"
                         % (len(bare), bare[0] if bare else ""))

    def test_15_route_and_close_deletes_the_answer_only_in_steps_3_and_4_and_the_overturn(self):
        self.assertIn(PARK_BRANCH, self.route, "scope: Route and close has no park branch, so the route scan has no end")
        head = self.route.split(PARK_BRANCH, 1)[0]
        self.assertTrue(all(anchor in head for anchor in (CLOSE_STEP, REWORD_STEP, CONTEXT_STEP, OVERTURN_SENTENCE)),
                        "scope: the route scan does not reach steps 2 to 4 and the overturn")
        bad = route_deletes(self.route)
        self.assertFalse(bad, "Route and close deletes the answer outside steps 3 and 4, the overturn and a reword; the first: %s"
                         % (bad[0] if bad else ""))

    def test_16_the_route_scan_flags_a_delete_sub_bullet_under_step_2(self):
        text = self.route_with("\n3. If the answer is", "\n   - Then delete `answers/<id>`.")
        self.assert_route_flags(text, "Then delete `answers/<id>`.")

    def test_17_the_route_scan_flags_a_standalone_delete_outside_step_2(self):
        text = self.route_with("\n\n1. Write `receipts/<id>`", "\n\nThe writer then deletes `answers/<id>` for good.")
        self.assert_route_flags(text, "The writer then deletes `answers/<id>` for good.")

    def test_18_the_route_scan_flags_a_clear_at_the_end_of_step_2(self):
        text = self.route_with("\n3. If the answer is", " Then clear `answers/<id>`.")
        self.assert_route_flags(text, "Then clear `answers/<id>`.")

    def test_19_the_reopen_check_flags_a_delete_in_the_same_sentence_as_an_open_again(self):
        mutant = "Open it again with `lane` and `lastAnswer`, and delete `answers/<id>`."
        anchor = "\n\n1. Write `receipts/<id>`"
        self.assertEqual(self.skill.count(anchor), 1, "scope: the step 1 anchor is not in SKILL.md once")
        text = self.skill.replace(anchor, "\n\n" + mutant + anchor, 1)
        flagged = reopen_deletes(text)
        self.assertTrue(any(mutant in s for s in flagged), "the reopen check does not flag %r; it flags: %s" % (mutant, flagged))

    def test_20_a_never_or_not_before_the_delete_verb_reads_as_no_delete(self):
        for s in ("A close never deletes the answer; only a reword (steps 3 and 4) or an overturn (step 5) does.",
                  "A non-park close never deletes it; only a reword (steps 3 and 4) or an overturn (step 5) does.",
                  "The `kept-answer:` line is the writer-path check: a non-park close that drops `answers/<id>` is wrong."):
            with self.subTest(s):
                self.assertTrue(names_delete(s), "scope: the sentence names no delete, so the negation has nothing to clear: " + s)
                self.assertFalse(deletes_answer(s), "a negated or approved delete reads as a delete: " + s)

    def test_21_a_non_park_scope_does_not_excuse_a_delete(self):
        for s in ("A non-park close deletes `answers/<id>`.", "A close (except a park) deletes `answers/<id>`.",
                  "A non-park close that drops `answers/<id>` is wrong, and it deletes the answer."):
            with self.subTest(s):
                self.assertTrue(deletes_answer(s), "a scoped delete of the answer reads as no delete: " + s)

    def test_22_a_delete_verb_counts_only_with_the_answer_as_its_object(self):
        for verb in ("delete", "drop", "remove", "discard", "clear", "rm", "unlink"):
            for obj in ("`answers/<id>`", "the answer", "it"):
                s = "Then %s %s." % (verb, obj)
                with self.subTest(s):
                    self.assertTrue(deletes_answer(s), "a %s of the answer reads as no delete: %s" % (verb, s))
        for s in ("When its wait has ended, drop `waits` and keep the answer.", "The session drops `lane` and nothing else.",
                  "Steps 3 and 4 skip their delete, and the writer sets `lastAnswer` from it.",
                  "A `none` answer with a clear direction takes step 3 only.",
                  "The busy-lane rule: a clear page answer (a `none` answer with a clear direction is one) takes the busy-lane path.",
                  "A decision answer is clear only when `page_grant.py` would print `counted` for it.",
                  "For every clear chat answer, it takes steps 1 and 2 in the turn it is read, and closes that turn."):
            with self.subTest(s):
                self.assertFalse(deletes_answer(s), "a verb with no answer as its object reads as a delete: " + s)


if __name__ == "__main__":
    unittest.main()
