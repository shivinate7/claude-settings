#!/usr/bin/env python3
"""Prose contract for the waiting page: skills/waiting-page/SKILL.md (its Park relay and option labels) and docs/debts/notes.md.

    python3 -m unittest skills/waiting-page/test_skill_park_relay.py

Reads prose only and runs none of the skill's code. Each case pins one claim:
  1. "Route and close" has a Park sentence that closes an item gated on `lane`, outside the park branch.
  2. In the park branch, the writer's send_message tell comes before the close update that drops `lane`.
  3. No sentence has the owning session send or tell the receiver at its wake after a park.
  4. The untold-receiver note no longer says the receiver cannot be found while a close drops `lane`.
  5. In the park branch, every message is under a `lane` condition, and a park on an item with no `lane` just closes.
  6. The park tell names only the page URL, the item id and the act withdrawn, never the answer's note or text.
  7. The decision's option bullet (the one with the option shape `{key, label, how`) says a settings-change option's
     label names settings.json and the entry.
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
RECEIVER = re.compile(r"\breceiver", re.I)
OWNING_SESSION = re.compile(r"\bowning session\b", re.I)
OWNER = re.compile(r"\bowning\b|\bowner\b|\bwake\b", re.I)
WAKE = re.compile(r"\bwake\b", re.I)
WRITER = re.compile(r"\bwriter\b", re.I)
CONDITION_WORDS = re.compile(r"\b(?:when|if)\b", re.I)
NEG = re.compile(r"\b(?:not|never|no|none|nothing|nor)\b|n't\b", re.I)
# Case 3's verbs: a message to the receiver, by any of these.
TELL_VERB = re.compile(r"\btells?\b|\bsends?\b|\bmessag\w*|\bnotif(?:y|ies|ied)\b|send_message", re.I)
# Case 5's trigger: a sentence that sends or names a message, or a withdrawn act.
MESSAGE_ACT = re.compile(r"send_message|\btells?\b|\bsends?\b|\bmessag\w*|\bnotif\w*|\bwithdrawn\b", re.I)
SEND_MESSAGE = re.compile(r"send_message", re.I)
NOTE_OR_TEXT = re.compile(r"\bnote\b|\btext\b", re.I)
PAGE_URL = re.compile(r"\burl\b", re.I)
ITEM_ID = re.compile(r"\bitem id\b", re.I)
WITHDRAWN = re.compile(r"\bwithdrawn\b", re.I)
# Case 4: the old claim, a receiver that cannot be found, tied to a close that drops lane.
OLD_FIND = re.compile(r"\b(?:cannot|can't|can not|unable to)\s+find\s+the\s+receiver\b", re.I)
DROP_LANE = re.compile(r"\bdrops?\b[^.]{0,60}\blane\b", re.I)
# Case 7: the option field list starts the decision's option bullet. Only its start is pinned, so a field added after
# `how` does not move the anchor. The label names the settings file and the entry, in code or plain text.
OPTION_SHAPE = "{key, label, how"
SETTINGS_LABEL = re.compile(r"label names `?settings\.json`? and the entry", re.I)


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


def note_entry(text):
    """The notes.md bullet for NOTE_ID, flattened, or "" when the note is gone."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("- " + NOTE_ID):
            entry = [line]
            for more in lines[i + 1:]:
                if not more.strip() or more.startswith(("- ", "#")):
                    break
                entry.append(more)
            return " ".join(" ".join(entry).split())
    return ""


def tells_receiver(sentence):
    return bool(TELL_VERB.search(sentence) and RECEIVER.search(sentence))


def owner_wake_then_tell(prev, cur):
    """The owning session or its wake is named before a tell to the receiver, a park is named, and nothing is negated.

    The tell's sentence must not name the writer as the teller: the writer telling the receiver is the fix.
    """
    return (bool(OWNER.search(prev)) and tells_receiver(cur) and not WRITER.search(cur)
            and bool(PARK.search(prev) or PARK.search(cur))
            and not (NEG.search(prev) or NEG.search(cur)))


def owning_wake_sends_after_park(sentence):
    """The owning session and its wake, a park, and a message verb in one sentence, with nothing negated."""
    return bool(OWNING_SESSION.search(sentence) and WAKE.search(sentence) and PARK.search(sentence)
                and TELL_VERB.search(sentence) and not NEG.search(sentence))


def lane_gated(sents, i):
    """Sentence i sits under a lane condition: it names lane with a condition or a negation, or the nearest
    earlier sentence with a condition (the one that opens the block) names lane."""
    if LANE.search(sents[i]) and (CONDITION_WORDS.search(sents[i]) or NEG.search(sents[i])):
        return True
    for j in range(i - 1, -1, -1):
        if CONDITION_WORDS.search(sents[j]):
            return bool(LANE.search(sents[j]))
    return False


def option_bullet(text):
    """The decision's option bullet: the two-space `- ` item holding OPTION_SHAPE, with its indented sub-bullets, up to the
    next sibling bullet or heading. "" when no bullet holds it."""
    start = text.find(OPTION_SHAPE)
    if start < 0:
        return ""
    head = text.rfind("\n  - ", 0, start)
    if head < 0:
        return ""
    stops = [i for i in (text.find("\n  - ", start), text.find("\n## ", start)) if i >= 0]
    return text[head + 1:min(stops) if stops else len(text)]


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

    def test_3_no_sentence_has_the_owner_send_or_tell_the_receiver_at_its_wake_after_a_park(self):
        self.assertTrue(self.park, "SKILL.md has no park branch, so there is no park to scope the scan to")
        found = []
        for block in blocks(self.skill):
            sents = sentences(block)
            for i, cur in enumerate(sents):
                if tells_receiver(cur) and OWNER.search(cur) and PARK.search(cur) and not NEG.search(cur):
                    found.append(cur)
                if owning_wake_sends_after_park(cur):
                    found.append(cur)
                if i and owner_wake_then_tell(sents[i - 1], cur):
                    found.append(sents[i - 1] + " " + cur)
        self.assertFalse(found, "a sentence has the owning session send or tell the receiver at its wake after a park: %s"
                         % (found[0] if found else ""))

    def test_4_the_untold_receiver_note_no_longer_says_a_close_drops_lane_when_the_receiver_cannot_be_found(self):
        entry = note_entry(read(NOTES))
        self.assertFalse(OLD_FIND.search(entry) and DROP_LANE.search(entry),
                         "docs/debts/notes.md note %s still says the receiver cannot be found while a close drops lane"
                         % NOTE_ID)

    def test_5_every_message_in_the_park_branch_is_under_a_lane_condition(self):
        self.assertTrue(self.park, "SKILL.md has no park branch, so there is no park to scope the scan to")
        sents = sentences(self.park)
        self.assertTrue([s for s in sents if CLOSE_ITEM.search(s) and PARK.search(s) and not CONDITION_WORDS.search(s)],
                        "the park branch no longer closes a parked item with no condition")
        self.assertTrue([s for s in sents if CONDITION_WORDS.search(s) and LANE.search(s)],
                        "the park branch no longer gates the lane drop on the item having `lane`")
        for i, s in enumerate(sents):
            if MESSAGE_ACT.search(s) and not lane_gated(sents, i):
                self.fail("the park branch has a message that is not under a lane condition: %s" % s)

    def test_6_the_park_tell_names_only_the_page_url_the_item_id_and_the_act_withdrawn(self):
        self.assertTrue(self.park, "SKILL.md has no park branch, so there is no park to scope the scan to")
        tells = [s for s in sentences(self.park) if SEND_MESSAGE.search(s)]
        self.assertTrue(tells, "the park branch has no send_message tell to check")
        self.assertFalse([s for s in tells if NOTE_OR_TEXT.search(s)],
                         "the park tell names the answer's note or text: %s" % (tells[0] if tells else ""))
        self.assertTrue(any(PAGE_URL.search(s) and ITEM_ID.search(s) and WITHDRAWN.search(s) for s in tells),
                        "the park tell does not name the page URL, the item id and the act withdrawn")


class OptionLabelGuidance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bullet = option_bullet(read(SKILL))

    def test_7_option_label_names_settings_json_and_the_entry(self):
        self.assertTrue(self.bullet, "SKILL.md has no decision option bullet with the option shape `{key, label, how`")
        self.assertRegex(self.bullet, SETTINGS_LABEL,
                         "the option guidance does not say a settings-change option's label names settings.json and the entry")


if __name__ == "__main__":
    unittest.main()
