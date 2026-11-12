#!/usr/bin/env python3
"""Prose contract for who watches the waiting page: skills/waiting-page/SKILL.md, "Read the answers".

    python3 skills/waiting-page/test_skill_watch_writer.py

Only the page's writer watches the page (owner, R18, Nov 10: "too many sessions seem too tapped in to the
artifact"). Each case pins one claim, one sentence at a time:
  1. "Read the answers" has a sentence that says only the writer watches the page.
  2. No sentence in SKILL.md gives a watch to a session other than the writer (foreign_watch).
  3. "Read the answers" has a sentence that says every other session never watches the page.
  4. "Read the answers" has a sentence that says a session other than the writer learns of an answer from the
     writer's message, which carries the page URL, the item id and the act.
  5. Control, holds on main: "Read the answers" keeps the turn-start read as the fallback.

foreign_watch is the one home of the watch rule. test_scaffold.py imports it for the hand-off template,
the operating model's rotation and the check's docstring.
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from test_skill_park_relay import blocks, read, sentences  # noqa: E402  the one home of the prose splitter

SKILL = os.path.join(HERE, "SKILL.md")
READ_HEADING = "## Read the answers"
# A watch verb: `watch`, `watches`, `watching`, the infinitive, or the action in backticks. Not the `Watch:` field
# and not the noun in "the watch bullet".
WATCH_VERB = re.compile(r"\bwatch(?:es|ing)?\b(?!:)(?!\s+bullet\b)", re.I)
WRITER = re.compile(r"\bwriter\b", re.I)
ONLY_WRITER = re.compile(r"\bonly the writer\b", re.I)
# The writer named as the one who watches: "the writer watches", "the writer's watch", "for the writer to watch".
WRITER_WATCH = re.compile(r"\bwriter(?:'s)?\s+(?:\S+\s+)?(?:to\s+)?watch(?:es)?\b", re.I)
# "never" must sit beside the watch: a "never" elsewhere in a sentence does not keep the others from watching.
NEVER_WATCH = re.compile(r"\bnever\s+(?:\S+\s+){0,2}?watch|\bno other sessions?\b[^.]*\bwatch", re.I)
# Other words that keep the other sessions from watching. "no writer" is a rotation gap, not a watch for anyone else.
NOT_OTHERS = re.compile(r"\b(?:does|do) not\s+(?:\S+\s+){0,2}?watch|\bno session but\b|\bno writer\b|\bnobody\b"
                        r"|\bonly the writer\b", re.I)
# The subject of a sentence is its text before the first clause break.
SUBJECT_END = re.compile(r"[,;:(]|\b(?:when|if)\b", re.I)
LEARNS = re.compile(r"\b(?:learns?|hears?|told)\b", re.I)
MESSAGE = re.compile(r"\bmessage\b|send_message", re.I)
PAGE_LINK = re.compile(r"\bpage (?:URL|link)\b", re.I)
ITEM_ID = re.compile(r"\bitem id\b", re.I)
ACT = re.compile(r"\bact\b", re.I)
RECEIVER = re.compile(r"\b(?:session|owner|receiver)\b", re.I)


def section(text, heading):
    """The section that starts at `heading`, up to the next `## ` heading, or "" when the heading is missing."""
    start = text.find(heading)
    if start < 0:
        return ""
    end = text.find("\n## ", start + 1)
    return text[start:] if end < 0 else text[start:end]


def prose_sentences(text):
    """The sentences of a prose text, judged one list item or paragraph at a time, so a heading never joins a sentence."""
    return [s for block in blocks(text) for s in sentences(block)]


def subject(sentence):
    m = SUBJECT_END.search(sentence)
    return sentence[:m.start()] if m else sentence


def foreign_watch(text):
    """The sentences of `text` that give a watch to a session other than the writer: a watch verb, no writer in the
    subject, and no word that keeps the other sessions from watching. Each sentence is judged alone."""
    return [s for s in prose_sentences(text)
            if WATCH_VERB.search(s) and not WRITER.search(subject(s))
            and not (WRITER_WATCH.search(s) or NEVER_WATCH.search(s) or NOT_OTHERS.search(s))]


class WatchWriterOnly(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill = read(SKILL)
        cls.answers = section(cls.skill, READ_HEADING)

    def test_1_read_the_answers_says_only_the_writer_watches_the_page(self):
        self.assertTrue(self.answers, "SKILL.md has no '## Read the answers' section")
        hits = [s for s in prose_sentences(self.answers) if ONLY_WRITER.search(s) and WATCH_VERB.search(s)]
        self.assertTrue(hits, "Read the answers has no sentence that says only the writer watches the page")

    def test_2_no_sentence_gives_a_watch_to_a_session_other_than_the_writer(self):
        self.assertTrue(self.skill, "SKILL.md is missing or empty")
        found = foreign_watch(self.skill)
        self.assertFalse(found, f"a sentence gives a watch to a session other than the writer: {found[0] if found else ''}")

    def test_3_read_the_answers_says_every_other_session_never_watches_the_page(self):
        self.assertTrue(self.answers, "SKILL.md has no '## Read the answers' section")
        hits = [s for s in prose_sentences(self.answers) if NEVER_WATCH.search(s)]
        self.assertTrue(hits, "Read the answers has no sentence that says every other session never watches the page")

    def test_4_a_session_that_is_not_the_writer_learns_of_an_answer_from_the_writers_message(self):
        self.assertTrue(self.answers, "SKILL.md has no '## Read the answers' section")
        hits = [s for s in prose_sentences(self.answers)
                if LEARNS.search(s) and MESSAGE.search(s) and PAGE_LINK.search(s) and ITEM_ID.search(s)
                and ACT.search(s) and RECEIVER.search(s)]
        self.assertTrue(hits, "Read the answers has no sentence that says a session other than the writer learns of "
                              "an answer from the writer's message (page URL, item id, act)")

    def test_5_read_the_answers_keeps_the_turn_start_read_as_the_fallback(self):
        self.assertTrue(self.answers, "SKILL.md has no '## Read the answers' section")
        self.assertIn("fallback", self.answers, "Read the answers lost the fallback word for the turn-start read")
        self.assertRegex(self.answers, r"(?i)start of each turn|turn-start",
                         "Read the answers no longer names the turn-start read")


if __name__ == "__main__":
    unittest.main()
