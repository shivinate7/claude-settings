#!/usr/bin/env python3
"""Controls for skills/waiting-page/page_grant.py: the page's answer `label` is read only to check the choice.

The waiting page saves a readable `label` beside `choice` on each decision answer: "A: <option label>" for a pick,
a list of those for a multi item, "none of these" for none. `choice` stays the key, or the list of keys, and `choice`
decides the grant. These cases pin that page_grant.py counts an answer whose label matches its choice, that a label of
the wrong shape is not read, and that a label naming another option than `choice` is held, not counted (ruling R60, 15:07 CST Nov 12,
exit 3): the owner confirms in words.

The controls are green on the current checker. The held case is red on the commit before the build of ruling R60 (its
commit trailer names that commit). The page tests in skills/waiting-page/tests/page.test.mjs show that the page writes
the label.

    python3 skills/waiting-page/test_page_grant_label.py

Each case builds its folders with test_page_grant's helpers (one home), under that module's run folder.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_page_grant as tpg  # noqa: E402  the checker's fixtures and the Base class (one home)
sys.path.insert(0, os.path.realpath(os.path.join(HERE, "..", "..", "lint")))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (the one home, lint/_test_temp.py)

ITEM_A = "A: Option A"
ITEM_B = "B: Option B"


def setUpModule():
    tpg.RUN_FOLDER = _test_temp.run_folder()  # Base.setUp takes its temp folders from the checker module's run folder


def tearDownModule():
    import shutil
    shutil.rmtree(tpg.RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


class LabelIsNotTheGrant(tpg.Base):
    def test_pick_with_its_own_label_counted(self):
        """A pick-one answer that carries its own label is counted by its choice."""
        r = self.check(self.repo(), self.pair(answer_fields={"label": ITEM_A}), pick="a")
        self.assertCounted(r, tpg.verdict("a"))

    def test_label_naming_another_option_is_held_not_counted(self):
        """The label names option B, the choice is a: the answer names an option the item no longer holds at key a, so
        it is held (exit 3) and is not a grant. The owner confirms in words which option he meant."""
        r = self.check(self.repo(), self.pair(answer_fields={"label": ITEM_B}), pick="a")
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue(r.stdout.startswith("held: "))

    def test_label_that_is_a_list_on_a_pick_one_answer_is_not_read(self):
        """A label of the wrong shape is still not read: the choice alone is the grant."""
        r = self.check(self.repo(), self.pair(answer_fields={"label": [ITEM_A]}), pick="a")
        self.assertCounted(r, tpg.verdict("a"))

    def test_multi_list_with_a_list_of_labels_counted_by_its_keys(self):
        """A multi item's answer carries a list of labels beside its list of keys: the keys are the grant."""
        item = tpg.item(multi=True, options=tpg.options("abc"))
        answer = tpg.answer(choice=["a", "b"], label=[ITEM_A, ITEM_B])
        r = self.check(self.repo(), self.fetch(items={tpg.ITEM_ID: item}, answers={tpg.ITEM_ID: answer}), pick="a+b")
        self.assertCounted(r, tpg.verdict("a+b"))

    def test_label_with_no_matching_pick_is_not_counted(self):
        """A label that says A does not make a choice of b a grant for a pick of a: --pick still decides."""
        r = self.check(self.repo(), self.pair(answer_fields={"choice": "b", "label": ITEM_A}), pick="a")
        self.assertNotCounted(r, "a label naming a, choice b, against pick a", "pick")


if __name__ == "__main__":
    unittest.main()
