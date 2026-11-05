#!/usr/bin/env python3
"""Prose contract for the waiting page's Park relay: skills/waiting-page/SKILL.md and docs/debts/notes.md.

    python3 -m unittest skills/waiting-page/test_skill_park_relay.py

Reads prose only and runs none of the skill's code. Each case pins one claim:
  1. "Route and close" has a Park sentence that closes an item gated on `lane`.
  2. In the park branch, the writer's send_message tell comes before the close update that drops `lane`.
  3. No sentence has the owning session tell the receiver at its wake after a park.
  4. The debt note relay-park-receiver-untold is gone from docs/debts/notes.md.
  5. In the park branch, a park on an item with no `lane` just closes, and a tell is only for a lane item.
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.realpath(os.path.join(HERE, "..", ".."))
SKILL = os.path.join(HERE, "SKILL.md")
NOTES = os.path.join(REPO, "docs", "debts", "notes.md")

ROUTE_HEADING = "## Route and close"
PARK_BRANCH = re.compile(r'answers/<item id>`[^\n]{0,40}act: "park"')  # the park branch's own anchor
NOTE_ID = "relay-park-receiver-untold"

PARK = re.compile(r"\bpark", re.I)
LANE = re.compile(r"\blane\b", re.I)
CLOSE = re.compile(r"\bclos", re.I)
CLOSE_ITEM = re.compile(r"\bcloses? the item\b", re.I)
CLOSE_UPDATE = re.compile(r"\bcloses? the item\b|\bclose update\b|\bdrops? (?:it\b|`?lane`?)", re.I)
TELL = re.compile(r"\btells?\b|send_message", re.I)
RECEIVER = re.compile(r"\breceiver", re.I)
OWNER = re.compile(r"\bowning\b|\bowner\b|\bwake\b", re.I)
WRITER = re.compile(r"\bwriter\b", re.I)
GATE = re.compile(r"\b(?:when|if)\b", re.I)
NEG = re.compile(r"\b(?:not|never|no|none|nothing|nor)\b|n't\b", re.I)


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


def park_branch(text):
    """The park branch paragraph, flattened, or "" when it is not found."""
    for block in blocks(text):
        flat = " ".join(block.split())
        if PARK_BRANCH.search(flat):
            return flat
    return ""


def route_rules(text):
    """Sentences of "Route and close" outside the park branch. The park branch sits under the same heading and
    names park, lane and close itself, so the Park exception that case 1 reads must come from the other rules."""
    park = park_branch(text)
    out = []
    for block in blocks(route_section(text)):
        flat = " ".join(block.split())
        if flat != park:
            out.extend(sentences(flat))
    return out


def tells_receiver(sentence):
    return bool(TELL.search(sentence) and RECEIVER.search(sentence))


def owner_wake_then_tell(prev, cur):
    """The owning session or its wake is named before a tell to the receiver, a park is named, and nothing is negated.

    The tell's sentence must not name the writer as the teller: the writer telling the receiver is the fix.
    """
    return (bool(OWNER.search(prev)) and tells_receiver(cur) and not WRITER.search(cur)
            and bool(PARK.search(prev) or PARK.search(cur))
            and not (NEG.search(prev) or NEG.search(cur)))


class ParkRelayProse(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill = read(SKILL)
        cls.route = route_section(cls.skill)
        cls.park = park_branch(cls.skill)

    def test_1_route_and_close_has_a_park_exception_gated_on_lane(self):
        self.assertTrue(self.route, "SKILL.md has no '## Route and close' section")
        hits = [s for s in route_rules(self.skill) if PARK.search(s) and LANE.search(s) and CLOSE.search(s)]
        self.assertTrue(hits, "Route and close has no Park exception that closes an item gated on `lane`")

    def test_2_park_tell_comes_before_the_close_that_drops_lane(self):
        self.assertTrue(self.park, "SKILL.md has no park branch (answers/<item id> with act park)")
        tell = self.park.find("send_message")
        self.assertGreaterEqual(tell, 0, "the park branch has no send_message tell to the receiver")
        close = CLOSE_UPDATE.search(self.park)
        self.assertIsNotNone(close, "the park branch has no close update")
        self.assertLess(tell, close.start(),
                        "the park branch sends the receiver its tell after the close update that drops lane")

    def test_3_no_sentence_has_the_owner_tell_the_receiver_at_its_wake_after_a_park(self):
        self.assertTrue(self.park, "SKILL.md has no park branch, so there is no park to scope the scan to")
        found = []
        for block in blocks(self.skill):
            sents = sentences(block)
            for i, cur in enumerate(sents):
                if tells_receiver(cur) and OWNER.search(cur) and PARK.search(cur) and not NEG.search(cur):
                    found.append(cur)
                if i and owner_wake_then_tell(sents[i - 1], cur):
                    found.append(sents[i - 1] + " " + cur)
        self.assertFalse(found, "a sentence has the owning session tell the receiver at its wake after a park: %s"
                         % (found[0] if found else ""))

    def test_4_the_debt_note_for_the_untold_receiver_is_gone(self):
        self.assertFalse(NOTE_ID in read(NOTES), "docs/debts/notes.md still holds the debt note %s" % NOTE_ID)

    def test_5_a_park_on_an_item_with_no_lane_just_closes(self):
        self.assertTrue(self.park, "SKILL.md has no park branch, so there is no park to scope the scan to")
        sents = sentences(self.park)
        self.assertTrue([s for s in sents if CLOSE_ITEM.search(s) and PARK.search(s) and not GATE.search(s)],
                        "the park branch no longer closes a parked item with no condition")
        self.assertTrue([s for s in sents if GATE.search(s) and LANE.search(s)],
                        "the park branch no longer gates the lane drop on the item having `lane`")
        for i, s in enumerate(sents):
            if tells_receiver(s) and not (LANE.search(s) or (i and LANE.search(sents[i - 1]))):
                self.fail("the park branch tells the receiver of a park on an item with no lane: %s" % s)


if __name__ == "__main__":
    unittest.main()
