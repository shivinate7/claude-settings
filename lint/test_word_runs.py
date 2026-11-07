#!/usr/bin/env python3
"""Fixture test for the one fence pattern of lint/word_runs.py. Run: python3 lint/test_word_runs.py -v

word_runs.FENCE is the one home of a fence line. Each check that reads fences uses it, and none holds a copy of its
own. A fence line indented four spaces or more under a list item is a fence too. Stdlib unittest; no file is read or
written. Rule building-one-home-per-capability.
"""
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
    def test_stale_cites_and_compliance_probes_use_word_runs_fence_and_hold_none_of_their_own(self):
        for module in (stale_cites, compliance_probes):
            with self.subTest(module=module.__name__):
                self.assertIs(getattr(module, "FENCE", word_runs.FENCE), word_runs.FENCE,
                              "%s holds its own FENCE regex; it must read word_runs.FENCE" % module.__name__)


if __name__ == "__main__":
    unittest.main()
