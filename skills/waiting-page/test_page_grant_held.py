#!/usr/bin/env python3
"""Cases for skills/waiting-page/page_grant.py: an answer that names an option the item no longer holds is held.

Ruling R60 (roadmap r60, 15:07 CST Nov 12), part 3: an answer to an item whose letters moved after it was shown is held,
and the owner confirms in words. A decision answer carries `label` ("A: Red") and, from R60, `optionId`, the id of the
option the owner picked. Against the item's option at the answer's `choice` key:
  - with `optionId`, the id must equal that option's id;
  - with no `optionId`, the label's letter must be the option's position letter, and its text the option's label;
  - a choice key the item does not hold is held too.
A held verdict prints one line `held: ...` that says the owner confirms in words, and exits non-zero. The ruling sets no
exit code, so these cases assert only that it is not 0. A matching answer stays `counted`, by its choice.

Red on the current head: each held case prints `counted`, or `not counted` for an absent key, so its assertion fails on
the verdict. The controls stay green.

Each case builds its folders with test_page_grant's helpers (one home), under that module's run folder.

    python3 skills/waiting-page/test_page_grant_held.py
"""
import copy
import json
import os
import shutil
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_page_grant as tpg  # noqa: E402  the checker's fixtures and the Base class (one home)
sys.path.insert(0, os.path.realpath(os.path.join(HERE, "..", "..", "lint")))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (the one home, lint/_test_temp.py)

ABSENT = tpg.ABSENT
ITEM_ID, ITEM_N, AT = tpg.ITEM_ID, tpg.ITEM_N, tpg.AT
# The item's options as the page holds them: position a is Red (id red), position b is Blue (id blue).
OPTIONS = [{"key": "a", "id": "red", "label": "Red"}, {"key": "b", "id": "blue", "label": "Blue"}]
HELD_FRAGMENT = "owner confirms in words"


def setUpModule():
    tpg.RUN_FOLDER = _test_temp.run_folder()  # Base.setUp takes its temp folders from the checker module's run folder


def tearDownModule():
    shutil.rmtree(tpg.RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


def counted(choice, label):
    """The counted line for item 231's answer to `choice`, with the label the item's option carries."""
    return "counted item=%s n=%d choice=%s at=%s label=%s" % (ITEM_ID, ITEM_N, choice, AT, json.dumps(label))


class Answered(tpg.Base):
    def answered(self, answer_fields, pick=tpg.PICK, options=OPTIONS):
        """The checker's verdict for an answer to item 231, whose options are OPTIONS. ABSENT leaves a field out."""
        fetched = self.fetch(items={ITEM_ID: tpg.item(options=copy.deepcopy(options))},
                             answers={ITEM_ID: tpg.answer(**answer_fields)})
        return self.check(self.repo(), fetched, pick=pick)

    def assertHeld(self, r, case):
        lines = r.stdout.splitlines()
        self.assertTrue(lines and lines[0].startswith("held: "),
                        "%s: want a held verdict, got exit %d, stdout %r" % (case, r.returncode, r.stdout))
        self.assertIn(HELD_FRAGMENT, lines[0], "%s: the held line does not say the %s" % (case, HELD_FRAGMENT))
        self.assertNotEqual(r.returncode, 0, "%s: a held answer exits 0, which reads as a grant" % case)


class Held(Answered):
    def test_label_letter_differs_without_option_id_is_held(self):
        """Choice a, label "B: Blue": the letter B is not position a's letter."""
        r = self.answered({"choice": "a", "label": "B: Blue"})
        self.assertHeld(r, "label letter B on choice a, no optionId")

    def test_label_text_differs_without_option_id_is_held(self):
        """Choice a, label "A: Blue": the letter matches, the text is another option's label."""
        r = self.answered({"choice": "a", "label": "A: Blue"})
        self.assertHeld(r, "label text Blue on choice a, no optionId")

    def test_option_id_mismatch_is_held(self):
        """The label reads right, but the id the page saved is blue, and option a's id is red."""
        r = self.answered({"choice": "a", "label": "A: Red", "optionId": "blue"})
        self.assertHeld(r, "optionId blue on choice a, whose id is red")

    def test_choice_key_absent_from_item_is_held(self):
        """Choice c: the item holds only a and b. pick c, so only the held rule can refuse the answer."""
        r = self.answered({"choice": "c", "label": "C: Green"}, pick="c")
        self.assertHeld(r, "choice c, which the item does not hold")


class Controls(Answered):
    def test_option_id_match_is_counted(self):
        r = self.answered({"choice": "a", "label": "A: Red", "optionId": "red"})
        self.assertCounted(r, counted("a", "Red"))

    def test_label_match_without_option_id_is_counted(self):
        r = self.answered({"choice": "a", "label": "A: Red"})
        self.assertCounted(r, counted("a", "Red"))

    def test_answer_with_no_label_or_option_id_is_counted(self):
        r = self.answered({"choice": "a", "label": ABSENT})
        self.assertCounted(r, counted("a", "Red"))

    def test_stored_label_with_a_trailing_space_is_counted(self):
        """The page trims the label it saves ("A: Red"); a stored label "Red " is the same words, not a moved option."""
        spaced = [{"key": "a", "id": "red", "label": "Red "}, {"key": "b", "id": "blue", "label": "Blue"}]
        r = self.answered({"choice": "a", "label": "A: Red"}, options=spaced)
        self.assertCounted(r, counted("a", "Red "))


if __name__ == "__main__":
    unittest.main()
