#!/usr/bin/env python3
"""Cases for lint/check_step_cites.py, the pure scan of `step:<slug>` cites. Standard library only.

    python3 lint/test_check_step_cites.py

cites(text) -> the sorted unique slugs one text cites. missing(texts, known) -> the sorted slugs the texts cite that `known` lacks,
each once. A cite is `step:<slug>` in inline code, where the slug has the form [a-z0-9][a-z0-9-]*. A cite inside a fenced block is no
cite. A placeholder such as `step:<slug>` and prose such as "next step: foo" are no cite either.
merge/test_lane_lint.py (StepCites) proves the same rules through merge --lane-lint on a pull request. This file proves the scan alone.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import check_step_cites as scan  # noqa: E402  the pure scan under test (lint/check_step_cites.py)


class CitesOfOneText(unittest.TestCase):
    def test_the_sorted_unique_slugs_come_back(self):
        self.assertEqual(scan.cites("`step:beta-one` then `step:alpha-one` and `step:beta-one`"), ["alpha-one", "beta-one"],
                         "cites() does not return the sorted unique slugs of the text")

    def test_an_inline_code_cite_counts(self):
        self.assertEqual(scan.cites("Builds on `step:inline-one`."), ["inline-one"], "an inline-code cite was not read")

    def test_a_bare_cite_in_prose_counts(self):
        self.assertEqual(scan.cites("Builds on step:bare-one in prose."), ["bare-one"], "a bare cite without backticks was not read")

    def test_a_cite_inside_a_backtick_fence_is_no_cite(self):
        self.assertEqual(scan.cites("```\nstep:fenced-one\n```\n"), [], "a cite inside a backtick fence was counted")

    def test_a_cite_inside_a_tilde_fence_is_no_cite(self):
        self.assertEqual(scan.cites("~~~\nstep:tilde-one\n~~~\n"), [], "a cite inside a tilde fence was counted")

    def test_a_cite_after_a_closed_fence_counts(self):
        self.assertEqual(scan.cites("```\nstep:fenced-one\n```\nAfter: `step:after-one`."), ["after-one"],
                         "a cite after a closed fence was not read")

    def test_a_longer_fence_holds_a_shorter_one_inside_it(self):
        self.assertEqual(scan.cites("````\n```\nstep:inner-one\n```\n````\n`step:outer-one`"), ["outer-one"],
                         "a shorter fence inside a longer one closed the fence early")

    def test_a_placeholder_is_no_cite(self):
        self.assertEqual(scan.cites("Write `step:<slug>` there."), [], "the placeholder step:<slug> was read as a cite")

    def test_prose_next_step_is_no_cite(self):
        self.assertEqual(scan.cites("The next step: foo is open."), [], "prose 'next step: foo' was read as a cite")

    def test_a_slug_must_have_the_slug_form(self):
        self.assertEqual(scan.cites("`step:-lead` `step:Upper` `step:ok-1`"), ["ok-1"],
                         "a cite whose slug is not [a-z0-9][a-z0-9-]* was read")

    def test_a_lone_quote_or_a_comment_opener_before_a_cite_does_not_hide_it(self):
        for lead in ("Don't: ", "// ", "# ", "/* ", '"'):
            with self.subTest(lead=lead):
                self.assertEqual(scan.cites(lead + "`step:hidden-one`"), ["hidden-one"],
                                 "a cite after %r was hidden" % lead)

    def test_a_cite_on_a_later_line_counts_after_a_line_with_an_opener(self):
        self.assertEqual(scan.cites("Note // nothing here\n`step:second-line`"), ["second-line"],
                         "a cite on the line after a comment opener was hidden")


class MissingOfTheTexts(unittest.TestCase):
    def test_missing_names_the_cited_slugs_the_known_set_lacks_sorted(self):
        texts = ["`step:zed-one` `step:amy-one`", "`step:amy-one` `step:known-one`"]
        self.assertEqual(scan.missing(texts, {"known-one"}), ["amy-one", "zed-one"],
                         "missing() does not return the sorted cited slugs that the known set lacks")

    def test_a_slug_cited_by_two_texts_is_listed_once(self):
        self.assertEqual(scan.missing(["`step:twice-one`", "`step:twice-one`"], set()), ["twice-one"],
                         "a slug cited by two texts is not listed once")

    def test_a_known_slug_is_never_missing(self):
        self.assertEqual(scan.missing(["`step:known-one`"], {"known-one"}), [], "a known slug was listed as missing")

    def test_no_cite_means_nothing_is_missing(self):
        self.assertEqual(scan.missing(["plain text, no cite"], set()), [], "a text with no cite listed a slug as missing")


if __name__ == "__main__":
    unittest.main()
