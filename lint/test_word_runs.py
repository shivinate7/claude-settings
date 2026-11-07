#!/usr/bin/env python3
"""Fixture test for the one fence pattern of lint/word_runs.py. Run: python3 lint/test_word_runs.py -v

word_runs.FENCE is the one home of a fence line. Each check that reads fences uses it, and none holds a copy of its
own. A fence line indented four spaces or more under a list item is a fence too. Stdlib unittest; no file is read or
written. Rule building-one-home-per-capability.
"""
import os
import re
import sys
import unittest

import compliance_probes
import stale_cites
import word_runs

DEEP_FENCES = ("    ```", "    ~~~", "        ```text", "      ~~~")  # four spaces or more, backtick or tilde
SHALLOW_FENCES = ("```", "   ~~~")  # at most three spaces: read before and after the change
NOT_FENCES = ("    text", "    ``")  # a fence needs three marks, and an indented line of text is no fence


class FenceLineTests(unittest.TestCase):
    def test_a_fence_line_indented_four_spaces_or_more_is_a_fence(self):
        missed = [line for line in DEEP_FENCES if word_runs.FENCE.match(line) is None]
        self.assertEqual(missed, [], "word_runs.FENCE misses a fence line indented four spaces or more; it reads three "
                                     "spaces at most")

    def test_a_fence_line_of_three_spaces_or_less_is_a_fence_and_prose_is_not(self):
        self.assertEqual([line for line in SHALLOW_FENCES if word_runs.FENCE.match(line) is None], [], "control")
        self.assertEqual([line for line in NOT_FENCES if word_runs.FENCE.match(line) is not None], [], "control")


class OneFenceHomeTests(unittest.TestCase):
    def test_stale_cites_and_compliance_probes_read_word_runs_fence_and_hold_no_fence_pattern_of_their_own(self):
        for module in (stale_cites, compliance_probes):
            with self.subTest(module=module.__name__):
                # The scope first: the module exposes FENCE at all. Then the subject: that name is the one home.
                self.assertTrue(hasattr(module, "FENCE"), "%s exposes no FENCE; alias word_runs.FENCE" % module.__name__)
                self.assertIs(module.FENCE, word_runs.FENCE,
                              "%s holds its own FENCE regex; it must read word_runs.FENCE" % module.__name__)
                # A fence pattern under another name is a copy too.
                renamed = [name for name, value in vars(module).items() if isinstance(value, re.Pattern)
                           and value is not word_runs.FENCE and any(value.match(line) for line in DEEP_FENCES)]
                self.assertEqual(renamed, [], "%s holds a fence pattern of its own under another name" % module.__name__)


class MovedFenceCopiesTests(unittest.TestCase):
    def test_each_moved_fence_copy_is_word_runs_fence(self):
        # check_skill_model_rows and feedback_guard read the one fence line. The other copies keep their own
        # 0-3 space rule (see their pins), so they are not listed here.
        hooks = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks")
        if hooks not in sys.path:
            sys.path.insert(0, hooks)
        import check_skill_model_rows
        import feedback_guard
        for module in (check_skill_model_rows, feedback_guard):
            with self.subTest(module=module.__name__):
                # The scope first: the module exposes FENCE at all. Then the subject: that name is the one home.
                self.assertTrue(hasattr(module, "FENCE"), "%s exposes no FENCE; alias word_runs.FENCE" % module.__name__)
                self.assertIs(module.FENCE, word_runs.FENCE,
                              "%s holds its own FENCE regex; it must read word_runs.FENCE" % module.__name__)


if __name__ == "__main__":
    unittest.main()
