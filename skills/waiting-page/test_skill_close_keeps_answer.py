#!/usr/bin/env python3
"""Prose contract for the waiting page's close: skills/waiting-page/SKILL.md, "Route and close" and "Read the answers".

    python3 -m unittest skills/waiting-page/test_skill_close_keeps_answer.py

A close keeps the owner's answer. Only a reword (step 3 or 4) or an overturn deletes the answer, and a lane reopen keeps it.
Reads prose only and runs none of the skill's code. Each case pins one claim:
  1. Step 2 (the close) has no sentence that deletes the answer, however worded.
  2. Step 2 says the close keeps the answer.
  3. No sentence outside the park sentences says a close, or step 2, deletes the answer, however worded.
  4. Steps 3 and 4, and the overturn, still delete the answer (control).
  5. No sentence says a reopen deletes the answer.
  6. A sentence says a delete of the answer comes only from a reword or an overturn, and names no reopen.
  7. The lane reopen (reopen with lane and lastAnswer) says the answer is kept.
  8. The turn-start read says the owning session skips a kept answer on a closed item and does not route it again.

The park branch closes an item and deletes its answer. The rule that a close keeps its answer does not name park, so park
sentences (the ones with the word park) are left out of case 3. Whether park keeps its answer is the owner's call.

A delete counts when the clause it sits in, from the last `;` or `:` before it to the next `;` or `:`, names the answer
(answers/<id>, the answer, the answers), or when a delete's object is `it` or `them`. A drop, remove or discard counts only
when the clause names the answer. A close and a delete of the answer in one sentence are flagged, so a sentence that closes
an item and deletes an answer must say each in its own sentence.

Ruling: triage, 15:01 CST Nov 12 (pick a: page_grant rule 4 stays, lane checks run before close, park unchanged, kept-answer
line stays without delete remedy), recorded at roadmap commit 23559d419.
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(HERE, "SKILL.md")

ROUTE_HEADING = "## Route and close"
READ_HEADING = "## Read the answers"
CLOSE_STEP = "2. Close the item"  # the list item that closes an item
REWORD_STEP = "3. If the answer is"  # the list item for a `none` answer with no clear direction
CONTEXT_STEP = "4. If any other answer"  # the list item for any other answer that is not clear
OVERTURN_SENTENCE = "The ruling's record stands"  # the one sentence of the overturn's delete, in its own block

DELETE_VERB = re.compile(r"\b(?:delet|drop|remov|discard|eras|purg|wip)\w*", re.I)
ANSWER_WORD = re.compile(r"\banswers?\b", re.I)  # answers/<id>, the answer, the answers; never lastAnswer
IT = re.compile(r"\b(?:it|them)\b", re.I)  # the answer as the object of a delete, as in "the writer deletes it"
CLOSE = re.compile(r"\bclos\w*", re.I)
STEP_TWO = re.compile(r"\bsteps? 2\b", re.I)
KEEP = re.compile(r"\bkeeps?\b|\bkept\b", re.I)
KEEP_OR_STAY = re.compile(r"\bkeeps?\b|\bkept\b|\bstays?\b|\bremains?\b|\bin place\b", re.I)
PARK = re.compile(r"\bpark", re.I)
REOPEN = re.compile(r"\breopen\w*", re.I)
LANE = re.compile(r"\blane\b", re.I)
LAST_ANSWER = re.compile(r"\blastAnswer\b")
ONLY = re.compile(r"\bonly\b", re.I)
REWORD = re.compile(r"\breword\w*", re.I)
OVERTURN = re.compile(r"\boverturn\w*", re.I)
TURN = re.compile(r"\bturn\b", re.I)
CLOSED = re.compile(r"\bclos\w*", re.I)
SKIP = re.compile(r"\bskip\w*|\bignor\w*", re.I)
ROUTE_AGAIN = re.compile(r"\bre-?rout\w*|\broutes? (?:it|them)\b", re.I)  # "re-route", "route it", "routes them"; not the heading
# A negation that governs the delete: "never delete", "does not delete", "skip their delete", "cannot ... delete".
NOT_BEFORE = re.compile(r"\b(?:not|never|no|cannot|skips?|without)\s+(?:\S+\s+){0,2}$|n't\s+(?:\S+\s+){0,2}$", re.I)
# A prohibition after the verb: "a close that drops answers/<id> is wrong" forbids the drop, so it is no instruction.
FORBIDDEN_AFTER = re.compile(r"\b(?:is|are) (?:wrong|a mistake|not allowed)\b", re.I)


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


def deletes_answer(sentence):
    """True when a delete, drop, remove or discard in the sentence acts on the answer, and no negation governs it. The clause of
    the verb runs from the last `;` or `:` before it to the next `;` or `:`, or to the end of the sentence. A clause that names
    the answer counts. A delete whose clause says `it` or `them` counts too. A verb that a prohibition follows is no delete."""
    for m in DELETE_VERB.finditer(sentence):
        before = sentence[:m.start()]
        start = max(before.rfind(";"), before.rfind(":")) + 1
        ends = [i for i in (sentence.find(";", m.end()), sentence.find(":", m.end())) if i >= 0]
        end = min(ends) if ends else len(sentence)
        clause = sentence[start:end]
        is_delete = m.group(0).lower().startswith("delet")
        names_answer = ANSWER_WORD.search(clause) or (is_delete and IT.search(clause))
        if names_answer and not NOT_BEFORE.search(before[start:]) and not FORBIDDEN_AFTER.search(sentence[m.end():end]):
            return True
    return False


class CloseKeepsAnswer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill = read(SKILL)
        cls.route = section(cls.skill, ROUTE_HEADING)
        cls.read = section(cls.skill, READ_HEADING)
        cls.close = block_starting(cls.skill, CLOSE_STEP)

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
            bad += [s for s in sentences(block) if not PARK.search(s) and deletes_answer(s) and (CLOSE.search(s) or STEP_TWO.search(s))]
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
        bad = [s for block in blocks(self.skill) for s in sentences(block) if REOPEN.search(s) and deletes_answer(s)]
        detail = bad[0] if bad else ""
        self.assertFalse(bad, "%d sentence(s) say a reopen deletes the answer; the first: %s" % (len(bad), detail))

    def test_6_a_delete_of_the_answer_comes_only_from_a_reword_or_an_overturn(self):
        self.assertTrue(self.route, "SKILL.md has no Route and close section, so the delete triggers have no scope")
        says = [s for block in blocks(self.route) for s in sentences(block)
                if deletes_answer(s) and ONLY.search(s) and REWORD.search(s) and OVERTURN.search(s) and not REOPEN.search(s)]
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


if __name__ == "__main__":
    unittest.main()
