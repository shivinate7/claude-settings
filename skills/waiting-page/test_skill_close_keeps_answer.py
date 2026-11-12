#!/usr/bin/env python3
"""Prose contract for the waiting page's close: skills/waiting-page/SKILL.md, "Route and close".

    python3 -m unittest skills/waiting-page/test_skill_close_keeps_answer.py

A close keeps the owner's answer. Only a reword (step 3 or 4) or an overturn deletes answers/<id>. Reads prose only and
runs none of the skill's code. Each case pins one claim:
  1. Step 2 (the close) has no sentence that deletes answers/<id>.
  2. Step 2 says the close keeps the answer.
  3. No sentence outside the park sentences says a close, or step 2, deletes answers/<id>.
  4. Steps 3 and 4, and the overturn, still delete answers/<id> (control).

The park branch closes an item and deletes its answer. The rule that a close keeps its answer does not name park, so park
sentences (the ones with the word park) are left out of case 3. Whether park keeps its answer is the owner's call.

A delete counts when the clause it sits in, from the last `;` or `:` before it, names answers/. A close and a delete of
answers/ in one sentence are flagged, so a sentence that closes an item and deletes an answer must say each in its own sentence.
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(HERE, "SKILL.md")

ROUTE_HEADING = "## Route and close"
CLOSE_STEP = "2. Close the item"  # the list item that closes an item
REWORD_STEP = "3. If the answer is"  # the list item for a `none` answer with no clear direction
CONTEXT_STEP = "4. If any other answer"  # the list item for any other answer that is not clear
OVERTURN_SENTENCE = "The ruling's record stands"  # the one sentence of the overturn's delete, in its own block

DELETE = re.compile(r"\bdelet\w*", re.I)
ANSWER_DOC = re.compile(r"answers/", re.I)
ANSWER_WORD = re.compile(r"\banswers?\b", re.I)
CLOSE = re.compile(r"\bclos\w*", re.I)
STEP_TWO = re.compile(r"\bsteps? 2\b", re.I)
KEEP = re.compile(r"\bkeeps?\b|\bkept\b", re.I)
PARK = re.compile(r"\bpark", re.I)
# A negation that governs the delete: "never delete", "does not delete", "skip their delete", "cannot ... delete".
NOT_BEFORE = re.compile(r"\b(?:not|never|no|cannot|skips?|without)\s+(?:\S+\s+){0,2}$|n't\s+(?:\S+\s+){0,2}$", re.I)


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def blocks(text):
    """Paragraphs and list items. A sentence pair never spans two of them."""
    return [b for b in re.split(r"\n[ \t]*\n|\n(?=[ \t]*(?:- |\d+\. ))", text) if b.strip()]


def sentences(block):
    flat = " ".join(block.split())
    return [s for s in re.split(r"(?<=[.!?])\s+", flat) if s]


def route_section(text):
    """The "Route and close" section, up to the next heading, or "" when the heading is missing."""
    start = text.find(ROUTE_HEADING)
    if start < 0:
        return ""
    end = text.find("\n## ", start + 1)
    return text[start:] if end < 0 else text[start:end]


def block_starting(text, opening):
    """The Route and close block that starts with `opening`, flattened, or "" when none does."""
    for block in blocks(route_section(text)):
        flat = " ".join(block.split())
        if flat.startswith(opening):
            return flat
    return ""


def block_containing(text, phrase):
    """The Route and close block that holds `phrase`, flattened, or "" when none does."""
    for block in blocks(route_section(text)):
        flat = " ".join(block.split())
        if phrase in flat:
            return flat
    return ""


def deletes_answer(sentence):
    """True when a `delete` in the sentence acts on answers/ and no negation governs it. The clause of a delete runs from the
    last `;` or `:` before it to the next `;` or `:`, or to the end of the sentence."""
    for m in DELETE.finditer(sentence):
        before = sentence[:m.start()]
        start = max(before.rfind(";"), before.rfind(":")) + 1
        ends = [i for i in (sentence.find(";", m.end()), sentence.find(":", m.end())) if i >= 0]
        clause = sentence[start:min(ends) if ends else len(sentence)]
        if ANSWER_DOC.search(clause) and not NOT_BEFORE.search(before[start:]):
            return True
    return False


class CloseKeepsAnswer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill = read(SKILL)
        cls.close = block_starting(cls.skill, CLOSE_STEP)

    def test_1_step_2_does_not_delete_the_answer(self):
        self.assertTrue(self.close, "SKILL.md's Route and close has no step 2 that starts with %r" % CLOSE_STEP)
        bad = [s for s in sentences(self.close) if deletes_answer(s)]
        detail = bad[0] if bad else ""
        self.assertFalse(bad, "step 2 (the close) deletes answers/<id>: " + detail)

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
        self.assertFalse(bad, "%d sentence(s) say a close or step 2 deletes answers/<id>; the first: %s" % (len(bad), detail))

    def test_4_steps_3_and_4_and_the_overturn_still_delete_the_answer(self):
        # The control: a reword, a context change and an overturn still delete the answer (SKILL.md steps 3, 4 and overturn).
        for label, opening in (("step 3", REWORD_STEP), ("step 4", CONTEXT_STEP)):
            block = block_starting(self.skill, opening)
            self.assertTrue(block, "SKILL.md has no %s block that starts with %r" % (label, opening))
            self.assertTrue(any(deletes_answer(s) for s in sentences(block)), "%s no longer deletes answers/<id>:\n%s" % (label, block))
        overturn = block_containing(self.skill, OVERTURN_SENTENCE)
        self.assertTrue(overturn, "SKILL.md has no overturn block that holds %r" % OVERTURN_SENTENCE)
        self.assertTrue(any(deletes_answer(s) for s in sentences(overturn)), "the overturn no longer deletes answers/<id>:\n" + overturn)


if __name__ == "__main__":
    unittest.main()
